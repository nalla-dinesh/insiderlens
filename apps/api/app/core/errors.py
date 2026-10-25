"""One uniform JSON error model for the whole API.

Shape:
    {"error": {"code": "machine_readable", "message": "human readable", "details": {...} | null}}

Raise `AppError` anywhere in services/routers. Handlers below also normalise
Starlette's HTTPException (404/405...), request-validation 422s, and unexpected
exceptions (logged, never leaked).
"""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_logger
from app.schemas.common import ErrorBody, ErrorResponse

logger = get_logger(__name__)


class AppError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 400,
        details: dict[str, Any] | list[Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details


def _body(code: str, message: str, details: Any = None) -> dict[str, Any]:
    return jsonable_encoder(ErrorResponse(error=ErrorBody(code=code, message=message, details=details)))


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_body(exc.code, exc.message, exc.details),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {404: "not_found", 405: "method_not_allowed", 401: "unauthorized", 403: "forbidden"}.get(
            exc.status_code, "http_error"
        )
        message = str(exc.detail) if exc.detail else "Request failed"
        return JSONResponse(status_code=exc.status_code, content=_body(code, message))

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=_body("validation_error", "Request failed validation", details=exc.errors()),
        )

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled_exception", error=str(exc))
        return JSONResponse(
            status_code=500,
            content=_body("internal_error", "Unexpected server error"),
        )
