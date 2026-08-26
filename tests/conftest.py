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
