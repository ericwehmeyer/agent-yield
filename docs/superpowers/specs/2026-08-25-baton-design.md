# The baton: a dispatch thread that does not grow

**Status: DRAFT, unapproved.** Written 2026-08-25 23:40 EDT from a design
conversation that got as far as one answered question before the operator went
to bed. Nothing here is built. The open fork at the bottom is dispatched to
Fable and its answer belongs in this document before anything is.

---

## The finding

**The dispatch thread does not need to eat any of the context, and today it eats
most of it.**

A parent running a fan-out pays three times, permanently:

| what lands in the parent, forever | measured |
|---|---|
| its own reads, to work out what each agent should do | §11: 58,475 -> 126,522 over one phase |
| the full brief text of every dispatch it issues | scales with task complexity |
| every child's return payload | the child decides the size; the parent cannot refuse |

All three are variable and all three scale with the work. The baton makes all
three constant.

**Per step the parent grows by one return line and one dispatch prompt — about
80 tokens, flat, whatever the step does.** Twenty steps costs ~1,600 tokens
against the 68,047 measured in §11.

One move does it: **the child writes the next child's brief.** The parent never
comprehends the work. It relays a line range.

---

## The mechanism

### The state file

`.agent-yield/baton/<run-id>.md`. Append-only. Committed to git after each step,
so a bad step is revertible and no finding dies in an evaporating transcript —
249 of 352 child transcripts were already empty before anyone looked.

Lines 1-20 are the run header. Written once, never changed:

```
# run <id> :: <the goal, one paragraph>
## invariants      <- what must stay true; violating one is an ASK, not a judgement call
## done means      <- the termination condition, stated as a shell check
## step cap: 12
```

Every step appends exactly one block:

```
## step 7 :: 2026-08-25T23:40 :: sonnet :: 8 calls
### done
<what changed, as file:line. One paragraph.>
### verdict
TESTS 197 passed | DIFF 3 files +84 -12 | PUSHED no
### next brief
<the whole brief for step 8: goal restatement, sed ranges, output path,
 return contract. This is the payload. The parent never reads it.>
```

### The parent's dispatch prompt, which is a constant

```
Read <state-file> lines 1,20 and lines <a>,<b>, both via `sed -n`. Those two
ranges are your entire task. Do not explore; if you need a file not named in
them, ASK and stop. Cap: 10 tool calls. Append one step block to that same file
before you exit.

Return EXACTLY one line:
  NEXT <start>,<end> <=12 words
  ASK <the question>
  DONE <reason>
  BLOCKED <reason>
```

Nothing in it varies but `<a>,<b>`. It is ~60 tokens whether step 8 is a
one-line config change or a module rewrite.

### The four return verbs, and why ASK is the important one

| verb | means | what the parent does |
|---|---|---|
| `NEXT a,b <=12 words` | step done, next brief is at those lines | verify the verdict, relay |
| `ASK <question>` | **the brief was not clear enough to act on** | stop the chain, wake the operator |
| `DONE <reason>` | the header's termination check passes | verify it, stop |
| `BLOCKED <reason>` | cannot proceed for a structural reason | stop the chain, wake the operator |

**`ASK` is the anti-drift mechanism and it is worth more than the other three.**
A child that guesses at an unclear brief produces work that looks finished and
is wrong, and the parent — which by construction does not read the work — cannot
catch it. A child that asks costs one stopped chain. The instruction has to be
explicit in every brief, because the default behaviour of a capable model handed
an ambiguous task is to resolve the ambiguity silently and keep going.

This is a fifth part for §12's four-part brief: **(e) a stated permission to
refuse.** The other four bound what the child reads and returns. This one bounds
what it invents.

### The parent's entire state

Run id, current line range, step count. Three values.

---

## Why the 10-call cap becomes enforceable

§11 fitted cost at `calls^1.54`: one 27-call agent billed 1,879,466 tokens
against 840,036 for the same calls split three ways. The cap has been policy
since and policy did not hold, because "one unit of work" was a judgement made
by whoever wrote the brief.

Under the baton it is structural. A step is a step. A child that cannot finish in
10 calls does not overrun — it writes what it has, briefs step N+1 to continue,
and exits. **The chain absorbs the overrun instead of one agent's cost curve
absorbing it.**

---

## Where it breaks

Five failure modes, in descending order of how likely they are to bite.

**1. The child under-writes the state file.** It did the work and recorded
nothing useful, so step 8 is briefed from a stub. This is the real risk and it
cannot be enforced from inside the parent's context.
*Catch:* the parent counts the appended block through the shell and treats a
short block as BLOCKED. Mechanical, no comprehension required.

**2. Telephone drift.** No judgement sits between steps, so the chain can walk
away from the goal one plausible step at a time.
*Catch:* every child reads lines 1-20 — the goal and the invariants — alongside
its own brief, and never sees the intervening steps. Drift does not compound
through the briefs, because each child is anchored to the header rather than to
its predecessor's reading of it. `ASK` is the other half of this catch.

**3. The verdict line lies.** A child claims tests pass when they do not.
*Catch:* the parent re-runs the assertion through the shell and compares —
`pytest -q | tail -1`, `git diff --stat | tail -1`. About 15 tokens, and it is
the only thing the parent reads with comprehension. §12 rule 2 finally doing
work instead of being advice.

**4. The chain never terminates.** *Catch:* the step cap sits in the header, the
parent refuses to dispatch past it, and ASK or BLOCKED always stops the chain.
A chain that ends on the cap is a failed run, not a finished one, and should say
so rather than reporting completion.

**5. Somebody uses it for parallel work.** The baton is serial by construction.
*Resolution:* it is for **sequential work with dependencies** — exactly the case
that today forces the parent to hold state between steps. Genuine fan-out needs
no baton: independent agents already return N verdict lines to a parent that
never had to hold anything. **Do not merge the two shapes.**

---

## What it costs, including the part that could sink it

Each child pays to read the header and its brief — about 70 lines, call it 3-5K.
The precedent is measured: a line-ranged agent told not to explore ran at 17,580
context/call against a 269,175 parent.

**Each child also pays to write the next brief, and that is new work the old
shape never had.** Output runs ~5x base input and punches roughly 40x above its
token weight in spend. A 50-line brief is not free and it is paid once per step.
**Nobody has measured it.** If a brief costs more than the parent growth it
prevents, the baton is a worse trade wearing a better one's clothes, and this
document is wrong.

---

## What would falsify this

To be recorded in `interventions.toml` with `expect=` **before** the first run,
per the rule that already refuses an intervention without one.

- **The parent stays flat.** A run of >=8 steps should grow the parent by under
  2,000 tokens between step 1 and step 8. Above 10,000 the relay is leaking and
  the design is wrong as specified.
- **Cost per step is flat.** If step 8 costs materially more than step 2, briefs
  are accreting and the state file needs pruning rather than appending.
- **Quality survives.** A baton run should ship work the operator judges
  equivalent to the same task done by a reading parent. If it does not, §12's own
  falsifier has fired — "if a parent that never reads a child's output ships
  worse work, rule 1 is a false economy" — and the honest response is to record
  it, not to tune the brief until the objection stops.
- **Brief overhead is smaller than the growth it prevents.** Output tokens spent
  writing briefs, against parent growth avoided. If the first exceeds the second,
  stop.
- **ASK fires at least once in ten steps.** A chain that never asks is either
  perfectly briefed or quietly guessing, and the second is far more likely. Zero
  ASKs across several runs is evidence the permission is not real.

---

## The one question this document does not answer

**Should the child write the next brief, or should the parent write it from the
child's verdict line?**

Child-writes is what is specified above, and it is the move that makes the
parent's prompt a constant. But it puts brief authorship in the least-informed
place in the system, and it is the step where drift enters. Parent-writes keeps
judgement where the goal lives, at the cost of the parent understanding each
verdict well enough to author from it — which is the reading §11 measured at 81%
of the session.

That fork decides the architecture, and being wrong about it is expensive, which
is the stated condition for spending Fable. Dispatched; the answer belongs here
before anything is built.

---

## Not decided here

- Whether `agent-yield` ships a `baton` subcommand or this stays a working
  practice. Build the practice first — a subcommand for an unvalidated shape is
  the mistake `predict` already made once.
- Whether `gate` should refuse a dispatch missing the return contract. §12 is
  explicit that an exploratory dispatch legitimately has none of the rubric's
  markers, so such a gate must tell a bad brief from a different kind of task
  before it refuses anything. Unsolved.

---

## Measured 2026-08-25 23:45: which inflow actually dominates

Five dispatch-heavy main-thread sessions from the 3GB archive, 2,516 intervals,
each interval's context delta attributed to whatever tool_result entered the
conversation before it.

```
SOURCE OF MAIN-THREAD CONTEXT GROWTH
  A  the parent reading things itself   55.4%
  C  assistant text, prompts, reminders  33.2%
  B  subagent return payloads            11.4%
```

**The parent reading things is roughly 5x the subagent returns.** That moves the
design's centre of gravity. "Write and exit" — bounding what children hand back —
attacks the 11.4%. **The move that matters is the parent never comprehending the
work at all, which attacks the 55.4%.** The baton does both, but it should be
argued and measured on the second, not the first.

C at 33.2% is the uncomfortable third: a third of growth is the conversation
itself, and no dispatch discipline touches it. That is an argument for restarting,
which is already the standing lever, and it caps how much any dispatch mechanism
can ever save.

**The caveat, and it is large.** The sanity check failed: attributed additions
sum to ~2x the sessions net growth, because negative deltas (compaction drops)
were floored at zero while every positive attribution was kept. So these are
shares of *gross* additions, not of net growth, and the two are not the same
quantity. The per-interval split is also proportional-by-character, which is a
guess at token counts. Treat the ordering as sound and the exact percentages as
indicative. All five sessions were dispatch-heavy by selection, so this says
nothing about whether the split holds in sessions that never dispatch.

Full method and tables: `docs/attribution-2026-08-25.md`.

---

## The missing layer: who cuts the work into slices

Everything above assumes the slices already exist. They do not, and whoever cuts
them has to understand the whole goal to do it. If that is the parent, the parent
reads everything, and the parent reading everything is the 55.4% we just measured.
**The design as written above solves the second half of the problem and hands the
first half straight back.**

So slicing is itself a dispatched job. Three roles, and the parent is the
smallest of them.

### 1. The slicer. One agent, once, at the start.

Given the goal, it writes a plan file: N slices, each one a piece of work small
enough to finish in 10 calls and **each with a test command that proves it
worked**. Testability is what defines a slice boundary - not call count, not file
count. A piece of work with no way to check it is not a slice, and the slicer
should say so rather than inventing one.

It returns two lines: how many slices, and the line range of the index table.

### 2. The index. The parents entire working memory.

One table at the top of the plan file. One row per slice:

```
id | lines    | depends on | test command
 1 | 40,95    | -          | pytest -q tests/test_thresholds.py
 2 | 96,140   | -          | pytest -q tests/test_report.py
 3 | 141,190  | 1          | pytest -q
```

About 15 tokens a row. Twelve slices is under 200 tokens, and that is the whole
of what the parent holds. It never reads a slice body. It reads which rows have
no unmet dependency, dispatches those, runs the test command in the last column,
and moves on.

### 3. The fleet, and the baton, which are the same thing at different widths

The `depends on` column decides the shape, and nobody has to choose it by hand:

- **rows with no dependency go out together** - a small fleet, in parallel, each
  agent capped at 10 calls, each returning two lines
- **rows in a dependency chain go out one at a time**, each handing the next its
  brief - the baton described above

Fleet and baton are not two designs. They are what one index does when the
dependency column is empty and when it is not. That resolves failure mode 5:
there is nothing to keep separate.

### The return contract, in plain English, two lines

This supersedes the one-line contract earlier in this document.

```
line 1   what happened      DONE 7 tests 197 passed
                            FAIL 7 tests 3 failed in test_report.py
                            ASK 7 the brief says "the gate" but there are two
line 2   what is next       NEXT 340,395 wire cost_band into statusline
                            STOP
```

Line 1 is checkable by the parent without understanding anything - it re-runs the
test command from the index and compares. Line 2 is a pointer, never content.

**ASK is the rule that stops the wild goose chases.** A child whose brief is not
clear enough to act on must return ASK and stop. It must not go and find out.
Going and finding out is the un-briefed populations 85,195 context per call, and
it is the single most expensive habit in the corpus. Say it in every brief; a
capable model handed a vague task will otherwise resolve the vagueness quietly
and keep working.

### What this costs the parent, per slice

```
dispatch prompt   ~60 tokens   fixed
return            ~25 tokens   two lines
test check        ~15 tokens   tail of the test output
                  -----------
                  ~100 tokens per slice
```

Twelve slices: about 1,200 tokens, plus the index. Against a parent that went
58,475 to 126,522 doing the same kind of phase by hand.

### The part that is still unsolved

The slicer is one agent deciding the shape of everything downstream, with no
review, and a bad cut poisons every slice under it. That is the same
concentration of risk the fork at the top of this document worries about, moved
one level up rather than removed. Options nobody has tested: two slicers and
compare their indexes, or a cheap reviewer that only checks that every slice has
a real test command. Both cost one extra dispatch. Neither has been measured.
