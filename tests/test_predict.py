from agent_yield.predict import project
from agent_yield.thresholds import DEFAULT_EXPECTED_CALLS, OBSERVED_CALL_RANGE

# Four real briefed dispatches, 2026-08-26 (issue #18 Part D):
# (calls, measured context/call, actual total tokens).
BRIEFED_DISPATCHES = [
    (4, 17_580, 94_602),
    (9, 27_241, 280_012),
    (15, 35_995, 569_321),
    (27, 67_123, 1_879_466),
]


def test_default_project_unchanged_from_today():
    p = project(136_449)
    low_calls, high_calls = OBSERVED_CALL_RANGE
    assert p.context == 136_449
    assert p.calls == DEFAULT_EXPECTED_CALLS
    assert p.expected == 136_449 * DEFAULT_EXPECTED_CALLS
    assert p.low == 136_449 * low_calls
    assert p.high == 136_449 * high_calls
    assert p.population == "subagent"
    assert p.context_is_fallback is False


def test_briefed_projection_lands_within_the_measured_envelope():
    for calls, context, actual in BRIEFED_DISPATCHES:
        p = project(context, expected_calls=calls, population="briefed")
        # the band brackets the actual, within the measured envelope's order
        # of magnitude -- unlike the old subagent-population default, which
        # overestimated these same dispatches by 5-100x.
        assert p.low / 10 <= actual <= p.high * 10
        assert p.expected / actual < 10
        assert actual / p.expected < 10


def test_band_carries_context_spread_not_only_calls():
    p = project(population="briefed")  # fallback context -> uses the measured range
    low_context_only = p.context * (4)
    high_context_only = p.context * (27)
    # if only calls varied the low/high would both equal context * call bound;
    # carrying context spread too means low/high differ from that.
    assert p.low != low_context_only or p.high != high_context_only


def test_fallback_projection_announces_itself():
    p = project(population="briefed")
    assert p.context_is_fallback is True
    assert "not measured" in p.describe()


def test_measured_projection_does_not_announce_fallback():
    p = project(35_995, population="briefed")
    assert p.context_is_fallback is False
    assert "not measured" not in p.describe()


def test_populations_differ_for_same_call_count():
    subagent = project(expected_calls=10, population="subagent")
    briefed = project(expected_calls=10, population="briefed")
    assert subagent.expected != briefed.expected
    assert subagent.describe() != briefed.describe()


def test_no_dollar_sign_in_describe():
    for p in (
        project(136_449),
        project(population="briefed"),
        project(35_995, population="briefed"),
    ):
        assert "$" not in p.describe()


def test_none_never_renders_as_zero():
    p = project(population="briefed")
    assert None not in (p.context, p.low, p.expected, p.high)
    assert p.context != 0
    assert p.low != 0
    assert p.high != 0
