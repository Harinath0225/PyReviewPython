from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect

from agent.adk_runtime import ADKRuntime
from agent.code_review_orchestrator import CodeReviewOrchestrator
from agent.github_pr_review_service import GitHubPRReviewRequest, GitHubPRReviewService
from agent.recommendation_history_store import get_recommendation_history_store
from agent.review_event_broadcaster import review_event_broadcaster

router = APIRouter(prefix="/api/v1")
_review_tasks: dict[str, asyncio.Task[None]] = {}


class ReviewRequest:
    def __init__(self, repo_path: str | None = None, code_snippet: str | None = None, language: str = "python") -> None:
        self.repo_path = repo_path
        self.code_snippet = code_snippet
        self.language = language


@router.post("/review")
async def review_code(payload: dict[str, Any]) -> dict[str, object]:
    repo_path = payload.get("repo_path")
    code_snippet = payload.get("code_snippet")
    language = payload.get("language", "python")

    if not repo_path and not code_snippet:
        raise HTTPException(status_code=400, detail="Either repo_path or code_snippet is required.")

    review_id = f"review-{uuid.uuid4().hex}"
    review_event_broadcaster.create(review_id, asyncio.get_running_loop())
    await review_event_broadcaster.set_status(review_id, "started")
    try:
        runtime = ADKRuntime(orchestrator=CodeReviewOrchestrator())
        result = await asyncio.to_thread(runtime.review, repo_path=repo_path, code_snippet=code_snippet, language=language, review_id=review_id)
        await review_event_broadcaster.set_status(review_id, "completed", result=result)
        return result
    except Exception as exc:
        await review_event_broadcaster.set_status(review_id, "failed", error=str(exc))
        raise HTTPException(status_code=500, detail="Review processing failed.") from exc


@router.post("/review/start", status_code=202)
async def start_review(payload: dict[str, Any]) -> dict[str, str]:
    repo_path = payload.get("repo_path")
    code_snippet = payload.get("code_snippet")
    language = payload.get("language", "python")
    if not repo_path and not code_snippet:
        raise HTTPException(status_code=400, detail="Either repo_path or code_snippet is required.")

    review_id = f"review-{uuid.uuid4().hex}"
    review_event_broadcaster.create(review_id, asyncio.get_running_loop())
    task = asyncio.create_task(_run_review(review_id, repo_path, code_snippet, language))
    _review_tasks[review_id] = task
    task.add_done_callback(lambda _: _review_tasks.pop(review_id, None))
    return {"review_id": review_id, "status": "started"}


async def _run_review(review_id: str, repo_path: str | None, code_snippet: str | None, language: str) -> None:
    await review_event_broadcaster.set_status(review_id, "started")
    try:
        runtime = ADKRuntime(orchestrator=CodeReviewOrchestrator())
        result = await asyncio.to_thread(runtime.review, repo_path=repo_path, code_snippet=code_snippet, language=language, review_id=review_id)
        await review_event_broadcaster.set_status(review_id, "completed", result=result)
    except Exception as exc:
        await review_event_broadcaster.set_status(review_id, "failed", error=str(exc))


@router.get("/review/{review_id}")
async def get_review(review_id: str) -> dict[str, Any]:
    state = review_event_broadcaster.status(review_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Review ID not found.")
    return state


@router.post("/review/github-pr")
async def review_github_pr(payload: dict[str, Any]) -> dict[str, Any]:
    owner = payload.get("owner")
    repo = payload.get("repo")
    pull_number = payload.get("pull_number")
    max_findings = int(payload.get("max_findings", 30))
    dry_run = bool(payload.get("dry_run", False))
    review_event = str(payload.get("review_event", "COMMENT"))
    review_body = payload.get("review_body")

    if not owner or not repo or not pull_number:
        raise HTTPException(status_code=400, detail="owner, repo and pull_number are required.")

    service = GitHubPRReviewService()
    request = GitHubPRReviewRequest(
        owner=str(owner),
        repo=str(repo),
        pull_number=int(pull_number),
        max_findings=max_findings,
        dry_run=dry_run,
        review_event=review_event,
        review_body=str(review_body) if review_body is not None else None,
    )
    return await service.review_pull_request(request)


@router.get("/review/history")
async def review_history(
    limit: int = Query(default=50, ge=1, le=500),
    source: str | None = Query(default=None),
    query: str | None = Query(default=None),
    n_results: int = Query(default=5, ge=1, le=20),
) -> dict[str, Any]:
    store = get_recommendation_history_store()
    history = store.list_history(limit=limit, source=source)
    similar = store.search_similar(query_text=query, limit=n_results) if query else []

    return {
        "status": "ok",
        "vector_store_enabled": store.vector_store_enabled,
        "count": len(history),
        "history": history,
        "similar": similar,
    }


@router.websocket("/ws/reviews/{review_id}")
async def review_stream(websocket: WebSocket, review_id: str) -> None:
    await websocket.accept()
    if not await review_event_broadcaster.attach(review_id, websocket):
        await websocket.send_json({"review_id": review_id, "node": "review_lifecycle", "event": "review_failed", "timestamp": datetime.now(timezone.utc).isoformat(), "payload": {"error": "Unknown review ID"}, "type": "review_failed"})
        await websocket.close(code=1008)
        return

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        review_event_broadcaster.unsubscribe(review_id, websocket)
