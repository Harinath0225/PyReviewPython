"""Launcher script for Google ADK WebUI with custom evaluation metrics suite.

Runs on port 8085 (default) to avoid conflict with backend FastAPI on port 8000.
"""

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
AGENTS_DIR = REPO_ROOT / "agents"

PORT = os.getenv("ADK_WEB_PORT", "8085")
HOST = os.getenv("ADK_WEB_HOST", "127.0.0.1")


def main():
    print("=" * 70)
    print("🚀 Google ADK WebUI Testing & Evaluation Suite")
    print("=" * 70)
    print(f"Agents Directory: {AGENTS_DIR}")
    print(f"Server URL:       http://{HOST}:{PORT}")
    print(f"Eval Set:         eval_set_1.evalset.json")
    print(f"Config:           test_config.json")
    print("Metrics Tracked:")
    print("  - Tokens Consumed (prompt, completion, tool trajectory)")
    print("  - Latency (execution time vs SLA)")
    print("  - Tool Call Trajectory (AST security analysis, BRD mapping)")
    print("  - METEOR Score (precision/recall harmonic mean + chunk penalty)")
    print("  - BLEU Score (n-gram precision + brevity penalty)")
    print("  - LLM-as-a-Judge (defensive remediation & business compliance)")
    print("=" * 70)
    print(f"Opening Web UI at http://{HOST}:{PORT} ...\n")

    cmd = [
        sys.executable,
        "-m",
        "google.adk.cli",
        "web",
        "--host",
        HOST,
        "--port",
        str(PORT),
        str(AGENTS_DIR),
    ]

    try:
        subprocess.run(cmd, cwd=str(REPO_ROOT), check=True)
    except KeyboardInterrupt:
        print("\n👋 ADK WebUI server stopped.")


if __name__ == "__main__":
    main()
