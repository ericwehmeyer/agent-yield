import datetime as dt
import os
import subprocess
from pathlib import Path

import pytest

from agent_yield.outcomes import DailyOutcome, daily_outcomes, default_branch

WHEN = "2026-08-24T12:00:00+00:00"


def _git(cwd: Path, *args: str, **env_extra: str) -> None:
    env = {
        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@e",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@e",
        "PATH": os.environ["PATH"],
        **env_extra,
    }
    subprocess.run(
        ["git", *args], cwd=cwd, env=env, capture_output=True, text=True, check=True
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


def test_counts_all_commits_across_branches(repo):
    day = dt.date(2026, 8, 24)
    outcomes = {o.day: o for o in daily_outcomes(repo, day, day)}
    # two ordinary commits plus the merge commit
    assert outcomes[day].commits == 3


def test_counts_net_insertions(repo):
    day = dt.date(2026, 8, 24)
    outcomes = {o.day: o for o in daily_outcomes(repo, day, day)}
    assert outcomes[day].lines == 3


def test_days_with_no_activity_are_present_and_zero(repo):
    outcomes = {
        o.day: o for o in
        daily_outcomes(repo, dt.date(2026, 8, 23), dt.date(2026, 8, 25))
    }
    assert outcomes[dt.date(2026, 8, 23)] == DailyOutcome(
        day=dt.date(2026, 8, 23), merges=0, commits=0, lines=0, tests=None
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
