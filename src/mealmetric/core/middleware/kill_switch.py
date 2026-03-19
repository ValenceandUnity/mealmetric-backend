from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


class KillSwitchMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, enabled: bool) -> None:  # type: ignore[no-untyped-def]
        super().__init__(app)
        self.enabled = enabled

    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        if self.enabled and request.url.path not in {
            "/health",
            "/livez",
            "/readyz",
            "/metrics",
            "/db/health",
        }:
            return JSONResponse(
                status_code=503, content={"detail": "Service temporarily unavailable"}
            )
        return await call_next(request)
