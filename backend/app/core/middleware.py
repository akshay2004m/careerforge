"""Security middleware: headers + rate limiting (auth + heavy AI routes)."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Callable, Deque, Dict, Tuple

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

# path prefix → (max_requests, window_seconds)
RATE_LIMIT_RULES: list[Tuple[str, int, int]] = [
    ("/api/auth/", 30, 60),
    ("/api/optimize", 8, 60),
    ("/api/interview/", 12, 60),
    ("/api/skills/", 20, 60),
]

# Paths under /api/auth that skip rate limiting
AUTH_SKIP = {"/api/auth/me"}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "microphone=(self), camera=()"
        response.headers["Cache-Control"] = "no-store"
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding-window rate limit keyed by (rule, client_ip)."""

    def __init__(self, app):
        super().__init__(app)
        self._hits: Dict[str, Deque[float]] = defaultdict(deque)

    def _client_ip(self, request: Request) -> str:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def _match_rule(self, path: str, method: str) -> Tuple[str, int, int] | None:
        if method == "OPTIONS":
            return None
        # Never rate-limit WebSocket upgrade paths (GET + Upgrade) — a 429 breaks the handshake
        if "/ws/" in path:
            return None
        for prefix, max_req, window in RATE_LIMIT_RULES:
            if path.startswith(prefix):
                if path in AUTH_SKIP or path.rstrip("/") in AUTH_SKIP:
                    return None
                # Don't rate-limit auth password change? keep limited
                return prefix, max_req, window
        return None

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        rule = self._match_rule(request.url.path, request.method)
        if not rule:
            return await call_next(request)

        prefix, max_requests, window = rule
        ip = self._client_ip(request)
        key = f"{prefix}:{ip}"
        now = time.time()
        q = self._hits[key]
        while q and now - q[0] > window:
            q.popleft()
        if len(q) >= max_requests:
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Rate limit exceeded for this endpoint. Please wait and try again."
                },
                headers={"Retry-After": str(window)},
            )
        q.append(now)
        return await call_next(request)


# Back-compat alias
AuthRateLimitMiddleware = RateLimitMiddleware
