import io
import json

from agent_yield.gate import (
    OVERRIDE_ENV,
    DispatchRequest,
    gate_message,
    main,
    read_dispatch,
)
from agent_yield.predict import project
from agent_yield.thresholds import DAILY_CEILING, DAILY_WARN

# The payload shape verified on 2026-08-25 by .claude/hooks/probe.py.
DISPATCH = {
    "hook_event_name": "PreToolUse",
    "tool_name": "Agent",
    "tool_input": {
        "description": "No-op probe agent",
        "model": "haiku",
        "prompt": "Do nothing.",
        "subagent_type": "general-purpose",
    },
}


def test_reads_the_verified_dispatch_fields():
    assert read_dispatch(DISPATCH) == DispatchRequest(
        subagent_type="general-purpose",
        model="haiku",
        description="No-op probe agent",
    )


def test_absent_keys_default_rather_than_raise():
    # `isolation` was absent from the observed payload simply because the
    # caller did not pass it. Absent means not passed, not unavailable.
    request = read_dispatch({"tool_name": "Agent", "tool_input": {"prompt": "x"}})
    assert request.subagent_type is None
    assert request.model is None


def test_non_dispatch_tools_are_ignored():
    assert read_dispatch({"tool_name": "Bash", "tool_input": {}}) is None


def test_silent_band_says_nothing():
    assert gate_message(1_000, project(136_449)) is None


def test_warn_band_names_the_burn_and_the_projection():
    message = gate_message(DAILY_WARN, project(136_449))
    assert "450,000,000" in message
    assert "M tokens" in message


def test_warn_band_does_not_block():
    payload = {**DISPATCH, "_day_total": DAILY_WARN}
    assert main(stdin=io.StringIO(json.dumps(payload))) == 0


def test_over_ceiling_refuses_the_dispatch(monkeypatch):
    monkeypatch.delenv(OVERRIDE_ENV, raising=False)
    payload = {**DISPATCH, "_day_total": DAILY_CEILING}
    assert main(stdin=io.StringIO(json.dumps(payload))) == 2


def test_named_override_lets_it_through(monkeypatch):
    monkeypatch.setenv(OVERRIDE_ENV, "1")
    payload = {**DISPATCH, "_day_total": DAILY_CEILING}
    assert main(stdin=io.StringIO(json.dumps(payload))) == 0


def test_malformed_payload_never_blocks():
    assert main(stdin=io.StringIO("not json")) == 0
    assert main(stdin=io.StringIO("")) == 0


def test_internal_error_fails_open(monkeypatch):
    """A crashing gate would refuse every dispatch. Only a decision may block."""
    def boom(*_args, **_kwargs):
        raise RuntimeError("ingest is a directory today")

    monkeypatch.setattr("agent_yield.gate._day_total", boom)
    assert main(stdin=io.StringIO(json.dumps(DISPATCH))) == 0
