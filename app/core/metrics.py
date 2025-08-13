from __future__ import annotations

import time


try:
    from prometheus_client import Counter, Histogram
except Exception:  # pragma: no cover
    class _NoopMetric:
        def labels(self, *_, **__):
            return self
        def inc(self, *_, **__):
            return None
        def observe(self, *_, **__):
            return None

    def Counter(*_, **__):  # type: ignore
        return _NoopMetric()

    def Histogram(*_, **__):  # type: ignore
        return _NoopMetric()


HTTP_REQUESTS = Counter("http_requests_total", "HTTP requests total", ["method", "path", "status"])
HTTP_REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "path", "status"],
    buckets=(0.05, 0.1, 0.2, 0.3, 0.5, 1, 2, 5),
)


def add_metrics_middleware(app):
    @app.middleware("http")
    async def _metrics_middleware(request, call_next):
        start = time.time()
        response = None
        try:
            response = await call_next(request)
            return response
        finally:
            status = str(getattr(response, "status_code", 500))
            method = request.method
            path = "/".join([p for p in request.url.path.split("/") if p][:2])
            path = f"/{path}" if path else "/"
            HTTP_REQUESTS.labels(method=method, path=path, status=status).inc()
            HTTP_REQUEST_LATENCY.labels(method=method, path=path, status=status).observe(time.time() - start)


