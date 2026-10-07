"""Launcher script for Google ADK WebUI with custom evaluation metrics suite.

Runs on port 8085 (default) to avoid conflict with backend FastAPI on port 8000.

The server runs in this process (not a subprocess) because the Web UI only lists metrics registered
in its own process, and the custom metrics are registered here before it starts.
"""

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
AGENTS_DIR = REPO_ROOT / "agents"

PORT = os.getenv("ADK_WEB_PORT", "8085")
HOST = os.getenv("ADK_WEB_HOST", "127.0.0.1")


def main():
    os.chdir(REPO_ROOT)
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))

    from agents.code_review_agent.metrics_registry import register_custom_metrics

    registered = register_custom_metrics()

    print("=" * 70)
    print("Google ADK WebUI Testing & Evaluation Suite")
    print("=" * 70)
    print(f"Agents Directory: {AGENTS_DIR}")
    print(f"Server URL:       http://{HOST}:{PORT}")
    print(f"Eval Set:         eval_set_1.evalset.json")
    print(f"Config:           test_config.json")
    print(f"Custom metrics registered for the Eval tab: {', '.join(registered)}")
    print("Metrics Tracked:")
    print("  - Tokens Consumed (prompt, completion, tool trajectory)")
    print("  - Latency (execution time vs SLA)")
    print("  - Tool Call Trajectory (AST security analysis, BRD mapping)")
    print("  - BLEU / METEOR / ROUGE-L (reference overlap against golden remediation)")
    print("  - LLM-as-a-Judge (rubric score, calibrated against human labels)")
    print("=" * 70)
    print(f"Opening Web UI at http://{HOST}:{PORT} ...\n")

    from google.adk.cli.cli_tools_click import main as adk_main

    try:
        adk_main(args=["web", "--host", HOST, "--port", str(PORT), "--no-reload", str(AGENTS_DIR)], prog_name="adk")
    except KeyboardInterrupt:
        print("\nADK WebUI server stopped.")


if __name__ == "__main__":
    main()
