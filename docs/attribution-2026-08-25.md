# Where main-thread context growth comes from (2026-08-25 sample)

Own reads (A) account for 55.4% of measured context growth across five main-thread sessions. Subagent returns (B) account for 11.4%. Everything else (C: assistant text, user turns, system reminders) accounts for 33.2%. The gap between B and C does not close even in the two most dispatch-heavy sessions in the sample.

## Sample

Five largest main-thread transcripts from `C:/Users/ewehm/transcript-archive/2026-08-25/projects/**/*.jsonl` that contain at least one `Agent` tool_use (files under `.../subagents/` and `.../tasks/` excluded — those are subagent transcripts, not main-thread):

- `C--Users-ewehm-repos/5435e727-...jsonl` — 937 intervals, 65 dispatches
- `C--Users-ewehm-repos-opik-rigor/7a853e19-...jsonl` — 473 intervals, 51 dispatches
- `C--Users-ewehm-repos-opik-rigor/15d4d5f9-...jsonl` — 383 intervals, 26 dispatches
- `C--Users-ewehm-repos-opik-rigor/17231070-...jsonl` — 376 intervals, 36 dispatches
- `C--Users-ewehm-repos-opik-rigor/19675672-...jsonl` — 347 intervals, 18 dispatches

All five happen to be dispatch-heavy (18-65 `Agent` tool_use blocks each), so there is no low-dispatch control group inside this sample — see the caveats below.

## Full sample

| source | tokens added | share of total growth | n intervals |
|---|---|---|---|
| A — own reads (Read/Bash/Grep/Glob/Edit/Write) | 2,923,881 | 55.4% | 2,516 (shared count) |
| B — subagent returns (Agent/Task) | 600,212 | 11.4% | 2,516 |
| C — everything else | 1,749,942 | 33.2% | 2,516 |
| **total** | **5,274,034** | 100% | 2,516 |

(n intervals is the count of context-increasing steps across all five sessions; each interval splits proportionally across A/B/C by character volume, so it is not a per-bucket count.)

## Restricted to sessions with >= 3 subagent dispatches

All five sampled sessions qualify (18-65 dispatches each), so this table is identical to the full-sample table above:

| source | tokens added | share of total growth |
|---|---|---|
| A | 2,923,881 | 55.4% |
| B | 600,212 | 11.4% |
| C | 1,749,942 | 33.2% |

Because the top-5-by-size filter already selected sessions with heavy dispatch activity, this sample cannot show whether the split shifts in a *low*-dispatch session — there wasn't one large enough to make the cut.

## Subagent-return interval sizes

- n B-attributed intervals: 113
- median single-interval delta attributed to B: 4,293 tokens
- max single-interval delta attributed to B: 25,700 tokens
  - tool_use_id: `toolu_01MCLWGZAvMfHwm1WEa5uRtr`
  - session: `7a853e19-dd91-4bd0-add3-23b8b8b635da` (opik-rigor)

## Sanity check

sum(A+B+C) = 5,274,034 tokens. sum(final_context - opening_context) across the five sessions = 2,703,420 tokens. That's a 95% discrepancy — the attributed total is nearly double the net growth these sessions actually ended up with.

The cause: step 2 floors every interval delta at 0 before attribution. Main-thread context does not only grow — it also drops sharply at compaction events and after certain cache-eviction boundaries, and this sample's sessions are long and dispatch-heavy enough to hit those repeatedly. Every drop is thrown away (floored to 0) while every rise is kept and attributed, so the running sum of attributed tokens overshoots the real end-to-end change by the total size of whatever got compacted away mid-session. This means the reported token counts above should be read as gross tokens attributed to growth events, not as a reconciled account of the session's final context size.

## What dominates, and does dispatch volume change it

Own reads dominate context growth in this sample, at roughly 5x the volume attributed to subagent returns (55.4% vs 11.4%). This holds inside the dispatch-heavy subset too, because the dispatch-heavy subset is the entire sample — there's no lower-dispatch comparison to check whether more subagent use shifts the ratio. Within the five sessions individually, the two with the most dispatches (65 and 51) also show B's largest absolute share (176,989 and 200,095 tokens respectively, both above the sample median), so the direction of the individual data points is consistent with "more dispatches, larger B" but the sample provides no contrast group to confirm this as a trend rather than coincidence.

## What this cannot tell you

The character-proportional split in step 4 is a guess, not a measurement. When an interval's growth has to be divided among multiple tool_results that arrived in the same gap (e.g., a Read and an Agent return landing between two API calls), the split assumes tokens grow in direct proportion to character count of the raw tool_result text — but Read/Bash/Grep output and Agent-return text tokenize differently (code and structured data have different chars-per-token ratios than prose subagent summaries), so a 50/50 character split is not a 50/50 token split. This biases the attribution in an unknown direction per interval; it is not correctable from this data alone.

The 95% sanity-check gap means roughly half of everything counted as "growth" in this analysis was later compacted away and is not present in the sessions' final context size. The percentage splits (A/B/C) are computed over that gross, uncompacted total — they say how new tokens got attributed as they arrived, not how much of the *current* context window each source is responsible for. A session that dispatches many subagents but also compacts aggressively after each one would show low B in a like-for-like comparison, and this method cannot separate that from a session that simply doesn't dispatch much.

Finally, all five sessions in this sample are dispatch-heavy by construction (they were selected by file size, and size correlates with dispatch count in this data). There is no low-dispatch main-thread session in the top five to compare against, so the claim "dispatch volume doesn't change the A/B/C split" is unverified here — it's simply not falsifiable from this sample.
