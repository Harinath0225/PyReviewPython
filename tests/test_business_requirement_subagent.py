from __future__ import annotations

import unittest
from fastapi.testclient import TestClient

from agent.business_requirement_subagent import BusinessRequirementSubagent
from agent.code_review_orchestrator import CodeReviewOrchestrator
from agents.code_review_agent.agent import root_agent
from backend.app import main
from tests.test_business_logic_flaws import SECURE_ORDER_CODE, VULNERABLE_ORDER_CODE


SAMPLE_BRD = """
# Feature: E-Commerce Returns & Proportional Discounts

## Executive Summary
This document specifies business rules for customer refunds and coupon stacking on orders.

## User Stories
As a customer, I want to return an individual item from my order, so that I receive an accurate refund for what I actually paid.

## Acceptance Criteria
- AC-1: Given an order with discounts, When an item is returned, Then the refund must equal the item's effective paid price.
- AC-2: Given a partial return, When subtotal drops below the threshold, Then the system must recalculate promotions.

## Business Rules
- Rule 1: Refund the item's purchase price based on proportional discount attribution.
- Rule 2: Threshold discounts apply to cart total when order exceeds $100.
- Rule 3: Send audit notification email to customer upon return completion.
"""

SAMPLE_JIRA_TICKET = """
Key: PAY-204
Summary: Implement proportional refund price calculation
Issue Type: Story
Priority: High

User Story:
As a finance manager, I want refunds to subtract proportional discounts, so that customers cannot exploit sticker price returns.

Acceptance Criteria:
- AC-1: Given discounted items When refund is triggered Then return effective_paid_price.
- AC-2: Ensure item price is verified against database.
"""

SAMPLE_TINY_PNG_DATA_URL = (
    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


class BusinessRequirementSubagentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.subagent = BusinessRequirementSubagent()
        self.client = TestClient(main.app)

    def test_brd_parsing_and_summary_creation(self) -> None:
        result = self.subagent.analyze_and_map(SAMPLE_BRD, code_snippet=VULNERABLE_ORDER_CODE)
        summary = result["summary"]
        self.assertIn("E-Commerce Returns", summary["title"])
        self.assertGreater(summary["user_stories_count"], 0)
        self.assertGreater(summary["acceptance_criteria_count"], 0)
        self.assertGreater(summary["business_rules_count"], 0)
        self.assertGreater(len(result["requirements"]), 0)

    def test_jira_ticket_parsing(self) -> None:
        result = self.subagent.analyze_and_map(SAMPLE_JIRA_TICKET, code_snippet=SECURE_ORDER_CODE)
        summary = result["summary"]
        self.assertEqual(summary["ticket_key"], "PAY-204")
        self.assertIn("proportional refund", summary["title"].lower())
        self.assertGreater(summary["user_stories_count"], 0)

    def test_screenshot_data_url_processing(self) -> None:
        payload = {"type": "jira_screenshot", "image_data": SAMPLE_TINY_PNG_DATA_URL}
        result = self.subagent.analyze_and_map(payload, code_snippet=VULNERABLE_ORDER_CODE)
        self.assertTrue(result["is_screenshot"])
        self.assertIn("summary", result)
        self.assertGreater(len(result["traceability_matrix"]), 0)

    def test_code_traceability_matrix_detects_vulnerable_order(self) -> None:
        result = self.subagent.analyze_and_map(SAMPLE_BRD, code_snippet=VULNERABLE_ORDER_CODE)
        matrix = result["traceability_matrix"]
        statuses = {m["status"] for m in matrix}
        self.assertIn("VULNERABLE", statuses)

        # Check vulnerability details
        vuln_item = next(m for m in matrix if m["status"] == "VULNERABLE")
        self.assertIn("Order.refund_item", [s.get("symbol") for s in vuln_item.get("mapped_symbols", [])])
        self.assertIn("effective_paid_price", vuln_item.get("remediation", ""))

        # Check findings
        rule_ids = {f.get("rule_id") for f in result["findings"]}
        self.assertIn("BIZ001", rule_ids)
        self.assertLess(result["coverage_score"], 80.0)

    def test_code_traceability_matrix_verifies_secure_order(self) -> None:
        result = self.subagent.analyze_and_map(SAMPLE_BRD, code_snippet=SECURE_ORDER_CODE)
        matrix = result["traceability_matrix"]
        statuses = {m["status"] for m in matrix}
        self.assertIn("COVERED", statuses)

        # Secure order uses effective_paid_price, so BIZ001 should not be flagged
        rule_ids = {f.get("rule_id") for f in result["findings"]}
        self.assertNotIn("BIZ001", rule_ids)

    def test_missing_requirement_identified_in_traceability_matrix(self) -> None:
        brd_with_missing = (
            "Feature: Notifications\n"
            "Requirement 1: Send SMS message to user phone number on successful purchase."
        )
        result = self.subagent.analyze_and_map(brd_with_missing, code_snippet=VULNERABLE_ORDER_CODE)
        matrix = result["traceability_matrix"]
        self.assertTrue(any(m["status"] == "MISSING" for m in matrix))
        missing_item = next(m for m in matrix if m["status"] == "MISSING")
        self.assertEqual(missing_item["coverage_score"], 0.0)

    def test_orchestrator_integration_returns_subagent_fields_and_dag_events(self) -> None:
        orchestrator = CodeReviewOrchestrator()
        result = orchestrator.review(
            code_snippet=VULNERABLE_ORDER_CODE,
            business_documents=[{"type": "brd", "content": SAMPLE_BRD}],
        )

        # Verify new subagent output keys in review result
        self.assertIn("business_summary", result)
        self.assertIn("business_requirements", result)
        self.assertIn("requirement_mappings", result)
        self.assertIn("business_coverage_score", result)
        self.assertGreater(len(result["requirement_mappings"]), 0)

        # Verify DAG event stream contains business_subagent milestones
        events = result["dag_events"]
        subagent_events = [e for e in events if e.get("node") == "business_subagent"]
        self.assertGreater(len(subagent_events), 0)
        event_names = {e.get("event") for e in subagent_events}
        self.assertIn("subagent_started", event_names)
        self.assertIn("requirements_summarized", event_names)
        self.assertIn("code_mapping_completed", event_names)
        self.assertIn("subagent_completed", event_names)

    def test_adk_agent_registers_subagent_and_tools(self) -> None:
        subagent_names = [a.name for a in getattr(root_agent, "sub_agents", [])]
        self.assertIn("business_requirement_subagent", subagent_names)

        root_tool_names = [t.__name__ for t in root_agent.tools]
        self.assertIn("analyze_and_map_business_requirements", root_tool_names)
        self.assertIn("extract_jira_or_brd_screenshot", root_tool_names)

    def test_api_business_mapping_endpoint(self) -> None:
        resp = self.client.post(
            "/api/v1/review/business-mapping",
            json={
                "business_document": SAMPLE_BRD,
                "code_snippet": VULNERABLE_ORDER_CODE,
            },
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "ok")
        self.assertIn("summary", data)
        self.assertIn("traceability_matrix", data)
        self.assertIn("coverage_score", data)
        self.assertGreater(len(data["traceability_matrix"]), 0)

    def test_api_review_with_screenshot_data_url(self) -> None:
        resp = self.client.post(
            "/api/v1/review",
            json={
                "code_snippet": VULNERABLE_ORDER_CODE,
                "business_screenshot": SAMPLE_TINY_PNG_DATA_URL,
            },
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("business_summary", data)
        self.assertIn("requirement_mappings", data)


if __name__ == "__main__":
    unittest.main()
