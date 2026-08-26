# How to run this pipeline

**Written 2026-08-25, from one session that built this tool in about forty
minutes across ten tasks and six subagents.** Every number here was measured in
that session, not estimated. Where something is a guess, it says so.

This is the operational counterpart to `design.md`. That document says what the
tool measures; this one says how to work so the measurements come out well.

---

## 1. The economics that drive everything else

```
cost  ≈  tool_calls  ×  context_size
```

The second term is the one people forget, and it belongs to *whoever is making
the call*. Measured live in the session that wrote this:

| | context/call | 
|---|---|
| main session, mid-build, carrying the whole conversation | **211,986** |
| fresh subagent handed a self-contained task | **~30,000** |

**Roughly 7× cheaper per call to dispatch than to do it yourself — and the gap
widens with every turn the main session survives.** A parent that has read three
documents and written a plan is the expensive place to run a tool call. It is
the cheap place to make a decision.

This inverts the intuition that subagents are costly. The case study's 12.4M
median agent was not expensive *because it was a subagent*; it was expensive
because it had a large context and made many calls. Give an agent a small
context and the same work costs a fraction.

**The corollary that matters:** the main session's job is to decide, dispatch,
verify, and commit. Not to type.

### Corrected on a second machine, 2026-08-26 (#12)

The 7× is real but it is **not a property of dispatching**. It is the payoff for
the §2 brief discipline, and without that discipline it mostly disappears.

Measured on the MacBook Pro, using `agent_yield` on its own transcripts:

| | agents | context/call |
|---|---|---|
| one agent dispatched by line range, forbidden to explore | 1 | **17,580** |
| every other subagent on this machine | 62 | median **85,195** (p25 67,736, p75 95,310, max 136,865) |
| main sessions with ≥20 calls | 4 | median **194,566** (min 62,215, max 397,947) |

Two things fall out, and they point in opposite directions.

**The brief works, better than claimed.** The one agent given a self-contained
task and exact `sed` line ranges ran at 17,580 — below the ~30,000 §1 quotes,
against a parent at 61,466. Held against the median parent it is 11×.

**The brief is not the default, and un-briefed dispatch is not 7× cheaper.** The
62 agents actually run on this machine — real work, no line-range discipline —
sat at a median 85,195, **2.8× the figure above**. Against the median parent
that is **2.3×, not 7×.** An agent that has to explore the repo to start rebuilds
the context you dispatched to escape.

So the honest form of the claim is: the denominator is what you control. A fresh
agent costs ~25K per call if you brief it and ~85K if you do not; the numerator
is whatever the parent happens to be carrying, which only grows. Quoting a
single multiplier hides both variables. This is the doc's own falsification
bullet — "if agents given self-contained briefs still explore the repo, the
line-range economy is imaginary" — coming back with a number attached: the
economy is real, and it is conditional.

### Re-measured at n=4, same day

The n=1 above was too thin, and three more briefed dispatches moved the answer.
Four agents, all briefed by line range on real #14/#15/#16 work:

| agent | calls | context/call | `subagent_tokens` understates by |
|---|---|---|---|
| doc edits | 4 | 17,580 | 3.7× |
| report split | 9 | 27,241 | 8.0× |
| CLI tag | 15 | 35,995 | 12.9× |
| HTML dashboard | 27 | 67,123 | 20.3× |
| **median** | | **31,618** | |

**§1's ~30,000 is right.** The median briefed agent came in at 31,618 — the
original figure, reproduced on different hardware and different work. My n=1
reading of 17,580 was the low end of the range, not the centre, and the
correction above overstated the case on the strength of it.

**And the 7× largely holds, for briefed agents.** 194,566 ÷ 31,618 = **6.2×**.
What does not hold is 7× for dispatch in general: against the 62 un-briefed
agents at 85,195, briefing is worth 2.7× and dispatch alone is worth 2.3×. So
the conditional claim stands; the number attached to the well-briefed case is
close to what §1 said all along.

**The new finding is that context/call scales with how long the agent runs.**
17,580 at 4 calls, 67,123 at 27 — a 3.8× spread across briefed agents doing the
same kind of work under the same discipline. The brief controls where an agent
*starts*, not where it ends up; every tool call adds to what the next one
re-reads. "A fresh agent costs ~30K per call" is true of short agents. Split a
long task rather than briefing a long agent, and the economy holds; let one
agent run 27 calls and it drifts toward parent territory on its own.

**`subagent_tokens` understates by a factor that scales the same way** — 3.7×
at 4 calls, 20.3× at 27, monotonic across all four. The case study's ~80× is
that curve continued, not a different phenomenon. This is why no correction
factor can be applied to that field: the error is a function of how much cache
the agent read, which is exactly what the field does not report.

**`subagent_tokens` was wrong again, by a different factor.** The dispatch above
reported 25,874; its transcript totals 94,602, a 3.7× understatement. The case
study's figure is ~80×. The error is not a constant either — it scales with how
much cache the agent read — so no correction factor can be applied to it. Read
the transcript.

## 2. Write the plan so an agent needs nothing else

The single highest-leverage practice. A task section must be **self-contained**:
literal test code, literal implementation code, exact file paths, exact commands,
and the interfaces it consumes and produces. If an agent has to explore the repo
to start, the plan failed and you pay for the exploration on every dispatch.

Dispatch by **line range**, never "read the plan":

```
sed -n '11,23p'    docs/superpowers/plans/<plan>.md   # global constraints
sed -n '1072,1315p' docs/superpowers/plans/<plan>.md  # this agent's task
```

The plan here is ~2,250 lines. Reading it whole would cost each agent ~60K
tokens before any work began; a task section costs 3–8K. Across six agents that
is the difference between ~360K and ~30K of pure preamble.

Get the ranges with one grep, and **re-grep after any edit to the plan** — line
numbers shift.

Confirmed on the Mac (#12): an agent handed two `sed -n` ranges and told not to
explore made four tool calls, read only those ranges, produced the edit, and
reported an omission it had chosen rather than hiding it. It stayed at 17,580
context/call. §2 holds.

## 3. Agents do not touch git

Parallel agents share one working tree. Let them all commit and you get
`index.lock` races, half-staged sweeps, and commits that mix three tasks.

The rule that worked:

> Agents write files and run **only their own test file**. The parent verifies,
> stages **named paths**, and commits. Never `git add -A` while agents are live.

The parent runs the test itself before committing. An agent reporting "6 passed"
is evidence, not proof — and it costs one cheap call to check.

One commit per task, with `Closes #N`, so the issue tracker closes itself.

## 4. Tell agents to report mismatches, not fix them

Give every agent this instruction:

> If an interface differs from what the task text expects, **report it rather
> than editing the dependency**.

An agent that silently "fixes" a shared module to match its own assumptions
breaks a sibling task and nobody learns anything. An agent that reports a
mismatch surfaces either a real bug or a stale brief. Both are useful.

**The parent will be wrong, and should say so up front.** In the session that
wrote this, the parent's briefs contained a stale instruction about an
`__import__` that no longer existed. The agent checked, found nothing, and said
so instead of inventing a change. That is the behaviour to ask for.

## 5. When an agent finds a bug in the plan, fix the plan too

The plan is an artefact, not a script that is consumed once. Two real cases from
this session:

- `git` parses a bare `YYYY-MM-DD` with local-timezone approxidate, so
  `--since 2026-08-24` **excluded** a commit stamped `2026-08-24T12:00:00Z`. The
  agent found it, fixed the code, and the plan was patched so the next
  implementer does not rediscover it.
- `python -m agent_yield.cli` exited 0 having done nothing, because the module
  had no `__main__` guard. A silent success is the worst failure mode a
  measurement tool can have.

If you fix only the code, the plan still teaches the bug — to the other machine,
or to the next session.

## 6. The dependency graph is the real limit, not the agent count

Map it before dispatching. From this build:

```
1 ─► 2 ─► 3 ─┐
             ├─► 8 ─┐
    6 ───────┘      │
                    ├─► 9 ─► 10
2,4,5 ─► 7 ─────────┘
```

Four tasks were independent and went out at once; the tail was strictly serial.
**Adding machines does not widen a narrow tail.** Check the graph before
concluding that more parallelism will help — usually it will not, and the honest
answer is that the work is nearly done.

Where a second machine genuinely pays is **independent corroboration**, not
speed: a different corpus, different hardware, and a reviewer with no memory of
how the code came to be.

## 7. Coordinating two machines: GitHub is the queue

One issue per task. Each issue body carries everything a cold session needs:

- the plan file and **line range**
- files it creates, and what it depends on
- the test command **for both platforms**
- the shared convention: pull first, commit only your own files, only when your
  own tests pass, push immediately

Then a session on either machine runs `gh issue list --label task --state open`,
claims one, and works without reading the whole plan or asking what the other
machine is doing.

This works without Remote Control. Note that Remote Control is **per-session**:
a session started without it cannot see one started with it, so if you want
direct messaging both ends need it from launch.

### 7.1 The issue is also the message bus, not just the queue

A queue hands out work. A **message** is different: it is addressed, it expects
a reply, and it carries something the recipient cannot derive on its own. The
issue tracker does both, and the second use was undocumented until #31 needed
it.

The shape that works:

- **Title the addressee.** `[Windows] ...`. A cold session on the other machine
  reads titles before bodies, and this is the field that decides whether to
  claim.
- **Label it `task` plus the machine.** The claim query stays
  `gh issue list --label task --state open`; the machine label is what keeps
  both ends from doing the same work twice.
- **Say what the recipient cannot derive.** Shared code arrives through git.
  **`.claude/` and `.agent-yield/` are gitignored**, so hook config, probe logs
  and handoffs are per-machine and invisible across the boundary — that gap is
  most of what is worth sending. "Pull the fix" is derivable; "your hook config
  is your own and still broken" is not.
- **Ask for one artifact back, and paste yours next to it.** #31 asks for a
  single probe line and includes the macOS line to compare against. A request
  with no reference value gets an answer nobody can score.
- **State the expected test count.** `233; if you see 226 you have not pulled`
  turns "did it work" into one command with three distinguishable outcomes.
- **Reply in the comments.** The comment thread is the return channel and it is
  durable, timestamped, and readable by a session that was not alive for any of
  it — which is the same property that makes the handoff work.

**This is asynchronous and that is the feature.** Neither machine waits, and
neither has to be running when the other sends. Remote Control is per-session
and requires both ends to have launched with it; an issue requires nothing of
the recipient except that it eventually reads. For two machines that restart
constantly *by design* — which is this project's whole thesis — the durable
channel beats the live one.

## 8. Snapshot perishable data before you need it

Subagent transcripts live in a temp directory, and which one differs by
platform. On Windows they sit under `tempfile.gettempdir()/claude`. On macOS
they do not: `tempfile.gettempdir()` resolves to the per-user `$TMPDIR`, e.g.
`/var/folders/qq/k7z8j7vj79585cprbknrw6r40000gn/T`, which holds no `claude`
directory at all, while Claude Code writes to `/tmp/claude-<uid>` —
`/tmp/claude-501` on this machine. Below that point the layout is identical:
`<root>/<project-slug>/<session-id>/tasks/<agentId>.output`.

A probe that checks only `tempfile.gettempdir()` therefore finds nothing, and
fails silently. `discovery.find_transcripts` skips a root that does not exist,
so the macOS walk returned cleanly having read 75 main transcripts and zero of
the 112 subagent transcripts — and reported that as the whole history.

The record is deleted continuously, and it is the exact data this tool exists
to read, but the rate varies. On Windows **249 of 352 subagent transcripts were
already empty**. On macOS, with a three-day-old history and temp not yet swept,
1 of 112 was empty — though a further 49 held no billable call, so 62 of 112
carried usage data.

On a machine whose sessions have completed, the scratch tree is also largely
redundant. Measured twice minutes apart, dedup gave 4,728 calls rising to 4,736
(8 unique to scratch), then 4,747 to 4,747 (0 unique). Main-session transcripts
already carry the sidechain lines, marked `"isSidechain": true`, and dedup
collapses the duplicates. The 8 briefly-unique calls belonged to a session still
running: a subagent's `.output` is written live, and the same calls reach the
main transcript slightly later. That weakens the urgency of snapshotting the
scratch tree in that case — not in general. Both numbers above were measured.

Copy first, analyse later. The snapshot that made Task 10 possible was 3.0 GB
and took under a minute:

```
transcript-archive/2026-08-25/projects   426 main-session transcripts
transcript-archive/2026-08-25/tasks      103 subagent transcripts
```

Anything you plan to measure historically, copy **before** you build the thing
that measures it.

## 9. Measure the session you are in, rather than guessing

Do not reason about context pressure from how heavy the conversation *feels*.
In this session the parent conceded it was bloated, measured, and found it was
at **21.2%** of the window — well below the 60% warn threshold in `design.md`
§5. The concession was wrong and would have triggered a needless restart.

The transcript is on disk. Read it:

```
~/.claude/projects/<project-slug>/<session-id>.jsonl
```

Sum `message.usage` per line, keeping the four fields apart. Current context is
the last record's `input + cache_read + cache_creation`.

**That you cannot see this without writing a script is the entire reason this
tool exists.**

## 10. Boundaries

A **natural boundary** is: work landed, checks green, pushed. At a boundary,
check the real number — above 50%, prefer a fresh session to a compact. A
compact costs a summarisation pass and loses fidelity; a fresh session costs
nothing and loses everything not written down.

**Precondition: findings are written down first.** One fleet lost eleven agents
at a token limit with ten having written nothing, and that work is gone. This
document exists because the method itself was, for most of a session, one of
those unwritten findings.


## 11. The method's own yield, measured end to end

**Everything above is per-call economics. This is the first measurement of
whether the method actually ships more per token — and the headline is a null
result.** One session, 2026-08-26, on the MacBook Pro, split at the first
dispatch.

| | solo (#11) | dispatching (#12, #14–16) |
|---|---|---|
| tokens | 2,396,312 | 8,971,302 |
| issues closed | 1 | 4 |
| lines added | 323 | 1,812 |
| **tokens / issue** | 2,396,312 | 2,242,826 |
| **tokens / line** | 7,419 | 4,951 |

**1.07× per issue. 1.50× per line.** Against per-call economics that predicted
6.2×. The agents were cheap — 48,504 context/call across 55 calls. The parent
ate the difference: its context went **58,475 → 126,522** context/call between
the two phases, because it read every diff, ran every suite, and wrote every
measurement script itself, at steadily growing context.

That is §6's falsification bullet firing — *"if central commits become the
bottleneck rather than the dependency graph, the parent is doing too much."*
It was.

### Why: cost is superlinear in the length of any single unit of work

`cost ≈ calls × context`, and context grows with every call *inside* a unit, so
each call re-reads a bigger pile than the last. Fitted on this session:

| | exponent |
|---|---|
| four briefed agents | cost ≈ calls<sup>1.54</sup> |
| this parent session | cost ≈ calls<sup>1.41</sup> |

Not quadratic, but firmly superlinear — and that is the whole lever. **The same
work is cheaper as more, shorter units.** The heavy context, the slow cache
reads and the spinning are one fact seen three ways: cache reads are 97.5% of
tokens *and* the latency.

### The three levers, in measured order

**1. ~~Cap agent length. Measured 2.2×.~~ RETRACTED 2026-08-25 — splitting
the same task cost 54% *more*.** See §11.1, which tested it directly. The
original claim: one agent ran 27 calls and cost **1,879,466 tokens — 21% of the
entire session in a single dispatch**, and the same 27 calls as three 9-call
agents, priced at the *measured* 9-call cost, is 840,036. That 2.2× was
**arithmetic, not a measurement**. It priced a split that was never run, and it
assumed a split preserves the call count. It does not. What survives is the
observation that prompted it — 27 calls in one dispatch is a lot of money in one
place, and §2's brief controls where an agent starts while nothing controls
where it ends. What does *not* survive is "cap at ~10 calls and split", which
was the actionable half.

**2. Restart the parent when context/call doubles. ~1.5×.** This session ran
93 calls, **45,830 → 175,677 context/call**. By the end every call cost ~4× a
call at the start, including trivial ones. §10 says to restart above 50% of the
window; the better trigger is *context/call having doubled from the session's
opening calls*, which is measurable, arrives earlier, and does not depend on
knowing the window size.

**3. Dispatch the mechanical verification, not the judgment.** This is where
the parent's growth came from — and it is the lever to apply most carefully,
because two of the three best catches in the session came from the parent
**not** rubber-stamping: a `commits` column one agent dropped to meet a width
budget while a sibling was adding a metric built on it, and an account name
leaking through a helper written to keep home directories out of a page.
Neither agent could see outside its own brief. So hand off *running the suite,
producing the diff, generating the measurement* — and keep the cross-cutting
read, which is a handful of calls, not forty.

### Limits

n=4 agents and one parent session. The 2.2× is measured; the 1.5× and both
exponents are fits over few points. The split is by wall-clock phase, and the
two phases did not ship the same kind of work — which is why tokens/line is
reported next to tokens/issue rather than instead of it.

### What would falsify this section

- ~~**If a task split into three short agents costs the same as one long one**,
  the superlinear fit is an artefact and lever 1 is worthless.~~ **TESTED
  2026-08-25, and it fired — worse than the bullet allowed for. The split did
  not cost the same; it cost 54% more.** §11.1.
- **If a restarted parent needs so much re-reading to become useful that it
  costs more than it saved**, lever 2 is a wash. Measure the first ten calls of
  a fresh session against the last ten of the one it replaced.
- **If dispatched verification misses the class of defect the parent caught
  here**, lever 3 is a false economy no matter what it saves.

---

## 11.1 Lever 1, tested and retracted

**The falsification test §11 asked for, run: the same audit dispatched as one
agent over three units, and as three agents over one unit each.** Identical
per-unit instructions, identical output schema, identical return contract, same
subagent type. Prediction recorded in `interventions.toml` *before* either arm
ran: the long agent costs **≥1.5×** the three short ones, and **<1.25×**
retracts the lever.

| | agents | calls | context/call | tokens |
|---|---|---|---|---|
| **split** (one unit each) | 3 | 12 | 31,836 | **385,109** |
| single, replicate 1 | 1 | 5 | 56,417 | 282,568 |
| single, replicate 2 | 1 | 5 | 43,411 | 217,321 |
| **single, mean** | 1 | 5 | | **249,944** |

**0.65×. Splitting the same task cost +135,164 tokens — 54% more.** The three
short agents landed within 6% of each other (123,809 / 129,897 / 131,403), so
the split arm's number is not noise.

### It is not that the cheap arm did less

| | split | single r1 | single r2 |
|---|---|---|---|
| tests enumerated | 17 / 21 / 19 | 17 / 21 / 19 | 17 / 21 / 19 |
| defects returned | 15 | 14 | 14 |

Agreement on the one *judgment* the task asked for: **75%** across arms, **82%**
between the two single agents. Two agents in the *same* arm disagreed about as
much as agents in different arms, so the disagreement is judgment
irreproducibility between any two agents, not an effect of splitting. That
control is why the second single-agent replicate was run, and it is what keeps
this a FAIL rather than a VOID.

### Why it failed, measured

Per-call context, every agent's run in order:

```
split-1   19,777  30,741  35,166  37,990
split-2   19,782  32,387  37,192  40,396
split-3   19,782  30,720  37,644  40,452
single    20,034  51,468  64,859  72,704  73,021
```

**Every agent's first call costs ~19,800 tokens before it reads anything.**
That is the fixed price of re-entry — system prompt, tool schemas, brief — and
it is nearly identical across all four. The split pays it three times:
**+39,307 tokens, 38% of the gap.**

The other 62% is the part the fit got wrong. **Splitting does not divide the
call count.** One agent read six files in 5 calls by batching; three agents
needed 12. Lower context per call (31,836 against 56,417) did not recover it,
because 12 × 31,836 still loses to 5 × 56,417.

**The superlinear effect itself is real and visible** — context grew 1.9× over
a short agent's four calls and 3.6× over the single agent's five. It is simply
too small to pay for re-entering three times. `cost ≈ calls^1.54` was fitted
across agents doing *different* tasks, so it conflated "longer agents cost
superlinearly more" with "agents given bigger tasks cost more". Holding the
task fixed separates them, and the second effect was doing the work.

The fit even says so once you use it honestly. Given the split arm's four calls
per agent, `calls^1.54` predicts the single agent is **cheaper** at 6 calls
(0.62×) and does not break even until about 11 — and it took 5.

### Limits, which decide how far this generalises

One task, six files, units of 4–5 calls, reads that batch cleanly. **Re-entry
is a fixed cost, so it amortises**: a split into genuinely long units may still
win, and a task where one agent would exhaust its context is not a choice at
all. The 27-call dispatch that motivated lever 1 is exactly that untested
regime. **The claim retracted is "splitting saves", not "splitting never
saves".** What replaces it is narrower and has a number attached: *a split
costs ~19,800 tokens per extra agent before any work happens, and only pays if
it also reduces total calls — which, on this task, it did not.*

---

## 12. The dispatch rubric: what a brief must contain

§11 measured the levers. This section is the operating instruction that falls
out of them, in the form it has to take to be used: **the child pays for what
it reads once; the parent pays for what it reads on every call afterwards.**
That asymmetry is the whole rubric. Everything below is a way of holding to it.

### The parent's four rules

1. **Dispatch and decide; do not read.** §11's null result — 1.07× end to end
   against 6.2× predicted — has one cause: the parent's context went 58,475 →
   126,522 because it read every diff and ran every suite itself. The agents
   were never the expense. **The parent was 81% of a 3.5M-token session; seven
   agents and 76 calls were 19%.**
2. **Verify through the shell, not through context.** `pytest -q | tail -3`,
   `git diff --stat`, `grep -c`. Aggregate where the aggregation is free and
   print ten lines, never a thousand.
3. **Batch tool calls.** Every API call re-reads the entire context. The macOS
   session ran **0.97 tool calls per API call while knowing this lever**;
   batching to 2.0 would have cut 123 API calls to 60. Knowing a lever is
   measurably not the same as applying it.
4. **Restart rather than compact** once loaded. A compact pays a summarization
   pass to stay in the expensive band; a restart leaves it.

### The brief's four parts

A brief that has all four produced 17,580–67,123 context/call. A brief missing
them produced a median 85,195 — the same model, the same repo, ~5× the cost.

| | part | why it is there |
|---|---|---|
| a | **Line ranges, not filenames** — "read `x.py` lines 22–58 via `sed -n`", plus *"do not explore; if you need a file not listed, say so and stop"* | the un-briefed population's cost is search, not work |
| b | **One unit of work** — ~~capped at ~10 calls~~ | ~~cost is `calls^1.54`: one 27-call agent billed 1,879,466 against 840,036 for the same calls split three ways~~ **Retracted 2026-08-25 — the 840,036 was arithmetic on a split nobody ran, and §11.1 ran it: the split cost 54% more.** One unit of work still earns its place, for (a) and (d)'s reasons — it bounds what the child reads and what it returns. The call cap does not; do not split a unit to meet a number |
| c | **A named output path the child writes to** | child transcripts evaporate — 249 of 352 were already empty before anyone looked |
| d | **A stated return contract** — "return the file:line list and one verdict line, nothing else" | the return lands in the parent's context and is re-billed on every later call |

Parts (a) and (d) are the two that pay: (a) bounds what the child reads, (d)
bounds what the parent reads. (b) and (c) are insurance — against the
superlinear tail, and against a finding that existed only in a transcript that
no longer exists.

### What this does not cover

**An exploratory dispatch is supposed to have none of these markers.** A search
agent told to sweep a repo cannot be briefed by line range without becoming a
different task. The rubric describes briefed work; it is not a test that every
dispatch should pass, and any mechanism built on it has to tell a bad brief
apart from a different kind of task before it refuses anything.

### What would falsify this section

- **If briefed and un-briefed dispatches cost the same** on a task where both
  are possible, part (a) is decoration and §1's economy is an artefact of which
  tasks happened to be briefed.
- **If a parent that never reads a child's output ships worse work**, rule 1 is
  a false economy — and §11's lever 3 already records two real catches that
  came from the parent *not* rubber-stamping. The rubric says verify through
  the shell, not that verification is optional.
- **If the four-part brief costs more to write than it saves** on short
  dispatches, there is a task size below which the rubric is overhead. Nobody
  has measured where that line is.

---


### 12.1 The rubric, scored (issue #18 Part C, 2026-08-25)

`agent-yield agents` joins each dispatch to the transcript of the agent it
started, which is what makes §11's length rule and §12's marker rubric
scorable at all. Before it, the prompt was in the parent's transcript and the
call count was in the child's, and **hooks do not fire inside a subagent**, so
`gate` could see the brief and never learn what it cost.

Scored over **73 dispatches** joined to their transcripts (0 unmatched).

**The first answer this produced was wrong, and it is kept here because the way
it was wrong is worth more than the rubric.** Pooled across every project on the
machine:

| | n | median calls | median ctx/call |
|---|---|---|---|
| carried all three markers | 4 | 6 | 39,139 |
| did not | 69 | 57 | 84,357 |

9.5x on calls. Written up as the first evidence that the markers *predict*
dispatch length, and posted to two issues, inside an hour.

**It was entirely project.** All 61 long un-briefed dispatches were one repo's
audit fleet; all 4 briefed ones another repo's. Exactly one project contained
both groups, and within it the effect disappears:

| agent-yield only | n | median calls | median ctx/call |
|---|---|---|---|
| carried all three markers | 4 | **6.0** | 39,139 |
| did not | 8 | **6.5** | 28,353 |

**There is currently no evidence that the three detectable markers predict
dispatch length.** The briefed dispatches were, if anything, slightly more
expensive per call. `agent-yield agents` now refuses to print a pooled
cross-project comparison and prints per-project rows instead, with a test
asserting the tempting number never appears.

**What does survive:**

- **The ranges overlap.** `thresholds.py` recorded that the briefed and
  un-briefed populations "do not overlap at all" (4-27 vs 62-188). Within
  agent-yield: un-briefed 3-27 against briefed 3-30. True of eight hand-picked
  dispatches, false of twelve measured ones. Retired.
- **4 of 73 dispatches carried all three markers; 60 of 73 exceeded the
  10-call cap** (longest 118). The rubric is followed about 5% of the time, in
  the repo whose subject is the rubric.
- **§12's asymmetry is untouched.** "The child pays for what it reads once; the
  parent pays on every call afterwards" is per-call economics, measured
  elsewhere. What is unsupported is the narrower claim that *these three
  regex-detectable markers* are what produce the saving.

**Three lessons, and the third is the general one:**

1. **A between-groups comparison over a pooled corpus is a confound until
   proven otherwise.** The corpus spanned projects because
   `main_transcript_dir()` spans projects, and nothing in the first version
   made that visible.
2. **The tool made the confound invisible, so the tool was the bug.** The fix
   is not "remember to check" -- it is that `render` cannot emit the pooled
   number any more.
3. **Speed of publication is a risk multiplier.** The wrong figure reached
   `thresholds.py`, `NEXT.md`, a commit message and two issue comments before
   it was checked, because it was a *good* result, and good results do not
   invite scrutiny. The interval between measuring and quoting is where this
   kind of error gets expensive.

**The join is a heuristic and says so.** There is no structural link from a
dispatch to its child: the parent's `tool_use` id appears nowhere in the
child's transcript, and the child's first record has `parentUuid: null`. The
match is same session, same subagent type, child starting within 120s after
the dispatch (measured lag: 1.4–1.6s). When it cannot match it reports
`unlinked` rather than picking one, and `--unlinked` lists the orphans,
because a join whose failures are invisible is indistinguishable from one that
always works — the same lesson as #29, one file over.

## What would falsify this

- **If a fresh agent's context is not much smaller than the parent's**, §1
  collapses and dispatching stops paying. Measure it; do not assume it.
- **If agents given self-contained briefs still explore the repo**, the brief is
  not self-contained, and the line-range economy is imaginary. Tested on the Mac
  (#12): a briefed agent held 17,580 context/call, but the 62 un-briefed agents
  on the same machine sat at a median 85,195. The economy is real and it is
  conditional — see the correction in §1.
- **If central commits become the bottleneck** rather than the dependency graph,
  the parent is doing too much and should batch or delegate verification.
- **The ~136K context-per-call constant is a planning figure, not a price.**
  Issue #11 ran it on a second machine. The aggregate held — 132,234 over 4,745
  calls, against the 136,449 and 135,943 of the case studies — but on that one
  machine context-per-call ranged from 47,347 to 179,864 across working
  directories. What is stable is the aggregate over a mixed session. Use it to
  plan a session; do not use it to price one known task.
