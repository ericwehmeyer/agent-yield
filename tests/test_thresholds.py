"""Tests for the two threshold families: capacity, and cost.

The families are in different units on purpose (issue #23): capacity is a
fraction of the window, cost is absolute tokens. Most of what is asserted
here is that they stay that way.
"""

from __future__ import annotations

import pytest

from agent_yield.thresholds import (
    COMPACT_AT_BOUNDARY,
    COMPACT_NOW,
    CONTEXT_WARN,
    COST_DISPATCH,
    COST_LADDER,
    COST_RESTART,
    COST_STOP,
    DEFAULT_WINDOW,
    PREFER_FRESH_SESSION_AT_BOUNDARY,
    RESTART_FACTOR,
    RESTART_HARD_FACTOR,
    cost_advice,
    cost_band,
    cost_says_leave,
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
