from __future__ import annotations

import unittest

from agent.review_tools import scan_python_source


class ReviewToolsTests(unittest.TestCase):
    def test_detects_apikey_variants(self) -> None:
        snippet = "\n".join(
            [
                "def load_configuration():",
                "    apiKey = 'demo-key-replace-with-secret-manager'",
                "    apikey = 'demo-key-2'",
                "    client_secret = 'demo-secret'",
                "    return apiKey",
            ]
        )

        findings = scan_python_source(snippet)
        sec002 = [item for item in findings if item.get("rule_id") == "SEC002"]
        evidence = {str(item.get("evidence", "")).lower() for item in sec002}

        self.assertGreaterEqual(len(sec002), 3)
        self.assertIn("apikey", evidence)
        self.assertIn("apikey", {value.replace("_", "") for value in evidence})
        self.assertIn("client_secret", evidence)

    def test_syntax_error_keeps_sensitive_fallback_findings(self) -> None:
        # Intentionally incomplete call to emulate partial/long snippets from UI paste operations.
        snippet = "\n".join(
            [
                "def broken():",
                "    apikey = 'demo-password-change-me'",
                "    payload = {",
                "    return payload",
            ]
        )

        findings = scan_python_source(snippet)
        rule_ids = [str(item.get("rule_id")) for item in findings]

        self.assertIn("PY001", rule_ids)
        self.assertIn("SEC002", rule_ids)

    def test_long_single_line_assignment_is_detected(self) -> None:
        long_value = "x" * 2000
        snippet = f"apikey = '{long_value}'"

        findings = scan_python_source(snippet)
        sec002 = [item for item in findings if item.get("rule_id") == "SEC002"]

        self.assertEqual(len(sec002), 1)
        self.assertEqual(sec002[0].get("severity"), "critical")
        self.assertEqual(sec002[0].get("severity_label"), "Critical / Blocker")
        self.assertTrue(sec002[0].get("pr_blocking"))


if __name__ == "__main__":
    unittest.main()