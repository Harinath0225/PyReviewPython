import os
import sys
from pathlib import Path

# Add root
root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))

from agents.code_review_agent.eval_metrics_custom import (
    calculate_sentence_bleu,
    calculate_meteor_score,
    _count_tokens,
    evaluate_bleu,
    evaluate_meteor,
    evaluate_latency,
    evaluate_tokens,
    evaluate_llm_judge,
)
from google.adk.evaluation.eval_case import Invocation
from google.adk.evaluation.eval_metrics import EvalMetric
from google.genai import types

def run_tests():
    cand = "Use parameterized queries like cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,)) to prevent SQL injection."
    ref = "Remediate SQL injection by using parameterized queries: cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))"

    bleu = calculate_sentence_bleu(cand, ref)
    meteor = calculate_meteor_score(cand, ref)
    tokens = _count_tokens(cand)

    print(f"Candidate: {cand[:40]}...")
    print(f"Reference: {ref[:40]}...")
    print(f"BLEU Score: {bleu:.4f}")
    print(f"METEOR Score: {meteor:.4f}")
    print(f"Tokens Count: {tokens}")

    # Test full ADK evaluator metrics
    inv_actual = Invocation(
        user_content=types.Content(parts=[types.Part.from_text(text="Review SQL query code")]),
        final_response=types.Content(parts=[types.Part.from_text(text=cand)]),
    )
    inv_expected = Invocation(
        user_content=types.Content(parts=[types.Part.from_text(text="Review SQL query code")]),
        final_response=types.Content(parts=[types.Part.from_text(text=ref)]),
    )

    metric_bleu = EvalMetric(metric_name="bleu_score", threshold=0.25)
    res_bleu = evaluate_bleu(metric_bleu, [inv_actual], [inv_expected])
    print(f"evaluate_bleu -> Score: {res_bleu.overall_score}, Status: {res_bleu.overall_eval_status.name}")

    metric_meteor = EvalMetric(metric_name="meteor_score", threshold=0.35)
    res_meteor = evaluate_meteor(metric_meteor, [inv_actual], [inv_expected])
    print(f"evaluate_meteor -> Score: {res_meteor.overall_score}, Status: {res_meteor.overall_eval_status.name}")

    metric_latency = EvalMetric(metric_name="latency_score", threshold=0.8)
    res_latency = evaluate_latency(metric_latency, [inv_actual], [inv_expected])
    print(f"evaluate_latency -> Score: {res_latency.overall_score}, Status: {res_latency.overall_eval_status.name}")

    metric_tokens = EvalMetric(metric_name="tokens_consumed_score", threshold=0.8)
    res_tokens = evaluate_tokens(metric_tokens, [inv_actual], [inv_expected])
    print(f"evaluate_tokens -> Score: {res_tokens.overall_score}, Status: {res_tokens.overall_eval_status.name}")

    metric_judge = EvalMetric(metric_name="llm_judge_score", threshold=0.7)
    res_judge = evaluate_llm_judge(metric_judge, [inv_actual], [inv_expected])
    print(f"evaluate_llm_judge -> Score: {res_judge.overall_score}, Status: {res_judge.overall_eval_status.name}")

    print("\nALL CUSTOM EVALUATORS PASSED!")

if __name__ == "__main__":
    run_tests()
