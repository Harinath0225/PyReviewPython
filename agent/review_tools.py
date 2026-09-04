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
