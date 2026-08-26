"""The price table, checked against the CLI's own bill on four archived arms.

Every rate here is a measurement or it is a guess, and the difference is
whether a test reconciles it against ground truth. `modelUsage.costUSD` from
`claude -p` is that ground truth; `tests/fixtures/arms-33/ground-truth.json`
holds it, per model, for the four #33 arms.
"""
import json
from pathlib import Path

import pytest

from agent_yield.ingest import incomplete_calls, load_records
from agent_yield.pricing import (
    BASE_RATE_PER_MTOK,
    OUTPUT,
    Priced,
    canonical,
    price,
    price_records,
    window_for,
)
from agent_yield.usage import Usage

FIXTURES = Path(__file__).parent / "fixtures" / "arms-33"
TRUTH = json.loads((FIXTURES / "ground-truth.json").read_text())["arms"]
ARMS = sorted(TRUTH)
CENT = 0.005

# Billed on every arm and present in no transcript: harness-side work on Haiku.
UNTRANSCRIBED = "claude-haiku-4-5-20251001"
# The output tokens #53 locates in calls whose terminal record was never
# written. Priced, they are the entire difference between a transcript-only
# figure and the bill -- which is what makes them a located gap and not slack.
SHORTFALL = {"baton-r1": 4_361, "baton-r2": 287, "reader-r1": 0, "reader-r2": 0}


def usage_from_truth(totals: dict) -> Usage:
    """A model's archived totals as a `Usage`, with the TTL split from the
    transcripts -- `modelUsage` aggregates the two TTLs into one number."""
    return Usage(
        input_tokens=totals["input_tokens"],
        output_tokens=totals["output_tokens"],
        cache_creation_tokens=totals["cache_creation_tokens"],
        cache_read_tokens=totals["cache_read_tokens"],
    )


def transcript_split(name: str) -> tuple[int, int]:
    total = Usage.zero()
    for record in load_records([FIXTURES / f"{name}.jsonl"]):
        total = total + record.usage
    return total.cache_creation_5m, total.cache_creation_1h


@pytest.mark.parametrize("name", ARMS)
def test_the_table_reproduces_the_bill_to_the_cent(name):
    """The assertion that makes these rates measurements rather than constants.

    If a rate changes, or a multiplier is wrong, or a model is dropped, this
    fails -- on data that is committed and cannot quietly go stale.
    """
    five_minute, one_hour = transcript_split(name)
    split_applied = False
    by_model: dict[str, Usage] = {}
    for model, totals in TRUTH[name]["model_usage"].items():
        usage = usage_from_truth(totals)
        if model != UNTRANSCRIBED:
            assert not split_applied, "more than one transcribed model on an arm"
            usage = Usage(
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cache_creation_tokens=usage.cache_creation_tokens,
                cache_read_tokens=usage.cache_read_tokens,
                cache_creation_5m=five_minute,
                cache_creation_1h=one_hour,
            )
            assert usage.cache_creation_unattributed == 0
            split_applied = True
        by_model[model] = usage

    priced = price(by_model)
    assert priced is not None and priced.is_complete
    assert abs(priced.dollars - TRUTH[name]["total_cost_usd"]) < CENT
    for model, totals in TRUTH[name]["model_usage"].items():
        assert abs(priced.by_model[model] - totals["cost_usd"]) < CENT


@pytest.mark.parametrize("name", ARMS)
def test_a_transcript_only_price_is_short_by_exactly_what_is_missing(name):
    """Nothing here is a tolerance. The residual is accounted for, twice over.

    A transcript can only be short in two named ways: the Haiku spend it never
    records, and the output tokens of calls whose terminal record was never
    written (#53). Priced, those two numbers close the gap to the cent -- so a
    future discrepancy means a NEW defect, not a wider error bar.
    """
    priced = price_records(load_records([FIXTURES / f"{name}.jsonl"]))
    assert priced is not None

    truth = TRUTH[name]["model_usage"]
    billed_for_the_transcribed_model = truth["claude-opus-5"]["cost_usd"]
    missing_output = (SHORTFALL[name] * OUTPUT
                      * BASE_RATE_PER_MTOK["claude-opus-5"] / 1_000_000)
    assert abs(billed_for_the_transcribed_model - priced.dollars
               - missing_output) < CENT

    untranscribed = truth[UNTRANSCRIBED]["cost_usd"]
    assert abs(TRUTH[name]["total_cost_usd"] - priced.dollars
               - missing_output - untranscribed) < CENT


@pytest.mark.parametrize("name", ["reader-r1", "reader-r2"])
def test_an_arm_with_no_incomplete_call_prices_exactly(name):
    records = load_records([FIXTURES / f"{name}.jsonl"])
    assert incomplete_calls(records) == 0
    priced = price_records(records)
    assert abs(priced.dollars
               - TRUTH[name]["model_usage"]["claude-opus-5"]["cost_usd"]) < CENT


def test_the_ttl_split_is_worth_real_money():
    """Repricing every write at the dearer TTL is not a rounding difference.

    It is the check that the split earns its place: mispriced, the dispatching
    arm moves by cents on a three-dollar run, and the arms are separated by
    less than a dollar.
    """
    five_minute, one_hour = transcript_split("baton-r1")
    honest = price({"claude-opus-5": Usage(
        cache_creation_tokens=five_minute + one_hour,
        cache_creation_5m=five_minute, cache_creation_1h=one_hour)})
    as_if_all_hourly = price({"claude-opus-5": Usage(
        cache_creation_tokens=five_minute + one_hour,
        cache_creation_5m=0, cache_creation_1h=five_minute + one_hour)})
    assert as_if_all_hourly.dollars - honest.dollars > 0.4


# -- Refusing, rather than guessing -------------------------------------------

def test_an_unknown_model_is_named_and_not_priced():
    priced = price({"claude-opus-5": Usage(output_tokens=1_000),
                    "some-future-model": Usage(output_tokens=1_000)})
    assert priced.unpriced_models == ("some-future-model",)
    assert priced.unpriced_tokens == 1_000
    assert not priced.is_complete
    assert "some-future-model" in priced.caveat()
    # The dollars cover only what could be priced -- not a silently short total.
    assert priced.dollars == pytest.approx(1_000 * OUTPUT * 5.00 / 1_000_000)


def test_nothing_priceable_returns_none_not_zero():
    # 0.0 would read as "it was free", which is the error this tool exists to
    # prevent. See report_html.py's second rule.
    assert price({"some-future-model": Usage(output_tokens=10)}) is None
    assert price({}) is None


def test_writes_with_no_ttl_are_charged_the_default_and_named():
    priced = price({"claude-opus-5": Usage(cache_creation_tokens=1_000_000)})
    assert priced.unattributed_cache_creation == 1_000_000
    assert not priced.is_complete
    assert "no TTL" in priced.caveat()
    assert priced.dollars == pytest.approx(1.25 * 5.00)


def test_a_dated_model_id_prices_as_its_model():
    assert canonical("claude-haiku-4-5-20251001") == "claude-haiku-4-5"
    priced = price({"claude-haiku-4-5-20251001": Usage(input_tokens=1_000_000)})
    assert priced.dollars == pytest.approx(1.00)


# -- The context denominator ---------------------------------------------------

@pytest.mark.parametrize("name", ARMS)
def test_the_window_registry_matches_what_the_runs_observed(name):
    # Observed in `modelUsage.contextWindow`, not assumed. Transcript records
    # carry no window, so this is the only place the registry can be checked.
    for model, totals in TRUTH[name]["model_usage"].items():
        assert window_for(model) == totals["context_window"]


def test_an_unmeasured_model_has_no_window_rather_than_a_default():
    assert window_for("some-future-model") is None
    assert window_for(None) is None
