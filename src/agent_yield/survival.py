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

import re
import subprocess
from pathlib import Path

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
