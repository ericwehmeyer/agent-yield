"""Section 4.6's second half: the self-contained HTML view.

One file, no network. Every style, every chart, every glyph is inline, so the
page opens from a local file with the wifi off. Charts are hand-written SVG --
no library, and deliberately no `xmlns` attribute, which would put a URL in a
page that is supposed to have none.

**Retrospective, not live.** No refresh, no polling, no timers. The question
this tool answers ("what did that mode of working cost, and did the
intervention do what it said?") is about days that already happened.

Two rules run through everything below:

* **Tokens here, money in `pricing.py`.** The old rule was "never money --
  rates change and vary by plan". Rates are now reconciled against the CLI's
  own `costUSD` on four archived arms every test run, which is what the rule
  was really asking for, and plan variation is handled by calling the figure a
  list-price equivalent rather than a bill. This page still prints tokens: it
  is retrospective and per-mode, and nothing on it is an arm comparison.
* **`None` is a dash, never a zero.** An empty window is "no evidence"; zero
  reads as "it was free", and that is the error this tool exists to prevent.

The main-vs-subagent split is derived here from `CallRecord.is_subagent`
rather than from any aggregate, so the two populations are counted from the
calls themselves. Blending them describes neither: measured 3.5x apart.
"""
from __future__ import annotations

import datetime as dt
import html
import math
import re
from typing import Iterable

from .records import CallRecord
from .report import BeforeAfter, YieldRow
from .usage import Usage

DASH = "-"

# ---------------------------------------------------------------- formatting


def _esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def _num(value: float | int | None) -> str:
    """A number with separators, or an explicit dash. Never a substitute 0."""
    if value is None:
        return DASH
    return f"{value:,.0f}"


def _pct(value: float | None) -> str:
    return DASH if value is None else f"{value * 100:.1f}%"


def _signed_pct(value: float | None) -> str:
    return DASH if value is None else f"{value * 100:+.1f}%"


def _compact(value: float | None) -> str:
    """Axis-tick scale. Dash for None, so a gap never reads as the origin."""
    if value is None:
        return DASH
    magnitude = abs(value)
    if magnitude >= 1e9:
        return f"{value / 1e9:.1f}B"
    if magnitude >= 1e6:
        return f"{value / 1e6:.1f}M"
    if magnitude >= 1e3:
        return f"{value / 1e3:.0f}k"
    return f"{value:.0f}"


def _count(number: int, word: str) -> str:
    return f"{_num(number)} {word}" + ("" if number == 1 else "s")


def _cell(value: float | int | None, extra: str = "") -> str:
    klass = "num dash" if value is None else "num"
    if extra:
        klass = f"{klass} {extra}"
    return f'<td class="{klass}">{_num(value)}</td>'


_HOME_ROOTS = frozenset({"users", "home"})
HOME_LABEL = "(home)"


def _repo(cwd: str | None) -> str:
    """The last path segment only, unless that segment is a person.

    The unit of account is the repository and the session, never a person, and
    a full working-directory path usually carries somebody's home directory --
    that is, their name -- into the page.

    Taking the last segment is not enough on its own: when the session ran in
    the home directory itself, the last segment *is* the account name, so the
    rule leaks exactly the case it was written to stop. `/Users/<name>`,
    `/home/<name>`, `C:\\Users\\<name>` and a bare `~` all collapse to
    HOME_LABEL instead.
    """
    if not cwd:
        return DASH
    raw = cwd.strip()
    if raw in {"~", "~/"}:
        return HOME_LABEL
    parts = [p for p in re.split(r"[\\/]+", raw) if p]
    # Drop a Windows drive letter so `C:\Users\name` has two segments, not three.
    parts = [p for p in parts if not re.fullmatch(r"[A-Za-z]:", p)]
    if not parts:
        return DASH
    if len(parts) == 2 and parts[0].lower() in _HOME_ROOTS:
        return HOME_LABEL
    return parts[-1]


# ---------------------------------------------------------------- aggregation


class _Split:
    """Totals with the main and subagent populations kept apart."""

    def __init__(self) -> None:
        self.calls = 0
        self.usage = Usage.zero()
        self.main_calls = 0
        self.main_usage = Usage.zero()
        self.sub_calls = 0
        self.sub_usage = Usage.zero()

    def add(self, record: CallRecord) -> None:
        self.calls += 1
        self.usage = self.usage + record.usage
        if record.is_subagent:
            self.sub_calls += 1
            self.sub_usage = self.sub_usage + record.usage
        else:
            self.main_calls += 1
            self.main_usage = self.main_usage + record.usage

    @staticmethod
    def _per_call(usage: Usage, calls: int) -> float | None:
        return usage.cache_read_tokens / calls if calls else None

    @property
    def context_per_call(self) -> float | None:
        return self._per_call(self.usage, self.calls)

    @property
    def main_context_per_call(self) -> float | None:
        return self._per_call(self.main_usage, self.main_calls)

    @property
    def sub_context_per_call(self) -> float | None:
        return self._per_call(self.sub_usage, self.sub_calls)


def _by_day(records: Iterable[CallRecord]) -> dict[dt.date, _Split]:
    out: dict[dt.date, _Split] = {}
    for record in records:
        out.setdefault(record.day, _Split()).add(record)
    return out


def _by_day_session(
    records: Iterable[CallRecord],
) -> dict[dt.date, dict[str, _Split]]:
    out: dict[dt.date, dict[str, _Split]] = {}
    for record in records:
        session = record.session_id or "(no session id)"
        out.setdefault(record.day, {}).setdefault(session, _Split()).add(record)
    return out


def _session_detail(records: Iterable[CallRecord]) -> dict[str, dict[str, set]]:
    detail: dict[str, dict[str, set]] = {}
    for record in records:
        session = record.session_id or "(no session id)"
        bucket = detail.setdefault(session, {"models": set(), "repos": set()})
        if record.model:
            bucket["models"].add(record.model)
        if record.cwd:
            bucket["repos"].add(_repo(record.cwd))
    return detail


# --------------------------------------------------------------------- charts

_W, _H = 880, 260
_PAD_L, _PAD_R, _PAD_T, _PAD_B = 78, 20, 42, 58
_X0, _X1 = _PAD_L, _W - _PAD_R
_Y0, _Y1 = _PAD_T, _H - _PAD_B


def _nice_max(value: float) -> float:
    if value <= 0:
        return 1.0
    exponent = math.floor(math.log10(value))
    base = 10.0**exponent
    for step in (1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10):
        if value <= step * base:
            return step * base
    return 10 * base


def _y_for(value: float, top: float) -> float:
    return _Y1 - (value / top) * (_Y1 - _Y0) if top else _Y1


def _band(count: int) -> float:
    return (_X1 - _X0) / count if count else (_X1 - _X0)


def _centre(index: int, band: float) -> float:
    return _X0 + (index + 0.5) * band


def _x_for_date(days: list[dt.date], when: dt.date, band: float) -> float:
    """Left edge of the first day at or after `when` -- "from here onward"."""
    ahead = sum(1 for day in days if day < when)
    return min(max(_X0 + ahead * band, _X0), _X1)


def _bar_top(x: float, y: float, width: float, height: float) -> str:
    """A bar anchored to the baseline with only its data-end rounded."""
    radius = min(4.0, width / 2, height)
    return (
        f"M {x:.1f} {y + height:.1f} V {y + radius:.1f} "
        f"A {radius:.1f} {radius:.1f} 0 0 1 {x + radius:.1f} {y:.1f} "
        f"H {x + width - radius:.1f} "
        f"A {radius:.1f} {radius:.1f} 0 0 1 {x + width:.1f} {y + radius:.1f} "
        f"V {y + height:.1f} Z"
    )


def _frame(days: list[dt.date], top: float, y_label: str) -> list[str]:
    """Grid, y ticks, x ticks. Recessive: the data is the ink."""
    band = _band(len(days))
    out: list[str] = []
    for step in range(5):
        value = top * step / 4
        y = _y_for(value, top)
        out.append(
            f'<line class="grid" x1="{_X0}" y1="{y:.1f}" '
            f'x2="{_X1}" y2="{y:.1f}" />'
        )
        out.append(
            f'<text class="tick" x="{_X0 - 10}" y="{y + 4:.1f}" '
            f'text-anchor="end">{_esc(_compact(value))}</text>'
        )
    # Top-left and left-anchored: an end-anchored label at the axis runs off
    # the left edge of the viewBox as soon as the unit has two words.
    out.append(
        f'<text class="axis-label" x="8" y="14" '
        f'text-anchor="start">{_esc(y_label)}</text>'
    )
    out.append(
        f'<line class="axis" x1="{_X0}" y1="{_Y1}" x2="{_X1}" y2="{_Y1}" />'
    )
    every = max(1, math.ceil(len(days) / 10))
    for index, day in enumerate(days):
        if index % every:
            continue
        x = _centre(index, band)
        out.append(
            f'<text class="tick" x="{x:.1f}" y="{_Y1 + 26}" '
            f'text-anchor="middle">{_esc(day.strftime("%m-%d"))}</text>'
        )
    return out


def _markers(days: list[dt.date], marks: list[tuple[int, object]]) -> list[str]:
    """Interventions on the timeline: a dashed rule plus its number.

    The number, not the colour, carries identity -- it keys straight into the
    table below, and survives a monochrome print.
    """
    if not days or not marks:
        return []
    band = _band(len(days))
    out: list[str] = []
    for number, intervention in marks:
        when = intervention.date  # type: ignore[attr-defined]
        if when < days[0] or when > days[-1]:
            continue
        x = _x_for_date(days, when, band)
        label = f"{intervention.name} -- expect: {intervention.expect}"  # type: ignore[attr-defined]
        out.append(
            f'<g class="mark"><title>{_esc(when.isoformat())}: '
            f"{_esc(label)}</title>"
            f'<line x1="{x:.1f}" y1="{_Y0 - 6}" x2="{x:.1f}" y2="{_Y1}" />'
            f'<circle cx="{x:.1f}" cy="{_Y0 - 12}" r="8" />'
            f'<text x="{x:.1f}" y="{_Y0 - 8.5}" text-anchor="middle">'
            f"{number}</text></g>"
        )
    return out


def _svg(title: str, body: list[str]) -> str:
    return (
        f'<svg class="plot" viewBox="0 0 {_W} {_H}" role="img" '
        f'aria-label="{_esc(title)}"><title>{_esc(title)}</title>'
        + "".join(body)
        + "</svg>"
    )


def _figure(heading: str, note: str, svg: str, legend: str = "") -> str:
    return (
        '<figure class="chart">'
        f"<figcaption><h3>{_esc(heading)}</h3>"
        f'<p class="note">{_esc(note)}</p></figcaption>'
        f'{legend}<div class="scroll">{svg}</div>'
        "</figure>"
    )


def _bar_chart(
    days: list[dt.date],
    values: list[float | None],
    marks: list[tuple[int, object]],
    heading: str,
    note: str,
    y_label: str,
) -> str:
    if not days:
        return _empty_chart(heading, note)
    present = [v for v in values if v is not None]
    top = _nice_max(max(present)) if present else 1.0
    band = _band(len(days))
    width = min(band * 0.62, 46.0)
    body = _frame(days, top, y_label)
    for index, (day, value) in enumerate(zip(days, values)):
        x = _centre(index, band) - width / 2
        if value is None:
            # Below the baseline, not just above it: a dash drawn inside the
            # plot area would read as a value near zero, which is the exact
            # misreading the dash exists to prevent.
            body.append(
                f'<text class="gap" x="{_centre(index, band):.1f}" '
                f'y="{_Y1 + 12}" text-anchor="middle">{DASH}</text>'
            )
            continue
        y = _y_for(value, top)
        height = max(_Y1 - y, 1.0)
        body.append(
            f'<g class="bar"><title>{_esc(day.isoformat())}: '
            f"{_esc(_num(value))} tokens</title>"
            f'<path d="{_bar_top(x, y, width, height)}" /></g>'
        )
    body.extend(_markers(days, marks))
    return _figure(heading, note, _svg(heading, body))


def _line_chart(
    days: list[dt.date],
    series: list[tuple[str, list[float | None], str, str, str]],
    marks: list[tuple[int, object]],
    heading: str,
    note: str,
    y_label: str,
) -> str:
    """Two populations, one y-axis. Never a second scale on the right."""
    if not days:
        return _empty_chart(heading, note)
    present = [v for _, values, _, _, _ in series for v in values if v is not None]
    top = _nice_max(max(present)) if present else 1.0
    band = _band(len(days))
    body = _frame(days, top, y_label)

    for series_index, (name, values, colour, dash, marker) in enumerate(series):
        # Two series missing the same day would stack their dashes on top of
        # each other; nudge each series' dash off centre so both stay legible.
        nudge = (series_index - (len(series) - 1) / 2) * 13
        run: list[str] = []
        for index, value in enumerate(values):
            if value is None:
                if len(run) > 1:
                    body.append(
                        f'<polyline class="line" points="{" ".join(run)}" '
                        f'stroke="{colour}" stroke-dasharray="{dash}" />'
                    )
                run = []
                continue
            run.append(f"{_centre(index, band):.1f},{_y_for(value, top):.1f}")
        if len(run) > 1:
            body.append(
                f'<polyline class="line" points="{" ".join(run)}" '
                f'stroke="{colour}" stroke-dasharray="{dash}" />'
            )
        for index, value in enumerate(values):
            x = _centre(index, band)
            if value is None:
                body.append(
                    f'<text class="gap" x="{x + nudge:.1f}" y="{_Y1 + 12}" '
                    f'text-anchor="middle">{DASH}</text>'
                )
                continue
            y = _y_for(value, top)
            tip = (
                f"<title>{_esc(days[index].isoformat())} -- {_esc(name)}: "
                f"{_esc(_num(value))}</title>"
            )
            if marker == "square":
                body.append(
                    f'<g class="dot">{tip}<rect x="{x - 4.5:.1f}" '
                    f'y="{y - 4.5:.1f}" width="9" height="9" '
                    f'fill="{colour}" /></g>'
                )
            else:
                body.append(
                    f'<g class="dot">{tip}<circle cx="{x:.1f}" cy="{y:.1f}" '
                    f'r="5" fill="{colour}" /></g>'
                )
    body.extend(_markers(days, marks))

    swatches = []
    for name, _, colour, dash, marker in series:
        shape = (
            f'<rect x="9" y="5.5" width="9" height="9" fill="{colour}" />'
            if marker == "square"
            else f'<circle cx="13.5" cy="10" r="5" fill="{colour}" />'
        )
        swatches.append(
            f'<span class="key"><svg class="swatch" viewBox="0 0 28 20" '
            f'aria-hidden="true"><line x1="0" y1="10" x2="28" y2="10" '
            f'stroke="{colour}" stroke-width="2" stroke-dasharray="{dash}" />'
            f"{shape}</svg>{_esc(name)}</span>"
        )
    legend = f'<div class="legend">{"".join(swatches)}</div>'
    return _figure(heading, note, _svg(heading, body), legend)


def _empty_chart(heading: str, note: str) -> str:
    return (
        '<figure class="chart">'
        f"<figcaption><h3>{_esc(heading)}</h3>"
        f'<p class="note">{_esc(note)}</p></figcaption>'
        f'<p class="empty">No days to plot.</p></figure>'
    )


# ----------------------------------------------------------------------- CSS

_CSS = """
:root {
  color-scheme: light;
  --bg: #fcfcfb;
  --surface: #ffffff;
  --surface-2: #f4f3f0;
  --border: #dcdad4;
  --text: #0b0b0b;
  --text-secondary: #52514e;
  --text-muted: #7a7873;
  --grid: #e7e5e0;
  --axis: #b7b4ad;
  --series-main: #2a78d6;
  --series-sub: #eb6834;
  --marker: #4a3aa7;
  --marker-ink: #ffffff;
  --accent: #1c5cab;
}
@media (prefers-color-scheme: dark) {
  :root {
    color-scheme: dark;
    --bg: #131312;
    --surface: #1a1a19;
    --surface-2: #232322;
    --border: #3a3a37;
    --text: #ffffff;
    --text-secondary: #c3c2b7;
    --text-muted: #96958c;
    --grid: #2c2c2a;
    --axis: #55534e;
    --series-main: #3987e5;
    --series-sub: #d95926;
    --marker: #9085e9;
    --marker-ink: #131312;
    --accent: #86b6ef;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0;
  padding: 32px 24px 72px;
  background: var(--bg);
  color: var(--text);
  font: 15px/1.5 ui-sans-serif, system-ui, -apple-system, "Segoe UI",
        Helvetica, Arial, sans-serif;
  overflow-x: hidden;
}
main { max-width: 1080px; margin: 0 auto; }
h1 { font-size: 1.6rem; margin: 0 0 4px; letter-spacing: -0.01em; }
h2 {
  font-size: 1.05rem; margin: 40px 0 4px; letter-spacing: 0.02em;
  text-transform: uppercase; color: var(--text-secondary);
}
h3 { font-size: 1rem; margin: 0 0 2px; }
p { margin: 0 0 8px; }
.note { color: var(--text-muted); font-size: 0.85rem; }
.lede { color: var(--text-secondary); font-size: 0.95rem; max-width: 68ch; }
.empty {
  border: 1px dashed var(--border); border-radius: 10px;
  padding: 24px; color: var(--text-secondary); background: var(--surface);
}
.tiles {
  display: grid; gap: 12px; margin: 12px 0 0;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
}
.tile {
  background: var(--surface); border: 1px solid var(--border);
  border-radius: 12px; padding: 14px 16px;
}
.tile .k {
  font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.04em;
  color: var(--text-muted);
}
.tile .v {
  font-size: 1.5rem; font-variant-numeric: tabular-nums;
  margin-top: 4px; color: var(--text);
}
.tile .v.dash { color: var(--text-muted); }
.tile .s { font-size: 0.8rem; color: var(--text-secondary); margin-top: 2px; }
.tile.hero { background: var(--surface-2); }
.tile.hero .v { font-size: 2rem; color: var(--accent); }
.split { display: grid; gap: 12px; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); }
.split .tile.main { border-left: 4px solid var(--series-main); }
.split .tile.sub { border-left: 4px solid var(--series-sub); }
.scroll { overflow-x: auto; max-width: 100%; }
table { border-collapse: collapse; width: 100%; min-width: 620px; font-size: 0.9rem; }
th, td { padding: 7px 10px; text-align: left; border-bottom: 1px solid var(--border); }
th {
  font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.04em;
  color: var(--text-muted); font-weight: 600; white-space: nowrap;
}
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
td.dash { color: var(--text-muted); }
td.wrap { min-width: 220px; white-space: normal; }
tbody tr:hover { background: var(--surface-2); }
code, .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 0.85em; }
td.mono { white-space: nowrap; }
details {
  background: var(--surface); border: 1px solid var(--border);
  border-radius: 10px; margin: 8px 0; padding: 0 12px;
}
summary { cursor: pointer; padding: 10px 2px; display: flex; gap: 12px; flex-wrap: wrap; align-items: baseline; }
summary .day { font-weight: 600; font-variant-numeric: tabular-nums; }
summary .meta { color: var(--text-secondary); font-size: 0.85rem; font-variant-numeric: tabular-nums; }
details[open] { background: var(--surface-2); }
details > .scroll { padding-bottom: 10px; }
.chart {
  margin: 16px 0 0; padding: 14px 16px 8px; background: var(--surface);
  border: 1px solid var(--border); border-radius: 12px;
}
.plot { width: 100%; height: auto; min-width: 660px; display: block; }
.plot .grid { stroke: var(--grid); stroke-width: 1; }
.plot .axis { stroke: var(--axis); stroke-width: 1; }
.plot .tick { fill: var(--text-muted); font-size: 11px; }
.plot .axis-label { fill: var(--text-secondary); font-size: 11px; letter-spacing: 0.03em; }
.plot .gap { fill: var(--text-muted); font-size: 13px; }
.plot .bar path { fill: var(--series-main); }
.plot .line { fill: none; stroke-width: 2; stroke-linejoin: round; stroke-linecap: round; }
.plot .dot rect, .plot .dot circle { stroke: var(--surface); stroke-width: 2; }
.plot .mark line { stroke: var(--marker); stroke-width: 1.5; stroke-dasharray: 4 4; }
.plot .mark circle { fill: var(--marker); }
.plot .mark text { fill: var(--marker-ink); font-size: 10px; font-weight: 700; }
.legend { display: flex; flex-wrap: wrap; gap: 16px; margin: 2px 0 10px; font-size: 0.85rem; color: var(--text-secondary); }
.key { display: inline-flex; align-items: center; gap: 6px; }
.swatch { width: 28px; height: 20px; flex: none; }
.pin {
  display: inline-flex; align-items: center; justify-content: center;
  width: 18px; height: 18px; border-radius: 50%;
  background: var(--marker); color: var(--marker-ink);
  font-size: 0.7rem; font-weight: 700;
}
footer { margin-top: 48px; color: var(--text-muted); font-size: 0.8rem; }
"""


# ------------------------------------------------------------------ sections


def _tile(key: str, value: str, sub: str = "", klass: str = "") -> str:
    dash = " dash" if value == DASH else ""
    sub_html = f'<div class="s">{_esc(sub)}</div>' if sub else ""
    return (
        f'<div class="tile {klass}"><div class="k">{_esc(key)}</div>'
        f'<div class="v{dash}">{_esc(value)}</div>{sub_html}</div>'
    )


def _consolidate(total: _Split) -> str:
    usage = total.usage
    fields = (
        ("Input", usage.input_tokens),
        ("Output", usage.output_tokens),
        ("Cache write", usage.cache_creation_tokens),
        ("Cache read", usage.cache_read_tokens),
    )
    share = (lambda v: v / usage.total if usage.total else None)
    rows = "".join(
        f"<tr><td>{_esc(name)}</td>{_cell(value)}"
        f'<td class="num">{_esc(_pct(share(value)))}</td></tr>'
        for name, value in fields
    )
    table = (
        '<div class="scroll"><table><thead><tr><th>Field</th>'
        '<th class="num">Tokens</th><th class="num">Share of total</th>'
        f"</tr></thead><tbody>{rows}</tbody>"
        "<tfoot><tr><td>Total</td>"
        f"{_cell(usage.total)}"
        '<td class="num">100.0%</td></tr></tfoot></table></div>'
    )
    tiles = "".join(
        [
            _tile("Calls", _num(total.calls)),
            _tile("Tokens", _num(usage.total), "all four fields, summed"),
            _tile(
                "Context per call",
                _num(total.context_per_call),
                "blended -- see the split below",
            ),
            _tile(
                "Cache read",
                _pct(usage.cache_read_share),
                "of every token consumed",
                "hero",
            ),
        ]
    )
    return (
        "<h2>Consolidate</h2>"
        '<p class="lede">The four usage fields are kept apart all the way to '
        "this page. Collapsing them is how a careful metrics file came to be "
        "wrong by roughly 80x -- cache reads are most of what is actually "
        "consumed, and a total that omits them is not a small error.</p>"
        f'<div class="tiles">{tiles}</div>{table}'
    )


def _main_vs_subagent(total: _Split) -> str:
    main = total.main_context_per_call
    sub = total.sub_context_per_call
    if main is not None and sub is not None and min(main, sub) > 0:
        ratio = f"{max(main, sub) / min(main, sub):.1f}x"
    else:
        ratio = DASH

    tiles = "".join(
        [
            _tile(
                "Main sessions -- context per call",
                _num(main),
                f"{_count(total.main_calls, 'call')}, "
                f"{_num(total.main_usage.total)} tokens",
                "main",
            ),
            _tile(
                "Subagents -- context per call",
                _num(sub),
                f"{_count(total.sub_calls, 'call')}, "
                f"{_num(total.sub_usage.total)} tokens",
                "sub",
            ),
            _tile("Gap", ratio, "one mean over both describes neither"),
        ]
    )

    chart = ""
    values = [v for v in (main, sub) if v is not None]
    if values:
        top = _nice_max(max(values))
        width, height, pad = 640, 132, 190
        bars = []
        for index, (name, value, colour) in enumerate(
            (
                ("Main sessions", main, "var(--series-main)"),
                ("Subagents", sub, "var(--series-sub)"),
            )
        ):
            y = 20 + index * 56
            bars.append(
                f'<text class="tick" x="{pad - 12}" y="{y + 22}" '
                f'text-anchor="end">{_esc(name)}</text>'
            )
            if value is None:
                bars.append(
                    f'<text class="gap" x="{pad + 6}" y="{y + 22}">{DASH}'
                    "</text>"
                )
                continue
            length = max((value / top) * (width - pad - 90), 2.0)
            bars.append(
                f'<rect x="{pad}" y="{y}" width="{length:.1f}" height="34" '
                f'rx="4" fill="{colour}"><title>{_esc(name)}: '
                f"{_esc(_num(value))} cache-read tokens per call</title>"
                "</rect>"
            )
            bars.append(
                f'<text class="tick" x="{pad + length + 10:.1f}" '
                f'y="{y + 22}">{_esc(_num(value))}</text>'
            )
        chart = (
            f'<figure class="chart"><figcaption>'
            "<h3>Context per call, by population</h3>"
            '<p class="note">Cache-read tokens per call. Each bar is labelled '
            "directly -- colour is never the only cue.</p></figcaption>"
            f'<div class="scroll"><svg class="plot" viewBox="0 0 {width} '
            f'{height}" role="img" aria-label="Context per call by '
            f'population"><title>Context per call by population</title>'
            f'{"".join(bars)}</svg></div></figure>'
        )

    return (
        "<h2>Main sessions vs subagents</h2>"
        '<p class="lede">Derived per call from the transcripts. These are two '
        "populations carrying context of a different order; the blended "
        "figure above hides the gap, which is the single thing on this page "
        "most worth acting on.</p>"
        f'<div class="tiles split">{tiles}</div>{chart}'
    )


def _trend(
    days: list[dt.date],
    tokens: list[float | None],
    main: list[float | None],
    sub: list[float | None],
    marks: list[tuple[int, object]],
) -> str:
    tokens_chart = _bar_chart(
        days,
        tokens,
        marks,
        "Tokens per day",
        "All four usage fields summed. Numbered rules mark interventions; "
        "hover one for its prediction.",
        "tokens",
    )
    context_chart = _line_chart(
        days,
        [
            ("Main sessions", main, "var(--series-main)", "", "circle"),
            ("Subagents", sub, "var(--series-sub)", "7 4", "square"),
        ],
        marks,
        "Context per call, per day",
        "A different scale from tokens per day, so it gets its own chart and "
        "its own single axis -- never a second axis on the right. A day with "
        f"no calls of that kind breaks the line and is marked {DASH}.",
        "tokens per call",
    )
    return "<h2>Trend</h2>" + tokens_chart + context_chart


def _interventions(comparisons: list[BeforeAfter], numbers: dict) -> str:
    if not comparisons:
        return (
            "<h2>Interventions</h2>"
            '<p class="empty">No interventions recorded. A process change '
            "without a written prediction is not an experiment.</p>"
        )
    rows = []
    for comparison in comparisons:
        intervention = comparison.intervention
        number = numbers.get((intervention.date, intervention.name), "")
        rows.append(
            f'<tr><td><span class="pin">{number}</span></td>'
            f'<td class="mono">{_esc(intervention.date.isoformat())}</td>'
            f"<td class=\"wrap\">{_esc(intervention.name)}</td>"
            f'<td class="wrap">{_esc(intervention.expect)}</td>'
            f"<td>{_esc(comparison.metric)}</td>"
            f"{_cell(comparison.before)}{_cell(comparison.after)}"
            f'<td class="num{"" if comparison.change is not None else " dash"}">'
            f"{_esc(_signed_pct(comparison.change))}</td></tr>"
        )
    return (
        "<h2>Interventions</h2>"
        '<p class="lede">Each change on the record with what it predicted, '
        "against the median of the window before and the window after. An "
        f"empty window is {DASH}, not zero -- zero would read as free.</p>"
        '<div class="scroll"><table><thead><tr><th></th><th>Date</th>'
        "<th>Intervention</th><th>Expected</th><th>Metric</th>"
        '<th class="num">Before</th><th class="num">After</th>'
        f'<th class="num">Change</th></tr></thead><tbody>{"".join(rows)}'
        "</tbody></table></div>"
    )


def _drilldown(records: list[CallRecord]) -> str:
    if not records:
        return (
            "<h2>Day to session</h2>"
            '<p class="empty">No calls found, so there is nothing to drill '
            "into.</p>"
        )
    per_day = _by_day(records)
    per_session = _by_day_session(records)
    detail = _session_detail(records)
    blocks = []
    for day in sorted(per_day, reverse=True):
        totals = per_day[day]
        sessions = per_session[day]
        rows = []
        for session in sorted(sessions):
            split = sessions[session]
            info = detail.get(session, {"models": set(), "repos": set()})
            models = ", ".join(sorted(info["models"])) or DASH
            repos = ", ".join(sorted(info["repos"])) or DASH
            short = session if len(session) <= 12 else session[:8] + "..."
            rows.append(
                f'<tr><td class="mono" title="{_esc(session)}">{_esc(short)}'
                f"</td>{_cell(split.calls)}{_cell(split.main_calls)}"
                f"{_cell(split.sub_calls)}{_cell(split.usage.total)}"
                f"{_cell(split.usage.cache_read_tokens)}"
                f"{_cell(split.main_context_per_call)}"
                f"{_cell(split.sub_context_per_call)}"
                f'<td class="mono">{_esc(models)}</td>'
                f'<td class="mono">{_esc(repos)}</td></tr>'
            )
        blocks.append(
            "<details><summary>"
            f'<span class="day">{_esc(day.isoformat())}</span>'
            f'<span class="meta">{_count(totals.calls, "call")} &middot; '
            f"{_num(totals.usage.total)} tokens &middot; "
            f'{_count(len(sessions), "session")} &middot; context/call '
            f"{_esc(_num(totals.context_per_call))}</span></summary>"
            '<div class="scroll"><table><thead><tr><th>Session</th>'
            '<th class="num">Calls</th><th class="num">Main</th>'
            '<th class="num">Sub</th><th class="num">Tokens</th>'
            '<th class="num">Cache read</th><th class="num">Main ctx/call</th>'
            '<th class="num">Sub ctx/call</th><th>Models</th>'
            f'<th>Repository</th></tr></thead><tbody>{"".join(rows)}'
            "</tbody></table></div></details>"
        )
    return (
        "<h2>Day to session</h2>"
        '<p class="lede">Open a day to see the sessions inside it. Plain '
        "disclosure widgets -- no scripting, so this works from a file with "
        "the network off.</p>" + "".join(blocks)
    )


def _yield_table(rows: list[YieldRow]) -> str:
    if not rows:
        return (
            "<h2>Yield per day and mode</h2>"
            '<p class="empty">No yield rows: no day had both spend and a '
            "recorded outcome.</p>"
        )
    body = []
    for row in rows:
        body.append(
            f'<tr><td class="mono">{_esc(row.day.isoformat())}</td>'
            f"<td>{_esc(row.mode)}</td>"
            f"{_cell(row.usage.total)}{_cell(row.calls)}{_cell(row.merges)}"
            f"{_cell(row.commits)}{_cell(row.lines)}{_cell(row.tests)}"
            f"{_cell(row.tokens_per_merge)}{_cell(row.tokens_per_commit)}"
            f"{_cell(row.context_per_call)}</tr>"
        )
    return (
        "<h2>Yield per day and mode</h2>"
        '<p class="lede">Outcomes are per day and cannot be attributed to a '
        "mode, so each row carries its day's outcomes whole. A denominator of "
        f"zero yields {DASH}.</p>"
        '<div class="scroll"><table><thead><tr><th>Day</th><th>Mode</th>'
        '<th class="num">Tokens</th><th class="num">Calls</th>'
        '<th class="num">Merges</th><th class="num">Commits</th>'
        '<th class="num">Lines</th><th class="num">Tests</th>'
        '<th class="num">Tokens/merge</th><th class="num">Tokens/commit</th>'
        '<th class="num">Context/call</th></tr></thead>'
        f'<tbody>{"".join(body)}</tbody></table></div>'
    )


# ------------------------------------------------------------------- the page


def _shell(title: str, body: str) -> str:
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{_esc(title)}</title>\n<style>{_CSS}</style>\n</head>\n"
        f"<body>\n<main>\n{body}\n</main>\n</body>\n</html>\n"
    )


def render_html(
    rows: list[YieldRow],
    comparisons: list[BeforeAfter],
    records: list[CallRecord],
) -> str:
    """Render the whole retrospective as one self-contained HTML string.

    Nothing is fetched: no CDN, no font, no script, no image. The string can
    be written to a file and opened on a plane.

    `records` is the ground truth for anything per-call -- the main/subagent
    split and the day-to-session drilldown -- because `is_subagent` lives on
    the call. `rows` carries the outcome side, which only exists per day.
    """
    rows = list(rows)
    comparisons = list(comparisons)
    records = list(records)

    if not rows and not comparisons and not records:
        return _shell(
            "agent-yield",
            "<h1>agent-yield</h1>"
            '<p class="lede">Retrospective view.</p>'
            '<p class="empty">Nothing to show: no calls, no yield rows and no '
            "interventions were supplied. Point the tool at a transcript "
            "directory and a repository, then render again.</p>",
        )

    total = _Split()
    for record in records:
        total.add(record)
    if not records and rows:
        # Rows without the calls behind them: the totals are still honest, but
        # the population split lives on the call and cannot be recovered, so
        # it stays a dash rather than becoming a plausible-looking blend.
        for row in rows:
            total.calls += row.calls
            total.usage = total.usage + row.usage

    # The day axis is the union of both sources, so a day that produced spend
    # but no row -- or the reverse -- is still visible rather than silently
    # dropped from the timeline.
    per_day = _by_day(records)
    row_days: dict[dt.date, tuple[int, int]] = {}
    for row in rows:
        tokens, calls = row_days.get(row.day, (0, 0))
        row_days[row.day] = (tokens + row.usage.total, calls + row.calls)
    days = sorted(set(per_day) | set(row_days))

    tokens_per_day: list[float | None] = []
    main_ctx: list[float | None] = []
    sub_ctx: list[float | None] = []
    for day in days:
        if day in row_days:
            tokens_per_day.append(row_days[day][0])
        elif day in per_day:
            tokens_per_day.append(per_day[day].usage.total)
        else:
            tokens_per_day.append(None)
        split = per_day.get(day)
        main_ctx.append(split.main_context_per_call if split else None)
        sub_ctx.append(split.sub_context_per_call if split else None)

    marks: list[tuple[int, object]] = []
    numbers: dict[tuple[dt.date, str], int] = {}
    seen: list = []
    for comparison in sorted(comparisons, key=lambda c: c.intervention.date):
        key = (comparison.intervention.date, comparison.intervention.name)
        if key in numbers:
            continue
        numbers[key] = len(numbers) + 1
        seen.append(comparison.intervention)
        marks.append((numbers[key], comparison.intervention))

    if days:
        span = (
            days[0].isoformat()
            if len(days) == 1
            else f"{days[0].isoformat()} to {days[-1].isoformat()}"
        )
    else:
        span = "no dated calls"

    body = (
        "<h1>agent-yield</h1>"
        f'<p class="lede">Spend over outcomes, {_esc(span)}. Tokens only -- '
        "this page never prints a rate, and it is not live: it is a snapshot "
        "of days that already happened, with no refresh of any kind.</p>"
        + _consolidate(total)
        + _main_vs_subagent(total)
        + _trend(days, tokens_per_day, main_ctx, sub_ctx, marks)
        + _interventions(comparisons, numbers)
        + _drilldown(records)
        + _yield_table(rows)
        + "<footer>Unit of account: the repository and the session. "
        "Never a person.</footer>"
    )
    return _shell("agent-yield retrospective", body)
