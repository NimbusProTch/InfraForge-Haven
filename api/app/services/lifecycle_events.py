"""Lifecycle event bus for real-time SSE streaming of tenant/service/app operations.

Each operation (tenant provision, service provision, app deploy) emits step-by-step
events that the UI consumes via Server-Sent Events (EventSource).

Usage::

    from app.services.lifecycle_events import lifecycle_bus

    # Emit events during tenant provisioning
    lifecycle_bus.emit("tenant:rotterdam", "namespace", "done", "Namespace tenant-rotterdam created")
    lifecycle_bus.emit("tenant:rotterdam", "quota", "done", "ResourceQuota applied (8 CPU, 16Gi)")

    # Stream events to UI
    async for chunk in lifecycle_bus.stream("tenant:rotterdam"):
        yield chunk  # SSE formatted
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import AsyncGenerator

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL = 15  # seconds
MAX_EVENTS = 200
STREAM_TIMEOUT = 300  # 5 minutes max stream


@dataclass
class LifecycleEvent:
    """Single step in a lifecycle operation."""

    event_id: int
    step: str
    status: str  # "running" | "done" | "failed" | "skipped"
    message: str
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    detail: dict | None = None

    def to_sse(self) -> str:
        """Serialize to SSE wire format."""
        data = {
            "step": self.step,
            "status": self.status,
            "message": self.message,
            "timestamp": self.timestamp,
        }
        if self.detail:
            data["detail"] = self.detail
        return f"id: {self.event_id}\nevent: step\ndata: {json.dumps(data)}\n\n"


@dataclass
class _DoneEvent:
    """Signals the operation is complete."""

    event_id: int
    success: bool
    message: str
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_sse(self) -> str:
        data = {"success": self.success, "message": self.message, "timestamp": self.timestamp}
        return f"id: {self.event_id}\nevent: done\ndata: {json.dumps(data)}\n\n"


class LifecycleChannel:
    """Event channel for a single operation (e.g. tenant:rotterdam provision)."""

    def __init__(self, max_events: int = MAX_EVENTS) -> None:
        self._events: deque[LifecycleEvent | _DoneEvent] = deque(maxlen=max_events)
        self._counter: int = 0
        self._done: bool = False
        self._waiters: list[asyncio.Event] = []
        self._created_at: float = time.monotonic()

    def emit(self, step: str, status: str, message: str, detail: dict | None = None) -> LifecycleEvent:
        """Add a step event to the channel."""
        self._counter += 1
        event = LifecycleEvent(
            event_id=self._counter,
            step=step,
            status=status,
            message=message,
            detail=detail,
        )
        self._events.append(event)
        self._notify()
        return event

    def mark_done(self, success: bool = True, message: str = "Operation completed") -> None:
        """Signal that the operation is finished."""
        self._counter += 1
        self._events.append(_DoneEvent(event_id=self._counter, success=success, message=message))
        self._done = True
        self._notify()

    def _notify(self) -> None:
        for w in self._waiters:
            w.set()

    @property
    def is_done(self) -> bool:
        return self._done

    @property
    def events(self) -> list[LifecycleEvent | _DoneEvent]:
        return list(self._events)

    def events_since(self, last_id: int = 0) -> list[LifecycleEvent | _DoneEvent]:
        return [e for e in self._events if e.event_id > last_id]

    async def stream(self, last_event_id: int = 0) -> AsyncGenerator[str, None]:
        """Async generator yielding SSE-formatted strings."""
        start = time.monotonic()

        # Replay buffered events
        for event in self.events_since(last_event_id):
            yield event.to_sse()
            last_event_id = event.event_id

        if self._done:
            return

        # Live tail
        while not self._done and (time.monotonic() - start) < STREAM_TIMEOUT:
            waiter = asyncio.Event()
            self._waiters.append(waiter)
            try:
                await asyncio.wait_for(waiter.wait(), timeout=HEARTBEAT_INTERVAL)
            except asyncio.TimeoutError:
                yield f": heartbeat {int(time.monotonic() - start)}s\n\n"
                continue
            finally:
                self._waiters.remove(waiter)

            for event in self.events_since(last_event_id):
                yield event.to_sse()
                last_event_id = event.event_id


class LifecycleEventBus:
    """Global registry of lifecycle channels, keyed by operation ID.

    Keys follow the pattern:
        tenant:{slug}           — tenant provision/deprovision
        service:{tenant}:{name} — service provision/deprovision
        app:{tenant}:{slug}     — app create/delete
    """

    def __init__(self) -> None:
        self._channels: dict[str, LifecycleChannel] = {}

    def channel(self, key: str) -> LifecycleChannel:
        """Get or create a channel for the given operation key."""
        if key not in self._channels:
            self._channels[key] = LifecycleChannel()
        return self._channels[key]

    def emit(self, key: str, step: str, status: str, message: str, detail: dict | None = None) -> LifecycleEvent:
        """Emit a step event on the given channel."""
        return self.channel(key).emit(step, status, message, detail)

    def mark_done(self, key: str, success: bool = True, message: str = "Operation completed") -> None:
        """Mark an operation channel as done."""
        self.channel(key).mark_done(success, message)

    def get(self, key: str) -> LifecycleChannel | None:
        """Get an existing channel (None if not found)."""
        return self._channels.get(key)

    async def stream(self, key: str, last_event_id: int = 0) -> AsyncGenerator[str, None]:
        """Stream events from a channel."""
        ch = self.channel(key)
        async for chunk in ch.stream(last_event_id):
            yield chunk

    def cleanup(self, max_age_seconds: float = 600) -> int:
        """Remove channels older than max_age_seconds. Returns count removed."""
        now = time.monotonic()
        expired = [k for k, ch in self._channels.items() if ch.is_done and (now - ch._created_at) > max_age_seconds]
        for k in expired:
            del self._channels[k]
        return len(expired)


# Module-level singleton
lifecycle_bus = LifecycleEventBus()
