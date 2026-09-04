from __future__ import annotations

import re
from functools import lru_cache
from typing import Any

from backend.app.config import Settings, get_settings


class PromptInjectionGuard:
    def __init__(self, min_match_hits: int = 1) -> None:
        self.min_match_hits = max(1, int(min_match_hits))
        self._patterns: list[tuple[str, re.Pattern[str]]] = [
            ("ignore_instructions", re.compile(r"\b(ignore|bypass|override|forget)\b.{0,80}\b(instruction(?:s)?|rule(?:s)?|policy|guardrail(?:s)?)\b", re.IGNORECASE)),
            ("system_prompt_exfiltration", re.compile(r"\b(reveal|show|print|leak|expose)\b.{0,80}\b(system\s*prompt|hidden\s*prompt|developer\s*message(?:s)?|internal\s*instruction(?:s)?)\b", re.IGNORECASE)),
            ("role_escalation", re.compile(r"\b(you\s+are\s+now|act\s+as|pretend\s+to\s+be)\b.{0,80}\b(admin|root|developer|system)\b", re.IGNORECASE)),
            ("jailbreak_marker", re.compile(r"\b(do\s+anything\s+now|dan|jailbreak|unfiltered|no\s+restrictions)\b", re.IGNORECASE)),
            ("policy_evasion", re.compile(r"\b(do\s+not\s+follow|disable|turn\s+off)\b.{0,40}\b(safety|security|policy|filter)\b", re.IGNORECASE)),
            ("prompt_injection_chain", re.compile(r"\b(previous\s+instruction(?:s)?|previous\s+rule(?:s)?|new\s+instruction(?:s)?|forget\s+everything\s+above)\b", re.IGNORECASE)),
        ]

    def validate_user_prompt(self, user_prompt: str) -> bool:
        cleaned = (user_prompt or "").strip()
        matches = 0
        for _, pattern in self._patterns:
            if pattern.search(cleaned):
                matches += 1

        if matches >= self.min_match_hits:
            raise ValueError("Security Alert: Prompt Injection / Jailbreak Attack Blocked")

        return True


class PromptInjectionGuardService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.enabled = bool(self.settings.prompt_guard_enabled)
        self._guard = PromptInjectionGuard(min_match_hits=self.settings.prompt_guard_min_match_hits)
        self._allowlist = self._parse_allowlist(self.settings.prompt_guard_allowlist)

    def _parse_allowlist(self, raw: str) -> list[str]:
        if not raw.strip():
            return []
        parts = re.split(r"[,\n]", raw)
        return [part.strip().lower() for part in parts if part and part.strip()]

    def _is_allowlisted(self, prompt: str) -> bool:
        normalized = prompt.strip().lower()
        if not normalized:
            return False

        for item in self._allowlist:
            if item and item in normalized:
                return True
        return False

    def validate(self, prompt: str) -> dict[str, Any]:
        cleaned = (prompt or "").strip()
        if not cleaned:
            return {"checked": False, "blocked": False, "reason": "empty_prompt"}

        if self._is_allowlisted(cleaned):
            return {"checked": True, "blocked": False, "reason": "allowlisted_prompt"}

        if not self.enabled:
            return {"checked": False, "blocked": False, "reason": "prompt_guard_disabled"}

        try:
            self._guard.validate_user_prompt(cleaned)
            return {"checked": True, "blocked": False, "reason": None}
        except ValueError as exc:
            return {"checked": True, "blocked": True, "reason": str(exc)}
        except Exception as exc:
            if self.settings.prompt_guard_block_on_error:
                return {"checked": True, "blocked": True, "reason": f"prompt_guard_error: {exc}"}
            return {"checked": False, "blocked": False, "reason": f"prompt_guard_error: {exc}"}


@lru_cache(maxsize=1)
def get_prompt_injection_guard_service() -> PromptInjectionGuardService:
    return PromptInjectionGuardService()
