from __future__ import annotations

from typing import Any


def build_story(payload: dict[str, Any]) -> dict[str, Any]:
    title = str(payload.get("title") or "Improve code review finding").strip()
    summary = str(payload.get("summary") or "Remediate the identified code review findings.").strip()
    findings = payload.get("findings") if isinstance(payload.get("findings"), list) else []
    acceptance = [
        f"Resolve finding {item.get('rule_id', 'GENERIC')} at line {item.get('line', '?')}."
        for item in findings if isinstance(item, dict)
    ] or ["Review and validate the change with automated tests."]
    return {
        "title": title,
        "business_document": {
            "problem": summary,
            "business_impact": "Unresolved security or quality findings increase release and maintenance risk.",
            "proposed_outcome": "A tested implementation that addresses the prioritized findings.",
            "success_metrics": ["No critical findings remain", "Automated tests pass"],
        },
        "jira_story": {
            "summary": title,
            "description": f"As an engineering team, we want to {summary.lower()} so that releases are safer and easier to maintain.",
            "acceptance_criteria": acceptance,
            "priority": "High" if any(item.get("severity") == "critical" for item in findings if isinstance(item, dict)) else "Medium",
        },
    }