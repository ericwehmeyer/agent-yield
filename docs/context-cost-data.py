"""Recompute every measured figure on `context-cost.html` from the corpus.

The page was hand-authored and its data blocks were pasted in. That is how it
came to carry two different corpus snapshots at once: the header said 20,757
calls while the figure-2 legend said 20,255, and nothing on the page could
have told you. A page whose numbers are typed cannot be re-derived, and a
number that cannot be re-derived goes stale silently -- which is the failure
this repo keeps filing (#44, #46, #67, #72).

So the numbers come from here now. `--check` re-derives them and reports what
disagrees with the page without touching it; `--write` rewrites the two data
blocks and every measured figure in the prose.

Definitions, and they are the page's own:

* **Context per call** is `input + cache_read + cache_creation`, which is
  `CallRecord.context`. Output is not in it: the bill under discussion is what
  was fed in.
* **Spend** is the sum of that context over calls. This page is deliberately
  in tokens rather than dollars -- it is a retrospective about context volume,
  not an arm comparison -- but see `docs/burn-ledger.md`, which prices the same
  corpus and shows how far the two units diverge.
* **Main and subagent** are split by `CallRecord.is_subagent`, from the calls
  themselves rather than from any aggregate. They are 2.6x apart at the
  median; blending them describes neither.
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agent_yield.ingest import load_ingested  # noqa: E402
from agent_yield import thresholds  # noqa: E402

HERE = Path(__file__).resolve().parent
PAGE = HERE / "context-cost.html"
CORPUS = HERE.parent / ".agent-yield" / "calls.jsonl"

STEP = 25_000          # histogram bucket width, and the page's `STEP`
BUCKETS = 33           # 0 .. 825,000
CUM_POINTS = 25        # 0 .. 600,000, the fig-3 decay curve
CURVE_POINTS = 125     # sampled points on the concentration curve

# The rules, and what each is worth. Main-thread limits come from
# `thresholds.py` so a retune moves the page; the subagent one is advice with
# no constant behind it yet and is named here as such.
MAIN_RULES = [
    ("dispatch", thresholds.COST_DISPATCH),
    ("restart", thresholds.COST_RESTART),
    ("stop", thresholds.COST_STOP),
]
SUB_BRIEF = 150_000
# The leverage series the closing section quotes, in ascending limit order.
LEVERAGE_LIMITS = [150_000, 200_000, 250_000, 300_000, 400_000, 500_000]


def population(records, subagent: bool) -> dict:
    ctx = sorted((r.context for r in records if r.is_subagent is subagent), reverse=True)
    total = sum(ctx)
    hist = [0] * BUCKETS
    toks = [0] * BUCKETS
    for c in ctx:
        i = min(c // STEP, BUCKETS - 1)
        hist[i] += 1
        toks[i] += c
    # Share of spending at or above each bucket edge.
    cum = []
    for k in range(CUM_POINTS):
        edge = k * STEP
        cum.append(round(100.0 * sum(c for c in ctx if c >= edge) / total, 1) if total else 0.0)
    return {
        "n": len(ctx),
        "total": total,
        "median": int(statistics.median(ctx)) if ctx else 0,
        "toks": toks,
        "hist": hist,
        "cum": cum,
        "_ctx": ctx,
    }


def curve(ctx: list[int], marks: list[int]) -> dict:
    """Calls ranked most-context-first against the running share of spending."""
    total = sum(ctx)
    n = len(ctx)
    pts = []
    running = 0
    step = max(1, n // CURVE_POINTS)
    for i, c in enumerate(ctx, start=1):
        running += c
        if i % step == 0 or i == n:
            pts.append([round(100.0 * i / n, 2), round(100.0 * running / total, 2)])
    out_marks = {}
    for limit in marks:
        calls = sum(1 for c in ctx if c >= limit)
        spend = sum(c for c in ctx if c >= limit)
        out_marks[str(limit)] = [round(100.0 * calls / n, 2), round(100.0 * spend / total, 2)]
    return {"pts": pts, "marks": out_marks}


def excess(ctx: list[int], limit: int) -> int:
    """Tokens spent ABOVE a limit -- what capping would not have bought.

    Not the spend of calls over the limit: the part of each such call that sat
    above the line. The distinction is the difference between 1.1B and 282M,
    and the page has always meant the second.
    """
    return sum(c - limit for c in ctx if c > limit)


def build() -> dict:
    records = load_ingested(CORPUS)
    if not records:
        raise SystemExit(f"no calls in {CORPUS}")
    main = population(records, subagent=False)
    sub = population(records, subagent=True)
    days = sorted({r.day for r in records})

    m_ctx, s_ctx = main.pop("_ctx"), sub.pop("_ctx")
    grand = main["total"] + sub["total"]

    rules = []
    for name, limit in MAIN_RULES:
        saved = excess(m_ctx, limit)
        rules.append({"rule": name, "limit": limit, "saved": saved,
                      "share": round(100.0 * saved / grand, 1),
                      "calls_over": sum(1 for c in m_ctx if c > limit)})
    brief = excess(s_ctx, SUB_BRIEF)
    rules.append({"rule": "brief failed", "limit": SUB_BRIEF, "saved": brief,
                  "share": round(100.0 * brief / grand, 1),
                  "calls_over": sum(1 for c in s_ctx if c > SUB_BRIEF)})

    # The rules nest: dispatch's saving already contains restart's, which
    # contains stop's. The headline is the union, not the sum.
    avoidable = excess(m_ctx, MAIN_RULES[0][1]) + brief

    leverage = []
    for limit in LEVERAGE_LIMITS:
        calls = sum(1 for c in m_ctx if c >= limit) / len(m_ctx)
        spend = sum(c for c in m_ctx if c >= limit) / main["total"]
        leverage.append(round(spend / calls, 2) if calls else None)

    return {
        "calls": len(records),
        "days": len(days),
        "span": [days[0].isoformat(), days[-1].isoformat()],
        "grand_total": grand,
        "avoidable": avoidable,
        "avoidable_share": round(100.0 * avoidable / grand, 1),
        "rules": rules,
        "leverage": leverage,
        "D": {"main": main, "sub": sub},
        "CURVE": {
            "main": curve(m_ctx, [600_000, 700_000, 500_000, 400_000, 300_000, 250_000, 150_000]),
            "sub": curve(s_ctx, [600_000, 400_000, 250_000, 150_000]),
        },
    }


def _fmt_m(n: int) -> str:
    return f"{n / 1e6:.0f}M" if n >= 1e6 else f"{n:,}"


def report(data: dict) -> str:
    lines = [
        f"corpus        {data['calls']:,} calls, {data['days']} days, "
        f"{data['span'][0]} -> {data['span'][1]}",
        f"context spend {data['grand_total']:,} tokens",
        f"  main        {data['D']['main']['n']:,} calls, {data['D']['main']['total']:,}, "
        f"median {data['D']['main']['median']:,}",
        f"  subagent    {data['D']['sub']['n']:,} calls, {data['D']['sub']['total']:,}, "
        f"median {data['D']['sub']['median']:,}",
        f"avoidable     {data['avoidable']:,} ({data['avoidable_share']}% of the context bill)",
        "rules:",
    ]
    for r in data["rules"]:
        lines.append(f"  {r['rule']:<13} >{r['limit']:>7,}  {_fmt_m(r['saved']):>6}  "
                     f"{r['share']:>4}%  over on {r['calls_over']:,} calls")
    lines.append("leverage      " + ", ".join(f"{v}" for v in data["leverage"]))
    return "\n".join(lines)


def write(data: dict) -> list[str]:
    """Replace the two data blocks. Prose figures are reported, not rewritten."""
    text = PAGE.read_text(encoding="utf-8")
    changed = []
    for name in ("D", "CURVE"):
        payload = json.dumps(data[name], separators=(",", ":"))
        pattern = re.compile(rf"^const {name} = .*?;$", re.M)
        if not pattern.search(text):
            raise SystemExit(f"const {name} block not found in {PAGE.name}")
        text = pattern.sub(f"const {name} = {payload};", text, count=1)
        changed.append(name)
    PAGE.write_text(text, encoding="utf-8")
    return changed


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true", help="rewrite the page's data blocks")
    ap.add_argument("--json", action="store_true", help="dump the whole computation")
    args = ap.parse_args(argv)

    data = build()
    if args.json:
        print(json.dumps(data, indent=1))
        return 0
    print(report(data))
    if args.write:
        print("\nrewrote: " + ", ".join(write(data)))
        print("prose figures are NOT rewritten -- check them against the report above")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
