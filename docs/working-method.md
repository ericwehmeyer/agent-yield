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

---

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
