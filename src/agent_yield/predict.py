"""What a dispatch is about to cost, before you spend it.

cost ~= tool_calls x context_size. This is a warning aid, not a forecast: the
observed call count across recorded agents spans 62 to 188, a 3x spread, so a
single number here would be false precision.
"""
from __future__ import annotations

from dataclasses import dataclass

from .thresholds import DEFAULT_EXPECTED_CALLS, OBSERVED_CALL_RANGE


@dataclass(frozen=True)
class Projection:
    context: int
    calls: int
    low: int
    expected: int
    high: int

    def describe(self) -> str:
        return (
            f"~{self.expected / 1e6:.1f}M tokens "
            f"(range {self.low / 1e6:.1f}M-{self.high / 1e6:.1f}M) "
            f"at {self.context:,} context x {self.calls} calls"
        )


def project(
    context_size: int, expected_calls: int = DEFAULT_EXPECTED_CALLS
) -> Projection:
    low_calls, high_calls = OBSERVED_CALL_RANGE
    return Projection(
        context=context_size,
        calls=expected_calls,
        low=context_size * low_calls,
        expected=context_size * expected_calls,
        high=context_size * high_calls,
    )
