"""Walk transcripts, dedup calls, persist a normalized copy."""
from __future__ import annotations

import datetime as dt
import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Iterable

from .discovery import find_transcripts
from .records import CallRecord, parse_line
from .usage import Usage


def load_records(paths: Iterable[Path]) -> list[CallRecord]:
    """Every billable call under `paths`, each counted once.

    A file that is empty, unreadable, or full of junk contributes nothing and
    does not abort the walk: subagent transcripts are routinely zero bytes.
    """
    records: list[CallRecord] = []
    seen: set[tuple[str, str]] = set()
    for path in paths:
        try:
            text = Path(path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            record = parse_line(line)
            if record is None:
                continue
            key = record.dedup_key
            if key is not None:
                if key in seen:
                    continue
                seen.add(key)
            records.append(record)
    return records


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
        "usage": {
            "input_tokens": record.usage.input_tokens,
            "output_tokens": record.usage.output_tokens,
            "cache_creation_input_tokens": record.usage.cache_creation_tokens,
            "cache_read_input_tokens": record.usage.cache_read_tokens,
        },
    })


def load_ingested(path: Path) -> list[CallRecord]:
    path = Path(path)
    if not path.exists():
        return []
    records: list[CallRecord] = []
    for line in path.read_text(encoding="utf-8").splitlines():
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
    for record in load_records(find_transcripts(list(roots))):
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
        "\n".join(_to_json(r) for r in merged) + "\n", encoding="utf-8"
    )
    return len(merged)
