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
from dataclasses import dataclass
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


@dataclass(frozen=True)
class TranscriptScan:
    """What a walk found, and what it could not reach.

    `unreadable` exists because the alternative is a silent zero. `rglob` is
    built on `glob`, which catches `OSError` in six places on its scandir
    path, so a subtree the process cannot enter simply does not appear: the
    walk returns fewer files, `ingest` reports a smaller call count, and the
    command exits 0. Undercounting is the one error this tool exists to
    prevent, and a short list that looks like a complete list is the worst
    possible way to do it.

    Measured on this machine 2026-08-26: `~/.claude/projects` has a longest
    path of 166 characters and the scratch tree 288 -- already past the
    260-character MAX_PATH limit. It works here only because
    `LongPathsEnabled = 1` in the registry, which is off by default and is a
    per-machine setting nobody in this repo controls. No attempt is made to
    solve long paths; the fix is to stop the two cases looking alike.
    """

    paths: list[Path]
    roots: tuple[Path, ...]
    unreadable: tuple[Path, ...]


def scan_transcripts(roots: list[Path]) -> TranscriptScan:
    """Every transcript file under the given roots, plus what was unreachable.

    A `.output` file counts only inside a `tasks/` directory, and nothing under
    a `scratchpad/` directory counts at all: the scratch tree mixes transcripts
    with session working files that happen to share the `.jsonl` suffix.

    `os.walk` rather than `rglob` for one reason: it takes an `onerror`
    callback. Neither follows directory symlinks, so what is found is
    unchanged.
    """
    found: list[Path] = []
    walked: list[Path] = []
    unreadable: list[Path] = []

    def note(error: OSError) -> None:
        name = getattr(error, "filename", None)
        unreadable.append(Path(name) if name else Path("<unknown>"))

    for root in roots:
        root = Path(root)
        if not root.exists():
            continue
        if root.is_file():
            found.append(root)
            walked.append(root)
            continue
        walked.append(root)
        for dirpath, dirnames, filenames in os.walk(root, onerror=note):
            here = Path(dirpath)
            if "scratchpad" in here.parts:
                dirnames[:] = []
                continue
            for name in filenames:
                if name.endswith(".jsonl"):
                    found.append(here / name)
                elif name.endswith(".output") and here.name == "tasks":
                    found.append(here / name)

    return TranscriptScan(
        paths=sorted(set(found)),
        roots=tuple(walked),
        unreadable=tuple(dict.fromkeys(unreadable)),
    )


def find_transcripts(roots: list[Path]) -> list[Path]:
    """Every transcript file under the given roots, in a stable order.

    The paths of a :func:`scan_transcripts`, for the callers that only want
    the files. Anything that reports a count to a human should use the scan --
    see :class:`TranscriptScan` for why.
    """
    return scan_transcripts(roots).paths


def default_roots() -> list[Path]:
    return [main_transcript_dir(), *subagent_transcript_dirs()]
