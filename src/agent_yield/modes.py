"""Work-mode tags. Recorded by the operator, never inferred.

A design conversation ships no merges; a mechanical sweep ships many cheap
commits. Inferring the mode from the shape of the work would let the tool pick
whichever denominator flatters the day.
"""
from __future__ import annotations

import tomllib
from pathlib import Path

VALID_MODES = frozenset({"build", "review", "design", "audit", "ops"})
UNTAGGED = "untagged"


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
