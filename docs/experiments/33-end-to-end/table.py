"""The #33 table: cumulative tokens per turn, both arms, both replicates.

Reads the per-turn snapshots `run.sh` wrote, so it reports what was measured at
the time rather than re-reading transcripts that may since have been emptied.

The crossover row is the point of the whole thing. The audit turn is one number
and the five turns after it are the other half of the claim -- a parent that
read everything carries it on every later call, and that is only visible
cumulatively.
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

RUNS = ["baton-r1", "baton-r2", "reader-r1", "reader-r2"]
TURNS = [f"t{n}" for n in range(1, 7)]


def load(base: Path, run: str) -> dict[str, dict]:
    out = {}
    for turn in TURNS:
        path = base / run / f"cumulative-{turn}.json"
        if path.exists():
            out[turn] = json.loads(path.read_text(encoding="utf-8"))
    return out


def main() -> int:
    base = Path(sys.argv[1] if len(sys.argv) > 1 else ".agent-yield/experiments/33")
    data = {run: load(base, run) for run in RUNS}
    present = [r for r in RUNS if data[r]]

    print(f"{'turn':6}" + "".join(f"{r:>14}" for r in present) + f"{'reader/baton':>14}")
    for turn in TURNS:
        cells, means = "", {}
        for run in present:
            total = data[run].get(turn, {}).get("total_tokens")
            cells += f"{total:>14,}" if total else f"{'-':>14}"
            means.setdefault(run.split("-")[0], []).append(total or 0)
        ratio = ""
        if means.get("baton") and means.get("reader") and all(means["baton"]) and all(means["reader"]):
            ratio = f"{statistics.fmean(means['reader']) / statistics.fmean(means['baton']):>14.2f}"
        print(f"{turn:6}{cells}{ratio}")

    print()
    for run in present:
        last = data[run].get("t6") or data[run][max(data[run])]
        print(f"{run:10} parent {last['parent_calls']:>3} calls {last['parent_tokens']:>10,}   "
              f"agents {last['agent_count']:>2} / {last['agent_calls']:>3} calls {last['agent_tokens']:>10,}   "
              f"total {last['total_tokens']:>10,}")

    finals = {}
    for run in present:
        last = data[run].get("t6") or data[run][max(data[run])]
        finals.setdefault(run.split("-")[0], []).append(last["total_tokens"])
    if len(finals) == 2:
        baton, reader = statistics.fmean(finals["baton"]), statistics.fmean(finals["reader"])
        print()
        print(f"mean baton  {baton:>12,.0f}")
        print(f"mean reader {reader:>12,.0f}")
        print(f"reader / baton  {reader / baton:.2f}x")
        for arm, vals in finals.items():
            if len(vals) > 1:
                print(f"within-{arm} spread  {max(vals) / min(vals):.2f}x  ({min(vals):,} .. {max(vals):,})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
