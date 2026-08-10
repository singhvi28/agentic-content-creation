"""Redis pub/sub fan-out so Arq workers can stream events to API WebSockets."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections import defaultdict

from fastapi import WebSocket
from redis.asyncio import Redis

from app.config import get_settings

logger = logging.getLogger(__name__)

CHANNEL_PREFIX = "job_events:"


class JobEventHub:
    def __init__(self) -> None:
        self._subscribers: dict[uuid.UUID, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()
        self._redis: Redis | None = None
        self._pubsub_task: asyncio.Task | None = None
        self._listening: set[uuid.UUID] = set()

    async def connect(self) -> None:
        if self._redis is None:
            self._redis = Redis.from_url(
                get_settings().redis_url, decode_responses=True
            )

    async def close(self) -> None:
        if self._pubsub_task:
            self._pubsub_task.cancel()
            try:
                await self._pubsub_task
            except asyncio.CancelledError:
                pass
            self._pubsub_task = None
        if self._redis:
            await self._redis.aclose()
            self._redis = None

    async def subscribe(self, job_id: uuid.UUID, ws: WebSocket) -> None:
        await self.connect()
        async with self._lock:
            self._subscribers[job_id].add(ws)
            need_listen = job_id not in self._listening
            if need_listen:
                self._listening.add(job_id)
        if need_listen:
            # Start a per-job listener (simple; fine at demo scale)
            asyncio.create_task(self._listen_job(job_id))

    async def unsubscribe(self, job_id: uuid.UUID, ws: WebSocket) -> None:
        async with self._lock:
            self._subscribers[job_id].discard(ws)
            if not self._subscribers[job_id]:
                del self._subscribers[job_id]
                self._listening.discard(job_id)

    async def publish(self, job_id: uuid.UUID, event: dict) -> None:
        """Publish from any process (API or worker)."""
        await self.connect()
        assert self._redis is not None
        payload = json.dumps(event, default=str)
        await self._redis.publish(f"{CHANNEL_PREFIX}{job_id}", payload)

    async def _listen_job(self, job_id: uuid.UUID) -> None:
        assert self._redis is not None
        pubsub = self._redis.pubsub()
        channel = f"{CHANNEL_PREFIX}{job_id}"
        await pubsub.subscribe(channel)
        try:
            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                async with self._lock:
                    still = job_id in self._subscribers
                    sockets = list(self._subscribers.get(job_id, set()))
                if not still:
                    break
                data = message["data"]
                dead: list[WebSocket] = []
                for ws in sockets:
                    try:
                        await ws.send_text(data)
                    except Exception:
                        dead.append(ws)
                for ws in dead:
                    await self.unsubscribe(job_id, ws)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Pubsub listener error for %s", job_id)
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()


hub = JobEventHub()