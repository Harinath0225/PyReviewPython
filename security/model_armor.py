from __future__ import annotations

from typing import Any

from security.prompt_injection_guard import PromptInjectionGuard


class ModelArmorService:
    """Local, deterministic input screening for prompts sent to an LLM."""

    def __init__(self, min_match_hits: int = 1) -> None:
        self.guard = PromptInjectionGuard(min_match_hits=min_match_hits)

    def check(self, text: str, source: str = "prompt") -> dict[str, Any]:
        cleaned = (text or "").strip()
        if not cleaned:
            return {"status": "skipped", "blocked": False, "source": source, "match_count": 0, "threats": []}

        threats: list[str] = []
        for name, pattern in self.guard._patterns:
            if pattern.search(cleaned):
                threats.append(name)

        return {
            "status": "blocked" if threats else "passed",
            "blocked": bool(threats),
            "source": source,
            "match_count": len(threats),
            "threats": threats,
            "provider": "local-programmatic",
        }


def get_model_armor_service() -> ModelArmorService:
    return ModelArmorService()