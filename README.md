# agent-yield

**What did that process change actually cost you?**

`/usage` and [`ccusage`](https://github.com/ryoppippi/ccusage) tell you what you
spent. Git records what you shipped. Nothing joins them — so nobody can answer
the question that matters when you are running AI agents at scale:

> We changed how we work last Tuesday. Did it make us cheaper per unit of work
> shipped, or did it just feel like it?

`agent-yield` joins agent token consumption to delivery outcomes, marks the
process changes you made on the same timeline, and tells you whether they
worked. It complements the reporting tools rather than replacing them.

---

## Why this exists

This tool was built after a single day of agent orchestration consumed
**970 million tokens**, and the document being used to budget that work turned
out to be wrong by **~80×**.

The project had a careful metrics file. It recorded that a subagent costs
110–200K tokens, measured across eighteen agents. That number came from
`subagent_tokens`, which each agent reports about itself.

Reading the raw session transcripts instead gave a very different answer:

```
77 subagent transcripts
median agent                       12,400,000 tokens
max                                68,500,000 tokens
```

The reported figure counts output and uncached input. It does not count **cache
reads, which are 97.4% of actual consumption** — because every tool call re-reads
the entire context.

That single correction changes the cost model completely:

```
cost  ≈  tool_calls  ×  context_size
```

Validated: agents reporting 66/62/89/101/73 tool calls at a measured ~136K
average context predict 9–14M tokens each. The measured median is 12.4M.

**A tool that only reports totals cannot catch an error like that.** You catch it
by dividing spend by what got shipped, and noticing the ratio is absurd.

## What it does that others don't

| | `/usage` | `ccusage` | `agent-yield` |
|---|---|---|---|
| What you spent | yes | yes | reads it |
| Per-session / daily reports | yes | yes | reads it |
| **Cost per unit shipped** | no | no | **yes** |
| **Process changes marked on the timeline** | no | no | **yes** |
| **Predicts a dispatch's cost before you spend it** | no | no | **yes** |
| **Context-per-call as a leading indicator** | no | no | **yes** |

The gate reaches the dispatch and stops there. A `PreToolUse` hook can refuse an
agent dispatch outright — measured, not assumed — so the *decision* to spend is
governable, and the requested model and agent type are readable before the spend
happens. The spending that follows that decision is not governable:
[claude-code#34692](https://github.com/anthropics/claude-code/issues/34692)
(hooks not firing for tool calls inside a subagent) and
[claude-code#55144](https://github.com/anthropics/claude-code/issues/55144)
(a dedicated `PreAgentSpawn` cost-policy hook) were both **closed as not
planned**. An agent waved through at a projected 5M that then burns 60M is
invisible until it finishes. `agent-yield` works within what hooks actually do,
and says plainly where it cannot reach.

## The session boundary

Context-per-call climbs as a session runs, and every call re-reads the pile.
Measured over 20,273 calls, **47% of the cache-read bill came from the 20% of
calls made above 200K context** — a band every capacity threshold is silent in,
because at 200K on a 1M window a session is at 20% of capacity and in no danger
of running out of room at all. Capacity and cost are different questions with
different trigger points.

```
agent-yield status     what this session costs, and whether to leave
agent-yield handoff    write down what a restart destroys, before it does
agent-yield boundary   UserPromptSubmit hook: advisory by default
```

`status` exits **1** when the session should end — past the hard growth factor,
or in the steep cost band — so a shell prompt, a `Makefile` or CI can branch on
it without parsing text.

**Nothing in Claude Code can restart a session.** No hook kills and respawns
one, so "automate the restart" is two jobs: make continuing refuse to work, and
make restarting nearly free. The second has to land first. A restart is
expensive only because what is not written down is lost, so a boundary that
cannot be cleared by writing things down punishes the operator for the tool's
own missing half — and gets disabled within a day. `agent-yield boundary`
therefore fires on *"this session is expensive **and** nothing is written
down"*, and one `agent-yield handoff` clears it for the rest of the session.

**`UserPromptSubmit` exit-2 semantics are not measured in this repository**,
and cannot be measured by the session that installs the hook: hook config loads
at session start, so a hook installed now first runs in the *next* session. So
`boundary` advises by default and refuses only under `--enforce`, and ships a
`--probe` mode that records what actually arrives:

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {"type": "command", "command": "agent-yield boundary --probe"}
        ]
      }
    ]
  }
}
```

Hooks do not inherit an activated virtualenv, so use an absolute path to the
binary unless `agent-yield` is on the system `PATH`. Run that for a session,
read `.agent-yield/boundary-probe.jsonl`, and only then decide whether
`--enforce` is buildable. Everything here fails **open**: a hook
that crashes is indistinguishable from one that refused, and a boundary that
crashes locks the operator out of their own session. `AGENT_YIELD_BOUNDARY_OVERRIDE=1`
silences it — named, never silent, and distinct from the gate's override so
that quieting the session boundary does not also quiet the daily ceiling.

## Status

**Implemented, 2026-08-25.** All six components are built and tested —
`transcripts`, `outcomes`, `interventions`, `report`, `predict`, `gate` — behind
an `agent-yield` CLI. The case-study figures are wired in as regression tests:
the parser must reproduce **136,449 context-per-call** and the **12,385,765
median agent** from the recorded data, or it is considered wrong.

| | |
|---|---|
| [`docs/design.md`](docs/design.md) | what it measures, and what would falsify it |
| [`docs/case-study.md`](docs/case-study.md) | the 5.83 billion tokens and the 80× error that produced it |
| [`docs/working-method.md`](docs/working-method.md) | how to run an agent pipeline cheaply — measured, not advice |
| `docs/superpowers/plans/` | the implementation plan, task by task |

Two things this README once claimed that measurement has since corrected: that
dispatch-time enforcement was impossible (it is not — a `PreToolUse` hook
refuses an `Agent` dispatch, verified), and that cache reads are a fixed 97.4%
of consumption (they are not — the share moves with workload; see §3). Both are
recorded rather than quietly edited away, because a document that revises itself
without saying so is the failure this project is about.

## License

MIT
