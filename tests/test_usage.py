from agent_yield.usage import Usage

# The 2026-08-24 column from docs/case-study.md. These four numbers sum to the
# recorded day total exactly, which is why this is a regression fixture and not
# an illustration.
AUG_24 = Usage(
    input_tokens=13_816,
    output_tokens=4_034_858,
    cache_creation_tokens=23_248_272,
    cache_read_tokens=942_865_149,
)


def test_total_matches_recorded_day_total():
    assert AUG_24.total == 970_162_095


def test_cache_read_share_of_the_recorded_day():
    # 942,865,149 / 970,162,095 = 97.2%.
    #
    # docs/case-study.md says "Cache reads are 97.4% of consumption" directly
    # beneath the table these four numbers come from. That figure does not fall
    # out of these numbers -- it may have been computed over the whole month
    # rather than this day. The share is load-bearing for the tool's thesis, so
    # this test asserts what the recorded column actually says.
    assert round(AUG_24.cache_read_share * 100, 1) == 97.2
    assert AUG_24.cache_read_share > 0.97


def test_fields_stay_separate_under_addition():
    doubled = AUG_24 + AUG_24
    assert doubled.cache_read_tokens == 1_885_730_298
    assert doubled.output_tokens == 8_069_716


def test_from_payload_reads_the_real_field_names():
    payload = {
        "input_tokens": 2,
        "output_tokens": 121,
        "cache_creation_input_tokens": 15_711,
        "cache_read_input_tokens": 31_316,
        # A real payload nests an `iterations` list repeating the same numbers.
        # Summing it on top of the top-level fields double-counts.
        "iterations": [{"input_tokens": 2, "output_tokens": 121}],
    }
    assert Usage.from_payload(payload) == Usage(2, 121, 15_711, 31_316)


def test_from_payload_tolerates_missing_fields():
    assert Usage.from_payload({}) == Usage.zero()
