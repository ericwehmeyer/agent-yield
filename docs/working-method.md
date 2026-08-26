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

Subagent transcripts live in the OS temp directory. On this machine, **249 of
352 were already empty** — the record of what agents cost is being deleted
continuously, and it is the exact data this tool exists to read.

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
  not self-contained, and the line-range economy is imaginary.
- **If central commits become the bottleneck** rather than the dependency graph,
  the parent is doing too much and should batch or delegate verification.
- **If the ~136K context-per-call constant turns out to be machine-specific**,
  the cost model in §1 needs per-machine calibration and the numbers here are
  local, not general. Issue #11 tests exactly this on a second machine.
