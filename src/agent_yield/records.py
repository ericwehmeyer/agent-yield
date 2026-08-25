"""One normalized record per API call, from either kind of transcript."""
from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass

from .usage import Usage


@dataclass(frozen=True)
class CallRecord:
    timestamp: dt.datetime
    usage: Usage
    session_id: str | None = None
    agent_id: str | None = None
    request_id: str | None = None
    message_id: str | None = None
    model: str | None = None
    is_subagent: bool = False
    cwd: str | None = None

    @property
    def day(self) -> dt.date:
        # Bucketed in UTC. Transcript timestamps are UTC with a `Z` suffix, and
        # a local-time bucket would silently move calls between days depending
        # on where the report is run.
        return self.timestamp.date()

    @property
    def dedup_key(self) -> tuple[str, str] | None:
        # Only a complete pair identifies a call. With either half missing the
        # record is counted rather than dropped -- under-counting is the error
        # this tool exists to prevent.
        if self.message_id and self.request_id:
            return (self.message_id, self.request_id)
        return None


def _timestamp(raw: str | None) -> dt.datetime | None:
    if not raw:
        return None
    try:
        parsed = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def parse_line(line: str) -> CallRecord | None:
    """Return a record, or None for any line that is not a billable call."""
    line = line.strip()
    if not line:
        return None
    try:
        payload = json.loads(line)
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None

    message = payload.get("message")
    if not isinstance(message, dict):
        return None
    usage_payload = message.get("usage")
    if not isinstance(usage_payload, dict):
        return None

    timestamp = _timestamp(payload.get("timestamp"))
    if timestamp is None:
        return None

    return CallRecord(
        timestamp=timestamp,
        usage=Usage.from_payload(usage_payload),
        session_id=payload.get("sessionId"),
        agent_id=payload.get("agentId"),
        request_id=payload.get("requestId"),
        message_id=message.get("id"),
        model=message.get("model"),
        is_subagent=bool(payload.get("isSidechain")),
        cwd=payload.get("cwd"),
    )
