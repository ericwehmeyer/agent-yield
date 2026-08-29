"""The guard has to be judged by what it lets through, not by what it stops.

Its predecessor -- a `"if": "Bash(git add -A*)"` matcher in `settings.json` --
stopped `git add -A` correctly and also refused a bare `cat` heredoc, a
`gh issue create --body "$(cat <<EOF ...)"`, a python heredoc and a `for` loop
containing a quoted grep pattern. That is the failure that cost something: the
issue-tracker doc tells agents to file tickets with a heredoc body, so the guard
blocked the documented way to file a ticket, and a guard like that gets turned
off. So the ALLOW cases below are the real commands measured as wrongly refused
on 2026-08-28, copied as commands rather than paraphrased, and the expectations
come from that measurement -- not from what the hook currently returns.

The hook is run as a real child process on a real stdin pipe, never imported:
the defect class this repo tracks lives in how a process reads and decodes its
input, and an in-process call would not exercise it.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

def run_hook(payload: dict) -> subprocess.CompletedProcess:
    """Through the CLI, which is the entry point settings.json actually calls.

    `-m agent_yield.cli` rather than the module directly: the wiring between
    subparser and hook is where the dispatch gate broke on 2026-08-28, so the
    thing under test is the whole invocation and not the matcher alone.
    """
    return subprocess.run(
        [sys.executable, "-m", "agent_yield.cli", "guard"],
        input=json.dumps(payload).encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def run_bash(command: str) -> subprocess.CompletedProcess:
    return run_hook({
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": command},
    })


HEREDOC_CAT = """cat <<EOF
a plain body, several lines long,
and the word git add -A appears in it as prose
EOF"""

HEREDOC_GH_ISSUE = '''gh issue create --title "guard scopes wrongly" --body "$(cat <<EOF
The matcher refuses commands that never run `git add -A`.

Closes nothing yet.
EOF
)"'''

HEREDOC_PYTHON = """.venv/Scripts/python.exe - <<'PY'
import json, pathlib
rows = [json.loads(l) for l in pathlib.Path("x.jsonl").read_text().splitlines()]
print(len(rows))
PY"""

FOR_LOOP = 'for f in a b; do grep -n "pat" "$f"; done'


@pytest.mark.parametrize("command", [
    "git add -A",
    "git add --all",
    "git add .",
    "git add --verbose -A",
    "git -C /tmp/x add -A",
    "cd /x && git add -A",
])
def test_tree_wide_add_is_refused(command):
    """The six shapes the rule exists to stop, including the two the old matcher
    missed entirely: a `-C` prefix and a stage hidden behind `&&`."""
    result = run_bash(command)
    assert result.returncode == 2, result.stderr.decode("utf-8", "replace")


@pytest.mark.parametrize("command", [
    HEREDOC_CAT,
    HEREDOC_GH_ISSUE,
    HEREDOC_PYTHON,
    FOR_LOOP,
])
def test_the_four_commands_measured_as_wrongly_refused_now_pass(command):
    """Derived from the 2026-08-28 measurement: `cat <<EOF`, the `gh issue
    create` heredoc body from docs/agents/issue-tracker.md, a multi-line python
    heredoc, and a `for` loop with a quoted grep pattern. None of them runs
    `git add`; all four were refused."""
    result = run_bash(command)
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")


@pytest.mark.parametrize("command", [
    "git add src/foo.py",
    "git add tests/",
    'echo "git add -A"',
])
def test_named_paths_and_quoted_text_pass(command):
    """`git add src/foo.py` and `git add tests/` are the staging the rule asks
    for. `echo "git add -A"` is the quoted-argument case: text, not a command."""
    result = run_bash(command)
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")


def test_a_non_bash_payload_passes():
    """A Write call carrying `git add -A` in the file it writes. The hook acts on
    Bash and nothing else."""
    result = run_hook({
        "hook_event_name": "PreToolUse",
        "tool_name": "Write",
        "tool_input": {"file_path": "notes.md", "content": "run git add -A here"},
    })
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")


def test_the_refusal_names_the_rule_and_where_it_is_written():
    """A refusal that only says no gets worked around. This one has to say what
    to do instead -- stage named paths -- and point at CLAUDE.md."""
    result = run_bash("git add -A")
    message = result.stderr.decode("utf-8", "replace")
    assert "stage the whole working tree" in message or "stages the whole working tree" in message
    assert "Stage named paths" in message
    assert "CLAUDE.md" in message
