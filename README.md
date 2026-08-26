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

**`UserPromptSubmit` fires, and its payload is measured** — by a later session,
because hook config loads at session start and no session can measure a hook it
installs. One prompt in a fresh session recorded the event carrying `cwd`,
`hook_event_name`, `permission_mode`, `prompt_id`, `session_id`,
`transcript_path` and `prompt`, so the live session is identified twice over
and the boundary no longer guesses at which session it is measuring. It also
never widens to "the most recently modified transcript": with two sessions
open that is routinely the *other* one.

**Whether exit 2 refuses a prompt is still unmeasured**, so `boundary` advises
by default and refuses only under `--enforce`. `agent-yield boundary
--arm-refusal` arms one deliberate refusal to settle it, and disarms itself
before refusing, so the next prompt goes through either way. Install the probe
mode to record what arrives:

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

## The status line

```json
{
  "statusLine": {
    "type": "command",
    "command": "agent-yield statusline"
  }
}
```

```
ay 132K 13% 2.6x                          a session that is still cheap
ay 296K 30% 7.4x KNEE -- handoff + restart    one that should have stopped
```

Context, share of the window, growth since the session's opening calls, and a
marker once a threshold is crossed. **It is not a model call: it costs no
tokens and burns no context**, which makes it the only lever here that can be
enforced continuously without paying for the enforcement — and the session
that measured the batching lever went on to ignore it, so ambient beats
remembered.

Unlike hooks, **the `statusLine` setting takes effect immediately**, in the
session that writes it. The payload hands over the real
`context_window.context_window_size`, so the bands are computed against this
session's actual window rather than the provisional 1M default, and the
current context, so the usual render reads no transcript at all. It fails
**silent**: malformed input, a missing transcript or a broken measurement all
print `ay -` and exit 0, because a status line that raises leaves a stack trace
under every keystroke and the operator's remedy is to delete the setting.

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
