"""The launchd installer's refusals and the plist it writes.

Nothing here calls `launchctl`. Every test drives the script against a
checkout-shaped tmp dir with its own `$HOME`, so a run cannot register an
agent, boot one out, or read the operator's real `~/Library/LaunchAgents`.
That leaves the two things worth asserting: the guards refuse before writing
anything, and the plist carries the guarantees #177 asked for -- read back
with `plistlib` rather than grepped, because a plist that lints and a plist
that says what you meant are different claims.

Skipped on Windows, which has `install-scheduler.ps1` and no launchd.
"""

from __future__ import annotations

import platform
import plistlib
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "install-scheduler.sh"

pytestmark = [
    pytest.mark.skipif(
        platform.system() == "Windows",
        reason="the launchd installer is a POSIX shell script; Windows registers "
               "its task with scripts/install-scheduler.ps1",
    ),
    pytest.mark.skipif(
        shutil.which("bash") is None, reason="no bash on this machine"
    ),
]


@pytest.fixture
def repo(tmp_path):
    """A checkout-shaped tmp dir. The script derives $REPO from its own path."""
    (tmp_path / "scripts").mkdir()
    (tmp_path / ".venv" / "bin").mkdir(parents=True)
    interpreter = tmp_path / ".venv" / "bin" / "python"
    interpreter.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    interpreter.chmod(0o755)
    (tmp_path / "scripts" / "run-unattended.py").write_text("", encoding="utf-8")
    shutil.copy(SCRIPT, tmp_path / "scripts" / "install-scheduler.sh")
    (tmp_path / "home" / "Library" / "LaunchAgents").mkdir(parents=True)
    return tmp_path


READ_ONLY = ("--dry-run", "--status", "--uninstall", "--run-now", "--help")


def run(repo, *args):
    """Drive the installer, defaulting to a mode that cannot reach launchd.

    Three tests in the first draft of this file left `--dry-run` off. `$HOME`
    was a tmp dir, so nothing was written where it would survive -- but the
    script got past the refusals to `launchctl bootstrap gui/$UID`, and the
    domain is the operator's real one whatever `$HOME` says. An agent named
    `com.agent-yield.unattended` was really registered, pointing at a plist
    pytest then deleted, and only the assertion that followed said so.

    So the default is read-only and a test opts INTO writing by naming a mode.
    A guard against a test's own mistake belongs in the helper every test goes
    through, not in each test's argument list.
    """
    if not any(a in READ_ONLY for a in args):
        args = (*args, "--dry-run")
    return subprocess.run(
        ["bash", str(repo / "scripts" / "install-scheduler.sh"), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env={"HOME": str(repo / "home"), "PATH": "/usr/bin:/bin:/usr/sbin:/sbin"},
    )


def plist(result) -> dict:
    """The dry run's stdout, minus the trailing sentence, as a parsed plist."""
    body = result.stdout.split("</plist>")[0] + "</plist>\n"
    return plistlib.loads(body.encode("utf-8"))


# --- refusals, which all happen before anything is written -----------------

def test_it_refuses_an_interval_that_is_a_loop_not_a_schedule(repo):
    result = run(repo, "--interval-minutes", "4")
    assert result.returncode == 1
    assert "loop, not a schedule" in result.stderr
    assert not list((repo / "home" / "Library" / "LaunchAgents").iterdir())


def test_it_refuses_an_interval_that_is_not_a_number(repo):
    result = run(repo, "--interval-minutes", "hourly")
    assert result.returncode == 1
    assert "whole number" in result.stderr


def test_it_refuses_an_interpreter_that_is_not_there(repo):
    """An agent that fires hourly against a missing interpreter is a silent
    failure with a schedule."""
    (repo / ".venv" / "bin" / "python").unlink()
    result = run(repo, "--dry-run")
    assert result.returncode == 1
    assert "does not exist" in result.stderr


def test_it_refuses_a_label_that_would_not_name_a_plist(repo):
    result = run(repo, "--label", "agent/yield")
    assert result.returncode == 1
    assert "cannot be empty or contain" in result.stderr


def test_status_exits_2_when_nothing_is_registered(repo):
    """Exit 2 is the ps1's code for the same finding, and it is not an error."""
    result = run(repo, "--status")
    assert result.returncode == 2
    assert "no agent named" in result.stdout


def test_uninstalling_nothing_is_not_a_failure(repo):
    result = run(repo, "--uninstall")
    assert result.returncode == 0
    assert "nothing to remove" in result.stdout


# --- the plist ------------------------------------------------------------

def test_the_dry_run_writes_nothing_and_prints_only_a_plist(repo):
    """Warnings go to stderr so stdout stays parseable. The first draft put the
    no-signing-key warning on stdout and `plutil -lint` choked on line 1."""
    result = run(repo, "--dry-run")
    assert result.returncode == 0
    assert not list((repo / "home" / "Library" / "LaunchAgents").iterdir())
    assert result.stdout.startswith("<?xml")
    assert plist(result)["Label"] == "com.agent-yield.unattended"


def test_the_plist_carries_the_guarantees_task_scheduler_gives(repo):
    """#177's four, three as plist keys and the fourth in the invocation.

    launchd has no ExecutionTimeLimit, so the 2h cap is perl's alarm around the
    runner. `StartInterval` is the StartWhenAvailable equivalent: launchd fires
    a tick the machine slept through on wake.
    """
    parsed = plist(run(repo, "--interval-minutes", "30"))
    assert parsed["StartInterval"] == 30 * 60
    assert parsed["RunAtLoad"] is False
    assert parsed["WorkingDirectory"] == str(repo)

    args = parsed["ProgramArguments"]
    assert args[0].endswith("perl")
    assert args[1] == "-e" and "alarm" in args[2] and "exec" in args[2]
    assert args[3] == "7200", "the 2h wall-clock cap install-scheduler.ps1 sets"
    assert args[4] == str(repo / ".venv" / "bin" / "python")
    assert args[5] == str(repo / "scripts" / "run-unattended.py")


def test_the_plist_carries_a_path_because_a_launch_agent_inherits_none(repo):
    """A LaunchAgent gets launchd's PATH, which holds no `claude`. The Windows
    task runs in the interactive session to inherit one; this copies it."""
    parsed = plist(run(repo, "--dry-run"))
    assert parsed["EnvironmentVariables"]["PATH"] == "/usr/bin:/bin:/usr/sbin:/sbin"
    assert parsed["EnvironmentVariables"]["HOME"] == str(repo / "home")


def test_the_run_is_logged_somewhere_status_can_read_it(repo):
    """Task Scheduler records LastTaskResult; launchd records nothing unless
    the plist names files."""
    parsed = plist(run(repo, "--dry-run"))
    assert parsed["StandardOutPath"] == str(repo / ".agent-yield" / "scheduler.log")
    assert parsed["StandardErrorPath"] == str(repo / ".agent-yield" / "scheduler.err")


# --- signing, which a scheduled job cannot carry in its environment --------

def test_the_signing_identity_goes_on_the_argument_line(repo):
    args = plist(run(repo, "--signing-key", "FPR",
                     "--signing-email", "a@b"))["ProgramArguments"]
    assert args[-4:] == ["--signing-key", "FPR", "--signing-email", "a@b"]


def test_no_commit_reaches_the_argument_line(repo):
    args = plist(run(repo, "--no-commit"))["ProgramArguments"]
    assert "--no-commit" in args


def test_committing_with_no_key_warns_rather_than_refuses(repo):
    """The clone still runs; it just does not commit. #171."""
    result = run(repo, "--dry-run")
    assert result.returncode == 0
    assert "--no-commit" not in plist(result)["ProgramArguments"]
    assert "no --signing-key" in result.stderr


def test_a_missing_claude_warns_because_the_path_is_a_copy(repo):
    """`claude` is not on the stub PATH this fixture passes."""
    assert "not on this shell's PATH" in run(repo, "--dry-run").stderr
