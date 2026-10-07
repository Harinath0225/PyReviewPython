"""Registers this agent's custom metrics (``test_config.json``) with ADK.

The ADK Web UI lists and runs only the metrics found in ADK's process-wide registry, and its
server never reads ``custom_metrics`` from ``test_config.json`` (only ``adk eval`` does). Calling
``register_custom_metrics`` before the server starts is what makes BLEU, METEOR, ROUGE and the
LLM judge selectable in the Web UI's eval metric picker.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger("adk_eval_suite")

CONFIG_PATH = Path(__file__).resolve().parent / "test_config.json"


def register_custom_metrics(config_path: Path = CONFIG_PATH) -> list[str]:
    """Registers every custom metric in the config; safe to call more than once."""
    from google.adk.evaluation.eval_config import EvalConfig
    from google.adk.evaluation.metric_evaluator_registry import register_custom_metrics_from_config

    config = EvalConfig.model_validate(json.loads(config_path.read_text(encoding="utf-8")))
    register_custom_metrics_from_config(config)
    return sorted(config.custom_metrics or {})
