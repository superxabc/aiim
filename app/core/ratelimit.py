from __future__ import annotations

import time

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from .config import settings

try:
    from redis import asyncio as aioredis  # type: ignore
except Exception:  # pragma: no cover
    aioredis = None


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self._rate = max(1, int(settings.RATE_LIMIT_PER_SEC))
        self._redis = None
        if settings.REDIS_URL and aioredis is not None:
            self._redis = aioredis.from_url(settings.REDIS_URL)
        self._bucket = {}

    async def dispatch(self, request: Request, call_next):
        # 跳过健康/指标
        path = request.url.path
        if path.startswith("/health") or path.startswith("/metrics") or path.startswith("/api/aiim/ws"):
            return await call_next(request)

        identifier = request.headers.get("Authorization") or request.client.host
        now = int(time.time())
        key = f"rate:{identifier}:{now}"
        allowed = True

        if self._redis is not None:
            try:
                c = await self._redis.incr(key)
                if c == 1:
                    await self._redis.expire(key, 1)
                if c > self._rate:
                    allowed = False
            except Exception:
                pass
        else:
            cnt = self._bucket.get(key, 0) + 1
            self._bucket[key] = cnt
            if cnt > self._rate:
                allowed = False

        if not allowed:
            return Response(status_code=429, content="rate limit exceeded")

        return await call_next(request)


