# The org dashboard has one measured cell

$163.01 of list-price equivalent over 15,018 inserted lines -- $10.85 per
thousand lines -- across two days, one machine, one repo, priced per model by
`pricing.py` over the same 1,365 calls. The 198,290,626 raw tokens behind that
are still on the page, in a table that says they are secondary. That is every
real number in `dashboard.html`.

Those figures are a capture, and the page names the instant it was taken.
`dashboard-data.py --write` produces them; `dashboard-data.py` alone re-derives
them and exits non-zero if a closed day has moved, which is what
`tests/test_org_dashboard_unit.py` runs. **On the clone that captured them** --
both sides of the leaf are per-clone, calls scoped by `cwd` and commits from
that clone's reflog, and `.agent-yield/` is never pushed, so the other machine
in §7 can neither re-derive a figure here nor be told it has gone stale.
`REAL_SCOPE.machine` names the clone, the check there says *not checkable* and
exits 0, and `--write` there refuses rather than replacing a real day with a
day this clone never made. The second day had not ended when the
capture was taken and is chipped `PARTIAL` on its row: its figures are a floor,
they are in the totals above unmarked, and excluding them would be a different
silence. Numbers quoted from an earlier capture -- $116.26 over 12,696 lines,
1,096 calls -- moved for two reasons and neither is a correction: the day kept
running, and #81 landed rates for `sonnet-5` and `fable-5`, so tokens that
priced to nothing before now price.

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

**Headline: list-price dollars per 1,000 inserted lines, any kind.**
Numerator: the list-price equivalent of the unit's recorded calls, priced per
model by `src/agent_yield/pricing.py`. Denominator: the inserted lines the
same unit's commits shipped, same window.

The denominator is the half this note originally defended, and it stands: it
is the least gameable one the repo has found, and every narrower one has
already produced a published error (#44's 25x from a cross-scope join, #46's
2.38x from a mix shift). The numerator was the unexamined half, and it was
raw `usage.total` -- the unit `thresholds.py` L76 calls crude in the same file
the page was told to read. Roughly 97% of that sum is cache reads at 0.10x a
base input token, so the ratio ranks cache-hit rate about as hard as it ranks
work. On this repo's own two days cache reads are 95.0% and 97.8% of the
tokens but 49.9% and 64.5% of the dollars: one unit calls the two days alike
and the other separates them by fifteen points. A team that restarts sessions
often -- this repo's recommended discipline, and #26's confound -- posts a
smaller cache-read total for the same work and ranks better on the old unit.
No headcount decision should ride a cache-hit ranking, so the headline moved.

These are LIST-PRICE EQUIVALENTS, and every scope strip says so. `pricing.py`'s
own rule holds here without amendment: on a subscription the ranking of two
ways of working survives, the absolute figure does not, and no view may claim
otherwise.

- `usdPerKIns` is the only per-line ratio that exists alone. The code and docs
  halves appear only inside the rendered triple `any/code/docs`, mirroring
  `PerInsertion.render`: no column, no tile, no selectable series carries a
  half. The mix panels (insertion counts by kind) are the guard that lets a
  reader test a yield delta against a mix shift.
- **Raw-token ratios are kept and have exactly one home**, a table under a
  heading reading *Secondary: the same ratios in raw tokens*. They are there
  because a reader who wants to watch the two units disagree needs both; they
  are not on a tile, an axis, a ranked bar, or a hero.
- **Every scope strip prints both cache-read shares** -- of the tokens and of
  the dollars -- next to the unit itself. The real leaf prints them per day,
  because its two days disagree and the strip is where a reader would look.
- **A model `pricing.py` cannot price is named, not dropped.** On the real
  leaf that is `claude-sonnet-5` on both days and `claude-fable-5` on the
  second, 15.9% of 2026-08-25's priced volume and 4.5% of 2026-08-26's, so
  each day's dollars are stated as the lower bound they are. No rate was
  invented to close the gap: `pricing.py` carries only rates reconciled
  against `modelUsage.costUSD`, and a guessed one would be exactly the
  unreconciled constant that module exists to refuse. #81 asks for the
  reconciliation.
- `tokens_per_commit` rides the tiles and tables as a secondary, in dollars
  per commit.
- Cost-band shares (share of main calls at or above the dispatch, restart and
  stop thresholds) label themselves from a `THRESHOLDS` object whose values
  are read from `src/agent_yield/thresholds.py` at build time and rendered at
  runtime. A retune is one regenerated block, not a hunt through markup. In a
  served version the block would be emitted by the module itself.
- A number a view cannot compute prints `UNSCORABLE`, styled as loudly as a
  number: the real team's period-over-period delta (no prior-window corpus)
  and the macOS machine row (no macOS calls in this clone's corpus; #66).
  **A window in which nothing could be priced is UNSCORABLE too**, never a
  token figure standing in for the dollars -- `sumDays` carries `dollars` as
  null rather than 0, because 0 would read as "it was free". Never a dash,
  never a plausible substitute. Four defects failed in the reassuring
  direction; this page is built not to be the fifth.

## The data model, in five lines

- A tree of units; a unit is either internal (has children) or a leaf.
- Every unit carries the same per-day record: dollars and the cache-read
  dollars inside them, raw tokens and the cache-read tokens inside them, the
  tokens no rate could price and the models they were on, calls, commits,
  inserted lines split code/docs/other, main and subagent context per call,
  cost-band counts, and whether the day had ended when it was captured.
- A parent's day is the sum of its children's days; nothing exists at a
  parent that is not a sum over leaves.
- A leaf's numerator comes from its members' `calls.jsonl`; its denominator
  from `git log` over its repos, attributed by reflog.
- The org shape itself comes from the directory (HR system or IdP), which is
  the only input this repo cannot produce.

## What `calls.jsonl` has today, and what an org would need

Exists on every record: timestamp/day, `session_id`, per-call usage (input,
output, cache read, cache write split by TTL), context, `is_subagent`,
`model`, and `cwd`, which is what `scope_to_repo` scopes on. Usage and model
together are the whole numerator: `pricing.price_records` needs nothing the
recorder does not already write, which is why the unit could change without
touching ingest. The denominator side (commits, insertions,
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
"improvement". Each team also carries a chosen COST PROFILE -- its cache-read,
cache-write and output shares, and how much of its spend is on the dear model
-- because without one, dollars would be a constant multiple of tokens and the
page would demonstrate nothing about why the unit changed. With them, Payments
and Trading Tools sit 4% apart on tok/ins and 2.5x apart in dollars, which is
the failure the old headline permitted, drawn. The profiles are held still
across the window on purpose, so a team's period-over-period delta stays a fact
about its work rather than about a profile made to drift. All of it is seeded
and deterministic, chipped SYNTHETIC in the UI, drawn dashed or translucent,
and excluded from every blend with the real team. The measured cell is Agent Yield: the two `agent-yield report
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
dollars-per-thousand-lines disagrees with this one by more than the day-to-day
spread measured here ($3.35 to $12.03), in which case the rollup has a real
question to answer and earns the extension. That spread is n=2 on one leaf and
is a weak bar, which N5 said of it in tokens and still says of it in dollars.
