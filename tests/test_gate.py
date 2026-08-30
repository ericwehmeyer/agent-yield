import io
import json
import pathlib

import pytest

from agent_yield import gate as gate_module
from agent_yield.allowance import STALE_AFTER_MINUTES as STALE_MINUTES
from agent_yield.allowance import Reading
from agent_yield.gate import (
    ALLOWANCE_OVERRIDE_ENV,
    OVERRIDE_ENV,
    OVERRIDE_MARKER,
    DispatchRequest,
    _decide,
    allowance_message,
    brief_message,
    gate_message,
    main,
    missing_markers,
    read_current_allowance,
    read_dispatch,
)
from agent_yield.predict import project
from agent_yield.thresholds import (
    ALLOWANCE_HANDOFF,
    ALLOWANCE_STOP,
    DAILY_CEILING,
    DAILY_WARN,
)

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


def test_a_description_marker_lets_a_dispatch_through_without_the_env_var(monkeypatch):
    # #143: a subagent cannot set OVERRIDE_ENV on the hook subprocess -- that
    # process reads the parent session's environment. The escape hatch has
    # to be reachable through the dispatch's own tool_input instead.
    monkeypatch.delenv(OVERRIDE_ENV, raising=False)
    payload = {
        **DISPATCH,
        "tool_input": {
            **DISPATCH["tool_input"],
            "description": f"No-op probe agent {OVERRIDE_MARKER}",
        },
        "_day_total": DAILY_CEILING,
    }
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


def test_the_description_marker_also_clears_the_enforce_brief_refusal(monkeypatch):
    monkeypatch.delenv(OVERRIDE_ENV, raising=False)
    payload = {
        **DISPATCH,
        "tool_input": {**DISPATCH["tool_input"], "description": OVERRIDE_MARKER},
        "_day_total": 0,
    }
    assert main(["--enforce-brief"], stdin=io.StringIO(json.dumps(payload))) == 0


def test_day_ceiling_and_brief_messages_both_reach_the_caller():
    payload = {**DISPATCH, "_day_total": DAILY_WARN}
    code, message = _decide(payload)
    assert code == 0
    assert "WARN" in message
    assert "line ranges" in message


def test_garbage_input_still_exits_0_even_with_enforce_brief():
    assert main(["--enforce-brief"], stdin=io.StringIO("not json")) == 0


# --- #32: the marker detector, against dispatches nobody wrote for it -------

# Captured verbatim from the parent transcript of session
# 6e63edd1-b7b5-4b98-a90f-ce5e2d79a995 (the five issue #18 Part E dispatches,
# 2026-08-25). These are not fixtures written to match the code -- that is the
# #26 failure, one file over, and it is exactly how #32 survived: the old
# fixtures agreed with the old regexes, so the suite was green while the
# detector scored all three markers missing on all five of these.
PART_E = json.loads(
    (pathlib.Path(__file__).parent / "fixtures" / "part_e_dispatches.json").read_text()
)


@pytest.mark.parametrize("dispatch", PART_E, ids=lambda d: d["description"])
def test_captured_part_e_briefs_carry_every_marker(dispatch):
    request = DispatchRequest(
        subagent_type=dispatch["subagent_type"], prompt=dispatch["prompt"]
    )
    assert missing_markers(request) == ()


def test_there_are_five_captured_briefs_and_none_is_paraphrased():
    assert len(PART_E) == 5
    for dispatch in PART_E:
        assert dispatch["prompt"].startswith("Fixture-reality audit of ")
        assert "RETURN CONTRACT:" in dispatch["prompt"]


# The three ways #32 failed, each reduced to the smallest prompt that shows it.
# Every one of these scored a missing marker before the fix.


def test_a_prohibition_stronger_than_the_word_explore_still_counts():
    prompt = (
        "Read resume.py (lines 1-260). PROHIBITED: do not grep or search the "
        "repository, do not read any other file. Write it to /tmp/o.json. "
        "Return at most 3 lines."
    )
    request = DispatchRequest(subagent_type="general-purpose", prompt=prompt)
    assert "line ranges" not in missing_markers(request)


def test_an_output_path_on_its_own_line_still_counts():
    inline = "Read x.py lines 1-9. Do not explore. write it to: /tmp/x.json. Return only that."
    across = inline.replace("to: /tmp", "to:\n  /tmp")
    for prompt in (inline, across):
        request = DispatchRequest(subagent_type="general-purpose", prompt=prompt)
        assert "output path" not in missing_markers(request), prompt


def test_at_most_n_lines_is_the_same_contract_as_under_n_lines():
    stem = "Read x.py lines 1-9. Do not explore. Write it to /tmp/x.json. "
    for contract in (
        "Return under 3 lines.",
        "RETURN CONTRACT: your final message must be at most 3 lines.",
        "Return no more than 3 lines, nothing else.",
    ):
        request = DispatchRequest(subagent_type="general-purpose", prompt=stem + contract)
        assert "return contract" not in missing_markers(request), contract


def test_an_exploratory_dispatch_still_carries_no_markers():
    # §12: "an exploratory dispatch is supposed to have none of these markers."
    # Loosening the regexes for the property must not make everything a brief.
    prompt = (
        "Find every place the repo joins a dispatch to its child transcript. "
        "Search broadly; report what you find and where."
    )
    request = DispatchRequest(subagent_type="general-purpose", prompt=prompt)
    assert missing_markers(request) == ("line ranges", "output path", "return contract")


# --- the wiring, which is where it actually broke ---------------------------
#
# EXIT 2 IS AMBIGUOUS HERE AND THAT IS THE POINT. `cli.main` catches argparse's
# SystemExit and returns its code, which for a usage error is 2 -- exactly the
# code a deliberate refusal uses, and exactly what a PreToolUse hook reads as
# "block". So `assert main([...]) == 2` PASSES against a broken CLI and proves
# nothing. Every test below asserts on the MESSAGE, which is the only thing
# that separates "the gate refused this dispatch" from "argparse refused this
# flag".


def test_the_cli_passes_enforce_brief_through_to_the_hook(monkeypatch, capsys):
    """The exact invocation `.claude/settings.json` makes as a PreToolUse hook.

    `gate.main()` has parsed the flag since it was written and the tests above
    prove it. The `gate` SUBPARSER declared no arguments, so `parse_args`
    rejected it first, and on 2026-08-28 every Agent dispatch in this repo died
    on `unrecognized arguments: --enforce-brief`. Module-level tests could not
    see it: the whole defect was in the wiring between the two.
    """
    import sys

    from agent_yield.cli import main as cli_main

    monkeypatch.delenv(OVERRIDE_ENV, raising=False)
    payload = {**DISPATCH, "_day_total": 0}
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))

    code = cli_main(["gate", "--enforce-brief"])
    err = capsys.readouterr().err

    assert code == 2
    assert "unrecognized arguments" not in err
    assert "line ranges" in err


def test_the_cli_gate_without_the_flag_warns_rather_than_refuses(monkeypatch, capsys):
    """The default has to survive the fix: eager refusal is opt-in (#27).

    A warning goes to stdout as `additionalContext`, never to stderr, because
    stderr plus exit 2 is the only pair the harness reads as a block.
    """
    import sys

    from agent_yield.cli import main as cli_main

    payload = {**DISPATCH, "_day_total": 0}
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))

    code = cli_main(["gate"])
    captured = capsys.readouterr()

    assert code == 0
    assert "line ranges" in captured.out
    assert captured.err == ""


def test_a_mistyped_gate_flag_is_a_usage_error_and_not_a_silent_block(capsys):
    """The failure mode that hid the defect for a whole session.

    An undeclared flag returns 2 with an argparse usage message. This test does
    not assert that it returns 0 -- it cannot, given `cli.main`'s contract --
    it pins the DISTINGUISHING evidence, so a future reader knows the exit code
    alone never told them which of the two happened.
    """
    from agent_yield.cli import main as cli_main

    code = cli_main(["gate", "--no-such-flag"])
    err = capsys.readouterr().err

    assert code == 2
    assert "unrecognized arguments" in err
    assert "line ranges" not in err


# --- The plan allowance, the one band nobody can spend past (#129) ---------


@pytest.fixture(autouse=True)
def _no_allowance_log_by_default(monkeypatch, tmp_path):
    """Every other test in this file decides about a band that is not this one.

    Without this they read whatever this machine's status line last wrote into
    `.agent-yield/allowance.jsonl`, which makes the day-ceiling tests pass or
    fail on the operator's rate limit. Tests that want a reading pass one.
    """
    monkeypatch.setattr(gate_module, "ALLOWANCE_PATH", tmp_path / "absent.jsonl")


def reading(window: str, used: int, age: float = 1.0, minutes_to_reset=None) -> Reading:
    return Reading(window=window, used_percentage=used, observed="t",
                   age_minutes=age, minutes_to_reset=minutes_to_reset)


def test_no_allowance_log_means_no_opinion(tmp_path):
    assert read_current_allowance(tmp_path / "nothing.jsonl") == {}
    assert allowance_message({}) == (None, False)
    assert allowance_message(None) == (None, False)


def test_a_clear_window_says_nothing():
    assert allowance_message({"five_hour": reading("five_hour", 40)}) == (None, False)


def test_the_handoff_band_warns_without_refusing():
    payload = {**DISPATCH, "_day_total": 0}
    code, message = _decide(
        payload, readings={"seven_day": reading("seven_day", ALLOWANCE_HANDOFF)}
    )
    assert code == 0
    assert "ALLOWANCE" in message


def test_the_stop_band_refuses_the_dispatch(monkeypatch):
    """The dispatch is the call that spends the rest of the window unattended.

    Hooks do not fire inside a subagent (#34692), so this is the last point at
    which anything can be refused before the spending goes out of view.
    """
    monkeypatch.delenv(ALLOWANCE_OVERRIDE_ENV, raising=False)
    payload = {**DISPATCH, "_day_total": 0}
    code, message = _decide(
        payload, readings={"five_hour": reading("five_hour", ALLOWANCE_STOP)}
    )
    assert code == 2
    assert "ALLOWANCE" in message
    assert f"{ALLOWANCE_OVERRIDE_ENV}=1" in message


def test_the_allowance_override_is_its_own(monkeypatch):
    # Deciding the day's token ceiling is wrong is not deciding the plan's
    # rate limit is wrong. One variable for both would let the first silence
    # the second by accident.
    monkeypatch.delenv(ALLOWANCE_OVERRIDE_ENV, raising=False)
    monkeypatch.setenv(OVERRIDE_ENV, "1")
    payload = {**DISPATCH, "_day_total": DAILY_CEILING}
    code, _ = _decide(
        payload, readings={"five_hour": reading("five_hour", ALLOWANCE_STOP)}
    )
    assert code == 2

    monkeypatch.setenv(ALLOWANCE_OVERRIDE_ENV, "1")
    code, message = _decide(
        payload, readings={"five_hour": reading("five_hour", ALLOWANCE_STOP)}
    )
    assert code == 0
    assert "ALLOWANCE" in message, "an override silences the refusal, never the line"


def test_a_stale_reading_never_refuses_anything():
    """A quiet log is ambiguous, and the ambiguity has to fail open.

    Nothing was spent, or the status line is not running at all (#120 reports
    exactly that on the other machine). A fossil at 95% would refuse every
    dispatch for the rest of the session, which is how a guard gets removed.
    """
    stale = {"five_hour": reading("five_hour", 99, age=STALE_MINUTES + 1)}
    assert allowance_message(stale) == (None, False)
    code, message = _decide({**DISPATCH, "_day_total": 0}, readings=stale)
    assert code == 0
    assert message is None or "ALLOWANCE" not in message


def test_both_windows_speak_and_the_stop_one_decides():
    message, refuse = allowance_message({
        "five_hour": reading("five_hour", ALLOWANCE_HANDOFF),
        "seven_day": reading("seven_day", ALLOWANCE_STOP),
    })
    assert refuse
    assert "five-hour window" in message and "seven-day window" in message


def test_a_reset_that_arrives_first_downgrades_the_refusal():
    # resets_at reaches the hook, not just the threshold module: a five-hour
    # window returning before this pace can exhaust it is a warning, not a
    # refusal. Never observed in a payload here -- see test_allowance.py.
    message, refuse = allowance_message(
        {"five_hour": reading("five_hour", 96, minutes_to_reset=3)}
    )
    assert not refuse
    assert "ALLOWANCE" in message


def test_the_allowance_leads_the_message():
    # Three bands can speak at once. The one the operator cannot decide to
    # spend past goes first.
    payload = {**DISPATCH, "_day_total": DAILY_CEILING}
    _code, message = _decide(
        payload, readings={"seven_day": reading("seven_day", ALLOWANCE_HANDOFF)}
    )
    assert message.index("ALLOWANCE") < message.index("OVER CEILING")


def test_a_broken_allowance_log_fails_open(monkeypatch, tmp_path):
    def boom(*_args, **_kwargs):
        raise RuntimeError("the log is a directory today")

    monkeypatch.setattr("agent_yield.gate.load_allowance", boom)
    assert read_current_allowance(tmp_path / "x.jsonl") == {}
    assert main(stdin=io.StringIO(json.dumps({**DISPATCH, "_day_total": 0}))) == 0


def test_a_non_dispatch_tool_is_never_refused_on_the_allowance():
    # The gate fires on Agent and Task. A Bash call is not the thing that
    # spends the window out of view, and refusing one would block the handoff
    # this band is telling the operator to write.
    code, message = _decide(
        {"tool_name": "Bash", "tool_input": {}, "_day_total": 0},
        readings={"five_hour": reading("five_hour", 99)},
    )
    assert (code, message) == (0, None)
