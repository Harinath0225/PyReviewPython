"""Probe: how well does the judge track the human labels, and does the calibration loop converge?"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
mode = sys.argv[1] if len(sys.argv) > 1 else "heuristic"
os.environ["LLM_JUDGE_MODE"] = mode

from agent.judge_calibration import load_golden_set, run_calibration  # noqa: E402
from agent.llm_judge import LLMJudge  # noqa: E402

judge = LLMJudge(mode=mode)
print(f"requested={judge.requested_mode} effective={judge.effective_mode} model={judge.model}")
golden = load_golden_set()
result = run_calibration(judge)

print("\nexample            human  raw   calibrated  split")
for point, example in zip(result["points"], golden["examples"]):
    print(f"  {point['id']:22s} {example['human_score']}   {point['raw']:.2f}   {point['calibrated']:.2f}   {point['split']}")

print("\nrounds:")
for r in result["rounds"]:
    print(
        f"  r{r['round']} slope={r['slope']:.3f} icpt={r['intercept']:.3f} thr={r['threshold']} "
        f"train_mae={r['train']['mae']} val_mae={r['validation']['mae']} "
        f"val_kappa={r['validation']['kappa']} val_pearson={r['validation']['pearson']}"
    )
print("stop:", result["stop_reason"], "| converged:", result["converged"])
print("improvement:", result["improvement"], "| trust:", result["trust_score"])
print("fallbacks:", result["judge"]["fallback_reasons"])
