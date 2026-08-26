# Start here after a session restart

**Written 2026-08-25 20:45 EDT, immediately before a deliberate restart.**

The restart is itself the finding. See *Why this session ended* at the bottom —
it is the most reusable thing on this page.

## State of the board

**The tool is built and works.** Fourteen modules, 98 tests, green on Windows and
macOS, everything pushed. `docs/superpowers/plans/2026-08-25-agent-yield.md` is
fully executed.

```
agent-yield ingest    read transcripts, dedup, persist to .agent-yield/calls.jsonl
agent-yield outcomes  what git says shipped
agent-yield report    the join, per mode, with intervention before/after
agent-yield tag       record a session's work mode (never inferred)
agent-yield predict   project a dispatch's cost as a band
agent-yield gate      PreToolUse hook -- all three bands, fails open
```

Two machines worked this repo in parallel through GitHub issues. That worked; it
needs no Remote Control, and it is documented in `docs/working-method.md` §7.

**Live dashboard** (private, from the real corpus):
https://claude.ai/code/artifact/42c04cb1-5f43-43a7-8a81-9678070cc2ce
Republish by re-running `Artifact` with the same file path, or regenerate from
the repo with `report_html.py`, which is the durable version of the same view.

## What was settled today

**Task 1 is fully answered, both halves.** A `PreToolUse` hook fires on the main
thread's `Agent` dispatch with `subagent_type` and `model` readable, **and exit
code 2 genuinely refuses the dispatch** — measured under human approval, not
assumed. §4.5 stands in full. The corollary is in the code: a gate that crashes
is indistinguishable from one that refuses, so it **fails open**.

**The founding constant was falsified, then reconciled.** `case-study.md` claimed
context-per-call was *"stable to 0.4%"*. Two independent measurements:

| | aggregate | decomposed |
|---|---|---|
| Windows, 20,273 calls, 22 days | 145,145 | days 74,349 → 391,473 |
| macOS, 4,745 calls | 132,234 | main 311,399 vs subagent 89,721 |

Both aggregates land within 6% of 136K; on **both** machines it dissolves under
decomposition. ~136K is a property of a typical *mixture* of work, not of a call.
`design.md` §3.1 has the full reconciliation. **Do not re-litigate this** — it is
measured, written down, and the two apparently opposite headlines are both right.

**Two smaller corrections, both recorded rather than quietly edited:** the
case study's 97.4% cache-read share is 97.2% for the day it is printed under, and
the share moves with workload (93.0% in a prose-heavy session). `README.md` and
`design.md` §6 both previously claimed dispatch-time enforcement was impossible;
both are corrected.

## Open work

| | |
|---|---|
| **#17** | §5 conflates running out of window with spending efficiently. **Do this first.** |
| **#13** | `predict` must use the context it is projecting *for*. **Deliberately deferred** to the week-1 review — do not implement it before 09-01. |

**#17 is the live one**, and it came out of the last measurement of the session:

```
CACHE-READ BILL BY CONTEXT SIZE OF THE CALL
   0- 50K   3,389 calls    106,116,334    3.6%
  50-100K   5,650 calls    420,711,400   14.3%
 100-200K   7,190 calls  1,023,363,126   34.8%
 200-400K   2,911 calls    817,724,501   27.8%
 400+       1,133 calls    574,603,095   19.5%
```

**47% of the bill comes from the 20% of calls made above 200K context.** §5's
thresholds (warn 60%, compact 75/85%) are *capacity* thresholds — they answer
"am I about to run out of window", not "am I spending efficiently". At 200K on a
1M window a session is at 20% of capacity and silent by every §5 rule, while
already in the band that generates half the spend. The issue asks for a cost
threshold family firing roughly 3× earlier, and for advice that says *dispatch or
restart*, not *compact*.

## Two review routines still armed

Both one-shot, cloud, reading only committed files. Everything is pushed, so they
will see the real state.

| | fires | |
|---|---|---|
| Week 1 | 2026-09-01 13:00 UTC | progress, falsification tests, thresholds, differentiator |
| Week 2 | 2026-09-08 13:00 UTC | recalibration, and whether interventions did what they predicted |

`interventions.toml` now holds four real interventions made today, each with a
prediction recorded **before** the result was known. Week 2 scores them. That
file is the experiment; do not add an intervention without an `expect` — the
loader will refuse it, which is the point.

## Do not re-derive

**`subagent_tokens` is not the cost, and its error is not a constant.** ~80× in
the case study, **3.7×** on one macOS dispatch. It scales with how much cache the
agent read, so no correction factor can be applied. Read the transcript.

**Cache reads are 97% of tokens but roughly 70% of spend.** The published ratios
are about 0.1× for cache read, 1.25× cache write, 5× output against base input.
Output punches ~40× above its token weight. The tool deliberately does not
hardcode rates — but know the shape before choosing what to optimise.

**Transcripts: one record per `tool_use` block, one API call per `requestId`.**
Records sharing a request also share the message id, so deduplicating on
`(message_id, request_id)` collapses them correctly. Counting records instead of
calls inflates both call counts and totals. This was checked; the numbers hold.

**Subagent transcripts live in the OS temp tree and evaporate.** 249 of 352 were
already empty. A 3.0 GB snapshot is at `C:/Users/ewehm/transcript-archive/2026-08-25`
(426 main + 103 `.output`, of which only **19** were real transcripts — the other
84 are plain-text write-ups). Ingest from the archive, not the live tree.

**The gate's test count is a floor, not an expectation** (`mk-main`).
`check_merge.py` goes red below `MINIMUM_TESTS = 2000`, on any failure, or on an
unreadable report — **not** because the count moved.

## model-migration-kit

`77dd372`, clean, pushed, seven gates green, 2357 tests. **Paused** by request.
One thing dangling: `chunk/latency-absence` is rebased onto main and gated green,
ready to merge whenever wanted. It is entangled with the Mac's U4 finding
(`--timeout` makes latency the strictest gate in a tool whose page says twice
that latency is never a gate) — sequence the two.

## Why this session ended, and how to work the next one

This session ended at ~212K context **not because it was near the window limit —
it was at 21% — but because it had entered the expensive band it had just
measured.** Those are different thresholds, and confusing them is #17.

`docs/working-method.md` is the full method, measured rather than asserted. The
four things that matter most:

1. **Dispatch briefed work off the loaded thread.** 269,175 context/call in a
   loaded parent against 17,580 in an agent handed `sed` line ranges and told not
   to explore. The economy is **conditional** on the brief — un-briefed agents
   measured 85,195.
2. **Batch tool calls.** Every API call re-reads the entire context. This session
   ran 1.33 tool calls per API call; 2.0 would have removed a third of the bill.
3. **Do not admit large things to context.** Line ranges, not whole files.
   Aggregate in the shell and print ten lines, not a thousand. Anything read once
   is paid for on every subsequent call, forever.
4. **Restart at natural boundaries** — work landed, checks green, pushed — and
   write the findings down first. That precondition is why this page exists.
