"""Discovery is where portability bugs land: the scratch root differs by OS."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from agent_yield.discovery import (
    default_roots,
    find_transcripts,
    main_transcript_dir,
    subagent_transcript_dirs,
)


def test_main_dir_follows_the_config_override(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    assert main_transcript_dir() == tmp_path / "projects"


@pytest.mark.skipif(not hasattr(os, "getuid"), reason="POSIX only")
def test_posix_offers_the_uid_scratch_root():
    """On macOS the transcripts are under /tmp/claude-<uid>, not $TMPDIR."""
    assert Path("/tmp") / f"claude-{os.getuid()}" in subagent_transcript_dirs()


def test_default_roots_include_every_scratch_candidate():
    roots = default_roots()
    assert roots[0] == main_transcript_dir()
    assert set(subagent_transcript_dirs()) <= set(roots)


def test_a_missing_root_is_skipped_not_fatal(tmp_path):
    assert find_transcripts([tmp_path / "nope"]) == []


def test_scratchpad_working_files_are_not_transcripts(tmp_path):
    """A session's scratchpad is full of unrelated .jsonl data files."""
    session = tmp_path / "-slug" / "session"
    (session / "tasks").mkdir(parents=True)
    (session / "scratchpad" / "job5").mkdir(parents=True)
    real = session / "tasks" / "abc123.output"
    real.write_text("{}\n")
    (session / "scratchpad" / "job5" / "candidate.jsonl").write_text("{}\n")
    (session / "scratchpad" / "stray.output").write_text("{}\n")

    assert find_transcripts([tmp_path]) == [real]


def test_output_files_count_only_inside_tasks(tmp_path):
    (tmp_path / "tasks").mkdir()
    inside = tmp_path / "tasks" / "agent.output"
    inside.write_text("{}\n")
    (tmp_path / "loose.output").write_text("{}\n")

    assert find_transcripts([tmp_path]) == [inside]


def test_main_transcripts_are_found_by_suffix(tmp_path):
    (tmp_path / "-slug").mkdir()
    session = tmp_path / "-slug" / "s1.jsonl"
    session.write_text("{}\n")
    assert find_transcripts([tmp_path]) == [session]


def test_a_file_root_is_taken_as_given(tmp_path):
    path = tmp_path / "anything.txt"
    path.write_text("{}\n")
    assert find_transcripts([path]) == [path]


def test_roots_are_deduplicated_and_ordered(tmp_path):
    (tmp_path / "b.jsonl").write_text("{}\n")
    (tmp_path / "a.jsonl").write_text("{}\n")
    found = find_transcripts([tmp_path, tmp_path])
    assert found == sorted(set(found))
    assert [p.name for p in found] == ["a.jsonl", "b.jsonl"]
