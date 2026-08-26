"""Subcommands. Thin -- every one is a call into a tested module."""
from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path

from . import gate as gate_module
from .discovery import default_roots
from .ingest import ingest, load_ingested
from .interventions import load_interventions
from .modes import load_modes
from .outcomes import daily_outcomes
from .predict import project
from .report import build_rows, compare_interventions, render_table
from .thresholds import DEFAULT_EXPECTED_CALLS, REFERENCE_CONTEXT

DEFAULT_CALLS_PATH = Path(".agent-yield") / "calls.jsonl"


def _cmd_ingest(args) -> int:
    roots = [Path(r) for r in args.root] if args.root else default_roots()
    held = ingest(Path(args.dest), roots)
    print(f"{held} calls held in {args.dest}")
    return 0


def _cmd_predict(args) -> int:
    print(project(args.context, args.calls).describe())
    return 0


def _cmd_outcomes(args) -> int:
    since = dt.date.fromisoformat(args.since)
    until = (dt.date.fromisoformat(args.until) if args.until
             else dt.datetime.now(dt.timezone.utc).date())
    for outcome in daily_outcomes(Path(args.repo), since, until):
        print(f"{outcome.day}  merges={outcome.merges}  "
              f"commits={outcome.commits}  lines={outcome.lines}")
    return 0


def _cmd_report(args) -> int:
    records = load_ingested(Path(args.calls))
    if not records:
        print(f"no calls recorded in {args.calls} -- run `agent-yield ingest` first")
        return 0

    days = sorted(r.day for r in records)
    since = dt.date.fromisoformat(args.since) if args.since else days[0]
    until = dt.date.fromisoformat(args.until) if args.until else days[-1]

    repo = Path(args.repo)
    rows = build_rows(
        [r for r in records if since <= r.day <= until],
        daily_outcomes(repo, since, until),
        load_modes(repo / "session-modes.toml"),
    )
    print(render_table(rows))

    interventions = load_interventions(repo / "interventions.toml")
    if interventions:
        print("\ninterventions")
        for result in compare_interventions(rows, interventions):
            before = "-" if result.before is None else f"{result.before:,.0f}"
            after = "-" if result.after is None else f"{result.after:,.0f}"
            print(f"  {result.intervention.date}  {result.intervention.name}")
            print(f"    expected: {result.intervention.expect}")
            print(f"    {result.metric}: {before} -> {after}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agent-yield")
    subs = parser.add_subparsers(dest="command", required=True)

    p = subs.add_parser("ingest", help="read transcripts and persist calls")
    p.add_argument("--root", action="append", help="transcript root (repeatable)")
    p.add_argument("--dest", default=str(DEFAULT_CALLS_PATH))
    p.set_defaults(func=_cmd_ingest)

    p = subs.add_parser("predict", help="project a dispatch's cost")
    p.add_argument("--context", type=int, default=REFERENCE_CONTEXT)
    p.add_argument("--calls", type=int, default=DEFAULT_EXPECTED_CALLS)
    p.set_defaults(func=_cmd_predict)

    p = subs.add_parser("outcomes", help="what git says shipped")
    p.add_argument("--repo", default=".")
    p.add_argument("--since", required=True)
    p.add_argument("--until")
    p.set_defaults(func=_cmd_outcomes)

    p = subs.add_parser("report", help="the join")
    p.add_argument("--repo", default=".")
    p.add_argument("--calls", default=str(DEFAULT_CALLS_PATH))
    p.add_argument("--since")
    p.add_argument("--until")
    p.set_defaults(func=_cmd_report)

    p = subs.add_parser("gate", help="PreToolUse hook entry point")
    p.set_defaults(func=lambda _args: gate_module.main())

    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code) if exc.code else 2
    return args.func(args)


if __name__ == "__main__":
    # Without this, `python -m agent_yield.cli ...` exits 0 having done
    # nothing -- a silent success, which is the worst way for a tool to fail.
    raise SystemExit(main())
