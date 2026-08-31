"""The guards, because each one only ever fires when nobody is watching.

Every test here drives `main` with the subprocess boundary stubbed. Nothing
invokes `claude`, reaches the tracker, or touches the real `.agent-yield/`:
this is the file that would otherwise put invented rows into a log the repo
treats as measurement.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
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

    def fake_claude(brief, cwd, permission_mode, timeout, claude,
                    denied=None, env=None):
        calls["claude"].append({"brief": brief, "mode": permission_mode,
                                "denied": denied, "env": env})
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

def test_the_brief_forbids_committing_when_there_is_no_key(repo, stubs, monkeypatch):
    """No signing identity, no commit -- whatever the flag says.

    The gate moved with #171. It is no longer `--commit` but whether the loop
    has a key of its own to sign with, because committing without one means
    signing as the operator, which is the whole defect.
    """
    monkeypatch.delenv(runner.SIGNING_KEY_ENV, raising=False)
    runner.main(["--commit"])
    brief = stubs["claude"][0]["brief"]
    assert "Do NOT commit" in brief and "#171" in brief
    assert rows(repo)[0]["committed"] is False


def test_no_commit_is_still_available_by_hand(repo, stubs):
    runner.main(["--no-commit", "--signing-key", "DEADBEEF"])
    assert "Do NOT commit" in stubs["claude"][0]["brief"]


def test_the_brief_tells_the_run_not_to_do_what_it_cannot(git_repo, stubs, monkeypatch):
    """Run 2 burned five turns on `git checkout -b` and was refused each time.

    The brief now names the branch it is already on and says the runner will
    commit, because asking an agent for something the harness will refuse is a
    brief defect, not an agent one.
    """
    monkeypatch.setattr(runner, "key_expiry", lambda *a, **k: None)
    monkeypatch.setattr(runner, "run_suite", lambda *a, **k: (True, "1 passed"))
    runner.main(["--signing-key", "DEADBEEF", "--signing-email", "a@b"])
    brief = stubs["claude"][0]["brief"]
    assert "Do not commit, branch or push" in brief
    assert "unattended/113" in brief
    assert "requires approval" in brief


def test_the_parent_makes_the_branch_before_the_run_starts(git_repo, stubs, monkeypatch):
    monkeypatch.setattr(runner, "key_expiry", lambda *a, **k: None)
    monkeypatch.setattr(runner, "run_suite", lambda *a, **k: (True, "1 passed"))
    runner.main(["--signing-key", "DEADBEEF", "--signing-email", "a@b"])
    head = subprocess.run(["git", "branch", "--show-current"], cwd=git_repo,
                          capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    assert head.stdout.strip() == "unattended/113"


def test_a_failing_suite_leaves_the_work_rather_than_committing_it(git_repo, stubs, monkeypatch):
    """Run 2 passed 21 of 21 in its own file while four failed elsewhere.

    The parent runs the whole suite, and a failure means the branch keeps the
    work uncommitted for a human instead of carrying a passing message.
    """
    monkeypatch.setattr(runner, "key_expiry", lambda *a, **k: None)
    monkeypatch.setattr(runner, "run_suite", lambda *a, **k: (False, "4 failed"))
    committed = []
    monkeypatch.setattr(runner, "commit_run",
                        lambda *a, **k: committed.append(a) or (None, "x"))
    runner.main(["--signing-key", "DEADBEEF", "--signing-email", "a@b"])
    assert committed == []
    row = rows(git_repo)[0]
    assert row["suite"] == "4 failed"
    assert "not committed" in row["commit_note"]


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


# --- #176: the guard is a denylist, because the allowlist was a comment ----

def test_the_denylist_covers_leaving_the_machine_and_signing_as_the_operator():
    denied = runner.DISALLOWED_TOOLS
    for pattern in ("Bash(git push*)", "Bash(git commit*)", "WebFetch",
                    "Bash(pip install*)", "Write(.agent-yield/STOP)"):
        assert pattern in denied, f"{pattern} is not denied"


def test_the_runner_passes_disallowed_not_allowed(repo, monkeypatch):
    """--allowed-tools measured additive on #176: it adds, never subtracts."""
    seen = {}

    class Out:
        stdout, stderr, returncode = '{"is_error": false}', "", 0

    def spy(cmd, **kwargs):
        seen["cmd"] = cmd
        return Out()

    monkeypatch.setattr(runner.subprocess, "run", spy)
    runner.run_claude("brief", repo, "acceptEdits", 5, "claude")
    assert "--disallowed-tools" in seen["cmd"]
    assert "--allowed-tools" not in seen["cmd"]


def test_denials_are_logged_because_they_indict_the_brief(repo, stubs, monkeypatch):
    monkeypatch.setattr(runner, "run_claude", lambda *a, **k: {
        "is_error": False, "num_turns": 3, "total_cost_usd": 0.1,
        "permission_denials": [{"tool_name": "Bash", "tool_input": {}},
                               {"tool_name": "WebFetch"}]})
    monkeypatch.setattr(runner, "figures_added_to_prose", lambda root: [])
    assert runner.main([]) == 0
    assert rows(repo)[0]["permission_denials"] == ["Bash", "WebFetch"]


# --- #175: figures the run put into prose ---------------------------------

DIFF = """diff --git a/docs/adr/0001.md b/docs/adr/0001.md
--- a/docs/adr/0001.md
+++ b/docs/adr/0001.md
@@ -56,0 +57 @@
+guard 156.8ms, gate 175.0ms, and 3,232 invocations in 2026
diff --git a/src/agent_yield/harness.py b/src/agent_yield/harness.py
--- a/src/agent_yield/harness.py
+++ b/src/agent_yield/harness.py
@@ -10,0 +11 @@
+TIMEOUT_MS = 5000
"""


def test_figures_in_prose_are_listed_and_code_constants_are_not(repo, monkeypatch):
    class Out:
        stdout, stderr, returncode = DIFF, "", 0

    monkeypatch.setattr(runner.subprocess, "run", lambda *a, **k: Out())
    found = runner.figures_added_to_prose(repo)
    assert "156.8" in found and "175.0" in found
    assert "5000" not in found, "a constant in code is not a claim in prose"


def test_a_figure_is_listed_once_however_often_it_repeats(repo, monkeypatch):
    text = ("--- a/docs/x.md\n+++ b/docs/x.md\n"
            "+62.1ms here\n+62.1ms again\n")

    class Out:
        stdout, stderr, returncode = text, "", 0

    monkeypatch.setattr(runner.subprocess, "run", lambda *a, **k: Out())
    assert runner.figures_added_to_prose(repo) == ["62.1"]


def test_the_run_prints_what_a_reviewer_has_to_check(repo, stubs, monkeypatch, capsys):
    monkeypatch.setattr(runner, "figures_added_to_prose", lambda root: ["156.8", "40"])
    assert runner.main([]) == 0
    out = capsys.readouterr().out
    assert "156.8" in out and "#175" in out
    assert rows(repo)[0]["figures_added"] == ["156.8", "40"]


def test_the_brief_forbids_a_number_that_no_command_produced(repo, stubs):
    runner.main([])
    brief = stubs["claude"][0]["brief"]
    assert "come from a command you ran" in brief
    assert "has failed even" in brief


# --- #171: the loop signs as itself, and a commit resolves to a run --------

@pytest.fixture
def git_repo(repo):
    """A real repository, because the audit reads commits rather than a stub.

    `commit.gpgsign` is pinned off locally: it is true in this operator's global
    config, and a fixture that inherits it makes four tests depend on a YubiKey
    being plugged in (#127).
    """
    subprocess.run(["git", "init", "-q", "-b", "main", "."], cwd=repo, check=True)
    for key, value in (("user.name", "T"), ("user.email", "t@t"),
                       ("commit.gpgsign", "false")):
        subprocess.run(["git", "config", key, value], cwd=repo, check=True)
    (repo / "seed.txt").write_text("seed", encoding="utf-8")
    subprocess.run(["git", "add", "seed.txt"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "seed"], cwd=repo, check=True,
                   capture_output=True)
    return repo


@pytest.fixture(autouse=True)
def no_inherited_key(monkeypatch):
    """The scheduled task sets these. A test that reads them measures the box.

    Without this the suite passes on a laptop and fails on the machine that
    actually runs the loop, which is the direction that hides a defect rather
    than showing one.
    """
    for name in (runner.SIGNING_KEY_ENV, runner.SIGNING_EMAIL_ENV):
        monkeypatch.delenv(name, raising=False)


def test_no_key_is_not_an_error_it_is_a_run_that_does_not_commit():
    identity, note = runner.signing_identity(None, None)
    assert identity is None
    assert runner.SIGNING_KEY_ENV in note and "#171" in note


def test_an_expired_key_refuses_rather_than_signing_with_it(monkeypatch):
    """A key that lapsed at 03:00 must not degrade into signing as the operator."""
    monkeypatch.setattr(runner, "key_expiry",
                        lambda *a, **k: runner.now() - timedelta(days=1))
    identity, note = runner.signing_identity("DEADBEEF", "a@b")
    assert identity is None
    assert "expired" in note


def test_a_key_expiring_soon_still_signs_but_says_so(monkeypatch):
    monkeypatch.setattr(runner, "key_expiry",
                        lambda *a, **k: runner.now() + timedelta(days=3))
    identity, note = runner.signing_identity("DEADBEEF", "a@b")
    assert identity is not None
    assert "3 day(s)" in note


def test_signing_env_overrides_the_child_and_writes_no_config(git_repo):
    """`GIT_CONFIG_*` reaches one process. `.git/config` reaches the operator.

    Writing user.signingkey into the clone would re-sign Eric's own commits in
    this repo with the machine key, which is a worse bug than #171.
    """
    before = (git_repo / ".git" / "config").read_text(encoding="utf-8")
    env = runner.signing_env({"key": "FPR", "email": "a@b"}, base={})
    pairs = {env[f"GIT_CONFIG_KEY_{i}"]: env[f"GIT_CONFIG_VALUE_{i}"]
             for i in range(int(env["GIT_CONFIG_COUNT"]))}
    assert pairs == {"user.signingkey": "FPR", "commit.gpgsign": "true"}
    assert env["GIT_AUTHOR_EMAIL"] == env["GIT_COMMITTER_EMAIL"] == "a@b"
    assert env["GIT_COMMITTER_NAME"] == runner.SIGNING_NAME
    assert (git_repo / ".git" / "config").read_text(encoding="utf-8") == before


def test_committing_is_allowed_out_of_the_denylist_only_when_signing_works():
    assert "Bash(git commit*)" in runner.disallowed_tools(False)
    assert "Bash(git commit*)" not in runner.disallowed_tools(True)
    # The entries that never come out, whatever else is true.
    for always in ("Bash(git push*)", "Bash(git tag*)", "Write(.agent-yield/STOP)"):
        assert always in runner.disallowed_tools(True)


def test_the_runner_passes_the_widened_denylist_and_the_env(git_repo, stubs, monkeypatch):
    monkeypatch.setattr(runner, "key_expiry", lambda *a, **k: None)
    monkeypatch.setattr(runner, "run_suite", lambda *a, **k: (True, "1 passed"))
    runner.main(["--signing-key", "FPR", "--signing-email", "a@b"])
    call = stubs["claude"][0]
    assert "Bash(git commit*)" not in call["denied"]
    assert call["env"]["GIT_CONFIG_VALUE_0"] == "FPR"


def test_a_commit_missing_its_trailer_is_reported_not_assumed(git_repo):
    """The audit reads commits; it does not take the brief's word for them."""
    before = runner.refs_now(git_repo)
    (git_repo / "a.txt").write_text("x", encoding="utf-8")
    subprocess.run(["git", "add", "a.txt"], cwd=git_repo, check=True)
    subprocess.run(["git", "-c", "commit.gpgsign=false", "commit", "-m", "no trailer"],
                   cwd=git_repo, check=True, capture_output=True)

    added, problems = runner.audit_commits(git_repo, before, {"key": "FPR"}, "run123")

    assert len(added) == 1
    assert any("not signed" in p for p in problems)
    assert any("Unattended-Run: run123" in p for p in problems)


def test_a_run_that_committed_with_the_trailer_is_clean(git_repo):
    before = runner.refs_now(git_repo)
    (git_repo / "a.txt").write_text("x", encoding="utf-8")
    subprocess.run(["git", "add", "a.txt"], cwd=git_repo, check=True)
    subprocess.run(["git", "-c", "commit.gpgsign=false", "commit",
                    "-m", "fix\n\nUnattended-Run: run123"],
                   cwd=git_repo, check=True, capture_output=True)

    added, problems = runner.audit_commits(git_repo, before, None, "run123")

    # identity None means the run was told not to commit, so committing at all
    # is the complaint -- and the trailer is not a second one.
    assert len(added) == 1
    assert problems == [f"{added[0][:7]} was committed by a run that had no "
                        "signing identity and was told not to commit"]


def test_the_commit_the_parent_writes_carries_the_id_the_audit_wants(git_repo, stubs, monkeypatch):
    """One string, two readers, and now one writer -- so they cannot diverge.

    The commit this makes is unsigned, and the audit says so. `signing_env` is
    stubbed so the suite-wide `commit.gpgsign = false` stands: a real signature
    needs the operator's key and, since the touch policy went to `Sign=on`, a
    hand on the YubiKey (#127). The one expected complaint is therefore named
    rather than filtered out, so a second one still fails -- and attribution,
    not the signature, is what this test is about.
    """
    monkeypatch.setattr(runner, "key_expiry", lambda *a, **k: None)
    monkeypatch.setattr(runner, "run_suite", lambda *a, **k: (True, "1 passed"))
    (git_repo / "fixed.txt").write_text("x", encoding="utf-8")
    monkeypatch.setattr(runner, "signing_env", lambda i, base=None: dict(os.environ))
    runner.main(["--signing-key", "FPR", "--signing-email", "a@b"])
    row = rows(git_repo)[0]
    body = subprocess.run(["git", "log", "-1", "--format=%B"], cwd=git_repo,
                          capture_output=True, text=True,
                          encoding="utf-8", errors="replace").stdout
    assert f"{runner.TRAILER}: {row['run_id']}" in body
    assert "Closes #113" in body
    assert len(row["commit_problems"]) == 1, row["commit_problems"]
    assert "is not signed" in row["commit_problems"][0], row["commit_problems"]


def test_the_row_carries_the_join_from_commit_back_to_cost(git_repo, stubs, monkeypatch):
    monkeypatch.setattr(runner, "key_expiry", lambda *a, **k: None)
    monkeypatch.setattr(runner, "run_suite", lambda *a, **k: (True, "1 passed"))
    runner.main(["--signing-key", "FPR", "--signing-email", "a@b"])
    row = rows(git_repo)[0]
    assert row["committed"] is True
    assert row["signing_key"] == "FPR"
    assert len(row["run_id"]) == 12
    assert row["branch"] == "unattended/113"
    assert row["suite"] == "1 passed"


def test_closes_after_the_trailer_does_not_hide_it(git_repo):
    """The shape a321c43 actually had, which reported itself unattributed.

    `Closes #N` has no colon, so git's trailer parser does not see a trailer
    block at all and `%(trailers)` comes back empty -- even though the line is
    right there in the message. The brief asks for both, so the audit reads the
    message rather than trusting the parser.
    """
    before = runner.refs_now(git_repo)
    (git_repo / "a.txt").write_text("x", encoding="utf-8")
    subprocess.run(["git", "add", "a.txt"], cwd=git_repo, check=True)
    subprocess.run(["git", "commit", "-m",
                    "#168: a fix\n\nUnattended-Run: run123\n\nCloses #168"],
                   cwd=git_repo, check=True, capture_output=True)

    # git itself sees nothing, which is the whole point of not asking it.
    trailers = subprocess.run(["git", "log", "-1", "--format=%(trailers)"],
                              cwd=git_repo, capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
    assert trailers.stdout.strip() == ""

    added, problems = runner.audit_commits(git_repo, before, {"key": "FPR"}, "run123")
    assert len(added) == 1
    assert not any("Unattended-Run" in p for p in problems), problems


def test_a_different_runs_id_is_still_caught(git_repo):
    """Reading the message must not degrade into matching any trailer at all."""
    before = runner.refs_now(git_repo)
    (git_repo / "a.txt").write_text("x", encoding="utf-8")
    subprocess.run(["git", "add", "a.txt"], cwd=git_repo, check=True)
    subprocess.run(["git", "commit", "-m", "fix\n\nUnattended-Run: someoneelse"],
                   cwd=git_repo, check=True, capture_output=True)

    _, problems = runner.audit_commits(git_repo, before, {"key": "FPR"}, "run123")
    assert any("Unattended-Run: run123" in p for p in problems)
