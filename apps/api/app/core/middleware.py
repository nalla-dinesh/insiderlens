"""Request-id middleware: every request gets an id, echoed back as X-Request-ID
and bound into structlog contextvars so all logs of that request correlate.
"""

from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from structlog import contextvars


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("x-request-id") or uuid4().hex[:16]
        request.state.request_id = request_id
        contextvars.bind_contextvars(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
        )
        try:
            response = await call_next(request)
        finally:
            contextvars.clear_contextvars()
        response.headers["X-Request-ID"] = request_id
        return response
