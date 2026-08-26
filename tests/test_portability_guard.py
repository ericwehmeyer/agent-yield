"""The guard: primitives whose platform behaviour was never thought about.

Five platform defects landed in one day, every one of them Windows-only,
every one silent, and four of the five found by accident while doing
something unrelated. The shape never varied -- a stdlib call whose default
differs by operating system, typed by someone with no reason at that moment
to wonder whether it did.

CI is the obvious answer and it is not sufficient: scored against those five
specimens, running the suite as it stands on `windows-latest` would have
caught **one** -- the symlink privilege, and only because it raises. The
other four fail by *succeeding differently*, and no matrix can see a
difference nothing asserts. Three of the five had no test on any platform;
a matrix would have turned them green on three operating systems instead of
one.

So this file is not a test of behaviour. It reads `src/` and `tests/` as
text and fails on the raw primitive itself, which is the only mechanism here
that catches a bug nobody has thought of yet -- statically, at authoring
time, on either machine, before push, with no test imagination required.
That was the thing actually missing.

Each rule names the issue it descends from, because a guard whose failure
message does not say *why* gets deleted by the next person it inconveniences.

This file exempts itself from its own rules: it must be free to spell the
banned primitives out in full. Nothing else is exempt.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_SOURCES = sorted(
    p
    for p in list((_ROOT / "src").rglob("*.py")) + list((_ROOT / "tests").rglob("*.py"))
    if p.name != Path(__file__).name
)


def _rel(path: Path) -> str:
    return path.relative_to(_ROOT).as_posix()


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _called(node: ast.Call) -> str:
    """The dotted name a call node invokes, as written."""
    func = node.func
    parts = []
    while isinstance(func, ast.Attribute):
        parts.append(func.attr)
        func = func.value
    if isinstance(func, ast.Name):
        parts.append(func.id)
    return ".".join(reversed(parts))


def _calls(path: Path, names: tuple[str, ...]) -> list[ast.Call]:
    """Every call to one of `names`, matched on the syntax tree, not the text.

    The first draft of this guard grepped, and its first run fired on a
    *docstring* in `test_outcomes.py` that quotes the banned call while
    explaining the bug. A guard that fires on prose gets satisfied by
    rewording prose, which is worse than no guard: it teaches the reflex of
    silencing the alarm. The tree only contains calls that will really run.
    """
    tree = ast.parse(_read(path), filename=str(path))
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and (_called(node).endswith(names) or _called(node) in names)
    ]


def _keywords(node: ast.Call) -> set[str]:
    return {kw.arg for kw in node.keywords if kw.arg}


@pytest.mark.parametrize("path", _SOURCES, ids=_rel)
def test_every_decoding_subprocess_call_names_its_encoding(path):
    """#41: a subprocess read decoded as cp1252 and corrupted the text.

    `subprocess.run(..., text=True)` with no `encoding=` decodes the child's
    bytes with `locale.getpreferredencoding()` -- cp1252 on Windows, UTF-8 on
    the other machine. Git speaks UTF-8 on both. The Windows read did not
    raise; it returned different text, which is why nothing noticed.

    The rule is about calls that DECODE, and the first draft was not: it
    demanded `encoding=` on every call, including binary ones. A call with no
    `text=` returns bytes, and bytes are the same on every platform -- the
    #43 test has to read raw bytes precisely because decoding is what hides
    the bug. A guard that bans the correct spelling of the fix teaches people
    to route around the guard.
    """
    offenders = [
        node.lineno
        for node in _calls(path, ("subprocess.run", "Popen"))
        if {"text", "universal_newlines"} & _keywords(node)
        and "encoding" not in _keywords(node)
    ]
    assert not offenders, (
        f"{_rel(path)}:{offenders} decodes a child's output with no encoding= "
        "-- cp1252 on Windows, UTF-8 elsewhere, silently and without raising "
        "(#41). Pass encoding='utf-8', errors='replace', or drop text= and "
        "read bytes."
    )


@pytest.mark.parametrize("path", _SOURCES, ids=_rel)
def test_no_path_rename(path):
    """#42: `Path.rename` raises on Windows when the target exists.

    POSIX `rename(2)` replaces silently, so the call reads as correct on the
    machine it was written on. On Windows every handoff after the first was
    lost. `os.replace` is the cross-platform spelling of what was meant.
    """
    offenders = [node.lineno for node in _calls(path, ("rename",))]
    assert not offenders, (
        f"{_rel(path)}:{offenders} calls .rename() -- it raises on Windows if "
        "the destination exists, where os.replace() overwrites (#42)."
    )


_SYMLINKERS = [p for p in _SOURCES if ".symlink_to(" in _read(p)]


@pytest.mark.parametrize("path", _SYMLINKERS, ids=_rel)
def test_every_symlink_in_the_suite_is_guarded(path):
    """The specimen that turned the build red rather than silently wrong.

    Creating a symlink on Windows needs Administrator or Developer Mode. It
    is a machine setting, not a platform constant, so the guard a test must
    carry is a *probe* -- either catching the OSError or skipping by name.
    Deleting the arm instead would be issue #29's silence: the Mac layout it
    reproduces is real and should still run where the privilege is held.
    """
    text = _read(path)
    for block in re.split(r"\ndef |\n    def ", text):
        if ".symlink_to(" not in block:
            continue
        guarded = "skip" in block or "OSError" in block
        assert guarded, (
            f"{_rel(path)} calls .symlink_to() in a function that neither "
            "catches OSError nor skips by name -- that is a red suite on any "
            "Windows box without Developer Mode."
        )


_STDIN_READER = "hookio.py"


@pytest.mark.parametrize("path", _SOURCES, ids=_rel)
def test_no_hook_reaches_for_sys_stdin_directly(path):
    """N3: `sys.stdin` decodes with the console code page on Windows.

    Hook payloads are UTF-8 JSON from node. Windows hands CPython a stdin
    whose encoding is cp1252 and whose errors are `surrogateescape`, so a
    payload naming a path with any non-ASCII character in it arrives corrupt
    and *nothing raises* -- the hook then measures nothing and exits 0.

    This is the one rule here that names a module rather than a primitive,
    because the fix is not a keyword argument: the stream has to be
    reconfigured before the first read, which is a thing to do rather than a
    thing to spell. Routing every hook through one reader is what makes the
    next hook correct by default -- `resume.py` has no observable corruption
    path today and would never have grown a test.
    """
    if path.name == _STDIN_READER:
        return
    tree = ast.parse(_read(path), filename=str(path))
    offenders = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and node.attr == "stdin"
        and isinstance(node.value, ast.Name)
        and node.value.id == "sys"
    ]
    assert not offenders, (
        f"{_rel(path)}:{offenders} reads sys.stdin directly -- on Windows that "
        "decodes UTF-8 hook payloads as cp1252, silently (#59, audit N3). Read it "
        f"through agent_yield.{_STDIN_READER[:-3]}.read_payload instead."
    )
