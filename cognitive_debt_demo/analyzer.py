from __future__ import annotations

import ast
import re
import textwrap
from typing import Any

from cognitive_debt_demo.schemas import TelemetryResult

CONTROL_FLOW_NODES = (
    ast.If,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.Try,
    ast.ExceptHandler,
    ast.With,
    ast.AsyncWith,
    ast.BoolOp,
)


class ParsedDiffFile:
    def __init__(self, filename: str) -> None:
        self.filename = filename
        self.added_lines: list[str] = []
        self.is_test: bool = (
            "test" in filename.lower()
            or filename.lower().startswith("test_")
            or filename.lower().endswith(("_test.py", "_spec.py"))
        )

    def add_line(self, line: str) -> None:
        self.added_lines.append(line)


def parse_diff_files(diff_text: str) -> list[ParsedDiffFile]:
    """Parses unified diff text or raw Python code into files with added lines."""
    files: list[ParsedDiffFile] = []
    current_file: ParsedDiffFile | None = None

    lines = diff_text.splitlines()
    is_unified_diff = any(
        line.startswith(("diff --git", "--- ", "+++ ", "@@ "))
        for line in lines[:20]
    )

    if not is_unified_diff:
        # Treat the raw text as a single file
        file_name = "test_sample.py" if "def test_" in diff_text or "mock" in diff_text else "module.py"
        f = ParsedDiffFile(file_name)
        f.added_lines = lines
        return [f]

    for line in lines:
        cleaned = line[1:] if line.startswith("+") and (line.startswith("+diff --git") or line.startswith("+--- ") or line.startswith("++++ ")) else line

        if cleaned.startswith("diff --git"):
            parts = cleaned.split()
            fname = "unknown.py"
            if len(parts) >= 4:
                fname = parts[3].lstrip("b/")
            current_file = ParsedDiffFile(fname)
            files.append(current_file)
            continue

        if cleaned.startswith("+++ "):
            raw_path = cleaned[4:].strip()
            fname = raw_path[2:] if raw_path.startswith("b/") else raw_path
            if current_file is None or current_file.filename == "unknown.py":
                current_file = ParsedDiffFile(fname)
                files.append(current_file)
            else:
                current_file.filename = fname
                current_file.is_test = (
                    "test" in fname.lower()
                    or fname.lower().startswith("test_")
                    or fname.lower().endswith(("_test.py", "_spec.py"))
                )
            continue

        if cleaned.startswith("--- "):
            continue

        if line.startswith("@@"):
            if current_file is None:
                current_file = ParsedDiffFile("unknown.py")
                files.append(current_file)
            continue

        if line.startswith("+") and not line.startswith("+++"):
            if current_file is None:
                current_file = ParsedDiffFile("unknown.py")
                files.append(current_file)
            current_file.add_line(line[1:])

    return files if files else [ParsedDiffFile("module.py")]


def is_logic_line(line: str) -> bool:
    """Returns True if the line contains executable Python code (not comments, blank, imports)."""
    stripped = line.strip()
    if not stripped:
        return False
    if stripped.startswith("#"):
        return False
    if stripped.startswith(('"""', "'''")):
        return False
    if stripped.startswith(("import ", "from ", "import\t", "from\t")):
        return False
    return True


def try_parse_ast(code: str) -> ast.AST | None:
    """Attempts to parse Python code into an AST using multiple recovery strategies."""
    if not code.strip():
        return None

    # Strategy 1: Direct parse
    try:
        return ast.parse(code)
    except SyntaxError:
        pass

    # Strategy 2: Dedent
    dedented = textwrap.dedent(code)
    try:
        return ast.parse(dedented)
    except SyntaxError:
        pass

    # Strategy 3: Wrap in synthetic function (handles statements like return/yield outside func)
    indented = textwrap.indent(dedented, "    ")
    wrapped = f"def _synthetic_scope_wrapper():\n{indented}\n"
    try:
        return ast.parse(wrapped)
    except SyntaxError:
        pass

    # Strategy 4: Line-by-line statement recovery
    valid_nodes: list[ast.stmt] = []
    buffer: list[str] = []
    for line in dedented.splitlines():
        buffer.append(line)
        candidate = "\n".join(buffer)
        try:
            tree = ast.parse(candidate)
            valid_nodes.extend(tree.body)
            buffer = []
        except SyntaxError:
            # If line ends with colon, try appending pass
            if candidate.rstrip().endswith(":"):
                try:
                    tree = ast.parse(candidate + "\n    pass")
                    valid_nodes.extend(tree.body)
                    buffer = []
                except SyntaxError:
                    pass

    if valid_nodes:
        module = ast.Module(body=valid_nodes, type_ignores=[])
        return module

    return None


def calculate_ast_nesting_score(node: ast.AST, control_depth: int = 0) -> int:
    """Recursively walks AST: +1 for each control-flow node; +2 penalty for each level > 2."""
    score = 0
    is_control = isinstance(node, CONTROL_FLOW_NODES)
    new_depth = control_depth + (1 if is_control else 0)

    if is_control:
        penalty = 2 * (new_depth - 2) if new_depth > 2 else 0
        score += 1 + penalty

    for child in ast.iter_child_nodes(node):
        score += calculate_ast_nesting_score(child, new_depth)

    return score


def calculate_test_tautology_ratio(tree: ast.AST) -> tuple[int, int]:
    """Counts mock assertion calls vs standard assert statements in test AST.

    Returns:
        (mock_assert_count, standard_assert_count)
    """
    mock_asserts = 0
    standard_asserts = 0

    for node in ast.walk(tree):
        if isinstance(node, ast.Assert):
            standard_asserts += 1
            continue

        if isinstance(node, ast.Call):
            func_name = ""
            caller_name = ""

            if isinstance(node.func, ast.Attribute):
                func_name = node.func.attr
                if isinstance(node.func.value, ast.Name):
                    caller_name = node.func.value.id
                elif isinstance(node.func.value, ast.Attribute):
                    caller_name = node.func.value.attr
            elif isinstance(node.func, ast.Name):
                func_name = node.func.id

            is_mock_call = (
                func_name.startswith("assert_called")
                or func_name in ("assert_not_called", "assert_any_call", "assert_has_calls")
                or "mock" in caller_name.lower()
                or "mock" in func_name.lower()
            )

            if is_mock_call:
                mock_asserts += 1
            elif func_name.startswith("assert") and not is_mock_call:
                # Standard unittest assertions like self.assertEqual, self.assertTrue, self.assertIn
                standard_asserts += 1

    return mock_asserts, standard_asserts


def analyze_pr_diff(diff_text: str, pr_body: str = "") -> TelemetryResult:
    """Calculates AST nesting complexity, undocumented logic burst, and test tautology ratio."""
    files = parse_diff_files(diff_text)

    # 1. Undocumented Logic Burst (net_new_logic_loc)
    net_new_logic_loc = 0
    for f in files:
        for line in f.added_lines:
            if is_logic_line(line):
                net_new_logic_loc += 1

    # 1.5x penalty multiplier if PR body has fewer than 30 words
    pr_words = len(pr_body.split()) if pr_body else 0
    if pr_words < 30:
        effective_loc = int(net_new_logic_loc * 1.5)
    else:
        effective_loc = net_new_logic_loc

    # 2. AST Nesting Complexity & Test Tautology
    total_nesting_score = 0
    total_mock_asserts = 0
    total_standard_asserts = 0

    for f in files:
        code = "\n".join(f.added_lines)
        tree = try_parse_ast(code)
        if tree is None:
            continue

        file_nesting = calculate_ast_nesting_score(tree, control_depth=0)
        total_nesting_score += file_nesting

        # Test tautology is evaluated on test files or files containing test functions
        has_tests = f.is_test or any(
            isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith("test_")
            for n in ast.walk(tree)
        )
        if has_tests:
            m_cnt, s_cnt = calculate_test_tautology_ratio(tree)
            total_mock_asserts += m_cnt
            total_standard_asserts += s_cnt

    total_asserts = total_mock_asserts + total_standard_asserts
    if total_asserts > 0:
        mock_tautology_ratio = round(total_mock_asserts / total_asserts, 4)
    else:
        mock_tautology_ratio = 0.0

    # 4. CDI Formula (0-100)
    c_pts = min(40, total_nesting_score * 2)
    l_pts = min(35, int((effective_loc / 300) * 35))
    t_pts = int(mock_tautology_ratio * 25)
    cdi_score = min(100, max(0, c_pts + l_pts + t_pts))
    gate_blocked = cdi_score >= 65

    return TelemetryResult(
        max_nesting_score=total_nesting_score,
        net_new_logic_loc=net_new_logic_loc,
        mock_tautology_ratio=mock_tautology_ratio,
        cdi_score=cdi_score,
        gate_blocked=gate_blocked,
    )
