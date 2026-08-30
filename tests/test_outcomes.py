import datetime as dt
import os
import subprocess
from pathlib import Path

import pytest

from agent_yield.outcomes import DailyOutcome, daily_outcomes, default_branch

WHEN = "2026-08-24T12:00:00+00:00"


# Variables a child process cannot start without, copied from the parent when
# the parent has them. The stripped environment below is deliberate -- it is
# what keeps git deterministic here, free of the operator's own config -- but
# stripping `SystemRoot` is not part of that intent: it is a documented way to
# break a child process on Windows, and the failure would present as an
# unreproducible one-platform CI flake rather than as this helper's doing
# (audit N9). Absent on POSIX, so no branch on os.name: "pass it through if it
# is there" is the correct rule on every platform.
_PASS_THROUGH = ("PATH", "SystemRoot")


def _git_env(**extra: str) -> dict[str, str]:
    env = {
        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@e",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@e",
    }
    for name in _PASS_THROUGH:
        if name in os.environ:
            env[name] = os.environ[name]
    env.update(extra)
    return env


def test_the_git_helper_hands_the_child_what_it_cannot_start_without(monkeypatch):
    """N9: the helper built its env from PATH and four identity variables.

    It works with this git build and would break on a Windows box whose git
    needs `SystemRoot` -- on one leg of the matrix, intermittently, looking
    like anything but a test helper. Asserted on all three platforms rather
    than behind a skipif: the rule under test is "copy it if the parent has
    it", which is true everywhere, and a Windows-only assertion here would go
    unrun on the machine most likely to edit this file.
    """
    monkeypatch.setenv("SystemRoot", "C:/Windows")
    env = _git_env()
    assert env["SystemRoot"] == "C:/Windows"
    assert env["PATH"] == os.environ["PATH"]


def _git(cwd: Path, *args: str, **env_extra: str) -> None:
    env = _git_env(**env_extra)
    subprocess.run(
        ["git", *args], cwd=cwd, env=env, capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=True
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    work = tmp_path / "r"
    work.mkdir()
    _git(work, "init", "-b", "main")
    (work / "a.txt").write_text("one\ntwo\n", encoding="utf-8")
    _git(work, "add", "a.txt")
    _git(work, "commit", "-m", "first",
         GIT_AUTHOR_DATE=WHEN, GIT_COMMITTER_DATE=WHEN)
    _git(work, "checkout", "-b", "feature")
    (work / "b.txt").write_text("three\n", encoding="utf-8")
    _git(work, "add", "b.txt")
    _git(work, "commit", "-m", "second",
         GIT_AUTHOR_DATE=WHEN, GIT_COMMITTER_DATE=WHEN)
    _git(work, "checkout", "main")
    _git(work, "merge", "--no-ff", "feature", "-m", "merge feature",
         GIT_AUTHOR_DATE=WHEN, GIT_COMMITTER_DATE=WHEN)
    return work


def test_default_branch_falls_back_to_main(repo):
    assert default_branch(repo) == "main"


def test_counts_one_merge_on_the_default_branch(repo):
    day = dt.date(2026, 8, 24)
    outcomes = {o.day: o for o in daily_outcomes(repo, day, day)}
    assert outcomes[day].merges == 1


def test_commits_counts_what_shipped_not_every_commit_object(repo):
    """One walk for the numerator's denominator, and it is the one `lines` uses.

    `commits` walked `git log --all --no-merges` and then folded the merge
    count back in, so a merged branch's work was counted twice: once as the
    branch commit and once as the merge that shipped it. `lines` walked
    `<branch> --first-parent --numstat` all along. The two sat on one row of
    the report and were divided into each other, over different universes --
    the #46 review's blocking finding 3.

    The fixture is main plus a feature branch merged in: three commit objects,
    two of which shipped. `lines` counts the same two, which is the property
    that makes the row divisible.
    """
    day = dt.date(2026, 8, 24)
    outcomes = {o.day: o for o in daily_outcomes(repo, day, day)}
    assert outcomes[day].commits == 2
    assert outcomes[day].merges == 1
    # Same walk, so this is a ratio and not a category error.
    assert outcomes[day].lines == 3


def test_a_commit_on_an_unmerged_branch_is_not_yet_shipped(repo):
    """The direction of the choice, stated as a test.

    A commit that exists only on a side branch is written work and is not
    landed work. This tool divides spend by what shipped, so it does not
    appear until a merge brings it in -- at which point it is counted once,
    through the merge.
    """
    (repo / "c.txt").write_text("four\n", encoding="utf-8")
    _git(repo, "checkout", "-b", "unmerged")
    _git(repo, "add", "c.txt")
    _git(repo, "commit", "-m", "third",
         GIT_AUTHOR_DATE=WHEN, GIT_COMMITTER_DATE=WHEN)
    _git(repo, "checkout", "main")

    day = dt.date(2026, 8, 24)
    outcomes = {o.day: o for o in daily_outcomes(repo, day, day)}
    assert outcomes[day].commits == 2
    assert outcomes[day].lines == 3


def test_counts_net_insertions(repo):
    day = dt.date(2026, 8, 24)
    outcomes = {o.day: o for o in daily_outcomes(repo, day, day)}
    assert outcomes[day].lines == 3


def test_days_with_no_activity_are_present_and_zero(repo):
    """`asof` is pinned because survival is measured against the wall clock.

    `surviving_by_day` returns None while a day's horizon is still in the
    future and a count once it has passed, so a floating `asof` makes this
    assertion flip from None to 0 the moment the horizon elapses -- which it
    did at 2026-08-30T00:00Z, on every branch at once, seven days after the
    2026-08-23 the dates below pin. The horizon guard is covered in
    `test_survival.py`; what this test claims is that a day nobody committed
    on is present with zeros, and that claim needs a settled clock to state.
    """
    outcomes = {
        o.day: o for o in daily_outcomes(
            repo, dt.date(2026, 8, 23), dt.date(2026, 8, 25),
            asof=dt.datetime(2026, 10, 1, tzinfo=dt.timezone.utc),
        )
    }
    assert outcomes[dt.date(2026, 8, 23)] == DailyOutcome(
        day=dt.date(2026, 8, 23), merges=0, commits=0, lines=0, tests=None,
        surviving_lines=0,
    )


def test_test_count_is_none_when_no_command_given(repo):
    day = dt.date(2026, 8, 24)
    outcomes = {o.day: o for o in daily_outcomes(repo, day, day)}
    assert outcomes[day].tests is None


def test_git_output_is_decoded_as_utf8_not_the_locale_codepage(tmp_path):
    """Git speaks UTF-8; `text=True` alone decodes it as cp1252 on Windows.

    `subprocess.run(..., text=True)` with no `encoding=` decodes using
    `locale.getpreferredencoding(False)`, which is cp1252 on Windows and
    UTF-8 nearly everywhere else. A commit subject containing a section
    mark came back as `Â§` on Windows only -- the mojibake in issue #41,
    which the audit of `read_text`/`write_text` could not find because the
    corrupting read is a subprocess, not a file.

    The subject below is a real one from this repo's history.
    """
    from agent_yield import handoff as handoff_module
    from agent_yield import outcomes as outcomes_module

    subject = "working-method §12: the rubric, and an em dash — here"
    work = tmp_path / "r"
    work.mkdir()
    _git(work, "init", "-b", "main")
    (work / "a.txt").write_text("one\n", encoding="utf-8")
    _git(work, "add", "a.txt")
    _git(work, "commit", "-m", subject,
         GIT_AUTHOR_DATE=WHEN, GIT_COMMITTER_DATE=WHEN)

    for name, fn in (
        ("outcomes", lambda: outcomes_module._git(work, "log", "--format=%s")),
        ("handoff", lambda: handoff_module._git(work, "log", "--format=%s")),
    ):
        got = fn() or ""
        assert "§" in got, f"{name}: section mark did not survive"
        assert "—" in got, f"{name}: em dash did not survive"
        assert "Â" not in got, f"{name}: mojibake -- decoded as cp1252"


@pytest.fixture
def areas(tmp_path: Path) -> Path:
    """One commit touching each of the three areas, with distinct line counts.

    Distinct counts so a classifier that puts a file in the wrong bucket
    cannot pass by arithmetic accident.
    """
    work = tmp_path / "areas"
    work.mkdir()
    _git(work, "init", "-b", "main")
    (work / "src").mkdir()
    (work / "docs").mkdir()
    (work / "src" / "m.py").write_text("a\n" * 5, encoding="utf-8")
    (work / "docs" / "d.md").write_text("b\n" * 7, encoding="utf-8")
    (work / "README.md").write_text("c\n" * 3, encoding="utf-8")
    (work / "pyproject.toml").write_text("d\n" * 11, encoding="utf-8")
    _git(work, "add", ".")
    _git(work, "commit", "-m", "areas",
         GIT_AUTHOR_DATE=WHEN, GIT_COMMITTER_DATE=WHEN)
    return work


def test_insertions_split_by_area_sum_to_the_total(areas):
    """#46 S1: the split is a decomposition, so it must add up.

    `lines` is the published number. A split that does not sum to it is a
    second measurement of the same quantity, and two numbers for one quantity
    is what this tool exists to stop.
    """
    day = dt.date(2026, 8, 24)
    outcome = {o.day: o for o in daily_outcomes(areas, day, day)}[day]
    assert outcome.code_lines == 5
    assert outcome.docs_lines == 10   # docs/d.md + README.md
    assert outcome.other_lines == 11  # pyproject.toml
    assert outcome.code_lines + outcome.docs_lines + outcome.other_lines \
        == outcome.lines


def test_a_markdown_file_outside_a_docs_directory_is_still_docs(areas):
    """The classifier keys on what a file IS, not on where this repo puts it.

    A rule spelled `docs/` reproduces the hand count that #46's plan
    pre-registered (1,127 code / 2,931 docs on 08-25) only because that count
    called README.md's 94 lines `other`. It is documentation by any reading,
    and a directory-prefix rule does not travel to a repo laid out
    differently. This is the one deliberate departure from the plan's
    acceptance figure, and it is 94 lines of 4,203.
    """
    day = dt.date(2026, 8, 24)
    outcome = {o.day: o for o in daily_outcomes(areas, day, day)}[day]
    assert outcome.docs_lines == 10


def test_the_area_split_walks_the_same_commits_as_the_total(areas):
    """A side-branch commit is not landed work, in the split as in the total.

    The #46 review's finding 3 was two walks over different populations
    divided into each other. A split computed on its own walk would
    reintroduce it one column over.
    """
    (areas / "src" / "n.py").write_text("z\n" * 99, encoding="utf-8")
    _git(areas, "checkout", "-b", "side")
    _git(areas, "add", ".")
    _git(areas, "commit", "-m", "unmerged",
         GIT_AUTHOR_DATE=WHEN, GIT_COMMITTER_DATE=WHEN)
    _git(areas, "checkout", "main")

    day = dt.date(2026, 8, 24)
    outcome = {o.day: o for o in daily_outcomes(areas, day, day)}[day]
    assert outcome.code_lines == 5


def test_thrash_is_what_a_day_wrote_and_did_not_keep():
    """Hand-counted: 10 lines written, 6 of them still there at the horizon."""
    outcome = DailyOutcome(
        day=dt.date(2026, 1, 1), lines=10, surviving_lines=6)
    assert outcome.thrash == 4


def test_thrash_is_none_while_survival_is_unmeasured():
    """A day inside the horizon has no thrash figure, and 0 would claim it had."""
    outcome = DailyOutcome(
        day=dt.date(2026, 1, 1), lines=10, surviving_lines=None)
    assert outcome.thrash is None
