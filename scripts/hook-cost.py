#!/usr/bin/env python
"""Time what a hook costs per tool call, because nothing here has priced one.

    python scripts/hook-cost.py --name probe --command "<exe> <script>"
    python scripts/hook-cost.py --all            # every hook this box has wired
    python scripts/hook-cost.py --all --max-ms 150

Exit 0 when every hook measured came in under `--max-ms`, 1 when one did not,
2 when a hook could not be run at all. The threshold is CHOSEN, not measured:
nothing in this repo knows what a tolerable per-call stall is, so it defaults
to off and is only a gate when a caller names one.

WHY THIS IS A SCRIPT AND NOT A NOTE. A hook is a process spawn on the hot path
of every tool call, and this repo's whole thesis is that the unmeasured cost is
the one that bites. #122 is that thesis pointed inward: a probe answering a
question it settled on day one, 3,202 invocations later, with no number on what
it costs. The answer had to be measurable by anyone, on either machine, which
is why this takes a command rather than knowing about any particular hook.

WHAT IT MEASURES AND WHAT IT DOES NOT. Wall-clock from spawn to exit, with a
representative payload on stdin. That is the interpreter start plus the hook's
own work, which together are what the harness waits for. It does not measure
the harness's own overhead in dispatching the hook, so every figure here is a
lower bound on the stall and an upper bound on nothing.

SOME HOOKS CANNOT BE TIMED WITHOUT CORRUPTING SOMETHING. A hook that derives a
row from its payload and appends it to a real log writes invented data every
time this script runs it. CLAUDE.md already states the rule for `statusline`;
the first run of this script proved it generalises, putting 26 synthetic rows
into `.agent-yield/resume-probe.jsonl` before anyone noticed -- the exact
defect the rule was written about, one command over. `--all` now skips those
and says which, and `--include-writers` is the deliberate override.
"""

from __future__ import annotations

import argparse
import json
import shlex
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# The shape the harness really sends, captured from `probe-log.jsonl`'s `keys`
# on 2026-08-30. A payload that is too small measures a hook parsing nothing.
PAYLOAD = {
    "hook_event_name": "PreToolUse",
    "session_id": "cost-probe",
    "transcript_path": str(ROOT / ".agent-yield" / "nonexistent.jsonl"),
    "cwd": str(ROOT),
    "permission_mode": "acceptEdits",
    "tool_name": "Bash",
    "tool_use_id": "toolu_costprobe",
    "tool_input": {"command": "echo hi", "description": "a representative call"},
}


def time_once(command: str, payload: dict) -> float:
    """Milliseconds for one spawn, stdin fed and output discarded."""
    started = time.perf_counter()
    subprocess.run(
        shlex.split(command, posix=False),
        input=json.dumps(payload),
        capture_output=True,
        text=True,
    )
    return (time.perf_counter() - started) * 1000


def measure(command: str, runs: int, payload: dict) -> dict:
    # One warm-up, discarded: the first spawn pays for a cold file cache and
    # would otherwise land in the median on a machine that has just booted.
    time_once(command, payload)
    samples = sorted(time_once(command, payload) for _ in range(runs))
    return {
        "runs": runs,
        "median_ms": statistics.median(samples),
        "mean_ms": statistics.fmean(samples),
        "min_ms": samples[0],
        "max_ms": samples[-1],
    }


# A command matching one of these appends a row DERIVED FROM ITS PAYLOAD to a
# real log, so timing it writes invented calibration data. Matched as
# substrings of the command, because the flag is the thing that does it.
WRITES_FROM_PAYLOAD = ("--probe", "statusline")


def writes_from_payload(command: str) -> str | None:
    """The token that makes this command unsafe to time, or None."""
    for token in WRITES_FROM_PAYLOAD:
        if token in command and "--no-write" not in command:
            return token
    return None


def wired_hooks() -> list[tuple[str, str]]:
    """Every command this box runs on a tool call, from both settings files.

    Reads the LIVE files rather than the template, because the question is what
    this machine pays and the template names no machine. A file that is absent
    contributes nothing: `settings.local.json` is machine state and the other
    box has never had one.
    """
    found: list[tuple[str, str]] = []
    for name in (".claude/settings.json", ".claude/settings.local.json"):
        path = ROOT / name
        if not path.is_file():
            continue
        try:
            settings = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            continue
        for event, groups in (settings.get("hooks") or {}).items():
            for group in groups:
                matcher = group.get("matcher", "*")
                for hook in group.get("hooks") or []:
                    command = hook.get("command")
                    if command:
                        found.append((f"{event}:{matcher} [{path.name}]", command))
    return found


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--command", help="the hook command to time")
    ap.add_argument("--name", default="hook", help="label for the row")
    ap.add_argument("--all", action="store_true",
                    help="time every hook wired on this machine")
    ap.add_argument("--runs", type=int, default=20)
    ap.add_argument("--max-ms", type=float,
                    help="exit 1 if any median exceeds this (chosen, not measured)")
    ap.add_argument("--include-writers", action="store_true",
                    help="also time hooks that append a payload-derived row to a "
                         "real log; they will write invented data")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    if args.all:
        targets = wired_hooks()
        if not args.include_writers:
            skipped = [(l, c) for l, c in targets if writes_from_payload(c)]
            targets = [(l, c) for l, c in targets if not writes_from_payload(c)]
            for label, command in skipped:
                print(f"skipped {label}: {writes_from_payload(command)!r} makes it "
                      "append a payload-derived row to a real log. "
                      "--include-writers to time it anyway.")
            if skipped:
                print()
    elif args.command:
        targets = [(args.name, args.command)]
    else:
        ap.error("pass --command or --all")

    if not targets:
        print("no hooks wired on this machine")
        return 0

    rows = []
    for label, command in targets:
        try:
            result = measure(command, args.runs, PAYLOAD)
        except (OSError, ValueError) as exc:
            print(f"{label}: could not run ({exc})", file=sys.stderr)
            return 2
        rows.append({"label": label, "command": command, **result})

    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        width = max(len(r["label"]) for r in rows)
        print(f"{'hook':{width}}  {'median':>9} {'mean':>9} {'min':>9} {'max':>9}")
        for r in rows:
            print(f"{r['label']:{width}}  {r['median_ms']:8.1f}ms "
                  f"{r['mean_ms']:8.1f}ms {r['min_ms']:8.1f}ms {r['max_ms']:8.1f}ms")
        total = sum(r["median_ms"] for r in rows)
        print(f"\n{len(rows)} hooks, {total:.1f}ms of medians. A tool call pays "
              "only the ones whose matcher it hits.")

    if args.max_ms is not None:
        over = [r for r in rows if r["median_ms"] > args.max_ms]
        for r in over:
            print(f"OVER: {r['label']} median {r['median_ms']:.1f}ms "
                  f"> {args.max_ms:.1f}ms", file=sys.stderr)
        if over:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
