from __future__ import annotations

import json
from typing import Any

from backend.app.config import get_settings

try:
    from google import genai
except Exception:
    genai = None


class LLMReasoner:
    def __init__(self) -> None:
        self.settings = get_settings()

    def generate_review_reasoning(
        self,
        findings: list[dict[str, Any]],
        historical_context: str,
        owasp_context: list[str],
    ) -> dict[str, Any]:
        provider = (self.settings.llm_provider or "gemini").strip().lower()
        if provider != "gemini":
            fallback = self._deterministic_fallback(findings=findings, historical_context=historical_context)
            fallback["provider"] = provider
            fallback["model"] = self.settings.llm_model
            fallback["fallback_used"] = True
            fallback["fallback_reason"] = f"Unsupported llm_provider '{provider}'."
            return fallback

        return self._generate_with_gemini(findings=findings, historical_context=historical_context, owasp_context=owasp_context)

    def _generate_with_gemini(
        self,
        findings: list[dict[str, Any]],
        historical_context: str,
        owasp_context: list[str],
    ) -> dict[str, Any]:
        api_key = self.settings.gemini_api_key
        if not api_key or genai is None:
            fallback = self._deterministic_fallback(findings=findings, historical_context=historical_context)
            fallback["provider"] = "gemini"
            fallback["model"] = self.settings.llm_model
            fallback["fallback_used"] = True
            fallback["fallback_reason"] = "Missing GEMINI_API_KEY or google-genai package."
            return fallback

        client = genai.Client(api_key=api_key)
        prompt = self._build_prompt(findings=findings, historical_context=historical_context, owasp_context=owasp_context)

        try:
            response = client.models.generate_content(
                model=self.settings.llm_model,
                contents=prompt,
            )
            text = getattr(response, "text", "") or ""
            parsed = self._parse_json_response(text)
            if parsed is None:
                fallback = self._deterministic_fallback(findings=findings, historical_context=historical_context)
                fallback["provider"] = "gemini"
                fallback["model"] = self.settings.llm_model
                fallback["fallback_used"] = True
                fallback["fallback_reason"] = "Model response was not valid JSON; deterministic fallback used."
                return fallback

            summary = str(parsed.get("summary", "")).strip() or "Generated review summary is empty."
            recommendations = parsed.get("recommendations", [])
            if not isinstance(recommendations, list):
                recommendations = []

            normalized = [str(item).strip() for item in recommendations if str(item).strip()]
            if not normalized:
                normalized = ["Review and remediate highest severity findings first."]

            return {
                "summary": summary,
                "recommendations": normalized[:8],
                "provider": "gemini",
                "model": self.settings.llm_model,
                "fallback_used": True,
                "fallback_reason": "Deterministic fallback used because no LLM call was available.",
            }
        except Exception as exc:
            fallback = self._deterministic_fallback(findings=findings, historical_context=historical_context)
            fallback["provider"] = "gemini"
            fallback["model"] = self.settings.llm_model
            fallback["fallback_used"] = True
            fallback["fallback_reason"] = str(exc)
            return fallback

    def _build_prompt(
        self,
        findings: list[dict[str, Any]],
        historical_context: str,
        owasp_context: list[str],
    ) -> str:
        top_findings = findings[:8]
        serialized_findings = json.dumps(top_findings, ensure_ascii=False)
        owasp_text = ", ".join(owasp_context)
        history_text = historical_context or "No historical context available."

        return (
            "You are a senior application security and code quality reviewer. "
            "Given deterministic findings from static checks, produce concise reasoning and remediation priorities.\n\n"
            f"Finding count: {len(top_findings)} (non-zero means issues are present).\n"
            "Severity policy: Critical / Blocker (severity=critical, PR blocking=yes), "
            "Major / Required (severity=major, PR blocking=yes), "
            "Minor / Suggestion (severity=minor, PR blocking=no), and "
            "Info / Nitpick (severity=info, PR blocking=no).\n"
            f"OWASP context: {owasp_text}\n\n"
            f"Historical context:\n{history_text}\n\n"
            f"Findings JSON:\n{serialized_findings}\n\n"
            "If findings are provided, do not claim the review is clean and do not state that no issues were found. "
            "Treat hardcoded API keys, passwords, tokens, and other live credentials as Critical / Blocker. "
            "Special focus: Evaluate business logic vulnerabilities including 'Buy to Discount, Return to Profit' (refunding sticker price instead of proportionally discounted paid price), threshold abuse padding, and additive coupon stacking without margin floors.\n\n"
            "Return strictly valid JSON with this schema only: "
            '{"summary": "string", "recommendations": ["string", "string"]}. '
            "Do not include markdown fences. Keep summary under 90 words."
        )

    def _parse_json_response(self, text: str) -> dict[str, Any] | None:
        cleaned = (text or "").strip()
        if not cleaned:
            return None

        try:
            parsed = json.loads(cleaned)
            if isinstance(parsed, dict):
                return parsed
            return None
        except json.JSONDecodeError:
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start == -1 or end == -1 or end <= start:
                return None
            snippet = cleaned[start : end + 1]
            try:
                parsed = json.loads(snippet)
                return parsed if isinstance(parsed, dict) else None
            except json.JSONDecodeError:
                return None

    def _deterministic_fallback(self, findings: list[dict[str, Any]], historical_context: str) -> dict[str, Any]:
        if not findings:
            summary = "No major issues found. The code passes deterministic checks and has no obvious high-risk patterns."
            if historical_context:
                summary = f"{summary} Prior history has similar recommendations to keep current safeguards in place."
            return {
                "summary": summary,
                "recommendations": [
                    "Keep review gates in place for future changes.",
                    "Track metrics and secure defaults as the code evolves.",
                ],
                "provider": "deterministic",
                "model": "deterministic-fallback",
                "fallback_used": False,
                "fallback_reason": None,
            }

        recommendations: list[str] = []
        for finding in findings[:5]:
            message = finding.get("recommendation", "Review the flagged area.")
            label = finding.get("severity_label", str(finding.get("severity", "info")).title())
            blocking = "Yes" if finding.get("pr_blocking", False) else "No"
            recommendations.append(
                f"### **[{label}] ({finding.get('severity', 'info').title()})** "
                f"Line {finding.get('line', 1)}\n{message} PR Blocking: {blocking}."
            )

        has_biz_flaws = any(f.get("category") == "business_logic" or str(f.get("rule_id", "")).startswith("BIZ") for f in findings)
        if has_biz_flaws:
            summary = (
                "The review detected critical business logic vulnerabilities, including refund price attribution exploits "
                "('Buy to Discount, Return to Profit') and unconstrained discount stacking. A proportional discount attribution "
                "architecture (effective_paid_price) and threshold clawback rules must be enforced before closing the review."
            )
        else:
            summary = (
                "The deterministic checks found risky patterns and quality issues. "
                "The highest-priority items are related to unsafe execution, secret handling, and code quality gates. "
                "A fix plan should be required before closing the review."
            )
        if historical_context:
            recommendations.append("Leverage similar historical fixes from prior reviews to speed remediation.")

        return {
            "summary": summary,
            "recommendations": recommendations,
            "provider": "deterministic",
            "model": "deterministic-fallback",
            "fallback_used": True,
            "fallback_reason": "Deterministic fallback used because no LLM call was available.",
        }
