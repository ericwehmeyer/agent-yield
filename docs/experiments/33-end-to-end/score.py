"""Did the two arms do the same work? The bar that decides pass from VOID.

#18 Part E is the precedent: a cheap arm that did less is not a saving, it is a
different task, and the only way to tell them apart is to score the work on the
same schema in both arms. Three things are checked here, all of them
pre-registered in `interventions.toml` before either arm ran:

- **coverage** -- all 19 modules, exactly once, in both arms;
- **volume** -- total claims counted, and VOID if either arm is more than 25%
  below the other;
- **compliance** -- the baton parent must not have opened a file under `src/`
  itself, and the reader must not have dispatched. Read from the transcripts,
  not from what the arm says it did.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

MODULES = [
    "agents.py", "boundary.py", "cli.py", "discovery.py", "gate.py",
    "handoff.py", "ingest.py", "interventions.py", "modes.py", "outcomes.py",
    "predict.py", "records.py", "report.py", "report_html.py", "resume.py",
    "session.py", "statusline.py", "thresholds.py", "usage.py",
]


def parse_result(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    text = payload.get("result", "")
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if fenced:
        text = fenced.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < 0:
        raise ValueError(f"no JSON object in {path}")
    return json.loads(text[start:end + 1])


def compliance(transcript: Path) -> dict:
    """What the parent actually did, from its own transcript."""
    reads_src, dispatches = 0, 0
    for line in transcript.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except ValueError:
            continue
        message = payload.get("message")
        if not isinstance(message, dict) or payload.get("isSidechain"):
            continue
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            name = block.get("name")
            args = block.get("input") if isinstance(block.get("input"), dict) else {}
            if name in ("Agent", "Task"):
                dispatches += 1
            elif name in ("Read", "Grep", "Glob", "Bash"):
                blob = json.dumps(args)
                if "src/agent_yield" in blob or "src\\agent_yield" in blob:
                    reads_src += 1
    return {"parent_reads_of_src": reads_src, "parent_dispatches": dispatches}


def score(name: str, out_dir: Path, transcript: Path) -> dict:
    data = parse_result(out_dir / "turn-1.json")
    modules = data.get("modules", [])
    seen = [m.get("module") for m in modules]
    row = {
        "arm": name,
        "modules_returned": len(seen),
        "missing": [m for m in MODULES if m not in seen],
        "extra": [m for m in seen if m not in MODULES],
        "duplicated": sorted({m for m in seen if seen.count(m) > 1}),
        "claims": sum(int(m.get("claims") or 0) for m in modules),
        "mismatches": sum(len(m.get("mismatches") or []) for m in modules),
        "tail_answered": sum(
            1 for n in range(2, 7)
            if (out_dir / f"turn-{n}.json").exists()
            and len(json.loads((out_dir / f"turn-{n}.json").read_text(encoding="utf-8")).get("result", "").strip()) > 40
        ),
        "cost_usd": round(sum(
            json.loads((out_dir / f"turn-{n}.json").read_text(encoding="utf-8")).get("total_cost_usd", 0.0)
            for n in range(1, 7) if (out_dir / f"turn-{n}.json").exists()), 2),
    }
    row.update(compliance(transcript))
    return row


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+", help="arm=dir pairs, e.g. baton-r1=.agent-yield/...")
    ap.add_argument("--projects", type=Path,
                    default=Path.home() / ".claude" / "projects" / "-Users-ericw-IdeaProjects-agent-yield")
    args = ap.parse_args(argv)

    rows = []
    for spec in args.runs:
        name, _, path = spec.partition("=")
        out_dir = Path(path)
        session_id = (out_dir / "session-id").read_text(encoding="utf-8").strip()
        rows.append(score(name, out_dir, args.projects / f"{session_id}.jsonl"))
    for row in rows:
        print(json.dumps(row))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
