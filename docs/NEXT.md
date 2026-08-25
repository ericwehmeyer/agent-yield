# Start here after a session restart

**Written 2026-08-25 07:05 EDT, after the restart that settled task 1.**

## What the restart answered

**A `PreToolUse` hook does fire on the main thread's dispatch call.** The gate is
viable. Measured, not assumed:

```
{"event":"PreToolUse","tool":"Agent",
 "dispatch_keys":["description","model","prompt","subagent_type"],
 "subagent_type":"general-purpose","model":"haiku"}
```

So a gate can read the requested model and subagent type *before* the spend. It
also fired for a **background** dispatch, so the async path is gated the same.
Read an absent key as "not passed", not "unavailable" — the probe call omitted
`isolation` and it is correspondingly absent. Recorded in `design.md` §4.5, and
§8 step 1 is struck through.

## What is still open, and why

**Does exit code 2 actually block the dispatch?** Firing is not blocking, and
§4.5 claims a refuse band. Testing it means installing a hook that denies a tool
call — the auto-mode classifier refused that three times, correctly. **This needs
your approval, not the session's.** It is Task 9 of the plan, written out
step-by-step and marked do-not-attempt-autonomously.

Until it is settled the gate is honestly a **warn**, and the plan builds it that
way. A negative here is a real result: it would make §4.5 permanently advisory
and earn `README.md` a sentence it does not currently have.

## Two edits the session could not make

The classifier blocks all hook-config changes, so these are yours:

**1. Narrow the probe.** It still matches `*` and pays a Python startup on every
tool call. In **both** `agent-yield/.claude/settings.local.json` and
`mk-main/.claude/settings.local.json`:

```
"matcher": "*"   ->   "matcher": "Agent|Task"
```

Or delete the `hooks` block entirely — the measurement it existed for is made,
except the refuse path, and Task 9 re-installs what it needs anyway. Either way
this takes effect at the *next* session start, not this one.

**2. Nothing else.** `probe.py` is unmodified and committed.

## Then

Execute `docs/superpowers/plans/2026-08-25-agent-yield.md` — eleven tasks,
TDD throughout, via `superpowers:subagent-driven-development` or
`superpowers:executing-plans`. Task 11 is the acceptance test: ingest the real
transcripts and confirm ~136K context-per-call falls out. **If it does not, the
parser is wrong — do not adjust the expected number.**

Two things found while writing the plan, both already in it:

- **Subagent transcripts live in the OS temp directory** —
  `<temp>/claude/<slug>/<session>/tasks/<agentId>.output`, marked
  `"isSidechain": true`. Of 352 such files on this machine, **249 were already
  empty**. This is why the plan persists an ingest instead of reading live; the
  alternative is a tool whose history shrinks every time temp is cleaned.
- **`usage.iterations`** repeats the same numbers per inference iteration. Sum
  the top-level fields only, or you double-count.

## State of the board

**agent-yield** — clean, pushed, private. README, `docs/design.md`,
`docs/case-study.md`, `docs/NEXT.md`, and now the plan. Still no code, which is
correct: the plan is the next artefact, not the first module.

**Two review routines armed**, both one-shot, cloud, reading only committed
files:

| | fires | |
|---|---|---|
| Week 1 | 2026-09-01 13:00 UTC | progress, falsification tests, thresholds, differentiator |
| Week 2 | 2026-09-08 13:00 UTC | recalibration, and whether interventions did what they predicted |

Each opens a GitHub issue on this repo. Both are told a null result is a real
result and that recommending we stop is a legitimate output.

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
