"""PreToolUse probe: does a hook fire on the subagent-dispatch tool?

Settles the one question the burn-ledger design turns on. GitHub issue #34692
(closed as not planned) establishes that hooks do NOT fire for tool calls made
*inside* a subagent, and #55144 (also closed as not planned) shows Anthropic
declined to add a dedicated spawn hook. Neither settles whether a PreToolUse
hook fires on the MAIN thread's dispatch call, which is where the gate would
live.

Matches every tool rather than just the dispatch tool, on purpose: a probe that
only matches `Agent` cannot distinguish "the matcher does not fire on this tool"
from "the hook is not loaded at all". Logging every tool name makes a negative
result interpretable instead of ambiguous.

Writes one JSON line per invocation and always exits 0 -- this probe must never
block a tool call. Exit code 2 is what blocks; 0 is what observes.
"""
from __future__ import annotations

import datetime as _dt
import json
import pathlib
import sys

LOG = pathlib.Path(__file__).resolve().parent / "probe-log.jsonl"


def main() -> int:
    raw = ""
    try:
        if not sys.stdin.isatty():
            raw = sys.stdin.read()
    except (OSError, ValueError):
        pass

    payload: dict = {}
    if raw:
        try:
            payload = json.loads(raw)
        except ValueError:
            payload = {"_unparseable": raw[:400]}

    tool = payload.get("tool_name") or payload.get("toolName") or "?"
    record = {
        "ts": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "event": payload.get("hook_event_name") or payload.get("hookEventName") or "?",
        "tool": tool,
        # Top-level keys only. The probe records the *shape* of the payload so a
        # later implementation knows what it may read; it does not copy tool
        # inputs, which can be large and can carry file contents.
        "keys": sorted(k for k in payload if not k.startswith("_")),
    }
    if tool in ("Agent", "Task"):
        ti = payload.get("tool_input") or {}
        if isinstance(ti, dict):
            record["dispatch_keys"] = sorted(ti)
            record["subagent_type"] = ti.get("subagent_type")
            record["model"] = ti.get("model")

    try:
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
