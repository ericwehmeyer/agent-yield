"""PreToolUse hook: price a dispatch before it happens, and refuse past a ceiling.

MEASURED 2026-08-25, both halves:

  - A PreToolUse matcher fires on the main thread's `Agent` dispatch, including
    background dispatches. `tool_input` carries the arguments the caller passed
    -- observed: description, model, prompt, subagent_type. Keys the caller
    omitted are simply absent, so every read here defaults rather than assuming
    presence.
  - Exit code 2 REFUSES the dispatch. The agent does not run and this hook's
    stderr reaches the caller.

Which makes the failure mode the thing to design around: a hook that crashes
looks exactly like one that refused, and would block every dispatch for the rest
of the session. So this fails OPEN. Everything is caught; only a decision
returns 2.

Two harness constraints, restated because they bound what this can ever do:
hooks do not fire for tool calls made inside a subagent (#34692), so what is
gated is the decision to dispatch and not the spending that follows it; and hook
config loads at session start, so a policy change lands in the NEXT session.

The plan allowance is read here too, and it is the only band in this repo
that refuses on a quantity the operator CANNOT spend past (#129). The other
two -- the daily ceiling and the brief rubric -- refuse things that would
still work if allowed. At 100% of a rate-limit window nothing works, the
session ends where it stands, and `agent-yield resume` injects nothing into
the next one because nothing was written. So the refusal here is not "this is
expensive", it is "what is left of this window is for writing down, not for
dispatching".

Three constraints on it, all from the data rather than from taste:

  - The input is a LOG, not the payload. A PreToolUse payload carries no
    `rate_limits`; only the statusline sees them, and it snapshots them at no
    token cost. So this reads what the status line last wrote, which makes
    staleness a first-class question and `allowance.STALE_AFTER_MINUTES` the
    answer. On a machine where the status line is not running (#120) the log
    goes quiet and this guard correctly goes silent with it.
  - The threshold is CHOSEN and says so in `thresholds.py`. Nothing in the log
    can measure the room one handoff needs.
  - Its override is its own. Silencing the allowance must not also silence the
    daily ceiling, for the same reason boundary.py keeps a separate one.

Brief quality is checked here too. `--enforce-brief` is the EAGER form,
refusing any non-exempt dispatch whose prompt lacks a marker, and
`.claude/settings.template.json` has passed it since `c32721f`. This docstring
claimed for five days that the flag was off; the template is tracked, so it
was on for every machine that pulled (#163).

The recommended form refuses only on a compound condition -- markers missing
AND this session has already produced a dispatch measured in the un-briefed
population -- so that a refusal redirects the dispatch path instead of
blocking a first offence. That needs per-dispatch call counts, which issue #18
Part C builds, and it is still not implemented.

What makes the eager form safe to leave on is narrowing what it demands. A
line range is asked only of a brief that names a repo file, and an output path
only of a child that can write one. Both narrowings are refusals this gate
actually issued on 2026-08-30 against dispatches that could not have complied.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from .allowance import (
    SNAPSHOT_PATH as ALLOWANCE_PATH,
    Reading,
    STALE_AFTER_MINUTES,
    latest_readings,
    load as load_allowance,
)
from .hookio import read_payload
from .state import anchored
from .predict import Projection, project
from .thresholds import (
    REFERENCE_CONTEXT,
    allowance_advice,
    allowance_says_stop,
    band_for_day,
)

DISPATCH_TOOLS = ("Agent", "Task")
DEFAULT_CALLS_PATH = Path(".agent-yield") / "calls.jsonl"

# Named, per section 4.5's "refuse-with-named-override". Never a silent bypass:
# an override that leaves no trace is indistinguishable from no gate at all.
OVERRIDE_ENV = "AGENT_YIELD_OVERRIDE"

# #143: the hook subprocess reads the parent session's environment, and a
# dispatch made from inside a subagent has no way to set a variable there.
# A marker in the dispatch's own description is reachable from wherever the
# call is made -- and, because tool_input is visible in the dispatch itself,
# it is still a trace, never a silent bypass.
OVERRIDE_MARKER = "AGENT_YIELD_OVERRIDE"

# Distinct from OVERRIDE_ENV on purpose, exactly as boundary.py keeps its own:
# an operator who decides the day's token ceiling is wrong has not decided
# that the plan's rate limit is wrong, and one variable for both would let the
# first silence the second by accident.
ALLOWANCE_OVERRIDE_ENV = "AGENT_YIELD_ALLOWANCE_OVERRIDE"

# docs/working-method.md §12: an exploratory dispatch is SUPPOSED to lack the
# brief markers below -- exempting it is the whole reason the rubric is safe
# to enforce. Kept as data, not a hardcoded branch, so the list can grow.
BRIEF_EXEMPT_TYPES = frozenset({"explore", "plan"})

# #164: an agent type whose tools cannot write a file is asked, by "output
# path", for something it structurally cannot produce. One dispatch spent
# 55,927 tokens discovering that. §12.3 says the return contract IS the
# artifact for these, so the marker is not scored against them.
READ_ONLY_TYPES = frozenset({"claude-code-guide"})


@dataclass(frozen=True)
class DispatchRequest:
    subagent_type: str | None = None
    model: str | None = None
    description: str | None = None
    prompt: str | None = None


def read_dispatch(payload: dict) -> DispatchRequest | None:
    if payload.get("tool_name") not in DISPATCH_TOOLS:
        return None
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        tool_input = {}
    return DispatchRequest(
        subagent_type=tool_input.get("subagent_type"),
        model=tool_input.get("model"),
        description=tool_input.get("description"),
        prompt=tool_input.get("prompt"),
    )


# §12's four-part brief, as pattern rather than checklist. Three of the four
# parts are visible in the prompt and are checked here: the line range plus its
# prohibition, the named output path, and the return contract. The fourth --
# the ~10-call cap -- is not checkable before the dispatch runs, and hooks do
# not fire inside a subagent (#34692), so it belongs to a post-hoc audit
# (issue #18 Part C) and is deliberately absent below.
#
# The line range and the prohibition are one marker on purpose: a range
# without "do not explore" is not the intervention that was measured. Briefed
# agents held 17,580-67,123 context/call; un-briefed ones on the same machine
# sat at a median 85,195.
_LINE_RANGE_RE = re.compile(
    r"(sed -n '\d+,\d+p')|(lines?\s+\d+\s*[-\u2013]\s*\d+)|(:\d+-\d+\b)", re.IGNORECASE
)

# #163: a range is a claim about a file, so it cannot honestly be demanded of a
# brief that names none. A dispatch reading vendor documentation has no lines
# to cite, which is the class \u00a712.2 exempts in as many words -- "an
# exploratory dispatch is SUPPOSED to carry none of these markers" -- and which
# the type-name exemption above cannot see, because a name is a proxy for the
# work and the two part company exactly here.
#
# Naming no file is NOT sufficient on its own, and the first draft of this got
# that wrong: an empty prompt names no file either, and so does every dispatch
# in the un-briefed population \u00a712 was built to catch. The prohibition is what
# separates them. A brief that says "do not explore" and cites nothing has
# bounded itself and has nothing to cite; one that says neither has simply not
# been written. So the demand is dropped only when both hold.
_REPO_PATH_RE = re.compile(
    r"""(?xi)
    (?: \b(?:src|tests?|docs|scripts)[/\\][\w./\\-]+
      | \.(?:claude|github)[/\\][\w./\\-]+
      | \b[\w-]+\.(?:py|md|json|toml|ya?ml|cfg|ini|sh|ps1)\b
    )"""
)

# #32: every one of these three used to test for particular *wording*, and all
# three then scored zero on five dispatches written to this section verbatim.
# They test for the property now. The rule that produced the bug, and the rule
# these are held to: a marker asks "does the brief bound this?", never "does
# the brief say it the way the author of the regex would have said it."
#
# (a)'s second half -- the prohibition. The property is "do not go looking":
# a negation applied to any way a child discovers files for itself, or a
# read directive that closes the list it just gave.
_NO_EXPLORE_RE = re.compile(
    r"""(?:
          (?:do \s+ not | don't | never | no) \s+ (?:\w+ \s+){0,3}
          (?: explor\w* | search\w* | grep\w* | glob\w* | browse\w* | discover\w*
            | hunt\w* | wander\w* | look \s+ (?:around|for)
            | read \s+ (?:any \s+)? (?:other|another|more|additional|further)
            | open \s+ (?:any \s+)? (?:other|another)
            )
        | no \s+ (?:exploration|searching|grepping|discovery)
        | read \s+ (?:exactly|only|nothing \s+ but)\b
        | read\w* [\s\S]{0,80}? nothing \s+ else
        | if \s+ you \s+ need \s+ [\s\S]{0,60}? not \s+ listed
        )""",
    re.IGNORECASE | re.VERBOSE,
)

# (c) -- a named output path. The old pattern used `.` without DOTALL, so a
# brief that put the path on its own line ("write it to:\n  /path/x.json")
# scored zero while the identical words on one line scored one. Verified both
# ways before the fix.
_OUTPUT_PATH_RE = re.compile(
    r"(write|save|output|append|produce|emit|dump|put)\b"
    r"[\s\S]{0,80}?"
    r"(/[^\s'\"]+|[\w./-]+\.(md|json|jsonl|py|txt|csv|tsv|html|ya?ml))",
    re.IGNORECASE,
)

# (d) -- a bound on what comes back. "at most 3 lines" is the same property as
# "under 3 lines"; only the vocabulary differed, and only the vocabulary was
# tested.
_RETURN_CONTRACT_RE = re.compile(
    r"""(?:
          return \s+ contract
        | (?: return\w* | repl(?:y|ies) | respond\w* | report \s+ back
            | final \s+ (?:message|answer|output|response|line)
            ) \b
          [\s\S]{0,100}?
          (?: only\b | nothing \s+ else | just\b
            | (?:at \s+ most | no \s+ more \s+ than | under | fewer \s+ than
              | at \s+ the \s+ outside) \s+ \d+
            | \d+ \s+ lines?\b
            | one \s+ (?:line|verdict|sentence|paragraph|word)
            | file:line
            | do \s+ not \s+ (?:paste|summari[sz]e|include|explain|quote)
            )
        )""",
    re.IGNORECASE | re.VERBOSE,
)

_BRIEF_REMEDY = {
    "line ranges": 'line ranges (e.g. via sed -n) plus an explicit "do not explore"',
    "output path": "a named output path for the child to write to",
    "return contract": "a stated return contract -- what to return, and nothing else",
}


def missing_markers(request: DispatchRequest) -> tuple[str, ...]:
    """Which rubric markers a dispatch prompt does not carry."""
    prompt = request.prompt or ""
    subagent_type = (request.subagent_type or "").lower()
    missing = []
    bounded_and_fileless = _NO_EXPLORE_RE.search(prompt) and not _REPO_PATH_RE.search(
        prompt
    )
    if not bounded_and_fileless and not (
        _LINE_RANGE_RE.search(prompt) and _NO_EXPLORE_RE.search(prompt)
    ):
        missing.append("line ranges")
    if subagent_type not in READ_ONLY_TYPES and not _OUTPUT_PATH_RE.search(prompt):
        missing.append("output path")
    if not _RETURN_CONTRACT_RE.search(prompt):
        missing.append("return contract")
    return tuple(missing)


def brief_message(missing: tuple[str, ...]) -> str | None:
    """One line naming what is missing and the remedy, or None."""
    if not missing:
        return None
    remedies = "; ".join(_BRIEF_REMEDY[marker] for marker in missing)
    return (
        f"[agent-yield] BRIEF: this dispatch is missing {', '.join(missing)} "
        f"(docs/working-method.md §12). Add {remedies}."
    )


def gate_message(day_total: int, projection: Projection) -> str | None:
    band = band_for_day(day_total)
    if band == "silent":
        return None
    prefix = "WARN" if band == "warn" else "OVER CEILING"
    return (
        f"[agent-yield] {prefix}: {day_total:,} tokens spent today. "
        f"This dispatch projects {projection.describe()}."
    )


def allowance_message(
    readings: dict[str, Reading] | None,
    stale_after: float = STALE_AFTER_MINUTES,
) -> tuple[str | None, bool]:
    """The line about the plan allowance, and whether it refuses this dispatch.

    Both windows are checked and the worse one speaks: they have opposite
    remedies -- five-hour refills, seven-day does not -- so which one is
    talking has to reach the caller.

    Silent on a stale reading, and that is the safe direction here rather than
    the timid one. A fossil says nothing about the window it names; refusing
    every dispatch in a session on a three-day-old 95% would be the failure
    mode that gets a guard uninstalled.
    """
    if not readings:
        return None, False
    lines, refuse = [], False
    for window in ("five_hour", "seven_day"):
        reading = readings.get(window)
        if reading is None or not reading.is_fresh(stale_after):
            continue
        advice = allowance_advice(
            window, reading.used_percentage, reading.minutes_to_reset
        )
        if advice is None:
            continue
        lines.append(f"[agent-yield] ALLOWANCE: {advice}")
        refuse = refuse or allowance_says_stop(
            window, reading.used_percentage, reading.minutes_to_reset
        )
    if not lines:
        return None, False
    return " ".join(lines), refuse


def read_current_allowance(path: Path | None = None) -> dict[str, Reading]:
    """What the status line last wrote about each window. Never raises.

    Resolved at call time rather than bound as a default, for boundary.py's
    reason: the hook reads the log from whatever working directory it is
    invoked in, and a default frozen at import time cannot be pointed
    elsewhere by a test.
    """
    try:
        return latest_readings(load_allowance(path or ALLOWANCE_PATH))
    except Exception:
        return {}


def _has_override(request: DispatchRequest) -> bool:
    """True when the dispatch itself carries the override marker.

    Reachable from inside a subagent, unlike OVERRIDE_ENV: the calling agent
    writes tool_input directly, so this needs no access to the hook
    subprocess's environment.
    """
    return bool(request.description) and OVERRIDE_MARKER in request.description


def _day_total(calls_path: Path) -> int:
    from .ingest import load_ingested

    today = dt.datetime.now(dt.timezone.utc).date()
    return sum(r.usage.total for r in load_ingested(calls_path) if r.day == today)


def _decide(
    payload: dict,
    enforce_brief: bool = False,
    readings: dict[str, Reading] | None = None,
) -> tuple[int, str | None]:
    """Return (exit_code, message). Exit 2 means refuse this dispatch.

    `readings` is passed in rather than read here: the allowance log lives in
    the working directory, and a decision function that reaches for it makes
    every test of every other band depend on whatever this machine's status
    line happened to write. `main` does the read.
    """
    request = read_dispatch(payload)
    if request is None:
        return 0, None

    # `_day_total` in the payload is a test seam; real runs read the ingest.
    day_total = payload.get("_day_total")
    if not isinstance(day_total, int):
        day_total = _day_total(anchored(DEFAULT_CALLS_PATH))

    day_message = gate_message(day_total, project(REFERENCE_CONTEXT))
    over_ceiling = (
        day_message is not None
        and band_for_day(day_total) == "over"
        and not os.environ.get(OVERRIDE_ENV)
        and not _has_override(request)
    )

    allow_message, over_allowance = allowance_message(readings)
    over_allowance = over_allowance and not os.environ.get(ALLOWANCE_OVERRIDE_ENV)

    brief_msg = None
    subagent_type = (request.subagent_type or "").lower()
    if subagent_type not in BRIEF_EXEMPT_TYPES:
        brief_msg = brief_message(missing_markers(request))

    # The allowance leads: it is the only one of the three that the operator
    # cannot decide to spend past.
    messages = [m for m in (allow_message, day_message, brief_msg) if m]
    combined = " ".join(messages) if messages else None

    # --enforce-brief is off by default: turning it on is a separate recorded
    # decision, not a side effect of building the check. When it is on, it
    # honours OVERRIDE_ENV exactly as the day-ceiling refusal does.
    refuse_brief = (
        enforce_brief
        and brief_msg is not None
        and not os.environ.get(OVERRIDE_ENV)
        and not _has_override(request)
    )

    overrides = []
    if over_allowance:
        overrides.append(ALLOWANCE_OVERRIDE_ENV)
    if over_ceiling or refuse_brief:
        overrides.append(OVERRIDE_ENV)
    if overrides:
        named = " and ".join(f"{name}=1" for name in dict.fromkeys(overrides))
        return 2, f"{combined} Set {named} to dispatch anyway."
    return 0, combined


def main(argv: list[str] | None = None, stdin: TextIO | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    enforce_brief = "--enforce-brief" in args
    try:
        payload = json.loads(read_payload(stdin) or "{}")
        if not isinstance(payload, dict):
            return 0
        code, message = _decide(
            payload,
            enforce_brief=enforce_brief,
            readings=read_current_allowance(),
        )
    except Exception:
        # Deliberately broad. A gate that raises refuses every dispatch in the
        # session and the caller cannot tell that apart from a real refusal.
        # Only a decision blocks; a bug never does.
        return 0

    if code == 2:
        print(message, file=sys.stderr)
        return 2
    if message:
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "additionalContext": message,
            }
        }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
