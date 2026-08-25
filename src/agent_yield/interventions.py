"""Process changes, on the record, with a prediction attached."""
from __future__ import annotations

import datetime as dt
import tomllib
from dataclasses import dataclass
from pathlib import Path


class InterventionError(ValueError):
    """An intervention file that cannot be trusted to mean what it says."""


@dataclass(frozen=True)
class Intervention:
    date: dt.date
    name: str
    expect: str


def load_interventions(path: Path) -> list[Intervention]:
    path = Path(path)
    if not path.exists():
        return []
    with path.open("rb") as handle:
        data = tomllib.load(handle)

    out: list[Intervention] = []
    for index, entry in enumerate(data.get("intervention", [])):
        where = f"{path}, intervention #{index + 1}"
        raw_date = entry.get("date")
        name = str(entry.get("name", "")).strip()
        expect = str(entry.get("expect", "")).strip()
        if not name:
            raise InterventionError(f"{where}: 'name' is required")
        # An intervention without a prediction is not an experiment. Refusing
        # it here is the whole reason this loader exists.
        if not expect:
            raise InterventionError(
                f"{where} ({name!r}): 'expect' is required and must say what "
                f"you predict will change"
            )
        if isinstance(raw_date, dt.datetime):
            parsed = raw_date.date()
        elif isinstance(raw_date, dt.date):
            parsed = raw_date
        else:
            try:
                parsed = dt.date.fromisoformat(str(raw_date))
            except ValueError as exc:
                raise InterventionError(
                    f"{where}: bad 'date' {raw_date!r}"
                ) from exc
        out.append(Intervention(date=parsed, name=name, expect=expect))

    out.sort(key=lambda i: i.date)
    return out
