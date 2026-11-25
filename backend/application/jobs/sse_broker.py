"""Server-Sent Events (SSE) Pub/Sub Event Broker.

Architectural Guarantees:
- Thread-safe publisher-subscriber pattern implementing IEventBroker.
- Dispatches typed domain events (mobile.batch_received, asset.updated, ai.progress,
  ozon.status_changed, sync.progress).
- Bounded client queues protecting against memory leaks from slow or disconnected clients.
- Clean SSE wire format conforming to W3C EventSource specifications.
"""

from __future__ import annotations

import json
import logging
import queue
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from backend.domain.ports import IEventBroker

logger = logging.getLogger(__name__)

# Valid domain SSE event types
EVENT_MOBILE_BATCH = "mobile.batch_received"
EVENT_ASSET_UPDATED = "asset.updated"
EVENT_AI_PROGRESS = "ai.progress"
EVENT_OZON_STATUS = "ozon.status_changed"
EVENT_SYNC_PROGRESS = "sync.progress"


@dataclass(frozen=True)
class SSEEvent:
    """Strongly-typed SSE message."""

    event_type: str
    data: Dict[str, Any] = field(default_factory=dict)
    event_id: Optional[str] = None
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_sse_message(self) -> str:
        """Format as valid SSE wire message."""
        payload = dict(self.data)
        if "timestamp" not in payload:
            payload["timestamp"] = self.timestamp

        data_json = json.dumps(payload, ensure_ascii=False)
        lines = [f"event: {self.event_type}"]
        if self.event_id:
            lines.append(f"id: {self.event_id}")
        lines.append(f"data: {data_json}")
        return "\n".join(lines) + "\n\n"


class SSEBroker(IEventBroker):
    """Thread-safe in-memory SSE broker distributing events to active HTTP streams."""

    def __init__(self, max_queue_size: int = 100) -> None:
        self.max_queue_size = max_queue_size
        self._subscribers: Set[queue.Queue[SSEEvent]] = set()
        self._lock = threading.Lock()

    def subscribe(self) -> queue.Queue[SSEEvent]:
        """Register a new client listener and return its event queue."""
        q: queue.Queue[SSEEvent] = queue.Queue(maxsize=self.max_queue_size)
        with self._lock:
            self._subscribers.add(q)
            count = len(self._subscribers)
        logger.debug("SSE client subscribed (active listeners: %d)", count)
        return q

    def unsubscribe(self, q: queue.Queue[SSEEvent]) -> None:
        """Unregister a client listener safely."""
        with self._lock:
            self._subscribers.discard(q)
            count = len(self._subscribers)
        logger.debug("SSE client unsubscribed (active listeners: %d)", count)

    @property
    def subscriber_count(self) -> int:
        """Return number of currently active subscribers."""
        with self._lock:
            return len(self._subscribers)

    def publish(self, event_type: str, data: Dict[str, Any]) -> None:
        """Publish a typed event to all connected subscribers."""
        event = SSEEvent(event_type=event_type, data=data)
        dead_queues: List[queue.Queue[SSEEvent]] = []

        with self._lock:
            subscribers_snapshot = list(self._subscribers)

        for q in subscribers_snapshot:
            try:
                # Non-blocking put to protect other clients from slow readers
                q.put_nowait(event)
            except queue.Full:
                logger.warning("Subscriber queue is full; dropping event and marking for disconnect")
                dead_queues.append(q)

        if dead_queues:
            with self._lock:
                for dq in dead_queues:
                    self._subscribers.discard(dq)
