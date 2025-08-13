from __future__ import annotations

import asyncio
from typing import Dict

from .config import settings

_lock = asyncio.Lock()
_in_memory_seq: Dict[str, int] = {}

_redis_client = None
if settings.REDIS_URL:
    try:
        from redis import asyncio as aioredis  # type: ignore

        _redis_client = aioredis.from_url(settings.REDIS_URL)
    except Exception:  # pragma: no cover
        _redis_client = None


async def next_seq(conversation_id: str) -> int:
    key = f"seq:{conversation_id}"
    # Prefer Redis if available
    if _redis_client is not None:
        try:
            return int(await _redis_client.incr(key))
        except Exception:
            pass
    # Fallback: in-memory per-process（仅当不强制 Redis 时，否则抛错）
    if settings.REQUIRE_REDIS:
        raise RuntimeError("Redis is required for seq generation in production")
    async with _lock:
        current = _in_memory_seq.get(key, 0) + 1
        _in_memory_seq[key] = current
        return current


