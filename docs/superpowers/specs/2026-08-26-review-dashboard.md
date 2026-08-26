# Review: the daily impact dashboard

**Verdict: RETHINK.** The plan's design rule — *"no decomposable aggregate appears
without its decomposition beside it"* — is right, and it is applied to the metrics
the plan inherited and not to the two it promotes. Both headlines fail it: the
`(5)+(6)` pair carries the exact one-machine-numerator/two-machine-denominator
defect the plan uses to demote `(7)` from headline status, and metric `(9)` is an
undecomposed aggregate over a session mixture whose confound the plan names for
`(8)` and omits for `(9)`. Worse, the finding the whole design exists to protect —
"tokens per insertion is FLAT at ~4,100" — is itself computed with a Windows-only
numerator over an all-machines denominator, and `working-method.md` §11 documents
an 11.4M-token MacBook session on 2026-08-26 whose ~2,135 added lines are in the
denominator and whose tokens are not. Correcting it in either direction turns
"flat" into "~15-17% worse". The premise needs re-deriving before seven stories,
three new modules and a rules engine are built on top of it. Nothing here says the
approach is wrong; it says the plan's own scalpel has not been turned on its own
two headline numbers, and that v1 should be two stories, not seven.

---

## 1. BLOCKING — The headline pair carries the defect that disqualified metric (7), and the "FLAT" finding may not survive it

**What is wrong.** The plan writes of tokens/commit:

> numerator from one machine over a denominator from two — 4 of 66 this morning,
> and it will not stay that small. Kept because §11 uses it, but always rendered
> with the contamination flag and never as a headline

It then writes of the metrics it *does* headline, `(5)` tokens/insertion and `(6)`
tokens/code-insertion: confounded by *"all insertions, cross-machine caveat as (7)"*
and *"same as (4), plus cross-machine"*. That is the identical defect, conceded in
the same table, and it disqualifies one metric and not the other. Mixture-immunity
(why `(5)` is the headline) and cross-machine contamination are orthogonal
properties; being immune to the first buys nothing against the second.

**Evidence.** This is not hypothetical. `docs/working-method.md` §11, lines 337-349,
records a session dated **2026-08-26, on the MacBook Pro**: 2,396,312 + 8,971,302 =
**11,367,614 tokens** producing 323 + 1,812 = **2,135 added lines**. The corpus is
Windows-only. The measured table gives 08-26 as 52.80M tokens over 12,979 insertions
= 4,068 tokens/insertion. Correct it either way:

- remove the foreign lines from the denominator: 52.80M / (12,979 − 2,135) = **4,869**
- add the foreign tokens to the numerator: (52.80M + 11.37M) / 12,979 = **4,944**

Against 08-25's 4,232, both readings are 15-17% *worse*, not flat. The two
corrections disagree about magnitude and agree about sign, which is the robust
part. The plan concedes the same-day contamination itself — *"This morning's
4-of-66 shows a small flag and keeps the number"* — so foreign commits landing in
this repo on 08-26 is the plan's own position, not my inference. Only the mapping
from those 4 commits to those 2,135 lines is inferred.

**What to do instead.** Do not promote `(5)+(6)` to headline until the flat result
has been recomputed against a denominator scoped to the measured machine. That is
a one-off arithmetic exercise on data already in `docs/working-method.md` §11, not
a build. If it survives, headline it. If it does not, the plan's opening sentence
changes and so does the figure in S7, whose caption is currently pre-written:
*"tokens per line is flat; the mix moved."* Do not write that caption before the
number is re-derived.

## 2. BLOCKING — The scorecard renders verdicts on the un-paired half, and would have printed PASS on this morning

**What is wrong.** The pairing rule is a display convention with no structural
enforcement, and the one place the plan permits verdicts routes around it. §1 says:

> **The pair (5)+(6) is a single display unit**

but S2 delivers *"`tokens_per_insertion`, `tokens_per_code_insertion`,
`tokens_per_docs_insertion` properties"* — three independent attributes on
`YieldRow`, any one readable alone. S5 then resolves predictions by metric name
against §1, and the plan explicitly blesses the un-paired case:

> a prediction naming `tokens_per_code_insertion` stays `metric-undefined` VOID
> until S2 lands, which is correct behavior, not a blocker

So an intervention may pre-register against `tokens_per_code_insertion` alone, and
once S2 lands the scorecard resolves it and prints a verdict.

**Evidence.** On the measured days, tokens/code-insertion moves 17.79M/1,127 =
15,785 to 52.80M/7,960 = 6,633 — a **2.38x "improvement"**, larger than the 2.22x
the plan was built to reject, on a day the plan agrees got no more efficient. A
prediction of the form "tokens/code-insertion falls below 10,000" reads **PASS**.
The dashboard's ban on deltas does not help here: §2 excludes *"Any single 'x.xx
better than yesterday' delta"*, but the scorecard's comparison is against a
pre-registered threshold, which the plan permits by design, and a mixture shift
crosses a fixed threshold just as easily as it moves a ratio.

Note also that the delta ban is weak even on the table itself. S6 renders one row
per day; two adjacent rows are a delta the reader computes in their head. Removing
the arrow removes the arithmetic from the page, not from the reader.

**What to do instead.** Make the pair structural, in the resolver and in the row.
Either (a) the scorecard refuses any prediction naming `(6)` unless the same
prediction registers a co-condition on `(5)`, or (b) `(6)` is exposed only as a
composite object that cannot be formatted without `(5)` beside it. Option (b) also
fixes the table. A convention that lives only in a design doc is not a guard.

## 3. BLOCKING — The contamination flag is measured in commits and applied to insertion denominators

**What is wrong.** §4 specifies one flag for all git-denominated metrics:

> Every metric whose denominator comes from git carries a per-day flag: the share
> of that day's commits presumed foreign.

Share of *commits* is a bad proxy for share of *insertions*, and the headline
metrics `(5)` and `(6)` are insertion-denominated. Commit sizes in this repo are
wildly unequal — a docs commit and a one-line fix count the same.

**Evidence.** Take the plan's own case. 4 of 66 commits is a **6% flag**, far below
the *"start at 25%"* dash threshold, so the day renders as a number. If those same
4 commits carry the §11 session's ~2,135 lines, they are **16% of the day's 12,979
insertions** — and, per finding 1, ~18% of the day's true token spend is missing
from the numerator. The guard reports "small flag, keep the number" precisely on
the day whose headline number is wrong. The flag is systematically optimistic in
the direction of hiding contamination.

There is a second, independent version of the same mismatch. `outcomes.py` counts
commits from `git log --all --no-merges` (lines 74-84) but counts added lines from
`git log <branch> --first-parent --numstat` (lines 86-96). The flag's population
(`--all`) is not the population of the denominator it guards (first-parent on the
default branch). The plan never mentions this; §1 metric (3) cites `--all` and
metric (4) cites only *"`--numstat` added lines"*. S1's acceptance check — reproduce
1,127 / 2,931 for 08-25 — may fail for this reason alone, if the hand count used a
different walk than the one it will be built on.

**What to do instead.** Weight the flag by the quantity it guards: for `(5)`/`(6)`,
the foreign *insertion* share, from the same walk that produces the denominator.
Fix the walk mismatch first, or state which walk each metric uses and accept that
`(5)` and `(7)` are ratios over different universes.

## 4. BLOCKING — Metric (9) is an undecomposed aggregate over a session mixture, and it is a headline

**What is wrong.** The plan's rule is universal — *"no decomposable aggregate
appears without its decomposition beside it"* — and `(9)` is decomposable by
session and is not decomposed. The plan even identifies the confound one row
earlier. For `(8)` it lists:

> session-length mix — one marathon drags the main mean with no behavior change

For `(9)` it lists only *"the thresholds are CHOSEN, not discovered"*. The same
mixture is present, one level down: the share of main calls above 300K is a mean
over a mixture of sessions, and adding cheap short sessions dilutes it with zero
change in how any session is run.

**Evidence.** Calls went 146 to 398 between the two days — a 2.7x change in the
population being averaged. The plan calls the result *"the cleanest real signal in
the two days measured"* and headlines it: *"The **headline row** is (5)+(6) as one
unit, and (9)."* No decomposition, no session count, no per-session view, and no
sample-size guard anywhere in the plan — 4% is printed without the n it is 4% of,
against `style-charts.md` rule 8 ("Axis labels get real numbers with real
separators").

**What to do instead.** Decompose by session: the share of *sessions* that crossed
each threshold, or the per-session maximum, beside the call-level share. Print the
counts, not only the percentages. If the decomposition dissolves the 20%→4%
signal, that is the same result the mixture split produced for insertions, and it
belongs on the page for the same reason.

## 5. SHOULD-FIX — The cross-machine argument rejects ingestion for a property the chosen option also has

**What is wrong.** §4's case against ingesting both corpora is:

> a corpus that stopped syncing is indistinguishable from a machine that stopped
> working, which recreates the silent-misalignment failure this task opened with

That is exactly the failure mode of the chosen heuristic. *"A commit whose UTC hour
contains zero corpus calls from this machine is presumed foreign"* fires
identically for a MacBook hour and for an hour where the Windows hook failed to
record — and this repo shipped `session: project_slug never handled Windows paths,
so find_session found nothing` four commits ago, which is that bug, in this
corpus, this week. The plan applies the silent-misalignment objection to the option
it rejected and not to the one it picked. It is not a fatal objection to the flag,
but it means the flag needs a numerator-completeness check beside it, which no
story provides.

Compounding it, **S4's acceptance check is circular**: *"must agree with a hand
count of one day's commits against that day's call hours"* — that hand count is a
manual execution of the heuristic's own definition. It validates the code against
the rule, never the rule against reality. Contrast S1, whose acceptance
(*"passes only if 08-25 shows 1,127 code / 2,931 docs"*) checks against an
independent measurement. S4 has no ground truth and, as designed, can never
acquire one.

**What to do instead.** Ground truth is cheap and does not require the rejected
option: a one-off manual export of the MacBook's session hours for two days costs
no transport channel and no staleness problem. Score the heuristic's false-negative
rate against it before the flag gates any metric. If false negatives are common,
the flag is worse than nothing — it puts a reassuring small number next to a
contaminated one.

## 6. SHOULD-FIX — Two of the "independent" slices are not independent, which is fatal for a packing experiment

**S5 contradicts itself.** §3 defines VOID to include *"denominator contaminated
past the §4 threshold"* — which is S4. S5's story then claims *"Depends on: only
the metrics predictions name — sub ctx/call already exists, so S5 runs today
without S1-S4."* S5 cannot implement its own stated verdict contract without S4.
Either the contamination VOID reason is deferred (say so) or S5 depends on S4.

**S4 is not file-independent from S1 in the way stated.** The story says
*"Depends on: nothing logically; shares outcomes.py with S1 — serialize the file,
not the thinking"*, while its acceptance imports `agent_yield.contamination`. So
either S4 duplicates the per-commit git walk in a new module, or it restructures
the same `_git(repo, "log", ...)` walk in `outcomes.py` that S1 is restructuring
for the path classifier. The dispatch batches put them in *different* batches
({S1,S2} and {S4}), which means concurrently if batches run in parallel.

This matters more here than usual: the plan says this set feeds #35 packing. A
slice labelled independent that in fact serializes on a file merge or duplicates
plumbing inflates the independent arm's measured cost and confounds the packing
result — the same class of error as §11.1's `calls^1.54` fit, which *"conflated
'longer agents cost superlinearly more' with 'agents given bigger tasks cost
more'"*.

**What to do instead.** Hoist the per-commit walk (day, hour, paths, added,
deleted) into S1's deliverable and make S4 and S6 consume it. Then S1, S3, S5 are
genuinely three, and the independence summary is true as written.

## 7. SHOULD-FIX — S7's acceptance check will fail on a correct page, and greps for the wrong leak

The check is:

    agent-yield impact --html out.html && grep -ci "http" out.html; grep -c "scorecard" out.html

with *"first grep must print 0 — no external URL in a page that is supposed to have
none"*. Any inline SVG carries `xmlns="http://www.w3.org/2000/svg"`, and a charset
meta tag may carry `http-equiv`. Neither is an external fetch; both match. The
check either fails on a correct page or gets "fixed" by stripping a namespace and
breaking the SVG.

It also greps for the wrong thing. The leak this repo actually caught, per
`working-method.md` §11 lines 393-397, was *"an account name leaking through a
helper written to keep home directories out of a page"*. The page is built on a
Windows box whose paths contain the user's account name.

**What to do instead.** Match external schemes excluding the SVG namespace, and
add a grep for the account name and home-directory prefix. Both still print one
line each. Every other story's acceptance does print under ten lines as claimed,
with one caveat: S3's command carries the parenthetical *"(exact loader spelling to
match the existing CLI's ingestion path)"*, i.e. it is not yet a runnable command.
Resolve the import before dispatch.

## 8. SHOULD-FIX — Deletions are missing entirely, and the confound the plan names is handled nowhere

Metrics (4)-(6) count added lines only, inheriting `outcomes.py`'s `added` field.
The plan names the consequence — *"days whose work is deletion or review (a
valuable negative-LOC day divides by ~0)"* — and then specifies no dash rule, no
floor, and no churn column. A refactor day that deletes 2,000 lines and adds 500
renders as a spike in the headline metric, on a table the plan intends to be read
as a series. There is no minimum-denominator guard anywhere in the plan, for any
metric.

**What to do instead.** Carry deleted lines from the same `--numstat` walk (it is
column two, already parsed past). Dash `(5)`/`(6)` below an insertion floor, pinned
as a constant beside `CONTAMINATION_VOID`, and label it CHOSEN as §4 does.

## 9. SHOULD-FIX — The dashboard cannot score the levers the repo actually has

Every surviving quantitative claim in §11 is session- or agent-scoped, and no §1
metric can express any of them:

- Lever 2's trigger is *"context/call having doubled from the session's opening
  calls"*. A daily mean over sessions cannot detect within-session doubling.
- §11's own falsification bullet asks to *"Measure the first ten calls of a fresh
  session against the last ten of the one it replaced."* Not computable from (8).
- §11.1's replacement claim is *"a split costs ~19,800 tokens per extra agent
  before any work happens"* — a per-agent first-call context, visible in the
  corpus, and absent from the metric set.

The plan sees this and defers it: §6 says if everything VOIDs, *"the honest rebuild
is per-session, and the daily join was the wrong call, not merely early."* It is
already knowable that the daily grain cannot score two of the three levers, so the
two-week wait buys nothing.

**What to do instead.** Put one session-grain metric in v1 — per-session opening
versus closing context/call, and per-subagent first-call context — before, or
instead of, the daily table. These are the numbers a reader can act on: restart, or
don't split. Contrast the headline `(5)`: at 4,232 versus 4,068 there is no action a
reader takes either way. It is a control, which is a legitimate role, but a control
is a poor headline.

## 10. NOTE — Metric (7) is specified but no story renders it

§1 says tokens/commit is *"always rendered with the contamination flag"*, but S6's
row is *"tokens, calls, commits with flag, the (5)+(6) pair, main/sub ctx-per-call,
≥300K share"* — no tokens/commit — and S7 does not mention it. Meanwhile S5's
resolver will happily resolve a prediction naming it. A metric that the scorecard
can name and no view shows is a VOID generator at best. Build it or delete it from
§1.

## 11. NOTE — Chart specification gaps against style-charts.md

S7's mixture figure is *"per-day area-split insertion bars with the tokens/insertion
pair as geometry"* — two units on one canvas, carrying two clauses (*"tokens per
line is flat; the mix moved"*). Rule 3 says a figure carrying two messages is
usually one figure and a paragraph; decide which clause the geometry proves and
demote the other. Rule 9 ("Interactive means the reader can interrogate it" — every
figure shows the underlying pair on hover) is not mentioned in S7's spec at all.
The plan's handling of rules 6, 7 and 10 (threshold lines as drawn null
hypotheses, reserved state colours, measured-versus-chosen labels) is exemplary and
should be kept as-is; the observation that *"the 30,000 line under the subagent
ctx/call series sitting at 48,480 is the brief-pack scorecard row, as geometry"* is
the best sentence in the document.

## 12. NOTE — Scope: this is three to four times the plan the question warrants

Seven stories, three new modules (`contamination.py`, `scorecard.py`, plus a CLI
command), a four-state verdict engine with a metric-name resolver, a terminal table
and an HTML section — to characterize **two days on one machine** with three
registered interventions, one of which is retracted. The plan's own instrument test
needs *"~10"* resolved interventions before the scorecard can be judged; there are
three.

The smallest thing that answers the question is **S1 + S3 plus deletions**, rendered
into the existing `render_table` and `report_html`. That is two stories, no new
modules, and it produces both decompositions the plan cares about. Defer S4 (a
heuristic that cannot be validated as specified — finding 5), S5 (an engine for
three rows, two of which are already known), and S6 (a second table rendering what
`render_table` already renders).

This is not "do not build it". It is: the decomposition rule is the valuable thing
in this document, it costs two stories to apply, and the remaining five stories are
where the plan stopped applying it to itself.
