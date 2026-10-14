from __future__ import annotations

from typing import Any
from fastapi import APIRouter, HTTPException

from cognitive_debt_demo.analyzer import analyze_pr_diff
from cognitive_debt_demo.agent_gate import (
    evaluate_author_explanation,
    extract_decisions_and_question,
    render_pr_comment,
)
from cognitive_debt_demo.demo_runner import (
    SAMPLE_BAD_DIFF,
    SAMPLE_BAD_PR_BODY,
    SAMPLE_CLEAN_DIFF,
    SAMPLE_CLEAN_PR_BODY,
)
from cognitive_debt_demo.schemas import (
    CognitiveDebtAnalyzeRequest,
    CognitiveDebtExplainRequest,
    CognitiveDebtResponse,
    PRReviewPayload,
    TelemetryResult,
)

router = APIRouter(prefix="/api/v1/cognitive-debt", tags=["cognitive-debt"])


@router.get("/samples")
async def get_sample_diffs() -> dict[str, Any]:
    """Returns preset sample PR diffs and descriptions for demonstration."""
    return {
        "bad_pr": {
            "name": "Async Payment Handler (High Cognitive Debt)",
            "diff_text": SAMPLE_BAD_DIFF,
            "pr_body": SAMPLE_BAD_PR_BODY,
            "description": "Unguarded global cache, swallowed exceptions, tight retry loops, and 100% tautological mocks.",
        },
        "clean_pr": {
            "name": "User Domain Utilities (Low Cognitive Debt)",
            "diff_text": SAMPLE_CLEAN_DIFF,
            "pr_body": SAMPLE_CLEAN_PR_BODY,
            "description": "Flat utility functions, complete PR documentation, and standard assertion unit tests.",
        },
    }


@router.post("/analyze", response_model=CognitiveDebtResponse)
async def analyze_cognitive_debt(payload: CognitiveDebtAnalyzeRequest) -> CognitiveDebtResponse:
    """Analyzes a PR diff for cognitive debt, returning AST telemetry, implicit agent decisions, and Socratic gate question."""
    diff_text = payload.diff_text.strip()
    if not diff_text:
        raise HTTPException(status_code=400, detail="diff_text cannot be empty.")

    telemetry = analyze_pr_diff(diff_text, payload.pr_body)

    if payload.extract_decisions:
        review_payload = extract_decisions_and_question(diff_text, telemetry)
    else:
        review_payload = PRReviewPayload(
            decisions=[],
            socratic_question="What failure modes or concurrency boundaries should be validated?",
        )

    comment_markdown = render_pr_comment(telemetry, review_payload)

    return CognitiveDebtResponse(
        telemetry=telemetry,
        payload=review_payload,
        comment_markdown=comment_markdown,
        verdict=None,
    )


@router.post("/explain", response_model=CognitiveDebtResponse)
async def explain_cognitive_debt(payload: CognitiveDebtExplainRequest) -> CognitiveDebtResponse:
    """Evaluates author explanation for Socratic question to flip gate from BLOCKED to APPROVED."""
    diff_text = payload.diff_text.strip()
    question = payload.question.strip()
    author_reply = payload.author_reply.strip()

    if not question:
        raise HTTPException(status_code=400, detail="question cannot be empty.")
    if not author_reply:
        raise HTTPException(status_code=400, detail="author_reply cannot be empty.")

    telemetry = payload.telemetry or analyze_pr_diff(diff_text)
    review_payload = payload.payload or extract_decisions_and_question(diff_text, telemetry)

    verdict = evaluate_author_explanation(question, author_reply, diff_text)
    comment_markdown = render_pr_comment(telemetry, review_payload, verdict)

    return CognitiveDebtResponse(
        telemetry=telemetry,
        payload=review_payload,
        comment_markdown=comment_markdown,
        verdict=verdict,
    )
