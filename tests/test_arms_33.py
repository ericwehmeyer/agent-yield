"""The instrument, checked against the four archived #33 arms.

This repo's recurring lesson: an instrument that cannot tell the KNOWN cases
apart cannot tell a NEW case apart. #26, #32 and #44 each shipped a scorer that
could not, and each was wrong. So before anything is priced or compared, the
ingest is checked against the CLI's own accounting on arms whose answers are
already in the archive.

`tests/fixtures/arms-33/*.jsonl` are the real transcript records of those arms,
reduced to the fields `parse_line` reads. `ground-truth.json` beside them holds
the `modelUsage` and `total_cost_usd` blocks from `claude -p`. The live
transcripts under `~/.claude` are volatile and one arm's are already gone,
which is why both halves are committed.
"""
import json
from collections import defaultdict
from pathlib import Path

import pytest

from agent_yield.ingest import incomplete_calls, load_records
from agent_yield.usage import Usage

FIXTURES = Path(__file__).parent / "fixtures" / "arms-33"
TRUTH = json.loads((FIXTURES / "ground-truth.json").read_text())["arms"]

# Arms whose every call left a terminal record. On these the transcript can be
# reconciled EXACTLY -- no tolerance, because there is nothing to tolerate.
COMPLETE = ["reader-r1", "reader-r2"]
# Arms holding calls whose terminal record was never written. Their output total
# is a lower bound, and the shortfall must live entirely in those calls.
INCOMPLETE = {"baton-r1": 2, "baton-r2": 2}

# Present in every arm's `modelUsage` and in NO transcript record: the harness
# does its own small work on Haiku, and it leaves no transcript behind. Carved
# out by name, with the reason, rather than left to fail the assertion forever.
UNTRANSCRIBED_MODELS = {"claude-haiku-4-5-20251001"}


def arm(name: str) -> list:
    return load_records([FIXTURES / f"{name}.jsonl"])


def truth_for(name: str) -> dict:
    return {model: totals
            for model, totals in TRUTH[name]["model_usage"].items()
            if model not in UNTRANSCRIBED_MODELS}


def by_model(records) -> dict[str, Usage]:
    totals: dict[str, Usage] = defaultdict(Usage.zero)
    for record in records:
        totals[record.model] = totals[record.model] + record.usage
    return dict(totals)


@pytest.mark.parametrize("name", COMPLETE + list(INCOMPLETE))
def test_cache_and_input_reconcile_exactly_on_every_arm(name):
    # Cache figures are byte-identical across a call's records, so no dedup rule
    # can get them wrong -- which is exactly why they hid the output bug. They
    # are asserted anyway: they are what proves the grouping itself is right.
    totals = by_model(arm(name))
    for model, expected in truth_for(name).items():
        assert totals[model].cache_read_tokens == expected["cache_read_tokens"]
        assert totals[model].cache_creation_tokens == expected["cache_creation_tokens"]
        assert totals[model].input_tokens == expected["input_tokens"]


@pytest.mark.parametrize("name", COMPLETE)
def test_output_reconciles_exactly_where_no_call_is_incomplete(name):
    # The assertion the old keep-first rule failed, and the reason it is stated
    # as equality rather than a floor: a >=90% tolerance would pass this arm at
    # 89.7% or at 100% and could not say which.
    records = arm(name)
    assert incomplete_calls(records) == 0
    totals = by_model(records)
    for model, expected in truth_for(name).items():
        assert totals[model].output_tokens == expected["output_tokens"]


# The measured shortfall on each incomplete arm, pinned. These are not
# tolerances -- they are the size of a known, located gap, and a test that
# pins them fails when the gap moves in either direction.
SHORTFALL = {"baton-r1": 4_361, "baton-r2": 287}


@pytest.mark.parametrize("name,expected_incomplete", INCOMPLETE.items())
def test_the_incomplete_arms_are_short_by_exactly_the_known_gap(name, expected_incomplete):
    records = arm(name)
    assert incomplete_calls(records) == expected_incomplete

    totals = by_model(records)
    for model, expected in truth_for(name).items():
        assert expected["output_tokens"] - totals[model].output_tokens == SHORTFALL[name]


@pytest.mark.parametrize("name", COMPLETE + list(INCOMPLETE))
def test_an_arm_is_short_if_and_only_if_it_holds_an_incomplete_call(name):
    """The claim that makes incompleteness a diagnosis rather than a tolerance.

    Across the four arms the correlation is perfect: 2 incomplete calls on
    baton-r1 and 2 on baton-r2 with a shortfall, 0 on both reader arms with
    none. If a future arm is short while reporting every call complete, the
    dedup rule is wrong and this fails -- which a >=90% floor could not do.
    """
    records = arm(name)
    totals = by_model(records)
    short = any(expected["output_tokens"] > totals[model].output_tokens
                for model, expected in truth_for(name).items())
    assert short == (incomplete_calls(records) > 0)


def test_keeping_the_first_record_is_what_the_old_rule_did():
    # The bug, stated as a number. Ordering the fixture's records and taking the
    # first of each group reproduces the 7,912 that shipped, against the 42,292
    # the CLI billed and the 37,931 the terminal rule recovers.
    first: dict[tuple[str, str], int] = {}
    for line in (FIXTURES / "baton-r1.jsonl").read_text().splitlines():
        payload = json.loads(line)
        key = (payload["message"]["id"], payload["requestId"])
        first.setdefault(key, payload["message"]["usage"]["output_tokens"])
    assert sum(first.values()) == 7_912

    recovered = sum(r.usage.output_tokens for r in arm("baton-r1"))
    assert recovered == 37_931
    assert TRUTH["baton-r1"]["model_usage"]["claude-opus-5"]["output_tokens"] == 42_292


@pytest.mark.parametrize("name", COMPLETE + list(INCOMPLETE))
def test_every_cache_write_on_every_arm_has_a_known_ttl(name):
    # If this ever fails, a price computed from these arms is partly a guess.
    total = Usage.zero()
    for record in arm(name):
        total = total + record.usage
    assert total.cache_creation_unattributed == 0
    assert total.cache_creation_5m + total.cache_creation_1h == total.cache_creation_tokens


def test_the_ttl_split_separates_the_arms():
    # Not a detail: it is the reason a cache write cannot carry one price.
    def five_minute_share(name: str) -> float:
        total = Usage.zero()
        for record in arm(name):
            total = total + record.usage
        return total.cache_creation_5m / total.cache_creation_tokens

    assert five_minute_share("reader-r1") == 0.0
    assert five_minute_share("reader-r2") == 0.0
    assert five_minute_share("baton-r1") > 0.6
    assert five_minute_share("baton-r2") > 0.9
