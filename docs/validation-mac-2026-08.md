# Independent corroboration of the ~136K constant — MacBook Pro, 2026-08-26

Third measurement of `cache_read_tokens / API call`, on different hardware and
unrelated work from the two in `case-study.md`. Task #11.

**Result: 132,234 cache-read tokens per API call.** That is 3.1% below the
2026-08-24 case-study figure of 136,449 and inside the band already spanned by
the three prior measurements. The constant corroborates.

The portability check did **not** pass cleanly. Three real bugs are recorded in
§4; all three are fixed in this commit, and the measurement above is the one
taken *after* the fixes. The number before them was 132,522 over 75 transcripts
— close, but for the wrong reason: it was missing the entire subagent scratch
tree and only agreed because main transcripts already carry sidechain lines.

## 1. Machine

| | |
|---|---|
| host | MacBook Pro, Apple silicon (`arm64`) |
| OS | macOS 26.5.1 (build 25F80) |
| Python | 3.12.5 (Homebrew) — **not** the system 3.9.13, which `pyproject.toml` correctly refuses |
| Claude Code | 2.1.246 |
| date measured | 2026-08-26 |
| history spanned | 2026-08-23 → 2026-08-26 |

Workloads in this history are photo-library work under `~/Pictures`, the
`model-migration-kit` repo, and this repo. None of it overlaps the work the
case-study numbers were taken from.

## 2. The measurement

```
transcripts      187
API calls        4,745
cache read       627,451,470
TOTAL            643,497,451
cache-read share 97.5%
context/call     132,234
median agent     5,167,865
```

Split by where the call was made:

| | calls | context/call | cache-read share |
|---|---|---|---|
| main session | 910 | 311,399 | 97.8% |
| subagent | 3,835 | 89,721 | 97.3% |

Split by working directory — the workload axis:

| calls | context/call | share | total tokens | cwd |
|---|---|---|---|---|
| 3,987 | 124,790 | 98.0% | 507,573,571 | `model-migration-kit` |
| 698 | 179,864 | 95.5% | 131,404,668 | `~/Pictures` |
| 31 | 80,230 | 97.5% | 2,550,348 | `~/Downloads` |
| 23 | 47,347 | 93.5% | 1,164,769 | `agent-yield` |
| 6 | — | — | 804,095 | four single-session dirs |

Models: `claude-opus-5` 4,720 calls, `claude-sonnet-5` 20, `claude-haiku-4-5` 5.

### Coverage — what was actually read

A corroboration that quietly ingests a fraction of history overstates its own
agreement, so:

| root | files found | contributed calls | empty | unreadable | parsed, no billable call |
|---|---|---|---|---|---|
| `~/.claude/projects` | 75 | 74 | 0 | 0 | 1 |
| `/tmp/claude-501` (`tasks/*.output`) | 112 | 62 | 1 | 0 | 49 |
| **total** | **187** | **136** | **1** | **0** | **50** |

Nothing was unreadable. Only one subagent transcript was empty — far from the
Windows machine's 249-of-352, because this history is three days old and temp
had not been swept. The 49 non-empty `.output` files with no billable call are
short agent runs whose lines carry no `message.usage` block.

"Contributed" above means the file held at least one billable line — before
dedup. After dedup the subagent scratch tree adds almost nothing over the main
tree alone. Measured twice, minutes apart:

| | main root only | both roots | unique to scratch |
|---|---|---|---|
| first run | 4,728 | 4,736 | 8 |
| later run | 4,747 | 4,747 | **0** |

Main-session transcripts already carry the sidechain lines, marked
`isSidechain: true`, and `dedup_key` collapses the duplicates. The 8 that were
briefly unique were from a session still running: the subagent's `.output` is
written live, and the same calls reach the main transcript slightly later. Once
it landed, the scratch tree held nothing the main tree did not.

So on this machine the volatile temp tree is redundant, and losing it to a temp
sweep would cost nothing. Do **not** generalise that: it holds because the
sessions here completed. It says nothing about a machine where temp is swept
while sessions are still open, and the Windows machine's 249-of-352 empty files
suggests that case is the common one.

### Against the known points

| source | context/call | cache-read share |
|---|---|---|
| case study 2026-08-24 | 136,449 | 97.2% |
| case study 2026-08-25 | 135,943 | — |
| Windows session, measured live | 128,852 | 93.0% |
| **this Mac, 2026-08-26** | **132,234** | **97.5%** |

Four measurements, two machines, three operating-system installs, unrelated
workloads: 128,852 – 136,449, a spread of ±2.8% around 132,650. The cost model
in §3 stands as written.

The spread is *not* noise, though, and the per-cwd table says why: context/call
varies from 47,347 to 179,864 **across workloads on this one machine**. What is
stable is the aggregate over a mixed session, not any single agent's context.
Use ~132K as a planning constant for a mixed workload; do not use it to price a
specific known task.

## 3. Portability check

```
.venv/bin/python -m pytest -q
69 passed
```

All 59 tests written on Windows pass on macOS unmodified, including the
`outcomes.py` git shell-out and its timezone handling. The 10 new tests cover
the bugs below.

One setup note, not a code bug: the system `python3` is 3.9.13, so
`python3 -m venv .venv && .venv/bin/python -m pip install -e .` fails with
`requires a different Python: 3.9.13 not in '>=3.11'`. Homebrew's
`/opt/homebrew/bin/python3.12` works. The `>=3.11` floor is doing its job.

## 4. Findings — three portability bugs in `discovery.py` / `records.py`

### 4.1 The subagent scratch root does not exist on macOS

`subagent_transcript_dir()` returned `tempfile.gettempdir() / "claude"`. On
macOS that resolves to the per-user `$TMPDIR`,
`/var/folders/qq/k7z.../T/claude` — which does not exist and never will.
Claude Code writes to `/tmp/claude-<uid>` instead (`/tmp/claude-501` here),
holding 112 subagent transcripts.

The failure is silent: `find_transcripts` skips a root that does not exist, so
the walk returns cleanly having read **zero** subagent transcripts and reports
75 files as if that were the whole history.

Fixed: `subagent_transcript_dirs()` returns both candidates, and `default_roots`
searches all of them.

### 4.2 The scratch tree is mostly not transcripts

`find_transcripts` rglobbed `*.jsonl` under every root. Under the scratch tree
each session also has a `scratchpad/` directory of unrelated working files —
**5,883** `.jsonl` files here (evaluation goldensets, judged outputs, evidence
dumps). Pointed at the correct root, the old code would have tried to parse all
of them as transcripts.

Fixed: `.output` counts only inside a `tasks/` directory, and nothing under a
`scratchpad/` directory counts at all.

### 4.3 `parse_line` let `RecursionError` abort the whole walk

`json.loads` raises `RecursionError`, not `ValueError`, on deeply nested input.
`parse_line` caught only `ValueError` and `load_records` only `OSError`, so one
pathological line ended the run with a traceback — contradicting
`load_records`'s own docstring promise that a file "full of junk contributes
nothing and does not abort the walk". This was hit for real: one scratchpad
file surfaced by 4.2 crashed the first measurement attempt.

Fixed: `parse_line` catches `RecursionError` too. Regression test in
`tests/test_ingest.py`.

## 5. Reproducing

```
/opt/homebrew/bin/python3.12 -m venv .venv
.venv/bin/python -m pip install -e . pytest
.venv/bin/python -m pytest -q
.venv/bin/python -m agent_yield.cli ingest      # or the snippet in issue #11
```

Numbers drift upward between runs — the session taking the measurement is
itself appending to `~/.claude/projects`. Three consecutive runs during this
work gave 4,736 / 4,744 / 4,745 calls and 132,376 / 132,249 / 132,234
context/call. The quoted figures are the last.
