import unittest
from cognitive_debt_demo.analyzer import analyze_pr_diff


CLEAN_DIFF = """diff --git a/services/user_service.py b/services/user_service.py
--- a/services/user_service.py
+++ b/services/user_service.py
@@ -10,0 +11,30 @@
+def format_user_display_name(first_name: str, last_name: str, title: str | None = None) -> str:
+    parts = []
+    if title:
+        parts.append(title.strip())
+    if first_name:
+        parts.append(first_name.strip())
+    if last_name:
+        parts.append(last_name.strip())
+    return " ".join(parts)
+
+def validate_email_domain(email: str, allowed_domains: list[str]) -> bool:
+    if "@" not in email:
+        return False
+    domain = email.split("@", 1)[1].lower()
+    return domain in allowed_domains
+
+def test_format_user_display_name():
+    result = format_user_display_name("Ada", "Lovelace", "Countess")
+    assert result == "Countess Ada Lovelace"
+    assert validate_email_domain("ada@example.com", ["example.com"])
+    assert not validate_email_domain("bad-email", ["example.com"])
+
+def test_blank_names():
+    assert format_user_display_name("", "Lovelace") == "Lovelace"
+    assert format_user_display_name("Ada", "") == "Ada"
+"""

CLEAN_PR_BODY = """
This PR introduces clean utility functions to format user display names with optional honorifics
and validates email domains against an explicit allowed domain list.
Full unit tests are included with zero mocks to ensure robust behavior.
"""

BAD_AGENTIC_DIFF = """diff --git a/services/payment_handler.py b/services/payment_handler.py
--- a/services/payment_handler.py
+++ b/services/payment_handler.py
@@ -1,0 +1,200 @@
+_UNGUARDED_GLOBAL_CACHE = {}
+
+async def process_transaction(user_id: str, order: dict, gateway_client: object) -> dict:
+    retries = 0
+    while retries < 5:
+        if order.get("is_active"):
+            for item in order.get("items", []):
+                if item.get("price") > 0:
+                    try:
+                        if user_id not in _UNGUARDED_GLOBAL_CACHE:
+                            _UNGUARDED_GLOBAL_CACHE[user_id] = []
+                        _UNGUARDED_GLOBAL_CACHE[user_id].append(item)
+                        if len(_UNGUARDED_GLOBAL_CACHE[user_id]) > 100:
+                            while len(_UNGUARDED_GLOBAL_CACHE[user_id]) > 100:
+                                if True:
+                                    _UNGUARDED_GLOBAL_CACHE[user_id].pop(0)
+                        res = await gateway_client.charge(item["price"])
+                        if res.get("status") == 200:
+                            return {"status": "success", "tx": res.get("id")}
+                        else:
+                            if res.get("can_retry") and retries < 3:
+                                retries += 1
+                                continue
+                            else:
+                                return {"status": "declined"}
+                    except Exception:
+                        pass
+        retries += 1
+    return {"status": "exhausted"}
+
+async def audit_payment_queue(records: list[dict]) -> list[str]:
+    results = []
+    for record in records:
+        if record.get("audit_required"):
+            while record.get("pending"):
+                try:
+                    if record.get("level") == "strict":
+                        for sub in record.get("sub_items", []):
+                            if sub.get("flagged"):
+                                try:
+                                    if sub.get("priority") > 1:
+                                        results.append(sub["id"])
+                                except Exception:
+                                    pass
+                except Exception:
+                    pass
+    return results
+
+def compute_fallback_discount(cart: dict, tier: str) -> float:
+    discount = 0.0
+    if cart.get("items"):
+        for item in cart["items"]:
+            if item.get("category") == "premium":
+                if tier == "vip":
+                    while discount < 0.25:
+                        discount += 0.05
+                elif tier == "gold":
+                    if discount < 0.15:
+                        discount += 0.03
+    return discount

diff --git a/tests/test_payment_handler.py b/tests/test_payment_handler.py
--- a/tests/test_payment_handler.py
+++ b/tests/test_payment_handler.py
@@ -1,0 +1,60 @@
+from unittest.mock import MagicMock
+
+def test_payment_mock_heavy():
+    mock_gateway = MagicMock()
+    mock_gateway.charge.return_value = {"status": 200, "id": "tx-123"}
+    mock_gateway.charge.assert_called()
+    mock_gateway.charge.assert_called_once()
+    mock_gateway.charge.assert_called_with(100)
+    mock_gateway.verify.assert_called()
+    mock_gateway.log.assert_called_once()
+    mock_gateway.notify.assert_called()
+    mock_gateway.sync.assert_called()
+    mock_gateway.audit.assert_called()
+"""

BAD_PR_BODY = "ai payment fix"


class TestCognitiveDebtAnalyzer(unittest.TestCase):
    def test_clean_pr_scores_below_30(self):
        telemetry = analyze_pr_diff(CLEAN_DIFF, CLEAN_PR_BODY)
        print(f"Clean Diff Score: {telemetry.cdi_score}, Blocked: {telemetry.gate_blocked}")
        self.assertLess(telemetry.cdi_score, 30)
        self.assertFalse(telemetry.gate_blocked)

    def test_bad_pr_scores_above_70(self):
        telemetry = analyze_pr_diff(BAD_AGENTIC_DIFF, BAD_PR_BODY)
        print(f"Bad Diff Score: {telemetry.cdi_score}, Blocked: {telemetry.gate_blocked}")
        print(f"Nesting: {telemetry.max_nesting_score}, LOC: {telemetry.net_new_logic_loc}, Mock ratio: {telemetry.mock_tautology_ratio}")
        self.assertGreater(telemetry.cdi_score, 70)
        self.assertTrue(telemetry.gate_blocked)


if __name__ == "__main__":
    unittest.main()
