"""Tests for the boundary: it must fail open, and it must be clearable."""

from __future__ import annotations

import datetime as dt
import io
import json
import os
from pathlib import Path

from agent_yield import boundary
from agent_yield.boundary import (
    OVERRIDE_ENV,
    boundary_message,
    decide,
    handoff_is_current,
    main,
)
from agent_yield.session import session_stats

STARTED = dt.datetime(2026, 8, 26, 2, 0, tzinfo=dt.timezone.utc)


def _transcript(tmp_path: Path, reads: list[int], name: str = "s") -> Path:
    lines = []
    for index, read in enumerate(reads):
        lines.append(json.dumps({
            "timestamp": f"2026-08-26T02:{index // 60:02d}:{index % 60:02d}.000Z",
            "sessionId": name, "requestId": f"req-{index}",
            "message": {"id": f"msg-{index}",
                        "usage": {"cache_read_input_tokens": read}},
        }))
    path = tmp_path / f"{name}.jsonl"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _grown(tmp_path: Path):
    """A session at 10x growth: opens at 10K, sits at 100K."""
    reads = [10_000] * 10 + [100_000] * 10
    return session_stats(_transcript(tmp_path, reads))


def _steep(tmp_path: Path):
    """A session deep in the cost band without ever doubling."""
    return session_stats(_transcript(tmp_path, [500_000] * 20, name="deep"))


def _cheap(tmp_path: Path):
    return session_stats(_transcript(tmp_path, [20_000] * 20, name="cheap"))


def _touch_handoff(tmp_path: Path, when: dt.datetime) -> Path:
    path = tmp_path / "handoff.md"
    path.write_text("# Handoff\n", encoding="utf-8")
    stamp = when.timestamp()
    os.utime(path, (stamp, stamp))
    return path


def test_a_cheap_session_is_never_stopped(tmp_path):
    assert boundary_message(_cheap(tmp_path), tmp_path / "none.md") is None


def test_growth_past_the_hard_factor_stops_the_session(tmp_path):
    message = boundary_message(_grown(tmp_path), tmp_path / "none.md")
    assert "grown 10.0x" in message
    assert "agent-yield handoff" in message


def test_the_steep_band_stops_a_session_that_never_doubled(tmp_path):
    stats = _steep(tmp_path)
    assert stats.growth is not None and stats.growth < 2.0
    message = boundary_message(stats, tmp_path / "none.md")
    assert "expensive band" in message


def test_a_handoff_written_this_session_clears_the_boundary(tmp_path):
    stats = _grown(tmp_path)
    handoff = _touch_handoff(tmp_path, STARTED + dt.timedelta(minutes=5))
    assert handoff_is_current(handoff, stats)
    assert boundary_message(stats, handoff) is None


def test_a_handoff_from_a_previous_session_does_not_clear_it(tmp_path):
    stats = _grown(tmp_path)
    stale = _touch_handoff(tmp_path, STARTED - dt.timedelta(hours=3))
    assert not handoff_is_current(stale, stats)
    assert boundary_message(stats, stale) is not None


def test_advising_is_the_default_and_never_returns_2(tmp_path):
    code, message = decide({}, stats=_grown(tmp_path),
                           handoff_path=tmp_path / "none.md")
    assert code == 0
    assert message is not None


def test_enforce_returns_2_and_only_when_asked(tmp_path):
    code, _ = decide({}, enforce=True, stats=_grown(tmp_path),
                     handoff_path=tmp_path / "none.md")
    assert code == 2


def test_the_named_override_silences_it(tmp_path, monkeypatch):
    monkeypatch.setenv(OVERRIDE_ENV, "1")
    code, message = decide({}, enforce=True, stats=_grown(tmp_path),
                           handoff_path=tmp_path / "none.md")
    assert (code, message) == (0, None)


def test_junk_on_stdin_exits_0(tmp_path):
    for junk in ("", "not json", "[]", "null"):
        assert main(["--enforce"], stdin=io.StringIO(junk)) == 0


def test_an_unreadable_session_exits_0_rather_than_guessing(tmp_path, monkeypatch):
    monkeypatch.setattr(boundary, "find_session", lambda *a, **k: None)
    assert main(["--enforce"], stdin=io.StringIO(json.dumps(
        {"hook_event_name": "UserPromptSubmit", "prompt": "hi"}))) == 0


def test_a_raising_measurement_never_blocks_the_operator(tmp_path, monkeypatch):
    def explode(*args, **kwargs):
        raise RuntimeError("measurement is broken")
    monkeypatch.setattr(boundary, "_stats_for", explode)
    payload = json.dumps({"hook_event_name": "UserPromptSubmit"})
    assert main(["--enforce"], stdin=io.StringIO(payload)) == 0


def test_enforce_writes_the_message_to_stderr(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(boundary, "_stats_for", lambda payload: _grown(tmp_path))
    monkeypatch.setattr(boundary, "DEFAULT_HANDOFF_PATH", tmp_path / "none.md")
    payload = json.dumps({"hook_event_name": "UserPromptSubmit"})
    assert main(["--enforce"], stdin=io.StringIO(payload)) == 2
    assert "agent-yield" in capsys.readouterr().err


def test_advisory_output_is_hook_json_on_stdout(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(boundary, "_stats_for", lambda payload: _grown(tmp_path))
    monkeypatch.setattr(boundary, "DEFAULT_HANDOFF_PATH", tmp_path / "none.md")
    payload = json.dumps({"hook_event_name": "UserPromptSubmit"})
    assert main([], stdin=io.StringIO(payload)) == 0
    out = capsys.readouterr().out
    emitted = json.loads(out)
    assert emitted["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit"
    assert "agent-yield" in emitted["hookSpecificOutput"]["additionalContext"]


def test_probe_records_what_arrived_and_never_blocks(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(boundary, "_stats_for", lambda payload: _grown(tmp_path))
    monkeypatch.setattr(boundary, "DEFAULT_HANDOFF_PATH", tmp_path / "none.md")
    monkeypatch.setattr(boundary, "PROBE_PATH", tmp_path / "probe.jsonl")
    payload = json.dumps({"hook_event_name": "UserPromptSubmit",
                          "session_id": "s", "prompt": "secret text"})
    assert main(["--probe", "--enforce"], stdin=io.StringIO(payload)) == 0
    recorded = json.loads((tmp_path / "probe.jsonl").read_text(encoding="utf-8"))
    assert recorded["hook_event_name"] == "UserPromptSubmit"
    assert recorded["would_stop"] is True
    assert recorded["has_prompt"] is True
    # The prompt itself is never recorded -- the probe measures the mechanism.
    assert "prompt" not in recorded["keys"]
    assert "secret text" not in json.dumps(recorded)


def test_tokens_never_money(tmp_path):
    assert "$" not in boundary_message(_grown(tmp_path), tmp_path / "none.md")
