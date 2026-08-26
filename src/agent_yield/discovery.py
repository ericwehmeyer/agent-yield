"""Where transcripts live.

Three locations, verified 2026-08-25 (Windows), 2026-08-25 and 2026-08-26 (macOS):

  main sessions  ~/.claude/projects/<project-slug>/<session-id>.jsonl
  subagents      <scratch>/<project-slug>/<session-id>/tasks/<agentId>.output
  subagents      ~/.claude/projects/<project-slug>/<session-id>/subagents/
                     agent-<agentId>.jsonl

**A third location, and it is the same file twice** -- found 2026-08-26 by the
#33 runs and by the audit those runs performed. Newer sessions write the agent
transcript under the *project* directory and leave the `tasks/*.output` entry as
a symlink to it: 84 of the 142 on this machine are symlinks, 58 are real files,
so both layouts are live at once and the older one is not gone. This root is
swept anyway, because `main_transcript_dir()` is walked recursively, which means
**every new agent transcript is seen twice** -- once directly and once through
the symlink. That is harmless only because a call is identified by
`(message_id, request_id)` and `ingest.load_records` dedups on it; `test_ingest`
pins it, because the day that dedup is relaxed this doubles the subagent bill.

The record still carries `isSidechain: true` in the new location (checked, not
assumed), so the main-against-subagent decomposition in §3.1 is unaffected.

`<scratch>` is *not* simply the OS temp directory. On Windows it is
`<temp>/claude`; on macOS Claude Code writes to `/tmp/claude-<uid>`, while
`tempfile.gettempdir()` resolves to the per-user `$TMPDIR` under
`/var/folders/...`, which holds no transcripts at all. Probing only the latter
finds nothing and -- because a missing root is skipped silently -- reports a
clean run over half the history. Both candidates are searched.

The scratch location is volatile: on the Windows machine 249 of 352 such files
were already empty, on the Mac 1 of 112. Read it early and persist what you
find. **The project-directory copy is not volatile in the same way** -- it lives
beside the main transcript and survives -- but nothing here depends on that, and
"read it early" costs nothing if it turns out to be durable.

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
