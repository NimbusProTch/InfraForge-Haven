"""Tests for Sprint I-10: Build/Deploy Pipeline UX.

Covers:
- ANSI → HTML conversion (ansi_parser)
- SSE buffer (reconnect, heartbeat, buffer)
- Pipeline state machine (transitions, timeout, serialization)
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.services.ansi_parser import ansi_to_html, strip_ansi
from app.services.pipeline_state import (
    DEFAULT_BUILD_TIMEOUT,
    MAX_BUILD_TIMEOUT,
    BuildTimeoutError,
    InvalidTransitionError,
    PipelineEvent,
    PipelineState,
    PipelineStateMachine,
    build_timeout_from_settings,
)
from app.services.sse_buffer import SseBufferRegistry, SseEvent, SseLogBuffer

# ===========================================================================
# ANSI Parser tests
# ===========================================================================


class TestAnsiParser:
    def test_plain_text_unchanged(self):
        assert ansi_to_html("hello world") == "hello world"

    def test_green_foreground(self):
        html = ansi_to_html("\x1b[32mOK\x1b[0m")
        assert '<span class="fg-green">OK</span>' in html

    def test_red_foreground(self):
        html = ansi_to_html("\x1b[31mERROR\x1b[0m")
        assert '<span class="fg-red">ERROR</span>' in html

    def test_bold(self):
        html = ansi_to_html("\x1b[1mbold text\x1b[0m")
        assert "bold" in html
        assert "bold text" in html

    def test_yellow(self):
        html = ansi_to_html("\x1b[33mWARN\x1b[0m")
        assert "fg-yellow" in html

    def test_blue(self):
        html = ansi_to_html("\x1b[34mINFO\x1b[0m")
        assert "fg-blue" in html

    def test_cyan(self):
        html = ansi_to_html("\x1b[36mDEBUG\x1b[0m")
        assert "fg-cyan" in html

    def test_reset_closes_span(self):
        html = ansi_to_html("\x1b[32mgreen\x1b[0m plain")
        assert "</span>" in html
        assert "plain" in html
        # After reset, no open span around "plain"
        idx_span_close = html.index("</span>")
        idx_plain = html.index("plain")
        assert idx_plain > idx_span_close

    def test_combined_bold_and_color(self):
        html = ansi_to_html("\x1b[1;32mBold Green\x1b[0m")
        assert "bold" in html
        assert "fg-green" in html

    def test_html_entities_escaped(self):
        html = ansi_to_html("<script>alert('xss')</script>")
        assert "<script>" not in html
        assert "&lt;script&gt;" in html

    def test_carriage_return_stripped(self):
        # Progress bar pattern: multiple \r overwrites
        html = ansi_to_html("10%\r50%\r100%")
        assert "\r" not in html

    def test_newline_to_br_option(self):
        html = ansi_to_html("line1\nline2", newline_to_br=True)
        assert "<br>" in html

    def test_strip_ansi(self):
        plain = strip_ansi("\x1b[32mgreen\x1b[0m text")
        assert plain == "green text"

    def test_non_sgr_sequences_discarded(self):
        # Cursor movement \x1b[2J (clear screen) — should be silently removed
        html = ansi_to_html("before\x1b[2Jafter")
        assert "before" in html
        assert "after" in html
        assert "\x1b" not in html

    def test_bright_colors(self):
        html = ansi_to_html("\x1b[92mbright green\x1b[0m")
        assert "fg-bright-green" in html

    def test_background_color(self):
        html = ansi_to_html("\x1b[41mred bg\x1b[0m")
        assert "bg-red" in html


# ===========================================================================
# SSE Buffer tests
# ===========================================================================


class TestSseEvent:
    def test_to_sse_format(self):
        evt = SseEvent(event_id=1, data="hello world", event_type="log")
        sse = evt.to_sse()
        assert "id: 1" in sse
        assert "event: log" in sse
        assert "data: hello world" in sse
        assert sse.endswith("\n\n")

    def test_multiline_data(self):
        evt = SseEvent(event_id=2, data="line1\nline2", event_type="log")
        sse = evt.to_sse()
        assert "data: line1" in sse
        assert "data: line2" in sse


class TestSseLogBuffer:
    def test_append_returns_incrementing_ids(self):
        buf = SseLogBuffer(job_id="j1")
        id1 = buf.append("line 1")
        id2 = buf.append("line 2")
        assert id2 == id1 + 1

    def test_events_since_filters_by_id(self):
        buf = SseLogBuffer(job_id="j2")
        buf.append("line 1")
        buf.append("line 2")
        buf.append("line 3")
        events = buf.events_since(last_event_id=1)
        assert len(events) == 2
        assert events[0].data == "line 2"

    def test_events_since_zero_returns_all(self):
        buf = SseLogBuffer(job_id="j3")
        buf.append("a")
        buf.append("b")
        assert len(buf.events_since(0)) == 2

    def test_max_lines_circular_buffer(self):
        buf = SseLogBuffer(job_id="j4", max_lines=3)
        for i in range(5):
            buf.append(f"line {i}")
        # Only last 3 lines retained
        all_events = buf.events_since(0)
        assert len(all_events) == 3
        assert all_events[0].data == "line 2"
        assert all_events[-1].data == "line 4"

    def test_mark_done_sets_flag(self):
        buf = SseLogBuffer(job_id="j5")
        assert not buf.is_done()
        buf.mark_done()
        assert buf.is_done()

    @pytest.mark.asyncio
    async def test_stream_yields_buffered_lines_then_done(self):
        buf = SseLogBuffer(job_id="j6")
        buf.append("line A")
        buf.append("line B")
        buf.mark_done()

        events = []
        async for chunk in buf.stream(last_event_id=0, heartbeat_interval=1):
            events.append(chunk)

        # Should have 2 log events + 1 done event
        assert any("line A" in e for e in events)
        assert any("line B" in e for e in events)
        assert any("event: done" in e for e in events)

    @pytest.mark.asyncio
    async def test_stream_reconnect_skips_seen_events(self):
        buf = SseLogBuffer(job_id="j7")
        buf.append("old line")  # event_id=1
        buf.append("new line")  # event_id=2
        buf.mark_done()

        events = []
        # Resume from event_id=1 — should only get "new line"
        async for chunk in buf.stream(last_event_id=1, heartbeat_interval=1):
            events.append(chunk)

        lines = "\n".join(events)
        assert "new line" in lines
        assert "old line" not in lines


class TestSseBufferRegistry:
    def test_get_or_create(self):
        reg = SseBufferRegistry()
        buf = reg.get_or_create("job-1")
        assert isinstance(buf, SseLogBuffer)
        # Same object returned on second call
        assert reg.get_or_create("job-1") is buf

    def test_get_returns_none_for_missing(self):
        reg = SseBufferRegistry()
        assert reg.get("nonexistent") is None

    def test_evict(self):
        reg = SseBufferRegistry()
        reg.get_or_create("job-evict")
        assert len(reg) == 1
        reg.evict("job-evict")
        assert len(reg) == 0


# ===========================================================================
# Pipeline state machine tests
# ===========================================================================


class TestPipelineStateMachine:
    def test_initial_state_is_queued(self):
        sm = PipelineStateMachine("dep-1", "job-1")
        assert sm.state == PipelineState.QUEUED

    def test_happy_path_full_transition(self):
        sm = PipelineStateMachine("dep-1", "job-1")
        sm.transition(PipelineState.BUILDING)
        sm.transition(PipelineState.PUSHING)
        sm.transition(PipelineState.SYNCING)
        sm.transition(PipelineState.DEPLOYING)
        sm.transition(PipelineState.HEALTHY)
        assert sm.state == PipelineState.HEALTHY
        assert sm.is_terminal()

    def test_fail_from_any_non_terminal_state(self):
        # Ordered path: advance step-by-step and verify fail is always allowed
        ordered = [
            PipelineState.QUEUED,
            PipelineState.BUILDING,
            PipelineState.PUSHING,
            PipelineState.SYNCING,
            PipelineState.DEPLOYING,
        ]
        for i, start_state in enumerate(ordered):
            sm = PipelineStateMachine("dep-x", "job-x")
            # Advance to start_state by following the ordered path up to index i
            for s in ordered[1 : i + 1]:
                sm.transition(s)
            assert sm.state == start_state
            sm.fail("test failure")
            assert sm.state == PipelineState.FAILED

    def test_invalid_transition_raises(self):
        sm = PipelineStateMachine("dep-2", "job-2")
        with pytest.raises(InvalidTransitionError):
            sm.transition(PipelineState.HEALTHY)  # QUEUED → HEALTHY not allowed

    def test_skip_state_raises(self):
        sm = PipelineStateMachine("dep-3", "job-3")
        sm.transition(PipelineState.BUILDING)
        with pytest.raises(InvalidTransitionError):
            sm.transition(PipelineState.DEPLOYING)  # BUILDING → DEPLOYING skips PUSHING/SYNCING

    def test_transition_from_terminal_raises(self):
        sm = PipelineStateMachine("dep-4", "job-4")
        sm.fail("early fail")
        with pytest.raises(InvalidTransitionError):
            sm.transition(PipelineState.BUILDING)

    def test_history_records_all_transitions(self):
        sm = PipelineStateMachine("dep-5", "job-5")
        sm.transition(PipelineState.BUILDING, "started build")
        sm.fail("oops")
        assert len(sm.history) == 2
        assert sm.history[0].to_state == PipelineState.BUILDING
        assert sm.history[1].to_state == PipelineState.FAILED
        assert sm.history[0].message == "started build"

    def test_on_transition_callback_called(self):
        events: list[PipelineEvent] = []
        sm = PipelineStateMachine("dep-6", "job-6", on_transition=events.append)
        sm.transition(PipelineState.BUILDING)
        sm.transition(PipelineState.PUSHING)
        assert len(events) == 2
        assert events[0].to_state == PipelineState.BUILDING

    def test_build_timeout_not_raised_before_started(self):
        sm = PipelineStateMachine("dep-7", "job-7", build_timeout=1)
        # Not BUILDING yet — no timeout
        sm.check_build_timeout()  # Should not raise

    def test_build_timeout_raises_when_exceeded(self):
        sm = PipelineStateMachine("dep-8", "job-8", build_timeout=1)
        sm.transition(PipelineState.BUILDING)
        # Backdate _started_at by 2 seconds
        sm._started_at = datetime.now(UTC) - timedelta(seconds=2)
        with pytest.raises(BuildTimeoutError):
            sm.check_build_timeout()

    def test_build_timeout_not_exceeded_within_limit(self):
        sm = PipelineStateMachine("dep-9", "job-9", build_timeout=60)
        sm.transition(PipelineState.BUILDING)
        sm.check_build_timeout()  # Should not raise

    def test_max_timeout_capped(self):
        sm = PipelineStateMachine("dep-10", "job-10", build_timeout=9999)
        assert sm.build_timeout == MAX_BUILD_TIMEOUT

    def test_to_dict(self):
        sm = PipelineStateMachine("dep-11", "job-11")
        sm.transition(PipelineState.BUILDING)
        d = sm.to_dict()
        assert d["state"] == "building"
        assert d["deployment_id"] == "dep-11"
        assert len(d["history"]) == 1

    def test_pipeline_event_sse_data(self):
        sm = PipelineStateMachine("dep-12", "job-12")
        evt = sm.transition(PipelineState.BUILDING, "starting")
        data = evt.to_sse_data()
        import json

        parsed = json.loads(data)
        assert parsed["state"] == "building"
        assert parsed["deployment_id"] == "dep-12"
        assert parsed["message"] == "starting"


class TestBuildTimeoutFromSettings:
    def test_valid_value_returned(self):
        assert build_timeout_from_settings(600) == 600

    def test_default_valid(self):
        assert build_timeout_from_settings(DEFAULT_BUILD_TIMEOUT) == DEFAULT_BUILD_TIMEOUT

    def test_raises_below_one(self):
        with pytest.raises(ValueError, match="at least 1"):
            build_timeout_from_settings(0)

    def test_raises_above_max(self):
        with pytest.raises(ValueError, match="cannot exceed"):
            build_timeout_from_settings(MAX_BUILD_TIMEOUT + 1)
