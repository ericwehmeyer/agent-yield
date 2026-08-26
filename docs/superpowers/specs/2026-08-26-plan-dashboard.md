# Plan: the daily impact dashboard

**The finding this design exists to protect: this morning's 2.2x "improvement" was a
mixture shift, not an efficiency gain.** 08-25 was doc-heavy, 08-26 code-heavy;
tokens per commit and tokens per code-line both "improved" ~2.2x while tokens per
line of any kind sat flat at ~4,100. A dashboard showing the aggregate alone would
have reported a win and been wrong — the same failure design.md §3.1 records for
blended context/call. So the design rule, applied everywhere below: **no
decomposable aggregate appears without its decomposition beside it.** The
decomposed pair is the display; the aggregate is the footnote.

Two facts constrain everything: the corpus is one machine (Windows) while the git
history is two, and the series is n=2. The dashboard's job is to make the series
legible as it accumulates — table first, dots not trendlines, no "improving"
language anywhere except the intervention scorecard, which judges against
pre-registered numbers, never against yesterday.

---

## 1. The metric set

Each metric: definition / denominator / confounded by / what makes it lie.

**Which metrics are decomposed, and why that is the point.** Three metrics exist
*only as pairs or triples*, because their aggregate dissolved under decomposition
on real data: (4)-(6) insertions by area (this morning), (8) context/call by role
(§3.1, 3.5x apart), (9) cost-band shares by threshold (no knee exists, so no
single number summarizes the curve). Everything in an aggregate's "what makes it
lie" column is exactly what its decomposition catches.

| # | metric | definition | denominator | confounded by | what makes it lie |
|---|---|---|---|---|---|
| 1 | tokens | corpus total per UTC day, this project's cwd, this machine | none (raw) | none as a count | read alone as effort: a cheap day may be a day off, an expensive day may be the day the hard bug died |
| 2 | calls | API calls per UTC day, this machine | none (raw) | batching (§12 rule 3: tool calls per API call varies) | fewer calls read as less work when the operator merely batched better — which is the *intended* effect of one intervention, so calls sits next to tokens, never in place of it |
| 3 | commits | `git log --all --no-merges` plus merges folded back, bucketed by `%cI` converted to UTC (outcomes.py already anchors the window to UTC midnight; a bare `--since=<date>` does not) | is the denominator of (7) | commit granularity; cross-machine (two machines commit, one is measured); history rewrites visible under `--all` | an intervention that says "commit smaller" improves tokens/commit by itself, having changed nothing about spend |
| 4 | insertions, split by area | `--numstat` added lines per UTC day, classified by path: **code** = `src/**` + `tests/**`; **docs** = `docs/**` + `*.md`; **other** = the rest, shown, never silently dropped | denominators of (5)-(6) | churn (a line rewritten three times is three insertions); generated or vendored files; LOC is not value | the classifier disagreeing with the hand count — S1's acceptance requires reproducing 1,127/2,931 for 08-25 before anything is built on the split |
| 5 | tokens / insertion (all areas) | (1) ÷ sum of (4) | all insertions, cross-machine caveat as (7) | churn; days whose work is deletion or review (a valuable negative-LOC day divides by ~0) | mainly by *omission*: it is the mixture-immune control, and shown without (6) it hides that the mix moved. It was the number that stayed honest this morning: flat at ~4,100 |
| 6 | tokens / code-insertion and tokens / docs-insertion | (1) ÷ each bucket of (4) | area insertions | same as (4), plus cross-machine | shown alone, either one is the 2.2x headline again. **The pair (5)+(6) is a single display unit**: flat (5) with moving (6) reads "mixture shift"; moving (5) reads "efficiency change" |
| 7 | tokens / commit | (1) ÷ (3) | commits, **all machines** | cross-machine contamination (§4); commit granularity | numerator from one machine over a denominator from two — 4 of 66 this morning, and it will not stay that small. Kept because §11 uses it, but always rendered with the contamination flag and never as a headline |
| 8 | context/call, main and subagent separately | cache-read tokens ÷ calls per role, mean *and* median side by side (report.py already refuses the blend and already pairs mean with median: where they part, a tail is carrying the mean) | calls per role | session-length mix — one marathon drags the main mean with no behavior change; model/window changes | the mean alone when the median disagrees; the blend (excluded outright, §2) |
| 9 | share of main-thread calls ≥ each cost threshold | % of main calls at ≥300K / ≥500K / ≥700K (COST_DISPATCH / COST_RESTART / COST_STOP), main-thread only per `cost_band`'s own contract — a subagent above them is a failed brief, not a session to restart | main calls | the thresholds are CHOSEN, not discovered — thresholds.py records there is no knee, so each is a policy line | retuning the constants mid-series silently rewrites history. The series pins the constants it was computed with; a retune starts a visibly new series. This is the one family untouched by the git-denominator problem, and 20% → 4% above 300K is the cleanest real signal in the two days measured |

The **headline row** is (5)+(6) as one unit, and (9). Not (7).

## 2. What is NOT on the dashboard

**Blended context/call.** It is the documented §3.1 failure; report.py already
pulled it off the terminal table while keeping it on the row, and putting it on a
page invites exactly the misreading the split exists to prevent. Available is not
displayed.

**Any single "x.xx better than yesterday" delta.** A ratio-of-ratios headline at
n=2 is this morning's 2.22x, mechanized. Day-over-day arrows, trendlines through
two points, and improving/worsening verdicts are all excluded. Verdicts live in
one place — the scorecard — where the comparison is against a pre-registered
threshold, not against yesterday. The dashboard shows series; the scorecard shows
judgments.

(Also out by standing rule: money. Tokens, never currency.)

## 3. The intervention scoring view

One row per intervention from `interventions.toml`, prediction and outcome
adjacent:

```
intervention      date        predicted                          observed   verdict
brief-pack        2026-08-xx  sub ctx/call < 30,000              48,480     FAIL
split-same-task   2026-08-25  long >= 1.5x split; <1.25x kills   0.65x      FAIL
packing-#35       2026-08-25  (as registered)                    -          PENDING
```

- **Predicted** is quoted from the TOML verbatim: metric name, comparator,
  threshold, window, and any registered void-condition. The metric name must
  resolve to a §1 metric; a prediction naming a metric the dashboard does not
  compute renders VOID with reason `metric-undefined` — pressure to register
  predictions in measurable terms.
- **Observed** is that metric over the registered window. Dash, never zero, on
  an empty window (report_html's standing rule).
- **Verdicts:** PASS / FAIL / VOID / PENDING.

**VOID differs from FAIL structurally, not just in color.** FAIL means the
measurement was made and the prediction lost: the row carries the observed
number, takes the reserved state color (style-charts rule 7: state colors are
never reused for series), and counts in the tally. VOID means the measurement
could not honestly be made — empty window, denominator contaminated past the §4
threshold, the metric's definition changed underneath it, or a registered control
failed. A VOID row is greyed, its observed cell is a dash plus a one-word reason,
and it is **excluded from the tally**: "3 PASS / 1 FAIL (2 VOID)" never collapses
to "3/4". §11.1 is the house example — the second single-agent replicate is what
kept that result a FAIL rather than a VOID — and the scorecard holds PASS/FAIL to
the same standard: a real number over an uncontaminated window, or no verdict.

On the charts, a prediction's threshold is a **chosen** reference line drawn on
the measured series (style-charts rules 6 and 10: the null hypothesis drawn, and
measured vs chosen labeled). The 30,000 line under the subagent ctx/call series
sitting at 48,480 *is* the brief-pack scorecard row, as geometry.

## 4. The cross-machine problem

**Chosen: show the git-denominated metrics with a contamination flag.** Every
metric whose denominator comes from git carries a per-day flag: the share of that
day's commits presumed foreign. Detection, v1: a commit whose UTC hour contains
zero corpus calls from this machine is presumed foreign. The heuristic is labeled
CHOSEN on the page. Days above a contamination share — start at 25%, a constant
in thresholds.py with its rationale beside it — render the affected metrics as
VOID-style dashes with the flag, not as numbers. This morning's 4-of-66 shows a
small flag and keeps the number; a MacBook-heavy day shows a dash, which is the
truth.

What the other two cost:

- **Ingest both corpora** is the correct end state and the wrong first move. It
  costs a transport channel from the MacBook plus a staleness problem: a corpus
  that stopped syncing is indistinguishable from a machine that stopped working,
  which recreates the silent-misalignment failure this task opened with, one
  level up. When ingestion lands, the flag machinery is still wanted — it
  becomes the staleness detector.
- **Scope the join per machine** requires attributing commits to machines, and
  git records no machine: same author, same email, both boxes. Any attribution
  is a guess — timestamp correlation, i.e. the flag's own signal promoted from a
  warning into the denominator itself — and "a guess about the denominator is
  the error this tool documents" (`build_rows`' docstring). The flag uses the
  identical signal but keeps it out of the arithmetic.

## 5. The stories

Slice thin for verification, batch fat for dispatch (#35). Suggested dispatch
batches: {S1,S2}, {S3}, {S4}, {S5}, {S6,S7}.

**S1 — Area-split insertions in outcomes.** `DailyOutcome` gains `code_lines` /
`docs_lines` / `other_lines` from the existing `--numstat` walk, classified by
path. Depends on: nothing.
Acceptance (prints 2 lines; passes only if 08-25 shows 1,127 code / 2,931 docs —
the classifier must reproduce the hand measurement before anything is built on
it):

    python -c "import datetime as dt; from pathlib import Path; from agent_yield.outcomes import daily_outcomes; [print(o.day, o.code_lines, o.docs_lines, o.other_lines) for o in daily_outcomes(Path('.'), dt.date(2026,8,25), dt.date(2026,8,26))]"

**S2 — Tokens-per-insertion pair on YieldRow.** `tokens_per_insertion`,
`tokens_per_code_insertion`, `tokens_per_docs_insertion` properties; None, never
zero, on an empty denominator. Depends on: S1 (reads its fields — cannot be
independent).
Acceptance:

    python -m pytest tests/test_report.py -q 2>&1 | tail -3

**S3 — Cost-band shares per day.** `band_shares(records)` → per-day % of
main-thread calls at ≥ COST_DISPATCH / COST_RESTART / COST_STOP, with the
constants pinned into the result so a retune cannot silently rewrite the series.
Depends on: nothing in S1/S2; touches report.py alongside S2 — logically
independent, serialize the file merge.
Acceptance (prints 2 data lines; 08-25 must show ~20% ≥300K, 08-26 ~4%):

    python -c "from agent_yield.report import band_shares; from agent_yield.cli import load_records; [print(r) for r in band_shares(load_records())]" | head -4

(exact loader spelling to match the existing CLI's ingestion path).

**S4 — Contamination flag.** Per-day foreign-commit share via the
zero-local-calls-in-hour heuristic; `CONTAMINATION_VOID` constant in
thresholds.py with its CHOSEN rationale. Depends on: nothing logically; shares
outcomes.py with S1 — serialize the file, not the thinking.
Acceptance (prints 2 lines: day, foreign, total, flagged; must agree with a hand
count of one day's commits against that day's call hours):

    python -c "import datetime as dt; from pathlib import Path; from agent_yield.contamination import daily_flags; [print(f) for f in daily_flags(Path('.'), dt.date(2026,8,25), dt.date(2026,8,26))]"

**S5 — Scorecard engine.** Parse predictions from `interventions.toml` (metric,
comparator, threshold, window), resolve against §1 metrics, emit
PASS/FAIL/VOID/PENDING with reasons; VOID excluded from the tally. Depends on:
only the metrics predictions name — sub ctx/call already exists, so S5 runs today
without S1-S4; a prediction naming `tokens_per_code_insertion` stays
`metric-undefined` VOID until S2 lands, which is correct behavior, not a blocker.
Acceptance (one line per intervention; brief-pack row must read FAIL with 48,480
against <30,000):

    python -c "from agent_yield.scorecard import score_all; [print(s) for s in score_all()]"

**S6 — `agent-yield impact` terminal table.** One row per UTC day: tokens,
calls, commits with flag, the (5)+(6) pair, main/sub ctx-per-call, ≥300K share.
Blended ctx/call and day-over-day deltas absent by construction. Depends on:
S1-S4. Cannot be independent: it is the join.
Acceptance:

    agent-yield impact --since 2026-08-25 --until 2026-08-26 | head -6

**S7 — HTML dashboard section.** Extends report_html.py: the scorecard table,
one figure for the mixture story (per-day area-split insertion bars with the
tokens/insertion pair as geometry; the one sentence: *"tokens per line is flat;
the mix moved"*), one figure for band shares with intervention dates as chosen
reference lines. Self-contained, both themes, dash-never-zero, no smoothing at
small n. Depends on: S5, S6.
Acceptance (file created; first grep must print 0 — no external URL in a page
that is supposed to have none; scorecard present):

    agent-yield impact --html out.html && grep -ci "http" out.html; grep -c "scorecard" out.html

Independence summary: S1, S3, S5 are genuinely independent of each other; S2
needs S1; S4 is logically independent but shares a file with S1; S6 and S7 are
integrations and cannot be sliced free.

## 6. What would falsify the dashboard itself

- **Every verdict goes VOID.** If after ~two weeks the scorecard is all VOID —
  daily windows too noisy, contamination flags always tripped — the UTC day was
  the wrong unit of account. Interventions act at session and dispatch
  granularity; the honest rebuild is per-session, and the daily join was the
  wrong call, not merely early.
- **It changes no decision.** The repo's own test for an instrument: if no
  intervention is kept, retuned, or retracted *because a scorecard row said so*
  by the time ~10 have resolved, the dashboard is ornament and its build cost —
  measurable in this very corpus — was pure loss.
- **The MacBook becomes the majority.** If foreign commits come to dominate,
  every outcome-denominated metric is permanently dashed and the page degrades
  to per-call metrics only. Then ingesting both corpora was the prerequisite,
  not the follow-up, and shipping the flag first was the wrong order.
- **The operator reads a trend from n=2.** If someone quotes an aggregate off
  this page without its decomposition — the exact misreading it was built
  against — the display failed its one job, whatever the code does.
