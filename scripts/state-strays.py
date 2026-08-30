#!/usr/bin/env python
"""Find the `.agent-yield/` stores that are not the project root's, and say what is in them.

Every state path used to resolve against the process's working directory, so
running the CLI or the status line from a subdirectory made a second store
there (#154). `.gitignore` matches `.agent-yield/` at any depth, so none of
them ever appeared in `git status`, and each machine has to look at its own
checkout because no other box can see it.

    python scripts/state-strays.py              # report, and change nothing
    python scripts/state-strays.py --merge      # fold stray allowance rows in

Exit 0 when the tree is clean, 1 when strays exist, 2 when it could not run.

`--merge` is deliberately not the default. The rows are real measurements and
the root log is calibration input: #69 is the standing case of a tool writing
to a log as a side effect and putting invented numbers into a real one. So the
merge is a thing an operator asks for, it prints every row it moves, and it
leaves the stray files in place for the operator to delete once satisfied.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agent_yield.allowance import SNAPSHOT_PATH, Snapshot, load  # noqa: E402
from agent_yield.state import project_root, stray_dirs, stray_files  # noqa: E402


def merge_allowance(root: Path, apply: bool) -> tuple[list[tuple[Path, Snapshot]], int]:
    """Stray allowance rows the root log does not already hold.

    Deduplicated by timestamp, which is what identifies a snapshot: the same
    render appended to two stores is one observation, not two.
    """
    target = root / SNAPSHOT_PATH
    held = {s.timestamp for s in load(target)}
    incoming: list[tuple[Path, Snapshot]] = []
    for path, _rows in stray_files(root):
        if path.name != SNAPSHOT_PATH.name:
            continue
        for snapshot in load(path):
            if snapshot.timestamp in held:
                continue
            held.add(snapshot.timestamp)
            incoming.append((path, snapshot))
    if apply and incoming:
        import dataclasses
        import json

        merged = sorted(load(target) + [s for _p, s in incoming],
                        key=lambda s: s.timestamp)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            "".join(json.dumps(dataclasses.asdict(s), sort_keys=True) + "\n"
                    for s in merged),
            encoding="utf-8", newline="\n")
        return incoming, len(merged)
    return incoming, len(held)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", help="checkout to scan; default is the project root")
    ap.add_argument("--merge", action="store_true",
                    help="fold stray allowance rows into the root log")
    args = ap.parse_args(argv)

    root = Path(args.root).resolve() if args.root else project_root()
    if not root.exists():
        print(f"no such root: {root}", file=sys.stderr)
        return 2

    print(f"root: {root}")
    rooted = root / ".agent-yield"
    print(f"      {'exists' if rooted.exists() else 'ABSENT'}  {rooted}")
    print()

    directories = stray_dirs(root)
    if not directories:
        print("no stray state directories")
        return 0

    files = stray_files(root)
    print(f"{len(directories)} stray state director"
          f"{'y' if len(directories) == 1 else 'ies'}, "
          f"{len(files)} file{'' if len(files) == 1 else 's'}:")
    for directory in directories:
        print(f"  {directory.relative_to(root)}")
        for path, rows in files:
            if path.parent == directory:
                print(f"      {rows:6} rows  {path.name}")

    incoming, total = merge_allowance(root, args.merge)
    print()
    if not incoming:
        print("no allowance rows the root log does not already hold")
    elif args.merge:
        print(f"merged {len(incoming)} rows into {rooted / 'allowance.jsonl'}, "
              f"now {total} rows. Provenance:")
        for path, snapshot in incoming:
            print(f"  {snapshot.timestamp}  from {path.relative_to(root)}")
        print("\nThe stray files are left in place. Delete them once you have "
              "checked the merge.")
    else:
        print(f"{len(incoming)} allowance rows are ONLY in the strays:")
        for path, snapshot in incoming:
            print(f"  {snapshot.timestamp}  five_hour={snapshot.five_hour} "
                  f"seven_day={snapshot.seven_day}  {path.relative_to(root)}")
        print("\n--merge folds them into the root log. It is not the default: "
              "these are real\nmeasurements going into calibration input, so "
              "moving them is an operator's call.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
