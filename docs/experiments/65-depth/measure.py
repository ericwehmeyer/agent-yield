"""One arm of #65, in the two units the ticket names: LIST DOLLARS and DEPTH.

Not raw tokens. #55 measured the same runs fitting `calls^1.38` in tokens and
`calls^1.11` in dollars, so a token-scored packing experiment measures the
cache-read rate rather than the packing. Tokens are still printed, because a
number that is not printed cannot be checked, but the bar is on dollars.

DEPTH is the other output and it is the one #65 exists to protect: "a 'depth 50'
experiment whose packed agent finished in 20 calls has not been run." So this
reports `packed_depth` -- the call count of the longest single agent -- and the
whole per-agent distribution beside it.

Subagent transcripts are volatile (`discovery`), so this is snapshotted and every
snapshot is merged by keeping the largest reading of each file. A call is
identified by `(message_id, request_id)` via `CallRecord`, so re-reading a
transcript cannot double-count it, and a file reachable both directly and through
its `tasks/*.output` symlink is counted once because paths are resolved first.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from agent_yield.discovery import main_transcript_dir, subagent_transcript_dirs
from agent_yield.ingest import load_records
from agent_yield.pricing import price_records
from agent_yield.session import project_slug
from agent_yield.usage import Usage


def arm_paths(session_id: str, cwd: Path) -> tuple[Path | None, list[Path]]:
    slug = project_slug(cwd)
    main = main_transcript_dir() / slug / f"{session_id}.jsonl"
    agents: dict[str, Path] = {}
    roots = [root / slug / session_id / "tasks" for root in subagent_transcript_dirs()]
    roots.append(main_transcript_dir() / slug / session_id / "subagents")
    for tasks in roots:
        if not tasks.is_dir():
            continue
        for path in sorted(tasks.iterdir()):
            if path.suffix not in (".output", ".jsonl"):
                continue
            agents.setdefault(str(path.resolve()), path)
    return (main if main.exists() else None), list(agents.values())


def totals(paths: list[Path]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for path in paths:
        records = load_records([path])
        usage = sum((r.usage for r in records), start=Usage())
        priced = price_records(records)
        out[str(path.resolve())] = {
            "path": str(path),
            "calls": len(records),
            "tokens": usage.total,
            "output": usage.output_tokens,
            "dollars": round(priced.dollars, 6) if priced else None,
            "unpriced_models": list(priced.unpriced_models) if priced else [],
        }
    return out


def merge(snapshots: list[dict]) -> dict:
    """Keep the largest reading of every file: a transcript only grows, until it
    is emptied, and an emptied file must not erase what was already measured."""
    best: dict[str, dict] = {}
    for snap in snapshots:
        for kind in ("main", "agents"):
            for name, entry in snap.get(kind, {}).items():
                key = f"{kind}/{name}"
                if entry["tokens"] >= best.get(key, {}).get("tokens", -1):
                    best[key] = {**entry, "kind": kind}
    return best


def measure(session_id: str, cwd: Path) -> dict:
    main, agents = arm_paths(session_id, cwd)
    return {"session_id": session_id,
            "main": totals([main]) if main else {},
            "agents": totals(agents)}


def summarise(best: dict) -> dict:
    main = [e for e in best.values() if e["kind"] == "main"]
    agents = [e for e in best.values() if e["kind"] == "agents"]
    agent_calls = sorted((e["calls"] for e in agents), reverse=True)
    unpriced = sorted({m for e in best.values() for m in e.get("unpriced_models") or []})

    def dollars(entries):
        vals = [e["dollars"] for e in entries if e["dollars"] is not None]
        return round(sum(vals), 6)

    return {
        "parent_calls": sum(e["calls"] for e in main),
        "parent_tokens": sum(e["tokens"] for e in main),
        "parent_dollars": dollars(main),
        "agent_count": len(agents),
        "agent_calls": sum(e["calls"] for e in agents),
        "agent_calls_each": agent_calls,
        "packed_depth": agent_calls[0] if agent_calls else 0,
        "agent_tokens": sum(e["tokens"] for e in agents),
        "agent_dollars": dollars(agents),
        "total_calls": sum(e["calls"] for e in best.values()),
        "total_tokens": sum(e["tokens"] for e in best.values()),
        "total_dollars": dollars(best.values()),
        "unpriced_models": unpriced,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("session_id")
    ap.add_argument("--cwd", type=Path, default=Path.cwd())
    ap.add_argument("--snapshot-dir", type=Path)
    ap.add_argument("--label", default="")
    args = ap.parse_args(argv)

    snapshot = measure(args.session_id, args.cwd)
    snapshots = [snapshot]
    if args.snapshot_dir:
        args.snapshot_dir.mkdir(parents=True, exist_ok=True)
        existing = sorted(args.snapshot_dir.glob("snap-*.json"))
        snapshots = [json.loads(p.read_text(encoding="utf-8")) for p in existing] + snapshots
        dest = args.snapshot_dir / f"snap-{len(existing):02d}{('-' + args.label) if args.label else ''}.json"
        dest.write_text(json.dumps(snapshot, indent=1), encoding="utf-8")

    print(json.dumps(summarise(merge(snapshots))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
