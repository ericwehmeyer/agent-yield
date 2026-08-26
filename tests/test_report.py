import datetime as dt

from agent_yield.interventions import Intervention
from agent_yield.outcomes import DailyOutcome
from agent_yield.records import CallRecord
from agent_yield.report import build_rows, compare_interventions, render_table
from agent_yield.usage import Usage


def _call(day: str, session: str, cache_read: int) -> CallRecord:
    tag = f"{day}{session}{cache_read}"
    return CallRecord(
        timestamp=dt.datetime.fromisoformat(f"{day}T12:00:00+00:00"),
        usage=Usage(cache_read_tokens=cache_read),
        session_id=session,
        request_id=f"r{tag}",
        message_id=f"m{tag}",
    )


def test_rows_are_split_by_mode_never_pooled():
    records = [_call("2026-08-24", "s1", 100), _call("2026-08-24", "s2", 900)]
    outcomes = [DailyOutcome(dt.date(2026, 8, 24), merges=2, commits=4, lines=10)]
    rows = {r.mode: r for r in
            build_rows(records, outcomes, {"s1": "build", "s2": "design"})}
    assert set(rows) == {"build", "design"}
    assert rows["build"].usage.cache_read_tokens == 100
    assert rows["design"].usage.cache_read_tokens == 900


def test_untagged_sessions_are_reported_separately():
    records = [_call("2026-08-24", "s1", 100), _call("2026-08-24", "unknown", 50)]
    outcomes = [DailyOutcome(dt.date(2026, 8, 24), merges=1, commits=1, lines=1)]
    rows = {r.mode: r for r in build_rows(records, outcomes, {"s1": "build"})}
    assert "untagged" in rows
    assert rows["untagged"].usage.cache_read_tokens == 50


def test_tokens_per_merge_is_none_when_nothing_merged():
    records = [_call("2026-08-24", "s1", 100)]
    outcomes = [DailyOutcome(dt.date(2026, 8, 24), merges=0, commits=3, lines=5)]
    row = build_rows(records, outcomes, {"s1": "design"})[0]
    assert row.tokens_per_merge is None
    assert row.tokens_per_commit == 100 / 3


def test_before_after_compares_the_windows_around_an_intervention():
    records = [_call("2026-08-20", "s1", 1000), _call("2026-08-26", "s1", 100)]
    outcomes = [
        DailyOutcome(dt.date(2026, 8, 20), merges=1, commits=1, lines=1),
        DailyOutcome(dt.date(2026, 8, 26), merges=1, commits=1, lines=1),
    ]
    rows = build_rows(records, outcomes, {"s1": "build"})
    intervention = Intervention(
        date=dt.date(2026, 8, 25), name="brief-pack",
        expect="cost per merge falls",
    )
    result = compare_interventions(rows, [intervention])[0]
    assert result.before == 1000
    assert result.after == 100
    assert result.intervention.expect == "cost per merge falls"


def test_before_after_reports_none_rather_than_zero_when_a_window_is_empty():
    records = [_call("2026-08-26", "s1", 100)]
    outcomes = [DailyOutcome(dt.date(2026, 8, 26), merges=1, commits=1, lines=1)]
    rows = build_rows(records, outcomes, {"s1": "build"})
    intervention = Intervention(date=dt.date(2026, 8, 25), name="x", expect="y")
    result = compare_interventions(rows, [intervention])[0]
    assert result.before is None
    assert result.change is None


def test_table_never_prints_a_currency_symbol():
    records = [_call("2026-08-24", "s1", 100)]
    outcomes = [DailyOutcome(dt.date(2026, 8, 24), merges=1, commits=1, lines=1)]
    rendered = render_table(build_rows(records, outcomes, {"s1": "build"}))
    assert "$" not in rendered
    assert "2026-08-24" in rendered
    assert "build" in rendered
