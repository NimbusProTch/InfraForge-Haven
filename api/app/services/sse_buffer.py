"""SSE log streaming buffer with reconnect support, heartbeat, and line cache.

Features
--------
- Circular in-memory buffer of the last ``max_lines`` log lines per build job.
- ``Last-Event-ID`` header support: new connections receive buffered lines from
  the last known event ID so no output is lost on reconnect.
- 30-second keep-alive heartbeat comment (``": heartbeat\\n\\n"``) to prevent
  proxy/browser timeouts.
- Thread-safe via asyncio: all mutating operations happen in the event loop.

Usage::

    from app.services.sse_buffer import SseLogBuffer, SseEvent

    buffer = SseLogBuffer(job_id="build-abc-12345678")
    buffer.append("line 1")
    buffer.append("line 2")

    # Consume as SSE events from event_id 0 onward
    events = buffer.events_since(last_event_id=0)
    for evt in events:
        print(evt.to_sse())
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

logger = logging.getLogger(__name__)

_DEFAULT_MAX_LINES = 100
_HEARTBEAT_INTERVAL = 30  # seconds


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class SseEvent:
    """A single Server-Sent Event."""

    event_id: int
    data: str
    event_type: str = "log"

    def to_sse(self) -> str:
        """Serialize to SSE wire format."""
        lines = [
            f"id: {self.event_id}",
            f"event: {self.event_type}",
        ]
        # Multi-line data: each line prefixed with "data: "
        for line in self.data.splitlines():
            lines.append(f"data: {line}")
        lines.append("")  # blank line = event boundary
        lines.append("")
        return "\n".join(lines)


@dataclass
class _BufferedLine:
    event_id: int
    text: str


# ---------------------------------------------------------------------------
# SseLogBuffer
# ---------------------------------------------------------------------------


class SseLogBuffer:
    """Per-build-job circular buffer of log lines with SSE emission helpers.

    Parameters
    ----------
    job_id:
        Unique identifier for the build job (used for logging only).
    max_lines:
        Maximum number of lines to keep in the circular buffer.
        Oldest lines are dropped when the buffer is full.
    """

    def __init__(self, job_id: str, max_lines: int = _DEFAULT_MAX_LINES) -> None:
        self.job_id = job_id
        self._max_lines = max_lines
        self._buffer: deque[_BufferedLine] = deque(maxlen=max_lines)
        self._next_id: int = 1
        self._done: bool = False
        self._waiters: list[asyncio.Future[None]] = []

    # ------------------------------------------------------------------
    # Write side
    # ------------------------------------------------------------------

    def append(self, text: str) -> int:
        """Append a log line and return its event ID."""
        event_id = self._next_id
        self._next_id += 1
        self._buffer.append(_BufferedLine(event_id=event_id, text=text))
        self._notify_waiters()
        return event_id

    def mark_done(self) -> None:
        """Signal that no more lines will be appended (build finished)."""
        self._done = True
        self._notify_waiters()

    # ------------------------------------------------------------------
    # Read side
    # ------------------------------------------------------------------

    def events_since(self, last_event_id: int = 0) -> list[SseEvent]:
        """Return buffered events with event_id > last_event_id."""
        return [
            SseEvent(event_id=item.event_id, data=item.text)
            for item in self._buffer
            if item.event_id > last_event_id
        ]

    def is_done(self) -> bool:
        return self._done

    # ------------------------------------------------------------------
    # Async streaming
    # ------------------------------------------------------------------

    async def stream(
        self,
        last_event_id: int = 0,
        heartbeat_interval: float = _HEARTBEAT_INTERVAL,
    ) -> AsyncIterator[str]:
        """Async generator that yields SSE-formatted strings.

        Sends buffered lines immediately, then waits for new lines or a
        heartbeat comment. Stops when :meth:`mark_done` is called.

        Parameters
        ----------
        last_event_id:
            Resume from this event ID (from ``Last-Event-ID`` header).
        heartbeat_interval:
            Seconds between keep-alive comments (default 30).
        """
        # Flush buffered lines first
        for evt in self.events_since(last_event_id):
            yield evt.to_sse()
            last_event_id = evt.event_id

        # Stream new lines as they arrive
        while not self._done:
            try:
                await asyncio.wait_for(self._wait_for_new(), timeout=heartbeat_interval)
            except TimeoutError:
                # Send heartbeat to keep connection alive
                yield ": heartbeat\n\n"
                continue

            # Emit any new lines
            for evt in self.events_since(last_event_id):
                yield evt.to_sse()
                last_event_id = evt.event_id

        # Final flush after mark_done
        for evt in self.events_since(last_event_id):
            yield evt.to_sse()

        # Send done event
        yield SseEvent(event_id=self._next_id, data="", event_type="done").to_sse()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _notify_waiters(self) -> None:
        for fut in self._waiters:
            if not fut.done():
                fut.set_result(None)
        self._waiters.clear()

    async def _wait_for_new(self) -> None:
        """Wait until a new line is appended or the buffer is done."""
        loop = asyncio.get_event_loop()
        fut: asyncio.Future[None] = loop.create_future()
        self._waiters.append(fut)
        await fut


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class SseBufferRegistry:
    """Global registry mapping job_id → SseLogBuffer.

    Provides a single place to create/retrieve/evict buffers across the
    application lifetime.
    """

    def __init__(self) -> None:
        self._buffers: dict[str, SseLogBuffer] = {}

    def get_or_create(self, job_id: str, max_lines: int = _DEFAULT_MAX_LINES) -> SseLogBuffer:
        """Return the buffer for *job_id*, creating it if it doesn't exist."""
        if job_id not in self._buffers:
            self._buffers[job_id] = SseLogBuffer(job_id=job_id, max_lines=max_lines)
            logger.debug("SseLogBuffer created for job %s", job_id)
        return self._buffers[job_id]

    def get(self, job_id: str) -> SseLogBuffer | None:
        """Return existing buffer or ``None``."""
        return self._buffers.get(job_id)

    def evict(self, job_id: str) -> None:
        """Remove a buffer from the registry (call after job is done)."""
        self._buffers.pop(job_id, None)

    def __len__(self) -> int:
        return len(self._buffers)


# Module-level singleton
sse_registry = SseBufferRegistry()
