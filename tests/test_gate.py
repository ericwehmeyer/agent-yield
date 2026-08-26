import io
import json

from agent_yield.gate import (
    OVERRIDE_ENV,
    DispatchRequest,
    _decide,
    brief_message,
    gate_message,
    main,
    missing_markers,
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

# A prompt carrying all four of §12's brief parts (a) and (d)'s two markers,
# plus the output-path marker.
FULL_BRIEF_PROMPT = (
    "Read gate.py lines 22-58 via sed -n. Do not explore; if you need a file "
    "not listed, say so and stop. Write your findings to /tmp/out.md. "
    "Return only the file:line list and one verdict line, nothing else."
)


def test_reads_the_verified_dispatch_fields():
    assert read_dispatch(DISPATCH) == DispatchRequest(
        subagent_type="general-purpose",
        model="haiku",
        description="No-op probe agent",
        prompt="Do nothing.",
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


# --- §12 brief-quality inspection -----------------------------------------


def test_full_brief_is_missing_nothing():
    request = DispatchRequest(subagent_type="general-purpose", prompt=FULL_BRIEF_PROMPT)
    assert missing_markers(request) == ()
    assert brief_message(missing_markers(request)) is None


def test_missing_line_ranges_is_named():
    prompt = "Write your findings to /tmp/out.md. Return only the verdict, nothing else."
    request = DispatchRequest(subagent_type="general-purpose", prompt=prompt)
    assert missing_markers(request) == ("line ranges",)


def test_missing_output_path_is_named():
    prompt = (
        "Read gate.py lines 22-58 via sed -n. Do not explore; if you need a "
        "file not listed, say so and stop. Return only the verdict, nothing else."
    )
    request = DispatchRequest(subagent_type="general-purpose", prompt=prompt)
    assert missing_markers(request) == ("output path",)


def test_missing_return_contract_is_named():
    prompt = (
        "Read gate.py lines 22-58 via sed -n. Do not explore; if you need a "
        "file not listed, say so and stop. Write your findings to /tmp/out.md."
    )
    request = DispatchRequest(subagent_type="general-purpose", prompt=prompt)
    assert missing_markers(request) == ("return contract",)


def test_brief_message_names_the_remedy_without_money_or_a_stop_order():
    message = brief_message(("line ranges", "output path"))
    assert "line ranges" in message
    assert "output path" in message
    assert "$" not in message
    assert "stop dispatching" not in message.lower()


def test_explore_and_plan_subagents_are_exempt_even_unbriefed(monkeypatch):
    monkeypatch.delenv(OVERRIDE_ENV, raising=False)
    for subagent_type in ("Explore", "Plan", "explore", "plan"):
        payload = {
            **DISPATCH,
            "tool_input": {**DISPATCH["tool_input"], "subagent_type": subagent_type, "prompt": ""},
            "_day_total": 0,
        }
        assert _decide(payload) == (0, None)


def test_missing_prompt_key_is_treated_as_empty_and_does_not_crash():
    payload = {"tool_name": "Agent", "tool_input": {"subagent_type": "general-purpose"}, "_day_total": 0}
    code, message = _decide(payload)
    assert code == 0
    assert "line ranges" in message


def test_brief_warning_is_exit_0_by_default():
    payload = {**DISPATCH, "_day_total": 0}
    assert main(stdin=io.StringIO(json.dumps(payload))) == 0


def test_brief_warning_is_exit_2_only_under_enforce_brief(monkeypatch):
    monkeypatch.delenv(OVERRIDE_ENV, raising=False)
    payload = {**DISPATCH, "_day_total": 0}
    assert main(["--enforce-brief"], stdin=io.StringIO(json.dumps(payload))) == 2


def test_override_env_clears_the_enforce_brief_refusal(monkeypatch):
    monkeypatch.setenv(OVERRIDE_ENV, "1")
    payload = {**DISPATCH, "_day_total": 0}
    assert main(["--enforce-brief"], stdin=io.StringIO(json.dumps(payload))) == 0


def test_day_ceiling_and_brief_messages_both_reach_the_caller():
    payload = {**DISPATCH, "_day_total": DAILY_WARN}
    code, message = _decide(payload)
    assert code == 0
    assert "WARN" in message
    assert "line ranges" in message


def test_garbage_input_still_exits_0_even_with_enforce_brief():
    assert main(["--enforce-brief"], stdin=io.StringIO("not json")) == 0
