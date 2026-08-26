"""The handoff: write down what a restart destroys, before it does.

Nothing in Claude Code can restart a session -- no hook kills and respawns
one -- so "automate the restart" is really two jobs: make continuing refuse
to work, and make restarting nearly free.  This is the second one, and it
has to land first.  A restart is expensive today only because everything
not written down is lost; enforce a boundary before the handoff exists and
the operator will disable the boundary, correctly.

Read-only about the repository.  Every git call here is a query: no fetch,
no checkout, no history rewriting.  The one thing this module writes is the
handoff file the caller asks for.

What it deliberately does not do is infer what the operator was in the
middle of.  ``--note`` is the only route in for that, the same rule mode
tags follow: a tool that guesses what you were doing will guess
flatteringly, and the one section a fresh session most needs to trust is
the one saying what is claimed and unfinished.
"""

from __future__ import annotations

import datetime as dt
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .session import SessionStats

__all__ = [
    "Handoff",
    "DEFAULT_HANDOFF_PATH",
    "NOTES_HEADING",
    "landed_since",
    "dirty_paths",
    "existing_notes",
    "build",
    "render",
    "write",
    "read",
]

DEFAULT_HANDOFF_PATH = Path(".agent-yield") / "handoff.md"
NOTES_HEADING = "## Claimed and unfinished"


def _git(repo: Path, *args: str) -> str | None:
    """A git query. ``None`` when git could not answer -- never ``""``.

    outcomes.py collapses a failed invocation into an empty string, which is
    right there: no commits found and no repository both mean no outcomes.
    Here they do not. An empty `git status --porcelain` means a clean tree,
    and reporting "clean" for a directory that is not a repository at all
    would be a lie in the loud direction -- exactly the direction this file
    must not lie in.
    """
    try:
        result = subprocess.run(
            ["git", *args], cwd=repo, capture_output=True, text=True
        )
    except OSError:
        return None
    return result.stdout if result.returncode == 0 else None


def _git_time(moment: dt.datetime) -> str:
    """An unambiguous instant for ``--since``.

    git parses a bare `YYYY-MM-DD` with approxidate in the *local* timezone,
    which already cost this repo one real bug (`0502920`). Anchor to UTC
    explicitly and the window means the same thing on every machine.
    """
    return moment.astimezone(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S +0000")


@dataclass(frozen=True)
class Handoff:
    """Everything a fresh session would otherwise have to rediscover."""

    stats: SessionStats | None
    branch: str | None
    landed: list[str]
    dirty: list[str] | None
    notes: list[str]
    written: dt.datetime


def landed_since(repo: Path, since: dt.datetime | None) -> list[str]:
    """Subject lines of commits on this branch since ``since``.

    Empty when the moment is unknown: a handoff that cannot say which
    commits belong to this session says nothing rather than listing the
    whole history as if it did.
    """
    if since is None:
        return []
    out = _git(
        repo,
        "log",
        "--first-parent",
        "--pretty=%h %s",
        "--since",
        _git_time(since),
    )
    if out is None:
        return []
    return [line.strip() for line in out.splitlines() if line.strip()]


def dirty_paths(repo: Path) -> list[str] | None:
    """Paths with uncommitted work, or ``None`` when git could not say."""
    out = _git(repo, "status", "--porcelain")
    if out is None:
        return None
    return [line.rstrip() for line in out.splitlines() if line.strip()]


def current_branch(repo: Path) -> str | None:
    out = _git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    return out.strip() if out and out.strip() else None


def existing_notes(path: Path) -> list[str]:
    """Notes already recorded in a handoff at ``path``.

    Regenerating a handoff must not silently delete the one section a human
    wrote by hand, so previous notes are carried forward.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []

    notes: list[str] = []
    inside = False
    for line in text.splitlines():
        if line.startswith("## "):
            inside = line.strip() == NOTES_HEADING
            continue
        if not inside:
            continue
        stripped = line.strip()
        if stripped.startswith("- ") and not stripped.startswith("- ("):
            notes.append(stripped[2:].strip())
    return notes


def build(
    repo: Path,
    stats: SessionStats | None,
    notes: list[str] | None = None,
    now: dt.datetime | None = None,
) -> Handoff:
    since = stats.started if stats is not None else None
    return Handoff(
        stats=stats,
        branch=current_branch(repo),
        landed=landed_since(repo, since),
        dirty=dirty_paths(repo),
        notes=list(notes or []),
        written=now or dt.datetime.now(dt.timezone.utc),
    )


def _n(value: float | int | None, digits: int = 0) -> str:
    """A number, or `-`. Never `0` for something unmeasured."""
    if value is None:
        return "-"
    if digits:
        return f"{value:,.{digits}f}"
    return f"{round(value):,}"


def _cost_lines(stats: SessionStats | None) -> list[str]:
    if stats is None or stats.calls == 0:
        return ["No session transcript was readable, so this handoff carries "
                "no cost measurement."]
    usage = stats.total
    # The four fields stay apart. `.total` is for the display line only --
    # they bill at different rates and summing them hides which one grew.
    return [
        "| | |",
        "|---|---|",
        f"| calls | {stats.calls:,} |",
        f"| context/call, opening | {_n(stats.opening_context_per_call)} |",
        f"| context/call, mean | {_n(stats.context_per_call)} |",
        f"| context, current call | {stats.current_context:,} |",
        f"| growth | {'-' if stats.growth is None else f'{stats.growth:.1f}x'} |",
        f"| input | {usage.input_tokens:,} |",
        f"| output | {usage.output_tokens:,} |",
        f"| cache write | {usage.cache_creation_tokens:,} |",
        f"| cache read | {usage.cache_read_tokens:,} |",
        f"| total (display only) | {usage.total:,} |",
    ]


def render(handoff: Handoff) -> str:
    """The handoff as Markdown: readable by a person, `cat`-able by a hook."""
    stats = handoff.stats
    written = handoff.written.astimezone(dt.timezone.utc)
    name = stats.path.stem if stats is not None else "unknown session"

    lines = [
        f"# Handoff -- session {name}",
        "",
        f"Written {written:%Y-%m-%d %H:%M} UTC by `agent-yield handoff`, "
        "before a deliberate restart.",
        "",
        "## Session cost so far",
        "",
    ]
    lines += _cost_lines(stats)
    lines += ["", "## What landed", ""]
    branch = handoff.branch or "-"
    if handoff.landed:
        lines.append(f"On `{branch}`, since this session's first call:")
        lines.append("")
        lines += [f"- {subject}" for subject in handoff.landed]
    else:
        lines.append(f"Nothing on `{branch}` since this session's first call.")

    lines += ["", "## Working tree", ""]
    if handoff.dirty is None:
        lines.append("Unknown -- git could not report on this directory.")
    elif not handoff.dirty:
        lines.append("Clean. A restart here loses nothing uncommitted.")
    else:
        # Loudly. Restarting with uncommitted work is a different situation.
        lines.append(
            f"**DIRTY -- {len(handoff.dirty)} path(s) uncommitted.** "
            "A restart abandons this unless it is committed or stashed first."
        )
        lines.append("")
        lines += [f"- `{entry}`" for entry in handoff.dirty]

    lines += ["", NOTES_HEADING, ""]
    if handoff.notes:
        lines += [f"- {note}" for note in handoff.notes]
    else:
        lines.append(
            "- (nothing recorded -- "
            "`agent-yield handoff --note \"what is half-done\"`)"
        )
    lines.append("")
    return "\n".join(lines)


def write(path: Path, text: str) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def read(path: Path) -> str | None:
    """The handoff at ``path``, or ``None`` when there is none to read."""
    try:
        return Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
