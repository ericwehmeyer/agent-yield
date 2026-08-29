"""Measure the session you are in, live.

Context on any one call is ``input_tokens + cache_read_tokens +
cache_creation_tokens``.  A long parent session pays that on every call, so
context/call climbs and late calls cost several times what early ones did.
The lever is restarting the parent once context/call has doubled from the
session's opening calls -- a trigger measurable from the transcript alone,
with no knowledge of the model's context-window size.

Everything unmeasurable is ``None``, never ``0``: a zero would read as "it
was free".  This module is read-only; it never writes a file.
"""

from __future__ import annotations

import datetime as dt
import os
from dataclasses import dataclass
from pathlib import Path

from .discovery import find_transcripts, main_transcript_dir
from .ingest import incomplete_calls, load_records, total_usage
from .pricing import Priced, price_records
from .thresholds import COST_LADDER, RESTART_FACTOR, cost_band
from .usage import Usage

__all__ = [
    "SessionStats",
    "find_session",
    "resolve_transcript",
    "session_stats",
    "restart_advice",
    "cost_crossings",
]


def _context(record) -> int:
    """Context carried on one call: everything the model had to read.

    The definition moved to `CallRecord.context` when `report.py` needed the
    same quantity to compute a day's band shares. Kept as a name here because
    this module reads better with it.
    """
    return record.context


@dataclass(frozen=True)
class SessionStats:
    """What one main session's transcript measures.

    ``opening_context_per_call``, ``context_per_call`` and ``growth`` are
    ``None`` when the session is too short to measure them.

    ``started`` is the timestamp of the session's first main-thread call.
    A handoff needs it to ask git what landed *during this session* rather
    than listing the whole branch as if the session had done it.

    ``priced`` is list dollars for the main thread, and ``subagent_priced``
    for this transcript's sidechain calls. They are kept APART for the reason
    ``cost_band`` keeps the two populations apart: the main figure answers
    "what does continuing this thread cost", and folding an agent's spend into
    it answers a different question with the same number. Both are ``None``
    when nothing could be priced -- 0.0 would read as "it was free".
    """

    path: Path
    calls: int
    opening_context_per_call: float | None
    current_context: int
    context_per_call: float | None
    growth: float | None
    total: Usage
    started: dt.datetime | None = None
    contexts: tuple[int, ...] = ()
    priced: Priced | None = None
    subagent_priced: Priced | None = None
    incomplete_calls: int = 0
    """Main-thread calls whose group held no terminal record. Their
    `output_tokens` is a lower bound, so `priced` is one too."""


def project_slug(cwd: Path | None = None) -> str:
    """The transcript directory name Claude Code derives from a cwd.

    Measured against the real tree on both platforms:
    `/Users/x/IdeaProjects/agent-yield` becomes `-Users-x-IdeaProjects-agent-yield`,
    and `C:\\Users\\ewehm\\repos\\agent-yield` becomes
    `C--Users-ewehm-repos-agent-yield` -- the doubled dash is the drive colon
    followed by the first backslash.

    Backslash and colon are not decoration. Without them the slug returned a
    Windows path unchanged, nothing ever matched `parent.name`, and
    `find_session` returned None for every session on that machine.
    """
    base = Path(cwd) if cwd is not None else Path.cwd()
    return (
        str(base)
        .replace("/", "-")
        .replace("\\", "-")
        .replace(":", "-")
        .replace(".", "-")
        .replace("_", "-")
    )


def find_session(
    session_id: str | None = None,
    root: Path | None = None,
    cwd: Path | None = None,
) -> Path | None:
    """The transcript for ``session_id``, or this project's most recent one.

    With a ``session_id`` the match is exact. Without one, candidates are
    restricted to the project directory for ``cwd`` (default: the process
    working directory) -- see the comment below on why the unrestricted
    fallback is a bug rather than a convenience.

    Returns ``None`` when nothing matches; never raises.
    """
    try:
        base = root if root is not None else main_transcript_dir()
    except Exception:
        return None
    if base is None:
        return None

    try:
        paths = find_transcripts([Path(base)])
    except Exception:
        return None
    if not paths:
        return None

    if session_id is not None:
        wanted = f"{session_id}.jsonl"
        for path in paths:
            if path.name == wanted:
                return path
        return None

    # Scope to THIS project before falling back to "most recent". Without
    # this the fallback reaches across every project on the machine, and with
    # two sessions open it routinely picks the other one -- measured 2026-08-25:
    # `agent-yield status` reported 357 calls, 535,788 context and 10.6x growth
    # for a 109-call session, because a photo-editing session in another repo
    # had written to its transcript a second earlier. It printed the right
    # session id while doing it, which is not a defence: `status` exits 1 to
    # mean "leave", and it was reading someone else's cost to decide.
    #
    # This is the same bug `boundary._stats_for` was fixed for, one function
    # over, and the fix there was the same: measure the session you can
    # identify, or measure nothing. A cross-project fallback is never right --
    # there is no sense in which another repo's session is "this" session.
    #
    # `normcase` and not `.lower()`, and it is the whole of #51. Windows does
    # not canonicalise path case -- `os.getcwd()` returns whatever case was
    # typed to enter the directory -- so a lowercase drive letter yields a
    # slug that can never equal the `C--...` directory Claude Code wrote, and
    # `find_session` returned None for the entire project while `status`
    # printed nothing and exited 0. `normcase` folds on Windows and is the
    # identity on POSIX, where `/repo/Mine` and `/repo/mine` really are two
    # projects and folding would hand one of them the other's cost. (It also
    # maps `/` to `\` on Windows; a slug contains neither, so that is inert.)
    # Only when the root was NOT given explicitly: `--transcripts <dir>` is a
    # caller who has already scoped the search, and second-guessing it would
    # make the flag useless.
    if root is None:
        wanted_slug = os.path.normcase(project_slug(cwd))
        scoped = [
            p for p in paths if os.path.normcase(p.parent.name) == wanted_slug
        ]
        if not scoped:
            return None
        paths = scoped

    def modified(path: Path) -> float:
        try:
            return path.stat().st_mtime
        except OSError:
            return float("-inf")

    return max(paths, key=modified)


def resolve_transcript(payload: dict) -> tuple[Path | None, str]:
    """The transcript for the session a hook payload came from, and how.

    MEASURED 2026-08-26 01:31 UTC, `UserPromptSubmit` on macOS, one prompt
    (`.agent-yield/boundary-probe.jsonl`, issue #22): the payload carries
    ``cwd``, ``hook_event_name``, ``permission_mode``, ``prompt_id``,
    ``session_id``, ``transcript_path`` and ``prompt``. So the live session
    is identified twice over, and the guessing the boundary shipped with is
    no longer needed.

    The route is returned alongside the path so a probe can record which one
    fired without recording the path itself.

    **It never widens to "the most recently modified transcript".** That
    fallback is what makes a hook measure the wrong session on any machine
    running two at once, and an enforcing boundary aimed at the wrong
    session is worse than no boundary. Unidentified means ``None``, which
    every caller here treats as "say nothing".
    """
    raw = payload.get("transcript_path")
    if isinstance(raw, str) and raw:
        candidate = Path(raw)
        try:
            exists = candidate.exists()
        except OSError:
            exists = False
        if exists:
            return candidate, "transcript_path"

    session_id = payload.get("session_id") or payload.get("sessionId")
    if isinstance(session_id, str) and session_id:
        found = find_session(session_id)
        if found is not None:
            return found, "session_id"
        return None, "session_id_unknown"

    return None, "unidentified"


def session_stats(path: Path, baseline_calls: int = 10) -> SessionStats:
    """Measure one session's transcript, main-session calls only.

    Subagent (sidechain) records belong to their own agents; counting them
    here would read a sidechain's context as the parent's own.
    """
    try:
        records = load_records([path])
    except Exception:
        records = []

    main = sorted(
        (r for r in records if not r.is_subagent),
        key=lambda r: r.timestamp,
    )
    calls = len(main)

    if calls == 0:
        return SessionStats(
            path=path,
            calls=0,
            opening_context_per_call=None,
            current_context=0,
            context_per_call=None,
            growth=None,
            total=Usage.zero(),
            started=None,
            contexts=(),
        )

    contexts = [_context(r) for r in main]
    current_context = contexts[-1]
    context_per_call = sum(contexts) / calls

    opening: float | None = None
    growth: float | None = None
    if baseline_calls > 0 and calls > baseline_calls:
        opening = sum(contexts[:baseline_calls]) / baseline_calls
        if opening > 0:
            growth = current_context / opening
        else:
            opening = None

    # Priced from the same `main` walk the tokens come from, so the dollars and
    # the token line are two readings of one population rather than two
    # measurements. The sidechain walk is the records `main` filtered OUT.
    return SessionStats(
        path=path,
        calls=calls,
        opening_context_per_call=opening,
        current_context=current_context,
        context_per_call=context_per_call,
        growth=growth,
        total=total_usage(main),
        started=main[0].timestamp,
        contexts=tuple(contexts),
        priced=price_records(main),
        subagent_priced=price_records([r for r in records if r.is_subagent]),
        incomplete_calls=incomplete_calls(main),
    )


def cost_crossings(stats: SessionStats) -> dict[str, int]:
    """Call number at which each cost band was first entered.

    Section 5 says each band fires once per session, at the crossing. That
    needs no hidden state: the transcript already records where the session
    crossed, so the crossing is measured rather than remembered. Bands never
    entered are absent from the mapping -- never present with a 0, which
    would read as "crossed on the first call".
    """
    seen: dict[str, int] = {}
    for index, context in enumerate(stats.contexts, start=1):
        band = cost_band(context)
        if band == "cheap":
            continue
        # A session that opens in the restart band crossed dispatch too -- on
        # its first call. Recording only the band it landed in would report
        # "never past dispatch" for exactly the sessions the concentration
        # finding is about, which open expensive rather than growing into it.
        for name in COST_LADDER[: COST_LADDER.index(band) + 1]:
            seen.setdefault(name, index)
    return seen


def restart_advice(stats: SessionStats, factor: float = RESTART_FACTOR) -> str | None:
    """One line naming the real numbers, or ``None`` if no restart is due."""
    growth = stats.growth
    opening = stats.opening_context_per_call
    if growth is None or opening is None:
        return None
    if growth < factor:
        return None
    return (
        f"context/call has grown {growth:.1f}x "
        f"({round(opening):,} -> {stats.current_context:,} "
        f"over {stats.calls:,} calls); a fresh session costs nothing "
        f"and this one costs ~{round(growth)}x per call"
    )
