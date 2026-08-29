# The 61.9% is the preamble; the roster is a fraction of it, and that fraction is still unmeasured

Written 2026-08-29 12:35 EDT (Windows), before a deliberate restart. Rewritten
13:25 EDT after the grill, which had already run when the first version was
committed and whose findings were not in it.

## The error this document was making

The heading used to read *the preamble is 61.9% of the tokens and 24.7% of the
dollars, so measure before cutting again*, and the experiment underneath it cuts
plugins. Those are two different quantities. The preamble is everything that
arrives before the first user turn: `CLAUDE.md`, memory, hook injections, the
harness's own system prompt and tool schema, and the plugin listings. Only the
last of those is what a roster cut removes.

So the plan sized its lever with its container's number. Measured on its own at
13:33 EDT, the roster is **5.2% of the opening**, not 61.9% and not the grill's
9.2%.

## What is already settled, and must not be re-litigated

`#98`'s six-plugin prediction is **spent**. It was scored on 2026-08-29 and the
result is committed in `interventions.toml` at `7ac1512`:

| | tokens |
|---|---|
| opening context/call (measured) | 56,623 |
| bar (chosen) | <= 64,761 |
| baseline (measured) | 68,761 |
| fall | 12,138 |

It cleared its bar and tripped its own suspect clause, which set 12,000 as the
line above which a fall must be checked against a lost capability. The check
fails: `playwright` was one of the six, and `#98`'s own text measures 26
playwright calls and concludes it earns its slot. Nine plugins were disabled
rather than the six pre-registered, so 12,138 is the effect of nine and the
six-plugin figure is unmeasured.

**Do not re-read the old prediction as if it covered the current roster.**

## The session's cost, which is the container and not the lever

Measured over session `76a3725b`, 49 calls:

| | tokens | tok % | dollars | $ % |
|---|---|---|---|---|
| cache write (1h) | 228,715 | 5.9% | $2.2872 | 44.9% |
| cache read | 3,595,504 | 93.0% | $1.7978 | 35.3% |
| output | 40,230 | 1.0% | $1.0057 | 19.8% |

The preamble is 2,774,522 tokens, 61.9% of everything the session consumed and
66.1% of every cache read, and **$1.39 of $5.62**. Cache reads price at
$0.50/Mtok against a write's $10.00/Mtok, so the largest token line is the
smallest dollar line but one. `#63` measured 14,992 cache read and 7,124 write
of the opening as the harness's own system prompt and tool schema, which is not
ours to remove.

$1.39 is the ceiling on cutting the *whole* preamble. The roster is a slice of
that slice, and pricing the roster at $1.39 is the error named above.

## The roster is 5.2% of the opening, and the number now repeats

Resolved 2026-08-29 13:33 EDT. `listing-share.py` beside this file returns the
same table twice, which was the bar:

| plugin | listed | hidden | chars | share |
|---|---|---|---|---|
| `pr-review-toolkit` | 7 | 0 | 6,264 | 53.4% |
| `mattpocock-skills` | 15 | 20 | 3,051 | 26.0% |
| `superpowers` | 14 | 0 | 1,863 | 15.9% |
| `claude-code-setup` | 1 | 0 | 354 | 3.0% |
| `remember` | 2 | 0 | 178 | 1.5% |
| `code-review` | 1 | 0 | 26 | 0.2% |
| `playwright` | 0 | 0 | 0 | 0.0% |
| **total** | **40** | **20** | **11,736** | |

11,736 characters is about 2,934 tokens, **5.2% of the 56,623-token opening**.
Against the $1.39 preamble that is roughly 7 cents a session.

Three earlier attempts gave 63.7%, 42.7% and the grill's 59% because all three
read the plugin version from cache directory names. That does not work. Several
plugins carry more than one cached version and some are named by git sha rather
than semver, so "newest" is not recoverable by sorting: the enabled
`superpowers` is 6.2.0 from `superpowers-marketplace` and sorting picked 6.3.0,
the disabled copy. `installed_plugins.json` states the installed path outright.

The second correction is `disable-model-invocation: true`. A skill carrying it
is reachable by `/name` and is not in the listing the model reads, so it costs
no resident tokens. 20 of 60 entries here are in that class, including
`mattpocock-skills`'s `grill-with-docs` and `wayfinder`.

Remaining slack, and it is stated rather than smoothed: the script counts 15
listed `mattpocock-skills` entries where a live session's listing shows 11. The
4-entry gap is unexplained and biases that plugin's share upward. It does not
move `pr-review-toolkit` off the top.

`4` chars per token is CHOSEN. The 5.2% moves with it, so a bar written from
this number states the divisor beside it.

## What the grill found wrong in fact, not in method

1. **`playwright` was disabled while the method assumed otherwise.** The
   first version wrote "once re-enabled" into a method that then counted it.
   It was re-enabled by hand at 13:26 EDT on 2026-08-29, line 21 of
   `~/.claude/settings.json`, and takes effect at the next session start. So
   the roster is seven plugins from that point, and every figure in this
   document was measured against six.
2. **`agent-yield` has tool limits the plan did not account for.**
3. **`CLAUDE.md` and `CONTEXT.md` disagree.** `CLAUDE.md` says `CONTEXT.md` and
   `docs/adr/` are "neither created yet". `CONTEXT.md` now exists, at
   `d951652`. `docs/adr/` still does not. The `CLAUDE.md` line needs correcting.

Roster verified against `~/.claude/settings.json` on 2026-08-29: seven enabled
(`claude-code-setup`, `code-review`, `mattpocock-skills`, `pr-review-toolkit`,
`playwright`, `remember`, `superpowers@superpowers-marketplace`), eight
disabled. The measurements above predate `playwright`'s return and cover six.
`superpowers` is installed twice from two marketplaces and the
`claude-plugins-official` copy is the disabled one.

## What is measured and what is chosen

MEASURED: every token and dollar figure in the cost table, by `agent-yield
status` over the session's own transcript at `--baseline-calls 10`, the same
estimator that produced the 68,761. Growth 2.06x, 56,623 to 116,895 over 49
calls. The enabled and disabled roster, read from settings.

MEASURED as of 13:33 EDT: the listing table above, by `listing-share.py`,
reproducible across runs.

RETIRED, all produced by version-by-directory-name and none reproducible:
9.2%, 59%, 6.5%, 42.7%, 63.7%.

CHOSEN, and defended in the answers below: that the remaining roster is worth
measuring at all.

## The grill's questions, answered

Round 1 ran 2026-08-29 12:50 EDT. These are its answers, not its
recommendations.

1. **Is spend the metric?** No, secondary. The ceiling on the whole preamble is
   $1.39 a session and the roster is a fraction of it. The primary bar is
   skill-selection quality: whether the agent picks the right skill when the
   listing is smaller. Score both and report spend second.
2. **What counts as "used"?** Invocations, with cost-per-use reported, not a
   use/no-use verdict. `#98` counted tool calls, and that is how `playwright`
   was cut with 26 calls to its name.
3. **What is the capability check?** Written into the prediction before the cut,
   naming per candidate what it costs us if it turns out to be needed. `#98`
   failed this twice, which is why its suspect clause fired.
4. **n=1 against n=1?** State the confounds in the prediction. The two sessions
   compared so far differed in a handoff injection and three unregistered
   plugins, so the difference was never attributable to the roster alone.
5. **Does this repo need `CONTEXT.md` and `docs/adr/` first?** Answered by
   events: `CONTEXT.md` was written at `d951652`. `docs/adr/` remains absent and
   is a separate session's work.
6. **What is the goal above this experiment?** Meta-efficiency: whether agentic
   AI raises throughput in a quality and release role by orders of magnitude.
   That is the operator's own throughput, not the agent's cost per commit. The
   two have different denominators, and this experiment moves only the second.

Open: Q10, unrecorded. It was posed at 13:03 EDT and its text did not survive.

## Now what

1. ~~Fix the denominator.~~ Done 13:33 EDT: `listing-share.py`, 5.2%.
2. Correct the `CLAUDE.md` line that says `CONTEXT.md` does not exist.
3. Run the invocation count against all seven enabled plugins. `playwright`
   is back as of 13:26 EDT, so the count and the cost table now disagree on
   the roster and the table is the older of the two.
4. Pre-register with `agent-yield prereg` before changing a setting: bar in
   tokens, plugins named, capability check written in, confounds stated.
5. Cut, restart, score.

Step 1 is done, so nothing is blocked. But 5.2% of the opening and about 7
cents a session is a small enough prize that step 4's bar should be written on
skill-selection quality first and spend second, exactly as answer 1 says.
