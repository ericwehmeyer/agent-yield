# Baton review: the fork, then the holes

**Status: review of 2026-08-25-baton-design.md, dispatched fork decided.**

---

## Verdict: the child writes the next brief

Line 204 has the premise backwards. The child that just finished step N is the
**best**-informed author of step N+1's brief, not the least: it holds the goal
and invariants (lines 1-20, re-read every step), its own brief, and — uniquely,
in the whole system — the actual state of the work it just touched. The parent
holds twelve words. "Least-informed" describes the parent at authoring time,
and parent-writes hands authorship to it.

Parent-writes has no version that survives its own arithmetic:

- **If the parent authors from the <=12-word verdict alone**, it is inventing
  sed ranges, file paths, and a goal decomposition from twelve words. That is
  drift by construction, worse than anything telephone drift can do.
- **If the child returns enough detail to author from**, that detail lands in
  the parent's context permanently — which is child-writes with the brief
  laundered through the return payload, minus the flat parent.
- **If the parent reads the state file or the repo to author**, it is the
  reading parent §11 measured at 81% of the session. The design's reason to
  exist is gone.

The cost objection cuts the other way once you price where each token lives. A
~50-line brief is roughly 600-700 output tokens (guess; nobody has measured it,
as the draft admits at line 168), paid **once**, in a context that is then
discarded. Every token parent-writes adds to the parent is re-read on every
subsequent parent turn for the rest of the run — the multiplicative
accumulation behind §11's calls^1.54 fit. At 5x output pricing, one-shot child
output still beats compounding parent input for any chain longer than a few
steps.

The header anchor (lines 135-138) is half-sufficient, and that is the "it
depends" line stated plainly: the header pins **what the goal is** but not
**whether the step trajectory still sums to it**. No context in the system ever
holds both the goal and the full work history, so decomposition drift — skipped
work, doubled work, a plausible dead-end pursued for four steps — is invisible
until termination. What makes that survivable is not the header; it is the
header's `done means` **as a shell check**. A machine-checkable termination
condition converts silent drift into a chain that ends BLOCKED or on the cap.
This repo's design already requires that (the header spec, ~line 46), so this
repo is on the safe side of the line — **provided the shell-check requirement
is enforced, not advisory**. A run whose `done means` is prose, not a command,
should be refused before step 1. Parent-writes would not fix drift anyway: a
parent that does not read the work cannot detect it either.

Verdict: **child writes.** Harden it (below), do not relocate it.

---

## Red team, most damaging first

**1. The ~80 tokens/step claim (lines 26-27) counts the two texts and nothing
around them.** Unaccounted, per step: the dispatch tool_use block and its
framing; the verification shell calls of line 142's catch — at least two
tool_use + tool_result pairs, and `pytest -q | tail -1` plus
`git diff --stat | tail -1` outputs are not "about 15 tokens" once harness
framing is on them; the block-counting shell call of line 130's catch; the
per-step git commit if the parent does it. Realistic parent growth is 300-600
tokens/step (guess, but bounded below by the tool-call scaffolding alone) —
4-8x the claim. The design survives, since 20 steps at even 600 is 12K against
the 68K baseline, but the published number is wrong, and it poisons falsifier 1
(line 179): an 8-step run grows the parent past 2,000 tokens on scaffolding
alone, so the falsifier fires on harness overhead while the design is working.
Re-derive the threshold from one measured step, or the first honest run
"falsifies" a design that is doing its job.

**2. Falsifier 5 (line 192) is unfalsifiable as written, and gameable in the
other direction.** Zero ASKs is pre-interpreted as "quietly guessing"; one ASK
confirms the permission is real. No outcome can count against the design,
which is the definition of not a falsifier. And once a child's prompt lineage
contains "zero ASKs is evidence the permission is not real," a compliant model
will manufacture an ASK to satisfy the expectation — the same
instruction-following pressure the ASK section itself describes, pointed the
wrong way. Replace with something scoreable: seed one deliberately ambiguous
brief per N runs and require ASK on that step specifically; unseeded steps
carry no ASK quota.

**3. A failure mode is missing that bites harder than 4 or 5: the line-range
relay has no integrity check.** The parent's entire state is `<a>,<b>` copied
from a child's NEXT line, and models miscount lines. A child that appends its
block and then reports the wrong range briefs step N+1 from someone else's
brief, half a brief, or prose — and the parent, which by construction never
reads, relays it without noticing. Same family: nothing enforces line 39's
"append-only." A child that edits lines 1-20, or inserts rather than appends
and shifts every line number, corrupts the anchor for every remaining step.
Both catches are mechanical and cheap — the parent takes the range from a grep
for the last `### next brief` heading, not from the child's report, and diffs
the header against git before dispatching — but the draft specifies neither,
and without them the failure is silent, which is the property that made mode 1
the draft's number one.

**4. Mode ordering: 2 should outrank 1.** Line 127 calls under-writing "the
real risk," but its catch is mechanical and fires every step. Telephone
drift's catch (line 135) is the header anchor, which — per the verdict section
— covers goal drift and not decomposition drift, plus ASK, which is
behavioral, not enforced. Rank by weakness of catch, not likelihood of
occurrence: the mode with the wishful catch is the real risk.

**5. Falsifier 4 (line 189) compares mispriced units and has no control run.**
"Output tokens spent writing briefs, against parent growth avoided" compares
raw counts, but the doc's own pricing note says output runs ~5x input, and
parent growth compounds across turns while brief output is paid once. Raw
counts can make either side win. Worse, "growth avoided" is a counterfactual:
measuring it requires a parent-writes control run nobody has scheduled, so as
written the item cannot fire. State it in dollars, and either schedule the
control or substitute the measured §11 baseline for the counterfactual.

**6. Mode 3's catch verifies only what the verdict schema names (line 142).**
Re-running `pytest` catches a lying verdict; it does not catch a child that
deleted the failing test, weakened an assertion, or did damage outside the
verdict's three fields — and the schema is fixed, so every child knows exactly
which assertions will be checked. Goodhart with a 15-token budget. The cheap
widening: check `git diff --stat` against the brief's named files and treat
any file outside them as BLOCKED.

---

## What is sound

- **ASK as brief element (e), and its rationale (lines 96-108).** The default
  behavior of a capable model handed ambiguity is silent resolution; a stated
  permission to refuse is the correct countermeasure and cheap.
- **The step cap becoming structural (lines 111-121).** Absorbing overrun into
  the chain instead of one agent's calls^1.54 curve is the best idea in the
  document, and it holds regardless of the fork's outcome.
- **Committing the state file per step (line 39).** With 249 of 352 child
  transcripts already empty, durable-by-default is not optional.
- **The serial/parallel separation (line 151).** Correctly scoped; keeping the
  two shapes unmerged is right.
- **Falsifiers 2 and 3 (lines 182-188).** Both honest as written — falsifier 3
  explicitly binds the design to §12's own falsifier instead of tuning past
  the objection, which is the rare direction for a design doc to point.
