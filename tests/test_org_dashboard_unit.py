"""The org dashboard's numerator unit, and the two ways it can rot.

#72. The prototype's headline was `tokens per inserted line`, summing raw
`usage.total`. `thresholds.py` L76 calls that unit crude in the same file the
page was told to read: ~97% of the sum is cache reads at 0.10x a base input
token, so a team that restarts sessions often -- this repo's own recommended
discipline -- posts a lower total for the same work and ranks better. A
Director reassigning headcount would be reassigning it on a cache-hit ranking.
The headline is now list-price dollars per 1,000 inserted lines.

Two failure modes, and this file has one test for each:

* **The constants drift.** `PRICING` in `dashboard.html` is a hand-copy of
  `pricing.py`'s rate table. A copy that silently disagrees with its source is
  N2's shape one level up, and it fails in whichever direction the stale copy
  happens to point. `test_page_pricing_matches_pricing_py` reads both.
* **The old unit creeps back onto a tile.** `tok/ins` is kept as a labelled
  secondary and is allowed exactly one home. `test_no_raw_token_ratio_on_a_tile`
  reads the page as text, in the manner of `test_portability_guard.py`, because
  the thing being prevented is an edit nobody has made yet.

And one that only runs where the corpus is: `.agent-yield/` is gitignored, so
CI has no `calls.jsonl` and cannot re-derive anything. Where the corpus DOES
exist, the day literals on the page are checked against `pricing.py` over the
same 1,096 calls. The skip is visible -- CI runs `pytest -rs` for exactly the
reason #29 documents, that a silent skip reads as a pass.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

import pytest

from agent_yield import pricing
from agent_yield.ingest import load_ingested
from agent_yield.report import scope_to_repo

_ROOT = Path(__file__).resolve().parent.parent
_PAGE = _ROOT / "docs" / "experiments" / "org-dashboard" / "dashboard.html"
_CORPUS = _ROOT / ".agent-yield" / "calls.jsonl"

# The window the page froze, and the scope line it prints.
_SINCE, _UNTIL = dt.date(2026, 8, 25), dt.date(2026, 8, 26)
_SCOPED_CALLS = 1096

pytestmark = pytest.mark.skipif(not _PAGE.exists(), reason="prototype deleted (see design.md's falsifier)")


def _page() -> str:
    return _PAGE.read_text(encoding="utf-8")


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


@pytest.mark.skipif(not _CORPUS.exists(), reason=".agent-yield/calls.jsonl is gitignored; no corpus on this machine")
def test_real_days_reproduce_from_pricing_py() -> None:
    """The page's dollar literals are what `pricing.py` says, to the cent.

    The prototype freezes its one real leaf as literals because it is a static
    file with no build step. Frozen literals are the honest form -- the page
    also prints its capture time -- but frozen and UNCHECKED is how #44 and #46
    shipped, so where the corpus is on disk, this recomputes them.
    """
    records = load_ingested(_CORPUS)
    windowed = [r for r in records if _SINCE <= r.day <= _UNTIL]
    scoped = scope_to_repo(windowed, _ROOT)

    if len(scoped) != _SCOPED_CALLS:
        pytest.skip(
            f"the corpus has moved on: {len(scoped)} calls in this window, not "
            f"{_SCOPED_CALLS}. The page is pinned to a capture, not to a live count."
        )

    page = _page()
    for day_literal in re.finditer(
        r'\{ day: "(\d{4}-\d\d-\d\d)",[^}]*?dollars: ([0-9.]+), crUsd: ([0-9.]+), crTok: (\d+),\s*'
        r"unpricedTok: (\d+)",
        page,
        re.S,
    ):
        day = dt.date.fromisoformat(day_literal.group(1))
        on_page = float(day_literal.group(2))
        cr_on_page = float(day_literal.group(3))
        cr_tok_on_page = int(day_literal.group(4))
        unpriced_on_page = int(day_literal.group(5))

        rows = [r for r in scoped if r.day == day]
        priced = pricing.price_records(rows)
        assert priced is not None, f"{day} priced to nothing"

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

        assert round(priced.dollars, 4) == on_page, f"{day}: page says ${on_page}, pricing.py says ${priced.dollars:.4f}"
        assert round(cache_read_dollars, 4) == cr_on_page, f"{day}: cache-read dollars"
        assert cache_read_tokens == cr_tok_on_page, f"{day}: cache-read tokens"
        assert unpriced_tokens == unpriced_on_page, f"{day}: unpriced tokens"


@pytest.mark.skipif(not _CORPUS.exists(), reason=".agent-yield/calls.jsonl is gitignored; no corpus on this machine")
def test_the_two_cache_read_shares_still_disagree() -> None:
    """The reason the unit changed, asserted rather than asserted-about.

    Cache reads are nearly all of the raw tokens and well under all of the
    money. If that gap ever closed, the page's scope strip would be printing a
    distinction that no longer exists and #72's argument would need re-making
    rather than re-rendering.
    """
    records = load_ingested(_CORPUS)
    scoped = scope_to_repo([r for r in records if _SINCE <= r.day <= _UNTIL], _ROOT)
    if len(scoped) != _SCOPED_CALLS:
        pytest.skip(f"the corpus has moved on: {len(scoped)} calls, not {_SCOPED_CALLS}")

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
