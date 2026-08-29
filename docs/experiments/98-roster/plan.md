# The preamble is 61.9% of the tokens and 24.7% of the dollars, so measure before cutting again

Written 2026-08-29 12:35 EDT (Windows), before a deliberate restart, for the
session that picks this up.

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
six-plugin figure is unmeasured. It is now unmeasurable as written, because
`playwright` is being re-enabled.

**Do not re-read the old prediction as if it covered the current roster.** The
configuration that remains needs a new one.

## The number that decides whether this is worth doing at all

Measured over session `76a3725b`, 49 calls:

| | tokens | tok % | dollars | $ % |
|---|---|---|---|---|
| cache write (1h) | 228,715 | 5.9% | $2.2872 | 44.9% |
| cache read | 3,595,504 | 93.0% | $1.7978 | 35.3% |
| output | 40,230 | 1.0% | $1.0057 | 19.8% |

The preamble is 2,774,522 tokens, 61.9% of everything the session consumed and
66.1% of every cache read, and **$1.39 of $5.62**. Cache reads price at
$0.50/Mtok against a write's $10.00/Mtok, so the largest token line is the
smallest dollar line but one.

That sets the honest ceiling on this work. Cutting the entire remaining plugin
roster cannot recover more than about a dollar per session at this length, and
`#63` measured 14,992 cache read + 7,124 write of the opening as the harness's
own system prompt and tool schema, which is not ours to remove. The case for
proceeding is skill-selection quality, not spend.

## What is measured and what is chosen

MEASURED: every token figure above, by `agent-yield status` over the session's
own transcript at `--baseline-calls 10`, the same estimator that produced the
68,761. Growth 2.06x, 56,623 to 116,895 over 49 calls.

CHOSEN, and not yet defended: that the remaining roster is worth measuring at
all, and which plugins would be cut. Both are questions for the grill below,
not assumptions to carry in.

## The method, which is not new

`#98` counted tool calls per plugin over the probe log and found zero postman,
zero vpai and zero chrome-devtools against 26 playwright. Apply the same count
to the currently enabled roster: `code-review`, `pr-review-toolkit`,
`superpowers`, `claude-code-setup`, `remember`, `mattpocock-skills`, plus
`playwright` once re-enabled.

Two contributors have never been checked the way postman was.
`mattpocock-skills` adds roughly 11 skills to the resident skill listing and
`pr-review-toolkit` roughly 6 agents to the agent listing. Listings do not
lazy-load; skill *bodies* and MCP tool *schemas* already do, so the listing is
the whole remaining lever.

## Now what

1. Run the count. It is a measurement, not an opinion, and it belongs before
   any prediction.
2. Pre-register with `agent-yield prereg` before changing a setting. State the
   bar in tokens, name the plugins, and write the capability check into the
   prediction rather than discovering it afterwards, which is what `#98` had to
   do.
3. Cut, restart, score.

## The grill has not happened yet, and these are its open questions

The operator asked for this to be stress-tested after the restart. Round 1 of
the frontier, with a recommended answer on each:

1. **Is spend the metric at all?** The ceiling is about $1 a session. If the
   real objective is skill-selection quality, the bar cannot be written in
   tokens. Recommendation: score both, and make the token bar secondary.
2. **What counts as "used"?** `#98` counted tool calls. A skill that fires once
   and saves an hour is not waste, and a listing entry consumed on every call
   is not free. Recommendation: count invocations, and report cost-per-use
   rather than a use/no-use verdict.
3. **What is the capability check, written in advance?** `#98` failed this
   twice. Recommendation: name, before cutting, what each candidate would cost
   us if it turns out to be needed.
4. **n=1 against n=1 again?** Every opening-context comparison so far compares
   one session to one session, and the two differed in a handoff injection and
   three unregistered plugins. Recommendation: state the confounds in the
   prediction, or raise the bar to cover them.
5. **Does this repo need `CONTEXT.md` and `docs/adr/` first?** `CLAUDE.md`
   names both and neither exists. Recommendation: no, keep them separate, but
   the domain-modeling pass is worth its own session.
