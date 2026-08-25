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

**Still unverified: the refuse path.** That the hook *fires* is not that exit 2
*blocks*. Testing that requires installing a hook which denies a tool call, which
is a privileged act and was correctly refused when this session tried to
self-approve it. **Until it is verified under human approval, this component is
honestly a `warn`, not a gate** — build the silent and warn bands first, and do
not ship refuse-with-named-override on the assumption that exit 2 works here.

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

- **It does not guarantee enforcement.** The upstream hooks required for reliable
  dispatch governance were requested and declined ([#55144], [#34692]).
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
   **Done 2026-08-25: it fires, on `Agent`, with the dispatch arguments
   readable.** §4.5 stands. One piece carries forward: the refuse path (does
   exit 2 actually block?) is untested and needs human approval to test, so
   §4.5 ships as `warn` until it is settled. Fold that test into step 5.
2. `transcripts` + `outcomes`, with the case-study figures as the regression
   fixture: the tool must reproduce 12.4M median and 136K context-per-call from
   real data, or it is wrong.
3. `interventions` + `report`.
4. `predict`.
5. `gate`.

[#55144]: https://github.com/anthropics/claude-code/issues/55144
[#34692]: https://github.com/anthropics/claude-code/issues/34692
