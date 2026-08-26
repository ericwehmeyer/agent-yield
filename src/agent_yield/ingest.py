"""Walk transcripts, dedup calls, persist a normalized copy.

The dedup rule is the load-bearing part, and it lives in `records.dedup` --
not here -- because this module was not its only caller and the other copy
rotted (#61). What follows is why the rule is what it is.
 Claude Code writes one transcript
record per CONTENT BLOCK -- thinking, text, each tool_use -- all sharing
`(message.id, requestId)` and byte-identical cache and input figures, with
`output_tokens` correct only on the terminal record. Keeping the FIRST of a
group therefore keeps a partial: on the archived #33 arms it held 7,912 output
tokens where the CLI's own accounting says 42,292, a 5.3x undercount. Cache
read and creation are identical across the copies, which is why the error
survived four experiments unnoticed.

The undercount is proportional to how much an arm dispatches -- subagents emit
more content blocks -- so it biased exactly the comparison this tool exists to
make, in the flattering direction.

The rule is NOT keep-max. Keep-max and keep-terminal agree on all 101 groups in
the archive, so that data cannot choose between them, and max is wrong on a
retry or a `max_tokens` continuation sharing a message id. So: take the
terminal record if the group has one; otherwise take the largest AND MARK THE
GROUP INCOMPLETE, because that output figure is a lower bound.

Incompleteness is not a tolerance to be sized. It is detectable per group with
no ground truth at all, and it accounts for the shortfall exactly: 2 incomplete
groups on baton-r1 and 2 on baton-r2, 0 on both reader arms, and the shortfall
against the CLI is non-zero on precisely the arms that have them.
"""
from __future__ import annotations

import datetime as dt
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Iterable

from .discovery import scan_transcripts
from .records import CallRecord, dedup, json_lines, parse_line
from .usage import Usage


def load_records(paths: Iterable[Path]) -> list[CallRecord]:
    """Every billable call under `paths`, each counted once, at its full size.

    A file that is empty, unreadable, or full of junk contributes nothing and
    does not abort the walk: subagent transcripts are routinely zero bytes.

    Calls whose group held no terminal record come back with `incomplete` set:
    their `output_tokens` is a lower bound, and a caller that reports a total
    should say how many there were rather than present the sum as exact.
    """
    def _lines() -> Iterable[CallRecord]:
        for path in paths:
            try:
                text = Path(path).read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for line in json_lines(text):
                record = parse_line(line)
                if record is not None:
                    yield record

    return dedup(_lines())


def incomplete_calls(records: Iterable[CallRecord]) -> int:
    """How many calls came back with a lower-bound `output_tokens`."""
    return sum(1 for record in records if record.incomplete)


def total_usage(records: Iterable[CallRecord]) -> Usage:
    total = Usage.zero()
    for record in records:
        total = total + record.usage
    return total


def context_per_call(records: Iterable[CallRecord]) -> float:
    """Cache-read tokens per API call -- the ~136K constant.

    Cache read, not total: this measures how much context is re-read on every
    call, which is the quantity the cost model multiplies by.
    """
    records = list(records)
    if not records:
        return 0.0
    return total_usage(records).cache_read_tokens / len(records)


def agent_totals(records: Iterable[CallRecord]) -> dict[str, int]:
    totals: dict[str, int] = defaultdict(int)
    for record in records:
        if record.is_subagent and record.agent_id:
            totals[record.agent_id] += record.usage.total
    return dict(totals)


def median_agent_total(records: Iterable[CallRecord]) -> int:
    totals = agent_totals(records)
    if not totals:
        return 0
    return int(statistics.median(sorted(totals.values())))


def _to_json(record: CallRecord) -> str:
    return json.dumps({
        "timestamp": record.timestamp.isoformat(),
        "session_id": record.session_id,
        "agent_id": record.agent_id,
        "request_id": record.request_id,
        "message_id": record.message_id,
        "model": record.model,
        "is_subagent": record.is_subagent,
        "cwd": record.cwd,
        "stop_reason": record.stop_reason,
        "incomplete": record.incomplete,
        "usage": {
            "input_tokens": record.usage.input_tokens,
            "output_tokens": record.usage.output_tokens,
            "cache_creation_input_tokens": record.usage.cache_creation_tokens,
            "cache_read_input_tokens": record.usage.cache_read_tokens,
            # Nested, matching the transcript shape `Usage.from_payload` parses.
            # A flat-only line loses the TTL split on every round trip, and the
            # loss is invisible: the total still adds up.
            "cache_creation": {
                "ephemeral_5m_input_tokens": record.usage.cache_creation_5m,
                "ephemeral_1h_input_tokens": record.usage.cache_creation_1h,
            },
        },
    })


def load_ingested(path: Path) -> list[CallRecord]:
    path = Path(path)
    if not path.exists():
        return []
    records: list[CallRecord] = []
    for line in json_lines(path.read_text(encoding="utf-8")):
        if not line.strip():
            continue
        raw = json.loads(line)
        records.append(CallRecord(
            timestamp=dt.datetime.fromisoformat(raw["timestamp"]),
            usage=Usage.from_payload(raw["usage"]),
            session_id=raw.get("session_id"),
            agent_id=raw.get("agent_id"),
            request_id=raw.get("request_id"),
            message_id=raw.get("message_id"),
            model=raw.get("model"),
            is_subagent=raw.get("is_subagent", False),
            cwd=raw.get("cwd"),
            stop_reason=raw.get("stop_reason"),
            incomplete=raw.get("incomplete", False),
        ))
    return records


def ingest(dest: Path, roots: Iterable[Path]) -> int:
    """Merge newly-found calls into `dest`. Returns the total count held."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)

    existing = load_ingested(dest)
    # Records with no dedup_key are always kept by load_records (undercounting
    # is worse than overcounting), so a fresh walk re-finds the same unkeyed
    # calls every run. Guard the merge itself: an unkeyed record already held
    # in `dest`, identified by (timestamp, usage.total), does not get re-added.
    unkeyed_seen: set[tuple[dt.datetime, int]] = {
        (r.timestamp, r.usage.total) for r in existing if r.dedup_key is None
    }

    merged = list(existing)
    seen: set[tuple[str, str]] = {
        r.dedup_key for r in existing if r.dedup_key is not None
    }
    scan = scan_transcripts(list(roots))
    if scan.unreadable:
        # #64: the count this function returns is the tool's headline
        # number, and a walk that could not enter part of the tree makes it
        # a floor rather than a total. glob swallows the OSError, so
        # without this a partial walk and a complete one are the same clean
        # exit 0. No attempt is made to solve long paths -- only to stop
        # the two cases looking alike.
        count = len(scan.unreadable)
        print(
            f"[agent-yield] {count} "
            f"director{'y' if count == 1 else 'ies'} could not be read "
            "while walking transcripts, so the call count is a floor, not "
            "a total: " + ", ".join(str(p) for p in scan.unreadable),
            file=sys.stderr,
        )
    for record in load_records(scan.paths):
        key = record.dedup_key
        if key is not None:
            if key in seen:
                continue
            seen.add(key)
        else:
            unkeyed_key = (record.timestamp, record.usage.total)
            if unkeyed_key in unkeyed_seen:
                continue
            unkeyed_seen.add(unkeyed_key)
        merged.append(record)

    merged.sort(key=lambda r: r.timestamp)
    dest.write_text(
        "\n".join(_to_json(r) for r in merged) + "\n", encoding="utf-8", newline="\n"
    )
    return len(merged)
