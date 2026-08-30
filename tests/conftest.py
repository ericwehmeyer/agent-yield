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


# A git config the operator's machine cannot leak past. Same idea as
# `cp1252_stdin` above: reproduce the machine-specific failure on every
# platform, so the suite goes red everywhere rather than on one box.
#
# A fixture that shells out to `git` must build its child environment from
# scratch -- PATH, SystemRoot, and the four identity variables -- because an
# inherited one carries the operator's global config with it. On a box with
# `commit.gpgsign=true` behind a smartcard that made four tests wait on a PIN
# CI never has (#127), green on all six arms and red only where the file gets
# edited. `gpg.program` here names a binary that does not exist, so a fixture
# that inherits the environment fails its commit outright, everywhere, at
# authoring time.
_NO_SUCH_GPG = (
    "[commit]\n\tgpgsign = true\n"
    "[gpg]\n\tformat = openpgp\n\tprogram = no-such-gpg-binary\n"
)


@pytest.fixture(autouse=True, scope="session")
def poison_the_operators_git_config(tmp_path_factory):
    """The global scope only. The system scope is the platform's, not his.

    Measured, not assumed: poisoning `GIT_CONFIG_SYSTEM` as well costs a
    passing test. Git for Windows ships `core.autocrlf=true` in the system
    config, and with that scope replaced `dirty_paths` reads the fixture's own
    committed file back as `M old.txt`, so a clean tree announces itself
    dirty. The line the boundary falls on: global config is what the operator
    chose and what must never reach a fixture, system config is what the
    installer wrote and what the code under test is entitled to read.
    """
    config = tmp_path_factory.mktemp("gitconfig") / "no-such-gpg.gitconfig"
    config.write_text(_NO_SUCH_GPG, encoding="utf-8")
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("GIT_CONFIG_GLOBAL", str(config))
        yield config
