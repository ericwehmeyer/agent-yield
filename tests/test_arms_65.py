"""#65's defect scorer, validated BEFORE either arm runs.

#47 validated its scorer against #33's four archived arms first, and that is the
only reason its AMBIGUOUS verdict could be trusted: an instrument that cannot
tell the known cases apart cannot tell a new one apart (#26, #32, #44). #65 has
no archived arms to check against -- its corpus is seeded rather than found -- so
the known cases are constructed here instead, from the same `ground-truth.json`
the run is scored with:

- an arm that quotes every seeded sentence must score 14 of 14;
- an arm that reports nothing must score 0, which is a RESULT and not a void;
- an arm that reports plausible mismatches about the same modules for reasons
  that are not the seeds must score 0 -- the false-positive leg, and the one a
  loose pattern would fail;
- the seeds themselves must still be present, exactly once, in the corpus the
  builder writes, and must all land inside a module docstring.
"""
import importlib.util
import json
from pathlib import Path

import pytest

EXPERIMENT = Path(__file__).resolve().parents[1] / "docs" / "experiments" / "65-depth"
TRUTH = json.loads((EXPERIMENT / "ground-truth.json").read_text(encoding="utf-8"))


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"exp65_{name}", EXPERIMENT / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_SCORE = _load("score")


@pytest.fixture(scope="module")
def score():
    return _SCORE


def arm_reporting(mismatches_by_module: dict[str, list[dict]]) -> dict:
    """A complete, well-formed arm answer -- every slice present exactly once."""
    return {"slices": [{"module": name, "claims": 3, "tests_passed": 5, "uncovered": 1,
                        "mismatches": mismatches_by_module.get(name, [])}
                       for name in _SCORE.SLICES]}


def test_an_arm_that_quotes_every_seed_scores_all_of_them(score):
    perfect = {seed["module"]: [{"claim": seed["new"], "why": seed["truth"]}]
               for seed in TRUTH["seeds"]}
    found = score.found(arm_reporting(perfect), TRUTH)
    assert sorted(found) == sorted(s["id"] for s in TRUTH["seeds"])


def test_an_arm_that_finds_nothing_scores_zero(score):
    # Zero seeds is the strongest DISPATCHING-side result, not a broken run, so
    # the scorer must return an empty list rather than raise or void.
    assert score.found(arm_reporting({}), TRUTH) == []


def test_plausible_findings_that_are_not_the_seeds_score_zero(score):
    # Same modules, real-sounding prose, none of it about the seeded sentence.
    decoys = {
        "agents.py": [{"claim": "the join is a heuristic and is labelled one",
                       "why": "the docstring says so and the code agrees; not a mismatch"}],
        "pricing.py": [{"claim": "verified against the CLI's own bill",
                        "why": "reconciliation lives in the test suite, not in this module"}],
        "report_html.py": [{"claim": "One file, no network",
                            "why": "the page embeds every style inline, which matches"}],
        "session.py": [{"claim": "This module is read-only; it never writes a file",
                        "why": "no write path exists here, so the claim holds"}],
        "usage.py": [{"claim": "Every total in this tool is built from a Usage",
                      "why": "that is a claim about other modules, not this one"}],
    }
    assert score.found(arm_reporting(decoys), TRUTH) == []


def test_the_slice_list_and_the_seeded_modules_agree(score):
    assert len(score.SLICES) == 23
    assert len(TRUTH["seeds"]) == 14
    for seed in TRUTH["seeds"]:
        assert seed["module"] in score.SLICES


def test_every_seed_lands_exactly_once_inside_a_module_docstring(tmp_path):
    import ast

    build = _load("build-corpus") if (EXPERIMENT / "build-corpus.py").exists() else None
    assert build is not None
    dest = tmp_path / "corpus"
    build.export(TRUTH["pinned_src"], dest)
    for seed in TRUTH["seeds"]:
        text = (dest / "src" / "agent_yield" / seed["module"]).read_text(encoding="utf-8")
        assert text.count(seed["old"]) == 1, seed["id"]
        assert seed["old"] in (ast.get_docstring(ast.parse(text)) or ""), seed["id"]
    build.seed(dest)
    for seed in TRUTH["seeds"]:
        text = (dest / "src" / "agent_yield" / seed["module"]).read_text(encoding="utf-8")
        assert seed["new"] in (ast.get_docstring(ast.parse(text)) or ""), seed["id"]
