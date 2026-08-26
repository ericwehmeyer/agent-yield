"""Total tokens for one arm of #33, end to end: parent plus every agent it started.

Deliberately a script and not a subcommand. #36 is the standing warning against
shipping a subcommand for a shape nobody has validated yet, and this shape has
been run exactly zero times.

Two things it does that a naive sum does not:

- **Subagent transcripts are volatile.** `discovery` says so and the corpus
  proves it -- 249 of 352 were already empty on one machine. This is run after
  every turn, not once at the end, and each snapshot is written to disk, so a
  file emptied between turn 3 and turn 6 is still counted from the turn-3
  snapshot. `--snapshot-dir` re-reads the earlier snapshots and keeps the
  MAXIMUM total seen for each agent file.
- **A call is identified by (message_id, request_id)**, via `CallRecord`, so a
  snapshot re-reading the same transcript cannot double-count it.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from agent_yield.discovery import main_transcript_dir, subagent_transcript_dirs
from agent_yield.ingest import load_records
from agent_yield.session import project_slug
from agent_yield.usage import Usage


def arm_paths(session_id: str, cwd: Path) -> tuple[Path | None, list[Path]]:
    slug = project_slug(cwd)
    main = main_transcript_dir() / slug / f"{session_id}.jsonl"
    agents: list[Path] = []
    for root in subagent_transcript_dirs():
        tasks = root / slug / session_id / "tasks"
        if tasks.is_dir():
            agents.extend(sorted(p for p in tasks.iterdir() if p.suffix == ".output"))
    return (main if main.exists() else None), agents


def totals(paths: list[Path]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for path in paths:
        records = load_records([path])
        usage = sum((r.usage for r in records), start=Usage())
        out[path.name] = {
            "path": str(path),
            "calls": len(records),
            "tokens": usage.total,
            "output": usage.output_tokens,
            "per_call": [r.usage.total for r in records],
        }
    return out


def merge(snapshots: list[dict]) -> dict:
    """Keep the largest reading of every file. A transcript only ever grows,
    until it is emptied -- and an emptied file must not erase what was already
    measured."""
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
    return {
        "session_id": session_id,
        "main": totals([main]) if main else {},
        "agents": totals(agents),
    }


def summarise(best: dict) -> dict:
    main = [e for e in best.values() if e["kind"] == "main"]
    agents = [e for e in best.values() if e["kind"] == "agents"]
    return {
        "parent_calls": sum(e["calls"] for e in main),
        "parent_tokens": sum(e["tokens"] for e in main),
        "agent_count": len(agents),
        "agent_calls": sum(e["calls"] for e in agents),
        "agent_tokens": sum(e["tokens"] for e in agents),
        "total_tokens": sum(e["tokens"] for e in best.values()),
        "total_calls": sum(e["calls"] for e in best.values()),
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

    best = merge(snapshots)
    print(json.dumps(summarise(best)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
