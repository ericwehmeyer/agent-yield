"""The numbers from design.md section 5, in one place.

PROVISIONAL. These are calibrated from a single month of one operator's data
and are meant to be revisited once two weeks of recorded yield exist. They are
gathered here so that revising them is one edit, not a search.

The dispatch model below covers two populations that do not overlap: an
un-briefed subagent (left free to explore) and a briefed dispatch (given a
self-contained brief and told not to explore). Their call ranges do not
overlap at all -- 62-188 versus 4-27 -- so a projection must say which one
it means. The briefed numbers are also PROVISIONAL, from four dispatches
measured on 2026-08-26.
"""
from __future__ import annotations

# Context, as a fraction of the window.
CONTEXT_WARN = 0.60
COMPACT_AT_BOUNDARY = 0.75
COMPACT_NOW = 0.85
PREFER_FRESH_SESSION_AT_BOUNDARY = 0.50

# Tokens.
DAILY_CEILING = 750_000_000
DAILY_WARN = 450_000_000
SESSION_SOFT_BUDGET = 400_000_000

# Dispatch model, from docs/case-study.md. This population is the un-briefed
# subagent: left free to explore, no brief telling it not to.
REFERENCE_CONTEXT = 136_449          # cache-read tokens per call, 2026-08-24
DEFAULT_EXPECTED_CALLS = 69          # median of the twelve agents on record
OBSERVED_CALL_RANGE = (62, 188)      # the 3x spread; this is why it is a band

# Briefed-dispatch population: self-contained brief, told not to explore.
# Four dispatches measured 2026-08-26 (issue #18 Part D correction); the
# un-briefed numbers above overestimated these by 5-100x.
BRIEFED_CONTEXT_RANGE = (17_580, 67_123)  # low-high context/call across the four, 2026-08-26
BRIEFED_REFERENCE_CONTEXT = 31_618        # median context/call across the four, 2026-08-26
BRIEFED_DEFAULT_EXPECTED_CALLS = 12       # median call count across the four, 2026-08-26
BRIEFED_CALL_RANGE = (4, 27)              # observed spread; does not overlap OBSERVED_CALL_RANGE above


def band_for_day(day_total: int) -> str:
    """Which of the three bands a day's spend falls in."""
    if day_total >= DAILY_CEILING:
        return "over"
    if day_total >= DAILY_WARN:
        return "warn"
    return "silent"
