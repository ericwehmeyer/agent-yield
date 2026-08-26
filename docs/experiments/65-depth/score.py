"""#65's bars, all of them pre-registered, none of them read off what the arm says.

Three questions, in the order they can void the run:

- **COMPLIANCE** -- read from the transcripts, not from the arm's prose. The
  parent must not have opened anything under `src/` or `tests/` itself, must not
  have run a test command itself, and must have dispatched EXACTLY the number of
  agents its own METHOD paragraph fixes: one for `packed`, 23 for `split`. An
  arm that broke its own packing is not a cheaper arm, it is a different one.
  Any `Edit`/`Write` anywhere is also flagged, because the full-schema arm has
  those tools and the corpus is supposed to leave the run unchanged.
- **COVERAGE** -- all 23 slices, exactly once. A slice missing or duplicated is
  VOID, per the ticket.
- **DEFECTS** -- which of the 14 SEEDED defects the arm reports, matched by
  module and pattern from `ground-truth.json`. This is the bar. #33 pre-registered
  its bar on CLAIMS COUNTED -- the denominator -- and would have passed an arm
  that found nothing; #47 fixed that and this keeps the fix. Total mismatch count
  is reported beside it as a descriptive number and is NOT a bar.

Zero seeds found is a RESULT, not a VOID.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from measure import arm_paths  # noqa: E402

HERE = Path(__file__).resolve().parent
SLICES = [
    "agents.py", "allowance.py", "attribution.py", "boundary.py", "cli.py",
    "discovery.py", "gate.py", "handoff.py", "hookio.py", "ingest.py",
    "interventions.py", "modes.py", "outcomes.py", "predict.py", "pricing.py",
    "records.py", "report.py", "report_html.py", "resume.py", "session.py",
    "statusline.py", "thresholds.py", "usage.py",
]
EXPECTED_AGENTS = {"packed": 1, "split": 23}
READ_TOOLS = {"Read", "Grep", "Glob", "NotebookRead"}
WRITE_TOOLS = {"Edit", "Write", "NotebookEdit", "MultiEdit"}
DISPATCH_TOOLS = {"Agent", "Task"}
SOURCE_PATH = re.compile(r"(^|[\s\"'/])(src/|tests/)")
TEST_CMD = re.compile(r"pytest")


def parse_result(out_dir: Path) -> dict:
    """The live run writes `turn-1.json`; the committed snapshot keeps only the
    arm's own answer as `turn-1-result.txt`, so a bar can be re-run without the
    volatile transcripts."""
    path = out_dir / "turn-1.json"
    if path.exists():
        text = json.loads(path.read_text(encoding="utf-8")).get("result", "")
    else:
        path = out_dir / "turn-1-result.txt"
        text = path.read_text(encoding="utf-8")
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if fenced:
        text = fenced.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < 0:
        raise ValueError(f"no JSON object in {path}")
    return json.loads(text[start:end + 1])


def tool_uses(transcript: Path, sidechain: bool):
    for line in transcript.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except ValueError:
            continue
        if bool(payload.get("isSidechain")) is not sidechain:
            continue
        message = payload.get("message")
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                yield block.get("name"), block.get("input") or {}


def sub_dispatched(agents: list[Path]) -> int:
    """Agents an AGENT started. The pilot's packed agent spawned a child to run
    the test commands, which un-packs the arm the METHOD paragraph fixed. The
    harness records it beside the transcript, in `agent-<id>.meta.json`, as a
    `parentAgentId` and a `spawnDepth` above 1."""
    depth = 0
    for path in agents:
        meta = path.resolve().with_suffix("").with_suffix(".meta.json")
        if not meta.exists():
            meta = path.resolve().parent / (path.resolve().stem + ".meta.json")
        if not meta.exists():
            continue
        try:
            payload = json.loads(meta.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if payload.get("parentAgentId") or (payload.get("spawnDepth") or 1) > 1:
            depth += 1
    return depth


def compliance(arm: str, session_id: str, cwd: Path) -> dict:
    main, agents = arm_paths(session_id, cwd)
    reads_source = dispatches = own_test_runs = writes = 0
    for name, args in tool_uses(main, sidechain=False) if main else []:
        blob = json.dumps(args)
        if name in DISPATCH_TOOLS:
            dispatches += 1
        elif name in READ_TOOLS and SOURCE_PATH.search(blob):
            reads_source += 1
        elif name == "Bash" and TEST_CMD.search(blob):
            own_test_runs += 1
    for path in ([main] if main else []) + agents:
        for side in (False, True):
            writes += sum(1 for tool, _ in tool_uses(path, sidechain=side)
                          if tool in WRITE_TOOLS)
    expected = EXPECTED_AGENTS[arm]
    sub = sub_dispatched(agents)
    return {
        "parent_reads_source": reads_source,
        "parent_test_runs": own_test_runs,
        "dispatches": dispatches,
        "dispatches_expected": expected,
        "sub_dispatches": sub,
        "writes_anywhere": writes,
        "ok": (reads_source == 0 and own_test_runs == 0 and dispatches == expected
               and writes == 0 and sub == 0),
    }


def found(data: dict, truth: dict) -> list[str]:
    hits = []
    for seed in truth["seeds"]:
        pattern = re.compile(seed["match"], re.I)
        for entry in data.get("slices", []):
            if entry.get("module") != seed["module"]:
                continue
            for mismatch in entry.get("mismatches") or []:
                blob = f"{mismatch.get('claim', '')} {mismatch.get('why', '')}"
                if pattern.search(blob):
                    hits.append(seed["id"])
                    break
            break
    return hits


def score(name: str, out_dir: Path, truth: dict, cwd: Path | None) -> dict:
    data = parse_result(out_dir)
    entries = data.get("slices", [])
    seen = [e.get("module") for e in entries]
    hits = found(data, truth)
    result = {
        "run": name,
        "seeds_found": hits,
        "seeds_n": len(hits),
        "seeds_total": len(truth["seeds"]),
        "mismatches": sum(len(e.get("mismatches") or []) for e in entries),
        "claims": sum(int(e.get("claims") or 0) for e in entries),
        "tests_passed": sum(int(e.get("tests_passed") or 0) for e in entries),
        "coverage_ok": sorted(seen) == sorted(SLICES),
        "missing": [s for s in SLICES if s not in seen],
        "duplicated": sorted({s for s in seen if seen.count(s) > 1}),
    }
    sid_file = out_dir / "session-id"
    if cwd and sid_file.exists():
        arm = name.split("-")[0]
        result["compliance"] = compliance(arm, sid_file.read_text().strip(), cwd)
    result["void"] = not result["coverage_ok"] or not result.get("compliance", {"ok": True})["ok"]
    return result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+", help="name=dir pairs; name must start with the arm")
    ap.add_argument("--truth", type=Path, default=HERE / "ground-truth.json")
    ap.add_argument("--cwd", type=Path, help="the corpus the arm ran in, for compliance")
    args = ap.parse_args(argv)

    truth = json.loads(args.truth.read_text(encoding="utf-8"))
    for spec in args.runs:
        name, _, path = spec.partition("=")
        print(json.dumps(score(name, Path(path), truth, args.cwd)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
