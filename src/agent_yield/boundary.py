"""UserPromptSubmit boundary: make continuing refuse to work -- carefully.

MEASURED, and the measurement matters more than the code:

  - PreToolUse on `Agent` fires, carries `tool_input`, and exit 2 refuses the
    dispatch (gate.py, 2026-08-25).
  - **UserPromptSubmit fires, and its payload is now measured** (probe,
    2026-08-26 01:31 UTC, macOS, issue #22). One prompt in a fresh session
    recorded the event as `UserPromptSubmit` carrying exactly:

        cwd, hook_event_name, permission_mode, prompt_id, session_id,
        transcript_path                                  (+ prompt)

    So the live session is identified twice over -- by path and by id -- and
    `session.resolve_transcript` now uses the observed contract instead of
    guessing at it.
  - **Whether exit 2 blocks a prompt is still NOT measured**, and neither is
    whether stderr reaches the operator. `--enforce` therefore remains
    unverified; see `--probe-refuse`, which measures it once, deliberately,
    and disarms itself.

And it cannot be verified from the session that installs it: hook config loads
at session start, so a hook installed now first runs in the NEXT session. That
is structural, not an accident of effort -- no session can measure a hook it
installs. So this module ships in two halves:

  - `--probe`, which records what actually arrives and what the harness does
    with the exit code, and always exits 0;
  - the decision itself, which defaults to ADVISING (exit 0 with the message
    on stderr and as additionalContext) and only refuses under `--enforce`.

Fail open, absolutely. A bug in gate.py blocks dispatches; a bug here locks
the operator out of their own session. Every path is caught and every
unexpected input exits 0 silently.

The boundary is a door, not a wall. It does not fire on "this session is
expensive" -- it fires on "this session is expensive AND nothing is written
down", and one `agent-yield handoff` clears it for the rest of the session.
A restart is only expensive because what is not written down is lost; a
boundary that cannot be cleared by writing it down is punishing the operator
for the tool's own missing half, and gets disabled within a day.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sys
from pathlib import Path
from typing import TextIO

from .handoff import DEFAULT_HANDOFF_PATH
from .session import (
    SessionStats,
    cost_crossings,
    resolve_transcript,
    session_stats,
)
from .thresholds import DEFAULT_WINDOW, RESTART_HARD_FACTOR, cost_band

__all__ = [
    "OVERRIDE_ENV",
    "PROBE_PATH",
    "REFUSAL_ARMED_PATH",
    "arm_refusal",
    "handoff_is_current",
    "boundary_message",
    "decide",
    "main",
]

# Distinct from gate's AGENT_YIELD_OVERRIDE on purpose: silencing the session
# boundary must not also silence the daily ceiling. Named, never silent -- an
# override that leaves no trace is indistinguishable from no boundary at all.
OVERRIDE_ENV = "AGENT_YIELD_BOUNDARY_OVERRIDE"

PROBE_PATH = Path(".agent-yield") / "boundary-probe.jsonl"

# The exit-2 measurement, armed by hand and fired exactly once. gate.py's
# exit 2 was measured by making one dispatch fail on purpose under human
# approval; this is the same move for prompts, with one addition -- the
# sentinel is deleted BEFORE the refusal is returned, so even if exit 2 does
# block the prompt, the operator's next one goes through. A measurement that
# can lock someone out of their session is not a measurement worth having.
REFUSAL_ARMED_PATH = Path(".agent-yield") / "boundary-refusal-armed"


def handoff_is_current(handoff_path: Path, stats: SessionStats) -> bool:
    """Was a handoff written during this session?

    Not "recently" and not "since the last call" -- either would go stale one
    call later and make the boundary unclearable. Written after this session's
    first call is what a restart actually needs, and it is one command away.
    """
    if stats.started is None:
        return False
    try:
        written = dt.datetime.fromtimestamp(
            Path(handoff_path).stat().st_mtime, tz=dt.timezone.utc
        )
    except OSError:
        return False
    return written >= stats.started


def boundary_message(
    stats: SessionStats,
    handoff_path: Path,
    hard_factor: float = RESTART_HARD_FACTOR,
    window: int = DEFAULT_WINDOW,
) -> str | None:
    """The one line, or ``None`` when this session may continue.

    Two independent reasons to stop, both meaning "leave": context/call has
    grown past the hard factor, or the session sits in the steep cost band.
    Neither fires while a handoff written in this session exists.
    """
    reasons = []
    if stats.growth is not None and stats.growth >= hard_factor:
        opening = round(stats.opening_context_per_call or 0)
        reasons.append(
            f"context/call has grown {stats.growth:.1f}x "
            f"({opening:,} -> {stats.current_context:,} over {stats.calls:,} calls)"
        )
    if window > 0 and cost_band(stats.current_context, window) == "steep":
        crossed = cost_crossings(stats, window).get("steep")
        where = f", crossed at call {crossed:,}" if crossed else ""
        reasons.append(
            f"this call sits at {stats.current_context / window:.0%} of a "
            f"{window:,} window, deep in the expensive band{where}"
        )
    if not reasons:
        return None
    if handoff_is_current(handoff_path, stats):
        return None
    return (
        "[agent-yield] " + "; and ".join(reasons) + ". "
        f"Nothing is written down for this session: run `agent-yield handoff "
        f"--note \"...\"` and then start a fresh session, or continue in this "
        f"one -- the handoff clears this boundary either way. "
        f"Set {OVERRIDE_ENV}=1 to silence it."
    )


def _stats_for(payload: dict) -> SessionStats | None:
    """Measure the session this prompt belongs to, or give up quietly."""
    path, _route = resolve_transcript(payload)
    if path is None:
        return None
    stats = session_stats(path)
    return stats if stats.calls else None


def _resolution(payload: dict) -> dict:
    """How the payload identified its session -- shape only, never content.

    The first probe recorded which keys arrived but not whether they *worked*,
    which left issue #22's real question open: can the hook find the live
    session's transcript, or is it measuring whichever session touched disk
    last? This answers it from the recording. No path and no prompt text is
    written -- a path carries the operator's home directory, and the boundary
    measures the mechanism, not the operator.
    """
    path, route = resolve_transcript(payload)
    session_id = payload.get("session_id") or payload.get("sessionId")
    resolved_calls = None
    matches_session_id = None
    if path is not None:
        try:
            resolved_calls = session_stats(path).calls
        except Exception:
            resolved_calls = None
        if isinstance(session_id, str) and session_id:
            matches_session_id = path.stem == session_id
    return {
        "route": route,
        "transcript_path_present": isinstance(
            payload.get("transcript_path"), str
        ) and bool(payload.get("transcript_path")),
        "resolved": path is not None,
        "resolved_calls": resolved_calls,
        "stem_matches_session_id": matches_session_id,
    }


def _probe(
    payload: dict,
    message: str | None,
    enforce: bool,
    exit_code: int = 0,
    refusal: bool = False,
) -> None:
    """Record what arrived, for the session that can finally read it.

    Never raises: a probe that breaks the hook it is measuring measures the
    hook's failure mode instead of its behaviour.
    """
    try:
        entry = {
            "observed": dt.datetime.now(dt.timezone.utc).isoformat(),
            "hook_event_name": payload.get("hook_event_name"),
            "keys": sorted(k for k in payload if k != "prompt"),
            "has_prompt": "prompt" in payload,
            "would_stop": message is not None,
            "enforce": enforce,
            "refusal_probe": refusal,
            "exit_code": exit_code,
        }
        entry.update(_resolution(payload))
        PROBE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with PROBE_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")
    except Exception:
        return


def arm_refusal(path: Path | None = None) -> Path:
    """Arm one deliberate exit-2 refusal, for the next prompt only."""
    target = Path(path) if path is not None else REFUSAL_ARMED_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        dt.datetime.now(dt.timezone.utc).isoformat() + "\n", encoding="utf-8"
    )
    return target


def _disarm_refusal(path: Path | None = None) -> bool:
    """Consume the sentinel. True if it was armed; disarms before refusing."""
    target = Path(path) if path is not None else REFUSAL_ARMED_PATH
    try:
        target.unlink()
    except OSError:
        return False
    return True


def decide(
    payload: dict,
    enforce: bool = False,
    handoff_path: Path | None = None,
    hard_factor: float = RESTART_HARD_FACTOR,
    window: int = DEFAULT_WINDOW,
    stats: SessionStats | None = None,
) -> tuple[int, str | None]:
    """Return (exit_code, message). Exit 2 only under ``enforce``."""
    # Resolved at call time, not bound as a default: the hook reads it from
    # the working directory it is invoked in, and tests point it elsewhere.
    handoff_path = handoff_path or DEFAULT_HANDOFF_PATH
    if os.environ.get(OVERRIDE_ENV):
        return 0, None
    if stats is None:
        stats = _stats_for(payload)
    if stats is None:
        return 0, None
    message = boundary_message(stats, handoff_path, hard_factor, window)
    if message is None:
        return 0, None
    return (2 if enforce else 0), message


REFUSAL_PROBE_MESSAGE = (
    "[agent-yield] Deliberate one-shot measurement of UserPromptSubmit exit 2 "
    "(issue #22): this hook has just exited 2. It has already disarmed itself, "
    "so send your prompt again and it will go through. If you are reading this "
    "and your prompt still ran, exit 2 does not refuse a prompt and `--enforce` "
    "is not buildable; if the prompt was refused, it is."
)


def main(argv: list[str] | None = None, stdin: TextIO | None = None) -> int:
    args = list(argv or [])
    enforce = "--enforce" in args
    probing = "--probe" in args
    stream = stdin if stdin is not None else sys.stdin
    try:
        payload = json.loads(stream.read() or "{}")
        if not isinstance(payload, dict):
            return 0
        # The armed one-shot refusal outranks everything below it, including
        # the override: it is not the boundary firing, it is the measurement
        # the boundary's own enforce flag is waiting on. Disarm first, refuse
        # second -- in that order a crash between the two leaves the operator
        # with a working session rather than a hook that refuses every prompt.
        if probing and _disarm_refusal():
            _probe(payload, REFUSAL_PROBE_MESSAGE, enforce, 2, refusal=True)
            print(REFUSAL_PROBE_MESSAGE, file=sys.stderr)
            return 2
        # A probe observes; it never blocks, whatever else was asked for.
        code, message = decide(payload, enforce=enforce and not probing)
        if probing:
            _probe(payload, message, enforce, code)
    except Exception:
        # Deliberately broad, and more important here than in gate.py: a
        # raising gate blocks dispatches, a raising boundary blocks the
        # operator's own prompts for the rest of the session.
        return 0

    if message is None:
        return 0
    if code == 2:
        print(message, file=sys.stderr)
        return 2
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": payload.get("hook_event_name") or "UserPromptSubmit",
            "additionalContext": message,
        }
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
