"""Dynamic noise injection for robustness evaluation (Agent Scorecard).

Simulates adverse runtime conditions inside the evaluation loop to measure
agent Robustness:

1. Latency injection  - artificial delay applied to the evaluation run.
2. Fault injection    - simulated upstream 500 errors / tool failures.
3. Prompt mutation    - slight rephrasing of the initial prompt to test
   prompt tolerance.

The injector is deterministic when a ``seed`` is provided so that benchmark
runs are reproducible.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Any

# Hard cap on real sleep so evaluations stay fast; anything above is only
# recorded as *simulated* latency in the metrics.
_MAX_REAL_SLEEP_MS = 250.0

_PROMPT_PREFIXES = [
    "Please ",
    "Could you ",
    "I need you to ",
    "Kindly ",
]
_PROMPT_SUFFIXES = [
    " Thanks.",
    " This is urgent.",
    " Be thorough.",
    "",
]


@dataclass(slots=True)
class NoiseOutcome:
    """Result of applying a noise profile to a single evaluation run."""

    profile: dict[str, Any]
    mutated_prompt: str
    injected_latency_ms: float
    simulated_faults: list[str] = field(default_factory=list)
    prompt_mutated: bool = False


class NoiseInjector:
    """Applies a configurable noise profile to an evaluation run."""

    def __init__(self, profile: dict[str, Any] | None = None) -> None:
        profile = dict(profile or {})
        self.profile = profile
        seed = profile.get("seed")
        self._rng = random.Random(seed) if seed is not None else random.Random()
        self.latency_ms = float(profile.get("latency_ms", 0) or 0)
        self.latency_jitter_ms = float(profile.get("latency_jitter_ms", 0) or 0)
        self.fault_rate = float(profile.get("fault_rate", 0.0) or 0.0)
        self.mutate_prompt = bool(profile.get("mutate_prompt", False))
        self.fault_kinds: list[str] = list(
            profile.get("fault_kinds") or ["http_500", "tool_timeout", "partial_response"]
        )

    @property
    def enabled(self) -> bool:
        return bool(
            self.latency_ms
            or self.latency_jitter_ms
            or self.fault_rate > 0
            or self.mutate_prompt
        )

    def apply(self, prompt: str) -> NoiseOutcome:
        """Applies noise and returns the outcome (mutated prompt + telemetry)."""
        injected_latency = 0.0
        if self.latency_ms or self.latency_jitter_ms:
            jitter = self._rng.uniform(0, self.latency_jitter_ms) if self.latency_jitter_ms else 0.0
            injected_latency = self.latency_ms + jitter
            # Sleep for real (capped); the remainder is simulated in metrics.
            time.sleep(min(injected_latency, _MAX_REAL_SLEEP_MS) / 1000.0)

        simulated_faults = [
            kind for kind in self.fault_kinds if self._rng.random() < self.fault_rate
        ]

        mutated_prompt = prompt
        prompt_mutated = False
        if self.mutate_prompt and prompt.strip():
            prefix = self._rng.choice(_PROMPT_PREFIXES)
            suffix = self._rng.choice(_PROMPT_SUFFIXES)
            candidate = f"{prefix}{prompt[0].lower() + prompt[1:] if prompt else prompt}{suffix}"
            if candidate != prompt:
                mutated_prompt = candidate
                prompt_mutated = True

        return NoiseOutcome(
            profile={
                "latency_ms": self.latency_ms,
                "latency_jitter_ms": self.latency_jitter_ms,
                "fault_rate": self.fault_rate,
                "mutate_prompt": self.mutate_prompt,
                **({"seed": self.profile["seed"]} if "seed" in self.profile else {}),
            },
            mutated_prompt=mutated_prompt,
            injected_latency_ms=round(injected_latency, 2),
            simulated_faults=simulated_faults,
            prompt_mutated=prompt_mutated,
        )


def compute_robustness_score(outcome: NoiseOutcome, run_passed: bool) -> float:
    """Scores the agent's ability to withstand the injected noise (0-100).

    A clean pass under noise scores 100. Each simulated fault that the run
    survived costs less than a fault that coincided with a failure.
    """
    if not run_passed:
        # Failed under noise: partial credit scaled by fault pressure.
        pressure = len(outcome.simulated_faults) + (1 if outcome.prompt_mutated else 0)
        return max(0.0, 40.0 - 10.0 * pressure)
    score = 100.0
    score -= 5.0 * len(outcome.simulated_faults)
    if outcome.prompt_mutated:
        score -= 5.0
    return max(0.0, score)
