"""#34: is re-entry a fixed price, or does the brief pay for itself?

~19,800 tokens is one number from one run of #18 Part E, and the whole cost
model on the baton rests on it being FIXED -- fixed is what makes it amortise,
and amortising is the only reason a long unit beats a short one. If instead it
scales with the length of the brief, then the five-part brief §12 asks for is
buying its own cost back, and "one unit of work" is not free either.

This is observational, over every subagent transcript that survives on this
machine. The first call of an agent is charged before the agent has read
anything, so its context IS the re-entry price: system prompt, tool schemas,
and the brief.

The join from a brief to the agent it started is `agents.join`, heuristic and
labelled one there. Unlinked runs are counted and reported, never guessed at.

Read the intercept and the slope together. The intercept is the fixed part --
what an agent costs before anyone says anything to it. The slope is what a
thousand characters of brief adds. A brief that "buys itself back" is a claim
about the slope; a baton that amortises is a claim about the intercept.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from agent_yield.agents import join, read_agent_runs, read_dispatches
from agent_yield.discovery import find_transcripts, main_transcript_dir, subagent_transcript_dirs
from agent_yield.records import parse_line


def first_call_context(path: Path) -> tuple[str | None, int] | None:
    """(agent_id, context of the first billable call) for one agent transcript."""
    agent_id = None
    try:
        handle = path.open(encoding="utf-8", errors="replace")
    except OSError:
        return None
    with handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except (ValueError, RecursionError):
                continue
            if not isinstance(payload, dict):
                continue
            if agent_id is None:
                agent_id = payload.get("agentId")
            record = parse_line(line)
            if record is None:
                continue
            usage = record.usage
            return agent_id, usage.input_tokens + usage.cache_read_tokens + usage.cache_creation_tokens
    return None


def fit(xs: list[float], ys: list[float]) -> tuple[float, float, float]:
    """Least squares slope, intercept, and Pearson r. No numpy in this repo."""
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    slope = sxy / sxx if sxx else 0.0
    r = sxy / ((sxx * syy) ** 0.5) if sxx and syy else 0.0
    return slope, my - slope * mx, r


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exclude", action="append", default=[],
                    help="substring of a session id to drop (this experiment's own runs)")
    args = ap.parse_args(argv)

    agent_paths = [p for p in find_transcripts(subagent_transcript_dirs())
                   if p.suffix == ".output"]
    main_paths = [p for p in find_transcripts([main_transcript_dir()]) if p.suffix == ".jsonl"]
    first: dict[str, int] = {}
    for path in agent_paths:
        got = first_call_context(path)
        if got and got[0]:
            first[got[0]] = got[1]

    runs = read_agent_runs(agent_paths)
    dispatches = read_dispatches(main_paths)
    audits, orphans = join(dispatches, runs)

    rows = []
    for audit in audits:
        run = audit.run
        if run is None or not run.agent_id or run.agent_id not in first:
            continue
        if any(x in (run.session_id or "") for x in args.exclude):
            continue
        rows.append({
            "project": audit.dispatch.project,
            "type": audit.dispatch.subagent_type,
            "brief_chars": len(audit.dispatch.prompt or ""),
            "first_call": first[run.agent_id],
            "calls": run.calls,
            "total": run.total.total,
        })

    print(f"agent transcripts   {len(agent_paths)}")
    print(f"runs with calls     {len(runs)}")
    print(f"dispatches seen     {len(dispatches)}")
    print(f"unclaimed runs      {len(orphans)}")
    print(f"joined with a brief {len(rows)}")
    if not rows:
        return 1

    firsts = sorted(r["first_call"] for r in rows)
    print()
    print("FIRST CALL OF AN AGENT, before it reads anything")
    print(f"  n       {len(firsts)}")
    print(f"  min     {firsts[0]:,}")
    print(f"  median  {int(statistics.median(firsts)):,}")
    print(f"  mean    {int(statistics.fmean(firsts)):,}")
    print(f"  max     {firsts[-1]:,}")
    print(f"  stdev   {int(statistics.stdev(firsts)):,}" if len(firsts) > 1 else "")

    slope, intercept, r = fit([float(x["brief_chars"]) for x in rows],
                              [float(x["first_call"]) for x in rows])
    print()
    print("FIRST CALL vs BRIEF LENGTH")
    print(f"  slope       {slope * 1000:,.0f} tokens per 1,000 brief chars")
    print(f"  intercept   {intercept:,.0f} tokens at a brief of zero length")
    print(f"  pearson r   {r:.3f}")
    print(f"  brief chars min {min(x['brief_chars'] for x in rows):,} "
          f"median {int(statistics.median([x['brief_chars'] for x in rows])):,} "
          f"max {max(x['brief_chars'] for x in rows):,}")

    # The mechanical price of the brief is ~1 token per 4 characters. A fitted
    # slope well above that is not the brief being expensive -- it is brief
    # length standing in for something else that arrives with it.
    print(f"  mechanical  ~250 tokens per 1,000 brief chars (4 chars a token)")
    quartile = sorted(rows, key=lambda x: x["brief_chars"])
    cut = max(1, len(quartile) // 4)
    short, long = quartile[:cut], quartile[-cut:]
    print(f"  shortest quarter of briefs  median brief {int(statistics.median([x['brief_chars'] for x in short])):,} "
          f"-> first call {int(statistics.median([x['first_call'] for x in short])):,}")
    print(f"  longest  quarter of briefs  median brief {int(statistics.median([x['brief_chars'] for x in long])):,} "
          f"-> first call {int(statistics.median([x['first_call'] for x in long])):,}")

    print()
    print("BY PROJECT (pooling projects is the confound that voided Part C's first run)")
    print(f"  {'project':24} {'n':>3} {'median first call':>18} {'median brief':>13}")
    projects = sorted({x["project"] for x in rows})
    for project in projects:
        sub = [x for x in rows if x["project"] == project]
        print(f"  {project:24} {len(sub):>3} "
              f"{int(statistics.median([x['first_call'] for x in sub])):>18,} "
              f"{int(statistics.median([x['brief_chars'] for x in sub])):>13,}")
        if len(sub) >= 5:
            s, i, rr = fit([float(x["brief_chars"]) for x in sub],
                           [float(x["first_call"]) for x in sub])
            print(f"  {'':24} {'':>3} slope {s * 1000:>9,.0f}/1k chars  "
                  f"intercept {i:>9,.0f}  r {rr:.3f}")

    print()
    print("BY SUBAGENT TYPE")
    for kind in sorted({x["type"] or "?" for x in rows}):
        sub = [x for x in rows if (x["type"] or "?") == kind]
        print(f"  {kind:24} {len(sub):>3} "
              f"median first call {int(statistics.median([x['first_call'] for x in sub])):>9,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
