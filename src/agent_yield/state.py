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


# --- Finding the stores that should not exist -------------------------------
#
# Anchoring stops new strays. It does nothing about the ones already written,
# and `.gitignore`'s `.agent-yield/` matches at any depth, so `git status` will
# never mention them. Six existed on the Mac holding 15 of the 66 allowance
# snapshots ever taken there. Neither machine could have found them by looking
# at the repo; each has to look at its own checkout.

STATE_DIR = ".agent-yield"

# Pruned rather than walked. `.venv` alone is tens of thousands of files and
# holds no state of ours; a scan that takes ten seconds is a scan nobody runs.
_SKIP = frozenset({".git", ".venv", "node_modules", "__pycache__", ".mypy_cache",
                   ".pytest_cache", ".ruff_cache", "site-packages"})


def stray_dirs(root: Path | None = None) -> list[Path]:
    """Every `.agent-yield/` under the project root except the root's own.

    Sorted, so two runs on the same tree report in the same order and a
    difference between them is a real difference.
    """
    base = Path(root) if root is not None else project_root()
    keep = (base / STATE_DIR).resolve()
    found = []
    for here, dirs, _files in os.walk(base):
        dirs[:] = [d for d in dirs if d not in _SKIP]
        if STATE_DIR in dirs:
            candidate = (Path(here) / STATE_DIR).resolve()
            if candidate != keep:
                found.append(candidate)
    return sorted(found)


def stray_files(root: Path | None = None) -> list[tuple[Path, int]]:
    """Each file in each stray store, with its line count.

    Lines, not bytes: every state file this package writes is JSONL or a small
    document, and a row count is the number a reader can act on. A file that
    cannot be read counts 0 rather than raising -- this is a diagnostic, and
    one unreadable file must not hide the other five directories.
    """
    out = []
    for directory in stray_dirs(root):
        for path in sorted(directory.iterdir()):
            if not path.is_file():
                continue
            try:
                rows = sum(1 for line in path.read_text(
                    encoding="utf-8", errors="replace").splitlines() if line.strip())
            except OSError:
                rows = 0
            out.append((path, rows))
    return out
