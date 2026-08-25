import pytest

from agent_yield.modes import ModeError, load_modes, mode_for


def test_loads_operator_tagged_sessions(tmp_path):
    path = tmp_path / "session-modes.toml"
    path.write_text(
        '[[session]]\nid = "588b0593"\nmode = "design"\n', encoding="utf-8"
    )
    assert load_modes(path) == {"588b0593": "design"}


def test_unknown_mode_is_rejected(tmp_path):
    path = tmp_path / "session-modes.toml"
    path.write_text('[[session]]\nid = "s1"\nmode = "vibes"\n', encoding="utf-8")
    with pytest.raises(ModeError, match="vibes"):
        load_modes(path)


def test_missing_file_is_empty_not_an_error(tmp_path):
    assert load_modes(tmp_path / "nope.toml") == {}


def test_untagged_sessions_are_untagged_never_guessed():
    assert mode_for("never-seen", {"s1": "build"}) == "untagged"
    assert mode_for(None, {"s1": "build"}) == "untagged"
