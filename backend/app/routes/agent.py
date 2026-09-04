from fastapi import APIRouter, Depends, HTTPException, Request

from agent.manager import AgentManager
from security.auth import require_api_key
from security.prompt_injection_guard import get_prompt_injection_guard_service

router = APIRouter(prefix="/api/v1")


@router.post("/agent/invoke")
async def invoke_agent(
    request: Request,
    payload: dict[str, str],
    _api_key: str | None = Depends(require_api_key),
):
    prompt = (payload or {}).get("prompt", "").strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="prompt is required")

    guard = get_prompt_injection_guard_service()
    guard_result = guard.validate(prompt)
    if guard_result.get("blocked"):
        raise HTTPException(status_code=400, detail=guard_result.get("reason") or "Prompt blocked by security policy")

    manager = getattr(request.app.state, "agent_manager", None)
    if manager is None:
        manager = AgentManager()
        await manager.initialize()
        request.app.state.agent_manager = manager

    runtime = await manager.get_runtime()
    response = runtime.run(prompt)
    return {
        "status": "ok",
        "response": response,
        "prompt_guard": guard_result,
    }
