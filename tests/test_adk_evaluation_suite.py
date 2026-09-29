"""Comprehensive ADK Testing Suite for Code Review Agent.

Verifies:
1. Google ADK EvalConfig and custom metric registration.
2. BLEU score evaluation against reference fixes.
3. METEOR score evaluation (precision/recall harmonic mean + chunk penalty).
4. Tokens consumed tracking and budget adherence.
5. Invocation latency tracking against SLA.
6. Tool call trajectory evaluation (expected tool sequence verification).
7. LLM-as-a-Judge multi-criteria code quality rating.
8. Native ADK WebUI and CLI eval set compatibility.
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from google.adk.evaluation.eval_case import IntermediateData, Invocation
from google.adk.evaluation.eval_config import EvalConfig
from google.adk.evaluation.eval_metrics import EvalMetric
from google.adk.evaluation.evaluator import EvalStatus
from google.adk.evaluation.local_eval_sets_manager import load_eval_set_from_file
from google.adk.evaluation.metric_evaluator_registry import (
    DEFAULT_METRIC_EVALUATOR_REGISTRY,
    register_custom_metrics_from_config,
)
from google.adk.evaluation.trajectory_evaluator import TrajectoryEvaluator
from google.genai import types

from agents.code_review_agent.eval_metrics_custom import (
    _count_tokens,
    calculate_meteor_score,
    calculate_sentence_bleu,
    evaluate_bleu,
    evaluate_latency,
    evaluate_llm_judge,
    evaluate_meteor,
    evaluate_tokens,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
AGENT_DIR = REPO_ROOT / "agents" / "code_review_agent"


def test_eval_config_and_custom_metrics_registration():
    """Validates test_config.json schema and custom metric registration into ADK registry."""
    config_path = AGENT_DIR / "test_config.json"
    assert config_path.exists(), "test_config.json must exist in agent folder"

    with open(config_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    eval_config = EvalConfig.model_validate(data)
    assert "tool_trajectory_avg_score" in eval_config.criteria
    assert "bleu_score" in eval_config.criteria
    assert "meteor_score" in eval_config.criteria
    assert "latency_score" in eval_config.criteria
    assert "tokens_consumed_score" in eval_config.criteria

    # Register into ADK's registry
    register_custom_metrics_from_config(eval_config)
    registered_names = [m.metric_name for m in DEFAULT_METRIC_EVALUATOR_REGISTRY.get_registered_metrics()]

    assert "bleu_score" in registered_names
    assert "meteor_score" in registered_names
    assert "latency_score" in registered_names
    assert "tokens_consumed_score" in registered_names


def test_bleu_and_meteor_nlp_scoring():
    """Validates BLEU and METEOR scores on candidate defensive remediations."""
    candidate = "Use parameterized queries: cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))"
    reference = "Remediate SQL injection with parameterized queries: cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))"

    bleu = calculate_sentence_bleu(candidate, reference)
    meteor = calculate_meteor_score(candidate, reference)

    assert 0.4 <= bleu <= 1.0, f"Expected strong BLEU score, got {bleu}"
    assert 0.5 <= meteor <= 1.0, f"Expected strong METEOR score, got {meteor}"

    # ADK evaluation function
    inv_actual = Invocation(
        user_content=types.Content(parts=[types.Part.from_text(text="Review query")]),
        final_response=types.Content(parts=[types.Part.from_text(text=candidate)]),
    )
    inv_expected = Invocation(
        user_content=types.Content(parts=[types.Part.from_text(text="Review query")]),
        final_response=types.Content(parts=[types.Part.from_text(text=reference)]),
    )

    bleu_res = evaluate_bleu(EvalMetric(metric_name="bleu_score", threshold=0.30), [inv_actual], [inv_expected])
    assert bleu_res.overall_eval_status == EvalStatus.PASSED
    assert bleu_res.overall_score >= 0.30

    meteor_res = evaluate_meteor(EvalMetric(metric_name="meteor_score", threshold=0.40), [inv_actual], [inv_expected])
    assert meteor_res.overall_eval_status == EvalStatus.PASSED
    assert meteor_res.overall_score >= 0.40


def test_token_and_latency_tracking():
    """Validates token tracking against budget and latency tracking against SLA."""
    text = "Review this Python code snippet for SQL injection and unsafe subprocess execution."
    tokens = _count_tokens(text)
    assert 10 <= tokens <= 30

    inv_actual = Invocation(
        user_content=types.Content(parts=[types.Part.from_text(text=text)]),
        final_response=types.Content(parts=[types.Part.from_text(text="Safe parameterized fix provided.")]),
        intermediate_data=IntermediateData(
            tool_uses=[types.FunctionCall(name="scan_python_code", args={"code_snippet": "..."})]
        ),
    )

    # Tokens evaluation (within 4000 token budget)
    tok_res = evaluate_tokens(EvalMetric(metric_name="tokens_consumed_score", threshold=0.8), [inv_actual])
    assert tok_res.overall_eval_status == EvalStatus.PASSED
    assert tok_res.overall_score == 1.0

    # Latency evaluation (within 12s SLA)
    lat_res = evaluate_latency(EvalMetric(metric_name="latency_score", threshold=0.8), [inv_actual])
    assert lat_res.overall_eval_status == EvalStatus.PASSED
    assert lat_res.overall_score == 1.0


def test_tool_trajectory_evaluation():
    """Validates tool call trajectory matching using ADK's TrajectoryEvaluator."""
    inv_actual = Invocation(
        user_content=types.Content(parts=[types.Part.from_text(text="Review code")]),
        final_response=types.Content(parts=[types.Part.from_text(text="Done")]),
        intermediate_data=IntermediateData(
            tool_uses=[types.FunctionCall(name="scan_python_code", args={"code_snippet": "query = f'SELECT * FROM users'"})]
        ),
    )
    inv_expected = Invocation(
        user_content=types.Content(parts=[types.Part.from_text(text="Review code")]),
        final_response=types.Content(parts=[types.Part.from_text(text="Done")]),
        intermediate_data=IntermediateData(
            tool_uses=[types.FunctionCall(name="scan_python_code", args={"code_snippet": "query = f'SELECT * FROM users'"})]
        ),
    )

    evaluator = TrajectoryEvaluator(threshold=1.0)
    result = evaluator.evaluate_invocations([inv_actual], [inv_expected])
    assert result.overall_score == 1.0
    assert result.overall_eval_status == EvalStatus.PASSED


def test_llm_judge_evaluation():
    """Validates LLM-as-a-Judge multi-criteria evaluation on defensive code remediation."""
    remediation_text = (
        "### Security Vulnerability: SQL Injection (OWASP A03:2021)\n"
        "The query uses string formatting which is vulnerable to SQL injection.\n"
        "```python\n"
        "import sqlite3\n"
        "def get_user(db, user_id):\n"
        "    with sqlite3.connect(db) as conn:\n"
        "        cursor = conn.cursor()\n"
        "        cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))\n"
        "        return cursor.fetchone()\n"
        "```\n"
        "Always use parameterized queries and input boundary verification."
    )

    inv_actual = Invocation(
        user_content=types.Content(parts=[types.Part.from_text(text="Review function")]),
        final_response=types.Content(parts=[types.Part.from_text(text=remediation_text)]),
    )

    judge_res = evaluate_llm_judge(EvalMetric(metric_name="llm_judge_score", threshold=0.60), [inv_actual])
    assert judge_res.overall_eval_status == EvalStatus.PASSED
    assert judge_res.overall_score >= 0.70


def test_eval_set_loading():
    """Verifies eval_set_1.evalset.json contains complete test cases for ADK WebUI."""
    evalset_path = AGENT_DIR / "eval_set_1.evalset.json"
    eval_set = load_eval_set_from_file(str(evalset_path), "eval_set_1")

    assert len(eval_set.eval_cases) >= 3
    case_ids = [c.eval_id for c in eval_set.eval_cases]
    assert "eval_sql_injection_defense" in case_ids
    assert "eval_command_injection_defense" in case_ids
    assert "eval_business_requirement_traceability" in case_ids

    # Check each case has user query and expected tool trajectory
    for case in eval_set.eval_cases:
        assert case.conversation is not None
        assert len(case.conversation) > 0
        inv = case.conversation[0]
        assert inv.user_content is not None
        assert inv.final_response is not None
        assert inv.intermediate_data is not None
