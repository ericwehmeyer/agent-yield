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
# than "how much room is left". ABSOLUTE TOKENS, and the units are the point
# (issue #23): cost is `context x rate`, and the window does not appear in
# that expression, so a fraction of the window moves when the window moves
# while the bill does not. The same 200,000-token call cannot be cheap on a
# 2M window and expensive on a 500K one; it costs the same either way.
#
# MEASURED: the concentration is real, and it is the one thing here that
# survives decomposition -- above 150K the share of the BILL runs well ahead
# of the share of CALLS in every project measured, not just in the pooled
# corpus. What does not survive is the pair of numbers: "~60% of calls, ~87%
# of the bill" was the two-corpus pooled figure, and on 2026-08-26 the three
# macOS projects give 28%/45%, 72%/93% and 72%/90% against a pooled 45%/74%
# (#80). The direction replicates; the magnitudes are a mixture.
#
# CHOSEN: every number below. There is NO KNEE -- plotted continuously the
# spend curve decays smoothly on both machines with no break anywhere, so no
# threshold can be discovered here and each one is a policy choice about what
# share of calls should trip it. That share is recorded next to the constant,
# because it is the only honest way to compare one corpus with another: the
# same token count sits at a different percentile on a different machine --
# and, #80, at a different percentile in a different PROJECT on the same
# machine, by a wider margin than the two machines differ.
#
# The shares were first recorded 2026-08-25 as ONE POOLED FIGURE over a macOS
# corpus of 1,165 main calls -- ~35% (p65) / ~13% (p87) / ~7% (p93). THAT FORM
# WAS THE DEFECT (#80). The share is decomposable by PROJECT, and the pooled
# number describes none of them. Re-measured 2026-08-26 over every main-thread
# call under ~/.claude/projects, 300,000 sits at p46 in model-migration-kit and
# at p100 in agent-yield -- same machine, same week. That spread is WIDER than
# the macOS-vs-Windows gap the caveat was written to warn about. The pooled
# figure itself moved 46% -> 18% between the two dates with nothing changed
# about how any session is run: the mixture changed, from 100% Pictures +
# model-migration-kit on the calibration day to 96% agent-yield today.
#
# So each constant carries a RANGE across projects first and the pooled figure
# second. Main-thread calls, macOS, 2,425 calls over three projects,
# 2026-08-26; n = 1,490 agent-yield / 437 model-migration-kit / 498 Pictures.
# The Windows corpus (20,255 calls) has never been decomposed this way.
#
# DO NOT RETUNE THESE PER PROJECT. #23 put cost in absolute tokens so that a
# threshold would stop being a property of the observer -- a fraction of the
# window moved when the window moved. Retuning per repo is the same error with
# `project` substituted for `window`: the same 300,000-token call costs the
# same in either repo, and it cannot be expensive in one and cheap in the
# other. A repo whose calls never get expensive SHOULD see this family stay
# silent, which is the argument section 5 already makes for small windows.
COST_DISPATCH = 300_000   # 0%-54% of main calls (p46-p100), 0%-84% of the bill; pooled 18% (p82), 48%
COST_RESTART = 500_000    # 0%-33% (p67-p100), 0%-63% of the bill; pooled 7% (p93), 27%
COST_STOP = 700_000       # 0%-19% (p81-p100), 0%-42% of the bill; pooled 4% (p96), 15%

# The order the bands are entered in. Named for their remedy, not for a shape
# in the curve, because the curve has no shape: what distinguishes the bands
# is what to do, and a band that shares another's remedy should not exist.
COST_LADDER = ("dispatch", "restart", "stop")

# Why abandoning fractions leaves no gap, so nobody "fixes" this back later.
# The defence of the fraction form was that on a small-window model an
# absolute 300K threshold never fires and the family goes quiet exactly when
# a session is in trouble. It does not hold: on a 200K window a 150K call is
# already 75% of capacity and COMPACT_AT_BOUNDARY is firing. Capacity is
# genuinely fractional; cost genuinely is not; together they cover both
# regimes, and the cost family being silent on a small window is correct
# behaviour rather than a hole.

# LAST RESORT, and it should almost never be reached. Two better answers come
# first: the window the session reports in its own payload, and failing that
# `pricing.MODEL_WINDOWS`, which is observed from `modelUsage.contextWindow`
# and so is a fact about the model rather than a habit of this operator. 1M is
# this operator's working default and nothing more; reaching it means the tool
# does not know which model it is looking at.
DEFAULT_WINDOW = 1_000_000

# Session growth, the other trigger: context/call relative to the session's
# opening calls. PROVISIONAL. The advisory factor is section 11's doubling.
# The hard factor is deliberately well above it: two sessions on two machines
# were abandoned at 6.0x and 6.6x having ignored the advisory throughout, so
# a boundary set near the advisory would fire in every working session and be
# disabled. A boundary that gets disabled is worth nothing.
RESTART_FACTOR = 2.0
RESTART_HARD_FACTOR = 4.0

# Tokens, and CRUDE ONES -- #52's defect at the scale of a day. These are
# summed from `usage.total`, and ~97% of that sum is cache reads, which cost
# 0.10x a base input token. A raw total therefore nearly counts the cheapest
# thing in the system, and two days with the same total can differ by a factor
# in what they actually cost.
#
# NOT re-denominated in dollars yet, on purpose. `gate._day_total` reads a
# `calls.jsonl` that does not exist on either machine, so this band returns 0
# and has never fired. Re-pricing an unreachable branch is not measurement:
# it would look like progress and be untested against anything. Re-denominate
# when the gate is actually wired, and score the change then.
DAILY_CEILING = 750_000_000
DAILY_WARN = 450_000_000

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
BRIEFED_CALL_RANGE = (4, 27)              # observed spread across the hand-identified four, 2026-08-26
# CORRECTION 2026-08-25 (#18 Part C, `agent-yield agents`). Two corrections,
# and the second retracts the first -- both kept, because the sequence is the
# lesson.
#
# FIRST, WRONG: pooled over 73 dispatches from every project on the machine,
# marker-briefed dispatches showed a median 6 calls against 57 un-briefed, and
# that 9.5x was written up as "the first evidence that the markers predict
# length". It reached two issue comments before anyone checked it.
#
# SECOND, CORRECT: the effect was entirely PROJECT. All 61 long un-briefed
# dispatches came from one repo's audit fleet; all 4 briefed ones from another.
# Exactly one project held both groups, and within it:
#
#     agent-yield   briefed n=4  median 6.0 calls, 39,139 ctx/call
#               un-briefed n=8  median 6.5 calls, 28,353 ctx/call
#
# The call difference vanishes and the briefed dispatches carry MORE context.
# **There is currently no evidence that the three detectable markers predict
# dispatch length.** `agents.render` now refuses the pooled comparison.
#
# What survives: "does not overlap OBSERVED_CALL_RANGE" is still retired --
# within agent-yield the un-briefed range is 3-27 against briefed 3-30. True
# of eight hand-picked dispatches, false of the twelve measured here.
#
# THIRD, 2026-08-25 (#32): the detector that produced the n=4/n=8 split was
# itself broken -- it tested for wording, not for the property, and scored
# 0 of 3 markers on all five briefs this repo wrote to its own rubric. Fixed,
# and the same twelve dispatches re-scored: briefed n=5 median 3.0 calls,
# un-briefed n=7 median 9.0. ONE dispatch was reclassified and both medians
# moved three calls. That does not resurrect the effect -- it shows the
# comparison is one row wide at n=12. The ranges still overlap (3-30 vs 3-27)
# and ctx/call is still flat (29,356 vs 31,108). "No evidence the markers
# predict length" stands; working-method.md 12.2 has the full re-score.
#
# The constants below are left alone. Part C reports, it does not retune, and
# it has less to retune with than it appeared to an hour ago.


def band_for_day(day_total: int) -> str:
    """Which of the three bands a day's spend falls in."""
    if day_total >= DAILY_CEILING:
        return "over"
    if day_total >= DAILY_WARN:
        return "warn"
    return "silent"


def cost_band(context: int) -> str:
    """Which cost band one call's context sits in, in tokens.

    MAIN-THREAD CALLS ONLY. Main and subagent are two populations 2.1x-2.6x
    apart -- median 184,905 against 88,201 here -- and a subagent above these
    numbers is a brief that failed, not a session to restart. Same token
    count, different diagnosis, different remedy; one family cannot serve
    both, so this one does not try.

    No ``window`` argument, deliberately: a call's bill is `context x rate`
    and the window is not in that expression (issue #23). Capacity questions
    take the window; this one cannot.

    Level, not growth. `session.restart_advice` catches sessions that run
    away; this catches sessions that open expensive, which is the norm --
    one machine's main sessions averaged 311,399 context/call with no
    doubling anywhere.
    """
    if context >= COST_STOP:
        return "stop"
    if context >= COST_RESTART:
        return "restart"
    if context >= COST_DISPATCH:
        return "dispatch"
    return "cheap"


def cost_says_leave(context: int) -> bool:
    """Whether the band's remedy is "end this session"."""
    return cost_band(context) in ("restart", "stop")


# Deliberately not the capacity wording, and it never says compact: a compact
# pays a summarization pass to stay in the expensive band. Each band names one
# action, and the actions differ -- otherwise the band would not be here.
_COST_ADVICE = {
    "dispatch": (
        "This call carries {context:,} tokens, past {COST_DISPATCH:,}. Every "
        "call from here re-reads all of it. Dispatch reads and searches to "
        "briefed subagents and keep this context flat. This is spend, not "
        "space -- capacity is a separate question and may be fine."
    ),
    "restart": (
        "This call carries {context:,} tokens, past {COST_RESTART:,}. At the "
        "next natural boundary -- work landed, checks green, pushed -- write "
        "findings down and start fresh. Do not compact: a compact pays a "
        "summarization pass to stay in the expensive band; a restart leaves "
        "it."
    ),
    "stop": (
        "This call carries {context:,} tokens, past {COST_STOP:,}. Do not "
        "wait for a boundary. Run `agent-yield handoff`, then start a fresh "
        "session; the next 40 calls here bill several times what they would "
        "there."
    ),
}


def cost_advice(context: int) -> str | None:
    """What to do about the band, or ``None`` in the cheap band."""
    template = _COST_ADVICE.get(cost_band(context))
    if template is None:
        return None
    return template.format(
        context=context,
        COST_DISPATCH=COST_DISPATCH,
        COST_RESTART=COST_RESTART,
        COST_STOP=COST_STOP,
    )


# CHOSEN, not measured. Seven days is long enough that a same-week rewrite
# lands inside it and short enough to score a day within the week it happened.
# Re-derive it once there is enough history to measure where survival actually
# flattens; until then it is a convention and is labelled one.
SURVIVAL_HORIZON_DAYS = 7
