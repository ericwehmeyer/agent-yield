"""#161's reporter, against fixtures whose arithmetic was done by hand.

Every expectation below is a number computed on paper from the fixture, not
one read back out of `sessions.py`. A test that asserts what the code returns
proves the code returns something; #51 survived a fix to the function it was
supposed to guard for exactly that reason.

The fixture is built so the two failure modes #161 names are visible rather
than plausible. Session `alpha` has 8 API calls written as 16 usage-bearing
records, so a reporter that counts rows says 16 and is caught; and it carries
sidechain records with a context two orders of magnitude larger than any of
its own, so a reporter that folds subagents into the parent reports a growth
factor nowhere near 3.5.
"""
import datetime as dt
import json

from agent_yield.cli import main
from agent_yield.records import CallRecord
from agent_yield.sessions import (
    build_sessions,
    corpus_window,
    distinct_calls,
    render,
    render_window,
    ungrouped_calls,
)
from agent_yield.usage import Usage


def _at(stamp: str) -> dt.datetime:
    return dt.datetime.fromisoformat(f"2026-08-{stamp}+00:00")


def _call(
    stamp: str,
    session: str,
    request: str | None,
    message: str,
    context: int,
    is_subagent: bool = False,
    cwd: str | None = None,
) -> CallRecord:
    # context == cache_read_tokens, since `CallRecord.context` sums input,
    # cache read and cache creation and the other two are left at zero.
    return CallRecord(
        timestamp=_at(stamp),
        usage=Usage(cache_read_tokens=context),
        session_id=session,
        request_id=request,
        message_id=message,
        is_subagent=is_subagent,
        cwd=cwd,
    )


# alpha: 8 requests at 5-minute spacing from 10:00 to 10:35, each written as
# two records sharing one requestId. Contexts 100..800 in order of time.
ALPHA_CONTEXTS = [100, 200, 300, 400, 500, 600, 700, 800]
ALPHA_MINUTES = ["10:00:00", "10:05:00", "10:10:00", "10:15:00",
                 "10:20:00", "10:25:00", "10:30:00", "10:35:00"]


def _alpha(cwd: str | None = None) -> list[CallRecord]:
    out = []
    for index, (minute, context) in enumerate(
            zip(ALPHA_MINUTES, ALPHA_CONTEXTS), start=1):
        for half in ("a", "b"):
            out.append(_call(f"01T{minute}", "alpha", f"req-{index}",
                             f"msg-{index}{half}", context, cwd=cwd))
    return out


# beta: 4 requests, 09:00 to 09:12. Started BEFORE alpha, so a table ordered
# by start time puts it first.
def _beta(cwd: str | None = None) -> list[CallRecord]:
    return [
        _call(f"01T09:0{n}:00", "beta", f"beta-{n}", f"bmsg-{n}",
              1000 + n, cwd=cwd)
        for n in (0, 4, 8)
    ] + [_call("01T09:12:00", "beta", "beta-12", "bmsg-12", 1012, cwd=cwd)]


# alpha's sidechains: same session_id, huge contexts, latest timestamp in the
# corpus. They must stay out of alpha's row and stay IN the corpus window.
def _sidechains(cwd: str | None = None) -> list[CallRecord]:
    return [
        _call("02T00:00:00", "alpha", "sub-1", "smsg-1", 999_000,
              is_subagent=True, cwd=cwd),
        _call("01T23:00:00", "alpha", "sub-2", "smsg-2", 999_000,
              is_subagent=True, cwd=cwd),
    ]


def _corpus(cwd: str | None = None) -> list[CallRecord]:
    return _alpha(cwd) + _beta(cwd) + _sidechains(cwd)


def test_a_call_is_a_distinct_request_not_a_usage_row():
    # 16 usage-bearing records, 8 requests. The naive count is 2.0x here; on
    # this box it is 2.6x (working-method 7.2).
    records = _alpha()
    assert len(records) == 16
    assert len(distinct_calls(records)) == 8


def test_the_row_reports_eight_calls_and_not_sixteen():
    rows = build_sessions(_corpus(), baseline_calls=3)
    alpha = next(r for r in rows if r.session_id == "alpha")
    assert alpha.calls == 8


def test_a_record_with_no_request_id_counts_as_its_own_call():
    # Ungroupable, so kept: undercounting is the error this tool prevents.
    records = [
        _call("01T10:00:00", "solo", None, "m1", 10),
        _call("01T10:01:00", "solo", None, "m2", 20),
    ]
    assert len(distinct_calls(records)) == 2


def test_growth_is_the_hand_computed_ratio_of_the_two_means():
    # open  = (100 + 200 + 300) / 3 = 200
    # close = (600 + 700 + 800) / 3 = 700
    # growth = 700 / 200 = 3.5
    rows = build_sessions(_corpus(), baseline_calls=3)
    alpha = next(r for r in rows if r.session_id == "alpha")
    assert alpha.open_context == 200.0
    assert alpha.close_context == 700.0
    assert alpha.growth == 3.5


def test_subagent_context_never_enters_the_parents_growth():
    # Each sidechain carries 999,000 context. Folding either into alpha would
    # push close_context above 300,000 and growth above 1,000x.
    rows = build_sessions(_corpus(), baseline_calls=3)
    alpha = next(r for r in rows if r.session_id == "alpha")
    assert alpha.close_context == 700.0
    assert alpha.calls == 8


def test_a_session_too_short_for_two_disjoint_windows_reports_no_growth():
    # beta has 4 calls and the baseline is 3: the windows would share two
    # calls, so the factor is not measured and is not invented.
    rows = build_sessions(_corpus(), baseline_calls=3)
    beta = next(r for r in rows if r.session_id == "beta")
    assert beta.calls == 4
    assert beta.open_context is None
    assert beta.close_context is None
    assert beta.growth is None


def test_minutes_is_wall_clock_between_first_and_last_call():
    # alpha 10:00 -> 10:35 is 35 minutes; beta 09:00 -> 09:12 is 12.
    rows = build_sessions(_corpus(), baseline_calls=3)
    by_id = {row.session_id: row for row in rows}
    assert by_id["alpha"].minutes == 35.0
    assert by_id["beta"].minutes == 12.0


def test_rows_are_ordered_by_start_time_and_by_nothing_else():
    # beta starts an hour earlier and is a third of alpha's size: any sort by
    # calls, minutes or growth would put it second.
    rows = build_sessions(_corpus(), baseline_calls=3)
    assert [row.session_id for row in rows] == ["beta", "alpha"]


def test_the_table_carries_no_normalising_column():
    # #76 is the standing case of a ranked figure that reads a quiet day as
    # the most efficient. The denominator is the operator's open decision.
    text = render(build_sessions(_corpus(), baseline_calls=3))
    header = text.splitlines()[0].lower()
    for banned in ("per commit", "per issue", "efficiency", "rank", "score"):
        assert banned not in header


def test_the_table_prints_the_hand_computed_row():
    text = render(build_sessions(_corpus(), baseline_calls=3))
    alpha_line = next(line for line in text.splitlines()
                      if line.startswith("alpha"))
    assert "2026-08-01 10:00" in alpha_line
    assert "3.5x" in alpha_line
    # 8 calls, 35 minutes, 200 open, 700 close -- all four on the row.
    for figure in ("8", "35", "200", "700"):
        assert figure in alpha_line.split()


def test_the_corpus_window_spans_subagent_rows_too():
    # It answers "what did this file cover", not "what is in the table".
    first, last = corpus_window(_corpus())
    assert first == _at("01T09:00:00")
    assert last == _at("02T00:00:00")


def test_the_window_line_names_both_bounds_and_the_age():
    # Run "today" fixed at 2026-08-04T00:00:00Z, three days after the last row.
    line = render_window(_corpus(), "calls.jsonl",
                         today=_at("04T00:00:00"))
    assert "2026-08-01T09:00:00Z" in line
    assert "2026-08-02T00:00:00Z" in line
    assert "2.0 days" in line
    # 16 alpha records + 4 beta + 2 sidechain = 22 rows read.
    assert "22 records" in line


def test_an_empty_corpus_says_so_rather_than_printing_a_window():
    assert "no calls" in render_window([], "calls.jsonl")


def test_parent_calls_with_no_session_id_are_counted_not_silently_dropped():
    records = _corpus() + [
        _call("01T11:00:00", "", "orphan-1", "omsg-1", 50),
        _call("01T11:01:00", "", "orphan-2", "omsg-2", 60),
    ]
    assert ungrouped_calls(records) == 2
    assert len(build_sessions(records, baseline_calls=3)) == 2
    assert "2 parent call(s) carried no session_id" in render(
        build_sessions(records, baseline_calls=3), ungrouped_calls(records))


def _write_corpus(tmp_path, records) -> None:
    store = tmp_path / ".agent-yield"
    store.mkdir(parents=True, exist_ok=True)
    lines = []
    for record in records:
        lines.append(json.dumps({
            "timestamp": record.timestamp.isoformat(),
            # The persisted key is the transcript's, not the dataclass field's
            # -- `Usage.from_payload` reads `cache_read_input_tokens`, and a
            # fixture written with the short name loads as zero context.
            "usage": {"cache_read_input_tokens": record.usage.cache_read_tokens},
            "session_id": record.session_id,
            "request_id": record.request_id,
            "message_id": record.message_id,
            "is_subagent": record.is_subagent,
            "cwd": record.cwd,
        }))
    (store / "calls.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_the_subcommand_prints_the_window_before_the_table(
        tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("AGENT_YIELD_ROOT", str(tmp_path))
    _write_corpus(tmp_path, _corpus(cwd=str(tmp_path)))

    assert main(["sessions", "--repo", str(tmp_path),
                 "--baseline-calls", "3"]) == 0

    out = capsys.readouterr().out.splitlines()
    assert out[0].startswith("corpus:")
    assert "2026-08-02T00:00:00Z" in out[0]
    alpha_line = next(line for line in out if line.startswith("alpha"))
    assert "3.5x" in alpha_line
    beta_line = next(line for line in out if line.startswith("beta"))
    # Ordered: beta's row precedes alpha's in the printed output.
    assert out.index(beta_line) < out.index(alpha_line)


def test_the_subcommand_says_so_when_the_corpus_is_missing(
        tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("AGENT_YIELD_ROOT", str(tmp_path))
    assert main(["sessions", "--repo", str(tmp_path)]) == 0
    assert "no calls" in capsys.readouterr().out
