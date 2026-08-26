"""Tests for the dispatch-length audit (#18 Part C).

The join is a heuristic -- same session, same subagent type, nearest child
starting after the dispatch -- so most of these tests are about the ways it
must refuse to guess, not the happy path.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from agent_yield.agents import (
    DISPATCH_CALL_CAP,
    MAX_JOIN_LAG_SECONDS,
    join,
    read_agent_runs,
    read_dispatches,
    render,
)

BASE = dt.datetime(2026, 8, 26, 2, 0, tzinfo=dt.timezone.utc)

BRIEFED = (
    "Read src/foo.py with sed -n '10,80p'. Do not explore the repo. "
    "Write your findings to docs/notes/foo.md. "
    "Return only the file:line of each hit, nothing else."
)
UNBRIEFED = "Have a look at the auth code and tell me what you think."


def _stamp(offset_seconds: float) -> str:
    return (BASE + dt.timedelta(seconds=offset_seconds)).isoformat()


def _dispatch_line(session, offset, subagent_type, prompt, description="d"):
    return json.dumps({
        "sessionId": session,
        "timestamp": _stamp(offset),
        "type": "assistant",
        "message": {
            "role": "assistant",
            "content": [{
                "type": "tool_use",
                "id": f"toolu_{subagent_type}_{offset}",
                "name": "Task",
                "input": {
                    "subagent_type": subagent_type,
                    "description": description,
                    "prompt": prompt,
                },
            }],
        },
    })


def _agent_call(session, agent_id, offset, subagent_type, request):
    return json.dumps({
        "sessionId": session,
        "agentId": agent_id,
        "attributionAgent": subagent_type,
        "isSidechain": True,
        "timestamp": _stamp(offset),
        "requestId": request,
        "type": "assistant",
        "message": {
            "id": f"msg_{request}",
            "role": "assistant",
            "usage": {
                "input_tokens": 10,
                "output_tokens": 5,
                "cache_read_input_tokens": 1_000,
                "cache_creation_input_tokens": 0,
            },
        },
    })


def _write(path: Path, lines: list[str]) -> Path:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _main(tmp_path, lines) -> list[Path]:
    return [_write(tmp_path / "main.jsonl", lines)]


def test_reads_a_dispatch_and_scores_its_markers(tmp_path):
    paths = _main(tmp_path, [
        _dispatch_line("s1", 0, "general-purpose", BRIEFED),
        _dispatch_line("s1", 10, "general-purpose", UNBRIEFED),
    ])
    dispatches = read_dispatches(paths)
    assert len(dispatches) == 2
    assert dispatches[0].missing == ()
    assert set(dispatches[1].missing) == {
        "line ranges", "output path", "return contract"
    }
    assert dispatches[0].subagent_type == "general-purpose"


def test_explore_and_plan_are_exempt(tmp_path):
    paths = _main(tmp_path, [
        _dispatch_line("s1", 0, "Explore", UNBRIEFED),
        _dispatch_line("s1", 5, "Plan", UNBRIEFED),
        _dispatch_line("s1", 9, "general-purpose", UNBRIEFED),
    ])
    dispatches = read_dispatches(paths)
    assert [d.exempt for d in dispatches] == [True, True, False]


def test_join_matches_the_child_that_followed(tmp_path):
    main = _main(tmp_path, [
        _dispatch_line("s1", 0, "general-purpose", BRIEFED, "first"),
        _dispatch_line("s1", 300, "general-purpose", UNBRIEFED, "second"),
    ])
    a1 = _write(tmp_path / "a1.output", [
        _agent_call("s1", "agent-1", 1.5, "general-purpose", f"r{i}")
        for i in range(3)
    ])
    a2 = _write(tmp_path / "a2.output", [
        _agent_call("s1", "agent-2", 301.5, "general-purpose", f"q{i}")
        for i in range(12)
    ])
    audits, orphans = join(read_dispatches(main), read_agent_runs([a1, a2]))

    assert orphans == []
    assert audits[0].run.agent_id == "agent-1"
    assert audits[0].run.calls == 3
    assert audits[0].briefed is True
    assert audits[0].over_cap is False

    assert audits[1].run.agent_id == "agent-2"
    assert audits[1].run.calls == 12
    assert audits[1].briefed is False
    assert audits[1].over_cap is True, f"12 > {DISPATCH_CALL_CAP}"


def test_a_run_is_claimed_at_most_once(tmp_path):
    """Two dispatches, one child: the second must report unlinked, not steal."""
    main = _main(tmp_path, [
        _dispatch_line("s1", 0, "general-purpose", BRIEFED, "first"),
        _dispatch_line("s1", 2, "general-purpose", BRIEFED, "second"),
    ])
    only = _write(tmp_path / "a1.output", [
        _agent_call("s1", "agent-1", 3, "general-purpose", "r1")
    ])
    audits, orphans = join(read_dispatches(main), read_agent_runs([only]))
    linked = [a for a in audits if a.run is not None]
    assert len(linked) == 1
    assert orphans == []


def test_join_refuses_across_sessions_and_types(tmp_path):
    """A wrong join attributes one agent's cost to another's brief."""
    main = _main(tmp_path, [
        _dispatch_line("s1", 0, "general-purpose", BRIEFED),
    ])
    other_session = _write(tmp_path / "a1.output", [
        _agent_call("s2", "agent-1", 1.5, "general-purpose", "r1")
    ])
    other_type = _write(tmp_path / "a2.output", [
        _agent_call("s1", "agent-2", 1.5, "code-reviewer", "r2")
    ])
    audits, orphans = join(
        read_dispatches(main), read_agent_runs([other_session, other_type])
    )
    assert audits[0].run is None
    assert len(orphans) == 2, "both must be reported, not silently dropped"


def test_join_refuses_outside_the_lag_window(tmp_path):
    main = _main(tmp_path, [_dispatch_line("s1", 0, "general-purpose", BRIEFED)])
    late = _write(tmp_path / "a1.output", [
        _agent_call("s1", "agent-1", MAX_JOIN_LAG_SECONDS + 30,
                    "general-purpose", "r1")
    ])
    audits, orphans = join(read_dispatches(main), read_agent_runs([late]))
    assert audits[0].run is None
    assert len(orphans) == 1


def test_a_child_starting_before_its_dispatch_is_not_a_match(tmp_path):
    """Causality is the one thing the heuristic can be sure of."""
    main = _main(tmp_path, [_dispatch_line("s1", 100, "general-purpose", BRIEFED)])
    early = _write(tmp_path / "a1.output", [
        _agent_call("s1", "agent-1", 50, "general-purpose", "r1")
    ])
    audits, orphans = join(read_dispatches(main), read_agent_runs([early]))
    assert audits[0].run is None
    assert len(orphans) == 1


def test_plain_text_output_files_are_skipped_not_counted(tmp_path):
    """`tasks/*.output` is a mix: 12 of 15 parsed as JSONL on the real corpus.

    A write-up must not become a zero-call run -- that would invent a
    dispatch that held perfectly to the cap.
    """
    prose = tmp_path / "memo.output"
    prose.write_text("Here is my report.\n\nIt was fine.\n", encoding="utf-8")
    assert read_agent_runs([prose]) == []


def test_calls_are_deduped_the_way_ingest_dedups(tmp_path):
    """One record per tool_use block, one call per requestId (§'Do not re-derive')."""
    dup = _write(tmp_path / "a1.output", [
        _agent_call("s1", "agent-1", 1, "general-purpose", "same"),
        _agent_call("s1", "agent-1", 2, "general-purpose", "same"),
        _agent_call("s1", "agent-1", 3, "general-purpose", "other"),
    ])
    runs = read_agent_runs([dup])
    assert runs[0].calls == 2, "identical (message_id, request_id) is one call"


def test_render_scores_both_rubrics_and_excludes_exempt(tmp_path):
    main = _main(tmp_path, [
        _dispatch_line("s1", 0, "general-purpose", BRIEFED, "briefed"),
        _dispatch_line("s1", 300, "general-purpose", UNBRIEFED, "unbriefed"),
        _dispatch_line("s1", 600, "Explore", UNBRIEFED, "exploring"),
    ])
    a1 = _write(tmp_path / "a1.output", [
        _agent_call("s1", "agent-1", 1.5, "general-purpose", f"r{i}")
        for i in range(4)
    ])
    a2 = _write(tmp_path / "a2.output", [
        _agent_call("s1", "agent-2", 301.5, "general-purpose", f"q{i}")
        for i in range(40)
    ])
    a3 = _write(tmp_path / "a3.output", [
        _agent_call("s1", "agent-3", 601.5, "Explore", f"e{i}")
        for i in range(90)
    ])
    audits, orphans = join(
        read_dispatches(main), read_agent_runs([a1, a2, a3])
    )
    out = render(audits, orphans)

    assert "1 exempt (Explore)" in out
    # the exempt 90-call run must not be scored against either rubric
    assert "§11 length: 1/2 over" in out
    assert "§12 brief:  1/2 carried all three markers" in out
    assert "briefed median 4 calls vs un-briefed 40" in out


def test_render_says_when_the_join_failed(tmp_path):
    """A join whose failures are invisible is one that always 'works'."""
    main = _main(tmp_path, [_dispatch_line("s1", 0, "general-purpose", BRIEFED)])
    stray = _write(tmp_path / "a1.output", [
        _agent_call("s9", "agent-9", 1.5, "general-purpose", "r1")
    ])
    audits, orphans = join(read_dispatches(main), read_agent_runs([stray]))
    out = render(audits, orphans, show_unlinked=True)
    assert "1 agent transcript(s) matched no dispatch" in out
    assert "agent-9" in out
    assert "unlinked" in out
