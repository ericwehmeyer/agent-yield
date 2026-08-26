"""Tests for the status line: it must never be loud, and never be slow.

The failure modes matter more than the happy path here. A status line runs on
every render, so a crash is not one stack trace -- it is a stack trace under
every keystroke for the rest of the session, and the operator's remedy is to
delete the setting.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

from agent_yield import statusline
from agent_yield.statusline import QUIET, line_for, main, render


def _transcript(tmp_path: Path, reads: list[int], name: str = "s") -> Path:
    lines = []
    for index, read in enumerate(reads):
        lines.append(json.dumps({
            "timestamp": f"2026-08-26T02:{index // 60:02d}:{index % 60:02d}.000Z",
            "sessionId": name, "requestId": f"req-{index}",
            "message": {"id": f"msg-{index}",
                        "usage": {"cache_read_input_tokens": read}},
        }))
    path = tmp_path / f"{name}.jsonl"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_a_cheap_session_reads_as_numbers_and_no_marker(tmp_path):
    line = line_for(_transcript(tmp_path, [20_000] * 20))
    assert line == "ay 20K 2% 1.0x"


def test_growth_past_the_advisory_factor_is_marked(tmp_path):
    line = line_for(_transcript(tmp_path, [10_000] * 10 + [30_000] * 10))
    assert "3.0x" in line and "GROWING" in line


def test_a_leave_band_says_leave(tmp_path):
    line = line_for(_transcript(tmp_path, [550_000] * 20))
    assert "RESTART" in line
    assert "handoff" in line


def test_unmeasurable_growth_renders_as_a_dash_never_zero(tmp_path):
    # Fewer calls than the baseline: growth is not 1.0x, it is unknown.
    line = line_for(_transcript(tmp_path, [20_000] * 3))
    assert line.endswith("-")
    assert "0.0x" not in line


def test_an_empty_transcript_is_quiet(tmp_path):
    empty = tmp_path / "empty.jsonl"
    empty.write_text("", encoding="utf-8")
    assert line_for(empty) == QUIET


def test_a_long_transcript_is_measured_from_bounded_slices(tmp_path):
    """The sliced path must agree with the exact one, not approximate it."""
    reads = [10_000] * 10 + [40_000] * 200
    path = _transcript(tmp_path, reads, name="long")
    sliced = line_for(path, tail_bytes=2_000, head_bytes=2_000,
                      cache_path=tmp_path / "cache.json")
    exact = line_for(path, cache_path=tmp_path / "cache2.json")
    assert sliced == exact == "ay 40K 4% 4.0x GROWING -- handoff + restart"


def test_the_opening_baseline_is_cached_after_the_first_render(tmp_path):
    path = _transcript(tmp_path, [10_000] * 10 + [40_000] * 200, name="long")
    cache = tmp_path / "cache.json"
    line_for(path, tail_bytes=2_000, head_bytes=2_000, cache_path=cache)
    held = json.loads(cache.read_text(encoding="utf-8"))
    assert held == {"long:10": 10_000.0}
    # Cached, so the head is never read again -- prove it by making the head
    # unreadable and asking for the same line.
    path.write_bytes(b"junk\n" + path.read_bytes())
    again = line_for(path, tail_bytes=2_000, head_bytes=2_000, cache_path=cache)
    assert "4.0x" in again


def test_malformed_empty_and_missing_stdin_all_exit_0_quietly(capsys):
    for payload in ("", "not json{", "[]", "null", "{}"):
        assert main([], stdin=io.StringIO(payload)) == 0
        assert capsys.readouterr().out.strip() == QUIET


def test_a_transcript_path_that_does_not_exist_exits_0_quietly(capsys):
    payload = json.dumps({"transcript_path": "/nowhere/at/all.jsonl"})
    assert main([], stdin=io.StringIO(payload)) == 0
    assert capsys.readouterr().out.strip() == QUIET


def test_a_raising_measurement_still_prints_one_harmless_line(monkeypatch, capsys):
    def explode(*args, **kwargs):
        raise RuntimeError("measurement is broken")
    monkeypatch.setattr(statusline, "line_for", explode)
    payload = json.dumps({"transcript_path": __file__})
    assert main([], stdin=io.StringIO(payload)) == 0
    assert capsys.readouterr().out.strip() == QUIET


def test_the_measured_payload_renders_a_line(tmp_path, capsys):
    path = _transcript(tmp_path, [20_000] * 20, name="live")
    payload = json.dumps({"session_id": "live", "transcript_path": str(path)})
    assert main([], stdin=io.StringIO(payload)) == 0
    out = capsys.readouterr().out.strip()
    assert out.startswith("ay ") and len(out) < 60


def test_the_probe_records_keys_and_never_their_values(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(statusline, "PROBE_PATH", tmp_path / "probe.jsonl")
    path = _transcript(tmp_path, [20_000] * 20, name="live")
    payload = json.dumps({
        "session_id": "live", "transcript_path": str(path),
        "workspace": {"current_dir": "/Users/someone/secret-project"},
    })
    assert main(["--probe"], stdin=io.StringIO(payload)) == 0
    recorded = json.loads((tmp_path / "probe.jsonl").read_text(encoding="utf-8"))
    assert "workspace.current_dir" in recorded["keys"]
    assert recorded["route"] == "transcript_path"
    assert recorded["resolved"] is True
    assert "secret-project" not in json.dumps(recorded)
    assert str(path) not in json.dumps(recorded)


def test_tokens_never_money(tmp_path):
    assert "$" not in render(500_000, 6.0)


def test_the_harness_window_sets_the_capacity_share_not_the_cost_band(tmp_path, capsys):
    """The window moves the percentage on the line and nothing else.

    It used to move the band as well, which is issue #23: the same 100,000
    tokens cost the same whatever window they sit in.
    """
    path = _transcript(tmp_path, [100_000] * 20, name="live")
    payload = json.dumps({
        "transcript_path": str(path), "session_id": "live",
        "context_window": {"context_window_size": 200_000,
                           "current_usage": {"input_tokens": 0,
                                             "cache_read_input_tokens": 100_000,
                                             "cache_creation_input_tokens": 0,
                                             "output_tokens": 4_000}},
    })
    assert main([], stdin=io.StringIO(payload)) == 0
    out = capsys.readouterr().out
    assert "50%" in out
    assert "STEEP" not in out and "RESTART" not in out and "DISPATCH" not in out


def test_an_explicit_window_overrides_the_harness(tmp_path, capsys):
    path = _transcript(tmp_path, [100_000] * 20, name="live")
    payload = json.dumps({
        "transcript_path": str(path), "session_id": "live",
        "context_window": {"context_window_size": 200_000,
                           "current_usage": {"cache_read_input_tokens": 100_000}},
    })
    assert main(["--window", "1000000"], stdin=io.StringIO(payload)) == 0
    out = capsys.readouterr().out
    assert "10%" in out


def test_output_tokens_are_not_context(tmp_path):
    """What a call produced is not what it had to read."""
    payload = {"context_window": {"current_usage": {
        "input_tokens": 2, "cache_read_input_tokens": 104_154,
        "cache_creation_input_tokens": 1_632, "output_tokens": 591}}}
    assert statusline.payload_context(payload) == 105_788


def test_a_payload_without_the_context_block_falls_back_to_the_transcript(tmp_path):
    path = _transcript(tmp_path, [20_000] * 20, name="live")
    assert statusline.payload_context({}) is None
    assert statusline.payload_window({"context_window": {}}) is None
    assert line_for(path, current_context=None) == "ay 20K 2% 1.0x"


# -- The context denominator ---------------------------------------------------

def test_payload_model_reads_the_id():
    assert statusline.payload_model({"model": {"id": "claude-opus-5"}}) == "claude-opus-5"
    assert statusline.payload_model({"model": {}}) is None
    assert statusline.payload_model({"model": "claude-opus-5"}) is None
    assert statusline.payload_model({}) is None


def test_the_model_registry_supplies_the_window_when_the_payload_does_not(tmp_path, capsys):
    """A fraction against the wrong window is off by five, not by a little.

    Opus is 1M and Haiku is 200K, both observed in `modelUsage.contextWindow`.
    Falling straight to DEFAULT_WINDOW on a Haiku session would report a call
    at 75% of capacity as 15%, which is the regime the capacity family exists
    for and the one where it would go quiet.
    """
    transcript = _transcript(tmp_path, [150_000] * 20)
    payload = json.dumps({
        "transcript_path": str(transcript),
        "model": {"id": "claude-haiku-4-5-20251001"},
    })
    assert main([], stdin=io.StringIO(payload)) == 0
    line = capsys.readouterr().out.strip()
    # 150,000 of a 200,000 window is 75%. Against DEFAULT_WINDOW it is 15%.
    assert "75%" in line


def test_the_payload_window_still_beats_the_registry(tmp_path, capsys):
    transcript = _transcript(tmp_path, [100_000] * 20)
    payload = json.dumps({
        "transcript_path": str(transcript),
        "model": {"id": "claude-haiku-4-5-20251001"},
        "context_window": {"context_window_size": 500_000},
    })
    assert main([], stdin=io.StringIO(payload)) == 0
    # 100,000 of the session's own 500,000 is 20%; of the registry's 200,000
    # it would be 50%. The session knows better than the registry.
    assert "20%" in capsys.readouterr().out


# -- The allowance -------------------------------------------------------------

def test_the_seven_day_percentage_is_rendered_and_snapshotted(tmp_path, capsys, monkeypatch):
    """The one budget number on a plan that is not an equivalent of another.

    A dollar figure on a subscription is a list-price equivalent. This is what
    the plan actually rations, in the units it enforces.
    """
    log = tmp_path / "allowance.jsonl"
    monkeypatch.setattr(statusline, "SNAPSHOT_PATH", log)
    transcript = _transcript(tmp_path, [20_000] * 20)
    payload = json.dumps({
        "transcript_path": str(transcript),
        "rate_limits": {
            "seven_day": {"used_percentage": 34, "resets_at": "2026-08-30T00:00:00Z"},
            "five_hour": {"used_percentage": 61, "resets_at": "2026-08-26T15:00:00Z"},
        },
        "cost": {"total_cost_usd": 2.75},
    })
    assert main([], stdin=io.StringIO(payload)) == 0
    assert "7d 34%" in capsys.readouterr().out

    from agent_yield.allowance import load
    (held,) = load(log)
    assert held.seven_day == 34 and held.five_hour == 61
    assert held.session_dollars == 2.75


def test_a_client_reporting_no_limits_renders_no_allowance(tmp_path, capsys, monkeypatch):
    # Absent is not 0%: printing "7d 0%" would read as a fresh week.
    monkeypatch.setattr(statusline, "SNAPSHOT_PATH", tmp_path / "allowance.jsonl")
    transcript = _transcript(tmp_path, [20_000] * 20)
    payload = json.dumps({"transcript_path": str(transcript)})
    assert main([], stdin=io.StringIO(payload)) == 0
    out = capsys.readouterr().out
    assert "7d" not in out and out.strip() == "ay 20K 2% 1.0x"


def test_the_opening_baseline_counts_calls_and_not_content_blocks(tmp_path):
    """#61's second site: `_opening` took the first N records as N calls.

    Each call here writes three content-block records sharing message and
    request id, so an undeduped baseline sees the first ~3 calls instead of
    the first 10 -- and because context grows, it reads LOW, which makes the
    growth ratio the restart advice keys off read HIGH.
    """
    reads = list(range(10_000, 10_000 + 1_000 * 20, 1_000))  # 20 rising calls
    lines = []
    for index, read in enumerate(reads):
        for block in range(3):
            lines.append(json.dumps({
                "timestamp": f"2026-08-26T02:{index // 60:02d}:{index % 60:02d}.000Z",
                "sessionId": "blocks", "requestId": f"req-{index}",
                "message": {"id": f"msg-{index}",
                            "stop_reason": "end_turn" if block == 2 else None,
                            "usage": {"cache_read_input_tokens": read}},
            }))
    path = tmp_path / "blocks.jsonl"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # A head slice that holds well over 30 records -- i.e. over 10 calls --
    # while leaving the file long enough to take the sliced path at all.
    head = 3 * len(lines[0]) * 15
    assert head < path.stat().st_size
    line_for(path, tail_bytes=2_000, head_bytes=head,
             cache_path=tmp_path / "cache.json")
    held = json.loads((tmp_path / "cache.json").read_text(encoding="utf-8"))
    # Mean of calls 1-10, not of the three blocks each of calls 1-4.
    assert held == {"blocks:10": sum(reads[:10]) / 10}


# --- composition (#66) -----------------------------------------------------
#
# `statusLine` takes one command and a project settings.json REPLACES the user
# one, so an operator cannot have this line and their own from configuration
# alone. These pin the join, and above all that a broken segment cannot take
# the measurement down with it.

def test_compose_puts_segments_in_front_so_the_band_marker_ends_the_line():
    from agent_yield.statusline import SEPARATOR, compose_line

    line = compose_line("ay 111K 11% 2.5x GROWING",
                        ["echo alpha", "echo beta"], payload="{}")
    assert line == SEPARATOR.join(["alpha", "beta", "ay 111K 11% 2.5x GROWING"])
    # The marker is the point of the line, and the end is where it is seen.
    assert line.endswith("GROWING")


def test_a_segment_that_fails_contributes_nothing_and_the_line_survives():
    # Four ways to fail, and none of them may cost the measurement. A status
    # line is not a place to report that a status line broke.
    from agent_yield.statusline import compose_line

    own = "ay 111K 11% 2.5x"
    for command in ("exit 1", "definitely-not-a-command-xyz",
                    "echo boom >&2", "true"):
        assert compose_line(own, [command], payload="{}") == own


def test_a_slow_segment_is_dropped_rather_than_delaying_the_line():
    from agent_yield.statusline import compose_line

    own = "ay 111K 11% 2.5x"
    assert compose_line(own, ["sleep 5; echo late"], payload="{}",
                        timeout=0.3) == own


def test_every_segment_gets_the_same_payload_on_stdin():
    # The payload arrives on stdin exactly ONCE. Any wrapper has to buffer it
    # and hand each consumer its own copy; a wrapper that pipes it through
    # gives the second command an empty stream.
    from agent_yield.statusline import SEPARATOR, compose_line

    line = compose_line("ay -", ["cat", "cat"], payload='{"a":1}')
    assert line == SEPARATOR.join(['{"a":1}', '{"a":1}', "ay -"])


def test_only_the_first_line_of_a_chatty_segment_is_used():
    from agent_yield.statusline import SEPARATOR, compose_line

    line = compose_line("ay -", ["printf 'one\\ntwo\\n'"], payload="{}")
    assert line == SEPARATOR.join(["one", "ay -"])


def test_no_commands_leaves_the_line_byte_identical():
    from agent_yield.statusline import compose_line

    own = "ay 111K 11% 2.5x GROWING"
    assert compose_line(own) == own
    assert compose_line(own, [], payload="{}") == own


def test_main_composes_from_argv_and_still_prints_exactly_one_line(tmp_path,
                                                                  capsys):
    from agent_yield.statusline import main

    main(["--with", "echo alpha"], stdin=io.StringIO("{}"))
    out = capsys.readouterr().out
    assert out.count("\n") == 1
    assert out.startswith("alpha")
    assert out.rstrip().endswith("ay -")
