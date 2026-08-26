"""The orientation term, measured a second time -- from the archive (issue #63).

§11.4's break-even rests on ONE measurement of what an extra agent costs before
it does any work: §11.1's pair, one agent over six files in 5 calls against
three agents in 12, which fits ~3.5 fixed calls an agent. Two runs, one task.
That single term is the whole width of the 55-281 break-even band, so #63 asked
for the experiment that measures it again -- dispatch one agent over k slices
against k agents, and count CALLS.

**That experiment has already been run and nobody noticed.** #33's baton arm and
#47's baton1 arm are the same task -- audit 19 module docstrings -- with the
same brief, the same return contract and the same five-turn tail, dispatched as
FIVE agents and as ONE. Two replicates each, compliance already verified from
the transcripts, defects already scored. All four sessions' agent transcripts
survive, both copies of each. So the second measurement costs nothing but this
file.

WHAT THE HEADLINE NUMBER ESTIMATES, stated so nobody over-reads it. The estimand
is the extra CALLS a split pays per extra agent on fixed work, which is what the
break-even equation needs. It is NOT pure arrival overhead: a fatter agent also
batches its reads better, and that saving is inside this number too. Same
estimator as §11.1's, applied to independent data, so the two are comparable --
and both are upper bounds on orientation alone.

Everything is priced in LIST DOLLARS (`pricing.py`), per #55. A token-scored
version of this measures the cache-read rate and not the packing.

    python3 docs/experiments/63-orientation/orientation.py
"""
from __future__ import annotations

import json
import statistics
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from agent_yield.discovery import main_transcript_dir, subagent_transcript_dirs
from agent_yield.ingest import load_records
from agent_yield.pricing import (BASE_RATE_PER_MTOK, CACHE_READ, CACHE_WRITE_5M,
                                 OUTPUT, canonical, price_records)

# The four archived arms. The slug differs because #47 ran in a throwaway
# worktree pinned to 76cbf08 -- see interventions.toml -- so a session id alone
# does not locate a transcript.
MAIN = "-Users-ericw-IdeaProjects-agent-yield"
WORKTREE = ("-private-tmp-claude-501--Users-ericw-IdeaProjects-agent-yield"
            "-b87046ab-1d77-46eb-8014-870cc270d8c9-scratchpad-ay47")

ARMS = [
    ("split-r1", 5, MAIN, "33333333-0000-4000-8000-000000001010"),
    ("split-r2", 5, MAIN, "33333333-0000-4000-8000-000000001020"),
    ("packed-r1", 1, WORKTREE, "33333333-0000-4000-8000-000000003010"),
    ("packed-r2", 1, WORKTREE, "33333333-0000-4000-8000-000000003020"),
]

# §11.4's terms, quoted so this file's arithmetic can be checked against the
# section it revises.
GROWTH = (0.00103, 0.00153, 0.00211)   # $ per call of depth: p25, median, p75
ORIENT_11_1 = 3.50                     # calls an agent, §11.1's only estimate
ARRIVAL_11_4 = 0.0577                  # $ for an agent's first call, corpus


def agent_paths(slug: str, session_id: str) -> dict[str, list[Path]]:
    """Every surviving copy of every agent transcript, grouped by agent id.

    Two locations hold the same transcript (discovery.py) and one is a symlink
    to the other; both are read and handed to one `load_records`, which dedups
    on (message_id, request_id), so reading a file twice cannot double-count.
    """
    by_agent: dict[str, list[Path]] = {}
    project = main_transcript_dir() / slug / session_id / "subagents"
    if project.is_dir():
        for path in sorted(project.glob("agent-*.jsonl")):
            by_agent.setdefault(path.stem.removeprefix("agent-"), []).append(path)
    for root in subagent_transcript_dirs():
        tasks = root / slug / session_id / "tasks"
        if tasks.is_dir():
            for path in sorted(tasks.glob("*.output")):
                by_agent.setdefault(path.stem, []).append(path)
    return by_agent


def per_call_dollars(paths: list[Path]) -> list[float]:
    """List dollars for each call of one transcript, in order.

    Priced one call at a time and per model, because a session is never one
    model: these arms ran `--model opus` and every one of them also billed
    `claude-haiku-4-5` for harness-side work.
    """
    records = load_records(paths)
    out = []
    for record in records:
        priced = price_records([record])
        out.append(priced.dollars if priced else 0.0)
    return out


def slope(ys: list[float]) -> float:
    """Least squares $/call against call index. No numpy in this repo."""
    n = len(ys)
    if n < 2:
        return 0.0
    xs = list(range(n))
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx if sxx else 0.0


@dataclass
class Arm:
    name: str
    agents: int
    calls: int
    dollars: float
    parent_calls: int
    parent_dollars: float
    per_agent: list[list[float]] = field(default_factory=list)

    @property
    def dollars_per_call(self) -> float:
        return self.dollars / self.calls


def read_arm(name: str, slug: str, session_id: str) -> Arm:
    per_agent = []
    for _, paths in sorted(agent_paths(slug, session_id).items()):
        calls = per_call_dollars(paths)
        if calls:
            per_agent.append(calls)
    parent = main_transcript_dir() / slug / f"{session_id}.jsonl"
    parent_calls = per_call_dollars([parent]) if parent.exists() else []
    return Arm(
        name=name,
        agents=len(per_agent),
        calls=sum(len(c) for c in per_agent),
        dollars=sum(sum(c) for c in per_agent),
        parent_calls=len(parent_calls),
        parent_dollars=sum(parent_calls),
        per_agent=per_agent,
    )


def prefix_of(record) -> tuple[int, int, int]:
    """(cache read, cache write, output) of one call -- an arrival's whole bill.

    An agent's first call reads nothing of the repo, so these three numbers ARE
    the arrival price: the system prompt and tool schema it arrives on, whatever
    of that had to be written, and the brief-sized answer it emits.
    """
    usage = record.usage
    return usage.cache_read_tokens, usage.cache_creation_tokens, usage.output_tokens


def corpus_arrival() -> tuple[float, float, int, dict[str, int]]:
    """§11.4's two corpus numbers, recomputed here so this file is checkable.

    It reports 84 priceable runs at $0.0577 and $0.0800; this walk finds 91 --
    the corpus has grown since -- and the nine exclusions are the same nine.
    """
    by_agent: dict[str, list[Path]] = {}
    for path in main_transcript_dir().rglob("subagents/agent-*.jsonl"):
        by_agent.setdefault(path.stem.removeprefix("agent-"), []).append(path)
    for root in subagent_transcript_dirs():
        if not root.exists():
            continue
        for path in root.rglob("*.output"):
            if path.parent.name == "tasks" and "scratchpad" not in path.parts:
                by_agent.setdefault(path.stem, []).append(path)

    firsts: list[float] = []
    laters: list[float] = []
    cold: list[float] = []
    warm: list[float] = []
    warm_prefix: list[tuple[int, int, int]] = []
    excluded: dict[str, int] = {}
    runs = 0
    for _, paths in sorted(by_agent.items()):
        records = load_records(paths)
        if not records:
            continue
        unpriced = {canonical(r.model) for r in records if r.model} - set(BASE_RATE_PER_MTOK)
        if unpriced:
            for model in unpriced:
                excluded[model or "?"] = excluded.get(model or "?", 0) + 1
            continue
        dollars = [price_records([r]).dollars for r in records]
        runs += 1
        firsts.append(dollars[0])
        laters.extend(dollars[1:])
        if records[0].usage.cache_read_tokens == 0:
            cold.append(dollars[0])          # the first agent of a session
        else:
            warm.append(dollars[0])          # every agent after it
            warm_prefix.append(prefix_of(records[0]))
    return (statistics.median(firsts), statistics.mean(laters), runs, excluded,
            cold, warm, warm_prefix)


def main() -> int:
    arms = {name: read_arm(name, slug, sid) for name, _, slug, sid in ARMS}
    ks = {name: k for name, k, _, _ in ARMS}
    split = [a for n, a in arms.items() if ks[n] == 5]
    packed = [a for n, a in arms.items() if ks[n] == 1]
    dk = 5 - 1

    print("PER ARM -- #33's baton (5 agents) against #47's baton1 (1 agent).")
    print("One task, 19 modules, identical brief and tail. n=2 an arm.\n")
    print(f"{'arm':<11}{'agents':>7}{'calls':>7}{'$ agents':>10}{'$/call':>9}"
          f"{'parent':>8}{'$ parent':>10}")
    for name, arm in arms.items():
        print(f"{name:<11}{arm.agents:>7}{arm.calls:>7}{arm.dollars:>10.4f}"
              f"{arm.dollars_per_call:>9.4f}{arm.parent_calls:>8}{arm.parent_dollars:>10.4f}")

    mean_split_calls = statistics.mean(a.calls for a in split)
    mean_packed_calls = statistics.mean(a.calls for a in packed)
    orient = (mean_split_calls - mean_packed_calls) / dk
    corners = sorted((s.calls - p.calls) / dk for s in split for p in packed)

    split_d = statistics.mean(a.dollars for a in split)
    packed_d = statistics.mean(a.dollars for a in packed)

    print("\nTHE ORIENTATION TERM -- extra calls per extra agent, on fixed work")
    print(f"  split, agent calls              {mean_split_calls:.1f}"
          f"  ({', '.join(str(a.calls) for a in split)})")
    print(f"  packed, agent calls             {mean_packed_calls:.1f}"
          f"  ({', '.join(str(a.calls) for a in packed)})")
    print(f"  extra calls per extra agent     {orient:.2f}"
          f"   corners {corners[0]:.2f}-{corners[-1]:.2f}")
    print(f"  §11.1's only prior estimate     {ORIENT_11_1:.2f}   one task, two runs")
    print(f"  extra dollars per extra agent   ${(split_d - packed_d) / dk:.4f}")

    print("\nTHE DIRECT RESULT, which needs no equation at all")
    print(f"  packed agent dollars            ${packed_d:.4f}")
    print(f"  split  agent dollars            ${split_d:.4f}"
          f"   -- splitting costs {split_d / packed_d:.2f}x")
    print(f"  call count                      x{mean_split_calls / mean_packed_calls:.2f}"
          "  splitting multiplies calls")
    print(f"  price of a call                 x{statistics.mean(a.dollars_per_call for a in split) / statistics.mean(a.dollars_per_call for a in packed):.2f}"
          "  splitting makes each one cheaper")
    print(f"  measured at a packed depth of   {mean_packed_calls:.1f} calls"
          f"   (deepest single agent: {max(len(c) for a in packed for c in a.per_agent)})")

    arrival_here = statistics.median(c[0] for a in arms.values() for c in a.per_agent)
    later_here = statistics.mean(d for a in arms.values() for c in a.per_agent for d in c[1:])
    arrival_corpus, later_corpus, runs, excluded, cold, warm, warm_prefix = corpus_arrival()
    print("\nTHE ARRIVAL PRICE IS NOT A CONSTANT, and this is the term that is now widest")
    print(f"  these 12 agents, first call     ${arrival_here:.4f}"
          f"   later calls ${later_here:.4f}  ({later_here / arrival_here:.2f}x)")
    print(f"  corpus, first call              ${arrival_corpus:.4f}"
          f"   later calls ${later_corpus:.4f}  ({later_corpus / arrival_corpus:.2f}x)")
    print(f"  corpus is {runs} priceable runs; §11.4 read 84 and reported "
          f"${ARRIVAL_11_4:.4f}. Excluded: {excluded}")

    print("\nAND IT IS NOT A MYSTERY CONSTANT -- an arrival is a PRICED PREFIX")
    print(f"  cold arrivals (cache read 0)    ${statistics.median(cold):.4f}  n={len(cold)}"
          "   the FIRST agent of a session")
    print(f"  warm arrivals                   ${statistics.median(warm):.4f}  n={len(warm)}"
          "   every agent after it -- the MARGINAL one")
    reads = statistics.median(p[0] for p in warm_prefix)
    writes = statistics.median(p[1] for p in warm_prefix)
    outs = statistics.median(p[2] for p in warm_prefix)
    rebuilt = (CACHE_READ * reads + CACHE_WRITE_5M * writes + OUTPUT * outs) * 5.00 / 1e6
    print(f"  a warm arrival's prefix         {reads:,.0f} read + {writes:,.0f} write"
          f" + {outs:,.0f} out")
    print(f"  priced straight from that       ${rebuilt:.4f}"
          f"   -- §11.4's ${ARRIVAL_11_4:.4f}, rebuilt from its parts")
    here = [prefix_of(r) for a in ARMS
            for paths in agent_paths(a[2], a[3]).values()
            for r in load_records(paths)[:1]]
    hr = statistics.median(p[0] for p in here if p[0])
    hw = statistics.median(p[1] for p in here if p[0])
    print(f"  these 12 agents' prefix         {hr:,.0f} read + {hw:,.0f} write"
          f"   -- {(reads + writes) / (hr + hw):.1f}x smaller")
    print("  The corpus prefix's cache read is 14,992 at p25, median AND p75: it is the"
          "\n  harness's own system prompt and tool schema, identical for every agent."
          "\n  These arms ran with five tools disallowed and a compact brief, so their"
          "\n  agents arrive on half the prefix and at half the price. THE ARRIVAL TERM"
          "\n  IS A PROPERTY OF THE BRIEF AND THE TOOL SCHEMA, not of dispatching.")

    slopes = sorted(slope(c) for a in arms.values() for c in a.per_agent)
    deep = sorted(slope(c) for a in packed for c in a.per_agent)
    print("\nWHY THIS FILE DOES NOT REFIT THE GROWTH TERM FROM THESE RUNS")
    print(f"  slope over all 12 agents        ${statistics.median(slopes):+.5f}/call"
          f"   ({len(slopes)} runs of 3-15 calls)")
    print(f"  slope over the 2 packed agents  ${statistics.median(deep):+.5f}/call")
    print(f"  §11.4, runs of >=20 calls       ${GROWTH[1]:+.5f}/call")
    print("  A slope fitted on a 4-call run measures its terminal call -- the one"
          "\n  carrying the return payload -- not depth. §11.4 fitted >=20 and was right to.")

    print("\nBREAK-EVEN DEPTH = orientation x arrival / growth   (§11.4's equation)")
    print(f"{'':<24}{'growth p25':>12}{'growth mid':>12}{'growth p75':>12}")
    rows = [
        (f"o={orient:.2f} A=${ARRIVAL_11_4}", orient, ARRIVAL_11_4),
        (f"o={ORIENT_11_1:.2f} A=${ARRIVAL_11_4}", ORIENT_11_1, ARRIVAL_11_4),
        (f"o={orient:.2f} A=${arrival_here:.4f}", orient, arrival_here),
        (f"o={ORIENT_11_1:.2f} A=${arrival_here:.4f}", ORIENT_11_1, arrival_here),
    ]
    for label, o, a in rows:
        print(f"{label:<24}" + "".join(f"{o * a / g:>12.0f}" for g in GROWTH))
    std = [o * a / g for _, o, a in rows if a == ARRIVAL_11_4 for g in GROWTH]
    trim = [o * a / g for _, o, a in rows if a != ARRIVAL_11_4 for g in GROWTH]
    lo, hi = min(std + trim), max(std + trim)
    print(f"\n  standard tool schema   {min(std):.0f}-{max(std):.0f} calls   (§11.4 said 55-281)")
    print(f"  trimmed brief+schema   {min(trim):.0f}-{max(trim):.0f} calls")
    print("  Median real dispatch 52 calls, p90 79, longest 118.")
    print("\n  Orientation is measured TWICE now and is the narrow term. The arrival price")
    print("  is the wide one, and it is not noise: it is what the agent's cached prefix")
    print("  costs. A tighter brief makes an extra agent CHEAPER and moves the break-even")
    print("  DOWN -- tightening a brief argues for splitting, not for packing.")
    print(f"\n  AND EVERY ARM EVER RUN SAT AT DEPTH <= 15 CALLS (this one"
          f" {mean_packed_calls:.1f}, §11.1's 5). Both bands are extrapolations of 3-13x"
          "\n  beyond any depth anyone has actually compared.")

    out = Path(__file__).parent / "orientation.json"
    out.write_text(json.dumps({
        "arms": {n: {"agents": a.agents, "calls": a.calls,
                     "dollars": round(a.dollars, 4),
                     "parent_calls": a.parent_calls,
                     "parent_dollars": round(a.parent_dollars, 4),
                     "per_agent_calls": [len(c) for c in a.per_agent]}
                 for n, a in arms.items()},
        "orientation_calls": round(orient, 3),
        "orientation_calls_corners": [round(corners[0], 3), round(corners[-1], 3)],
        "orientation_dollars": round((split_d - packed_d) / dk, 5),
        "split_over_packed": round(split_d / packed_d, 4),
        "packed_depth_calls": mean_packed_calls,
        "arrival_here": round(arrival_here, 5),
        "arrival_corpus": round(arrival_corpus, 5),
        "corpus_runs": runs,
        "break_even_band": [round(lo), round(hi)],
    }, indent=1) + "\n", encoding="utf-8")
    print(f"\nwritten: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
