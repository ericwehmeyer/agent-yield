"""Process changes, on the record, with a prediction attached."""
from __future__ import annotations

import datetime as dt
import tomllib
from dataclasses import dataclass
from pathlib import Path


# What a prediction is allowed to name. Every entry must be a property of
# `report.YieldRow`; `test_report.py` is what holds the two together, because
# this tuple deliberately does NOT import the report -- the loader has to be
# able to reject a typo without pulling in the reporting stack.
#
# The list is short on purpose. A prediction naming something not here is not
# a prediction this tool can settle, and the honest record of that is no
# metric at all plus an UNSCORABLE line in the report (#44). Adding a name
# here is a claim that the quantity is computable from a day's calls, so it is
# a decision, not a convenience.
SCORABLE_METRICS = (
    "tokens_per_merge",
    "tokens_per_commit",
    # The WHOLE-day ratio only. `tokens_per_code_insertion` and its docs twin
    # are deliberately absent and are not properties either: the code half
    # moved 2.38x "better" across the two measured days on a mix shift alone,
    # so a threshold prediction against it reads PASS on a day nothing
    # improved (#46 review, finding 2). See `report.PerInsertion`.
    "tokens_per_insertion",
    # Divides by what lasted. `tokens_per_insertion` stays, because the pair is
    # the thrash measurement: naming both is how a prediction claims it reduced
    # rewriting rather than typing.
    "tokens_per_surviving_insertion",
    "context_per_call",
    "main_context_per_call",
    "subagent_context_per_call",
)


class InterventionError(ValueError):
    """An intervention file that cannot be trusted to mean what it says."""


@dataclass(frozen=True)
class Intervention:
    date: dt.date
    name: str
    expect: str
    metric: str | None = None
    """The row property this prediction is scored on, or None.

    None means UNSCORABLE and is the common, correct case: most predictions
    here name tool calls per agent, the cost of an experiment arm, or whether
    a transcript is still readable, and none of those is a property of a day's
    calls. What #44 found is that scoring such a prediction on whatever a CLI
    flag defaulted to prints a plausible number under a question it cannot
    answer -- the reassuring-silence failure this repo has now hit four times.
    """


def load_interventions(path: Path) -> list[Intervention]:
    path = Path(path)
    if not path.exists():
        return []
    with path.open("rb") as handle:
        data = tomllib.load(handle)

    out: list[Intervention] = []
    for index, entry in enumerate(data.get("intervention", [])):
        where = f"{path}, intervention #{index + 1}"
        raw_date = entry.get("date")
        name = str(entry.get("name", "")).strip()
        expect = str(entry.get("expect", "")).strip()
        if not name:
            raise InterventionError(f"{where}: 'name' is required")
        # An intervention without a prediction is not an experiment. Refusing
        # it here is the whole reason this loader exists.
        if not expect:
            raise InterventionError(
                f"{where} ({name!r}): 'expect' is required and must say what "
                f"you predict will change"
            )
        # A metric that does not exist is a claim that failed on a keystroke,
        # and reading it as "no metric named" would leave a scorable
        # prediction unscored while looking exactly like the honest case.
        metric = entry.get("metric")
        if metric is not None:
            metric = str(metric).strip()
            if metric not in SCORABLE_METRICS:
                raise InterventionError(
                    f"{where} ({name!r}): metric {metric!r} is not one this "
                    f"tool can compute -- pick one of "
                    f"{', '.join(SCORABLE_METRICS)}, or leave it out and the "
                    f"report will say UNSCORABLE"
                )
        if isinstance(raw_date, dt.datetime):
            parsed = raw_date.date()
        elif isinstance(raw_date, dt.date):
            parsed = raw_date
        else:
            try:
                parsed = dt.date.fromisoformat(str(raw_date))
            except ValueError as exc:
                raise InterventionError(
                    f"{where}: bad 'date' {raw_date!r}"
                ) from exc
        out.append(Intervention(
            date=parsed, name=name, expect=expect, metric=metric
        ))

    out.sort(key=lambda i: i.date)
    return out
