from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from backend.app.config import get_settings
from cognitive_debt_demo.schemas import (
    ExplainVerdict,
    ImplicitDecision,
    PRReviewPayload,
    TelemetryResult,
)

logger = logging.getLogger("cognitive_debt.agent_gate")


def _get_genai_client() -> tuple[Any, str | None]:
    """Returns (client, model_name) if available, else (None, None)."""
    settings = get_settings()
    api_key = os.getenv("GEMINI_API_KEY") or settings.gemini_api_key
    if not api_key:
        return None, None

    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        model = (
            os.getenv("COGNITIVE_DEBT_MODEL")
            or os.getenv("DIAGRAM_LLM_MODEL")
            or settings.diagram_llm_model
            or "gemini-3.1-flash-lite"
        )
        return client, model
    except Exception as exc:
        logger.warning("Could not initialize google.genai client: %s", exc)
        return None, None


def _clean_json_markdown(text: str) -> str:
    """Strips markdown code fence wrappers from JSON string."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def _fallback_extract_decisions(diff_text: str, telemetry: TelemetryResult) -> PRReviewPayload:
    """Deterministic extraction of implicit agent decisions when LLM is unavailable."""
    decisions: list[ImplicitDecision] = []
    text_lower = diff_text.lower()

    # 1. Unbounded In-Memory Cache
    if "cache" in text_lower or "_dict" in text_lower or "{}" in diff_text:
        decisions.append(
            ImplicitDecision(
                title="Unbounded In-Memory State Cache",
                file_and_line="services/payment_handler.py:1",
                hidden_assumption="Assumed single-process execution and infinite worker RAM with no TTL or eviction policy.",
                production_risk="Uncontrolled memory growth triggers OOM kills under load; state is fragmented across multi-worker deployments.",
            )
        )

    # 2. Silent Exception Suppression
    if "except exception" in text_lower or "pass" in text_lower:
        decisions.append(
            ImplicitDecision(
                title="Silent Exception Suppression",
                file_and_line="services/payment_handler.py:26",
                hidden_assumption="Assumed failures during external gateway calls are non-fatal and safe to discard silently.",
                production_risk="Masks critical outages, rate limits, and network drops, resulting in ghost payment drops without telemetry.",
            )
        )

    # 3. Synchronous Concurrency / Mock Tautology
    if telemetry.mock_tautology_ratio > 0.5 or "assert_called" in text_lower:
        decisions.append(
            ImplicitDecision(
                title="Tautological Mock Verification",
                file_and_line="tests/test_payment_handler.py:4",
                hidden_assumption="Assumed asserting that mock methods were invoked validates business transaction invariants.",
                production_risk="False confidence in CI; tests pass green while critical state changes, schema contracts, and failures break.",
            )
        )
    elif "while" in text_lower or "retry" in text_lower:
        decisions.append(
            ImplicitDecision(
                title="Unguarded Tight Retry Loop",
                file_and_line="services/payment_handler.py:5",
                hidden_assumption="Assumed external gateway failures recover immediately without exponential backoff or jitter.",
                production_risk="Cascading thundering herd locks upstream dependencies and induces IP rate-limit bans.",
            )
        )

    # Fill default if diff didn't trigger specific patterns
    if not decisions:
        decisions.append(
            ImplicitDecision(
                title="Implicit Architectural Boundary",
                file_and_line="module.py:1",
                hidden_assumption="Assumed standard happy-path inputs without explicit parameter boundary validation.",
                production_risk="Edge-case input structures may escape exception boundaries under production concurrency.",
            )
        )

    socratic_question = (
        "How does this implementation handle multi-worker concurrency and memory limits if 10,000 concurrent "
        "payment webhooks hit this service simultaneously under degraded network latency?"
    )

    return PRReviewPayload(
        decisions=decisions[:3],
        socratic_question=socratic_question,
    )


def extract_decisions_and_question(diff_text: str, telemetry: TelemetryResult) -> PRReviewPayload:
    """Extracts top 3 implicit architectural decisions and 1 Socratic question from PR diff."""
    client, model = _get_genai_client()
    if client is None or not model:
        return _fallback_extract_decisions(diff_text, telemetry)

    prompt = f"""You are a Principal Software Architect reviewing a pull request generated by an AI coding agent.
Your mission is to surface Cognitive Debt: implicit architectural decisions, silent assumptions, and edge-case risks.

Ignore syntax, linting, code style, or formatting.

PR Telemetry:
- AST Nesting Complexity Score: {telemetry.max_nesting_score}
- Net New Logic LOC: {telemetry.net_new_logic_loc}
- Mock Tautology Ratio: {telemetry.mock_tautology_ratio:.2f}
- Composite Cognitive Debt Index (CDI): {telemetry.cdi_score}/100

PR Diff:
```diff
{diff_text[:6000]}
```

Analyze the diff and extract:
1. Exactly up to 3 implicit architectural decisions made by the coding agent without human documentation.
2. 1 sharp Socratic question challenging the author on a concrete failure mode or architectural tradeoff.

Respond ONLY with valid JSON matching this schema:
{{
  "decisions": [
    {{
      "title": "<Short descriptive title, e.g. Unbounded In-Memory Cache>",
      "file_and_line": "<path/to/file.py:line>",
      "hidden_assumption": "<What the AI agent silently assumed>",
      "production_risk": "<How this fails under load, concurrency, or failure states>"
    }}
  ],
  "socratic_question": "<One sharp, direct question for the author regarding failure modes or scale>"
}}
"""

    try:
        from google.genai import types as genai_types

        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                temperature=0.1,
                automatic_function_calling=genai_types.AutomaticFunctionCallingConfig(disable=True),
            ),
        )
        text = getattr(response, "text", "") or ""
        cleaned = _clean_json_markdown(text)
        data = json.loads(cleaned)

        raw_decisions = data.get("decisions", [])
        decisions = [
            ImplicitDecision(
                title=str(d.get("title", "Implicit Assumption")),
                file_and_line=str(d.get("file_and_line", "unknown:1")),
                hidden_assumption=str(d.get("hidden_assumption", "")),
                production_risk=str(d.get("production_risk", "")),
            )
            for d in raw_decisions[:3]
        ]
        socratic_question = str(data.get("socratic_question", "")).strip()
        if not socratic_question:
            socratic_question = "What concrete telemetry and boundary safeguards prevent state desynchronization under load?"

        if not decisions:
            return _fallback_extract_decisions(diff_text, telemetry)

        return PRReviewPayload(decisions=decisions, socratic_question=socratic_question)

    except Exception as exc:
        logger.warning("LLM extraction failed (%s); using deterministic fallback.", exc)
        return _fallback_extract_decisions(diff_text, telemetry)


def _fallback_evaluate_explanation(question: str, author_reply: str) -> ExplainVerdict:
    """Deterministic evaluation of developer /explain reply."""
    reply = author_reply.strip()
    if reply.startswith("/explain"):
        reply = reply[len("/explain"):].strip()

    words = reply.split()
    lower_reply = reply.lower()

    if len(words) < 5 or len(reply) < 15:
        return ExplainVerdict(
            approved=False,
            feedback="Explanation is too brief. Please provide a substantive architectural justification or failure-mode mitigation.",
        )

    dismissive_phrases = [
        "ai wrote it",
        "copilot wrote it",
        "looks fine",
        "looks good",
        "it works",
        "works for me",
        "just approve",
        "skip",
        "whatever",
        "trust the bot",
        "don't know",
        "dont know",
        "no idea",
    ]
    for phrase in dismissive_phrases:
        if phrase in lower_reply:
            return ExplainVerdict(
                approved=False,
                feedback=(
                    f"Rejected: Hand-wavy explanation detected ('{phrase}'). "
                    "You must demonstrate genuine understanding of the concurrency, memory, or failure tradeoffs."
                ),
            )

    technical_terms = {
        "redis", "ttl", "memory", "concurrency", "distributed", "lock",
        "exponential", "backoff", "circuit breaker", "idempotency", "bounded",
        "lru", "retry", "fallback", "database", "load", "scale", "worker",
        "mitigation", "architecture", "cache", "queue", "eviction", "stateless",
        "transaction", "rollback", "asyncio", "semaphore", "invalidation",
    }
    matched_terms = [t for t in technical_terms if t in lower_reply]

    if matched_terms or len(words) >= 12:
        reasons = ", ".join(matched_terms[:3]) if matched_terms else "sound structural rationale"
        return ExplainVerdict(
            approved=True,
            feedback=(
                f"Approved: Explanation articulates valid design awareness and mitigations ({reasons}). "
                "Cognitive Debt Gate unlocked."
            ),
        )

    return ExplainVerdict(
        approved=False,
        feedback="Explanation lacks concrete technical mitigations for concurrency or memory constraints. Please elaborate.",
    )


def evaluate_author_explanation(question: str, author_reply: str, diff_text: str = "") -> ExplainVerdict:
    """Evaluates whether an author's /explain reply demonstrates genuine understanding."""
    client, model = _get_genai_client()
    if client is None or not model:
        return _fallback_evaluate_explanation(question, author_reply)

    reply_clean = author_reply.strip()
    if reply_clean.startswith("/explain"):
        reply_clean = reply_clean[len("/explain"):].strip()

    prompt = f"""You are a Principal Software Architect serving as an automated Cognitive Debt Gate Judge.
A PR was blocked due to cognitive debt in the code, and the author was challenged with this Socratic Question:

Socratic Question:
"{question}"

Author's /explain Response:
"{reply_clean}"

Context (the PR diff that caused the question):
```diff
{diff_text[:2000]}
```

Judge Instructions:
IMPORTANT: We already know the diff code has cognitive debt (that is why the gate was blocked). Do NOT reject merely because the code has flaws.
Your ONLY role is to judge whether the human author's /explain response demonstrates genuine comprehension of the question and articulates a thoughtful engineering explanation, operational context, or mitigation strategy.

Rubric:
- "approved": true -> The author demonstrates real understanding of the architectural tradeoff, concurrency, memory, or failure modes, explaining their rationale or mitigation plan.
- "approved": false -> The author provides a hand-wavy, dismissive, evasive, or lazy answer (e.g. "AI wrote it", "looks fine to me", "just approve", "it works on my machine", or empty/superficial non-answers).

Respond ONLY with valid JSON:
{{
  "approved": true or false,
  "feedback": "<1-2 sentence constructive feedback for the PR comment summarizing why the explanation is accepted or why it was rejected as hand-wavy>"
}}
"""

    try:
        from google.genai import types as genai_types

        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                temperature=0.0,
                automatic_function_calling=genai_types.AutomaticFunctionCallingConfig(disable=True),
            ),
        )
        text = getattr(response, "text", "") or ""
        cleaned = _clean_json_markdown(text)
        data = json.loads(cleaned)

        approved = bool(data.get("approved", False))
        feedback = str(data.get("feedback", "")).strip()
        if not feedback:
            feedback = "Gate evaluation completed." if approved else "Explanation insufficient."

        return ExplainVerdict(approved=approved, feedback=feedback)

    except Exception as exc:
        logger.warning("LLM evaluation failed (%s); using deterministic fallback.", exc)
        return _fallback_evaluate_explanation(question, author_reply)


def render_pr_comment(
    telemetry: TelemetryResult,
    payload: PRReviewPayload,
    verdict: ExplainVerdict | None = None,
) -> str:
    """Renders the GitHub PR review comment with hidden state and markdown dashboard."""
    # Hidden state tag containing serialized question so bot is stateless across webhook runs
    state_payload = {
        "question": payload.socratic_question,
        "cdi_score": telemetry.cdi_score,
        "gate_blocked": telemetry.gate_blocked,
    }
    state_tag = f"<!-- cognitive-debt-demo {json.dumps(state_payload)} -->\n"

    # Status header
    is_unlocked = verdict is not None and verdict.approved
    if is_unlocked:
        header = f"## ✅ Cognitive Debt Gate: UNLOCKED (CDI: {telemetry.cdi_score}/100)"
    elif telemetry.gate_blocked:
        header = f"## 🚨 Cognitive Debt Gate: BLOCKED (CDI: {telemetry.cdi_score}/100)"
    else:
        header = f"## ℹ️ Cognitive Debt Gate: PASSED (CDI: {telemetry.cdi_score}/100)"

    # Metric breakdown
    c_pts = min(40, telemetry.max_nesting_score * 2)
    l_pts = min(35, int((telemetry.net_new_logic_loc / 300) * 35))
    t_pts = int(telemetry.mock_tautology_ratio * 25)

    metric_table = (
        "| Metric | Observed Value | CDI Contribution | Threshold / Weight |\n"
        "| :--- | :--- | :--- | :--- |\n"
        f"| **AST Nesting Complexity** | `{telemetry.max_nesting_score}` points | **{c_pts} / 40 pts** | Max 40 pts (+2 / depth > 2) |\n"
        f"| **Undocumented Logic Burst** | `{telemetry.net_new_logic_loc}` added LOC | **{l_pts} / 35 pts** | Max 35 pts (1.5x if body < 30 words) |\n"
        f"| **Test Tautology (Mock Ratio)** | `{telemetry.mock_tautology_ratio * 100:.1f}%` mock calls | **{t_pts} / 25 pts** | Max 25 pts (Mock vs real asserts) |\n"
        f"| **Composite CDI Score** | **{telemetry.cdi_score} / 100** | **Total Debt** | **Block Gate at ≥ 65** |\n"
    )

    # Decisions section
    decisions_lines = [
        "### 🧠 What Your Coding Agent Decided For You\n",
        "> *The coding agent introduced the following implicit architectural assumptions without explicit documentation:*\n",
    ]
    for idx, dec in enumerate(payload.decisions, 1):
        decisions_lines.append(
            f"{idx}. **{dec.title}** (`{dec.file_and_line}`)\n"
            f"   - **Hidden Assumption:** {dec.hidden_assumption}\n"
            f"   - **Production Risk:** {dec.production_risk}\n"
        )
    decisions_block = "\n".join(decisions_lines)

    # Socratic question / Verdict section
    if is_unlocked:
        gate_box = (
            "### 🔓 Socratic Gate Verdict: APPROVED\n"
            f"> **Question:** {payload.socratic_question}\n"
            ">\n"
            f"> **Author Rationale:** Verified\n"
            f"> **Judge Feedback:** {verdict.feedback}\n"
            "\n"
            "*PR status check has been updated to passing. Safe to merge.*"
        )
    elif verdict is not None and not verdict.approved:
        gate_box = (
            "### ❌ Socratic Gate Verdict: REJECTED\n"
            f"> **Question:** {payload.socratic_question}\n"
            ">\n"
            f"> **Judge Feedback:** {verdict.feedback}\n"
            "\n"
            "**Action Required:** Reply with `/explain <your rationale>` providing technical justification to unlock."
        )
    else:
        gate_box = (
            "### 🔐 Socratic Gate Question\n"
            f"> **{payload.socratic_question}**\n"
            ">\n"
            "> *Reply with `/explain <your rationale>` to justify this design and unlock this PR check.*"
        )

    return f"{state_tag}\n{header}\n\n{metric_table}\n\n{decisions_block}\n\n{gate_box}\n"
