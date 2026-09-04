from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class MemoryEntry:
    role: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


class InMemoryReviewMemory:
    def __init__(self, max_messages: int = 50) -> None:
        self._store: dict[str, deque[MemoryEntry]] = defaultdict(deque)
        self.max_messages = max_messages

    def add(self, review_id: str, role: str, content: str, **metadata: Any) -> None:
        queue = self._store[review_id]
        queue.append(MemoryEntry(role=role, content=content, metadata=metadata))
        while len(queue) > self.max_messages:
            queue.popleft()

    def get_context(self, review_id: str) -> list[dict[str, Any]]:
        return [
            {"role": entry.role, "content": entry.content, **entry.metadata}
            for entry in self._store.get(review_id, deque())
        ]

    def summarize(self, review_id: str) -> dict[str, Any]:
        entries = self.get_context(review_id)
        return {
            "review_id": review_id,
            "messages": len(entries),
            "last_role": entries[-1]["role"] if entries else None,
            "last_content_preview": entries[-1]["content"][:180] if entries else None,
        }
