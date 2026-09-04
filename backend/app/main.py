from __future__ import annotations

from typing import Any

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse

from backend.app.config import get_settings
from backend.app.lifespan import lifespan
from backend.app.routes.agent import router as agent_router
from backend.app.routes.health import router as health_routes
from backend.app.routes.review import router as review_router
from security.middleware import LatencyMetricsMiddleware


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        debug=settings.app_env == "development",
        lifespan=lifespan,
        default_response_class=ORJSONResponse,
    )
    app.add_middleware(LatencyMetricsMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:4200", "http://127.0.0.1:4200"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health_routes)
    app.include_router(agent_router)
    app.include_router(review_router)

    @app.get("/")
    async def root() -> dict[str, Any]:
        return {"app": settings.app_name, "status": "online"}

    return app


app = create_app()


def main() -> None:
    uvicorn.run("backend.app.main:app", host="0.0.0.0", port=8000, reload=False)


if __name__ == "__main__":
    main()
