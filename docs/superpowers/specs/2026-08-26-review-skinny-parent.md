# Review: "Skinny the parent"

**Verdict: RETHINK.** The plan picks the right target and correctly refuses to
put `Workflow` inside #33's arms, but its headline case is arithmetic of exactly
the shape that has failed twice here — and worse than the plan admits: the 28x
asymmetry compares the reading parent's *marginal* re-billing against the baton's
*absolute* one-shot cost, with the baton parent's own carry, the baton's brief
output, and arm B's own children all set to zero. Corrected on the plan's own
numbers it is ~6.5x, which is the 6.2x §11 predicted before measuring 1.07x. On
top of that, S0 writes the unmeasured design into §12 two slices before #33 runs
— the exact path lever 1 took into policy — arm B is specified in five words
against arm A's seven relay rules, and the retraction bar is stated to a 0.95x
precision that an n=1 experiment cannot resolve when §11.1's own same-arm
replicates differed by 30%. None of this says the baton is wrong. It says the
plan cannot currently tell you whether it is.

---

## 1. BLOCKING — the 28x is not a hypothesis, it is a units error, and correcting it lands on the last failed prediction

**What is wrong.** The plan's §1 consequence 1:

> 68,047 of parent growth carried over 100 more calls is ~6.8M; twelve child
> re-entries are ~238K. Any mechanism that trades one-shot child cost for
> permanent parent weight wins on this asymmetry or not at all.

The left side is a *marginal* quantity re-billed over 100 calls. The right side
is an *absolute* one-shot. They are not comparable, and three terms are missing
from the baton's side of the ledger:

- **The baton parent's own carry.** The plan budgets 400–800 tokens/step, "8,000
  over the run" (§6 `expect`). Carried over the same 100 subsequent calls that
  the 6.8M assumes, that is **800K**, not zero.
- **Brief-writing output.** The plan lists it as a cost — "the child's
  brief-writing output, unmeasured, at ~5x output pricing" — then omits it from
  the comparison. The spec is blunt about the stakes: "If a brief costs more than
  the parent growth it prevents, the baton is a worse trade wearing a better
  one's clothes, and this document is wrong."
- **Arm B's children.** Arm B is "the §11 shape, deliberately" — and §11's shape
  is a *dispatching* parent: "seven agents and 76 calls were 19%" of 3.5M, i.e.
  ~665K that the reading parent pays and the plan charges to nobody.

Doing it symmetrically on the plan's own figures: baton ≈ 238K re-entry + 800K
carry + unmeasured brief output ≈ **1.04M and rising**, against 6.8M. That is
**~6.5x**, not 28x — and 6.5x is indistinguishable from the **6.2x §11 predicted
before it measured 1.07x**. The plan's own admissible range makes this worse: the
retraction bar tolerates parent growth up to 25,000 without retracting, and
25,000 x 100 calls + 238K gives **~2.5x**. On the plan's own numbers the design's
passing band spans 2.5x–6.5x while its headline advertises 28x.

**The measured/inferred line, held.** What is measured: the parent went
58,475 → 126,522 context/call (§11); the parent was 81% of a 3.5M session;
re-entry is ~19,800 (n=4, one run, #34 open). What is *inferred*: that the 68,047
delta is **removable**. It is not removed by the baton — it is relocated to
children who read the same material and re-pay ~19,800 each to arrive. The only
thing the baton removes is the *re-billing* of those reads on later parent calls.
So §3's reason 1, "it is the only mechanism aimed at the 55.4%," is not an
independent argument; it is the asymmetry claim restated. The entire case reduces
to the one unmeasured term.

**What to do instead.** Rewrite the asymmetry with both sides symmetric and both
arms' children counted, and publish the corrected factor (~6.5x, plus the
unmeasured brief-output term) as the plan's headline. Then note that the
corrected factor is the same magnitude §11 got wrong by 6x, and let that set the
prior. Do not carry 28x into `interventions.toml`, NEXT.md, or any summary.

---

## 2. BLOCKING — the bar can fail, but it cannot resolve: n=1 against a 0.95x threshold

**What is wrong.** Credit first: `retract = "Arm A >= 0.95x arm B"` is a real kill
switch, it mirrors §11.1's structure, and the plan deliberately predicted 0.70x
rather than 28x. That part is honest. The problem is precision, not courage.

§11.1 is the repo's own evidence that a single run of an arm is not a number: the
two single-agent replicates came in at **282,568 and 217,321 — a 30% spread
within one arm** — and §11.1 says the control that produced that second replicate
"is what keeps this a FAIL rather than a VOID." This plan runs **one** arm A and
**one** arm B (S4: "same task class, arm A baton / arm B reading parent"). A
0.95x retraction threshold sits inside the noise floor the repo has already
measured on itself. Whether the recommendation survives would be decided by
variance.

Three further gaps:

- **The 0.70–0.95 survival band has no floor.** "If arm A lands between 0.70x and
  0.95x, the recommendation survives narrowed." A 0.94x result — a 6% saving,
  well inside the 30% same-arm spread — leaves the recommendation standing.
- **The expect and retract clauses do not span.** Arm A at 0.80x with the
  seeded-ASK step failing to return ASK: `expect` is violated, no `retract` clause
  fires. Parent growth of 15,000 over the run: same. There is a 3x band
  (8,000–25,000) of tolerated failure between the prediction and the retraction,
  and this repo's record is that discretion zones resolve in the mechanism's
  favour.
- **The quality clause cannot fire on the defect class it exists for.** "Any
  slice failing or never run in arm A that arm B ships green" — neither of §11's
  two catches would trip that. A `commits` column dropped to meet a width budget
  passes its own slice's test; a leaked account name in a helper passes every test
  in the suite. The quality falsifier is scoped to a defect class the record does
  not document, and blind to the one it does.

**What to do instead.** Run two replicates per arm before the threshold means
anything, and state the observed same-arm spread as the resolution limit — if the
spread is 30%, a 0.95x bar is not a bar and the threshold has to move to
something the experiment can see. Make the bands span: every outcome outside
`expect` must map to retract, narrow, or void, with no undefined region. Add a
quality clause that can fire on a cross-cutting defect which passes all slice
tests.

---

## 3. BLOCKING — S0 and S3 adopt the practice before the number that is supposed to justify it exists

**What is wrong.** The plan says "Nothing in this plan is believed until #33's
end-to-end number exists — including this plan," and then sequences:

- **S0**: "Adopt the relay rules as a §12 amendment" — deps: **none**. First slice.
- **S3**: "Hand-run baton pilot (#36 executed): one small real task... state file
  committed per step" — "no (real work ships)".
- **S4**: #33, the measurement. Fourth.

So the normative operating rubric is amended, and real work ships under the
unvalidated shape, before the measurement runs. The source spec's closing line is
the direct instruction against this: "**Do not build from it yet.**" And the repo
has run this exact play before — §12's own part (b) carries the scar tissue: "The
cap has been policy since and policy did not hold," retracted by §11.1.

Calling S0 "practice-only" does not help. §12 is the document the parent's
behaviour is read out of; writing seven relay rules into it is adoption, and
§11.1 shows what un-writing costs. S2 compounds it — a fixture drill of the
hardening of a mechanism not yet shown to be worth having.

**What to do instead.** Invert: pre-register (S1) first, measure (S4) second,
amend §12 (S0) only in S6 alongside the verdict, and phrase the amendment in
terms of the measured factor. The relay rules can live in the run's own brief for
the duration of the experiment without entering the method doc. Drop S2 until
after S4 — hardening an unvalidated mechanism is work spent on the wrong side of
the decision.

---

## 4. BLOCKING — arm B is five words, arm A is seven rules

**What is wrong.** §4 specifies arm A exhaustively: "baton practice — relay
parent, child-written briefs, shell verification, one end-of-run read," plus S0's
constant dispatch prompt, grep-derived range, header integrity diff, `diff --stat`
check, seeded-ASK. Arm B in full: "**the §11 shape, deliberately.**"

That is not a control, it is a re-enactment, performed by the operator who wrote
and believes arm A. Arm B's total is dominated by a single free parameter — how
much the parent chooses to read — and nothing in the plan constrains it. Does arm
B batch tool calls (§12 rule 3)? Restart when context/call doubles (lever 2)?
Aggregate through the shell (rule 2)? If not, the experiment compares a hardened
design against deliberate sloppiness and the result is unusable in either
direction.

Two more design gaps in the same section:

- **"Same task class," not the same task.** §11's limits paragraph names this as
  the flaw in its own headline: "The split is by wall-clock phase, and the two
  phases did not ship the same kind of work — which is why tokens/line is reported
  next to tokens/issue rather than instead of it." §11.1 fixed it and the repo has
  the template: "Identical per-unit instructions, identical output schema,
  identical return contract, same subagent type." The plan reaches for the weaker
  standard §11 already apologised for.
- **Order effect, unaddressed.** Whichever arm runs second is run by someone who
  now knows the task. The plan has no mitigation and does not mention it.

**What to do instead.** Write arm B's protocol to the same length as arm A's, and
make it the *disciplined* reading parent — §12 rules 2, 3 and 4 applied — so the
comparison is reading-vs-relaying and not discipline-vs-none. Use one identical
task, run in both arms, replicated, with arm order counterbalanced or recorded as
an explicit limit.

---

## 5. BLOCKING — `Workflow` is reasoned about from the ticket text and then sequenced after the hand loop it was meant to precede

**What is wrong.** NEXT.md #39 is explicit: "**Evaluate before #36 writes a parent
loop by hand.**" The plan's S3 *is* #36 executed by hand, and the evaluation is
S5, two slices later and dependent on S4. The instruction is reversed.

§2b is a fair-minded write-up, and its costs section makes one genuinely good
argument — that putting `Workflow` inside arm A is "a second untested variable in
an experiment that exists to test the first." That argument is correct and I
endorse it. But it is an argument against `Workflow` **in #33's arms**, not
against **evaluating** it first, and the plan uses it for both. That is where the
evaluation becomes a dismissal: two questions are conflated and only one is
answered.

The plan's own text shows why the order matters. §2b concedes `Workflow` is
"strictly better loop mechanics than any model-run parent, *if it works as
documented*," and that under it "the per-step parent turn (the baton's 400–800
tokens...) goes to zero." If that holds, S0's relay rules — the constant dispatch
prompt, the grep-derived range, the hand verification — are dead text the day S5
lands, and the plan will have written them into §12 six slices earlier. The cost
of finding out is one dispatch on a throwaway task; the plan spends seven slices
avoiding it.

**What to do instead.** Run a cheap smoke test of `Workflow` — does
`agent(prompt, {schema})` work as documented on this repo, what does a schema
retry cost — **before** S0, and let the answer decide whether the hand relay
layer is worth codifying into §12 at all. Keep `Workflow` out of #33's arms; the
plan is right about that and the confound reasoning should stand as written.

---

## 6. SHOULD-FIX — the answer to the blind parent is underpriced by roughly an order of magnitude, and mistimed

**What is wrong.** §3's structural answer:

> the parent reads the full `git diff` exactly once, at DONE, before accepting
> the run: a fixed 2–5K cost replacing a per-step cost, preserving the defect
> class at ~5% of the old price.

Two problems.

**The price.** §11's dispatching phase added 1,812 lines. A full `git diff` of a
multi-step run at that scale is 20K+ tokens, not 2–5K — the estimate looks like it
was made for a diff the size of one step's. §11 itself describes the shape as "a
handful of calls, not forty," which is not one 2–5K read either. Since this read
"is included in arm A's token total," the understatement flows straight into the
#33 number.

**The timing.** The plan asserts "per-step reading is not what caught them;
reading *across* the work was." Half true. §11's first catch is a `commits`
column "one agent dropped to meet a width budget **while a sibling was adding a
metric built on it**" — caught in flight, while the sibling work was live. An
end-of-run read finds it after eleven further steps have been built on the
dropped column. The cost of a late catch is not the read; it is the rework, and
the plan prices only the read.

The plan also does the thing it criticises. §2c dismisses shell aggregation as
"Goodhart with a 15-token budget," then §3 and §6 lean on per-slice test commands
as the primary quality instrument — for a defect class that passes every test.

**What to do instead.** Price the end-of-run read from a real diff of comparable
size before putting it in arm A's budget. Add at least one mid-chain
cross-cutting check — the header's `## invariants` block re-verified against the
work so far is the cheap version — so a dependency break is caught while it is
still cheap, and charge it honestly. If the cross-cutting read cannot be made
cheap, that is a finding about the design, not a line item to shrink.

---

## 7. SHOULD-FIX — the seeded ASK is a positive control, not a falsifier, and the plan deletes the only signal that would catch quiet guessing

**What is wrong.** The plan is right that "zero ASKs is evidence" was
unfalsifiable and gameable. Its replacement:

> one step's brief per run is written deliberately ambiguous, and the child is
> expected to return ASK on that step specifically. Unseeded steps carry no ASK
> quota.

A seeded probe can only confirm the mechanism fires when triggered. It can never
detect the failure the spec actually worries about — "the default behaviour of a
capable model handed an ambiguous task is to resolve the ambiguity silently and
keep going" — because that happens on *naturally* ambiguous briefs, which are
exactly the unseeded steps the plan has just exempted from any expectation. The
old falsifier was unfalsifiable; the new one is a non-detector.

**What to do instead.** Keep the seeded probe as a positive control, and add a
detector for silent resolution: for each unseeded step, diff the brief's named
scope against what the child actually touched (`git diff --stat` vs the brief's
file list is already in S0) and record any step that went outside scope without
asking. Mechanical, costs nothing the plan is not already spending, and can
actually fire.

---

## 8. SHOULD-FIX — "batch fat" and ">=8 steps" pull against each other and can void the prediction

**What is wrong.** §3 reason 4: "the step count — and with it the re-entry bill —
is minimised by construction." §6 `expect`: "Arm A (baton, **>=8 steps**) totals
<= 0.70x arm B." The plan's own design pressure drives the run below the
threshold at which its prediction is defined. If the pilot task packs into 5
steps, the prediction does not apply and the run is uninterpretable — a
self-voiding condition with no stated handling.

**What to do instead.** Fix the step count as a protocol parameter of the
experiment (as #35 fixed the slice set and varied only packing), or restate the
prediction per-step so it holds at any step count.

---

## 9. NOTE — 81% and 55.4% are different datasets presented as one budget

**What is wrong.** The opening: "The parent is 81% of a 3.5M-token session and
55.4% of gross main-thread growth is the parent reading things itself." The 81%
is the single 2026-08-26 macOS session (§11). The 55.4% is five archived
dispatch-heavy sessions whose sanity check **failed** — "attributed additions sum
to ~2x the session's net growth" — and whose per-interval split is
"proportional-by-character, which is a guess at token counts." Adjacent
presentation implies the 55.4% decomposes the 81%. It does not.

The §1 table then labels A "share 55.4%" and answers "practice can remove it?"
with "**Yes.**" That converts an indicative share of gross additions on a
selected sample into a removable line item on this run. The caveat sentence is
present and honest; the table overrides it.

**What to do instead.** State the two numbers as what they are — one session's
parent share, and an ordering (not a magnitude) from five other sessions — and
replace "Yes" in the removability column with "the hypothesis under test."

---

## 10. NOTE — the plan is about twice the size the question warrants

Seven slices, a §12 amendment, a fixture drill, a pilot, a two-arm measurement, a
second measurement and a verdict doc, to answer "does relaying instead of reading
save tokens end to end." The actionable content of the practice is one sentence.

The minimal honest version is four steps: (i) smoke-test `Workflow` (finding 5),
(ii) pre-register with a bar the experiment can resolve (finding 2), (iii) run one
identical task in both arms, replicated, with arm B specified (finding 4), (iv)
amend §12 only after, in terms of the measured factor (finding 3). S2 goes away
until there is something worth hardening; S0 moves to the end; S5 moves to the
front and shrinks to a probe.

"Do not build this; change the practice for one task and measure" remains
available and is close to what is left after the above.

---

## What is right, and should survive the rewrite

- Refusing to put `Workflow` inside #33's arms is correct, and the confound
  reasoning in §4 is the best-argued part of the plan.
- Predicting 0.70x rather than 28x, and saying why, is the right response to two
  retractions.
- Separating "loop-attributable parent growth" from total session growth is
  correct — the 33.2% conversation share would flatter or damn at random.
- Recording "the baton saves nothing at this task size" as a legitimate outcome in
  advance, per the #22 precedent, is exactly right and should be kept verbatim.
- Naming its own riskiest assumption honestly is why this review could be
  specific. The finding is that the assumption is worse than stated, not that it
  was hidden.
