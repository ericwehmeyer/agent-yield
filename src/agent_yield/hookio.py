r"""The one place a hook payload is decoded.

Claude Code hands every hook a UTF-8 JSON payload on stdin. CPython does not
decode it that way: `sys.stdin` uses `locale.getpreferredencoding()`, which is
cp1252 on a stock Windows box and UTF-8 on the other two platforms. Nothing
raises when it goes wrong -- Windows also sets `errors="surrogateescape"`, so
the undefined code points are absorbed and the payload arrives *quietly*
different. A `transcript_path` under `C:\Users\Jose\` with an acute accent
resolves to a file that does not exist, `resolve_transcript` returns None, and
the hook says nothing and exits 0. That is indistinguishable from a healthy
session with nothing to report.

This is the inbound half of the pair fixed in #41 (a subprocess read) and #43
(stdout), and it is the half nobody filed. It lives in its own module rather
than as four copies of one line because `test_portability_guard.py` can then
state the rule as "no hook touches sys.stdin", which is checkable, instead of
"every hook remembers to reconfigure it", which is a hope.
"""

from __future__ import annotations

import sys
from typing import TextIO


def read_payload(stream: TextIO | None = None) -> str:
    """Read a hook's whole stdin as UTF-8, whatever the console code page is.

    `stream` is the injected test seam; None means the real stdin.

    Reconfiguring is deliberate rather than reading `stream.buffer` and
    decoding: it works on the real `sys.stdin` and on a `TextIOWrapper` a test
    hands in declaring a hostile encoding, so the fixture that reproduces
    Windows on Linux exercises this exact line. Streams that cannot be
    reconfigured -- `io.StringIO`, which most of this suite injects, and a
    stream already read from -- carry no encoding to get wrong, so failing to
    reconfigure them is correct rather than tolerated.
    """
    if stream is None:
        stream = sys.stdin
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure is not None:
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass
    return stream.read()
