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
from .survival import surviving_by_day


@dataclass(frozen=True)
class DailyOutcome:
    day: dt.date
    merges: int = 0
    commits: int = 0
    lines: int = 0
    tests: int | None = None
    code_lines: int = 0
    docs_lines: int = 0
    other_lines: int = 0
    """`lines`, decomposed by what each changed file IS. The three always sum
    to `lines`: a split that does not add up is a second measurement of the
    same quantity, and `classify_path` has no fourth answer."""
    unattributable: int = 0
    """Commits this machine can neither claim nor disown -- older than its own
    reflog. Counted and reported, never folded into `commits`, because a commit
    that is not attributable is not thereby somebody else's (`attribution.py`).
    Always 0 when the caller did not ask for machine scoping."""

    surviving_lines: int | None = None
    """`lines` that were still present at this day's horizon. None until the
    horizon arrives: a day measured too early has not survived nothing."""

    @property
    def thrash(self) -> int | None:
        """Shipped code this day did not keep. None while survival is unmeasured."""
        if self.surviving_lines is None:
            return None
        return self.lines - self.surviving_lines


CODE_SUFFIXES = frozenset({
    ".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".go", ".rs", ".rb",
    ".c", ".h", ".cc", ".cpp", ".hpp", ".java", ".kt", ".swift", ".cs",
    ".sh", ".bash", ".zsh", ".ps1", ".sql", ".lua", ".pl", ".r",
})
DOCS_SUFFIXES = frozenset({".md", ".rst", ".txt", ".adoc"})


def classify_path(path: str) -> str:
    """Which of `code` / `docs` / `other` a changed file belongs to.

    Keyed on what the file IS, not on where this repo happens to put it.
    #46's plan pre-registered a hand count of 1,127 code / 2,931 docs for
    2026-08-25, and a `src/`+`tests/` versus `docs/` prefix rule reproduces it
    to the line. This rule differs by 94 -- README.md, which it calls
    documentation. It is documentation by any reading, and a prefix rule is a
    fact about one repo's layout rather than about its work. The code figure,
    the one both the plan and its review headline, reproduces either way.

    `other` is an honest bucket rather than a leftover one: config, lockfiles,
    fixtures and generated pages are neither of the two things this split
    exists to tell apart, and folding them into `code` would inflate the
    denominator the scorecard divides spend by.

    Paths arrive from `git --numstat`, which reports forward slashes on every
    platform, so there is no separator to normalise here.
    """
    parts = path.split("/")
    name = parts[-1]
    # `name[1:]`: a leading dot is not a suffix -- `.gitignore` is `other`,
    # not a file of type `.gitignore`.
    suffix = name[name.rindex("."):].lower() if "." in name[1:] else ""
    if suffix in CODE_SUFFIXES:
        return "code"
    if suffix in DOCS_SUFFIXES:
        return "docs"
    # Extensionless under a docs directory is prose; extensionless anywhere
    # else is not. LICENSE is not documentation of the work.
    if not suffix and "docs" in parts[:-1]:
        return "docs"
    return "other"


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
    *,
    asof: dt.datetime | None = None,
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
    areas: dict[tuple[dt.date, str], int] = {}
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
        added, _, rest = raw.partition("\t")
        if added.isdigit():
            lines[current] = lines.get(current, 0) + int(added)
            # The same field of the same line of the same walk that produced
            # the total, so the split is a decomposition of that number and
            # not a rival measurement of it (#46 review, finding 3).
            key = (current, classify_path(rest.partition("\t")[2]))
            areas[key] = areas.get(key, 0) + int(added)

    tests: dict[dt.date, int | None] = {}
    if test_command:
        for day in merges:
            sha = _git(repo, "log", branch, "--first-parent", "-1", "--pretty=%H",
                       "--until", _utc_midnight(day + dt.timedelta(days=1))).strip()
            if sha:
                tests[day] = test_count_at(repo, sha, test_command)

    # Blame hands back bare shas, while `Machine.label` needs the commit time to
    # tell FOREIGN from UNKNOWN, so the shas have to be dated before they can be
    # scoped. Whole history rather than `window`: a line surviving into this
    # range may well have been written before it, and dating only the range
    # would label every such origin UNKNOWN and drop it.
    sha_when: dict[str, dt.datetime | None] = {}
    if machine is not None:
        for line in _git(repo, "log", branch, "--pretty=%H %cI").splitlines():
            sha, iso = _split(line)
            sha_when[sha] = _when(iso)

    surviving = surviving_by_day(
        repo, branch, since, until, asof=asof,
        is_local=(None if machine is None
                  else lambda sha: machine.label(sha, sha_when.get(sha)) == LOCAL),
    )

    out: list[DailyOutcome] = []
    day = since
    while day <= until:
        out.append(DailyOutcome(
            day=day,
            merges=merges.get(day, 0),
            commits=commits.get(day, 0),
            lines=lines.get(day, 0),
            code_lines=areas.get((day, "code"), 0),
            docs_lines=areas.get((day, "docs"), 0),
            other_lines=areas.get((day, "other"), 0),
            tests=tests.get(day),
            unattributable=unattributable.get(day, 0),
            surviving_lines=surviving.get(day),
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
