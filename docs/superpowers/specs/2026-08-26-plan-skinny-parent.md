# Skinny the parent: the plan

**Recommendation up front: run the baton practice, hand-operated through the
ordinary Agent tool, as arm A of #33 — and evaluate `Workflow` in a separate,
single-variable comparison afterwards, not inside the first measurement.**
The parent is 81% of a 3.5M-token session and 55.4% of gross main-thread
growth is the parent reading things itself. That is the only large removable
line item, the baton is the only mechanism that removes it without confounding
#33, and everything else in this plan is scaffolding around that one move.

Planning only. No code, no branches, no repo changes are proposed before the
slices below say so, and three of the seven slices are practice-only.

---

## 1. Where the parent's context actually goes

The budget, from the five-session attribution in the baton spec (shares of
*gross* additions, proportional-by-character — the ordering is sound, the
percentages indicative, and the gross-vs-net caveat travels with every number
below):

| line item | share | practice can remove it? |
|---|---|---|
| **A. The parent's own reads** — every diff, every suite run, every file it opened to author a brief | 55.4% | **Yes.** This is the whole target. §11 measured it directly: 58,475 → 126,522 context/call in one phase, because the parent read and ran everything itself. |
| **C. The conversation itself** — assistant text, dispatch prompts, system reminders | 33.2% | **Mostly structural.** A constant ~60-token dispatch prompt trims the dispatch share; the rest is only touched by restart (lever 2, standing) or by moving the loop out of model turns entirely (`Workflow`, §3). No dispatch discipline reaches it. |
| **B. Child return payloads** | 11.4% | **Bounded, already small.** The two-line return contract caps it. It was never the expense — designs aimed at B are aiming at the smallest slice. |
| **Per-call re-billing** — system prompt, tool schemas, and all of the above re-read on every API call | a multiplier, not a line item | Structural. Batching (§12 rule 3) and restart are the only levers; the measured habit was 0.97 tool calls per API call *while knowing the lever*. |

Two consequences the mechanisms below must answer to:

1. **The asymmetry is the whole economic case.** A token the parent absorbs is
   re-billed on every later parent call; a token a child spends is paid once
   and discarded. 68,047 of parent growth carried over 100 more calls is ~6.8M;
   twelve child re-entries are ~238K. Any mechanism that trades one-shot child
   cost for permanent parent weight wins on this asymmetry or not at all.
2. **Per-call arithmetic has predicted the wrong sign twice** (§11: 6.2×
   predicted, 1.07× measured; Part E: ≥1.5× predicted, 0.65× measured). The
   28× figure above is therefore a hypothesis. Nothing in this plan is believed
   until #33's end-to-end number exists — including this plan.

---

## 2. The mechanisms, compared

### 2a. The baton (child writes the next brief, returns a pointer)

- **Removes:** line item A almost entirely — the parent never comprehends the
  work; it relays a line range, verifies one verdict through the shell, and
  holds three values of state. Bounds B to two lines. Per-step parent growth
  budgeted at 400–800 tokens all in, flat in the size of the step.
- **Costs:** ~19,800 tokens of re-entry per step (fixed — one number from one
  run; #34 is open on whether it generalises); the child's brief-writing
  output, unmeasured, at ~5× output pricing; serial by construction.
- **Fails when:** the child under-writes the state file; the line-range relay
  is wrong and the parent, blind by design, relays garbage; decomposition
  drift walks the chain somewhere plausible and wrong; or the blind parent
  misses the cross-cutting defects §11's lever 3 caught. The review names the
  hardening for the first three (range taken from `grep -n '### next brief' |
  tail -1`, never from the child's report; header diffed against git before
  each dispatch; `git diff --stat` checked against the brief's named files).
  The fourth gets a design answer in §4.

### 2b. `Workflow` (#39, the harness's orchestrator)

- **Removes:** the loop itself from model context. `agent(prompt, {schema})`
  validates the child's return at the tool layer and retries on mismatch —
  the two-line contract stops being a request. Deterministic control flow runs
  as code, so the per-step parent turn (the baton's 400–800 tokens, which
  live in line item C) goes to zero: strictly better loop mechanics than any
  model-run parent, *if it works as documented*.
- **Costs:** it does not dodge re-entry (#39 says so explicitly); schema
  retries re-bill the child's context invisibly; the control flow must be
  written before the work is understood; and it is **unevaluated on this
  repo** — adopting it inside the first end-to-end measurement is a second
  untested variable in an experiment that exists to test the first.
- **Fails when:** the deterministic script meets a step that needs judgment.
  Lever 3's two catches were judgment, and a script has no judge unless it
  escalates — which reintroduces a reading parent at exactly the moments that
  matter.

**On #36, plainly: it is not obsolete.** #36 was already "as a practice, no
code" — it forswore the subcommand from the start. What #39 obsoletes is any
future *codification* of the parent loop: if `Workflow` validates in slice S5,
the loop never becomes agent-yield code, because the harness already ships it.
Until S5 runs, #36's hand-run practice is not a rival to `Workflow` — it is
#33's instrument, the only way to run arm A without confounding the result.

### 2c. Shell-side aggregation alone

- **Removes:** the verification portion of A — `pytest -q | tail -3`,
  `git diff --stat | tail -1`, `grep -c`; ten lines instead of a thousand,
  essentially free.
- **Costs:** nothing measurable.
- **Fails when:** the parent still reads to *author* and to *comprehend*,
  which is most of A. And aggregation only checks what the command names —
  Goodhart with a 15-token budget, per the review's mode 6.
- **Verdict:** not a rival; a component. Every other option contains it. Alone
  it trims A's edge and leaves its body.

### 2d. Do nothing

- **Removes:** nothing. The parent stays at 81%, context/call keeps doubling,
  restarts keep paying re-read costs.
- **Costs:** the measured baseline — and it is the only option that ships the
  lever-3 catches for free, because the parent reads everything.
- **Fails:** already measured failing (§11's null result, §6's falsifier
  fired). But it is the control arm, and it must be run as one.

---

## 3. The recommendation, argued

**The baton practice, hardened per the review, dispatched through the ordinary
Agent tool, hand-operated — as arm A of #33.**

Four reasons, in order of weight:

1. **It is the only mechanism aimed at the 55.4%.** Shell aggregation trims
   verification reads; return contracts trim the 11.4%; only "the parent never
   comprehends the work" removes the parent's own reading, and the reconciled
   spec is explicit that the design should be argued on that number.
2. **It is the only arm that keeps #33 clean.** #33 compares a baton run
   against a reading parent. Both arms must dispatch identically (see §5).
   `Workflow` in arm A would change the relay discipline *and* the loop engine
   at once — and this repo has retracted two levers for exactly that kind of
   uncontrolled arithmetic.
3. **The asymmetry argument survives Part E; nothing else about the baton
   does unmeasured.** Re-entry per step is real and paid once; parent growth
   is paid on every subsequent call. The 28× is a hypothesis, but it is the
   *right* hypothesis to spend one experiment on, because it is the one thing
   the Part E retraction explicitly left standing.
4. **Slice thin, batch fat is already folded in** (#35, protocol and
   prediction recorded). A baton step is not one slice; it is as many
   adjacent, dependency-free slices as one child can carry, verified per
   slice through the index's test commands. Re-entry is charged per agent,
   not per slice, so the step count — and with it the re-entry bill — is
   minimised by construction, not by a cap.

`Workflow` is not rejected; it is sequenced. If it validates in S5 it becomes
the loop engine and the per-step parent cost drops from 400–800 to ~0 — a
better skinny than this plan's arm A. But that is a second measurement, after
the first one exists.

### Keeping the parent from being blind (constraint 2)

The failure §12 names — a parent that never reads ships worse work — gets two
structural answers, not a hope:

- **Per-slice test commands, both arms.** Quality is scored the way #35
  scores it: pass, fail, or never run, per slice. A skipped slice is visible.
- **One bounded cross-cutting read at chain end.** The two lever-3 catches
  were cross-cutting (a dropped column a sibling depended on; a leaked account
  name) — per-step reading is not what caught them; reading *across* the work
  was. So the parent reads the full `git diff` exactly once, at DONE, before
  accepting the run: a fixed 2–5K cost replacing a per-step cost, preserving
  the defect class at ~5% of the old price. This read is part of the practice,
  is included in arm A's token total, and if the catches it enables don't
  materialise while its cost does, it is the first thing to cut.

---

## 4. The confound, and how the measurement avoids it (constraint 4)

NEXT.md's warning: if #33's arms use different dispatch mechanisms, the result
is confounded. The design that avoids it is two comparisons, each varying one
thing:

**Comparison 1 (#33 proper): reading discipline.** One task class, two arms,
both dispatching children through the ordinary Agent tool, same model, same
repo, same slicing.
- Arm A: baton practice — relay parent, child-written briefs, shell
  verification, one end-of-run read.
- Arm B: reading parent — the §11 shape, deliberately.
- Measured: total tokens end to end, per-arm; parent growth attributable to
  the loop (not total session growth — the 33.2% conversation share accrues
  either way and would flatter or damn at random); per-slice test outcomes.

**Comparison 2 (#39 evaluation): loop engine.** Arm A's task re-run under
`Workflow`, holding the state-file protocol, briefs, and slicing fixed. The
only variable is who runs the loop. This is where "#36's loop becomes code
never" gets decided.

What #34 does and does not block: the end-to-end totals in comparison 1 do not
need the re-entry decomposition, so #34 does not block #33. It blocks
*interpreting* the gap — without it, "re-entry ate the savings" and "briefs
ate the savings" are indistinguishable. Run #33 regardless; caveat the
attribution until #34 lands.

---

## 5. The stories (constraint 5)

Each slice independently checkable; acceptance is a shell command printing
under ten lines. "Practice-only" means documentation and fixtures, no shipped
code — #36's own rule: no subcommand for an unvalidated shape.

| id | slice | acceptance check | deps | practice-only |
|---|---|---|---|---|
| S0 | **Adopt the relay rules as a §12 amendment**: constant dispatch prompt, two-line return, grep-derived range (never the child's report), header-vs-git integrity diff, `diff --stat` vs named files, seeded-ASK (replacing the unfalsifiable falsifier 5), one bounded end-of-run read | `grep -c 'EXACTLY two lines' docs/working-method.md` → prints `1` | — | **yes** |
| S1 | **Pre-register #33 in `interventions.toml`** with the `expect=` and retraction bar from §6, before either arm runs | `grep -n 'skinny-parent' interventions.toml \| head -4` | S0 | **yes** |
| S2 | **Fixture drill of the mechanical catches**: a scratchpad state file with a deliberately wrong NEXT range and an edited header; confirm the grep-range and git-diff catches fire | `grep -n '### next brief' <fixture>.md \| tail -1` → one line, the true range, disagreeing with the planted NEXT | S0 | **yes** (fixture in scratchpad, nothing shipped) |
| S3 | **Hand-run baton pilot** (#36 executed): one small real task, 3–6 steps, Agent-tool dispatch, state file committed per step under `.agent-yield/baton/` | `grep -c '^## step' .agent-yield/baton/<run>.md` → ≥ `3`; `git log --oneline -3 -- .agent-yield/baton/` → 3 lines | S0, S2 | no (real work ships; still no agent-yield code) |
| S4 | **#33, both arms**: same task class, arm A baton / arm B reading parent, both Agent-tool dispatch; totals and per-slice test outcomes written to a dated doc under `docs/` | `sed -n '1,8p' docs/33-endtoend-<date>.md` → the two-arm totals table | S1, S3 | no |
| S5 | **#39 evaluation**: arm A's task under `Workflow`, briefs and protocol held fixed; decides whether the loop is ever codified (expected answer: never — the harness ships it or the hand practice stands) | `sed -n '1,8p' docs/39-workflow-<date>.md` → engine-vs-hand totals table | S4 | no |
| S6 | **Verdict recorded**: adopt, retract, or narrow, written into working-method.md and NEXT.md the way §11.1 recorded lever 1 | `grep -n 'skinny-parent' docs/working-method.md \| head -3` | S4 (S5 informs, does not block) | **yes** |

The seeded-ASK from S0, made concrete for S3/S4: one step's brief per run is
written deliberately ambiguous, and the child is expected to return ASK **on
that step specifically**. Unseeded steps carry no ASK quota. This replaces
"zero ASKs is evidence" — which the review showed was both unfalsifiable and
gameable — with a scoreable probe.

---

## 6. The pre-registered prediction, with a retraction bar (constraint 6)

In the `interventions.toml` style, recorded at S1 before either arm of S4 runs:

```toml
[skinny-parent-33]
date    = "2026-08-26"
expect  = """
Arm A (baton, >=8 steps) totals <= 0.70x arm B (reading parent), end to end,
child tokens included. Parent growth attributable to the loop in arm A:
<= 800 tokens/step, <= 8,000 over the run. Seeded-ASK step returns ASK.
Every slice's test command passes in both arms.
"""
retract = """
Arm A >= 0.95x arm B: the asymmetry does not pay at this task size; withdraw
the recommendation and record it beside lever 1.
Any slice failing or never run in arm A that arm B ships green: SS12's own
falsifier has fired -- the blind parent ships worse work -- and the
recommendation is withdrawn on quality regardless of the token ratio.
Parent growth > 25,000 over >=8 steps: the relay is leaking; the design is
wrong as specified even if the total happens to win.
"""
```

The 0.70× is deliberately far below the asymmetry arithmetic's 28×, because
per-call arithmetic has predicted the wrong sign twice and the honest prior
after §11 and Part E is "the fixed costs are bigger than you think." The
0.95× retraction bar mirrors §11.1's structure: a prediction the result can
actually kill. If arm A lands between 0.70× and 0.95×, the recommendation
survives narrowed — record the measured factor, not the predicted one.

Two outcomes are recorded as legitimate in advance, per the #22 precedent:
- **"The baton saves nothing at this task size"** — then the parent's skinny
  is restart (lever 2) plus shell aggregation, and the 55.4% is carried, not
  removed. That is a real result, not a failure of the experiment.
- **"`Workflow` beats the hand-run loop"** (S5) — then the practice's relay
  layer retires the day the engine validates, and this plan's arm A was the
  control that made that conclusion clean.

---

## Files this plan rests on

- `C:\Users\ewehm\repos\agent-yield\docs\working-method.md` §11, §11.1, §12
- `C:\Users\ewehm\repos\agent-yield\docs\superpowers\specs\2026-08-25-baton-design.md`
- `C:\Users\ewehm\repos\agent-yield\docs\superpowers\specs\2026-08-25-baton-review.md`
- `C:\Users\ewehm\repos\agent-yield\docs\NEXT.md` (tickets #33–#41)

Named but not read, per the brief's boundary: `interventions.toml` (S1 edits
it; its loader's exact schema should be checked at execution time, not
guessed here), and `docs/attribution-2026-08-25.md` (the full method behind
the 55.4/33.2/11.4 split, cited via the baton spec's summary).
