"""Tests for the two threshold families: capacity, and cost.

The families are in different units on purpose (issue #23): capacity is a
fraction of the window, cost is absolute tokens. Most of what is asserted
here is that they stay that way.
"""

from __future__ import annotations

import pytest

from agent_yield.thresholds import (
    ALLOWANCE_HANDOFF,
    ALLOWANCE_LADDER,
    ALLOWANCE_STOP,
    ALLOWANCE_WINDOWS,
    COMPACT_AT_BOUNDARY,
    COMPACT_NOW,
    CONTEXT_WARN,
    COST_DISPATCH,
    COST_LADDER,
    COST_RESTART,
    COST_STOP,
    DEFAULT_WINDOW,
    FIVE_HOUR_POINTS_PER_MINUTE,
    MAX_OBSERVED_STEP_POINTS,
    PREFER_FRESH_SESSION_AT_BOUNDARY,
    RESTART_FACTOR,
    RESTART_HARD_FACTOR,
    allowance_advice,
    allowance_band,
    allowance_decision,
    allowance_says_stop,
    cost_advice,
    cost_band,
    cost_says_leave,
    minutes_of_allowance_left,
)

MILLION = DEFAULT_WINDOW


def test_the_bands_open_at_their_constants():
    assert cost_band(COST_DISPATCH - 1) == "cheap"
    assert cost_band(COST_DISPATCH) == "dispatch"
    assert cost_band(COST_RESTART - 1) == "dispatch"
    assert cost_band(COST_RESTART) == "restart"
    assert cost_band(COST_STOP - 1) == "restart"
    assert cost_band(COST_STOP) == "stop"


def test_the_cost_family_is_ordered_and_named_for_its_remedies():
    # Replaces the old ordering test, which compared 0.20 against 0.60 across
    # two families measuring different things. Once the units differ that
    # comparison is meaningless, which is #23's point in test form: the only
    # ordering left to assert is the one *within* each family.
    assert COST_DISPATCH < COST_RESTART < COST_STOP
    assert COST_LADDER == ("dispatch", "restart", "stop")
    assert PREFER_FRESH_SESSION_AT_BOUNDARY < CONTEXT_WARN < COMPACT_AT_BOUNDARY
    assert COMPACT_AT_BOUNDARY < COMPACT_NOW


def test_the_cost_family_takes_no_window():
    # Not a style preference: cost is `context x rate` and the window is not
    # in that expression. A window argument here is a bug, so the signature
    # refuses one rather than ignoring it.
    with pytest.raises(TypeError):
        cost_band(500_000, MILLION)
    with pytest.raises(TypeError):
        cost_advice(500_000, MILLION)


def test_the_same_call_costs_the_same_on_every_window():
    # The breaking case from #23: under fractions this one call was cheap on
    # a 2M window, at the knee on 1M and steep on 500K. Same call, same bill.
    for _window in (500_000, MILLION, 2_000_000):
        assert cost_band(400_000) == "dispatch"


def test_a_small_window_leaves_no_gap_because_capacity_covers_it():
    # The defence of the fraction form was that on a 200K-window model the
    # absolute family goes quiet when a session is in trouble. It does not:
    # a 150K call on a 200K window is 75% of capacity, so
    # COMPACT_AT_BOUNDARY is already firing. Cost silent there is correct.
    assert cost_band(150_000) == "cheap"
    assert 150_000 / 200_000 >= COMPACT_AT_BOUNDARY


def test_the_cheap_band_is_silent():
    assert cost_advice(50_000) is None
    assert not cost_says_leave(50_000)


def test_the_dispatch_band_says_dispatch_and_never_says_compact():
    advice = cost_advice(COST_DISPATCH + 1)
    assert "compact" not in advice.lower()
    assert "Dispatch" in advice
    assert "capacity is a separate question" in advice
    # Its remedy is to dispatch, not to leave -- the distinction the band
    # exists for. Blocking here would cut off the cheapest path out.
    assert not cost_says_leave(COST_DISPATCH + 1)


def test_the_restart_band_says_leave_at_the_next_boundary():
    advice = cost_advice(COST_RESTART + 1)
    assert "Do not compact" in advice
    assert "natural boundary" in advice
    assert cost_says_leave(COST_RESTART + 1)


def test_the_stop_band_says_leave_now_rather_than_at_a_boundary():
    # A third band earns its place only by naming a different action.
    advice = cost_advice(COST_STOP + 1)
    assert "Do not wait for a boundary" in advice
    assert "handoff" in advice
    assert cost_says_leave(COST_STOP + 1)


def test_every_band_names_a_distinct_action():
    said = {cost_advice(t) for t in (COST_DISPATCH, COST_RESTART, COST_STOP)}
    assert len(said) == 3


def test_advice_is_tokens_never_money():
    for context in (COST_DISPATCH, COST_RESTART, COST_STOP):
        assert "$" not in cost_advice(context)


def test_the_thresholds_are_recorded_with_the_share_of_calls_they_fire_on():
    # There is no knee to discover, so each constant is a policy choice about
    # what share of main-thread calls should trip it. The percentile is the
    # only thing that makes one corpus comparable with another, so the file
    # has to carry it -- and a threshold at the median, firing on half of
    # everything, is the failure RESTART_HARD_FACTOR = 4.0 was set to avoid.
    #
    # A RANGE, not one pooled number, and this test is why the defect lasted:
    # the earlier version demanded only a "%" and a "p" on the line, which a
    # pooled aggregate satisfies. It did (#80). The share is decomposable by
    # project -- 300,000 is p46 in one repo on this machine and p100 in
    # another -- so a single figure describes no project that produced it.
    # This is the dashboard's own rule (no decomposable aggregate without its
    # decomposition, #67/#68) turned on the constants themselves.
    import re
    from pathlib import Path

    source = Path(__file__).resolve().parents[1] / "src" / "agent_yield" / "thresholds.py"
    text = source.read_text()
    for name in ("COST_DISPATCH", "COST_RESTART", "COST_STOP"):
        line = next(ln for ln in text.splitlines() if ln.startswith(name))
        comment = line.split("#", 1)[1]
        assert "%" in comment, name
        assert re.search(r"p\d+-p\d+", comment), f"{name} lost its per-project range"
        assert "pooled" in comment, f"{name} lost the pooled figure the range is read against"


def test_the_hard_restart_factor_sits_well_above_the_advisory():
    # Both real sessions were abandoned at ~6x having ignored the advisory.
    # A boundary near the advisory would fire in every working session.
    assert RESTART_HARD_FACTOR > RESTART_FACTOR
    assert RESTART_HARD_FACTOR >= 2 * RESTART_FACTOR


# --- The third family: the allowance, which is neither capacity nor cost ----
#
# It is in a third unit -- percent of a plan window -- and that is the point.
# Capacity asks how much room is left, cost asks what the next call bills, and
# both are quantities the operator can decide to spend anyway. This one ends
# the session whatever the operator decides, which is why it is the only band
# here whose remedy is "write it down" rather than "spend it differently".

def test_the_band_is_at_or_above_never_crossed():
    """The defect this forecloses is the one the log's step size guarantees.

    The window moves up to 4 points between consecutive renders (5% at 20:17,
    9% at 20:30 on 2026-08-26), so a session can go 78 -> 82 and never take
    the value 80. Any test of the form "did it cross" misses that session
    entirely.
    """
    assert allowance_band(ALLOWANCE_HANDOFF - 1) == "clear"
    assert allowance_band(ALLOWANCE_HANDOFF) == "handoff"
    assert allowance_band(ALLOWANCE_STOP - 1) == "handoff"
    assert allowance_band(ALLOWANCE_STOP) == "stop"
    # The jump that skips both exact thresholds still lands in the band.
    assert allowance_band(ALLOWANCE_STOP + 2) == "stop"


def test_no_single_render_can_jump_the_whole_band():
    # The gap has to be wider than the largest step ever observed, or a
    # session can pass from "clear" to capped without a render in between
    # where anything could have fired.
    assert ALLOWANCE_STOP - ALLOWANCE_HANDOFF > MAX_OBSERVED_STEP_POINTS
    assert 100 - ALLOWANCE_STOP > MAX_OBSERVED_STEP_POINTS


def test_a_window_that_was_not_reported_is_not_a_window_at_zero():
    # Same refusal as allowance.read_allowance: absent means the client did
    # not send the block. 0% would read as a fresh allowance and silence the
    # band exactly when the client is the one that cannot be measured.
    assert allowance_band(None) == "clear"
    assert allowance_advice("five_hour", None) is None
    assert not allowance_says_stop("five_hour", None)


def test_the_stop_band_leaves_room_for_the_remedy_it_names():
    # The band's whole justification: at the one measured rate there is still
    # time to write a handoff after it fires. One turn, not one minute.
    minutes = minutes_of_allowance_left(ALLOWANCE_STOP)
    assert minutes == (100 - ALLOWANCE_STOP) / FIVE_HOUR_POINTS_PER_MINUTE
    assert minutes >= 15
    assert minutes_of_allowance_left(ALLOWANCE_HANDOFF) > minutes
    # Past the cap the answer is zero, never negative time.
    assert minutes_of_allowance_left(120) == 0.0


def test_the_two_windows_get_different_advice_at_the_same_percentage():
    """The reason they are two bands and not one.

    Five-hour refills on its own, so its remedy is write it down and wait.
    Seven-day ends the week, so its remedy is write it down and stop. A
    single band would have to pick one of those and be wrong half the time.
    """
    five, seven = (allowance_advice(w, 95) for w in ALLOWANCE_WINDOWS)
    assert five != seven
    assert "refills on its own" in five
    assert "does not come back this week" in seven


def test_a_reset_that_beats_the_burn_rate_downgrades_the_five_hour_stop():
    # resets_at is in the CONDITION, not just the wording: 95% with the window
    # returning in four minutes is not the same situation as 95% with four
    # hours of it left to burn, and only one of them is worth refusing a
    # dispatch over.
    assert allowance_decision("five_hour", 95) == "stop"
    assert allowance_decision("five_hour", 95, minutes_to_reset=4) == "handoff"
    assert allowance_decision("five_hour", 95, minutes_to_reset=90) == "stop"
    assert not allowance_says_stop("five_hour", 95, minutes_to_reset=4)


def test_the_seven_day_window_never_downgrades_on_its_reset():
    # There is no measured climb rate for the seven-day window, so there is
    # nothing to say it is safe with. Borrowing the five-hour rate would be a
    # fabrication with a decimal point on it.
    assert allowance_decision("seven_day", 95, minutes_to_reset=1) == "stop"
    assert allowance_says_stop("seven_day", 95, minutes_to_reset=1)


def test_the_ladder_names_remedies_and_the_bands_do_not_share_one():
    # Same rule COST_LADDER is held to: a band that shares another's remedy
    # should not exist.
    assert ALLOWANCE_LADDER == ("handoff", "stop")
    said = {allowance_advice(w, pct)
            for w in ALLOWANCE_WINDOWS
            for pct in (ALLOWANCE_HANDOFF, ALLOWANCE_STOP)}
    assert len(said) == 4


def test_the_chosen_numbers_say_they_are_chosen():
    """The distinction this repo exists to make, applied to its own constants.

    A handoff moves `used_percentage` by less than its 1-point resolution, so
    no amount of logging can measure the room these numbers reserve. They are
    policy, and the file has to say so where the next person edits them.
    """
    from pathlib import Path

    source = Path(__file__).resolve().parents[1] / "src" / "agent_yield" / "thresholds.py"
    text = source.read_text()
    block = text.split("# Allowance: the plan's rate limit", 1)[1]
    block = block.split("ALLOWANCE_HANDOFF", 1)[0]
    assert "CHOSEN" in block
    assert "MEASURED" in block, "the rate the numbers are read against"
    assert "0.5 points per minute" in block


def test_the_advice_never_prices_the_allowance_in_dollars():
    # Same rule as cost_advice, and it bites harder here: allowance.py's whole
    # argument is that the plan's size is calibrated and never declared, so a
    # dollar figure in a hook message would be the tier table it refuses.
    for window in ALLOWANCE_WINDOWS:
        for pct in (ALLOWANCE_HANDOFF, ALLOWANCE_STOP):
            assert "$" not in allowance_advice(window, pct)
