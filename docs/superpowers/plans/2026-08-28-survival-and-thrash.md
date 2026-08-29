# Survival and Thrash Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the denominator count code that lasted, so a day of thrash stops
reading as a day of delivery.

**Architecture:** `git blame` at a fixed horizon after each day, aggregated by
the originating commit's day. Git already tracks which commit a surviving line
came from, so survival is a lookup and not an estimate. Each day is measured at
its OWN horizon (day + 7 days), never "as of today", so an old day is not
penalised for having had longer to erode.

**Tech Stack:** Python 3.11+, stdlib only, `subprocess` against `git`, pytest.

## Global Constraints

- The interpreter with pytest is `.venv/Scripts/python.exe`. Bare `python` has none.
- Whole suite: `.venv/Scripts/python.exe -m pytest -q`. One file: `.venv/Scripts/python.exe -m pytest tests/test_survival.py -q`.
- A test whose expectation is derived from the code under test proves nothing. Every expected number below is hand-counted from the fixture, never computed by calling the function under test.
- Unmeasurable is `None`, never `0`. A zero reads as "it was free".
- Vocabulary is fixed by `CONTEXT.md`: **survival**, **thrash**, **shipped**, **project**. Do not write `churn`, `rework`, or `retention`.
- No per-area survival metric (code/docs/other). `report.PerInsertion` records why: on the two measured days the code half moved 2.38x on a mix shift alone, and a threshold prediction against it would have printed PASS on a day nothing improved.
- One commit per task, staging **named paths**. Never `git add -A`.

---

### Task 1: Blame-based line counts at a sha

**Files:**
- Create: `src/agent_yield/survival.py`
- Modify: `src/agent_yield/thresholds.py` (append at end of file)
- Test: `tests/test_survival.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `blame_counts(repo: Path, sha: str) -> dict[str, int]`, mapping a
  commit sha to how many lines of the tree at `sha` that commit is still
  responsible for. `SURVIVAL_HORIZON_DAYS: int` in `thresholds`.

`survival.py` defines its own `_git` rather than importing `outcomes._git`.
Task 4 makes `outcomes` import `survival`, and reaching the other way would be
a cycle.

- [ ] **Step 1: Write the failing test**

Create `tests/test_survival.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_survival.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'agent_yield.survival'`

- [ ] **Step 3: Write minimal implementation**

Create `src/agent_yield/survival.py`:

```python
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
```

Append to `src/agent_yield/thresholds.py`:

```python
# CHOSEN, not measured. Seven days is long enough that a same-week rewrite
# lands inside it and short enough to score a day within the week it happened.
# Re-derive it once there is enough history to measure where survival actually
# flattens; until then it is a convention and is labelled one.
SURVIVAL_HORIZON_DAYS = 7
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_survival.py -q`
Expected: PASS, 1 passed

- [ ] **Step 5: Commit**

```bash
git add src/agent_yield/survival.py src/agent_yield/thresholds.py tests/test_survival.py
git commit -m "survival: blame at a sha credits each surviving line to the commit that wrote it"
```

---

### Task 2: Surviving lines per day, at each day's own horizon

**Files:**
- Modify: `src/agent_yield/survival.py`
- Test: `tests/test_survival.py`

**Interfaces:**
- Consumes: `blame_counts(repo, sha) -> dict[str, int]`, `SURVIVAL_HORIZON_DAYS`.
- Produces: `surviving_by_day(repo: Path, branch: str, since: dt.date, until: dt.date, *, horizon_days: int = SURVIVAL_HORIZON_DAYS, asof: dt.datetime | None = None, is_local: Callable[[str], bool] | None = None) -> dict[dt.date, int | None]`.
  `None` for a day whose horizon has not arrived. `is_local` defaults to
  counting every commit; Task 3 proves the seam.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_survival.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_survival.py -q`
Expected: FAIL, `ImportError: cannot import name 'surviving_by_day'`

- [ ] **Step 3: Write minimal implementation**

Replace the import block at the top of `src/agent_yield/survival.py` with:

```python
from __future__ import annotations

import datetime as dt
import re
import subprocess
from collections.abc import Callable
from pathlib import Path

from .thresholds import SURVIVAL_HORIZON_DAYS
```

Then append:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_survival.py -q`
Expected: PASS, 3 passed

- [ ] **Step 5: Commit**

```bash
git add src/agent_yield/survival.py tests/test_survival.py
git commit -m "survival: score each day at its own horizon, None before it arrives"
```

---

### Task 3: Count only this machine's surviving lines

**Files:**
- Modify: `src/agent_yield/survival.py` (the `surviving_by_day` docstring)
- Test: `tests/test_survival.py`

**Interfaces:**
- Consumes: `surviving_by_day(..., is_local=...)` from Task 2.
- Produces: no new symbol. This task proves the `is_local` seam holds, so Task 4
  can pass `attribution`'s verdict through it.

The defect this closes is #44's shape: dividing one machine's tokens by both
machines' commits was wrong by 25x on one day. An unattributed survival count
reintroduces it on the new denominator.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_survival.py`:

```python
def test_a_foreign_commits_surviving_lines_are_not_this_machines(repo):
    """Hand-counted: two commits on the same day, one of them foreign.

    Ten lines survive to the horizon and each commit wrote five. Scoped to the
    local one, the day scores 5, not 10.
    """
    local = _commit(repo, "a.txt", "".join(f"a{i}\n" for i in range(5)),
                    "2026-01-01T10:00:00+00:00")
    _commit(repo, "b.txt", "".join(f"b{i}\n" for i in range(5)),
            "2026-01-01T11:00:00+00:00")

    scoped = surviving_by_day(
        repo, "main", dt.date(2026, 1, 1), dt.date(2026, 1, 1),
        asof=dt.datetime(2026, 3, 1, tzinfo=dt.timezone.utc),
        is_local=lambda sha: sha == local,
    )
    unscoped = surviving_by_day(
        repo, "main", dt.date(2026, 1, 1), dt.date(2026, 1, 1),
        asof=dt.datetime(2026, 3, 1, tzinfo=dt.timezone.utc),
    )

    assert scoped[dt.date(2026, 1, 1)] == 5
    assert unscoped[dt.date(2026, 1, 1)] == 10
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_survival.py -q`
Expected: PASS if Task 2's seam is correct. That is the point of the task: the
seam now has a test that would catch its removal. Do not skip Step 3.

- [ ] **Step 3: State the contract in the docstring**

Replace the `surviving_by_day` docstring with:

```python
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
```

- [ ] **Step 4: Run the whole file**

Run: `.venv/Scripts/python.exe -m pytest tests/test_survival.py -q`
Expected: PASS, 4 passed

- [ ] **Step 5: Commit**

```bash
git add src/agent_yield/survival.py tests/test_survival.py
git commit -m "survival: scope the count to one machine, and state what blame cannot see"
```

---

### Task 4: Carry survival and thrash on the daily outcome

**Files:**
- Modify: `src/agent_yield/outcomes.py:20-37` (the `DailyOutcome` dataclass) and the `out.append(DailyOutcome(...))` block near line 240
- Test: `tests/test_outcomes.py`

**Interfaces:**
- Consumes: `surviving_by_day(...)` from Task 2.
- Produces: `DailyOutcome.surviving_lines: int | None` and
  `DailyOutcome.thrash: int | None` (a property). `daily_outcomes` gains a
  keyword-only `asof: dt.datetime | None = None`, passed through for tests.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_outcomes.py`:

```python
def test_thrash_is_what_a_day_wrote_and_did_not_keep():
    """Hand-counted: 10 lines written, 6 of them still there at the horizon."""
    outcome = DailyOutcome(
        day=dt.date(2026, 1, 1), lines=10, surviving_lines=6)
    assert outcome.thrash == 4


def test_thrash_is_none_while_survival_is_unmeasured():
    """A day inside the horizon has no thrash figure, and 0 would claim it had."""
    outcome = DailyOutcome(
        day=dt.date(2026, 1, 1), lines=10, surviving_lines=None)
    assert outcome.thrash is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_outcomes.py -k thrash -q`
Expected: FAIL, `TypeError: DailyOutcome.__init__() got an unexpected keyword argument 'surviving_lines'`

- [ ] **Step 3: Write minimal implementation**

In `src/agent_yield/outcomes.py`, add to the imports:

```python
from .survival import surviving_by_day
```

Add to `DailyOutcome`, after the `unattributable` field and its docstring:

```python
    surviving_lines: int | None = None
    """`lines` that were still present at this day's horizon. None until the
    horizon arrives: a day measured too early has not survived nothing."""

    @property
    def thrash(self) -> int | None:
        """Shipped code this day did not keep. None while survival is unmeasured."""
        if self.surviving_lines is None:
            return None
        return self.lines - self.surviving_lines
```

In `daily_outcomes`, add `asof: dt.datetime | None = None` as a keyword-only
parameter, and insert before the `out: list[DailyOutcome] = []` line:

```python
    surviving = surviving_by_day(
        repo, branch, since, until, asof=asof,
        is_local=(None if machine is None
                  else lambda sha: machine.label(sha) == LOCAL),
    )
```

Add to the `DailyOutcome(...)` call inside the loop:

```python
            surviving_lines=surviving.get(day),
```

- [ ] **Step 4: Run the tests**

Run: `.venv/Scripts/python.exe -m pytest tests/test_outcomes.py -q`
Expected: PASS, the existing tests plus the two new ones

- [ ] **Step 5: Commit**

```bash
git add src/agent_yield/outcomes.py tests/test_outcomes.py
git commit -m "outcomes: a day carries what it kept, and what it threw away"
```

---

### Task 5: Report tokens per surviving insertion, and make it scorable

**Files:**
- Modify: `src/agent_yield/report.py:165-230` (`YieldRow`) and the render block near line 545
- Modify: `src/agent_yield/interventions.py` (`SCORABLE_METRICS`)
- Test: `tests/test_report.py`

**Interfaces:**
- Consumes: `DailyOutcome.surviving_lines`, `DailyOutcome.thrash`.
- Produces: `YieldRow.surviving_lines: int | None`,
  `YieldRow.tokens_per_surviving_insertion -> float | None`, and the string
  `"tokens_per_surviving_insertion"` in `SCORABLE_METRICS`.

No per-area split. `PerInsertion`'s docstring records why a decomposable ratio
becomes a scorable metric that passes on a mix shift.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_report.py`:

```python
def test_tokens_per_surviving_insertion_divides_by_what_lasted():
    """Hand-counted: 1,000,000 tokens over 6 surviving of 10 written.

    Against insertions the day reads 100,000 per line. Against survival it
    reads 166,666.67, and the gap between them is the thrash.
    """
    row = YieldRow(
        day=dt.date(2026, 1, 1), mode="build",
        usage=Usage(input_tokens=1_000_000), calls=1,
        merges=0, commits=1, lines=10, surviving_lines=6,
    )
    assert row.tokens_per_insertion == pytest.approx(100_000.0)
    assert row.tokens_per_surviving_insertion == pytest.approx(1_000_000 / 6)


def test_tokens_per_surviving_insertion_is_none_before_the_horizon():
    row = YieldRow(
        day=dt.date(2026, 1, 1), mode="build",
        usage=Usage(input_tokens=1_000_000), calls=1,
        merges=0, commits=1, lines=10, surviving_lines=None,
    )
    assert row.tokens_per_surviving_insertion is None


def test_the_surviving_metric_is_scorable():
    """A prediction may name it, so the metric list and the row must not drift."""
    from agent_yield.interventions import SCORABLE_METRICS
    assert "tokens_per_surviving_insertion" in SCORABLE_METRICS
    assert hasattr(YieldRow, "tokens_per_surviving_insertion")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_report.py -k surviving -q`
Expected: FAIL, `TypeError: YieldRow.__init__() got an unexpected keyword argument 'surviving_lines'`

- [ ] **Step 3: Write minimal implementation**

In `src/agent_yield/report.py`, add to `YieldRow` after `other_lines`:

```python
    surviving_lines: int | None = None
```

Add the property beside `tokens_per_insertion`:

```python
    @property
    def tokens_per_surviving_insertion(self) -> float | None:
        """Tokens per inserted line that was still there at the horizon.

        The headline denominator. `tokens_per_insertion` counts a line written
        three times as three lines shipped, so a thrash day and a clean day of
        the same size read alike; this one does not. None, never zero, when
        survival is unmeasured or nothing survived.
        """
        if self.surviving_lines is None or self.surviving_lines <= 0:
            return None
        return self.usage.total / self.surviving_lines
```

Wherever a `YieldRow` is built from a `DailyOutcome`, pass
`surviving_lines=outcome.surviving_lines`.

In the render block near line 545, add the column beside the existing one:

```python
            f"{_fmt(row.tokens_per_surviving_insertion):>9}"
```

and add a matching header cell to the header string above it.

In `src/agent_yield/interventions.py`, add to `SCORABLE_METRICS`:

```python
    # Divides by what lasted. `tokens_per_insertion` stays, because the pair is
    # the thrash measurement: naming both is how a prediction claims it reduced
    # rewriting rather than typing.
    "tokens_per_surviving_insertion",
```

- [ ] **Step 4: Run the whole suite**

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: PASS, the full suite green

- [ ] **Step 5: Commit**

```bash
git add src/agent_yield/report.py src/agent_yield/interventions.py tests/test_report.py
git commit -m "report: divide spend by what lasted, and let a prediction name it"
```

---

## Out of scope, deliberately

- **Multi-project.** `cwd` is on all 20,757 records and `report.py` already
  filters calls by repo, but the denominator is still one repo's git. Its own
  plan.
- **Operator versus machine.** Attribution identifies a clone, not a person, so
  one person on two machines reads as two contributors. That is a modelling
  change, not a metric, and it blocks the team case rather than this one.
- **"Good" as survived-and-tested.** `DailyOutcome.tests` exists; joining it to
  survival is a third plan, and it should not land before survival has history.
- **Backfill of the 16 recorded predictions.** They were made against the old
  denominator. Rescoring them after the fact is exactly what that file exists to
  prevent.
