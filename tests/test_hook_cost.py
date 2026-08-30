"""`scripts/hook-cost.py`: the part that must not be wrong is the skip list.

Timing a hook is only useful if doing it is free of consequence, and one of
this box's hooks appends a row derived from its payload to a real log. The
first run of the script wrote 26 invented rows into
`.agent-yield/resume-probe.jsonl` before anyone looked -- the same defect
CLAUDE.md records for `statusline`, one command over. So the guard is what is
tested here, and the timing is not: a wall-clock measurement has no assertion
that would not be flaky.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "hook-cost.py"


def _load():
    spec = importlib.util.spec_from_file_location("hook_cost", _SCRIPT)
    assert spec and spec.loader, f"cannot load {_SCRIPT}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def meter():
    return _load()


def test_a_probe_hook_is_named_as_unsafe_to_time(meter):
    assert meter.writes_from_payload("agent-yield.exe resume --hook --probe") == "--probe"


def test_the_status_line_is_named_too(meter):
    # CLAUDE.md's own rule, and the reason this list exists at all.
    assert meter.writes_from_payload("agent-yield.exe statusline") == "statusline"


def test_no_write_clears_it(meter):
    # The escape CLAUDE.md already documents for a hand render.
    assert meter.writes_from_payload("agent-yield.exe statusline --no-write") is None


def test_the_hooks_that_only_read_are_not_skipped(meter):
    for command in ("agent-yield.exe gate --enforce-brief",
                    "agent-yield.exe guard",
                    "agent-yield.exe boundary --enforce",
                    "agent-yield.exe ingest --changed-only --quiet"):
        assert meter.writes_from_payload(command) is None, command


def test_wired_hooks_reads_both_settings_files_and_survives_a_missing_one(
    meter, tmp_path, monkeypatch
):
    """`settings.local.json` is machine state; the Mac has never had one.

    A box without it must report its own hooks rather than raising, because
    the whole point of the script is that either machine can run it.
    """
    claude = tmp_path / ".claude"
    claude.mkdir()
    (claude / "settings.json").write_text(json.dumps({
        "hooks": {"PreToolUse": [
            {"matcher": "Bash", "hooks": [{"type": "command", "command": "x guard"}]}
        ]}
    }), encoding="utf-8")
    monkeypatch.setattr(meter, "ROOT", tmp_path)

    found = meter.wired_hooks()
    assert [command for _, command in found] == ["x guard"]
    assert "PreToolUse:Bash" in found[0][0]


def test_unreadable_settings_contribute_nothing_rather_than_aborting(
    meter, tmp_path, monkeypatch
):
    claude = tmp_path / ".claude"
    claude.mkdir()
    (claude / "settings.json").write_text("{ not json", encoding="utf-8")
    monkeypatch.setattr(meter, "ROOT", tmp_path)
    assert meter.wired_hooks() == []


def test_the_payload_carries_the_keys_the_harness_really_sends(meter):
    """Captured from `probe-log.jsonl`, not invented.

    A payload missing `tool_input` measures a hook parsing nothing, which is
    the wrong number and the flattering one.
    """
    for key in ("hook_event_name", "session_id", "transcript_path", "cwd",
                "tool_name", "tool_input"):
        assert key in meter.PAYLOAD, key
    assert meter.PAYLOAD["tool_input"].get("command")
