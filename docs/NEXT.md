# Start here after a session restart

**Written 2026-08-25 17:10 EDT, after task 1 was settled in full.**

## Task 1 is answered, both halves

**The hook fires on the dispatch, and exit 2 refuses it.** Measured, not assumed.

```
{"event":"PreToolUse","tool":"Agent",
 "dispatch_keys":["description","model","prompt","subagent_type"],
 "subagent_type":"general-purpose","model":"haiku"}
```

Then, with a deny path added to the probe under human approval:

```
PreToolUse:Agent hook error: agent-yield: deny-path test
```

The agent never ran. So a gate can read the requested model and subagent type
before the spend, and can refuse. §4.5 stands in full — all three bands are
buildable. The hook fires for **background** dispatches too, and an absent key
means "not passed", not "unavailable" (`isolation` was absent only because the
probe call omitted it).

`design.md` §4.5 and §8 record this. §6 and `README.md` were both corrected: they
claimed dispatch-time enforcement was a gap that would not close, and that is no
longer true.

**What is still genuinely out of reach:** hooks do not fire for tool calls made
*inside* a running subagent (#34692). An agent approved at a projected 5M that
then burns 60M is invisible until it finishes. The gate is a doorway, not a
meter — and the plan says so in the module docstring.

**The design consequence that fell out of this**, now in `design.md` §4.5 and
Task 8: a hook that crashes is indistinguishable from one that refuses, so a
buggy gate would block every dispatch for the rest of the session. The gate must
fail **open** — catch everything, exit 0, and return 2 only on an actual
decision. An unreadable ingest file must not become an outage.

## One edit still yours

The classifier blocks hook-config changes, so this one is not something the
session can do. The probe still matches `*` and pays a Python startup on every
tool call, in **both** repos:

```
agent-yield/.claude/settings.local.json
mk-main/.claude/settings.local.json

"matcher": "*"   ->   "matcher": "Agent|Task"
```

Or delete the `hooks` block outright — the measurement it existed for is
complete. Either way it takes effect at the *next* session start.

`probe.py` is back to observe-only; the deny path was removed and the revert was
confirmed by a dispatch that ran normally. Note it is **gitignored, not tracked**
— `git checkout` will not restore it.

## Then

Execute `docs/superpowers/plans/2026-08-25-agent-yield.md` — ten TDD tasks, via
`superpowers:subagent-driven-development` or `superpowers:executing-plans`.

Task 10 is the acceptance test: ingest the real transcripts and confirm ~136K
context-per-call falls out. **If it does not, the parser is wrong — do not adjust
the expected number.**

Two things found while writing the plan, both already in it:

- **Subagent transcripts live in the OS temp directory** —
  `<temp>/claude/<slug>/<session>/tasks/<agentId>.output`, marked
  `"isSidechain": true`. Of 352 such files on this machine, **249 were already
  empty**. This is why the plan persists an ingest instead of reading live; the
  alternative is a tool whose history shrinks every time temp is cleaned.
- **`usage.iterations`** repeats the top-level numbers per inference iteration.
  Sum the top-level fields only, or you double-count.

## State of the board

**agent-yield** — README, `docs/design.md`, `docs/case-study.md`, this file, and
the plan. Still no code, which is correct: the plan was the next artefact, not
the first module. **Commits are local — not yet pushed.**

**Two review routines armed**, both one-shot, cloud, reading only committed
files:

| | fires | |
|---|---|---|
| Week 1 | 2026-09-01 13:00 UTC | progress, falsification tests, thresholds, differentiator |
| Week 2 | 2026-09-08 13:00 UTC | recalibration, and whether interventions did what they predicted |

Each opens a GitHub issue on this repo. Both are told a null result is a real
result and that recommending we stop is a legitimate output. **They read only
committed files — push before 09-01 or week 1 reviews an empty repo.**

**model-migration-kit** — `77dd372`, clean, pushed, seven gates green, 2357
tests. Work there is **paused** by request. One thing dangling:

- `chunk/latency-absence` is **rebased onto main and gated green**, ready to
  merge whenever wanted. It is entangled with the Mac's U4 finding (`--timeout`
  makes latency the strictest gate in a tool whose page says twice that latency
  is never a gate) — sequence the two.

## Two things not to re-derive

**The gate's test count is a floor, not an expectation.** `check_merge.py` goes
red below `MINIMUM_TESTS = 2000`, on any failure or error, or on an unreadable
report — **not** because the count moved. Do not "fix" it into a hardcoded
number; that rots at every merge.

**`subagent_tokens` is not the cost.** It counts output and uncached input, not
the cache reads that are 97.4% of consumption. It is off by roughly 80×. This
already misled one live dispatch decision. `docs/case-study.md` §4 has the
numbers. If any code in this repo ever reads that field, it is a bug.
