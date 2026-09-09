#!/usr/bin/env python3
"""Test script to verify SQL injection and unused import detection."""

import os
from agent.review_tools import scan_python_source

# Your test code
test_code = '''import os


def get_user(user_id):
    # SQL Injection vulnerability
    query = f"SELECT * FROM users WHERE id = '{user_id}'"

    print(query)

    return query


def calculate_average(numbers):
    total = 0

    for number in numbers:
        total += number

    return total / len(numbers)


def unused_function():
    unused_variable = "test"
    return True
'''

print("=" * 80)
print("Testing AST Scanner for SQL Injection Detection")
print("=" * 80)
findings = scan_python_source(test_code)

print(f"\nTotal findings: {len(findings)}\n")
for finding in findings:
    print(f"[{finding['severity'].upper()}] {finding['rule_id']}: {finding['message']}")
    print(f"  Line: {finding['line']}")
    print(f"  Category: {finding['category']}")
    print(f"  Recommendation: {finding['recommendation']}")
    if 'replacement' in finding:
        print(f"  Replacement: {finding['replacement']}")
    print()

# Check for SQL injection detection
sql_findings = [f for f in findings if f['rule_id'] == 'SEC003']
if sql_findings:
    print("✅ SQL Injection DETECTED (SEC003)")
    for finding in sql_findings:
        print(f"   Line {finding['line']}: {finding['message']}")
else:
    print("❌ SQL Injection NOT DETECTED")

print("\n" + "=" * 80)
print("Testing Ruff for Unused Import Detection")
print("=" * 80)

# Save to temp file and run Ruff
import tempfile
from pathlib import Path
from agent.review_tools import run_ruff_scan

tmp_path = None
try:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as tmp_file:
        tmp_file.write(test_code)
        tmp_path = tmp_file.name
    
    print(f"\nTemp file created: {tmp_path}")
    ruff_findings = run_ruff_scan(tmp_path)
    
    print(f"Ruff findings: {len(ruff_findings)}\n")
    for finding in ruff_findings:
        print(f"[{finding['severity'].upper()}] {finding['rule_id']}: {finding['message']}")
        print(f"  Line: {finding['line']}")
        print(f"  Category: {finding['category']}")
        print()
    
    # Check for unused import
    unused_import_findings = [f for f in ruff_findings if 'unused' in f['message'].lower() or 'import' in f['message'].lower()]
    if unused_import_findings:
        print("✅ Unused Import DETECTED")
        for finding in unused_import_findings:
            print(f"   Line {finding['line']}: {finding['message']}")
    else:
        print("❌ Unused Import NOT DETECTED")
        print("Ruff output:", ruff_findings)
        
finally:
    if tmp_path and Path(tmp_path).exists():
        Path(tmp_path).unlink()
        print(f"\nTemp file cleaned up")
