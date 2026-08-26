"""One normalized record per API call, from either kind of transcript."""
from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass, replace
from typing import Iterable

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
    stop_reason: str | None = None
    # True when this call's group held no terminal record, so `usage.output_tokens`
    # is a LOWER BOUND. Set by `dedup` below, never by `parse_line`: a single
    # line cannot know whether its siblings finished.
    incomplete: bool = False

    @property
    def day(self) -> dt.date:
        # Bucketed in UTC. Transcript timestamps are UTC with a `Z` suffix, and
        # a local-time bucket would silently move calls between days depending
        # on where the report is run.
        return self.timestamp.date()

    @property
    def context(self) -> int:
        """Everything the model had to read on this call.

        The quantity `thresholds.cost_band` takes, and the reason it lives
        here rather than in either caller: `session.py` needs it to say which
        band the current call is in, `report.py` needs it to say what share of
        a day's main calls sat in each band, and two copies of the definition
        is how a share stops counting the band it names. Output is not in it
        -- the bill under discussion is what was fed in.
        """
        return (
            self.usage.input_tokens
            + self.usage.cache_read_tokens
            + self.usage.cache_creation_tokens
        )

    @property
    def is_terminal(self) -> bool:
        """This record carries the call's final `output_tokens`.

        Claude Code writes one record per CONTENT BLOCK -- thinking, text, each
        tool_use -- all sharing `(message.id, requestId)` and identical cache and
        input figures, with `output_tokens` correct only on the last. The last is
        the one that carries a `stop_reason`.
        """
        return bool(self.stop_reason)

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


def json_lines(text: str) -> list[str]:
    """Cut JSONL into lines the way the FORMAT does, not the way the stdlib does.

    `str.splitlines()` also breaks on \\v, \\f, \\x1c-\\x1e, \\x85, U+2028 and
    U+2029. None of those end a line in JSONL and JSON does not require them to
    be escaped inside a string, so a record carrying one was cut in half, both
    halves failed `json.loads`, and `parse_line` returned None for each --
    silently, because these walks are written to survive junk.

    Measured over 286 transcripts here (#62): 5 files affected, 10,879 spurious
    splits, 3 records lost, 5,326 output tokens. The loss is small because most
    fragments are junk on both sides. What makes it worth a named function is
    WHICH record it took on `a1f5f48f6b1fe2e91`: the terminal one, the only
    member of its group carrying the call's real `output_tokens`. The call
    survived through a sibling, so the count stayed right and #53's machinery
    marked it `incomplete`. **A call that looks unfinished is this bug's
    symptom**, which also means the corpus-wide incomplete count is inflated by
    an unknown amount from this cause.

    `\\r\\n` is handled because the trailing `\\r` leaves the JSON parseable.
    """
    return text.split("\n")


def parse_line(line: str) -> CallRecord | None:
    """Return a record, or None for any line that is not a billable call."""
    line = line.strip()
    if not line:
        return None
    try:
        payload = json.loads(line)
    except (ValueError, RecursionError):
        # RecursionError, not ValueError, is what json.loads raises on deeply
        # nested input. It escaped `except ValueError` and aborted the whole
        # walk on one pathological line -- load_records promises that junk
        # contributes nothing, not that it stops the run.
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
        stop_reason=message.get("stop_reason"),
    )


def _supersedes(new: CallRecord, held: CallRecord) -> bool:
    """Should `new` replace the record already held for this call?

    A terminal record beats a non-terminal one, whatever the counts say. Among
    two terminal records the first is kept -- the second is a continuation or a
    retry, not more of the same call, and taking the larger would be picking a
    number rather than a call. Among two non-terminal records the larger output
    wins, which is the best available lower bound.
    """
    if held.is_terminal:
        return False
    if new.is_terminal:
        return True
    return new.usage.output_tokens > held.usage.output_tokens


def dedup(records: Iterable[CallRecord]) -> list[CallRecord]:
    """Collapse per-content-block records into one record per API call.

    THIS LIVES HERE, AND NOT IN THE MODULE THAT WALKS FILES, BECAUSE THERE
    WERE TWO COPIES OF IT. #53 fixed the rule in `ingest.load_records`;
    `agents.read_agent_runs` held its own keep-FIRST copy under a docstring
    saying it deduped "the way `ingest` dedups", and went on undercounting
    subagent output tokens by 8.7x for as long as the sentence stayed
    plausible (#61). The rule is a property of a `CallRecord` -- of
    `dedup_key` and `is_terminal`, both defined above -- not of ingestion, so
    a second caller should reach for it rather than re-derive it.

    Records with no `dedup_key` cannot be grouped and are kept as they come:
    undercounting is the error this tool exists to prevent. They are never
    marked incomplete either, because nothing here can tell whether they
    finished.
    """
    out: list[CallRecord] = []
    at: dict[tuple[str, str], int] = {}
    for record in records:
        key = record.dedup_key
        if key is None:
            out.append(record)
            continue
        index = at.get(key)
        if index is None:
            at[key] = len(out)
            out.append(record)
        elif _supersedes(record, out[index]):
            out[index] = record
    for index in at.values():
        held = out[index]
        if not held.is_terminal:
            out[index] = replace(held, incomplete=True)
    return out
