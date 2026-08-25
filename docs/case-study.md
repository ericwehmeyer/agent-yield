# Case study: 5.83 billion tokens, and a metrics file that was wrong by 80×

**Measured 2026-08-25 from Claude Code session transcripts. Every number here
came out of `~/.claude/projects/<slug>/**/*.jsonl`, which records a `usage`
block on every assistant message. Where a figure is derived rather than read, it
says so.**

This is the analysis that produced `agent-yield`. It is kept in the repository
because the tool's central claim — that totals alone cannot tell you whether your
process is working — is a claim this analysis is the evidence for.

---

## 1. The setting

A Python project being built by a fleet of Claude Code agents: four roles per
unit of work (implementer, blind tester, reviewer, fix pass), several running
concurrently, coordinated across two machines through GitHub Issues.

It worked. On 2026-08-24 that pipeline produced:

| | |
|---|---|
| commits, all branches | 255 |
| merges landed on `main` | 37 |
| net lines on `main` | +34,223 / −1,699 |
| test suite | ~315 → 2,283 |
| active hours | 13 |

It also exhausted a Max plan.

## 2. What it cost

424 transcripts, 22 active days, **5.83 billion tokens**.

```
2026-08-14   1,678,328,586   <- record
2026-08-24     970,162,095
2026-08-25     744,876,333   <- by 06:18, one session
2026-08-21     670,682,026
2026-08-22     512,164,217
2026-08-01     470,679,576
2026-08-13     248,726,218
             ...16 further days, every one under 125M
```

**Median day ~57M. The top six days are 77% of the month.** The distribution is
not noisy — it is bimodal. There are ordinary days, and there are fan-out days.

Any budget built on an average would be wrong about both.

## 3. Where it goes

| | 2026-08-24 | 2026-08-25 (to 06:18) |
|---|---|---|
| API calls | 6,910 | 5,333 |
| output | 4,034,858 | 2,501,266 |
| cache write | 23,248,272 | 14,552,948 |
| **cache read** | **942,865,149** | **724,985,381** |
| uncached input | 13,816 | 10,666 |

**Cache reads are 97.4% of consumption.**

Which yields the constant the whole tool rests on:

```
cache-read / calls  =  136,449 tokens per call   (08-24)
                       135,943 tokens per call   (08-25)
```

**Average context is ~136K tokens, and it is re-read on every single API call.**
Stable to 0.4% across two days and two unrelated workloads.

## 4. The error

The project had a metrics document. It was careful, it was appended to rather
than rewritten, and it recorded per-role costs measured across eighteen agents:

```
implementer 110k  <  reviewer 150k  <  blind tester 169k  <  fix pass 198k
a full unit of work through all five stages: 600-650k tokens
```

Reading the transcripts instead:

```
77 subagent transcripts
total                              1,190,554,043 tokens
median per agent                      12,385,765
max                                   68,475,554
```

**An ~80× undercount.** The document reported `subagent_tokens` — what each agent
says about itself — which counts output and uncached input and not the cache
reads that are almost the entire bill.

The same document also recorded, as a finding:

> *"Tool calls do not predict anything… Count tokens. Ignore call counts."*

That is correct for predicting *reported* tokens, and exactly wrong for
predicting cost — because every tool call re-reads the whole context. The
correct model is the one that document's own data supports once you use the
right numerator:

```
cost  ≈  tool_calls  ×  context_size
```

Agents reporting 66/62/89/101/73 tool calls predict 9–14M each at 136K context.
Measured median: **12.4M**. Subagents are **70% of all consumption**.

**The failure was not a lack of measurement. It was a well-maintained
measurement of the wrong quantity, consulted confidently.** On the night this was
found, that document was used to justify a dispatch decision — the operator
stated four agents had cost 562K when they had cost closer to 40M.

## 5. Why totals could not catch it

Divide spend by what shipped:

| day | tokens | merges | **tokens per merge** |
|---|---|---|---|
| 2026-08-24 | 970,162,095 | 37 | **26.2M** |
| 2026-08-25 | 744,876,333 | 6 | **124.1M** |

**4.7× more expensive per merge**, one night to the next.

That ratio is what makes the question askable at all. And the instrument
immediately raises the right objection to its own number: the second night's
merges were gate repairs carrying five-revert proofs, and a large share of its
spend was a design conversation that ships no merges whatsoever.

**That objection is the point.** A total cannot be argued with because it makes
no claim. A ratio makes a claim, and a claim can be wrong in an informative
direction. The confound — that work modes differ — is a real requirement
discovered by taking the measurement, and it is why `agent-yield` segments by
work mode rather than reporting one global number.

## 6. What the upstream harness will and will not do

Two feature requests settle the boundary of what a tool can enforce:

- [**#55144** — `PreAgentSpawn` hook: executable cost policy for sub-agent
  dispatch](https://github.com/anthropics/claude-code/issues/55144). **Closed as
  not planned.** Its argument corroborates §3–§4 independently: *"sub-agent costs
  are non-obvious and massive… differences can approach 10× when accounting for
  model tier inheritance, cache read rates, and 200K extended-context pricing
  cliffs."*
- [**#34692** — PreToolUse/PostToolUse hooks do not fire for subagent tool
  calls](https://github.com/anthropics/claude-code/issues/34692). **Closed as not
  planned.**

So dispatch-time cost governance is a documented gap that will not close
upstream. A tool in this space should say so plainly and work within what hooks
actually do, rather than implying an enforcement guarantee it cannot keep.

One further constraint, found by testing rather than reading: **hooks load at
session start.** A budget policy edited mid-session does not take effect until
the next one. That is a real limit on how responsive any gate can be, and it was
discovered by writing a probe hook, watching it not fire, and checking why.

## 7. What this says about running agent fleets

1. **Measure the artifact, not the agent's self-report.** The transcripts are
   ground truth; `subagent_tokens` is a subset that happens to exclude almost all
   of the cost.
2. **Cost is `tool_calls × context_size`.** Both terms are controllable, and the
   context term multiplies across every call an agent makes — which is why
   trimming an agent's starting brief pays roughly eighty times over.
3. **Normalize by what shipped.** A total tells you nothing about whether a
   change helped. A ratio does, and invites the objection that improves it.
4. **A well-maintained metric of the wrong quantity is more dangerous than no
   metric**, because it is consulted with confidence.
