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

**[macOS 2026-08-26 22:30] The restart loop is wired shut, and this page is no
longer the only thing that survives a restart.** `SessionStart` now loads the
handoff into the next session automatically (#26) — the session reading this
may already have been handed one. `agent-yield resume` prints it without
consuming it. **The dispatch rubric is written down (§12) and `gate` warns when
a brief lacks its markers** (#27). Open next: **#18 Part C**, which is now the
only thing that can score either rubric.

**[macOS 2026-08-26] #23 is implemented and closed; the cost family is in
absolute tokens.** Anything below this line still quoting `COST_KNEE = 0.20`
or a "steep band" is describing the previous units — `thresholds.py` and
design.md §5 are the current statement. **`working-method.md` §12 is new: the
dispatch rubric**, which is what §11's levers look like as an instruction.

**[macOS 2026-08-25] #18 Part E is done, and it retracted §11's lever 1.**
Splitting a task into three agents cost **54% more**, not less — 385,109 tokens
against 249,944 as one agent, where the prediction was ≥1.5× the other way.
§11.1 is the write-up. **The old 2.2× was arithmetic on a split nobody ran.**
Everything that quoted it is corrected: `agents.py`'s cap comment, §12's rubric
row (b), and the `context-cost.html` "split it" row. **#18 is closed.**

**And a bug the experiment found by accident: the §12 marker detector had a
false-negative rate near 100% on a textbook brief** — **#32, fixed and closed
2026-08-25.** All five Part E dispatches carried line ranges, an explicit
prohibition, a named output path and a return contract, and `gate` scored them
**0 of 3**. The three regexes tested for *wording*, not for the property.
Fixed, and Part C re-scored in **working-method.md §12.2**: the corpus-wide
count goes **4 → 10 of 87**, and on the same twelve dispatches §12.1 published,
one reclassification swings the medians from 6.0/6.5 to 3.0/9.0 — which is the
real finding. **"No evidence the markers predict dispatch length" stands**, now
for the sharper reason that the comparison is one row wide.

**[macOS 2026-08-26] #33 IS ANSWERED, AND IT BLOCKED EVERYTHING — read this
before the baton sections below, which were written without it.** The baton
beats a reading parent **1.71x end to end**, n=2 an arm, every baton run cheaper
than every reader run. **The 28x on this page is retracted as an end-to-end
number** (it divided growth avoided by arrival paid); the real long-run figure is
**3.55x**. **At the audit turn alone the arms are 1.20x apart, under the
retraction bar** — the effect lives entirely in the turns *after* the reading,
which is why the protocol had a tail. **And the arm that saved the money found
half the defects, in both replicates.** #47. **#34 is answered too:** re-entry is
fixed at a median **22,114** (19,800 was 12% low), and the brief moves it 11%.
working-method **§11.2** and **§11.3**.

## State of the board

**The tool is built and works.** Nineteen modules, green on Windows and macOS,
everything pushed, working tree clean.
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
| **#26** | ~~SessionStart loads the handoff~~ — shipped 22:20, **and it never fired.** It read `session_start_reason`; the harness names the reason in **`source`**, a string that does not occur in the harness binary at all. Every session start took the fail-open path and injected nothing, and the unit tests passed because the fixture invented the same key the code read. **Fixed 2026-08-25**, with the real payload pinned verbatim in `tests/test_resume.py` and a test that the abandoned key does *not* inject. The 2026-08-26 falsification test is scored **VOID** in `interventions.toml`, not passed — the next session opened at 48,744 context/call, but it received no handoff, so that number says nothing about the loader. **Re-armed, and SCORED PASS 2026-08-25 by the session it treated** — and this time the treatment demonstrably ran: `.agent-yield/resume-probe.jsonl` carries `decision=injected`, `has_reason_key=true`, `source=startup`, `injected_chars=5993`, and `handoff.md.loaded` exists, so the archive was consumed. Opening **44,516** against the 60,000 bound; **449,515** tokens over the first ten calls against the 1,420,000 bound. **Read the caveat before quoting it:** the VOID run — same restart, *no* handoff — opened at **48,744**, the same band. Nothing separates the two arms. So this scores that a ~6,000-character injection **does not cost the opening**; it does **not** show the handoff saves anything. The comparison against the replaced session is confounded with a fresh session being cheap for reasons unrelated to the loader — the same confound that made run 1 VOID. **What would actually score it: whether the treated session repeats work the handoff already told it.** That is the next prediction to arm. |
| **#27** | **Dispatch rubric enforcement. Stage 1 shipped**, warning only, `Explore`/`Plan` exempt. **Stage 2 is now blocked twice over, and `--enforce-brief` must stay OFF.** It was already worse-supported after Part C (marker-only enforcement fires on ~95% of dispatches — the RESTART_HARD_FACTOR failure). ~~**#32 is the second block**~~ — **closed 2026-08-25, and it removes itself as a blocker without unblocking Stage 2.** The detector no longer refuses the five Part E briefs, but the *first* block is worse than before: with the markers detected properly, marker-only enforcement fires on **77 of 87** dispatches, and §12 says an exploratory dispatch is supposed to carry none of them. Stage 2 needs a way to tell a bad brief from a different kind of task, which is not a detector problem. |
| **#29** | ~~SessionStart needs a probe~~ — **closed `c979f52`.** Named silences + `--probe`. The general rule is the keeper: *the one hook a session cannot measure by installing it is the one that most needs a probe.* `UserPromptSubmit` at least fires again next prompt; `SessionStart` fires once, before anyone can watch. |
| **#31** | **[Windows] Open, and addressed, not assigned.** Reinstall the hook with `--probe`, expect 233 tests, restart, paste the probe line. Its `keys` list is the ask — one machine, one binary read, no live capture. |
| **#28** | What a scheduler can and cannot do, measured: no session can replace itself, `claude -p` works non-interactively, **interactive launch from cron is undocumented**, routines run in Anthropic's cloud. Filed so the assumption stops being repeated without its caveat. Three things worth measuring are listed there. |
| ~~**#18**~~ | **Closed 2026-08-25.** Three levers; Parts A–E all done. **Part E killed lever 1.** The same audit dispatched as three agents (one unit each) cost **385,109 tokens over 12 calls**; as one agent, **282,568 and 217,321 over 5 calls** across two replicates. **0.65× — splitting cost +54%**, against a pre-registered prediction of ≥1.5× the other way and a <1.25× retraction bar. Not VOID: the arms did equal work (tests enumerated 17/21/19 in all three runs, defects 15/14/14), and the two arms agreed on the judgment call (75%) about as often as two same-arm agents agreed with each other (82%) — that second long replicate was run as the control precisely so a cheap-because-worse arm could be ruled out. **Why:** every agent's first call costs ~19,800 tokens before it reads anything, so a 3-way split pays it three times (38% of the gap), and **a split does not divide the call count** — one agent batched six files into 5 calls, three agents needed 12. Superlinear growth *within* an agent is real (1.9× over 4 calls, 3.6× over 5); it is just too small to pay for re-entry. **Limits: one task, units of 4–5 calls, reads that batch cleanly. Re-entry is fixed, so it amortises — long units are untested, and the 27-call dispatch that motivated the lever is exactly that untested regime. Retracted is 'splitting saves', not 'splitting never saves'.** |
| ~~**#32**~~ | **Closed 2026-08-25.** The §12 marker detector scored **0 of 3 on all five** Part E dispatches — briefs this repo wrote to its own rubric. All three regexes tested for particular wording: the prohibition demanded the literal word *explore* (so "do not grep or search the repository, do not read any other file" scored zero), the output path used `.{0,60}` without `DOTALL` (so a path on its own line missed while the same words inline matched), and the return contract knew `under \d+ lines` but not `at most 3 lines`. **All three now test for the property.** The five prompts are pinned verbatim in `tests/fixtures/part_e_dispatches.json` as *captured* positive cases — the bug survived because `test_gate.py`'s fixtures were written to match the regexes, which is #26's failure one file over. 260 tests. **Part C re-scored (§12.2):** corpus-wide **4 → 10 briefed of 87**; on §12.1's own twelve dispatches the old regexes reproduce 4/6.0 vs 8/6.5 exactly, and the fixed ones give 5/**3.0** vs 7/**9.0** — a swing produced by reclassifying **one** 3-call dispatch. Ranges still overlap (3–30 vs 3–27), ctx/call still flat (29,356 vs 31,108). **The conclusion does not move: no evidence the markers predict length**, and now the reason is that n=12 is one row wide. `--enforce-brief` stays OFF: the marker-only rule fires on 77 of 87. |
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

## [macOS 2026-08-26 22:30] What this session added

**Four commits, 37 new tests (187 → 224), three issues filed, everything
pushed.** #23 closed, #26 shipped, #27 half-shipped by design.

**The restart loop is wired shut except for the keystroke.** `boundary` makes
continuing expensive to ignore → `handoff` makes leaving cheap → **`SessionStart`
makes arriving cheap** → a human types the restart. That last step is not
laziness: no hook kills and respawns a session, and `SessionStart` *cannot block
a session from starting* — exit 2 there only surfaces stderr. It is a loader,
never a gate, which is the opposite of `UserPromptSubmit` and worth remembering
before designing anything else on it.

**Staleness is solved by consuming rather than checking.** The hook archives the
handoff as it injects it, so injection is exactly-once **with no state file
anywhere**. Older than 24h it is neither injected nor archived — readable by
hand, never loaded. A handoff describing a dead session is worse than none,
because it is confidently wrong rather than absent. Measured: **3,892 chars,
~973 tokens, ~95K over a 100-call session**, against ~10.3M spent here.

**The dispatch rubric, §12 of `working-method.md`.** One asymmetry generates all
of it: **the child pays for what it reads once; the parent pays for what it
reads on every call afterwards.** Four parent rules, four brief parts. §11's
1.07× null result had exactly one cause — the parent read every diff and ran
every suite itself.

**The rubric splits along an observability line, and that is what makes it
enforceable.** Three markers are visible in the dispatch prompt (line range
**and** "do not explore" — one marker, since the range without the prohibition
is not what was measured; a named output path; a return contract). The ~10-call
cap is only knowable afterwards, because hooks do not fire inside a subagent.
So `gate` warns on the first three and #18 Part C must carry the fourth.

**Two live data points against the rubric, both from this session, and one is
embarrassing:**

- **A briefed implementation agent with a stated 14-call cap ran 36 calls.**
  Stating a cap does not enforce it — which is the argument for Part C existing,
  and evidence that the pre-dispatch half cannot cover part (b).
- **That same agent reported "236 tests passed" when the real number was 224.**
  Agent-reported numbers were verified rather than trusted, and the commit
  carries the verified one. **Verify a subagent's numbers before quoting them.**
- I also briefed two Fable agents to write their memos to the **scratchpad**,
  which evaporates — rubric part (c) violated by its own author within an hour.
  Both memos were reconstructed into issues #26 and #27, which is where they
  should have been written. **A "named output path" means a durable one.**

**Fable earned its cost twice, on questions where being wrong is expensive.**
The enforcement split above is Fable's, not mine — I offered three mechanisms
and it rejected all three for a fourth. The consume-on-injection design is
Fable's too. Both are the kind of answer that is cheap to get wrong and
expensive to discover wrong.

**#23 shipped as measured, not as proposed.** The ticket's 150K/250K/400K fires
on 60%/42%/25% of main-thread calls; the shipped 300K/500K/700K fires on
35%/13%/7%, and each constant now carries that share in its comment because
**there is no knee to anchor to** — a threshold here is a policy choice about
what fraction of calls should trip it, and a threshold at the median fires on
half of everything.

## [macOS 2026-08-25] The handoff loader never fired

The session that wrote the handoff below predicted its successor would arrive
carrying it. The successor arrived blank, and the operator had to say so by
hand. `resume.py` read `session_start_reason`; the harness sends `source`.

**Three things about this are worth keeping, and none of them are the typo.**

- **The contract was labelled "Measured contract" in design.md and was not
  measured.** The five reason *values* were right, so the source was
  documentation, read carefully and then trusted. `--probe` exists in this repo
  precisely because reading a contract is not measuring it, and it was not used
  on the one hook that could not measure itself.
- **The tests could not have caught it.** `_payload()` built its fixture from
  the same key `main()` read, so the suite verified that the code agreed with
  itself. 226 green tests, one hook that had never run. Every payload fixture
  in this repo should be a captured payload or an explicitly-labelled guess.
- **Failing open hid it.** The hook is right to fail open, but silence on a
  loader is indistinguishable from "nothing to load", so it never fired once
  and never complained once. A loader that fails open needs a way to say it
  declined and why — the boundary's `--probe` log is the shape to copy.

**The one hook that cannot be measured by the session that installs it is the
one that most needs a probe.** #22 established that for `UserPromptSubmit` and
built the probe; `SessionStart` has the same property and shipped without one.

**#29 closed the same night** (`c979f52`). The five outcomes are named and
distinct — `injected`, `no_handoff`, `stale`, `reason_not_injecting`,
`unparseable_payload` — decided in one `classify()` that is also the only place
that consumes the handoff, so exactly-once still needs no state file. `stale`
and `no_handoff` were the same `None` before, and only one of them is a bug
worth chasing. `resume --hook --probe` records payload **keys, never values**
(no `session_title`, no handoff text, only its length; there are sentinels in
the tests asserting it), and it does **not** fire on a hand-run read — an
operator looking is not a session start. `has_reason_key` is written explicitly
rather than left to be inferred, because it is the one field that would have
caught the original bug the same day. 226 → 233 tests.

**The probe is armed on this machine and unfired.** It cannot fire until the
next restart, which is the property that made all of this necessary. The first
line in `.agent-yield/resume-probe.jsonl` is the evidence that #26 works;
there is no line in it yet.

**#31 is a message, not a task** — the first deliberate use of the tracker as a
message bus rather than a queue, and `working-method.md` **§7.1** now writes
down the shape. The Windows machine has the same broken key through git, and
**cannot have received the fix to its hook config**, because `.claude/` and
`.agent-yield/` are gitignored — that gap is precisely what is worth sending
across the boundary. It asks for one probe line back and pastes the macOS line
beside it, since this payload has been measured on exactly one machine, by
reading a binary rather than catching a live call. If the Windows key list
differs, §3.1's lesson applies again.

## [macOS 2026-08-25] #18 Part C: the rubric scored, and the first answer retracted

`agent-yield agents` joins each dispatch to the transcript of the agent it
started - §11's length rule needs the child's call count, §12's markers need
the parent's prompt, they live in different files, and **hooks do not fire
inside a subagent**. 73 dispatches joined, 0 unmatched.

**Read this before quoting any number from it.** The first result was a 9.5x
effect, it was wrong, and it was in `thresholds.py`, a commit message, this
page and two issue comments within the hour.

| pooled, all projects | n | median calls |
|---|---|---|
| all three markers | 4 | 6 |
| missing one or more | 69 | 57 |

**Entirely project.** All 61 long un-briefed dispatches were
`model-migration-kit`'s audit fleet; all 4 briefed ones were this repo's.
Exactly one project held both groups:

| agent-yield only | n | median calls | median ctx/call |
|---|---|---|---|
| all three markers | 4 | **6.0** | 39,139 |
| missing one or more | 8 | **6.5** | 28,353 |

**There is currently no evidence that the three detectable markers predict
dispatch length.** The briefed ones carried *more* context per call. `render`
now refuses the pooled comparison and prints per-project rows, with a test
asserting the tempting number never appears - **the tool made the confound
invisible, so the tool was the bug**, and "remember to check" is not a fix.

**What survives, and it is not nothing:**

- **The overlap claim is retired.** `thresholds.py` said the two populations
  "do not overlap at all" (4-27 vs 62-188). Within agent-yield: un-briefed
  3-27, briefed 3-30. True of eight hand-picked dispatches, false of twelve
  measured ones.
- **4 of 73 carried all three markers; 60 of 73 blew the 10-call cap**
  (longest **118**). The rubric is followed ~5% of the time, in the repo whose
  subject is the rubric.
- **§12's asymmetry is untouched** - "the child pays once, the parent pays on
  every call after" is per-call economics measured elsewhere. What is
  unsupported is that *these three regexes* are what capture it.
- **#27 Stage 2 is now worse-supported, not better.** It was blocked on this
  data; the data does not justify refusing a dispatch on markers. Keep
  `--enforce-brief` off.

**The lesson worth carrying: speed of publication is a risk multiplier.** It
was a *good* result, and good results do not invite scrutiny. The gap between
measuring and quoting is where this gets expensive - the same shape as #29,
where a contract was labelled "measured" because it had been read carefully.

## [macOS 2026-08-25] `status` was measuring the wrong session

Caught at the end of the session, while verifying the handoff. `agent-yield
status` reported **357 calls, 535,788 context, 10.6x growth, cost band
`restart`** for a session that had made **109 calls at 183,096 context**. It
was measuring a photo-editing session in another repo that had written to its
transcript a second earlier.

`find_session(None)` fell back to *the most recently modified transcript under
`~/.claude/projects`* — which spans **every project on the machine**. With two
sessions open it picks whichever wrote last.

**This is the same bug `boundary._stats_for` was fixed for, one function
over**, and NEXT.md already recorded that fix: *"an enforcing boundary would
have refused prompts in one session on another session's cost."* The fix was
applied where it was found and not where else it lived. `status` exits **1** to
mean *leave*, and `handoff` writes the same numbers into the file the next
session inherits — so this reached the durable record, not just a display.

**Fixed:** with no explicit session id, candidates are restricted to the
project directory for the cwd; if none match, it returns `None` and measures
nothing rather than measuring a stranger. An explicit `--transcripts` root is
never second-guessed. Three regression tests.

**Two things worth keeping:**

- **It printed the right session id the whole time**, on line 1, and that was
  not enough — the id was there and the number was quoted anyway. Labelling a
  number correctly does not stop it being used wrongly.
- **A fix applied at the site it was found is half a fix.** The pattern
  "fall back to the most recent transcript" existed in two functions; one was
  corrected, the other kept the bug for a day. When a fallback is wrong once,
  grep for it.

**Tonight's third retraction, and the shape does not change:** something
confident, specific and wrong, past a green suite, caught by asking one more
question of data already in hand.

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

## [Windows 2026-08-25 23:50] A planning session, and the one number that moved

**Nothing was built. One spec was written and one measurement was taken**, and
the measurement reframes the spec, so read them in that order.

**Where main-thread context growth actually comes from.** Five dispatch-heavy
sessions out of the archive, 2,516 intervals, each context delta attributed to
whatever entered the conversation before it (`docs/attribution-2026-08-25.md`):

```
  the parent reading things itself   55.4%
  the conversation itself            33.2%
  subagent return payloads           11.4%
```

**The parent reading is roughly 5x the returns.** Every dispatch discipline
written so far — the return contract, write-and-exit, §12(d) — is aimed at the
11%. The lever that matters is the parent never comprehending the work at all.
And the 33.2% is untouchable by any dispatch mechanism, which caps how much this
whole line of work can ever save; that third is an argument for restarting, which
is already the standing lever.

**The caveat is large and it is in the doc:** the sanity check failed at ~2x
because negative deltas (compaction drops) were floored at zero. These are shares
of *gross* additions, not net growth. Ordering sound, percentages indicative. All
five sessions were dispatch-heavy by selection, so there is no control group.

**The spec: `docs/superpowers/specs/2026-08-25-baton-design.md`.** DRAFT,
unapproved, nothing built. Three roles, and the parent is the smallest:

| | |
|---|---|
| **slicer** | one agent, once — cuts the goal into slices small enough for 10 calls, **each with a test command that proves it**. Testability defines the slice boundary, not call count. A piece of work with no way to check it is not a slice. |
| **index** | one table, one row per slice: `id / lines / depends on / test command`. ~15 tokens a row. **This is the whole of what the parent holds.** |
| **fleet or baton** | rows with no dependency go out together in parallel; rows in a chain go one at a time, each child writing the next child's brief. Same design, different width of the dependency column. |

Parent cost per slice: ~60 tokens of dispatch prompt (a constant — it varies only
in the line range), ~25 for a two-line return, ~15 to re-run the test command
from the index. **~100 tokens a slice against a parent that went 58,475 to
126,522 doing one phase by hand.**

**The return contract is two lines. Line 1 is what happened, line 2 is a
pointer.** Line 1 is checkable without understanding anything — the parent
re-runs the test command from the index and compares.

**`ASK` is the new verb and it is the point.** A child whose brief is not clear
enough to act on returns ASK and stops. It does not go and find out. Going and
finding out is the un-briefed population's 85,195 context/call, and it is the most
expensive habit in the corpus. This is a fifth part for §12's four-part brief:
**(e) a stated permission to refuse.** The other four bound what a child reads
and returns; this one bounds what it invents.

**Still unsolved, and written into the spec rather than smoothed over:**

1. **The child-writes-vs-parent-writes fork.** Child-writes is what makes the
   parent's prompt a constant, but it puts brief authorship in the least-informed
   context in the system. Dispatched to Fable — see below.
2. **The slicer is one agent with no review**, and a bad cut poisons every slice
   under it. That is the same concentration of risk moved up a level, not
   removed. Untested options: two slicers and diff their indexes, or a cheap
   reviewer that only checks every slice has a real test command.
3. **The cost of a child writing the next brief has never been measured.** Output
   runs ~5x base input. If a brief costs more than the parent growth it prevents,
   the baton is a worse trade wearing a better one's clothes.

**Falsifiers are in the spec** and belong in `interventions.toml` with `expect=`
before the first run. The sharpest: **ASK should fire at least once in ten
steps.** A chain that never asks is either perfectly briefed or quietly guessing,
and the second is far more likely.

**Two dispatches, both briefed by line range, both capped at 10 calls, both
write-and-exit.** The attribution agent used 7 calls and returned 3 lines. That
is the shape the spec is about, used to write the spec.

---

## Enforcement: gently, firmly, assiduously — and measured

A rubric that is only written down does not hold. That is not a hypothesis here;
it is measured twice. §12 was written yesterday and §11 still recorded the parent
at 81% of the session. The macOS session ran **0.97 tool calls per API call while
knowing the batching lever**. Knowing a lever is measurably not the same as
pulling it.

So each rule below gets a rung on a ladder, and the ladder ends in a number.

| rung | mechanism | what it does | already exists |
|---|---|---|---|
| **gently** | `statusline` | renders steps in the run, parent growth since step 1, and slices remaining. Continuous, ambient, **zero token cost** — the payload arrives on every render whether or not anything reads it. | yes, live |
| **firmly** | `gate` (PreToolUse on `Agent`) | reads the dispatch prompt before it is sent. No `sed -n` range, no call cap, no return contract → warn on stderr and **let it through**. Fails open, always. | yes, fails open |
| **assiduously** | `agent-yield discipline` | scores every dispatch in the corpus against the five-part brief and prints one compliance number and its trend. **New. Does not exist.** | no |
| **honestly** | `interventions.toml` | every rule above gets an `expect=` recorded before its result is known, and Week 2 scores it. The loader already refuses an intervention without one. | yes |

### Why the gate warns and never blocks

A bug in `gate` blocks dispatches — and past the cost threshold the remedy *is*
to dispatch, so a blocking gate cuts off the cheapest path out of an expensive
session. That argument is already in design.md §5 and it has not changed. The
gate is a mirror held up at the moment of dispatch, not a door.

### The thing §12 left unsolved, and how the brief solves it itself

§12 records that the rubric cannot be a gate, because **an exploratory dispatch
is supposed to have none of its markers** — a search agent told to sweep a repo
cannot be briefed by line range without becoming a different task. Any mechanism
has to tell a bad brief from a different kind of task before it refuses anything.

The brief can just say which it is. One token at the top:

```
BRIEF:    line ranges, call cap, return contract, output path, ASK permission
EXPLORE:  none of those required. Bounded by a call cap and a question, nothing else.
```

That makes the gate's job trivial — it checks `BRIEF:` dispatches against the
rubric and leaves `EXPLORE:` alone — and it buys something better than
enforcement: **the exploratory share becomes a measured quantity.** Nobody knows
what fraction of dispatches genuinely need to explore. The suspicion is that it
is small and that `EXPLORE:` will be used as an escape hatch. If the share climbs
over time, that is the escape hatch being used, and it will be visible in the
number rather than arguable.

An undeclared dispatch is treated as `BRIEF:` and warned. Silence is not a third
category.

### What `discipline` measures

Per dispatch, from the transcripts that already exist:

```
declared BRIEF or EXPLORE          share of each, over time
line ranges in the prompt          yes / no
call cap stated                    yes / no
calls actually used                distribution, and the share over 10
return contract stated             yes / no
lines actually returned            distribution, and the share over 2
ASK returned                       count -- expected to be non-zero
parent growth per dispatch         tokens
```

Two of those rows are the ones to watch, because they are where stated intent and
actual behaviour come apart:

- **calls stated vs calls used.** A cap that is declared and blown is worse than
  no cap, because it reads as compliance in every other column.
- **contract stated vs lines returned.** Same failure, on the other side.

**And ASK count is the honest-broker row.** A fleet that never returns ASK is
either perfectly briefed or quietly guessing, and across a real corpus the second
is far more likely. Zero ASKs is evidence the permission is not real, not
evidence the briefs were good.

### The falsifier for the enforcement itself

Compliance measured **before** any of this ships is the baseline. If compliance
does not move after the statusline and gate warnings are live, then ambient
measurement does not change behaviour either, and the honest conclusion is that
only structure does — that the discipline has to be built into how work is cut
and dispatched, not shown to whoever is dispatching. Record that outcome as
legitimate in advance, the way #22 recorded "exit 2 does not block" in advance,
so it cannot be quietly skipped when the number disappoints.

---

## Reconciled against #18 Part E, which landed while this was being written

**The Mac ran the falsification test this document assumed the answer to, and it
went the other way.** `4413ea1`, pushed at roughly the hour this spec was drafted:

```
split   3 agents  12 calls  385,109 tokens
single  1 agent    5 calls  282,568   (replicate 1)
single  1 agent    5 calls  217,321   (replicate 2)
```

**0.65x. Splitting one task three ways cost 54% more**, against a predicted
>=1.5x saving. The arms did equal work, so it is a result and not a void run.
Two causes, both of which this spec ignored:

1. **Every agent pays ~19,800 tokens of re-entry before it reads anything.** A
   three-way split pays that three times — 38% of the gap.
2. **Splitting does not divide the call count.** One agent batched six files into
   5 calls; three agents needed 12. Superlinear growth inside an agent is real
   (1.9x over four calls, 3.6x over five) and simply too small to pay for
   re-entering three times.

A second retraction landed with it (`45e9c62`): the claim that the brief's
detectable markers predict dispatch length was **pooled across projects**. Within
the one project holding both groups, the call difference vanishes and the briefed
dispatches carry *more* context per call. There is currently no evidence that
those markers predict anything.

### What this kills in this document

**"Why the 10-call cap becomes enforceable" is now arguing for a cap whose
benefit has been measured and is negative.** The `calls^1.54` fit it rests on is
real but was never the whole cost: it omitted re-entry, exactly as this spec's
80-tokens-a-step figure omitted scaffolding. Both errors have the same shape —
counting the part that varies and ignoring the fixed part underneath.

Naively, the baton looks worse than what it replaces. Twelve steps is twelve
re-entries, about **237,600 tokens** of pure arrival, to avoid roughly 68,000 of
parent growth.

### What survives, and why the baton is not dead

**Re-entry is paid once per agent. Parent growth is paid on every parent call for
the rest of the session.** That asymmetry is what the arithmetic above leaves
out, and it is the one thing the retraction commit says explicitly is untouched.

A parent carrying 68,047 extra tokens over another 100 calls has spent 6.8M on
carrying it. Twelve re-entries cost 238K. ~~**The baton still wins by roughly
28x**~~ — **RETRACTED 2026-08-26 as an end-to-end number by #33, which measured
it.** That 28x divides growth *avoided* by arrival *paid*: two different
quantities, not a ratio of two runs. Measured end to end the baton wins by
**1.71x over six turns**, tending to **3.55x** as a session lengthens. The
direction was right — the first time in three tries — and the magnitude was out
by about eight-fold. The asymmetry itself stands, and is now measured per call:
a reading parent's turn costs ~127,600 tokens against a dispatching parent's
~35,900. See working-method §11.3.

The independent support is the attribution measured here: 55.4% of main-thread
growth is the parent reading. Part E says nothing about that number. It compared
one agent against three agents. **It did not compare N agents against a parent
that reads everything**, which is the comparison the baton actually makes.

### The design change this forces

**Slice thin for verification. Batch fat for dispatch.**

The slicer should cut on testability — a slice is still the smallest piece with a
command that proves it, and that part was right. But the parent should then hand
**as many adjacent, dependency-free slices to one agent as that agent can carry**,
because re-entry is charged per agent and not per slice. The index does not
change; what changes is that a row is a unit of *verification*, not a unit of
dispatch.

So: the 10-call cap is retired as a target. What replaces it is **the fewest
agents that still leave every slice independently checkable**. An agent running
20 calls over six slices is now the expected shape, not a violation — and
`60 of 73` real dispatches already exceeded the old cap, which should have been
read as evidence about the cap rather than about the dispatchers.

### What this does to the falsifiers

- **The parent-stays-flat falsifier stands** and becomes the primary one. It
  tests the asymmetry, which is what survived.
- ~~**A new one is needed and is the sharper test:** total tokens for a baton run
  against the same work done by a reading parent, end to end.~~ **RUN, 2026-08-26,
  and it passed: 1.71x, n=2 an arm, every baton run cheaper than every reader
  run** (§11.3, `interventions.toml`). Per-call economics had predicted the wrong
  sign twice before this — §11 promised 6.2x and measured 1.07x, Part E promised
  >=1.5x and measured 0.65x — and this is the first one to get the sign right.
  **The number to carry forward is not the headline but the tail:** at the audit
  turn alone the two arms are 1.20x apart, *under* the retraction bar. Everything
  the baton is worth appears in the turns after the reading.
- **Any falsifier resting on the markers is void** until `45e9c62`'s retraction
  is addressed, including the enforcement ladder's compliance score. `discipline`
  can still count markers; it may not claim they predict cost.

~~**Status of this spec after reconciliation: the mechanism stands, the
justification is half retracted, and the end-to-end test has not been run.**
Do not build from it yet.~~

**Status 2026-08-26: the end-to-end test has been run and the mechanism is
measured, so this spec may now be built from — with one qualification that is
not about cost.** The baton arm found **half the defects** the reading arm found,
in both replicates, and the reader's findings are close to a superset rather than
a different judgment call. Per defect found, the reader is 1.17x *cheaper*. #47
is that question, and #35-#38 should be read with it open.

### The baton, as discrete tickets: #33-#38

Written as an index on purpose — each one independently checkable, so the set is
itself the input to #38.

| | | |
|---|---|---|
| ~~**#33**~~ | **CLOSED 2026-08-26. 1.71x, and it passed.** Bars committed at `76cbf08` before the first call; result in §11.3 and `interventions.toml`. Baton 975,338 / 690,323 against reader 1,368,208 / 1,476,964, every baton run cheaper than every reader run. **At the audit turn alone: 1.20x, under the bar** — the tail of five turns is where the whole effect lives, and an experiment that stopped where Part E stopped would have reported no effect. **But the baton found 4 defects in both replicates and the reader 8 in both, so per defect found the reader is 1.17x cheaper and the headline reverses.** The pre-registered volume bar was on *claims counted* — the denominator — when the output of the task is *mismatches*: it would have passed an arm that returned zero defects. That is #47. |
| ~~**#34**~~ | **CLOSED 2026-08-26. It is fixed, and 19,800 was 12% low.** 79 dispatch-to-agent pairs on this machine, 0 unclaimed: median first call **22,114**, stdev 2,958. Price a dispatch at ~22,000 for `general-purpose`. The brief moves it 11% across the real interquartile range, so the five-part brief does **not** buy its own cost back and does not need to — write it. The fitted slope (780 per 1,000 chars pooled; 476 and 1,835 within projects) is 2-7x the mechanical price of the text, so brief length is a **proxy for something else** and must not be quoted as what a brief costs. **The lead worth two dispatches:** `general-purpose` arrives at 22,131 (n=74), `Explore` at 8,909 (n=1), `statusline-setup` at 9,440 (n=2). If that holds, a narrow type is a third of the price. working-method §11.2. |
| **#35** | slice thin, batch fat | retires the 10-call cap as a target and replaces it. A row is a unit of verification, not of dispatch. |
| **#36** | the index and the parent loop | as a practice, **no code** — `predict` is the standing example of shipping a subcommand for an unvalidated shape. |
| **#37** | `BRIEF:` / `EXPLORE:` self-declaration | what §12 left open and what #32 says the detector cannot do. Makes the exploratory share measurable. Related: #27, #32. |
| **#38** | **can the method build itself?** | build #36 and #37 through the baton rather than by hand. A method that cannot carry its own implementation is not a method. Three outcomes, all recorded in advance, and "it cannot hold discipline" is the most useful of them. |

### [Windows 23:55] Three more tickets, and a Windows bug that was hiding under them

**`project_slug` never handled Windows paths** (`68f068f`). `C:\...` becomes
`C--Users-...` in the transcript tree — drive colon and every backslash become a
dash — and the slug replaced neither. So `cb8bb7d`'s project scoping returned
`None` for **every** session on this machine: `status` and `restart_advice`
measured nothing and said nothing about it. Worse than the cross-project
fallback it replaced, which at least failed loudly. It surfaced as `cb8bb7d`'s
own test failing here, because the fixture builds its directory *from* the slug.
250 green; `status` resolves a session on Windows for the first time.

**The `SessionStart` hook is installed here** (#31). `.claude/settings.json` did
not exist at all — **`gate`, `boundary` and the status line have never been
installed on this machine either**; the only local hook was a stale `PreToolUse`
probe pointing at *migration-kit's* venv. The probe line posted to #31 carries
**synthetic keys**: this session installed the hook and no session can measure a
hook it installs. **The real Windows key list still needs a restart, and that is
#31's actual ask.**

| | |
|---|---|
| **#39** | the harness ships a `Workflow` orchestrator and superpowers ships three relevant skills. **Evaluate before #36 writes a parent loop by hand.** `agent(prompt, {schema})` validates the return at the tool layer and retries the model on mismatch — the two-line contract stops being a request. It does not dodge re-entry, and if #33's arms use different dispatch mechanisms the result is confounded. |
| ~~**#40**~~ | **Closed 2026-08-26 (macOS).** `build()` supersedes: a later note that restates an earlier one replaces it *in the earlier one's position*, and the CLI says how many were dropped. Threshold **0.5** is measured, not chosen — containment of the shorter note in the longer; six real distinct notes peak at **0.35**, the three real restatements bottom out at **0.62**, and a test fails if the constant leaves that gap. Both fixtures captured, not written for the code. |
| **#41** | **Windows, still open, and the diagnosis is wrong.** There is *no* write path missing `encoding="utf-8"` — every `write_text`/`read_text`/`open()` in the package was audited and all name it. A `§`-and-en-dash round trip through `render → write → read →` the real injected payload now ships as a test and passes on macOS. **If it passes on Windows too, the corruption enters before the file** — `argv`, the console code page, or the harness. The only unencoded streams left are `sys.stdin`/`sys.stdout` in `resume.main`, locale-encoded on Windows and UTF-8 everywhere else: a one-machine difference of exactly the §3.1 shape. Needs the machine that can see it. |

**#35 now has a protocol and a recorded prediction** (`7ffc414`). Slice set cut
once and held fixed; only the packing varies — 12 agents / 3 agents / 1 agent
over the same 12 slices. Part E's limits paragraph is why this is worth running:
it says the long-unit regime is **untested** and that what it retracted was
*"splitting saves"*, not *"splitting never saves"*. Quality is scored only
through each slice's own test command — pass, fail, or never run — because
silently skipped slices are invisible in a token count. **If the 12-agent arm
wins, the 10-call cap should be un-retracted rather than left quietly retired.**

## [Windows 2026-08-26 08:30] The first daily report, and what it says about progress

**The honest answer to "are we getting more effective" is: on the least gameable
measure, we got 24% worse — and the first version of this section said "flat"
because it divided one machine's tokens by two machines' commits.** This is the first time
the daily question has been asked against the real corpus (20,757 calls,
re-ingested this morning), scoped to this project's `cwd` and bucketed by
**UTC** day, which is what the corpus timestamps are. Bucket git any other way
and the join silently misaligns — a bare `git log --since=<date>` does exactly
that, and it is the same approxidate trap already recorded against `outcomes.py`.

```
agent-yield only, UTC days, and BOTH sides scoped to the machine that was measured
day        tokens   calls  commits    ins  code-ins  docs-ins  main ctx/call  >300K  sub ctx/call
2026-08-25  17.79M   146      10    4,203    1,127     2,931       177,068     20%      45,766
2026-08-26  52.80M   398      50   10,025    5,493     4,274       142,095      4%      48,480
              (macOS, same 08-26 UTC day: 18 commits, 3,069 insertions, 82% of them code)

tokens/commit         1,778,703 -> 1,056,044   0.59x  better
tokens/code-line         15,783 ->     9,613   0.61x  better
tokens/line-of-any-kind   4,232 ->     5,267   1.24x  WORSE
```

**Corrected 2026-08-26 09:00, before anything was built on it.** The first
version of this table divided a Windows-only token count by a two-machine commit
count, and reported tokens-per-line as *flat*. It is not flat. Attributing every
commit in the window to the machine that was awake when it landed — Windows call
timestamps against committer time, +/-6 minutes — gives macOS **18 commits and
3,069 insertions** on the 08-26 UTC day, not the 4 commits first estimated, and
**82% of macOS's lines were code**, which is exactly the column the headline
leaned on. The independent review of the dashboard plan caught this
before the plan's own figure caption was written; it reached 15-17% worse by a
different route (§11's 11.4M-token macOS session against its 2,135 lines).
**Three estimates, two methods, one sign.** The 6-minute window can only
misattribute macOS commits *to* Windows, so 10,025 is an upper bound on the
Windows denominator and 24% is a **floor** on how much worse it got.

**So the honest headline is worse than "no progress."** Tokens per line of any
kind rose 24%. The two ratios that still look like wins — per commit, per line of
*code* — are the mixture artefact: 08-25 was doc-heavy, 08-26 code-heavy, and
both denominators move with that mix while the token count does not. The least
gameable denominator is the one that got worse.

**What does survive the decomposition, with its caveat attached.** Main-thread
context/call fell 177,068 → 142,095 and the share of main calls above
`COST_DISPATCH` fell **20% → 4%**, with nothing above `COST_RESTART` on either
day. Machine-wide the same tail has been shrinking for five days: calls above
500K ran 34% (08-21) → 8% → 1% → 6% → **0%** (08-26). That is the cost-threshold
family's own pre-registered prediction — *"the two leave bands fire on under 15%
of main-thread calls"* — and it passes. **The caveat is not small: the restart
discipline produces many short sessions, and a fresh session is cheap for
reasons that have nothing to do with any threshold.** It is the #26 confound
again, and two days is n=2.

**One prediction is failing and should be said out loud.** brief-pack expected
subagent context/call under 30,000, from a measured 89,721. It is **48,480**,
and it went *up* between the two days (45,766 → 48,480). Halfway, stalled, and
not yet retractable at n=2 — but it is not passing.

**The corpus is per-machine; the git history is shared.** Only Windows calls are
in this corpus while both machines commit. This morning that was 4 of 66 commits
and nearly harmless. It will not stay that way, and every tokens-per-commit
figure carries it.

### The scorer that was supposed to answer all this cannot (#44)

Running the report properly for the first time found three defects, and the
third is the one that matters. `report` sums tokens **machine-wide** and divides
by commits **in this repo** — 447,948,034 over 10 commits on 08-25, a
**25x** error against the true 1,778,703. The default metric is
`tokens_per_merge`, and this repo commits to `main` and never merges, so every
intervention has printed `- -> -` since the scorer was written. And under the
brief-pack prediction, which names *subagent* context/call, the scorer prints an
**aggregate**: `context_per_call: 139,580 -> 133,996`, a number that cannot rise
or fall with the thing predicted, with nothing saying so.

**The third one is the worst because it prints a plausible number.** #29's
loader declined every session, #42's archive reported `no_handoff` for a real
loss, and now a scorer reports a figure for a prediction it cannot evaluate.
Three times, and every one failed in the direction that looks like it is
working. `UNSCORABLE` needs to be a visible outcome, distinct from VOID.

### Two Windows-only bugs, both found by asking a question of the tool

| | |
|---|---|
| ~~**#31**~~ | **Closed.** The real `SessionStart` payload here carries six keys — `cwd`, `hook_event_name`, `model`, `session_id`, `source`, `transcript_path` — captured by a session that did not install the hook. The synthetic line had three and was missing half of it. `REASON_KEY = "source"` is confirmed against live Windows data. `agent_type` is in the binary's constructor but **absent** from the live payload; do not branch on it. `transcript_path` is the interesting one: it makes injection correlatable to the session that received it, which is what #26 lacked. |
| ~~**#42**~~ | **NEW, found, fixed, closed.** The handoff written at 23:48 never reached the 23:50 session; it is still on disk. `Path.rename` is `os.rename`, which **raises on Windows when the destination exists** and silently overwrites on POSIX. Once a machine has archived one handoff, every later `consume` hit the existing `.loaded`, raised, was swallowed by `except OSError`, and returned `None` — reported as `no_handoff`. Not the first handoff: **every handoff after the first, on this platform, forever.** `os.replace` fixes it. The old double-consume test never reached the rename, because the first consume moves the file away. |
| ~~**#41**~~ | **Closed, and the macOS diagnosis was right to find nothing.** The file layer was never wrong — the shipped `§` round-trip test **passes on Windows**. Every `subprocess.run` in the package passed `text=True` with no `encoding=`, which decodes with the locale code page: cp1252 here. Git speaks UTF-8, so `git log --format=%s` returned `Â§12` where the same call with `encoding="utf-8"` returns `§12`, both real subjects from this history. **The "two write paths" were never two write paths — they were two *source* paths**, git-derived notes against literals, mixed into one payload by `build()`. Five call sites fixed. |
| **#43** | **NEW, open, split out of #41.** `sys.stdout` is cp1252 here, so `agent-yield --help` emits a bare `0xA7` that is **not valid UTF-8** — a consumer decoding the stream gets an invalid start byte, not a replacement glyph. The `SessionStart` injection is safe **by accident**: `json.dumps` defaults to `ensure_ascii=True` and escapes the payload before it reaches the stream. Protected-by-accident is not a property to rely on; anything added later that prints outside a `json.dumps` inherits the bug silently. |

## [macOS 2026-08-26] What this session added, and the one number to start from

`agent-yield handoff` before you restart. Then read this.

**#33 and #34 are closed. The baton is no longer blocked, and #35-#38 may
proceed** — with #47 open beside them, because the thing #33 could not settle is
whether the cheap arm is the worse arm.

**What the next session should not re-derive.** All of it is in
`working-method.md` §11.2 and §11.3, and in `interventions.toml` with the
prediction that was recorded before the run:

| | |
|---|---|
| end to end | **1.71x** to the baton over six turns, **3.55x** in the limit |
| at the audit turn only | **1.20x** — *under* the 1.25x bar. The tail is the finding |
| a reading parent's turn | ~127,600 tokens, and it grows: 22,424 → 127,510 across one run |
| a dispatching parent's turn | ~35,900 tokens, roughly flat: 22,515 → 31,767 |
| re-entry, per agent | median **22,114**, stdev 2,958, n=79. Not 19,800 |
| what a brief adds | ~11% across the real interquartile range. Write the brief |
| defects found | baton **4/4**, reader **8/8**. Per defect the reader is 1.17x cheaper |

**The protocol is reusable and is committed**, which matters more than any single
number here: `docs/experiments/33-end-to-end/` runs an arm end to end
(`run.sh baton 1`), `measure.py` totals a session including every agent it
started, `score.py` reads compliance out of the transcripts rather than trusting
what an arm says it did, and `table.py` rebuilds the table from the committed
snapshots without needing the transcripts, which are volatile.

### Reconciled against #44, which landed while this was being written

**#33's and #34's numbers do not come from `report` and do not inherit its
defect.** #44 found the scorer summing tokens machine-wide and dividing by
commits in this repo — a 25x error — so the question is fair and needs answering
rather than assuming. Both measurements here go through `ingest.load_records`
over **explicitly named transcripts**: `measure.py` takes one pinned session id,
totals that session's own file plus only the agent transcripts under that
session's directory, and snapshots after every turn. No machine-wide sum, no
commit denominator, and each arm ran as its own `--session-id` so attribution is
by construction rather than by heuristic. The one heuristic in play is
`agents.join` in #34, which reports its failures — 0 unclaimed of 79.

**The two findings agree about something more useful than either number.** #44's
theme is three silences that each *looked* like they were working. #33's
pre-registered VOID bar is a fourth: it was written on claims counted rather than
defects found, so it would have passed an arm that returned nothing. `UNSCORABLE`
as a visible outcome is the fix #44 proposes; **a bar stated in the units of the
finding** is the same fix one file over.

### #47, and it is the one worth running next

| | |
|---|---|
| **#47** | **does dispatching systematically find less?** #33's baton arm returned 4 mismatches in both replicates against the reader's 8, and the reader's are close to a superset — two the baton missed twice were verified by hand and are real defects. Cost per defect *reverses* the headline. Candidate causes, none tested: an agent seeing 4 of 19 modules cannot use the other 15 as context; a "return only JSON" contract discourages a second pass; five agents at 24 calls total is 4.8 calls a module against the reader's 15 calls over 19. **The cheapest discriminating run** is the same task with the baton arm given *one* agent for all 19 modules — if the defect count recovers, it is packing, not dispatching. |

### Two lessons about the bars themselves, which outlast the numbers

**The bar has to be on the finding, not on the denominator.** #33 pre-registered
its VOID condition on *claims counted* when the task's output is *mismatches*. A
baton arm returning zero defects with a full set of claim counts would have
passed. That is #26's failure and #32's failure a third time: **the test written
to the shape of the work rather than to the point of it.**

**A protocol that stops at the obvious turn measures the wrong half.** At t1 this
experiment says "no effect, 1.20x". The five turns after it are the entire
result. Part E stopped at t1 by construction, and that is *why* it could measure
splitting and say nothing about the baton.

### What was found by accident, and fixed

The audit both arms ran was a real audit of this repo, and two of its findings
were verified by hand and are now fixed (`aa973b0`): `discovery` claimed two
transcript locations when there are **three** — newer sessions write
`~/.claude/projects/<slug>/<session>/subagents/agent-<id>.jsonl` and leave
`tasks/<id>.output` as a **symlink** to it, so every new agent transcript is
swept **twice** and only the `(message_id, request_id)` dedup keeps the subagent
bill from doubling. A test pins that now. `resume` claimed five silences where
its own code comment says four of five outcomes are silences.

**Both were missed by the baton arm in both replicates. That is #47 in its
smallest concrete form.**

### The two planning tracks, both reviewed, both RETHINK (#45, #46, #48)

**Method, because it is the point as much as the output.** Each track was planned
by a Fable subagent briefed to §12 — line ranges, a prohibition on exploring, a
named output path, a three-line return contract — and then reviewed by an **Opus**
agent with no shared context and no sight of the planner's reasoning. Different
model on purpose: an independent review is worth nothing if it is the author
agreeing with itself. All four documents are committed under
`docs/superpowers/specs/2026-08-26-*`, because a plan that lives only in a
session tree is the thing §12(c) exists to prevent.

**Both reviews came back RETHINK** — 4 blocking findings on the dashboard, 5 on
the baton — and **the dashboard review caught this page's own headline before
anything was built on it.** That is the strongest argument for the practice that
has come out of it so far: the review paid for itself on its first run, against
the session that commissioned it.

| | |
|---|---|
| **#45** | **Attribute every commit to the machine that made it.** Blocks everything else. Windows call timestamps against committer time, ±6 min. `unknown` must be a real outcome — a commit in a gap where neither machine has calls is not attributable, and pretending otherwise is how the first number went wrong. The window can only misattribute macOS commits *to* Windows, so the Windows denominator is an upper bound and **24% worse is a floor**. |
| **#46** | **Dashboard v1: two stories, not seven.** The plan proposed 9 metrics, 3 modules and a rules engine; the review's scope finding is the one to act on. The blocking finding to carry: the scorecard **would have printed PASS this morning** — `tokens_per_code_insertion` moves 2.38x "better" on a day nothing got more efficient, a *larger* apparent win than the 2.22x the design exists to reject. A display convention is not an enforcement mechanism: **if a metric must not be read alone, it must not be reachable alone.** Contains #44. |
| **#48** | **The baton's 28x is a units error.** Marginal re-billing compared against an absolute one-shot, with the baton parent's own carry (800K, not zero), its brief-writing output, and arm B's own children (~665K) all set to zero. Symmetrically it is **~6.5x**, and its admissible band bottoms out at 2.5x. **6.5x is the magnitude §11 predicted before measuring 1.07x.** Do not carry 28x into `interventions.toml` or §12. |

**The line the review held, and this page should too.** *Measured:* the parent
went 58,475 → 126,522 context/call; the parent was 81% of a 3.5M session;
re-entry ~19,800 (n=4, one run — #34). *Inferred:* that the 68,047 delta is
**removable**. The baton does not remove it — it relocates it to children who read
the same material and pay ~19,800 each to arrive. What it removes is the
**re-billing** of those reads on later parent calls. One term. The whole case
rests on it, and #33 is still the only thing that can settle it.

**#39 and #36 both took a comment rather than a ticket.** The plan reasoned about
`Workflow` from #39's text instead of running it, then sequenced the evaluation
*after* the hand-written loop it was meant to precede — and #36's first slice
would have written the practice into §12 two slices before #33 reports. That is
lever 1's exact path into policy. **Prose is cheaper to write than code and no
cheaper to retract.**
