from contextvars import ContextVar
from uuid import uuid4

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

REQUEST_ID_HEADER = "X-Request-ID"
request_id_context: ContextVar[str] = ContextVar("request_id", default="-")


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid4())
        request.state.request_id = request_id
        token = request_id_context.set(request_id)
        try:
            response: Response = await call_next(request)
        finally:
            request_id_context.reset(token)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response


def get_request_id() -> str:
    return request_id_context.get()
