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
"""
from __future__ import annotations

import datetime as dt
import json
import os
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


@dataclass(frozen=True)
class DispatchRequest:
    subagent_type: str | None = None
    model: str | None = None
    description: str | None = None


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


def _decide(payload: dict) -> tuple[int, str | None]:
    """Return (exit_code, message). Exit 2 means refuse this dispatch."""
    if read_dispatch(payload) is None:
        return 0, None

    # `_day_total` in the payload is a test seam; real runs read the ingest.
    day_total = payload.get("_day_total")
    if not isinstance(day_total, int):
        day_total = _day_total(DEFAULT_CALLS_PATH)

    message = gate_message(day_total, project(REFERENCE_CONTEXT))
    if message is None:
        return 0, None

    if band_for_day(day_total) == "over" and not os.environ.get(OVERRIDE_ENV):
        return 2, f"{message} Set {OVERRIDE_ENV}=1 to dispatch anyway."
    return 0, message


def main(argv: list[str] | None = None, stdin: TextIO | None = None) -> int:
    stream = stdin if stdin is not None else sys.stdin
    try:
        payload = json.loads(stream.read() or "{}")
        if not isinstance(payload, dict):
            return 0
        code, message = _decide(payload)
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
