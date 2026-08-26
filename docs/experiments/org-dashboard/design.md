# The org dashboard has one measured cell

156,447,461 tokens over 12,696 inserted lines, 12,323 tokens per line, two
days, one machine, one repo. That is every real number in `dashboard.html`.
The other six teams, their eight weeks of history, and the rollup's aggregate
are generated, and the page says so on the banner, on every tile, and on every
bar the generated numbers touch. The prototype exists to show what the view
would be worth if the data existed, and to be deleted if the data never does
(see the falsifier at the bottom).

## Seven levels became two, because five of them asked no new question

The brief started as CTO, MD, ED, Director, Manager, Team Lead, Team. The
middle five are the same screen with a bigger denominator: children compared
on the same ratio, an outlier flagged, a mix check. A level that asks no new
question is not a level, so the page has two renderers over one recursive
tree. An internal node renders the rollup (children compared over two
windows); a leaf renders the ledger (days, machines). A deeper org is more
internal nodes fed to the same two renderers, which is where the hierarchy
lives now: in the data shape, not in screens.

## The metric family, and the scope printed beside it

**Headline: tokens per inserted line, any kind.** Numerator: the unit's
recorded calls. Denominator: the inserted lines the same unit's commits
shipped, same window. It is the least gameable denominator this repo has
found; every narrower one has already produced a published error (#44's 25x
from a cross-scope join, #46's 2.38x from a mix shift). Each view prints its
scope in a strip at the top, because a correct number with an unstated scope
is how both defects shipped.

- `tokens_per_insertion` is the only per-line ratio that exists alone. The
  code and docs halves appear only inside the rendered triple `any/code/docs`,
  mirroring `PerInsertion.render`: no column, no tile, no selectable series
  carries a half. The mix panels (insertion counts by kind) are the guard
  that lets a reader test a yield delta against a mix shift.
- `tokens_per_commit` rides the tiles and tables as a secondary.
- Cost-band shares (share of main calls at or above the dispatch, restart and
  stop thresholds) label themselves from a `THRESHOLDS` object whose values
  are read from `src/agent_yield/thresholds.py` at build time and rendered at
  runtime. A retune is one regenerated block, not a hunt through markup. In a
  served version the block would be emitted by the module itself.
- A number a view cannot compute prints `UNSCORABLE`, styled as loudly as a
  number: the real team's period-over-period delta (no prior-window corpus)
  and the macOS machine row (no macOS calls in this clone's corpus; #66).
  Never a dash, never a plausible substitute. Four defects failed in the
  reassuring direction; this page is built not to be the fifth.

## The data model, in five lines

- A tree of units; a unit is either internal (has children) or a leaf.
- Every unit carries the same per-day record: tokens, calls, commits,
  inserted lines split code/docs/other, main and subagent context per call,
  cost-band counts.
- A parent's day is the sum of its children's days; nothing exists at a
  parent that is not a sum over leaves.
- A leaf's numerator comes from its members' `calls.jsonl`; its denominator
  from `git log` over its repos, attributed by reflog.
- The org shape itself comes from the directory (HR system or IdP), which is
  the only input this repo cannot produce.

## What `calls.jsonl` has today, and what an org would need

Exists on every record: timestamp/day, `session_id`, per-call usage (input,
output, cache read), context, `is_subagent`, `model`, and `cwd`, which is
what `scope_to_repo` scopes on. The denominator side (commits, insertions,
`classify_path`, reflog attribution) comes from git, not from the corpus.

Does not exist anywhere: a user identity, a team identity, an org path, a
machine identity inside the record, or a repo-to-team mapping. Those are the
entire cost of the real version. `cwd` plus a maintained repo-to-team table
would bootstrap team attribution without touching the recorder; user and org
attribution need a field the recorder does not write today.

## What is synthetic

Six teams (Payments, Risk Analytics, Platform, Client Portal, Market Data,
Trading Tools), their 56 days, the rollup aggregate, and both teaching
outliers: Risk Analytics' 1.9x climb and Client Portal's mix-shift
"improvement". All of it is seeded and deterministic, chipped SYNTHETIC in
the UI, drawn dashed or translucent, and excluded from every blend with the
real team. The measured cell is Agent Yield: the two `agent-yield report
--since 2026-08-25 --machine` rows and their `outcomes` join, captured
2026-08-26 while the second day was still running. The numbers are measured;
the windows, thresholds and team shapes are chosen.

## Delete this by 2026-09-23 unless a second real leaf exists

If by **2026-09-23** the rollup still has exactly one real team, meaning no
second corpus (the macOS clone's `calls.jsonl` per #66, or any second user)
has been ingested and joined to its own denominator, delete this dashboard
rather than extend it. A rollup over one real leaf compares nothing with
nothing; keeping it would be scaffolding dressed as measurement, and the
scaffold has already served its purpose by naming the missing fields above.
What would change my mind before the date: a second leaf lands and its
tokens-per-line disagrees with this one by more than the day-to-day spread
measured here (4,232 to 16,326), in which case the rollup has a real question
to answer and earns the extension.
