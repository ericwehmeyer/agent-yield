"""The guards, because each one only ever fires when nobody is watching.

Every test here drives `main` with the subprocess boundary stubbed. Nothing
invokes `claude`, reaches the tracker, or touches the real `.agent-yield/`:
this is the file that would otherwise put invented rows into a log the repo
treats as measurement.
"""

from __future__ import annotations

import importlib.util
import json
from datetime import timedelta
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "run-unattended.py"

spec = importlib.util.spec_from_file_location("run_unattended", SCRIPT)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


PICKED_LINE = "#113 every tool call runs a hook through migration-kit's virtualenv\n  marked ready-for-agent, unassigned, no open blockers (2 eligible of 59 open)"


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A checkout-shaped tmp dir, with the module's own paths anchored to it."""
    (tmp_path / ".git").mkdir()
    (tmp_path / ".agent-yield").mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(runner, "project_root", lambda *a, **k: tmp_path)
    return tmp_path


@pytest.fixture
def stubs(monkeypatch):
    """Stand in for every subprocess the runner makes, and record the calls."""
    calls = {"claimed": [], "claude": []}

    def fake_pick(python):
        return calls.get("pick", (0, PICKED_LINE))

    def fake_claude(brief, cwd, permission_mode, timeout, claude):
        calls["claude"].append({"brief": brief, "mode": permission_mode})
        return {"session_id": "s1", "num_turns": 4, "duration_ms": 1234,
                "total_cost_usd": 0.4212, "is_error": False,
                "usage": {"input_tokens": 12, "output_tokens": 3400,
                          "cache_read_input_tokens": 998_001,
                          "cache_creation_input_tokens": 41_000}}

    monkeypatch.setattr(runner, "pick", fake_pick)
    monkeypatch.setattr(runner, "issue_body", lambda number: "the body")
    monkeypatch.setattr(runner, "tree_is_dirty", lambda root: None)
    monkeypatch.setattr(runner, "claim",
                        lambda number, label: calls["claimed"].append((number, label)))
    monkeypatch.setattr(runner, "run_claude", fake_claude)
    return calls


def rows(repo):
    text = (repo / ".agent-yield" / "unattended.jsonl").read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


# --- the off switch -------------------------------------------------------

def test_stop_file_refuses_before_the_tracker_is_read(repo, stubs, monkeypatch, capsys):
    """STOP is checked first, so the loop stops even when gh is unreachable."""
    (repo / ".agent-yield" / "STOP").write_text("paused for the demo", encoding="utf-8")
    monkeypatch.setattr(runner, "pick",
                        lambda python: pytest.fail("the picker ran despite STOP"))
    assert runner.main([]) == 1
    assert "paused for the demo" in capsys.readouterr().out


def test_an_empty_stop_file_still_stops(repo):
    (repo / ".agent-yield" / "STOP").write_text("   \n", encoding="utf-8")
    assert runner.stop_requested(repo) == "STOP file present"


# --- the tree ------------------------------------------------------------

def test_a_dirty_tree_refuses_and_names_what_is_dirty(repo, stubs, monkeypatch, capsys):
    monkeypatch.setattr(runner, "tree_is_dirty", lambda root: " M src/agent_yield/gate.py")
    assert runner.main([]) == 1
    out = capsys.readouterr().out
    assert "not clean" in out and "gate.py" in out
    assert not stubs["claude"], "a run started on top of uncommitted work"


def test_allow_dirty_starts_anyway(repo, stubs, monkeypatch):
    monkeypatch.setattr(runner, "tree_is_dirty",
                        lambda root: pytest.fail("checked despite --allow-dirty"))
    assert runner.main(["--allow-dirty"]) == 0
    assert len(stubs["claude"]) == 1


# --- the picker's three exit codes ---------------------------------------

def test_the_allowance_band_saying_stop_exits_2(repo, stubs, monkeypatch, capsys):
    monkeypatch.setattr(runner, "pick", lambda python: (2, "STOP: 94% of the 7-day window"))
    assert runner.main([]) == 2
    assert "94%" in capsys.readouterr().out


def test_nothing_eligible_is_exit_0_because_a_quiet_night_is_not_a_failure(
        repo, stubs, monkeypatch):
    monkeypatch.setattr(runner, "pick", lambda python: (1, "nothing picked: 0 of 59"))
    assert runner.main([]) == 0


def test_a_first_line_that_is_not_an_issue_is_not_guessed_at():
    with pytest.raises(ValueError, match="not an issue"):
        runner.parse_pick("STOP: something else entirely")


def test_parse_pick_reads_the_number_and_title():
    assert runner.parse_pick(PICKED_LINE)[0] == 113
    assert runner.parse_pick(PICKED_LINE)[1].startswith("every tool call")


# --- the lock ------------------------------------------------------------

def test_a_live_lock_refuses_the_second_run(repo, stubs, capsys):
    runner.take_lock(repo, 4.0)
    assert runner.main([]) == 1
    assert "already holding" in capsys.readouterr().out
    assert not stubs["claude"]


def test_an_expired_lock_is_broken_and_the_break_is_reported(repo):
    stale = (runner.now() - timedelta(hours=9)).isoformat()
    path = repo / ".agent-yield" / "unattended.lock"
    path.write_text(json.dumps({"pid": 4242, "started_at": stale}), encoding="utf-8")
    _, broke = runner.take_lock(repo, 4.0)
    assert broke and "9.0h old" in broke and "4242" in broke


def test_an_unparseable_lock_is_treated_as_live(repo):
    (repo / ".agent-yield" / "unattended.lock").write_text("{{{", encoding="utf-8")
    with pytest.raises(RuntimeError, match="already holding"):
        runner.take_lock(repo, 4.0)


def test_the_lock_is_released_even_when_the_run_raises(repo, stubs, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("claude fell over")

    monkeypatch.setattr(runner, "run_claude", boom)
    with pytest.raises(RuntimeError):
        runner.main([])
    assert not (repo / ".agent-yield" / "unattended.lock").exists()


# --- the brief -----------------------------------------------------------

def test_the_brief_forbids_committing_by_default(repo, stubs):
    runner.main([])
    brief = stubs["claude"][0]["brief"]
    assert "Do NOT commit" in brief and "#171" in brief


def test_commit_names_a_branch_and_never_main(repo, stubs):
    runner.main(["--commit"])
    brief = stubs["claude"][0]["brief"]
    assert "unattended/113" in brief and "Closes #113" in brief
    assert "Do not touch `main`" in brief


def test_the_brief_carries_the_do_not_explore_prohibition(repo, stubs):
    """CLAUDE.md scores the range and the prohibition as one marker."""
    runner.main([])
    assert "Do not explore" in stubs["claude"][0]["brief"]


def test_the_brief_carries_the_issue_body_and_the_pytest_rule(repo, stubs):
    runner.main([])
    brief = stubs["claude"][0]["brief"]
    assert "the body" in brief and "-rs" in brief


# --- the claim and the log -----------------------------------------------

def test_the_issue_is_claimed_for_this_box_before_the_run(repo, stubs, monkeypatch):
    monkeypatch.setattr(runner.platform, "system", lambda: "Windows")
    runner.main([])
    assert stubs["claimed"] == [(113, "windows")]


def test_an_unknown_platform_claims_nothing_rather_than_guessing(monkeypatch):
    monkeypatch.setattr(runner.platform, "system", lambda: "Linux")
    assert "no machine label" in runner.claim(113, runner.MACHINE_LABELS.get("Linux"))


def test_every_run_appends_one_priced_row(repo, stubs):
    assert runner.main([]) == 0
    row, = rows(repo)
    assert row["issue"] == 113
    assert row["total_cost_usd"] == 0.4212
    assert row["cache_read_input_tokens"] == 998_001
    assert row["is_error"] is False
    assert row["started_at"] <= row["finished_at"]


def test_a_failed_run_is_logged_too_and_exits_1(repo, stubs, monkeypatch, capsys):
    monkeypatch.setattr(runner, "run_claude", lambda *a, **k: {
        "is_error": True, "error": "timed out after 3600s"})
    assert runner.main([]) == 1
    row, = rows(repo)
    assert row["is_error"] is True and "timed out" in row["error"]
    assert "timed out" in capsys.readouterr().out


def test_a_missing_claude_is_a_shaped_failure_not_a_traceback(repo, tmp_path):
    result = runner.run_claude("brief", tmp_path, "acceptEdits", 5,
                               "definitely-not-on-path-claude")
    assert result["is_error"] and "not on PATH" in result["error"]


def test_non_json_output_is_kept_rather_than_discarded(repo, tmp_path, monkeypatch):
    class Out:
        stdout, stderr, returncode = "Usage: claude [options]", "", 0

    monkeypatch.setattr(runner.subprocess, "run", lambda *a, **k: Out())
    result = runner.run_claude("brief", tmp_path, "acceptEdits", 5, "claude")
    assert result["is_error"] and result["raw"].startswith("Usage:")


# --- dry run -------------------------------------------------------------

def test_dry_run_claims_nothing_and_runs_nothing(repo, stubs, capsys):
    assert runner.main(["--dry-run"]) == 0
    assert stubs["claimed"] == [] and stubs["claude"] == []
    assert not (repo / ".agent-yield" / "unattended.jsonl").exists()
    assert "Do not explore" in capsys.readouterr().out


# --- the body is the body plus its comments ------------------------------

def test_comments_are_part_of_the_task_not_commentary(monkeypatch):
    """#113's second deliverable and #168's corpus decision are both comments."""
    payload = json.dumps({
        "body": "the original root cause",
        "comments": [{"body": "and clause 3 of #122 folds in here"},
                     {"body": ""},
                     {"body": "the machine question is decided"}],
    })

    class Out:
        stdout, stderr, returncode = payload, "", 0

    monkeypatch.setattr(runner.subprocess, "run", lambda *a, **k: Out())
    text = runner.issue_body(113)
    assert "the original root cause" in text
    assert "clause 3 of #122" in text
    assert "the machine question is decided" in text
    assert text.count("added later") == 2, "an empty comment became a section"


def test_a_tracker_that_cannot_be_read_yields_an_empty_body_not_a_crash(monkeypatch):
    class Out:
        stdout, stderr, returncode = "", "gh: not authenticated", 1

    monkeypatch.setattr(runner.subprocess, "run", lambda *a, **k: Out())
    assert runner.issue_body(113) == ""
