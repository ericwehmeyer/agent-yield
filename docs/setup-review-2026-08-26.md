# Claude Code setup review — ewehm, Windows clone, 2026-08-26

> **Provenance, added when this was landed on main.** Written by a Fable agent
> reading `~/.claude/`, the hooks, the plugin roster and the corpus, finishing
> 23:13 UTC. One section was overtaken while it ran, and it is annotated here
> rather than edited, for the reason the sibling review carries the same note:
> a review is a measurement with a date on it.
>
> * **R5 is out of date in both directions.** `fetch-depth: 0` landed in
>   `a55c352` about twenty minutes before this document was written, together
>   with the two halves #82 asks for. More importantly, the fix cannot be
>   confirmed and is not what is red now: every job since ~22:24 UTC comes back
>   with `runner_id=0`, `steps=[]`, and the annotation "The job was not started
>   because recent account payments have failed or your spending limit needs to
>   be increased." `bcef5eb` at 22:23:26Z ran on a runner; `86feea2` at
>   22:30:39Z did not. R5's conclusion survives -- the machinery is off and
>   outranks everything below it -- but the cause is billing, not the pin, and
>   "minutes of work" is wrong: no change in this repo can fix it.
> * **None of the `settings.json` edits in R1, R3 or R6 have been applied.**
>   They are recommendations about the operator's own machine configuration,
>   and they are his to make. Nothing under `~/.claude/` was touched.
>
> The corpus arithmetic -- 419 dispatches, 200 over the 27-call cap holding 91%
> of subagent tokens, 92% of subagent calls on opus-5 -- has not been
> independently re-derived here. It is the reviewer's, from the file named at
> the top of §1.

Filed as issues #96 (gate), #97 (subagent model), #98 (plugins), #99 (handoffs),
#101 (CLAUDE.md), #102 (autoMode block), #103 (small cleanups); CI and NEXT.md
findings were already covered by #82 and #25 and were not re-filed.

Corpus: `.agent-yield/calls.jsonl`, 21,614 calls, 2026-07-24 to 2026-08-26,
3.216B tokens, $2,192 list-price equivalent (burn-ledger figures, cross-checked
by independent recomputation here: $2,250 including a $5/M guess for the
unpriced opus-4-8 rows). The corpus is machine-wide, not repo-wide: opik-rigor
8,481 calls, mk-main 5,253, governor 1,940, agent-yield itself 1,361.

## 1. Verdict

The restart discipline works and the measurement culture is real: on 08-26 the
main thread made zero calls above 500K context, against 148 of 437 on 08-21,
and every constant in the tool carries its own denominator. What is costing you
is the thing your own rubric already names: 200 of 419 subagent dispatches
exceeded your 27-call briefed cap, and they carry 1.51B of 1.66B subagent
tokens — 91%, roughly $1,000 of the $2,192 total. The single highest-value
change is to wire up the enforcement you already built: `agent-yield gate`
exists, is tested, and is not installed — the PreToolUse hook that IS installed
is a finished research probe running someone else's venv on every tool call.
Second is subagent model choice: 92% of subagent calls ran on opus-5 at $5/M
when sonnet-5 at $2/M was never tried at scale.

## 2. Recommendations, by expected value

### R1. Install `agent-yield gate` as the PreToolUse hook; retire probe.py

**Evidence.** Grouping `.agent-yield/calls.jsonl` by `(session_id, agent_id)`
directly (not `agent-yield agents`, which #84 says under-joins): 419 dispatches,
median 26 calls each, p90 84, max 281. The 200 dispatches over the 27-call
briefed cap hold 1.51B of 1.66B subagent tokens (91%). Subagent spend is
$1,176.70 (53.7% of all dollars), so oversized dispatches are on the order of
$1,000 over 23 days — ~$43/day at list. The single worst dispatch (session
5435e727, agent ad12d693) made 281 calls and 44.4M tokens, about $25 by itself.
Your own thresholds.py records that briefed dispatches run 4–27 calls and
unbriefed ones 62–188; the corpus says the unbriefed shape still dominates the
bill. Meanwhile `.claude/settings.local.json` runs `probe.py` on every tool
call — 1,618 spawns in the last two days — and the probe answered its question
on 08-25 (the log contains `Agent` events with `dispatch_keys`, which is the
one fact it existed to establish). It also runs under
`C:/Users/ewehm/repos/migration-kit/.venv` — a cross-repo dependency that
breaks silently if that venv moves — and at the 150–800ms per-spawn cost the
remember plugin measured on Windows, 1,618 spawns is 4–20 minutes of pure
wall-clock over two days.

**Change.** `.claude/settings.local.json` becomes:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Agent",
        "hooks": [
          {
            "type": "command",
            "command": "C:/Users/ewehm/repos/agent-yield/.venv/Scripts/agent-yield.exe gate",
            "timeout": 5
          }
        ]
      }
    ]
  }
}
```

(Adjust the invocation to whatever `gate`'s hook contract expects — it is your
own CLI. Matcher `Agent` only: the probe matched `*` because it was measuring;
the gate has no business firing on `Bash`.) Optionally add `agent-yield
boundary` under `UserPromptSubmit` — NEXT.md claims "both hooks are installed
in `.claude/settings.json` on this machine" and on this machine only
SessionStart is. That sentence is currently false on Windows.

**Cost to adopt.** One settings edit. `gate` fails open by design. #27 says
enforcement "waits on measured waste" — the measured waste is the paragraph
above.

### R2. Default subagents to sonnet-5; verify with one arm

**Evidence.** 14,250 of 15,513 subagent calls (92%) ran claude-opus-5;
recomputing dollars per call puts subagent opus-5 spend at ~$1,138. Sonnet-5's
reconciled rate in your own pricing.py is $2/M against opus-5's $5/M — same
multipliers, so a sonnet subagent with the same token profile costs 40% as
much. If half the dispatch volume (search, audit, file-bounded edits per §12
briefs) holds quality on sonnet, that is roughly $340 per 23 days, ~$15/day at
list. Your recent behaviour already leans this way — the probe log's 24
dispatches chose sonnet 10, fable 7, haiku 3, opus 3 — but nothing enforces it
and the historical default was opus.

**Change.** Add to the project CLAUDE.md (this repo has none — that is itself
worth fixing, see R6) or the dispatch rubric in working-method.md §12: every
briefed dispatch passes `model: "sonnet"` unless the brief says why not. Then
run it as an arm, pre-registered like #83: `baton1v` re-run with sonnet
workers, bar set at the existing defect counts. Do not adopt on price alone;
#47 showed the brief moves defect yield 2x, so model effects must be measured
against that noise.

**Cost to adopt.** One rubric line plus one experiment (~$5 by your arm costs).

### R3. Disable the plugins this machine does not use

**Evidence.** The per-session fixed context this roster injects, measured from
this session's own transcript: skill listing 18,899 chars (~4.7K tokens), agent
listing 9,962 (~2.5K), deferred-tool names 7,385 (~1.8K), superpowers
SessionStart preamble 3,472 (~0.9K), remember SessionStart 7,211 (~1.8K) —
about 11.7K tokens before the first prompt, re-read as cache on every call.
Attribution by plugin: postman ~630 tok of skills plus an agent entry and 2
deferred tools; chrome-devtools-mcp ~430 tok of skills plus 33 deferred tools;
vpai ~100; claude-code-setup ~100; mattpocock ~640. The probe log's 1,618 tool
calls over two days contain zero postman, zero vpai, zero chrome-devtools
calls — and 26 playwright calls, so playwright earns its slot.
`settings.json` also enables superpowers twice
(`superpowers@superpowers-marketplace` 6.2.0 AND
`superpowers@claude-plugins-official` 6.3.0) — two copies, two hook
registrations, one of them stale.

**Change.** In `~/.claude/settings.json` `enabledPlugins`:

```json
"postman@claude-plugins-official": false,
"vibe-prospecting@claude-plugins-official": false,
"chrome-devtools-mcp@claude-plugins-official": false,
"claude-code-setup@claude-plugins-official": false,
"superpowers@superpowers-marketplace": false
```

**Payoff, honestly sized.** Roughly 3.5–4K tokens of fixed context per call;
at cache-read rates across 21,614 calls that is on the order of $40 over 23
days, call it $2/day — about 2% of spend. The larger benefit is not dollars:
it is that 24 postman/vpai/chrome-devtools skills stop competing for skill
selection in a repo where they can only misfire, and session start gets
quieter. Do not expect this to move the bill visibly.

### R4. One handoff mechanism, not three

**Evidence.** Three systems currently carry state across restarts. (1)
`agent-yield handoff`/`resume` — consumed-once, measured (re-entry median
22,114 tokens, #34), wired as SessionStart, and correctly emitted nothing today
when no handoff was pending. (2) The remember plugin — this session's
SessionStart injected a 7,211-char block whose own header says "already
delivered 17 times since 2026-08-26 10:42 — no new handoff has been written
since". Seventeen deliveries of a stale handoff is ~30K tokens of noise across
the day's 11 sessions, and its "Next" items (#51, #49, #50) closed days ago.
(3) `docs/NEXT.md` — 176,767 bytes, ~44K tokens if a session reads it, still
titled "Start here after a session restart". #25 already names the fix (a file
per session); the cheaper immediate cut is archival: NEXT.md's own head says
everything below a certain line describes retired units.

**Change.** Keep (1). For (2), keep remember's daily digest but stop writing
its handoff section — `agent-yield handoff` is the purpose-built version, and
`/remember`'s handoff duplicates it one prompt later; if the plugin's config
cannot separate the two, live with it but stop treating its Next list as
current. For (3), move everything above the "State of the board" section into
`docs/next-archive/2026-08-25.md` and hold NEXT.md under ~10KB. A start-here
doc that costs 44K tokens to start on is charging you the thing it exists to
save.

**Cost to adopt.** One file split plus a habit. No tooling.

### R5. Fix CI before the next experiment lands (#82, already filed)

**Evidence.** All five most recent pushes show `tests` failing in 4–56s; #82
says the cause is `test_arms_65` running `git archive` against a SHA a shallow
checkout lacks. CI is one day old and has been red its whole life. Every
"green on six jobs" claim since 17:08 UTC on 08-26 was manual. This is filed
already, so no new ticket — but it outranks everything below it here, because
the workflow's whole premise is that claims are checked by machinery, and the
machinery is off.

**Change.** `fetch-depth: 0` on the checkout step, or fetch the pinned SHA
explicitly. Minutes of work.

### R6. Give the repo a CLAUDE.md, and fix the stale autoMode block

**Evidence.** The project has no CLAUDE.md or AGENTS.md. The rules every
session must rediscover — interpreter is `.venv/Scripts/python.exe` (bare
`python` has no pytest; the handoff quoted above repeats this every restart),
handoff-before-restart, the §12 dispatch rubric, "pull before touching
docs/NEXT.md because the Mac pushes continuously" — live in a 176KB NEXT.md and
in the handoff text, both of which are per-session artifacts. Ten lines of
CLAUDE.md would carry them permanently for ~250 tokens. Separately,
`~/.claude/settings.json`'s `autoMode.environment` block names
**ericwehmeyer/opik-rigor** as "the trusted repo" and its working directory as
`C:\Users\ewehm\repos\opik-rigor` — copied from another project and now wrong
in every auto-mode session started in agent-yield. A trust declaration that
names the wrong repo is worse than none.

**Change.** A CLAUDE.md of roughly:

```markdown
# agent-yield

- Interpreter: `.venv/Scripts/python.exe` (bare `python` has no pytest).
- Tests: `.venv/Scripts/python.exe -m pytest`.
- Before ending a session: `agent-yield handoff`. Before starting work: `git pull` (two machines push to main).
- Subagent dispatches follow working-method.md §12: line ranges, no-explore prohibition, output path, return contract, second-pass clause, `model: sonnet` unless justified.
- Numbers in docs/ are generated, never typed. Regenerate via the script named at the bottom of each doc.
```

And regenerate or delete the autoMode environment block (it is per-user
config; re-run whatever produced it from inside this repo).

**Cost to adopt.** ~250 tokens per call of new fixed context — cheaper than the
handoff re-stating the interpreter path forever.

### R7. Small items

- **Permissions**: the global allowlist permits `Bash(pytest *)` and
  `python -m pytest` — spellings this repo never uses; the real one is
  `.venv/Scripts/python.exe -m pytest`. Add
  `"Bash(.venv/Scripts/python.exe -m pytest *)"` and
  `"Bash(.venv/Scripts/agent-yield.exe *)"` to project `.claude/settings.json`
  (the `/fewer-permission-prompts` skill will derive this list from your
  transcripts).
- **statusline.ps1** still contains its "one-shot sample dump — delete this
  block after" block, plus a Test-Path per render. Harmless, finished, delete.
- **`.claude/hooks/probe-log.jsonl`** is 370KB and growing on every tool call;
  R1 stops the growth; archive the log next to the working-method §12 evidence
  it supports.
- **#66** (hand over the macOS status line) is open and cheap; two machines
  with different instrumentation is how #45's denominator bug happened.

## 3. What NOT to change

- **The restart/handoff discipline.** It measurably works: 08-21 had 148 of
  437 main calls at ≥500K context; 08-26 had zero, across 11 sessions. Median
  within-session context growth is 4.7x (first call ~44K to max ~250K) — the
  sessions now end near the 300K dispatch band instead of the 700K stop band.
  The rule you are already living is the right one: **hand off and restart when
  the status line reaches 300K**, the band whose calls historically carried
  54.4% of main-thread dollars. The remaining headroom is small — capping every
  historical main call at 300K would have saved only ~$141 of cache reads over
  23 days — because you already closed most of it. Do not tighten further; a
  restart costs a measured 22K re-entry and the curve has no knee.
- **The status line.** Zero token cost, carries context and dollars, correctly
  built with a git timeout. This is the cheapest instrument you own.
- **Issue-per-defect with pre-registration.** #83 and #39 registering their
  bars before the runs is the reason the #47 retraction was possible. Keep it.
- **Generated docs.** The burn-ledger/context-cost "nothing here is typed in"
  rule has caught real staleness three times (#44, #46, #72). Keep it.
- **`commit.cleanup whitespace`** — already set on this clone; set it on the
  Mac if not done (#66's sibling).
- **superpowers TDD / brainstorming flow.** The 08-26 report shows 142 commits
  in a day with tests green locally; the process is not the leak, the dispatch
  sizing is.
- **Keeping the corpus in `.agent-yield/calls.jsonl`.** This review exists
  because that file does.

## 4. Open questions

- **Actual bill vs list price.** Everything here is list-price equivalent;
  `allowance` implies a subscription, so real marginal cost of R1–R3 may be
  rate-limit headroom rather than dollars. The ranking of recommendations
  survives (their own pricing.py argument); the absolute $/day figures do not.
  Determining it needs the plan tier, which no file states.
- **Does sonnet-5 hold quality on §12-briefed dispatches?** Unmeasured. One
  pre-registered arm answers it (R2).
- **The macOS clone.** Its corpus, settings, hooks, and status line are
  invisible from here (#66, #20). Every machine-wide claim above is really a
  Windows claim.
- **Tokens per shipped commit over 23 days.** Not answerable from this repo:
  the corpus spans opik-rigor/mk-main/governor, whose git histories weren't
  joined, and agent-yield's own history starts 08-25. Within this repo,
  tokens-per-inserted-line rose 4,232 → 6,170 from 08-25 to 08-26 — but that is
  two data points during a shift from building to measuring, not a trend.
  `agent-yield outcomes --since 2026-07-24 --repo <path>` run per-repo would
  answer it; that join is the tool's stated purpose and is still the least
  exercised subcommand.
- **Whether subagents inherit the full skill/agent listings.** Assumed yes in
  R3's arithmetic; if the harness trims subagent system context, the R3 saving
  shrinks toward its main-thread share (~28%).
