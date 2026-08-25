"""The numbers from design.md section 5, in one place.

PROVISIONAL. These are calibrated from a single month of one operator's data
and are meant to be revisited once two weeks of recorded yield exist. They are
gathered here so that revising them is one edit, not a search.
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

# Dispatch model, from docs/case-study.md.
REFERENCE_CONTEXT = 136_449          # cache-read tokens per call, 2026-08-24
DEFAULT_EXPECTED_CALLS = 69          # median of the twelve agents on record
OBSERVED_CALL_RANGE = (62, 188)      # the 3x spread; this is why it is a band


def band_for_day(day_total: int) -> str:
    """Which of the three bands a day's spend falls in."""
    if day_total >= DAILY_CEILING:
        return "over"
    if day_total >= DAILY_WARN:
        return "warn"
    return "silent"
