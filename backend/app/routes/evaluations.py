"""Agent Scorecard API endpoints.

Serves the aggregated Capability / Reliability / Adaptability / Efficiency
metrics and per-session trajectory traces consumed by the Angular Scorecard
dashboard (route `/scorecard`). Every endpoint accepts `?source=` to return one
source's results (`agent_lab`, `adk_eval`, `code_review`); omit it or pass `all`
for the combined aggregate.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from agent.evaluation_history_store import SOURCES, EvaluationHistoryStore, get_evaluation_history_store
from agent.evaluation_ingest import sync_adk_results
from agent.judge_calibration import load_golden_set, run_calibration
from agent.llm_judge import CRITERIA, LLMJudge

router = APIRouter(prefix="/api/evaluations", tags=["evaluations"])
logger = logging.getLogger("evaluations_api")

# Calibration makes one LLM call per golden example, so only one run at a time and not back-to-back.
_calibration_lock = threading.Lock()
_calibration_last_started = 0.0
_CALIBRATION_COOLDOWN_SECONDS = 15.0
_JUDGE_MODES = {"auto", "llm", "heuristic"}


def synced_store() -> EvaluationHistoryStore:
    """Returns the store after importing any new ADK Web UI eval results."""
    store = get_evaluation_history_store()
    try:
        sync_adk_results(store)
    except Exception:
        logger.exception("ADK eval sync failed; serving data already recorded")
    return store


def source_filter(
    source: str = Query(default="all", description="all, agent_lab, adk_eval or code_review"),
) -> str | None:
    if source == "all":
        return None
    if source not in SOURCES:
        raise HTTPException(status_code=400, detail=f"source must be 'all' or one of {', '.join(SOURCES)}.")
    return source


@router.get("/scorecard-summary")
async def get_scorecard_summary(
    source: str | None = Depends(source_filter),
    store: EvaluationHistoryStore = Depends(synced_store),
) -> dict[str, Any]:
    """Aggregated Hero stats: Capability Score + Reliability Index."""
    return store.scorecard_summary(source)


@router.get("/reliability-metrics")
async def get_reliability_metrics(
    source: str | None = Depends(source_filter),
    store: EvaluationHistoryStore = Depends(synced_store),
) -> dict[str, Any]:
    """Reliability Quadrant data: consistency, robustness, predictability,
    safety, plus the Scenario & Adaptability grid."""
    return store.reliability_metrics(source)


@router.get("/efficiency-metrics")
async def get_efficiency_metrics(
    source: str | None = Depends(source_filter),
    store: EvaluationHistoryStore = Depends(synced_store),
) -> dict[str, Any]:
    """Operational efficiency: steps, latency, tokens and cost per task."""
    return store.efficiency_metrics(source)


@router.get("/sources")
async def get_sources(store: EvaluationHistoryStore = Depends(synced_store)) -> dict[str, Any]:
    """Combined result plus one result per source, for side-by-side comparison."""
    return store.source_breakdown()


@router.get("/kpis")
async def get_kpis(
    source: str | None = Depends(source_filter),
    store: EvaluationHistoryStore = Depends(synced_store),
) -> dict[str, Any]:
    """KPIs with the evaluation metrics mapped to each (BLEU/METEOR/ROUGE, LLM judge, safety...)."""
    return store.kpi_scorecard(source)


@router.get("/judge-calibration")
async def get_judge_calibration(store: EvaluationHistoryStore = Depends(synced_store)) -> dict[str, Any]:
    """Current judge, the latest calibration loop (with its round-by-round trace) and history."""
    judge = LLMJudge()
    golden = load_golden_set()
    latest = store.latest_calibration(judge.key)
    return {
        "status": "ok",
        "judge": {
            "requested_mode": judge.requested_mode,
            "effective_mode": judge.effective_mode,
            "model": judge.model if judge.effective_mode == "llm" else "heuristic-rubric",
            "llm_available": judge.llm_available,
            "criteria": [
                {"name": name, "weight": meta["weight"], "description": meta["description"]}
                for name, meta in CRITERIA.items()
            ],
        },
        "golden_set": {"examples": len(golden["examples"]), "pass_human_score": golden.get("pass_human_score", 4)},
        "latest": latest,
        "history": store.list_calibrations(),
    }


@router.post("/judge-calibration/run")
def run_judge_calibration(
    payload: dict[str, Any] | None = None,
    store: EvaluationHistoryStore = Depends(synced_store),
) -> dict[str, Any]:
    """Runs the calibration loop on the human-labelled golden set and stores the result.

    Synchronous on purpose: FastAPI runs it in a worker thread, so LLM calls do not block the event loop.
    """
    global _calibration_last_started
    payload = payload or {}
    mode = str(payload.get("mode", "auto")).lower()
    max_rounds = payload.get("max_rounds", 5)
    if mode not in _JUDGE_MODES:
        raise HTTPException(status_code=400, detail=f"mode must be one of {', '.join(sorted(_JUDGE_MODES))}.")
    if isinstance(max_rounds, bool) or not isinstance(max_rounds, int) or not 1 <= max_rounds <= 8:
        raise HTTPException(status_code=400, detail="max_rounds must be an integer from 1 to 8.")

    if not _calibration_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="A calibration run is already in progress.")
    try:
        wait = _CALIBRATION_COOLDOWN_SECONDS - (time.monotonic() - _calibration_last_started)
        if wait > 0:
            raise HTTPException(status_code=429, detail=f"Calibration just ran; try again in {int(wait) + 1}s.")
        _calibration_last_started = time.monotonic()
        judge = LLMJudge(mode=mode)
        result = run_calibration(judge, max_rounds=max_rounds)
        result["id"] = store.save_calibration(judge.key, result)
        return {"status": "ok", **result}
    finally:
        _calibration_lock.release()


@router.post("/sync")
async def sync_adk_eval_results() -> dict[str, Any]:
    """Imports ADK Web UI eval results from disk now."""
    return {"status": "ok", **sync_adk_results(get_evaluation_history_store())}


@router.get("/runs")
async def list_evaluation_runs(
    limit: int = Query(default=50, ge=1, le=500),
    source: str | None = Depends(source_filter),
    store: EvaluationHistoryStore = Depends(synced_store),
) -> dict[str, Any]:
    """Recent sessions with high-level outcome (Pass/Fail)."""
    runs = store.list_runs(limit=limit, source=source)
    return {"status": "ok", "count": len(runs), "runs": runs}


@router.get("/trajectories/{session_id}")
async def get_trajectory(
    session_id: str,
    store: EvaluationHistoryStore = Depends(synced_store),
) -> dict[str, Any]:
    """Detailed white-box trajectory trace for a single session."""
    trajectory = store.get_trajectory(session_id)
    if trajectory is None:
        raise HTTPException(status_code=404, detail=f"No evaluation run found for session '{session_id}'.")
    return trajectory
