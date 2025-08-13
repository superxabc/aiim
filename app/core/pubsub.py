from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from .config import settings

try:
    from redis import asyncio as aioredis  # type: ignore

    REDIS_AVAILABLE = True
except Exception:  # pragma: no cover
    aioredis = None
    REDIS_AVAILABLE = False


class InMemoryPubSub:
    def __init__(self) -> None:
        self._subs: Dict[str, List[asyncio.Queue]] = {}
        self._lock = asyncio.Lock()

    async def subscribe(self, channel: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        async with self._lock:
            lst = self._subs.get(channel)
            if lst is None:
                lst = []
                self._subs[channel] = lst
            lst.append(q)
        return q

    async def unsubscribe(self, channel: str, q: asyncio.Queue) -> None:
        async with self._lock:
            lst = self._subs.get(channel)
            if not lst:
                return
            if q in lst:
                lst.remove(q)
                try:
                    q.put_nowait(None)  # sentinel to stop forwarders
                except Exception:
                    pass
            if not lst:
                self._subs.pop(channel, None)

    async def publish(self, channel: str, data: Any) -> None:
        async with self._lock:
            lst = self._subs.get(channel)
            if not lst:
                return
            for q in lst:
                try:
                    q.put_nowait(data)
                except Exception:
                    pass


class RedisPubSub:
    def __init__(self, url: str):
        self._url = url
        self._pub = aioredis.from_url(url)
        self._sub = aioredis.from_url(url)
        self._tasks: Dict[str, asyncio.Task] = {}
        self._queues: Dict[str, asyncio.Queue] = {}
        self._router_key_prefix = "conn:"

    async def subscribe(self, channel: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        pubsub = self._sub.pubsub()
        await pubsub.subscribe(channel)

        async def reader():
            try:
                while True:
                    message = await pubsub.get_message(
                        ignore_subscribe_messages=True, timeout=1.0
                    )
                    if message is None:
                        await asyncio.sleep(0.05)
                        continue
                    data = message.get("data")
                    # 调用方 publish 的是 JSON 序列化后的对象
                    try:
                        import json

                        if isinstance(data, (bytes, bytearray)):
                            data = json.loads(data.decode("utf-8"))
                        elif isinstance(data, str):
                            data = json.loads(data)
                    except Exception:
                        pass
                    await q.put(data)
            except Exception:
                pass
            finally:
                try:
                    await pubsub.unsubscribe(channel)
                    await pubsub.close()
                except Exception:
                    pass

        task = asyncio.create_task(reader())
        self._tasks[channel] = task
        self._queues[channel] = q
        return q

    async def unsubscribe(self, channel: str, q: asyncio.Queue) -> None:
        task = self._tasks.pop(channel, None)
        if task:
            task.cancel()
        self._queues.pop(channel, None)

    async def publish(self, channel: str, data: Any) -> None:
        try:
            import json

            payload = json.dumps(data)
        except Exception:
            payload = data
        await self._pub.publish(channel, payload)

    async def close(self) -> None:
        try:
            await self._pub.close()
        except Exception:
            pass
        try:
            await self._sub.close()
        except Exception:
            pass

    # 在线路由（最小实现）
    async def set_connection(self, user_id: str, info: str, ttl_sec: int = 60) -> None:
        key = f"{self._router_key_prefix}{user_id}"
        await self._pub.set(key, info, ex=ttl_sec)  # type: ignore

    async def get_connection(self, user_id: str) -> Optional[Dict[str, Any]]:
        key = f"{self._router_key_prefix}{user_id}"
        val = await self._pub.get(key)  # type: ignore
        if not val:
            return None
        try:
            import json

            if isinstance(val, (bytes, bytearray)):
                return json.loads(val.decode("utf-8"))
            if isinstance(val, str):
                return json.loads(val)
        except Exception:
            return None


pubsub = (
    RedisPubSub(settings.REDIS_URL)
    if (REDIS_AVAILABLE and settings.REDIS_URL)
    else InMemoryPubSub()
)
