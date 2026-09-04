from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from agent.review_event_broadcaster import ReviewEventBroadcaster


@dataclass(slots=True)
class DAGEvent:
    node: str
    event: str
    timestamp: str
    payload: dict[str, Any] = field(default_factory=dict)


class DAGEventStream:
    def __init__(self, review_id: str | None = None, broadcaster: ReviewEventBroadcaster | None = None) -> None:
        self.review_id = review_id
        self._broadcaster = broadcaster
        self._events: list[DAGEvent] = []

    def emit(self, node: str, event: str, payload: dict[str, Any] | None = None) -> DAGEvent:
        item = DAGEvent(
            node=node,
            event=event,
            timestamp=datetime.now(timezone.utc).isoformat(),
            payload=payload or {},
        )
        self._events.append(item)

        if self._broadcaster is not None and self.review_id:
            message = {
                "review_id": self.review_id,
                "node": item.node,
                "event": item.event,
                "timestamp": item.timestamp,
                "payload": item.payload,
            }
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._broadcaster.publish(self.review_id, message))
            except RuntimeError:
                self._broadcaster.publish_from_thread(self.review_id, message)

        return item

    def snapshot(self) -> list[dict[str, Any]]:
        return [
            {
                "node": event.node,
                "event": event.event,
                "timestamp": event.timestamp,
                "payload": event.payload,
            }
            for event in self._events
        ]
