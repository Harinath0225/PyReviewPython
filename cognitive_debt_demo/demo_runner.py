from __future__ import annotations

import argparse
import sys
import time

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from cognitive_debt_demo.analyzer import analyze_pr_diff
from cognitive_debt_demo.agent_gate import (
    evaluate_author_explanation,
    extract_decisions_and_question,
    render_pr_comment,
)

SAMPLE_BAD_DIFF = """diff --git a/services/payment_handler.py b/services/payment_handler.py
--- a/services/payment_handler.py
+++ b/services/payment_handler.py
@@ -1,0 +1,180 @@
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

SAMPLE_BAD_PR_BODY = "ai payment fix and retry handler"

SAMPLE_CLEAN_DIFF = """diff --git a/services/user_service.py b/services/user_service.py
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
+"""

SAMPLE_CLEAN_PR_BODY = """
This PR introduces clean utility functions to format user display names with optional honorifics
and validates email domains against an explicit allowed domain list.
Full unit tests are included with zero mocks to ensure robust behavior.
"""


def run_demo(
    diff_text: str = SAMPLE_BAD_DIFF,
    pr_body: str = SAMPLE_BAD_PR_BODY,
    interactive: bool = True,
    sample_reply_choice: int = 2,
) -> None:
    print("=" * 72)
    print("🧠  COGNITIVE DEBT PR GATE — ZERO-INFRA MVP")
    print("   Plugs into PR reviews to surface AI agent assumptions & enforce Socratic gates")
    print("=" * 72)
    print()

    # Step 1: Telemetry & Decision Extraction
    print("⏳ [Step 1/2] Analyzing PR Diff with Native AST Telemetry...")
    t0 = time.perf_counter()
    telemetry = analyze_pr_diff(diff_text, pr_body)
    dt = time.perf_counter() - t0

    print(f"   AST Nesting Complexity Score : {telemetry.max_nesting_score} pts")
    print(f"   Net New Logic LOC            : {telemetry.net_new_logic_loc} lines (Body words: {len(pr_body.split())})")
    print(f"   Mock Tautology Ratio         : {telemetry.mock_tautology_ratio * 100:.1f}%")
    print(f"   Composite CDI Score          : {telemetry.cdi_score} / 100")
    print(f"   Gate Status                  : {'🚨 BLOCKED (CDI >= 65)' if telemetry.gate_blocked else '✅ PASS (CDI < 65)'}")
    print(f"   Analysis completed in {dt*1000:.1f}ms")
    print()

    print("🤖 Calling LLM Decision Extractor (1 call per PR review)...")
    payload = extract_decisions_and_question(diff_text, telemetry)

    initial_comment = render_pr_comment(telemetry, payload)
    print("\n" + "-" * 72)
    print("📝 GENERATED GITHUB PR REVIEW COMMENT (STEP 1):")
    print("-" * 72)
    print(initial_comment)
    print("-" * 72)

    if not telemetry.gate_blocked:
        print("\n✨ PR passed cognitive debt threshold with low debt. Gate is already UNLOCKED.")
        return

    # Step 2: Socratic Gate & Author /explain Evaluation
    print("\n🔐 [Step 2/2] Socratic Gate Challenge Triggered!")
    print(f"Question: \"{payload.socratic_question}\"")
    print()

    author_reply = ""
    if interactive:
        try:
            print("Options for demonstration:")
            print("  [1] Try Hand-wavy reply: \"/explain AI wrote it, looks fine to me, please just approve.\"")
            print("  [2] Try Solid rationale: \"/explain To ensure transaction atomicity and prevent duplicate charges on restart, each transaction carries an idempotent UUID passed to the gateway charge() call. The gateway deduplicates identical transaction IDs on its side. The in-memory cache is purely an ephemeral read cache to avoid re-querying active orders, so a process crash safely re-reads the relational DB state on restart without duplicate charges.\"")
            print("  [3] Type your own custom reply")
            choice = input("\nSelect [1-3] or type your explanation (default: 2): ").strip()

            if choice == "1":
                author_reply = "/explain AI wrote it, looks fine to me, please just approve."
            elif choice == "2" or not choice:
                author_reply = (
                    "/explain To ensure transaction atomicity and prevent duplicate charges on restart, each transaction "
                    "carries an idempotent UUID passed to the gateway charge() call. The gateway deduplicates identical "
                    "transaction IDs on its side. The in-memory cache is purely an ephemeral read cache to avoid re-querying "
                    "active orders, so a process crash safely re-reads the relational DB state on restart without duplicate charges."
                )
            elif choice == "3":
                author_reply = input("Enter your /explain reply: ").strip()
            else:
                author_reply = choice if choice.startswith("/explain") else f"/explain {choice}"
        except (EOFError, KeyboardInterrupt):
            author_reply = (
                "/explain To ensure transaction atomicity and prevent duplicate charges on restart, each transaction "
                "carries an idempotent UUID passed to the gateway charge() call. The gateway deduplicates identical "
                "transaction IDs on its side. The in-memory cache is purely an ephemeral read cache, so a process crash "
                "safely re-reads the relational DB state on restart without duplicate charges."
            )
    else:
        if sample_reply_choice == 1:
            author_reply = "/explain AI wrote it, looks fine to me, please just approve."
        else:
            author_reply = (
                "/explain To ensure transaction atomicity and prevent duplicate charges on restart, each transaction "
                "carries an idempotent UUID passed to the gateway charge() call. The gateway deduplicates identical "
                "transaction IDs on its side. The in-memory cache is purely an ephemeral read cache to avoid re-querying "
                "active orders, so a process crash safely re-reads the relational DB state on restart without duplicate charges."
            )

    print(f"\nDeveloper Submitted:")
    print(f"   \"{author_reply}\"")
    print("\n⚖️ Evaluating author reply with LLM Gate Judge (1 call on author reply)...")

    verdict = evaluate_author_explanation(payload.socratic_question, author_reply, diff_text)
    print(f"   Verdict:  {'✅ APPROVED' if verdict.approved else '❌ REJECTED'}")
    print(f"   Feedback: {verdict.feedback}")

    transition = "🚨 BLOCKED ➔ ✅ UNLOCKED" if verdict.approved else "🚨 BLOCKED (Remains Blocked)"
    print(f"   Status Check Transition: {transition}")

    updated_comment = render_pr_comment(telemetry, payload, verdict)
    print("\n" + "-" * 72)
    print("📝 UPDATED GITHUB PR REVIEW COMMENT (POST-EXPLAIN):")
    print("-" * 72)
    print(updated_comment)
    print("-" * 72)


def main() -> None:
    parser = argparse.ArgumentParser(description="Cognitive Debt PR Gate Demo Runner")
    parser.add_argument("--auto", action="store_true", help="Run automatically without waiting for prompt input")
    parser.add_argument("--clean", action="store_true", help="Run against the clean PR diff")
    parser.add_argument("--handwavy", action="store_true", help="Test rejection using hand-wavy reply in auto mode")
    args = parser.parse_args()

    if args.clean:
        run_demo(diff_text=SAMPLE_CLEAN_DIFF, pr_body=SAMPLE_CLEAN_PR_BODY, interactive=False)
    else:
        reply_choice = 1 if args.handwavy else 2
        run_demo(
            diff_text=SAMPLE_BAD_DIFF,
            pr_body=SAMPLE_BAD_PR_BODY,
            interactive=not args.auto,
            sample_reply_choice=reply_choice,
        )


if __name__ == "__main__":
    main()
