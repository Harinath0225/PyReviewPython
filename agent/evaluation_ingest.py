"""Adapters that turn ADK Web UI eval results and code reviews into scorecard runs.

Both adapters emit the same result shape as ``AgentEvaluationService.evaluate`` so
``EvaluationHistoryStore.record_run`` and the Scorecard API treat every source alike.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent.evaluation_history_store import (
    SOURCE_ADK_EVAL,
    SOURCE_CODE_REVIEW,
    EvaluationHistoryStore,
)

logger = logging.getLogger("evaluation_ingest")

_REPO_ROOT = Path(__file__).resolve().parent.parent
_ADK_RESULT_GLOB = "*.evalset_result.json"

# ADK metrics judged by a model rather than by deterministic rules.
_SOFT_METRIC_MARKERS = (
    "judge",
    "rubric",
    "hallucination",
    "safety_v1",
    "multi_turn",
    "final_response_match_v2",
    "response_evaluation",
)

# Blended USD per 1K tokens, kept identical to AgentEvaluationService.
_PROMPT_USD_PER_1K = 0.00125
_COMPLETION_USD_PER_1K = 0.00375

_REVIEW_SUB_AGENTS = ["CodeReviewAgent", "DependencyFlowAgent"]


def _grade(score: float) -> str:
    return "A" if score >= 90 else "B" if score >= 75 else "C" if score >= 60 else "D"


def _cost_usd(prompt_tokens: int, completion_tokens: int) -> float:
    return round(
        (prompt_tokens * _PROMPT_USD_PER_1K + completion_tokens * _COMPLETION_USD_PER_1K) / 1000, 6
    )


def _truncate(value: Any, limit: int = 200) -> Any:
    if isinstance(value, str):
        return value if len(value) <= limit else value[:limit] + "..."
    if isinstance(value, dict):
        return {k: _truncate(v, limit) for k, v in value.items()}
    if isinstance(value, list):
        return [_truncate(v, limit) for v in value[:20]]
    return value


def _utc_string(timestamp: float) -> str | None:
    if timestamp and timestamp > 0:
        return datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    return None


# ---------------------------------------------------------------------------
# ADK Web UI / eval-set results
# ---------------------------------------------------------------------------

def _adk_agents_dir() -> Path:
    return Path(os.getenv("ADK_AGENTS_DIR") or _REPO_ROOT / "agents")


def _content_text(content: Any) -> str:
    parts = getattr(content, "parts", None) or []
    return "\n".join(p.text for p in parts if getattr(p, "text", None))


# ADK metric name -> quality metric key used by the scorecard KPIs.
_QUALITY_METRIC_KEYS = {
    "bleu_score": "bleu",
    "meteor_score": "meteor",
    "rouge_score": "rougeL",
    "llm_judge_score": "llm_judge",
}


def _dimension_key(metric_name: str) -> str:
    if metric_name == "safety_v1":
        return "safety"
    return metric_name[: -len("_score")] if metric_name.endswith("_score") else metric_name


def _normalized_score(metric_name: str, score: float) -> float:
    # response_evaluation_score is graded 1-5; every other metric is already 0-1.
    return min(1.0, max(0.0, score / 5.0 if metric_name == "response_evaluation_score" else score))


def _case_capabilities(eval_id: str) -> list[str]:
    name = eval_id.lower()
    if "business" in name or "requirement" in name:
        return ["ambiguity", "search"]
    if "injection" in name or "security" in name or "owasp" in name:
        return ["execution", "search"]
    return ["execution"]


def _agent_dna_for(app_dir: Path) -> dict[str, Any]:
    try:
        config = json.loads((app_dir / "test_config.json").read_text(encoding="utf-8"))
        if isinstance(config.get("agent_dna"), dict):
            return config["agent_dna"]
    except (OSError, json.JSONDecodeError):
        pass
    from agent.evaluation import build_agent_dna

    return build_agent_dna()


def adk_case_to_run(set_result: Any, case: Any, agent_dna: dict[str, Any]) -> dict[str, Any] | None:
    """Converts one ADK ``EvalCaseResult`` to a scorecard result; None when ADK did not score it."""
    from google.adk.evaluation.eval_case import get_all_tool_calls, get_all_tool_calls_with_responses
    from google.adk.evaluation.evaluator import EvalStatus

    if case.final_eval_status == EvalStatus.NOT_EVALUATED:
        return None

    prompt_text = ""
    completion_text = ""
    calls: list[tuple[Any, Any]] = []
    expected_tools: list[str] = []
    for item in case.eval_metric_result_per_invocation:
        actual = item.actual_invocation
        prompt_text += _content_text(actual.user_content)
        completion_text += _content_text(actual.final_response)
        calls.extend(get_all_tool_calls_with_responses(actual.intermediate_data))
        if item.expected_invocation is not None:
            expected_tools.extend(c.name for c in get_all_tool_calls(item.expected_invocation.intermediate_data))

    evaluated = [m for m in case.overall_eval_metric_results if m.score is not None]
    normalized = [_normalized_score(m.metric_name, float(m.score)) for m in evaluated]
    score = round(sum(normalized) / len(normalized) * 100) if normalized else 0

    dimensions = {
        _dimension_key(m.metric_name): round(n * 100, 2) for m, n in zip(evaluated, normalized)
    }
    metric_results = [
        {
            "metric_name": m.metric_name,
            "score": round(float(m.score), 4),
            "threshold": m.threshold,
            "status": m.eval_status.name,
        }
        for m in evaluated
    ]
    quality_metrics = {
        _QUALITY_METRIC_KEYS[m.metric_name]: round(n, 4)
        for m, n in zip(evaluated, normalized)
        if m.metric_name in _QUALITY_METRIC_KEYS
    }

    has_soft = any(any(marker in m.metric_name for marker in _SOFT_METRIC_MARKERS) for m in evaluated)
    has_hard = any(not any(marker in m.metric_name for marker in _SOFT_METRIC_MARKERS) for m in evaluated)
    verifier_type = "hybrid" if has_soft and has_hard else "soft" if has_soft else "hard"

    expected_set = set(expected_tools)
    actual_names = [call.name for call, _ in calls]
    matched = [name for name in dict.fromkeys(expected_tools) if name in actual_names]
    trajectory_metric = next((m for m in evaluated if m.metric_name == "tool_trajectory_avg_score"), None)
    match_score = (
        round(float(trajectory_metric.score) * 100)
        if trajectory_metric is not None
        else round(len(matched) / len(set(expected_tools)) * 100) if expected_tools else None
    )

    steps = [
        {
            "step": index,
            "tool": call.name,
            "phase": "Tool call",
            "latency_ms": 0,
            "status": "SUCCESS" if response is not None else "NO_RESPONSE",
            "args": _truncate(dict(call.args or {})),
            "result": str(_truncate(str(response.response), 300)) if response is not None else "No response recorded",
            "matched": call.name in expected_set,
        }
        for index, (call, response) in enumerate(calls, start=1)
    ]

    prompt_tokens = max(1, len(prompt_text) // 4 + sum(len(json.dumps(s["args"])) for s in steps) // 4)
    completion_tokens = max(1, (len(completion_text) + sum(len(s["result"]) for s in steps)) // 4)
    passed = case.final_eval_status == EvalStatus.PASSED

    return {
        "session_id": f"adk-{set_result.eval_set_result_id}-{case.eval_id}",
        "scenario_id": case.eval_id,
        "evaluated_at": _utc_string(set_result.creation_timestamp),
        "agent_dna": agent_dna,
        "verifier_type": verifier_type,
        "capabilities": _case_capabilities(case.eval_id),
        "score": score,
        "grade": _grade(score),
        "conformance": {
            "status": "CONFORMANT" if passed else "FAILED",
            "label": f"ADK eval {case.final_eval_status.name}",
        },
        "trajectory": {
            "expected": list(dict.fromkeys(expected_tools)),
            "actual": actual_names,
            "matched": matched,
            "match_score": match_score,
            "steps": steps,
        },
        "dimensions": dimensions,
        "metric_results": metric_results,
        "quality_metrics": quality_metrics,
        "efficiency": {
            "steps": len(steps),
            "latency_ms": 0,  # ADK does not record per-case duration.
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "cost_usd": _cost_usd(prompt_tokens, completion_tokens),
        },
        "noise": None,
    }


def sync_adk_results(store: EvaluationHistoryStore, agents_dir: Path | None = None) -> dict[str, int]:
    """Imports new or changed ADK ``.evalset_result.json`` files into the store (idempotent)."""
    from google.adk.evaluation._eval_set_results_manager_utils import parse_eval_set_result_json

    root = agents_dir or _adk_agents_dir()
    stats = {"files_scanned": 0, "files_imported": 0, "runs_recorded": 0, "errors": 0}
    if not root.is_dir():
        return stats

    for app_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        history_dir = app_dir / ".adk" / "eval_history"
        if not history_dir.is_dir():
            continue
        for path in sorted(history_dir.glob(_ADK_RESULT_GLOB)):
            stats["files_scanned"] += 1
            key = str(path.resolve())
            try:
                mtime = path.stat().st_mtime
                if store.import_mtime(key) == mtime:
                    continue
                set_result = parse_eval_set_result_json(path.read_text(encoding="utf-8"))
                dna = _agent_dna_for(app_dir)
                recorded = 0
                for case in set_result.eval_case_results:
                    run = adk_case_to_run(set_result, case, dna)
                    if run is None:
                        continue
                    store.record_run(
                        run,
                        scenario_name=case.eval_id,
                        source=SOURCE_ADK_EVAL,
                        created_at=run["evaluated_at"],
                    )
                    recorded += 1
                store.mark_imported(key, mtime)
                stats["files_imported"] += 1
                stats["runs_recorded"] += recorded
            except Exception:
                # A file still being written by ADK is retried on the next sync.
                logger.exception("Could not import ADK eval result %s", path)
                stats["errors"] += 1
    return stats


# ---------------------------------------------------------------------------
# Code reviews (New Review)
# ---------------------------------------------------------------------------

def _parse_iso(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def build_review_run(
    *,
    review_id: str | None,
    result: dict[str, Any] | None,
    mode: str,
    duration_ms: float,
    error: str | None = None,
    has_business_documents: bool = False,
) -> dict[str, Any]:
    """Builds a scorecard result from a finished (or failed) code review."""
    from backend.app.config import get_settings

    result = result or {}
    events: list[dict[str, Any]] = list(result.get("dag_events") or [])
    failed_events = [
        e for e in events if "fail" in str(e.get("event", "")).lower() or "error" in str(e.get("event", "")).lower()
    ]
    armor = result.get("model_armor") or {}
    blocked = bool(armor.get("blocked"))
    fallback_used = bool(result.get("llm_fallback_used"))

    previous: datetime | None = None
    steps: list[dict[str, Any]] = []
    for index, event in enumerate(events, start=1):
        moment = _parse_iso(event.get("timestamp"))
        delta = round((moment - previous).total_seconds() * 1000, 1) if moment and previous else 0
        previous = moment or previous
        failed = event in failed_events
        payload = event.get("payload") or {}
        steps.append(
            {
                "step": index,
                "tool": str(event.get("node", "")),
                "phase": str(event.get("event", "")),
                "latency_ms": max(0, delta),
                "status": "FAILED" if failed else "SUCCESS",
                "args": {},
                "result": str(_truncate(", ".join(f"{k}={v}" for k, v in payload.items()), 300)),
                "matched": not failed,
            }
        )

    if error:
        dimensions = {"pipeline_completion": 0.0}
        status = "FAILED"
    else:
        dimensions = {
            "pipeline_completion": float(max(0, 100 - 25 * len(failed_events))),
            "safety": 100.0 if armor else 50.0,
            "llm_grounding": 50.0 if fallback_used else 100.0,
        }
        status = "BLOCKED" if blocked else "FAILED" if failed_events else "CONFORMANT"
    score = round(sum(dimensions.values()) / len(dimensions))

    nodes = {str(e.get("node", "")) for e in events}
    capabilities = ["execution"]
    if nodes & {"rag", "owasp"}:
        capabilities.append("search")
    if has_business_documents or result.get("business_requirements"):
        capabilities.append("ambiguity")
    if fallback_used and not error:
        capabilities.append("adaptability")

    prompt_tokens = max(1, len(str(result.get("source_code") or "")) // 4)
    completion_tokens = max(
        1, (len(str(result.get("summary") or "")) + len(json.dumps(result.get("recommendations") or []))) // 4
    )
    sub_agents = list(_REVIEW_SUB_AGENTS)
    if has_business_documents:
        sub_agents.append("BusinessRequirementSubagent")

    return {
        "session_id": review_id or f"review-{uuid.uuid4().hex}",
        "scenario_id": f"code_review:{mode}",
        "agent_dna": {
            "base_model": result.get("llm_model") or get_settings().llm_model,
            "harness": "google-adk-custom-loop",
            "sub_agents": sub_agents,
            "environment": {"type": "live-review", "sandbox": "none"},
        },
        # Pipeline health checks are rule-based; no model judges the review.
        "verifier_type": "hard",
        "capabilities": capabilities,
        "score": score,
        "grade": _grade(score),
        "conformance": {"status": status, "label": "Code review pipeline"},
        "trajectory": {
            "expected": [],
            "actual": list(dict.fromkeys(str(e.get("node", "")) for e in events)),
            "matched": [],
            "match_score": None,
            "steps": steps,
        },
        "dimensions": dimensions,
        "efficiency": {
            "steps": len(steps),
            "latency_ms": round(duration_ms, 2),
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "cost_usd": _cost_usd(prompt_tokens, completion_tokens),
        },
        "findings_count": int(result.get("total_findings") or 0),
        "error": error,
        "noise": None,
    }


def record_review_run(
    store: EvaluationHistoryStore,
    *,
    review_id: str | None,
    result: dict[str, Any] | None,
    mode: str,
    duration_ms: float,
    error: str | None = None,
    has_business_documents: bool = False,
) -> str | None:
    """Records a code review as a scorecard run; telemetry failures never break the review."""
    try:
        run = build_review_run(
            review_id=review_id,
            result=result,
            mode=mode,
            duration_ms=duration_ms,
            error=error,
            has_business_documents=has_business_documents,
        )
        return store.record_run(run, scenario_name=f"Code review ({mode})", source=SOURCE_CODE_REVIEW)
    except Exception:
        logger.exception("Could not record code review %s on the scorecard", review_id)
        return None
