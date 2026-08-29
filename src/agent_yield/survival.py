"""What survived: shipped lines still present a fixed horizon later.

`git blame` already knows which commit a line in a tree came from, so survival
is a lookup rather than an estimate. Each day is measured at its own horizon,
never "as of today": measuring every day against the present would penalise an
old day for having had longer to erode, and the trend would move with the
calendar rather than with the work.

`_git` is defined here rather than imported from `outcomes`, because `outcomes`
imports this module and the other direction would be a cycle.
"""
from __future__ import annotations

import datetime as dt
import re
import subprocess
from collections.abc import Callable
from pathlib import Path

from .thresholds import SURVIVAL_HORIZON_DAYS

# A porcelain blame emits one header per source line: `<sha> <orig> <final>`,
# with a trailing group size on the first line of each group. Matching the
# three-field prefix therefore counts lines, not groups.
_BLAME_LINE = re.compile(r"^([0-9a-f]{40}) \d+ \d+")


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    return result.stdout if result.returncode == 0 else ""


def blame_counts(repo: Path, sha: str) -> dict[str, int]:
    """How many lines of the tree at `sha` each commit is still responsible for.

    `-w` so that a reindent does not transfer a surviving line to the day that
    reformatted it. Binary and unreadable paths blame to nothing and are
    skipped in silence, which is the same shape as `_git` returning "".
    """
    counts: dict[str, int] = {}
    for path in _git(repo, "ls-tree", "-r", "--name-only", sha).splitlines():
        if not path.strip():
            continue
        blamed = _git(repo, "blame", "--porcelain", "-w", sha, "--", path)
        for line in blamed.splitlines():
            match = _BLAME_LINE.match(line)
            if match:
                counts[match.group(1)] = counts.get(match.group(1), 0) + 1
    return counts


def _day_of(iso: str) -> dt.date | None:
    try:
        return dt.datetime.fromisoformat(iso).astimezone(dt.timezone.utc).date()
    except ValueError:
        return None


def surviving_by_day(
    repo: Path,
    branch: str,
    since: dt.date,
    until: dt.date,
    *,
    horizon_days: int = SURVIVAL_HORIZON_DAYS,
    asof: dt.datetime | None = None,
    is_local: Callable[[str], bool] | None = None,
) -> dict[dt.date, int | None]:
    """Lines each day wrote that were still present `horizon_days` later.

    None for a day whose horizon is still in the future: unmeasured, not empty.

    `is_local` scopes the count to one machine's commits. It must be passed
    whenever the numerator is one machine's tokens: dividing this machine's
    spend by both machines' surviving lines is #44's error on a new
    denominator, measured there at 25x on one day.

    Blame attributes a line to the commit that introduced it, which on a merged
    side branch is not a first-parent commit, while `outcomes.lines` counts
    first-parent only. On a linear history the two agree exactly. On a branchy
    one, survival can exceed insertions for a day, and that is a real limit of
    this measurement rather than a bug in it.
    """
    asof = asof or dt.datetime.now(dt.timezone.utc)
    sha_day: dict[str, dt.date] = {}
    for line in _git(repo, "log", branch, "--pretty=%H %cI").splitlines():
        sha, _, iso = line.strip().partition(" ")
        day = _day_of(iso)
        if day:
            sha_day[sha] = day

    blame_cache: dict[str, dict[str, int]] = {}
    out: dict[dt.date, int | None] = {}
    day = since
    while day <= until:
        horizon = dt.datetime.combine(
            day + dt.timedelta(days=horizon_days), dt.time.min, dt.timezone.utc)
        if horizon > asof:
            out[day] = None
            day += dt.timedelta(days=1)
            continue
        sha = _git(repo, "log", branch, "--first-parent", "-1", "--pretty=%H",
                   "--until", horizon.strftime("%Y-%m-%dT%H:%M:%S+00:00")).strip()
        if not sha:
            out[day] = None
            day += dt.timedelta(days=1)
            continue
        if sha not in blame_cache:
            blame_cache[sha] = blame_counts(repo, sha)
        out[day] = sum(
            count for origin, count in blame_cache[sha].items()
            if sha_day.get(origin) == day
            and (is_local is None or is_local(origin))
        )
        day += dt.timedelta(days=1)
    return out
