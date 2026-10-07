"""SQLite-backed persistence for agent runs (Agent Scorecard).

Runs from three sources are recorded here so the Scorecard API can aggregate
Capability, Reliability, Adaptability and Efficiency metrics both combined and
per source:

- ``agent_lab``   - Agent Lab "Run ADK Evaluation" (``/agent/evaluate``)
- ``adk_eval``    - Google ADK Web UI / eval-set runs (imported from disk)
- ``code_review`` - production code reviews (New Review)
"""

from __future__ import annotations

import json
import math
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent.scorecard_kpis import compute_kpis

_DEFAULT_DB = "data/evaluation_history.sqlite3"

SOURCE_AGENT_LAB = "agent_lab"
SOURCE_ADK_EVAL = "adk_eval"
SOURCE_CODE_REVIEW = "code_review"

SOURCE_LABELS: dict[str, str] = {
    SOURCE_AGENT_LAB: "Agent Lab evaluations",
    SOURCE_ADK_EVAL: "ADK Web UI evals",
    SOURCE_CODE_REVIEW: "Code reviews",
}
SOURCES: tuple[str, ...] = tuple(SOURCE_LABELS)


class EvaluationHistoryStore:
    def __init__(self, sqlite_path: str = _DEFAULT_DB) -> None:
        self.sqlite_path = sqlite_path
        Path(self.sqlite_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_sqlite()

    def _conn(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.sqlite_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_sqlite(self) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS evaluation_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL UNIQUE,
                    source TEXT NOT NULL DEFAULT 'agent_lab',
                    scenario_id TEXT,
                    scenario_name TEXT,
                    capability_tags TEXT NOT NULL DEFAULT '[]',
                    verifier_type TEXT NOT NULL DEFAULT 'soft',
                    status TEXT NOT NULL,
                    score REAL NOT NULL,
                    grade TEXT,
                    trajectory_length INTEGER NOT NULL DEFAULT 0,
                    latency_ms REAL NOT NULL DEFAULT 0,
                    prompt_tokens INTEGER NOT NULL DEFAULT 0,
                    completion_tokens INTEGER NOT NULL DEFAULT 0,
                    cost_usd REAL NOT NULL DEFAULT 0,
                    has_noise INTEGER NOT NULL DEFAULT 0,
                    robustness REAL,
                    dimensions TEXT NOT NULL DEFAULT '{}',
                    quality_metrics TEXT NOT NULL DEFAULT '{}',
                    agent_dna TEXT NOT NULL DEFAULT '{}',
                    result_json TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            # Databases created before the source column existed hold Agent Lab runs only.
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(evaluation_runs)")}
            if "source" not in columns:
                conn.execute(
                    "ALTER TABLE evaluation_runs ADD COLUMN source TEXT NOT NULL DEFAULT 'agent_lab'"
                )
            if "quality_metrics" not in columns:
                conn.execute(
                    "ALTER TABLE evaluation_runs ADD COLUMN quality_metrics TEXT NOT NULL DEFAULT '{}'"
                )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS judge_calibrations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    judge_key TEXT NOT NULL,
                    judge_mode TEXT NOT NULL,
                    judge_model TEXT NOT NULL,
                    example_count INTEGER NOT NULL,
                    params TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_evaluation_runs_created_at
                ON evaluation_runs(created_at DESC)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_evaluation_runs_scenario
                ON evaluation_runs(scenario_id)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_evaluation_runs_source
                ON evaluation_runs(source)
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS import_state (
                    path TEXT PRIMARY KEY,
                    mtime REAL NOT NULL
                )
                """
            )

    def import_mtime(self, path: str) -> float | None:
        with self._conn() as conn:
            row = conn.execute("SELECT mtime FROM import_state WHERE path = ?", (path,)).fetchone()
        return float(row["mtime"]) if row else None

    def mark_imported(self, path: str, mtime: float) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO import_state (path, mtime) VALUES (?, ?)", (path, mtime)
            )

    # ------------------------------------------------------------------
    # Write path
    # ------------------------------------------------------------------

    def record_run(
        self,
        result: dict[str, Any],
        scenario_name: str | None = None,
        source: str = SOURCE_AGENT_LAB,
        created_at: str | None = None,
    ) -> str:
        """Persists one run (re-recording the same session_id replaces it) and returns its session_id."""
        if source not in SOURCES:
            raise ValueError(f"unknown run source: {source}")
        created_at = created_at or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        efficiency = result.get("efficiency") or {}
        quality = {
            str(name): float(value)
            for name, value in (result.get("quality_metrics") or {}).items()
            if isinstance(value, (int, float)) and not isinstance(value, bool)
        }
        dimensions = result.get("dimensions") or {}
        conformance = result.get("conformance") or {}
        noise = result.get("noise")

        session_id = str(result.get("session_id") or "")
        if not session_id:
            raise ValueError("evaluation result is missing session_id")

        status = "PASSED" if conformance.get("status") == "CONFORMANT" else (
            "BLOCKED" if conformance.get("status") == "BLOCKED" else "FAILED"
        )

        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO evaluation_runs (
                    session_id, source, scenario_id, scenario_name, capability_tags,
                    verifier_type, status, score, grade, trajectory_length,
                    latency_ms, prompt_tokens, completion_tokens, cost_usd,
                    has_noise, robustness, dimensions, agent_dna, result_json,
                    quality_metrics, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    source,
                    result.get("scenario_id") or result.get("adk_spec", {}).get("eval_id"),
                    scenario_name,
                    json.dumps(result.get("capabilities") or []),
                    str(result.get("verifier_type") or "soft"),
                    status,
                    float(result.get("score") or 0),
                    result.get("grade"),
                    int(efficiency.get("steps") or 0),
                    float(efficiency.get("latency_ms") or 0),
                    int(efficiency.get("prompt_tokens") or 0),
                    int(efficiency.get("completion_tokens") or 0),
                    float(efficiency.get("cost_usd") or 0),
                    1 if noise else 0,
                    float(dimensions["robustness"]) if "robustness" in dimensions else None,
                    json.dumps(dimensions),
                    json.dumps(result.get("agent_dna") or {}),
                    json.dumps(result),
                    json.dumps(quality),
                    created_at,
                ),
            )
        return session_id

    # ------------------------------------------------------------------
    # Read path / aggregations
    # ------------------------------------------------------------------

    def _fetch_all(self, source: str | None = None) -> list[sqlite3.Row]:
        with self._conn() as conn:
            if source:
                return conn.execute(
                    "SELECT * FROM evaluation_runs WHERE source = ? ORDER BY created_at DESC",
                    (source,),
                ).fetchall()
            return conn.execute(
                "SELECT * FROM evaluation_runs ORDER BY created_at DESC"
            ).fetchall()

    @staticmethod
    def _percentile(values: list[float], pct: float) -> float:
        if not values:
            return 0.0
        ordered = sorted(values)
        rank = (len(ordered) - 1) * pct
        low = math.floor(rank)
        high = math.ceil(rank)
        if low == high:
            return float(ordered[low])
        return float(ordered[low] + (ordered[high] - ordered[low]) * (rank - low))

    def scorecard_summary(self, source: str | None = None) -> dict[str, Any]:
        rows = self._fetch_all(source)
        total = len(rows)
        passed = sum(1 for r in rows if r["status"] == "PASSED")
        scores = [float(r["score"]) for r in rows]
        capability_score = round((passed / total) * 100, 2) if total else 0.0
        reliability = self.reliability_metrics(source)
        agent_dna = json.loads(rows[0]["agent_dna"]) if rows else {}

        return {
            "status": "ok",
            "source": source or "all",
            "total_runs": total,
            "passed_runs": passed,
            "failed_runs": total - passed,
            "capability_score": capability_score,
            "average_score": round(sum(scores) / total, 2) if total else 0.0,
            "reliability_index": reliability["reliability_index"],
            "agent_dna": agent_dna,
        }

    def reliability_metrics(self, source: str | None = None) -> dict[str, Any]:
        rows = self._fetch_all(source)

        # Consistency needs repeated runs of the same scenario; otherwise it is unmeasured.
        consistency: float | None = None
        by_scenario: dict[str, list[int]] = {}
        for r in rows:
            key = r["scenario_id"] or "custom"
            by_scenario.setdefault(key, []).append(int(r["trajectory_length"]))
        variances: list[float] = []
        for lengths in by_scenario.values():
            if len(lengths) > 1:
                mean = sum(lengths) / len(lengths)
                std = math.sqrt(sum((v - mean) ** 2 for v in lengths) / len(lengths))
                variances.append(min(1.0, std / max(1.0, mean)))
        if variances:
            consistency = round((1.0 - sum(variances) / len(variances)) * 100, 2)

        # Robustness: average robustness score across noise-injected runs.
        noisy = [r for r in rows if r["has_noise"] and r["robustness"] is not None]
        robustness = (
            round(sum(float(r["robustness"]) for r in noisy) / len(noisy), 2)
            if noisy
            else None
        )

        # Predictability (calibration): 1 - |mean confidence - actual pass rate|.
        predictability = None
        if rows:
            mean_confidence = sum(float(r["score"]) for r in rows) / len(rows) / 100.0
            pass_rate = sum(1 for r in rows if r["status"] == "PASSED") / len(rows)
            predictability = round((1.0 - abs(mean_confidence - pass_rate)) * 100, 2)

        # Safety: average safety dimension across runs.
        safety_values: list[float] = []
        for r in rows:
            try:
                dims = json.loads(r["dimensions"])
                if "safety" in dims:
                    safety_values.append(float(dims["safety"]))
            except (json.JSONDecodeError, TypeError, ValueError):
                continue
        safety = round(sum(safety_values) / len(safety_values), 2) if safety_values else None

        components = [
            v for v in (consistency, robustness, predictability, safety) if v is not None
        ]
        reliability_index = round(sum(components) / len(components), 2) if components else 0.0

        # Adaptability grid: pass rate per capability tag.
        grid: dict[str, dict[str, Any]] = {}
        for r in rows:
            try:
                tags = json.loads(r["capability_tags"])
            except (json.JSONDecodeError, TypeError):
                tags = []
            for tag in tags:
                bucket = grid.setdefault(tag, {"runs": 0, "passed": 0})
                bucket["runs"] += 1
                bucket["passed"] += 1 if r["status"] == "PASSED" else 0
        adaptability_grid = {
            tag: {
                "runs": bucket["runs"],
                "pass_rate": round(bucket["passed"] / bucket["runs"] * 100, 2) if bucket["runs"] else 0.0,
            }
            for tag, bucket in sorted(grid.items())
        }

        return {
            "status": "ok",
            "source": source or "all",
            "reliability_index": reliability_index,
            "consistency": consistency,
            "robustness": robustness,
            "predictability": predictability,
            "safety": safety,
            "adaptability_grid": adaptability_grid,
        }

    def efficiency_metrics(self, source: str | None = None) -> dict[str, Any]:
        rows = self._fetch_all(source)
        steps = [float(r["trajectory_length"]) for r in rows]
        # A latency of 0 means the source could not measure it, so it is left out of the stats.
        latencies = [float(r["latency_ms"]) for r in rows if float(r["latency_ms"]) > 0]
        prompt_tokens = [float(r["prompt_tokens"]) for r in rows]
        completion_tokens = [float(r["completion_tokens"]) for r in rows]
        costs = [float(r["cost_usd"]) for r in rows]

        return {
            "status": "ok",
            "source": source or "all",
            "total_runs": len(rows),
            "steps_median": self._percentile(steps, 0.50),
            "steps_p90": self._percentile(steps, 0.90),
            "latency_ms_median": self._percentile(latencies, 0.50) if latencies else None,
            "latency_ms_p90": self._percentile(latencies, 0.90) if latencies else None,
            "prompt_tokens_total": int(sum(prompt_tokens)),
            "completion_tokens_total": int(sum(completion_tokens)),
            "cost_usd_total": round(sum(costs), 6),
            "cost_usd_per_task": round(sum(costs) / len(costs), 6) if costs else 0.0,
        }

    def source_breakdown(self) -> dict[str, Any]:
        """Side-by-side results per source plus the combined (all sources) result."""

        def describe(source: str | None) -> dict[str, Any]:
            summary = self.scorecard_summary(source)
            efficiency = self.efficiency_metrics(source)
            runs = self.list_runs(limit=1, source=source)
            return {
                "source": source or "all",
                "label": SOURCE_LABELS.get(source or "", "All sources (combined)"),
                "total_runs": summary["total_runs"],
                "passed_runs": summary["passed_runs"],
                "failed_runs": summary["failed_runs"],
                "capability_score": summary["capability_score"],
                "average_score": summary["average_score"],
                "reliability_index": summary["reliability_index"],
                "steps_median": efficiency["steps_median"],
                "latency_ms_median": efficiency["latency_ms_median"],
                "cost_usd_per_task": efficiency["cost_usd_per_task"],
                "last_run_at": runs[0]["created_at"] if runs else None,
            }

        return {
            "status": "ok",
            "combined": describe(None),
            "sources": [describe(source) for source in SOURCES],
        }

    def list_runs(self, limit: int = 50, source: str | None = None) -> list[dict[str, Any]]:
        where = "WHERE source = ?" if source else ""
        params: tuple[Any, ...] = (source, limit) if source else (limit,)
        with self._conn() as conn:
            rows = conn.execute(
                f"""
                SELECT session_id, source, scenario_id, scenario_name, verifier_type,
                       status, score, grade, trajectory_length, latency_ms,
                       prompt_tokens, completion_tokens,
                       cost_usd, has_noise, created_at
                FROM evaluation_runs
                {where}
                ORDER BY created_at DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [dict(row) for row in rows]

    def get_trajectory(self, session_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT source, result_json FROM evaluation_runs WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        if row is None:
            return None
        result = json.loads(row["result_json"])
        return {
            "status": "ok",
            "session_id": session_id,
            "source": row["source"],
            "verifier_type": result.get("verifier_type"),
            "agent_dna": result.get("agent_dna"),
            "conformance": result.get("conformance"),
            "trajectory": result.get("trajectory"),
            "dimensions": result.get("dimensions"),
            "efficiency": result.get("efficiency"),
            "noise": result.get("noise"),
            "metric_results": result.get("metric_results"),
            "quality_metrics": result.get("quality_metrics"),
            "judge": result.get("judge"),
        }

    # ------------------------------------------------------------------
    # Judge calibration
    # ------------------------------------------------------------------

    def save_calibration(self, judge_key: str, result: dict[str, Any]) -> int:
        """Stores a calibration loop result and returns its id."""
        judge = result["judge"]
        with self._conn() as conn:
            cursor = conn.execute(
                """
                INSERT INTO judge_calibrations
                    (judge_key, judge_mode, judge_model, example_count, params, result_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    judge_key,
                    judge["mode"],
                    judge["model"],
                    int(result["example_count"]),
                    json.dumps(result["params"]),
                    json.dumps(result),
                ),
            )
            return int(cursor.lastrowid)

    @staticmethod
    def _calibration_from_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "judge_key": row["judge_key"],
            "judge_mode": row["judge_mode"],
            "judge_model": row["judge_model"],
            "example_count": row["example_count"],
            "params": json.loads(row["params"]),
            "result": json.loads(row["result_json"]),
            "created_at": row["created_at"],
        }

    def latest_calibration(self, judge_key: str | None = None) -> dict[str, Any] | None:
        """Newest calibration, for one judge when a key is given."""
        with self._conn() as conn:
            if judge_key:
                row = conn.execute(
                    "SELECT * FROM judge_calibrations WHERE judge_key = ? ORDER BY id DESC LIMIT 1",
                    (judge_key,),
                ).fetchone()
            else:
                row = conn.execute("SELECT * FROM judge_calibrations ORDER BY id DESC LIMIT 1").fetchone()
        return self._calibration_from_row(row) if row else None

    def list_calibrations(self, limit: int = 20) -> list[dict[str, Any]]:
        """Calibration history (newest first) without the heavy per-example trace."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM judge_calibrations ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        history = []
        for row in rows:
            entry = self._calibration_from_row(row)
            result = entry.pop("result")
            entry.update(
                trust_score=result.get("trust_score"),
                converged=result.get("converged"),
                rounds=len(result.get("rounds", [])),
                validation_mae_before=(result.get("before") or {}).get("mae"),
                validation_mae_after=(result.get("after") or {}).get("mae"),
            )
            history.append(entry)
        return history

    # ------------------------------------------------------------------
    # KPIs
    # ------------------------------------------------------------------

    def kpi_scorecard(self, source: str | None = None) -> dict[str, Any]:
        """KPI values and statuses for one source or all sources combined."""
        runs = []
        for row in self._fetch_all(source):
            try:
                dimensions = json.loads(row["dimensions"])
                quality = json.loads(row["quality_metrics"])
            except (json.JSONDecodeError, TypeError):
                dimensions, quality = {}, {}
            runs.append({"status": row["status"], "dimensions": dimensions, "quality": quality})
        calibration = self.latest_calibration()
        return {
            "status": "ok",
            "source": source or "all",
            "total_runs": len(runs),
            "kpis": compute_kpis(runs, calibration),
            "calibration_id": calibration["id"] if calibration else None,
        }


_default_store: EvaluationHistoryStore | None = None


def get_evaluation_history_store() -> EvaluationHistoryStore:
    global _default_store
    if _default_store is None:
        _default_store = EvaluationHistoryStore(os.getenv("EVAL_HISTORY_DB") or _DEFAULT_DB)
    return _default_store
