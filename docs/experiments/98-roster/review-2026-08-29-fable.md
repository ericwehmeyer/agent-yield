# The lever is 2,934 tokens and the same-day drift is 12,535, so do not run this cut

Review of `plan.md` (rewritten 13:32 EDT), written 2026-08-29 against two
facts the plan predates: the opening was re-measured at 69,158 tokens on the
same box, the same day, with fewer plugins enabled (#121), and the 7-day
allowance the account is billed against has zero recorded snapshots (#120).
Both figures are measured; every chosen number below says so.

## 1. No. A 2,934-token lever cannot be read against a 12,535-token unexplained swing

The plan's lever is the plugin roster: 11,736 characters (measured), about
2,934 tokens at the plan's chosen 4 chars per token, 5.2% of the 56,623-token
opening it was sized against. Since the plan was written, the opening moved
from 56,623 to 69,158 — a 12,535-token drift, same day, same machine, with
*fewer* plugins enabled. The drift is 4.3 times the lever, its direction is
the wrong way for a plugin explanation, and 46,477 of the 69,158 tokens have
no attributed source.

Run the experiment anyway and the score is unreadable. Cut the roster, restart,
and the opening lands somewhere in a band at least 12,535 tokens wide for
reasons nobody can name; a 2,934-token effect vanishes inside it. The result
would be attributable to the roster only by assuming the drift holds still for
exactly the interval of the measurement, and nothing measured today supports
that assumption.

The drift also reaches backward. The plan's "settled" section records `#98`'s
fall as 12,138 tokens — smaller than the 12,535 the opening moved with no
intervention at all. That scored result stays committed, as the plan insists,
but it now carries the same caveat this review attaches to the next one: a
fall inside the noise band is not yet a fall.

The spend side rescues nothing. Context is 99.3% of consumption (measured),
the roster is roughly 7 cents of a $1.39-per-session preamble ceiling, and the
one quantity the account is billed against — the 7-day allowance — has zero
snapshots, because the statusline wiring that would record it receives
`rate_limits: null` (#120). A 7-cent saving in a unit that is not the billed
unit, scored against a denominator that moves 12,535 tokens a day, is not an
experiment. It is a coin flip with paperwork.

## 2. The pre-registration question is moot

Question 2 was conditional on yes. The confounds it would have had to name
(the drift, `playwright`'s mid-day return, handoff injections) are exactly
what question 3's experiment exists to measure, so nothing is lost.

## 3. The smallest worthwhile experiment is a repeatability run, and its denominator is 69,158

Before any lever is worth pulling, the noise floor of the thing it moves must
be measured. The experiment: change no setting, restart five times, measure
the opening each time with the same estimator that produced the 68,761
baseline, and attribute what the runs contain. Its denominator is the
69,158-token opening measured today (measured); its numerator is tokens moved
from the unattributed 46,477 into named sources; its bar is the spread across
identical restarts, which becomes the floor every future lever must clear.
Five runs is chosen, not derived — enough to see a spread, cheap enough to do
this week.

Two results are possible and both pay. If the spread is small, the 12,535 was
a one-time attributable event, #121 closes with a cause, and the roster cut
revives with a real noise floor under it. If the spread is large, the roster
cut was never scoreable and this review's no is confirmed at the cost of five
restarts. Fixing #120 belongs in the same pass: until `rate_limits` arrives
non-null, no spend claim in the billed unit is checkable at all.

## 4. Skill-selection quality is not measurable as the plan describes it, so the experiment has no primary bar

Answer 1 names the primary bar: "whether the agent picks the right skill when
the listing is smaller." Step 3's instrument is an invocation count across the
seven enabled plugins. An invocation count measures how often a skill fired,
not whether it was the right one; it has no ground truth, no task set, no
denominator of opportunities, and no baseline accuracy to compare against. As
written, the primary bar cannot produce a pass or a fail, which leaves spend —
disqualified above — as the only live bar.

What would make it measurable: a pre-registered battery of prompts, each with
the correct skill named in advance, run in fresh sessions against both
rosters, scored as picked-right over total. The battery and its size are
chosen; the accuracy is measured. Until that battery exists, the honest
statement is that the experiment has no primary bar, and step 4 should not be
written.

## 5. Where the plan breaks docs/style.md

- **Rule 1, lead with the finding.** The first sentence is "Written 2026-08-29
  12:35 EDT (Windows), before a deliberate restart." That is provenance. The
  finding, 5.2%, arrives in line 17.
- **Rule 6, the measured/chosen distinction belongs in the prose.** The plan
  carries a section headed "What is measured and what is chosen" with
  "MEASURED:" and "CHOSEN," blocks — the separate section of epistemic
  throat-clearing rule 6 names and bans.
- **Rule 10, headings are sentences.** "Now what" and "The grill's questions,
  answered" are labels. So is the title's tail: "that fraction is still
  unmeasured" stands over a body whose own line 77 measures it at 5.2%, a
  heading the structure pass should have caught.
- **Rule 5, the writer admiring the writing.** "Remaining slack, and it is
  stated rather than smoothed" performs its own honesty; the sentence works
  without the flourish.

## Now what

1. Do not execute the plan's step 5. Steps 3 through 5 are blocked behind
   #121 and #120, not behind more analysis.
2. Run the five-restart repeatability pass and attribute the 46,477
   unattributed tokens. Close or bound #121 with the result.
3. Fix the null `rate_limits` payload so the allowance series starts existing
   (#120).
4. If the noise floor comes back under the lever, write step 4's
   pre-registration then, with the skill battery from section 4 as the
   primary bar and spend second.

What would change this verdict: five identical restarts whose openings agree
within about 1,000 tokens. That would mean the 12,535 was an event, not a
band, and a 2,934-token lever becomes readable overnight.
