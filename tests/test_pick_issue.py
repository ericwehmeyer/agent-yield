"""The unattended picker refuses by default, and the refusal is the design.

`docs/agents/triage-labels.md` records that `ready-for-agent` has no label in
this tracker, so a fully specified issue reads exactly like one nobody has
looked at. The picker therefore has no signal for readiness and must not
invent one: every proxy available here -- body length, a "Now what" heading,
an issue citing file:line -- measures how well an issue is WRITTEN, and the
best-written issues in this tracker are the research questions.

So these tests are mostly about what it declines to pick. The eligibility
predicate is a pure function over the JSON `gh` returns, which is why it can
be tested at all without a tracker.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "pick-issue.py"


def _load():
    spec = importlib.util.spec_from_file_location("pick_issue", _SCRIPT)
    assert spec and spec.loader, f"cannot load {_SCRIPT}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def picker():
    return _load()


def issue(number: int, *labels: str, assignees=(), blocked=()) -> dict:
    return {
        "number": number,
        "title": f"issue {number}",
        "labels": [{"name": name} for name in labels],
        "assignees": list(assignees),
        "blockedBy": {"nodes": [{"number": n, "closed": False} for n in blocked],
                      "totalCount": len(blocked)},
    }


def test_an_unmarked_issue_is_never_picked(picker):
    """The whole design in one assertion.

    `task` and `bug` say what an issue IS. Neither says a human decided an
    agent may take it, and 45 of the 62 open issues carry one of them.
    """
    assert picker.ineligible(issue(1), on_windows=False)
    assert picker.ineligible(issue(2, "task"), on_windows=False)
    assert picker.ineligible(issue(3, "bug", "priority:high"), on_windows=False)


def test_a_marked_issue_is_picked(picker):
    assert picker.ineligible(issue(4, "ready-for-agent"), on_windows=False) is None
    # Honoured because issue-tracker.md documents it as the AFK ticket type in
    # as many words -- the one place this tracker already says an agent may
    # take something.
    assert picker.ineligible(issue(5, "wayfinder:research"), on_windows=False) is None


def test_the_human_in_the_loop_types_are_refused_even_when_marked(picker):
    # A grilling ticket is a decision reached by conversation. Marking one
    # ready would be a mistake, and the refusal outranks the marker so that
    # one mislabel cannot run a five-hour window into a conversation.
    for label in ("wayfinder:grilling", "wayfinder:prototype", "wayfinder:map"):
        assert picker.ineligible(issue(6, label, "ready-for-agent"), on_windows=False)


def test_the_other_machine_s_claim_is_honoured_and_is_one_directional(picker):
    """`windows` means claimed; there is no reciprocal label.

    The Mac cannot claim anything, so two unattended sessions would both see
    every unclaimed issue. That gap is real and is written down rather than
    guessed at -- it needs a label before both boxes ever run this at once.
    """
    claimed = issue(7, "windows", "ready-for-agent")
    assert picker.ineligible(claimed, on_windows=False) == "claimed by the other machine"
    assert picker.ineligible(claimed, on_windows=True) is None


def test_blocked_and_assigned_and_unmet_dependencies_are_refused(picker):
    assert picker.ineligible(issue(8, "blocked", "ready-for-agent"), on_windows=False)
    assert picker.ineligible(
        issue(9, "ready-for-agent", assignees=[{"login": "someone"}]), on_windows=False
    ) == "already assigned"
    assert "blocked by #12" in picker.ineligible(
        issue(10, "ready-for-agent", blocked=(12,)), on_windows=False
    )


def test_a_closed_blocker_does_not_block(picker):
    # `blockedBy` is a connection, not a list, and a bare truth test on it is
    # true even at totalCount 0. That bug refused everything on first run.
    ready = issue(11, "ready-for-agent")
    ready["blockedBy"] = {"nodes": [{"number": 3, "closed": True}], "totalCount": 1}
    assert picker.ineligible(ready, on_windows=False) is None
    empty = issue(12, "ready-for-agent")
    empty["blockedBy"] = {"nodes": [], "totalCount": 0}
    assert picker.ineligible(empty, on_windows=False) is None


def test_priority_high_is_ranked_first_then_the_oldest(picker):
    # Stated so it can be argued with, rather than emerging from list order.
    ordered = sorted(
        [issue(50, "ready-for-agent"), issue(9, "ready-for-agent"),
         issue(80, "ready-for-agent", "priority:high")],
        key=picker.rank,
    )
    assert [i["number"] for i in ordered] == [80, 9, 50]


def test_the_allowance_stop_reads_129_s_bands_not_a_second_threshold(picker, tmp_path):
    """Exit 2's condition is the one the dispatch gate already refuses on."""
    log = tmp_path / "allowance.jsonl"
    import datetime as dt
    import json
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    log.write_text(json.dumps({"timestamp": now, "five_hour": 95, "seven_day": 40}) + "\n")
    said = picker.allowance_stop(log)
    assert said is not None and "five-hour window is at 95%" in said


def test_a_stale_reading_does_not_stop_the_picker(picker, tmp_path):
    # Same rule as the gate: a log that stopped being written looks exactly
    # like a window that stopped moving, so a fossil decides nothing.
    log = tmp_path / "allowance.jsonl"
    import json
    log.write_text(json.dumps(
        {"timestamp": "2026-08-01T00:00:00+00:00", "five_hour": 99, "seven_day": 99}
    ) + "\n")
    assert picker.allowance_stop(log) is None


def test_an_absent_allowance_log_does_not_stop_the_picker(picker, tmp_path):
    assert picker.allowance_stop(tmp_path / "nothing.jsonl") is None
