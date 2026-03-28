"""Build/deploy pipeline state machine.

States
------
QUEUED → BUILDING → PUSHING → SYNCING → DEPLOYING → HEALTHY
                                                    ↘ FAILED  (from any state)

Each transition emits an :class:`PipelineEvent` that can be forwarded to the
SSE buffer so the browser receives real-time status updates.

Usage::

    from app.services.pipeline_state import PipelineStateMachine, PipelineState

    sm = PipelineStateMachine(deployment_id="dep-123", job_id="build-abc")
    sm.transition(PipelineState.BUILDING)  # QUEUED → BUILDING ✓
    sm.transition(PipelineState.HEALTHY)   # raises InvalidTransitionError
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# State enum
# ---------------------------------------------------------------------------


class PipelineState(StrEnum):
    """Ordered pipeline phases."""

    QUEUED = "queued"
    BUILDING = "building"
    PUSHING = "pushing"
    SYNCING = "syncing"
    DEPLOYING = "deploying"
    HEALTHY = "healthy"
    FAILED = "failed"


# ---------------------------------------------------------------------------
# Allowed transitions
# ---------------------------------------------------------------------------

# Maps each state to the set of states it may transition into.
_ALLOWED: dict[PipelineState, frozenset[PipelineState]] = {
    PipelineState.QUEUED: frozenset({PipelineState.BUILDING, PipelineState.FAILED}),
    PipelineState.BUILDING: frozenset({PipelineState.PUSHING, PipelineState.FAILED}),
    PipelineState.PUSHING: frozenset({PipelineState.SYNCING, PipelineState.FAILED}),
    PipelineState.SYNCING: frozenset({PipelineState.DEPLOYING, PipelineState.FAILED}),
    PipelineState.DEPLOYING: frozenset({PipelineState.HEALTHY, PipelineState.FAILED}),
    PipelineState.HEALTHY: frozenset(),    # terminal
    PipelineState.FAILED: frozenset(),     # terminal
}

# Build timeout defaults (seconds)
DEFAULT_BUILD_TIMEOUT = 15 * 60   # 15 minutes
MAX_BUILD_TIMEOUT = 30 * 60       # 30 minutes


# ---------------------------------------------------------------------------
# Event
# ---------------------------------------------------------------------------


@dataclass
class PipelineEvent:
    """Emitted on every state transition."""

    deployment_id: str
    job_id: str
    from_state: PipelineState
    to_state: PipelineState
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    message: str = ""

    def to_sse_data(self) -> str:
        """JSON-serializable representation for SSE ``event: pipeline`` data."""
        import json
        return json.dumps(
            {
                "deployment_id": self.deployment_id,
                "job_id": self.job_id,
                "state": self.to_state,
                "from_state": self.from_state,
                "timestamp": self.timestamp,
                "message": self.message,
            }
        )


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class InvalidTransitionError(ValueError):
    """Raised when a state transition is not allowed."""

    def __init__(self, from_state: PipelineState, to_state: PipelineState) -> None:
        super().__init__(
            f"Invalid transition: {from_state} → {to_state}. "
            f"Allowed from {from_state}: {sorted(_ALLOWED[from_state])}"
        )
        self.from_state = from_state
        self.to_state = to_state


class BuildTimeoutError(RuntimeError):
    """Raised when the build exceeds the configured maximum timeout."""

    def __init__(self, timeout_seconds: int) -> None:
        super().__init__(
            f"Build timed out after {timeout_seconds}s "
            f"(max={MAX_BUILD_TIMEOUT}s)"
        )
        self.timeout_seconds = timeout_seconds


# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------


class PipelineStateMachine:
    """Tracks the lifecycle of a single build/deploy pipeline run.

    Parameters
    ----------
    deployment_id:
        UUID of the :class:`app.models.deployment.Deployment` record.
    job_id:
        K8s build job name, used to correlate log buffers.
    build_timeout:
        Maximum build duration in seconds. Defaults to
        :data:`DEFAULT_BUILD_TIMEOUT`. Capped at :data:`MAX_BUILD_TIMEOUT`.
    on_transition:
        Optional callback invoked with the :class:`PipelineEvent` after
        every successful transition. Use to forward events to SSE buffers.
    """

    def __init__(
        self,
        deployment_id: str,
        job_id: str,
        build_timeout: int = DEFAULT_BUILD_TIMEOUT,
        on_transition: Callable[[PipelineEvent], None] | None = None,
    ) -> None:
        self.deployment_id = deployment_id
        self.job_id = job_id
        self.build_timeout = min(max(build_timeout, 1), MAX_BUILD_TIMEOUT)
        self._on_transition = on_transition
        self._state = PipelineState.QUEUED
        self._history: list[PipelineEvent] = []
        self._started_at: datetime | None = None

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    @property
    def state(self) -> PipelineState:
        return self._state

    @property
    def history(self) -> list[PipelineEvent]:
        return list(self._history)

    def is_terminal(self) -> bool:
        return self._state in (PipelineState.HEALTHY, PipelineState.FAILED)

    # ------------------------------------------------------------------
    # Transition
    # ------------------------------------------------------------------

    def transition(self, to_state: PipelineState, message: str = "") -> PipelineEvent:
        """Move to *to_state*.

        Parameters
        ----------
        to_state:
            Target state. Must be reachable from the current state.
        message:
            Human-readable description of why this transition happened.

        Returns
        -------
        PipelineEvent
            The event object created for this transition.

        Raises
        ------
        InvalidTransitionError
            If the transition is not allowed from the current state.
        """
        from_state = self._state
        allowed = _ALLOWED[from_state]
        if to_state not in allowed:
            raise InvalidTransitionError(from_state, to_state)

        # Track build start time for timeout enforcement
        if to_state == PipelineState.BUILDING:
            self._started_at = datetime.now(UTC)

        self._state = to_state
        event = PipelineEvent(
            deployment_id=self.deployment_id,
            job_id=self.job_id,
            from_state=from_state,
            to_state=to_state,
            message=message,
        )
        self._history.append(event)
        logger.info(
            "Pipeline %s: %s → %s%s",
            self.deployment_id,
            from_state,
            to_state,
            f" ({message})" if message else "",
        )

        if self._on_transition:
            try:
                self._on_transition(event)
            except Exception:  # noqa: BLE001
                logger.exception("on_transition callback raised an error")

        return event

    def fail(self, reason: str = "") -> PipelineEvent:
        """Shorthand for ``transition(PipelineState.FAILED, reason)``."""
        return self.transition(PipelineState.FAILED, message=reason)

    # ------------------------------------------------------------------
    # Timeout check
    # ------------------------------------------------------------------

    def check_build_timeout(self) -> None:
        """Raise :class:`BuildTimeoutError` if the build has exceeded its timeout.

        Should be called periodically while polling the build job status.
        """
        if self._state != PipelineState.BUILDING:
            return
        if self._started_at is None:
            return
        elapsed = (datetime.now(UTC) - self._started_at).total_seconds()
        if elapsed > self.build_timeout:
            raise BuildTimeoutError(int(elapsed))

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Return a snapshot suitable for JSON serialization."""
        return {
            "deployment_id": self.deployment_id,
            "job_id": self.job_id,
            "state": self._state,
            "build_timeout": self.build_timeout,
            "is_terminal": self.is_terminal(),
            "history": [
                {
                    "from": e.from_state,
                    "to": e.to_state,
                    "timestamp": e.timestamp,
                    "message": e.message,
                }
                for e in self._history
            ],
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def build_timeout_from_settings(seconds: int) -> int:
    """Clamp and validate a build timeout value from user/settings input."""
    if seconds < 1:
        raise ValueError("build_timeout must be at least 1 second")
    if seconds > MAX_BUILD_TIMEOUT:
        raise ValueError(f"build_timeout cannot exceed {MAX_BUILD_TIMEOUT}s ({MAX_BUILD_TIMEOUT // 60}m)")
    return seconds
