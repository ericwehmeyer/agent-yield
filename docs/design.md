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

### Cost thresholds (added 2026-08-25; units corrected 2026-08-26, issue #23)

The family above is capacity: it answers "am I about to run out of window."
Measured over 20,273 calls on 2026-08-25, 47% of the cache-read bill came from
the 20% of calls made above 200K context — a band every capacity rule is silent
in. On a 1M window, 200K is 20% of capacity; the 60% warn fires near 600K, by
which point each call bills roughly 3x what it did at 200K. This tool told its
own operator "21% of window, no action needed" on a session already deep in the
expensive band. That was the design being wrong, not the operator. So a second
family, answering "how much does the next call cost":

```
cost:      dispatch 300,000 tokens    restart 500,000    stop 700,000
```

**Absolute tokens, not fractions of the window.** The first version of this
family shipped as `COST_KNEE = 0.20` and `COST_STEEP = 0.40`, on the reasoning
that fractions survive a model change. They survive it syntactically and break
it semantically. Cost is `context × rate`; the window does not appear in that
expression, so `0.20 × W` moves when `W` changes while the bill does not:

| window | `0.20 × W` fires at | what a 200,000-token call costs |
|---|---|---|
| 500,000 | 100,000 | 200,000 tokens |
| 1,000,000 | 200,000 | 200,000 tokens |
| 2,000,000 | 400,000 | 200,000 tokens |

Same call, same bill, three different verdicts. The code's own comment conceded
it — *"calibrated on a 1M window only"* — and **a cost threshold that needs a
window caveat is measuring the wrong thing.**

**Abandoning fractions leaves no gap**, and this is written down so nobody
reverts it: the obvious defence is that on a 200K-window model an absolute
150K threshold barely fires and the family goes quiet exactly when a session is
in trouble. It fails, because at that window a 150K call is already 75% of
capacity and `COMPACT_AT_BOUNDARY` is firing. **Capacity is genuinely
fractional and cost genuinely is not; together they cover both regimes**, and
the cost family being silent on a small window is correct rather than a hole.

**There is no knee, and 200,000 was a bucket edge.** Plotted continuously the
spend curve decays smoothly on both machines with no break anywhere — main-thread
share of the bill above each threshold runs 95% → 87% → 78% → 67% → 54% → 36%,
monotone throughout. §11's superlinear fit (`calls^1.54`) is why: a session does
not cross into an expensive state, it accumulates into one. **So no threshold
here can be discovered; each is a policy choice about what share of calls should
trip it**, and that share is recorded next to the constant, because the same
token count sits at a different percentile on a different machine.

**— and at a different percentile in a different *project on the same machine*,
by a wider margin (#80, 2026-08-26).** The table below originally carried one
pooled figure per constant — ~35% (p65) / ~13% (p87) / ~7% (p93), macOS, 1,165
main calls, 2026-08-25. **That pooled form was the defect**, and it is the same
one the dashboard rule names: no decomposable aggregate without its
decomposition. Every main-thread call under `~/.claude/projects`, deduped,
2026-08-26:

| | tokens | share of main-thread calls | of the bill |
|---|---|---|---|
| `COST_DISPATCH` | 300,000 | 0%–54% (p46–p100) · pooled 18% (p82) | 0%–84% · pooled 48% |
| `COST_RESTART` | 500,000 | 0%–33% (p67–p100) · pooled 7% (p93) | 0%–63% · pooled 27% |
| `COST_STOP` | 700,000 | 0%–19% (p81–p100) · pooled 4% (p96) | 0%–42% · pooled 15% |

Ranges are across three macOS projects, n = 1,490 `agent-yield` / 437
`model-migration-kit` / 498 `Pictures`, 2,425 calls pooled. **300,000 sits at
p46 in one repo and p100 in another**, so the family fires on more than half of
`model-migration-kit`'s main calls and on *none* of this repo's — whose peak main
context, over 1,490 calls and 20 sessions, is 295,861. The pooled figure also
moved 46% → 18% between the two measurement dates with nothing changed about how
any session is run: on the calibration day the corpus was 100% `Pictures` +
`model-migration-kit`, today it is 96% `agent-yield`. **The mixture moved, not
the behaviour.**

**These are not retuned per project, and must not be.** #23 put cost in absolute
tokens so a threshold would stop being a property of the observer; a per-repo
retune is that same error with *project* substituted for *window*. The same
300,000-token call costs the same in either repo. **A repo whose calls never get
expensive should see this family stay silent** — the argument two paragraphs up,
about small windows, unchanged. Nor is `agent-yield`'s 295,861 peak a near-miss
inviting a nudge: 8.5% of its calls pass 200K, 1.4% pass 250K, and the median
*session* peak is 156,455. 300,000 is off the end of this repo's workload, not
1.4% away from it.

The original proposal on #23 was 150K/250K/400K, anchored to the Windows
median. A threshold at the median fires on half of all calls — the failure
`RESTART_HARD_FACTOR = 4.0` was set to avoid, since **a boundary that fires in
every working session gets disabled, and a boundary that gets disabled is worth
nothing.** Both machines measured that family firing on 42–50% of main calls;
neither set out to. The numbers above are the counter-proposal, agreed on the
issue.

**Three bands, because there are three distinct actions** — a band that shares
another's remedy should not exist. Past `COST_DISPATCH`, stop growing: push
reads and searches out to briefed subagents. Past `COST_RESTART`, leave at the
next natural boundary. Past `COST_STOP`, leave now, without waiting for one.
The bands are named for their remedies rather than for a shape in the curve,
since the curve has no shape.

**Main-thread calls only.** Main and subagent are two populations 2.1–2.6×
apart — median 184,905 against 88,201 on macOS, 249,257 against 97,341 on
Windows — and a subagent above these numbers is a brief that failed, not a
session to restart. Same token count, different diagnosis, different remedy;
one family cannot serve both, so `cost_band` does not try.

Each band fires once per session, at the crossing, in the next report — never
as an interrupt. The wording is not the capacity wording and never says
compact:

- dispatch: "This call carries N tokens, past 300,000. Every call from here
  re-reads all of it. Dispatch reads and searches to briefed subagents and keep
  this context flat. This is spend, not space — capacity is a separate question
  and may be fine."
- restart: "…past 500,000. At the next natural boundary — work landed, checks
  green, pushed — write findings down and start fresh. Do not compact: a
  compact pays a summarization pass to stay in the expensive band; a restart
  leaves it."
- stop: "…past 700,000. Do not wait for a boundary. Run `agent-yield handoff`,
  then start a fresh session; the next 40 calls here bill several times what
  they would there."

Level, not growth — and both families stay. `session.restart_advice` already
fires on context/call doubling from the session's opening calls; a growth
trigger catches runaway sessions but is blind to sessions that open expensive,
and those are the norm: one machine's main sessions averaged 311,399
context/call against 89,721 for subagents, no doubling anywhere. Level says
where the session is; growth says where it is going; the concentration finding
is about where sessions are.

The dispatch band will fire on a third of working main calls. That is the
finding, not a false alarm — mains live in the expensive band, and a rule that
stays polite about it is the rule that said "no action needed." The habituation
risk attaches to repetition, not to firing: one message per band per session,
with operator action reserved for the two leave bands, is a status change, not
a siren.

`gate` does not carry this family. Gate refuses dispatches, and past the
dispatch threshold a dispatch is the remedy — subagents ran at 89,721
context/call against parents' 311,399, and the advice there is precisely
"dispatch more." A cost-band refusal would block the cheapest path and force
inline work in the most expensive context, and a hook that fails open cannot
fail politely: wrong once, it does maximum damage in exactly the sessions that
most need to dispatch. Gate keeps its daily-ceiling refusal; the cost family is
advisory only.

The two families coexist: capacity protects the window, cost protects the
bill. Capacity thresholds above are unchanged and still correct for what they
measure; the correction recorded here is that they were the only family — and
the second correction, three days later, is that they were the only *units*.

### The session boundary (added 2026-08-26)

The cost family above is advice, and advice was measured as insufficient twice
in one day: `session.restart_advice` printed its line on the macOS session at
6.6x growth and that session ran for another twenty minutes. Two machines, two
operators, the same failure. **Measurement without enforcement changes
nothing** — and it is not a discipline problem, because both operators had
just written the measurement.

Nothing in Claude Code can restart a session. So enforcement decomposes into a
**boundary** (make continuing refuse to work) and a **handoff** (make
restarting nearly free), and the handoff has to land first. A restart is
expensive only because everything not written down is lost — one fleet lost
eleven agents' findings with ten having written nothing. Install a boundary
before the handoff exists and the operator disables it, correctly.

**The boundary fires on "expensive AND nothing written down", never on
"expensive".** That distinction is the whole design:

- It cannot fire twice for the same reason. One `agent-yield handoff` clears
  it for the session, so it is a status change, not a siren.
- It is cleared by doing the thing the boundary exists to protect, which makes
  compliance and the remedy the same action.
- It cannot lock anyone out. The escape is one command, and there is a named
  override (`AGENT_YIELD_BOUNDARY_OVERRIDE`) besides.

"Written down" means *written during this session*, not *written recently*: a
handoff from yesterday describes a session that no longer exists, and any
freshness rule tied to the last call goes stale one call later and makes the
boundary unclearable.

**A blanket hard stop on prompts was considered and rejected.** #19 asked for
one above a hard growth factor. A bug in `gate` blocks dispatches; a bug in a
prompt gate locks an operator out of their own session, including out of the
commands that would end it cleanly. Against that, the benefit of an
unconditional stop over a clearable one is a single nudge — the operator who
has already written the handoff is exactly the one who does not need to be
stopped. The conditional boundary keeps the enforcement and removes the
failure mode.

**And the mechanism it would need is unmeasured.** Whether `UserPromptSubmit`
exit 2 blocks a prompt is not verified in this repository, and **cannot be
verified by the session that installs the hook**: hook config loads at session
start. So `boundary` advises by default, refuses only under `--enforce`, and
ships `--probe`, which records what arrives and always exits 0. If the probe
shows exit 2 does not block, `--enforce` is not buildable and the status line,
`status`, and the advisory are the whole answer. That is a legitimate outcome,
recorded in advance so it cannot be quietly skipped.

### The probe, read (2026-08-26)

The boundary shipped with its own mechanism unmeasured, and #22 exists because
no session can measure a hook it installs. A later session read
`.agent-yield/boundary-probe.jsonl`. **The hook fires**, and one prompt in a
fresh session recorded `UserPromptSubmit` carrying exactly:

```
cwd, hook_event_name, permission_mode, prompt_id, session_id,
transcript_path                                              (+ prompt)
```

Two consequences, both already in the code:

- **The live session is identified twice over**, by path and by id, and the
  transcript stem equals the session id. The guessing `boundary._stats_for`
  shipped with is gone; `session.resolve_transcript` uses the observed
  contract and records which route fired.
- **The "most recently modified transcript" fallback was a correctness bug,
  and is removed from the hook path.** A payload that names a session the tool
  cannot find now measures *nothing*. With two sessions open, the most recent
  transcript is routinely the other one's, and a boundary enforcing against
  the wrong session is the worst object in this repository.

**Exit 2 was then measured, and it refuses the prompt.** One deliberate
refusal, armed by `agent-yield boundary --arm-refusal` under human approval —
the same move `gate` was measured with, with the sentinel deleted *before* the
refusal is returned so that even a blocking exit 2 cannot cost more than one
re-send. Fired 2026-08-26 01:48 UTC. The refused prompt never reached the
model, and the operator saw:

```
UserPromptSubmit operation blocked by hook:
  [/path/to/agent-yield boundary --probe]: <the hook's stderr, verbatim>

Original prompt: <what they typed>
```

So `--enforce` is buildable, and the safety argument shifts in its favour:

- **stderr reaches the operator in full**, so a boundary that refuses can
  explain itself and name its remedy. A silent refusal would have been
  unusable regardless of whether it worked.
- **The hook is identified by command path in the message**, so a refusal is
  traceable to its cause rather than looking like the harness misbehaving.
- **The harness echoes the prompt back.** Refusing costs a re-send, not the
  operator's typing — which was most of what the caution about `--enforce`
  was protecting against.

What does *not* change: the boundary still fires only on "expensive AND
nothing written down", and a bug that refuses unconditionally still locks the
operator out of the session, if not out of their words. Enforcement remains
opt-in per install, and `AGENT_YIELD_BOUNDARY_OVERRIDE` remains the escape.
The mechanism is verified; the policy is still deliberately conservative.

### Arriving: SessionStart loads the handoff (added 2026-08-26, issue #26)

The boundary and the handoff make *leaving* cheap. Nothing made *arriving*
cheap, and the two are one lever: a fresh session opened blank and the operator
re-explained, which is precisely the cost the restart was supposed to avoid.
Half a lever is not a lever.

**Contract, corrected 2026-08-25 after it silently failed.** `SessionStart`
fires with matchers `startup`, `resume`, `clear`, `compact`, `fork`, and names
which one in **`source`** — not `session_start_reason`, which is what this
section claimed and the hook read for its first day alive. That string does not
occur anywhere in the harness binary; `source` is what it constructs. The hook
therefore read an absent key on every real session start, took the fail-open
path, and injected nothing, while the unit tests passed because the fixture
invented the same key the code read. **A contract labelled "measured" that was
in fact read off documentation is the exact failure this repo exists to catch**,
and it cost a session its handoff. `tests/test_resume.py` now pins the real
payload shape verbatim rather than building it from the code's own assumption.
`SessionStart` injects context as `{"hookSpecificOutput": {"hookEventName": "SessionStart",
"additionalContext": ...}}`. **It cannot block a session from starting** — exit
2 only surfaces stderr, and the session proceeds. Where `UserPromptSubmit` gave
a verified refusal (§5, #22), this gives a loader. The asymmetry is the design
constraint: enforcement lives at the prompt, loading lives at the start.

**The injection is context, so it is re-billed on every call of the session.**
That is this tool's founding economics turned on the tool itself, and it decides
the content question. Measured on a real handoff: 3,892 characters, **~973
tokens, ~95,000 over a 100-call session** — against the ~7,000,000 the session
that wrote it spent. A pointer to the file loses: the successor reads the file
anyway, so a pointer costs the same recurring tokens plus an extra call, and
adds a failure mode where it is ignored.

**Staleness is solved by consuming, not by checking.** The hook archives the
handoff as it injects it, so the injection is **exactly-once with no state
anywhere** — no flag file, no "have I already loaded this" bookkeeping that can
drift from reality. Older than 24 hours it is neither injected nor archived:
still readable by hand, never loaded automatically. **A handoff describing a
session that no longer exists is worse than no handoff**, because it is
confidently wrong rather than absent.

**The injection is invisible, so it announces itself — and as of 2026-08-26
that is measured, not assumed.** `additionalContext` puts text into the
successor's context with nothing on screen: a working loader and #29's broken
one look identical to the operator, which is precisely how #29 stayed hidden
for a day while the operator said "I don't see it" and was right. The hook now
emits an announcement — `[agent-yield] handoff loaded: N chars, written … ago.`
— on **both** `systemMessage` and stderr, and records which it emitted in the
probe log. **The operator confirmed seeing that line** at the 20:01 UTC `clear`
start (7,596 chars, session `b008f92d`), the first start after the announcement
shipped. What is settled is that a line renders; **which of the two channels
rendered it is not**, because both were emitted on the same start and neither
was suppressed to isolate the other. Recorded that way rather than credited to
`systemMessage` because the docs say so — that substitution is §4.6's original
failure. `resume --status` reads the flag back and now says which half it is
reporting: receipt from the transcript, visibility from the announcement.

`startup` and `clear` only. A session that resumed, compacted or forked already
carries the context; injecting there pays for it twice and buys nothing.

**The objection this cannot answer, and why it ships anyway.** The hook cannot
read intent, so a session starting genuinely unrelated work eats an injection it
did not want. That is bounded — one session, one window, ~95K worst case, about
1.5% of what the session that wrote it spent — and the preamble names the
handoff as written by an ended session and tells such a session to set it aside.
Against that, the alternative is a command the operator must remember, and this
repo has measured twice what remembering is worth: `restart_advice` printed and
the session ran another twenty minutes.

**What this does not close.** Nothing in Claude Code can restart a session — no
hook kills and respawns one, and `SessionStart` cannot prevent or control a
session starting. Scheduling can launch `claude -p` non-interactively;
launching an *interactive* session from cron is undocumented (issue #28). So
the loop is `boundary` → `handoff` → `SessionStart` → **a human types the
restart**, and claiming otherwise would be claiming a closed loop that is
three-quarters closed.

### 4.7-adjacent: the status line, and what the harness already knows

`statusLine` is the one lever that enforces itself at zero token cost, and
measuring its contract turned up something the rest of this document assumed
away. **The `statusLine` setting takes effect immediately**, in the session
that writes it — unlike hooks, whose config loads at session start. And the
payload carries, alongside `session_id` and `transcript_path`:

```
context_window.context_window_size          1000000
context_window.used_percentage              11
context_window.current_usage.{input_tokens, output_tokens,
    cache_creation_input_tokens, cache_read_input_tokens}
rate_limits.{five_hour,seven_day}.used_percentage
cost.total_cost_usd
```

- **`DEFAULT_WINDOW` no longer has to be a guess.** thresholds.py says "the
  tool cannot read the model's context window, so a caller must say"; in the
  status line it can, so the measured window wins over the provisional
  constant and the cost bands are computed against the window this session
  actually has. Everywhere else the constant still stands.
- The three input fields summed to 105,788 against 104,156 measured from the
  transcript's last call — the same quantity, one call apart. The current
  context is handed over, so the common render reads no transcript tail at
  all.
- `cost.total_cost_usd` is deliberately ignored. Tokens, never money — and on
  a subscription it is an API-rate equivalent rather than a bill, so rendering
  it would be doubly wrong.
- `rate_limits.seven_day.used_percentage` is the operator's real currency on a
  subscription, and is the obvious next thing this line could carry. Out of
  scope for the ticket that built it; recorded rather than quietly added.

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
- **If a fresh session that reads the handoff is not cheaper than the session
  it replaced**, the boundary is cruelty rather than efficiency and the whole
  restart lever is wrong. The test is stated so it can fail: compare the first
  ten calls of the new session against the last ten of the old one.

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
