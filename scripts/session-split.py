#!/usr/bin/env python
"""Split one session's token bill across its segments, deduped by request.

Why this exists as a script rather than a one-off pipeline. A transcript has
one assistant entry per streamed message and several of those share a single
API request, so counting usage-bearing entries overstates calls badly: 2.1x on
the Mac and 2.6x on the Windows box, measured. Both machines answering "what
did the cross-machine channel cost" with separately invented arithmetic is how
two boxes produce two incomparable numbers, which is the failure section 7.2
exists to avoid.

    python scripts/session-split.py --transcript PATH
    python scripts/session-split.py --session-id 7899d007-...

Segments break at a human prompt or an inbound peer message. Exit 0 on a
session it could measure, 1 on one it could not.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HUMAN = {"typed", "suggestion_accepted"}
PEER = "cross-session-message"


def _text(entry: dict) -> str:
    content = (entry.get("message") or {}).get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(
            part.get("text", "") for part in content if isinstance(part, dict)
        )
    return ""


def _is_break(entry: dict) -> str | None:
    """A human turn or an inbound peer message starts a new segment."""
    if entry.get("type") != "user":
        return None
    if entry.get("promptSource") in HUMAN:
        return "you"
    if PEER in _text(entry):
        return "peer"
    return None


def segments(rows: list[dict]) -> list[dict]:
    out: list[dict] = []
    current: dict | None = None
    for entry in rows:
        kind = _is_break(entry)
        if kind:
            label = " ".join(_text(entry).split())[:58]
            current = {"kind": kind, "label": label, "requests": {},
                       "read": 0, "write": 0, "output": 0}
            out.append(current)
            continue
        if current is None:
            continue
        usage = (entry.get("message") or {}).get("usage")
        request = entry.get("requestId")
        if not usage or not request or request in current["requests"]:
            continue
        current["requests"][request] = True
        current["read"] += usage.get("cache_read_input_tokens", 0)
        current["write"] += usage.get("cache_creation_input_tokens", 0)
        current["output"] += usage.get("output_tokens", 0)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transcript", help="path to the .jsonl transcript")
    parser.add_argument("--session-id", help="resolved under --projects")
    parser.add_argument("--projects", default=str(Path.home() / ".claude" / "projects"))
    args = parser.parse_args(argv)

    path = Path(args.transcript) if args.transcript else None
    if path is None and args.session_id:
        found = list(Path(args.projects).rglob(f"{args.session_id}*.jsonl"))
        path = found[0] if found else None
    if path is None or not path.exists():
        print("no transcript: pass --transcript or --session-id", file=sys.stderr)
        return 1

    rows = [json.loads(line) for line in
            path.read_text(encoding="utf-8").splitlines() if line.strip()]
    bearing = [r for r in rows if (r.get("message") or {}).get("usage")]
    unique = {r.get("requestId") for r in bearing if r.get("requestId")}
    found = segments(rows)
    if not found:
        print("no segments found in that transcript", file=sys.stderr)
        return 1

    print(f"{path.name}")
    print(f"  {len(bearing)} usage-bearing entries behind {len(unique)} requests "
          f"({len(bearing) / max(len(unique), 1):.1f}x if counted naively)")
    print()
    print(f"  {'from':5} {'calls':>5} {'cache read':>12} {'cache wr':>9} "
          f"{'output':>8} {'ctx/call':>9}  segment")
    totals = {"you": [0, 0], "peer": [0, 0]}
    for segment in found:
        calls = len(segment["requests"])
        if not calls:
            continue
        per = segment["read"] // calls
        totals[segment["kind"]][0] += calls
        totals[segment["kind"]][1] += segment["read"]
        print(f"  {segment['kind']:5} {calls:5} {segment['read']:12,} "
              f"{segment['write']:9,} {segment['output']:8,} {per:9,}  "
              f"{segment['label']}")

    calls_all = sum(v[0] for v in totals.values()) or 1
    read_all = sum(v[1] for v in totals.values()) or 1
    print()
    for kind, name in (("you", "your turns"), ("peer", "peer turns")):
        calls, read = totals[kind]
        print(f"  {name:12} {calls:3} calls ({calls * 100 // calls_all:2}%)   "
              f"{read:12,} cache read ({read * 100 // read_all:2}%)")
    print()
    print("  The peer share is a LOWER BOUND. A send made inside a turn the")
    print("  operator started produces no break, so its calls are attributed to")
    print("  the operator -- this segments by who started a turn, not by what")
    print("  the calls were spent on. Hand-labelling gives the upper bound.")
    print()
    print("  The call share is the portable figure. The context share depends on")
    print("  WHERE in the session the segments fell, since context per call grows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
