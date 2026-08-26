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

**And the probe cannot answer the question an operator actually asks.** It
says the hook EMITTED a handoff. It says nothing about whether a session
RECEIVED one, and those two failed apart once already -- which is #29. So
``--status`` joins the probe log to the session transcripts: the harness
writes the injected text into the transcript as an ``attachment`` record
stamped at the session's start, so a probe entry saying ``injected`` at time
T is confirmed by an attachment carrying ``RECEIPT_MARKER`` at time T. An
entry with no matching record means the hook emitted and the session did not
take it, and ``--status`` says so rather than reporting the log as a pass.

**An injection also announces itself, because a loader nobody can see working
is indistinguishable from a broken one.** ``additionalContext`` is injected
silently: nothing on screen when it works and nothing when it does not. One
line goes out on ``systemMessage`` and on stderr -- both, because WHICH ONE
THE OPERATOR SEES IS STILL NOT MEASURED. What IS measured, 2026-08-26: the
operator confirmed seeing the line at that day's 20:01 UTC ``clear`` start, so
an announcement does render under SessionStart at exit 0. Both channels were
emitted on that start and neither was suppressed, so neither is credited alone
and both stay. The probe records which were emitted. The four silences stay
silent: a line on every session start, most of them saying nothing happened,
is how a hook gets turned off.

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

from .handoff import (
    ARCHIVE_SUFFIX,
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
    "RECEIPT_MARKER",
    "classify",
    "preamble",
    "probe_entries",
    "receipts",
    "status",
    "format_status",
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


# The first words of every injection, and the ONLY thing a later session can
# match on to prove the handoff arrived. `preamble` is built from it so the two
# cannot drift apart; `test_resume` pins that they agree.
RECEIPT_MARKER = "The handoff below was written by a session that has already ended"


def preamble(age_hours: float) -> str:
    """Two lines that tell a fresh session what it is looking at.

    Names the handoff as written by a session that has already ended, with
    its age; says which section to trust; and tells the reader to set it
    aside if this session is starting unrelated work.
    """
    section = NOTES_HEADING.lstrip("#").strip()
    return (
        f"{RECEIPT_MARKER}, about {_format_age(age_hours)} ago.\n"
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
    announced: tuple[str, ...] = (),
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
            # Which user-visible channels this start emitted on. Recorded
            # because WHICH ONE THE OPERATOR SEES IS UNMEASURED, and a claim
            # about it should rest on a log entry rather than on the docs.
            "announced": list(announced),
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


# ---------------------------------------------------------------------------
# Diagnostics. The probe answers "did the hook emit a handoff"; it does NOT
# answer "did a session receive one", and those are two different questions
# that failed apart once already (#29: the hook declined every real start and
# said nothing about it). An operator cannot see the difference either way,
# because `additionalContext` is injected silently -- there is nothing on the
# screen when it works and nothing when it does not.
#
# So the receipt is read from the SESSION's own transcript, not from the
# hook's log. The harness writes the injected text into the transcript as an
# `attachment` record stamped at the session's start, so a probe entry that
# says `injected` at time T is confirmed by an attachment carrying
# RECEIPT_MARKER at time T. Agreement is evidence; a probe entry with no
# matching attachment is the failure mode this exists to make visible.


def probe_entries(path: Path | None = None, limit: int | None = None) -> list[dict]:
    """The probe log, newest last. Unreadable or corrupt lines are skipped
    rather than raised on: a diagnostic that dies on its own log is worse than
    one that reports a short list."""
    path = path or PROBE_PATH
    entries: list[dict] = []
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except ValueError:
                continue
            if isinstance(payload, dict):
                entries.append(payload)
    except OSError:
        return []
    return entries[-limit:] if limit else entries


def receipts(transcripts: Path | None = None) -> list[dict]:
    """Every session transcript that actually CARRIES an injected handoff.

    Matches on `RECEIPT_MARKER` and reports the session id and the timestamp
    of the record it was found in, so it can be joined to a probe entry by
    time. Only the first hit per transcript counts: a session that later
    quotes its own handoff back (this one does) must not read as two loads.
    """
    from .discovery import main_transcript_dir
    from .session import project_slug

    root = transcripts or (main_transcript_dir() / project_slug(Path.cwd()))
    found: list[dict] = []
    try:
        paths = sorted(root.glob("*.jsonl"))
    except OSError:
        return []
    for path in paths:
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line in lines:
            if RECEIPT_MARKER not in line:
                continue
            try:
                payload = json.loads(line)
            except ValueError:
                continue
            if payload.get("type") != "attachment":
                continue
            found.append({"session_id": path.stem,
                          "at": payload.get("timestamp"),
                          "path": str(path)})
            break
    return found


def _within(a: str | None, b: str | None, seconds: float = 120.0) -> bool:
    if not a or not b:
        return False
    try:
        first = dt.datetime.fromisoformat(a)
        second = dt.datetime.fromisoformat(b)
    except ValueError:
        return False
    return abs((first - second).total_seconds()) <= seconds


def status(out: Path | None = None, probe_path: Path | None = None,
           transcripts: Path | None = None, limit: int = 5) -> dict:
    """What the loader did, and whether a session can be shown to have got it."""
    out = out or DEFAULT_HANDOFF_PATH
    archived = out.with_name(out.name + ARCHIVE_SUFFIX)
    now = dt.datetime.now(dt.timezone.utc)
    got = receipts(transcripts)

    entries = []
    for entry in probe_entries(probe_path, limit=limit):
        match = next((r for r in got if _within(entry.get("observed"), r.get("at"))), None)
        entries.append({**entry,
                        "received_by": match["session_id"] if match else None,
                        "received": match is not None})
    return {
        "handoff": {"path": str(out), "exists": out.exists(),
                    "age_hours": _age_hours(out, now),
                    "stale": (lambda a: a is not None and a > MAX_HANDOFF_AGE_HOURS)(
                        _age_hours(out, now))},
        "archived": {"path": str(archived), "exists": archived.exists(),
                     "age_hours": _age_hours(archived, now)},
        "probe_path": str(probe_path or PROBE_PATH),
        "recent": entries,
        "receipts_seen": len(got),
    }


def format_status(report: dict) -> str:
    """The report an operator reads, which has to answer one question: did a
    session receive the handoff, and if not, which of the five outcomes was it."""
    lines: list[str] = []
    handoff, archived = report["handoff"], report["archived"]

    if handoff["exists"]:
        age = handoff["age_hours"] or 0
        state = "STALE, the hook will decline it" if handoff["stale"] else "waiting to be loaded"
        lines.append(f"handoff   {handoff['path']}  {_format_age(age)} old -- {state}")
    else:
        lines.append(f"handoff   none at {handoff['path']}"
                     + ("  (consumed -- see archived below)" if archived["exists"] else ""))
    if archived["exists"]:
        lines.append(f"archived  {archived['path']}  "
                     f"{_format_age(archived['age_hours'] or 0)} old -- the last one consumed")

    recent = report["recent"]
    if not recent:
        lines.append(f"probe     no entries in {report['probe_path']} -- "
                     "the hook has not run, or has never run with --probe")
        return "\n".join(lines)

    lines.append("")
    lines.append(f"{'when':20s} {'decision':22s} {'chars':>7s}  received by")
    for entry in recent:
        when = (entry.get("observed") or "")[:19].replace("T", " ")
        if entry.get("received"):
            got = entry["received_by"][:8]
        elif entry.get("decision") == "injected":
            got = "NOT FOUND IN ANY TRANSCRIPT"
        else:
            got = "-"
        lines.append(f"{when:20s} {str(entry.get('decision')):22s} "
                     f"{entry.get('injected_chars') or 0:7d}  {got}")

    injected = [e for e in recent if e.get("decision") == "injected"]
    confirmed = [e for e in injected if e.get("received")]
    lines.append("")
    if not injected:
        lines.append("No injection in the entries above. The decision column names which of "
                     "the five outcomes it was; four of them are silences.")
    elif len(confirmed) == len(injected):
        # Whether the operator SAW anything is a separate question from whether
        # a session RECEIVED anything, and this report used to answer only the
        # second while asserting the first was silent. Since 2026-08-26 an
        # injection announces itself and records that it did; say which.
        announced = [e for e in injected if e.get("announced")]
        lines.append(f"{len(confirmed)}/{len(injected)} injections are CONFIRMED in a session "
                     "transcript.")
        if not announced:
            lines.append("None of them announced itself, so nothing appeared on screen when they "
                         "worked -- this report is the only evidence there is.")
        elif len(announced) == len(injected):
            lines.append("Each announced itself on screen as it loaded (operator-confirmed "
                         "visible, 2026-08-26), so this report corroborates that line rather "
                         "than standing in for it.")
        else:
            lines.append(f"{len(announced)}/{len(injected)} announced themselves on screen; the "
                         "rest predate the announcement and loaded with nothing visible.")
    else:
        lines.append(f"ONLY {len(confirmed)}/{len(injected)} injections are confirmed. An entry "
                     "the hook logged as injected with no matching transcript record means the "
                     "hook emitted it and the session did not take it -- report that, do not "
                     "assume the log.")
    return "\n".join(lines)


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

    if "--status" in args:
        # An operator asking a question, not a session start: read nothing from
        # stdin, consume nothing, record nothing.
        print(format_status(status(out)))
        return 0

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
            _probe(payload, decision, len(message or ""), age_hours,
                   ("systemMessage", "stderr") if message is not None else ())

        if message is None:
            return 0

        # THE ANNOUNCEMENT, and it is deliberately two channels.
        #
        # `additionalContext` is injected SILENTLY: nothing appears on screen
        # when it works and nothing when it does not, so an operator cannot
        # tell a working loader from #29's broken one. That is not a cosmetic
        # gap -- it is the same gap that let this hook decline every real
        # session for a day.
        #
        # SETTLED 2026-08-26, half of it: the operator confirmed seeing this
        # line at the 20:01 UTC `clear` start. So an announcement DOES render
        # under SessionStart at exit 0 -- the invisibility that hid #29 for a
        # day is closed. WHICH channel rendered it is still unknown: both were
        # emitted on that start and neither was suppressed to isolate the
        # other. Both stay until an isolating run says one is dead weight.
        announcement = (
            f"[agent-yield] handoff loaded: {len(message):,} chars, written "
            f"{_format_age(age_hours) if age_hours is not None else 'unknown age'} "
            f"ago. `agent-yield resume --status` to confirm receipt."
        )
        print(json.dumps({
            "systemMessage": announcement,
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": message,
            }
        }))
        try:
            print(announcement, file=sys.stderr)
        except Exception:
            pass
        return 0
    except Exception:
        # Fail open: a raising hook still cannot block the session, and
        # printing noise here is worse than saying nothing.
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
