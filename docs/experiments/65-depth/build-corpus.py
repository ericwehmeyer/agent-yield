"""Build #65's corpus: the tree at a pinned sha, with fourteen docstring defects seeded.

Pinned because #47 learned the hard way that an experiment run at HEAD scores an
arm that finds nothing identically to one that finds everything, the moment the
defects it is looking for are fixed. Here the defects are seeded rather than
found, so the pin is what makes the corpus REPRODUCIBLE rather than what makes it
falsifiable -- `ground-truth.json` names the sha and every substitution, and this
script is the only thing that writes the corpus.

Seeds are docstring-only BY CONSTRUCTION and the check is enforced here, not
hoped for: every substitution must land inside the module docstring (the string
literal before the first import), and the full suite must still pass on the
result. A seed that broke a test would let the per-slice test command find the
defect, and the depth this experiment is measuring would collapse into a grep.

    build-corpus.py <dest>            # build, verify, refuse on any mismatch
    build-corpus.py <dest> --no-test  # skip the suite (pilot only)
"""
from __future__ import annotations

import argparse
import ast
import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
TRUTH = json.loads((HERE / "ground-truth.json").read_text(encoding="utf-8"))


def export(sha: str, dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    archive = subprocess.run(["git", "archive", sha], cwd=REPO, check=True,
                             stdout=subprocess.PIPE).stdout
    subprocess.run(["tar", "-x", "-C", str(dest)], input=archive, check=True)


def seed(dest: Path) -> list[str]:
    """Apply every substitution, refusing anything ambiguous or outside a docstring."""
    applied = []
    for s in TRUTH["seeds"]:
        path = dest / "src" / "agent_yield" / s["module"]
        text = path.read_text(encoding="utf-8")
        hits = text.count(s["old"])
        if hits != 1:
            raise SystemExit(f"{s['id']}: `old` appears {hits} times in {s['module']}, need exactly 1")
        doc = ast.get_docstring(ast.parse(text))
        if doc is None or s["old"] not in doc:
            raise SystemExit(f"{s['id']}: `old` is not inside {s['module']}'s module docstring")
        path.write_text(text.replace(s["old"], s["new"]), encoding="utf-8")
        after = ast.get_docstring(ast.parse(path.read_text(encoding="utf-8")))
        if after is None or s["new"] not in after:
            raise SystemExit(f"{s['id']}: substitution left {s['module']}'s docstring wrong")
        applied.append(s["id"])
    return applied


def wire_venv(dest: Path) -> None:
    """The slice test command runs the repo's interpreter against the CORPUS source.

    The venv installs `agent_yield` editable against the repo's own `src`, so a
    bare `pytest` in the corpus would import the tree the experiment is not
    auditing. `PYTHONPATH=src` precedes site-packages and fixes that; the symlink
    is only so the command in the brief is a short literal path.
    """
    (dest / ".venv").symlink_to(REPO / ".venv")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("dest", type=Path)
    ap.add_argument("--no-test", action="store_true")
    args = ap.parse_args()

    export(TRUTH["pinned_src"], args.dest)
    applied = seed(args.dest)
    wire_venv(args.dest)

    if not args.no_test:
        proc = subprocess.run(
            [".venv/bin/python", "-m", "pytest", "-q"], cwd=args.dest,
            env={**__import__("os").environ, "PYTHONPATH": "src"},
            capture_output=True, text=True)
        tail = (proc.stdout or proc.stderr).strip().splitlines()[-1:]
        if proc.returncode != 0:
            print("\n".join((proc.stdout or "").splitlines()[-25:]), file=sys.stderr)
            raise SystemExit("the suite does not pass on the seeded corpus -- a seed is not docstring-only")
        print(f"suite on seeded corpus: {tail[0] if tail else 'ok'}")

    print(json.dumps({"dest": str(args.dest), "sha": TRUTH["pinned_src"], "seeded": applied}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
