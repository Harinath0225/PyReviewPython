import unittest
from cognitive_debt_demo.schemas import TelemetryResult, PRReviewPayload, ImplicitDecision, ExplainVerdict
from cognitive_debt_demo.agent_gate import (
    extract_decisions_and_question,
    evaluate_author_explanation,
    render_pr_comment,
)
from tests.test_cognitive_debt_analyzer import BAD_AGENTIC_DIFF, BAD_PR_BODY


class TestCognitiveDebtGate(unittest.TestCase):
    def test_extract_decisions_and_question(self):
        telemetry = TelemetryResult(
            max_nesting_score=221,
            net_new_logic_loc=68,
            mock_tautology_ratio=1.0,
            cdi_score=76,
            gate_blocked=True,
        )
        payload = extract_decisions_and_question(BAD_AGENTIC_DIFF, telemetry)
        self.assertIsInstance(payload, PRReviewPayload)
        self.assertLessEqual(len(payload.decisions), 3)
        self.assertGreaterEqual(len(payload.decisions), 1)
        self.assertTrue(bool(payload.socratic_question))
        for d in payload.decisions:
            self.assertTrue(bool(d.title))
            self.assertTrue(bool(d.hidden_assumption))
            self.assertTrue(bool(d.production_risk))

    def test_evaluate_handwavy_explanation(self):
        question = "How does this cache handle memory limits under 10k webhooks?"
        handwavy_reply = "/explain AI wrote it, looks fine to me, please just approve."
        verdict = evaluate_author_explanation(question, handwavy_reply, BAD_AGENTIC_DIFF)
        self.assertIsInstance(verdict, ExplainVerdict)
        self.assertFalse(verdict.approved)
        self.assertTrue("reject" in verdict.feedback.lower() or "dismiss" in verdict.feedback.lower() or not verdict.approved)

    def test_evaluate_solid_explanation(self):
        question = "How does this cache handle memory limits under 10k webhooks?"
        solid_reply = (
            "/explain We recognize the risk of in-memory caching under load. In this staging deployment, "
            "we are capping the cache at 1,000 entries and limiting webhook concurrency via an asyncio semaphore. "
            "For production, Ticket #ENG-4421 tracks moving to Redis with a 5-minute TTL and dead-letter queue."
        )
        verdict = evaluate_author_explanation(question, solid_reply, BAD_AGENTIC_DIFF)
        self.assertIsInstance(verdict, ExplainVerdict)
        self.assertTrue(verdict.approved)

    def test_render_pr_comment_blocked_and_unlocked(self):
        telemetry = TelemetryResult(
            max_nesting_score=221,
            net_new_logic_loc=68,
            mock_tautology_ratio=1.0,
            cdi_score=76,
            gate_blocked=True,
        )
        payload = PRReviewPayload(
            decisions=[
                ImplicitDecision(
                    title="Unbounded Cache",
                    file_and_line="payment.py:1",
                    hidden_assumption="RAM is infinite",
                    production_risk="OOM crash under load",
                )
            ],
            socratic_question="How will this handle 10k concurrent webhooks?",
        )
        comment_blocked = render_pr_comment(telemetry, payload)
        self.assertIn("<!-- cognitive-debt-demo", comment_blocked)
        self.assertIn("BLOCKED", comment_blocked)
        self.assertIn("Unbounded Cache", comment_blocked)
        self.assertIn("How will this handle 10k concurrent webhooks?", comment_blocked)

        verdict = ExplainVerdict(approved=True, feedback="Valid Redis migration plan.")
        comment_unlocked = render_pr_comment(telemetry, payload, verdict)
        self.assertIn("UNLOCKED", comment_unlocked)
        self.assertIn("APPROVED", comment_unlocked)


if __name__ == "__main__":
    unittest.main()
