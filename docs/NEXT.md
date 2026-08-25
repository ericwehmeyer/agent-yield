# Start here after a session restart

**Written 2026-08-25 06:52 EDT, immediately before a deliberate restart.**

## Do this first, before anything else

**Settle whether a `PreToolUse` hook fires on the subagent-dispatch tool.**
Step 1 of `design.md` §8. Everything downstream is provisional until it is
answered, and it cannot be answered without a restart — which is why the restart
happened.

A probe is already wired up and waiting, in **both** repos, matched on `*` so a
negative result is interpretable rather than ambiguous:

```
C:/Users/ewehm/repos/agent-yield/.claude/hooks/probe.py
C:/Users/ewehm/repos/mk-main/.claude/hooks/probe.py
```

Both log to `probe-log.jsonl` beside themselves. **Both logs were deleted before
the restart, so any entry you find was produced by the new session.**

The check, in order:

1. Run any tool at all (a `Bash` echo will do), then look for
   `.claude/hooks/probe-log.jsonl`. **If it does not exist, hooks are not
   loading** — stop and diagnose that before concluding anything about the
   dispatch tool.
2. If it does exist, dispatch one trivial Haiku agent that does nothing.
3. Read the log. An entry with `"tool": "Agent"` (or `"Task"`) means **the gate
   is viable** — and `dispatch_keys` tells you exactly which fields a real gate
   may read.
4. No such entry, while other tools *are* logged, means **the gate is not
   viable**. §4.5 becomes advisory, and `design.md` must be re-reviewed rather
   than silently downgraded.

Record the answer in `design.md` §4.5 either way. A negative is a real result and
is worth as much as a positive — it is the difference between a tool that claims
enforcement and one that honestly cannot.

**Then remove or narrow the probe.** It matches `*`, so it pays a Python startup
on every tool call. It is a measuring instrument, not a fixture.

## Then

Write the implementation plan (`superpowers:writing-plans`) against
`design.md` §8, with step 1's answer in hand rather than assumed.

## State of the board

**agent-yield** — `5d31693`, clean, pushed, private.
README, `docs/design.md`, `docs/case-study.md`. No code yet, deliberately.

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
numbers.
