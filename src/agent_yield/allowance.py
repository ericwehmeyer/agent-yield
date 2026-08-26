"""The budget an operator on a subscription actually spends, and its one number.

`pricing.py` produces dollars, and says plainly that on a subscription they are
LIST-PRICE EQUIVALENTS: the ranking of two ways of working survives, the
absolute figure does not. This module is the other half -- what the operator is
really rationed on.

WHAT IS OBSERVABLE. The statusline payload carries
`rate_limits.{five_hour,seven_day}.{used_percentage,resets_at}`. That is the
binding constraint, measured, in the units the plan actually enforces, and it
needs no price table at all.

WHAT IS NOT, AND WHY THERE IS NO TIER TABLE HERE. The allowance's absolute
size, whether models draw on it at different rates, and overage behaviour
appear in no transcript and in no `-p` output. A table of per-plan token
allocations would be a hardcoded price table with no `costUSD` to check itself
against -- exactly the failure `pricing.py` is designed out of, rebuilt one
module over. So the plan's size is not declared. It is CALIBRATED, from one
pair of snapshots:

    plan_window_dollars ~= delta_list_dollars / delta_seven_day_points x 100

WHY THAT IS A LOWER BOUND, AND WHY THE BOUND FALLS THE RIGHT WAY. Only this
tool's own sessions contribute to the numerator, while every session on the
account -- other terminals, the web, anything not ingested -- contributes to
the denominator. Unmeasured spend therefore inflates the points and DEFLATES
the estimate. So the number is a lower bound on the plan's size and hence an
UPPER bound on the fraction of it a piece of work consumed. For a budget
figure that is the conservative direction, and it is the reason this is worth
shipping at n=2 rather than waiting for a regression that needs a month of
fully-instrumented use to say anything.

`used_percentage` is an integer, so a pair that moved fewer than
`MIN_POINTS` points is refused rather than reported: at 1-point quantization a
2-point move carries a 50% error and would print as a fact.
"""
from __future__ import annotations

import datetime as dt
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from .records import json_lines

SNAPSHOT_PATH = Path(".agent-yield") / "allowance.jsonl"

# Below this the quantization error dominates: at 1-point resolution, a 4-point
# move is +/-25% before anything else goes wrong.
MIN_POINTS = 5


@dataclass(frozen=True)
class Snapshot:
    timestamp: str
    seven_day: int
    five_hour: int | None = None
    seven_day_resets_at: str | None = None
    five_hour_resets_at: str | None = None
    # This tool's own measured spend at the moment of the snapshot. Part of the
    # numerator only; see the module docstring on why it is always short.
    session_dollars: float | None = None


@dataclass(frozen=True)
class PlanEstimate:
    window_dollars: float
    points: int
    dollars: float
    span_hours: float
    # Always True as things stand. Kept as a field rather than a comment so a
    # caller cannot print the number without the qualification being available.
    is_lower_bound: bool = True

    def describe(self) -> str:
        return (f"7-day allowance >= ${self.window_dollars:,.0f} list-equivalent "
                f"(from {self.points} points over {self.span_hours:.1f}h, "
                f"${self.dollars:.2f} measured; a LOWER bound -- sessions this "
                f"tool did not see move the points and not the dollars)")


def _percentage(block: object) -> int | None:
    if not isinstance(block, dict):
        return None
    value = block.get("used_percentage")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return int(value)


def _resets_at(block: object) -> str | None:
    if not isinstance(block, dict):
        return None
    value = block.get("resets_at")
    return value if isinstance(value, str) and value else None


def read_allowance(payload: dict, timestamp: str | None = None) -> Snapshot | None:
    """One snapshot from a statusline payload, or None if it carries no limits.

    None rather than zeros: a payload without `rate_limits` is a client that
    does not report them, and recording that as 0% used would read as a fresh
    allowance.
    """
    limits = payload.get("rate_limits")
    if not isinstance(limits, dict):
        return None
    seven_day = _percentage(limits.get("seven_day"))
    if seven_day is None:
        return None

    cost = payload.get("cost")
    dollars = None
    if isinstance(cost, dict):
        value = cost.get("total_cost_usd")
        if not isinstance(value, bool) and isinstance(value, (int, float)):
            dollars = float(value)

    return Snapshot(
        timestamp=timestamp or dt.datetime.now(dt.timezone.utc).isoformat(),
        seven_day=seven_day,
        five_hour=_percentage(limits.get("five_hour")),
        seven_day_resets_at=_resets_at(limits.get("seven_day")),
        five_hour_resets_at=_resets_at(limits.get("five_hour")),
        session_dollars=dollars,
    )


def append(path: Path, snapshot: Snapshot, previous: Snapshot | None = None) -> bool:
    """Append a snapshot, unless it says nothing new. Never raises.

    A statusline renders on every keystroke. Writing an identical line each
    time would turn the log into a keystroke counter, so a snapshot is kept
    only when a percentage moved or a window reset.
    """
    if previous is not None and (
        previous.seven_day == snapshot.seven_day
        and previous.five_hour == snapshot.five_hour
        and previous.seven_day_resets_at == snapshot.seven_day_resets_at
    ):
        return False
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with Path(path).open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(asdict(snapshot), sort_keys=True) + "\n")
    except OSError:
        return False
    return True


def load(path: Path) -> list[Snapshot]:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return []
    out: list[Snapshot] = []
    for line in json_lines(text):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except ValueError:
            continue
        if not isinstance(raw, dict) or "seven_day" not in raw:
            continue
        out.append(Snapshot(
            timestamp=raw.get("timestamp", ""),
            seven_day=raw["seven_day"],
            five_hour=raw.get("five_hour"),
            seven_day_resets_at=raw.get("seven_day_resets_at"),
            five_hour_resets_at=raw.get("five_hour_resets_at"),
            session_dollars=raw.get("session_dollars"),
        ))
    return out


def _hours(first: Snapshot, last: Snapshot) -> float:
    try:
        start = dt.datetime.fromisoformat(first.timestamp)
        end = dt.datetime.fromisoformat(last.timestamp)
    except ValueError:
        return 0.0
    return max(0.0, (end - start).total_seconds() / 3600)


def estimate(snapshots: Iterable[Snapshot]) -> PlanEstimate | None:
    """Calibrate the plan's 7-day window from the widest usable pair.

    Refuses, rather than guessing, in every case where the arithmetic would be
    a shape rather than a measurement: no pair inside one window, a move under
    `MIN_POINTS`, no dollars recorded, or dollars that did not rise.
    """
    ordered = sorted(snapshots, key=lambda s: s.timestamp)
    by_window: dict[str | None, list[Snapshot]] = {}
    for snapshot in ordered:
        if snapshot.session_dollars is None:
            continue
        by_window.setdefault(snapshot.seven_day_resets_at, []).append(snapshot)

    best: PlanEstimate | None = None
    for window in by_window.values():
        if len(window) < 2:
            continue
        # Widest pair in the window: the most points, so the least
        # quantization error. A pair straddling a reset is impossible here
        # because the reset timestamp is the key.
        first, last = window[0], window[-1]
        points = last.seven_day - first.seven_day
        dollars = last.session_dollars - first.session_dollars
        if points < MIN_POINTS or dollars <= 0:
            continue
        candidate = PlanEstimate(
            window_dollars=dollars / points * 100,
            points=points,
            dollars=dollars,
            span_hours=_hours(first, last),
        )
        if best is None or candidate.points > best.points:
            best = candidate
    return best
