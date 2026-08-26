"""Tests for the resume hook: load the handoff into a fresh session, once."""

from __future__ import annotations

import io
import json
import os
from pathlib import Path

from agent_yield import handoff as handoff_module
from agent_yield.handoff import NOTES_HEADING, write
from agent_yield.resume import main


def _out(tmp_path: Path) -> Path:
    return tmp_path / "handoff.md"


def _payload(reason) -> str:
    body = {
        "session_id": "s1",
        "transcript_path": "/tmp/s1.jsonl",
        "cwd": "/repo",
        "permission_mode": "default",
        "hook_event_name": "SessionStart",
    }
    if reason is not None:
        body["source"] = reason
    return json.dumps(body)


def _run(out: Path, reason) -> tuple[int, str]:
    stdin = io.StringIO(_payload(reason))
    stdout = io.StringIO()
    import contextlib

    with contextlib.redirect_stdout(stdout):
        code = main(["--out", str(out)], stdin=stdin)
    return code, stdout.getvalue()


def test_startup_injects_the_handoff(tmp_path):
    out = _out(tmp_path)
    write(out, "# Handoff\n\n## Claimed and unfinished\n\n- do the thing\n")
    code, printed = _run(out, "startup")
    assert code == 0
    payload = json.loads(printed)
    assert set(payload.keys()) == {"hookSpecificOutput"}
    inner = payload["hookSpecificOutput"]
    assert set(inner.keys()) == {"hookEventName", "additionalContext"}
    assert inner["hookEventName"] == "SessionStart"
    assert "do the thing" in inner["additionalContext"]
    assert not out.exists()  # consumed


def test_clear_injects_the_handoff(tmp_path):
    out = _out(tmp_path)
    write(out, "# Handoff\n\n## Claimed and unfinished\n\n- x\n")
    code, printed = _run(out, "clear")
    assert code == 0
    assert json.loads(printed)["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert not out.exists()


def test_the_preamble_names_the_handoff_as_written_by_an_ended_session(tmp_path):
    out = _out(tmp_path)
    write(out, "# Handoff\n\n## Claimed and unfinished\n\n- x\n")
    _, printed = _run(out, "startup")
    context = json.loads(printed)["hookSpecificOutput"]["additionalContext"]
    assert "ended" in context
    assert "Claimed and unfinished" in context


def test_resume_reason_does_not_inject_or_consume(tmp_path):
    out = _out(tmp_path)
    write(out, "# Handoff\n\n## Claimed and unfinished\n\n- x\n")
    code, printed = _run(out, "resume")
    assert code == 0
    assert printed == ""
    assert out.exists()


def test_compact_and_fork_do_not_inject_or_consume(tmp_path):
    for reason in ("compact", "fork"):
        out = _out(tmp_path)
        write(out, "# Handoff\n\n## Claimed and unfinished\n\n- x\n")
        code, printed = _run(out, reason)
        assert code == 0
        assert printed == ""
        assert out.exists()


def test_missing_reason_does_not_inject_or_consume(tmp_path):
    out = _out(tmp_path)
    write(out, "# Handoff\n\n## Claimed and unfinished\n\n- x\n")
    code, printed = _run(out, None)
    assert code == 0
    assert printed == ""
    assert out.exists()


def test_read_mode_prints_the_handoff_and_leaves_it_unconsumed(tmp_path):
    out = _out(tmp_path)
    write(out, "# Handoff\n\nbody\n")
    stdin = io.StringIO("")
    stdout = io.StringIO()
    import contextlib

    with contextlib.redirect_stdout(stdout):
        code = main(["--out", str(out)], stdin=stdin)
    assert code == 0
    assert stdout.getvalue() == "# Handoff\n\nbody\n"
    assert out.exists()


def test_garbage_stdin_exits_zero_and_prints_nothing(tmp_path):
    out = _out(tmp_path)
    write(out, "# Handoff\n\n## Claimed and unfinished\n\n- x\n")
    stdin = io.StringIO("{not json")
    stdout = io.StringIO()
    import contextlib

    with contextlib.redirect_stdout(stdout):
        code = main(["--out", str(out)], stdin=stdin)
    assert code == 0
    assert stdout.getvalue() == ""
    assert out.exists()


def test_absent_handoff_exits_zero_and_prints_nothing(tmp_path):
    out = _out(tmp_path)
    code, printed = _run(out, "startup")
    assert code == 0
    assert printed == ""


def test_unreadable_handoff_exits_zero_and_prints_nothing(tmp_path):
    out = _out(tmp_path)
    out.mkdir()  # a directory where a file is expected -> unreadable
    code, printed = _run(out, "startup")
    assert code == 0
    assert printed == ""


def test_the_real_harness_payload_key_is_source(tmp_path):
    """Regression: the reason key is `source`, and nothing else.

    This hook shipped reading `session_start_reason` and silently never
    fired -- the key is absent from a real payload, so every session start
    fell through the fail-open path and the operator arrived blank. The old
    unit tests passed because the fixture invented the same key the code
    read. So this test does NOT use `_payload`: the body below is the shape
    the 2.1.246 binary constructs, verbatim, and it must inject.
    """
    out = _out(tmp_path)
    write(out, "# Handoff\n\n## Claimed and unfinished\n\n- do the thing\n")
    real = json.dumps({
        "session_id": "ee20b0fe-d582-4062-bdf2-df13cda1be5e",
        "transcript_path": "/tmp/ee20b0fe.jsonl",
        "cwd": "/repo",
        "hook_event_name": "SessionStart",
        "source": "startup",
    })
    stdout = io.StringIO()
    import contextlib

    with contextlib.redirect_stdout(stdout):
        code = main(["--out", str(out)], stdin=io.StringIO(real))
    assert code == 0
    payload = json.loads(stdout.getvalue())
    assert payload["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert "do the thing" in payload["hookSpecificOutput"]["additionalContext"]


def test_the_abandoned_key_no_longer_injects(tmp_path):
    """The guessed key must not work, or the bug can come back unnoticed."""
    out = _out(tmp_path)
    write(out, "# Handoff\n\n## Claimed and unfinished\n\n- do the thing\n")
    stale = json.dumps({
        "hook_event_name": "SessionStart",
        "session_start_reason": "startup",
    })
    stdout = io.StringIO()
    import contextlib

    with contextlib.redirect_stdout(stdout):
        code = main(["--out", str(out)], stdin=io.StringIO(stale))
    assert code == 0
    assert stdout.getvalue() == ""
    assert out.exists(), "a non-injecting start must not consume the handoff"


# --- #29: the four silences are not the same event ----------------------


def _classify(out: Path, payload, now=None):
    from agent_yield.resume import classify

    return classify(payload, out, now=now)


def _handoff(out: Path) -> None:
    write(out, "# Handoff\n\n## Claimed and unfinished\n\n- do the thing\n")


def test_each_silence_is_named_separately(tmp_path):
    """Before #29 these were one silence, which is how the bug survived."""
    out = _out(tmp_path)

    # nothing on disk
    assert _classify(out, {"source": "startup"})[0] == "no_handoff"

    # a reason that carries its own context
    _handoff(out)
    assert _classify(out, {"source": "resume"})[0] == "reason_not_injecting"
    assert out.exists(), "a declined start must not consume the handoff"

    # not a JSON object at all
    assert _classify(out, None)[0] == "unparseable_payload"
    assert out.exists()

    # the ordinary success
    decision, message, age = _classify(out, {"source": "startup"})
    assert decision == "injected"
    assert "do the thing" in message
    assert age is not None
    assert not out.exists(), "injection must consume"


def test_stale_is_distinguishable_from_absent(tmp_path):
    """Both used to return None. Only one of them is a bug worth chasing."""
    import datetime as dt

    out = _out(tmp_path)
    _handoff(out)
    later = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=30)

    decision, message, age = _classify(out, {"source": "startup"}, now=later)
    assert decision == "stale"
    assert message is None
    assert age > 24
    assert out.exists(), "a stale handoff stays readable by hand"


def test_probe_records_the_decision_but_never_a_value(tmp_path, monkeypatch):
    """The probe writes keys. `session_title` is a value; so is the handoff."""
    import agent_yield.resume as resume_mod

    probe = tmp_path / "resume-probe.jsonl"
    monkeypatch.setattr(resume_mod, "PROBE_PATH", probe)

    out = _out(tmp_path)
    write(out, "# Handoff\n\n## Claimed and unfinished\n\n- SECRETNOTE\n")
    payload = json.dumps({
        "session_id": "s1",
        "hook_event_name": "SessionStart",
        "source": "startup",
        "session_title": "SECRETTITLE",
        "model": "claude-opus-5",
    })

    stdout = io.StringIO()
    import contextlib

    with contextlib.redirect_stdout(stdout):
        code = main(["--out", str(out), "--probe"], stdin=io.StringIO(payload))
    assert code == 0

    raw = probe.read_text(encoding="utf-8")
    entry = json.loads(raw.strip())
    assert entry["decision"] == "injected"
    assert entry["injected"] is True
    assert entry["injected_chars"] > 0
    assert entry["has_reason_key"] is True
    assert "session_title" in entry["keys"]
    # keys, never values
    assert "SECRETTITLE" not in raw
    assert "SECRETNOTE" not in raw


def test_probe_records_a_decline_so_it_can_be_seen(tmp_path, monkeypatch):
    """A loader that fails open must be able to say it declined, and why.

    This is the whole point of #29: the broken hook declined every real
    session start and left no trace of having done so.
    """
    import agent_yield.resume as resume_mod

    probe = tmp_path / "resume-probe.jsonl"
    monkeypatch.setattr(resume_mod, "PROBE_PATH", probe)

    out = _out(tmp_path)
    _handoff(out)
    # the exact payload that used to be silently dropped
    stale_key = json.dumps({
        "hook_event_name": "SessionStart",
        "session_start_reason": "startup",
    })

    stdout = io.StringIO()
    import contextlib

    with contextlib.redirect_stdout(stdout):
        code = main(["--out", str(out), "--probe"], stdin=io.StringIO(stale_key))
    assert code == 0
    assert stdout.getvalue() == ""

    entry = json.loads(probe.read_text(encoding="utf-8").strip())
    assert entry["decision"] == "reason_not_injecting"
    assert entry["injected"] is False
    assert entry["has_reason_key"] is False, (
        "the probe must show the reason key was absent -- that is the "
        "single fact that would have caught this in a day"
    )
    assert out.exists()


def test_hand_run_does_not_probe(tmp_path, monkeypatch):
    """An operator reading is not a session start; it must not log one."""
    import agent_yield.resume as resume_mod

    probe = tmp_path / "resume-probe.jsonl"
    monkeypatch.setattr(resume_mod, "PROBE_PATH", probe)

    out = _out(tmp_path)
    _handoff(out)
    stdout = io.StringIO()
    import contextlib

    with contextlib.redirect_stdout(stdout):
        code = main(["--out", str(out), "--probe"], stdin=io.StringIO(""))
    assert code == 0
    assert "do the thing" in stdout.getvalue()
    assert not probe.exists()
    assert out.exists(), "reading by hand must not consume"
