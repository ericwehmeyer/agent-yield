"""The denominator: what git says shipped.

Read-only by construction. Every git invocation here is a query -- no fetch,
no checkout of the caller's working tree, no history rewriting. The one
operation that needs a different tree (`test_count_at`) uses a detached
worktree in a temp directory and removes it afterwards.
"""
from __future__ import annotations

import datetime as dt
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .attribution import LOCAL, UNKNOWN, Machine


@dataclass(frozen=True)
class DailyOutcome:
    day: dt.date
    merges: int = 0
    commits: int = 0
    lines: int = 0
    tests: int | None = None
    unattributable: int = 0
    """Commits this machine can neither claim nor disown -- older than its own
    reflog. Counted and reported, never folded into `commits`, because a commit
    that is not attributable is not thereby somebody else's (`attribution.py`).
    Always 0 when the caller did not ask for machine scoping."""


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    return result.stdout if result.returncode == 0 else ""


def default_branch(repo: Path) -> str:
    head = _git(repo, "symbolic-ref", "--quiet", "refs/remotes/origin/HEAD").strip()
    if head:
        return head.rsplit("/", 1)[-1]
    for candidate in ("main", "master"):
        if _git(repo, "rev-parse", "--verify", "--quiet", candidate).strip():
            return candidate
    return _git(repo, "rev-parse", "--abbrev-ref", "HEAD").strip() or "main"


def _day_of(iso: str) -> dt.date | None:
    try:
        return dt.datetime.fromisoformat(iso).astimezone(dt.timezone.utc).date()
    except ValueError:
        return None


def _when(iso: str) -> dt.datetime | None:
    try:
        return dt.datetime.fromisoformat(iso).astimezone(dt.timezone.utc)
    except ValueError:
        return None


def _split(line: str) -> tuple[str, str]:
    """`<sha> <iso>` -> (sha, iso)."""
    sha, _, iso = line.strip().partition(" ")
    return sha, iso


def _split3(line: str) -> tuple[str, str, str]:
    """`<sha> <iso> <parents...>` -> (sha, iso, parents).

    The parent list is how a merge is recognised without a second walk: a
    commit with more than one parent is a merge, and `--first-parent` has
    already put it in the population being counted.
    """
    sha, _, rest = line.strip().partition(" ")
    iso, _, parents = rest.partition(" ")
    return sha, iso, parents


def _utc_midnight(day: dt.date) -> str:
    # A bare "YYYY-MM-DD" is parsed by git's approxidate in the local
    # timezone, and on at least some platform/git-version combinations that
    # produces off-by-one-day results at exactly midnight boundaries.
    # Anchoring explicitly to UTC midnight makes the window unambiguous.
    return f"{day.isoformat()} 00:00:00 +0000"


def daily_outcomes(
    repo: Path,
    since: dt.date,
    until: dt.date,
    test_command: list[str] | None = None,
    machine: "Machine | None" = None,
) -> list[DailyOutcome]:
    """One row per day in range.

    `machine` scopes the denominator to the clone that made the commits. Without
    it these counts are every machine's work, which is right for "what shipped"
    and wrong for anything divided by one machine's tokens -- #44 measured that
    mismatch at 25x. With it, a commit this clone did not write is not counted,
    and one it cannot judge is counted separately in `unattributable` rather
    than dropped silently. See `attribution.py`.
    """
    repo = Path(repo)
    branch = default_branch(repo)
    window = ["--since", _utc_midnight(since),
              "--until", _utc_midnight(until + dt.timedelta(days=1))]

    unattributable: dict[dt.date, int] = {}

    def mine(sha: str, iso: str, day: dt.date) -> bool:
        """Does this commit belong in this machine's denominator?"""
        if machine is None:
            return True
        verdict = machine.label(sha, _when(iso))
        if verdict == UNKNOWN:
            unattributable[day] = unattributable.get(day, 0) + 1
        return verdict == LOCAL

    # ONE walk for both counts, and it is the walk `lines` below already used.
    #
    # `commits` came from `git log --all --no-merges` with the merge count
    # folded back in, so a merged branch's work was counted twice -- once as
    # the branch commit and once as the merge that shipped it -- while `lines`
    # counted it once. The two then sat on one row of the report and were
    # divided into each other over different universes (#46 review, finding 3).
    #
    # First-parent on the default branch is "what shipped", which is what this
    # tool divides spend by. A commit that exists only on a side branch is
    # written work and not landed work; it appears when a merge brings it in,
    # once, through the merge. On a linear history -- this repo's -- the two
    # walks agree exactly, so no published figure moves.
    #
    # One walk also means `mine` is called once per commit. Two walks over
    # overlapping populations counted the same unattributable commit twice,
    # which is why the `lines` walk below re-implements the machine check
    # instead of calling it.
    commits: dict[dt.date, int] = {}
    merges: dict[dt.date, int] = {}
    for line in _git(repo, "log", branch, "--first-parent",
                     "--pretty=%H %cI %P", *window).splitlines():
        sha, iso, parents = _split3(line)
        day = _day_of(iso)
        if day and mine(sha, iso, day):
            commits[day] = commits.get(day, 0) + 1
            if len(parents.split()) > 1:
                merges[day] = merges.get(day, 0) + 1

    lines: dict[dt.date, int] = {}
    current: dt.date | None = None
    counting = True
    for raw in _git(repo, "log", branch, "--first-parent", "--pretty=@%H %cI",
                    "--numstat", *window).splitlines():
        if raw.startswith("@"):
            sha, iso = _split(raw[1:])
            current = _day_of(iso)
            # `mine` is not called again here: this walk revisits the same
            # commits as the merge walk above, and a second call would count
            # the same unattributable commit twice.
            counting = current is not None and (
                machine is None or machine.label(sha, _when(iso)) == LOCAL)
            continue
        if not raw.strip() or current is None or not counting:
            continue
        added = raw.split("\t", 1)[0]
        if added.isdigit():
            lines[current] = lines.get(current, 0) + int(added)

    tests: dict[dt.date, int | None] = {}
    if test_command:
        for day in merges:
            sha = _git(repo, "log", branch, "--first-parent", "-1", "--pretty=%H",
                       "--until", _utc_midnight(day + dt.timedelta(days=1))).strip()
            if sha:
                tests[day] = test_count_at(repo, sha, test_command)

    out: list[DailyOutcome] = []
    day = since
    while day <= until:
        out.append(DailyOutcome(
            day=day,
            merges=merges.get(day, 0),
            commits=commits.get(day, 0),
            lines=lines.get(day, 0),
            tests=tests.get(day),
            unattributable=unattributable.get(day, 0),
        ))
        day += dt.timedelta(days=1)
    return out


_COLLECTED = re.compile(r"(\d+)\s+tests?\s+collected")


def test_count_at(repo: Path, sha: str, command: list[str]) -> int | None:
    """Collected test count at `sha`, via a throwaway detached worktree.

    The caller's working tree is never touched. Returns None if the worktree
    cannot be made or the command's output carries no collected count.
    """
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "wt"
        made = subprocess.run(
            ["git", "worktree", "add", "--detach", str(target), sha],
            cwd=repo, capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        if made.returncode != 0:
            return None
        try:
            result = subprocess.run(
                command, cwd=target, capture_output=True, text=True, encoding="utf-8", errors="replace"
            )
            match = _COLLECTED.search(result.stdout + result.stderr)
            return int(match.group(1)) if match else None
        finally:
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(target)],
                cwd=repo, capture_output=True, text=True, encoding="utf-8", errors="replace",
            )
