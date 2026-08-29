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
