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
- **Rebase with `git -c core.commentChar=";"`.** Every commit subject in this
  repo starts with `#NN:`, and git's default cleanup strips a leading `#` as a
  comment. On 2026-08-26 a ten-commit rebase over the other machine's nine
  silently deleted the subject line of the three commits it had to re-commit,
  promoting each body's first paragraph in its place and losing the ticket
  number. Nothing warns. Read the subjects after any rebase — and the reason
  there was a ten-commit rebase at all is that "push immediately" above was not
  followed.

**This is asynchronous and that is the feature.** Neither machine waits, and
neither has to be running when the other sends. Remote Control is per-session
and requires both ends to have launched with it; an issue requires nothing of
the recipient except that it eventually reads. For two machines that restart
constantly *by design* — which is this project's whole thesis — the durable
channel beats the live one.

**Take the ticket number from GitHub, never from arithmetic.** Both machines
allocated **#64** within an hour of each other on 2026-08-26 -- one for a
portability finding, one for the depth experiment -- because each read the
highest number in `NEXT.md` and added one. The issue tracker is the allocator:
`gh issue create` returns the number, and only then does it go in a commit
subject, in `interventions.toml`, or on this page. A number that exists in two
places is worse than no number, because both halves of the repo will cite it.

### 7.2 Which machine made a commit (issue #45)

Two machines through one queue means every git-denominated metric divides **one**
machine's tokens by **both** machines' commits. #44 measured that at 25x on one
day, and the daily report's "we got 24% worse" rested on it — **that figure is
retracted at the end of this section**. #45 proposed
correlating a commit's timestamp against this machine's calls, ±6 minutes.

**Measured, that rule is 61% accurate and over-attributes 1.67x.** On this
repository's 118 commits it claims 106 for this machine when **63** are its:

| window | says LOCAL | accuracy | over-attributes |
|---|---|---|---|
| 1 min | 98 | 67.6% | 1.56x |
| **6 min** | **106** | **61.1%** | **1.67x** |
| 30 min | 116 | 58.3% | 1.71x |

It is not a tuning problem — tightening the window to one minute barely moves
it. **Both machines work the same hours; that is what the queue is for.** The
nearest local call to a *foreign* commit is routinely under ten seconds, so "was
this machine busy" cannot separate them. And 32% of these commits carry a
committer stamp a rebase rewrote (median +50s, up to +31 min), which is the
second reason the stamp #45 named is the wrong one: **committer time is when
history was last touched, by whoever touched it.**

**Git does record the machine. It is `.git/logs/HEAD`.** The reflog is per clone
and is never pushed: it holds a line for every sha this clone *wrote* and a
different line for every sha that merely *arrived*. Attribution is a lookup:

```
agent-yield outcomes --since 2026-08-25 --machine
2026-08-25  merges=0  commits=0   lines=0       unattributable=10
2026-08-26  merges=0  commits=63  lines=13,316  unattributable=0
```

`unattributable` is the third outcome and it is never folded into either other
one. A commit older than this clone's reflog is not this machine's and is not
the other's either — this clone did not exist yet. Reporting that as *foreign*
is #44's failure a fourth time: the silence that reads as a measurement.

**Read the verb, not the message.** The reflog line is `<verb>: <subject>`, and
the subject is the commit's own text. `commit`, `commit (amend)`, anything
ending `(pick)`, and a bare `rebase (continue)` all write a sha; `(start)`,
`(finish)`, `reset`, `pull`, `clone` and `(abort)` only move the tip. **The
first version of this missed `rebase (continue)`** and labelled three commits
this machine made as foreign — #52, #56 and #57, the same three whose subjects
the rebase ate above.

**Limits, and they decide where this can be used.** The reflog **expires**
(90 days reachable, 30 unreachable), so this answers "who shipped it" for recent
work and returns `unknown` for old work, which is the correct answer rather than
a failure. It is **per clone**, so it scopes a numerator and a denominator to
the same machine and says nothing about the other machine's total. And **a
rebase re-commits**: when the other machine rebases work authored here, the sha
it publishes was written there. `local` means *this clone wrote this sha*, which
is the right question for a denominator and is not the same question as who
typed it.

`--machine` is **off by default**, on `outcomes` and on `report`, because
scoping changes what a count means and a number whose meaning changed silently
is the failure this whole tool documents.

**What the correction cost the published numbers (#45's obligation, discharged
2026-08-26, #67).** The daily report's "24% worse" was computed with the
±6-minute rule. Re-run on the reflog denominator — same numerator to the token,
same window — the rule claimed **50** of the window's 66 commits for this
repo's Windows clone when the reflog shows it wrote **22**: 2.27x
over-attribution on commits, **6.59x on code lines**. Two of the three ratios
reverse sign:

| ratio, 08-25 → 08-26 | published | re-run |
|---|---|---|
| tokens / commit | 1,056,044, *0.59x better* | **2,400,100, 1.35x worse** |
| tokens / insertion | 5,267, 1.24x worse | **13,747, 3.25x worse** |
| tokens / code insertion | 9,613, *0.61x better* | **63,388, 4.02x worse** |

The published figure was argued as a **floor** and the direction held; the size
was 13x low — 225% worse, not 24%. **Do not quote 24%, 0.59x, 0.61x or 5,267.**
And the mixture argument that explained away the two apparent wins was
misattribution one level up: on this clone's own lines 08-26 was **doc-heavy
too** — 833 code against 2,050 docs — so the code lines that argument leaned on
were the other machine's. Full re-run in `NEXT.md`, *[Windows 2026-08-26
16:15]*.

## 7.1 A queue moves work; it cannot answer a question about the other box

Section 7 holds for anything that is committed. It cannot help with what is
deliberately not: `.claude/settings.json` is rendered per machine, and #130
turned on whether the Mac's copy ran `boundary --enforce` against code that
still had the deadlock. No commit records that. Guessing it from here was
wrong in the dangerous direction once already -- `boundary-audit.sh` reported
the defect on a fixed machine on its first run, because bare `python` has no
`agent_yield`.

`ListAgents` shows sessions reachable over Remote Control, so ask that box and
take the output verbatim -- a summary is inference wearing a witness's
clothes. When the check will be run again, ship it as a script with an exit
code first: the #130 list was four commands and is now `sh
scripts/boundary-audit.sh`. For a one-off, just ask.

The one hard line: do not ask a peer to do what this session was refused. That
launders the operator's permission decision across machines, and it is the
same failure as the boundary defect that produced this section.

Full argument and what would falsify it:
`docs/adr/0003-machine-local-facts-are-asked-for-not-inferred.md`.


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


## 11.2 Re-entry, measured across the corpus (issue #34)

**§11.1's ~19,800 was one number from one run, and the entire cost model on the
baton rests on it being *fixed*.** Fixed is what makes it amortise, and
amortising is the only reason a long unit can beat a short one. If it scales
with the brief instead, then §12's five-part brief is buying its own cost back
and "one unit of work" is not free either.

**The first call of an agent is charged before the agent has read anything**, so
its context *is* the re-entry price: system prompt, tool schemas, brief. Every
subagent transcript that survives on this machine, joined to the dispatch that
started it by `agents.join`: 142 files, 84 with billable calls, 93 dispatches,
**79 joined and 0 runs left unclaimed**.

| | tokens |
|---|---|
| min | 8,909 |
| median | **22,114** |
| mean | 21,353 |
| max | 26,401 |
| stdev | 2,958 |

**It is fixed, near enough, and §11.1's 19,800 is 12% low.** The band is tight —
one standard deviation is 13% of the median — and anything estimating what a
dispatch costs before it starts should use **~22,000 for a `general-purpose`
agent**, not 19,800.

### The brief moves it, and by less than the fit says

```
slope       780 tokens per 1,000 brief chars     intercept 18,160     r 0.412
mechanical  ~250 tokens per 1,000 brief chars    (4 chars a token)
```

**The fitted slope is three times the mechanical price of the text**, and within
each project separately it is 476 (agent-yield, n=17) and 1,835
(model-migration-kit, n=62) — 2× and 7×. A brief cannot cost seven times what it
tokenizes to. **So brief length is standing in for something else that arrives
with it**, and the slope must not be read as "what a brief costs". Two candidates
worth separating, neither measured here: a longer brief names more files, and a
longer brief comes from a session that has more loaded.

What the data does support is the size of the whole effect, which is small:

| briefs | median brief | median first call |
|---|---|---|
| shortest quarter | 2,678 chars | 20,038 |
| longest quarter | 4,950 chars | 22,281 |

**11% across the interquartile range of real briefs.** So #34's question — *does
the five-part brief buy its own cost back?* — is answered **no, and it does not
need to**: at ~4,000 characters a brief accounts for something between 1,000
tokens (mechanical) and 3,100 (the pooled fit) against a floor of ~18,000. Write
the brief. It is not where the money is.

### The one number here that could change a decision

| subagent type | n | median first call |
|---|---|---|
| `general-purpose` | 74 | 22,131 |
| `claude-code-guide` | 2 | 13,860 |
| `statusline-setup` | 2 | 9,440 |
| `Explore` | 1 | 8,909 |

**A narrow agent type appears to arrive for a third of the price of a
`general-purpose` one** — and re-entry is charged per agent, so on a twelve-agent
baton that is the difference between ~265,000 tokens of arrival and ~110,000.
**n is 1 and 2. That is a lead, not a finding**, and it is the cheapest
measurement on this page: dispatch the same brief to `general-purpose` and to a
narrow type and read the two first calls.

### Limits

One machine, two projects, and — the one that bites — **these are the survivors.**
Subagent transcripts are volatile (`discovery`: 249 of 352 already empty on the
Windows corpus, 1 of 112 here), files empty over time, so recent dispatches are
over-represented and anything that changed the price of re-entry earlier in the
history is invisible. 62 of the 79 rows come from a single project.

---


## 11.3 The end-to-end number (issue #33)

**The comparison the baton actually makes, and the one nothing on this page had
run.** §11.1 compared one agent against three agents — both arms dispatched. It
says nothing about a parent that reads everything, which is what the baton
claims to replace. Per-call arithmetic had by then predicted the wrong sign
twice (§11's 6.2× measured 1.07×, §11.1's 1.5× measured 0.65×), so this one got
its bars written into `interventions.toml` and committed *before the first
call*: `76cbf08`.

**The task**, identical in both arms: audit the module docstring of all 19
modules in `src/agent_yield` against their own code, return one JSON object.
**Then five identical follow-up turns**, because the mechanism being tested is
an asymmetry — re-entry is paid once per agent, parent growth is paid on *every
parent call afterwards* — and an experiment that stops at the audit turn
measures the wrong half of it.

- **BATON**: the parent may not open a single file under `src/`; it dispatches
  and assembles. Packing is its own choice.
- **READER**: the parent does the whole audit itself and may not dispatch.

Same model, same flags, same task text, same tail. The arm paragraph is the only
difference — deliberately, since allowing `Agent` in one arm and not the other
would change the tool schema, and this experiment is a token count.

### The result

Cumulative tokens, parent plus every agent the session started:

| turn | baton-r1 | baton-r2 | reader-r1 | reader-r2 | reader/baton |
|---|---|---|---|---|---|
| t1 (the audit) | 781,703 | 535,616 | 733,466 | 846,760 | 1.20 |
| t2 | 819,441 | 565,221 | 859,290 | 971,519 | 1.32 |
| t3 | 857,657 | 595,548 | 985,702 | 1,097,098 | 1.43 |
| t4 | 896,407 | 626,466 | 1,112,703 | 1,223,293 | 1.53 |
| t5 | 935,639 | 658,152 | 1,240,132 | 1,349,746 | 1.62 |
| **t6** | **975,338** | **690,323** | **1,368,208** | **1,476,964** | **1.71** |

**1.71×, and it passes** — the bar was 1.25×. **Every baton run cost less than
every reader run** (worst baton 975,338 against best reader 1,368,208), which is
the strongest simple statement the data supports and does not depend on
averaging.

**The first time in three tries that per-call reasoning got the sign right.**

### The tail is not decoration, and the numbers say so

**At the audit turn alone the arms are 1.20× apart — under the bar.** Had this
experiment stopped where §11.1 stopped, it would have returned "no effect", and
in one pair (r1) the *reader* was ahead at t1 and behind by t2. The whole result
lives in the five turns afterwards, which is what the pre-registration predicted
and the reason they were part of the protocol rather than an afterthought.

Per call, the mechanism is not inferred, it is visible:

```
reader parent   22,424  22,862  42,622  56,852  64,287  77,937  95,199 ... 127,510
baton parent    22,515  28,362  29,296  29,691  30,412  31,026  31,767
```

**A reader tail turn costs ~127,600 tokens. A baton tail turn costs ~35,900.**
That ratio, 3.55×, is what the advantage tends to as a session gets longer, and
it is the honest form of the extrapolation: at six turns 1.71×, without bound in
the number of turns, asymptotically 3.55× *on this task*.

### The 28× is retracted as an end-to-end number

`NEXT.md` claimed the baton "still wins by roughly 28×", from a parent carrying
68,047 extra tokens over another 100 calls (6.8M) against twelve re-entries
(238K). **That is a ratio of two different quantities — growth avoided against
arrival paid — and it is not an end-to-end ratio.** Measured end to end the
number is 1.71× at six turns and 3.55× in the limit. The direction was right;
the magnitude was overstated by about eight-fold. Do not quote 28× again.

### The cheap arm found half the defects, and the bar did not catch it

| | claims counted | mismatches found | tokens per mismatch |
|---|---|---|---|
| baton | 121 / 123 | **4 / 4** | 208,208 |
| reader | 111 / 100 | **8 / 8** | 177,823 |

Coverage was equal — all 19 modules, exactly once, in all four runs, and the
claim counts are 13.5% apart against a 25% VOID bar. **But the reader found
twice the defects, in both replicates, and its extra findings are close to a
superset of the baton's rather than a different judgment call.** Two of the four
the baton missed in *both* runs were verified by hand afterwards and are real:
`discovery`'s "only `tasks/*.output` under that tree is a transcript" (agent
transcripts now also live under `~/.claude/projects/<slug>/<session>/subagents/`,
with the `.output` entries as symlinks to them), and `resume`'s "the silences
... there are five of them" against its own code comment saying four of the five
outcomes are silences.

**Per defect found, the reader is 1.17× cheaper, and the headline reverses.**

**The bar was written on the wrong quantity.** It counted *claims* — the
denominator, which is a measure of coverage — when the task's output is
*mismatches*. A volume bar has to be on the finding, not on the thing the
finding is found in, and this one would have passed a baton arm that returned
zero defects with a full set of claim counts. That is the reusable error here,
and it is the same shape as #26 and #32: **the test was written to match the
shape of the work rather than the point of it.**

So: **#33 passes on cost and opens a question it cannot answer** — whether
splitting a task across agents systematically finds less. n=2 per arm, one task.
That is #47.

### Bar 4, the noise clause, scored rather than skipped

| | spread | cause |
|---|---|---|
| within baton | **1.41×** (690,323 .. 975,338) | the parent's own call count: 14 calls against 7 |
| within reader | 1.08× (1,368,208 .. 1,476,964) | — |

The pre-registration said that if the within-arm spread exceeded the gap between
arms, the result is noise. It does not — 1.41× against 1.71× — but the margin is
thin and the honest reading is that **the baton arm is the volatile one.** All of
its spread is the parent: the two baton runs' *agents* cost 484,256 and 479,629,
1% apart, over identical 24 calls. The parent of r1 spent seven extra calls
before dispatching (a `ToolSearch`, a `ListAgents`, and a slower assembly) and
that alone is 280,388 tokens, 41% of a whole run. **A parent that does not read
is not automatically a parent that is cheap** — what it costs is how many calls
it takes to decide, and nothing in the baton design bounds that.

### Limits

One task, one machine, 19 files that batch cleanly, five tail turns, n=2 an arm.
The tail was driven by `claude -p --resume`, one process per turn, so each turn
pays a cache re-creation the same session would not pay uninterrupted; it is
charged to both arms in proportion to what they carry, which is the quantity
under test, but it flatters the absolute numbers in both. Total cost of the four
runs: **$11.54**.

---

## 11.4 The packing rule, priced (issue #35)

**#35 asked how many index rows go to one agent, and said the answer is a
function of re-entry cost. It is not.** Re-entry turns out to be the cheap term
once it is priced. What decides the pack is the growth of a call with its depth
in the agent, and a fixed orientation cost that has been measured exactly once.

Everything here is **list dollars** (`pricing.py`, `costBasis: "list"`), per
#55, over the **84** subagent transcripts on this machine that price completely.
**9 runs are excluded and named** — 5 `claude-sonnet-5`, 4 `claude-fable-5`,
models this repo has no reconciled rate for. A rate it has not checked is a
guess, and a guess averaged into a median is worse than a gap.

### Re-entry costs less than the calls it is supposed to amortise

| | tokens | list dollars |
|---|---|---|
| an agent's first call | 22,052 | **$0.0577** |
| its later calls, mean | — | **$0.0800** |

**1.33x — the wrong way round.** The baton spec argued for long units because
re-entry is a large fixed fee paid once, and long units amortise it. Priced,
**arrival is cheaper than the median call that follows it.** The reason is in
its composition: a first call is **54.1% cache read at 0.10x and 45.9% cache
write at 1.25x**, with essentially no fresh input. It is not billed like
reading; it is billed like re-reading.

So the amortisation argument is retired. **Packing fat is still right, and for
a different reason than the one that was given.**

### The exponent is 1.54 in tokens and 1.11 in dollars

The same 56 runs of >=20 calls, fitted three ways — cumulative cost against
call index, within each run, so no between-run difference can produce it:

| unit | exponent | p25-p75 |
|---|---|---|
| context tokens | **1.38** | 1.36-1.42 |
| raw tokens | **1.38** | 1.36-1.42 |
| **list dollars** | **1.11** | 1.09-1.15 |

`calls^1.54` is real and it is a **token** fact. In the unit the operator is
billed in it is very nearly linear, because **54.5% of a subagent's bill is
cache read at a tenth of base input** — 96.4% of its tokens, an eighth of its
weight. Output is 1.0% of the tokens and **27.3%** of the bill.

Within a run the growth is flat enough to state as a rate: **+$0.00153 per call
of depth** (p25 $0.00103, p75 $0.00211).

### The packing rule, and the number under it

Splitting a unit in two buys back the depth-growth of the calls it moves, and
pays for a second agent's orientation. Both sides are now numbers:

```
buys back   $0.00153 x (calls moved) x (their depth)
pays        (orientation calls) x (a WARM arrival)
break even  depth = orientation x arrival / 0.00153
```

The arrival term is the **warm** one, $0.0577 on the standard tool schema: a
split pays one cold arrival and k-1 warm ones, so the marginal agent is a warm
one. §11.4.1 measures both, and measures how far the warm price moves.

**Orientation was the weak term. It has now been measured twice** — §11.4.1
below — and it is **2.6 to 3.5 fixed calls an agent**. The band that follows
uses both estimates and both quartiles of the growth term:

| | |
|---|---|
| break-even depth, standard tool schema | **72-196 calls** |
| break-even depth, trimmed brief and schema | **35-97 calls** |
| median dispatch, **pooled across projects** | **52 calls** |
| p90 / longest, pooled | 79 / **118** |
| **median dispatch in THIS repo** | **5 calls** |
| **p90 / longest in this repo** | **22 / 30** |

**So the rule is:**

> **Pack every adjacent, dependency-free row into one agent. Split on a
> dependency edge or on a verification boundary — never on cost.**

**And here is the honest reading of the band under it.** Dispatching the way
this repo's fleet dispatches — full tool schema — cost never argues for
splitting the median dispatch, and starts to argue somewhere between the p90 and
twice the longest dispatch on record. Dispatch agents on a trimmed schema and a
compact brief and the break-even falls to **35-97**, straddling the median. That
is not a hedge, it is the mechanism: **the arrival price is what the agent's
cached prefix costs, so tightening a brief makes an extra agent cheaper and
argues for splitting, not for packing.**

**Every arm anyone has ever run sat at a packed depth of 15 calls or fewer**
(§11.1's 5, §11.4.1's 13.5). Both bands are extrapolations of 3-13x beyond any
depth that has been compared. The rule is measured where it is measured, and
above ~15 calls it is arithmetic.

### The 52-call median is another project's, and this one never reaches the band (issue #65)

**Measured 2026-08-26, `docs/experiments/65-depth/depth.py`, 102 subagent
transcripts.** The Limits section below has always said 62 of the 84 runs come
from one project's audit fleet. Broken out, that caveat is the whole story:

| project | n | median | p90 | max | at or over 35 calls |
|---|---|---|---|---|---|
| model-migration-kit | 62 | **57.5** | 88.8 | 118 | **52** |
| **agent-yield** | 29 | **5.0** | 22.0 | **30** | **0** |
| Pictures | 7 | 27.0 | 108.0 | 108 | 3 |
| pooled | 102 | 44.0 | 81.1 | 118 | 56 |

**Zero of this repo's 29 dispatches reach the FLOOR of the cheaper band**, and
the longest it has ever made — 30 calls — is short of it. So the paragraph above
is wrong about which fleet it describes: *"dispatching the way this repo's fleet
dispatches, cost never argues for splitting the median dispatch"* is true, and
it is true by a margin of 7x rather than the near-thing the table implied. And
the trimmed-schema band does not straddle **this repo's** median; it sits an
order of magnitude above it.

**What that does to #65.** The ticket asked for an arm at a packed depth of 50
because the rule is *applied* at a 52-call median. It is not applied at 52 here.
Where the rule could be wrong is model-migration-kit's fleet, and an experiment
that wants to find out has to be run there. In this repo the rule is not an
untested extrapolation — it is untestable, because the depth that would test it
does not occur.

**Depth is a property of the work, not of the brief.** Within agent-yield,
`agents` reports briefed n=10 at a median of 4 calls against un-briefed n=17 at
5. The 62-188 call range `thresholds.OBSERVED_CALL_RANGE` calls "un-briefed" is
the other project's fleet, not this repo's un-briefed dispatches.

**And an audit task cannot be sized up to depth 50 to manufacture the test.**
One packed pilot, 23 slices over 46 of this repo's 49 python files, issued **49
Read blocks in 15 calls — 3.27 files per call**, for a clean depth of ~24. Slices
share files, so cutting the same 49 files into 49 slices or 100 adds no file to
open and therefore no call: **the packed arm's depth scales with unique artifacts
opened over the batch width, not with the slice count.** A task that decomposes
into k independent slices is exactly the task whose packed agent batches — which
is not a flaw in the task, it is the thing packing buys, measured.

## 11.4.1 The orientation term, measured a second time (issue #63)

#63 asked for one experiment: dispatch one agent over k slices against k agents
over one slice each, and count CALLS. **It had already been run.** #33's baton
arm and #47's baton1 arm are the same task — audit 19 module docstrings — with
the same brief, the same return contract and the same five-turn tail, dispatched
as **five agents** and as **one**, two replicates each, compliance verified from
the transcripts and defects already scored. All four sessions' agent transcripts
survive. `docs/experiments/63-orientation/orientation.py` reprices them.

| | agents | agent calls | list dollars | $/call |
|---|---|---|---|---|
| split, r1 / r2 | 5 | 24 / 24 | 1.7212 / 1.7570 | 0.0725 |
| packed, r1 / r2 | 1 | 12 / 15 | 1.4465 / 1.6111 | 0.1133 |

**Extra calls per extra agent: 2.62** (corners 2.25-3.00), against §11.1's 3.50
from a different task at a different k. Two independent estimates, and they
agree to within the spread of either. The estimand is the extra calls a split
pays on fixed work — it absorbs the fatter agent's better read-batching too, so
it is an upper bound on arrival alone, exactly as §11.1's is.

**The direct result needs no equation at all.** Splitting multiplied the call
count by **1.78** and divided the price of a call by **1.56**; net, splitting
cost **1.14x**. Under #33's own 1.25x bar, so on its own this establishes the
sign and not the size — but the sign is the one the rule claims, at a packed
depth of 13.5 calls, and the packed arm found no fewer defects (#47: 5 and 4
against 4 and 4). End to end in list dollars the four arms come to $2.80 / $2.17
against $1.77 / $1.83, reproducing the CLI's own `total_cost_usd` means of $2.54
and $1.81 to within 3% — the same reconciliation `pricing.py` runs in the suite,
on transcripts it did not calibrate against.

### The arrival price is not a constant, and it is not a mystery either

| | |
|---|---|
| cold arrival — the **first** agent of a session | **$0.1299** (n=15) |
| warm arrival — every agent after it | **$0.0573** (n=76) |

A split pays one cold arrival and k-1 warm ones, so **the warm price is the
marginal one**, and the corpus median ($0.0583) is essentially it. A warm
arrival's prefix is **14,992 cache read + 7,124 write + 228 output** — and the
cache read is 14,992 at p25, median *and* p75, because it is the harness's own
system prompt and tool schema, identical for every agent. Priced straight from
those three numbers at the opus base rate: **$0.0577**, which is §11.4's arrival
figure rebuilt from its parts.

**The #33/#47 agents arrive on half that prefix** — 6,650 read + 3,139 write,
2.3x smaller — because those sessions ran with five tools disallowed and a
compact brief, and they arrive at **$0.0284**. That 2x is the widest term in the
break-even now, it is not noise, and it is under the operator's control. §12's
brief rubric is therefore also a lever on the packing number, which nothing in
§11 anticipated.

### Why this does not refit the growth term

Fitted on these runs the slope is **$0.017/call** over all twelve agents and
**$0.0072** over the two packed ones, against §11.4's **$0.00153**. It is not a
contradiction: a slope fitted on a 3-6 call run measures its **terminal** call,
the one carrying the return payload, not depth. §11.4 fitted runs of >=20 calls
and was right to; these runs are too short to say anything about growth, which
is the second reason the depth experiment below is the one worth running.

### What would falsify §11.4 and §11.4.1

- **The packing falsifier, recorded before it is run** (#35's own, in the unit
  #55 requires): one agent carrying six slices against six agents carrying one
  each, scored on **defects found** and on **list dollars**. If the packed arm
  returns fewer defects, the packing rule is wrong and the retired cap was
  right for a reason nobody measured. **The bar is on defects, not on claims
  counted** — #33 pre-registered the denominator and would have passed an arm
  that found nothing, which is how #47 came to exist.
- ~~**If the orientation term is not ~3.5 calls**~~ — **measured, §11.4.1.**
  2.62 on a second task at a different k, against 3.50; the band above uses
  both. Orientation is now the narrow term and the **arrival price** is the wide
  one, at 2x between tool schemas.
- ~~**The depth experiment (#65), and it is now the only thing that can move
  this section**~~ — **measured, and it cannot be run here**; see *The 52-call
  median is another project's* above. The median it was filed against is
  model-migration-kit's fleet. This repo's median is 5, its longest is 30, and
  **none of its 29 dispatches reach the 35-call floor of the cheaper band**.
  The experiment is built and sized (`docs/experiments/65-depth/`) and would
  have to run in that other fleet, where the depth exists. What
  survives as a falsifier for the rule AS APPLIED HERE is much weaker and should
  be stated as such: at a packed depth of 5, nothing about the break-even matters,
  and the packing rule stands on the defect result rather than on cost.
- **If re-entry stops being mostly cache read** — a different agent type, a
  cold parent, a first call that actually reads — arrival gets dearer than a
  later call and the amortisation argument comes back.

### Limits

One machine. **62 of the 84 runs come from a single project's audit fleet**, so
"the median dispatch is 52 calls" describes that fleet more than it describes
dispatching — now counted rather than warned about, above: that fleet's median
is 57.5 and this repo's is 5. These are also the survivors: subagent transcripts evaporate
(§11.2), so the sample is biased toward recent runs. And every dollar here is a
**list-price equivalent**: on a plan the ranking survives and the absolute
figure does not.

**§11.4.1's own limits, which are tighter.** Four runs of one task, n=2 an arm,
one packing alternative — 5 agents against 1, with nothing between them tested.
A packed depth of 13.5 calls, against a break-even quoted in the high tens. And
the two arms ran in different working trees (#47 pinned `src/` to 76cbf08 in a
throwaway worktree), so the paths in every prompt differ; that was right for
#47's defect scoring and it means the call counts here are compared across two
trees of byte-identical source rather than one.

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
| b | **As many adjacent, dependency-free slices as one agent can carry.** A slice is the smallest piece of work with a command that proves it; **a row of the index is a unit of verification, not a unit of dispatch** | ~~capped at ~10 calls, because cost is `calls^1.54`~~ — retracted twice over. §11.1 ran the split and it cost **54% more**; §11.4 then re-fitted the exponent **in list dollars on the same runs** and got **1.11**, against 1.38 for the same runs in raw tokens. The superlinearity is a token fact that mostly dissolves at the price of a cache read. **Do not split a unit to meet a number, and do not pack it to meet one either: cost is not what bounds the pack. Verification is** |
| c | **A named output path the child writes to** | child transcripts evaporate — 249 of 352 were already empty before anyone looked |
| d | **A stated return contract** — "return the file:line list and one verdict line, nothing else" | the return lands in the parent's context and is re-billed on every later call |

Parts (a) and (d) are the two that pay: (a) bounds what the child reads, (d)
bounds what the parent reads. (c) is insurance against a finding that existed
only in a transcript that no longer exists. **(b) is no longer insurance
against the superlinear tail** — §11.4 priced that tail and it is small. (b)
survives because a slice with no command that proves it cannot be checked, and
because a dependency edge has to fall somewhere.

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
- ~~**4 of 73 dispatches carried all three markers**~~ — **that was a detector
  floor, not a briefing rate. Re-scored 2026-08-25 after #32; see §12.2.**
  **60 of 73 exceeded the 10-call cap** (longest 118), which is unaffected —
  the cap is counted from the child's transcript, not from the prompt.
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

### 12.2 The detector was the floor (issue #32, 2026-08-25)

Every number in §12.1 that counts markers was produced by three regexes that
**tested for particular wording rather than for the property they name.** Five
dispatches written to this section deliberately — the issue #18 Part E audits,
each carrying an explicit line range, a prohibition on reading anything else, a
named output path and a stated return contract — scored **0 of 3 markers, all
five**. Diagnosed per regex, not guessed:

| marker | why it failed | the property it should have asked for |
|---|---|---|
| line ranges | the range matched; the *prohibition* demanded the literal word "explore", so `"do not grep or search the repository, do not read any other file"` — strictly stronger — scored zero | is discovery bounded, by whatever words |
| output path | `.{0,60}` without `DOTALL`, so `write it to:\n  /path/x.json` missed while the same words on one line matched. Verified both ways | is a path named for the child to write to |
| return contract | `at most 3 lines` is not `under \d+ lines` | is what comes back bounded |

**What the fix changes, and what it does not.** Run against the same
Part-C-era population, the old regexes reproduce §12.1's published rows
exactly — briefed n=4 median 6.0 calls, un-briefed n=8 median 6.5 — so the two
detectors are comparable on the same twelve dispatches:

| agent-yield, same 12 dispatches | briefed | median calls | un-briefed | median calls |
|---|---|---|---|---|
| old detector (§12.1 as published) | 4 | 6.0 | 8 | 6.5 |
| fixed detector | 5 | **3.0** | 7 | **9.0** |

Across the whole corpus the floor was much lower than it was here: **4 briefed
of 87 non-exempt dispatches becomes 10 of 87** — the old detector missed six of
every ten briefs it was shown.

**Read the second table the way it deserves and it says nothing about the
rubric.** Exactly **one** dispatch was reclassified — a 3-call one — and it
moved both medians by three calls. A comparison whose answer inverts on a
single row at n=12 cannot support either answer. The ranges are still
3–30 briefed against 3–27 un-briefed, still fully overlapping; median
context/call is still 29,356 against 31,108. **§12.1's conclusion stands
unchanged: there is no evidence that the three detectable markers predict
dispatch length.** What #32 changes is that the marker *population* can now be
trusted; what it does not change is that the population is far too small.

**The general lesson, and it is not about regexes.** The five briefs that
scored zero were written by the same repo, to the same section, in the same
week. A detector that its own author's textbook example fails is not
mis-tuned — it is measuring a different thing than it claims to. And it stayed
green because `test_gate.py`'s fixtures were *written to match the regexes*:
the same failure as #26 one file over, where a hook read a payload key the
harness never sends and 226 tests agreed with it. The five Part E prompts are
now pinned verbatim in `tests/fixtures/part_e_dispatches.json` as captured
positive cases, because **a fixture you wrote cannot falsify a pattern you
wrote.**

**#27 Stage 2 stays off.** A better detector is still not a licence to refuse
dispatches: the marker-only rule now fires on 77 of 87, and §12 says an
exploratory dispatch is *supposed* to carry none of these markers.

**The join is a heuristic and says so.** There is no structural link from a
dispatch to its child: the parent's `tool_use` id appears nowhere in the
child's transcript, and the child's first record has `parentUuid: null`. The
match is same session, same subagent type, child starting within 120s after
the dispatch (measured lag: 1.4–1.6s). When it cannot match it reports
`unlinked` rather than picking one, and `--unlinked` lists the orphans,
because a join whose failures are invisible is indistinguishable from one that
always works — the same lesson as #29, one file over.

### 12.3 Admission and receipt: the two rules the rubric left out (2026-08-30)

§12 says what a brief must contain and what the parent must not read. It does
not say **when a dispatch is worth making at all**, nor what the parent does
with the artifact once part (c) has produced one. Both gaps were hit in one
session on 2026-08-30.

#### The admission test: four conditions, or do it inline

1. **Independent.** No shared state, no sequential dependency on another live
   agent. §11.1 is the counter-case: a *dependent* task split three ways cost
   385,109 tokens against 249,944, 54% more.
2. **Read-heavy and decision-light.** The child pays once for what it reads.
   That asymmetry is what §12 opens with, and it only pays when there is a lot
   to read.
3. **A nameable output path exists**, per part (c).
4. **Doing it inline would put more into the parent than the return contract
   will.**

Condition 4 decides most cases and is the reason "dispatch to save context" is
usually wrong for a small task. The dispatch overhead *is* the return, and a
return costing more than the reading it replaced is a loss.

#### The receipt rule: do not read back what you dispatched

Part (c) exists because child transcripts evaporate, not because the parent
should open the file. A parent that dispatches, takes a bounded summary, then
reads the artifact anyway has paid for that reading twice and cancelled rule 1.
Read it only when a decision the parent must make is unsettled by the summary,
and then read the range that settles it rather than the document.

#### The measurement is an anecdote with a receipt, and says so

Two research dispatches on 2026-08-30, both carrying parts (a) through (d),
cost 62,831 tokens over 15 tool uses and 83,601 over 20. Those totals come from
the harness completion record. They do **not** come from `agent-yield agents`,
which could not join either run: both report `unlinked`, which is issue #84.

The instrument cannot currently score the dispatches this section is about.
Until it can, the per-call context that would make these comparable to
§11.4's 17,580–67,123 band does not exist, and no figure here should be quoted
as if it did.

The parent's side is what did work: two return summaries of roughly 400 words
each, against two documents it has still not opened.

#### An amendment to §3, whose premise was the tree and not the agent

§3 says agents do not touch git, because parallel agents in one working tree
race the index and produce commits mixing three tasks. Both dispatches above
committed to their own branches without incident, each running in its own git
worktree. Where that isolation is available, §3 reads: **agents do not share a
working tree.** Where it is not, §3 stands as written.

#### What would falsify §12.3

- **If a parent that reads its children's artifacts ships better work**, the
  receipt rule is a false economy in the way rule 1 could also be. §11's lever 3
  already records two real catches that came from a parent not rubber-stamping.
- **If condition 4 is unmeasurable in practice**, it is a slogan. Nobody has
  measured the task size below which a dispatch's return costs more than the
  reading it replaced.
- **If briefed dispatches in worktrees cost more than briefed dispatches in a
  shared tree**, the §3 amendment has bought correctness with tokens and that
  price is not recorded here.

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
