"""Tests for the two threshold families: capacity, and cost."""

from __future__ import annotations

from agent_yield.thresholds import (
    COMPACT_AT_BOUNDARY,
    COMPACT_NOW,
    CONTEXT_WARN,
    COST_KNEE,
    COST_STEEP,
    DEFAULT_WINDOW,
    PREFER_FRESH_SESSION_AT_BOUNDARY,
    RESTART_FACTOR,
    RESTART_HARD_FACTOR,
    cost_advice,
    cost_band,
)

MILLION = DEFAULT_WINDOW


def test_the_knee_sits_at_the_measured_200k_on_a_million_window():
    assert cost_band(199_999, MILLION) == "cheap"
    assert cost_band(200_000, MILLION) == "knee"
    assert cost_band(399_999, MILLION) == "knee"
    assert cost_band(400_000, MILLION) == "steep"


def test_the_cost_family_fires_ahead_of_every_capacity_threshold():
    # The whole point of #17: at 20% of window a session is silent by every
    # capacity rule while already in the band producing half the bill.
    assert COST_KNEE < COST_STEEP
    assert COST_STEEP < PREFER_FRESH_SESSION_AT_BOUNDARY
    assert PREFER_FRESH_SESSION_AT_BOUNDARY < CONTEXT_WARN < COMPACT_AT_BOUNDARY
    assert COMPACT_AT_BOUNDARY < COMPACT_NOW


def test_bands_are_fractions_so_they_survive_a_model_change():
    # A 200K window (Haiku 4.5) opens the same bands at 40K and 80K.
    assert cost_band(39_999, 200_000) == "cheap"
    assert cost_band(40_000, 200_000) == "knee"
    assert cost_band(80_000, 200_000) == "steep"


def test_the_cheap_band_is_silent():
    assert cost_advice(50_000, MILLION) is None


def test_the_knee_says_dispatch_and_never_says_compact():
    advice = cost_advice(250_000, MILLION)
    assert "compact" not in advice.lower()
    assert "Dispatch" in advice
    assert "capacity is fine" in advice


def test_steep_says_restart_and_explicitly_refuses_compaction():
    advice = cost_advice(600_000, MILLION)
    assert "Do not compact" in advice
    assert "start fresh" in advice


def test_advice_is_tokens_never_money():
    for context in (250_000, 600_000):
        assert "$" not in cost_advice(context, MILLION)


def test_an_unknown_window_never_divides_by_zero():
    assert cost_band(500_000, 0) == "cheap"
    assert cost_advice(500_000, 0) is None


def test_the_hard_restart_factor_sits_well_above_the_advisory():
    # Both real sessions were abandoned at ~6x having ignored the advisory.
    # A boundary near the advisory would fire in every working session.
    assert RESTART_HARD_FACTOR > RESTART_FACTOR
    assert RESTART_HARD_FACTOR >= 2 * RESTART_FACTOR
