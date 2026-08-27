"""Recompute every measured figure on `context-cost.html` from the corpus.

The page was hand-authored and its data blocks were pasted in. That is how it
came to carry two different corpus snapshots at once: the header said 20,757
calls while the figure-2 legend said 20,255, and nothing on the page could
have told you. A page whose numbers are typed cannot be re-derived, and a
number that cannot be re-derived goes stale silently -- which is the failure
this repo keeps filing (#44, #46, #67, #72).

So the numbers come from here now. `--check` re-derives them and compares BOTH
halves of the page -- the two `const` data blocks and the figures typed into
the prose -- reporting what disagrees without touching the file and exiting
non-zero if anything does. `--write` rewrites the data blocks and only those.

The prose is hand-written and stays that way, which is exactly why `--check`
reads it. `--write` on a moved corpus updates `D` and `CURVE` underneath two
dozen typed figures that nothing then re-derives, which is the two-snapshots
state above, reassembled by the tool built to prevent it. A figure a generator
cannot rewrite is a figure it has to watch instead.

An anchor that no longer matches is reported as a disagreement rather than
skipped. A reworded sentence that quietly stops being checked is the same
defect as a wrong number, and harder to see.

Definitions, and they are the page's own:

* **Context per call** is `input + cache_read + cache_creation`, which is
  `CallRecord.context`. Output is not in it: the bill under discussion is what
  was fed in.
* **Spend** is the sum of that context over calls. This page is deliberately
  in tokens rather than dollars -- it is a retrospective about context volume,
  not an arm comparison -- but see `docs/burn-ledger.md`, which prices the same
  corpus and shows how far the two units diverge.
* **Main and subagent** are split by `CallRecord.is_subagent`, from the calls
  themselves rather than from any aggregate. Their medians are far enough
  apart that blending them describes neither. The ratio itself is on the page,
  where `--check` guards it, and is deliberately not repeated here: this
  docstring said 2.6x while the corpus said 2.3x, which is the same rot one
  level up from the page.
"""
from __future__ import annotations

import argparse
import json
import math
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
# The context sizes the fig-3 caption reads its decay series off. Named here so
# the check derives the percentages and the sentence's own list of edges from
# one place: a caption that moved its edges but kept its percentages would
# otherwise pass.
FIG3_EDGES = [200_000, 250_000, 300_000, 400_000, 500_000]


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


def _pct0(value: float) -> str:
    """A percentage as the page writes it: whole, and rounded half UP.

    `f"{58.5:.0f}"` is `58` -- Python rounds halves to even, the page's author
    did not, and the fig-3 series has a 58.5 in it. Getting this wrong makes
    the guard fail on a page that is correct, which is the way a guard gets
    switched off.
    """
    return str(math.floor(value + 0.5))


def _anchors(d: dict) -> list[tuple[str, re.Pattern, tuple[str, ...]]]:
    """Every measured figure typed into the prose, with where to find it.

    Each entry is (what it is, a pattern whose groups ARE the figures, what
    those groups should read). The pattern doubles as the assertion that the
    sentence still exists: `check` reports a pattern that finds nothing as a
    disagreement, because a caption reworded past its anchor stops being
    guarded without ever going red.
    """
    main, sub = d["D"]["main"], d["D"]["sub"]
    marks = d["CURVE"]["main"]["marks"]
    rules = {r["rule"]: r for r in d["rules"]}
    grand, avoid = d["grand_total"], d["avoidable"]
    billions, millions = f"{grand / 1e9:.2f}", f"{avoid / 1e6:.0f}"

    out: list[tuple[str, str, tuple[str, ...]]] = [
        ("headline",
         r"<h1>We spent ([\d.]+) billion tokens\. (\d+) million of them bought nothing\.</h1>",
         (billions, millions)),
        ("tile: spent",
         r'<span class="k">Spent</span>\s*<span class="v">([^<]+)</span>\s*'
         r'<span class="n">tokens of context, (\d+) days</span>',
         (f"{billions}B", str(d["days"]))),
        ("tile: avoidable",
         r'<span class="k">Avoidable</span>\s*<span class="v">([^<]+)</span>',
         (f"{millions}M",)),
        ("tile: share of the bill",
         r'<span class="k">Share of the bill</span>\s*<span class="v">([^<]+)</span>',
         (f"{_pct0(d['avoidable_share'])}%",)),
        ("finding 1: main median",
         r"main-session calls carry more than ([\d,]+) tokens\.",
         (f"{main['median']:,}",)),
        ("finding 2: subagent median",
         r"median subagent call carries ([\d,]+) tokens\.",
         (f"{sub['median']:,}",)),
        ("median ratio",
         r"median main call carries ([\d.]+) times the median subagent",
         (f"{main['median'] / sub['median']:.1f}",)),
        ("fig-1 aria-label",
         r"at ([\d,]+) tokens, sits at ([\d.]+)% of calls and ([\d.]+)% of spending",
         ("600,000", f"{marks['600000'][0]:.1f}", f"{marks['600000'][1]:.1f}")),
        ("fig-1 caption",
         r"catches ([\d.]+)% of calls and ([\d.]+)% of the money",
         (f"{marks['600000'][0]:.1f}", f"{marks['600000'][1]:.1f}")),
        ("fig-1 caption: the 300,000 share",
         r"the largest (\d+)% of their calls, everything above ([\d,]+) tokens",
         (_pct0(marks["300000"][0]), "300,000")),
        ("fig-2 legend",
         r"Main session, ([\d,]+) calls.*?Subagent, ([\d,]+) calls",
         (f"{main['n']:,}", f"{sub['n']:,}")),
        ("fig-3 caption: decay series",
         r"slides through ((?:\d+%, )+\d+%) without a break.*?"
         r"at ([\d,]+(?:, [\d,]+)* and [\d,]+) tokens",
         (", ".join(f"{_pct0(main['cum'][e // STEP])}%" for e in FIG3_EDGES),
          ", ".join(f"{e:,}" for e in FIG3_EDGES[:-1]) + f" and {FIG3_EDGES[-1]:,}")),
        ("so-what heading",
         r"<h2>(\d+) million tokens, and what to take off it</h2>",
         (millions,)),
        ("so-what: share",
         r"in the table below: (\d+)% of everything",
         (_pct0(d["avoidable_share"]),)),
        ("so-what: halved",
         r"It is still (\d+) million tokens",
         (f"{avoid / 2 / 1e6:.0f}",)),
        ("leverage series",
         r"share of calls disturbed, goes ((?:\d+\.\d+, )+\d+\.\d+)\.",
         (", ".join(str(v) for v in d["leverage"]),)),
        ("footer: corpus",
         r"calls\.jsonl</span>: ([\d,]+) calls, deduplicated, "
         r"(\d{4}-\d\d-\d\d) to (\d{4}-\d\d-\d\d)",
         (f"{d['calls']:,}", d["span"][0], d["span"][1])),
    ]

    # The rules table. Each row states its limit once and its worth twice, and
    # the chip is what ties a row to the rule it came from -- matching on the
    # worth instead would happily pair `restart`'s row with `stop`'s numbers.
    for name in ("dispatch", "restart", "stop", "brief failed"):
        rule = rules[name]
        chip = rf'<span class="chip [ms]">{re.escape(name)}</span>'
        out.append((f"rules table: {name} limit",
                    chip + r'<br><span class="mono">([\d,]+)</span>',
                    (f"{rule['limit']:,}",)))
        out.append((f"rules table: {name} worth",
                    chip + r'.*?<td class="n">([\d.]+M)(?: of it)?<br>'
                           r'<span class="dim">([\d.]+)%</span>',
                    (_fmt_m(rule["saved"]), str(rule["share"]))))

    return [(label, re.compile(pattern, re.S), expected)
            for label, pattern, expected in out]


class Unreadable(Exception):
    """A `const` block cannot be read back, so nothing can be checked.

    Either the page predates this generator and still carries the pasted
    literals, or somebody hand-edited a generated block into something that is
    no longer JSON. Both mean the page asserts numbers no reader can
    re-derive, which is the condition `--check` exists to fail on, so it is
    reported as a stale result rather than raised as a crash.
    """


def page_blocks(text: str) -> dict:
    """The two `const` blocks, parsed back out of the page."""
    out = {}
    for name in ("D", "CURVE"):
        block = re.search(rf"^const {name} = (\{{.*?\}});$", text, re.M)
        if not block:
            raise Unreadable(f"no `const {name}` block on the page at all")
        try:
            out[name] = json.loads(block.group(1))
        except json.JSONDecodeError as exc:
            raise Unreadable(f"`const {name}` is not JSON: {exc}") from None
    return out


def diff(data: dict, text: str) -> list[str]:
    """Everything on the page that disagrees with the corpus, both halves."""
    out: list[str] = []
    try:
        blocks = page_blocks(text)
    except Unreadable as exc:
        return [f"the data blocks cannot be checked ({exc}); run --write once"]

    for name in ("D", "CURVE"):
        if blocks[name] != json.loads(json.dumps(data[name])):
            out.append(f"const {name}: the block on the page differs from the corpus")

    for label, pattern, expected in _anchors(data):
        found = pattern.search(text)
        if not found:
            out.append(f"{label}: the sentence this figure lives in is gone, so it "
                       f"is no longer checked (expected {', '.join(expected)})")
            continue
        actual = found.groups()
        if actual != expected:
            moved = [f"{a!r} -> {e!r}" for a, e in zip(actual, expected) if a != e]
            out.append(f"{label}: " + "; ".join(moved))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="compare the page's data blocks AND prose against the "
                         "corpus without touching it; exit 1 on any disagreement")
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
        # Still true, and now it is only half the story: --check reads them.
        print("prose figures are NOT rewritten -- run --check to compare them")
        return 0

    if args.check:
        stale = diff(data, PAGE.read_text(encoding="utf-8"))
        if stale:
            print("\nSTALE -- the page disagrees with the corpus:")
            for line in stale:
                print(f"  {line}")
            print("\n--write fixes the data blocks. The prose is hand-written: "
                  "edit it against the report above.")
            return 1
        print("\nevery measured figure on the page matches the corpus")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
