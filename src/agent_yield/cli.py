"""Subcommands. Thin -- every one is a call into a tested module."""
from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path

from . import boundary as boundary_module
from . import gate as gate_module
from . import handoff as handoff_module
from . import session as session_module
from .discovery import default_roots
from .ingest import ingest, load_ingested
from .interventions import load_interventions
from .modes import (
    VALID_MODES,
    ModeError,
    load_modes,
    record_mode,
    tagged_sessions,
    untagged_sessions,
)
from .handoff import DEFAULT_HANDOFF_PATH
from .outcomes import daily_outcomes
from .predict import project
from .report import build_rows, compare_interventions, render_table
from .thresholds import (
    DEFAULT_EXPECTED_CALLS,
    DEFAULT_WINDOW,
    REFERENCE_CONTEXT,
    RESTART_FACTOR,
    RESTART_HARD_FACTOR,
    cost_advice,
    cost_band,
)

DEFAULT_CALLS_PATH = Path(".agent-yield") / "calls.jsonl"
MODES_FILENAME = "session-modes.toml"
METRICS = ("tokens_per_merge", "tokens_per_commit", "context_per_call")


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
        load_modes(repo / MODES_FILENAME),
    )
    print(render_table(rows))

    interventions = load_interventions(repo / "interventions.toml")
    if interventions:
        print("\ninterventions")
        results = compare_interventions(rows, interventions, metric=args.metric)
        for result in results:
            before = "-" if result.before is None else f"{result.before:,.0f}"
            after = "-" if result.after is None else f"{result.after:,.0f}"
            print(f"  {result.intervention.date}  {result.intervention.name}")
            print(f"    expected: {result.intervention.expect}")
            print(f"    {result.metric}: {before} -> {after}")
        if _metric_is_empty(rows, results, args.metric):
            # A column of dashes reads as "no change". It usually means the
            # denominator does not exist in this repo at all.
            print(_empty_metric_note(args.metric))
    return 0


def _metric_is_empty(rows, results, metric: str) -> bool:
    every_result_blank = all(
        result.before is None and result.after is None for result in results
    )
    no_row_has_it = not any(getattr(row, metric, None) is not None for row in rows)
    return every_result_blank or no_row_has_it


def _empty_metric_note(metric: str) -> str:
    alternative = (
        "tokens_per_commit" if metric != "tokens_per_commit" else "context_per_call"
    )
    because = (
        " (this repo may have no merge commits)"
        if metric == "tokens_per_merge"
        else ""
    )
    return (
        f"  all rows are empty for {metric!r}{because}"
        f" -- try --metric {alternative}"
    )


def _cmd_status(args) -> int:
    """One measurement of the session you are in, and what it costs to stay.

    Exit 1 means this session should end: either context/call has grown past
    the hard factor, or the session is in the steep cost band. Both are
    "leave"; everything else is exit 0, so a prompt, a Makefile or CI can
    branch on it without parsing this text.
    """
    root = Path(args.transcripts) if args.transcripts else None
    path = session_module.find_session(args.session_id, root)
    if path is None:
        print("no session transcript found -- nothing to measure")
        return 0

    stats = session_module.session_stats(path, args.baseline_calls)
    if stats.calls == 0:
        print(f"{path.stem}: no main-thread calls recorded yet")
        return 0

    usage = stats.total
    window = args.window
    band = cost_band(stats.current_context, window)
    print(f"session {path.stem}")
    print(f"  calls           {stats.calls:,}")
    print(f"  context/call    opening {_num(stats.opening_context_per_call)}  "
          f"mean {_num(stats.context_per_call)}  "
          f"current {stats.current_context:,}  "
          f"growth {'-' if stats.growth is None else f'{stats.growth:.1f}x'}")
    # The four fields stay apart; the total is the parenthetical, for display.
    print(f"  tokens          input {usage.input_tokens:,}  "
          f"output {usage.output_tokens:,}  "
          f"cache write {usage.cache_creation_tokens:,}  "
          f"cache read {usage.cache_read_tokens:,}  "
          f"(total {usage.total:,})")
    of_window = (f" ({stats.current_context / window:.0%} of a {window:,} window)"
                 if window > 0 else "")
    print(f"  cost band       {band}{of_window}")

    crossings = session_module.cost_crossings(stats, window)
    for name in ("knee", "steep"):
        if name in crossings:
            print(f"  crossed {name:<7} at call {crossings[name]:,}")

    advice = cost_advice(stats.current_context, window)
    if advice:
        print(f"\n{advice}")
    growth_advice = session_module.restart_advice(stats, args.factor)
    if growth_advice:
        print(f"\n{growth_advice}")

    past_hard = stats.growth is not None and stats.growth >= args.hard_factor
    if past_hard or band == "steep":
        print("\nExit 1: write findings down (`agent-yield handoff`) "
              "and start a fresh session.")
        return 1
    return 0


def _num(value: float | None) -> str:
    """A number, or `-`. Never `0` for something unmeasured."""
    return "-" if value is None else f"{round(value):,}"


def _cmd_handoff(args) -> int:
    """Write down what a restart destroys -- or read back what was written."""
    out = Path(args.out)
    if args.read_:
        text = handoff_module.read(out)
        if text is None:
            print(f"no handoff at {out} "
                  "-- run `agent-yield handoff` before restarting")
            return 0
        print(text, end="" if text.endswith("\n") else "\n")
        return 0

    root = Path(args.transcripts) if args.transcripts else None
    path = session_module.find_session(args.session_id, root)
    stats = (session_module.session_stats(path, args.baseline_calls)
             if path is not None else None)

    # Notes already in the file are carried forward: regenerating a handoff
    # must not delete the one section a human wrote by hand.
    notes = handoff_module.existing_notes(out) + list(args.note or [])
    handoff = handoff_module.build(Path(args.repo), stats, notes)
    handoff_module.write(out, handoff_module.render(handoff))

    print(f"handoff written to {out}")
    if stats is None:
        print("  no session transcript found -- cost is unmeasured in it")
    if handoff.dirty:
        print(f"  working tree is DIRTY ({len(handoff.dirty)} path(s)) "
              "-- commit or stash before restarting")
    if not notes:
        print("  nothing claimed as unfinished "
              "-- `agent-yield handoff --note \"...\"` if something is")
    return 0


def _cmd_tag(args) -> int:
    path = Path(args.repo) / MODES_FILENAME
    if args.list_:
        return _list_tags(path, Path(args.calls))
    if not args.session_id or not args.mode:
        print("usage: agent-yield tag <session-id> <mode>   (or: tag --list)")
        return 2
    try:
        record_mode(path, args.session_id, args.mode)
    except ModeError as exc:
        print(str(exc))
        return 2
    print(f"{args.session_id}  {args.mode}  recorded in {path}")
    return 0


def _list_tags(path: Path, calls_path: Path) -> int:
    """Tagged sessions, then untagged ones by size. Never a suggested mode."""
    try:
        modes = load_modes(path)
    except ModeError as exc:
        print(str(exc))
        return 2

    print("tagged")
    if modes:
        for session_id, mode in tagged_sessions(path):
            print(f"  {session_id}  {mode}")
    else:
        print(f"  nothing recorded in {path}")

    records = load_ingested(calls_path)
    if not records:
        print(f"\nno calls recorded in {calls_path} "
              "-- run `agent-yield ingest` first")
        return 0

    # Usage objects are summed field by field; .total is for the line below.
    totals = {}
    for record in records:
        session_id = record.session_id
        if not session_id:
            continue
        held = totals.get(session_id)
        totals[session_id] = record.usage if held is None else held + record.usage

    biggest_first = sorted(totals, key=lambda s: totals[s].total, reverse=True)
    pending = untagged_sessions(biggest_first, modes)
    print("\nuntagged  (agent-yield tag <session-id> <mode>)")
    if not pending:
        print("  none -- every recorded session has a mode")
    for session_id in pending:
        print(f"  {session_id}  {totals[session_id].total:,} tokens")
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
    p.add_argument("--metric", choices=METRICS, default=METRICS[0],
                   help="which yield the intervention comparison reads")
    p.set_defaults(func=_cmd_report)

    p = subs.add_parser("tag", help="record a session's work mode")
    p.add_argument("session_id", nargs="?")
    p.add_argument("mode", nargs="?", help=f"one of {sorted(VALID_MODES)}")
    p.add_argument("--list", dest="list_", action="store_true",
                   help="show tagged sessions, then untagged ones by size")
    p.add_argument("--repo", default=".")
    p.add_argument("--calls", default=str(DEFAULT_CALLS_PATH))
    p.set_defaults(func=_cmd_tag)

    p = subs.add_parser("status", help="measure the session you are in")
    p.add_argument("--session-id", dest="session_id",
                   help="which session; default is the most recent transcript")
    p.add_argument("--transcripts", help="transcript root (default: discovered)")
    p.add_argument("--baseline-calls", dest="baseline_calls", type=int,
                   default=10, help="calls averaged for the opening context")
    p.add_argument("--window", type=int, default=DEFAULT_WINDOW,
                   help="context window this session runs in (provisional)")
    p.add_argument("--factor", type=float, default=RESTART_FACTOR,
                   help="growth factor at which a restart is advised")
    p.add_argument("--hard-factor", dest="hard_factor", type=float,
                   default=RESTART_HARD_FACTOR,
                   help="growth factor at which this command exits 1")
    p.set_defaults(func=_cmd_status)

    p = subs.add_parser("handoff", help="write down what a restart destroys")
    p.add_argument("--out", default=str(DEFAULT_HANDOFF_PATH))
    p.add_argument("--repo", default=".")
    p.add_argument("--session-id", dest="session_id",
                   help="which session; default is the most recent transcript")
    p.add_argument("--transcripts", help="transcript root (default: discovered)")
    p.add_argument("--baseline-calls", dest="baseline_calls", type=int,
                   default=10, help="calls averaged for the opening context")
    p.add_argument("--note", action="append",
                   help="what is claimed and unfinished (repeatable)")
    p.add_argument("--read", dest="read_", action="store_true",
                   help="print the handoff instead of writing one")
    p.set_defaults(func=_cmd_handoff)

    p = subs.add_parser("gate", help="PreToolUse hook entry point")
    p.set_defaults(func=lambda _args: gate_module.main())

    p = subs.add_parser(
        "boundary",
        help="UserPromptSubmit hook entry point (advisory unless --enforce)",
    )
    p.add_argument("--enforce", action="store_true",
                   help="exit 2 to refuse the prompt -- UNVERIFIED mechanism")
    p.add_argument("--probe", action="store_true",
                   help="record what the hook receives; never blocks")
    p.set_defaults(func=lambda args: boundary_module.main(
        (["--enforce"] if args.enforce else [])
        + (["--probe"] if args.probe else [])
    ))

    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code) if exc.code else 2
    return args.func(args)


if __name__ == "__main__":
    # Without this, `python -m agent_yield.cli ...` exits 0 having done
    # nothing -- a silent success, which is the worst way for a tool to fail.
    raise SystemExit(main())
