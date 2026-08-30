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
  - `cost.total_cost_usd` is also handed over, and is still not rendered. Not
    because money cannot be trusted -- `pricing.py` reproduces it to the cent
    -- but because on a subscription a dollar figure is a list-price
    equivalent rather than a bill, and the line has room for one number about
    budget. The percentage below is the one an operator can act on.
  - `rate_limits.seven_day.used_percentage` is the operator's real currency
    on a subscription, and the line now carries it as `7d NN%`. It is the one
    budget number on a plan that is not an equivalent of something else, and
    unlike a dollar figure it needs no price table to mean what it says.
    Every render also snapshots the two windows to `allowance.py`'s log --
    but only when a percentage moves, or a status line becomes a keystroke
    counter.

`--probe` records the keys that arrive (shape only, never values) so the
contract can be re-measured after any upgrade rather than trusted.

`--no-write` (issue #69) is the guard for the fact that this READ command is
silently also a WRITE: the allowance snapshot above, and the probe log, are
both appended to by an ordinary render. Rendering the line by hand with a
synthesized payload therefore writes invented percentages into the input of a
number the tool later reports, and on 2026-08-26 it did. With the flag the line
is byte-identical and neither log is touched. **Every hand render should carry
it.** The default writes, because the harness cannot be asked to pass a flag
and a render that quietly stopped collecting would be worse than the hazard.

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
from pathlib import Path
from typing import TextIO

from .allowance import SNAPSHOT_PATH, append as append_allowance, load as load_allowance, read_allowance
from .hookio import read_payload
from .pricing import window_for
from .records import dedup, json_lines, parse_line
from .session import SessionStats, resolve_transcript, session_stats
from .state import anchored
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
    "payload_model",
    "payload_window",
    "render",
    "line_for",
    "compose_line",
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

# COMPOSITION (issue #66). `statusLine` takes ONE command, and a project
# `.claude/settings.json` REPLACES the user one rather than merging with it, so
# an operator who wants this line AND their own general-purpose one cannot have
# both from configuration. `--with` is the join: each command is run with the
# SAME payload on stdin and its first line becomes a segment.
#
# Why here rather than a shell script: the payload arrives on stdin exactly
# once, so any wrapper has to buffer it and hand each consumer its own copy --
# and a shell wrapper would have to be written twice, once per machine. This
# runs wherever the tool already runs.
#
# 1.5 seconds because that is what the other machine's PowerShell line already
# chose for its git calls, and composition is the moment latency starts adding
# up: this tool shells out to nothing, but the lines it may be composed with
# shell out to git with no timeout of their own.
COMPOSE_TIMEOUT = 1.5


# `\u00b7`, not an ASCII bar. The sh status line on this machine picks its ⚠
# glyph by sniffing LC_ALL/LC_CTYPE/LANG, and carries a comment about that
# glyph crashing a Windows console at chcp 437 -- but that script writes raw
# bytes to whatever the console is. This tool does not: `cli.main` forces
# stdout to UTF-8 with `errors="replace"` (#43, where a bare 0xA7 on a cp1252
# Windows stream broke a consumer decoding the WHOLE read). So the console's
# own code page cannot corrupt this, and an ASCII fallback here would be a
# branch that can never be taken -- a safety feature that is really dead code.
SEPARATOR = "  \u00b7  "


def _compose(commands, payload: str, timeout: float = COMPOSE_TIMEOUT) -> list[str]:
    """Run each command with `payload` on stdin; collect its first line.

    A command that fails, times out, writes only to stderr or prints nothing
    contributes NOTHING -- no placeholder, no error text. A status line is not
    a place to report that a status line broke, and the segments that did work
    are still worth showing. Same reasoning as `QUIET`, one level up.

    `shell=True` deliberately: the commands come from the operator's own
    `settings.json`, they are the same strings `statusLine` itself would run,
    and they need `$HOME`/quoting handled the way the operator wrote them.
    """
    out: list[str] = []
    if not commands:
        return out
    import subprocess
    for command in commands:
        try:
            # encoding= named, never inherited: #41's guard, and a status
            # line composed of another program's output is exactly where a
            # cp1252 default would mangle a glyph on Windows and nowhere else.
            done = subprocess.run(
                command, shell=True, timeout=timeout,
                input=payload, capture_output=True, text=True,
                encoding="utf-8", errors="replace")
        except Exception:
            continue
        for candidate in (done.stdout or "").splitlines():
            if candidate.strip():
                out.append(candidate.rstrip())
                break
    return out


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
    """Main-thread calls in a slice of transcript, one record per call.

    Main-thread only: a sidechain line is the subagent's context, and reading
    it as the parent's is the one error session.py names.

    DEDUPED, though nothing here reads `output_tokens` (#61). Context is
    byte-identical across a call's content-block records, so the sizes were
    never wrong -- but `_opening` takes the first N *records* as the first N
    *calls*, and on the two long transcripts here that was 10 of 106 and 10
    of 61 records against 37 and 32 distinct calls. The opening baseline came
    out 5.2% and 7.4% low, which made the growth ratio on the status line --
    the number the restart advice keys off -- read 5-7% high.

    `records.dedup` needs a whole group to decide, so it is applied to the
    slice rather than streamed. The slice is bounded by design.
    """
    parsed = []
    for line in json_lines(text):
        record = parse_line(line)
        if record is not None and not record.is_subagent:
            parsed.append(record)
    yield from dedup(parsed)


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
        Path(cache_path).write_text(json.dumps(data), encoding="utf-8", newline="\n")
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


def payload_model(payload: dict) -> str | None:
    """The model id this session is running, or None."""
    model = payload.get("model")
    if not isinstance(model, dict):
        return None
    identifier = model.get("id")
    return identifier if isinstance(identifier, str) and identifier else None


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
    seven_day: int | None = None,
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

    # The allowance, before the markers, because it is a number and they are
    # not. Omitted entirely when the client does not report it -- absent is
    # not 0%, which would read as a fresh week.
    if seven_day is not None:
        parts.append(f"7d {seven_day}%")

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
    seven_day: int | None = None,
) -> str:
    """Render one session's line, or ``QUIET``.

    ``current_context`` is the harness's own figure when it sent one; the
    transcript is read for it only when it did not. The transcript is still
    read for the opening baseline, because growth is a fact about the whole
    session and no single payload carries it.
    """
    cache_path = anchored(CACHE_PATH if cache_path is None else cache_path)
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
        return render(current, growth, window, seven_day=seven_day)

    current = current_context
    if current is None:
        contexts = [_context(r)
                    for r in _records(_slice(path, tail_bytes, True))]
        if not contexts:
            return QUIET
        current = contexts[-1]
    opening = _opening(path, cache_path, baseline_calls, head_bytes)
    growth = None if opening is None else current / opening
    return render(current, growth, window, seven_day=seven_day)


def compose_line(
    own: str,
    commands=(),
    payload: str = "",
    timeout: float = COMPOSE_TIMEOUT,
) -> str:
    """This tool's line, with any `--with` segments in front of it.

    Composition can only ADD to the line. With no commands, or with commands
    that all fail, the result is exactly what this tool would have printed
    alone -- a broken segment must not be able to take the measurement down
    with it.
    """
    segments = _compose(commands, payload, timeout)
    if not segments:
        return own
    return SEPARATOR.join([*segments, own])


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
        probe = anchored(PROBE_PATH)
        probe.parent.mkdir(parents=True, exist_ok=True)
        with probe.open("a", encoding="utf-8", newline="\n") as handle:
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
    # #69: this is a READ command that is silently also a WRITE, and rendering
    # the line by hand with a synthesized payload put invented percentages into
    # the calibration log. `--no-write` renders the same line and appends to
    # neither log. It covers the probe as well as the allowance: the probe file
    # is the evidence for what the harness sends, and a hand-made payload's key
    # set is a claim about that contract the harness never made.
    #
    # NOT covered, deliberately: `.agent-yield/statusline-cache.json`. Every
    # entry there is a pure function of a real transcript's head, keyed by that
    # transcript's stem, so a hand render can only write the value the next
    # genuine render would have computed anyway.
    #
    # A flag is a lever that must be remembered, which §12.1 of
    # working-method.md names as the weak kind of fix -- but no signal
    # separates a hand render from a harness render with the confidence this
    # needs. A hand test run from inside a Claude Code session shares the
    # harness's environment and its piped stdin, and usually points at a real
    # transcript; and a guard that guesses wrong on a genuine render stops the
    # calibration silently, which is worse than the bug it would prevent.
    writing = "--no-write" not in args
    asked_window: int | None = None
    if "--window" in args:
        try:
            asked_window = int(args[args.index("--window") + 1])
        except (IndexError, ValueError):
            asked_window = None
    # `--with` repeats; each occurrence is one segment, in the order given.
    with_commands = [args[i + 1] for i, a in enumerate(args)
                     if a == "--with" and i + 1 < len(args)]
    with_timeout = COMPOSE_TIMEOUT
    if "--with-timeout" in args:
        try:
            with_timeout = float(args[args.index("--with-timeout") + 1])
        except (IndexError, ValueError):
            with_timeout = COMPOSE_TIMEOUT

    line = QUIET
    payload: dict = {}
    raw = ""
    try:
        raw = read_payload(stdin) or ""
        loaded = json.loads(raw or "{}")
        if isinstance(loaded, dict):
            payload = loaded
            # Four answers, best first. An explicit --window is the operator
            # overriding a measurement, so it wins. Then the window this
            # session reports for itself. Then the registry, which is observed
            # from `modelUsage.contextWindow` and is a fact about the model
            # rather than a habit of this operator -- 1M for opus, 200K for
            # haiku, and a fraction against the wrong one of those is off by
            # five. DEFAULT_WINDOW last, and reaching it means the tool does
            # not know which model it is looking at.
            window = (asked_window
                      or payload_window(payload)
                      or window_for(payload_model(payload))
                      or DEFAULT_WINDOW)
            # Measured on every render, kept only when it moved. This is the
            # data any later calibration needs and it cannot be recovered
            # after the fact, so it is collected before it is used for
            # anything -- the opposite order to the one that lost #47's
            # baton1 arm.
            allowance = read_allowance(payload)
            if allowance is not None and writing:
                held = load_allowance(SNAPSHOT_PATH)
                append_allowance(SNAPSHOT_PATH, allowance,
                                 held[-1] if held else None)

            path, _route = resolve_transcript(payload)
            if path is not None:
                line = line_for(
                    path, window,
                    current_context=payload_context(payload),
                    seven_day=allowance.seven_day if allowance else None)
    except Exception:
        line = QUIET

    if probing and writing:
        _probe(payload, line)

    # Composed segments go FIRST so that this tool's own band marker --
    # `EXPENSIVE`, `GROWING`, `-- handoff + restart` -- stays at the end of the
    # whole line, which is where a marker is seen. The probe records the
    # tool's own line, never the composition: what arrived is this tool's
    # contract to measure, and another command's output is not.
    print(compose_line(line, with_commands, raw, with_timeout))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
