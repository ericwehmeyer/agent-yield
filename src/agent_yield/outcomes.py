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


@dataclass(frozen=True)
class DailyOutcome:
    day: dt.date
    merges: int = 0
    commits: int = 0
    lines: int = 0
    tests: int | None = None


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True
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
) -> list[DailyOutcome]:
    repo = Path(repo)
    branch = default_branch(repo)
    window = ["--since", _utc_midnight(since),
              "--until", _utc_midnight(until + dt.timedelta(days=1))]

    merges: dict[dt.date, int] = {}
    for line in _git(repo, "log", branch, "--merges", "--first-parent",
                     "--pretty=%cI", *window).splitlines():
        day = _day_of(line.strip())
        if day:
            merges[day] = merges.get(day, 0) + 1

    commits: dict[dt.date, int] = {}
    for line in _git(repo, "log", "--all", "--no-merges", "--pretty=%cI",
                     *window).splitlines():
        day = _day_of(line.strip())
        if day:
            commits[day] = commits.get(day, 0) + 1
    # Merge commits are commits too. `--no-merges` above kept the two walks
    # independent, so fold the merges back in rather than walking twice.
    for day, count in merges.items():
        commits[day] = commits.get(day, 0) + count

    lines: dict[dt.date, int] = {}
    current: dt.date | None = None
    for raw in _git(repo, "log", branch, "--first-parent", "--pretty=@%cI",
                    "--numstat", *window).splitlines():
        if raw.startswith("@"):
            current = _day_of(raw[1:].strip())
            continue
        if not raw.strip() or current is None:
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
            cwd=repo, capture_output=True, text=True,
        )
        if made.returncode != 0:
            return None
        try:
            result = subprocess.run(
                command, cwd=target, capture_output=True, text=True
            )
            match = _COLLECTED.search(result.stdout + result.stderr)
            return int(match.group(1)) if match else None
        finally:
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(target)],
                cwd=repo, capture_output=True, text=True,
            )
