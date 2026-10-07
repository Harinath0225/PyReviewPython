from functools import lru_cache
import os
from typing import Self

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "latency-fastapi-adk"
    app_env: str = "development"
    log_level: str = "info"
    api_key: str | None = None
    github_token: str | None = None
    gemini_api_key: str | None = None
    llm_provider: str = "gemini"
    llm_model: str = "gemma-4-26b-a4b-it"
    diagram_llm_model: str = "gemini-3.1-flash-lite"
    vision_llm_model: str = "gemini-3.1-flash-lite"
    # auto = LLM when an API key is configured, else heuristic; llm / heuristic force one.
    llm_judge_mode: str = "auto"
    # Empty means reuse diagram_llm_model, which differs from the agent under test (llm_model).
    judge_llm_model: str = ""
    prompt_guard_enabled: bool = False
    prompt_guard_min_match_hits: int = 1
    prompt_guard_block_on_error: bool = False
    prompt_guard_allowlist: str = ""
    google_project_id: str | None = None
    google_region: str = "us-central1"
    http_timeout_seconds: float = 2.5
    max_keepalive_connections: int = 20
    max_connections: int = 100
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @model_validator(mode="after")
    def resolve_model_aliases(self) -> Self:
        diagram_env = (
            os.getenv("DIAGRAM_LLM_MODEL")
            or os.getenv("MERMAID_LLM_MODEL")
            or os.getenv("DIAGRAM_MODEL")
            or os.getenv("MERMAID_MODEL")
        )
        if diagram_env:
            self.diagram_llm_model = diagram_env

        gemma_env = os.getenv("GEMMA_MODEL")
        if gemma_env and not os.getenv("LLM_MODEL"):
            self.llm_model = gemma_env

        vision_env = os.getenv("VISION_LLM_MODEL") or os.getenv("VISION_MODEL")
        if vision_env:
            self.vision_llm_model = vision_env

        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
