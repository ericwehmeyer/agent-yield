"""Fixtures shared across the suite.

`cp1252_stdin` exists because every hook test in this repo injects
`io.StringIO`, and a `StringIO` carries no encoding at all. The seam is the
right one -- `main(stdin=...)` -- but it is transparent, so the class of bug
that owns two of the five platform specimens (#41, #43) and the audit's N3 is
structurally invisible to the suite on every platform, this box included.

Wrapping the real UTF-8 bytes in a stream that *declares* cp1252 reproduces
the Windows console on macOS and Linux. The test then fails everywhere
without the fix, which is the property that makes it worth having.
"""

from __future__ import annotations

import io
import json

import pytest

from agent_yield import boundary


@pytest.fixture
def cp1252_stdin():
    """A hook payload as UTF-8 bytes behind a stream that claims cp1252.

    `surrogateescape` matches what CPython gives `sys.stdin` on Windows: the
    undefined code points are absorbed rather than raised on, so the
    corruption is silent -- which is the whole difficulty.
    """
    def make(payload: dict) -> io.TextIOWrapper:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        return io.TextIOWrapper(
            io.BytesIO(raw), encoding="cp1252", errors="surrogateescape"
        )

    return make


@pytest.fixture(autouse=True)
def _no_test_commit_is_signed(monkeypatch):
    """No fixture commits with the operator's key, whatever their config says.

    #127 was this, fixed in one file. It came back on 2026-08-30 in another:
    `test_handoff.py` built its subprocess environment from `os.environ` and
    set author and committer but not signing, so it inherited a global
    `commit.gpgsign = true`.

    That was survivable while the key signed without a physical act. It stopped
    being survivable the moment the YubiKey's touch policy went to `Sign=on`:
    four tests then waited out a pinentry timeout each and failed at exit 128,
    and the suite went from 26 seconds to 265. A test that needs a human to
    touch a device is not a test.

    Suite-wide and by environment rather than per-file and by argument, because
    the per-file fix has now been made twice and missed twice. `GIT_CONFIG_*`
    reaches every `git` a test starts, including ones written later by someone
    who never read this. A test that deliberately exercises signing sets its
    own numbered overrides and wins, because it writes the same indices.
    """
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "commit.gpgsign")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "false")


@pytest.fixture(autouse=True)
def _refusal_sentinel_stays_in_tmp(tmp_path, monkeypatch):
    """No test spends the live repo's one refusal.

    Autouse and suite-wide rather than per-file: the boundary's refusal is
    now recorded on disk, so a test that runs `--enforce` without redirecting
    the sentinel writes real session state and then passes or fails depending
    on whether the suite has run before. That is #69's defect in a new place,
    and the second run is the one that catches it.
    """
    monkeypatch.setattr(boundary, "REFUSAL_SPENT_PATH",
                        tmp_path / "boundary-refusal-spent")
    monkeypatch.setattr(boundary, "REFUSAL_LOG_PATH",
                        tmp_path / "boundary-refusals.jsonl")
