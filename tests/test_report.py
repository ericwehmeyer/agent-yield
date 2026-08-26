import datetime as dt

from agent_yield.interventions import Intervention
from agent_yield.outcomes import DailyOutcome
from agent_yield.records import CallRecord
from agent_yield.report import (
    build_model_rows,
    build_rows,
    compare_interventions,
    render_model_table,
    render_table,
)
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


def _sub_call(day: str, session: str, cache_read: int) -> CallRecord:
    tag = f"sub{day}{session}{cache_read}"
    return CallRecord(
        timestamp=dt.datetime.fromisoformat(f"{day}T12:00:00+00:00"),
        usage=Usage(cache_read_tokens=cache_read),
        session_id=session,
        request_id=f"r{tag}",
        message_id=f"m{tag}",
        is_subagent=True,
    )


def _outcome(day: str = "2026-08-24") -> list[DailyOutcome]:
    return [DailyOutcome(dt.date.fromisoformat(day), merges=1, commits=1, lines=1)]


def test_context_per_call_is_reported_for_each_population():
    records = [
        _call("2026-08-24", "s1", 300),
        _call("2026-08-24", "s1", 500),
        _sub_call("2026-08-24", "s1", 100),
    ]
    row = build_rows(records, _outcome(), {"s1": "build"})[0]
    assert row.main_calls == 2
    assert row.subagent_calls == 1
    assert row.main_context_per_call == 400
    assert row.subagent_context_per_call == 100
    assert row.main_context_per_call != row.subagent_context_per_call
    # The blended figure sits between them and describes neither.
    assert row.context_per_call == 900 / 3


def test_missing_subagent_population_is_none_not_zero():
    records = [_call("2026-08-24", "s1", 300)]
    row = build_rows(records, _outcome(), {"s1": "build"})[0]
    assert row.subagent_context_per_call is None
    assert row.subagent_context_per_call != 0
    assert row.main_context_per_call == 300


def test_missing_main_population_is_none_not_zero():
    records = [_sub_call("2026-08-24", "s1", 700)]
    row = build_rows(records, _outcome(), {"s1": "build"})[0]
    assert row.main_context_per_call is None
    assert row.main_context_per_call != 0
    assert row.subagent_context_per_call == 700


def test_split_usage_keeps_the_four_token_fields_apart():
    records = [
        CallRecord(
            timestamp=dt.datetime.fromisoformat("2026-08-24T12:00:00+00:00"),
            usage=Usage(input_tokens=1, output_tokens=2,
                        cache_creation_tokens=3, cache_read_tokens=4),
            session_id="s1", request_id="ra", message_id="ma",
        ),
        CallRecord(
            timestamp=dt.datetime.fromisoformat("2026-08-24T12:00:00+00:00"),
            usage=Usage(input_tokens=10, output_tokens=20,
                        cache_creation_tokens=30, cache_read_tokens=40),
            session_id="s1", request_id="rb", message_id="mb",
            is_subagent=True,
        ),
    ]
    row = build_rows(records, _outcome(), {"s1": "build"})[0]
    assert row.main_usage.input_tokens == 1
    assert row.main_usage.cache_creation_tokens == 3
    assert row.subagent_usage.output_tokens == 20
    assert row.subagent_usage.cache_read_tokens == 40
    assert row.usage.total == row.main_usage.total + row.subagent_usage.total


def test_table_shows_both_context_columns_and_dashes_a_missing_population():
    records = [_call("2026-08-24", "s1", 300), _sub_call("2026-08-24", "s1", 100)]
    rendered = render_table(build_rows(records, _outcome(), {"s1": "build"}))
    header, _rule, row_line = rendered.splitlines()
    assert "main ctx/call" in header
    assert "sub ctx/call" in header
    assert "300" in row_line and "100" in row_line
    assert "$" not in rendered

    main_only = render_table(build_rows([_call("2026-08-24", "s1", 300)],
                                        _outcome(), {"s1": "build"}))
    assert main_only.splitlines()[2].rstrip().endswith("-")
    assert "$" not in main_only


def test_table_stays_within_terminal_width():
    header = render_table([]).splitlines()[0]
    assert len(header) <= 100


def _model_call(model: str | None, cache_read: int, *,
                is_subagent: bool = False, output: int = 0) -> CallRecord:
    tag = f"{model}{cache_read}{is_subagent}{output}"
    return CallRecord(
        timestamp=dt.datetime.fromisoformat("2026-08-24T12:00:00+00:00"),
        usage=Usage(cache_read_tokens=cache_read, output_tokens=output),
        session_id="s1",
        request_id=f"r{tag}",
        message_id=f"m{tag}",
        model=model,
        is_subagent=is_subagent,
    )


def test_models_that_are_not_models_are_reported_rather_than_dropped():
    rows = build_model_rows([
        _model_call("claude-opus-5", 500),
        _model_call(None, 300),
        _model_call("<synthetic>", 100),
    ])
    assert {r.model for r in rows} == {"claude-opus-5", "none", "<synthetic>"}
    assert sum(r.calls for r in rows) == 3


def test_one_model_at_both_roles_stays_two_rows():
    rows = build_model_rows([
        _model_call("claude-opus-5", 900),
        _model_call("claude-opus-5", 100, is_subagent=True),
    ])
    assert len(rows) == 2
    by_role = {r.is_subagent: r for r in rows}
    assert by_role[False].usage.cache_read_tokens == 900
    assert by_role[True].usage.cache_read_tokens == 100


def test_median_context_is_reported_beside_the_mean_it_corrects():
    rows = build_model_rows([
        _model_call("claude-opus-5", 100),
        _model_call("claude-opus-5", 100),
        _model_call("claude-opus-5", 1000, output=90),
    ])
    row = rows[0]
    assert row.context_per_call == 400
    assert row.median_context_per_call == 100
    assert row.output_per_call == 30


def test_rows_are_ordered_by_where_the_money_went():
    rows = build_model_rows([
        _model_call("cheap", 100),
        _model_call("dear", 5000),
        _model_call("middling", 900),
    ])
    assert [r.model for r in rows] == ["dear", "middling", "cheap"]


def test_empty_row_set_renders_a_header_and_no_lines():
    assert render_model_table([]).count("\n") == 1


def test_the_model_table_names_every_model_it_was_given():
    text = render_model_table(build_model_rows([
        _model_call("claude-opus-5", 500),
        _model_call(None, 300),
        _model_call("<synthetic>", 100),
    ]))
    for name in ("claude-opus-5", "none", "<synthetic>"):
        assert name in text
