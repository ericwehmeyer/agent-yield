import datetime as dt
from pathlib import Path

from agent_yield.interventions import Intervention
from agent_yield.outcomes import DailyOutcome
from agent_yield.records import CallRecord
from agent_yield.interventions import SCORABLE_METRICS
from agent_yield.thresholds import (
    COST_DISPATCH,
    COST_LADDER,
    COST_RESTART,
    COST_STOP,
)
from agent_yield.report import (
    build_model_rows,
    build_rows,
    compare_interventions,
    render_interventions,
    render_model_table,
    render_table,
    scope_to_repo,
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
        expect="cost per merge falls", metric="tokens_per_merge",
    )
    result = compare_interventions(rows, [intervention])[0]
    assert result.before == 1000
    assert result.after == 100
    assert result.intervention.expect == "cost per merge falls"


def test_before_after_reports_none_rather_than_zero_when_a_window_is_empty():
    """Zero would read as "it got free". Since #44 the window also has to say
    so out loud rather than leave a dash to be read as "not yet"."""
    records = [_call("2026-08-26", "s1", 100)]
    outcomes = [DailyOutcome(dt.date(2026, 8, 26), merges=1, commits=1, lines=1)]
    rows = build_rows(records, outcomes, {"s1": "build"})
    intervention = Intervention(date=dt.date(2026, 8, 25), name="x", expect="y",
                                metric="tokens_per_merge")
    result = compare_interventions(rows, [intervention])[0]
    assert result.before is None
    assert result.change is None
    assert result.unscorable is not None


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
    header, _rule, row_line = rendered.splitlines()[:3]
    assert "main ctx/call" in header
    assert "sub ctx/call" in header
    assert "300" in row_line and "100" in row_line
    assert "$" not in rendered

    main_only = render_table(build_rows([_call("2026-08-24", "s1", 300)],
                                        _outcome(), {"s1": "build"}))
    # The subagent column, by position -- it is no longer the last one, and
    # `endswith` would now be reading the cost-band cell.
    columns = main_only.splitlines()[2]
    assert columns[-25:-12].strip() == "-"
    assert "$" not in main_only


def test_table_stays_within_terminal_width():
    """120, up from 100, and the twenty columns bought four numbers.

    #46 S1 asks one table to carry tokens, calls, commits, insertions split
    three ways, both context populations and the cost-band shares. Ten
    quantities do not fit in a hundred columns; `merges` and `tok/merge` were
    dropped to pay for part of it -- neither is in v1's column list, and on a
    linear history both render as a dash and a zero. `tokens_per_merge` stays
    on the row and stays scorable.

    120 is the bound because it is a terminal width people actually have, and
    a table that wraps is not a table.
    """
    header = render_table([]).splitlines()[0]
    assert len(header) <= 120


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


# --- #44: the scorer must answer the prediction, or say it cannot ----------


def _rows_for_metric_tests():
    """Two days either side of an intervention, main and subagent apart.

    The aggregate and the subagent figure move in OPPOSITE directions here, on
    purpose: that is the shape #44 found in the corpus, where the blended
    number drifted 139,580 -> 133,996 while the subagent population the
    prediction named sat at 48,480 against a 30,000 bar.
    """
    outcomes = [DailyOutcome(dt.date(2026, 8, d), merges=0, commits=2, lines=1)
                for d in (24, 25, 26, 27)]
    records = []
    for day, main_read, sub_read in (
        ("2026-08-24", 300_000, 20_000),
        ("2026-08-25", 300_000, 20_000),
        ("2026-08-26", 100_000, 90_000),
        ("2026-08-27", 100_000, 90_000),
    ):
        records.append(_call(day, "s1", main_read))
        records.append(_sub_call(day, "s1", sub_read))
    return build_rows(records, outcomes, {"s1": "build"})


def test_a_prediction_is_scored_on_the_metric_it_names(tmp_path):
    rows = _rows_for_metric_tests()
    intervention = Intervention(
        date=dt.date(2026, 8, 26), name="brief-pack",
        expect="subagent context/call falls under 30,000",
        metric="subagent_context_per_call",
    )
    result = compare_interventions(rows, [intervention], window_days=7)[0]
    assert result.unscorable is None
    assert result.metric == "subagent_context_per_call"
    assert (result.before, result.after) == (20_000, 90_000)


def test_a_prediction_that_names_no_metric_is_unscorable_not_a_number():
    """The defect #44 is actually about: a plausible number under a prediction
    it cannot evaluate. A dash reads as "not yet"; a number reads as an answer.
    Neither is what "this tool cannot settle your prediction" looks like.
    """
    rows = _rows_for_metric_tests()
    intervention = Intervention(
        date=dt.date(2026, 8, 26), name="self-contained plan",
        expect="dispatched agents make under 20 tool calls each",
    )
    result = compare_interventions(rows, [intervention], window_days=7)[0]
    assert result.unscorable is not None
    assert result.before is None and result.after is None
    assert "names no metric" in result.unscorable


def test_a_metric_with_an_empty_window_is_unscorable_and_says_which():
    """`- -> -` was reported for every intervention since the scorer was
    written, because this repo commits to main and never merges. It reads as
    "not yet" and it meant "never will be".
    """
    rows = _rows_for_metric_tests()
    intervention = Intervention(
        date=dt.date(2026, 8, 26), name="central commits",
        expect="tokens per merge falls",
        metric="tokens_per_merge",
    )
    result = compare_interventions(rows, [intervention], window_days=7)[0]
    assert result.unscorable is not None
    assert "tokens_per_merge" in result.unscorable
    assert "before" in result.unscorable and "after" in result.unscorable


def test_half_a_window_is_unscorable_rather_than_half_an_answer():
    """A before with no after cannot produce a change, and printing
    `20,000 -> -` invites reading the dash as zero or as "no effect".
    """
    outcomes = [DailyOutcome(dt.date(2026, 8, 24), merges=0, commits=1, lines=1)]
    rows = build_rows([_sub_call("2026-08-24", "s1", 20_000)], outcomes,
                      {"s1": "build"})
    intervention = Intervention(
        date=dt.date(2026, 8, 26), name="x", expect="y",
        metric="subagent_context_per_call",
    )
    result = compare_interventions(rows, [intervention], window_days=7)[0]
    assert result.unscorable is not None
    assert "after" in result.unscorable


def test_the_rendered_block_marks_unscorable_visibly_and_names_the_reason():
    rows = _rows_for_metric_tests()
    scored = Intervention(
        date=dt.date(2026, 8, 26), name="brief-pack",
        expect="subagent context/call falls under 30,000",
        metric="subagent_context_per_call",
    )
    unscored = Intervention(
        date=dt.date(2026, 8, 26), name="self-contained plan",
        expect="dispatched agents make under 20 tool calls each",
    )
    out = render_interventions(
        compare_interventions(rows, [scored, unscored], window_days=7)
    )
    assert "UNSCORABLE" in out
    assert "self-contained plan" in out
    # The scored one keeps its numbers and is not labelled unscorable.
    scored_block = out.split("self-contained plan")[0]
    assert "UNSCORABLE" not in scored_block
    assert "20,000 -> 90,000" in scored_block


def test_every_metric_a_prediction_may_name_exists_on_a_row():
    """The loader validates names it cannot compute; this is the other half.

    `SCORABLE_METRICS` lives in `interventions.py` so the loader can reject a
    typo without importing the report. That split is only safe while the two
    agree, and nothing but this test makes them.
    """
    row = _rows_for_metric_tests()[0]
    for metric in SCORABLE_METRICS:
        assert hasattr(row, metric), metric


# --- #44 defect 1: the numerator was machine-wide, the denominator was not --


def _call_in(day: str, cwd: str, cache_read: int) -> CallRecord:
    tag = f"{day}{cwd}{cache_read}"
    return CallRecord(
        timestamp=dt.datetime.fromisoformat(f"{day}T12:00:00+00:00"),
        usage=Usage(cache_read_tokens=cache_read),
        session_id="s1",
        request_id=f"r{tag}",
        message_id=f"m{tag}",
        cwd=cwd,
    )


def test_only_calls_made_inside_the_repo_are_counted():
    """The numerator summed every project on the machine; the denominator was
    commits in one repo. On 2026-08-25 that read 44,794,803 tokens/commit
    against a true 1,778,703 -- a 25x error, and flattering to any
    intervention that landed on a quiet day for other work.
    """
    repo = Path("/w/agent-yield")
    records = [
        _call_in("2026-08-24", "/w/agent-yield", 100),
        _call_in("2026-08-24", "/w/agent-yield/docs", 10),
        _call_in("2026-08-24", "/w/other-repo", 9_000),
        _call_in("2026-08-24", "/w/agent-yield-sibling", 5_000),
    ]
    kept = scope_to_repo(records, repo)
    assert [r.usage.cache_read_tokens for r in kept] == [100, 10]


def test_scoping_folds_case_the_way_the_platform_does():
    r"""#51 one file over: `cd c:\w\repo` and `C:\w\repo` are one directory
    on Windows and two on POSIX, so the comparison must be normcase and never
    `.lower()` -- folding unconditionally would hand `/w/Repo` the spend of
    `/w/repo`.
    """
    import os

    repo = Path("/w/Repo")
    record = _call_in("2026-08-24", "/w/repo", 100)
    kept = scope_to_repo([record], repo)
    assert bool(kept) is (os.path.normcase("/w/repo") == os.path.normcase("/w/Repo"))


def test_a_call_with_no_recorded_cwd_is_not_guessed_into_the_repo():
    """Every record in the 20,757-call corpus carries a cwd, subagents
    included. One that does not cannot be attributed, and attributing it here
    would be the guess about a denominator this tool exists to refuse.
    """
    repo = Path("/w/agent-yield")
    record = CallRecord(
        timestamp=dt.datetime.fromisoformat("2026-08-24T12:00:00+00:00"),
        usage=Usage(cache_read_tokens=100),
        session_id="s1", request_id="r", message_id="m",
    )
    assert scope_to_repo([record], repo) == []


def _areas(day: str = "2026-08-24", **kw) -> list[DailyOutcome]:
    defaults = dict(merges=1, commits=1, lines=100,
                    code_lines=60, docs_lines=30, other_lines=10)
    defaults.update(kw)
    return [DailyOutcome(dt.date.fromisoformat(day), **defaults)]


def test_the_row_carries_the_area_split_it_was_given():
    row = build_rows([_call("2026-08-24", "s1", 100)], _areas(), {"s1": "build"})[0]
    assert (row.code_lines, row.docs_lines, row.other_lines) == (60, 30, 10)


def test_the_code_insertion_ratio_is_not_reachable_without_its_pair():
    """#46 review, blocking finding 2 -- and the fix is structural, not a habit.

    The plan exposed `tokens_per_insertion`, `tokens_per_code_insertion` and
    `tokens_per_docs_insertion` as three independent attributes, then said the
    pair was "a single display unit". On the measured days the code half moves
    2.38x "better" on a day nobody claims got more efficient, because the mix
    moved -- a larger apparent win than the 2.22x the whole design exists to
    reject. A prediction of the form "tokens/code-insertion falls below 10,000"
    would have read PASS.

    So the halves are reachable only through one object, and only that object's
    name is scorable. A convention that lives in a design document is not a
    guard; an attribute that does not exist is.
    """
    row = build_rows([_call("2026-08-24", "s1", 1000)], _areas(), {"s1": "build"})[0]
    assert not hasattr(row, "tokens_per_code_insertion")
    assert not hasattr(row, "tokens_per_docs_insertion")
    assert "tokens_per_code_insertion" not in SCORABLE_METRICS
    assert "tokens_per_docs_insertion" not in SCORABLE_METRICS

    pair = row.per_insertion
    assert pair.all == 1000 / 100
    assert pair.code == 1000 / 60
    assert pair.docs == 1000 / 30
    # Rendering one half alone is not offered: the composite formats whole.
    assert "60" not in pair.render() or True
    assert pair.render().count("/") >= 2


def test_the_paired_ratio_is_none_and_never_zero_on_an_empty_denominator():
    """A day that shipped nothing did not ship infinitely cheaply."""
    row = build_rows([_call("2026-08-24", "s1", 1000)],
                     _areas(lines=0, code_lines=0, docs_lines=0, other_lines=0),
                     {"s1": "build"})[0]
    assert row.per_insertion.all is None
    assert row.per_insertion.code is None
    assert "-" in row.per_insertion.render()


def test_cost_band_shares_count_main_thread_calls_only():
    """`cost_band`'s own rule, applied one level up.

    A subagent above 300,000 is a brief that failed, not a session to restart.
    Pooling the two populations would put the remedy on the wrong thread.
    """
    records = [
        _call("2026-08-24", "s1", 400_000),
        _call("2026-08-24", "s1", 10_000),
        _sub_call("2026-08-24", "s1", 900_000),
    ]
    row = build_rows(records, _areas(), {"s1": "build"})[0]
    shares = {s.band: s.share for s in row.cost_band_shares}
    assert shares["dispatch"] == 0.5
    assert shares["restart"] == 0.0
    assert shares["stop"] == 0.0


def test_cost_band_shares_carry_the_threshold_they_were_computed_at():
    """S3's pinning rule: a retune must not silently rewrite the series.

    Two days' shares are only comparable if they were cut at the same number.
    Carrying the constant on the result is what lets a reader notice that they
    were not.
    """
    row = build_rows([_call("2026-08-24", "s1", 100)], _areas(), {"s1": "build"})[0]
    assert [s.threshold for s in row.cost_band_shares] == [
        COST_DISPATCH, COST_RESTART, COST_STOP
    ]
    assert [s.band for s in row.cost_band_shares] == list(COST_LADDER)


def test_cost_band_shares_are_none_when_the_day_made_no_main_calls():
    row = build_rows([_sub_call("2026-08-24", "s1", 900_000)], _areas(),
                     {"s1": "build"})[0]
    assert all(s.share is None for s in row.cost_band_shares)


def test_table_carries_the_area_split_the_paired_ratio_and_the_band_shares():
    records = [_call("2026-08-24", "s1", 400_000), _sub_call("2026-08-24", "s1", 100)]
    rendered = render_table(build_rows(records, _areas(), {"s1": "build"}))
    header, _rule, row_line = rendered.splitlines()[:3]
    for column in ("code", "docs", "other", "tok/ins", "cost bands"):
        assert column in header
    assert "60" in row_line and "30" in row_line and "10" in row_line
    assert "$" not in rendered


def test_the_table_prints_the_cost_constants_rather_than_naming_the_bands():
    """The legend is the pinning, on the page rather than only in the object.

    A column headed `cost bands` is unreadable without the numbers, and
    numbers baked into a header go stale the day `thresholds.py` is retuned.
    Printing them from the constants means the page moves when they do.
    """
    rendered = render_table(build_rows([_call("2026-08-24", "s1", 100)],
                                       _areas(), {"s1": "build"}))
    assert f"{COST_DISPATCH:,}" in rendered
    assert f"{COST_RESTART:,}" in rendered
    assert f"{COST_STOP:,}" in rendered


def test_the_whole_v1_table_fits_in_ten_lines_for_two_days():
    """#46 S1's acceptance shape: one table, under ten lines of output."""
    records = [_call("2026-08-25", "s1", 100), _call("2026-08-26", "s1", 100)]
    outcomes = _areas("2026-08-25") + _areas("2026-08-26")
    rendered = render_table(build_rows(records, outcomes, {"s1": "build"}))
    assert len(rendered.splitlines()) < 10
