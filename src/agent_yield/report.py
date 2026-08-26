"""The join: spend over outcomes, per mode, with interventions marked.

Reports tokens. Money lives in `pricing.py` and is not printed here.

The old rule was "never money -- rates change and vary by plan, and a tool that
hardcodes them lies quietly later." The danger was real and the remedy was
wrong: a rate reconciled against the CLI's own `costUSD` on every test run is a
measurement, and what the rule actually objected to was an UNRECONCILED
constant. Plan variation is answered by labelling -- everything `pricing.py`
returns is a list-price equivalent, a comparator and not a bill. This report
stays in tokens because its subject is spend over outcomes per mode, not cost;
an arm COMPARISON belongs in dollars, and that is #55's ruling, not this file's.
"""
from __future__ import annotations

import datetime as dt
import os
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from .interventions import SCORABLE_METRICS, Intervention
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


def scope_to_repo(records: Iterable[CallRecord], repo: Path) -> list[CallRecord]:
    r"""Only the calls made inside `repo`, by their recorded `cwd`.

    The report divides spend by what shipped. Before this, the numerator summed
    every project on the machine while the denominator counted commits in one
    repo: on 2026-08-25 that read **44,794,803 tokens per commit** against a
    true 1,778,703, a 25x error and a flattering one -- any intervention that
    happened to land on a quiet day for other work looked better for it (#44).
    `cwd` is on every one of the 20,757 records in the corpus, subagents
    included, so the scoping was available and simply not applied.

    `normcase` on both sides, and never `.lower()`: it folds on Windows, where
    `cd c:\w\repo` and `C:\w\repo` are one directory, and is the identity on
    POSIX, where `/w/Repo` and `/w/repo` are two projects and folding would
    hand one of them the other's spend. That is #51, one file over.

    A record with no `cwd` is dropped rather than assumed to belong here.
    Attributing it would be a guess about a denominator, which is the error
    this tool documents.
    """
    wanted = os.path.normcase(os.path.abspath(str(repo)))
    kept = []
    for record in records:
        if not record.cwd:
            continue
        cwd = os.path.normcase(os.path.abspath(record.cwd))
        if cwd == wanted or cwd.startswith(wanted + os.sep):
            kept.append(record)
    return kept


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
    metric: str | None
    before: float | None
    after: float | None
    unscorable: str | None = None
    """Why this prediction was not scored, or None if it was.

    A distinct outcome, and distinct from VOID. VOID says the run did not
    happen properly; UNSCORABLE says the run happened and this tool cannot
    settle the question that was asked of it. Printing `- -> -` for either was
    #44: a dash reads as "not yet" when it means "never will be", and a
    plausible number reads as an answer when it answers a different question.
    """

    @property
    def change(self) -> float | None:
        if self.before is None or self.after is None or self.before == 0:
            return None
        return (self.after - self.before) / self.before


def compare_interventions(
    rows: Iterable[YieldRow],
    interventions: Iterable[Intervention],
    window_days: int = 7,
) -> list[BeforeAfter]:
    """Median of each prediction's OWN metric in the windows around it.

    There is no `metric` parameter and there is deliberately no default. The
    scorer used to take one from a CLI flag, so a prediction naming subagent
    context/call was scored on a blend of main and subagent -- a quantity
    `design.md` §3.1 already records as dissolving under decomposition, 311,399
    against 89,721. It printed 133,996 under a prediction about 48,480 and
    said nothing about the substitution (#44).

    An empty window yields UNSCORABLE, not None and not zero. Zero would read
    as "it got free"; None printed as a dash reads as "not yet".
    """
    rows = list(rows)
    results: list[BeforeAfter] = []

    def sample(metric: str, lo: dt.date, hi: dt.date) -> float | None:
        values = []
        for row in rows:
            if lo <= row.day <= hi:
                value = getattr(row, metric)
                if value is not None:
                    values.append(value)
        return statistics.median(values) if values else None

    for intervention in interventions:
        metric = intervention.metric
        if metric is None:
            results.append(BeforeAfter(
                intervention=intervention, metric=None,
                before=None, after=None,
                unscorable=NO_METRIC,
            ))
            continue

        start = intervention.date - dt.timedelta(days=window_days)
        end = intervention.date + dt.timedelta(days=window_days)
        before = sample(metric, start, intervention.date - dt.timedelta(days=1))
        after = sample(metric, intervention.date, end)

        empty = [
            name for name, value in (("before", before), ("after", after))
            if value is None
        ]
        unscorable = None
        if empty:
            # Half a window is half an answer, and `20,000 -> -` invites
            # reading the dash as zero or as "no effect".
            unscorable = (
                f"{metric} has no value in the {' and '.join(empty)} window"
                f" ({window_days} days)"
            )
            before = after = None

        results.append(BeforeAfter(
            intervention=intervention, metric=metric,
            before=before, after=after, unscorable=unscorable,
        ))
    return results


NO_METRIC = "this prediction names no metric this tool computes"


def render_interventions(results: Iterable[BeforeAfter]) -> str:
    """The interventions block, with UNSCORABLE as loud as a number.

    Rendering lives here rather than in the CLI because the distinction this
    block exists to draw -- scored against unscorable -- is the finding of
    #44, and a finding that only exists in a print statement cannot be tested.
    """
    results = list(results)
    out = ["interventions"]
    for result in results:
        out.append(f"  {result.intervention.date}  {result.intervention.name}")
        out.append(f"    expected: {result.intervention.expect}")
        if result.unscorable is not None:
            out.append(f"    UNSCORABLE: {result.unscorable}")
            continue
        out.append(
            f"    {result.metric}: {_fmt(result.before)} -> {_fmt(result.after)}"
        )
    # The remedy once, at the bottom, rather than on every row. Repeating
    # the list of metrics fourteen times buries the one line that carries a
    # measurement, which is the opposite of what this block is for.
    if any(r.unscorable == NO_METRIC for r in results):
        out.append("")
        out.append(
            "  UNSCORABLE means this tool cannot settle the prediction, "
            "not that nothing happened."
        )
        out.append(
            "  To score one, add metric = <"
            + " | ".join(SCORABLE_METRICS)
            + "> to interventions.toml."
        )
    return "\n".join(out)


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
