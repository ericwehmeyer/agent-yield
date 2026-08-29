"""Append a prediction to `interventions.toml` without risking the ones in it.

A prediction is only worth something if it was written down BEFORE the result,
so the file this appends to is append-only by intent and cannot be re-made
after the fact. It is also 33KB of prose that a hand-edit can invalidate in one
keystroke, and the loader's error then names the file rather than the edit --
so the entry that breaks it is not the one you lose.

Every check therefore runs BEFORE anything is written, and the write itself is
verified by reparsing the whole file and comparing the entry count. If either
fails, the original bytes go back. The alternative is a half-written entry,
which is a corrupt file, which is every prior prediction gone.

The validation deliberately mirrors `load_interventions`: a `name`, an
`expect`, and a `metric` this tool can actually compute. Refusing on write is
the same rule enforced where the operator can still do something about it,
rather than days later on the next read.
"""
from __future__ import annotations

import datetime as dt
import tomllib
from pathlib import Path

from .interventions import SCORABLE_METRICS


class PreregError(ValueError):
    """A pre-registration that would not survive being read back."""


# TOML's basic string escapes. Backslash first, or it doubles the ones the
# other rules just added. The control characters are not decoration: a stray
# newline inside a basic string is a parse error rather than a long line.
_ESCAPES = (
    ("\\", "\\\\"),
    ('"', '\\"'),
    ("\b", "\\b"),
    ("\f", "\\f"),
    ("\n", "\\n"),
    ("\r", "\\r"),
    ("\t", "\\t"),
)


def _escape(text: str) -> str:
    for raw, escaped in _ESCAPES:
        text = text.replace(raw, escaped)
    return "".join(
        char if char >= " " or char == "\x7f" else f"\\u{ord(char):04x}"
        for char in text
    )


def _as_date(value: str | dt.date) -> dt.date:
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    try:
        return dt.date.fromisoformat(str(value))
    except ValueError as exc:
        raise PreregError(f"bad 'date' {value!r}: want YYYY-MM-DD") from exc


def render_intervention(
    *,
    date: str | dt.date,
    name: str,
    expect: str,
    metric: str | None = None,
) -> str:
    """One `[[intervention]]` block, validated, as text.

    Separate from the write so the rendering can be tested and previewed
    without a file, and so `append_intervention` has nothing left to fail on
    once it has opened one.
    """
    name = str(name).strip()
    expect = str(expect).strip()
    if not name:
        raise PreregError("'name' is required: say what the intervention IS")
    # An intervention without a prediction is not an experiment. This is
    # `load_interventions`' own rule, moved to where it is still actionable.
    if not expect:
        raise PreregError(
            "'expect' is required and must say what you predict will change, "
            "with the bar that would falsify it"
        )
    if metric is not None and metric not in SCORABLE_METRICS:
        raise PreregError(
            f"metric {metric!r} is not one this tool can compute -- pick one "
            f"of {', '.join(SCORABLE_METRICS)}, or leave it out and the "
            f"report will say UNSCORABLE"
        )

    lines = [
        "",
        "[[intervention]]",
        f'date   = "{_as_date(date).isoformat()}"',
    ]
    if metric is not None:
        lines.append(f'metric = "{_escape(metric)}"')
    lines.append(f'name   = "{_escape(name)}"')
    lines.append(f'expect = "{_escape(expect)}"')
    return "\n".join(lines) + "\n"


def append_intervention(
    path: Path,
    *,
    date: str | dt.date,
    name: str,
    expect: str,
    metric: str | None = None,
) -> int:
    """Append one prediction. Returns the new entry count.

    The file is reparsed after the write and rolled back if it does not come
    back with exactly one more entry than it went in with. A pre-registration
    tool that can corrupt the pre-registrations is worse than editing by hand,
    because it looks like it checked.
    """
    path = Path(path)
    block = render_intervention(date=date, name=name, expect=expect, metric=metric)

    original = path.read_bytes() if path.exists() else None
    try:
        before = len(tomllib.loads(
            original.decode("utf-8") if original else ""
        ).get("intervention", []))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
        raise PreregError(
            f"{path} does not parse BEFORE this append, so nothing was "
            f"written: {exc}"
        ) from exc

    # newline="\n" because a Mac and a Windows box both append to this file
    # (audit N11). Without it the same prediction lands as \r\n here and \n
    # there, and the diff between the two machines is line endings rather than
    # predictions.
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(block)

    try:
        entries = tomllib.loads(path.read_text(encoding="utf-8"))["intervention"]
        if len(entries) != before + 1:
            raise PreregError(
                f"append produced {len(entries)} entries, expected {before + 1}"
            )
        if entries[-1]["name"] != name.strip():
            raise PreregError("the appended entry did not read back as itself")
    except Exception:
        if original is None:
            path.unlink(missing_ok=True)
        else:
            path.write_bytes(original)
        raise

    return before + 1
