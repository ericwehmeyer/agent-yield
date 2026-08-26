# Start here after a session restart

**Written 2026-08-25 20:45 EDT (Windows), updated 21:10, 21:30 and 21:55 EDT
(macOS), each time immediately before a deliberate restart.**

The restart is itself the finding — four times now. See *Why these sessions
ended* at the bottom; it is the most reusable thing on this page.

**Everything below the Windows machine wrote at 20:45 still stands, except its
cost thresholds — see #23.** What the macOS sessions changed is marked
**[macOS 21:10]**, **[macOS 21:30]** and **[macOS 21:55]**.

**[macOS 21:30] The boundary and the handoff are built (#19), and the cost
family is implemented (#17).** `agent-yield handoff` before you restart —
that is now the first move of every session end, and the boundary is cleared
by making it.

**[macOS 21:55] The mechanism under all of it is measured. `UserPromptSubmit`
exit 2 refuses the prompt** (#22, closed), **the status line is live** (#18
Part B), **and the cost thresholds you are about to read are in the wrong
units** — #23 is right and answered, and implementing it is the next action.

**[macOS 2026-08-26] #23 is implemented and closed; the cost family is in
absolute tokens.** Anything below this line still quoting `COST_KNEE = 0.20`
or a "steep band" is describing the previous units — `thresholds.py` and
design.md §5 are the current statement. **`working-method.md` §12 is new: the
dispatch rubric**, which is what §11's levers look like as an instruction.

## State of the board

**The tool is built and works.** Nineteen modules, **187 tests**, green on
Windows and macOS, everything pushed, working tree clean.
`docs/superpowers/plans/2026-08-25-agent-yield.md` is fully executed.

```
agent-yield ingest    read transcripts, dedup, persist to .agent-yield/calls.jsonl
agent-yield outcomes  what git says shipped
agent-yield report    the join, per mode, with intervention before/after
agent-yield tag       record a session's work mode (never inferred)
agent-yield predict   project a dispatch's cost as a band
agent-yield gate      PreToolUse hook -- all three bands, fails open
```

**[macOS 21:10] Two modules added since:** `session.py` (measure the live session,
say when to restart) and `report_html.py` (the self-contained dashboard, #16).

**[macOS 21:30] Two more, and three subcommands:**

```
agent-yield status    what this session costs; exit 1 means leave
agent-yield handoff   write down what a restart destroys, before it does
agent-yield boundary  UserPromptSubmit hook -- advisory unless --enforce
```

**[macOS 21:55] One more, and it is the cheapest thing here:**

```
agent-yield statusline   one line, rendered continuously, at zero token cost
```

Both hooks are installed in `.claude/settings.json` on this machine (gitignored
— reinstall from the README on any other). The status line is live; the
boundary runs in `--probe` mode and advises.

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
| ~~**#23**~~ | **Closed 2026-08-26.** Cost is absolute tokens now — `COST_DISPATCH = 300_000` (p65) / `COST_RESTART = 500_000` (p87) / `COST_STOP = 700_000` (p93), each carrying the share of main-thread calls it fires on, and a test that fails if a constant loses its percentile. `window` is off the cost path: `cost_band` and `cost_advice` raise `TypeError` if handed one. Three bands because there are three actions; `cost_band` is main-thread only. design.md §5 rewritten. |
| **#18** | Three levers. Parts A, B and D **done**; **C (agent-length audit) and E (the falsification test) are open.** E is the one that could invalidate §11's headline — one task dispatched as one long agent against three short ones. It needs subagents and a lot of tokens: give it a fresh session, not the tail of one. |
| **#24** | The status line could carry `rate_limits.seven_day.used_percentage` — measured, free on every render, and on a subscription it is the operator's *real* currency. The design question is whether an allowance percentage counts as "money" under the tokens-never-money rule. **Retitle it: it says "Task 23" and collides with #23.** |
| ~~**#22**~~ | **Closed 21:55.** Exit 2 refuses the prompt, stderr reaches the operator, and the harness echoes the prompt back. |
| **#20, #21** | Opened by the Windows machine at 01:19–01:20 UTC while the macOS session was working: a blind re-measurement of context/call by model and role, and `report --by-model`. Not started. |
| **#13** | `predict` must use the context it is projecting *for*. **Deliberately deferred** to the week-1 review — do not implement before 09-01. **Partly overtaken:** `bb2cbc0` split predict into two populations, which answers most of it. Read that commit before the review argues with the ticket. |
| ~~**#19**~~ | **Closed 21:30.** Handoff, status, boundary — B before A before C, as it insisted. |
| ~~**#17**~~ | **Closed 21:30.** `COST_KNEE`/`COST_STEEP` implemented; the family is surfaced by `status` and the boundary, and gate still does not carry it. |

**#17's finding**, which is what set the whole last hour going:

```
CACHE-READ BILL BY CONTEXT SIZE OF THE CALL
   0- 50K   3,389 calls    106,116,334    3.6%
  50-100K   5,650 calls    420,711,400   14.3%
 100-200K   7,190 calls  1,023,363,126   34.8%
 200-400K   2,911 calls    817,724,501   27.8%
 400+       1,133 calls    574,603,095   19.5%
```

**[macOS 21:55] Read this next paragraph with #23 in hand.** The 200K is a
bucket edge, not a knee: plotted continuously the curve decays smoothly on both
machines with no break anywhere, and the 47%/20% split is a Windows fact — on
macOS, 47.9% of main-thread calls are above 200K and they carry 78.8% of the
bill. The *shape* of the finding holds everywhere; the numbers do not travel.

**47% of the bill comes from the 20% of calls made above 200K context.** §5's
thresholds (warn 60%, compact 75/85%) are *capacity* thresholds — they answer
"am I about to run out of window", not "am I spending efficiently". At 200K on a
1M window a session is at 20% of capacity and silent by every §5 rule, while
already in the band that generates half the spend. The issue asks for a cost
threshold family firing roughly 3× earlier, and for advice that says *dispatch or
restart*, not *compact*.

## [macOS 21:10] What the last hour added

**§11 of `working-method.md` — the method's own yield, and it is a null result.**
Everything in that doc before §11 was per-call economics. §11 is the first
end-to-end measurement of whether the method ships more per token:

| | solo | dispatching |
|---|---|---|
| tokens/issue | 2,396,312 | 2,242,826 |
| tokens/line | 7,419 | 4,951 |

**1.07× per issue** against per-call economics predicting 6.2×. Weighting by real
per-field rates moves it to 1.01×, so the "you collapsed the four fields"
objection does not rescue it. **The parent ate the gain** — its context went
58,475 → 126,522 between the phases because it read every diff and ran every
suite itself.

**The single most important number of the session:**

> **7 agents, 76 calls, 3.5M tokens — 19% of the session. The parent was 81%.**

118 parent calls against 76 agent calls, and the parent burned four times the
tokens. The agents were never the expense.

**Cost is superlinear in the length of one unit of work.** Fitted: agents
`calls^1.54`, parent `calls^1.41`. One 27-call agent cost 1,879,466 tokens — 21%
of the session in a single dispatch — against 840,036 for the same calls as three
measured 9-call agents. **Cap dispatches at ~10 calls and split the task.**

**`predict` was wrong on both factors, now fixed** (`bb2cbc0`). It projected ~9.4M
for every dispatch; the four real briefed agents cost 94,602 / 280,012 / 569,321 /
1,879,466 — overestimates of 99.5× / 33.6× / 16.5× / 5.0×. Briefed and un-briefed
agents are two populations whose call ranges **do not overlap at all** (4–27 vs
62–188), so one set of defaults could never describe both. The briefed band now
reads 0.1M–1.8M and brackets all four.

**A growth trigger alone is not enough** (`c9bc11a`, decided on Fable 5).
`session.restart_advice` fires on context/call doubling, but **main sessions
average 311,399 context/call without ever doubling** — they open expensive. The
47%-of-bill finding is invisible to a growth check. §5 now carries both a level
family (`COST_KNEE = 0.20`, `COST_STEEP = 0.40` of window) and the growth trigger,
and records why `gate` deliberately does **not** carry the cost band: past the
knee the remedy is to dispatch, so a blocking hook would cut off the cheapest path.

**Nothing in Claude Code can restart a session.** No hook kills and respawns one.
So "automate the restart" is really two jobs — make continuing refuse to work, and
make restarting free. #19 enumerates both, and insists on the handoff first.

**Billing, checked:** no `ANTHROPIC_API_KEY` and no `ant` CLI on the Mac, so this
runs on the Max subscription, not API billing. **Every dollar figure in the
commit log and the docs is an API-rate equivalent, not a bill.** On Max the
currency is your usage allowance and wall-clock, not money — the levers are
identical, the payoff is throughput. This whole session would have been $15.76 on
Opus 5 API rates, $3.15 on Haiku 4.5.

**Model fit, used deliberately and it held:** Sonnet 5 implemented the `predict`
split including its design judgement (band vs refuse) and was right. Fable 5 took
the §5 threshold decision — 2× Opus per token, so it has to earn it, and it did:
the "growth is blind to sessions that open expensive" catch is Fable's, and it
corrected the trigger I had just built. Opus for cross-cutting verification,
Haiku for mechanical work. **Fable is not a cost lever — it is the most expensive
model. Use it where being wrong is expensive.**

## [macOS 21:30] What this session added

**#19 and #17, both closed.** Four commits, 53 new tests, everything pushed.

**The boundary fires on "expensive AND nothing written down", never on
"expensive".** That one condition is the whole design, and it is what makes it
a door rather than a wall: it cannot fire twice for the same reason, it is
cleared by doing the very thing it exists to protect, and one
`agent-yield handoff` silences it for the session. "Written down" means
*written during this session* — a handoff from yesterday describes a session
that no longer exists, and any freshness rule keyed to the last call goes stale
one call later and makes the boundary unclearable.

**The blanket hard stop #19 asked for was rejected, and the argument is in
design.md §5.** A bug in `gate` blocks dispatches; a bug in a prompt gate locks
the operator out of their own session. Against that, an unconditional stop buys
one extra nudge aimed at the operator who has already written the handoff and
therefore does not need stopping.

**`UserPromptSubmit` exit 2 is UNMEASURED, and no session can measure a hook it
installs** — hook config loads at session start. That is structural, not
laziness, and it is why #22 exists. `boundary` advises by default, refuses only
under `--enforce`, and ships `--probe`, which records the event name, the
payload keys and whether it would have stopped — **never the prompt text**, and
there is a test asserting that. design.md §5 records *in advance* that "exit 2
does not block ⇒ `--enforce` is not buildable" is a legitimate outcome, so it
cannot be quietly skipped later.

**#17's cost family is real code now.** `COST_KNEE = 0.20`, `COST_STEEP = 0.40`
of window, and a test asserts the whole ordering
`COST_KNEE < COST_STEEP < PREFER_FRESH < CONTEXT_WARN < COMPACT_AT_BOUNDARY <
COMPACT_NOW`, so nobody can tune one family into the other's territory quietly.
"Once per band per session" needed no state: `session.cost_crossings` reads the
crossing out of the transcript, and a session that *opens* steep is recorded as
crossing the knee on call 1 — otherwise the sessions the 47% finding is about
would report "never past the knee".

**`status` exits 1 for two conditions, not the one #19 named:** past
`RESTART_HARD_FACTOR` (4.0, deliberately well above the 2.0 advisory, because a
boundary that fires in every working session gets disabled), or in the steep
band. To a caller both mean *leave*.

**Two interventions recorded with predictions, before the results are known.**
The handoff one is the falsification test the whole restart lever rests on: a
session started from a handoff should open under 60,000 context/call, and its
first ten calls should cost less than the last ten of the session it replaced.
It is design.md §7 as well, so it can fail in public.

## [Windows 21:55] What this session added

**Two style guides, and they are enforced, not decorative.**
`docs/style.md` governs prose, `docs/style-charts.md` governs figures. Every
example in both is a real line or a real chart written here and thrown away.
The operator's verdict on the first draft of the cost page was that it was
machine-generated slop, and he was right: it was pages of measurement that
never said what anything cost or what to do on Monday.

The two rules that account for most of the damage:

- **Lead with the finding, not the approach.** "Every threshold we have measures
  the wrong thing" is a claim about our instruments. "We spent 3.02 billion
  tokens, 565 million of them bought nothing" is a claim about money.
- **A chart contains data or it is not a chart.** The cost page's first figure
  was a token axis with six of our own policy constants marked on it. No
  measured value was plotted anywhere on it.

**`docs/context-cost.html` — the argument for #17/#23, drawn.** Three figures:
the concentration curve, the two populations, and the smooth no-knee decay.
Published at https://claude.ai/code/artifact/9cd30289-ff9b-40e6-a80b-76016a6ab14b
and committed, so it survives the artifact.

**The savings number, which #17 never produced.** Spend above the proposed
limits, over 20,255 calls:

```
main capped at 250,000     396M    13% of the corpus
sub  capped at 150,000     169M     6%
                          -----
                           565M    19% of 3,019,183,507
```

Halve it for what restarting costs — §11 measured 1.07x where per-call
arithmetic promised 6.2x — and **280M still stands.**

**The concentration readout, which is the strongest single argument for #23:**

```
                      share of calls   share of spending
first alarm 600,000         4.05%            10.41%
stop        400,000        22.35%            41.78%
restart     250,000        49.88%            74.28%
dispatch    150,000        72.27%            90.55%
```

**The alarm we had catches 4% of calls and 10% of the money.**

**A Fable dispatch, briefed by line range, did the second editorial pass.**
13 tool calls, ~54K reported (understated as always). It caught a factual error
two humans had read past — "half of every main-session call carries more than
249,257 tokens" claims half of *each call* — and its criticism of `style.md`
was sharper than its prose edits: four genuine holes, including that rule 9's
two-em-dash budget contradicted rule 6's own exemplar. All four are fixed. **One
dispatch is not evidence about a model**; #21 is what turns that into a table.

**Open, and mine, not the Mac's:** #20 (blind re-measurement, deliberately
withheld the Windows numbers), #21 (`report --by-model`), #23 (the units).
## [macOS 21:55] What this session added

*Written in parallel with the Windows section above; the two machines were in
this file within minutes of each other. Read them together — the Windows
concentration readout is the same argument this section replicates, and its
`restart 250,000 → 49.88% of calls` line is the number that made the macOS
reply object to that constant.*

**#22 closed, #18 Part B landed, #23 answered.** Four commits, 24 new tests
(163 → 187), everything pushed.

**`UserPromptSubmit` exit 2 refuses the prompt.** Measured by arming exactly
one deliberate refusal (`agent-yield boundary --arm-refusal`, sentinel deleted
*before* the refusal returns, so it can cost at most one re-send). The refused
prompt never reached the model, and the operator saw:

```
UserPromptSubmit operation blocked by hook:
  [/path/to/agent-yield boundary --probe]: <the hook's stderr, verbatim>

Original prompt: <what they typed>
```

Three things follow and **the third is the one that moves the design**: stderr
arrives in full so a boundary can explain itself; the hook is named by command
path so a refusal is traceable; and **the harness echoes the prompt back**, so
refusing costs a re-send rather than someone's typing — which was most of what
the caution around `--enforce` was protecting. The mechanism is verified. **The
policy did not move with it:** the boundary still fires only on "expensive AND
nothing written down", `--enforce` is still off, and turning it on is an
intervention that needs an `expect=` in `interventions.toml` first.

**The boundary payload was measured, and it was hiding a correctness bug.**
`UserPromptSubmit` carries `cwd, hook_event_name, permission_mode, prompt_id,
session_id, transcript_path` and `prompt`; the transcript stem equals the
session id, so the live session is identified twice over. But `_stats_for` fell
back to *the most recently modified transcript* when a payload did not resolve
— and with two sessions open that is routinely the other one. **An enforcing
boundary would have refused prompts in one session on another session's cost.**
Removed: an unresolvable payload now measures nothing.

**The status line is live, and measuring its contract paid better than
building it.** Two findings:

- **`statusLine` config takes effect immediately, in the session that writes
  it.** Hooks do not — theirs loads at session start, which is the entire
  reason #22 had to exist. So this is the one lever you can install and see.
- **The payload hands over `context_window.context_window_size`.**
  `thresholds.DEFAULT_WINDOW` says "the tool cannot read the model's context
  window, so a caller must say". In the status line it can. It also hands over
  `current_usage`, which matched the transcript's last call to within one call
  (105,788 vs 104,156), so the usual render reads no transcript at all. 3 ms
  cold on a 1.5 MB transcript, 2 ms warm, and it fails silent four ways.

`cost.total_cost_usd` arrives on every render and is deliberately dropped.
`rate_limits.seven_day.used_percentage` also arrives, is the real currency on a
subscription, and became #24 rather than being quietly added.

**#23 is right and this session conceded it.** Cost is `context × rate`; the
window is not in that expression. Both of its empirical claims replicate here
on 5,052 macOS calls, independently of the Windows corpus:

| | Windows | macOS |
|---|---|---|
| main vs subagent median context/call | 249,257 vs 97,341 (2.6×) | 188,011 vs 88,201 (2.1×) |
| a knee at 200K | none — smooth decay | none — smooth decay |

Two things were added to the ticket rather than just agreeing:

1. **Abandoning fractions leaves no gap.** The obvious defence — "on a 200K
   window an absolute 150K threshold never fires" — fails, because at that
   window a 150K call is already 75% of capacity and `COMPACT_AT_BOUNDARY` is
   firing. Capacity is genuinely fractional; cost genuinely is not; together
   they cover both regimes. Put that in the comment so nobody reverts it.
2. **The proposed `COST_RESTART = 250_000` is anchored to one machine's
   median, and a threshold at the median fires on half of all calls.** The
   proposed family fires on 60.6% / 41.7% / 25.1% of main-thread calls here.
   That is exactly the failure `RESTART_HARD_FACTOR = 4.0` was set to avoid.
   With no knee to anchor to, a threshold is a policy choice about *what share
   of calls should trip it* — so record the percentile next to the constant.
   Counter-proposal on the ticket: 300K / 500K / 700K ≈ p64 / p86 / p92 here.
   **The Windows section above reaches the same number from the other side**
   — its readout puts `restart 250,000` at 49.88% of calls. Both machines
   measured a threshold that fires on half of everything; neither set out to.

**#23 was the next action and it is done** (`8c280eb`): absolute tokens,
`window` off the cost path, `cost_band` main-thread only, and the ordering test
replaced — it asserted `COST_KNEE < COST_STEEP < PREFER_FRESH < CONTEXT_WARN`,
comparing 0.20 against 0.60 across two families that measure different things.
Once the units differ that comparison is meaningless, which is #23's point in
test form. What is left in its neighbourhood is the *aggressiveness* of
300K/500K/700K, which is a policy choice nobody has evidence for — the
percentile beside each constant is what makes it arguable later.

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

## Why these sessions ended, and how to work the next one

The Windows session ended at ~212K context **not because it was near the window
limit — it was at 21% — but because it had entered the expensive band it had just
measured.** Those are different thresholds, and confusing them is #17.

**[macOS 21:10] The same thing happened again, and this time the tool said so.**
The macOS session ended at **120 parent calls, 278,356 context, 6.58× growth from
its opening 42,294**. `session.restart_advice` printed:

```
context/call has grown 6.6x (42,294 -> 278,356 over 120 calls);
a fresh session costs nothing and this one costs ~6x per call
```

It printed that, and the session kept running for another twenty minutes.
**Measurement without enforcement changes nothing** — which is the whole premise
of #19. Two machines, two operators, same failure. It is not a discipline problem.

**[macOS 21:30] The third session stopped on purpose, at 2.6x.** At the handoff
it stood at **43 calls, 132,259 context, 2.6x growth from an opening 50,801** —
work landed,
163 tests green, everything pushed, `agent-yield handoff` written first. Not
because it had to: the boundary it had just built would not have fired, since
the cost band was still cheap and growth was under the hard factor. It stopped
at the natural boundary instead of running to one. That is the first session of
the three to end that way, and it is the only one whose ending is worth copying.

**[macOS 21:55] The fourth session also stopped on purpose, and earlier.** At
the handoff it stood at **67 calls, 150,614 context, 3.2× growth from an
opening 47,728** — #22 closed, #18 Part B landed, #23 answered, 187 tests
green, everything pushed. The boundary would not have fired: cheap band, under
the hard factor. It stopped because the next piece of work (#23's refactor) is
well specified and mechanical, and the arithmetic says that work is ~2× cheaper
in a fresh session:

```
cost(N) ≈ N × current_context + slope × N²/2
```

At 150K context and 1,262 tokens added per call, the next 40 calls bill ~6.2M
here against ~2.9M starting fresh. **That formula is the whole argument for
restarting**, and it is worth more than any of the thresholds: it is why "just
one more thing" gets expensive, and it does not depend on a knee existing.

**The falsification baseline for design.md §7 is recorded:** this session's
last ten calls averaged 142,097 context against a 47,728 opening. A session
started from this handoff should open under 60,000 and its first ten calls
should cost less than 1.42M. If it does not, the restart lever is wrong and
this page is cruelty rather than efficiency.

`docs/working-method.md` is the full method, measured rather than asserted. The
four things that matter most:

1. **Dispatch briefed work off the loaded thread.** 269,175 context/call in a
   loaded parent against 17,580 in an agent handed `sed` line ranges and told not
   to explore. The economy is **conditional** on the brief — un-briefed agents
   measured 85,195.
2. **Batch tool calls.** Every API call re-reads the entire context. The Windows
   session ran 1.33 tool calls per API call. **[macOS 21:10] The macOS session ran
   0.97 — worse, while knowing the lever.** 123 API calls for 119 tool calls;
   batching to 2.0 would have cut it to 60, **a 52% reduction**. Knowing this lever
   is measurably not the same as applying it, which is the argument for #18 Part B
   making it ambient rather than remembered.
3. **Do not admit large things to context.** Line ranges, not whole files.
   Aggregate in the shell and print ten lines, not a thousand. Anything read once
   is paid for on every subsequent call, forever.
4. **Restart at natural boundaries** — work landed, checks green, pushed — and
   write the findings down first. That precondition is why this page exists.
