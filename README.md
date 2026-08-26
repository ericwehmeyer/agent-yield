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
different trigger points — and different **units**: capacity is a fraction of
the window (warn 60%, compact 75/85%), cost is absolute tokens (dispatch
300,000, restart 500,000, stop 700,000), because a call's bill is `context ×
rate` and the window does not appear in that expression. There is no knee in
the curve to anchor to, so each cost threshold is a policy choice recorded with
the share of main-thread calls it fires on: ~35%, ~13%, ~7%.

```
agent-yield status     what this session costs, and whether to leave
agent-yield handoff    write down what a restart destroys, before it does
agent-yield boundary   UserPromptSubmit hook: advisory by default
agent-yield resume     SessionStart hook: load the last handoff, exactly once
agent-yield agents     audit dispatches: call counts, and which brief markers
```

`agents` is the post-hoc half of the dispatch rubric, and the only half that
can exist: **hooks do not fire inside a subagent**, so `gate` sees a brief and
never learns what it cost. It joins each dispatch to its child's transcript —
a heuristic join, because the parent's `tool_use` id appears nowhere in the
child and the child's first record has `parentUuid: null`. It reports
`unlinked` rather than guessing.

**It also refuses to answer one question it is asked.** Pooled across
projects, its first run reported briefed dispatches at a median 6 calls
against 57 un-briefed — 9.5×, and entirely an artifact of comparing one
repo's audit fleet against another repo's four short dispatches. Within a
single project: 6.0 against 6.5. There is **no** current evidence that the
three detectable markers predict dispatch length, and `agents` now groups by
the dispatching `cwd` and prints per-project rows rather than a pooled figure.
The fix was removing the code path, not remembering to check.

`status` exits **1** when the session should end — past the hard growth factor,
or in a cost band whose remedy is to leave — so a shell prompt, a `Makefile` or
CI can branch on it without parsing text.

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

**Exit 2 refuses the prompt — measured**, by arming one deliberate refusal
(`agent-yield boundary --arm-refusal`, which disarms itself before refusing so
it can cost at most one re-send). The refused prompt never reached the model,
and the operator saw the hook's stderr in full, the hook's own command path,
and their **original prompt echoed back** — so refusing costs a re-send rather
than someone's typing. `--enforce` is therefore a verified mechanism; it stays
opt-in per install anyway, because the policy question — how often a boundary
should refuse — is separate from whether it can. Install the probe mode to
record what arrives:

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

## Arriving: the other half of the restart

A boundary that makes leaving cheap is worth nothing if arriving is expensive.
`handoff` wrote the findings down and **nothing loaded them**, so every fresh
session opened blank and the operator re-explained — the exact cost the restart
was supposed to avoid.

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup|clear",
        "hooks": [
          {"type": "command", "command": "agent-yield resume --hook --probe"}
        ]
      }
    ]
  }
}
```

**`SessionStart` cannot block a session from starting** — unlike
`UserPromptSubmit`, whose exit 2 was measured refusing a prompt outright. Exit 2
here only surfaces stderr and the session proceeds. It is a **loader, never a
gate**.

**The injection is context, not a display**: it is re-billed on every call of
that session. Measured on a real handoff — 3,892 characters, **~973 tokens,
~95,000 over a 100-call session**, against the ~7,000,000 that the session
writing it had spent. A pointer to the file would cost the same recurring
tokens plus an extra call to read it, and adds a failure mode where the pointer
is ignored.

**Exactly once, and never stale.** `agent-yield resume --hook` archives the
handoff as it injects it, so the injection is exactly-once with no state file
anywhere. A handoff older than 24 hours is neither injected **nor archived** —
still readable by hand, never loaded automatically, because a handoff
describing a session that no longer exists is worse than no handoff at all. It
injects on `startup` and `clear` only: a session that resumed, compacted or
forked already carries the context, and injecting there pays for it twice.

`agent-yield resume` on its own prints the handoff **without** consuming it, so
looking is free.

**`--probe` is not optional in practice, and the reason is a scar.** This hook
shipped reading a key the harness does not send (`session_start_reason`; it is
`source`), declined every real session start, and — because it fails open —
said nothing about it for a day. On a *loader*, silence is indistinguishable
from "nothing to load". So the outcomes are named and recorded to
`.agent-yield/resume-probe.jsonl`:

```
injected  no_handoff  stale  reason_not_injecting  unparseable_payload
```

`has_reason_key: false` in that log is the single line that would have caught
it the same day. The probe records payload **keys, never values** — no
`session_title`, no handoff text, only its length — and there is a test
asserting that.

**The one hook a session cannot measure by installing it is the one that most
needs a probe.** Hook config loads at session start, so no session can measure
a hook it just installed; `UserPromptSubmit` at least fires again on the next
prompt, while `SessionStart` fires exactly once, before anyone can watch.

**Nothing in Claude Code can restart a session** — confirmed, not assumed: no
hook kills and respawns one, and `SessionStart` cannot prevent or control a
session starting. Scheduling can launch `claude -p` non-interactively;
launching an *interactive* session from cron is undocumented. So the loop is
`boundary` → `handoff` → `SessionStart` → **a human types the restart**, and
that last step stays manual.

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
ay 132K 13% 2.6x                              a session that is still cheap
ay 512K 51% 7.4x RESTART -- handoff + restart  one that should have stopped
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

**Rendering it by hand writes to disk — pass `--no-write` when you do.** An
ordinary render appends the payload's `rate_limits` to
`.agent-yield/allowance.jsonl`, which is the calibration input for the plan's
size, and `--probe` appends the payload's key set to the log that documents
what the harness sends. So a synthesized test payload puts invented numbers
into real data, silently; on 2026-08-26 one did (issue #69).
`agent-yield statusline --no-write` prints the identical line and touches
neither log. The default writes because the harness cannot be asked to pass a
flag, and a render that quietly stopped collecting would be the worse failure.

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
