"""Where transcripts live.

Two locations, verified 2026-08-25:

  main sessions  ~/.claude/projects/<project-slug>/<session-id>.jsonl
  subagents      <temp>/claude/<project-slug>/<session-id>/tasks/<agentId>.output

The second is under the OS temp directory and is volatile -- on the machine
this was verified against, 249 of 352 such files were already empty. Read it
early and persist what you find.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path


def main_transcript_dir() -> Path:
    override = os.environ.get("CLAUDE_CONFIG_DIR")
    base = Path(override) if override else Path.home() / ".claude"
    return base / "projects"


def subagent_transcript_dir() -> Path:
    return Path(tempfile.gettempdir()) / "claude"


def find_transcripts(roots: list[Path]) -> list[Path]:
    """Every transcript file under the given roots, in a stable order."""
    found: list[Path] = []
    for root in roots:
        root = Path(root)
        if not root.exists():
            continue
        if root.is_file():
            found.append(root)
            continue
        found.extend(root.rglob("*.jsonl"))
        found.extend(root.rglob("*.output"))
    return sorted(set(found))


def default_roots() -> list[Path]:
    return [main_transcript_dir(), subagent_transcript_dir()]
