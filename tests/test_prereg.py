"""A pre-registration is appended by a tool, or it is appended by hand.

`interventions.toml` is 33,411 bytes of predictions that cannot be re-made
after the fact -- that is the whole point of the file. A hand-edit that breaks
the syntax does not lose the entry being added, it loses every entry already
there, and the loader's own error message points at the file rather than at
the edit. So the append is verified by reparsing, and these tests are written
against the failure that costs something rather than against the happy path.
"""
import tomllib
from pathlib import Path

import pytest

from agent_yield.prereg import PreregError, append_intervention

EXISTING = '''[[intervention]]
date   = "2026-08-01"
name   = "the one that was already there"
expect = "it survives whatever happens next"
'''


@pytest.fixture
def toml_file(tmp_path: Path) -> Path:
    path = tmp_path / "interventions.toml"
    path.write_text(EXISTING, encoding="utf-8")
    return path


def test_the_entry_is_readable_by_the_loader_that_will_score_it(toml_file):
    """Hand-counted: one entry in, one appended, two out -- and the first is
    still the first. Round-tripped through `tomllib`, not through the writer."""
    append_intervention(
        toml_file, date="2026-08-28", name="a second prediction",
        expect="something measurable changes", metric="tokens_per_insertion",
    )

    entries = tomllib.loads(toml_file.read_text(encoding="utf-8"))["intervention"]

    assert len(entries) == 2
    assert entries[0]["name"] == "the one that was already there"
    assert entries[1]["name"] == "a second prediction"
    assert entries[1]["metric"] == "tokens_per_insertion"
    assert str(entries[1]["date"]) == "2026-08-28"


def test_quotes_and_backslashes_in_the_prose_do_not_break_the_file(toml_file):
    """The characters a real prediction actually contains.

    `interventions.toml`'s existing entries quote metric names and name
    Windows paths, so this is the ordinary case rather than a hostile one.
    The text below is read back and compared to what went in: an escape that
    writes valid TOML but changes the prose has still lost the prediction.
    """
    prose = 'he said "no" about C:\\Users\\ewehm, and \\"that\\" is verbatim'
    append_intervention(
        toml_file, date="2026-08-28", name=prose, expect=prose)

    entries = tomllib.loads(toml_file.read_text(encoding="utf-8"))["intervention"]

    assert entries[1]["name"] == prose
    assert entries[1]["expect"] == prose


def test_a_prediction_with_no_expect_is_refused(toml_file):
    """`load_interventions` refuses it on read. Refusing it on write is where
    the operator can still do something about it."""
    with pytest.raises(PreregError):
        append_intervention(
            toml_file, date="2026-08-28", name="a name", expect="   ")


def test_a_metric_that_cannot_be_computed_is_refused_before_it_is_written(toml_file):
    """A metric that does not exist is a claim that failed on a keystroke, and
    the loader says so -- but only on the next read, which may be days later."""
    with pytest.raises(PreregError):
        append_intervention(
            toml_file, date="2026-08-28", name="a name",
            expect="a prediction", metric="tokens_per_vibe")


def test_a_refused_append_leaves_the_file_byte_identical(toml_file):
    """The failure that costs something. A half-written entry is a corrupt
    file, and the entries it destroys are ones nobody can honestly re-make."""
    before = toml_file.read_bytes()

    with pytest.raises(PreregError):
        append_intervention(
            toml_file, date="2026-08-28", name="", expect="a prediction")

    assert toml_file.read_bytes() == before
