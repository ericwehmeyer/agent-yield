"""The filer writes the dependency edge twice: as prose and as an API fact.

Only the second one gates anything. `scripts/pick-issue.py` reads GitHub's
`blockedBy` field, so a ticket set whose blockers live only in the body is a
set where every ticket is eligible at once -- measured on 2026-08-30 filing
#184 through #190, where the picker reported all seven eligible until the real
edges were added. These tests are mostly about that: that both copies come
from one field in the plan, and that a re-run repairs a set rather than
duplicating it.

Every test stubs `gh` itself, the script's one subprocess boundary, so nothing
here reaches a tracker. Above that line the code is under test, including how
it parses what `gh` returns.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "file-tickets.py"


def _load():
    spec = importlib.util.spec_from_file_location("file_tickets", _SCRIPT)
    assert spec and spec.loader, f"cannot load {_SCRIPT}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def filer():
    return _load()


class FakeGh:
    """Answers by command shape, and records what was created and linked."""

    def __init__(self, existing=None, blocked=None, fail_on_create=None):
        self.existing = dict(existing or {})     # title -> number
        self.blocked = {n: set(b) for n, b in (blocked or {}).items()}
        self.fail_on_create = fail_on_create
        self.created: list[tuple[str, str]] = []  # (title, body)
        self.edges: list[tuple[int, int]] = []    # (issue, blocker id)
        self.next_number = 100

    def __call__(self, args):
        if args[:2] == ["repo", "view"]:
            return 0, json.dumps({"nameWithOwner": "owner/name"}), ""
        if args[:2] == ["issue", "list"]:
            rows = [{"number": n, "title": t} for t, n in self.existing.items()]
            return 0, json.dumps(rows), ""
        if args[:2] == ["issue", "create"]:
            title = args[args.index("--title") + 1]
            body = args[args.index("--body") + 1]
            if self.fail_on_create and self.fail_on_create in title:
                return 1, "", "GraphQL: something went wrong"
            self.next_number += 1
            self.created.append((title, body))
            self.existing[title] = self.next_number
            return 0, f"https://github.com/owner/name/issues/{self.next_number}", ""
        if args[:2] == ["issue", "view"]:
            number = int(args[2])
            nodes = [{"number": b, "closed": False}
                     for b in sorted(self.blocked.get(number, ()))]
            return 0, json.dumps({"blockedBy": {"nodes": nodes}}), ""
        if args[0] == "api" and "--method" in args:
            number = int(args[args.index("--method") + 2].split("/")[4])
            blocker_id = int(args[-1].split("=")[1])
            self.edges.append((number, blocker_id))
            self.blocked.setdefault(number, set()).add(blocker_id - 1_000_000)
            return 0, "{}", ""
        if args[0] == "api":                      # the id lookup
            return 0, json.dumps(1_000_000 + int(args[1].split("/")[4])), ""
        raise AssertionError(f"unexpected gh call: {args}")


@pytest.fixture
def gh(filer, monkeypatch):
    fake = FakeGh()
    monkeypatch.setattr(filer, "gh", fake)
    return fake


TWO = """
repo = "owner/name"
parent = 50
label = "ready-for-agent"

[[ticket]]
key = "walk"
title = "The walk"
body = "It walks."

[[ticket]]
key = "guard"
title = "The guard"
blocked_by = ["walk"]
body = "It guards what #{{walk}} walked, under #{{parent}}."
"""


def plan(tmp_path, text: str) -> Path:
    path = tmp_path / "plan.toml"
    path.write_text(text, encoding="utf-8")
    return path


# --- the plan is refused before anything is sent -------------------------

def test_a_missing_plan_file_is_exit_2_and_sends_nothing(filer, gh, tmp_path):
    assert filer.main([str(tmp_path / "nope.toml")]) == 2
    assert gh.created == []


def test_a_plan_that_is_not_toml_is_exit_2(filer, gh, tmp_path, capsys):
    assert filer.main([str(plan(tmp_path, "[[ticket]\nkey ="))]) == 2
    assert "not valid TOML" in capsys.readouterr().out


def test_a_plan_with_no_tickets_is_exit_2(filer, gh, tmp_path, capsys):
    assert filer.main([str(plan(tmp_path, 'repo = "owner/name"\n'))]) == 2
    assert "no [[ticket]] tables" in capsys.readouterr().out


def test_a_ticket_missing_a_title_is_exit_2_and_says_which(filer, gh, tmp_path, capsys):
    text = '[[ticket]]\nkey = "a"\nbody = "x"\n'
    assert filer.main([str(plan(tmp_path, text))]) == 2
    assert "ticket 1 has no title" in capsys.readouterr().out


def test_a_duplicate_key_is_exit_2(filer, gh, tmp_path, capsys):
    text = ('[[ticket]]\nkey = "a"\ntitle = "one"\nbody = "x"\n'
            '[[ticket]]\nkey = "a"\ntitle = "two"\nbody = "y"\n')
    assert filer.main([str(plan(tmp_path, text))]) == 2
    assert "duplicate key" in capsys.readouterr().out


def test_a_blocker_defined_below_is_refused_rather_than_reordered(
        filer, gh, tmp_path, capsys):
    """Order in the file is the filing order, so a blocker cannot come later."""
    text = ('[[ticket]]\nkey = "a"\ntitle = "one"\nblocked_by = ["b"]\nbody = "x"\n'
            '[[ticket]]\nkey = "b"\ntitle = "two"\nbody = "y"\n')
    assert filer.main([str(plan(tmp_path, text))]) == 2
    out = capsys.readouterr().out
    assert "not defined above it" in out
    assert gh.created == []


def test_a_body_referencing_a_later_ticket_is_refused_and_names_it(
        filer, gh, tmp_path, capsys):
    """The forward reference that stopped the first hand-written filer."""
    text = ('[[ticket]]\nkey = "a"\ntitle = "one"\nbody = "see #{{b}}"\n'
            '[[ticket]]\nkey = "b"\ntitle = "two"\nbody = "y"\n')
    assert filer.main([str(plan(tmp_path, text))]) == 2
    out = capsys.readouterr().out
    assert "references b" in out
    assert gh.created == []


# --- the body it posts ---------------------------------------------------

def test_a_placeholder_becomes_the_number_the_blocker_actually_got(
        filer, gh, tmp_path):
    assert filer.main([str(plan(tmp_path, TWO))]) == 0
    guard_body = dict(gh.created)["The guard"]
    assert "It guards what #101 walked, under #50." in guard_body


def test_the_blocked_by_section_is_generated_from_the_field(filer, gh, tmp_path):
    assert filer.main([str(plan(tmp_path, TWO))]) == 0
    bodies = dict(gh.created)
    assert bodies["The guard"].rstrip().endswith("## Blocked by\n\n- #101")
    assert filer.NO_BLOCKERS in bodies["The walk"]


def test_the_parent_section_is_prepended_when_the_plan_names_one(
        filer, gh, tmp_path):
    assert filer.main([str(plan(tmp_path, TWO))]) == 0
    assert dict(gh.created)["The walk"].startswith("## Parent\n\n#50")


def test_no_parent_means_no_parent_section(filer, gh, tmp_path):
    text = '[[ticket]]\nkey = "a"\ntitle = "one"\nbody = "x"\n'
    assert filer.main([str(plan(tmp_path, text))]) == 0
    assert "## Parent" not in dict(gh.created)["one"]


# --- the edges, which are the half that gates the picker -----------------

def test_every_blocker_becomes_an_api_edge_not_only_prose(filer, gh, tmp_path):
    assert filer.main([str(plan(tmp_path, TWO))]) == 0
    # #102 blocked by #101, sent as #101's database id.
    assert gh.edges == [(102, 1_000_101)]


def test_an_edge_already_present_is_not_added_again(filer, tmp_path, monkeypatch):
    """A re-run repairs a half-linked set; it does not duplicate the links."""
    fake = FakeGh(existing={"The walk": 101, "The guard": 102},
                  blocked={102: {101}})
    monkeypatch.setattr(filer, "gh", fake)
    assert filer.main([str(plan(tmp_path, TWO))]) == 0
    assert fake.edges == []
    assert fake.created == []


def test_a_ticket_with_no_blockers_asks_for_no_edges(filer, gh, tmp_path):
    text = '[[ticket]]\nkey = "a"\ntitle = "one"\nbody = "x"\n'
    assert filer.main([str(plan(tmp_path, text))]) == 0
    assert gh.edges == []


# --- re-running --------------------------------------------------------

def test_an_existing_title_is_adopted_and_its_number_used_downstream(
        filer, tmp_path, monkeypatch, capsys):
    fake = FakeGh(existing={"The walk": 77})
    monkeypatch.setattr(filer, "gh", fake)
    assert filer.main([str(plan(tmp_path, TWO))]) == 0
    assert [title for title, _ in fake.created] == ["The guard"]
    assert "It guards what #77 walked" in dict(fake.created)["The guard"]
    assert "exists, adopted" in capsys.readouterr().out


def test_strict_refuses_a_plan_whose_titles_already_exist(
        filer, tmp_path, monkeypatch, capsys):
    fake = FakeGh(existing={"The walk": 77})
    monkeypatch.setattr(filer, "gh", fake)
    assert filer.main([str(plan(tmp_path, TWO)), "--strict"]) == 1
    assert "The walk" in capsys.readouterr().out
    assert fake.created == []


# --- the boundary failing ------------------------------------------------

def test_a_failed_create_is_exit_1_and_names_the_ticket(
        filer, tmp_path, monkeypatch, capsys):
    fake = FakeGh(fail_on_create="guard")
    monkeypatch.setattr(filer, "gh", fake)
    assert filer.main([str(plan(tmp_path, TWO))]) == 1
    out = capsys.readouterr().out
    assert "The guard" in out
    # The one that succeeded stays filed, which is why adoption exists.
    assert [title for title, _ in fake.created] == ["The walk"]


# --- dry run -------------------------------------------------------------

def test_dry_run_sends_nothing_and_reports_the_edge_count(
        filer, gh, tmp_path, capsys):
    assert filer.main([str(plan(tmp_path, TWO)), "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert gh.created == [] and gh.edges == []
    assert "2 ticket(s), 1 dependency edge(s), nothing sent" in out


def test_dry_run_names_blockers_by_key_because_it_has_no_numbers(
        filer, gh, tmp_path, capsys):
    """It printed `<- #-1` first, which reads as an edge to a real issue."""
    assert filer.main([str(plan(tmp_path, TWO)), "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "<- walk" in out
    assert "-1" not in out


def test_dry_run_still_refuses_a_forward_reference(filer, gh, tmp_path):
    """Validation is the point of a dry run, so it must not be skipped."""
    text = ('[[ticket]]\nkey = "a"\ntitle = "one"\nbody = "see #{{b}}"\n'
            '[[ticket]]\nkey = "b"\ntitle = "two"\nbody = "y"\n')
    assert filer.main([str(plan(tmp_path, text)), "--dry-run"]) == 2


# --- pure functions ------------------------------------------------------

def test_unresolved_reports_every_placeholder_left_standing(filer):
    assert filer.unresolved("a #{{x}} and #{{y}} and #{{x}}") == ["x", "y"]


def test_render_body_leaves_an_unknown_placeholder_alone_to_be_caught(filer):
    """Substitution does not guess; the caller refuses on what is left."""
    ticket = {"key": "a", "title": "t", "body": "#{{later}}"}
    body = filer.render_body(ticket, None, {})
    assert "{{later}}" in body
    assert filer.unresolved(body) == ["later"]
