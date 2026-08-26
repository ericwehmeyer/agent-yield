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

# Capacity: context as a fraction of the window. "Am I about to run out."
CONTEXT_WARN = 0.60
COMPACT_AT_BOUNDARY = 0.75
COMPACT_NOW = 0.85
PREFER_FRESH_SESSION_AT_BOUNDARY = 0.50

# Cost: the second family, answering "what does the next call bill" rather
# than "how much room is left". Measured 2026-08-25 over 20,273 calls: 47% of
# the cache-read bill came from the 20% of calls made above 200K context, a
# band every capacity rule above is silent in. Fractions, not token counts,
# so the family survives a model change. PROVISIONAL and calibrated on a 1M
# window only; on smaller windows it is conservative. See design.md section 5.
COST_KNEE = 0.20
COST_STEEP = 0.40

# The tool cannot read the model's context window, so a caller must say. 1M
# is this operator's working default, not a fact about any model.
DEFAULT_WINDOW = 1_000_000

# Session growth, the other trigger: context/call relative to the session's
# opening calls. PROVISIONAL. The advisory factor is section 11's doubling.
# The hard factor is deliberately well above it: two sessions on two machines
# were abandoned at 6.0x and 6.6x having ignored the advisory throughout, so
# a boundary set near the advisory would fire in every working session and be
# disabled. A boundary that gets disabled is worth nothing.
RESTART_FACTOR = 2.0
RESTART_HARD_FACTOR = 4.0

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


def cost_band(context: int, window: int = DEFAULT_WINDOW) -> str:
    """Which cost band one call's context sits in: cheap, knee, or steep.

    Level, not growth. `session.restart_advice` catches sessions that run
    away; this catches sessions that open expensive, which is the norm --
    one machine's main sessions averaged 311,399 context/call with no
    doubling anywhere.
    """
    if window <= 0:
        return "cheap"
    fraction = context / window
    if fraction >= COST_STEEP:
        return "steep"
    if fraction >= COST_KNEE:
        return "knee"
    return "cheap"


# Deliberately not the capacity wording, and it never says compact: a compact
# pays a summarization pass to stay in the expensive band.
_COST_ADVICE = {
    "knee": (
        "Past the cost knee ({fraction:.0%} of a {window:,} window). Calls "
        "from here bill about 3x the cheap band. Dispatch reads and searches "
        "to subagents and keep this context flat. This is spend, not space "
        "-- capacity is fine."
    ),
    "steep": (
        "Deep in the expensive band ({fraction:.0%} of a {window:,} window). "
        "At the next natural boundary, write findings down and start fresh. "
        "Do not compact -- a compact pays a summarization pass to stay in "
        "the expensive band; a restart leaves it."
    ),
}


def cost_advice(context: int, window: int = DEFAULT_WINDOW) -> str | None:
    """What to do about the band, or ``None`` in the cheap band."""
    band = cost_band(context, window)
    template = _COST_ADVICE.get(band)
    if template is None or window <= 0:
        return None
    return template.format(fraction=context / window, window=window)
