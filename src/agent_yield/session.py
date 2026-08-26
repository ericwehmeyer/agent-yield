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

from dataclasses import dataclass
from pathlib import Path

from .discovery import find_transcripts, main_transcript_dir
from .ingest import load_records, total_usage
from .usage import Usage

__all__ = [
    "SessionStats",
    "find_session",
    "session_stats",
    "restart_advice",
]


def _context(record) -> int:
    """Context carried on one call: everything the model had to read."""
    usage = record.usage
    return (
        usage.input_tokens
        + usage.cache_read_tokens
        + usage.cache_creation_tokens
    )


@dataclass(frozen=True)
class SessionStats:
    """What one main session's transcript measures.

    ``opening_context_per_call``, ``context_per_call`` and ``growth`` are
    ``None`` when the session is too short to measure them.
    """

    path: Path
    calls: int
    opening_context_per_call: float | None
    current_context: int
    context_per_call: float | None
    growth: float | None
    total: Usage


def find_session(session_id: str | None = None, root: Path | None = None) -> Path | None:
    """The transcript for ``session_id``, or the most recently modified one.

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

    def modified(path: Path) -> float:
        try:
            return path.stat().st_mtime
        except OSError:
            return float("-inf")

    return max(paths, key=modified)


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

    return SessionStats(
        path=path,
        calls=calls,
        opening_context_per_call=opening,
        current_context=current_context,
        context_per_call=context_per_call,
        growth=growth,
        total=total_usage(main),
    )


def restart_advice(stats: SessionStats, factor: float = 2.0) -> str | None:
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
