import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))

from google.adk.evaluation.local_eval_sets_manager import load_eval_set_from_file

evalset_path = root / "agents" / "code_review_agent" / "eval_set_1.evalset.json"
eval_set = load_eval_set_from_file(str(evalset_path), "eval_set_1")

print(f"Eval set loaded successfully!")
print(f"ID: {eval_set.eval_set_id}")
print(f"Name: {eval_set.name}")
print(f"Number of test cases: {len(eval_set.eval_cases)}")
for case in eval_set.eval_cases:
    print(f"  - Case ID: {case.eval_id} (Invocations: {len(case.conversation) if case.conversation else 0})")
