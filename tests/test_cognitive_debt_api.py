import unittest
from fastapi.testclient import TestClient
from backend.app.main import app
from cognitive_debt_demo.demo_runner import SAMPLE_BAD_DIFF, SAMPLE_BAD_PR_BODY, SAMPLE_CLEAN_DIFF, SAMPLE_CLEAN_PR_BODY


class TestCognitiveDebtAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_get_samples(self):
        res = self.client.get("/api/v1/cognitive-debt/samples")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("bad_pr", data)
        self.assertIn("clean_pr", data)

    def test_analyze_endpoint_bad_diff(self):
        res = self.client.post(
            "/api/v1/cognitive-debt/analyze",
            json={
                "diff_text": SAMPLE_BAD_DIFF,
                "pr_body": SAMPLE_BAD_PR_BODY,
                "extract_decisions": True,
            },
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("telemetry", data)
        self.assertIn("payload", data)
        self.assertIn("comment_markdown", data)
        telemetry = data["telemetry"]
        self.assertTrue(telemetry["gate_blocked"])
        self.assertGreaterEqual(telemetry["cdi_score"], 65)

    def test_explain_endpoint_handwavy(self):
        analyze_res = self.client.post(
            "/api/v1/cognitive-debt/analyze",
            json={
                "diff_text": SAMPLE_BAD_DIFF,
                "pr_body": SAMPLE_BAD_PR_BODY,
                "extract_decisions": True,
            },
        )
        self.assertEqual(analyze_res.status_code, 200)
        analyze_data = analyze_res.json()

        explain_res = self.client.post(
            "/api/v1/cognitive-debt/explain",
            json={
                "diff_text": SAMPLE_BAD_DIFF,
                "question": analyze_data["payload"]["socratic_question"],
                "author_reply": "/explain AI wrote it, looks fine, please approve.",
                "telemetry": analyze_data["telemetry"],
                "payload": analyze_data["payload"],
            },
        )
        self.assertEqual(explain_res.status_code, 200)
        explain_data = explain_res.json()
        self.assertIsNotNone(explain_data["verdict"])
        self.assertFalse(explain_data["verdict"]["approved"])
        self.assertIn("REJECTED", explain_data["comment_markdown"])


if __name__ == "__main__":
    unittest.main()
