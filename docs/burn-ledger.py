"""The burn ledger: where the corpus's tokens went, and where its money went.

These are not the same question, and that is the whole reason this file exists.
A raw token total is ~97% cache reads at 0.10x a base input token, so the two
units rank the same work differently -- `thresholds.py` L76 says so, #72 moved
the org dashboard's headline off tokens for it, and this ledger is the corpus
-wide version of that finding.

The first burn ledger was built on 2026-08-25 and lived only in session notes,
which is how its 3.67B figure survives with nothing to reconcile it against.
This one is generated: `python docs/burn-ledger.py --write` regenerates
`docs/burn-ledger.md` from `.agent-yield/calls.jsonl`, and any figure in that
document that cannot be produced here does not belong in it.

Dollars are LIST-PRICE EQUIVALENTS via `pricing.py`, on `costBasis: "list"`.
On a subscription the ranking of two ways of working survives and the absolute
figure does not. Models `pricing.py` has no reconciled rate for are NAMED and
their tokens reported, never silently dropped -- see #81.
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agent_yield import pricing, thresholds  # noqa: E402
from agent_yield.ingest import load_ingested  # noqa: E402
from agent_yield.usage import Usage  # noqa: E402

HERE = Path(__file__).resolve().parent
CORPUS = HERE.parent / ".agent-yield" / "calls.jsonl"
DEST = HERE / "burn-ledger.md"

BANDS = [
    ("dispatch", thresholds.COST_DISPATCH),
    ("restart", thresholds.COST_RESTART),
    ("stop", thresholds.COST_STOP),
]


def _rate(model: str | None) -> float | None:
    return pricing.BASE_RATE_PER_MTOK.get(pricing.canonical(model) or "")


def _dollars(usage: Usage, model: str | None) -> float:
    rate = _rate(model)
    return 0.0 if rate is None else rate * pricing.weighted_tokens(usage) / 1_000_000


def _component_dollars(usage: Usage, model: str | None) -> dict[str, float]:
    """The formula's five terms, priced separately.

    `weighted_tokens` collapses them; this reproduces the same arithmetic term
    by term so a reader can see which one is actually buying anything.
    """
    rate = _rate(model)
    if rate is None:
        return {}
    per = rate / 1_000_000
    return {
        "input": per * usage.input_tokens,
        "cache read": per * pricing.CACHE_READ * usage.cache_read_tokens,
        "cache write": per * (
            pricing.CACHE_WRITE_5M * usage.cache_creation_5m
            + pricing.CACHE_WRITE_1H * usage.cache_creation_1h
            + pricing.CACHE_WRITE_5M * usage.cache_creation_unattributed
        ),
        "output": per * pricing.OUTPUT * usage.output_tokens,
    }


def _component_tokens(usage: Usage) -> dict[str, int]:
    return {
        "input": usage.input_tokens,
        "cache read": usage.cache_read_tokens,
        "cache write": usage.cache_creation_tokens,
        "output": usage.output_tokens,
    }


def build() -> dict:
    records = load_ingested(CORPUS)
    if not records:
        raise SystemExit(f"no calls in {CORPUS}")

    days = sorted({r.day for r in records})
    priced = pricing.price_records(records)

    tok_parts: dict[str, int] = defaultdict(int)
    usd_parts: dict[str, float] = defaultdict(float)
    by_model: dict[str, dict] = defaultdict(lambda: {"calls": 0, "tokens": 0, "dollars": 0.0, "priced": True})
    by_role: dict[str, dict] = {
        "main": {"calls": 0, "tokens": 0, "dollars": 0.0},
        "subagent": {"calls": 0, "tokens": 0, "dollars": 0.0},
    }
    band_rows = {name: {"calls": 0, "tokens": 0, "dollars": 0.0} for name, _ in BANDS}
    main_calls = main_tokens = 0
    main_dollars = 0.0

    for r in records:
        usd = _dollars(r.usage, r.model)
        for k, v in _component_tokens(r.usage).items():
            tok_parts[k] += v
        for k, v in _component_dollars(r.usage, r.model).items():
            usd_parts[k] += v

        m = by_model[pricing.canonical(r.model) or "unknown"]
        m["calls"] += 1
        m["tokens"] += r.usage.total
        m["dollars"] += usd
        m["priced"] = _rate(r.model) is not None

        role = "subagent" if r.is_subagent else "main"
        by_role[role]["calls"] += 1
        by_role[role]["tokens"] += r.usage.total
        by_role[role]["dollars"] += usd

        if not r.is_subagent:
            main_calls += 1
            main_tokens += r.usage.total
            main_dollars += usd
            for name, limit in BANDS:
                if r.context >= limit:
                    band_rows[name]["calls"] += 1
                    band_rows[name]["tokens"] += r.usage.total
                    band_rows[name]["dollars"] += usd

    return {
        "generated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "calls": len(records),
        "days": len(days),
        "span": (days[0].isoformat(), days[-1].isoformat()),
        "tokens": sum(r.usage.total for r in records),
        "dollars": priced.dollars if priced else None,
        "caveat": priced.caveat() if priced else None,
        "incomplete": sum(1 for r in records if r.incomplete),
        "tok_parts": dict(tok_parts),
        "usd_parts": dict(usd_parts),
        "by_model": dict(by_model),
        "by_role": by_role,
        "bands": band_rows,
        "main": {"calls": main_calls, "tokens": main_tokens, "dollars": main_dollars},
    }


def _pct(part: float, whole: float) -> str:
    return "-" if not whole else f"{100.0 * part / whole:.1f}%"


def render(d: dict) -> str:
    tok_total = sum(d["tok_parts"].values())
    usd_total = sum(d["usd_parts"].values())
    order = ["cache read", "input", "cache write", "output"]

    out: list[str] = []
    w = out.append

    w("# The burn ledger")
    w("")
    w(f"`{d['calls']:,}` calls over {d['days']} days, {d['span'][0]} to {d['span'][1]}, one")
    w(f"machine. **{d['tokens']:,} raw tokens** and **${d['dollars']:,.2f}** of list-price")
    w("equivalent. Every figure below is regenerated by `docs/burn-ledger.py`; nothing")
    w("here is typed in.")
    w("")
    w("## The two units disagree, and that is the finding")
    w("")
    w("The same corpus, split by what the tokens actually were. Dollars use")
    w("`pricing.py`'s formula term by term -- cache reads at 0.10x a base input token,")
    w("cache writes at 1.25x or 2.00x, output at 5.00x.")
    w("")
    w("| component | tokens | share of tokens | dollars | share of dollars |")
    w("|---|---:|---:|---:|---:|")
    for key in order:
        tk = d["tok_parts"].get(key, 0)
        us = d["usd_parts"].get(key, 0.0)
        w(f"| {key} | {tk:,} | {_pct(tk, tok_total)} | ${us:,.2f} | {_pct(us, usd_total)} |")
    w(f"| **total** | **{tok_total:,}** | | **${usd_total:,.2f}** | |")
    w("")
    cr_t = _pct(d["tok_parts"].get("cache read", 0), tok_total)
    cr_d = _pct(d["usd_parts"].get("cache read", 0.0), usd_total)
    out_t = _pct(d["tok_parts"].get("output", 0), tok_total)
    out_d = _pct(d["usd_parts"].get("output", 0.0), usd_total)
    w(f"Cache reads are **{cr_t} of the tokens and {cr_d} of the money**. Output is")
    w(f"**{out_t} of the tokens and {out_d} of the money**. A ledger kept in tokens is")
    w("very nearly a ledger of cache reads; a ledger kept in dollars is most of the way")
    w("to a ledger of what was written. Ranking anything on the token column ranks")
    w("cache-hit rate, which is why #72 moved the org dashboard's headline off it.")
    w("")
    w("## By model")
    w("")
    w("| model | calls | tokens | dollars | priced |")
    w("|---|---:|---:|---:|---|")
    for name, m in sorted(d["by_model"].items(), key=lambda kv: -kv[1]["tokens"]):
        money = f"${m['dollars']:,.2f}" if m["priced"] else "UNPRICED"
        w(f"| `{name}` | {m['calls']:,} | {m['tokens']:,} | {money} | "
          f"{'yes' if m['priced'] else '**no**'} |")
    w("")
    if d["caveat"]:
        w(f"**The total is a lower bound.** {d['caveat']}. No rate was invented to close")
        w("the gap: `pricing.py` carries only rates reconciled against the CLI's own")
        w("`modelUsage.costUSD`, and an unreconciled constant is the thing that module")
        w("exists to refuse. #81 solved sonnet-5 and fable-5 that way; #86 is what is")
        w("left, and names a `<synthetic>` fixture tag that should not be in a real")
        w("corpus at all.")
        w("")
    if d["incomplete"]:
        w(f"{d['incomplete']:,} calls carry a lower-bound `output_tokens` -- their terminal")
        w("record was never written -- so the output row and the total are short by")
        w("whatever those calls emitted.")
        w("")
    w("## Main thread against subagents")
    w("")
    w("Split by `CallRecord.is_subagent`, from the calls themselves. Blending them")
    w("describes neither population.")
    w("")
    w("| role | calls | tokens | share of tokens | dollars | share of dollars |")
    w("|---|---:|---:|---:|---:|---:|")
    for role in ("main", "subagent"):
        r = d["by_role"][role]
        w(f"| {role} | {r['calls']:,} | {r['tokens']:,} | {_pct(r['tokens'], d['tokens'])} | "
          f"${r['dollars']:,.2f} | {_pct(r['dollars'], d['dollars'])} |")
    w("")
    w("## What the cost bands actually cover")
    w("")
    w("Main-thread calls at or above each limit in `thresholds.py`. The share of the")
    w("bill is the number a band is worth acting on; the share of calls is what acting")
    w("on it disturbs.")
    w("")
    w("| band | limit | calls | share of main calls | dollars | share of main dollars |")
    w("|---|---:|---:|---:|---:|---:|")
    for name, limit in BANDS:
        b = d["bands"][name]
        w(f"| {name} | {limit:,} | {b['calls']:,} | {_pct(b['calls'], d['main']['calls'])} | "
          f"${b['dollars']:,.2f} | {_pct(b['dollars'], d['main']['dollars'])} |")
    w("")
    w("These are cumulative, not exclusive: every `stop` call is also a `restart` call")
    w("and a `dispatch` call.")
    w("")
    w("## What this is not")
    w("")
    w("One operator, one machine, one clone. `#20` is the blind re-run on a second, and")
    w("`#66` is the macOS ledger that would make this two machines rather than one.")
    w("Dollars are list-price equivalents and not a bill: on a subscription the ranking")
    w("of two ways of working survives, the absolute figure does not, and no report may")
    w("claim otherwise.")
    w("")
    w("The context-volume argument built on the same corpus is `docs/context-cost.html`,")
    w("deliberately kept in tokens because it is a retrospective about how much context")
    w("was read rather than a comparison between ways of working.")
    w("")
    w(f"*Generated {d['generated']} by `docs/burn-ledger.py` from")
    w("`.agent-yield/calls.jsonl`.*")
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true", help=f"write {DEST.name}")
    args = ap.parse_args(argv)
    text = render(build())
    if args.write:
        DEST.write_text(text, encoding="utf-8")
        print(f"wrote {DEST}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
