# Validation against real data — 2026-08-25

Task 10 of `docs/superpowers/plans/2026-08-25-agent-yield.md`. All 59 unit
tests pass on synthetic fixtures; this record is what happened when the tool
was pointed at real transcripts instead.

## Archive used

Snapshot at `C:/Users/ewehm/transcript-archive/2026-08-25/`, taken 2026-08-25,
ingested via:

```
.venv/Scripts/python.exe -m agent_yield.cli ingest \
  --root "C:/Users/ewehm/transcript-archive/2026-08-25/projects" \
  --root "C:/Users/ewehm/transcript-archive/2026-08-25/tasks" \
  --dest .agent-yield/calls.jsonl
```

| root | files found |
|---|---|
| `projects` (main sessions, `*.jsonl`) | 426 |
| `tasks` (subagent output, `*.output`) | 103 |
| **total** | **529** |

## File-level accounting

| | count |
|---|---|
| files unreadable (`OSError`) | 0 |
| files empty (0 bytes / whitespace only) | 0 |
| files that parsed to **zero** billable-call records | 85 |
| — of which `.jsonl` | 1 |
| — of which `.output` | 84 |

None of the 529 files were literally empty or unreadable — the archive
snapshot itself is intact. But 85 of them (16%) contributed nothing to the
measurement:

- The one empty `.jsonl` (`projects/C--Users-ewehm-repos-governor/5ee86b5d-...jsonl`,
  9 lines) is a real short session that only ever wrote metadata
  (`mode`, `file-history-snapshot`) before ending — no assistant message was
  ever logged, so legitimately zero calls.
- Of the 103 `.output` files, only **19** are genuine JSONL subagent
  transcripts with usage data. The other **84** are plain-text content
  (task write-ups, not transcripts — inspecting one, e.g. `b02khd4lm.output`,
  shows ordinary prose, not JSON lines at all). These are two visibly
  different naming schemes (`a<17 hex>.output` for the 19 real transcripts vs
  `b<9 alnum>.output` for the 84 text files), so this isn't file corruption —
  the `tasks` directory holds two kinds of artifact under one glob, and most
  of what's there isn't a transcript to begin with. This is a different
  failure mode than the plan's warning about temp-directory volatility
  (files disappearing), but it lands on the same conclusion: don't trust the
  subagent count without checking what actually parsed.

Total lines read across all 529 files: 36,674,281. Lines that parsed as a
billable call (before dedup): 43,245. After dedup by `(message_id,
request_id)`: **20,273** records held in `calls.jsonl` — roughly 47% of
pre-dedup lines survive, consistent with Claude Code transcripts logging
multiple partial/streamed entries per turn under the same message id.

## The measurement (Step 2)

Computed via `agent_yield.ingest.load_ingested` against `.agent-yield/calls.jsonl`:

```
total calls               20,273
input_tokens                 290,427
output_tokens               6,849,414
cache_creation_tokens        76,374,624
cache_read_tokens          2,942,518,456
total tokens (sum of four) 3,026,032,921
cache-read share            97.24 %
context/call                145,145
subagent calls              15,252   (75.2% of all calls)
median agent total          1,887,651
```

Of the 15,252 subagent-flagged records, essentially all (29,912 of ~32,422
pre-dedup subagent lines) came from `isSidechain` entries embedded in the
main `.jsonl` transcripts, not from the `tasks/*.output` files — those
contributed only ~2,510 pre-dedup lines, matching the fact that only 19 of
103 `.output` files had any usable data at all.

## Does the constant hold?

| source | context/call |
|---|---|
| case study, 2026-08-24 | 136,449 |
| case study, 2026-08-25 | 135,943 |
| this Windows session (live) | 128,852 |
| **this run, full archive** | **145,145** |

145,145 is in the same order of magnitude as the other three points (all
within roughly 100K–150K), but it is the largest deviation from ~136,000 of
the four: **+6.7%** above the 2026-08-25 case-study figure and **+12.7%**
above the live-session figure, well outside the ±0.4% stability the case
study reported between its own two days. I am not adjusting the parser or
the expectation to make this line up — reporting it as measured.

`median_agent_total` diverges much more sharply: **1,887,651** measured here
versus **12,385,765** in the case study — the case-study figure is **6.6x**
larger. This is a real difference in whatever workload each corpus
represents, not a rounding difference.

The `report` command's day-by-day breakdown (below) makes the aggregate
number look more stable than the underlying data actually is:
context-per-call by day ranges from **0** (two low-volume days with no
cache reads at all) up to **406,661** — a machine's-width discrepancy across
days. The archive-wide 145,145 is a token-weighted average over that spread,
not evidence that any given day sits near 136K.

## `report --repo . --calls .agent-yield/calls.jsonl`

```
day         mode                tokens   calls  merges  commits     tok/merge   ctx/call
----------------------------------------------------------------------------------------
2026-07-24  untagged        22,000,735     143       0        0             -    148,293
2026-07-25  untagged        44,138,240     189       0        0             -    226,530
2026-07-26  untagged         3,814,236      31       0        0             -    102,325
2026-07-29  untagged         6,518,742      20       0        0             -    286,886
2026-07-31  untagged        31,472,129     187       0        0             -    163,623
2026-08-01  untagged       244,940,983   2,213       0        0             -    107,326
2026-08-02  untagged            36,514       4       0        0             -          0
2026-08-04  untagged         3,379,653      29       0        0             -    100,216
2026-08-05  untagged                 0       1       0        0             -          0
2026-08-07  untagged        55,796,776     612       0        0             -     86,867
2026-08-11  untagged         4,427,072      53       0        0             -     79,696
2026-08-12  untagged         4,747,932      60       0        0             -     74,349
2026-08-13  untagged       129,099,031     645       0        0             -    195,707
2026-08-14  untagged       863,052,161   5,191       0        0             -    161,815
2026-08-15  untagged        19,441,441      44       0        0             -    406,661
2026-08-17  untagged        33,721,526      76       0        0             -    391,473
2026-08-18  untagged        13,445,059     109       0        0             -    112,664
2026-08-19  untagged           149,323       1       0        0             -     27,906
2026-08-21  untagged       297,953,533   1,771       0        0             -    165,080
2026-08-22  untagged       246,610,087   1,890       0        0             -    126,132
2026-08-24  untagged       560,647,394   3,926       0        0             -    139,580
2026-08-25  untagged       440,640,354   3,078       0       10             -    140,293
```

Cross-check: summing the `tokens` column over all 22 rows gives
3,026,032,921 and summing `calls` gives 20,273 — both match the aggregate
totals above exactly, so `report` and `load_ingested`/`context_per_call`
agree with each other on this corpus.

Things that look odd but check out as correct, not bugs:

- **`merges` is 0 and `tok/merge` is `-` on every row.** This repository's
  git history is entirely linear — `git log --merges` returns nothing (0 of
  14 commits are merge commits) — so a merge-commit-based metric is
  correctly empty here. Not a parser problem, just a repo that doesn't use
  merge commits.
- **`commits` for 2026-08-25 shows 10, but `git log` shows 14 commits made
  "today."** The report buckets by UTC day (`outcomes.py: _day_of`
  converts committer timestamps to UTC before taking `.date()`), while the
  4 missing commits were made between 20:00 and 20:11 **local** time
  (UTC-04:00), which is already 2026-08-26 in UTC. The report's default
  `--since`/`--until` window is bounded by the days present in the ingested
  call data (2026-07-24 through 2026-08-25 in this archive), so those four
  UTC-08-26 commits fall outside the window and are correctly excluded by
  the tool's own stated logic — they just don't match a naive "commits
  today" expectation from local wall-clock time. Worth knowing when reading
  the table, not a defect.
- **`mode` is `untagged` for every row** because no intervention/mode config
  was supplied to this run — expected with the plain command as given.

No crashes, no exceptions, no missing/garbled columns. The table is
internally consistent and the arithmetic reconciles with the raw ingest.

## Bottom line

- The tool ran end-to-end against 529 real transcript files with zero
  crashes and zero unreadable files.
- 85 of 529 files (16%) — mostly `tasks/*.output` files that turned out to
  be plain-text content rather than JSONL transcripts — contributed no
  usage data. This is a real gap in what "subagent transcripts" means in
  this temp directory, not a parser failure, but it means the subagent-call
  count and totals should be read as a floor, not a complete census.
- **Context-per-call landed at 145,145** on the full archive, versus
  ~136,000 in the case study and 128,852 measured live in this session. It
  is in the right neighborhood (same order of magnitude, all four points
  cluster in the 100K–150K band) but is a 6.7–12.7% deviation from the other
  three points, larger than the ±0.4% stability the case study itself
  reported. Per §7 of the design, a deviation this size is grounds to treat
  it as a real signal, not noise to explain away — recorded here as
  measured, without adjusting the tool or the expectation to match.
- **Median agent total** (1,887,651) is 6.6x smaller than the case study's
  (12,385,765) — a large, unexplained divergence, reported as-is.
- **Cache-read share** measured at 97.24% on this archive, close to the
  case study's day-column figure of 97.2% and above this session's live
  93.0%. Consistent with the existing note that this share varies by
  workload rather than being a fixed constant.
