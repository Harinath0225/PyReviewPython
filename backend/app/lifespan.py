from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from agent.manager import AgentManager
from backend.app.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    timeout_value = settings.http_timeout_seconds
    app.state.http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(
            connect=timeout_value,
            read=timeout_value,
            write=timeout_value,
            pool=timeout_value,
        ),
        limits=httpx.Limits(
            max_keepalive_connections=settings.max_keepalive_connections,
            max_connections=settings.max_connections,
        ),
        headers={"x-app-name": settings.app_name},
    )
    app.state.agent_manager = AgentManager()
    await app.state.agent_manager.initialize()
    yield
    await app.state.http_client.aclose()
