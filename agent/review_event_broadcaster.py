from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from fastapi import WebSocket


class ReviewEventBroadcaster:
    def __init__(self) -> None:
        self._subscribers: dict[str, set[WebSocket]] = defaultdict(set)
        self._events: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._reviews: dict[str, dict[str, Any]] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._loops: dict[str, asyncio.AbstractEventLoop] = {}

    def create(self, review_id: str, loop: asyncio.AbstractEventLoop) -> None:
        self._reviews[review_id] = {"status": "created", "result": None, "error": None}
        self._events[review_id] = []
        self._locks[review_id] = asyncio.Lock()
        self._loops[review_id] = loop

    def status(self, review_id: str) -> dict[str, Any] | None:
        state = self._reviews.get(review_id)
        if state is None:
            return None
        return {"review_id": review_id, "status": state["status"], "result": state["result"], "error": state["error"], "events": list(self._events[review_id])}

    def subscribe(self, review_id: str, websocket: WebSocket) -> None:
        self._subscribers[review_id].add(websocket)

    def unsubscribe(self, review_id: str, websocket: WebSocket) -> None:
        sockets = self._subscribers.get(review_id, set())
        sockets.discard(websocket)
        if not sockets:
            self._subscribers.pop(review_id, None)

    async def publish(self, review_id: str, payload: dict[str, Any]) -> None:
        if review_id not in self._reviews:
            return
        self._events[review_id].append(payload)
        async with self._locks[review_id]:
            for websocket in list(self._subscribers.get(review_id, set())):
                try:
                    await websocket.send_json(payload)
                except Exception:
                    self.unsubscribe(review_id, websocket)

    def publish_from_thread(self, review_id: str, payload: dict[str, Any]) -> None:
        loop = self._loops.get(review_id)
        if loop is not None and not loop.is_closed():
            asyncio.run_coroutine_threadsafe(self.publish(review_id, payload), loop)

    async def set_status(self, review_id: str, status: str, result: dict[str, Any] | None = None, error: str | None = None) -> None:
        if review_id not in self._reviews:
            return
        self._reviews[review_id].update({"status": status, "result": result, "error": error})
        await self.publish(review_id, {
            "review_id": review_id,
            "node": "review_lifecycle",
            "event": f"review_{status}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": {"status": status, **({"error": error} if error else {})},
            "type": f"review_{status}",
        })

    async def attach(self, review_id: str, websocket: WebSocket) -> bool:
        if review_id not in self._reviews:
            return False
        self._subscribers[review_id].add(websocket)
        async with self._locks[review_id]:
            await websocket.send_json({"type": "connected", "review_id": review_id})
            for event in list(self._events[review_id]):
                await websocket.send_json(event)
        return True


review_event_broadcaster = ReviewEventBroadcaster()
