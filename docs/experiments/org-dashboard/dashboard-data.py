"""Recapture the org dashboard's one real leaf -- both sides, one instant.

#73, review finding B7. `dashboard.html` is a static file with no build step,
so its real leaf is frozen as literals. Frozen is the honest form. Frozen from
two different instants is not: the page held a numerator from one run of
`report` and a denominator from a later run of `outcomes`, and printed neither
capture time. `2026-08-26` disagreed three ways -- 50 commits on the page, 51
from the CLI, 49 in NEXT.md's earlier capture -- against a numerator nobody
could date. 0.3%, and it changed no conclusion; it is still the defect this
repo keeps filing, because a reader had nothing with which to notice.

So both sides come from here, in one invocation, stamped once. The stamp is
taken BEFORE either walk and written to `REAL_SCOPE.captured`, which the page
renders in its scope strip.

`--check` (the default) re-derives and reports what disagrees with the page,
touching nothing, and exits non-zero if a CLOSED day has moved. `--write`
rewrites the two blocks.

**The leaf is ONE CLONE's work, on both sides**, and until now nothing said so
in a form a program could read. The numerator is scoped by `cwd` to this
clone's path; the denominator is this clone's reflog. Two machines work this
repo (§7) and `.agent-yield/` is never pushed, so a page captured on one of
them cannot be re-derived on the other -- every row differs, correctly, and
`--check` read that as *the page is stale*. It is not: it is *this is not the
population the page measured*. `REAL_SCOPE.machine` now records the capturing
clone, `--check` elsewhere reports it and exits 0, and `--write` elsewhere
REFUSES -- rewriting there would replace the capturing clone's real days with
this one's and shrink the page's scope with nothing marking that a day was
lost, which is #72/#81's shape exactly. `--adopt` is how somebody moves the
leaf to this clone in so many words.

A day that has not ended yet still moves. `partial: true` marks it, the page
chips the row, and `--check` reports its drift without failing on it: a day
that is still accruing is not stale, it is unfinished. The distinction is the
one thing this file exists to keep visible.

Definitions, and they are `report.py`'s rather than this file's:

* **calls / tokens** are the window's records whose recorded `cwd` is this
  repo (`scope_to_repo`), and `usage.total`.
* **mainCtx / subCtx** are `cache_read_tokens / calls` over each population
  separately -- `YieldRow.main_context_per_call` and its subagent twin. The
  two run 3-4x apart, so one mean over both describes neither.
* **bands** is the share of the day's MAIN calls at or above each threshold in
  `thresholds.py`, as whole percents, in ladder order.
* **dollars** is `pricing.price_records`, list-price equivalents per model.
  **crUsd / crTok** are the cache-read component of that, which is #72's whole
  argument: ~97% of the tokens and ~65% of the money.
* **commits / code / docs / other** are `daily_outcomes(..., machine=)` --
  this clone's reflog only. Without `--machine` the denominator is every
  machine's work divided by one machine's tokens, which #44 measured at 25x.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "src"))

from agent_yield import pricing, thresholds  # noqa: E402
from agent_yield.attribution import Machine  # noqa: E402
from agent_yield.ingest import load_ingested  # noqa: E402
from agent_yield.outcomes import daily_outcomes  # noqa: E402
from agent_yield.report import scope_to_repo  # noqa: E402

PAGE = HERE / "dashboard.html"
CORPUS = ROOT / ".agent-yield" / "calls.jsonl"

# `REAL_SCOPE.calls` has named the capturing clone since the block was first
# generated, so a page written before `machine` existed can still say where it
# came from. The explicit key wins; this only bridges pages older than it.
CLONE_IN_CALLS = re.compile(
    r"those whose recorded cwd is (.+?) \([\d,]+ calls in the corpus overall\)")

# The window the leaf covers. Every call this repo has ever made falls inside
# it; it is an argument rather than a constant so that widening it is a
# decision somebody records on a command line.
SINCE, UNTIL = dt.date(2026, 8, 25), dt.date(2026, 8, 26)

LADDER = [thresholds.COST_DISPATCH, thresholds.COST_RESTART, thresholds.COST_STOP]

# Keys whose drift on a closed day is a failure. The scope strings and
# `partial` are checked separately; everything measured is here.
MEASURED = ("tokens", "calls", "commits", "merges", "code", "docs", "other",
            "mainCtx", "subCtx", "bands", "dollars", "crUsd", "crTok",
            "unpricedTok", "unpricedModels")


def day_row(records, outcome, partial: bool) -> dict:
    """One `REAL_DAYS` entry, from this day's calls and this day's commits."""
    main = [r for r in records if not r.is_subagent]
    sub = [r for r in records if r.is_subagent]

    cr_dollars = 0.0
    unpriced_tokens = 0
    unpriced_models = set()
    for record in records:
        name = pricing.canonical(record.model) or ""
        rate = pricing.BASE_RATE_PER_MTOK.get(name)
        if rate is None:
            unpriced_tokens += record.usage.total
            unpriced_models.add(name)
        else:
            cr_dollars += rate * pricing.CACHE_READ * record.usage.cache_read_tokens / 1e6

    priced = pricing.price_records(records)

    def per_call(population) -> int:
        if not population:
            return 0
        return round(sum(r.usage.cache_read_tokens for r in population) / len(population))

    return {
        "day": records[0].day.isoformat(),
        "partial": partial,
        "tokens": sum(r.usage.total for r in records),
        "calls": len(records),
        "commits": outcome.commits,
        "merges": outcome.merges,
        "code": outcome.code_lines,
        "docs": outcome.docs_lines,
        "other": outcome.other_lines,
        "mainCtx": per_call(main),
        "subCtx": per_call(sub),
        # Whole percents: the page prints them as "20%/0%/0%", and a decimal
        # place here would imply a precision the session mixture does not have.
        "bands": [round(100 * sum(1 for r in main if r.context >= limit) / len(main))
                  if main else 0
                  for limit in LADDER],
        "dollars": round(priced.dollars, 4) if priced else None,
        "crUsd": round(cr_dollars, 4),
        "crTok": sum(r.usage.cache_read_tokens for r in records),
        "unpricedTok": unpriced_tokens,
        "unpricedModels": sorted(unpriced_models),
    }


def rollup(days: list[dict]) -> dict:
    """What `design.md`'s opening paragraph quotes. Reported, never written."""
    insertions = sum(d["code"] + d["docs"] + d["other"] for d in days)
    dollars = sum(d["dollars"] or 0.0 for d in days)
    return {
        "dollars": round(dollars, 2),
        "insertions": insertions,
        "per_1k": round(1000 * dollars / insertions, 2) if insertions else None,
        "tokens": sum(d["tokens"] for d in days),
        "calls": sum(d["calls"] for d in days),
        "commits": sum(d["commits"] for d in days),
    }


def build(since: dt.date, until: dt.date) -> dict:
    """One stamp, then both walks. The stamp is the point of the file."""
    captured = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)

    corpus = load_ingested(CORPUS)
    if not corpus:
        raise SystemExit(f"no calls in {CORPUS}")
    window = [r for r in corpus if since <= r.day <= until]
    scoped = scope_to_repo(window, ROOT)
    if not scoped:
        raise SystemExit(f"no calls made in {ROOT} between {since} and {until}")

    outcomes = {o.day: o
                for o in daily_outcomes(ROOT, since, until, machine=Machine(ROOT))}
    unattributable = sum(o.unattributable for o in outcomes.values())

    by_day: dict[dt.date, list] = {}
    for record in scoped:
        by_day.setdefault(record.day, []).append(record)

    days = [day_row(by_day[day], outcomes[day], partial=day >= captured.date())
            for day in sorted(by_day)]
    partial = [d["day"] for d in days if d["partial"]]

    stamp = captured.strftime("%Y-%m-%d %H:%M UTC")
    note = (f"; {', '.join(partial)} had not ended and is marked PARTIAL"
            if partial else "")
    scope = {
        # Machine-readable provenance, and the same argument as #73's
        # timestamp one line down: the page already NAMED this path inside
        # `calls`, in prose, where only a person could find it. `--check` ran
        # on the other clone for a day and reported thirteen true differences
        # as staleness because nothing it could read said whose leaf this is.
        "machine": str(ROOT),
        "calls": f"{len(scoped):,} of {len(window):,} calls this machine made "
                 f"{since}..{until} -- those whose recorded cwd is {ROOT} "
                 f"({len(corpus):,} calls in the corpus overall)",
        "outcomes": f"commits and insertions from this clone's reflog (--machine); "
                    f"unattributable: {unattributable} across the window",
        "captured": f"captured {stamp} -- numerator and denominator from one "
                    f"invocation of dashboard-data.py, at that one instant{note}",
        "numerator": f"list-price equivalents from pricing.py over those same "
                     f"{len(scoped):,} calls, priced per model",
    }
    return {"REAL_SCOPE": scope, "REAL_DAYS": days,
            "captured": captured.isoformat(), "rollup": rollup(days)}


class Unreadable(Exception):
    """The page's block cannot be read back, so nothing can be checked.

    Two ways to get here and they want the same answer -- run `--write` once.
    Either the page predates this generator and still carries the
    hand-authored JS literals, or somebody hand-edited the generated block
    into something that is no longer JSON. Both mean the page is asserting
    numbers no reader can re-derive, which is the condition `--check` exists
    to fail on, so this is a stale result rather than a crash.
    """


def page_days() -> list[dict]:
    """What the page currently holds, parsed back out of its own block."""
    text = PAGE.read_text(encoding="utf-8")
    block = re.search(r"^const REAL_DAYS = (\[.*?^\]);$", text, re.M | re.S)
    if not block:
        raise Unreadable("no REAL_DAYS block on the page at all")
    try:
        return json.loads(block.group(1))
    except json.JSONDecodeError as exc:
        raise Unreadable(f"REAL_DAYS is not JSON: {exc}") from None


def page_scope() -> dict:
    """What the page's `REAL_SCOPE` block holds, parsed back out."""
    text = PAGE.read_text(encoding="utf-8")
    block = re.search(r"^const REAL_SCOPE = (\{.*?^\});$", text, re.M | re.S)
    if not block:
        raise Unreadable("no REAL_SCOPE block on the page at all")
    try:
        return json.loads(block.group(1))
    except json.JSONDecodeError as exc:
        raise Unreadable(f"REAL_SCOPE is not JSON: {exc}") from None


def capturing_clone() -> str | None:
    """The clone whose work the page's leaf is, or None if it does not say."""
    scope = page_scope()
    explicit = scope.get("machine")
    if isinstance(explicit, str) and explicit:
        return explicit
    match = CLONE_IN_CALLS.search(scope.get("calls") or "")
    return match.group(1) if match else None


def same_clone(theirs: str, ours: Path) -> bool:
    r"""Is the page's clone this one?

    `normcase` on both sides and deliberately NO `abspath`, which is where
    `scope_to_repo`'s rule stops applying: both values are already absolute,
    and resolving a foreign absolute path against this filesystem is what
    turns `C:\Users\...` into `/Users/ericw/.../C:\Users\...` -- a path that
    matches nothing, by accident rather than by measurement.
    """
    return os.path.normcase(theirs) == os.path.normcase(str(ours))


def diff(fresh: list[dict]) -> tuple[list[str], list[str], list[str]]:
    """Disagreements, split three ways. Only `stale` fails.

    `foreign` is not a gentler `stale`. It is the statement that nothing here
    was measured over the same population, so there is nothing to compare --
    and it is returned INSTEAD of a comparison, never alongside one. A
    row-by-row diff of two clones' work is thirteen true differences that
    mean one thing, and reading them as drift is how this check spent a day
    pointing at the wrong defect.

    It is also not an amnesty, and that distinction is the whole of it: on
    the clone that DID capture the page, a day that vanishes is still
    `stale` and still fails. #26, #32, #44 and #33's own VOID bar each went
    wrong by widening an exemption until a real defect fitted inside it.
    """
    try:
        on_page = {d["day"]: d for d in page_days()}
        theirs = capturing_clone()
    except Unreadable as exc:
        return [f"the page cannot be checked ({exc}); run --write once"], [], []
    if theirs is None:
        return [], [], [
            "the page does not say which clone captured it, so its rows are "
            "re-derivable nowhere; one --write on the clone whose work it is "
            "stamps REAL_SCOPE.machine and this check starts working again",
        ]
    if not same_clone(theirs, ROOT):
        return [], [], [
            f"the page's leaf is {theirs}'s work; this clone is {ROOT}",
            "both of its sides -- calls scoped by cwd, commits from that "
            "clone's reflog -- were measured there, and .agent-yield/ is "
            "never pushed, so nothing on the page can be re-derived here",
            f"days it holds: {', '.join(sorted(on_page))}",
        ]
    stale: list[str] = []
    drifting: list[str] = []
    for day in fresh:
        old = on_page.get(day["day"])
        if old is None:
            stale.append(f"{day['day']}: measured, but not on the page at all")
            continue
        moved = [f"{day['day']} {key}: {old.get(key)!r} -> {day[key]!r}"
                 for key in MEASURED if old.get(key) != day[key]]
        (drifting if day["partial"] else stale).extend(moved)
    measured_days = {d["day"] for d in fresh}
    stale.extend(f"{day}: on the page, absent from the corpus"
                 for day in on_page if day not in measured_days)
    return stale, drifting, []


def report(data: dict) -> str:
    roll = data["rollup"]
    lines = [
        f"captured   {data['captured']}",
        f"scope      {data['REAL_SCOPE']['calls']}",
        f"rollup     ${roll['dollars']} over {roll['insertions']:,} inserted lines "
        f"= ${roll['per_1k']} per 1,000 -- {roll['tokens']:,} raw tokens, "
        f"{roll['calls']:,} calls, {roll['commits']} commits",
        "days:",
    ]
    for day in data["REAL_DAYS"]:
        mark = "PARTIAL" if day["partial"] else ""
        lines.append(
            f"  {day['day']} {mark:<7} ${day['dollars']:>9,.2f}  "
            f"{day['tokens']:>12,} tok  {day['calls']:>5} calls  "
            f"{day['commits']:>3} commits  "
            f"{day['code'] + day['docs'] + day['other']:>6,} ins  "
            f"ctx {day['mainCtx']:,}/{day['subCtx']:,}  bands "
            + "/".join(f"{b}%" for b in day["bands"])
        )
        if day["unpricedModels"]:
            lines.append(f"      unpriced: {day['unpricedTok']:,} tokens on "
                         + ", ".join(day["unpricedModels"]))
    return "\n".join(lines)


def write(data: dict) -> None:
    """Replace the two blocks. They are emitted as JSON so `diff` can re-read them."""
    text = PAGE.read_text(encoding="utf-8")
    days = ",\n  ".join(json.dumps(d, separators=(", ", ": ")) for d in data["REAL_DAYS"])
    blocks = {
        "REAL_SCOPE": ("const REAL_SCOPE = "
                       + json.dumps(data["REAL_SCOPE"], indent=2) + ";"),
        # No trailing comma. JS would take it; JSON will not, and `diff` reads
        # this block back with `json.loads`.
        "REAL_DAYS": "const REAL_DAYS = [\n  " + days + "\n];",
    }
    for name, replacement in blocks.items():
        opener, closer = (r"\{", r"\}") if name == "REAL_SCOPE" else (r"\[", r"\]")
        pattern = re.compile(rf"^const {name} = {opener}.*?^{closer};$", re.M | re.S)
        if not pattern.search(text):
            raise SystemExit(f"const {name} block not found in {PAGE.name}")
        text = pattern.sub(lambda _match, value=replacement: value, text, count=1)
    PAGE.write_text(text, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true",
                        help="rewrite REAL_SCOPE and REAL_DAYS on the page")
    parser.add_argument("--adopt", action="store_true",
                        help="with --write on a clone that did not capture the "
                             "page: move the leaf HERE, replacing that clone's "
                             "days with this one's")
    parser.add_argument("--json", action="store_true",
                        help="dump the whole computation")
    parser.add_argument("--since", type=dt.date.fromisoformat, default=SINCE)
    parser.add_argument("--until", type=dt.date.fromisoformat, default=UNTIL)
    args = parser.parse_args(argv)

    data = build(args.since, args.until)
    if args.json:
        print(json.dumps(data, indent=1))
        return 0

    print(report(data))
    stale, drifting, foreign = diff(data["REAL_DAYS"])

    if args.write:
        if foreign and not args.adopt:
            print("\nREFUSING TO WRITE -- the page's leaf is not this clone's:")
            for line in foreign:
                print(f"  {line}")
            print("\nWriting here would replace those days with this clone's own and "
                  "shrink\nthe page's scope with nothing marking that a day was lost "
                  "-- #72/#81's\nshape, and the reason that finding keeps being "
                  "refiled. Re-run this on\nthe capturing clone, or pass --adopt to "
                  "move the leaf here deliberately.")
            return 1
        write(data)
        print("\nrewrote REAL_SCOPE and REAL_DAYS")
        print("prose is NOT rewritten -- design.md's opening quotes the rollup above")
        return 0

    if foreign:
        # Exit 0. The page is not stale; it is not this clone's to check, and a
        # check that cannot run is not a check that failed.
        print("\nNOT CHECKABLE HERE -- the page was captured on another clone:")
        for line in foreign:
            print(f"  {line}")
        print("\nThis is not staleness. Run --check on that clone to learn whether "
              "the\npage has actually gone stale; the report above is this clone's "
              "own work,\nwhich the page has never claimed to cover.")
        return 0

    if drifting:
        print("\nstill accruing, so this is movement rather than staleness:")
        for line in drifting:
            print(f"  {line}")
    if stale:
        print("\nSTALE -- a closed day on the page disagrees with the corpus:")
        for line in stale:
            print(f"  {line}")
        print("\nre-run with --write, then re-check design.md's opening figures")
        return 1
    print("\nevery closed day on the page matches the corpus")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
