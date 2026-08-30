"""The template has to be judged by what it refuses to write down.

`6d35b47` shipped a `.claude/settings.json` naming
`C:/Users/ewehm/repos/agent-yield/.venv/Scripts/agent-yield.exe`, and pulling it
onto the Mac overwrote four working hooks with four that could not run -- an
ignored file, so git replaced it without a word (#125). Every test here is
about one of the two facts that made that possible: an absolute path belonging
to one person's home directory, and a `Scripts/…​.exe` layout belonging to one
operating system.

The four command strings are pinned. A template that still renders is worth
nothing if it renders a different instrument than the one the measurements were
taken under, and those measurements are already published.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from agent_yield import harness

REPO_ROOT = Path(__file__).resolve().parent.parent

# The exact four commands the Windows box was running at 6d35b47, as arguments.
# Pinned rather than derived: this is the instrument every figure in the repo
# was measured under, so a change here retires those figures and must be
# deliberate enough to edit a test.
PINNED_ARGUMENTS = [
    "resume --hook --probe",
    "gate --enforce-brief",
    "guard",
    "boundary --enforce",
]


def arguments_in(document: str) -> list[str]:
    """Every hook command with its executable removed, in document order."""
    found: list[str] = []

    def walk(node: object) -> None:
        if isinstance(node, dict):
            if node.get("type") == "command" and isinstance(node.get("command"), str):
                found.append(harness._split_executable(node["command"]))
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(json.loads(document))
    return found


def make_venv(root: Path, bindir: str, name: str) -> Path:
    executable = root / ".venv" / bindir / name
    executable.parent.mkdir(parents=True, exist_ok=True)
    executable.write_text("", encoding="utf-8")
    return executable


def make_project(root: Path, bindir: str = "bin", name: str = "agent-yield") -> Path:
    (root / ".claude").mkdir(parents=True, exist_ok=True)
    (root / harness.TEMPLATE_PATH).write_text(
        (REPO_ROOT / harness.TEMPLATE_PATH).read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    return make_venv(root, bindir, name)


# --- the tracked template names no machine -------------------------------

def test_the_template_carries_no_machine_fact():
    """The whole defect, as a rule over the committed bytes.

    Not a spot check on the paths that happen to be wrong today: any drive
    letter, any home directory, any Windows-only venv layout and any `.exe` is
    a fact about one box, and the tracked file is the one artefact that must
    hold for both.
    """
    text = (REPO_ROOT / harness.TEMPLATE_PATH).read_text(encoding="utf-8")
    banned = {
        "C:/": "a drive letter",
        "C:\\": "a drive letter",
        "/Users/": "a macOS home directory",
        "/home/": "a Linux home directory",
        "ewehm": "a user name",
        "ericw": "a user name",
        ".exe": "a Windows executable suffix",
        "Scripts": "the Windows venv layout",
        "/bin/": "the POSIX venv layout",
    }
    for needle, why in banned.items():
        assert needle not in text, f"{harness.TEMPLATE_PATH} contains {why}: {needle!r}"


def test_the_template_still_renders_the_four_hooks_that_were_measured():
    rendered = harness.render(
        (REPO_ROOT / harness.TEMPLATE_PATH).read_text(encoding="utf-8"),
        Path("/anywhere/.venv/bin/agent-yield"),
    )
    assert arguments_in(rendered) == PINNED_ARGUMENTS


def test_rendering_reproduces_the_windows_commands_byte_for_byte():
    """The other machine's file, regenerated from the template that replaced it.

    If this drifts, the Windows box's next `--install` silently changes the
    harness it has been measuring under, and nothing on that machine would say
    so.
    """
    windows = Path("C:/Users/ewehm/repos/agent-yield/.venv/Scripts/agent-yield.exe")
    rendered = harness.render(
        (REPO_ROOT / harness.TEMPLATE_PATH).read_text(encoding="utf-8"), windows
    )
    commands = [
        node["command"]
        for node in json.loads(rendered)["hooks"]["PreToolUse"][0]["hooks"]
    ]
    assert commands == [
        "C:/Users/ewehm/repos/agent-yield/.venv/Scripts/agent-yield.exe "
        "gate --enforce-brief"
    ]


# --- OS tolerance ---------------------------------------------------------

@pytest.mark.parametrize(
    "bindir,name",
    [("bin", "agent-yield"), ("Scripts", "agent-yield.exe"), ("Scripts", "agent-yield")],
)
def test_the_executable_is_found_by_looking_not_by_guessing(tmp_path, bindir, name):
    """Both layouts resolve on whichever OS the suite is running on.

    The point of probing rather than branching on `os.name`: a venv built under
    msys on Windows lays out `bin/`, and a branch would have declared it absent.
    """
    expected = make_venv(tmp_path, bindir, name)
    assert harness.resolve_executable(tmp_path) == expected


def test_this_platforms_layout_wins_when_both_are_present(tmp_path):
    make_venv(tmp_path, "bin", "agent-yield")
    make_venv(tmp_path, "Scripts", "agent-yield.exe")
    found = harness.resolve_executable(tmp_path)
    expected_dir = "Scripts" if os.name == "nt" else "bin"
    assert found.parent.name == expected_dir


def test_a_missing_venv_refuses_rather_than_rendering_a_dead_path(tmp_path):
    """Nothing is written. A hook pointing at an absent file is #125 again."""
    make_project(tmp_path)
    (tmp_path / ".venv" / "bin" / "agent-yield").unlink()
    with pytest.raises(harness.HarnessError) as excinfo:
        harness.check(tmp_path)
    assert "build the venv first" in str(excinfo.value)
    assert not (tmp_path / harness.LIVE_PATH).exists()


def test_a_path_with_a_space_is_quoted(tmp_path):
    assert harness.command_for(Path("/no/space/agent-yield")) == "/no/space/agent-yield"
    assert harness.command_for(
        Path("/has a space/agent-yield")
    ) == '"/has a space/agent-yield"'


def test_the_rendered_command_is_absolute_even_from_a_relative_root(tmp_path, monkeypatch):
    """A hook's working directory belongs to the harness, not to this repo."""
    make_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    code, _ = harness.install(Path("."))
    assert code == 0
    for command in json.loads(
        (tmp_path / harness.LIVE_PATH).read_text(encoding="utf-8")
    )["hooks"]["UserPromptSubmit"][0]["hooks"]:
        assert Path(command["command"].split(" ")[0]).is_absolute()


# --- install refuses to repeat the defect ---------------------------------

def test_install_replaces_another_machines_render(tmp_path):
    """Same instrument, different executable -- safe to replace, and replaced."""
    make_project(tmp_path)
    foreign = harness.render(
        (tmp_path / harness.TEMPLATE_PATH).read_text(encoding="utf-8"),
        Path("C:/Users/ewehm/repos/agent-yield/.venv/Scripts/agent-yield.exe"),
    )
    (tmp_path / harness.LIVE_PATH).write_text(foreign, encoding="utf-8")

    code, report = harness.install(tmp_path)

    assert code == 0
    assert "rendered" in report
    live = (tmp_path / harness.LIVE_PATH).read_text(encoding="utf-8")
    assert "ewehm" not in live
    assert arguments_in(live) == PINNED_ARGUMENTS


def test_install_refuses_a_file_it_did_not_write(tmp_path):
    """The lesson of #125, enforced against this tool itself.

    A live file carrying a hook the template does not have is somebody's work.
    Overwriting it without being asked is the mistake being fixed, so it exits
    nonzero, shows the diff, and leaves the bytes alone.
    """
    make_project(tmp_path)
    hand_written = json.dumps({
        "hooks": {
            "SessionStart": [{
                "hooks": [{"type": "command", "command": "/usr/bin/something else"}]
            }]
        }
    }, indent=2) + "\n"
    (tmp_path / harness.LIVE_PATH).write_text(hand_written, encoding="utf-8")

    code, report = harness.install(tmp_path)

    assert code == 1
    assert "REFUSING" in report
    assert (tmp_path / harness.LIVE_PATH).read_text(encoding="utf-8") == hand_written

    code, _ = harness.install(tmp_path, force=True)
    assert code == 0
    assert (tmp_path / harness.LIVE_PATH).read_text(encoding="utf-8") != hand_written


def test_install_is_idempotent(tmp_path):
    make_project(tmp_path)
    assert harness.install(tmp_path)[0] == 0
    code, report = harness.install(tmp_path)
    assert code == 0
    assert "already rendered" in report


# --- check names the failure rather than burying it in a diff -------------

def test_check_names_a_foreign_render(tmp_path):
    """#125's signature, said out loud.

    Thirteen lines of diff do not tell a reader that none of their hooks can
    have fired. That sentence has to be the first one.
    """
    make_project(tmp_path)
    (tmp_path / harness.LIVE_PATH).write_text(
        harness.render(
            (tmp_path / harness.TEMPLATE_PATH).read_text(encoding="utf-8"),
            Path("C:/Users/ewehm/repos/agent-yield/.venv/Scripts/agent-yield.exe"),
        ),
        encoding="utf-8",
    )
    code, report = harness.check(tmp_path)
    assert code == 1
    assert report.startswith("FOREIGN RENDER")
    assert "C:/Users/ewehm/repos/agent-yield/.venv/Scripts/agent-yield.exe" in report


def test_check_does_not_cry_foreign_over_a_local_edit(tmp_path):
    """A drifted-but-present executable is drift, not a foreign machine.

    Both report exit 1, so the distinction only exists if it is in the words.
    """
    make_project(tmp_path)
    harness.install(tmp_path)
    other = make_venv(tmp_path, "bin", "agent-yield-old")
    (tmp_path / harness.LIVE_PATH).write_text(
        harness.render(
            (tmp_path / harness.TEMPLATE_PATH).read_text(encoding="utf-8"), other
        ),
        encoding="utf-8",
    )
    code, report = harness.check(tmp_path)
    assert code == 1
    assert "FOREIGN RENDER" not in report
    assert "DRIFTS" in report


def test_check_reports_a_missing_live_file_as_no_hooks_at_all(tmp_path):
    make_project(tmp_path)
    code, report = harness.check(tmp_path)
    assert code == 1
    assert "MISSING" in report
    assert "--install" in report


# --- the CLI wiring, which is where the gate broke once before ------------

def test_the_subcommand_reaches_the_module(tmp_path):
    """Through `-m agent_yield.cli`, because `gate --enforce-brief` proved a
    subparser can accept a flag the module never sees (#116's neighbour)."""
    make_project(tmp_path)
    done = subprocess.run(
        [sys.executable, "-m", "agent_yield.cli", "harness",
         "--root", str(tmp_path), "--check"],
        capture_output=True, text=True, encoding="utf-8", cwd=REPO_ROOT,
    )
    assert done.returncode == 1, done.stderr
    assert "MISSING" in done.stdout

    done = subprocess.run(
        [sys.executable, "-m", "agent_yield.cli", "harness",
         "--root", str(tmp_path), "--install"],
        capture_output=True, text=True, encoding="utf-8", cwd=REPO_ROOT,
    )
    assert done.returncode == 0, done.stderr
    assert (tmp_path / harness.LIVE_PATH).is_file()


# --- this clone's own harness --------------------------------------------

@pytest.mark.skipif(
    harness.resolve_executable(REPO_ROOT) is None,
    reason="no .venv in this checkout, so there is no live harness to check",
)
def test_this_clone_is_running_the_template_it_ships():
    """The drift check #119 asks each machine to run and paste.

    Skipped rather than faked where there is no venv -- CI clones have none,
    and `-rs` puts the skip on screen instead of letting it read as a pass.
    """
    code, report = harness.check(REPO_ROOT)
    assert code == 0, report
