r"""#59: the four hooks read `sys.stdin` with no encoding -- the inbound twin.

#41 was a subprocess read decoded as cp1252. #43 was stdout encoded as
cp1252. Both were fixed. The same defect on the *inbound* side of the process
boundary was never filed, and it is the worst of the three: hook payloads are
UTF-8 JSON produced by node, `sys.stdin` on Windows decodes with the console
code page, and `surrogateescape` absorbs every undefined byte without raising.

Measured on this machine (CPython 3.14.4, `utf8_mode 0`), fed a payload whose
`transcript_path` is `C:\Users\Jose\s.jsonl` with an acute accent:

    want : 'C:\Users\Jos\xe9\s.jsonl'
    got  : 'C:\Users\Jos\xc3\xa9\s.jsonl'

`resolve_transcript` then finds no such file, and every hook here swallows
the outcome in `except Exception: return 0`. Any operator whose Windows
account name or repo path carries a non-ASCII character measures nothing,
permanently and without a symptom.

Each test below asserts the *consequence*, not the decode: a transcript that
is found, a brief marker that is still recognised. They fail on Linux and
macOS too, because the hostile stream is the fixture rather than the
platform -- the transferable half of #43's lesson.

`resume` is absent from this file on purpose. It reads only `source` and
`hook_event_name` from the payload, both ASCII, so today it has no observable
corruption path. The guard rule in `test_portability_guard.py` covers it and
every hook written after this one; that is the mechanism for a defect nobody
has a test for yet.
"""

from __future__ import annotations

import json
from pathlib import Path

from agent_yield import boundary, statusline
from agent_yield.gate import main as gate_main
from agent_yield.statusline import QUIET, main as statusline_main

# U+00E9. Two bytes in UTF-8, one undefined round trip through cp1252.
ACCENTED = "Jos\u00e9"


def _transcript(tmp_path: Path, reads: list[int], name: str) -> Path:
    """A transcript under a directory whose name is not ASCII."""
    home = tmp_path / ACCENTED
    home.mkdir(exist_ok=True)
    lines = [
        json.dumps({
            "timestamp": f"2026-08-26T02:{index // 60:02d}:{index % 60:02d}.000Z",
            "sessionId": name, "requestId": f"req-{index}",
            "message": {"id": f"msg-{index}",
                        "usage": {"cache_read_input_tokens": read}},
        })
        for index, read in enumerate(reads)
    ]
    path = home / f"{name}.jsonl"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_statusline_measures_a_transcript_under_an_accented_path(
    tmp_path, capsys, cp1252_stdin
):
    transcript = _transcript(tmp_path, [20_000] * 20, "s")
    assert statusline_main([], stdin=cp1252_stdin({
        "hook_event_name": "Status",
        "transcript_path": str(transcript),
    })) == 0
    line = capsys.readouterr().out.strip()
    assert line != QUIET, "the transcript path did not survive stdin"
    assert line == "ay 20K 2% 1.0x"


def test_boundary_measures_a_transcript_under_an_accented_path(
    tmp_path, monkeypatch, capsys, cp1252_stdin
):
    monkeypatch.setattr(boundary, "DEFAULT_HANDOFF_PATH", tmp_path / "none.md")
    transcript = _transcript(tmp_path, [10_000] * 10 + [60_000] * 10, "grown")
    code = boundary.main(["--enforce"], stdin=cp1252_stdin({
        "hook_event_name": "UserPromptSubmit",
        "transcript_path": str(transcript),
        "prompt": "hi",
    }))
    assert code == 2, "the transcript path did not survive stdin"
    assert "agent-yield" in capsys.readouterr().err


# §12's four brief parts, with the line range written the way a person types
# it rather than the way ASCII allows. `_LINE_RANGE_RE` accepts U+2013 for
# exactly this reason -- and cp1252 turns those three bytes into three other
# characters, so the marker the brief carries stops being found.
EN_DASH_BRIEF = (
    "Read gate.py lines 22 \u2013 58. Do not explore; if you need a file "
    "not listed, say so and stop. Write your findings to /tmp/out.md. "
    "Return only the file:line list and one verdict line, nothing else."
)


def test_gate_recognises_a_brief_whose_line_range_uses_an_en_dash(
    capsys, cp1252_stdin
):
    assert gate_main([], stdin=cp1252_stdin({
        "hook_event_name": "PreToolUse",
        "tool_name": "Agent",
        "tool_input": {
            "description": "A properly briefed dispatch",
            "subagent_type": "general-purpose",
            "prompt": EN_DASH_BRIEF,
        },
        "_day_total": 0,
    })) == 0
    printed = capsys.readouterr().out
    assert printed == "", (
        "the gate warned about a brief that carries every marker -- the en "
        f"dash did not survive stdin: {printed}"
    )
