"""In-memory sliding-window rate limit by client IP."""

from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.config import get_settings

# Paths that enqueue or mutate expensive work
LIMITED_PREFIXES = (
    "/content/generate",
)


def _is_limited(path: str, method: str) -> bool:
    if method != "POST":
        return False
    if path.rstrip("/") == "/content/generate":
        return True
    if path.endswith("/choose") or path.endswith("/feedback"):
        return True
    return False


class IPRateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app) -> None:
        super().__init__(app)
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def _client_ip(self, request: Request) -> str:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        if request.client:
            return request.client.host
        return "unknown"

    async def dispatch(self, request: Request, call_next) -> Response:
        settings = get_settings()
        limit = settings.rate_limit_per_minute
        if limit <= 0 or not _is_limited(request.url.path, request.method):
            return await call_next(request)

        ip = self._client_ip(request)
        now = time.monotonic()
        window = self._hits[ip]
        while window and now - window[0] > 60.0:
            window.popleft()
        if len(window) >= limit:
            retry = max(1, int(60 - (now - window[0])))
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded"},
                headers={"Retry-After": str(retry)},
            )
        window.append(now)
        return await call_next(request)
