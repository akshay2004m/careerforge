"""Consistent HTTP error helpers + exception handlers."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("careerforge")


def http_error(status_code: int, detail: str, **extra: Any) -> HTTPException:
    if extra:
        return HTTPException(status_code=status_code, detail={"message": detail, **extra})
    return HTTPException(status_code=status_code, detail=detail)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        from app.core.logging_config import request_id_ctx

        req_id = request_id_ctx.get()
        logger.warning(
            "validation_error path=%s req_id=%s errors=%s", request.url.path, req_id, exc.errors()
        )
        # Flatten for UI-friendly messages
        messages = []
        for err in exc.errors():
            loc = ".".join(str(x) for x in err.get("loc", []) if x != "body")
            messages.append(
                f"{loc}: {err.get('msg', 'invalid')}" if loc else err.get("msg", "invalid")
            )
        return JSONResponse(
            status_code=422,
            content={
                "detail": "; ".join(messages) or "Validation failed",
                "error_code": "validation_error",
                "request_id": req_id,
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_handler(request: Request, exc: StarletteHTTPException):
        from app.core.logging_config import request_id_ctx

        req_id = request_id_ctx.get()
        if exc.status_code >= 500:
            logger.error(
                "http_error path=%s req_id=%s status=%s detail=%s",
                request.url.path,
                req_id,
                exc.status_code,
                exc.detail,
            )
        else:
            logger.warning(
                "http_error path=%s req_id=%s status=%s detail=%s",
                request.url.path,
                req_id,
                exc.status_code,
                exc.detail,
            )

        # Ensure 'detail' handles both str and dict formats seamlessly for the frontend
        return JSONResponse(
            status_code=exc.status_code, content={"detail": exc.detail, "request_id": req_id}
        )

    @app.exception_handler(Exception)
    async def unhandled_handler(request: Request, exc: Exception):
        from app.core.exceptions import CareerForgeException, handle_careerforge_exception
        from app.core.logging_config import request_id_ctx

        if isinstance(exc, CareerForgeException):
            http_exc = handle_careerforge_exception(exc)
            req_id = request_id_ctx.get()
            logger.error(
                f"careerforge_error path={request.url.path} req_id={req_id} detail={http_exc.detail}"
            )
            return JSONResponse(
                status_code=http_exc.status_code,
                content={"detail": http_exc.detail, "request_id": req_id},
            )

        req_id = request_id_ctx.get()
        logger.exception("unhandled_error path=%s req_id=%s err=%s", request.url.path, req_id, exc)
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Internal server error. Please try again.",
                "error_code": "internal_error",
                "request_id": req_id,
            },
        )
