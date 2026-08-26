"""Tests for measuring the session you are in."""

from __future__ import annotations

import json
import os
from pathlib import Path

from agent_yield.session import find_session, restart_advice, session_stats


def _line(
    *,
    session_id: str,
    index: int,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_creation: int = 0,
    cache_read: int = 0,
    sidechain: bool = False,
) -> str:
    record = {
        "timestamp": f"2026-08-26T12:{index // 60:02d}:{index % 60:02d}.000Z",
        "sessionId": session_id,
        "requestId": f"req-{session_id}-{index}",
        "message": {
            "id": f"msg-{session_id}-{index}",
            "usage": {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cache_creation_input_tokens": cache_creation,
                "cache_read_input_tokens": cache_read,
            },
        },
    }
    if sidechain:
        record["isSidechain"] = True
    return json.dumps(record)


def _write(path: Path, lines: list[str]) -> Path:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _rising(session_id: str, calls: int, *, start: int, step: int) -> list[str]:
    return [
        _line(
            session_id=session_id,
            index=i,
            input_tokens=100,
            output_tokens=50,
            cache_read=start + step * i,
        )
        for i in range(calls)
    ]


def test_growth_over_a_rising_series(tmp_path: Path) -> None:
    path = _write(tmp_path / "s1.jsonl", _rising("s1", 20, start=1_000, step=1_000))
    stats = session_stats(path, baseline_calls=10)

    assert stats.calls == 20
    # opening: cache_read 1000..10000 mean 5500, plus 100 input each.
    assert stats.opening_context_per_call == 5_600.0
    # last call: cache_read 20000 + input 100.
    assert stats.current_context == 20_100
    assert stats.growth == 20_100 / 5_600.0
    assert stats.growth > 3.0
    assert stats.context_per_call is not None
    assert stats.total.output_tokens == 20 * 50


def test_growth_is_none_when_calls_do_not_exceed_baseline(tmp_path: Path) -> None:
    path = _write(tmp_path / "s2.jsonl", _rising("s2", 10, start=1_000, step=1_000))
    stats = session_stats(path, baseline_calls=10)

    assert stats.calls == 10
    assert stats.growth is None
    assert stats.opening_context_per_call is None
    assert stats.current_context > 0


def test_empty_and_absent_transcripts_are_none_not_zero(tmp_path: Path) -> None:
    empty = _write(tmp_path / "empty.jsonl", [])
    stats = session_stats(empty)
    assert stats.calls == 0
    assert stats.context_per_call is None
    assert stats.opening_context_per_call is None
    assert stats.growth is None
    assert stats.total.total == 0

    missing = session_stats(tmp_path / "nope.jsonl")
    assert missing.calls == 0
    assert missing.context_per_call is None
    assert missing.growth is None


def test_restart_advice_below_factor_is_none(tmp_path: Path) -> None:
    # Flat context: growth is ~1x, no restart is due.
    lines = [
        _line(session_id="s3", index=i, input_tokens=100, cache_read=5_000)
        for i in range(20)
    ]
    stats = session_stats(_write(tmp_path / "s3.jsonl", lines), baseline_calls=10)

    assert stats.growth is not None
    assert restart_advice(stats) is None


def test_restart_advice_above_factor_names_both_numbers(tmp_path: Path) -> None:
    path = _write(tmp_path / "s4.jsonl", _rising("s4", 20, start=1_000, step=1_000))
    stats = session_stats(path, baseline_calls=10)

    advice = restart_advice(stats, factor=2.0)
    assert advice is not None
    assert advice.count("\n") == 0
    assert "5,600" in advice
    assert "20,100" in advice
    assert "20 calls" in advice
    assert "$" not in advice


def test_restart_advice_is_none_when_growth_is_none(tmp_path: Path) -> None:
    path = _write(tmp_path / "s5.jsonl", _rising("s5", 3, start=1_000, step=1_000))
    stats = session_stats(path, baseline_calls=10)

    assert stats.growth is None
    assert restart_advice(stats) is None


def test_sidechain_records_excluded_from_parent_stats(tmp_path: Path) -> None:
    lines = _rising("s6", 20, start=1_000, step=1_000)
    # A subagent line with a huge context, interleaved into the parent file.
    lines.insert(
        5,
        _line(
            session_id="s6",
            index=99,
            input_tokens=500_000,
            output_tokens=1_000,
            cache_read=500_000,
            sidechain=True,
        ),
    )
    path = _write(tmp_path / "s6.jsonl", lines)

    stats = session_stats(path, baseline_calls=10)
    clean = session_stats(
        _write(tmp_path / "s6-clean.jsonl", _rising("s6c", 20, start=1_000, step=1_000)),
        baseline_calls=10,
    )

    assert stats.calls == clean.calls == 20
    assert stats.opening_context_per_call == clean.opening_context_per_call
    assert stats.current_context == clean.current_context
    assert stats.growth == clean.growth
    assert stats.total.total == clean.total.total


def test_find_session_picks_the_newest_file(tmp_path: Path) -> None:
    old = _write(tmp_path / "old.jsonl", _rising("old", 3, start=100, step=100))
    new = _write(tmp_path / "new.jsonl", _rising("new", 3, start=100, step=100))
    os.utime(old, (1_000_000, 1_000_000))
    os.utime(new, (2_000_000, 2_000_000))

    assert find_session(None, root=tmp_path) == new


def test_find_session_by_id_and_unknown_id(tmp_path: Path) -> None:
    wanted = _write(tmp_path / "abc-123.jsonl", _rising("abc-123", 3, start=100, step=100))
    _write(tmp_path / "other.jsonl", _rising("other", 3, start=100, step=100))

    assert find_session("abc-123", root=tmp_path) == wanted
    assert find_session("no-such-session", root=tmp_path) is None
