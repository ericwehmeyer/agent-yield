# agent-yield — design

**2026-08-25. Status: approved, not implemented.**

The evidence for everything asserted here is in
[`case-study.md`](case-study.md). This document is the design that follows from
it.

---

## 1. The one question

> We changed how we work. Did it make us cheaper per unit of work shipped?

`/usage` and `ccusage` supply the numerator (what was spent). Git supplies the
denominator (what was shipped). **Nothing joins them, and nothing marks the
changes you made on that timeline.** That join is the product.

Everything else in this design exists to make that question answerable or to act
on its answer.

## 2. Scope

**In.** Outcome-normalized yield, work-mode segmentation, intervention markers,
cost prediction before a dispatch, a best-effort dispatch gate, and the
context-per-call leading indicator.

**Out.** Re-implementing usage reporting. `ccusage` already reads the same
transcripts across sixteen agent CLIs and reports daily/weekly/monthly/session
totals. `agent-yield` consumes that rather than competing with it, and falls back
to reading transcripts directly when it is absent.

**Explicitly not claimed.** Hard enforcement. See §6.

## 3. The model

```
cost  ≈  tool_calls  ×  context_size

yield =  cost  /  outcome
```

`outcome` comes from git and is deliberately plural, because no single measure
survives contact with real work:

| outcome | reads |
|---|---|
| merges | merge commits on the default branch |
| commits | all commits, all branches |
| tests | net change in collected test count |
| lines | net insertions on the default branch |

**Work modes.** A design conversation ships no merges; a mutation-testing pass
ships one merge for enormous spend; a mechanical sweep ships many cheap commits.
Reporting one global ratio across those is the same class of error the case study
documents. Sessions are tagged by mode — `build`, `review`, `design`, `audit`,
`ops` — and yield is reported per mode. **A mode tag is a claim about the work
and must be recorded by the operator, not inferred**, because a tool that guesses
the denominator's meaning will guess flatteringly.

### 3.1 Correction, measured 2026-08-25: context size is not a constant

`case-study.md` §3 says average context is ~136K and is *"stable to 0.4% across
two days and two unrelated workloads."* Run against 20,273 real calls over 15
days, that claim does not survive:

```
median   140,293      min  74,349      max  391,473
stdev / mean = 50.4%
```

The two figures the case study compared (136,449 and 135,943) were adjacent days
of similar work. **Two points agreeing is not stability; it is a sample of two.**

A second machine measured it independently the same day (#11, macOS, an
unrelated corpus: photo-library work, `model-migration-kit`, this repo) and
reported **132,234** — and headlined it as *corroboration*. Both readings are
correct, and together they say something neither says alone.

**The aggregate reproduces. The decomposition does not.**

| corpus | aggregate | decomposed |
|---|---|---|
| Windows, 20,273 calls, 15 days | 145,145 | day range 74,349 → 391,473 |
| macOS, 4,745 calls | 132,234 | main 311,399 vs subagent 89,721 |
| macOS, by working directory | — | 47,347 → 179,864 |

Two machines, unrelated work, aggregates 3–6% either side of 136K. That is a
real and reproducible central tendency. But on **both** machines it dissolves the
moment you split it: 3.5× between main sessions and subagents, ~4× across
workloads, ~5× across days.

So ~136K is a property of *a typical mixture of work*, not a property of a call.
It reproduces because both machines run a similar blend — not because context
size is stable. Averaging a stable mixture of unstable things yields a stable
average, and mistaking that for a constant is the same error the case study
documents, one level up.

**This strengthens §3's mode segmentation** rather than undermining it. Context
size varies precisely along the axis the design already insists on splitting.
Reporting one global context-per-call is the same class of error as reporting
one global yield.

**Consequence for `predict` (§4.4), and it is concrete.** A dispatch is not an
average call. Measured: subagents run at **89,721**, and a subagent given a
self-contained brief and forbidden to explore ran at **17,580**. Projecting such
a dispatch with `REFERENCE_CONTEXT = 136,449` overestimates it by up to 7×.
`predict` should take the context it is projecting *for* — the session's measured
current context when projecting the parent, the observed subagent figure when
projecting a dispatch — and fall back to a reference only when neither is
readable. The band must then carry the context spread as well as the 3×
call-count spread, or it will read as far more precise than the data supports.

**Consequence for `subagent_tokens`.** Its error is not a constant either. The
case study measured ~80×; the macOS run measured **3.7×** on one dispatch (25,874
reported against 94,602 actual). It scales with how much cache the agent read, so
**no correction factor can be applied to it**. Read the transcript or do not
claim a number.

**Consequence for §5.** The daily and session thresholds were calibrated from the
same two-day sample. They should be treated as provisional in the strong sense —
not merely "revisit later" but "derived from a sample now known to be
unrepresentative."

This is exactly the failure the case study documents, turned on the case study
itself: a careful measurement of a real quantity, over-generalised, and then
relied upon. It was caught because the tool was pointed at its own evidence.

## 4. Components

### 4.1 `transcripts` — the reader
Parses Claude Code JSONL, summing the four usage fields **separately** (input,
output, cache-write, cache-read). They are priced differently and collapsing them
is precisely how the 80× error happened. Distinguishes main-session from subagent
transcripts, which nothing else appears to do.

### 4.2 `outcomes` — the git side
Reads merges/commits/tests/lines per day for a repository. No network, no
history rewriting, read-only.

### 4.3 `interventions` — the timeline
A committed file — `interventions.toml` — recording process changes:

```toml
[[intervention]]
date  = "2026-08-25"
name  = "brief-pack: agents stop rediscovering the repo"
expect = "per-agent median falls from 12.4M"
```

`expect` is required. **An intervention recorded without a prediction is not an
experiment**, and the whole point is to be able to be wrong on the record.

### 4.4 `predict` — before you spend
Given the current context size and an expected tool-call count, projects a
dispatch's cost. Default expectation is 70 calls (the median of the twelve agents
on record is 69.5), and the projection carries its own uncertainty: the observed
spread is 3× (62 → 188 calls), so this is a warning aid, not a forecast.

### 4.5 `gate` — best effort, honestly labelled
A `PreToolUse` hook that injects the current burn before a dispatch and can
refuse past a ceiling. Three bands: silent, warn, refuse-with-named-override.

**Measured 2026-08-25 (task 1).** A `PreToolUse` matcher **does** fire on the
main thread's dispatch call, so the gate is viable. The matched `tool_name` is
`Agent`. The payload carries a `tool_input` dict holding the arguments the caller
passed — observed on a real dispatch: `description`, `model`, `prompt`,
`subagent_type`. A gate may therefore read the requested model and subagent type
*before* the spend happens, which is exactly what the three bands need. Read
absent keys as "not passed" rather than "unavailable": the probe call omitted
`isolation`, and it is correspondingly absent, so a gate must default rather than
assume presence. The hook also fired for a **background** dispatch, so the async
path is gated on the same footing as a blocking one.

**The refuse path is confirmed (2026-08-25, under human approval).** A probe
returning exit code 2 on an `Agent` dispatch **blocked it outright**. The agent
never ran, and the hook's stderr came back to the caller as
`PreToolUse:Agent hook error: agent-yield: deny-path test`. The probe's log line
is written before the refusal, so the record shows exactly which dispatch was
stopped. **This is therefore a real gate, not a warning** — all three bands in
§4.5 are buildable as designed, and the third band's override must be a *named*
environment variable rather than a silent bypass.

**The consequence to respect: a gate that crashes refuses everything.** A hook
that raises, times out, or exits 2 by accident is indistinguishable to the caller
from a deliberate refusal. The gate must catch its own exceptions and exit 0 on
any internal error, so that only a *decision* ever blocks a dispatch. An
unreadable ingest file must not become an outage.

**Two harness constraints this must state, not hide:** hooks do not fire for tool
calls made inside a subagent ([#34692], closed as not planned), and hooks load at
session start, so a policy change takes effect at the *next* session.

### 4.6 `report` — the answer
Yield per mode over time, with interventions marked, and a before/after for each
one against its stated `expect`. Terminal table first; a self-contained HTML view
second. **Not a live dashboard** — the question is retrospective by nature.

## 5. Thresholds

Provisional, calibrated from the case study, to be revisited after two weeks of
recorded data:

```
context:   warn 60%    compact at next boundary 75%    compact now 85%
daily:     ceiling 750,000,000     warn from 450,000,000
session:   soft budget 400,000,000
dispatch:  projected = expected_tool_calls x context_size
```

A **natural boundary** is: work landed, checks green, pushed. Above 50% context at
a boundary, prefer a fresh session to a compact — a compact costs a summarization
pass and loses fidelity; a fresh session costs nothing and loses everything not
written down. **Precondition: findings are written down first.** One fleet lost
eleven agents at a token limit with ten having written nothing, and that work is
gone.

## 6. What this tool does not do

Stated here so no reader has to discover it:

- **It enforces at the dispatch and nowhere else.** A `PreToolUse` hook *does*
  refuse an `Agent` dispatch — measured 2026-08-25, §4.5 — so the decision to
  spend is genuinely gated. What follows that decision is not: hooks do not fire
  for tool calls made inside a running subagent ([#34692], closed as not
  planned), and a dedicated spawn hook was requested and declined ([#55144]). An
  agent waved through at a projected 5M that then burns 60M is invisible until it
  finishes. **The gate is a doorway, not a meter.**
- **It does not price anything.** It reports tokens. Rates change and vary by
  plan; a tool that hardcodes them lies quietly later.
- **It does not attribute cost to a person.** The unit is the repository and the
  work mode.

## 7. What would falsify this design

- **If context-per-call stops being stable**, §3's model is wrong and every
  projection built on it is wrong. Reported as a first-class series so it fails
  loudly.
- **If yield-per-mode does not move when an intervention lands**, either the
  intervention did nothing or the mode segmentation is too coarse. Both are
  findings; the tool must report the null result rather than bury it.
- **If the gate is overridden routinely**, the ceiling is wrong, not the work. The
  override rate is recorded and is itself a measurement.

## 8. Order of work

1. ~~Verify whether a `PreToolUse` matcher fires on the dispatch tool.~~
   **Done 2026-08-25. It fires on `Agent` with the dispatch arguments readable,
   and exit code 2 refuses the dispatch.** §4.5 stands in full: all three bands
   are buildable, enforcement on the main thread's dispatch is real. The
   constraint that survives is §6's — hooks still do not fire *inside* a
   subagent, so what is gated is the decision to dispatch, not the spending that
   follows it.
2. `transcripts` + `outcomes`, with the case-study figures as the regression
   fixture: the tool must reproduce 12.4M median and 136K context-per-call from
   real data, or it is wrong.
3. `interventions` + `report`.
4. `predict`.
5. `gate`.

[#55144]: https://github.com/anthropics/claude-code/issues/55144
[#34692]: https://github.com/anthropics/claude-code/issues/34692
