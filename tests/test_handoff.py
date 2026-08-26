"""Tests for the handoff: what a restart destroys, written down first."""

from __future__ import annotations

import contextlib
import datetime as dt
import io
import json
import os
import pathlib
import subprocess
from pathlib import Path

from agent_yield import handoff as handoff_module
from agent_yield.handoff import (
    ARCHIVE_SUFFIX,
    NOTES_HEADING,
    SUPERSEDE_CONTAINMENT,
    build,
    consume,
    dirty_paths,
    existing_notes,
    landed_since,
    read,
    render,
    supersede,
    write,
)
from agent_yield.session import session_stats

NOW = dt.datetime(2026, 8, 26, 3, 0, tzinfo=dt.timezone.utc)


def _line(*, index: int, cache_read: int, session_id: str = "s1",
          output_tokens: int = 5, sidechain: bool = False) -> str:
    record = {
        "timestamp": f"2026-08-26T02:{index // 60:02d}:{index % 60:02d}.000Z",
        "sessionId": session_id,
        "requestId": f"req-{index}",
        "message": {
            "id": f"msg-{index}",
            "usage": {
                "input_tokens": 3,
                "output_tokens": output_tokens,
                "cache_creation_input_tokens": 7,
                "cache_read_input_tokens": cache_read,
            },
        },
    }
    if sidechain:
        record["isSidechain"] = True
    return json.dumps(record)


def _transcript(tmp_path: Path, calls: int = 20) -> Path:
    path = tmp_path / "s1.jsonl"
    lines = [_line(index=i, cache_read=1_000 * (i + 1)) for i in range(calls)]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@e",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@e"}
    def git(*args, when: str | None = None):
        full = dict(env)
        if when:
            full["GIT_AUTHOR_DATE"] = full["GIT_COMMITTER_DATE"] = when
        subprocess.run(["git", *args], cwd=repo, check=True,
                       capture_output=True, text=True,
                       env={**_environ(), **full})
    git("init", "-q")
    (repo / "old.txt").write_text("old\n", encoding="utf-8")
    git("add", "-A")
    git("commit", "-q", "-m", "before the session", when="2026-08-20T12:00:00 +0000")
    (repo / "new.txt").write_text("new\n", encoding="utf-8")
    git("add", "-A")
    git("commit", "-q", "-m", "during the session", when="2026-08-26T02:30:00 +0000")
    return repo


def _environ() -> dict:
    import os
    return dict(os.environ)


def test_the_four_usage_fields_stay_apart(tmp_path):
    stats = session_stats(_transcript(tmp_path))
    text = render(build(tmp_path, stats, now=NOW))
    for field in ("input", "output", "cache write", "cache read"):
        assert f"| {field} |" in text
    assert "| calls | 20 |" in text


def test_tokens_never_money(tmp_path):
    stats = session_stats(_transcript(tmp_path))
    assert "$" not in render(build(tmp_path, stats, now=NOW))


def test_unmeasurable_renders_as_a_dash_not_a_zero(tmp_path):
    short = tmp_path / "short.jsonl"
    short.write_text(_line(index=0, cache_read=10) + "\n", encoding="utf-8")
    stats = session_stats(short)
    text = render(build(tmp_path, stats, now=NOW))
    # One call: growth is unmeasurable, and must not read as "no growth".
    assert "| growth | - |" in text
    assert "| growth | 0" not in text


def test_no_transcript_says_so_rather_than_reporting_a_free_session(tmp_path):
    text = render(build(tmp_path, None, now=NOW))
    assert "no cost measurement" in text


def test_landed_lists_only_commits_since_the_session_started(tmp_path):
    repo = _repo(tmp_path)
    since = dt.datetime(2026, 8, 26, 0, 0, tzinfo=dt.timezone.utc)
    subjects = landed_since(repo, since)
    assert any("during the session" in s for s in subjects)
    assert not any("before the session" in s for s in subjects)


def test_landed_is_empty_when_the_session_start_is_unknown(tmp_path):
    assert landed_since(_repo(tmp_path), None) == []


def test_a_dirty_tree_is_announced_loudly_with_its_paths(tmp_path):
    repo = _repo(tmp_path)
    (repo / "unsaved.txt").write_text("half done\n", encoding="utf-8")
    text = render(build(repo, None, now=NOW))
    assert "DIRTY" in text
    assert "unsaved.txt" in text


def test_a_clean_tree_says_a_restart_loses_nothing_uncommitted(tmp_path):
    text = render(build(_repo(tmp_path), None, now=NOW))
    assert "Clean." in text


def test_outside_a_repository_the_tree_is_unknown_not_clean(tmp_path):
    assert dirty_paths(tmp_path) is None
    text = render(build(tmp_path, None, now=NOW))
    assert "Unknown" in text
    assert "Clean." not in text


def test_notes_come_from_the_operator_and_survive_regeneration(tmp_path):
    path = tmp_path / "handoff.md"
    write(path, render(build(tmp_path, None, ["thresholds half done"], now=NOW)))
    assert existing_notes(path) == ["thresholds half done"]

    carried = existing_notes(path) + ["and the hook is unmeasured"]
    write(path, render(build(tmp_path, None, carried, now=NOW)))
    assert existing_notes(path) == [
        "thresholds half done",
        "and the hook is unmeasured",
    ]


def test_an_empty_notes_section_reads_back_as_no_notes(tmp_path):
    path = tmp_path / "handoff.md"
    write(path, render(build(tmp_path, None, now=NOW)))
    assert existing_notes(path) == []
    assert NOTES_HEADING in path.read_text(encoding="utf-8")


def test_read_returns_none_when_there_is_no_handoff(tmp_path):
    assert read(tmp_path / "missing.md") is None


def test_write_creates_the_directory_it_is_pointed_at(tmp_path):
    path = handoff_module.write(tmp_path / "a" / "b" / "handoff.md", "# x\n")
    assert path.read_text(encoding="utf-8") == "# x\n"


def _written_at(path: Path, text: str, when: dt.datetime) -> None:
    write(path, text)
    stamp = when.timestamp()
    os.utime(path, (stamp, stamp))


def test_consume_returns_the_text_and_archives_the_file(tmp_path):
    path = tmp_path / "handoff.md"
    _written_at(path, "# handoff\n", NOW)
    assert consume(path, now=NOW) == "# handoff\n"
    assert not path.exists()
    assert (tmp_path / f"handoff.md{ARCHIVE_SUFFIX}").read_text(
        encoding="utf-8"
    ) == "# handoff\n"


def test_consume_a_second_time_returns_none(tmp_path):
    path = tmp_path / "handoff.md"
    _written_at(path, "# handoff\n", NOW)
    assert consume(path, now=NOW) == "# handoff\n"
    assert consume(path, now=NOW) is None


def test_consume_refuses_a_handoff_older_than_the_age_limit(tmp_path):
    path = tmp_path / "handoff.md"
    _written_at(path, "# handoff\n", NOW)
    stale = NOW + dt.timedelta(hours=handoff_module.MAX_HANDOFF_AGE_HOURS + 1)
    assert consume(path, now=stale) is None
    # Left in place -- the operator can still read it by hand.
    assert path.exists()
    assert read(path) == "# handoff\n"


def test_sidechain_calls_are_not_counted_as_the_parents_context(tmp_path):
    path = tmp_path / "s1.jsonl"
    lines = [_line(index=i, cache_read=1_000) for i in range(12)]
    lines.append(_line(index=99, cache_read=900_000, sidechain=True))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    text = render(build(tmp_path, session_stats(path), now=NOW))
    assert "| calls | 12 |" in text
    assert "900,000" not in text


def test_notes_from_a_previous_session_are_not_carried_forward(tmp_path):
    # Carrying notes forward across sessions was harmless while a human read
    # the file and judged what to believe. Once SessionStart injects it
    # automatically, three sessions of "NEXT ACTION" lines contradict each
    # other and the newest is indistinguishable from the oldest -- the real
    # file carried "implement #23" twice, hours after #23 had shipped.
    path = tmp_path / "handoff.md"
    path.write_text(
        "# Handoff -- session old-session\n\n"
        "## Claimed and unfinished\n\n"
        "- NEXT ACTION: implement the thing that is now done\n",
        encoding="utf-8",
    )
    assert handoff_module.existing_notes(path, "new-session") == []
    assert handoff_module.existing_notes(path, "old-session") == [
        "NEXT ACTION: implement the thing that is now done"
    ]
    # No session named: the old behaviour, for a caller that cannot know.
    assert len(handoff_module.existing_notes(path)) == 1


def test_a_handoff_without_the_session_header_carries_nothing(tmp_path):
    path = tmp_path / "handoff.md"
    path.write_text(
        "## Claimed and unfinished\n\n- a note with no header above it\n",
        encoding="utf-8",
    )
    assert handoff_module.existing_notes(path, "some-session") == []


# --- #40: a handoff must not carry every draft of a note ------------------

_NOTES = json.loads(
    (pathlib.Path(__file__).parent / "fixtures" / "handoff_notes.json").read_text()
)
DISTINCT_NOTES = _NOTES["distinct"]
RESTATED_NOTES = _NOTES["restatements"]


def test_six_genuinely_distinct_notes_stay_six():
    # The negative control, and the one that matters: a supersession rule that
    # eats a real note is worse than the repetition it was written to fix.
    assert supersede(DISTINCT_NOTES) == DISTINCT_NOTES


def test_progressive_restatements_collapse_to_the_latest():
    assert supersede(RESTATED_NOTES) == [RESTATED_NOTES[-1]]


def test_the_later_wording_wins_in_the_earlier_position():
    notes = [RESTATED_NOTES[0], DISTINCT_NOTES[0], RESTATED_NOTES[2]]
    # The order of the bullets is the writer's ordering of the work, so the
    # survivor keeps the slot the first draft claimed.
    assert supersede(notes) == [RESTATED_NOTES[2], DISTINCT_NOTES[0]]


def test_the_threshold_has_margin_on_the_measured_data():
    # 0.35 is the highest containment between any two of the six distinct
    # notes; 0.62 the lowest between any two restatements. If the constant
    # ever wanders out of that gap, this fails rather than degrading quietly.
    assert 0.35 < SUPERSEDE_CONTAINMENT < 0.62


def test_build_supersedes_and_an_empty_note_list_is_untouched():
    handoff = build(Path("."), None, notes=list(RESTATED_NOTES))
    assert handoff.notes == [RESTATED_NOTES[-1]]
    assert build(Path("."), None, notes=[]).notes == []


def test_a_blank_note_is_not_a_duplicate_of_everything():
    assert supersede(["", DISTINCT_NOTES[0], ""]) == ["", DISTINCT_NOTES[0], ""]


# --- #41: section marks come back mojibaked, and not from here ------------


def test_a_section_mark_survives_write_then_inject(tmp_path):
    # #41 measured "Â§12" and "§7" in the SAME injected payload on Windows,
    # and asked for the write path that omits encoding="utf-8". There is not
    # one -- every write_text/read_text/open in the package names it, and this
    # asserts the whole file->injection round trip rather than the file alone.
    # If this passes on Windows too, the corruption enters BEFORE the file:
    # through argv, the console code page, or the harness, not through here.
    note = "See working-method.md §12 and design.md §3.1 -- en dash – too."
    out = tmp_path / "handoff.md"
    text = render(build(Path("."), None, notes=[note]))
    write(out, text)

    assert note in out.read_text(encoding="utf-8")
    assert "Â§" not in out.read_text(encoding="utf-8")

    # ...and out through the hook, the way SessionStart actually receives it.
    from agent_yield import resume as resume_module

    stdout = io.StringIO()
    payload = {"session_id": "s", "source": "startup", "cwd": str(tmp_path)}
    with contextlib.redirect_stdout(stdout):
        resume_module.main(["--out", str(out)], stdin=io.StringIO(json.dumps(payload)))
    injected = json.loads(stdout.getvalue())["hookSpecificOutput"]["additionalContext"]
    assert note in injected
    assert "Â§" not in injected


def test_consume_replaces_an_archive_left_by_an_earlier_handoff(tmp_path):
    """The second handoff on a machine, which is where Windows broke.

    `Path.rename` is `os.rename`, and on Windows that raises FileExistsError
    when the destination exists, where POSIX silently overwrites. The archive
    from the previous consume was enough to make every later handoff vanish
    into `except OSError` and report itself as `no_handoff` (#42).

    Consuming twice in a row does not reach the rename -- the first consume
    moves the file away, so the second returns None at the read. Only a
    *newly written* handoff gets there.
    """
    path = tmp_path / "handoff.md"
    archive = tmp_path / f"handoff.md{ARCHIVE_SUFFIX}"

    _written_at(path, "# first\n", NOW)
    assert consume(path, now=NOW) == "# first\n"
    assert archive.read_text(encoding="utf-8") == "# first\n"

    _written_at(path, "# second\n", NOW)
    assert consume(path, now=NOW) == "# second\n"
    assert not path.exists()
    assert archive.read_text(encoding="utf-8") == "# second\n"
