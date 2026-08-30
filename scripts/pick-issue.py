#!/usr/bin/env python
"""Pick the one issue an unattended session may work next, or refuse to pick.

    python scripts/pick-issue.py              # choose, or say why not
    python scripts/pick-issue.py --explain    # every open issue and what it failed

Exit 0 and print the issue number and a one-line reason. Exit 1 when nothing
is eligible. Exit 2 when the plan allowance says stop.

WHY THE PREDICATE IS AN OPT-IN AND NOT A HEURISTIC. A fully specified issue
reads exactly like one nobody has looked at, so readiness has to be asserted
and cannot be inferred. When this script was written, 0 of 62 open issues
carried any marker a human had applied to mean "an agent may take this", while
34 carried `task` and 11 carried `bug` -- which say what an issue IS and
nothing about whether it is ready.

That is not a gap to paper over with a proxy. Every proxy available here --
body length, a "Now what" heading, an issue that cites file:line -- measures
how well the issue is WRITTEN, and the best-written issues in this tracker are
the research questions. A picker on that proxy runs a five-hour window into a
grilling ticket at 3am and produces prose nobody asked for. So:

    exclusion is well served by the labels that exist; inclusion is not.

`ready-for-agent` was created on 2026-08-30 to close that gap, carrying the
label description "root cause is stated, the fix has a named file, and no
operator judgment remains". Those are the three conditions, and they are strict
on purpose: an issue failing any of them is one this refuses rather than
guesses at. The rules that keep the label honest, which nothing enforces:

  - It is applied at triage by whoever writes the issue down, not in a sweep.
    A label applied in bulk records the sweep, not the issue.
  - It is REMOVED when a blocker appears. Nothing enforces that, so the label
    is a claim about the past and its age is the honest measure of its decay.
    `--max-label-age-days` exists for that and defaults to off, because there
    is no measurement here to set it from.
  - It never means "important". `priority:high` already exists and means
    something else; one label carrying both is how readiness stops being
    checkable.

`wayfinder:research` is honoured alongside it, because `docs/agents/issue-tracker.md`
documents it as the AFK ticket type in as many words. It says the same thing
about a shape of work rather than about a state.

`blocked`, `wontfix`, `question`, `wayfinder:grilling` (documented HITL) and a
machine claim label are all real, checkable statements a human made, and they
outrank the marker: one mislabel should not be able to spend a window.
"""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agent_yield.allowance import (  # noqa: E402
    SNAPSHOT_PATH,
    STALE_AFTER_MINUTES,
    latest_readings,
    load,
)
from agent_yield.state import anchored  # noqa: E402
from agent_yield.thresholds import allowance_advice, allowance_says_stop  # noqa: E402

# A human said "an agent may take this". Nothing infers membership here.
READY_LABELS = ("ready-for-agent", "wayfinder:research")

# A human said "not this, or not yet, or not by a machine".
REFUSED_LABELS = {
    "blocked": "has unmet dependencies",
    "wontfix": "will not be actioned",
    "question": "waiting on information",
    "duplicate": "duplicate",
    "invalid": "invalid",
    "wayfinder:map": "a map, not a ticket",
    "wayfinder:grilling": "HITL: a decision reached by conversation",
    "wayfinder:prototype": "HITL: an artifact for a human to react to",
}

# One label per box, each meaning "this machine has claimed it". The pair is
# symmetric as of 2026-08-30: before `macos` existed the Mac could not claim
# anything, so two unattended sessions would both have seen every unclaimed
# issue and raced for it.
#
# Keyed by `platform.system()`. A machine that is neither -- Linux, or a
# platform.system() this does not know -- gets None and is refused every
# claimed issue, which is the safe direction: an unrecognised box takes only
# what nobody has claimed.
MACHINE_LABELS = {"Windows": "windows", "Darwin": "macos"}
CLAIM_LABELS = frozenset(MACHINE_LABELS.values())


def this_machine() -> str | None:
    """The claim label belonging to the box this is running on, or None."""
    return MACHINE_LABELS.get(platform.system())


def _labels(issue: dict) -> set[str]:
    return {label.get("name", "") for label in issue.get("labels") or []}


def ineligible(issue: dict, machine: str | None) -> str | None:
    """Why this issue may not be worked unattended, or None if it may.

    `machine` is this box's own claim label, from `this_machine()`.

    Order matters only for the message: the first true reason is the one
    reported, and the cheapest, most certain statements come first.
    """
    labels = _labels(issue)
    for label, reason in REFUSED_LABELS.items():
        if label in labels:
            return reason
    if issue.get("assignees"):
        return "already assigned"
    # `gh` returns a connection, not a list: {"nodes": [...], "totalCount": n}.
    # A bare truth test on it is true even when totalCount is 0.
    blocked_by = issue.get("blockedBy") or {}
    nodes = blocked_by.get("nodes") if isinstance(blocked_by, dict) else blocked_by
    open_blockers = [b for b in (nodes or []) if not b.get("closed")]
    if open_blockers:
        return "blocked by " + ", ".join(f"#{b['number']}" for b in open_blockers)
    claimed = labels & CLAIM_LABELS
    if claimed and machine not in claimed:
        return "claimed by " + ", ".join(sorted(claimed))
    if not labels & set(READY_LABELS):
        return "no human has marked it ready for an agent"
    return None


def rank(issue: dict) -> tuple[int, int]:
    """`priority:high` first, then oldest. Stated, so it can be argued with."""
    return (0 if "priority:high" in _labels(issue) else 1, issue["number"])


def open_issues() -> list[dict]:
    out = subprocess.run(
        ["gh", "issue", "list", "--state", "open", "--limit", "200",
         "--json", "number,title,labels,assignees,blockedBy"],
        capture_output=True, text=True, check=True,
    )
    return json.loads(out.stdout)


def allowance_stop(path: Path | None = None) -> str | None:
    """The allowance band's own words when it says stop, else None.

    Reads #129's bands rather than inventing a second threshold, and inherits
    their staleness rule: a reading older than STALE_AFTER_MINUTES decides
    nothing, because a log that stops being written looks exactly like a
    window that stopped moving.
    """
    readings = latest_readings(load(anchored(path or SNAPSHOT_PATH)))
    for window in ("five_hour", "seven_day"):
        reading = readings.get(window)
        if reading is None or not reading.is_fresh(STALE_AFTER_MINUTES):
            continue
        if allowance_says_stop(window, reading.used_percentage, reading.minutes_to_reset):
            return allowance_advice(window, reading.used_percentage, reading.minutes_to_reset)
    return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--explain", action="store_true",
                    help="print every open issue and the reason it was passed over")
    args = ap.parse_args(argv)

    stop = allowance_stop()
    if stop:
        print(f"STOP: {stop}")
        return 2

    try:
        issues = open_issues()
    except Exception as exc:
        # Exit 1, not a third code. Every reason not to work is the same
        # action at 3am, and the first line says which reason it was.
        print(f"nothing picked: the tracker could not be read ({exc})")
        return 1

    machine = this_machine()
    eligible, passed_over = [], []
    for issue in issues:
        reason = ineligible(issue, machine)
        (passed_over if reason else eligible).append((issue, reason))

    if args.explain:
        print(f"{len(issues)} open, {len(eligible)} eligible\n")
        for issue, reason in sorted(passed_over, key=lambda pair: pair[0]["number"]):
            print(f"  #{issue['number']:<4} {reason}")
        print()

    if not eligible:
        print(f"nothing picked: 0 of {len(issues)} open issues carry "
              f"{' or '.join(READY_LABELS)}.")
        print("A picker that refuses is cheap. Label an issue, or read this "
              "script's docstring\nfor the three conditions "
              "`ready-for-agent` asserts.")
        return 1

    chosen = sorted((issue for issue, _ in eligible), key=rank)[0]
    marker = ", ".join(sorted(_labels(chosen) & set(READY_LABELS)))
    first = "priority:high, " if "priority:high" in _labels(chosen) else ""
    print(f"#{chosen['number']} {chosen['title']}")
    print(f"  {first}marked {marker}, unassigned, no open blockers "
          f"({len(eligible)} eligible of {len(issues)} open)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
