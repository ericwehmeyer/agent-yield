"""#65's first question, answered from the corpus before spending on the arms.

#65 was filed on one premise: the packing rule is applied to dispatches with a
**52-call median**, and no arm has ever been run at a packed depth over 15, so
the rule is arithmetic above ~15 calls. The first half of that premise is a
POOLED figure. §11.4's own limits already say 62 of the 84 runs come from one
other project's audit fleet; nobody had broken the call counts out per project,
and the break-out is what decides whether the experiment can be run here at all.

So this counts calls per subagent transcript, grouped by the project the session
ran in, and asks one question of each group: how many of its dispatches reach the
break-even depth §11.4 quotes.

    depth.py                 # every project on this machine
    depth.py --breakeven 35  # against the trimmed-schema band's floor

A call is `(message_id, request_id)` via `CallRecord`, so a transcript reachable
both directly and through its `tasks/*.output` symlink is counted once -- symlinks
are skipped and the real file is read.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from agent_yield.discovery import main_transcript_dir, subagent_transcript_dirs
from agent_yield.ingest import load_records

# The two ends of §11.4's break-even band: trimmed brief and schema, and the
# standard schema this repo's fleet actually dispatches on.
BANDS = {"trimmed": (35, 97), "standard": (72, 196)}


def call_counts() -> dict[str, list[int]]:
    by_project: dict[str, list[int]] = defaultdict(list)
    for root in [main_transcript_dir(), *subagent_transcript_dirs()]:
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if path.is_symlink() or not path.is_file():
                continue
            name = path.name
            if name.endswith(".meta.json"):
                continue
            if not (name.endswith(".output") or name.startswith("agent-")):
                continue
            records = load_records([path])
            if records:
                by_project[path.relative_to(root).parts[0]].append(len(records))
    return by_project


def describe(calls: list[int], breakeven: int) -> dict:
    calls = sorted(calls)
    return {
        "n": len(calls),
        "median": statistics.median(calls),
        "p90": statistics.quantiles(calls, n=10)[8] if len(calls) >= 10 else max(calls),
        "max": max(calls),
        "at_or_over_breakeven": sum(1 for c in calls if c >= breakeven),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--breakeven", type=int, default=BANDS["trimmed"][0],
                    help="floor of the band to count against (default 35, trimmed schema)")
    args = ap.parse_args(argv)

    by_project = call_counts()
    pooled: list[int] = []
    rows = {}
    for slug, calls in sorted(by_project.items(), key=lambda kv: -len(kv[1])):
        pooled += calls
        rows[slug] = describe(calls, args.breakeven)
    rows["POOLED"] = describe(pooled, args.breakeven)

    print(f"{'project':50s} {'n':>4s} {'median':>7s} {'p90':>6s} {'max':>5s} "
          f"{'>=' + str(args.breakeven):>6s}")
    for slug, row in rows.items():
        print(f"{slug[:50]:50s} {row['n']:4d} {row['median']:7.1f} {row['p90']:6.1f} "
              f"{row['max']:5d} {row['at_or_over_breakeven']:6d}")
    print(json.dumps({"breakeven": args.breakeven, "bands": BANDS, "projects": rows}, default=float))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
