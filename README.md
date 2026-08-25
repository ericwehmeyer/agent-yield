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

## Status

**Pre-implementation.** The design is in
[`docs/design.md`](docs/design.md); the measured case study that produced it is
in [`docs/case-study.md`](docs/case-study.md).

Nothing here is built yet. This README describes what is being built and why,
and will be corrected if the measurements stop supporting it — see
*What would falsify this* in the design.

## License

MIT
