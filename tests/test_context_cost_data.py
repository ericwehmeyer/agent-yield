"""`context-cost.html`'s figures, and the half of them nothing used to watch.

#87. `context-cost-data.py` exists because typed page numbers go stale
silently -- the page once carried two corpus snapshots at once, 20,757 calls
in the header against 20,255 in a legend, and nothing on it could have told
you. The generator's docstring said `--check` re-derived every figure and that
`--write` rewrote the prose. Neither was true: `main()` defined only `--write`
and `--json`, and `write()` replaced the two `const` blocks and nothing else.

That left the majority of the page unguarded -- the H1, all three tiles, both
medians, the caption series, the rules table's Worth column, the leverage
series, the legend call counts -- with a human reading a printed report as the
only thing standing between a `--write` on a moved corpus and the exact
two-snapshot state the file was written to prevent.

Three things are tested here, and the third is the one that matters.

* **`--check` agrees with the committed page.** The weakest of the three: on
  its own it would only prove the generator reproduces whatever is there.
* **`--check` goes red when a figure moves.** Once per kind of figure -- a
  prose number, a data block, a percentage series -- because the guard is
  three different mechanisms wearing one flag.
* **`--check` goes red when a sentence is REWORDED past its anchor.** This is
  the one that keeps the guard honest. Every other failure announces itself; a
  caption edited so the pattern no longer matches would leave that figure
  silently unchecked forever, which is #87 again one level down. The anchors
  are regexes over hand-written prose, so this is not hypothetical -- writing
  this file produced exactly that bug, an anchor reading `carries 96,567.`
  against a page that says `carries 96,567 tokens.`, and this is what caught it.

`test_docstring_promises_only_flags_that_exist` needs no corpus and so runs on
CI. It is the direct prevention for #87's own shape: a docstring naming a flag
the parser does not define. The rest are corpus-gated -- `.agent-yield/` is
gitignored -- and the skip is visible, for #29's reason.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_GENERATOR = _ROOT / "docs" / "context-cost-data.py"
_PAGE = _ROOT / "docs" / "context-cost.html"
_CORPUS = _ROOT / ".agent-yield" / "calls.jsonl"

needs_corpus = pytest.mark.skipif(
    not _CORPUS.exists(),
    reason=".agent-yield/calls.jsonl is gitignored; no corpus on this machine",
)


def _load():
    """Import the hyphenated generator by path; it is a script, not a package."""
    spec = importlib.util.spec_from_file_location("context_cost_data", _GENERATOR)
    assert spec and spec.loader, f"cannot load {_GENERATOR}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def module():
    return _load()


@pytest.fixture(scope="module")
def data(module):
    """One `build()` for the whole file; it reads 21k records."""
    return module.build()


@pytest.fixture(scope="module")
def page() -> str:
    return _PAGE.read_text(encoding="utf-8")


def test_docstring_promises_only_flags_that_exist(module) -> None:
    """#87 exactly: the docstring named a `--check` the parser did not define.

    Runs anywhere, because it needs no corpus -- which matters, since this is
    the guard against the defect recurring rather than against the page going
    stale. Any `--flag` the module docstring mentions must be a real option.
    """
    promised = sorted(set(re.findall(r"`(--[a-z][a-z-]*)`", module.__doc__ or "")))
    assert promised, "the docstring names no flags at all; has it been rewritten?"

    # Ask the real parser rather than a copy of it -- a copy would drift from
    # `main` the same way the docstring did. `--help` exits 0; argparse
    # rejects an unknown flag with exit 2 before help is ever printed.
    for flag in promised:
        with pytest.raises(SystemExit) as exit_info:
            module.main([flag, "--help"])
        assert exit_info.value.code == 0, (
            f"the docstring promises {flag}, but the parser rejects it. That is "
            "#87's defect: a file describing behaviour it does not have."
        )


@needs_corpus
def test_check_agrees_with_the_committed_page(module) -> None:
    """The acceptance criterion, run as a test: `--check` exists and passes."""
    assert module.main(["--check"]) == 0


@needs_corpus
def test_every_anchor_matches_the_page(module, data, page) -> None:
    """No anchor is dead.

    `diff` reports a non-matching pattern rather than skipping it, so this is
    already covered by the test above -- but that one fails with a single line
    and this one names the anchor, which is the difference between a minute
    and ten when a caption gets reworded.
    """
    dead = [label for label, pattern, _ in module._anchors(data)
            if not pattern.search(page)]
    assert not dead, f"anchors that no longer match the page: {dead}"


@needs_corpus
def test_check_passes_on_the_unmodified_text(module, data, page) -> None:
    assert module.diff(data, page) == []


@needs_corpus
@pytest.mark.parametrize(
    ("label", "before", "after"),
    [
        ("a prose median", "218,440 tokens", "218,441 tokens"),
        ("the headline", "We spent 3.21 billion", "We spent 3.22 billion"),
        ("a tile", '<span class="v">452M</span>', '<span class="v">453M</span>'),
        ("a decay series entry", "79%, 68%, 59%", "79%, 68%, 60%"),
        ("the leverage series", "1.29, 1.43", "1.29, 1.44"),
        ("a rules-table worth", "283M<br>", "284M<br>"),
        ("the legend", "Main session, 6,101 calls", "Main session, 6,102 calls"),
        ("a data block", '"median":218440', '"median":218441'),
    ],
)
def test_check_fails_when_a_figure_moves(module, data, page, label, before, after) -> None:
    """One case per kind of figure, because the guard is several mechanisms.

    A JSON block is compared by equality, a prose number by regex group, and a
    series by a joined string. Passing on one says nothing about the others.
    """
    assert before in page, f"the page no longer contains {before!r}; fixture is stale"
    stale = module.diff(data, page.replace(before, after, 1))
    assert stale, f"moving {label} did not make --check fail"


@needs_corpus
def test_check_fails_when_a_sentence_is_reworded_past_its_anchor(module, data, page) -> None:
    """The one that keeps the guard honest.

    Deleting the figure would be caught by anything. Rewording the sentence
    around it, leaving the number correct, is what silently switches a check
    off -- so `diff` treats a pattern that finds nothing as a disagreement,
    not as a pass.
    """
    reworded = page.replace(
        "median subagent call carries 96,567 tokens.",
        "typical subagent call runs to 96,567 tokens.",
        1,
    )
    assert reworded != page, "the fixture sentence is gone; update this test"

    stale = module.diff(data, reworded)
    assert any("no longer checked" in line for line in stale), (
        "a reworded sentence left its figure unguarded without failing. That is "
        "#87 one level down: the guard stops guarding and nothing goes red.\n"
        + "\n".join(stale)
    )


@needs_corpus
def test_page_figures_reproduce_without_the_generator(page) -> None:
    """The page's headline figures, derived straight from the corpus.

    The tests above compare the page to `build()`. That pair is only worth
    having if something also checks `build()` itself -- otherwise the
    generator grades its own arithmetic, which is N10's defect, where three
    `find_session` tests took their expectation from the function under test
    and so survived the morning's fix of it.

    So this one does not import the generator at all. It reads the corpus,
    does the arithmetic in four lines of `statistics`, and compares the result
    to what is typed on the page. A bug in `population()` that the page was
    regenerated from would pass every other test in this file and fail here.
    """
    import statistics

    from agent_yield.ingest import load_ingested

    records = load_ingested(_CORPUS)
    main_ctx = [r.context for r in records if not r.is_subagent]
    sub_ctx = [r.context for r in records if r.is_subagent]
    grand = sum(main_ctx) + sum(sub_ctx)

    expected = {
        "headline billions": (r"We spent ([\d.]+) billion", f"{grand / 1e9:.2f}"),
        "main call count": (r"Main session, ([\d,]+) calls", f"{len(main_ctx):,}"),
        "subagent call count": (r"Subagent, ([\d,]+) calls", f"{len(sub_ctx):,}"),
        "main median": (r"main-session calls carry more than ([\d,]+) tokens",
                        f"{int(statistics.median(main_ctx)):,}"),
        "subagent median": (r"median subagent call carries ([\d,]+) tokens",
                            f"{int(statistics.median(sub_ctx)):,}"),
    }
    for label, (pattern, want) in expected.items():
        found = re.search(pattern, page)
        assert found, f"{label}: no longer on the page"
        assert found.group(1) == want, f"{label}: page says {found.group(1)}, corpus says {want}"


@needs_corpus
def test_unreadable_data_block_is_reported_rather_than_raised(module, data, page) -> None:
    """A hand-edited block is a stale result, not a crash.

    `--check` has to survive the page it is most likely to be pointed at: one
    somebody edited by hand. It reports and exits 1.
    """
    broken = re.sub(r"^const D = \{.*?\};$", "const D = {oops};", page, count=1, flags=re.M)
    assert broken != page

    stale = module.diff(data, broken)
    assert stale and "cannot be checked" in stale[0], stale
