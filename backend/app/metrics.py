import math
from collections import deque
from dataclasses import dataclass


@dataclass(slots=True)
class LatencySummary:
    count: int
    p50_ms: float
    p95_ms: float
    p99_ms: float
    max_ms: float

    def as_dict(self) -> dict[str, float | int]:
        return {
            "count": self.count,
            "p50_ms": round(self.p50_ms, 3),
            "p95_ms": round(self.p95_ms, 3),
            "p99_ms": round(self.p99_ms, 3),
            "max_ms": round(self.max_ms, 3),
        }


class LatencyHistogram:
    def __init__(self, max_samples: int = 10_000) -> None:
        self._samples: deque[float] = deque(maxlen=max_samples)

    def observe(self, duration_ms: float) -> None:
        self._samples.append(float(duration_ms))

    def snapshot(self) -> dict[str, float | int]:
        if not self._samples:
            return {"count": 0, "p50_ms": 0.0, "p95_ms": 0.0, "p99_ms": 0.0, "max_ms": 0.0}

        ordered = sorted(self._samples)
        count = len(ordered)
        return LatencySummary(
            count=count,
            p50_ms=self._percentile(ordered, 0.50),
            p95_ms=self._percentile(ordered, 0.95),
            p99_ms=self._percentile(ordered, 0.99),
            max_ms=ordered[-1],
        ).as_dict()

    @staticmethod
    def _percentile(values: list[float], percentile: float) -> float:
        if not values:
            return 0.0
        if len(values) == 1:
            return values[0]
        index = max(0, min(len(values) - 1, math.ceil(percentile * len(values)) - 1))
        return values[index]


latency_histogram = LatencyHistogram()
