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

**But failing open on a loader is indistinguishable from having nothing to
load** (issue #29), and that is how this hook stayed broken for its first
day alive: it read a key the harness does not send, declined every real
session start, and said nothing about it. So the outcomes are named. There
are five of them, four of which are silences, and they are not the same event:

    injected                the handoff went into the session
    no_handoff              nothing at the path -- the ordinary case
    stale                   older than 24h; left on disk, readable by hand
    reason_not_injecting    resume/compact/fork, which carry their own context
    unparseable_payload     stdin was not a JSON object

``--probe`` appends the decision to ``.agent-yield/resume-probe.jsonl`` so a
later session can read what this one could not watch. It records the payload
*keys*, never their values: ``session_title`` is a value this hook has no
business writing down, and the handoff text is the very thing being loaded.

Run with no payload on stdin at all -- a human at a terminal, not the
harness -- ``main`` falls back to reading the handoff plainly, without
consuming it, so the operator can look without spending the one chance a
fresh session gets to see it.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import TextIO

from .handoff import (
    DEFAULT_HANDOFF_PATH,
    MAX_HANDOFF_AGE_HOURS,
    NOTES_HEADING,
    consume,
    read,
)
from .hookio import read_payload

__all__ = [
    "INJECT_REASONS",
    "PROBE_PATH",
    "REASON_KEY",
    "DECISIONS",
    "classify",
    "preamble",
    "main",
]

# resume/compact/fork sessions already carry the prior context; injecting
# there pays for the handoff twice for nothing.
INJECT_REASONS = {"startup", "clear"}

# The harness names the session-start reason here. Measured from the 2.1.246
# binary, which constructs
#     {..., hook_event_name:"SessionStart", source:t, agent_type:o, model:s}
# and carries no "session_start_reason" string anywhere -- that was this
# hook's original guess, and it silently never fired. Do not rename this
# without a captured payload; see docs/design.md and issue #29.
REASON_KEY = "source"

PROBE_PATH = Path(".agent-yield") / "resume-probe.jsonl"

# The five outcomes. Four of them are silences, and before #29 they were one.
DECISIONS = (
    "injected",
    "no_handoff",
    "stale",
    "reason_not_injecting",
    "unparseable_payload",
)

# `session_title` is a value; the probe records keys, so it needs no
# exclusion list -- but say why, so nobody starts logging values later.
_VALUE_SAFE_KEYS = ("hook_event_name", REASON_KEY)


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


def _age_hours(path: Path, now: dt.datetime) -> float | None:
    try:
        mtime = dt.datetime.fromtimestamp(
            path.stat().st_mtime, tz=dt.timezone.utc
        )
    except OSError:
        return None
    return (now - mtime).total_seconds() / 3600


def classify(
    payload: object,
    out: Path,
    now: dt.datetime | None = None,
) -> tuple[str, str | None, float | None]:
    """Decide what this session start gets, and name the reason.

    Returns ``(decision, message, age_hours)``. ``message`` is the text to
    inject and is non-None only for ``"injected"``. This is the only place
    that consumes the handoff, and it consumes it exactly when it injects
    it -- which is what makes injection once-only with no state file.
    """
    moment = now if now is not None else dt.datetime.now(dt.timezone.utc)

    if not isinstance(payload, dict):
        return "unparseable_payload", None, None

    if payload.get(REASON_KEY) not in INJECT_REASONS:
        return "reason_not_injecting", None, None

    age_hours = _age_hours(out, moment)
    if age_hours is None:
        return "no_handoff", None, None
    if age_hours > MAX_HANDOFF_AGE_HOURS:
        # Left where it is, deliberately: unreadable by the hook, readable
        # by a human with `agent-yield resume`.
        return "stale", None, age_hours

    text = consume(out, now=moment)
    if text is None:
        return "no_handoff", None, age_hours
    return "injected", preamble(age_hours) + "\n\n" + text, age_hours


def _probe(
    payload: object,
    decision: str,
    injected_chars: int,
    age_hours: float | None,
) -> None:
    """Record the decision, for the session that can finally read it.

    Never raises: a probe that breaks the hook it is measuring measures the
    hook's failure mode instead of its behaviour.

    Records payload KEYS and never their values. `session_title` and
    `model` arrive here and are nobody's business downstream; the handoff
    text is the thing being loaded, so only its length is recorded.
    """
    try:
        entry: dict[str, object] = {
            "observed": dt.datetime.now(dt.timezone.utc).isoformat(),
            "decision": decision,
            "injected": decision == "injected",
            "injected_chars": injected_chars,
            "handoff_age_hours": (
                round(age_hours, 3) if age_hours is not None else None
            ),
        }
        if isinstance(payload, dict):
            entry["keys"] = sorted(payload)
            entry["has_reason_key"] = REASON_KEY in payload
            for key in _VALUE_SAFE_KEYS:
                entry[key] = payload.get(key)
        else:
            entry["keys"] = None
            entry["has_reason_key"] = False
        PROBE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with PROBE_PATH.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(entry) + "\n")
    except Exception:
        return


def _parse_out(args: list[str]) -> Path:
    if "--out" in args:
        i = args.index("--out")
        if i + 1 < len(args):
            return Path(args[i + 1])
    return DEFAULT_HANDOFF_PATH


def main(argv: list[str] | None = None, stdin: TextIO | None = None) -> int:
    args = list(argv or [])
    out = _parse_out(args)
    probing = "--probe" in args
    try:
        raw = read_payload(stdin)
    except Exception:
        return 0

    if not raw or not raw.strip():
        # Hand-run with nothing piped in: look, don't consume, don't probe.
        # This is an operator reading, not a session start, and recording it
        # would put events in the log that never happened to a session.
        text = read(out)
        if text is not None:
            print(text, end="" if text.endswith("\n") else "\n")
        return 0

    try:
        try:
            payload = json.loads(raw)
        except ValueError:
            payload = None

        decision, message, age_hours = classify(payload, out)

        if probing:
            _probe(payload, decision, len(message or ""), age_hours)

        if message is None:
            return 0

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
