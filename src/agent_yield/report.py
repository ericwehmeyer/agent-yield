"""The join: spend over outcomes, per mode, with interventions marked.

Reports tokens. Never money -- rates change and vary by plan, and a tool that
hardcodes them lies quietly later.
"""
from __future__ import annotations

import datetime as dt
import statistics
from dataclasses import dataclass
from typing import Iterable

from .interventions import Intervention
from .modes import mode_for
from .outcomes import DailyOutcome
from .records import CallRecord
from .usage import Usage


@dataclass(frozen=True)
class YieldRow:
    day: dt.date
    mode: str
    usage: Usage
    calls: int
    merges: int
    commits: int
    lines: int
    tests: int | None = None

    @property
    def tokens_per_merge(self) -> float | None:
        return self.usage.total / self.merges if self.merges else None

    @property
    def tokens_per_commit(self) -> float | None:
        return self.usage.total / self.commits if self.commits else None

    @property
    def context_per_call(self) -> float | None:
        return self.usage.cache_read_tokens / self.calls if self.calls else None


def build_rows(
    records: Iterable[CallRecord],
    outcomes: Iterable[DailyOutcome],
    modes: dict[str, str],
) -> list[YieldRow]:
    """One row per (day, mode) that had spend.

    Outcomes are per-day and cannot be attributed to a mode, so each row
    carries its day's outcomes whole. Splitting them between modes would be a
    guess, and a guess about the denominator is the error this tool documents.
    """
    outcome_by_day = {o.day: o for o in outcomes}

    buckets: dict[tuple[dt.date, str], list[CallRecord]] = {}
    for record in records:
        key = (record.day, mode_for(record.session_id, modes))
        buckets.setdefault(key, []).append(record)

    rows: list[YieldRow] = []
    for (day, mode), calls in sorted(buckets.items()):
        usage = Usage.zero()
        for call in calls:
            usage = usage + call.usage
        outcome = outcome_by_day.get(day, DailyOutcome(day))
        rows.append(YieldRow(
            day=day, mode=mode, usage=usage, calls=len(calls),
            merges=outcome.merges, commits=outcome.commits,
            lines=outcome.lines, tests=outcome.tests,
        ))
    return rows


@dataclass(frozen=True)
class BeforeAfter:
    intervention: Intervention
    metric: str
    before: float | None
    after: float | None

    @property
    def change(self) -> float | None:
        if self.before is None or self.after is None or self.before == 0:
            return None
        return (self.after - self.before) / self.before


def compare_interventions(
    rows: Iterable[YieldRow],
    interventions: Iterable[Intervention],
    window_days: int = 7,
    metric: str = "tokens_per_merge",
) -> list[BeforeAfter]:
    """Median of `metric` in the window before and after each intervention.

    An empty window yields None, not zero. Zero would read as "it got free".
    """
    rows = list(rows)
    results: list[BeforeAfter] = []

    def sample(lo: dt.date, hi: dt.date) -> float | None:
        values = []
        for row in rows:
            if lo <= row.day <= hi:
                value = getattr(row, metric)
                if value is not None:
                    values.append(value)
        return statistics.median(values) if values else None

    for intervention in interventions:
        start = intervention.date - dt.timedelta(days=window_days)
        end = intervention.date + dt.timedelta(days=window_days)
        results.append(BeforeAfter(
            intervention=intervention,
            metric=metric,
            before=sample(start, intervention.date - dt.timedelta(days=1)),
            after=sample(intervention.date, end),
        ))
    return results


def _fmt(value: float | None) -> str:
    return "-" if value is None else f"{value:,.0f}"


def render_table(rows: Iterable[YieldRow]) -> str:
    header = (
        f"{'day':<12}{'mode':<10}{'tokens':>16}{'calls':>8}"
        f"{'merges':>8}{'commits':>9}{'tok/merge':>14}{'ctx/call':>11}"
    )
    lines = [header, "-" * len(header)]
    for row in rows:
        lines.append(
            f"{row.day.isoformat():<12}{row.mode:<10}"
            f"{row.usage.total:>16,}{row.calls:>8,}"
            f"{row.merges:>8,}{row.commits:>9,}"
            f"{_fmt(row.tokens_per_merge):>14}{_fmt(row.context_per_call):>11}"
        )
    return "\n".join(lines)
