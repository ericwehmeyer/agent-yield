"""The state directory follows the project, not the working directory.

`.gitignore` matches `.agent-yield/` at any depth, so a second store is
invisible to `git status` and to every reviewer. The Mac found seven of them
on one checkout, six strays holding 23% of the allowance snapshots ever taken
there (#154). Two of the eleven paths carry a guarantee rather than a
measurement, and those are the ones tested here.
"""

from __future__ import annotations

import os
from pathlib import Path

from agent_yield import boundary
from agent_yield.state import ROOT_ENV, anchored, project_root

from test_boundary import _grown


def test_the_root_is_the_checkout_not_the_cwd(tmp_path, monkeypatch):
    (tmp_path / ".git").mkdir()
    deep = tmp_path / "docs" / "experiments"
    deep.mkdir(parents=True)
    monkeypatch.chdir(deep)
    assert project_root() == tmp_path.resolve()
    assert anchored(Path(".agent-yield") / "x") == tmp_path.resolve() / ".agent-yield" / "x"


def test_an_absolute_path_is_left_alone(tmp_path):
    """Every test that points a constant at tmp_path depends on this."""
    assert anchored(tmp_path / "spent") == tmp_path / "spent"


def test_without_a_marker_it_falls_back_to_the_cwd(tmp_path, monkeypatch):
    """Old behaviour where there is no clue, so a chdir'd test stays put."""
    monkeypatch.chdir(tmp_path)
    assert project_root() == tmp_path.resolve()


def test_the_named_override_wins(tmp_path, monkeypatch):
    monkeypatch.setenv(ROOT_ENV, str(tmp_path))
    assert project_root() == tmp_path
    assert anchored(Path(".agent-yield") / "y") == tmp_path / ".agent-yield" / "y"


def test_one_refusal_per_session_survives_a_change_of_directory(tmp_path, monkeypatch):
    """The property #145 shipped, which a second state directory would break.

    Before anchoring, `REFUSAL_SPENT_PATH` resolved against the cwd, so a hook
    invoked from a subdirectory got a fresh refusal budget in a fresh file and
    "one per session" quietly became one per directory.
    """
    (tmp_path / ".git").mkdir()
    sub = tmp_path / "docs"
    sub.mkdir()
    monkeypatch.setattr(boundary, "REFUSAL_SPENT_PATH",
                        Path(".agent-yield") / "boundary-refusal-spent")
    payload = {"hook_event_name": "UserPromptSubmit", "session_id": "s"}
    common = dict(payload=payload, enforce=True, stats=_grown(tmp_path),
                  handoff_path=tmp_path / "none.md")

    monkeypatch.chdir(tmp_path)
    assert boundary.decide(**common)[0] == 2, "the first refusal should fire"
    monkeypatch.chdir(sub)
    assert boundary.decide(**common)[0] == 0, "a subdirectory is not a new session"

    stores = list(tmp_path.rglob(".agent-yield"))
    assert len(stores) == 1, f"one store, got {[str(s) for s in stores]}"
