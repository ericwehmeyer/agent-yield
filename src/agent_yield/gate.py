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

Brief quality is checked here too, and warns rather than refuses.
`--enforce-brief` exists and is OFF: it is the EAGER form, refusing any
non-exempt dispatch whose prompt lacks a marker. The recommended form refuses
only on a compound condition -- markers missing AND this session has already
produced a dispatch measured in the un-briefed population -- so that a
refusal redirects the dispatch path instead of blocking a first offence. That
condition needs per-dispatch call counts, which are exactly what issue #18
Part C builds, so it is not implemented and the flag stays off until it is.
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

from .predict import Projection, project
from .thresholds import REFERENCE_CONTEXT, band_for_day

DISPATCH_TOOLS = ("Agent", "Task")
DEFAULT_CALLS_PATH = Path(".agent-yield") / "calls.jsonl"

# Named, per section 4.5's "refuse-with-named-override". Never a silent bypass:
# an override that leaves no trace is indistinguishable from no gate at all.
OVERRIDE_ENV = "AGENT_YIELD_OVERRIDE"

# docs/working-method.md §12: an exploratory dispatch is SUPPOSED to lack the
# brief markers below -- exempting it is the whole reason the rubric is safe
# to enforce. Kept as data, not a hardcoded branch, so the list can grow.
BRIEF_EXEMPT_TYPES = frozenset({"explore", "plan"})


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
    r"(sed -n '\d+,\d+p')|(lines?\s+\d+\s*[-–]\s*\d+)|(:\d+-\d+\b)", re.IGNORECASE
)
_NO_EXPLORE_RE = re.compile(
    r"(do not|don't|never)\s+explore|no exploration", re.IGNORECASE
)
_OUTPUT_PATH_RE = re.compile(
    r"""(write|save|output|append)\b.{0,60}(/[^\s'"]+|[\w./-]+\.(md|json|jsonl|py|txt|csv|html))""",
    re.IGNORECASE,
)
_RETURN_CONTRACT_RE = re.compile(
    r"return\w*\b.{0,80}(only|nothing else|under \d+ lines|one (line|verdict)|file:line)",
    re.IGNORECASE,
)

_BRIEF_REMEDY = {
    "line ranges": 'line ranges (e.g. via sed -n) plus an explicit "do not explore"',
    "output path": "a named output path for the child to write to",
    "return contract": "a stated return contract -- what to return, and nothing else",
}


def missing_markers(request: DispatchRequest) -> tuple[str, ...]:
    """Which rubric markers a dispatch prompt does not carry."""
    prompt = request.prompt or ""
    missing = []
    if not (_LINE_RANGE_RE.search(prompt) and _NO_EXPLORE_RE.search(prompt)):
        missing.append("line ranges")
    if not _OUTPUT_PATH_RE.search(prompt):
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


def _day_total(calls_path: Path) -> int:
    from .ingest import load_ingested

    today = dt.datetime.now(dt.timezone.utc).date()
    return sum(r.usage.total for r in load_ingested(calls_path) if r.day == today)


def _decide(payload: dict, enforce_brief: bool = False) -> tuple[int, str | None]:
    """Return (exit_code, message). Exit 2 means refuse this dispatch."""
    request = read_dispatch(payload)
    if request is None:
        return 0, None

    # `_day_total` in the payload is a test seam; real runs read the ingest.
    day_total = payload.get("_day_total")
    if not isinstance(day_total, int):
        day_total = _day_total(DEFAULT_CALLS_PATH)

    day_message = gate_message(day_total, project(REFERENCE_CONTEXT))
    over_ceiling = (
        day_message is not None
        and band_for_day(day_total) == "over"
        and not os.environ.get(OVERRIDE_ENV)
    )

    brief_msg = None
    subagent_type = (request.subagent_type or "").lower()
    if subagent_type not in BRIEF_EXEMPT_TYPES:
        brief_msg = brief_message(missing_markers(request))

    messages = [m for m in (day_message, brief_msg) if m]
    combined = " ".join(messages) if messages else None

    # --enforce-brief is off by default: turning it on is a separate recorded
    # decision, not a side effect of building the check. When it is on, it
    # honours OVERRIDE_ENV exactly as the day-ceiling refusal does.
    refuse_brief = (
        enforce_brief and brief_msg is not None and not os.environ.get(OVERRIDE_ENV)
    )

    if over_ceiling or refuse_brief:
        return 2, f"{combined} Set {OVERRIDE_ENV}=1 to dispatch anyway."
    return 0, combined


def main(argv: list[str] | None = None, stdin: TextIO | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    enforce_brief = "--enforce-brief" in args
    stream = stdin if stdin is not None else sys.stdin
    try:
        payload = json.loads(stream.read() or "{}")
        if not isinstance(payload, dict):
            return 0
        code, message = _decide(payload, enforce_brief=enforce_brief)
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
