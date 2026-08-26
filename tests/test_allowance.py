"""The one budget number on a subscription that is not an equivalent of another.

`pricing.py` says dollars are list-price equivalents. This is the constraint an
operator is actually rationed on, and the point of these tests is mostly what
the module REFUSES: the arithmetic is trivial and every way it can be a shape
rather than a measurement has to be closed.
"""
import json

from agent_yield import allowance
from agent_yield.allowance import (
    MIN_POINTS,
    Snapshot,
    append,
    estimate,
    load,
    read_allowance,
)

PAYLOAD = {
    "rate_limits": {
        "seven_day": {"used_percentage": 12, "resets_at": "2026-08-30T00:00:00Z"},
        "five_hour": {"used_percentage": 40, "resets_at": "2026-08-26T15:00:00Z"},
    },
    "cost": {"total_cost_usd": 1.50},
}


def at(hour: int, seven_day: int, dollars: float | None,
       window: str = "2026-08-30T00:00:00Z") -> Snapshot:
    return Snapshot(timestamp=f"2026-08-26T{hour:02d}:00:00+00:00",
                    seven_day=seven_day, seven_day_resets_at=window,
                    session_dollars=dollars)


def test_a_payload_with_rate_limits_reads_both_windows():
    snapshot = read_allowance(PAYLOAD, timestamp="2026-08-26T10:00:00+00:00")
    assert snapshot.seven_day == 12
    assert snapshot.five_hour == 40
    assert snapshot.seven_day_resets_at == "2026-08-30T00:00:00Z"
    assert snapshot.session_dollars == 1.50


def test_a_client_that_reports_no_limits_gives_none_not_zero():
    # 0% used would read as a fresh week, which is the most misleading number
    # this file could produce.
    assert read_allowance({}) is None
    assert read_allowance({"rate_limits": {}}) is None
    assert read_allowance({"rate_limits": {"seven_day": {}}}) is None


def test_a_snapshot_is_kept_only_when_something_moved(tmp_path):
    # A status line renders on every keystroke. Without this the log is a
    # keystroke counter.
    log = tmp_path / "allowance.jsonl"
    first = read_allowance(PAYLOAD, timestamp="2026-08-26T10:00:00+00:00")
    assert append(log, first, None)
    assert not append(log, first, first)

    moved = read_allowance({**PAYLOAD, "rate_limits": {
        **PAYLOAD["rate_limits"],
        "seven_day": {"used_percentage": 13, "resets_at": "2026-08-30T00:00:00Z"},
    }}, timestamp="2026-08-26T11:00:00+00:00")
    assert append(log, moved, first)
    assert len(load(log)) == 2


def test_a_reset_is_a_change_even_when_the_percentage_is_not(tmp_path):
    log = tmp_path / "allowance.jsonl"
    before = at(10, 40, 5.0, window="2026-08-30T00:00:00Z")
    after = at(11, 40, 5.0, window="2026-09-06T00:00:00Z")
    assert append(log, before, None)
    assert append(log, after, before)


def test_the_estimate_is_the_widest_pair_inside_one_window():
    got = estimate([at(10, 10, 1.0), at(12, 14, 5.0), at(16, 30, 21.0)])
    # 20 points for $20 -> $100 for the whole window. Taken across the widest
    # pair, not the last two: more points is less quantization error.
    assert got.points == 20
    assert got.window_dollars == 100.0
    assert got.span_hours == 6.0


def test_the_estimate_is_labelled_a_lower_bound():
    """The bound falls the conservative way, and the label has to travel.

    Only this tool's sessions move the dollars; every session on the account
    moves the points. Unmeasured spend therefore deflates the estimate, making
    it a lower bound on the plan and an UPPER bound on the fraction spent.
    """
    got = estimate([at(10, 10, 1.0), at(16, 30, 21.0)])
    assert got.is_lower_bound
    assert ">=" in got.describe() and "LOWER bound" in got.describe()


def test_a_move_too_small_to_measure_is_refused():
    # used_percentage is an integer: a 4-point move is +/-25% before anything
    # else goes wrong, and printing it would make quantization look like a fact.
    assert estimate([at(10, 10, 1.0), at(12, 10 + MIN_POINTS - 1, 9.0)]) is None
    assert estimate([at(10, 10, 1.0), at(12, 10 + MIN_POINTS, 9.0)]) is not None


def test_a_pair_straddling_a_reset_is_never_used():
    # The percentage falls across a reset, so the pair would price the
    # allowance negative. Keying by the reset timestamp makes it unreachable.
    assert estimate([at(10, 90, 1.0, window="w1"),
                     at(16, 5, 30.0, window="w2")]) is None


def test_snapshots_without_measured_spend_do_not_calibrate():
    assert estimate([at(10, 10, None), at(16, 30, None)]) is None
    assert estimate([at(10, 10, 1.0)]) is None


def test_dollars_that_did_not_rise_are_refused():
    assert estimate([at(10, 10, 5.0), at(16, 30, 5.0)]) is None


def test_a_corrupt_log_line_is_skipped_not_fatal(tmp_path):
    log = tmp_path / "allowance.jsonl"
    log.write_text("not json\n"
                   + json.dumps({"timestamp": "t", "seven_day": 3}) + "\n"
                   + json.dumps({"no": "percentage"}) + "\n")
    held = load(log)
    assert [s.seven_day for s in held] == [3]


def test_no_tier_table_ships_with_this_module():
    """The decline, asserted.

    Declared per-plan allocations would be a hardcoded price table with no
    ground truth to check itself against -- the failure `pricing.py` exists to
    avoid, rebuilt one module over. The size is calibrated, never declared.
    """
    source = allowance.__doc__ or ""
    assert "not declared" in source.lower() or "CALIBRATED" in source
    assert not any(name.lower().endswith(("_plans", "_tiers", "plan_table"))
                   for name in vars(allowance))
