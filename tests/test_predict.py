from agent_yield.predict import project
from agent_yield.thresholds import DAILY_CEILING, DAILY_WARN, band_for_day


def test_projects_the_case_study_median_agent():
    """136K context x ~70 calls should land near the measured 12.4M median."""
    projection = project(context_size=136_449, expected_calls=70)
    assert projection.expected == 136_449 * 70
    assert 9_000_000 < projection.expected < 14_000_000


def test_projection_carries_the_observed_spread_not_a_point():
    projection = project(context_size=136_449)
    assert projection.low == 136_449 * 62
    assert projection.high == 136_449 * 188
    assert projection.low < projection.expected < projection.high


def test_default_expected_calls_is_the_observed_median():
    assert project(context_size=1).expected == 69


def test_describe_reports_tokens_never_money():
    described = project(136_449).describe()
    assert "M tokens" in described
    assert "$" not in described


def test_bands_follow_section_5():
    assert band_for_day(100) == "silent"
    assert band_for_day(DAILY_WARN) == "warn"
    assert band_for_day(DAILY_CEILING) == "over"
    assert band_for_day(DAILY_CEILING + 1) == "over"
