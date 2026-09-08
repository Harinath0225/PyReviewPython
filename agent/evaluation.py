from __future__ import annotations

from typing import Any

from agent.owasp_tool import OWASPWebsiteTool
from agent.review_tools import scan_python_source
from security.model_armor import ModelArmorService


class AgentEvaluationService:
    def __init__(self) -> None:
        self.armor = ModelArmorService()
        self.owasp = OWASPWebsiteTool()

    def evaluate(self, prompt: str, code_snippet: str = "", expected_keywords: list[str] | None = None) -> dict[str, Any]:
        armor = self.armor.check(prompt)
        findings = scan_python_source(code_snippet) if code_snippet else []
        owasp = self.owasp.lookup(findings)
        keywords = [item.lower() for item in (expected_keywords or []) if item]
        searchable = " ".join([
            "security review",
            " ".join(str(item.get("message", "")) for item in findings),
            " ".join(item["category"] for item in owasp),
        ]).lower()
        keyword_score = 100 if not keywords else round(sum(item in searchable for item in keywords) / len(keywords) * 100)
        dimensions = {
            "safety": 100 if not armor["blocked"] else 0,
            "deterministic_analysis": 100 if code_snippet and findings else 80 if not code_snippet else 40,
            "owasp_grounding": 100 if owasp else 60,
            "response_completeness": keyword_score,
        }
        score = round(sum(dimensions.values()) / len(dimensions))
        return {
            "status": "ok",
            "score": score,
            "grade": "A" if score >= 90 else "B" if score >= 75 else "C" if score >= 60 else "D",
            "dimensions": dimensions,
            "model_armor": armor,
            "findings": findings,
            "owasp": owasp,
            "recommendations": self._recommendations(dimensions),
        }

    def _recommendations(self, dimensions: dict[str, int]) -> list[str]:
        return [f"Improve {name.replace('_', ' ')}." for name, value in dimensions.items() if value < 80]