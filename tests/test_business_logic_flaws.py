from __future__ import annotations

import unittest

from agent.business_logic_analyzer import BusinessLogicAnalyzer
from agent.code_review_orchestrator import CodeReviewOrchestrator
from agent.review_tools import scan_python_source


VULNERABLE_ORDER_CODE = '''
class OrderItem:
    def __init__(self, item_id: str, price: float):
        self.item_id = item_id
        self.price = price

class Order:
    def __init__(self, items, promo_code=None):
        self.items = items
        self.promo_code = promo_code
        self.subtotal = sum(i.price for i in self.items)
        self.discount = 0.0
        if self.subtotal >= 100.0:
            self.discount += self.subtotal * 0.20
        if self.promo_code == "WELCOME10":
            self.discount += 10.0

    def refund_item(self, item_id: str) -> float:
        for item in self.items:
            if item.item_id == item_id:
                return item.price
        raise ValueError("Item not found")
'''

SECURE_ORDER_CODE = '''
class SecureOrderItem:
    def __init__(self, item_id: str, name: str, price: float):
        self.item_id = item_id
        self.name = name
        self.price = price
        self.effective_paid_price = price

class SecureOrder:
    def __init__(self, items: list, promo_code: str = None):
        self.items = items
        self.promo_code = promo_code
        self.subtotal = sum(i.price for i in self.items)
        self.total_discount = 0.0
        self._apply_discounts()

    def _apply_discounts(self):
        discount = 0.0
        if self.subtotal >= 100.0:
            discount += self.subtotal * 0.20
        if self.promo_code == "WELCOME10":
            discount += 10.0

        self.total_discount = min(self.subtotal, discount)
        if self.subtotal > 0:
            for item in self.items:
                item_share = item.price / self.subtotal
                item_discount = self.total_discount * item_share
                item.effective_paid_price = round(item.price - item_discount, 2)

    def calculate_total(self) -> float:
        return round(self.subtotal - self.total_discount, 2)

    def refund_item(self, item_id: str) -> float:
        for item in self.items:
            if item.item_id == item_id:
                return item.effective_paid_price
        raise ValueError("Item not found")
'''


class BusinessLogicFlawTests(unittest.TestCase):
    def test_vulnerable_order_detects_all_business_logic_flaws(self) -> None:
        findings = scan_python_source(VULNERABLE_ORDER_CODE)
        rule_ids = {f.get("rule_id") for f in findings}

        # Verify BIZ001: Sticker Price Refund Exploit ("Buy to Discount, Return to Profit")
        self.assertIn("BIZ001", rule_ids)
        biz001 = next(f for f in findings if f.get("rule_id") == "BIZ001")
        self.assertEqual(biz001["severity"], "critical")
        self.assertTrue(biz001["pr_blocking"])
        self.assertIn("Sticker Price Refund Exploit", biz001["message"])
        self.assertIn("proportional discount attribution", biz001["recommendation"])

        # Verify BIZ002: Threshold Abuse / Missing Promotion Recalculation
        self.assertIn("BIZ002", rule_ids)
        biz002 = next(f for f in findings if f.get("rule_id") == "BIZ002")
        self.assertEqual(biz002["severity"], "major")
        self.assertTrue(biz002["pr_blocking"])
        self.assertIn("Threshold", biz002["message"])

        # Verify BIZ003: Unconstrained Discount Stacking / Negative Margin Risk
        self.assertIn("BIZ003", rule_ids)
        biz003 = next(f for f in findings if f.get("rule_id") == "BIZ003")
        self.assertEqual(biz003["severity"], "major")
        self.assertIn("Discount Stacking", biz003["message"])

    def test_secure_order_passes_cleanly_without_sticker_price_exploit(self) -> None:
        findings = scan_python_source(SECURE_ORDER_CODE)
        rule_ids = {f.get("rule_id") for f in findings}

        # The proportional attribution and effective_paid_price pattern eliminates BIZ001
        self.assertNotIn("BIZ001", rule_ids)
        self.assertNotIn("BIZ003", rule_ids)

    def test_flawed_requirements_detection(self) -> None:
        analyzer = BusinessLogicAnalyzer()
        req_doc = """
        Feature: Shopping Cart & Returns
        Requirement 1: Refund the item's purchase price when a customer requests a return.
        Requirement 2: Threshold discounts apply to cart total when order exceeds $100.
        Requirement 3: Coupons stack with global sales additively.
        """
        flaws = analyzer.analyze_flawed_requirements(req_doc)
        flaw_rules = {f["rule_id"] for f in flaws}

        self.assertIn("BIZ001", flaw_rules)
        self.assertIn("BIZ002", flaw_rules)
        self.assertIn("BIZ003", flaw_rules)

        # Check mitigation details
        biz001_flaw = next(f for f in flaws if f["rule_id"] == "BIZ001")
        self.assertIn("proportional", biz001_flaw["mitigation"].lower())

    def test_full_review_orchestrator_detects_business_logic_flaws(self) -> None:
        orchestrator = CodeReviewOrchestrator()
        result = orchestrator.review(code_snippet=VULNERABLE_ORDER_CODE)

        self.assertGreater(result["total_findings"], 0)
        rule_ids = {f.get("rule_id") for f in result["findings"]}
        self.assertIn("BIZ001", rule_ids)

        # Check that business_logic_findings contains the detected flaws
        biz_findings = result.get("business_logic_findings", [])
        self.assertTrue(any(f.get("rule_id") == "BIZ001" for f in biz_findings))

        # Check summary mentions business logic vulnerabilities
        summary = result["summary"].lower()
        self.assertTrue("business logic" in summary or "refund" in summary or "discount" in summary)


if __name__ == "__main__":
    unittest.main()
