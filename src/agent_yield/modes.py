"""Work-mode tags. Recorded by the operator, never inferred.

A design conversation ships no merges; a mechanical sweep ships many cheap
commits. Inferring the mode from the shape of the work would let the tool pick
whichever denominator flatters the day.
"""
from __future__ import annotations

import tomllib
from collections.abc import Iterable
from pathlib import Path

VALID_MODES = frozenset({"build", "review", "design", "audit", "ops"})
UNTAGGED = "untagged"

_HEADER = (
    "# Work-mode tags. Recorded by the operator, never inferred.\n"
    "# Written by `agent-yield tag <session-id> <mode>`.\n\n"
)


class ModeError(ValueError):
    """A mode tag that is not one of the five."""


def load_modes(path: Path) -> dict[str, str]:
    path = Path(path)
    if not path.exists():
        return {}
    with path.open("rb") as handle:
        data = tomllib.load(handle)

    modes: dict[str, str] = {}
    for index, entry in enumerate(data.get("session", [])):
        where = f"{path}, session #{index + 1}"
        session_id = str(entry.get("id", "")).strip()
        mode = str(entry.get("mode", "")).strip()
        if not session_id:
            raise ModeError(f"{where}: 'id' is required")
        if mode not in VALID_MODES:
            raise ModeError(
                f"{where}: mode {mode!r} is not one of {sorted(VALID_MODES)}"
            )
        modes[session_id] = mode
    return modes


def mode_for(session_id: str | None, modes: dict[str, str]) -> str:
    """The recorded mode, or UNTAGGED. Never a guess."""
    if not session_id:
        return UNTAGGED
    return modes.get(session_id, UNTAGGED)


def record_mode(path: Path, session_id: str, mode: str) -> None:
    """Write one operator-recorded tag, updating an id already present.

    The whole file is rewritten from what `load_modes` read back, so an id
    recorded twice ends up tagged once. There is no tomllib writer, so the
    text is generated here -- which is why the id is refused if it carries a
    quote or a newline rather than emitting TOML that will not parse.
    """
    path = Path(path)
    session_id = str(session_id).strip()
    mode = str(mode).strip()
    if not session_id:
        raise ModeError("'id' is required")
    if any(ch in session_id for ch in ('"', "\n", "\r", "\\")):
        raise ModeError(
            f"session id {session_id!r} contains a quote, backslash or newline"
        )
    if mode not in VALID_MODES:
        raise ModeError(f"mode {mode!r} is not one of {sorted(VALID_MODES)}")

    modes = load_modes(path)
    modes[session_id] = mode

    body = "".join(
        f'[[session]]\nid = "{sid}"\nmode = "{tag}"\n\n'
        for sid, tag in modes.items()
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_HEADER + body, encoding="utf-8")


def tagged_sessions(path: Path) -> list[tuple[str, str]]:
    """(session id, mode) for every recorded tag, by id."""
    return sorted(load_modes(path).items())


def untagged_sessions(
    session_ids: Iterable[str | None], modes: dict[str, str]
) -> list[str]:
    """The ids with no recorded mode, in the order given.

    Order is the caller's -- the listing sorts by tokens, not by anything
    that would hint at what the mode is. This function knows nothing that
    could suggest one.
    """
    seen: set[str] = set()
    pending: list[str] = []
    for session_id in session_ids:
        if not session_id or session_id in modes or session_id in seen:
            continue
        seen.add(session_id)
        pending.append(session_id)
    return pending
