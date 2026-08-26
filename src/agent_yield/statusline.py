"""The zero-token lever: what this session costs, rendered continuously.

Claude Code's `statusLine` setting runs a shell command and renders its
stdout. **It is not a model call** -- it costs no tokens and burns no
context, which makes it the only one of working-method.md section 11's three
levers that can be enforced continuously without paying for the enforcement.
Everything else the tool knows has to be asked for, and section 11's own
measurement is that knowing a lever is not the same as applying it: the
session that wrote the batching finding ran 0.97 tool calls per API call
while knowing it.

MEASURED 2026-08-26 01:38 UTC, macOS, Claude Code with Opus 5 (1M):

  - **The `statusLine` setting takes effect immediately**, in the session
    that writes it. Hooks do not -- their config loads at session start,
    which is the entire reason issue #22 exists. So this lever can be
    installed and seen at once, and it is the only part of the tool that can.
  - The payload carries `session_id`, `transcript_path` (stem == session id),
    `cwd`, `model.id`, `version`, `workspace.*`, `exceeds_200k_tokens`,
    `rate_limits.{five_hour,seven_day}.used_percentage`, `cost.*` and:

        context_window.context_window_size      1000000
        context_window.used_percentage          11
        context_window.current_usage.{input_tokens, output_tokens,
            cache_creation_input_tokens, cache_read_input_tokens}

    The three input fields summed to 105,788 against 104,156 measured from
    the transcript's last call -- the same quantity, one call apart. So the
    current context is handed over directly and no tail read is needed when
    the block is present.
  - **`context_window_size` is the real window.** thresholds.DEFAULT_WINDOW
    says "the tool cannot read the model's context window, so a caller must
    say"; here it can, so the payload wins over the provisional default and
    the cost bands are computed against the window this session actually has.
  - `cost.total_cost_usd` is also handed over, and is deliberately ignored.
    Tokens, never money -- and on a subscription that number is an API-rate
    equivalent rather than a bill, so rendering it would be doubly wrong.
  - `rate_limits.seven_day.used_percentage` is the operator's real currency
    on a subscription. Not rendered here -- out of scope for issue #18 Part
    B, which asks for context, growth and a marker -- but it is measured and
    available, and it is the obvious next thing this line could carry.

`--probe` records the keys that arrive (shape only, never values) so the
contract can be re-measured after any upgrade rather than trusted.

Speed, because this runs on every render: the transcript is append-only, so
two bounded slices answer both questions and the whole file is never read.
The last `TAIL_BYTES` carry the current call's context; the first
`HEAD_BYTES` carry the opening baseline, and since the head of an
append-only file never changes it is memoized per session in
`.agent-yield/statusline-cache.json`. Small transcripts skip all of it and
are measured exactly by `session.session_stats`. A 1.5 MB transcript costs
one bounded read per render after the first.

Fail silent, never loud. A status line that raises leaves a stack trace
under every keystroke, so every path here is caught and the failure prints a
short neutral string. Same reasoning as gate.py failing open, and the same
reason: the tool is not worth more than the session it is measuring.

Tokens, never money -- there is no rate in here and no `$`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TextIO

from .records import parse_line
from .session import SessionStats, resolve_transcript, session_stats
from .thresholds import (
    DEFAULT_WINDOW,
    RESTART_FACTOR,
    RESTART_HARD_FACTOR,
    cost_band,
    cost_says_leave,
)

__all__ = [
    "CACHE_PATH",
    "PROBE_PATH",
    "payload_context",
    "payload_window",
    "render",
    "line_for",
    "main",
]

# Bounded reads. Both are far larger than any single transcript line and far
# smaller than a working session's transcript, which is the whole point.
TAIL_BYTES = 256_000
HEAD_BYTES = 512_000
BASELINE_CALLS = 10

CACHE_PATH = Path(".agent-yield") / "statusline-cache.json"
PROBE_PATH = Path(".agent-yield") / "statusline-probe.jsonl"

# What a failure looks like: short, neutral, and obviously this tool's, so a
# persistently blank measurement is visible rather than mistaken for calm.
QUIET = "ay -"


def _slice(path: Path, size: int, from_end: bool) -> str:
    """One bounded slice of a file, as text. Empty string on any failure."""
    try:
        with Path(path).open("rb") as handle:
            if from_end:
                handle.seek(0, 2)
                start = max(0, handle.tell() - size)
                handle.seek(start)
                raw = handle.read()
                # A tail rarely starts on a line boundary; the first line is
                # a fragment and json.loads rejects it anyway, but dropping
                # it keeps the parse honest rather than accidentally right.
                if start > 0:
                    _, _, raw = raw.partition(b"\n")
            else:
                raw = handle.read(size)
    except OSError:
        return ""
    return raw.decode("utf-8", errors="replace")


def _records(text: str):
    for line in text.splitlines():
        record = parse_line(line)
        # Main-thread only: a sidechain line is the subagent's context, and
        # reading it as the parent's is the one error session.py names.
        if record is not None and not record.is_subagent:
            yield record


def _context(record) -> int:
    usage = record.usage
    return (
        usage.input_tokens
        + usage.cache_read_tokens
        + usage.cache_creation_tokens
    )


def _cache_read(cache_path: Path) -> dict:
    try:
        data = json.loads(Path(cache_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _cache_write(cache_path: Path, data: dict) -> None:
    try:
        Path(cache_path).parent.mkdir(parents=True, exist_ok=True)
        Path(cache_path).write_text(json.dumps(data), encoding="utf-8")
    except OSError:
        return


def _opening(
    path: Path,
    cache_path: Path,
    baseline_calls: int,
    head_bytes: int,
) -> float | None:
    """Mean context over the session's first calls, memoized.

    ``None``, never ``0``, when the head slice holds fewer than
    ``baseline_calls`` calls -- growth measured against a partial baseline is
    growth against a number that will change, which is worse than no number.
    """
    key = f"{Path(path).stem}:{baseline_calls}"
    cache = _cache_read(cache_path)
    cached = cache.get(key)
    if isinstance(cached, (int, float)) and cached > 0:
        return float(cached)

    contexts = []
    for record in _records(_slice(path, head_bytes, from_end=False)):
        contexts.append(_context(record))
        if len(contexts) >= baseline_calls:
            break
    if len(contexts) < baseline_calls:
        return None
    opening = sum(contexts) / baseline_calls
    if opening <= 0:
        return None
    cache[key] = opening
    _cache_write(cache_path, cache)
    return opening


def payload_context(payload: dict) -> int | None:
    """Current context, straight from the harness, or ``None``.

    Input side only -- ``output_tokens`` is what the call produced, not what
    it had to read, and `session._context` excludes it for the same reason.
    """
    window = payload.get("context_window")
    if not isinstance(window, dict):
        return None
    usage = window.get("current_usage")
    if not isinstance(usage, dict):
        return None
    total = 0
    for field in ("input_tokens", "cache_read_input_tokens",
                  "cache_creation_input_tokens"):
        value = usage.get(field)
        if isinstance(value, bool) or not isinstance(value, int):
            continue
        total += value
    return total or None


def payload_window(payload: dict) -> int | None:
    """The window this session actually has, or ``None`` to fall back."""
    window = payload.get("context_window")
    if not isinstance(window, dict):
        return None
    size = window.get("context_window_size")
    if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
        return None
    return size


def _short(value: int) -> str:
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"{value / 1_000:.0f}K"
    return str(value)


def render(
    current_context: int,
    growth: float | None,
    window: int = DEFAULT_WINDOW,
    factor: float = RESTART_FACTOR,
    hard_factor: float = RESTART_HARD_FACTOR,
) -> str:
    """The line itself: context, share of the window, growth, and a marker.

    The marker is the whole point of the line. Numbers alone were already
    available on demand and were already being ignored; what a status line
    adds is that the moment a session crosses into the expensive band, the
    crossing is on screen without anyone having asked.
    """
    parts = [f"ay {_short(current_context)}"]
    if window > 0:
        parts.append(f"{current_context / window:.0%}")
    # `-`, never `0`: an unmeasurable growth is not flat growth.
    parts.append("-" if growth is None else f"{growth:.1f}x")

    # The band reads the token count, never the window fraction beside it:
    # cost is absolute, capacity is fractional, and the line shows both
    # because they disagree (issue #23).
    band = cost_band(current_context)
    if band != "cheap":
        parts.append(band.upper())
    elif growth is not None and growth >= factor:
        parts.append("GROWING")

    leave = cost_says_leave(current_context) or (
        growth is not None and growth >= hard_factor)
    if leave:
        parts.append("-- handoff + restart")
    return " ".join(parts)


def line_for(
    path: Path,
    window: int = DEFAULT_WINDOW,
    baseline_calls: int = BASELINE_CALLS,
    cache_path: Path | None = None,
    tail_bytes: int = TAIL_BYTES,
    head_bytes: int = HEAD_BYTES,
    current_context: int | None = None,
) -> str:
    """Render one session's line, or ``QUIET``.

    ``current_context`` is the harness's own figure when it sent one; the
    transcript is read for it only when it did not. The transcript is still
    read for the opening baseline, because growth is a fact about the whole
    session and no single payload carries it.
    """
    cache_path = CACHE_PATH if cache_path is None else cache_path
    try:
        size = Path(path).stat().st_size
    except OSError:
        return QUIET

    # Small enough to measure exactly: the sliced path exists for long
    # sessions, and a short session deserves the same numbers `status` gives.
    if size <= head_bytes:
        stats: SessionStats = session_stats(path, baseline_calls)
        if stats.calls == 0 and current_context is None:
            return QUIET
        current = current_context or stats.current_context
        growth = stats.growth
        if current_context is not None and stats.opening_context_per_call:
            growth = current_context / stats.opening_context_per_call
        return render(current, growth, window)

    current = current_context
    if current is None:
        contexts = [_context(r)
                    for r in _records(_slice(path, tail_bytes, True))]
        if not contexts:
            return QUIET
        current = contexts[-1]
    opening = _opening(path, cache_path, baseline_calls, head_bytes)
    growth = None if opening is None else current / opening
    return render(current, growth, window)


def _probe(payload: dict, line: str) -> None:
    """Record the shape of what arrived. Keys only -- never their values.

    Dotted keys for nested objects, because the useful question is whether
    the payload carries a transcript path at all, and a value would carry the
    operator's home directory into a file the tool may later publish.
    """
    def keys(obj: dict, prefix: str = "") -> list[str]:
        out = []
        for key, value in obj.items():
            out.append(prefix + key)
            if isinstance(value, dict):
                out.extend(keys(value, prefix + key + "."))
        return out

    try:
        path, route = resolve_transcript(payload)
        PROBE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with PROBE_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({
                "keys": sorted(keys(payload)),
                "route": route,
                "resolved": path is not None,
                "rendered": line != QUIET,
            }) + "\n")
    except Exception:
        return


def main(argv: list[str] | None = None, stdin: TextIO | None = None) -> int:
    """Always exits 0, always prints exactly one line.

    Every failure mode -- malformed stdin, empty stdin, a transcript path
    that does not exist, a session with no calls yet -- prints ``QUIET``.
    There is no failure of this command that is worth interrupting the
    operator for.
    """
    args = list(argv or [])
    probing = "--probe" in args
    asked_window: int | None = None
    if "--window" in args:
        try:
            asked_window = int(args[args.index("--window") + 1])
        except (IndexError, ValueError):
            asked_window = None

    line = QUIET
    payload: dict = {}
    try:
        stream = stdin if stdin is not None else sys.stdin
        raw = stream.read()
        loaded = json.loads(raw or "{}")
        if isinstance(loaded, dict):
            payload = loaded
            # An explicit --window is the operator overriding a measurement,
            # so it wins; otherwise the measured window beats the provisional
            # constant, which exists only because nothing else knew.
            window = asked_window or payload_window(payload) or DEFAULT_WINDOW
            path, _route = resolve_transcript(payload)
            if path is not None:
                line = line_for(path, window,
                                current_context=payload_context(payload))
    except Exception:
        line = QUIET

    if probing:
        _probe(payload, line)
    print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
