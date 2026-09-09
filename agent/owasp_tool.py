from __future__ import annotations

from typing import Any

import httpx


_OWASP = {
    "SEC001": ("A03:2021 Injection", "https://owasp.org/Top10/A03_2021-Injection/"),
    "SEC003": ("A03:2021 Injection", "https://owasp.org/Top10/A03_2021-Injection/"),
    "SEC002": ("A02:2021 Cryptographic Failures", "https://owasp.org/Top10/A02_2021-Cryptographic_Failures/"),
    "SSR": ("A10:2021 Server-Side Request Forgery", "https://owasp.org/Top10/A10_2021-Server-Side_Request_Forgery_%28SSRF%29/"),
}
_DEFAULT = ("A05:2021 Security Misconfiguration", "https://owasp.org/Top10/A05_2021-Security_Misconfiguration/")


class OWASPWebsiteTool:
    """Categorizes findings and verifies the linked OWASP page is reachable."""

    def __init__(self, timeout_seconds: float = 3.0) -> None:
        self.timeout_seconds = timeout_seconds

    def lookup(self, findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        seen: set[str] = set()
        for finding in findings:
            rule_id = str(finding.get("rule_id", ""))
            category, url = _OWASP.get(rule_id, _DEFAULT)
            if category in seen:
                continue
            seen.add(category)
            results.append({
                "category": category,
                "url": url,
                "importance": self._importance(finding),
                "rule_ids": [rule_id] if rule_id else [],
                "source": "OWASP website tool",
                "reachable": self._is_reachable(url),
            })
        return results

    def _is_reachable(self, url: str) -> bool:
        try:
            response = httpx.get(url, timeout=self.timeout_seconds, follow_redirects=True)
            return response.is_success
        except httpx.HTTPError:
            return False

    def _importance(self, finding: dict[str, Any]) -> str:
        severity = str(finding.get("severity", "info")).lower()
        return {
            "critical": "Immediate remediation; this may permit compromise or secret exposure.",
            "major": "High priority remediation before release.",
            "minor": "Address during normal hardening work.",
        }.get(severity, "Informational security context.")