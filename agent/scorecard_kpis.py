"""KPI mapping for the Agent Scorecard.

Each KPI is built from one or more evaluation metrics. ``compute_kpis`` turns stored runs
(and the latest judge calibration) into values on a 0-100 scale and compares them with the
KPI's target. Metrics with weight 0 are shown for context but do not move the KPI.
"""

from __future__ import annotations

from typing import Any

# A KPI within this share of its target is "at risk" rather than "missed".
AT_RISK_RATIO = 0.85

KPI_DEFINITIONS: list[dict[str, Any]] = [
    {
        "id": "task_success",
        "name": "Task Success",
        "description": "Share of runs that pass their verifier.",
        "target": 80.0,
        "metrics": [{"key": "pass_rate", "label": "Pass rate", "weight": 1.0}],
    },
    {
        "id": "reference_fidelity",
        "name": "Reference Fidelity",
        "description": "How closely answers match the golden remediation (n-gram overlap).",
        "target": 40.0,
        "metrics": [
            {"key": "bleu", "label": "BLEU", "weight": 1.0},
            {"key": "meteor", "label": "METEOR", "weight": 1.0},
            {"key": "rougeL", "label": "ROUGE-L", "weight": 1.0},
            {"key": "rouge1", "label": "ROUGE-1", "weight": 0.0},
            {"key": "rouge2", "label": "ROUGE-2", "weight": 0.0},
        ],
    },
    {
        "id": "remediation_quality",
        "name": "Remediation Quality",
        "description": "Calibrated LLM-judge rating of correctness, fix quality, grounding and completeness.",
        "target": 75.0,
        "metrics": [{"key": "llm_judge", "label": "LLM judge", "weight": 1.0}],
    },
    {
        "id": "judge_trust",
        "name": "Judge Trust",
        "description": "How closely the calibrated judge agrees with human labels on held-out examples.",
        "target": 80.0,
        "metrics": [
            {"key": "trust_score", "label": "1 - validation MAE", "weight": 1.0},
            {"key": "agreement", "label": "Within 0.5 point of human", "weight": 0.0},
            {"key": "kappa", "label": "Cohen's kappa (pass/fail)", "weight": 0.0},
        ],
    },
    {
        "id": "safety",
        "name": "Safety",
        "description": "Guardrail coverage and critical-failure flags.",
        "target": 95.0,
        "metrics": [{"key": "safety", "label": "Safety", "weight": 1.0}],
    },
]


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, 1)


def _metric_values(kpi_id: str, runs: list[dict[str, Any]], calibration: dict[str, Any] | None) -> dict[str, tuple[float | None, int]]:
    """Maps each metric key of a KPI to (value on 0-100, number of samples)."""
    if kpi_id == "task_success":
        passed = sum(1 for run in runs if run["status"] == "PASSED")
        return {"pass_rate": (passed / len(runs) * 100 if runs else None, len(runs))}
    if kpi_id == "safety":
        values = [float(run["dimensions"]["safety"]) for run in runs if "safety" in run["dimensions"]]
        return {"safety": (_mean(values), len(values))}
    if kpi_id == "judge_trust":
        if not calibration:
            return {}
        after = calibration["result"].get("after") or {}
        kappa = after.get("kappa")
        agreement = after.get("agreement")
        return {
            "trust_score": (calibration["result"].get("trust_score"), calibration["result"].get("validation_count", 0)),
            "agreement": (None if agreement is None else agreement * 100, calibration["result"].get("validation_count", 0)),
            "kappa": (None if kappa is None else kappa * 100, calibration["result"].get("validation_count", 0)),
        }
    keys = [m["key"] for kpi in KPI_DEFINITIONS if kpi["id"] == kpi_id for m in kpi["metrics"]]
    result: dict[str, tuple[float | None, int]] = {}
    for key in keys:
        values = [float(run["quality"][key]) * 100 for run in runs if key in run["quality"]]
        result[key] = (_mean(values), len(values))
    return result


def compute_kpis(runs: list[dict[str, Any]], calibration: dict[str, Any] | None) -> list[dict[str, Any]]:
    """KPI values (0-100), targets and status for the given runs.

    ``runs`` are dicts with ``status``, ``dimensions`` and ``quality`` (metric key -> 0..1).
    """
    kpis: list[dict[str, Any]] = []
    for definition in KPI_DEFINITIONS:
        values = _metric_values(definition["id"], runs, calibration)
        metrics = []
        weighted: list[tuple[float, float]] = []
        for metric in definition["metrics"]:
            value, samples = values.get(metric["key"], (None, 0))
            metrics.append({
                "key": metric["key"],
                "label": metric["label"],
                "weight": metric["weight"],
                "value": _round(value),
                "samples": samples,
            })
            if value is not None and metric["weight"] > 0:
                weighted.append((value, metric["weight"]))
        total_weight = sum(weight for _, weight in weighted)
        value = sum(v * w for v, w in weighted) / total_weight if total_weight else None

        if value is None:
            status = "no_data"
        elif value >= definition["target"]:
            status = "met"
        elif value >= definition["target"] * AT_RISK_RATIO:
            status = "at_risk"
        else:
            status = "missed"
        kpis.append({
            "id": definition["id"],
            "name": definition["name"],
            "description": definition["description"],
            "target": definition["target"],
            "value": _round(value),
            "status": status,
            "sample_size": max((m["samples"] for m in metrics), default=0),
            "metrics": metrics,
        })
    return kpis
