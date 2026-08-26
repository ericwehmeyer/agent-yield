"""What a call actually cost, per model, verified against the CLI's own bill.

This module reverses the "tokens, never money" rule that `report.py`,
`report_html.py` and `statusline.py` each state. The rule was right about the
danger and wrong about the remedy. Its two reasons were that rates CHANGE and
that they VARY BY PLAN:

* **Rates change** -- answered by measurement, not by trust. `claude -p
  --output-format json` returns a per-model `modelUsage` block carrying
  `costUSD`, so the table below is checked against the CLI's own accounting on
  four archived arms every time the suite runs. A rate that is reconciled is a
  measurement; the rule's real objection was to an UNRECONCILED constant.
* **Rates vary by plan** -- answered by labelling, not by solving. Every
  `modelUsage` block in the archive carries `costBasis: "list"`, and so does
  everything here: these are LIST-PRICE EQUIVALENTS, a comparator and not a
  bill. On a subscription the ranking of two ways of working survives; the
  absolute figure does not, and no report may claim it does.

The model, and it is exact rather than approximate:

    cost = SUM over models of base(model) x (
              input
            + 0.10 x cache_read
            + 1.25 x cache_write_5m
            + 2.00 x cache_write_1h
            + 5.00 x output )

Against `total_cost_usd` on the four archived #33 arms it reproduces
$2.9123, $2.1818, $3.1987 and $3.2540 -- exact to the cent, all four -- and on
the two #81 rate arms $0.059175 and $0.215854, exact to the microdollar. From
transcripts alone it lands within 0.3-0.7% on five of six arms, and the
residual is not slack: it is the priced value of the output tokens that #53
identifies as missing, to the cent.

WHY THIS IS PER-MODEL AND WILL NOT ACCEPT A BARE `Usage`. Every one of those
arms was run with `--model opus`, and every one of them also billed
`claude-haiku-4-5` for harness-side work. A session is never one model, so a
signature that takes a single `Usage` would be quietly wrong for the same
reason a single `cache_creation_tokens` was.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Mapping

from .records import CallRecord
from .usage import Usage

# Dollars per million base input tokens. Verified 2026-08-26 against the
# `modelUsage.costUSD` blocks of the four archived #33 arms and the two #81 rate
# arms; the tests that do it live in tests/test_pricing.py and are the reason
# these are not guesses.
#
# `claude-sonnet-5` and `claude-fable-5` were added 2026-08-26 for #81, which
# found them billed on 44% of one real day's calls with no rate here at all. NOT
# typed in from a price list -- each was SOLVED from its own `-p` run and then
# checked back: the arm reads a file twice, so it bills a cache write and a cache
# read as well as input and output, and a rate solved from input alone would be
# one equation that cannot see the multipliers. Both arms also bill
# `claude-haiku-4-5` for harness-side work, and the existing $1.00 reproduces its
# `costUSD` to the microdollar on both -- the control that says the model, not
# just the new number, is right.
BASE_RATE_PER_MTOK: dict[str, float] = {
    "claude-opus-5": 5.00,
    "claude-fable-5": 10.00,
    "claude-sonnet-5": 2.00,
    "claude-haiku-4-5": 1.00,
}

# Multipliers on the base input rate. `CACHE_WRITE_5M` and `CACHE_WRITE_1H` are
# the whole reason `Usage` carries a TTL split: subagents write the cheap one
# and parents write the dear one, so an arm's cache-write price depends on how
# it dispatched. See usage.py.
CACHE_READ = 0.10
CACHE_WRITE_5M = 1.25
CACHE_WRITE_1H = 2.00
OUTPUT = 5.00

# Context window per model, in tokens. Observed in `modelUsage.contextWindow`,
# not assumed. Transcript records carry no window, so this registry is
# self-checkable only from `-p` output -- which is why it is a registry and not
# a computation.
MODEL_WINDOWS: dict[str, int] = {
    "claude-opus-5": 1_000_000,
    "claude-fable-5": 1_000_000,
    "claude-sonnet-5": 1_000_000,
    "claude-haiku-4-5": 200_000,
}

_DATED = re.compile(r"-\d{8}$")


def canonical(model: str | None) -> str | None:
    """`claude-haiku-4-5-20251001` -> `claude-haiku-4-5`.

    Transcripts carry the dated id and `modelUsage` carries both; the rate is a
    property of the model, not of the snapshot date.
    """
    if not model:
        return None
    return _DATED.sub("", model)


def window_for(model: str | None) -> int | None:
    """The model's context window, or None if this tool has not measured it.

    None, never a default: a fraction computed against a guessed denominator is
    worse than no fraction, because it looks like a measurement.
    """
    return MODEL_WINDOWS.get(canonical(model) or "")


@dataclass(frozen=True)
class Priced:
    """A list-price equivalent, with everything it could not price named."""

    dollars: float
    by_model: dict[str, float]
    unpriced_models: tuple[str, ...]
    unpriced_tokens: int
    unattributed_cache_creation: int

    @property
    def is_complete(self) -> bool:
        return not self.unpriced_models and not self.unattributed_cache_creation

    def caveat(self) -> str | None:
        """One clause a report can append, or None when there is nothing to say."""
        parts = []
        if self.unpriced_models:
            parts.append(f"{len(self.unpriced_models)} model"
                         f"{'s' if len(self.unpriced_models) > 1 else ''} unpriced"
                         f" ({', '.join(self.unpriced_models)})")
        if self.unattributed_cache_creation:
            parts.append(f"{self.unattributed_cache_creation:,} cache-write tokens"
                         " with no TTL, priced at the 5m default")
        return "; ".join(parts) if parts else None


def weighted_tokens(usage: Usage) -> float:
    """Base-input-equivalent tokens: the bracket of the formula above.

    Multiply by a model's base rate to get dollars. Cache writes with no TTL are
    charged at the 5m rate -- the API's default when none is requested -- and
    counted separately by `price` so a caller can qualify or refuse the figure
    rather than discover the assumption later.
    """
    return (
        usage.input_tokens
        + CACHE_READ * usage.cache_read_tokens
        + CACHE_WRITE_5M * usage.cache_creation_5m
        + CACHE_WRITE_1H * usage.cache_creation_1h
        + CACHE_WRITE_5M * usage.cache_creation_unattributed
        + OUTPUT * usage.output_tokens
    )


def price(usage_by_model: Mapping[str | None, Usage]) -> Priced | None:
    """List-price equivalent for a per-model usage split.

    Returns None only when NOTHING could be priced -- there is no honest number
    to report then, and 0.0 would read as "it was free", which is the error this
    tool exists to prevent. When some models price and others do not, the
    dollars cover the ones that do and the rest are NAMED, so a caller prints
    "$2.91 (1 model unpriced)" rather than a silently short total.
    """
    by_model: dict[str, float] = {}
    unpriced: list[str] = []
    unpriced_tokens = 0
    unattributed = 0

    for model, usage in usage_by_model.items():
        rate = BASE_RATE_PER_MTOK.get(canonical(model) or "")
        if rate is None:
            unpriced.append(model or "unknown")
            unpriced_tokens += usage.total
            continue
        unattributed += usage.cache_creation_unattributed
        by_model[model or "unknown"] = rate * weighted_tokens(usage) / 1_000_000

    if not by_model:
        return None
    return Priced(
        dollars=sum(by_model.values()),
        by_model=by_model,
        unpriced_models=tuple(sorted(unpriced)),
        unpriced_tokens=unpriced_tokens,
        unattributed_cache_creation=unattributed,
    )


def usage_by_model(records: Iterable[CallRecord]) -> dict[str | None, Usage]:
    totals: dict[str | None, Usage] = {}
    for record in records:
        totals[record.model] = totals.get(record.model, Usage.zero()) + record.usage
    return totals


def price_records(records: Iterable[CallRecord]) -> Priced | None:
    """Price a walk of calls. Note what it CANNOT see.

    A call marked `incomplete` by `load_records` carries a lower-bound
    `output_tokens`, so the dollars it contributes are a lower bound too. The
    flag survives into `CallRecord`; a caller reporting a total over records it
    did not check should say how many were incomplete.
    """
    return price(usage_by_model(records))
