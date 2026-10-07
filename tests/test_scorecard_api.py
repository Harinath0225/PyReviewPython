"""Tests for the Agent Scorecard API endpoints and evaluation persistence."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from google.adk.evaluation.eval_case import IntermediateData, Invocation
from google.adk.evaluation.eval_metrics import EvalMetricResult, EvalMetricResultPerInvocation
from google.adk.evaluation.eval_result import EvalCaseResult, EvalSetResult
from google.adk.evaluation.evaluator import EvalStatus
from google.genai import types

import agent.evaluation_history_store as store_module
import backend.app.routes.review as review_routes
from agent.evaluation_history_store import EvaluationHistoryStore
from backend.app.main import create_app


@pytest.fixture()
def agents_dir(tmp_path, monkeypatch):
    path = tmp_path / "agents"
    path.mkdir()
    monkeypatch.setenv("ADK_AGENTS_DIR", str(path))
    return path


@pytest.fixture()
def client(tmp_path, monkeypatch, agents_dir) -> TestClient:
    store = EvaluationHistoryStore(sqlite_path=str(tmp_path / "eval_history.sqlite3"))
    monkeypatch.setattr(store_module, "_default_store", store)
    return TestClient(create_app())


def _run_evaluation(client: TestClient, noise: dict | None = None) -> dict:
    payload = {
        "prompt": "Review this Python backend code for critical vulnerabilities.",
        "code_snippet": (
            "import sqlite3\n"
            "def get_user(username):\n"
            "    conn = sqlite3.connect('users.db')\n"
            "    cursor = conn.cursor()\n"
            f"    cursor.execute(f\"SELECT * FROM users WHERE username = '{{username}}'\")\n"
            "    return cursor.fetchall()\n"
        ),
        "scenario_id": "sec_multi_vuln",
    }
    if noise:
        payload["noise_config"] = noise
    response = client.post("/api/v1/agent/evaluate", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def test_evaluate_injects_agent_dna_and_session(client: TestClient) -> None:
    result = _run_evaluation(client)
    assert result["session_id"].startswith("eval-")
    dna = result["agent_dna"]
    assert set(dna) == {"base_model", "harness", "sub_agents", "environment"}
    assert dna["harness"] == "google-adk-custom-loop"
    assert result["verifier_type"] in {"hard", "soft", "hybrid"}
    assert "execution" in result["capabilities"]
    assert result["efficiency"]["steps"] > 0


def test_evaluate_with_noise_injection(client: TestClient) -> None:
    result = _run_evaluation(
        client,
        noise={"latency_ms": 100, "fault_rate": 1.0, "mutate_prompt": True, "seed": 42},
    )
    assert result["noise"] is not None
    assert result["noise"]["simulated_faults"]
    assert "robustness" in result["dimensions"]


def test_scorecard_summary_after_runs(client: TestClient) -> None:
    _run_evaluation(client)
    response = client.get("/api/evaluations/scorecard-summary")
    assert response.status_code == 200
    data = response.json()
    assert data["total_runs"] == 1
    assert 0 <= data["capability_score"] <= 100
    assert 0 <= data["reliability_index"] <= 100
    assert data["agent_dna"]["harness"] == "google-adk-custom-loop"


def test_reliability_metrics_shape(client: TestClient) -> None:
    _run_evaluation(client)
    response = client.get("/api/evaluations/reliability-metrics")
    assert response.status_code == 200
    data = response.json()
    for key in ("reliability_index", "consistency", "robustness", "predictability", "safety", "adaptability_grid"):
        assert key in data
    assert "execution" in data["adaptability_grid"]


def test_efficiency_metrics(client: TestClient) -> None:
    _run_evaluation(client)
    response = client.get("/api/evaluations/efficiency-metrics")
    assert response.status_code == 200
    data = response.json()
    assert data["total_runs"] == 1
    assert data["steps_median"] > 0
    assert data["prompt_tokens_total"] > 0


def test_trajectory_roundtrip_and_404(client: TestClient) -> None:
    result = _run_evaluation(client)
    session_id = result["session_id"]

    response = client.get(f"/api/evaluations/trajectories/{session_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == session_id
    assert data["trajectory"]["steps"]
    assert data["verifier_type"] in {"hard", "soft", "hybrid"}

    missing = client.get("/api/evaluations/trajectories/does-not-exist")
    assert missing.status_code == 404


def test_list_runs(client: TestClient) -> None:
    _run_evaluation(client)
    response = client.get("/api/evaluations/runs")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 1
    assert data["runs"][0]["verifier_type"] in {"hard", "soft", "hybrid"}
    assert data["runs"][0]["source"] == "agent_lab"


# ---------------------------------------------------------------------------
# Multi-source aggregation (Agent Lab, ADK Web UI evals, code reviews)
# ---------------------------------------------------------------------------

def _invocation(tools: list[str], answer: str) -> Invocation:
    return Invocation(
        user_content=types.Content(parts=[types.Part.from_text(text="Review this code for injection")]),
        final_response=types.Content(parts=[types.Part.from_text(text=answer)]),
        intermediate_data=IntermediateData(
            tool_uses=[types.FunctionCall(name=name, args={"code_snippet": "x = 1"}) for name in tools],
            tool_responses=[types.FunctionResponse(name=name, response={"findings": 2}) for name in tools],
        ),
    )


def _metric(name: str, score: float | None, status: EvalStatus, threshold: float = 0.5) -> EvalMetricResult:
    return EvalMetricResult(metric_name=name, threshold=threshold, score=score, eval_status=status)


def _write_adk_result(agents_dir, name: str = "app_set_1.evalset_result.json") -> None:
    app = agents_dir / "demo_agent"
    (app / ".adk" / "eval_history").mkdir(parents=True)
    (app / "test_config.json").write_text(
        json.dumps({"agent_dna": {"base_model": "test-model", "harness": "adk-web", "sub_agents": [], "environment": {}}}),
        encoding="utf-8",
    )
    passing = EvalCaseResult(
        eval_set_id="set",
        eval_id="eval_sql_injection_defense",
        final_eval_status=EvalStatus.PASSED,
        overall_eval_metric_results=[_metric("tool_trajectory_avg_score", 1.0, EvalStatus.PASSED)],
        eval_metric_result_per_invocation=[
            EvalMetricResultPerInvocation(
                actual_invocation=_invocation(["scan_python_code"], "Use parameterized queries."),
                expected_invocation=_invocation(["scan_python_code"], "Use parameterized queries."),
            )
        ],
        session_id="s1",
    )
    failing = EvalCaseResult(
        eval_set_id="set",
        eval_id="eval_business_requirement_traceability",
        final_eval_status=EvalStatus.FAILED,
        overall_eval_metric_results=[
            _metric("response_match_score", 0.2, EvalStatus.FAILED),
            _metric("rubric_based_final_response_quality_v1", 0.6, EvalStatus.PASSED),
            _metric("hallucinations_v1", None, EvalStatus.NOT_EVALUATED),
        ],
        eval_metric_result_per_invocation=[
            EvalMetricResultPerInvocation(
                actual_invocation=_invocation(["scan_python_code", "lookup_owasp_guidance"], "Looks fine."),
                expected_invocation=_invocation(["scan_python_code"], "Map the requirement."),
            )
        ],
        session_id="s2",
    )
    result = EvalSetResult(
        eval_set_result_id="app_set_1",
        eval_set_id="set",
        eval_case_results=[passing, failing],
        creation_timestamp=1790508246.0,
    )
    (app / ".adk" / "eval_history" / name).write_text(result.model_dump_json(indent=2), encoding="utf-8")


def test_adk_web_ui_results_are_imported_as_their_own_source(client: TestClient, agents_dir) -> None:
    _write_adk_result(agents_dir)

    data = client.get("/api/evaluations/scorecard-summary", params={"source": "adk_eval"}).json()
    assert data["source"] == "adk_eval"
    assert data["total_runs"] == 2
    assert data["passed_runs"] == 1
    assert data["capability_score"] == 50.0
    assert data["agent_dna"]["base_model"] == "test-model"

    runs = client.get("/api/evaluations/runs", params={"source": "adk_eval"}).json()["runs"]
    by_scenario = {r["scenario_id"]: r for r in runs}
    assert by_scenario["eval_sql_injection_defense"]["status"] == "PASSED"
    assert by_scenario["eval_sql_injection_defense"]["verifier_type"] == "hard"
    assert by_scenario["eval_sql_injection_defense"]["score"] == 100
    assert by_scenario["eval_business_requirement_traceability"]["status"] == "FAILED"
    assert by_scenario["eval_business_requirement_traceability"]["verifier_type"] == "hybrid"
    assert by_scenario["eval_business_requirement_traceability"]["score"] == 40
    assert all(r["created_at"].startswith("2026-") for r in runs)


def test_adk_import_is_idempotent_and_exposes_the_trace(client: TestClient, agents_dir) -> None:
    _write_adk_result(agents_dir)
    for _ in range(3):
        assert client.get("/api/evaluations/scorecard-summary", params={"source": "adk_eval"}).json()["total_runs"] == 2

    runs = client.get("/api/evaluations/runs", params={"source": "adk_eval"}).json()["runs"]
    failing = next(r for r in runs if r["status"] == "FAILED")
    trace = client.get(f"/api/evaluations/trajectories/{failing['session_id']}").json()
    assert trace["source"] == "adk_eval"
    steps = trace["trajectory"]["steps"]
    assert [s["tool"] for s in steps] == ["scan_python_code", "lookup_owasp_guidance"]
    assert [s["matched"] for s in steps] == [True, False]
    assert {m["metric_name"] for m in trace["metric_results"]} == {
        "response_match_score",
        "rubric_based_final_response_quality_v1",
    }


def test_manual_sync_reports_imports(client: TestClient, agents_dir) -> None:
    _write_adk_result(agents_dir)
    first = client.post("/api/evaluations/sync").json()
    assert first["files_imported"] == 1
    assert first["runs_recorded"] == 2
    assert client.post("/api/evaluations/sync").json()["files_imported"] == 0


class _FakeOrchestrator:
    def __init__(self, **_: object) -> None:
        pass


class _FakeRuntime:
    fail = False

    def __init__(self, orchestrator: object = None) -> None:
        pass

    def review(self, **kwargs: object) -> dict:
        if self.fail:
            raise RuntimeError("model unavailable")
        return {
            "review_id": kwargs["review_id"],
            "source_code": "def f():\n    return 1\n",
            "summary": "One issue found.",
            "recommendations": ["Add a docstring."],
            "total_findings": 1,
            "llm_model": "fake-model",
            "llm_fallback_used": False,
            "model_armor": {"blocked": False},
            "dag_events": [
                {"node": "model_armor", "event": "scan_started", "timestamp": "2026-10-05T10:00:00+00:00", "payload": {}},
                {"node": "rag", "event": "retrieval_completed", "timestamp": "2026-10-05T10:00:01+00:00", "payload": {"matches": 2}},
                {"node": "orchestrator", "event": "pipeline_completed", "timestamp": "2026-10-05T10:00:03+00:00", "payload": {}},
            ],
        }


def test_code_reviews_are_recorded_as_their_own_source(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(review_routes, "ADKRuntime", _FakeRuntime)
    monkeypatch.setattr(review_routes, "CodeReviewOrchestrator", _FakeOrchestrator)

    response = client.post("/api/v1/review", json={"code_snippet": "def f():\n    return 1\n"})
    assert response.status_code == 200

    data = client.get("/api/evaluations/scorecard-summary", params={"source": "code_review"}).json()
    assert data["total_runs"] == 1
    assert data["passed_runs"] == 1
    assert data["agent_dna"]["base_model"] == "fake-model"

    run = client.get("/api/evaluations/runs", params={"source": "code_review"}).json()["runs"][0]
    assert run["scenario_id"] == "code_review:snippet"
    assert run["trajectory_length"] == 3
    assert run["latency_ms"] > 0

    trace = client.get(f"/api/evaluations/trajectories/{run['session_id']}").json()
    assert [s["latency_ms"] for s in trace["trajectory"]["steps"]] == [0, 1000.0, 2000.0]
    grid = client.get("/api/evaluations/reliability-metrics", params={"source": "code_review"}).json()["adaptability_grid"]
    assert set(grid) == {"execution", "search"}


def test_failed_code_review_is_recorded_as_failed(client: TestClient, monkeypatch) -> None:
    class _Failing(_FakeRuntime):
        fail = True

    monkeypatch.setattr(review_routes, "ADKRuntime", _Failing)
    monkeypatch.setattr(review_routes, "CodeReviewOrchestrator", _FakeOrchestrator)

    assert client.post("/api/v1/review", json={"code_snippet": "x = 1"}).status_code == 500

    data = client.get("/api/evaluations/scorecard-summary", params={"source": "code_review"}).json()
    assert data["total_runs"] == 1
    assert data["failed_runs"] == 1


def test_sources_breakdown_separates_and_combines(client: TestClient, agents_dir, monkeypatch) -> None:
    monkeypatch.setattr(review_routes, "ADKRuntime", _FakeRuntime)
    monkeypatch.setattr(review_routes, "CodeReviewOrchestrator", _FakeOrchestrator)
    _run_evaluation(client)
    _write_adk_result(agents_dir)
    client.post("/api/v1/review", json={"code_snippet": "def f():\n    return 1\n"})

    data = client.get("/api/evaluations/sources").json()
    per_source = {s["source"]: s for s in data["sources"]}
    assert set(per_source) == {"agent_lab", "adk_eval", "code_review"}
    assert per_source["agent_lab"]["total_runs"] == 1
    assert per_source["adk_eval"]["total_runs"] == 2
    assert per_source["code_review"]["total_runs"] == 1
    assert data["combined"]["total_runs"] == 4
    assert data["combined"]["source"] == "all"

    combined = client.get("/api/evaluations/scorecard-summary").json()
    assert combined["total_runs"] == 4
    assert client.get("/api/evaluations/scorecard-summary", params={"source": "all"}).json()["total_runs"] == 4


def test_unknown_source_is_rejected(client: TestClient) -> None:
    assert client.get("/api/evaluations/runs", params={"source": "bogus"}).status_code == 400


def test_legacy_database_without_source_column_is_migrated(tmp_path) -> None:
    import sqlite3

    path = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE evaluation_runs (id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL UNIQUE, "
            "scenario_id TEXT, scenario_name TEXT, capability_tags TEXT NOT NULL DEFAULT '[]', "
            "verifier_type TEXT NOT NULL DEFAULT 'soft', status TEXT NOT NULL, score REAL NOT NULL, grade TEXT, "
            "trajectory_length INTEGER NOT NULL DEFAULT 0, latency_ms REAL NOT NULL DEFAULT 0, "
            "prompt_tokens INTEGER NOT NULL DEFAULT 0, completion_tokens INTEGER NOT NULL DEFAULT 0, "
            "cost_usd REAL NOT NULL DEFAULT 0, has_noise INTEGER NOT NULL DEFAULT 0, robustness REAL, "
            "dimensions TEXT NOT NULL DEFAULT '{}', agent_dna TEXT NOT NULL DEFAULT '{}', "
            "result_json TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP)"
        )
        conn.execute(
            "INSERT INTO evaluation_runs (session_id, status, score, result_json) VALUES ('old', 'PASSED', 90, '{}')"
        )

    store = EvaluationHistoryStore(sqlite_path=str(path))
    assert store.scorecard_summary("agent_lab")["total_runs"] == 1
    assert store.scorecard_summary("adk_eval")["total_runs"] == 0
