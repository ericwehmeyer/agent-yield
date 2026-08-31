#!/usr/bin/env python
"""Join every resume-probe injection to the transcripts carrying its receipt.

`agent-yield resume --status` reports the first receipt inside the window and
names one session. This reports *every* transcript inside the window, so a
one-to-many join stays visible instead of collapsing to an arbitrary winner
(#195), and prints whether the payload carried `agent_type` (#123).

    python scripts/receipt-join.py [--probe PATH] [--transcripts DIR]
                                   [--window SECONDS]

Exit 1 when any injection has no receipt in any transcript.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sys

# The preamble line every injection carries; resume.py owns the string.
MARKER = "The handoff below was written by a session that has already ended"

# Claude Code encodes a project directory by replacing separators with dashes.
def transcript_dir(cwd: pathlib.Path) -> pathlib.Path:
    slug = str(cwd.resolve()).replace(":", "-").replace("\\", "-").replace("/", "-")
    return pathlib.Path.home() / ".claude" / "projects" / slug


def parse(ts: str) -> dt.datetime:
    return dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))


def receipts(directory: pathlib.Path) -> list[tuple[dt.datetime, str]]:
    found = []
    for path in directory.glob("*.jsonl"):
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if MARKER not in line:
                continue
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if record.get("type") == "attachment" and record.get("timestamp"):
                found.append((parse(record["timestamp"]), path.stem))
    return found


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--probe", type=pathlib.Path,
                    default=pathlib.Path(".agent-yield/resume-probe.jsonl"))
    ap.add_argument("--transcripts", type=pathlib.Path, default=None)
    ap.add_argument("--window", type=float, default=120.0,
                    help="seconds after the probe entry a receipt may land")
    ap.add_argument("--tz", type=float, default=-4.0,
                    help="hours from UTC to report in; the probe stores UTC (#118)")
    args = ap.parse_args(argv)

    directory = args.transcripts or transcript_dir(pathlib.Path.cwd())
    if not directory.is_dir():
        print(f"no transcript directory at {directory}", file=sys.stderr)
        return 2
    if not args.probe.is_file():
        print(f"no probe log at {args.probe}", file=sys.stderr)
        return 2

    local = dt.timezone(dt.timedelta(hours=args.tz))
    seen = receipts(directory)
    rows = [json.loads(line) for line in
            args.probe.read_text(encoding="utf-8").splitlines() if line.strip()]

    missing = injected = 0
    for row in rows:
        if row.get("decision") != "injected":
            continue
        injected += 1
        at = parse(row["observed"])
        hits = sorted({s for t, s in seen
                       if 0 <= (t - at).total_seconds() <= args.window})
        missing += not hits
        print(f"{at.astimezone(local):%Y-%m-%d %H:%M:%S}  "
              f"{row.get('injected_chars', 0):>6,}c  "
              f"agent_type={'yes' if 'agent_type' in (row.get('keys') or []) else ' no'}  "
              f"{len(hits)} receipt(s): {', '.join(s[:8] for s in hits) or 'NONE'}")

    print(f"\n{injected - missing} of {injected} injections have a receipt; "
          f"{missing} reach no transcript.")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
