import os
import sys
import tempfile
from pathlib import Path

repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

# Tests must be deterministic and free: never call a real LLM judge or touch real evaluation history.
os.environ["LLM_JUDGE_MODE"] = "heuristic"
os.environ["EVAL_HISTORY_DB"] = str(Path(tempfile.mkdtemp(prefix="pyreview-tests-")) / "evaluation_history.sqlite3")
