from __future__ import annotations

import ast
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

OWASP_TOP_10 = [
    "Broken Access Control",
    "Cryptographic Failures",
    "Injection",
    "Insecure Design",
    "Security Misconfiguration",
    "Vulnerable and Outdated Components",
    "Identification and Authentication Failures",
    "Software and Data Integrity Failures",
    "Security Logging and Monitoring Failures",
    "Server-Side Request Forgery (SSRF)",
]

_SENSITIVE_NAME_TOKENS = {
    "apikey",
    "secret",
    "token",
    "password",
    "passwd",
    "pwd",
    "accesskey",
    "clientsecret",
    "privatekey",
    "authkey",
}

_SENSITIVE_ASSIGNMENT_RE = re.compile(
    r"^\s*([A-Za-z_][A-Za-z0-9_\.]*)\s*=\s*([\"']).{4,}\2\s*$",
    re.IGNORECASE,
)

_SEVERITY_POLICY = {
    "critical": {"label": "Critical / Blocker", "pr_blocking": True},
    "major": {"label": "Major / Required", "pr_blocking": True},
    "minor": {"label": "Minor / Suggestion", "pr_blocking": False},
    "info": {"label": "Info / Nitpick (Nit)", "pr_blocking": False},
}


def _python_ast_issues(source: str) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        syntax_issue = {
            "line": exc.lineno or 1,
            "severity": "critical",
            "rule_id": "PY001",
            "category": "syntax",
            "message": f"Python syntax error: {exc.msg}",
            "recommendation": "Fix the syntax before review continues.",
            "evidence": exc.text.strip() if exc.text else "",
        }
        # Keep scanning lexically so partial diffs / long incomplete snippets still report security signals.
        return [syntax_issue, *_lexical_fallback_issues(source)]

    suspicious_calls = {
        "eval": "Avoid dynamic execution; prefer explicit parsing or safe APIs.",
        "exec": "Avoid runtime code execution from untrusted input.",
        "subprocess.run": "Validate the command input and consider restricting subprocess access.",
        "subprocess.Popen": "Validate the command input and consider restricting subprocess access.",
        "pickle.loads": "Deserialization from untrusted input can lead to code execution.",
        "yaml.load": "Use safe loaders like yaml.safe_load instead of yaml.load.",
        "requests.get": "Ensure outbound requests are constrained and validated. Consider timeouts.",
    }

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func_name = _call_name(node.func)
            if func_name in suspicious_calls:
                issues.append({
                    "line": getattr(node, "lineno", 1),
                    "severity": "critical" if func_name in {"eval", "exec", "pickle.loads"} else "major",
                    "rule_id": "SEC001",
                    "category": "security",
                    "message": f"Suspicious call detected: {func_name}",
                    "recommendation": suspicious_calls[func_name],
                    "evidence": func_name,
                })

    sql_fstring_variables: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.JoinedStr):
            target_names = [target.id for target in node.targets if isinstance(target, ast.Name)]
            sql_text = "".join(item.value for item in node.value.values if isinstance(item, ast.Constant)).lower()
            if any(keyword in sql_text for keyword in ("select ", "insert ", "update ", "delete ")):
                sql_fstring_variables.update(target_names)

        if isinstance(node, ast.Call) and _call_name(node.func).split(".")[-1] in {"execute", "executemany"}:
            query_argument = node.args[0] if node.args else None
            is_formatted_sql = isinstance(query_argument, ast.JoinedStr)
            is_tainted_sql = isinstance(query_argument, ast.Name) and query_argument.id in sql_fstring_variables
            if is_formatted_sql or is_tainted_sql:
                issues.append({
                    "line": getattr(node, "lineno", 1),
                    "severity": "critical",
                    "rule_id": "SEC003",
                    "category": "security",
                    "message": "SQL query is built with string formatting or interpolation.",
                    "recommendation": "Use parameterized SQL queries and pass user values as bound parameters instead of interpolating them into SQL syntax.",
                    "evidence": "SQL interpolation",
                    "replacement": (
                        "query = \"SELECT * FROM users WHERE username = ? AND password = ?\"\n"
                        "cursor.execute(query, (username, password))"
                    ),
                })

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            is_literal_assignment = _is_hardcoded_literal(node.value)
            for target in node.targets:
                target_name = _extract_assignment_target_name(target)
                if target_name and _looks_sensitive_identifier(target_name):
                    issues.append({
                        "line": getattr(node, "lineno", 1),
                        "severity": "critical" if is_literal_assignment else "major",
                        "rule_id": "SEC002",
                        "category": "security",
                        "message": "Sensitive value assigned in code.",
                        "recommendation": "Load secrets from environment variables or a secret manager instead of hardcoding them.",
                        "evidence": target_name,
                    })

        if isinstance(node, ast.AnnAssign):
            target_name = _extract_assignment_target_name(node.target)
            if target_name and _looks_sensitive_identifier(target_name):
                is_literal_assignment = _is_hardcoded_literal(node.value)
                issues.append({
                    "line": getattr(node, "lineno", 1),
                    "severity": "critical" if is_literal_assignment else "major",
                    "rule_id": "SEC002",
                    "category": "security",
                    "message": "Sensitive value assigned in code.",
                    "recommendation": "Load secrets from environment variables or a secret manager instead of hardcoding them.",
                    "evidence": target_name,
                })

    for node in ast.walk(tree):
        if isinstance(node, ast.Assert):
            issues.append({
                "line": getattr(node, "lineno", 1),
                "severity": "minor",
                "rule_id": "PY002",
                "category": "quality",
                "message": "Use of assert is not recommended in production code.",
                "recommendation": "Replace assert statements with explicit validation and exceptions.",
                "evidence": "assert",
            })

    issues.extend(_business_logic_ast_issues(tree, source))

    return issues


def _business_logic_ast_issues(tree: ast.AST, source: str) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    source_lower = source.lower()
    has_global_discount = any(tok in source_lower for tok in ["discount", "promo_code", "coupon", "voucher"])
    has_global_proportional = any(tok in source_lower for tok in [
        "effective_paid_price", "item_discount", "item_share", "proportional", "paid_price", "allocated_discount"
    ])

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            class_text = ast.get_source_segment(source, node) or ""
            class_lower = class_text.lower()
            has_class_discount = any(tok in class_lower for tok in ["discount", "promo_code", "coupon", "voucher"]) or has_global_discount
            has_class_proportional = any(tok in class_lower for tok in [
                "effective_paid_price", "item_discount", "item_share", "proportional", "paid_price", "allocated_discount"
            ]) or has_global_proportional

            for method in node.body:
                if isinstance(method, ast.FunctionDef):
                    # BIZ001: Refund item returns sticker price without proportional attribution
                    if any(term in method.name.lower() for term in ["refund", "return_item", "process_refund"]):
                        for sub in ast.walk(method):
                            if isinstance(sub, ast.Return) and sub.value:
                                is_price_attr = isinstance(sub.value, ast.Attribute) and sub.value.attr == "price"
                                is_raw_price = isinstance(sub.value, ast.Name) and sub.value.id == "price"
                                if (is_price_attr or is_raw_price) and has_class_discount and not has_class_proportional:
                                    issues.append({
                                        "line": getattr(sub, "lineno", method.lineno),
                                        "severity": "critical",
                                        "rule_id": "BIZ001",
                                        "category": "business_logic",
                                        "message": (
                                            "Business Logic Flaw: Sticker Price Refund Exploit (Threshold Abuse / "
                                            "Missing Proportional Discount Attribution). Refunding item sticker price "
                                            "when order-level discounts exist allows customers to buy to discount and return to profit."
                                        ),
                                        "recommendation": (
                                            "Do not refund the item's original sticker price when order-level discounts "
                                            "have been applied. Implement proportional discount attribution across order line-items "
                                            "(e.g., allocating effective_paid_price = price - item_discount) so refunds never exceed net realized revenue."
                                        ),
                                        "evidence": "return item.price",
                                    })

                    # BIZ002: Threshold discount without recalculation/clawback on partial return
                    if any(term in method.name.lower() for term in ["discount", "__init__", "calculate", "apply"]):
                        for stmt in ast.walk(method):
                            if isinstance(stmt, ast.If) and isinstance(stmt.test, ast.Compare):
                                comp = stmt.test
                                left_name = ""
                                if isinstance(comp.left, ast.Attribute):
                                    left_name = comp.left.attr
                                elif isinstance(comp.left, ast.Name):
                                    left_name = comp.left.id

                                if "subtotal" in left_name.lower() or "total" in left_name.lower():
                                    has_clawback = any(tok in class_lower for tok in [
                                        "clawback", "recalculate", "adjust_discount", "threshold_recheck", "remaining"
                                    ])
                                    if not has_clawback and "refund" in class_lower and not has_class_proportional:
                                        issues.append({
                                            "line": getattr(stmt, "lineno", method.lineno),
                                            "severity": "major",
                                            "rule_id": "BIZ002",
                                            "category": "business_logic",
                                            "message": (
                                                "Business Logic Flaw: Threshold Padding / Missing Promotion Recalculation on Partial Return. "
                                                "Cart threshold qualifies for tier discount but partial returns do not recalculate eligibility."
                                            ),
                                            "recommendation": (
                                                "Recalculate order threshold eligibility upon partial return or cancellation. "
                                                "If remaining items drop below the qualifying threshold, claw back or adjust the promotion."
                                            ),
                                            "evidence": f"if {left_name} >= threshold",
                                        })

                    # BIZ003: Unconstrained additive discount stacking without margin floor / COGS check
                    if any(term in method.name.lower() for term in ["discount", "__init__", "apply"]):
                        has_pct_discount = bool("0." in class_lower or "percent" in class_lower)
                        has_flat_coupon = bool("promo_code" in class_lower or "coupon" in class_lower)
                        has_floor_or_cap = any(tok in class_lower for tok in ["min(", "max(", "floor", "cogs", "cost", "margin"])
                        if has_pct_discount and has_flat_coupon and not has_floor_or_cap:
                            issues.append({
                                "line": method.lineno,
                                "severity": "major",
                                "rule_id": "BIZ003",
                                "category": "business_logic",
                                "message": (
                                    "Business Logic Flaw: Unconstrained Additive Discount Stacking without Margin Floor. "
                                    "Percentage discount and flat coupons stack additively without minimum floor or COGS checks."
                                ),
                                "recommendation": (
                                    "Define strict evaluation ordering (apply percentage discount sequentially, or enforce mutual exclusion) "
                                    "and enforce a post-discount basket floor so items cannot be sold below cost."
                                ),
                                "evidence": "additive discount stacking without min/floor",
                            })

    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            if any(term in node.name.lower() for term in ["refund", "return_item", "process_refund"]):
                if has_global_discount and not has_global_proportional:
                    for sub in ast.walk(node):
                        if isinstance(sub, ast.Return) and sub.value:
                            is_price_attr = isinstance(sub.value, ast.Attribute) and sub.value.attr == "price"
                            is_raw_price = isinstance(sub.value, ast.Name) and sub.value.id == "price"
                            if is_price_attr or is_raw_price:
                                issues.append({
                                    "line": getattr(sub, "lineno", node.lineno),
                                    "severity": "critical",
                                    "rule_id": "BIZ001",
                                    "category": "business_logic",
                                    "message": (
                                        "Business Logic Flaw: Sticker Price Refund Exploit (Threshold Abuse / "
                                        "Missing Proportional Discount Attribution). Standalone refund handler returns sticker price."
                                    ),
                                    "recommendation": (
                                        "Implement proportional discount attribution across order line items "
                                        "so that refunded amount reflects net realized revenue instead of sticker price."
                                    ),
                                    "evidence": "return item.price",
                                })

    return issues


def _lexical_fallback_issues(source: str) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for line_no, line in enumerate(source.splitlines(), start=1):
        match = _SENSITIVE_ASSIGNMENT_RE.match(line)
        if not match:
            continue

        identifier = match.group(1)
        if not _looks_sensitive_identifier(identifier):
            continue

        issues.append({
            "line": line_no,
            "severity": "critical",
            "rule_id": "SEC002",
            "category": "security",
            "message": "Sensitive value assigned in code.",
            "recommendation": "Load secrets from environment variables or a secret manager instead of hardcoding them.",
            "evidence": identifier,
        })
    return issues


def _extract_assignment_target_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _call_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""


def _normalize_identifier(identifier: str) -> str:
    return re.sub(r"[^a-z0-9]", "", identifier.lower())


def _looks_sensitive_identifier(identifier: str) -> bool:
    normalized = _normalize_identifier(identifier)
    return any(token in normalized for token in _SENSITIVE_NAME_TOKENS)


def _is_hardcoded_literal(node: ast.AST | None) -> bool:
    if isinstance(node, ast.Constant):
        return isinstance(node.value, (str, bytes, int, float))
    if isinstance(node, ast.JoinedStr):
        return True
    return False


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Attribute):
        parent = _call_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    if isinstance(node, ast.Name):
        return node.id
    return ""


def run_ruff_scan(file_path: str | os.PathLike[str]) -> list[dict[str, Any]]:
    path = str(file_path)
    if not os.path.exists(path):
        return []

    result: list[dict[str, Any]] = []
    try:
        completed = subprocess.run(
            ["ruff", "check", "--output-format=json", path],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode in (0, 1):
            try:
                payload = json.loads(completed.stdout or "[]")
                for item in payload:
                    result.append({
                        "line": int(item.get("location", {}).get("row", 1)),
                        "severity": _normalize_severity(item.get("severity")),
                        "rule_id": item.get("code", "RUF"),
                        "category": "lint",
                        "message": item.get("message", "Lint issue"),
                        "recommendation": "Fix the issue reported by Ruff to keep the codebase consistent and secure.",
                        "evidence": item.get("filename", path),
                    })
            except json.JSONDecodeError:
                pass
    except FileNotFoundError:
        pass

    return [_with_severity_policy(finding) for finding in result]


def scan_python_source(source: str) -> list[dict[str, Any]]:
    return [_with_severity_policy(finding) for finding in _python_ast_issues(source)]


def _normalize_severity(value: object) -> str:
    severity = str(value or "info").lower()
    aliases = {"error": "critical", "high": "critical", "warning": "major", "medium": "major", "low": "minor"}
    return aliases.get(severity, severity if severity in _SEVERITY_POLICY else "info")


def _with_severity_policy(finding: dict[str, Any]) -> dict[str, Any]:
    severity = _normalize_severity(finding.get("severity"))
    policy = _SEVERITY_POLICY[severity]
    return {
        **finding,
        "severity": severity,
        "severity_label": policy["label"],
        "pr_blocking": policy["pr_blocking"],
        "comment_prefix": f"### **[{policy['label']}] ({severity.title()})**",
    }


def discover_python_files(repo_path: str | Path) -> list[str]:
    root = Path(repo_path)
    if not root.exists():
        return []
    return [str(path) for path in root.rglob("*.py") if path.is_file()]


def gather_repo_findings(repo_path: str | Path) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for file_path in discover_python_files(repo_path):
        try:
            source = Path(file_path).read_text(encoding="utf-8")
        except OSError:
            continue
        findings.extend(scan_python_source(source))
        findings.extend(run_ruff_scan(file_path))
    return findings
