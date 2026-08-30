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
  - **Exit 2 refuses the prompt, and the operator is told why** (armed
    refusal, 2026-08-26 01:48 UTC). The refused prompt never reached the
    model; the operator saw, verbatim:

        UserPromptSubmit operation blocked by hook:
          [/path/to/agent-yield boundary --probe]: <this hook's stderr>

        Original prompt: <what they typed>

    Three things follow, and the third is the one that changes the design.
    stderr reaches the operator in full, so an enforcing boundary can
    explain itself. The hook is named in the message, so a refusal can be
    traced to its cause without guesswork. And **the harness echoes the
    prompt back**, so refusing costs the operator a re-send, not their
    typing -- which is most of the risk `--enforce` was being cautious
    about. It is a verified mechanism now, not a hopeful flag.

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
import re
import sys
from pathlib import Path
from typing import TextIO

from .handoff import DEFAULT_HANDOFF_PATH
from .hookio import read_payload
from .state import anchored
from .session import (
    SessionStats,
    cost_crossings,
    resolve_transcript,
    session_stats,
)
from .thresholds import RESTART_HARD_FACTOR, cost_band, cost_says_leave

__all__ = [
    "OVERRIDE_ENV",
    "PROBE_PATH",
    "REFUSAL_ARMED_PATH",
    "REFUSAL_SPENT_PATH",
    "REFUSAL_LOG_PATH",
    "arm_refusal",
    "invokes_the_remedy",
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

# Refusals are recorded here rather than by `_probe`, which only writes when
# `--probe` is passed -- and passing it forces advisory mode, so an enforcing
# hook could never record anything. "No refusals" and "never refused" were the
# same log on both machines from the moment enforcement was switched on. Found
# by the Mac session on 2026-08-30 while running the audit script.
REFUSAL_LOG_PATH = Path(".agent-yield") / "boundary-refusals.jsonl"

# The exit-2 measurement, armed by hand and fired exactly once. gate.py's
# exit 2 was measured by making one dispatch fail on purpose under human
# approval; this is the same move for prompts, with one addition -- the
# sentinel is deleted BEFORE the refusal is returned, so even if exit 2 does
# block the prompt, the operator's next one goes through. A measurement that
# can lock someone out of their session is not a measurement worth having.
REFUSAL_ARMED_PATH = Path(".agent-yield") / "boundary-refusal-armed"

# One refusal per session, spent before it is returned. `--enforce` used to
# return 2 on every prompt while the condition held, so the remedy the message
# prescribes needed a turn the refusal was denying. Session c15eb016 hit that
# on 2026-08-30 at 11:45 EDT, ran 88 calls to 220,658 context, and was exited
# with nothing written down -- the boundary lost the session it exists to save
# (#130). The comment above REFUSAL_ARMED_PATH already stated the rule; this
# is the enforce path finally keeping it.
REFUSAL_SPENT_PATH = Path(".agent-yield") / "boundary-refusal-spent"

# A prompt that runs the remedy is never refused. Matching is deliberately
# loose -- across `agent-yield handoff`, a venv path, a `.exe`, and a leading
# `!`. Too wide costs one missed refusal; too narrow costs the whole session,
# so the asymmetry decides which way to err.
REMEDY_RE = re.compile(r"""agent-yield(?:\.exe)?["']?\s+handoff\b""", re.IGNORECASE)


def invokes_the_remedy(prompt: str | None) -> bool:
    """Does this prompt run `agent-yield handoff`?"""
    return bool(prompt and REMEDY_RE.search(prompt))


def _spend_refusal(session_id: str, path: Path | None = None) -> bool:
    """Claim this session's one refusal. False once it is already spent.

    Recorded before the refusal is returned, never after: a crash between the
    two must leave a session that can still be prompted. Keyed by session so a
    fresh session gets a fresh refusal, and failing to write means not
    refusing -- a boundary that cannot record itself has no business blocking.
    """
    target = anchored(path if path is not None else REFUSAL_SPENT_PATH)
    try:
        if target.read_text(encoding="utf-8").strip() == session_id:
            return False
    except OSError:
        pass
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(session_id + "\n", encoding="utf-8", newline="\n")
    except OSError:
        return False
    return True


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
            anchored(handoff_path).stat().st_mtime, tz=dt.timezone.utc
        )
    except OSError:
        return False
    return written >= stats.started


def boundary_message(
    stats: SessionStats,
    handoff_path: Path,
    hard_factor: float = RESTART_HARD_FACTOR,
) -> str | None:
    """The one line, or ``None`` when this session may continue.

    Two independent reasons to stop, both meaning "leave": context/call has
    grown past the hard factor, or this call sits in a cost band whose remedy
    is to end the session. Neither fires while a handoff written in this
    session exists.

    No window: the cost bands are absolute tokens (issue #23), and the
    boundary asks what the next call bills, never how much room is left.
    """
    reasons = []
    if stats.growth is not None and stats.growth >= hard_factor:
        opening = round(stats.opening_context_per_call or 0)
        reasons.append(
            f"context/call has grown {stats.growth:.1f}x "
            f"({opening:,} -> {stats.current_context:,} over {stats.calls:,} calls)"
        )
    if cost_says_leave(stats.current_context):
        band = cost_band(stats.current_context)
        crossed = cost_crossings(stats).get(band)
        where = f", crossed at call {crossed:,}" if crossed else ""
        reasons.append(
            f"this call carries {stats.current_context:,} tokens, in the "
            f"{band} band{where}"
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
        f"A handoff written now is loaded automatically into the next session. "
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
        probe = anchored(PROBE_PATH)
        probe.parent.mkdir(parents=True, exist_ok=True)
        with probe.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(entry) + "\n")
    except Exception:
        return


def arm_refusal(path: Path | None = None) -> Path:
    """Arm one deliberate exit-2 refusal, for the next prompt only."""
    target = anchored(path if path is not None else REFUSAL_ARMED_PATH)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        dt.datetime.now(dt.timezone.utc).isoformat() + "\n", encoding="utf-8", newline="\n"
    )
    return target


def _disarm_refusal(path: Path | None = None) -> bool:
    """Consume the sentinel. True if it was armed; disarms before refusing."""
    target = anchored(path if path is not None else REFUSAL_ARMED_PATH)
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
    stats: SessionStats | None = None,
    spent_path: Path | None = None,
) -> tuple[int, str | None]:
    """Return (exit_code, message). Exit 2 only under ``enforce``, and at
    most once per session -- never on the prompt that runs the remedy."""
    # Resolved at call time, not bound as a default: the hook reads it from
    # the working directory it is invoked in, and tests point it elsewhere.
    handoff_path = handoff_path or DEFAULT_HANDOFF_PATH
    if os.environ.get(OVERRIDE_ENV):
        return 0, None
    if stats is None:
        stats = _stats_for(payload)
    if stats is None:
        return 0, None
    message = boundary_message(stats, handoff_path, hard_factor)
    if message is None:
        return 0, None
    if not enforce:
        return 0, message
    # The message prescribes `agent-yield handoff`; refusing that prompt is
    # the one thing this hook must never do.
    if invokes_the_remedy(payload.get("prompt")):
        return 0, message
    session = str(payload.get("session_id") or "unidentified")
    if not _spend_refusal(session, spent_path):
        return 0, message
    return 2, message + REFUSED_SUFFIX


# Appended only when a prompt is actually refused, so the operator learns the
# refusal is survivable from the refusal itself. Without this the message
# named a remedy and no way to reach it.
#
# The `!` escape was measured on 2026-08-30, not assumed: a `!`-prefixed input
# produced no UserPromptSubmit hook output at all, where every ordinary prompt
# in the same session did. It is harness behaviour rather than a promise this
# repo can keep, which is why it is phrased as what the prefix does and not as
# a guarantee that it always will.
REFUSED_SUFFIX = (
    " This refusal is spent: send your prompt again and it will go through. "
    "A prompt running `agent-yield handoff` is never refused, and a prompt "
    "prefixed with `!` runs as a shell command without reaching this hook."
)


REFUSAL_PROBE_MESSAGE = (
    "[agent-yield] Deliberate one-shot measurement of UserPromptSubmit exit 2 "
    "(issue #22): this hook has just exited 2. It has already disarmed itself, "
    "so send your prompt again and it will go through. If you are reading this "
    "and your prompt still ran, exit 2 does not refuse a prompt and `--enforce` "
    "is not buildable; if the prompt was refused, it is."
)


def _record_refusal(payload: dict, message: str, path: Path | None = None) -> None:
    """Append the shape of a refusal that actually happened.

    Never the prompt: the probe's rule is that the mechanism is measured and
    the content is not, and a refusal log is a worse place to break it. The
    message is generated by this module, so the context figures travel without
    anything the operator typed.
    """
    target = anchored(path if path is not None else REFUSAL_LOG_PATH)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps({
                "observed": dt.datetime.now(dt.timezone.utc).isoformat(),
                "session_id": payload.get("session_id"),
                "hook_event_name": payload.get("hook_event_name"),
                "exit_code": 2,
                "message": message,
            }) + "\n")
    except Exception:
        # Recording a refusal must never be the reason a prompt dies.
        pass


def main(argv: list[str] | None = None, stdin: TextIO | None = None) -> int:
    args = list(argv or [])
    enforce = "--enforce" in args
    probing = "--probe" in args
    try:
        payload = json.loads(read_payload(stdin) or "{}")
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
        _record_refusal(payload, message)
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
