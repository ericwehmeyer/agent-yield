"""Which machine made a commit, from a record git keeps and never pushes.

Two machines work this repo through GitHub (§7), and every git-denominated
metric in `report` divides ONE machine's tokens by BOTH machines' commits. #44
measured that error at 25x on one day. #45 proposed fixing it by correlating a
commit's timestamp against this machine's calls, +/- 6 minutes.

**Measured, that rule is 61% accurate and over-attributes 1.67x** -- it claims
106 of this repo's 118 commits for this machine when 63 are its. It is not a
tuning problem: at every window from one minute to thirty it calls almost
everything local, because both machines work the same hours -- which is what the
queue in §7 is FOR -- so "this machine was busy near the commit" is true of a
foreign commit too. The nearest local call to a foreign commit is routinely
under ten seconds. `docs/experiments/45-attribution/attribute.py` has the sweep.

**Git does record the machine. It is `.git/logs/HEAD`.** The reflog is per clone
and is never pushed: it holds a line for every sha this clone WROTE and a
different line for every sha that merely arrived. So attribution is a lookup,
not a guess, and the three outcomes are honest ones:

    local     this clone's reflog shows it writing that sha
    foreign   the reflog covers that moment and does not
    unknown   the commit predates the reflog -- this clone did not exist yet

WHAT THIS CANNOT DO, before any caller relies on it:

* **The reflog expires** (`gc.reflogExpire`, 90 days reachable, 30 unreachable).
  This answers "who shipped it" for recent work, which is what a daily report
  asks. It will not answer it for a quarter-old commit, and `unknown` is what it
  will say then -- which is the correct answer, not a failure.
* **A rebase re-commits.** When the other machine rebases work authored here, the
  sha it publishes was written there and this clone never saw it. `local` means
  "this clone wrote this sha", which is the right question for a denominator of
  what shipped from here, and it is not the same question as who typed it.
* **It is per clone**, so it scopes a numerator and a denominator to the SAME
  machine. It says nothing about the other machine's total, and a caller that
  needs both must get the other machine's set from that machine.

`unknown` is a real outcome and is never folded into either other bucket. A
commit that is not attributable is not thereby foreign; pretending otherwise is
the failure #44 found three times in one day, each time in the direction that
looks like it is working.
"""
from __future__ import annotations

import datetime as dt
import subprocess
from pathlib import Path

LOCAL = "local"
FOREIGN = "foreign"
UNKNOWN = "unknown"


def created_here(action: str) -> bool:
    """Does this reflog action mean THIS CLONE WROTE THIS SHA?

    Read the verb, never the message: everything after the first colon is the
    commit's own subject and may contain any of these words. The verbs that
    write a sha are `commit`, `commit (amend)`, anything ending `(pick)` -- a
    rebase or `pull --rebase` replaying work, which mints a sha that exists
    nowhere else -- and a bare `rebase (continue)`, which is how a pick that
    stopped on a conflict finishes.

    **That last one is easy to miss, and the first version of this missed it**,
    marking three commits this clone made as foreign: #52, #56 and #57 -- the
    same three whose subject lines the rebase ate (§7). The verbs that only MOVE
    the tip create nothing: `(start)`, `(finish)`, `reset`, `pull`, `clone`,
    `(abort)`, and a foreign sha enters under exactly those.
    """
    verb = action.split(":", 1)[0].strip()
    return (verb.startswith("commit")
            or verb.endswith("(pick)")
            or verb.endswith("(continue)"))


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=repo, capture_output=True,
                            text=True, encoding="utf-8", errors="replace")
    return result.stdout if result.returncode == 0 else ""


def read_reflog(repo: Path) -> tuple[set[str], dt.datetime | None]:
    """(shas this clone wrote, when its reflog begins).

    The second value is what makes `unknown` honest. Returns `(set(), None)` for
    a repository with no reflog at all -- a fresh clone, or one whose reflog has
    expired -- and every commit is then `unknown`, which is true.
    """
    written: set[str] = set()
    begins: dt.datetime | None = None
    for line in _git(repo, "reflog", "show", "--date=iso-strict",
                     "--format=%H|%gd|%gs", "HEAD").splitlines():
        parts = line.split("|", 2)
        if len(parts) != 3:
            continue
        sha, when, action = parts
        stamp = _stamp(when)
        if stamp is not None:
            begins = stamp if begins is None else min(begins, stamp)
        if created_here(action):
            written.add(sha)
    return written, begins


def _stamp(reflog_selector: str) -> dt.datetime | None:
    """`HEAD@{2026-08-26T11:37:55-04:00}` -> an aware UTC datetime."""
    start, end = reflog_selector.find("{"), reflog_selector.rfind("}")
    if start < 0 or end < start:
        return None
    try:
        return dt.datetime.fromisoformat(
            reflog_selector[start + 1:end]).astimezone(dt.timezone.utc)
    except ValueError:
        return None


def label(sha: str, committed: dt.datetime | None, written: set[str],
          begins: dt.datetime | None) -> str:
    """`local`, `foreign` or `unknown` for one commit. Never guesses."""
    if sha in written:
        return LOCAL
    if begins is None or committed is None or committed < begins:
        return UNKNOWN
    return FOREIGN


class Machine:
    """This clone's answer to "did I write that?", read once and reused.

    Held as an object because `read_reflog` shells out, and the callers that
    need it -- a per-day walk over every commit in a range -- would otherwise
    run it once per commit.
    """

    def __init__(self, repo: Path) -> None:
        self.repo = Path(repo)
        self.written, self.begins = read_reflog(self.repo)

    @property
    def available(self) -> bool:
        """False when there is no reflog to read: everything is `unknown`."""
        return self.begins is not None

    def label(self, sha: str, committed: dt.datetime | None) -> str:
        return label(sha, committed, self.written, self.begins)
