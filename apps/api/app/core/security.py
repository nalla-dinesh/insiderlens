"""Phase-08 hardening primitives.

- SecurityHeadersMiddleware: nosniff / DENY frame / no-referrer on every API response.
- AnalysisRateLimitMiddleware: fixed-window (5 POSTs/min/client) on /api/analysis/run
  — a run is the most expensive endpoint in the system; in production it must not
  be a DoS vector (Laptop dev unchanged: middleware only mounted when
  settings.is_production is True — see app/main.py).
- cors_prod_guard(): ENV=production + CORS_ORIGINS containing '*' → refuse startup
  (shell-out config typos must never quietly ship wide-open CORS).
"""

from __future__ import annotations

import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.errors import _body as error_body


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        return response


class AnalysisRateLimitMiddleware(BaseHTTPMiddleware):
    """Fixed-window limiter, in-memory (single-instance; free tier). Path-scoped to
    POST /api/analysis/run — GET queries and every other endpoint stay untouched."""

    def __init__(self, app, *, max_hits: int = 5, window_seconds: int = 60) -> None:  # noqa: ANN001
        super().__init__(app)
        self.max_hits = max_hits
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.method == "POST" and request.url.path == "/api/analysis/run":
            now = time.monotonic()
            client = request.client.host if request.client else "unknown"
            q = self._hits[client]
            while q and now - q[0] > self.window:
                q.popleft()
            if len(q) >= self.max_hits:
                return JSONResponse(
                    status_code=429,
                    content=error_body(
                        code="rate_limited",
                        message=(
                            f"analysis runs are limited to {self.max_hits}/min per client "
                            "in production — the queue keeps working meanwhile."
                        ),
                    ),
                )
            q.append(now)
        return await call_next(request)


def cors_prod_guard(origins: list[str], *, is_production: bool) -> None:
    """Starve the * typo at startup — production + wildcard CORS refuses to boot."""
    if is_production and ("*" in origins or not origins):
        raise RuntimeError(
            "CORS_ORIGINS='*' (or empty) with ENV=production is refused. "
            "Name your real origins: CORS_ORIGINS=https://your-web.example.com"
        )
