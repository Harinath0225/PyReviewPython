"""Calibration loop for the LLM judge.

The judge scores a human-labelled golden set once. The loop then repeatedly fits a
linear correction (calibrated = slope * raw + intercept), moves the live parameters
part of the way towards that fit, and measures agreement with the human labels again,
until the error stops improving. Examples are split into a train and a held-out
validation set so the reported improvement is not just the loop memorising its labels.
"""

from __future__ import annotations

import json
import math
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from agent.llm_judge import DEFAULT_PASS_THRESHOLD, LLMJudge

GOLDEN_SET_PATH = Path(__file__).resolve().parent.parent / "data" / "judge_calibration_set.json"

_AGREEMENT_TOLERANCE = 0.125  # half a point on the 1-5 human scale
_BIN_EDGES = (0.0, 0.2, 0.4, 0.6, 0.8, 1.0001)


def load_golden_set(path: Path | None = None) -> dict[str, Any]:
    return json.loads((path or GOLDEN_SET_PATH).read_text(encoding="utf-8"))


def _normalize_human(score: float) -> float:
    return (float(score) - 1.0) / 4.0


def _clamp(value: float) -> float:
    return min(1.0, max(0.0, value))


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _pearson(a: list[float], b: list[float]) -> float | None:
    if len(a) < 2:
        return None
    mean_a, mean_b = _mean(a), _mean(b)
    covariance = sum((x - mean_a) * (y - mean_b) for x, y in zip(a, b))
    spread = math.sqrt(sum((x - mean_a) ** 2 for x in a) * sum((y - mean_b) ** 2 for y in b))
    return covariance / spread if spread > 1e-12 else None


def _ranks(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    position = 0
    while position < len(order):
        end = position
        while end + 1 < len(order) and values[order[end + 1]] == values[order[position]]:
            end += 1
        for index in order[position : end + 1]:
            ranks[index] = (position + end) / 2 + 1
        position = end + 1
    return ranks


def _cohen_kappa(judge_pass: list[bool], human_pass: list[bool]) -> float | None:
    total = len(judge_pass)
    if total == 0:
        return None
    observed = sum(1 for j, h in zip(judge_pass, human_pass) if j == h) / total
    judge_rate, human_rate = sum(judge_pass) / total, sum(human_pass) / total
    expected = judge_rate * human_rate + (1 - judge_rate) * (1 - human_rate)
    if expected >= 1.0 - 1e-12:
        return 1.0 if observed >= 1.0 - 1e-12 else 0.0
    return (observed - expected) / (1 - expected)


def agreement_metrics(
    predicted: list[float], human: list[float], threshold: float, human_pass_threshold: float
) -> dict[str, Any]:
    """How closely judge scores track human scores (all in [0, 1])."""
    if not predicted:
        return {"n": 0, "mae": None, "bias": None, "rmse": None, "pearson": None, "spearman": None,
                "agreement": None, "kappa": None}
    errors = [p - h for p, h in zip(predicted, human)]
    spearman = _pearson(_ranks(predicted), _ranks(human))
    kappa = _cohen_kappa(
        [p >= threshold for p in predicted], [h >= human_pass_threshold for h in human]
    )
    pearson = _pearson(predicted, human)

    def rounded(value: float | None) -> float | None:
        return None if value is None else round(value, 4)

    return {
        "n": len(predicted),
        "mae": round(_mean([abs(e) for e in errors]), 4),
        "bias": round(_mean(errors), 4),
        "rmse": round(math.sqrt(_mean([e * e for e in errors])), 4),
        "pearson": rounded(pearson),
        "spearman": rounded(spearman),
        "agreement": round(sum(1 for e in errors if abs(e) <= _AGREEMENT_TOLERANCE) / len(errors), 4),
        "kappa": rounded(kappa),
    }


def fit_linear(raw: list[float], human: list[float]) -> tuple[float, float]:
    """Least-squares (slope, intercept) mapping judge scores to human scores."""
    mean_raw, mean_human = _mean(raw), _mean(human)
    variance = sum((r - mean_raw) ** 2 for r in raw)
    if variance < 1e-9:
        # The judge gives every answer the same score, so only a level shift is learnable.
        return 1.0, mean_human - mean_raw
    slope = sum((r - mean_raw) * (h - mean_human) for r, h in zip(raw, human)) / variance
    return slope, mean_human - slope * mean_raw


def tune_threshold(calibrated: list[float], human: list[float], human_pass_threshold: float) -> float:
    """Pass threshold that best agrees with the human pass/fail call (ties keep the closest to the default)."""
    human_pass = [h >= human_pass_threshold for h in human]
    best, best_kappa = DEFAULT_PASS_THRESHOLD, -2.0
    for step in range(12, 37):  # 0.30 .. 0.90
        threshold = step * 0.025
        kappa = _cohen_kappa([c >= threshold for c in calibrated], human_pass)
        kappa = -1.0 if kappa is None else kappa
        if kappa > best_kappa + 1e-9 or (
            abs(kappa - best_kappa) <= 1e-9 and abs(threshold - DEFAULT_PASS_THRESHOLD) < abs(best - DEFAULT_PASS_THRESHOLD)
        ):
            best, best_kappa = threshold, kappa
    return round(best, 3)


def _split(examples: list[dict[str, Any]]) -> tuple[list[int], list[int]]:
    """Every third example by human score goes to validation, so both splits span the score range."""
    order = sorted(range(len(examples)), key=lambda i: (examples[i]["human_score"], examples[i]["id"]))
    validation = {index for position, index in enumerate(order) if position % 3 == 1}
    train = [i for i in range(len(examples)) if i not in validation]
    return train, sorted(validation)


def _reliability_bins(calibrated: list[float], human: list[float]) -> list[dict[str, Any]]:
    bins = []
    for low, high in zip(_BIN_EDGES, _BIN_EDGES[1:]):
        members = [(c, h) for c, h in zip(calibrated, human) if low <= c < high]
        bins.append({
            "range": f"{low:.1f}-{min(high, 1.0):.1f}",
            "count": len(members),
            "mean_judge": round(_mean([c for c, _ in members]), 4) if members else None,
            "mean_human": round(_mean([h for _, h in members]), 4) if members else None,
        })
    return bins


def _judge_examples(judge: LLMJudge, examples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def run(example: dict[str, Any]) -> dict[str, Any]:
        return judge.judge(
            prompt=example["task"],
            response=example["response"],
            reference=example.get("reference"),
            code=example.get("code"),
            apply_calibration=False,
        )

    with ThreadPoolExecutor(max_workers=4) as pool:
        return list(pool.map(run, examples))


def run_calibration(
    judge: LLMJudge,
    *,
    max_rounds: int = 5,
    learning_rate: float = 0.6,
    tolerance: float = 0.002,
    golden_set: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Runs the calibration loop and returns the full trace; persisting it is the caller's job."""
    golden = golden_set or load_golden_set()
    examples: list[dict[str, Any]] = golden["examples"]
    human_pass_threshold = _normalize_human(golden.get("pass_human_score", 4))
    human = [_normalize_human(e["human_score"]) for e in examples]

    verdicts = _judge_examples(judge, examples)
    raw = [v["raw_score"] for v in verdicts]
    train_idx, val_idx = _split(examples)
    train_raw, train_human = [raw[i] for i in train_idx], [human[i] for i in train_idx]
    val_raw, val_human = [raw[i] for i in val_idx], [human[i] for i in val_idx]

    slope, intercept, threshold = 1.0, 0.0, DEFAULT_PASS_THRESHOLD

    def calibrated(values: list[float], a: float, b: float) -> list[float]:
        return [_clamp(a * v + b) for v in values]

    def snapshot(round_number: int, a: float, b: float, cut: float) -> dict[str, Any]:
        return {
            "round": round_number,
            "slope": round(a, 4),
            "intercept": round(b, 4),
            "threshold": round(cut, 3),
            "train": agreement_metrics(calibrated(train_raw, a, b), train_human, cut, human_pass_threshold),
            "validation": agreement_metrics(calibrated(val_raw, a, b), val_human, cut, human_pass_threshold),
        }

    rounds = [snapshot(0, slope, intercept, threshold)]
    history = [(slope, intercept)]
    stop_reason = f"Reached the {max_rounds}-round limit."
    converged = False
    for round_number in range(1, max_rounds + 1):
        target_slope, target_intercept = fit_linear(train_raw, train_human)
        slope += learning_rate * (target_slope - slope)
        intercept += learning_rate * (target_intercept - intercept)
        history.append((slope, intercept))
        rounds.append(snapshot(round_number, slope, intercept, threshold))
        gain = rounds[-2]["train"]["mae"] - rounds[-1]["train"]["mae"]
        if gain < tolerance:
            converged = True
            stop_reason = (
                f"Train MAE got worse in round {round_number}; kept the best earlier round."
                if gain < 0
                else f"Train MAE improved by less than {tolerance} in round {round_number}."
            )
            break

    # Keep the round with the lowest train error (earliest wins ties), not simply the last one.
    best = min(range(len(rounds)), key=lambda i: (rounds[i]["train"]["mae"], i))
    slope, intercept = history[best]
    threshold = tune_threshold(calibrated(train_raw, slope, intercept), train_human, human_pass_threshold)
    final = snapshot(best, slope, intercept, threshold)
    final["selected"] = True
    rounds[best] = final

    all_calibrated = calibrated(raw, slope, intercept)
    train_set = set(train_idx)
    points = [
        {
            "id": example["id"],
            "scenario": example["scenario"],
            "split": "train" if i in train_set else "validation",
            "human": round(human[i], 4),
            "raw": round(raw[i], 4),
            "calibrated": round(all_calibrated[i], 4),
            "human_pass": human[i] >= human_pass_threshold,
            "judge_pass": all_calibrated[i] >= threshold,
        }
        for i, example in enumerate(examples)
    ]

    before, after = rounds[0]["validation"], final["validation"]
    return {
        "judge": {
            "key": judge.key,
            "mode": judge.effective_mode,
            "requested_mode": judge.requested_mode,
            "model": judge.model if judge.effective_mode == "llm" else "heuristic-rubric",
            "fallback_reasons": sorted({v["fallback_reason"] for v in verdicts if v.get("fallback_reason")}),
        },
        "example_count": len(examples),
        "train_count": len(train_idx),
        "validation_count": len(val_idx),
        "human_pass_threshold": human_pass_threshold,
        "learning_rate": learning_rate,
        "rounds": rounds,
        "converged": converged,
        "stop_reason": stop_reason,
        "params": {"slope": final["slope"], "intercept": final["intercept"], "threshold": final["threshold"]},
        "before": before,
        "after": after,
        "improvement": {
            "validation_mae": round(before["mae"] - after["mae"], 4),
            "validation_agreement": round(after["agreement"] - before["agreement"], 4),
        },
        "trust_score": round(100 * (1 - after["mae"]), 1),
        "points": points,
        "reliability_bins": _reliability_bins(all_calibrated, human),
    }
