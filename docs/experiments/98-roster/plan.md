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

So the plan sized its lever with its container's number. The grill put the
roster's own share near 9.2%, and a re-measurement on 2026-08-29 at 13:24 EDT
did not reproduce that figure. Both numbers stay marked unconfirmed until one
method produces the same answer twice.

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

## The roster's own share is the blocker, and three methods disagree

On 2026-08-29 at 13:24 EDT, counting the `description:` frontmatter of every
skill and agent shipped by the six enabled plugins (the text that lands in the
resident listings, which do not lazy-load) returned:

| method | `pr-review-toolkit` share |
|---|---|
| all cached versions | 63.7% |
| newest version per plugin | 42.7% |
| grill, 2026-08-29 12:50 EDT | 59% |

The spread is version selection. Several plugins carry more than one cached
version and one is directory-named by sha rather than semver, so "the installed
version" is not recoverable by sorting directory names. The newest-version pass
also counted 35 `mattpocock-skills` skills against roughly 11 that appear in a
live session's listing, so it is reading skills the harness does not surface.

Its total, 14,718 characters of listing description across 51 skills and 6
agents, is about 3,680 tokens against a 56,623-token opening: **6.5%**. That is
the same neighbourhood as the grill's 9.2%, produced by a method that is
provably counting the wrong set. Agreement between two wrong methods is not
evidence.

**Nothing downstream of this number runs until one method is reproducible.** A
pre-registered bar computed from an unstable denominator is `#111` again.

## What the grill found wrong in fact, not in method

1. **`playwright` is not being re-enabled.** The first version wrote "once
   re-enabled" into the method. The setting is still `false` at line 21 of
   `~/.claude/settings.json`; re-enabling was auto-denied and needs a manual
   edit. Any count that includes it is projecting.
2. **`agent-yield` has tool limits the plan did not account for.**
3. **`CLAUDE.md` and `CONTEXT.md` disagree.** `CLAUDE.md` says `CONTEXT.md` and
   `docs/adr/` are "neither created yet". `CONTEXT.md` now exists, at
   `d951652`. `docs/adr/` still does not. The `CLAUDE.md` line needs correcting.

Roster verified against `~/.claude/settings.json` on 2026-08-29: six enabled
(`claude-code-setup`, `code-review`, `mattpocock-skills`, `pr-review-toolkit`,
`remember`, `superpowers@superpowers-marketplace`), nine disabled. `superpowers`
is installed twice from two marketplaces and the `claude-plugins-official` copy
is the disabled one.

## What is measured and what is chosen

MEASURED: every token and dollar figure in the cost table, by `agent-yield
status` over the session's own transcript at `--baseline-calls 10`, the same
estimator that produced the 68,761. Growth 2.06x, 56,623 to 116,895 over 49
calls. The enabled and disabled roster, read from settings.

UNCONFIRMED, and treated as neither measured nor chosen: 9.2%, 59%, 6.5%,
42.7%, 63.7%.

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

1. **Fix the denominator.** Read the installed plugin version from the harness's
   own resolution rather than from cache directory names, and count only the
   entries that reach a listing. The test is that the method returns the same
   share twice.
2. Correct the `CLAUDE.md` line that says `CONTEXT.md` does not exist.
3. Run the invocation count against the six enabled plugins, `playwright`
   excluded until it is actually re-enabled.
4. Pre-register with `agent-yield prereg` before changing a setting: bar in
   tokens, plugins named, capability check written in, confounds stated.
5. Cut, restart, score.

Steps 3 through 5 are blocked on step 1.
