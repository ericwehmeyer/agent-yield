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
        body["session_start_reason"] = reason
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
