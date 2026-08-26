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


# --- #81: the two rates that were missing while 44% of a day's calls used them.
#
# These arms exist for one purpose: to make `claude-sonnet-5` and
# `claude-fable-5` measurements instead of constants. The module's doctrine is
# that an unreconciled rate is the thing it exists to refuse, so a rate typed in
# from a price list would be exactly the defect. Each was solved from its own
# `-p` run and checked back against that run's `costUSD`.

RATE_FIXTURES = Path(__file__).parent / "fixtures" / "arms-81"
RATE_TRUTH = json.loads((RATE_FIXTURES / "ground-truth.json").read_text())["arms"]
RATE_ARMS = sorted(RATE_TRUTH)
# The arm each rate was solved from, so a broken reconciliation names the model
# whose number is now unsupported rather than just a filename.
RATE_UNDER_TEST = {"sonnet-rate": "claude-sonnet-5", "fable-rate": "claude-fable-5"}


def rate_transcript_split(name: str) -> dict[str, tuple[int, int]]:
    """The 5m/1h cache-write split per model, which `modelUsage` aggregates away.

    Measured, not assumed. Both arms came back 100% 1h, and that is load-bearing:
    priced as 5m writes the same bills solve to $2.6253 and $13.0536 rather than
    $2.00 and $10.00, so reading the TTL off the transcript is the difference
    between a rate and a plausible number.
    """
    split: dict[str, list[int]] = {}
    for record in load_records([RATE_FIXTURES / f"{name}.jsonl"]):
        model = canonical(record.model) or "?"
        held = split.setdefault(model, [0, 0])
        held[0] += record.usage.cache_creation_5m
        held[1] += record.usage.cache_creation_1h
    return {model: (a, b) for model, (a, b) in split.items()}


@pytest.mark.parametrize("name", RATE_ARMS)
def test_the_new_rates_reproduce_their_own_arms_bill(name):
    arm = RATE_TRUTH[name]
    split = rate_transcript_split(name)
    for model, totals in arm["model_usage"].items():
        write_5m, write_1h = split.get(canonical(model), (0, 0))
        usage = Usage(
            input_tokens=totals["input_tokens"],
            output_tokens=totals["output_tokens"],
            cache_read_tokens=totals["cache_read_tokens"],
            cache_creation_tokens=totals["cache_creation_tokens"],
            cache_creation_5m=write_5m,
            cache_creation_1h=write_1h,
        )
        priced = price({model: usage})
        assert priced.dollars == pytest.approx(totals["cost_usd"], abs=CENT), model
        assert priced.is_complete, priced.caveat()


@pytest.mark.parametrize("name", RATE_ARMS)
def test_the_haiku_control_still_holds_on_the_new_arms(name):
    """The control. Both arms bill harness-side Haiku at a rate measured
    elsewhere, on different traffic; if the model were wrong, the new numbers
    could still be tuned to fit and this would not."""
    totals = RATE_TRUTH[name]["model_usage"][UNTRANSCRIBED]
    priced = price({UNTRANSCRIBED: usage_from_truth(totals)})
    assert priced.dollars == pytest.approx(totals["cost_usd"], abs=CENT)


@pytest.mark.parametrize("name", RATE_ARMS)
def test_the_cache_writes_on_the_new_arms_were_all_one_hour(name):
    """Pinned because the solved rate depends on it. If a future arm writes 5m
    and this is relaxed rather than re-measured, the rates silently become the
    2.6253/13.0536 numbers that fit the wrong multiplier."""
    model = RATE_UNDER_TEST[name]
    write_5m, write_1h = rate_transcript_split(name)[model]
    assert write_1h > 0 and write_5m == 0


@pytest.mark.parametrize("name", RATE_ARMS)
def test_the_new_arms_windows_match_what_the_runs_observed(name):
    for model, totals in RATE_TRUTH[name]["model_usage"].items():
        assert window_for(model) == totals["context_window"], model


def test_every_rate_in_the_table_is_backed_by_an_arm():
    """The rule the table exists to enforce, turned on the table itself: a rate
    with no archived run behind it is the unreconciled constant this module
    refuses. #81 was that hole -- two models billed on real traffic and absent
    here -- and this fails the moment a fifth rate is typed in without one."""
    billed = {
        canonical(model)
        for truth in (TRUTH, RATE_TRUTH)
        for arm in truth.values()
        for model in arm["model_usage"]
    }
    assert set(BASE_RATE_PER_MTOK) <= billed, set(BASE_RATE_PER_MTOK) - billed
