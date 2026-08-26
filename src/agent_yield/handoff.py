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
import re
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
    "consume",
    "ARCHIVE_SUFFIX",
    "MAX_HANDOFF_AGE_HOURS",
]

DEFAULT_HANDOFF_PATH = Path(".agent-yield") / "handoff.md"
NOTES_HEADING = "## Claimed and unfinished"
ARCHIVE_SUFFIX = ".loaded"
MAX_HANDOFF_AGE_HOURS = 24


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


def existing_notes(path: Path, session_id: str | None = None) -> list[str]:
    """Notes already recorded in a handoff at ``path``.

    Regenerating a handoff must not silently delete the one section a human
    wrote by hand, so previous notes are carried forward -- but only within
    one session. Notes written by a session that has ended describe a session
    that no longer exists, which is the same argument that makes a stale
    handoff worse than none (see `consume`). Carrying them forward was
    harmless while a human read the file and chose what to believe; once
    SessionStart injects it automatically, three sessions of accumulated
    "NEXT ACTION" lines contradict each other and the newest is not
    distinguishable from the oldest. Measured on the real file: it carried
    "implement #23" twice, hours after #23 shipped.

    ``session_id`` is the session doing the writing. When it is given and the
    file names a different session, nothing is carried.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []

    if session_id is not None:
        first = text.splitlines()[0] if text.splitlines() else ""
        # The header render is `# Handoff -- session <id>`; a file that does
        # not name this session is a previous session's, and is not carried.
        if not first.startswith("# Handoff -- session ") or \
                first[len("# Handoff -- session "):].strip() != session_id:
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


# #40: a handoff regenerated mid-session carried every draft of a note as well
# as the note. Four bullets on the Windows file were progressive restatements
# of one paragraph -- ~2,800 of 3,716 characters -- and this file is not a
# display, it is context, re-billed on every call of the session it is
# injected into.
#
# The threshold is measured, not chosen. On the six real notes of the handoff
# this repo actually injected on 2026-08-25, all of them genuinely distinct,
# the highest containment between any pair is 0.35. On the three restatements
# quoted in #40 it is 0.62-0.80. 0.5 sits in the gap with margin on both
# sides, and the quoted restatements are elided, so a full one overlaps more.
SUPERSEDE_CONTAINMENT = 0.5

_WORD_RE = re.compile(r"[a-z0-9#.\-]+")


def _words(note: str) -> set[str]:
    return set(_WORD_RE.findall(note.lower()))


def supersede(notes: list[str]) -> list[str]:
    """Drop earlier drafts of a note that a later one restates.

    Containment rather than Jaccard, and of the *shorter* note in the longer:
    a restatement usually grows as it is edited, and the question being asked
    is "does the later note already say what the earlier one said", which is
    asymmetric. The later wording wins, in the earlier one's position -- the
    order of the bullets is the writer's ordering of the work, and the first
    bullet is by convention the next action.

    Only near-duplicates are collapsed. Six distinct notes stay six.
    """
    kept: list[str] = []
    kept_words: list[set[str]] = []
    for note in notes:
        words = _words(note)
        replaced = False
        for index in range(len(kept) - 1, -1, -1):
            earlier = kept_words[index]
            smaller = min(len(words), len(earlier))
            if not smaller:
                continue
            if len(words & earlier) / smaller >= SUPERSEDE_CONTAINMENT:
                kept[index] = note
                kept_words[index] = words
                replaced = True
                break
        if not replaced:
            kept.append(note)
            kept_words.append(words)
    return kept


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
        notes=supersede(list(notes or [])),
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


def consume(
    path: Path,
    now: dt.datetime | None = None,
    max_age_hours: float = MAX_HANDOFF_AGE_HOURS,
) -> str | None:
    """Read the handoff and archive it, so it can never be loaded twice.

    The rename to ``path`` + :data:`ARCHIVE_SUFFIX` is what makes injection
    exactly-once -- there is no separate state file to fall out of sync with
    the handoff it describes. A second call, in this session or the next,
    finds nothing left at ``path`` and returns ``None``, same as if there
    had never been a handoff.

    A handoff older than ``max_age_hours`` (by mtime) also returns ``None``,
    but is deliberately left where it is: a session that would inject stale
    context is worse than one that injects nothing, but the operator can
    still `agent-yield resume --read` it by hand.
    """
    path = Path(path)
    try:
        mtime = dt.datetime.fromtimestamp(path.stat().st_mtime, tz=dt.timezone.utc)
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    moment = now if now is not None else dt.datetime.now(dt.timezone.utc)
    age_hours = (moment - mtime).total_seconds() / 3600
    if age_hours > max_age_hours:
        return None
    try:
        path.rename(path.with_name(path.name + ARCHIVE_SUFFIX))
    except OSError:
        return None
    return text
