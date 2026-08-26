"""#47's bar, scored in the units of the FINDING rather than the denominator.

#33 pre-registered its VOID condition on CLAIMS COUNTED -- the denominator --
when the output of the task is MISMATCHES. A baton arm that returned a full set
of claim counts and zero defects would have passed. That is the fourth instance
of the same failure in this repo (#26's loader, #32's detector, #44's scorer):
the test written to the shape of the work rather than to the point of it.

So this scorer counts DEFECTS FOUND, and it checks two of them by identity, not
by count. Both were verified by hand after #33 ran and are real; both were
reported by the reader arm in both replicates and missed by the five-agent baton
arm in both. They are the only defects here with ground truth attached.

Zero mismatches is a RESULT, not a VOID. VOID is reserved for an arm that did
not do the task -- broken coverage, or a parent that broke its own method.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MODULES = [
    "agents.py", "boundary.py", "cli.py", "discovery.py", "gate.py",
    "handoff.py", "ingest.py", "interventions.py", "modes.py", "outcomes.py",
    "predict.py", "records.py", "report.py", "report_html.py", "resume.py",
    "session.py", "statusline.py", "thresholds.py", "usage.py",
]


def parse_result(out_dir: Path) -> dict:
    """The live run writes `turn-1.json`; the committed snapshot keeps only the
    arm's own answer as `turn-1-result.txt`. Score either, so this bar can be
    re-run against #33's archived arms without their volatile transcripts."""
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


def found(data: dict, truth: dict) -> list[str]:
    """Which ground-truth defects does this arm's output report?"""
    hits = []
    for defect in truth["defects"]:
        pattern = re.compile(defect["match"], re.I)
        for module in data.get("modules", []):
            if module.get("module") != defect["module"]:
                continue
            for mismatch in module.get("mismatches") or []:
                blob = f"{mismatch.get('claim', '')} {mismatch.get('why', '')}"
                if pattern.search(blob):
                    hits.append(defect["id"])
                    break
            break
    return hits


def score(name: str, out_dir: Path, truth: dict) -> dict:
    data = parse_result(out_dir)
    modules = data.get("modules", [])
    seen = [m.get("module") for m in modules]
    hits = found(data, truth)
    return {
        "arm": name,
        "mismatches": sum(len(m.get("mismatches") or []) for m in modules),
        "claims": sum(int(m.get("claims") or 0) for m in modules),
        "ground_truth_found": hits,
        "ground_truth_n": len(hits),
        "coverage_ok": sorted(seen) == sorted(MODULES),
        "missing": [m for m in MODULES if m not in seen],
        "per_module": {m.get("module"): len(m.get("mismatches") or []) for m in modules
                       if m.get("mismatches")},
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+", help="arm=dir pairs")
    ap.add_argument("--truth", type=Path, default=HERE / "ground-truth.json")
    args = ap.parse_args(argv)

    truth = json.loads(args.truth.read_text(encoding="utf-8"))
    for spec in args.runs:
        name, _, path = spec.partition("=")
        print(json.dumps(score(name, Path(path), truth)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
