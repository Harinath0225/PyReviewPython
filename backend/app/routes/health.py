from fastapi import APIRouter

from backend.app.metrics import latency_histogram

router = APIRouter()


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
async def readyz() -> dict[str, str]:
    return {"status": "ready"}


@router.get("/metrics")
async def metrics() -> dict[str, float | int]:
    return latency_histogram.snapshot()
