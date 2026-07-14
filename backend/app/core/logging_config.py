"""Structured-ish request logging for API observability."""

from __future__ import annotations

import logging
import time
import uuid
import contextvars
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

# Context variable to store the request ID for the current async context
request_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")

class RequestIdFilter(logging.Filter):
    """Injects the request_id from contextvars into log records."""
    def filter(self, record):
        record.request_id = request_id_ctx.get()
        return True

def setup_logging() -> None:
    # Use a format that includes the request ID
    log_format = "%(asctime)s %(levelname)s [%(name)s] [req_id=%(request_id)s] %(message)s"
    
    logging.basicConfig(level=logging.INFO, format=log_format)
    
    # Apply filter to the root logger so all logs get request_id
    root_logger = logging.getLogger()
    for handler in root_logger.handlers:
        handler.addFilter(RequestIdFilter())

    # Quiet noisy libs
    logging.getLogger("chromadb").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        req_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        # Set the request ID in context
        token = request_id_ctx.set(req_id)
        
        start = time.perf_counter()
        response: Response | None = None
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = req_id
            return response
        finally:
            ms = (time.perf_counter() - start) * 1000
            status = response.status_code if response is not None else 500
            logging.getLogger("careerforge.http").info(
                "method=%s path=%s status=%s duration_ms=%.1f",
                request.method,
                request.url.path,
                status,
                ms,
            )
            # Reset context var
            request_id_ctx.reset(token)
