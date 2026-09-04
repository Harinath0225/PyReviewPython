import time

from starlette.middleware.base import BaseHTTPMiddleware

from backend.app.metrics import latency_histogram


class LatencyMetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        started = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - started) * 1000.0
        latency_histogram.observe(duration_ms)
        response.headers["X-Latency-ms"] = f"{duration_ms:.2f}"
        response.headers["X-Latency-p50-ms"] = f"{latency_histogram.snapshot()['p50_ms']:.2f}"
        return response
