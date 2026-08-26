"""Discovery is where portability bugs land: the scratch root differs by OS."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from agent_yield.discovery import (
    default_roots,
    find_transcripts,
    scan_transcripts,
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


def _refuse(target: Path):
    """An `os.scandir` that cannot enter one directory.

    The real trigger for N4 is a path past MAX_PATH on a Windows box with
    `LongPathsEnabled` off, which is the default and is a per-machine registry
    setting nobody in this repo controls. It cannot be created on the box that
    has it on. Injecting the `OSError` the stdlib would raise is the same
    branch, on every platform, and it is what stops this from being deleted on
    a machine where the condition never arises.
    """
    real = os.scandir

    def fake(path="."):
        if Path(path) == Path(target):
            raise PermissionError(13, "cannot enter", str(target))
        return real(path)

    return fake


def test_a_subtree_the_walk_cannot_enter_is_counted_rather_than_dropped(
    tmp_path, monkeypatch
):
    """#64: a short list and a complete list must not look the same.

    `rglob` is built on `glob`, which catches `OSError` in six places on the
    scandir path. A subtree it cannot enter simply does not appear, the walk
    returns fewer files, `ingest` reports a smaller call count, and everything
    exits 0. Undercounting is the one error this tool's own docstrings say it
    exists to prevent, and here it happened with a clean exit.

    Measured on this machine: `~/.claude/projects` has a longest path of 166
    characters, and the scratch tree 288 -- already past the 260-character
    MAX_PATH limit. It works here only because `LongPathsEnabled = 1`.
    """
    reachable = tmp_path / "-slug"
    reachable.mkdir()
    (reachable / "a.jsonl").write_text("{}\n", encoding="utf-8")
    blocked = tmp_path / "-deep"
    blocked.mkdir()
    (blocked / "b.jsonl").write_text("{}\n", encoding="utf-8")

    monkeypatch.setattr(os, "scandir", _refuse(blocked))
    scan = scan_transcripts([tmp_path])

    assert scan.paths == [reachable / "a.jsonl"]
    assert scan.unreadable == (blocked,)


@pytest.mark.skipif(
    os.name == "nt", reason="mode bits do not deny scandir on Windows"
)
def test_an_unreadable_directory_is_really_unreadable(tmp_path):
    """The same claim without the injection, where the OS will honour it.

    The companion above proves the branch on every platform; this proves the
    branch is reachable by something other than a monkeypatch. Neither is
    sufficient alone -- that is the lesson N2 taught one file over.
    """
    reachable = tmp_path / "-slug"
    reachable.mkdir()
    (reachable / "a.jsonl").write_text("{}\n", encoding="utf-8")
    blocked = tmp_path / "-deep"
    blocked.mkdir()
    (blocked / "b.jsonl").write_text("{}\n", encoding="utf-8")

    blocked.chmod(0o000)
    try:
        if os.access(blocked, os.R_OK):
            pytest.skip("mode bits do not bind this user (running as root?)")
        scan = scan_transcripts([tmp_path])
        assert scan.paths == [reachable / "a.jsonl"]
        assert scan.unreadable == (blocked,)
    finally:
        blocked.chmod(0o700)


def test_find_transcripts_is_the_paths_of_a_scan(tmp_path):
    """The old name keeps the old shape: four callers want a plain list."""
    (tmp_path / "-slug").mkdir()
    (tmp_path / "-slug" / "a.jsonl").write_text("{}\n", encoding="utf-8")
    assert find_transcripts([tmp_path]) == scan_transcripts([tmp_path]).paths
