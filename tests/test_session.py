"""Tests for measuring the session you are in."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from agent_yield.session import (
    cost_crossings,
    find_session,
    restart_advice,
    session_stats,
)


def _line(
    *,
    session_id: str,
    index: int,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_creation: int = 0,
    cache_read: int = 0,
    sidechain: bool = False,
) -> str:
    record = {
        "timestamp": f"2026-08-26T12:{index // 60:02d}:{index % 60:02d}.000Z",
        "sessionId": session_id,
        "requestId": f"req-{session_id}-{index}",
        "message": {
            "id": f"msg-{session_id}-{index}",
            "usage": {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cache_creation_input_tokens": cache_creation,
                "cache_read_input_tokens": cache_read,
            },
        },
    }
    if sidechain:
        record["isSidechain"] = True
    return json.dumps(record)


def _write(path: Path, lines: list[str]) -> Path:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _rising(session_id: str, calls: int, *, start: int, step: int) -> list[str]:
    return [
        _line(
            session_id=session_id,
            index=i,
            input_tokens=100,
            output_tokens=50,
            cache_read=start + step * i,
        )
        for i in range(calls)
    ]


def test_growth_over_a_rising_series(tmp_path: Path) -> None:
    path = _write(tmp_path / "s1.jsonl", _rising("s1", 20, start=1_000, step=1_000))
    stats = session_stats(path, baseline_calls=10)

    assert stats.calls == 20
    # opening: cache_read 1000..10000 mean 5500, plus 100 input each.
    assert stats.opening_context_per_call == 5_600.0
    # last call: cache_read 20000 + input 100.
    assert stats.current_context == 20_100
    assert stats.growth == 20_100 / 5_600.0
    assert stats.growth > 3.0
    assert stats.context_per_call is not None
    assert stats.total.output_tokens == 20 * 50


def test_growth_is_none_when_calls_do_not_exceed_baseline(tmp_path: Path) -> None:
    path = _write(tmp_path / "s2.jsonl", _rising("s2", 10, start=1_000, step=1_000))
    stats = session_stats(path, baseline_calls=10)

    assert stats.calls == 10
    assert stats.growth is None
    assert stats.opening_context_per_call is None
    assert stats.current_context > 0


def test_empty_and_absent_transcripts_are_none_not_zero(tmp_path: Path) -> None:
    empty = _write(tmp_path / "empty.jsonl", [])
    stats = session_stats(empty)
    assert stats.calls == 0
    assert stats.context_per_call is None
    assert stats.opening_context_per_call is None
    assert stats.growth is None
    assert stats.total.total == 0

    missing = session_stats(tmp_path / "nope.jsonl")
    assert missing.calls == 0
    assert missing.context_per_call is None
    assert missing.growth is None


def test_restart_advice_below_factor_is_none(tmp_path: Path) -> None:
    # Flat context: growth is ~1x, no restart is due.
    lines = [
        _line(session_id="s3", index=i, input_tokens=100, cache_read=5_000)
        for i in range(20)
    ]
    stats = session_stats(_write(tmp_path / "s3.jsonl", lines), baseline_calls=10)

    assert stats.growth is not None
    assert restart_advice(stats) is None


def test_restart_advice_above_factor_names_both_numbers(tmp_path: Path) -> None:
    path = _write(tmp_path / "s4.jsonl", _rising("s4", 20, start=1_000, step=1_000))
    stats = session_stats(path, baseline_calls=10)

    advice = restart_advice(stats, factor=2.0)
    assert advice is not None
    assert advice.count("\n") == 0
    assert "5,600" in advice
    assert "20,100" in advice
    assert "20 calls" in advice
    assert "$" not in advice


def test_restart_advice_is_none_when_growth_is_none(tmp_path: Path) -> None:
    path = _write(tmp_path / "s5.jsonl", _rising("s5", 3, start=1_000, step=1_000))
    stats = session_stats(path, baseline_calls=10)

    assert stats.growth is None
    assert restart_advice(stats) is None


def test_sidechain_records_excluded_from_parent_stats(tmp_path: Path) -> None:
    lines = _rising("s6", 20, start=1_000, step=1_000)
    # A subagent line with a huge context, interleaved into the parent file.
    lines.insert(
        5,
        _line(
            session_id="s6",
            index=99,
            input_tokens=500_000,
            output_tokens=1_000,
            cache_read=500_000,
            sidechain=True,
        ),
    )
    path = _write(tmp_path / "s6.jsonl", lines)

    stats = session_stats(path, baseline_calls=10)
    clean = session_stats(
        _write(tmp_path / "s6-clean.jsonl", _rising("s6c", 20, start=1_000, step=1_000)),
        baseline_calls=10,
    )

    assert stats.calls == clean.calls == 20
    assert stats.opening_context_per_call == clean.opening_context_per_call
    assert stats.current_context == clean.current_context
    assert stats.growth == clean.growth
    assert stats.total.total == clean.total.total


def test_find_session_picks_the_newest_file(tmp_path: Path) -> None:
    old = _write(tmp_path / "old.jsonl", _rising("old", 3, start=100, step=100))
    new = _write(tmp_path / "new.jsonl", _rising("new", 3, start=100, step=100))
    os.utime(old, (1_000_000, 1_000_000))
    os.utime(new, (2_000_000, 2_000_000))

    assert find_session(None, root=tmp_path) == new


def test_find_session_by_id_and_unknown_id(tmp_path: Path) -> None:
    wanted = _write(tmp_path / "abc-123.jsonl", _rising("abc-123", 3, start=100, step=100))
    _write(tmp_path / "other.jsonl", _rising("other", 3, start=100, step=100))

    assert find_session("abc-123", root=tmp_path) == wanted
    assert find_session("no-such-session", root=tmp_path) is None


def test_cost_crossings_report_the_call_each_band_was_entered_on(tmp_path):
    path = _write(tmp_path / "s.jsonl", [
        _line(session_id="s", index=i, cache_read=read)
        for i, read in enumerate(
            [10_000, 50_000, 350_000, 400_000, 550_000, 750_000]
        )
    ])
    crossings = cost_crossings(session_stats(path))
    assert crossings == {"dispatch": 3, "restart": 5, "stop": 6}


def test_a_band_never_entered_is_absent_rather_than_zero(tmp_path):
    path = _write(tmp_path / "s.jsonl", [
        _line(session_id="s", index=i, cache_read=10_000) for i in range(5)
    ])
    assert cost_crossings(session_stats(path)) == {}


def test_a_session_that_opens_in_a_band_crossed_the_ones_below_it_on_call_one(tmp_path):
    # Main sessions open expensive rather than growing into it: one machine
    # averaged 311,399 context/call with no doubling anywhere. Reporting
    # "never past dispatch" for those would miss the whole finding.
    path = _write(tmp_path / "s.jsonl", [
        _line(session_id="s", index=i, cache_read=550_000) for i in range(3)
    ])
    assert cost_crossings(session_stats(path)) == {"dispatch": 1, "restart": 1}


# Eight path shapes, seven of them read off the real transcript tree on this
# machine (`~/.claude/projects`) and the eighth -- the lowercase drive letter --
# the input #51 is about. A table rather than one example, because every slug
# bug so far has been a shape nobody had a reason to type: the fix for Windows
# separators (68f062f) was written and tested on the affected machine, by
# someone who had just diagnosed the class, and still missed the case variant
# one `cd` away.
_SLUG_SHAPES = [
    # measured: the directory this repo's own transcripts live in
    (r"C:\Users\ewehm\repos\agent-yield", "C--Users-ewehm-repos-agent-yield"),
    # the #51 input. The slug stays case-PRESERVING -- the comparison folds,
    # not the slug, because the slug is also what a human reads in an error.
    (r"c:\Users\ewehm\repos\agent-yield", "c--Users-ewehm-repos-agent-yield"),
    # measured: two levels up, and the scratchpad tree
    (r"C:\Users\ewehm", "C--Users-ewehm"),
    (r"C:\Users\ewehm\AppData\Local\Temp", "C--Users-ewehm-AppData-Local-Temp"),
    # measured, and the only real evidence for the `.` rule on either machine:
    # `\.claude\` becomes `--claude-`, the doubled dash being separator-then-dot.
    (
        r"C:\Users\ewehm\Documents\SampleProject\.claude\worktrees\summary-wt",
        "C--Users-ewehm-Documents-SampleProject--claude-worktrees-summary-wt",
    ),
    # measured on macOS: no drive, so the leading separator is a single dash
    ("/Users/x/IdeaProjects/agent-yield", "-Users-x-IdeaProjects-agent-yield"),
    ("/Users/x/.claude/projects", "-Users-x--claude-projects"),
    # NOT measured against a real tree -- no project on either machine has an
    # underscore in its path. It pins a rule the code already implements so a
    # refactor cannot drop it silently; if a real underscore project ever
    # appears and disagrees, this row is the one that is wrong.
    ("/Users/x/agent_yield", "-Users-x-agent-yield"),
]


@pytest.mark.parametrize("path,expected", _SLUG_SHAPES)
def test_project_slug_matches_the_real_transcript_directory_names(path, expected):
    r"""Measured on Windows 2026-08-26, against the real tree.

    `C:\Users\ewehm\repos\agent-yield` is stored by Claude Code as
    `C--Users-ewehm-repos-agent-yield`: the drive colon and every backslash
    become a dash, which is why the doubled dash appears after the drive
    letter. The slug replaced `/`, `.` and `_` and neither of those, so on
    Windows it returned the path unchanged, no candidate ever matched
    `parent.name`, and `find_session` returned None for *every* session --
    `status` measured nothing on that machine and said so silently.

    The POSIX rows are asserted alongside the Windows ones so a future edit
    cannot fix one platform by breaking the other. Section 3.1 is the standing
    reminder: a constant measured on one machine is not a constant.
    """
    from agent_yield.session import project_slug

    assert project_slug(Path(path)) == expected


@pytest.mark.skipif(
    os.name != "nt", reason="path case-folding is a Windows-only property (#51)"
)
def test_find_session_matches_when_only_the_drive_letter_case_differs(
    tmp_path, monkeypatch
):
    r"""#51, proven by hand on this machine before it was filed.

    Windows does not canonicalise path case: `os.getcwd()` returns whatever
    case was used to enter the directory, and `cd c:\users\ewehm\repos` is an
    ordinary thing to type. The slug that comes out can never equal the
    directory name Claude Code wrote, `find_session` returns None for the
    whole project, and `status` prints nothing and exits 0 -- so every session
    measurement taken here was conditional on how the drive letter happened to
    be capitalised, including the growth figures quoted in NEXT.md.

    The input is LOWERCASE on purpose. The same test written with the natural
    `C:` passes against the broken code, which is exactly how this survived
    68f062f, the morning fix of this same function.
    """
    projects = tmp_path / "projects"
    canonical = projects / "C--Users-ewehm-repos-agent-yield"
    canonical.mkdir(parents=True)
    ours = canonical / "aaa.jsonl"
    ours.write_text("{}\n", encoding="utf-8")

    monkeypatch.setattr(
        "agent_yield.session.main_transcript_dir", lambda: projects
    )
    found = find_session(None, None, cwd=Path(r"c:\Users\ewehm\repos\agent-yield"))
    assert found == ours


@pytest.mark.skipif(
    os.name == "nt", reason="POSIX path case-sensitivity cannot be shown on Windows"
)
def test_find_session_stays_case_sensitive_on_posix(tmp_path, monkeypatch):
    """The other half of #51's fix, and the reason it is not a `.lower()`.

    On POSIX `/repo/Mine` and `/repo/mine` are two directories, so two slugs
    differing only in case are two projects. Folding unconditionally would let
    `status` in one of them measure the other -- the cross-project read
    `find_session` was scoped to prevent, reintroduced by the fix for #51.
    """
    projects = tmp_path / "projects"
    theirs = projects / "-repo-Mine"
    theirs.mkdir(parents=True)
    (theirs / "aaa.jsonl").write_text("{}\n", encoding="utf-8")

    monkeypatch.setattr(
        "agent_yield.session.main_transcript_dir", lambda: projects
    )
    assert find_session(None, None, cwd=Path("/repo/mine")) is None


def test_find_session_does_not_reach_into_another_project(tmp_path, monkeypatch):
    """Measured 2026-08-25: `status` reported another repo's session.

    The unrestricted "most recently modified" fallback spans every project
    under ~/.claude/projects. With two sessions open it picks whichever
    wrote last -- and `agent-yield status` reported 357 calls, 535,788
    context and 10.6x growth for a 109-call session, because a session in
    another repo had touched its transcript a second earlier. `status`
    exits 1 to mean "leave"; deciding that on another session's cost is the
    same failure `boundary._stats_for` was fixed for.
    """
    from agent_yield.session import find_session, project_slug

    projects = tmp_path / "projects"
    mine = projects / project_slug(Path("/repo/mine"))
    theirs = projects / "-some-other-project"
    mine.mkdir(parents=True)
    theirs.mkdir(parents=True)

    ours = mine / "aaa.jsonl"
    ours.write_text("{}\n", encoding="utf-8")
    newer = theirs / "bbb.jsonl"
    newer.write_text("{}\n", encoding="utf-8")
    os.utime(ours, (1_000, 1_000))
    os.utime(newer, (2_000, 2_000))  # the other project wrote more recently

    monkeypatch.setattr(
        "agent_yield.session.main_transcript_dir", lambda: projects
    )
    found = find_session(None, None, cwd=Path("/repo/mine"))
    assert found == ours, "the newer file belongs to another project"


def test_find_session_returns_none_when_this_project_has_no_transcript(
    tmp_path, monkeypatch
):
    """Measure the session you can identify, or measure nothing."""
    from agent_yield.session import find_session

    projects = tmp_path / "projects"
    other = projects / "-some-other-project"
    other.mkdir(parents=True)
    (other / "bbb.jsonl").write_text("{}\n", encoding="utf-8")

    monkeypatch.setattr(
        "agent_yield.session.main_transcript_dir", lambda: projects
    )
    assert find_session(None, None, cwd=Path("/repo/mine")) is None


def test_an_explicit_root_is_not_second_guessed(tmp_path, monkeypatch):
    """`--transcripts <dir>` is a caller who has already scoped the search."""
    from agent_yield.session import find_session

    root = tmp_path / "anywhere"
    root.mkdir()
    only = root / "ccc.jsonl"
    only.write_text("{}\n", encoding="utf-8")
    assert find_session(None, root, cwd=Path("/repo/unrelated")) == only
