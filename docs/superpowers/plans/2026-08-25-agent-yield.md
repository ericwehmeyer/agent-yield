# agent-yield Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the CLI that joins agent token consumption to git delivery outcomes, marks process changes on that timeline, and reports whether they worked.

**Architecture:** A stdlib-only Python package. `transcripts` parses Claude Code JSONL into a normalized `CallRecord` stream and persists it (subagent transcripts live in the OS temp dir and are volatile). `outcomes` shells out to read-only `git`. `interventions` and `session-modes` are operator-authored TOML. `report` joins them. `predict` and `gate` are thin consumers of the same model. Every layer keeps the four usage fields separate — collapsing them is the exact error this tool exists to prevent.

**Tech Stack:** Python 3.11+ (`tomllib` is stdlib from 3.11), `pytest`, `git`. No runtime third-party dependencies.

## Global Constraints

Copied verbatim from `docs/design.md`. Every task's requirements implicitly include this section.

- **Sum the four usage fields separately** (input, output, cache-write, cache-read). "They are priced differently and collapsing them is precisely how the 80× error happened." (§4.1)
- **It does not price anything. It reports tokens.** No rates, no currency, anywhere in the codebase. "a tool that hardcodes them lies quietly later." (§6)
- **It does not attribute cost to a person.** The unit is the repository and the session. (§6)
- **A mode tag is a claim about the work and must be recorded by the operator, not inferred**, "because a tool that guesses the denominator's meaning will guess flatteringly." (§3)
- **`expect` is required on every intervention.** "An intervention recorded without a prediction is not an experiment." (§4.3)
- **`outcomes` is read-only:** no network, no history rewriting. (§4.2)
- **Never report one global yield ratio across modes.** That is the class of error the case study documents. (§3)
- Thresholds are **provisional**, live in one module, and are labelled as such. (§5)

## Reference constants (from `docs/case-study.md`)

These are load-bearing test fixtures, not decoration.

```
2026-08-24:  calls 6,910   output 4,034,858   cache-write 23,248,272
             cache-read 942,865,149           uncached input 13,816
             day total  970,162,095           cache-read share 97.4%
             cache-read / calls = 136,449 tokens per call

2026-08-25 (to 06:18):  calls 5,333  cache-read 724,985,381
             cache-read / calls = 135,943 tokens per call

77 subagent transcripts: total 1,190,554,043 / median 12,385,765 / max 68,475,554
Subagents are 70% of all consumption. Dispatch call-count spread: 62 -> 188, median 69.5.
```

## Transcript facts (verified 2026-08-25 against this machine)

- **Main sessions:** `~/.claude/projects/<project-slug>/<session-id>.jsonl`, records carry `"isSidechain": false`.
- **Subagents:** `<temp>/claude/<project-slug>/<session-id>/tasks/<agentId>.output`, JSONL, records carry `"isSidechain": true` plus `agentId` and `attributionAgent`. **This is under the OS temp directory and is volatile** — 352 such files existed, of which only 103 were non-empty and many were zero bytes. This is why Task 3 persists an ingest.
- **Usage payload** lives at `record["message"]["usage"]` with keys `input_tokens`, `output_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens`. A nested `usage["iterations"]` list repeats the same numbers per iteration — **it must not be summed on top of the top-level fields.**
- **Identity:** `record["requestId"]` and `record["message"]["id"]`. `timestamp` is ISO-8601 UTC with a `Z` suffix.

## File Structure

| File | Responsibility |
|---|---|
| `pyproject.toml` | Package metadata, pytest config, console script |
| `src/agent_yield/usage.py` | `Usage` value type — the four fields, kept apart |
| `src/agent_yield/records.py` | `CallRecord` + JSONL line -> record parsing |
| `src/agent_yield/discovery.py` | Where transcripts live; main vs subagent roots |
| `src/agent_yield/ingest.py` | Walk, dedup, persist to `.agent-yield/calls.jsonl` |
| `src/agent_yield/outcomes.py` | Read-only git: merges, commits, lines, test count |
| `src/agent_yield/interventions.py` | `interventions.toml` load + validation |
| `src/agent_yield/modes.py` | `session-modes.toml` load; untagged stays untagged |
| `src/agent_yield/thresholds.py` | §5 numbers in one place, labelled provisional |
| `src/agent_yield/report.py` | The join, per mode, with intervention before/after |
| `src/agent_yield/predict.py` | Pre-dispatch projection with its spread |
| `src/agent_yield/gate.py` | `PreToolUse` hook entry point (warn bands) |
| `src/agent_yield/cli.py` | argparse subcommands |
| `tests/` | Mirrors the above, one test module per source module |

---

### Task 1: Package skeleton and the `Usage` type

The four-field separation is the tool's whole thesis, so it is the first thing built and the first thing tested.

**Files:**
- Create: `pyproject.toml`
- Create: `src/agent_yield/__init__.py`
- Create: `src/agent_yield/usage.py`
- Test: `tests/test_usage.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `Usage(input_tokens: int, output_tokens: int, cache_creation_tokens: int, cache_read_tokens: int)`, frozen dataclass; `Usage.total -> int`; `Usage.cache_read_share -> float`; `Usage.from_payload(payload: dict) -> Usage`; `Usage.__add__`; `Usage.zero() -> Usage`.

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=61"]
build-backend = "setuptools.build_meta"

[project]
name = "agent-yield"
version = "0.1.0"
description = "Join agent token consumption to delivery outcomes."
requires-python = ">=3.11"
dependencies = []

[project.scripts]
agent-yield = "agent_yield.cli:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q"
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_usage.py`:

```python
from agent_yield.usage import Usage

# The 2026-08-24 column from docs/case-study.md. These four numbers sum to the
# recorded day total exactly, which is why this is a regression fixture and not
# an illustration.
AUG_24 = Usage(
    input_tokens=13_816,
    output_tokens=4_034_858,
    cache_creation_tokens=23_248_272,
    cache_read_tokens=942_865_149,
)


def test_total_matches_recorded_day_total():
    assert AUG_24.total == 970_162_095


def test_cache_read_share_is_97_percent():
    assert round(AUG_24.cache_read_share * 100, 1) == 97.4


def test_fields_stay_separate_under_addition():
    doubled = AUG_24 + AUG_24
    assert doubled.cache_read_tokens == 1_885_730_298
    assert doubled.output_tokens == 8_069_716


def test_from_payload_reads_the_real_field_names():
    payload = {
        "input_tokens": 2,
        "output_tokens": 121,
        "cache_creation_input_tokens": 15_711,
        "cache_read_input_tokens": 31_316,
        # A real payload nests an `iterations` list repeating the same numbers.
        # Summing it on top of the top-level fields double-counts.
        "iterations": [{"input_tokens": 2, "output_tokens": 121}],
    }
    assert Usage.from_payload(payload) == Usage(2, 121, 15_711, 31_316)


def test_from_payload_tolerates_missing_fields():
    assert Usage.from_payload({}) == Usage.zero()
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/test_usage.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'agent_yield.usage'`

- [ ] **Step 4: Write minimal implementation**

Create `src/agent_yield/__init__.py` (empty file) and `src/agent_yield/usage.py`:

```python
"""The four usage fields, kept apart.

Collapsing these is how a careful metrics file came to be wrong by ~80x:
`subagent_tokens` counts output and uncached input, and cache reads are 97.4%
of what is actually consumed. Every total in this tool is built from a `Usage`
so that the four numbers stay visible all the way to the report.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0

    @classmethod
    def zero(cls) -> "Usage":
        return cls()

    @classmethod
    def from_payload(cls, payload: dict) -> "Usage":
        # Top-level fields only. `payload["iterations"]` repeats these numbers
        # per inference iteration; adding it would double-count.
        def field(name: str) -> int:
            value = payload.get(name, 0)
            return value if isinstance(value, int) else 0

        return cls(
            input_tokens=field("input_tokens"),
            output_tokens=field("output_tokens"),
            cache_creation_tokens=field("cache_creation_input_tokens"),
            cache_read_tokens=field("cache_read_input_tokens"),
        )

    @property
    def total(self) -> int:
        return (
            self.input_tokens
            + self.output_tokens
            + self.cache_creation_tokens
            + self.cache_read_tokens
        )

    @property
    def cache_read_share(self) -> float:
        return self.cache_read_tokens / self.total if self.total else 0.0

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(
            self.input_tokens + other.input_tokens,
            self.output_tokens + other.output_tokens,
            self.cache_creation_tokens + other.cache_creation_tokens,
            self.cache_read_tokens + other.cache_read_tokens,
        )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pip install -e . && python -m pytest tests/test_usage.py -v`
Expected: PASS, 5 passed

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml src/agent_yield/__init__.py src/agent_yield/usage.py tests/test_usage.py
git commit -m "usage: keep the four token fields apart, with the 08-24 column as the fixture"
```

---

### Task 2: `CallRecord` — parsing one transcript line

**Files:**
- Create: `src/agent_yield/records.py`
- Test: `tests/test_records.py`

**Interfaces:**
- Consumes: `Usage`, `Usage.from_payload` (Task 1).
- Produces: `CallRecord(timestamp: datetime, usage: Usage, session_id: str | None, agent_id: str | None, request_id: str | None, message_id: str | None, model: str | None, is_subagent: bool, cwd: str | None)`; `CallRecord.day -> date`; `CallRecord.dedup_key -> tuple[str, str] | None`; `parse_line(line: str) -> CallRecord | None`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_records.py`:

```python
import datetime as dt
import json

from agent_yield.records import parse_line
from agent_yield.usage import Usage

# Field-for-field the shape of a real main-session transcript line, 2026-08-25.
MAIN_LINE = json.dumps({
    "parentUuid": "fcf14bca",
    "isSidechain": False,
    "type": "assistant",
    "requestId": "req_011CePM2BZLuuNrHSYzzX6Ck",
    "timestamp": "2026-08-25T10:56:36.286Z",
    "sessionId": "588b0593",
    "cwd": "C:\\Users\\ewehm\\repos\\agent-yield",
    "message": {
        "model": "claude-opus-5",
        "id": "msg_011CePM2CMU3jxtNi68Djy5L",
        "role": "assistant",
        "usage": {
            "input_tokens": 2,
            "cache_creation_input_tokens": 15711,
            "cache_read_input_tokens": 31316,
            "output_tokens": 121,
        },
    },
})

# The shape of a real subagent `.output` line.
SUBAGENT_LINE = json.dumps({
    "isSidechain": True,
    "agentId": "a21d33bb9cc0571cc",
    "type": "assistant",
    "requestId": "req_sub_1",
    "timestamp": "2026-08-25T11:02:00.000Z",
    "sessionId": "588b0593",
    "message": {
        "model": "claude-opus-5",
        "id": "msg_sub_1",
        "usage": {
            "input_tokens": 2,
            "output_tokens": 6,
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 30025,
        },
    },
})


def test_parses_a_main_session_line():
    record = parse_line(MAIN_LINE)
    assert record.usage == Usage(2, 121, 15_711, 31_316)
    assert record.is_subagent is False
    assert record.session_id == "588b0593"
    assert record.model == "claude-opus-5"


def test_timestamp_is_timezone_aware_utc():
    record = parse_line(MAIN_LINE)
    assert record.timestamp.utcoffset() == dt.timedelta(0)
    assert record.day == dt.date(2026, 8, 25)


def test_subagent_line_is_marked_as_subagent():
    record = parse_line(SUBAGENT_LINE)
    assert record.is_subagent is True
    assert record.agent_id == "a21d33bb9cc0571cc"


def test_dedup_key_pairs_message_and_request():
    assert parse_line(MAIN_LINE).dedup_key == (
        "msg_011CePM2CMU3jxtNi68Djy5L",
        "req_011CePM2BZLuuNrHSYzzX6Ck",
    )


def test_dedup_key_is_none_when_either_id_is_missing():
    line = json.dumps({
        "type": "assistant",
        "timestamp": "2026-08-25T11:00:00.000Z",
        "message": {"usage": {"output_tokens": 5}},
    })
    assert parse_line(line).dedup_key is None


def test_non_usage_lines_are_skipped():
    assert parse_line('{"type":"mode","mode":"normal"}') is None
    assert parse_line("") is None
    assert parse_line("not json at all") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_records.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'agent_yield.records'`

- [ ] **Step 3: Write minimal implementation**

Create `src/agent_yield/records.py`:

```python
"""One normalized record per API call, from either kind of transcript."""
from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass

from .usage import Usage


@dataclass(frozen=True)
class CallRecord:
    timestamp: dt.datetime
    usage: Usage
    session_id: str | None = None
    agent_id: str | None = None
    request_id: str | None = None
    message_id: str | None = None
    model: str | None = None
    is_subagent: bool = False
    cwd: str | None = None

    @property
    def day(self) -> dt.date:
        # Bucketed in UTC. Transcript timestamps are UTC with a `Z` suffix, and
        # a local-time bucket would silently move calls between days depending
        # on where the report is run.
        return self.timestamp.date()

    @property
    def dedup_key(self) -> tuple[str, str] | None:
        # Only a complete pair identifies a call. With either half missing the
        # record is counted rather than dropped -- under-counting is the error
        # this tool exists to prevent.
        if self.message_id and self.request_id:
            return (self.message_id, self.request_id)
        return None


def _timestamp(raw: str | None) -> dt.datetime | None:
    if not raw:
        return None
    try:
        parsed = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def parse_line(line: str) -> CallRecord | None:
    """Return a record, or None for any line that is not a billable call."""
    line = line.strip()
    if not line:
        return None
    try:
        payload = json.loads(line)
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None

    message = payload.get("message")
    if not isinstance(message, dict):
        return None
    usage_payload = message.get("usage")
    if not isinstance(usage_payload, dict):
        return None

    timestamp = _timestamp(payload.get("timestamp"))
    if timestamp is None:
        return None

    return CallRecord(
        timestamp=timestamp,
        usage=Usage.from_payload(usage_payload),
        session_id=payload.get("sessionId"),
        agent_id=payload.get("agentId"),
        request_id=payload.get("requestId"),
        message_id=message.get("id"),
        model=message.get("model"),
        is_subagent=bool(payload.get("isSidechain")),
        cwd=payload.get("cwd"),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_records.py -v`
Expected: PASS, 6 passed

- [ ] **Step 5: Commit**

```bash
git add src/agent_yield/records.py tests/test_records.py
git commit -m "records: normalize a transcript line into one call, main or subagent"
```

---

### Task 3: Discovery and ingest, with the case-study regression

This is §8 step 2, and it carries the acceptance test the design names: the tool must reproduce **136K context-per-call** and the **12.4M median agent** or it is wrong.

Ingest persists because subagent transcripts live in the OS temp directory. **This is an addition to §8 step 2, made deliberately:** of 352 `.output` files on this machine, 249 were already empty. A tool that reads that directory live will silently report a shrinking history.

**Files:**
- Create: `src/agent_yield/discovery.py`
- Create: `src/agent_yield/ingest.py`
- Test: `tests/test_ingest.py`

**Interfaces:**
- Consumes: `CallRecord`, `parse_line` (Task 2), `Usage` (Task 1).
- Produces: `main_transcript_dir() -> Path`; `subagent_transcript_dir() -> Path`; `default_roots() -> list[Path]`; `find_transcripts(roots: list[Path]) -> list[Path]`; `load_records(paths) -> list[CallRecord]` (deduped); `total_usage(records) -> Usage`; `context_per_call(records) -> float`; `agent_totals(records) -> dict[str, int]`; `median_agent_total(records) -> int`; `ingest(dest: Path, roots) -> int`; `load_ingested(path: Path) -> list[CallRecord]`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_ingest.py`:

```python
import json

from agent_yield.ingest import (
    context_per_call,
    ingest,
    load_ingested,
    load_records,
    median_agent_total,
)


def _line(**kw):
    """Build a transcript line in the verified real shape."""
    return json.dumps({
        "type": "assistant",
        "timestamp": kw.get("ts", "2026-08-24T12:00:00.000Z"),
        "sessionId": kw.get("session", "s1"),
        "isSidechain": kw.get("sub", False),
        "agentId": kw.get("agent"),
        "requestId": kw["req"],
        "message": {
            "id": kw["msg"],
            "model": "claude-opus-5",
            "usage": {
                "input_tokens": kw.get("inp", 0),
                "output_tokens": kw.get("out", 0),
                "cache_creation_input_tokens": kw.get("cw", 0),
                "cache_read_input_tokens": kw.get("cr", 0),
            },
        },
    })


def test_duplicate_message_and_request_pairs_are_counted_once(tmp_path):
    path = tmp_path / "s.jsonl"
    path.write_text(
        _line(req="r1", msg="m1", cr=100) + "\n"
        + _line(req="r1", msg="m1", cr=100) + "\n",
        encoding="utf-8",
    )
    assert len(load_records([path])) == 1


def test_records_without_ids_are_kept_not_dropped(tmp_path):
    path = tmp_path / "s.jsonl"
    line = json.dumps({
        "type": "assistant", "timestamp": "2026-08-24T12:00:00.000Z",
        "message": {"usage": {"cache_read_input_tokens": 50}},
    })
    path.write_text(line + "\n" + line + "\n", encoding="utf-8")
    assert len(load_records([path])) == 2


def test_empty_and_corrupt_files_do_not_abort_the_walk(tmp_path):
    (tmp_path / "empty.output").write_text("", encoding="utf-8")
    (tmp_path / "junk.output").write_text("{not json\n", encoding="utf-8")
    good = tmp_path / "good.jsonl"
    good.write_text(_line(req="r1", msg="m1", cr=7) + "\n", encoding="utf-8")
    records = load_records(
        [tmp_path / "empty.output", tmp_path / "junk.output", good]
    )
    assert len(records) == 1


def test_reproduces_the_case_study_context_per_call(tmp_path):
    """docs/case-study.md 2026-08-24: 942,865,149 cache-read over 6,910 calls."""
    path = tmp_path / "s.jsonl"
    per_call = 942_865_149 // 6_910
    remainder = 942_865_149 - per_call * 6_910
    lines = [
        _line(req=f"r{i}", msg=f"m{i}", cr=per_call + (remainder if i == 0 else 0))
        for i in range(6_910)
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    records = load_records([path])
    assert len(records) == 6_910
    assert round(context_per_call(records)) == 136_449


def test_reproduces_the_case_study_median_agent(tmp_path):
    """docs/case-study.md: 77 subagents, median 12,385,765."""
    path = tmp_path / "subs.jsonl"
    totals = ([1_000_000] * 38) + [12_385_765] + ([68_475_554] * 38)
    lines = [
        _line(req=f"r{i}", msg=f"m{i}", sub=True, agent=f"a{i}", cr=total)
        for i, total in enumerate(totals)
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    records = load_records([path])
    assert median_agent_total(records) == 12_385_765


def test_ingest_persists_and_reloads_identically(tmp_path):
    src = tmp_path / "s.jsonl"
    src.write_text(_line(req="r1", msg="m1", cr=5, out=2), encoding="utf-8")
    dest = tmp_path / ".agent-yield" / "calls.jsonl"
    assert ingest(dest, [src]) == 1
    reloaded = load_ingested(dest)
    assert reloaded[0].usage.cache_read_tokens == 5
    assert reloaded[0].usage.output_tokens == 2


def test_ingest_is_idempotent_across_runs(tmp_path):
    src = tmp_path / "s.jsonl"
    src.write_text(_line(req="r1", msg="m1", cr=5), encoding="utf-8")
    dest = tmp_path / ".agent-yield" / "calls.jsonl"
    ingest(dest, [src])
    ingest(dest, [src])
    assert len(load_ingested(dest)) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ingest.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'agent_yield.ingest'`

- [ ] **Step 3: Write `discovery.py`**

```python
"""Where transcripts live.

Two locations, verified 2026-08-25:

  main sessions  ~/.claude/projects/<project-slug>/<session-id>.jsonl
  subagents      <temp>/claude/<project-slug>/<session-id>/tasks/<agentId>.output

The second is under the OS temp directory and is volatile -- on the machine
this was verified against, 249 of 352 such files were already empty. Read it
early and persist what you find.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path


def main_transcript_dir() -> Path:
    override = os.environ.get("CLAUDE_CONFIG_DIR")
    base = Path(override) if override else Path.home() / ".claude"
    return base / "projects"


def subagent_transcript_dir() -> Path:
    return Path(tempfile.gettempdir()) / "claude"


def find_transcripts(roots: list[Path]) -> list[Path]:
    """Every transcript file under the given roots, in a stable order."""
    found: list[Path] = []
    for root in roots:
        root = Path(root)
        if not root.exists():
            continue
        if root.is_file():
            found.append(root)
            continue
        found.extend(root.rglob("*.jsonl"))
        found.extend(root.rglob("*.output"))
    return sorted(set(found))


def default_roots() -> list[Path]:
    return [main_transcript_dir(), subagent_transcript_dir()]
```

- [ ] **Step 4: Write `ingest.py`**

```python
"""Walk transcripts, dedup calls, persist a normalized copy."""
from __future__ import annotations

import datetime as dt
import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Iterable

from .discovery import find_transcripts
from .records import CallRecord, parse_line
from .usage import Usage


def load_records(paths: Iterable[Path]) -> list[CallRecord]:
    """Every billable call under `paths`, each counted once.

    A file that is empty, unreadable, or full of junk contributes nothing and
    does not abort the walk: subagent transcripts are routinely zero bytes.
    """
    records: list[CallRecord] = []
    seen: set[tuple[str, str]] = set()
    for path in paths:
        try:
            text = Path(path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            record = parse_line(line)
            if record is None:
                continue
            key = record.dedup_key
            if key is not None:
                if key in seen:
                    continue
                seen.add(key)
            records.append(record)
    return records


def total_usage(records: Iterable[CallRecord]) -> Usage:
    total = Usage.zero()
    for record in records:
        total = total + record.usage
    return total


def context_per_call(records: Iterable[CallRecord]) -> float:
    """Cache-read tokens per API call -- the ~136K constant.

    Cache read, not total: this measures how much context is re-read on every
    call, which is the quantity the cost model multiplies by.
    """
    records = list(records)
    if not records:
        return 0.0
    return total_usage(records).cache_read_tokens / len(records)


def agent_totals(records: Iterable[CallRecord]) -> dict[str, int]:
    totals: dict[str, int] = defaultdict(int)
    for record in records:
        if record.is_subagent and record.agent_id:
            totals[record.agent_id] += record.usage.total
    return dict(totals)


def median_agent_total(records: Iterable[CallRecord]) -> int:
    totals = agent_totals(records)
    if not totals:
        return 0
    return int(statistics.median(sorted(totals.values())))


def _to_json(record: CallRecord) -> str:
    return json.dumps({
        "timestamp": record.timestamp.isoformat(),
        "session_id": record.session_id,
        "agent_id": record.agent_id,
        "request_id": record.request_id,
        "message_id": record.message_id,
        "model": record.model,
        "is_subagent": record.is_subagent,
        "cwd": record.cwd,
        "usage": {
            "input_tokens": record.usage.input_tokens,
            "output_tokens": record.usage.output_tokens,
            "cache_creation_input_tokens": record.usage.cache_creation_tokens,
            "cache_read_input_tokens": record.usage.cache_read_tokens,
        },
    })


def load_ingested(path: Path) -> list[CallRecord]:
    path = Path(path)
    if not path.exists():
        return []
    records: list[CallRecord] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        raw = json.loads(line)
        records.append(CallRecord(
            timestamp=dt.datetime.fromisoformat(raw["timestamp"]),
            usage=Usage.from_payload(raw["usage"]),
            session_id=raw.get("session_id"),
            agent_id=raw.get("agent_id"),
            request_id=raw.get("request_id"),
            message_id=raw.get("message_id"),
            model=raw.get("model"),
            is_subagent=raw.get("is_subagent", False),
            cwd=raw.get("cwd"),
        ))
    return records


def ingest(dest: Path, roots: Iterable[Path]) -> int:
    """Merge newly-found calls into `dest`. Returns the total count held."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)

    merged = load_ingested(dest) + load_records(find_transcripts(list(roots)))

    deduped: list[CallRecord] = []
    seen: set[tuple[str, str]] = set()
    for record in merged:
        key = record.dedup_key
        if key is not None:
            if key in seen:
                continue
            seen.add(key)
        deduped.append(record)

    deduped.sort(key=lambda r: r.timestamp)
    dest.write_text(
        "\n".join(_to_json(r) for r in deduped) + "\n", encoding="utf-8"
    )
    return len(deduped)
```

Note: records that carry no `dedup_key` are appended on every run by design in `load_records`, but `ingest` would re-add them each time it merges. Guard that in Step 5 if `test_ingest_is_idempotent_across_runs` reveals it — the fixture there uses a keyed record, so extend the test with an unkeyed one and make `ingest` skip unkeyed records already present by `(timestamp, usage.total)`.

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_ingest.py -v`
Expected: PASS, 7 passed. If `test_reproduces_the_case_study_context_per_call` fails, **the parser is wrong — do not adjust the expected number.**

- [ ] **Step 6: Commit**

```bash
git add src/agent_yield/discovery.py src/agent_yield/ingest.py tests/test_ingest.py
git commit -m "ingest: dedup and persist calls; case-study figures as the regression gate"
```

---

### Task 4: `outcomes` — the git denominator

**Files:**
- Create: `src/agent_yield/outcomes.py`
- Test: `tests/test_outcomes.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `DailyOutcome(day: date, merges: int, commits: int, lines: int, tests: int | None)`; `default_branch(repo: Path) -> str`; `daily_outcomes(repo: Path, since: date, until: date, test_command: list[str] | None = None) -> list[DailyOutcome]`; `test_count_at(repo: Path, sha: str, command: list[str]) -> int | None`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_outcomes.py`:

```python
import datetime as dt
import os
import subprocess
from pathlib import Path

import pytest

from agent_yield.outcomes import DailyOutcome, daily_outcomes, default_branch

WHEN = "2026-08-24T12:00:00+00:00"


def _git(cwd: Path, *args: str, **env_extra: str) -> None:
    env = {
        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@e",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@e",
        "PATH": os.environ["PATH"],
        **env_extra,
    }
    subprocess.run(
        ["git", *args], cwd=cwd, env=env, capture_output=True, text=True, check=True
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    work = tmp_path / "r"
    work.mkdir()
    _git(work, "init", "-b", "main")
    (work / "a.txt").write_text("one\ntwo\n", encoding="utf-8")
    _git(work, "add", "a.txt")
    _git(work, "commit", "-m", "first",
         GIT_AUTHOR_DATE=WHEN, GIT_COMMITTER_DATE=WHEN)
    _git(work, "checkout", "-b", "feature")
    (work / "b.txt").write_text("three\n", encoding="utf-8")
    _git(work, "add", "b.txt")
    _git(work, "commit", "-m", "second",
         GIT_AUTHOR_DATE=WHEN, GIT_COMMITTER_DATE=WHEN)
    _git(work, "checkout", "main")
    _git(work, "merge", "--no-ff", "feature", "-m", "merge feature",
         GIT_AUTHOR_DATE=WHEN, GIT_COMMITTER_DATE=WHEN)
    return work


def test_default_branch_falls_back_to_main(repo):
    assert default_branch(repo) == "main"


def test_counts_one_merge_on_the_default_branch(repo):
    day = dt.date(2026, 8, 24)
    outcomes = {o.day: o for o in daily_outcomes(repo, day, day)}
    assert outcomes[day].merges == 1


def test_counts_all_commits_across_branches(repo):
    day = dt.date(2026, 8, 24)
    outcomes = {o.day: o for o in daily_outcomes(repo, day, day)}
    # two ordinary commits plus the merge commit
    assert outcomes[day].commits == 3


def test_counts_net_insertions(repo):
    day = dt.date(2026, 8, 24)
    outcomes = {o.day: o for o in daily_outcomes(repo, day, day)}
    assert outcomes[day].lines == 3


def test_days_with_no_activity_are_present_and_zero(repo):
    outcomes = {
        o.day: o for o in
        daily_outcomes(repo, dt.date(2026, 8, 23), dt.date(2026, 8, 25))
    }
    assert outcomes[dt.date(2026, 8, 23)] == DailyOutcome(
        day=dt.date(2026, 8, 23), merges=0, commits=0, lines=0, tests=None
    )


def test_test_count_is_none_when_no_command_given(repo):
    day = dt.date(2026, 8, 24)
    outcomes = {o.day: o for o in daily_outcomes(repo, day, day)}
    assert outcomes[day].tests is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_outcomes.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'agent_yield.outcomes'`

- [ ] **Step 3: Write minimal implementation**

Create `src/agent_yield/outcomes.py`:

```python
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


def daily_outcomes(
    repo: Path,
    since: dt.date,
    until: dt.date,
    test_command: list[str] | None = None,
) -> list[DailyOutcome]:
    repo = Path(repo)
    branch = default_branch(repo)
    window = ["--since", since.isoformat(),
              "--until", (until + dt.timedelta(days=1)).isoformat()]

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
                       "--until", (day + dt.timedelta(days=1)).isoformat()).strip()
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
```

Rename note: `test_count_at` starts with `test_`, which pytest will try to collect from any module it imports. It lives in `src/`, not `tests/`, so collection does not reach it — but if a future test module does `from agent_yield.outcomes import *`, rename it to `collected_tests_at`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_outcomes.py -v`
Expected: PASS, 6 passed

- [ ] **Step 5: Commit**

```bash
git add src/agent_yield/outcomes.py tests/test_outcomes.py
git commit -m "outcomes: read-only git denominators, one row per day in range"
```

---

### Task 5: `interventions` and `session-modes` — the operator's claims

Both files are operator-authored and committed. Neither is ever inferred.

**Files:**
- Create: `src/agent_yield/interventions.py`
- Create: `src/agent_yield/modes.py`
- Test: `tests/test_interventions.py`
- Test: `tests/test_modes.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `Intervention(date: date, name: str, expect: str)`; `InterventionError`; `load_interventions(path: Path) -> list[Intervention]`; `VALID_MODES: frozenset[str]`; `UNTAGGED: str`; `ModeError`; `load_modes(path: Path) -> dict[str, str]`; `mode_for(session_id: str | None, modes: dict[str, str]) -> str`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_interventions.py`:

```python
import datetime as dt

import pytest

from agent_yield.interventions import (
    Intervention,
    InterventionError,
    load_interventions,
)

GOOD = '''
[[intervention]]
date = "2026-08-25"
name = "brief-pack: agents stop rediscovering the repo"
expect = "per-agent median falls from 12.4M"
'''


def test_loads_a_well_formed_intervention(tmp_path):
    path = tmp_path / "interventions.toml"
    path.write_text(GOOD, encoding="utf-8")
    assert load_interventions(path) == [Intervention(
        date=dt.date(2026, 8, 25),
        name="brief-pack: agents stop rediscovering the repo",
        expect="per-agent median falls from 12.4M",
    )]


def test_missing_expect_is_rejected_loudly(tmp_path):
    path = tmp_path / "interventions.toml"
    path.write_text(
        '[[intervention]]\ndate = "2026-08-25"\nname = "x"\n', encoding="utf-8"
    )
    with pytest.raises(InterventionError, match="expect"):
        load_interventions(path)


def test_whitespace_only_expect_is_rejected(tmp_path):
    path = tmp_path / "interventions.toml"
    path.write_text(
        '[[intervention]]\ndate = "2026-08-25"\nname = "x"\nexpect = "  "\n',
        encoding="utf-8",
    )
    with pytest.raises(InterventionError, match="expect"):
        load_interventions(path)


def test_missing_file_is_an_empty_list_not_an_error(tmp_path):
    assert load_interventions(tmp_path / "nope.toml") == []


def test_interventions_come_back_in_date_order(tmp_path):
    path = tmp_path / "interventions.toml"
    path.write_text(
        '[[intervention]]\ndate = "2026-08-26"\nname = "b"\nexpect = "y"\n'
        '[[intervention]]\ndate = "2026-08-25"\nname = "a"\nexpect = "x"\n',
        encoding="utf-8",
    )
    assert [i.name for i in load_interventions(path)] == ["a", "b"]
```

Create `tests/test_modes.py`:

```python
import pytest

from agent_yield.modes import ModeError, load_modes, mode_for


def test_loads_operator_tagged_sessions(tmp_path):
    path = tmp_path / "session-modes.toml"
    path.write_text(
        '[[session]]\nid = "588b0593"\nmode = "design"\n', encoding="utf-8"
    )
    assert load_modes(path) == {"588b0593": "design"}


def test_unknown_mode_is_rejected(tmp_path):
    path = tmp_path / "session-modes.toml"
    path.write_text('[[session]]\nid = "s1"\nmode = "vibes"\n', encoding="utf-8")
    with pytest.raises(ModeError, match="vibes"):
        load_modes(path)


def test_missing_file_is_empty_not_an_error(tmp_path):
    assert load_modes(tmp_path / "nope.toml") == {}


def test_untagged_sessions_are_untagged_never_guessed():
    assert mode_for("never-seen", {"s1": "build"}) == "untagged"
    assert mode_for(None, {"s1": "build"}) == "untagged"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_interventions.py tests/test_modes.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'agent_yield.interventions'`

- [ ] **Step 3: Write `interventions.py`**

```python
"""Process changes, on the record, with a prediction attached."""
from __future__ import annotations

import datetime as dt
import tomllib
from dataclasses import dataclass
from pathlib import Path


class InterventionError(ValueError):
    """An intervention file that cannot be trusted to mean what it says."""


@dataclass(frozen=True)
class Intervention:
    date: dt.date
    name: str
    expect: str


def load_interventions(path: Path) -> list[Intervention]:
    path = Path(path)
    if not path.exists():
        return []
    with path.open("rb") as handle:
        data = tomllib.load(handle)

    out: list[Intervention] = []
    for index, entry in enumerate(data.get("intervention", [])):
        where = f"{path}, intervention #{index + 1}"
        raw_date = entry.get("date")
        name = str(entry.get("name", "")).strip()
        expect = str(entry.get("expect", "")).strip()
        if not name:
            raise InterventionError(f"{where}: 'name' is required")
        # An intervention without a prediction is not an experiment. Refusing
        # it here is the whole reason this loader exists.
        if not expect:
            raise InterventionError(
                f"{where} ({name!r}): 'expect' is required and must say what "
                f"you predict will change"
            )
        if isinstance(raw_date, dt.datetime):
            parsed = raw_date.date()
        elif isinstance(raw_date, dt.date):
            parsed = raw_date
        else:
            try:
                parsed = dt.date.fromisoformat(str(raw_date))
            except ValueError as exc:
                raise InterventionError(
                    f"{where}: bad 'date' {raw_date!r}"
                ) from exc
        out.append(Intervention(date=parsed, name=name, expect=expect))

    out.sort(key=lambda i: i.date)
    return out
```

- [ ] **Step 4: Write `modes.py`**

```python
"""Work-mode tags. Recorded by the operator, never inferred.

A design conversation ships no merges; a mechanical sweep ships many cheap
commits. Inferring the mode from the shape of the work would let the tool pick
whichever denominator flatters the day.
"""
from __future__ import annotations

import tomllib
from pathlib import Path

VALID_MODES = frozenset({"build", "review", "design", "audit", "ops"})
UNTAGGED = "untagged"


class ModeError(ValueError):
    """A mode tag that is not one of the five."""


def load_modes(path: Path) -> dict[str, str]:
    path = Path(path)
    if not path.exists():
        return {}
    with path.open("rb") as handle:
        data = tomllib.load(handle)

    modes: dict[str, str] = {}
    for index, entry in enumerate(data.get("session", [])):
        where = f"{path}, session #{index + 1}"
        session_id = str(entry.get("id", "")).strip()
        mode = str(entry.get("mode", "")).strip()
        if not session_id:
            raise ModeError(f"{where}: 'id' is required")
        if mode not in VALID_MODES:
            raise ModeError(
                f"{where}: mode {mode!r} is not one of {sorted(VALID_MODES)}"
            )
        modes[session_id] = mode
    return modes


def mode_for(session_id: str | None, modes: dict[str, str]) -> str:
    """The recorded mode, or UNTAGGED. Never a guess."""
    if not session_id:
        return UNTAGGED
    return modes.get(session_id, UNTAGGED)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_interventions.py tests/test_modes.py -v`
Expected: PASS, 9 passed

- [ ] **Step 6: Commit**

```bash
git add src/agent_yield/interventions.py src/agent_yield/modes.py tests/test_interventions.py tests/test_modes.py
git commit -m "interventions+modes: operator claims, expect required, modes never guessed"
```

---

### Task 6: `thresholds` and `predict`

**Files:**
- Create: `src/agent_yield/thresholds.py`
- Create: `src/agent_yield/predict.py`
- Test: `tests/test_predict.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `CONTEXT_WARN`, `COMPACT_AT_BOUNDARY`, `COMPACT_NOW`, `PREFER_FRESH_SESSION_AT_BOUNDARY`, `DAILY_CEILING`, `DAILY_WARN`, `SESSION_SOFT_BUDGET`, `REFERENCE_CONTEXT`, `DEFAULT_EXPECTED_CALLS`, `OBSERVED_CALL_RANGE`, `band_for_day(day_total: int) -> str`; `Projection(context: int, calls: int, low: int, expected: int, high: int)` with `.describe() -> str`; `project(context_size: int, expected_calls: int = DEFAULT_EXPECTED_CALLS) -> Projection`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_predict.py`:

```python
from agent_yield.predict import project
from agent_yield.thresholds import DAILY_CEILING, DAILY_WARN, band_for_day


def test_projects_the_case_study_median_agent():
    """136K context x ~70 calls should land near the measured 12.4M median."""
    projection = project(context_size=136_449, expected_calls=70)
    assert projection.expected == 136_449 * 70
    assert 9_000_000 < projection.expected < 14_000_000


def test_projection_carries_the_observed_spread_not_a_point():
    projection = project(context_size=136_449)
    assert projection.low == 136_449 * 62
    assert projection.high == 136_449 * 188
    assert projection.low < projection.expected < projection.high


def test_default_expected_calls_is_the_observed_median():
    assert project(context_size=1).expected == 69


def test_describe_reports_tokens_never_money():
    described = project(136_449).describe()
    assert "M tokens" in described
    assert "$" not in described


def test_bands_follow_section_5():
    assert band_for_day(100) == "silent"
    assert band_for_day(DAILY_WARN) == "warn"
    assert band_for_day(DAILY_CEILING) == "over"
    assert band_for_day(DAILY_CEILING + 1) == "over"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_predict.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'agent_yield.predict'`

- [ ] **Step 3: Write `thresholds.py`**

```python
"""The numbers from design.md section 5, in one place.

PROVISIONAL. These are calibrated from a single month of one operator's data
and are meant to be revisited once two weeks of recorded yield exist. They are
gathered here so that revising them is one edit, not a search.
"""
from __future__ import annotations

# Context, as a fraction of the window.
CONTEXT_WARN = 0.60
COMPACT_AT_BOUNDARY = 0.75
COMPACT_NOW = 0.85
PREFER_FRESH_SESSION_AT_BOUNDARY = 0.50

# Tokens.
DAILY_CEILING = 750_000_000
DAILY_WARN = 450_000_000
SESSION_SOFT_BUDGET = 400_000_000

# Dispatch model, from docs/case-study.md.
REFERENCE_CONTEXT = 136_449          # cache-read tokens per call, 2026-08-24
DEFAULT_EXPECTED_CALLS = 69          # median of the twelve agents on record
OBSERVED_CALL_RANGE = (62, 188)      # the 3x spread; this is why it is a band


def band_for_day(day_total: int) -> str:
    """Which of the three bands a day's spend falls in."""
    if day_total >= DAILY_CEILING:
        return "over"
    if day_total >= DAILY_WARN:
        return "warn"
    return "silent"
```

- [ ] **Step 4: Write `predict.py`**

```python
"""What a dispatch is about to cost, before you spend it.

cost ~= tool_calls x context_size. This is a warning aid, not a forecast: the
observed call count across recorded agents spans 62 to 188, a 3x spread, so a
single number here would be false precision.
"""
from __future__ import annotations

from dataclasses import dataclass

from .thresholds import DEFAULT_EXPECTED_CALLS, OBSERVED_CALL_RANGE


@dataclass(frozen=True)
class Projection:
    context: int
    calls: int
    low: int
    expected: int
    high: int

    def describe(self) -> str:
        return (
            f"~{self.expected / 1e6:.1f}M tokens "
            f"(range {self.low / 1e6:.1f}M-{self.high / 1e6:.1f}M) "
            f"at {self.context:,} context x {self.calls} calls"
        )


def project(
    context_size: int, expected_calls: int = DEFAULT_EXPECTED_CALLS
) -> Projection:
    low_calls, high_calls = OBSERVED_CALL_RANGE
    return Projection(
        context=context_size,
        calls=expected_calls,
        low=context_size * low_calls,
        expected=context_size * expected_calls,
        high=context_size * high_calls,
    )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_predict.py -v`
Expected: PASS, 5 passed

- [ ] **Step 6: Commit**

```bash
git add src/agent_yield/thresholds.py src/agent_yield/predict.py tests/test_predict.py
git commit -m "predict: cost as a band, with section 5 thresholds in one module"
```

---

### Task 7: `report` — the join

This is the product. Everything before it was materials.

**Files:**
- Create: `src/agent_yield/report.py`
- Test: `tests/test_report.py`

**Interfaces:**
- Consumes: `CallRecord` (Task 2), `DailyOutcome` (Task 4), `Intervention`, `mode_for` (Task 5), `Usage` (Task 1).
- Produces: `YieldRow(day: date, mode: str, usage: Usage, calls: int, merges: int, commits: int, lines: int, tests: int | None)` with `.tokens_per_merge`, `.tokens_per_commit`, `.context_per_call`; `build_rows(records, outcomes, modes) -> list[YieldRow]`; `BeforeAfter(intervention, metric, before, after)` with `.change`; `compare_interventions(rows, interventions, window_days=7, metric="tokens_per_merge") -> list[BeforeAfter]`; `render_table(rows) -> str`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_report.py`:

```python
import datetime as dt

from agent_yield.interventions import Intervention
from agent_yield.outcomes import DailyOutcome
from agent_yield.records import CallRecord
from agent_yield.report import build_rows, compare_interventions, render_table
from agent_yield.usage import Usage


def _call(day: str, session: str, cache_read: int) -> CallRecord:
    tag = f"{day}{session}{cache_read}"
    return CallRecord(
        timestamp=dt.datetime.fromisoformat(f"{day}T12:00:00+00:00"),
        usage=Usage(cache_read_tokens=cache_read),
        session_id=session,
        request_id=f"r{tag}",
        message_id=f"m{tag}",
    )


def test_rows_are_split_by_mode_never_pooled():
    records = [_call("2026-08-24", "s1", 100), _call("2026-08-24", "s2", 900)]
    outcomes = [DailyOutcome(dt.date(2026, 8, 24), merges=2, commits=4, lines=10)]
    rows = {r.mode: r for r in
            build_rows(records, outcomes, {"s1": "build", "s2": "design"})}
    assert set(rows) == {"build", "design"}
    assert rows["build"].usage.cache_read_tokens == 100
    assert rows["design"].usage.cache_read_tokens == 900


def test_untagged_sessions_are_reported_separately():
    records = [_call("2026-08-24", "s1", 100), _call("2026-08-24", "unknown", 50)]
    outcomes = [DailyOutcome(dt.date(2026, 8, 24), merges=1, commits=1, lines=1)]
    rows = {r.mode: r for r in build_rows(records, outcomes, {"s1": "build"})}
    assert "untagged" in rows
    assert rows["untagged"].usage.cache_read_tokens == 50


def test_tokens_per_merge_is_none_when_nothing_merged():
    records = [_call("2026-08-24", "s1", 100)]
    outcomes = [DailyOutcome(dt.date(2026, 8, 24), merges=0, commits=3, lines=5)]
    row = build_rows(records, outcomes, {"s1": "design"})[0]
    assert row.tokens_per_merge is None
    assert row.tokens_per_commit == 100 / 3


def test_before_after_compares_the_windows_around_an_intervention():
    records = [_call("2026-08-20", "s1", 1000), _call("2026-08-26", "s1", 100)]
    outcomes = [
        DailyOutcome(dt.date(2026, 8, 20), merges=1, commits=1, lines=1),
        DailyOutcome(dt.date(2026, 8, 26), merges=1, commits=1, lines=1),
    ]
    rows = build_rows(records, outcomes, {"s1": "build"})
    intervention = Intervention(
        date=dt.date(2026, 8, 25), name="brief-pack",
        expect="cost per merge falls",
    )
    result = compare_interventions(rows, [intervention])[0]
    assert result.before == 1000
    assert result.after == 100
    assert result.intervention.expect == "cost per merge falls"


def test_before_after_reports_none_rather_than_zero_when_a_window_is_empty():
    records = [_call("2026-08-26", "s1", 100)]
    outcomes = [DailyOutcome(dt.date(2026, 8, 26), merges=1, commits=1, lines=1)]
    rows = build_rows(records, outcomes, {"s1": "build"})
    intervention = Intervention(date=dt.date(2026, 8, 25), name="x", expect="y")
    result = compare_interventions(rows, [intervention])[0]
    assert result.before is None
    assert result.change is None


def test_table_never_prints_a_currency_symbol():
    records = [_call("2026-08-24", "s1", 100)]
    outcomes = [DailyOutcome(dt.date(2026, 8, 24), merges=1, commits=1, lines=1)]
    rendered = render_table(build_rows(records, outcomes, {"s1": "build"}))
    assert "$" not in rendered
    assert "2026-08-24" in rendered
    assert "build" in rendered
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_report.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'agent_yield.report'`

- [ ] **Step 3: Write minimal implementation**

Create `src/agent_yield/report.py`:

```python
"""The join: spend over outcomes, per mode, with interventions marked.

Reports tokens. Never money -- rates change and vary by plan, and a tool that
hardcodes them lies quietly later.
"""
from __future__ import annotations

import datetime as dt
import statistics
from dataclasses import dataclass
from typing import Iterable

from .interventions import Intervention
from .modes import mode_for
from .outcomes import DailyOutcome
from .records import CallRecord
from .usage import Usage


@dataclass(frozen=True)
class YieldRow:
    day: dt.date
    mode: str
    usage: Usage
    calls: int
    merges: int
    commits: int
    lines: int
    tests: int | None = None

    @property
    def tokens_per_merge(self) -> float | None:
        return self.usage.total / self.merges if self.merges else None

    @property
    def tokens_per_commit(self) -> float | None:
        return self.usage.total / self.commits if self.commits else None

    @property
    def context_per_call(self) -> float | None:
        return self.usage.cache_read_tokens / self.calls if self.calls else None


def build_rows(
    records: Iterable[CallRecord],
    outcomes: Iterable[DailyOutcome],
    modes: dict[str, str],
) -> list[YieldRow]:
    """One row per (day, mode) that had spend.

    Outcomes are per-day and cannot be attributed to a mode, so each row
    carries its day's outcomes whole. Splitting them between modes would be a
    guess, and a guess about the denominator is the error this tool documents.
    """
    outcome_by_day = {o.day: o for o in outcomes}

    buckets: dict[tuple[dt.date, str], list[CallRecord]] = {}
    for record in records:
        key = (record.day, mode_for(record.session_id, modes))
        buckets.setdefault(key, []).append(record)

    rows: list[YieldRow] = []
    for (day, mode), calls in sorted(buckets.items()):
        usage = Usage.zero()
        for call in calls:
            usage = usage + call.usage
        outcome = outcome_by_day.get(day, DailyOutcome(day))
        rows.append(YieldRow(
            day=day, mode=mode, usage=usage, calls=len(calls),
            merges=outcome.merges, commits=outcome.commits,
            lines=outcome.lines, tests=outcome.tests,
        ))
    return rows


@dataclass(frozen=True)
class BeforeAfter:
    intervention: Intervention
    metric: str
    before: float | None
    after: float | None

    @property
    def change(self) -> float | None:
        if self.before is None or self.after is None or self.before == 0:
            return None
        return (self.after - self.before) / self.before


def compare_interventions(
    rows: Iterable[YieldRow],
    interventions: Iterable[Intervention],
    window_days: int = 7,
    metric: str = "tokens_per_merge",
) -> list[BeforeAfter]:
    """Median of `metric` in the window before and after each intervention.

    An empty window yields None, not zero. Zero would read as "it got free".
    """
    rows = list(rows)
    results: list[BeforeAfter] = []

    def sample(lo: dt.date, hi: dt.date) -> float | None:
        values = []
        for row in rows:
            if lo <= row.day <= hi:
                value = getattr(row, metric)
                if value is not None:
                    values.append(value)
        return statistics.median(values) if values else None

    for intervention in interventions:
        start = intervention.date - dt.timedelta(days=window_days)
        end = intervention.date + dt.timedelta(days=window_days)
        results.append(BeforeAfter(
            intervention=intervention,
            metric=metric,
            before=sample(start, intervention.date - dt.timedelta(days=1)),
            after=sample(intervention.date, end),
        ))
    return results


def _fmt(value: float | None) -> str:
    return "-" if value is None else f"{value:,.0f}"


def render_table(rows: Iterable[YieldRow]) -> str:
    header = (
        f"{'day':<12}{'mode':<10}{'tokens':>16}{'calls':>8}"
        f"{'merges':>8}{'commits':>9}{'tok/merge':>14}{'ctx/call':>11}"
    )
    lines = [header, "-" * len(header)]
    for row in rows:
        lines.append(
            f"{row.day.isoformat():<12}{row.mode:<10}"
            f"{row.usage.total:>16,}{row.calls:>8,}"
            f"{row.merges:>8,}{row.commits:>9,}"
            f"{_fmt(row.tokens_per_merge):>14}{_fmt(row.context_per_call):>11}"
        )
    return "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_report.py -v`
Expected: PASS, 6 passed

- [ ] **Step 5: Commit**

```bash
git add src/agent_yield/report.py tests/test_report.py
git commit -m "report: join spend to outcomes per mode, with intervention before/after"
```

---

### Task 8: `gate` — the warn bands only

**The refuse band is deliberately not built in this task.** Task 1 of `design.md` §8 established that a `PreToolUse` hook *does* fire on the `Agent` dispatch with `subagent_type` and `model` readable. It did **not** establish that exit code 2 blocks that dispatch. Task 9 settles that under human approval; until it passes, this component warns.

**Files:**
- Create: `src/agent_yield/gate.py`
- Test: `tests/test_gate.py`

**Interfaces:**
- Consumes: `load_ingested` (Task 3), `project`, `Projection` (Task 6), `band_for_day`, `REFERENCE_CONTEXT` (Task 6).
- Produces: `DISPATCH_TOOLS: tuple[str, ...]`; `DispatchRequest(subagent_type, model, description)`; `read_dispatch(payload: dict) -> DispatchRequest | None`; `gate_message(day_total: int, projection: Projection) -> str | None`; `main(argv=None, stdin=None) -> int`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_gate.py`:

```python
import io
import json

from agent_yield.gate import DispatchRequest, gate_message, main, read_dispatch
from agent_yield.predict import project
from agent_yield.thresholds import DAILY_CEILING, DAILY_WARN

# The payload shape verified on 2026-08-25 by .claude/hooks/probe.py.
DISPATCH = {
    "hook_event_name": "PreToolUse",
    "tool_name": "Agent",
    "tool_input": {
        "description": "No-op probe agent",
        "model": "haiku",
        "prompt": "Do nothing.",
        "subagent_type": "general-purpose",
    },
}


def test_reads_the_verified_dispatch_fields():
    assert read_dispatch(DISPATCH) == DispatchRequest(
        subagent_type="general-purpose",
        model="haiku",
        description="No-op probe agent",
    )


def test_absent_keys_default_rather_than_raise():
    # `isolation` was absent from the observed payload simply because the
    # caller did not pass it. Absent means not passed, not unavailable.
    request = read_dispatch({"tool_name": "Agent", "tool_input": {"prompt": "x"}})
    assert request.subagent_type is None
    assert request.model is None


def test_non_dispatch_tools_are_ignored():
    assert read_dispatch({"tool_name": "Bash", "tool_input": {}}) is None


def test_silent_band_says_nothing():
    assert gate_message(1_000, project(136_449)) is None


def test_warn_band_names_the_burn_and_the_projection():
    message = gate_message(DAILY_WARN, project(136_449))
    assert "450,000,000" in message
    assert "M tokens" in message


def test_over_ceiling_still_exits_zero_because_refuse_is_unverified():
    payload = {**DISPATCH, "_day_total": DAILY_CEILING}
    assert main(stdin=io.StringIO(json.dumps(payload))) == 0


def test_hook_never_exits_nonzero_on_a_malformed_payload():
    assert main(stdin=io.StringIO("not json")) == 0
    assert main(stdin=io.StringIO("")) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_gate.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'agent_yield.gate'`

- [ ] **Step 3: Write minimal implementation**

Create `src/agent_yield/gate.py`:

```python
"""PreToolUse hook: say what this dispatch is about to cost.

VERIFIED 2026-08-25: a PreToolUse matcher fires on the main thread's `Agent`
dispatch, and `tool_input` carries the arguments the caller passed -- observed:
description, model, prompt, subagent_type. Keys the caller omitted are simply
absent, so every read here defaults instead of assuming presence. The hook also
fires for a background dispatch.

NOT VERIFIED: that exit code 2 refuses the dispatch. Until it is, this hook
always exits 0. A gate that claims enforcement it does not have is worse than
one that admits it warns.

Two harness constraints, restated because they bound what this can ever do:
hooks do not fire for tool calls made inside a subagent (#34692), and hook
config loads at session start, so a policy change lands in the NEXT session.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from .predict import Projection, project
from .thresholds import REFERENCE_CONTEXT, band_for_day

DISPATCH_TOOLS = ("Agent", "Task")
DEFAULT_CALLS_PATH = Path(".agent-yield") / "calls.jsonl"


@dataclass(frozen=True)
class DispatchRequest:
    subagent_type: str | None = None
    model: str | None = None
    description: str | None = None


def read_dispatch(payload: dict) -> DispatchRequest | None:
    if payload.get("tool_name") not in DISPATCH_TOOLS:
        return None
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        tool_input = {}
    return DispatchRequest(
        subagent_type=tool_input.get("subagent_type"),
        model=tool_input.get("model"),
        description=tool_input.get("description"),
    )


def gate_message(day_total: int, projection: Projection) -> str | None:
    band = band_for_day(day_total)
    if band == "silent":
        return None
    prefix = "WARN" if band == "warn" else "OVER CEILING"
    return (
        f"[agent-yield] {prefix}: {day_total:,} tokens spent today. "
        f"This dispatch projects {projection.describe()}."
    )


def _day_total(calls_path: Path) -> int:
    from .ingest import load_ingested

    today = dt.datetime.now(dt.timezone.utc).date()
    return sum(r.usage.total for r in load_ingested(calls_path) if r.day == today)


def main(argv: list[str] | None = None, stdin: TextIO | None = None) -> int:
    """Always returns 0. See the module docstring for why."""
    stream = stdin if stdin is not None else sys.stdin
    try:
        payload = json.loads(stream.read() or "{}")
    except (ValueError, OSError):
        return 0
    if not isinstance(payload, dict):
        return 0

    if read_dispatch(payload) is None:
        return 0

    # `_day_total` in the payload is a test seam; real runs read the ingest.
    day_total = payload.get("_day_total")
    if not isinstance(day_total, int):
        try:
            day_total = _day_total(DEFAULT_CALLS_PATH)
        except (OSError, ValueError):
            day_total = 0

    message = gate_message(day_total, project(REFERENCE_CONTEXT))
    if message:
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "additionalContext": message,
            }
        }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_gate.py -v`
Expected: PASS, 7 passed

- [ ] **Step 5: Commit**

```bash
git add src/agent_yield/gate.py tests/test_gate.py
git commit -m "gate: warn bands on a verified dispatch payload; refuse stays unbuilt"
```

---

### Task 9: Settle the refuse path (**requires human approval**)

**Do not attempt this task autonomously.** It installs a hook that denies a tool call. An agent session that self-approves that is doing something it should not; the correct move when blocked is to stop and ask, which is what happened on 2026-08-25.

**Files:**
- Modify: `docs/design.md` §4.5
- Modify: `src/agent_yield/gate.py` (only if the deny path is confirmed)
- Modify: `README.md` (only if it is not)

- [ ] **Step 1: Ask the operator to approve the experiment**

State plainly: "To finish §4.5 I need to temporarily make a `PreToolUse` hook return exit code 2 on `Agent` dispatches, dispatch one throwaway agent, and observe whether it is refused. It reverts immediately. May I?"

- [ ] **Step 2: With approval, add the deny path to the probe**

In `.claude/hooks/probe.py`, immediately before `return 0`:

```python
    if tool in ("Agent", "Task"):
        print("agent-yield: deny-path test", file=sys.stderr)
        return 2
```

The probe's matcher must cover the dispatch tool. Note that hook *config* loads at session start — if the matcher was narrowed to `Agent|Task` and that narrowing has not taken effect yet, the `*` matcher from the previous session is what is live.

- [ ] **Step 3: Dispatch one trivial agent and record what happens**

Expected if the refuse path is real: the dispatch is blocked and the stderr text is surfaced. Expected if not: the agent runs normally and only the log line appears.

- [ ] **Step 4: Revert the probe immediately**

```bash
git checkout -- .claude/hooks/probe.py
```

- [ ] **Step 5: Record the result in `docs/design.md` §4.5**

Replace the "Still unverified: the refuse path" paragraph with what was measured. **A negative is a real result** — if exit 2 does not block, §4.5 is permanently a warn, `README.md` must say so rather than implying a gate, and §6's "It does not guarantee enforcement" earns a second, sharper sentence.

- [ ] **Step 6: Only if confirmed, add the refuse band to `gate.py`**

```python
    if band_for_day(day_total) == "over" and not os.environ.get("AGENT_YIELD_OVERRIDE"):
        print(message, file=sys.stderr)
        return 2
```

The override must be a **named** environment variable, per §4.5's "refuse-with-named-override" — never a silent bypass. Update `test_over_ceiling_still_exits_zero_because_refuse_is_unverified` to match the new behaviour rather than deleting it.

- [ ] **Step 7: Commit**

```bash
git add docs/design.md src/agent_yield/gate.py README.md
git commit -m "gate: settle the refuse path against a measured result"
```

---

### Task 10: `cli` — wire the subcommands together

**Files:**
- Create: `src/agent_yield/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: everything above.
- Produces: `main(argv: list[str] | None = None) -> int` with subcommands `ingest`, `outcomes`, `report`, `predict`, `gate`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_cli.py`:

```python
import json

from agent_yield.cli import main


def test_predict_prints_a_band(capsys):
    assert main(["predict", "--context", "136449", "--calls", "70"]) == 0
    out = capsys.readouterr().out
    assert "M tokens" in out
    assert "$" not in out


def test_ingest_reports_how_many_calls_it_holds(tmp_path, capsys):
    src = tmp_path / "s.jsonl"
    src.write_text(json.dumps({
        "type": "assistant", "timestamp": "2026-08-24T12:00:00.000Z",
        "requestId": "r1", "sessionId": "s1",
        "message": {"id": "m1", "usage": {"cache_read_input_tokens": 10}},
    }), encoding="utf-8")
    dest = tmp_path / "calls.jsonl"
    assert main(["ingest", "--root", str(src), "--dest", str(dest)]) == 0
    assert "1 calls" in capsys.readouterr().out


def test_report_on_an_empty_ingest_says_so_rather_than_printing_zeroes(
    tmp_path, capsys
):
    assert main(["report", "--calls", str(tmp_path / "nothing.jsonl"),
                 "--repo", str(tmp_path)]) == 0
    assert "no calls" in capsys.readouterr().out.lower()


def test_unknown_subcommand_is_an_error():
    assert main(["nonsense"]) != 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_cli.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'agent_yield.cli'`

- [ ] **Step 3: Write minimal implementation**

Create `src/agent_yield/cli.py`:

```python
"""Subcommands. Thin -- every one is a call into a tested module."""
from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path

from . import gate as gate_module
from .discovery import default_roots
from .ingest import ingest, load_ingested
from .interventions import load_interventions
from .modes import load_modes
from .outcomes import daily_outcomes
from .predict import project
from .report import build_rows, compare_interventions, render_table
from .thresholds import DEFAULT_EXPECTED_CALLS, REFERENCE_CONTEXT

DEFAULT_CALLS_PATH = Path(".agent-yield") / "calls.jsonl"


def _cmd_ingest(args) -> int:
    roots = [Path(r) for r in args.root] if args.root else default_roots()
    held = ingest(Path(args.dest), roots)
    print(f"{held} calls held in {args.dest}")
    return 0


def _cmd_predict(args) -> int:
    print(project(args.context, args.calls).describe())
    return 0


def _cmd_outcomes(args) -> int:
    since = dt.date.fromisoformat(args.since)
    until = (dt.date.fromisoformat(args.until) if args.until
             else dt.datetime.now(dt.timezone.utc).date())
    for outcome in daily_outcomes(Path(args.repo), since, until):
        print(f"{outcome.day}  merges={outcome.merges}  "
              f"commits={outcome.commits}  lines={outcome.lines}")
    return 0


def _cmd_report(args) -> int:
    records = load_ingested(Path(args.calls))
    if not records:
        print(f"no calls recorded in {args.calls} -- run `agent-yield ingest` first")
        return 0

    days = sorted(r.day for r in records)
    since = dt.date.fromisoformat(args.since) if args.since else days[0]
    until = dt.date.fromisoformat(args.until) if args.until else days[-1]

    repo = Path(args.repo)
    rows = build_rows(
        [r for r in records if since <= r.day <= until],
        daily_outcomes(repo, since, until),
        load_modes(repo / "session-modes.toml"),
    )
    print(render_table(rows))

    interventions = load_interventions(repo / "interventions.toml")
    if interventions:
        print("\ninterventions")
        for result in compare_interventions(rows, interventions):
            before = "-" if result.before is None else f"{result.before:,.0f}"
            after = "-" if result.after is None else f"{result.after:,.0f}"
            print(f"  {result.intervention.date}  {result.intervention.name}")
            print(f"    expected: {result.intervention.expect}")
            print(f"    {result.metric}: {before} -> {after}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agent-yield")
    subs = parser.add_subparsers(dest="command", required=True)

    p = subs.add_parser("ingest", help="read transcripts and persist calls")
    p.add_argument("--root", action="append", help="transcript root (repeatable)")
    p.add_argument("--dest", default=str(DEFAULT_CALLS_PATH))
    p.set_defaults(func=_cmd_ingest)

    p = subs.add_parser("predict", help="project a dispatch's cost")
    p.add_argument("--context", type=int, default=REFERENCE_CONTEXT)
    p.add_argument("--calls", type=int, default=DEFAULT_EXPECTED_CALLS)
    p.set_defaults(func=_cmd_predict)

    p = subs.add_parser("outcomes", help="what git says shipped")
    p.add_argument("--repo", default=".")
    p.add_argument("--since", required=True)
    p.add_argument("--until")
    p.set_defaults(func=_cmd_outcomes)

    p = subs.add_parser("report", help="the join")
    p.add_argument("--repo", default=".")
    p.add_argument("--calls", default=str(DEFAULT_CALLS_PATH))
    p.add_argument("--since")
    p.add_argument("--until")
    p.set_defaults(func=_cmd_report)

    p = subs.add_parser("gate", help="PreToolUse hook entry point")
    p.set_defaults(func=lambda _args: gate_module.main())

    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code) if exc.code else 2
    return args.func(args)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_cli.py -v`
Expected: PASS, 4 passed

- [ ] **Step 5: Run the whole suite**

Run: `python -m pytest -v`
Expected: PASS, all tests

- [ ] **Step 6: Commit**

```bash
git add src/agent_yield/cli.py tests/test_cli.py
git commit -m "cli: ingest, outcomes, report, predict, gate"
```

---

### Task 11: Prove it against real data

The regression fixtures in Task 3 are synthetic replicas of the case-study numbers — they prove the arithmetic, not the parser's grip on real files. This task runs the tool against the actual transcripts on the machine and checks the constant falls out.

**Files:**
- Create: `docs/validation-2026-08.md`
- Modify: `.gitignore`

- [ ] **Step 1: Ingest real transcripts**

```bash
python -m agent_yield.cli ingest --dest .agent-yield/calls.jsonl
```

- [ ] **Step 2: Check context-per-call against the case study**

```bash
python -c "
from pathlib import Path
from agent_yield.ingest import load_ingested, context_per_call, median_agent_total
records = load_ingested(Path('.agent-yield/calls.jsonl'))
subs = [r for r in records if r.is_subagent]
print('calls          ', len(records))
print('context/call   ', round(context_per_call(records)))
print('subagent calls ', len(subs))
print('median agent   ', median_agent_total(records))
"
```

Expected: context-per-call in the neighbourhood of **136,000**. The case study measured 136,449 and 135,943 on two unrelated workloads — stable to 0.4%.

- [ ] **Step 3: Write down what was actually measured**

Create `docs/validation-2026-08.md` recording the real numbers, the date, how many transcripts were readable, and **how many were missing**. Note explicitly if the subagent count is far below the 77 the case study recorded: the temp directory had already lost 249 of 352 files by 2026-08-25, and a validation that quietly ingests a fraction of history would overstate its own agreement.

- [ ] **Step 4: If the constant does not reproduce, the tool is wrong**

Do not adjust the expectation. Per §7 of the design, a failure here falsifies the parser, not the case study. Debug with `superpowers:systematic-debugging`.

- [ ] **Step 5: Add the ingest to `.gitignore` and commit**

```bash
echo ".agent-yield/" >> .gitignore
git add docs/validation-2026-08.md .gitignore
git commit -m "validation: measure the real corpus against the case-study constant"
```

The ingest is machine-local data, not source.

---

## Notes for whoever executes this

**Where §8's steps landed.** Step 1 is done (settled 2026-08-25). Step 2 is Tasks 1–4. Step 3 is Tasks 5 and 7. Step 4 is Task 6. Step 5 is Tasks 8–9. Task 11 is the acceptance test for the whole thing.

**One addition to §8, made deliberately:** ingest persists to `.agent-yield/calls.jsonl` rather than reading transcripts live. Subagent transcripts live in the OS temp directory and are being deleted continuously. This is not scope creep; without it the tool's own history shrinks every time the machine cleans temp.

**The HTML view from §4.6 is not in this plan.** The design calls the terminal table first and HTML second, and the terminal table is what makes the question answerable. Add it once there is real data worth looking at.

**`subagent_tokens` is not the cost.** If any code in this repo ever reads that field, it is a bug. It counts output and uncached input, not the cache reads that are 97.4% of consumption — off by roughly 80×.
