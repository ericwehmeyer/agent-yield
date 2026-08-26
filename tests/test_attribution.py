"""#45: which machine wrote a commit, and the two ways of being wrong about it.

The end-to-end tests build TWO clones and move commits between them over the
filesystem, because the whole claim is that a sha this clone wrote is
distinguishable from one that arrived -- and a single-repo fixture cannot tell
those apart, which is the shape of failure this ticket exists to remove.
"""
from __future__ import annotations

import datetime as dt
import os
import subprocess
from pathlib import Path

import pytest

from agent_yield.attribution import FOREIGN, LOCAL, UNKNOWN, Machine, created_here
from agent_yield.outcomes import daily_outcomes

WHEN = "2026-08-24T12:00:00+00:00"
DAY = dt.date(2026, 8, 24)
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
    return subprocess.run(
        ["git", *args], cwd=cwd, env=_git_env(**env_extra), capture_output=True,
        text=True, encoding="utf-8", errors="replace", check=True,
    ).stdout


def _commit(work: Path, name: str, body: str) -> str:
    (work / name).write_text(body, encoding="utf-8")
    _git(work, "add", name)
    _git(work, "commit", "-m", name, GIT_AUTHOR_DATE=WHEN, GIT_COMMITTER_DATE=WHEN)
    return _git(work, "rev-parse", "HEAD").strip()


@pytest.fixture
def two_clones(tmp_path: Path) -> tuple[Path, Path, str, str]:
    """(here, there, sha written here, sha written there and fetched in).

    `there` is a second clone standing in for the other machine. Its commit
    reaches `here` by a fetch, exactly as the other machine's does, so `here`'s
    reflog sees it arrive and never sees it written.
    """
    here = tmp_path / "here"
    here.mkdir()
    _git(here, "init", "-b", "main")
    _commit(here, "base.txt", "base\n")

    there = tmp_path / "there"
    _git(tmp_path, "clone", "-q", str(here), str(there))
    foreign = _commit(there, "theirs.txt", "theirs\n")

    mine = _commit(here, "mine.txt", "mine\n")
    _git(here, "fetch", "-q", str(there), "main:refs/remotes/there/main")
    return here, there, mine, foreign


def test_a_sha_this_clone_wrote_is_local(two_clones):
    here, _, mine, _ = two_clones
    assert Machine(here).label(mine, dt.datetime.now(dt.timezone.utc)) == LOCAL


def test_a_sha_that_arrived_over_the_wire_is_foreign(two_clones):
    """The whole point. A fetch moves a sha in without writing it, so the
    reflog has an entry for the fetch and none for the commit."""
    here, _, _, foreign = two_clones
    assert Machine(here).label(foreign, dt.datetime.now(dt.timezone.utc)) == FOREIGN


def test_a_commit_older_than_the_reflog_is_unknown_not_foreign(two_clones):
    """UNKNOWN is a real outcome. A clone made today cannot disown a commit
    made before it existed, and calling that FOREIGN is how a denominator goes
    quietly wrong."""
    here, _, _, foreign = two_clones
    machine = Machine(here)
    before = machine.begins - dt.timedelta(hours=1)
    assert machine.label(foreign, before) == UNKNOWN


def test_no_reflog_at_all_means_unknown_rather_than_foreign(tmp_path: Path):
    empty = tmp_path / "empty"
    empty.mkdir()
    _git(empty, "init", "-b", "main")
    machine = Machine(empty)
    assert not machine.available
    assert machine.label("0" * 40, dt.datetime.now(dt.timezone.utc)) == UNKNOWN


def test_a_rebase_continue_writes_a_sha_and_is_counted(tmp_path: Path):
    """The verb this originally missed, and the reason three commits this
    machine made were labelled foreign: a pick that stops on a conflict
    finishes as a bare `rebase (continue)`, with no `(pick)` anywhere on the
    line."""
    assert created_here("rebase (continue): #52: closed -- three measurement errors")
    assert created_here("rebase (continue) (pick): #58: delete the constant")
    assert created_here("commit: first")
    assert created_here("commit (amend): first, again")
    assert created_here("pull --rebase -q (pick): #61: the dedup had a second copy")
    assert not created_here("rebase (start): checkout origin/main")
    assert not created_here("rebase (continue) (finish): returning to refs/heads/main")
    assert not created_here("reset: moving to 0207098")
    assert not created_here("clone: from https://example.invalid/r.git")
    assert not created_here("pull: Fast-forward")


def test_the_verb_is_read_and_the_subject_is_not():
    """#32's lesson one file over: the test is on the property, not the wording.
    A commit subject can contain any of these words -- this repo's own subjects
    quote reflog verbs -- and it is the verb before the first colon that says
    what happened."""
    assert not created_here("rebase (start): commit: what a pick does")
    assert not created_here("reset: moving to a commit (amend) of sorts")
    assert not created_here("pull: merged the (pick) branch")


def test_daily_outcomes_counts_only_what_this_clone_wrote(two_clones):
    """`daily_outcomes` walks `--all`, so the other machine's commit is in the
    count the moment it is fetched -- branch or no branch. That is the 25x
    denominator #44 found, in three commits."""
    here, _, _, _ = two_clones
    everything = {o.day: o for o in daily_outcomes(here, DAY, DAY)}
    scoped = {o.day: o for o in daily_outcomes(here, DAY, DAY, machine=Machine(here))}

    assert everything[DAY].commits == 3          # base, mine, theirs
    assert scoped[DAY].commits == 2              # base and mine; theirs is not ours
    assert scoped[DAY].unattributable == 0


def test_unattributable_commits_are_reported_and_not_counted(two_clones, monkeypatch):
    """A commit the clone cannot judge is counted in its own field. Folding it
    into either `commits` or the foreign pile would be the guess this module
    refuses to make."""
    here, _, _, _ = two_clones
    machine = Machine(here)
    machine.written = set()                      # as if the reflog had expired
    machine.begins = dt.datetime.now(dt.timezone.utc)

    scoped = {o.day: o for o in daily_outcomes(here, DAY, DAY, machine=machine)}
    assert scoped[DAY].commits == 0
    assert scoped[DAY].unattributable == 3


def test_unscoped_outcomes_are_unchanged_and_report_zero_unattributable(two_clones):
    """Off by default: every existing number keeps its meaning until a caller
    asks for the other one."""
    here, _, _, _ = two_clones
    rows = daily_outcomes(here, DAY, DAY)
    assert all(o.unattributable == 0 for o in rows)
    assert rows[0].commits == 3                  # base, mine, theirs -- every machine
