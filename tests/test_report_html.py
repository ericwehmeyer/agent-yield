"""The HTML view has to survive being opened from a file with no network,
and it has to keep the two promises the terminal report keeps: tokens only,
and `None` is a dash. These tests are those promises, plus the escaping that
stops an operator-written `expect` from breaking the page.
"""
from __future__ import annotations

import datetime as dt
import re

import pytest

from agent_yield.interventions import Intervention
from agent_yield.records import CallRecord
from agent_yield.report import BeforeAfter, YieldRow
from agent_yield.report_html import render_html
from agent_yield.usage import Usage

DAY = dt.date(2026, 8, 24)
NEXT = dt.date(2026, 8, 25)


def _at(day: dt.date, hour: int = 12) -> dt.datetime:
    return dt.datetime(day.year, day.month, day.day, hour, tzinfo=dt.timezone.utc)


def _records() -> list[CallRecord]:
    """One main call and one subagent call, so the split is unambiguous:
    context per call is exactly the cache-read figure on each side."""
    return [
        CallRecord(
            timestamp=_at(DAY, 9),
            usage=Usage(
                input_tokens=12345,
                output_tokens=23456,
                cache_creation_tokens=34567,
                cache_read_tokens=311399,
            ),
            session_id="aaaaaaaa-1111-2222-3333-444444444444",
            model="claude-opus-5",
            is_subagent=False,
            cwd="/Users/someone/IdeaProjects/agent-yield",
        ),
        CallRecord(
            timestamp=_at(DAY, 10),
            usage=Usage(
                input_tokens=1000,
                output_tokens=2000,
                cache_creation_tokens=3000,
                cache_read_tokens=89721,
            ),
            session_id="bbbbbbbb-5555-6666-7777-888888888888",
            agent_id="agent-1",
            model="claude-opus-5",
            is_subagent=True,
            cwd="/Users/someone/IdeaProjects/agent-yield",
        ),
        CallRecord(
            timestamp=_at(NEXT, 9),
            usage=Usage(cache_read_tokens=311_399, output_tokens=500),
            session_id="cccccccc-9999-0000-1111-222222222222",
            model="claude-opus-5",
            is_subagent=False,
            cwd="/Users/someone/IdeaProjects/agent-yield",
        ),
    ]


def _rows() -> list[YieldRow]:
    """`merges=0` gives a None tokens/merge, and `tests=None` a None cell --
    both must reach the page as a dash."""
    return [
        YieldRow(
            day=DAY,
            mode="fleet",
            usage=Usage(
                input_tokens=13345,
                output_tokens=25456,
                cache_creation_tokens=37567,
                cache_read_tokens=401_120,
            ),
            calls=2,
            merges=0,
            commits=3,
            lines=420,
            tests=None,
            # One expensive call and one cheap one, both in the same session:
            # half the calls crossed the dispatch line and all of the sessions
            # did. The two figures disagreeing is the point of carrying both.
            main_contexts=(400_000, 100),
            main_session_peaks=(400_000,),
        ),
        YieldRow(
            day=NEXT,
            mode="solo",
            usage=Usage(output_tokens=500, cache_read_tokens=311_399),
            calls=1,
            merges=2,
            commits=4,
            lines=88,
            tests=7,
        ),
    ]


def _comparisons() -> list[BeforeAfter]:
    hostile = Intervention(
        date=NEXT,
        name="brief-pack <agents & co>",
        expect="per-agent median falls <script>alert(1)</script> from 12.4M",
    )
    plain = Intervention(
        date=DAY,
        name="gate at dispatch",
        expect="projected dispatches above 5M get refused",
    )
    return [
        BeforeAfter(plain, "tokens_per_merge", 1_000_000.0, 600_000.0),
        BeforeAfter(hostile, "tokens_per_merge", 1_000_000.0, None),
    ]


def _render() -> str:
    return render_html(_rows(), _comparisons(), _records())


def test_is_a_whole_html_document():
    out = _render()
    assert out.lstrip().lower().startswith("<!doctype html>")
    assert "</html>" in out
    assert "<title>" in out


def test_never_prints_money():
    # Section 6: it reports tokens. A currency on this page would be a lie
    # with a shelf life.
    assert "$" not in _render()


def test_is_self_contained():
    out = _render()
    for forbidden in ("http://", "https://", "<script", "<link", "@import", "url("):
        assert forbidden not in out, forbidden


def test_four_usage_fields_stay_apart():
    out = _render()
    # input, output, cache-write, cache-read -- four numbers, not one total.
    for value in ("13,345", "25,956", "37,567", "712,519"):
        assert value in out
    assert "Cache write" in out and "Cache read" in out


def test_main_and_subagent_context_per_call_are_shown_separately():
    out = _render()
    assert "311,399" in out
    assert "89,721" in out
    assert "3.5x" in out  # the gap a blended mean would have hidden


def test_none_metric_renders_as_a_dash_not_a_zero():
    out = _render()
    yield_table = out.split("Yield per day and mode", 1)[1]
    row = next(
        r
        for r in re.findall(r"<tr>(.*?)</tr>", yield_table, re.S)
        if ">2026-08-24<" in r
    )
    cells = [
        re.sub(r"<[^>]+>", "", c)
        for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
    ]
    # day, mode, tokens, calls, merges, commits, lines, tests,
    # tokens/merge, tokens/commit, context/call
    assert cells[7] == "-"  # tests is None
    assert cells[8] == "-"  # merges is 0, so tokens/merge has no value
    assert cells[8] != "0"
    assert 'class="num dash">-</td>' in row


def test_intervention_expect_is_shown_and_escaped():
    out = _render()
    assert "projected dispatches above 5M get refused" in out
    assert "per-agent median falls" in out
    assert "&lt;" in out
    assert "<script>alert(1)</script>" not in out
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in out
    assert "brief-pack &lt;agents &amp; co&gt;" in out


def test_empty_input_renders_an_explicit_empty_state():
    out = render_html([], [], [])
    assert out.lstrip().lower().startswith("<!doctype html>")
    assert "</html>" in out
    assert "Nothing to show" in out
    assert "$" not in out


def test_dark_mode_only_redefines_tokens_that_light_mode_defines():
    out = _render()
    css = out.split("<style>", 1)[1].split("</style>", 1)[0]
    root = re.search(r":root\s*\{(.*?)\}", css, re.S).group(1)
    dark = re.search(
        r"@media\s*\(prefers-color-scheme:\s*dark\)\s*\{(.*?)\n\}", css, re.S
    ).group(1)
    names = lambda block: set(re.findall(r"(--[a-z0-9-]+)\s*:", block))
    assert names(root), "the light palette must be defined on bare :root"
    assert names(dark), "dark mode must redefine something"
    assert names(dark) <= names(root)
    assert "background: var(--bg)" in css


def test_charts_carry_a_legend_and_the_drilldown_needs_no_javascript():
    out = _render()
    assert "<details>" in out and "<summary>" in out
    assert 'class="legend"' in out
    assert "Main sessions" in out and "Subagents" in out
    assert 'class="scroll"' in out


def test_rows_without_records_keep_the_split_as_a_dash():
    # The main/subagent split lives on the call. Without calls it is unknown,
    # and unknown must not render as a number.
    out = render_html(_rows(), [], [])
    assert "789,387" in out  # the totals are still honest
    assert '<div class="v dash">-</div>' in out
    assert "311,399" not in out.split("Trend", 1)[0]


def test_no_person_is_named():
    # The unit of account is the repository and the session; a full cwd would
    # carry a home directory, which is a person.
    out = _render()
    assert "/Users/someone" not in out
    assert "agent-yield" in out


# Eleven literal path shapes and what the page must render for each. A table
# rather than a list of asserts because `_repo` is a redaction: every row that
# is missing is a shape that leaks, and the two the audit found -- UNC and the
# WSL mount -- were missing precisely because nobody had typed them (N5).
_REPO_SHAPES = [
    # the home directory itself, on each platform's spelling of it
    ("/Users/ada", "HOME"),
    ("/home/ada", "HOME"),
    (r"C:\Users\ada", "HOME"),
    ("~", "HOME"),
    ("~/", "HOME"),
    # N5: a Windows network share. Three segments, not two, so the old
    # `len(parts) == 2` home check never fired and the function returned the
    # account name -- the one thing it exists to keep off a shared page.
    (r"\\server\Users\ada", "HOME"),
    # N5: a WSL mount, where the distro name sits between host and home.
    (r"\\wsl.localhost\Ubuntu\home\eric", "HOME"),
    # a real repository is still named, on every shape
    ("/Users/ada/IdeaProjects/agent-yield", "agent-yield"),
    (r"C:\Users\ada\src\agent-yield", "agent-yield"),
    (r"\\server\projects\agent-yield", "agent-yield"),
    # trailing separator, which splits to an empty final segment
    ("/Users/ada/repos/agent-yield/", "agent-yield"),
]


@pytest.mark.parametrize("cwd,expected", _REPO_SHAPES, ids=lambda v: v)
def test_a_home_directory_cwd_never_renders_the_account_name(cwd, expected):
    """The last-segment rule leaks the very thing it exists to hide.

    A session run in the home directory has the account name as its last path
    segment, so `/Users/ada` would render as "ada" -- a person, which is not
    the unit of account.

    The rule is now "the segment before the last is a home root", not "the
    path has exactly two segments". That is deliberately looser than it needs
    to be, and the direction of the looseness is the point: a repository whose
    parent directory is literally named `home` or `Users` renders as (home)
    instead of by name, which costs a label on a page. Getting it wrong the
    other way puts somebody's account name on a page that may be shared. A
    redaction should fail toward redacting.
    """
    from agent_yield.report_html import HOME_LABEL, _repo

    assert _repo(cwd) == (HOME_LABEL if expected == "HOME" else expected)


def test_a_repo_whose_parent_is_named_home_is_redacted_rather_than_named():
    """The known false positive, written down so it is a decision, not a bug.

    `/srv/home/dotfiles` is a real repository called `dotfiles`, and it
    renders as (home). That is the looseness above, chosen on purpose: the
    cost is a missing label, and the alternative costs a name.
    """
    from agent_yield.report_html import HOME_LABEL, _repo

    assert _repo("/srv/home/dotfiles") == HOME_LABEL


def test_the_html_yield_table_carries_the_area_split_and_the_band_shares():
    """#46 S1 renders into report_html as well as render_table.

    The review's scope finding was that v1 is two stories rendered into the
    two views that already exist, not a third view. The columns are appended
    rather than interleaved so the existing dash test keeps its cell indices.
    """
    out = _render()
    yield_table = out.split("Yield per day and mode", 1)[1]
    for column in ("Code", "Docs", "Other", "Tokens/insertion"):
        assert f">{column}</th>" in yield_table, column
    assert "300,000" in yield_table


def test_the_html_cost_bands_never_show_calls_without_sessions():
    """#46 review, finding 4, in the view that would be screenshotted.

    The share of main calls above a threshold is a mean over a session
    mixture: cheap short sessions move it with nothing changed about how any
    session is run. On this repo's own 2026-08-26 corpus the two figures
    disagree by 3x at every cut where either is non-zero. So the calls column
    does not exist without the sessions column, and both carry their
    denominator rather than a bare percentage.
    """
    yield_table = _render().split("Yield per day and mode", 1)[1]
    assert ">Cost bands, calls</th>" in yield_table
    assert ">Cost bands, sessions</th>" in yield_table
    assert yield_table.count(">Cost bands, calls</th>") == \
        yield_table.count(">Cost bands, sessions</th>")
    # Counts and denominators, not bare percentages: a share without its n is
    # not a measurement. Here 50% of calls crossed the dispatch line and 100%
    # of sessions did, off the same two calls.
    assert "calls 1/0/0 of 2 50/0/0%" in yield_table
    assert "sessions 1/0/0 of 1 100/0/0%" in yield_table
    # And the row with no main calls dashes rather than reading 0 of 0.
    assert "calls - of 0" in yield_table


def test_the_html_table_offers_no_per_area_ratio():
    """The same guard as the terminal, in the view that would be screenshotted.

    A `Tokens/code-insertion` column is a 2.38x apparent win rendered as a
    fact (#46 review, finding 2). The mix columns are counts; the only ratio
    on the row is the whole-day one.
    """
    yield_table = _render().split("Yield per day and mode", 1)[1]
    assert "Tokens/code-insertion" not in yield_table
    assert "Tokens/docs-insertion" not in yield_table
