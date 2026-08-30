"""One row per parent session: how long it ran, and what a call cost in it.

Ten parent sessions in this repo had a median of 104.5 calls and 85 wall-clock
minutes, range 26 to 829 minutes (#161). Those figures were computed by hand
from `.agent-yield/calls.jsonl` once and never again, so nothing could say
whether a dispatcher session is getting shorter, denser, or neither as the
method changes. This module is that reporter.

Two things here are load-bearing and neither is a layout preference.

**A call is a distinct `requestId`, not a usage-bearing entry.** `calls.jsonl`
is already collapsed to one row per `(message.id, requestId)` pair by
`records.dedup`, and that is not one row per API call: Claude Code writes a
message per assistant turn and several turns share one request. Counting rows
overstates calls 2.6x on this box (`docs/working-method.md` 7.2). A session
report built on the row count would put every figure in the table out by that
factor while looking entirely reasonable.

**There is no normalised column here, and that is the finding, not an
omission.** Calls per merged commit, minutes per closed issue and calls to
first commit were all proposed in #161 and none was decided. #76 is this
repo's standing case of what shipping one anyway does: a ranked figure that
renders the quietest day as the most efficient. Until the operator picks a
denominator, the rows carry raw quantities, ordered by start time, and the
reader does the dividing.

`render` prints the corpus window above the table for the same reason. The
last row in the corpus on both machines is 2026-08-26T22:39:12Z, because
`ingest` only runs when someone remembers to run it; a series that describes a
four-day-old corpus without saying so is worse than no series. The window is
printed whether it is stale or fresh, so that no figure can be quoted without
its denominator in time.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Iterable, Sequence

from .records import CallRecord

__all__ = [
    "DEFAULT_BASELINE_CALLS",
    "SessionRow",
    "distinct_calls",
    "corpus_window",
    "build_sessions",
    "render",
    "render_window",
]

# Chosen, not measured: the same 10 `agent-yield status` averages its opening
# context over. One call is noise -- a single tool result can double the
# context read on one call -- and a tenth of a 104-call session is a window
# small enough that a session's shape still shows through it.
DEFAULT_BASELINE_CALLS = 10


@dataclass(frozen=True)
class SessionRow:
    """One parent session, as `calls.jsonl` recorded it.

    `open_context`, `close_context` and `growth` are `None` for a session too
    short to hold two disjoint baseline windows. `None` and not 0.0: a session
    whose growth was never measurable must not read as one that did not grow.
    """

    session_id: str
    started: dt.datetime
    ended: dt.datetime
    calls: int
    open_context: float | None
    close_context: float | None
    growth: float | None

    @property
    def minutes(self) -> float:
        return (self.ended - self.started).total_seconds() / 60.0


def distinct_calls(records: Iterable[CallRecord]) -> list[CallRecord]:
    """One record per API call, keyed on `request_id`, in timestamp order.

    Records sharing a `requestId` carry identical input and cache figures --
    that is why `CallRecord.context` can be read off any one of them -- so the
    first in time is kept and the rest dropped.

    A record with no `request_id` cannot be grouped and is kept as its own
    call, which is `records.dedup`'s rule and for its reason: undercounting is
    the error this tool exists to prevent.
    """
    ordered = sorted(records, key=lambda r: r.timestamp)
    kept: list[CallRecord] = []
    seen: set[str] = set()
    for record in ordered:
        if record.request_id:
            if record.request_id in seen:
                continue
            seen.add(record.request_id)
        kept.append(record)
    return kept


def corpus_window(
    records: Sequence[CallRecord],
) -> tuple[dt.datetime | None, dt.datetime | None]:
    """First and last timestamp of the corpus that was read.

    Over every record loaded, subagent rows included: this answers "what did
    this file cover", not "what is in the table", and the two differ.
    """
    if not records:
        return (None, None)
    stamps = [r.timestamp for r in records]
    return (min(stamps), max(stamps))


def build_sessions(
    records: Iterable[CallRecord],
    baseline_calls: int = DEFAULT_BASELINE_CALLS,
) -> list[SessionRow]:
    """Parent sessions, one row each, ordered by start time.

    Ordered by time and by nothing else. The series IS the ordering: a table
    sorted by duration or by call count answers "which session was biggest",
    which no one asked, and hides the only question #161 poses -- whether the
    numbers are moving.

    Subagent records are excluded before grouping. A sidechain's context is the
    agent's, and folding it into the parent's row reads a dispatch's cost as
    the dispatcher's own. Records with no `session_id` cannot be grouped and
    are dropped; `render` says how many, because a silent drop is how a
    denominator goes wrong.
    """
    groups: dict[str, list[CallRecord]] = {}
    for record in records:
        if record.is_subagent or not record.session_id:
            continue
        groups.setdefault(record.session_id, []).append(record)

    rows: list[SessionRow] = []
    for session_id, group in groups.items():
        calls = distinct_calls(group)
        if not calls:
            continue
        contexts = [c.context for c in calls]
        open_context = close_context = growth = None
        # Two DISJOINT windows. Overlapping them on a 12-call session would
        # divide a mean by a mean that shares eight of its terms, and report a
        # growth factor of ~1.0 for a session that had grown.
        if baseline_calls > 0 and len(contexts) >= 2 * baseline_calls:
            open_context = sum(contexts[:baseline_calls]) / baseline_calls
            close_context = sum(contexts[-baseline_calls:]) / baseline_calls
            if open_context > 0:
                growth = close_context / open_context
            else:
                open_context = None
                close_context = None
        rows.append(SessionRow(
            session_id=session_id,
            started=calls[0].timestamp,
            ended=calls[-1].timestamp,
            calls=len(calls),
            open_context=open_context,
            close_context=close_context,
            growth=growth,
        ))
    return sorted(rows, key=lambda row: row.started)


def _utc(stamp: dt.datetime) -> dt.datetime:
    if stamp.tzinfo is None:
        return stamp.replace(tzinfo=dt.timezone.utc)
    return stamp.astimezone(dt.timezone.utc)


def _stamp(stamp: dt.datetime) -> str:
    return _utc(stamp).strftime("%Y-%m-%dT%H:%M:%SZ")


def _num(value: float | None) -> str:
    """A number, or `-`. Never `0` for something unmeasured."""
    return "-" if value is None else f"{round(value):,}"


def render_window(
    records: Sequence[CallRecord],
    source: str,
    today: dt.datetime | None = None,
) -> str:
    """The corpus bound, printed above the table and never optional.

    `ingest` is a manual subcommand, so the corpus ends whenever someone last
    ran it -- 2026-08-26T22:39:12Z on both machines when #161 was filed, four
    days before the sessions anyone was reasoning about. The age is printed as
    a measured number rather than a warning threshold: the reader decides what
    is stale, but cannot fail to see the window.
    """
    first, last = corpus_window(records)
    if first is None or last is None:
        return f"corpus: no calls in {source} -- run `agent-yield ingest` first"
    now = _utc(today) if today is not None else dt.datetime.now(dt.timezone.utc)
    age_days = (now - _utc(last)).total_seconds() / 86400.0
    return (
        f"corpus: {len(records):,} records in {source}, "
        f"{_stamp(first)} to {_stamp(last)} "
        f"({age_days:.1f} days before this run)"
    )


def render(rows: Sequence[SessionRow], ungrouped: int = 0) -> str:
    """The table. Raw columns, time order, no denominator.

    `calls` is distinct requests. `minutes` is wall clock between the first and
    last call, which measures the session's span and not the time anyone spent
    in it -- a session left open over lunch reports the lunch.
    """
    header = (
        f"{'session':<10}{'start (UTC)':<18}{'calls':>7}{'minutes':>9}"
        f"{'ctx/call open':>15}{'ctx/call close':>16}{'growth':>8}"
    )
    lines = [header, "-" * len(header)]
    for row in rows:
        growth = "-" if row.growth is None else f"{row.growth:.1f}x"
        lines.append(
            f"{row.session_id[:8]:<10}"
            f"{_utc(row.started).strftime('%Y-%m-%d %H:%M'):<18}"
            f"{row.calls:>7,}{row.minutes:>9.0f}"
            f"{_num(row.open_context):>15}{_num(row.close_context):>16}"
            f"{growth:>8}"
        )
    if not rows:
        lines.append("(no parent sessions in this corpus)")
    if ungrouped:
        lines.append(
            f"{ungrouped:,} parent call(s) carried no session_id and are in "
            f"no row above"
        )
    return "\n".join(lines)


def ungrouped_calls(records: Iterable[CallRecord]) -> int:
    """Parent calls that could not be grouped, so the drop is never silent."""
    return len(distinct_calls(
        r for r in records if not r.is_subagent and not r.session_id
    ))
