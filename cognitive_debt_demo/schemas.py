from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class TelemetryResult(BaseModel):
    max_nesting_score: int = Field(
        ...,
        description="AST control-flow + nesting depth penalty"
    )
    net_new_logic_loc: int = Field(
        ...,
        description="Added non-comment/non-blank code lines"
    )
    mock_tautology_ratio: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="0.0 to 1.0: mock assertions / total assertions"
    )
    cdi_score: int = Field(
        ...,
        ge=0,
        le=100,
        description="0 to 100 composite score"
    )
    gate_blocked: bool = Field(
        ...,
        description="True if cdi_score >= 65"
    )


class ImplicitDecision(BaseModel):
    title: str = Field(..., description="Short summary of the implicit architectural decision")
    file_and_line: str = Field(..., description="File path and line or scope reference")
    hidden_assumption: str = Field(..., description="What the AI coding agent assumed silently")
    production_risk: str = Field(..., description="How it fails under load or edge cases")


class PRReviewPayload(BaseModel):
    decisions: list[ImplicitDecision] = Field(
        ...,
        max_length=3,
        description="Top implicit architectural decisions made by the coding agent (max 3)"
    )
    socratic_question: str = Field(
        ...,
        description="1 sharp edge-case question for the author"
    )


class ExplainVerdict(BaseModel):
    approved: bool = Field(..., description="Whether the author explanation passes the gate")
    feedback: str = Field(..., description="Why the explanation passed or what is still missing")


class CognitiveDebtAnalyzeRequest(BaseModel):
    diff_text: str
    pr_body: str = ""
    extract_decisions: bool = True


class CognitiveDebtExplainRequest(BaseModel):
    diff_text: str
    question: str
    author_reply: str
    telemetry: TelemetryResult | None = None
    payload: PRReviewPayload | None = None


class CognitiveDebtResponse(BaseModel):
    telemetry: TelemetryResult
    payload: PRReviewPayload
    comment_markdown: str
    verdict: ExplainVerdict | None = None
