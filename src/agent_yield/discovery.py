"""Where transcripts live.

Two locations, verified 2026-08-25 (Windows) and 2026-08-25 (macOS):

  main sessions  ~/.claude/projects/<project-slug>/<session-id>.jsonl
  subagents      <scratch>/<project-slug>/<session-id>/tasks/<agentId>.output

`<scratch>` is *not* simply the OS temp directory. On Windows it is
`<temp>/claude`; on macOS Claude Code writes to `/tmp/claude-<uid>`, while
`tempfile.gettempdir()` resolves to the per-user `$TMPDIR` under
`/var/folders/...`, which holds no transcripts at all. Probing only the latter
finds nothing and -- because a missing root is skipped silently -- reports a
clean run over half the history. Both candidates are searched.

Either way the location is volatile: on the Windows machine 249 of 352 such
files were already empty, on the Mac 1 of 112. Read it early and persist what
you find.

The scratch tree also holds session `scratchpad/` directories full of unrelated
`.jsonl` working files -- 5,883 of them on the Mac. Only `tasks/*.output` under
that tree is a transcript.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path


def main_transcript_dir() -> Path:
    override = os.environ.get("CLAUDE_CONFIG_DIR")
    base = Path(override) if override else Path.home() / ".claude"
    return base / "projects"


def subagent_transcript_dirs() -> list[Path]:
    """Every plausible subagent scratch root, existing or not."""
    dirs = [Path(tempfile.gettempdir()) / "claude"]
    getuid = getattr(os, "getuid", None)
    if getuid is not None:
        dirs.append(Path("/tmp") / f"claude-{getuid()}")
    seen: set[Path] = set()
    return [d for d in dirs if not (d in seen or seen.add(d))]


def find_transcripts(roots: list[Path]) -> list[Path]:
    """Every transcript file under the given roots, in a stable order.

    A `.output` file counts only inside a `tasks/` directory, and nothing under
    a `scratchpad/` directory counts at all: the scratch tree mixes transcripts
    with session working files that happen to share the `.jsonl` suffix.
    """
    found: list[Path] = []
    for root in roots:
        root = Path(root)
        if not root.exists():
            continue
        if root.is_file():
            found.append(root)
            continue
        for path in root.rglob("*.jsonl"):
            if "scratchpad" not in path.parts:
                found.append(path)
        for path in root.rglob("*.output"):
            if path.parent.name == "tasks" and "scratchpad" not in path.parts:
                found.append(path)
    return sorted(set(found))


def default_roots() -> list[Path]:
    return [main_transcript_dir(), *subagent_transcript_dirs()]
