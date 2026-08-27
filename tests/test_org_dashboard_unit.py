"""The org dashboard's numerator unit, and the four ways it can rot.

#72. The prototype's headline was `tokens per inserted line`, summing raw
`usage.total`. `thresholds.py` L76 calls that unit crude in the same file the
page was told to read: ~97% of the sum is cache reads at 0.10x a base input
token, so a team that restarts sessions often -- this repo's own recommended
discipline -- posts a lower total for the same work and ranks better. A
Director reassigning headcount would be reassigning it on a cache-hit ranking.
The headline is now list-price dollars per 1,000 inserted lines.

Four failure modes, and this file has tests for each:

* **The constants drift.** `PRICING` in `dashboard.html` is a hand-copy of
  `pricing.py`'s rate table. A copy that silently disagrees with its source is
  N2's shape one level up, and it fails in whichever direction the stale copy
  happens to point. `test_page_pricing_matches_pricing_py` reads both.
* **The old unit creeps back onto a tile.** `tok/ins` is kept as a labelled
  secondary and is allowed exactly one home. `test_no_raw_token_ratio_on_a_tile`
  reads the page as text, in the manner of `test_portability_guard.py`, because
  the thing being prevented is an edit nobody has made yet.
* **The real leaf goes stale.** #73. The leaf is frozen literals, which is the
  honest form for a static page with no build step -- but it was frozen from
  two instants, the numerator from one run and the denominator from a later
  one, and the page printed neither time. `dashboard-data.py` now writes both
  blocks in one stamped invocation, and the tests below are what keep the page
  from drifting away from it again.
* **The leaf is checked against the wrong machine.** Both of its sides are
  per-clone -- calls scoped by `cwd`, commits from that clone's reflog -- and
  `.agent-yield/` is never pushed, so a page captured on one of §7's two
  machines is re-derivable only there. `--check` on the other reported every
  row as staleness, correctly and uselessly, and its printed remedy would have
  replaced a real day with nothing. The pair below now SKIPS on a clone that
  did not capture the page, and `test_the_check_tells_a_foreign_clone_from_a
  _vanished_day` is what keeps that skip from becoming an amnesty.

The staleness tests come in a pair on purpose. One asks whether the page still
equals a fresh capture; the other recomputes the dollar figures straight from
`pricing.py` and compares them to the literals on the page. Only the first
would leave the generator checking its own arithmetic -- N10's defect, where
three `find_session` tests took their expectation from the function under test
and so survived the morning's fix of it.

The pair that needs the corpus is skipped where there is none: `.agent-yield/`
is gitignored, so CI cannot re-derive anything. The skip is visible -- CI runs
`pytest -rs` for exactly the reason #29 documents, that a silent skip reads as
a pass. Everything that can be checked from the page's own text runs anywhere.
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
import re
from pathlib import Path

import pytest

from agent_yield import pricing
from agent_yield.attribution import Machine
from agent_yield.ingest import load_ingested
from agent_yield.report import scope_to_repo

_ROOT = Path(__file__).resolve().parent.parent
_DIR = _ROOT / "docs" / "experiments" / "org-dashboard"
_PAGE = _DIR / "dashboard.html"
_GENERATOR = _DIR / "dashboard-data.py"
_CORPUS = _ROOT / ".agent-yield" / "calls.jsonl"

pytestmark = pytest.mark.skipif(not _PAGE.exists(), reason="prototype deleted (see design.md's falsifier)")


def _machine_attribution_available() -> bool:
    """Can this clone still say which commits it wrote?

    `--machine` reads `.git/logs/HEAD`, so the answer is no in a clone whose
    reflog has been expired -- which is what a history rewrite does on its way
    out. The numbers the page froze are not wrong when that happens; they are
    merely no longer re-derivable HERE, and a guard that cannot re-derive must
    say so rather than read the resulting zeros as drift.
    """
    return Machine(_ROOT).available


def _page() -> str:
    return _PAGE.read_text(encoding="utf-8")


def _generator():
    """Import the hyphenated generator by path; it is a script, not a package."""
    spec = importlib.util.spec_from_file_location("dashboard_data", _GENERATOR)
    assert spec and spec.loader, f"cannot load {_GENERATOR}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _real_days() -> list[dict]:
    """The page's own block, read back as JSON.

    It is emitted as JSON rather than in the hand-authored JS style the rest of
    the file uses so that it CAN be read back. A hand-edit that breaks the
    parse is the drift these tests exist to catch, so the failure is the point.
    """
    block = re.search(r"^const REAL_DAYS = (\[.*?^\]);$", _page(), re.M | re.S)
    assert block, "the page no longer declares a REAL_DAYS block"
    try:
        return json.loads(block.group(1))
    except json.JSONDecodeError as exc:
        pytest.fail(
            f"REAL_DAYS is no longer JSON ({exc}). It is generated by "
            "dashboard-data.py and emitted as JSON so that it can be read back "
            "and checked -- an edit that breaks that is exactly the drift #73 "
            "closed. Re-run `python docs/experiments/org-dashboard/"
            "dashboard-data.py --write` rather than editing the block."
        )


def _skip_if_captured_elsewhere(module) -> None:
    """Skip where the page's leaf is another clone's, and say so out loud.

    Not `assert`, and not silence either: `pytest -rs` is what CI runs (#29),
    so this reads as a reported skip rather than a pass. The condition is a
    fact about which machine is running, exactly like the corpus skip above.
    """
    theirs = module.capturing_clone()
    if theirs is None:
        pytest.skip("the page does not record which clone captured it; one "
                    "--write on that clone stamps REAL_SCOPE.machine")
    if not module.same_clone(theirs, _ROOT):
        pytest.skip(
            f"the page's leaf is {theirs}'s work and this clone is {_ROOT}. "
            "Both its sides are per-clone and .agent-yield/ is never pushed, "
            "so there is nothing here to re-derive it from."
        )


def _fake_page(tmp_path: Path, machine: str, days: list[dict]) -> Path:
    """A page holding just the two blocks the generator reads back."""
    page = tmp_path / "dashboard.html"
    scope = {"machine": machine, "calls": "", "outcomes": "",
             "captured": "", "numerator": ""}
    page.write_text(
        "const REAL_SCOPE = " + json.dumps(scope, indent=2) + ";\n"
        "const REAL_DAYS = [\n  "
        + ",\n  ".join(json.dumps(d, separators=(", ", ": ")) for d in days)
        + "\n];\n",
        encoding="utf-8",
    )
    return page


def _real_scope() -> dict:
    block = re.search(r"^const REAL_SCOPE = (\{.*?^\});$", _page(), re.M | re.S)
    assert block, "the page no longer declares a REAL_SCOPE block"
    return json.loads(block.group(1))


def _js_number(block: str, key: str) -> float:
    match = re.search(rf"\b{re.escape(key)}\s*:\s*([0-9.]+)", block)
    assert match, f"{key} not found in the page's PRICING block"
    return float(match.group(1))


def test_page_pricing_matches_pricing_py() -> None:
    """The copied rate table still equals the module it was copied from."""
    block = re.search(r"const PRICING = \{(.*?)\n\};", _page(), re.S)
    assert block, "the page no longer declares a PRICING block"
    body = block.group(1)

    rates = dict(re.findall(r'"(claude-[a-z0-9.-]+)":\s*([0-9.]+)', body))
    assert {k: float(v) for k, v in rates.items()} == pricing.BASE_RATE_PER_MTOK, (
        "dashboard.html's base rates have drifted from pricing.py. The page is a "
        "hand-copy on purpose -- a served version would emit this block from the "
        "module -- so the copy is what has to be re-synced, not this assertion."
    )
    assert _js_number(body, "cacheRead") == pricing.CACHE_READ
    assert _js_number(body, "cacheWrite5m") == pricing.CACHE_WRITE_5M
    assert _js_number(body, "cacheWrite1h") == pricing.CACHE_WRITE_1H
    assert _js_number(body, "output") == pricing.OUTPUT


def test_no_raw_token_ratio_on_a_tile() -> None:
    """`tok/ins` has exactly one home, and it is not the headline.

    Static, not rendered: the edit this guards against -- someone putting the
    old unit back on a tile because it reads more familiarly -- has not been
    made, so there is no behaviour to assert. There is only text.
    """
    page = _page()

    tiles = re.findall(r'tile\(\s*"([^"]*)"', page)
    offenders = [t for t in tiles if "tok/ins" in t or "tokens per inserted line" in t]
    assert not offenders, (
        f"a tile is denominated in raw tokens per line: {offenders}. #72: that unit "
        "ranks cache-hit rate as much as work. It belongs under the secondary heading."
    )

    # The three yield charts name their unit in the aria-label; the two mix
    # charts are about inserted lines by kind and are not yield charts.
    axes = re.findall(r'aria-label="([^"]*)"', page)
    yield_axes = [a for a in axes if "per 1,000 inserted lines" in a]
    assert len(yield_axes) == 3, f"expected three yield charts, found {yield_axes}"
    assert all("list-price dollars" in a for a in yield_axes), (
        f"a yield axis does not say what it is denominated in: {yield_axes}"
    )
    assert not [a for a in axes if "tokens per inserted line" in a], (
        "a chart axis is still in raw tokens per line"
    )

    assert page.count('<div class="section-h">Secondary: the same ratios in raw tokens</div>') == 1, (
        "the secondary section is where tok/ins lives; if it moved, this rule moves with it"
    )


def test_the_capture_says_when_it_was_taken() -> None:
    """#73's acceptance, and it needs no corpus: a timestamp, not a bare date.

    The whole finding was that the page asserted "same work on both sides"
    while holding two instants and printing neither. A date alone cannot
    distinguish a numerator captured at 09:00 from a denominator captured at
    19:54 on the same day, which is the pair that actually disagreed.
    """
    captured = _real_scope()["captured"]
    assert re.search(r"\d{4}-\d\d-\d\d \d\d:\d\d UTC", captured), (
        f"REAL_SCOPE.captured carries no UTC timestamp: {captured!r}"
    )
    assert "one invocation" in captured, (
        "the capture line no longer says both sides came from one invocation, "
        "which is the claim the timestamp exists to support"
    )
    # And the scope strip is where a reader meets it.
    assert "REAL_SCOPE.captured" in _page(), (
        "the capture line is no longer rendered in the scope strip"
    )


def test_every_day_declares_whether_it_had_ended() -> None:
    """`partial` is a flag on the data, so the prose can ask instead of assert.

    The page used to say in prose that its second day was still running, and
    would have gone on saying so after the day closed -- #74's shape. Now the
    sentence reads `last.partial`. That only works if every generated day
    carries the flag.
    """
    days = _real_days()
    assert days, "REAL_DAYS is empty"
    for day in days:
        assert isinstance(day.get("partial"), bool), (
            f"{day.get('day')} carries no `partial` flag; the page's prose and its "
            "PARTIAL chip both read it, and an absent flag reads as `closed`"
        )

    page = _page()
    if any(day["partial"] for day in days):
        assert "PARTIAL" in _real_scope()["captured"], (
            "a day is marked partial but the scope strip does not say so"
        )
        assert "chip-part" in page, "no PARTIAL chip is rendered for the partial day"


def test_the_page_says_which_clone_captured_it() -> None:
    """Provenance, machine-readable, and it needs no corpus to check.

    The path was always in `REAL_SCOPE.calls`, in prose, where only a person
    reading carefully could find it -- and for a day nobody did: `--check` on
    the other machine reported thirteen true cross-clone differences as
    staleness, and the remedy it printed would have deleted a real day. Same
    argument as #73's timestamp: a claim a reader cannot mechanically check is
    a claim that goes unchecked.
    """
    module = _generator()
    theirs = module.capturing_clone()
    assert theirs, (
        "the page no longer says which clone captured it. Re-run "
        "`dashboard-data.py --write` on the clone whose work the leaf is; it "
        "stamps REAL_SCOPE.machine."
    )
    assert "REAL_SCOPE.machine" in _page(), (
        "the scope strip no longer tells a reader that this leaf is one "
        "clone's work, which is the caveat that was missing when the check "
        "read a foreign clone's numbers as drift"
    )


def _row(module, day: str, **over) -> dict:
    """A generated day, zeroed, so a test can move exactly one field."""
    row: dict = {"day": day, "partial": False}
    for key in module.MEASURED:
        row[key] = [] if key == "unpricedModels" else (
            [0, 0, 0] if key == "bands" else 0)
    row.update(over)
    return row


def test_the_check_tells_a_foreign_clone_from_a_vanished_day(
        tmp_path, monkeypatch) -> None:
    """The skip is keyed on the clone, and it is NOT an amnesty.

    Both halves matter and only together. A page captured elsewhere cannot be
    checked here and must not be called stale -- that is the defect. But on
    the clone that DID capture it, a day that vanishes must still fail, and so
    must a day that moved. #26, #32, #44 and #33's own VOID bar each went
    wrong the other way: an exemption written for a real condition, widened
    until a genuine defect fitted inside it and passed as the excused one.

    No corpus needed -- `diff` is handed its fresh side -- so this runs in CI,
    where the pair it guards is skipped.
    """
    module = _generator()
    on_page = [_row(module, "2026-08-25", calls=146)]

    monkeypatch.setattr(module, "PAGE",
                        _fake_page(tmp_path, r"C:\elsewhere\agent-yield", on_page))
    stale, _drifting, foreign = module.diff([])
    assert foreign, "a page captured on another clone was not reported as such"
    assert not stale, f"another clone's leaf was reported as staleness: {stale}"

    # Same page, this clone. The day is gone from the fresh side and that is
    # a result, not an exemption.
    monkeypatch.setattr(module, "PAGE",
                        _fake_page(tmp_path, str(_ROOT), on_page))
    stale, _drifting, foreign = module.diff([])
    assert not foreign
    assert any("absent from the corpus" in line for line in stale), (
        f"a day that vanished on the capturing clone was excused: {stale}"
    )

    # And a closed day that merely moved still fails, which is #73's original
    # criterion and the thing all of this must not have quietly relaxed.
    stale, _drifting, foreign = module.diff([_row(module, "2026-08-25", calls=999)])
    assert not foreign
    assert any("calls" in line for line in stale), (
        f"a closed day moved and the check did not fail: {stale}"
    )


@pytest.mark.skipif(not _CORPUS.exists(), reason=".agent-yield/calls.jsonl is gitignored; no corpus on this machine")
@pytest.mark.skipif(not _machine_attribution_available(), reason="this clone has no reflog, so --machine cannot re-derive the denominator")
def test_no_closed_day_has_moved_since_the_capture() -> None:
    """#73's acceptance criterion, run as a test.

    "Re-running report and outcomes and diffing against REAL_DAYS produces
    zero differences for every closed day." A day still accruing is expected
    to differ and is reported by the generator without failing -- unfinished
    is not stale.
    """
    module = _generator()
    _skip_if_captured_elsewhere(module)
    data = module.build(module.SINCE, module.UNTIL)
    stale, _drifting, _foreign = module.diff(data["REAL_DAYS"])
    assert not stale, (
        "the page's real leaf no longer matches the corpus:\n  "
        + "\n  ".join(stale)
        + "\n\nRe-run `python docs/experiments/org-dashboard/dashboard-data.py "
        "--write`, then re-check design.md's opening figures against the report "
        "it prints."
    )


@pytest.mark.skipif(not _CORPUS.exists(), reason=".agent-yield/calls.jsonl is gitignored; no corpus on this machine")
def test_closed_day_dollars_reproduce_from_pricing_py() -> None:
    """The same figures, derived without the generator.

    Deliberately duplicated arithmetic. The test above compares the page to
    `dashboard-data.py`, which is the right staleness check and the wrong
    correctness check: it would pass just as happily if the generator's pricing
    were wrong, because the page would carry the same wrong number. N10 is that
    defect -- three `find_session` tests took their expectation from the
    function under test and so survived a fix to it. This path starts at
    `pricing.py` instead.
    """
    _skip_if_captured_elsewhere(_generator())
    records = load_ingested(_CORPUS)
    closed = [d for d in _real_days() if not d["partial"]]
    if not closed:
        pytest.skip("every day on the page was still accruing when it was captured")

    for day in closed:
        when = dt.date.fromisoformat(day["day"])
        rows = scope_to_repo([r for r in records if r.day == when], _ROOT)
        assert rows, f"{day['day']}: on the page, no calls in the corpus"

        priced = pricing.price_records(rows)
        assert priced is not None, f"{day['day']} priced to nothing"

        cache_read_dollars = 0.0
        cache_read_tokens = 0
        unpriced_tokens = 0
        for record in rows:
            rate = pricing.BASE_RATE_PER_MTOK.get(pricing.canonical(record.model) or "")
            cache_read_tokens += record.usage.cache_read_tokens
            if rate is None:
                unpriced_tokens += record.usage.total
            else:
                cache_read_dollars += (
                    rate * pricing.CACHE_READ * record.usage.cache_read_tokens / 1_000_000
                )

        assert len(rows) == day["calls"], f"{day['day']}: calls"
        assert sum(r.usage.total for r in rows) == day["tokens"], f"{day['day']}: tokens"
        assert round(priced.dollars, 4) == day["dollars"], (
            f"{day['day']}: page says ${day['dollars']}, pricing.py says ${priced.dollars:.4f}"
        )
        assert round(cache_read_dollars, 4) == day["crUsd"], f"{day['day']}: cache-read dollars"
        assert cache_read_tokens == day["crTok"], f"{day['day']}: cache-read tokens"
        assert unpriced_tokens == day["unpricedTok"], f"{day['day']}: unpriced tokens"


@pytest.mark.skipif(not _CORPUS.exists(), reason=".agent-yield/calls.jsonl is gitignored; no corpus on this machine")
def test_the_two_cache_read_shares_still_disagree() -> None:
    """The reason the unit changed, asserted rather than asserted-about.

    Cache reads are nearly all of the raw tokens and well under all of the
    money. If that gap ever closed, the page's scope strip would be printing a
    distinction that no longer exists and #72's argument would need re-making
    rather than re-rendering.

    Unpinned from any call count: this is a property of the corpus, not of one
    capture, and pinning it to 1,096 calls is how it came to skip silently for
    a day while the corpus grew twentyfold.
    """
    records = load_ingested(_CORPUS)
    days = [dt.date.fromisoformat(d["day"]) for d in _real_days()]
    scoped = scope_to_repo([r for r in records if min(days) <= r.day <= max(days)], _ROOT)
    assert scoped, "no calls from this repo in the window the page covers"

    priced = pricing.price_records(scoped)
    assert priced is not None

    raw = sum(r.usage.total for r in scoped)
    cache_read_raw = sum(r.usage.cache_read_tokens for r in scoped)
    cache_read_dollars = sum(
        (pricing.BASE_RATE_PER_MTOK.get(pricing.canonical(r.model) or "") or 0.0)
        * pricing.CACHE_READ
        * r.usage.cache_read_tokens
        / 1_000_000
        for r in scoped
    )

    token_share = cache_read_raw / raw
    dollar_share = cache_read_dollars / priced.dollars
    assert token_share > 0.95, f"cache reads are only {token_share:.1%} of the tokens"
    assert token_share - dollar_share > 0.20, (
        f"the two shares have converged: {token_share:.1%} of tokens against "
        f"{dollar_share:.1%} of dollars. #72's argument is that these differ."
    )
