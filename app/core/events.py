from __future__ import annotations

import asyncio
from typing import Any

from .pubsub import pubsub


async def publish_event(channel: str, payload: Any) -> None:
    await pubsub.publish(channel, payload)


def publish_event_async(channel: str, payload: Any) -> None:
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(pubsub.publish(channel, payload))
    except RuntimeError:
        asyncio.run(pubsub.publish(channel, payload))
