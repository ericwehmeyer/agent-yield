"""The join: spend over outcomes, per mode, with interventions marked.

Reports tokens. Never money -- rates change and vary by plan, and a tool that
hardcodes them lies quietly later.
"""
from __future__ import annotations

import datetime as dt
import statistics
from dataclasses import dataclass, field
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
    main_calls: int = 0
    subagent_calls: int = 0
    main_usage: Usage = field(default_factory=Usage.zero)
    subagent_usage: Usage = field(default_factory=Usage.zero)

    @property
    def tokens_per_merge(self) -> float | None:
        return self.usage.total / self.merges if self.merges else None

    @property
    def tokens_per_commit(self) -> float | None:
        return self.usage.total / self.commits if self.commits else None

    @property
    def context_per_call(self) -> float | None:
        """The blended figure. Kept, but read the two below instead.

        Main sessions and subagents carry context of a different order --
        measured 3.5x apart on the corpus -- so one mean over both populations
        describes neither.
        """
        return self.usage.cache_read_tokens / self.calls if self.calls else None

    @property
    def main_context_per_call(self) -> float | None:
        if not self.main_calls:
            return None
        return self.main_usage.cache_read_tokens / self.main_calls

    @property
    def subagent_context_per_call(self) -> float | None:
        if not self.subagent_calls:
            return None
        return self.subagent_usage.cache_read_tokens / self.subagent_calls


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
        main_usage = Usage.zero()
        subagent_usage = Usage.zero()
        main_calls = 0
        subagent_calls = 0
        for call in calls:
            usage = usage + call.usage
            if call.is_subagent:
                subagent_usage = subagent_usage + call.usage
                subagent_calls += 1
            else:
                main_usage = main_usage + call.usage
                main_calls += 1
        outcome = outcome_by_day.get(day, DailyOutcome(day))
        rows.append(YieldRow(
            day=day, mode=mode, usage=usage, calls=len(calls),
            merges=outcome.merges, commits=outcome.commits,
            lines=outcome.lines, tests=outcome.tests,
            main_calls=main_calls, subagent_calls=subagent_calls,
            main_usage=main_usage, subagent_usage=subagent_usage,
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
    """One line per (day, mode), context split main vs subagent.

    `commits` stays. It is a denominator, and this tool exists to divide spend
    by what shipped -- dropping the count while offering a `tokens_per_commit`
    metric would hide the very number that metric is built on. The split costs
    width instead: 100 columns, which needs a 120-wide terminal. The blended
    `context_per_call` is off the table but stays on the row.
    """
    header = (
        f"{'day':<12}{'mode':<9}{'tokens':>15}{'calls':>7}"
        f"{'merges':>8}{'commits':>9}{'tok/merge':>13}"
        f"{'main ctx/call':>14}{'sub ctx/call':>13}"
    )
    lines = [header, "-" * len(header)]
    for row in rows:
        lines.append(
            f"{row.day.isoformat():<12}{row.mode:<9}"
            f"{row.usage.total:>15,}{row.calls:>7,}"
            f"{row.merges:>8,}{row.commits:>9,}"
            f"{_fmt(row.tokens_per_merge):>13}"
            f"{_fmt(row.main_context_per_call):>14}"
            f"{_fmt(row.subagent_context_per_call):>13}"
        )
    return "\n".join(lines)


@dataclass(frozen=True)
class ModelRow:
    """One model at one role. No outcome join -- see `build_rows`' docstring.

    Carries every call's context rather than only a summed `Usage`, because a
    median cannot be recovered from a sum and the mean alone misreads a skewed
    distribution. `contexts` is the raw material; the properties are the read.
    """
    model: str
    is_subagent: bool
    calls: int
    usage: Usage
    contexts: tuple[int, ...] = ()

    @property
    def total_context(self) -> int:
        return sum(self.contexts)

    @property
    def context_per_call(self) -> float | None:
        # Cache reads, matching `YieldRow.context_per_call`: the same name in
        # the same module counts the same tokens.
        return self.usage.cache_read_tokens / self.calls if self.calls else None

    @property
    def median_context_per_call(self) -> float | None:
        return statistics.median(self.contexts) if self.contexts else None

    @property
    def output_per_call(self) -> float | None:
        return self.usage.output_tokens / self.calls if self.calls else None


def build_model_rows(records: Iterable[CallRecord]) -> list[ModelRow]:
    """One row per (model, role), ordered by total context descending.

    `model` is `None` on some records and the literal `<synthetic>` on others.
    Neither is a model and both are kept: a table that quietly drops calls is
    the failure this tool exists to catch. `None` is labelled `none`.
    """
    buckets: dict[tuple[str, bool], list[CallRecord]] = {}
    for record in records:
        key = (record.model or "none", record.is_subagent)
        buckets.setdefault(key, []).append(record)

    rows: list[ModelRow] = []
    for (model, is_subagent), calls in buckets.items():
        usage = Usage.zero()
        for call in calls:
            usage = usage + call.usage
        rows.append(ModelRow(
            model=model, is_subagent=is_subagent, calls=len(calls),
            usage=usage,
            contexts=tuple(c.usage.cache_read_tokens for c in calls),
        ))
    # Descending spend, because the question is where the money went.
    rows.sort(key=lambda r: (-r.total_context, r.model, r.is_subagent))
    return rows


def render_model_table(rows: Iterable[ModelRow]) -> str:
    """Absolute tokens throughout. The window is a capacity fact, not a cost.

    Mean and median sit side by side deliberately. Where they part, the mean is
    being carried by a tail, and the pair says so at a glance.
    """
    header = (
        f"{'model':<26}{'role':<10}{'calls':>8}{'tokens':>16}"
        f"{'ctx/call':>12}{'median ctx':>12}{'out/call':>10}"
    )
    lines = [header, "-" * len(header)]
    for row in rows:
        lines.append(
            f"{row.model:<26}{'subagent' if row.is_subagent else 'main':<10}"
            f"{row.calls:>8,}{row.usage.total:>16,}"
            f"{_fmt(row.context_per_call):>12}"
            f"{_fmt(row.median_context_per_call):>12}"
            f"{_fmt(row.output_per_call):>10}"
        )
    return "\n".join(lines)
