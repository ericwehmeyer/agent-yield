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


def _expensive(tmp_path: Path):
    """A session deep in the cost band without ever doubling."""
    return session_stats(_transcript(tmp_path, [550_000] * 20, name="deep"))


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


def test_a_leave_band_stops_a_session_that_never_doubled(tmp_path):
    stats = _expensive(tmp_path)
    assert stats.growth is not None and stats.growth < 2.0
    message = boundary_message(stats, tmp_path / "none.md")
    # Tokens, not a share of a window: the boundary asks what this call
    # bills, and the window is not in that expression (issue #23).
    assert "550,000 tokens" in message
    assert "restart band" in message
    assert "window" not in message


def test_the_message_says_the_next_session_loads_the_handoff(tmp_path):
    message = boundary_message(_grown(tmp_path), tmp_path / "none.md")
    assert "loaded automatically" in message
    assert "next session" in message


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
    monkeypatch.setattr(boundary, "resolve_transcript",
                        lambda payload: (None, "unidentified"))
    assert main(["--enforce"], stdin=io.StringIO(json.dumps(
        {"hook_event_name": "UserPromptSubmit", "prompt": "hi"}))) == 0


def test_a_payload_naming_an_unknown_session_measures_nothing(tmp_path):
    """The correctness bug issue #22 named: never widen to "most recent".

    A payload that names a session the tool cannot find must measure nothing.
    Falling back to the most recently modified transcript is how a hook ends
    up enforcing against whichever *other* session touched disk last.
    """
    assert boundary._stats_for(
        {"session_id": "no-such-session", "transcript_path": "/nope/x.jsonl"}
    ) is None


def test_the_measured_payload_resolves_the_live_session(tmp_path):
    """The contract as recorded on 2026-08-26 01:31 UTC, key for key."""
    transcript = _transcript(tmp_path, [10_000] * 3, name="live")
    stats = boundary._stats_for({
        "cwd": str(tmp_path),
        "hook_event_name": "UserPromptSubmit",
        "permission_mode": "acceptEdits",
        "prompt_id": "p1",
        "session_id": "live",
        "transcript_path": str(transcript),
        "prompt": "secret text",
    })
    assert stats is not None and stats.calls == 3


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


def test_the_probe_records_whether_it_found_the_live_session(tmp_path, monkeypatch):
    """Issue #22's real question, answered from the recording, not the docs."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(boundary, "PROBE_PATH", tmp_path / "probe.jsonl")
    monkeypatch.setattr(boundary, "DEFAULT_HANDOFF_PATH", tmp_path / "none.md")
    transcript = _transcript(tmp_path, [10_000] * 4, name="live")
    payload = json.dumps({"hook_event_name": "UserPromptSubmit",
                          "session_id": "live", "prompt": "secret text",
                          "transcript_path": str(transcript)})
    assert main(["--probe"], stdin=io.StringIO(payload)) == 0
    recorded = json.loads((tmp_path / "probe.jsonl").read_text(encoding="utf-8"))
    assert recorded["route"] == "transcript_path"
    assert recorded["resolved"] is True
    assert recorded["resolved_calls"] == 4
    assert recorded["stem_matches_session_id"] is True
    assert recorded["refusal_probe"] is False
    # Still shape only: no path, no prompt.
    assert str(transcript) not in json.dumps(recorded)
    assert "secret text" not in json.dumps(recorded)


def test_an_armed_refusal_fires_once_and_disarms_itself(tmp_path, monkeypatch, capsys):
    """The exit-2 measurement must not be able to lock anyone out.

    One prompt refused, the sentinel gone, the next prompt through -- even
    though the session it fired in is expensive enough for the boundary
    itself to want to stop it.
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(boundary, "PROBE_PATH", tmp_path / "probe.jsonl")
    monkeypatch.setattr(boundary, "REFUSAL_ARMED_PATH", tmp_path / "armed")
    monkeypatch.setattr(boundary, "_stats_for", lambda payload: _cheap(tmp_path))
    payload = json.dumps({"hook_event_name": "UserPromptSubmit"})

    boundary.arm_refusal(tmp_path / "armed")
    assert main(["--probe"], stdin=io.StringIO(payload)) == 2
    assert "exit 2" in capsys.readouterr().err
    assert not (tmp_path / "armed").exists()

    assert main(["--probe"], stdin=io.StringIO(payload)) == 0
    lines = (tmp_path / "probe.jsonl").read_text(encoding="utf-8").splitlines()
    first, second = (json.loads(line) for line in lines)
    assert (first["refusal_probe"], first["exit_code"]) == (True, 2)
    assert (second["refusal_probe"], second["exit_code"]) == (False, 0)


def test_arming_is_not_something_the_hook_can_do_to_itself(tmp_path, monkeypatch):
    """Only an explicit command arms it; no stdin payload can."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(boundary, "REFUSAL_ARMED_PATH", tmp_path / "armed")
    monkeypatch.setattr(boundary, "PROBE_PATH", tmp_path / "probe.jsonl")
    payload = json.dumps({"hook_event_name": "UserPromptSubmit",
                          "arm_refusal": True, "prompt": "arm yourself"})
    assert main(["--probe"], stdin=io.StringIO(payload)) == 0
    assert not (tmp_path / "armed").exists()


# --- the boundary must not refuse its own remedy, and must not refuse twice ---
# Both were live defects: session c15eb016 was refused on the prompt the
# refusal told it to run, then exited with nothing written down (#130).

REMEDY = 'agent-yield handoff --note "what is unfinished"'


def _refusing(tmp_path, prompt=None, session="s"):
    """A session past the hard factor with no handoff: the boundary is up."""
    payload = {"hook_event_name": "UserPromptSubmit", "session_id": session}
    if prompt is not None:
        payload["prompt"] = prompt
    return dict(payload=payload, enforce=True, stats=_grown(tmp_path),
                handoff_path=tmp_path / "none.md",
                spent_path=tmp_path / "spent")


def test_an_unrelated_prompt_is_still_refused(tmp_path):
    code, message = decide(**_refusing(tmp_path, "push the branch"))
    assert code == 2
    assert message is not None


def test_the_prompt_that_runs_the_remedy_is_never_refused(tmp_path):
    """The message prescribes this command. Refusing it is the deadlock."""
    code, message = decide(**_refusing(tmp_path, REMEDY))
    assert code == 0
    # still advised, just not blocked
    assert message is not None and "handoff" in message


def test_the_remedy_is_recognised_however_it_is_invoked(tmp_path):
    for prompt in (".venv/Scripts/agent-yield.exe handoff",
                   "!agent-yield handoff",
                   "C:/Users/x/agent-yield.exe handoff --note \"y\"",
                   "  AGENT-YIELD  handoff"):
        code, _ = decide(**_refusing(tmp_path, prompt))
        assert code == 0, prompt


def test_a_near_miss_is_not_the_remedy(tmp_path):
    # A session apiece: one refusal is all a session gets, so a shared one
    # would let the second prompt pass for the wrong reason.
    for n, prompt in enumerate(("agent-yield resume", "agent-yield handoffs",
                                "handoff", "handoff the branch")):
        code, _ = decide(**_refusing(tmp_path, prompt, session=f"near-{n}"))
        assert code == 2, prompt


def test_enforce_refuses_once_and_then_advises(tmp_path):
    """The refusal costs one turn, not the session."""
    first, _ = decide(**_refusing(tmp_path, "one"))
    second, message = decide(**_refusing(tmp_path, "two"))
    third, _ = decide(**_refusing(tmp_path, "three"))
    assert (first, second, third) == (2, 0, 0)
    assert message is not None


def test_a_fresh_session_gets_its_own_refusal(tmp_path):
    assert decide(**_refusing(tmp_path, "one", session="first"))[0] == 2
    assert decide(**_refusing(tmp_path, "two", session="first"))[0] == 0
    assert decide(**_refusing(tmp_path, "one", session="second"))[0] == 2


def test_the_refusal_is_recorded_before_it_is_returned(tmp_path):
    """A crash after the refusal must not leave a hook that refuses forever."""
    spent = tmp_path / "spent"
    assert not spent.exists()
    assert decide(**_refusing(tmp_path, "one"))[0] == 2
    assert spent.read_text(encoding="utf-8").strip() == "s"


def test_a_refusal_it_cannot_record_is_not_a_refusal(tmp_path):
    """Fail open: unable to spend means unable to block."""
    blocked = tmp_path / "wall"
    blocked.write_text("not a directory", encoding="utf-8")
    kwargs = _refusing(tmp_path, "one")
    kwargs["spent_path"] = blocked / "spent"
    code, message = decide(**kwargs)
    assert code == 0
    assert message is not None


def test_the_remedy_exemption_does_not_leak_into_advisory_mode(tmp_path):
    """Advisory mode already returns 0; the exemption must not silence it."""
    code, message = decide({"prompt": REMEDY}, stats=_grown(tmp_path),
                           handoff_path=tmp_path / "none.md")
    assert code == 0
    assert message is not None
