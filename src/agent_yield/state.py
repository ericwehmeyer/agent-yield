"""Where this project's state lives, resolved once instead of eleven times.

Every state path in this package was `Path(".agent-yield") / name`, resolved
against whatever working directory the process inherited. For a hook invoked
at the repo root that is correct and invisible. For anything else it silently
makes a second store: the Mac found seven `.agent-yield/` directories on one
checkout, six of them strays holding 23% of the allowance snapshots ever taken
there, and `.gitignore`'s `.agent-yield/` matches at any depth so `git status`
never mentioned them (#154).

Two of those paths carry a correctness guarantee rather than a measurement.
`boundary-refusal-spent` is what makes a refusal one-shot, so a second store
means a second refusal budget and the property degrades to one per directory.
`handoff.md` is what the next session loads, so a handoff written from a
subdirectory is one that `resume` will not find -- a handoff going missing
silently is the exact failure the boundary exists to prevent.

`anchored` leaves absolute paths alone, which is what keeps every test that
points a constant at `tmp_path` working unchanged.
"""

from __future__ import annotations

import os
from pathlib import Path

__all__ = ["ROOT_ENV", "project_root", "anchored"]

# Named, like the override envs in boundary and gate: an operator who has to
# put state somewhere else should be able to say so, not discover it moved.
ROOT_ENV = "AGENT_YIELD_ROOT"


def project_root(start: Path | None = None) -> Path:
    """The checkout this state belongs to, or the cwd when there is no clue.

    Walks up for `.git`. Falling back to the cwd rather than raising keeps the
    old behaviour anywhere the marker is absent -- including a test that has
    chdir'd into a temporary directory, which must keep writing there and not
    into the real repo.
    """
    override = os.environ.get(ROOT_ENV)
    if override:
        return Path(override)
    try:
        here = Path(start) if start is not None else Path.cwd()
        here = here.resolve()
    except OSError:
        return Path(".")
    for candidate in (here, *here.parents):
        if (candidate / ".git").exists():
            return candidate
    return here


def anchored(path: Path | str, start: Path | None = None) -> Path:
    """Anchor a relative state path to the project root, not the cwd."""
    target = Path(path)
    if target.is_absolute():
        return target
    return project_root(start) / target
