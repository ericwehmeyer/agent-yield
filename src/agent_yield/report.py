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
from .thresholds import COST_DISPATCH, COST_LADDER, COST_RESTART, COST_STOP
from .usage import Usage


@dataclass(frozen=True)
class PerInsertion:
    """Tokens per inserted line, whole and decomposed, as ONE object.

    The #46 review's blocking finding 2. The plan put `tokens_per_insertion`,
    `tokens_per_code_insertion` and `tokens_per_docs_insertion` on the row as
    three independent attributes and called the pair "a single display
    convention". On the two measured days the code half moves 15,785 ->
    6,633, a 2.38x apparent improvement -- larger than the 2.22x this whole
    design exists to reject -- on a day nobody claims got more efficient. The
    mix moved, not the efficiency. A prediction reading "tokens per
    code-insertion falls below 10,000" would have printed PASS.

    So the halves have no names of their own. `SCORABLE_METRICS` carries
    `tokens_per_insertion` and neither half, `render` formats all three or
    none, and there is no attribute a scorer could resolve alone. A convention
    that lives in a design document is not a guard; an attribute that does not
    exist is.

    None, never zero, on an empty denominator: a day that shipped nothing did
    not ship infinitely cheaply.
    """
    all: float | None
    code: float | None
    docs: float | None
    other: float | None

    def render(self) -> str:
        return "/".join(_fmt(v) for v in (self.all, self.code, self.docs))


@dataclass(frozen=True)
class CostBand:
    """One cost threshold, counted over BOTH populations that can cross it.

    The #46 review's blocking finding 4, closed as #68. The plan headlined
    "share of main calls at or above 300,000" and left it undecomposed, one
    row after naming the session-length confound for context/call and omitting
    it here. The share of calls above a threshold is a mean over a session
    mixture: adding cheap short sessions moves it with nothing changed about
    how any session is run, and the two measured days changed the population
    being averaged 2.7x (146 calls -> 398). 20% -> 4% is the number the plan
    called "the cleanest real signal", and a mixture shift is exactly what
    this design exists to refuse to read as a signal.

    Measured on this clone's own 2026-08-26 corpus, the two are not the same
    quantity: cut at 200,000 tokens, 8.9% of the 1,420 main calls are above
    the line and 26.3% of the 19 sessions are. They disagree at every cut and
    they cross over below ~75,000. The lower cuts are a diagnostic; the series
    stays pinned at the constants below.

    So a band carries the call count, the session count and both denominators,
    and `cost_band_cells` formats all four or none -- the same structural
    guard `PerInsertion` applies to the insertion halves. The session figure
    is the share of that row's main sessions whose most expensive main call
    crossed the threshold; a per-session maximum is what "did this session get
    into the expensive band" means, and it is recoverable from nothing coarser.

    The counts are carried rather than only the percentages because the review
    is right that "4%" without its n is not a measurement: on this clone
    2026-08-26 the session denominator is 19, where one session moves the
    share five points.

    `threshold` is on the result rather than looked up at read time (S3's
    pinning rule): two days' figures are comparable only if they were cut at
    the same number, and carrying the constant is what lets a reader notice a
    retune instead of reading straight through one.
    """
    band: str
    threshold: int
    calls_above: int
    calls: int
    sessions_above: int
    sessions: int

    @property
    def call_share(self) -> float | None:
        """None when the row made no main-thread calls -- not 0.0, which would
        read as "none of them were expensive"."""
        return self.calls_above / self.calls if self.calls else None

    @property
    def session_share(self) -> float | None:
        return self.sessions_above / self.sessions if self.sessions else None


def cost_band_cells(bands: Iterable[CostBand]) -> tuple[str, str]:
    """The calls half and the sessions half, always returned together.

    There is deliberately no function that formats the call share by itself.
    That is finding 4's remedy in the same shape as finding 2's: the display
    rule -- no decomposable aggregate without its decomposition beside it --
    is a rule only where the code cannot express its violation. A caller that
    wants the aggregate has to take the decomposition with it.
    """
    bands = list(bands)
    calls = bands[0].calls if bands else 0
    sessions = bands[0].sessions if bands else 0
    if not calls:
        # No main calls is no evidence, and `0/0/0 of 0` reads as a
        # measurement that came back clean. Dash-never-zero, one level up
        # from the shares.
        return ("calls - of 0", "sessions - of 0")
    return (
        f"calls {_counts(b.calls_above for b in bands)} of {calls:,}"
        f" {_shares(b.call_share for b in bands)}",
        f"sessions {_counts(b.sessions_above for b in bands)} of {sessions:,}"
        f" {_shares(b.session_share for b in bands)}",
    )


def render_cost_bands(bands: Iterable[CostBand]) -> str:
    """One line carrying both populations and both denominators."""
    calls, sessions = cost_band_cells(bands)
    return f"{calls}   {sessions}"


def _counts(values: Iterable[int]) -> str:
    return "/".join(f"{v:,}" for v in values)


def _shares(values: Iterable[float | None]) -> str:
    """`20/0/0%`, or a single dash when the denominator is empty.

    All three shares of a band set share one denominator, so they are None
    together or not at all; a mixed `-/0/0%` cannot occur and is not spelled.
    """
    values = list(values)
    if any(v is None for v in values):
        return "-"
    return "/".join(f"{v * 100:.0f}" for v in values) + "%"


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
    code_lines: int = 0
    docs_lines: int = 0
    other_lines: int = 0
    surviving_lines: int | None = None
    main_contexts: tuple[int, ...] = ()
    """Every main call's context, kept rather than summed, because a share
    above a threshold cannot be recovered from a mean."""
    main_session_peaks: tuple[int, ...] = ()
    """The most expensive main call in each of this row's main sessions.

    The decomposition the call-level share needs (#46 review, finding 4). A
    peak is the right per-session summary because the question a threshold
    asks -- did this session get into the band where the remedy is to leave --
    is answered by the worst call in it, not by its average call.

    Sessions, not calls, and only the sessions that made MAIN calls: a row
    whose subagents ran hot has a failed brief, not a session to restart, and
    `cost_band`'s own contract keeps the two populations apart.
    """

    @property
    def tokens_per_merge(self) -> float | None:
        return self.usage.total / self.merges if self.merges else None

    @property
    def tokens_per_commit(self) -> float | None:
        return self.usage.total / self.commits if self.commits else None

    @property
    def per_insertion(self) -> PerInsertion:
        """The paired ratio. Read `PerInsertion`'s docstring before using it."""
        def ratio(denominator: int) -> float | None:
            return self.usage.total / denominator if denominator else None
        return PerInsertion(
            all=ratio(self.lines),
            code=ratio(self.code_lines),
            docs=ratio(self.docs_lines),
            other=ratio(self.other_lines),
        )

    @property
    def tokens_per_insertion(self) -> float | None:
        """The whole-day ratio, which IS safe to read alone.

        Its decomposition is `per_insertion`, and the halves deliberately have
        no properties of their own. This name exists because a prediction may
        legitimately be registered against the undecomposed figure.
        """
        return self.per_insertion.all

    @property
    def tokens_per_surviving_insertion(self) -> float | None:
        """Tokens per inserted line that was still there at the horizon.

        The headline denominator. `tokens_per_insertion` counts a line written
        three times as three lines shipped, so a thrash day and a clean day of
        the same size read alike; this one does not. None, never zero, when
        survival is unmeasured or nothing survived.
        """
        if self.surviving_lines is None or self.surviving_lines <= 0:
            return None
        return self.usage.total / self.surviving_lines

    @property
    def cost_bands(self) -> tuple[CostBand, ...]:
        """This row's MAIN calls, and the main SESSIONS they came from, at or
        above each cost threshold.

        Main-thread only, which is `cost_band`'s own rule one level up: a
        subagent above 300,000 is a brief that failed, not a session to
        restart. Same token count, different diagnosis, different remedy, so
        pooling the two populations would put the remedy on the wrong thread.

        At-or-above rather than in-band: the bands nest, and "what share of
        the day was expensive enough to dispatch" is the question an operator
        asks. Each count therefore includes the ones above it.

        Read `CostBand` for why the session figure is here and not optional.
        """
        thresholds = (COST_DISPATCH, COST_RESTART, COST_STOP)
        return tuple(
            CostBand(
                band=band,
                threshold=threshold,
                calls_above=sum(1 for c in self.main_contexts if c >= threshold),
                calls=len(self.main_contexts),
                sessions_above=sum(
                    1 for p in self.main_session_peaks if p >= threshold
                ),
                sessions=len(self.main_session_peaks),
            )
            for band, threshold in zip(COST_LADDER, thresholds)
        )

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
        main_contexts: list[int] = []
        # session id -> the most expensive main call seen in it. A record with
        # no `session_id` becomes a session of its own rather than joining one
        # anonymous bucket: two calls that do not say which session they are
        # in are not evidence that they share one, and pooling them would move
        # the session denominator on a guess. Where identity is missing
        # everywhere the decomposition degrades to the call-level share, which
        # is visible on the page as sessions == calls rather than hidden.
        peaks: dict[object, int] = {}
        subagent_calls = 0
        for index, call in enumerate(calls):
            usage = usage + call.usage
            if call.is_subagent:
                subagent_usage = subagent_usage + call.usage
                subagent_calls += 1
            else:
                main_usage = main_usage + call.usage
                main_contexts.append(call.context)
                key = call.session_id if call.session_id else ("call", index)
                peaks[key] = max(peaks.get(key, 0), call.context)
        outcome = outcome_by_day.get(day, DailyOutcome(day))
        rows.append(YieldRow(
            day=day, mode=mode, usage=usage, calls=len(calls),
            merges=outcome.merges, commits=outcome.commits,
            lines=outcome.lines, tests=outcome.tests,
            main_calls=len(main_contexts), subagent_calls=subagent_calls,
            main_usage=main_usage, subagent_usage=subagent_usage,
            code_lines=outcome.code_lines, docs_lines=outcome.docs_lines,
            other_lines=outcome.other_lines,
            surviving_lines=outcome.surviving_lines,
            main_contexts=tuple(main_contexts),
            main_session_peaks=tuple(peaks.values()),
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
    """#46 S1's one table: spend, what shipped, and where the spend sat.

    `commits` stays. It is a denominator, and this tool exists to divide spend
    by what shipped -- dropping the count while offering a `tokens_per_commit`
    metric would hide the very number that metric is built on.

    `merges` and `tok/merge` are GONE from the table, and only from the table.
    Neither is in v1's column list, on a linear history the first is always
    zero and the second always a dash, and ten quantities do not fit in a
    hundred columns. `tokens_per_merge` stays on the row and stays scorable;
    `agent-yield outcomes` still prints the merge count.

    `tok/ins` is the WHOLE-day ratio and the code/docs/other columns beside it
    are the mix. The per-area ratios are not here and are not properties --
    see `PerInsertion`, and the 2.38x it exists to stop.

    The cost bands moved OFF the grid and into a block under it, one line per
    row, and that is the #46 review's finding 4 rather than a layout
    preference. Finding 4 is that the share of main calls above a threshold is
    an aggregate over a session mixture and was headlined undecomposed; the
    remedy is the session share and both counts beside it. Eight numbers per
    row -- three call counts, three session counts, two denominators -- do not
    fit in a twelve-column cell, and in the limit two `100/100/100` triples
    are twenty-five characters on their own. **A cell that fits only after the
    decomposition is dropped is how the aggregate got printed alone in the
    first place**, so the grid gives the bands up rather than the reverse.
    The constants are still read from `thresholds.py` for the legend, which is
    S3's pinning rule: numbers baked into a header go stale the day the module
    is retuned.

    118 columns now. Moving the bands off bought the grid down from 120 to
    108, and `tok/surv` spends ten of that back: the pair is the thrash
    reading, and a table carrying only the insertion half is the reading this
    work exists to replace. The blended `context_per_call` is off the table
    but stays on the row.
    """
    header = (
        f"{'day':<11}{'mode':<9}{'tokens':>13}{'calls':>7}{'commits':>8}"
        f"{'code':>8}{'docs':>8}{'other':>8}{'tok/ins':>9}{'tok/surv':>10}"
        f"{'main ctx/call':>14}{'sub ctx/call':>13}"
    )
    lines = [header, "-" * len(header)]
    for row in rows:
        lines.append(
            f"{row.day.isoformat():<11}{row.mode:<9}"
            f"{row.usage.total:>13,}{row.calls:>7,}{row.commits:>8,}"
            f"{row.code_lines:>8,}{row.docs_lines:>8,}{row.other_lines:>8,}"
            f"{_fmt(row.tokens_per_insertion):>9}"
            f"{_fmt(row.tokens_per_surviving_insertion):>10}"
            f"{_fmt(row.main_context_per_call):>14}"
            f"{_fmt(row.subagent_context_per_call):>13}"
        )
    lines.append(
        f"cost bands, at or above {COST_DISPATCH:,} / {COST_RESTART:,} /"
        f" {COST_STOP:,} context tokens -- main calls, then the main sessions"
        f" they came from"
    )
    for row in rows:
        lines.append(
            f"  {row.day.isoformat()} {row.mode:<9}"
            f" {render_cost_bands(row.cost_bands)}"
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
