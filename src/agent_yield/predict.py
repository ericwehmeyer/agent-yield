"""What a dispatch is about to cost, before you spend it.

cost ~= tool_calls x context_size. This is a warning aid, not a forecast, and
it covers two populations that do not overlap at all: an un-briefed subagent
(context ~136K/call, 62-188 calls) and a briefed dispatch (context
17.6K-67K/call, 4-27 calls). Treating them as one population is what made the
old default overestimate a briefed dispatch by 5-100x -- see issue #18 Part D.

A band this wide could instead refuse to give a number (issue #13). This
module chooses to keep the band, scoped per population: once the two
populations are told apart, the briefed band lands within 2x of the four
measured dispatches, which is useful; refusing would throw that away. What it
must never do is imply more precision than it has, so every projection names
its population and, when the context figure is a reference rather than a
measurement, says so.
"""
from __future__ import annotations

from dataclasses import dataclass

from .thresholds import (
    BRIEFED_CALL_RANGE,
    BRIEFED_CONTEXT_RANGE,
    BRIEFED_DEFAULT_EXPECTED_CALLS,
    BRIEFED_REFERENCE_CONTEXT,
    DEFAULT_EXPECTED_CALLS,
    OBSERVED_CALL_RANGE,
    REFERENCE_CONTEXT,
)

_POPULATIONS = {
    "subagent": {
        "reference_context": REFERENCE_CONTEXT,
        "context_range": (REFERENCE_CONTEXT, REFERENCE_CONTEXT),
        "default_calls": DEFAULT_EXPECTED_CALLS,
        "call_range": OBSERVED_CALL_RANGE,
    },
    "briefed": {
        "reference_context": BRIEFED_REFERENCE_CONTEXT,
        "context_range": BRIEFED_CONTEXT_RANGE,
        "default_calls": BRIEFED_DEFAULT_EXPECTED_CALLS,
        "call_range": BRIEFED_CALL_RANGE,
    },
}


@dataclass(frozen=True)
class Projection:
    context: int
    calls: int
    low: int
    expected: int
    high: int
    population: str
    context_is_fallback: bool

    def describe(self) -> str:
        note = (
            " (context is a reference figure, not measured for this dispatch)"
            if self.context_is_fallback
            else ""
        )
        return (
            f"~{self.expected / 1e6:.1f}M tokens "
            f"(range {self.low / 1e6:.1f}M-{self.high / 1e6:.1f}M) "
            f"at {self.context:,} context x {self.calls} calls "
            f"[{self.population} population]{note}"
        )


def project(
    context_size: int | None = None,
    expected_calls: int | None = None,
    *,
    population: str = "subagent",
) -> Projection:
    """Project token cost for one dispatch.

    `context_size` should be the measured cache-read context for this
    dispatch. If it is not known yet, omit it (or pass None) and the
    population's reference context is used instead -- `describe()` will say
    so. `population` selects which observed population's call range and
    reference context apply: "subagent" (the default, un-briefed) or
    "briefed" (self-contained brief, told not to explore).

    Calling `project(context_size)` with no other arguments reproduces the
    original single-population behaviour exactly.
    """
    if population not in _POPULATIONS:
        raise ValueError(
            f"unknown population {population!r}: expected 'subagent' or 'briefed'"
        )
    pop = _POPULATIONS[population]

    context_is_fallback = context_size is None
    if context_is_fallback:
        context = pop["reference_context"]
        context_low, context_high = pop["context_range"]
    else:
        context = context_size
        context_low = context_high = context_size

    calls = expected_calls if expected_calls is not None else pop["default_calls"]
    calls_low, calls_high = pop["call_range"]

    return Projection(
        context=context,
        calls=calls,
        low=context_low * calls_low,
        expected=context * calls,
        high=context_high * calls_high,
        population=population,
        context_is_fallback=context_is_fallback,
    )
