"""#65's result, in the two units the ticket pre-registered and no others.

Reads every run directory under `.agent-yield/experiments/65/` (or the paths
given), joins `measured.json` to `score.py`'s verdict, and prints the arm
comparison at each tool schema.

The bar, restated so the table cannot be read past it: the packed arm costs no
more than **1.25x** the split arm in LIST DOLLARS and finds **at least as many**
seeded defects. Both halves have to hold; the cost half alone is what #33
pre-registered and #47 had to reopen.

`packed_depth` is printed on every row, including the split rows, because the
ticket's own void condition is a sizing one: "a 'depth 50' experiment whose
packed agent finished in 20 calls has not been run."
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import score as scorer  # noqa: E402

HERE = Path(__file__).resolve().parent
DEFAULT_ROOT = HERE.parents[2] / ".agent-yield" / "experiments" / "65"
TRUTH = json.loads((HERE / "ground-truth.json").read_text(encoding="utf-8"))
BAR = 1.25


def read_run(path: Path) -> dict | None:
    measured = path / "measured.json"
    if not measured.exists():
        return None
    row = json.loads(measured.read_text(encoding="utf-8"))
    arm, schema, rep = path.name.split("-")
    corpus = (path / "corpus-path").read_text(encoding="utf-8").strip() if (path / "corpus-path").exists() else None
    verdict = scorer.score(path.name, path, TRUTH, Path(corpus) if corpus else None)
    turn = path / "turn-1.json"
    cli = json.loads(turn.read_text(encoding="utf-8")).get("total_cost_usd") if turn.stat().st_size else None
    return {"arm": arm, "schema": schema, "rep": rep, **row, **verdict, "cli_dollars": cli}


def fmt(rows: list[dict]) -> None:
    print(f"{'run':26s} {'agents':>6s} {'depth':>6s} {'calls':>6s} "
          f"{'$ list':>8s} {'$ cli':>8s} {'seeds':>6s} {'mism':>5s} {'void':>5s}")
    for r in rows:
        print(f"{r['arm']+'/'+r['schema']+' r'+r['rep']:26s} {r['agent_count']:6d} "
              f"{r['packed_depth']:6d} {r['total_calls']:6d} "
              f"{r['total_dollars']:8.4f} {(r['cli_dollars'] or 0):8.4f} "
              f"{r['seeds_n']:6d} {r['mismatches']:5d} {str(r['void']):>5s}")


def compare(rows: list[dict], schema: str) -> None:
    arms = {a: [r for r in rows if r["schema"] == schema and r["arm"] == a and not r["void"]]
            for a in ("packed", "split")}
    if not arms["packed"] or not arms["split"]:
        print(f"\n{schema}: incomplete -- "
              f"packed n={len(arms['packed'])}, split n={len(arms['split'])}")
        return
    money = {a: statistics.mean(r["total_dollars"] for r in rs) for a, rs in arms.items()}
    seeds = {a: statistics.mean(r["seeds_n"] for r in rs) for a, rs in arms.items()}
    depth = statistics.mean(r["packed_depth"] for r in arms["packed"])
    ratio = money["packed"] / money["split"]
    cost_ok = ratio <= BAR
    quality_ok = seeds["packed"] >= seeds["split"]
    print(f"\n== {schema} schema, packed depth {depth:.1f} calls")
    print(f"   list dollars  packed {money['packed']:.4f}  split {money['split']:.4f}"
          f"   ratio {ratio:.2f}x  (bar {BAR}x, {'PASS' if cost_ok else 'FAIL'})")
    print(f"   seeds found   packed {seeds['packed']:.1f}  split {seeds['split']:.1f}"
          f"   of {len(TRUTH['seeds'])}  ({'PASS' if quality_ok else 'FAIL'})")
    print(f"   PREDICTION: {'HELD' if cost_ok and quality_ok else 'FAILED'}"
          f"  -- {'break-even is above' if cost_ok else 'the rule does not hold at'}"
          f" a packed depth of {depth:.0f} calls")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="*", type=Path)
    ap.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    args = ap.parse_args(argv)

    paths = args.paths or sorted(p for p in args.root.iterdir() if p.is_dir())
    rows = [row for row in (read_run(p) for p in paths) if row]
    rows.sort(key=lambda r: (r["schema"], r["arm"], r["rep"]))
    fmt(rows)
    for schema in ("trimmed", "full"):
        if any(r["schema"] == schema for r in rows):
            compare(rows, schema)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
