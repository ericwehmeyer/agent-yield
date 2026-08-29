import datetime as dt
import os
import subprocess
from pathlib import Path

import pytest

from agent_yield.survival import blame_counts

# Variables a child process cannot start without, copied from the parent when
# the parent has them (audit N9: stripping SystemRoot breaks git on Windows).
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


def _git(cwd: Path, *args: str, **env_extra: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=cwd, env=_git_env(**env_extra),
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return result.stdout


def _commit(repo: Path, path: str, body: str, when: str) -> str:
    (repo / path).write_text(body, encoding="utf-8")
    _git(repo, "add", path)
    _git(repo, "commit", "-m", f"write {path}",
         GIT_AUTHOR_DATE=when, GIT_COMMITTER_DATE=when)
    return _git(repo, "rev-parse", "HEAD").strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-b", "main")
    return tmp_path


def test_blame_counts_credits_each_line_to_the_commit_that_wrote_it(repo):
    """Hand-counted: first writes 10 lines, second replaces 4 of them.

    The tree at the second commit holds 10 lines. Six are the originals that
    were left alone; four are the replacements. Neither number comes from the
    code under test -- they are read off the two file bodies below.
    """
    first = _commit(repo, "a.txt", "".join(f"line {i}\n" for i in range(10)),
                    "2026-01-01T12:00:00+00:00")
    kept = "".join(f"line {i}\n" for i in range(6))
    replaced = "".join(f"new {i}\n" for i in range(4))
    second = _commit(repo, "a.txt", kept + replaced, "2026-01-05T12:00:00+00:00")

    counts = blame_counts(repo, second)

    assert counts[first] == 6
    assert counts[second] == 4


from agent_yield.survival import surviving_by_day


def test_a_day_is_scored_at_its_own_horizon_not_at_today(repo):
    """Hand-counted: 2026-01-01 writes 10 lines, 2026-01-05 replaces 4.

    2026-01-01's horizon is 2026-01-08, and the newest commit by then is the
    one on the 5th, whose tree holds 6 of the 10. So 6, and it stays 6 however
    much later the report is run.
    """
    _commit(repo, "a.txt", "".join(f"line {i}\n" for i in range(10)),
            "2026-01-01T12:00:00+00:00")
    kept = "".join(f"line {i}\n" for i in range(6))
    replaced = "".join(f"new {i}\n" for i in range(4))
    _commit(repo, "a.txt", kept + replaced, "2026-01-05T12:00:00+00:00")

    got = surviving_by_day(
        repo, "main", dt.date(2026, 1, 1), dt.date(2026, 1, 5),
        asof=dt.datetime(2026, 3, 1, tzinfo=dt.timezone.utc),
    )

    assert got[dt.date(2026, 1, 1)] == 6
    assert got[dt.date(2026, 1, 5)] == 4


def test_a_day_younger_than_the_horizon_is_none_rather_than_zero(repo):
    """A day whose horizon has not arrived is unmeasured, not empty.

    Zero would read as "nothing survived", which is a finding. There is no
    finding here yet.
    """
    _commit(repo, "a.txt", "one\n", "2026-01-01T12:00:00+00:00")

    got = surviving_by_day(
        repo, "main", dt.date(2026, 1, 1), dt.date(2026, 1, 1),
        asof=dt.datetime(2026, 1, 3, tzinfo=dt.timezone.utc),
    )

    assert got[dt.date(2026, 1, 1)] is None
