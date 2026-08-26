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


def test_a_named_metric_is_carried_through(tmp_path):
    path = tmp_path / "i.toml"
    path.write_text(
        '[[intervention]]\ndate = "2026-08-25"\nname = "n"\n'
        'expect = "subagent context/call falls under 30,000"\n'
        'metric = "subagent_context_per_call"\n',
        encoding="utf-8",
    )
    assert load_interventions(path)[0].metric == "subagent_context_per_call"


def test_an_intervention_with_no_metric_loads_and_is_not_scorable(tmp_path):
    """Absent is legal and it means UNSCORABLE, not "score it on something".

    Most predictions in this repo name quantities this tool cannot compute --
    tool calls per agent, transcript readability week over week, the cost of
    an experiment arm. Absent is the honest record of that. What is NOT legal
    is scoring such a prediction on whatever metric a CLI flag happened to
    default to, which is #44.
    """
    path = tmp_path / "i.toml"
    path.write_text(
        '[[intervention]]\ndate = "2026-08-25"\nname = "n"\n'
        'expect = "dispatched agents make under 20 tool calls each"\n',
        encoding="utf-8",
    )
    assert load_interventions(path)[0].metric is None


def test_a_metric_this_tool_cannot_compute_is_rejected_at_load(tmp_path):
    """A typo must be loud here, not silently UNSCORABLE later.

    The two failure modes are not symmetric: a prediction with no metric is a
    prediction nobody claimed was scorable, and a prediction naming
    `subagent_context_per_cal` is a claim that failed on a keystroke. Reading
    the second as the first is how a scorable prediction goes unscored for a
    week.
    """
    path = tmp_path / "i.toml"
    path.write_text(
        '[[intervention]]\ndate = "2026-08-25"\nname = "n"\n'
        'expect = "x"\nmetric = "subagent_context_per_cal"\n',
        encoding="utf-8",
    )
    with pytest.raises(InterventionError) as excinfo:
        load_interventions(path)
    assert "subagent_context_per_cal" in str(excinfo.value)
    assert "subagent_context_per_call" in str(excinfo.value)
