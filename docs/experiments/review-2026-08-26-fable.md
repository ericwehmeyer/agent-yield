# Review, 2026-08-26 (Fable)

> **Provenance, added when this was landed on main.** Written by a Fable agent
> in an isolated worktree checked out at `c6d829e`, before `#73` landed. Two
> things it says have moved since, and both are recorded here rather than
> edited out of the findings below -- a review is a measurement with a date on
> it, and silently updating one is the defect this repo files against itself.
>
> * **The suite count.** "585 passed, 6 skipped" is that worktree, which has no
>   `.agent-yield/` corpus. On the main clone at `a55c352` it is 639 passed, 4
>   skipped; the two extra skips were the corpus-dependent org-dashboard tests.
> * **Finding 5 (#91) is half-closed.** `_SCOPED_CALLS = 1096` and its
>   permanent skip are gone as of `#73`. The other half stands and #91 stays
>   open for it: the dollar reconciliation still needs a corpus, so it still
>   does not run on CI. The fixture this finding proposes is the fix for that,
>   and it is a better one than the pin's removal.
>
> Nothing else in the document has been checked against the tree as it stands.

Scope: all 23 modules in `src/agent_yield/`, the full test suite (run on this
Windows machine: 585 passed, 6 skipped, 0 failed), `docs/burn-ledger.{md,py}`,
`docs/context-cost.html` + `context-cost-data.py`, the org-dashboard tests,
README.md, and `.github/workflows/test.yml`. Cross-checked against the 27 open
issues so nothing below duplicates one.

## Verdict

The measurement core is solid, and unusually so. `usage.py`, `records.py`,
`ingest.py` and `pricing.py` keep units apart all the way down, every rate is
reconciled against the CLI's own `costUSD` on committed fixtures, and the
dedup/incompleteness machinery accounts for its residuals to the cent
(`test_arms_33.py`, `test_pricing.py`). The tests I went hunting in for
expectation-derived-from-code — the defect #51/N10 already found once — are
clean: expectations come from committed ground truth or hand arithmetic, not
from the module under test. Skips are visible (`-rs` in CI) and each carries a
reason.

Where the project is weaker is exactly where it says its last three defects
lived: numbers that leave the generators. The flagship page's prose is
unguarded and its generator's docstring promises a `--check` that does not
exist; the burn ledger has a generator but no checker; README still carries
the pooled percentile shares that #80 retired; and the one test that
reconciles the org dashboard's dollar literals is pinned to a corpus count
that has already moved on, so it will skip everywhere, permanently. One
module-level qualifier (`allowance.PlanEstimate.is_lower_bound = True`) can be
false under the repo's own documented two-sessions working pattern.

On over-engineering: the docstring essays mostly pay rent — they carry the
measured provenance the discipline requires — but the same #44/#46/#61
stories are retold in roughly six places each, and the repo has already had to
"correct everywhere quoted, not only where found" once. That is a real
maintenance tax; I would not cut the essays, but I would stop duplicating the
case histories and point at one telling. One genuinely dead feature exists
(finding 8).

Findings, ordered by severity. CI being red on all six jobs (shallow checkout
vs `git archive` in `test_arms_65`) is real but already filed as #82; locally
the suite is green.

---

## 1. The context-cost page's prose is unguarded, and its generator's docstring promises a `--check` mode that does not exist

**What is wrong.** `docs/context-cost-data.py` exists because "a page whose
numbers are typed cannot be re-derived, and a number that cannot be re-derived
goes stale silently" (its own docstring, lines 1–8, citing the header that
said 20,757 calls while a legend said 20,255). Its docstring then claims
(lines 10–12): "`--check` re-derives them and reports what disagrees with the
page without touching it; `--write` rewrites the two data blocks and every
measured figure in the prose." Neither clause is true. `main()` (lines
204–218) defines only `--write` and `--json`; there is no `--check`. And
`write()` (line 190) replaces only the `const D` and `const CURVE` blocks —
its own docstring says "Prose figures are reported, not rewritten", and the
CLI prints "prose figures are NOT rewritten -- check them against the report
above" (line 217). No test compares the page to the generator either (grep of
`tests/` and `.github/` finds no reference to context-cost).

**The exposure.** The unguarded half is the majority of the page's numbers:
the H1 ("3.21 billion", "452 million"), all three tiles, the medians 218,440
and 96,567, the fig-1/fig-3 caption series ("3.3% of calls and 9.3% of
spending"; "79%, 68%, 59%, 37%, 18%"), both aria-labels, the rules table's
Worth column (283M/51M/5M/169M and their percentages), the leverage series
(1.29…2.41), and the legend call counts (6,101 / 15,513). I re-derived the
prose against the current `D`/`CURVE` blocks and today they agree — the page
is not wrong now. The failure is one `--write` away: the JS blocks update
silently underneath ~25 typed figures, reproducing the two-snapshots-at-once
state this file was written to kill, with the human-checks-the-report step as
the only guard.

**Impact estimate.** No published number is wrong today. The historical size
of this exact divergence class on this exact page was ~2.4% (20,757 vs
20,255) — but here the unguarded half includes every headline, so a stale
run would misstate the headline by however much the corpus moved, silently.

**Fix.** Implement `--check` (re-derive, compare both the data blocks and a
list of prose figures extracted by regex, exit non-zero on disagreement), or
extend `--write` to rewrite the prose figures from named placeholders. Either
way, add a corpus-guarded test in the style of
`test_org_dashboard_unit.test_real_days_reproduce_from_pricing_py`.

## 2. `allowance.estimate` pairs snapshots across sessions, and its `is_lower_bound: True` can then be false

**What is wrong.** `Snapshot.session_dollars` is `cost.total_cost_usd` from
whatever session rendered the status line — a per-session counter
(`allowance.py:113–118`). `estimate()` pairs the first and last snapshot
inside a 7-day window (`allowance.py:208–210`) and subtracts
`last.session_dollars - first.session_dollars` as "measured spend". Snapshots
carry no session id, so with two sessions interleaving in one repo — the
working pattern this repo documents (`session.py`'s "with two sessions open"
bug note) — the subtraction crosses counters.

**Failure scenario, concrete.** Session A has spent $10 by 14:00. Session B
starts at 14:00. The 7-day percentage ticks at 14:05 while B renders
(`session_dollars=$0.30`, 40%) and again at 18:00 while A renders ($12.40,
45%). `estimate` computes $12.10 over 5 points → "allowance >= $242", where
the spend actually measured inside the interval was ~$2.70 → the honest bound
is ~$54. The module's whole argument (docstring lines 23–31) is that
unmeasured spend can only *deflate* the estimate; cross-session pairing lets
it inflate it, and `PlanEstimate.is_lower_bound` (line 74) is unconditionally
`True` — the field exists "so a caller cannot print the number without the
qualification", and the qualification would be wrong.

**Impact estimate.** Zero until two sessions overlap in one repo while the
percentage moves ≥ MIN_POINTS; then unbounded in the wrong direction (the
example above is 4.5x). n=2 calibration today, so nothing published rests on
it yet — which is the moment to fix it.

**Fix.** Record `session_id` in `Snapshot`; `estimate` pairs only within one
session (or refuses cross-session pairs the way it already refuses < 5
points). Acceptance: a constructed interleaved log yields no estimate, or one
scoped to a single session's pair.

## 3. README still records the cost-threshold shares that #80 retired

**What is wrong.** `README.md:87`: "each cost threshold is a policy choice
recorded with the share of main-thread calls it fires on: ~35%, ~13%, ~7%."
`thresholds.py:46–59` now says the pooled-share form "WAS THE DEFECT (#80)",
and records each constant with a per-project range and the pooled figure
second: 18% / 7% / 4% (lines 69–71), noting the pooled number moved 46% → 18%
with nothing changed about how any session is run. The README quotes the
2026-08-25 calibration corpus's pooled figures as if they were what the
module records, and points the reader at a module that says something else.

**Impact estimate.** The three figures are each ~2x off the current pooled
values, in the repo's front door, in exactly the mixture-as-signal form #80
closed. Nobody's dollars are wrong; the project's credibility claim ("every
published number re-derivable") is.

**Fix.** Restate line 87 the way `thresholds.py` now does (range first,
pooled second, dated), or drop the numbers and point at the module. The
README's own closing section says corrections are recorded, not silently
edited — follow that form.

## 4. `docs/burn-ledger.md` is generated but never checked

**What is wrong.** `burn-ledger.py` regenerates the committed
`burn-ledger.md` (`--write`), and the document claims "Every figure below is
regenerated by `docs/burn-ledger.py`; nothing here is typed in." True at
generation time — but nothing ever verifies the committed copy still matches
a regeneration. There is no `--check`, and no test references burn-ledger
(grep of `tests/` and `.github/`). The corpus grows daily; a pricing retune,
an ingest, or an edit to `render()` leaves the committed document silently
disagreeing with what the generator would say. The document does print its
generation timestamp, so staleness is *datable*, but so was the context-cost
footer, and this repo's standard (#44, #46, #67, #72, and the c6d829e commit
message "can no longer go stale silently") is a check, not a date.

**Impact estimate.** Today's copy is fresh (generated 22:43 UTC on the
capture date). Drift begins with the next ingest; the headline ($2,191.99,
3.216B) moves by whatever a day adds — on this corpus roughly $50–100/day.

**Fix.** Add `--check` (regenerate, diff against `DEST`, nonzero exit) and a
`skipif(not CORPUS)` test that runs it, in the pattern
`test_org_dashboard_unit` already established. Note in passing: "21,614 calls
over 23 days, 2026-07-24 to 2026-08-26" (line 164 of the generator) reads as
a 23-day span but is 23 *active* days inside a 34-day span; "23 active days"
would stop the reader's arithmetic from failing.

## 5. The org dashboard's dollar-literal reconciliation is pinned to a corpus count that has already moved on — the check will skip everywhere, forever

**What is wrong.** `test_org_dashboard_unit.py:48` pins `_SCOPED_CALLS =
1096` and both corpus tests skip when the scoped window count differs (lines
127–130, 180–181). The window is 2026-08-25..26 and the corpus kept ingesting
after capture (the committed burn ledger, captured 22:43 UTC the same day,
already shows the corpus at 21,614 calls), so the scoped count will not be
1096 again. CI never runs these tests (no corpus); once the count moves on
the operator's machines, the only living check on the dashboard's frozen
dollar literals is dead on every machine that exists. The skip is visible
under `-rs` — but a permanent skip that reads as routine is the #29 failure
in slow motion.

**Impact estimate.** The literals were verified at capture, so nothing is
wrong today; what is lost is the guard. The guarded quantity is the page's
headline dollars, the same class the two corpus tests were written for.

**Fix.** Commit the 1,096 scoped call records as a fixture (the `arms-33`
pattern: reduced to the fields `parse_line` reads), point the two tests at
it, and drop the count-pinned skips. Then the check runs on CI too.

## 6. `agents.join` claims collision handling it does not implement, and misattributes silently when a run is missing

**What is wrong.** The comment above `MAX_JOIN_LAG_SECONDS`
(`agents.py:79–82`): two same-type dispatches within the window collide, "at
which point `join` reports both as ambiguous rather than guessing." No such
path exists. `join()` (lines ~370–400) is greedy nearest-first in dispatch
order, per dispatch, with no ambiguity detection. The module docstring's own
standard (lines 34–38): "a wrong join here would attribute one agent's cost
to another's brief, which is worse than a gap."

**Failure scenario.** Dispatch 1 and dispatch 2, same type, 30s apart;
dispatch 1's transcript evaporated (§8 says they routinely do — 249 of 352
scratch files on this machine were already empty). Dispatch 1 claims
dispatch 2's run at 31s lag; dispatch 2 reports unlinked. The audit prints
the wrong brief against the run's cost, silently, in a table whose purpose is
brief-vs-cost.

**Impact estimate.** Currently masked by #84 (408 of 426 dispatches unlinked
anyway); once #84 lands and the join actually fires at scale, this is the
next defect in line. On the 12-dispatch record it was 1:1 and harmless.

**Fix.** When more than one unclaimed same-session same-type run falls inside
one dispatch's window — or one run falls inside two dispatches' windows —
report the group ambiguous/unlinked instead of assigning. Acceptance: a
constructed two-dispatch/one-run fixture yields zero joins and two flagged
rows, not one confident join.

## 7. "context/call" is two different quantities, and the two flavors sit on the same table

**What is wrong.** Two definitions circulate under one name:

- **Cache reads only**: `YieldRow.context_per_call` / `main_context_per_call`
  (`report.py:266,272`), `ModelRow.context_per_call` and its `contexts` tuple
  (`report.py:584,615`), `ingest.context_per_call`, and
  `thresholds.REFERENCE_CONTEXT` (line 120, "cache-read tokens per call").
- **Full context** (`input + cache_read + cache_creation` =
  `CallRecord.context`): `session.py`, `statusline.py`, the cost bands,
  `agents.AgentRun.context`, and therefore
  `thresholds.BRIEFED_REFERENCE_CONTEXT`/`BRIEFED_CONTEXT_RANGE` (lines
  127–128), which were measured by the agents audit.

Consequences: (a) `render_table` prints "main ctx/call" (cache reads)
directly above a cost-bands block cut on full context against the same
300K/500K/700K constants — a reader relating column to band compares
different quantities; (b) `predict._POPULATIONS` puts REFERENCE_CONTEXT
(cache-read flavor) and BRIEFED_REFERENCE_CONTEXT (full flavor) on the same
axis; (c) `SCORABLE_METRICS` includes `main_context_per_call`, so a
prediction can be registered against the cache-read flavor while the operator
reasons in the full flavor `status` shows them.

**Impact estimate.** On this corpus the two differ by
(input+cache_creation)/context ≈ 2.5%. Small — say 2.5%, not more — but it is
a unit collapse of precisely the class `usage.py`'s docstring exists to
prevent, and it sits inside the calibration constants, where 2.5% silently
becomes part of a "measured" number.

**Fix.** Pick `CallRecord.context` as the one meaning of "context/call"
(matching the cost bands), rename the cache-read-only quantity
(`cache_read_per_call`), and re-derive REFERENCE_CONTEXT once under the
chosen definition. Related nit, same file: `build_model_rows` sorts by
`total_context` — a sum of cache reads — under the comment "Descending spend,
because the question is where the money went" (`report.py:617`). Cache reads
are 69% of the money on this corpus (burn ledger), so the ordering is
mostly-right-by-accident; an output-heavy model misranks.

## 8. The `tests` denominator is dead: unreachable from the CLI, and keyed to merge days on a linear history

**What is wrong.** `daily_outcomes(..., test_command=...)` computes test
counts only `for day in merges` (`outcomes.py:228–233`) — days with at least
one merge commit. This repo's history is linear (the code's own comment at
line 183: "On a linear history -- this repo's"), so `merges` is empty and
`tests` would be `None` on every day even if wired. And it is not wired: no
caller passes `test_command` — `cli._cmd_outcomes` and `_cmd_report` never do
(cli.py:89,140) — and `test_count_at`'s temp-worktree machinery
(`outcomes.py:256–281`, ~25 lines including subprocess and cleanup paths) has
zero test coverage and zero callers outside the dead branch. `DailyOutcome.tests`
and `YieldRow.tests` carry it through the whole reporting stack as permanent
`None`s.

**Impact estimate.** No wrong number — the column is honestly `None` — just
dead weight in the module the denominator discipline lives in, and a trap:
whoever wires `test_command` will get all-`None` on a linear history and have
to rediscover the merge-days condition.

**Fix.** Either wire `--test-command` through the CLI and key the loop on
days with commits (or all days in range), with a test on `test_count_at`; or
delete `test_count_at`, the `test_command` parameter, and the `tests` fields.
Both are defensible; carrying it half-built is not.

## 9. `Dispatch.project` splits on `/` only, so on Windows the "project" is the whole path

**What is wrong.** `agents.py:125`:
`self.cwd.rstrip("/").rsplit("/", 1)[-1]` under a docstring saying "The last
path segment of the dispatching session's cwd." Windows cwds use backslashes,
so the property returns `C:\Users\ewehm\repos\agent-yield` whole. Grouping in
`_brief_effect` still works (full paths are distinct per project), but the
rendered rows truncate to `project[:24]` — every Windows project displays as
the same `C:\Users\ewehm\repos\ag…` prefix, which defeats the display's
purpose (making the per-project decomposition readable) on the machine half
this repo runs on.

**Impact estimate.** Display-only; the confound guard's logic survives.
Cosmetic until someone reads two identical-looking rows as one project.

**Fix.** `PurePath(self.cwd).name` handles both separators; one line. The
repo already has `test_portability_guard.py` as the natural home for the
assertion.

---

## Review-only notes (no issue filed)

- **Skipped tests on this machine** (pytest `-rs`): two POSIX-only
  (`test_discovery.py:23,131`), one symlink-privilege
  (`test_ingest.py:89`), one POSIX case-sensitivity (`test_session.py:301`),
  and the two corpus-dependent org-dashboard tests (no `.agent-yield/` in
  this worktree). All carry reasons; the org-dashboard pair is finding 5.
- **CI is red** on all six jobs (#82, already filed) — `test_arms_65` runs
  `git archive` against a SHA a depth-1 checkout lacks. Locally green.
- **`ingest.ingest` unkeyed-record guard** (`ingest.py`, the
  `(timestamp, usage.total)` set): two genuinely distinct unkeyed calls with
  identical timestamp and total collapse to one, against the module's
  "undercounting is the error" doctrine. With millisecond timestamps the
  collision is improbable; noted, not filed.
- **`context-cost-data.curve()`** divides by `n` and `total` without a guard;
  an empty population (a corpus with no subagent calls) raises. The corpus
  guard upstream makes this unreachable today.
- **Silent `except Exception` blocks** in `gate.main`, `boundary.main`,
  `statusline.main`, `session.find_session` are all deliberate fail-open
  hook policy, each with the rationale written down and the failure rendered
  as a distinct visible token (`QUIET`, exit 0). This is the acceptable kind.
- **Over-engineering verdict.** `thresholds.py` is 246 lines for ~14
  constants and 4 small functions; `usage.py` is half docstring. I read all
  of it and would keep nearly all of it — the essays are the audit trail the
  discipline depends on, and twice while reviewing they answered the exact
  question I was about to file. The genuine excesses are: the retold case
  histories (#44 appears in at least 6 modules — one canonical telling,
  pointed at, would cut the correction surface), the dead `tests` machinery
  (finding 8), and `report_html.py` at 1,031 lines for a retrospective page
  whose analytical content the terminal report already carries. None of
  these is costing correctness today.
- **Test-suite quality.** The reconciliation suites (`test_arms_33`,
  `test_pricing`, `test_arms_65`) are the strongest I have reviewed in a
  repo this size: expectations pinned from committed external ground truth,
  residuals accounted exactly rather than tolerated, and the false-positive
  legs tested. `test_report.py` defines `_sub_call` twice (lines ~38 and
  ~113, identical) — harmless shadowing worth a one-line cleanup on the next
  pass.
