from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


class InputSizeGuardMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_request_bytes: int) -> None:  # type: ignore[no-untyped-def]
        super().__init__(app)
        self.max_request_bytes = max_request_bytes

    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        raw_content_length = request.headers.get("content-length")
        if raw_content_length is not None:
            try:
                content_length = int(raw_content_length)
            except ValueError:
                return JSONResponse(
                    status_code=400, content={"detail": "Invalid Content-Length header"}
                )

            if content_length > self.max_request_bytes:
                return JSONResponse(status_code=413, content={"detail": "Request entity too large"})

        return await call_next(request)
