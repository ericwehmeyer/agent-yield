import datetime as dt

import pytest

from agent_yield.interventions import (
    Intervention,
    InterventionError,
    load_interventions,
)

GOOD = '''
[[intervention]]
date = "2026-08-25"
name = "brief-pack: agents stop rediscovering the repo"
expect = "per-agent median falls from 12.4M"
'''


def test_loads_a_well_formed_intervention(tmp_path):
    path = tmp_path / "interventions.toml"
    path.write_text(GOOD, encoding="utf-8")
    assert load_interventions(path) == [Intervention(
        date=dt.date(2026, 8, 25),
        name="brief-pack: agents stop rediscovering the repo",
        expect="per-agent median falls from 12.4M",
    )]


def test_missing_expect_is_rejected_loudly(tmp_path):
    path = tmp_path / "interventions.toml"
    path.write_text(
        '[[intervention]]\ndate = "2026-08-25"\nname = "x"\n', encoding="utf-8"
    )
    with pytest.raises(InterventionError, match="expect"):
        load_interventions(path)


def test_whitespace_only_expect_is_rejected(tmp_path):
    path = tmp_path / "interventions.toml"
    path.write_text(
        '[[intervention]]\ndate = "2026-08-25"\nname = "x"\nexpect = "  "\n',
        encoding="utf-8",
    )
    with pytest.raises(InterventionError, match="expect"):
        load_interventions(path)


def test_missing_file_is_an_empty_list_not_an_error(tmp_path):
    assert load_interventions(tmp_path / "nope.toml") == []


def test_interventions_come_back_in_date_order(tmp_path):
    path = tmp_path / "interventions.toml"
    path.write_text(
        '[[intervention]]\ndate = "2026-08-26"\nname = "b"\nexpect = "y"\n'
        '[[intervention]]\ndate = "2026-08-25"\nname = "a"\nexpect = "x"\n',
        encoding="utf-8",
    )
    assert [i.name for i in load_interventions(path)] == ["a", "b"]
