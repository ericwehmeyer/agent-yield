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
