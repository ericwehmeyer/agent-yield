"""SessionStart hook: load the last handoff into a fresh session, once.

A ``SessionStart`` hook cannot block a session from starting -- exit 2 only
shows stderr, and the session proceeds regardless -- so this is a loader,
never a gate. It injects context by printing the handoff, wrapped in the
one JSON shape the harness reads, to stdout.

It injects only on ``startup`` and ``clear``: those are the sessions with no
context of their own. ``resume``, ``compact`` and ``fork`` already carry the
prior conversation, so injecting there pays the handoff's cost twice for
nothing. A missing or unrecognized reason injects nothing.

Like every hook in this repo, this one FAILS OPEN: any error -- garbage on
stdin, a missing or unreadable handoff, a stale one -- prints nothing and
exits 0. A hook that raises blocks nothing (it cannot), but a hook that
prints noise on every session start is worse than one that occasionally
says nothing when it had something to say.

Run with no payload on stdin at all -- a human at a terminal, not the
harness -- ``main`` falls back to reading the handoff plainly, without
consuming it, so the operator can look without spending the one chance a
fresh session gets to see it.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path
from typing import TextIO

from .handoff import DEFAULT_HANDOFF_PATH, NOTES_HEADING, consume, read

__all__ = ["INJECT_REASONS", "preamble", "main"]

# resume/compact/fork sessions already carry the prior context; injecting
# there pays for the handoff twice for nothing.
INJECT_REASONS = {"startup", "clear"}


def _format_age(age_hours: float) -> str:
    if age_hours < 1:
        minutes = max(1, round(age_hours * 60))
        return f"{minutes} minute{'s' if minutes != 1 else ''}"
    hours = round(age_hours)
    return f"{hours} hour{'s' if hours != 1 else ''}"


def preamble(age_hours: float) -> str:
    """Two lines that tell a fresh session what it is looking at.

    Names the handoff as written by a session that has already ended, with
    its age; says which section to trust; and tells the reader to set it
    aside if this session is starting unrelated work.
    """
    section = NOTES_HEADING.lstrip("#").strip()
    return (
        f"The handoff below was written by a session that has already "
        f"ended, about {_format_age(age_hours)} ago.\n"
        f'Trust the "{section}" section above everything else here -- and '
        f"if this session is starting unrelated work, set this handoff "
        f"aside rather than act on it."
    )


def _parse_out(args: list[str]) -> Path:
    if "--out" in args:
        i = args.index("--out")
        if i + 1 < len(args):
            return Path(args[i + 1])
    return DEFAULT_HANDOFF_PATH


def main(argv: list[str] | None = None, stdin: TextIO | None = None) -> int:
    args = list(argv or [])
    out = _parse_out(args)
    stream = stdin if stdin is not None else sys.stdin
    try:
        raw = stream.read()
    except Exception:
        return 0

    if not raw or not raw.strip():
        # Hand-run with nothing piped in: look, don't consume.
        text = read(out)
        if text is not None:
            print(text, end="" if text.endswith("\n") else "\n")
        return 0

    try:
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            return 0
        # The harness names the reason in "source" -- measured from the
        # 2.1.246 binary, which constructs
        #   {..., hook_event_name:"SessionStart", source:t, agent_type:...}
        # and carries no "session_start_reason" string anywhere. That was
        # this hook's original guess, and it silently never fired: the key
        # was absent, so every real session start fell straight through the
        # fail-open path. Do not rename this without a captured payload.
        reason = payload.get("source")
        if reason not in INJECT_REASONS:
            return 0
        mtime = dt.datetime.fromtimestamp(out.stat().st_mtime, tz=dt.timezone.utc)
        text = consume(out)
        if text is None:
            return 0
        age_hours = (
            dt.datetime.now(dt.timezone.utc) - mtime
        ).total_seconds() / 3600
        message = preamble(age_hours) + "\n\n" + text
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": message,
            }
        }))
        return 0
    except Exception:
        # Fail open: a raising hook still cannot block the session, and
        # printing noise here is worse than saying nothing.
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
