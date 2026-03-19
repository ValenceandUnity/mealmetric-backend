import time
from collections.abc import Callable

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


class TokenBucketLimiter:
    def __init__(self, rate_per_second: float, clock: Callable[[], float] | None = None) -> None:
        self.rate_per_second = max(rate_per_second, 0.1)
        self.capacity = max(int(rate_per_second), 1)
        self.clock = clock or time.monotonic
        self._buckets: dict[str, tuple[float, float]] = {}

    def allow(self, key: str) -> bool:
        now = self.clock()
        tokens, last = self._buckets.get(key, (float(self.capacity), now))
        elapsed = max(now - last, 0.0)
        tokens = min(float(self.capacity), tokens + elapsed * self.rate_per_second)

        if tokens < 1.0:
            self._buckets[key] = (tokens, now)
            return False

        self._buckets[key] = (tokens - 1.0, now)
        return True


class RateLimiterMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, rate_per_second: float) -> None:  # type: ignore[no-untyped-def]
        super().__init__(app)
        self.limiter = TokenBucketLimiter(rate_per_second=rate_per_second)

    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        client = request.client.host if request.client is not None else "unknown"
        if not self.limiter.allow(client):
            return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded"})
        return await call_next(request)
