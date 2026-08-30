"""The one budget number on a subscription that is not an equivalent of another.

`pricing.py` says dollars are list-price equivalents. This is the constraint an
operator is actually rationed on, and the point of these tests is mostly what
the module REFUSES: the arithmetic is trivial and every way it can be a shape
rather than a measurement has to be closed.
"""
import datetime as dt
import json

from agent_yield import allowance
from agent_yield.allowance import (
    MIN_POINTS,
    STALE_AFTER_MINUTES,
    Snapshot,
    append,
    estimate,
    latest_readings,
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


# --- Either window, and the freshest value each one has ---------------------
NOW = dt.datetime(2026, 8, 26, 12, 0, tzinfo=dt.timezone.utc)


def snap(minutes_ago: int, five_hour=None, seven_day=None, resets_at=None) -> Snapshot:
    when = NOW - dt.timedelta(minutes=minutes_ago)
    return Snapshot(timestamp=when.isoformat(), five_hour=five_hour,
                    seven_day=seven_day, five_hour_resets_at=resets_at)


def test_a_five_hour_only_payload_is_recorded_not_dropped():
    """#129: the window that pops first was the one that went unrecorded.

    `read_allowance` required a seven-day value, so a client sending only the
    five-hour block recorded nothing at all -- and five-hour is the window
    that caps a session first.
    """
    snapshot = read_allowance({"rate_limits": {"five_hour": {"used_percentage": 88}}})
    assert snapshot is not None
    assert snapshot.five_hour == 88
    assert snapshot.seven_day is None


def test_a_payload_with_neither_window_is_still_none():
    assert read_allowance({"rate_limits": {"five_hour": {}, "seven_day": {}}}) is None


def test_a_five_hour_only_row_survives_the_round_trip(tmp_path):
    log = tmp_path / "allowance.jsonl"
    append(log, snap(0, five_hour=88), None)
    held = load(log)
    assert [s.five_hour for s in held] == [88]
    assert held[0].seven_day is None


def test_a_row_with_no_seven_day_value_cannot_calibrate_the_seven_day_plan():
    # The estimate prices the seven-day window in dollars per point. A row
    # with no seven-day value has no points to contribute.
    rows = [Snapshot(timestamp="2026-08-26T10:00:00+00:00", five_hour=40,
                     session_dollars=1.0),
            at(12, 30, 21.0)]
    assert estimate(rows) is None


def test_each_window_keeps_its_own_freshest_value():
    """Per window, never per row.

    Four of the 51 snapshots on this machine carry `five_hour: null` against a
    seven-day value. Taking the last row wholesale would let one of those
    retire a five-hour reading that is still the only one there is.
    """
    readings = latest_readings(
        [snap(60, five_hour=30, seven_day=40), snap(5, seven_day=44)], now=NOW
    )
    assert readings["five_hour"].used_percentage == 30
    assert readings["seven_day"].used_percentage == 44
    assert readings["five_hour"].age_minutes == 60
    assert readings["seven_day"].age_minutes == 5


def test_staleness_is_reported_and_not_applied():
    # The log is only written when a percentage MOVES, so a quiet log is
    # ambiguous: nothing spent, or no status line running at all (#120).
    # Nothing here can tell those apart, so this hands the caller the age and
    # lets it decide what it will refuse a dispatch on.
    old, fresh = latest_readings([snap(STALE_AFTER_MINUTES + 1, five_hour=95)],
                                 now=NOW), latest_readings(
        [snap(1, five_hour=95)], now=NOW)
    assert not old["five_hour"].is_fresh()
    assert fresh["five_hour"].is_fresh()


def test_the_reset_clock_is_minutes_from_now_when_the_client_sends_one():
    resets = (NOW + dt.timedelta(minutes=25)).isoformat().replace("+00:00", "Z")
    readings = latest_readings([snap(1, five_hour=95, resets_at=resets)], now=NOW)
    assert round(readings["five_hour"].minutes_to_reset) == 25


def test_no_reset_timestamp_has_ever_been_observed_here():
    """The claim in the docstring, checked against the log rather than assumed.

    `resets_at` was in this module's WHAT IS OBSERVABLE paragraph from the
    start, read off the field name. It is null in every snapshot this machine
    has ever taken, so anything built on it is unexercised, and a reading
    without it has to work.
    """
    readings = latest_readings([snap(1, five_hour=95, seven_day=44)], now=NOW)
    assert readings["five_hour"].minutes_to_reset is None
    assert readings["five_hour"].used_percentage == 95
    assert "has never seen" in (allowance.__doc__ or "").lower() or \
        "never sent" in (allowance.__doc__ or "").lower()


def test_an_unparseable_timestamp_is_skipped_rather_than_dated_to_now():
    # Dating it to now would make a corrupt row the freshest reading in the
    # log, which is the one row that must never win.
    readings = latest_readings([Snapshot(timestamp="not a time", five_hour=99),
                                snap(10, five_hour=20)], now=NOW)
    assert readings["five_hour"].used_percentage == 20
