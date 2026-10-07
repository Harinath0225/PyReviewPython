import logging

from .agent import root_agent

try:
    from .metrics_registry import register_custom_metrics

    register_custom_metrics()
except Exception:  # Metric registration must never stop the agent from loading.
    logging.getLogger("adk_eval_suite").exception("Could not register custom ADK metrics")
