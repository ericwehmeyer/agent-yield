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
import subprocess
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


_WRITE_MODES = ("w", "a", "x", "+")


def _writes(node: ast.Call) -> bool:
    """Whether this `open` call is opening a text file for writing.

    The mode is the FIRST positional argument of `Path.open` and the SECOND of
    the builtin. The first draft read args[1:] for both, so every
    `PROBE_PATH.open("a", ...)` in the hooks read as mode "r" and the rule
    reported them clean -- a guard scoped one argument too narrowly says
    nothing while looking like it said yes.
    """
    positional = node.args if isinstance(node.func, ast.Attribute) else node.args[1:]
    mode = next(
        (a.value for a in positional
         if isinstance(a, ast.Constant) and isinstance(a.value, str)),
        None,
    )
    if mode is None:
        mode = next(
            (kw.value.value for kw in node.keywords
             if kw.arg == "mode" and isinstance(kw.value, ast.Constant)),
            "r",
        )
    return "b" not in mode and any(m in mode for m in _WRITE_MODES)


@pytest.mark.parametrize("path", sorted((_ROOT / "src").rglob("*.py")), ids=_rel)
def test_every_text_file_this_tool_writes_names_its_line_ending(path):
    r"""N11: these files are the tool's own record of its own measurements.

    A text write with no `newline=` gets `os.linesep` -- `\r\n` on Windows,
    `\n` everywhere else. Nothing breaks today: every internal reader goes
    through `splitlines()`, and `json.loads` tolerates a trailing `\r`. It is
    listed anyway because `calls.jsonl`, `handoff.md` and the probe logs are
    what this repo compares between two machines, and a file that differs
    byte-for-byte by platform is a bad thing to be comparing. `statusline`
    already slices one of these trees by byte offset.

    The rule is on `src/` only. Tests write fixtures whose bytes nobody
    carries anywhere, and a guard that fires where the property does not
    matter is how guards get switched off.
    """
    tree = ast.parse(_read(path), filename=str(path))
    offenders = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and (
            _called(node).endswith("write_text")
            or (_called(node).endswith("open") and _writes(node))
        )
        and "newline" not in _keywords(node)
    ]
    assert not offenders, (
        f"{_rel(path)}:{offenders} writes text with no newline= -- that is "
        r"\r\n on Windows and \n everywhere else, in a file this tool writes "
        r'to compare two machines (audit N11). Pass newline="\n".'
    )


# --- the data half of the same rule (#100) ---------------------------------
#
# Every rule above reads SOURCE and fails on a primitive. This one reads the
# repo's own BYTES, because the third instance of this root cause was not in
# any source file: it was a committed artifact.
#
# #70, #85 and #100 are one defect wearing three hats -- something written in
# whatever encoding the platform happened to be using, read back later with a
# fixed one. #100's specimen was a single 0xA7 (a `§`, typed on Windows at
# cp1252) inside `results/baton1v-r2/turn-1-result.txt`, which exists
# specifically so #33's CONTROL arm can be re-scored after its volatile
# transcripts are gone (`defects.py:36`). Every scorer opens `encoding="utf-8"`,
# so the control crashed its own scorer and the one fallback that was supposed
# to outlive the run was already dead.


def _committed_files() -> list[Path]:
    """What git tracks -- not `rglob`.

    `.venv/`, `.agent-yield/` and a local experiment's output all sit in this
    tree and none of them are what the repo publishes. The rule is about files
    that travel to the other machine, so the index is the right list.
    """
    try:
        done = subprocess.run(
            ["git", "ls-files", "-z"], cwd=_ROOT, capture_output=True,
            # encoding= named, and the irony is the point: this rule's own
            # subprocess call is exactly the primitive rule one bans (#41).
            text=True, encoding="utf-8", errors="replace", timeout=30)
    except (OSError, subprocess.SubprocessError):
        return []
    if done.returncode != 0:
        return []
    return [_ROOT / name for name in done.stdout.split("\0") if name]


def test_every_committed_file_decodes_as_utf8():
    r"""#100, and #70 and #85 before it: one root cause, three instances.

    One test rather than a parametrize over 217 files: the offender list is
    the finding here, and a sweep that reports "these three files" is more use
    than three separate red ids. The failure message names every one.

    Binary is skipped by looking for a NUL rather than by an extension list,
    because an extension list is a thing that goes stale quietly -- the same
    property this rule exists to defend. Today the repo tracks 217 files and
    not one of them contains a NUL.

    **Do not fix a failure here by loosening the reader to
    `errors="replace"`.** That turns the offending byte into U+FFFD and then
    everything downstream scores cleanly, which is the flattering direction
    and how this cause got to three instances. Fix the FILE: decode it in the
    encoding it was really written in, re-encode UTF-8, and check the round
    trip is exact before writing.
    """
    files = _committed_files()
    if not files:
        pytest.skip("git ls-files unavailable; nothing to enumerate")

    offenders = []
    for path in files:
        try:
            raw = path.read_bytes()
        except OSError:
            continue          # a tracked file this checkout does not have
        if b"\0" in raw:
            continue          # binary; not this rule's business
        try:
            raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            offenders.append(f"{_rel(path)}: {exc}")

    assert not offenders, (
        "committed files are not UTF-8:\n  " + "\n  ".join(offenders)
        + "\n\nEvery reader in this repo opens encoding=\"utf-8\", so a file "
        "written in the platform's own code page reads back as a crash on one "
        "machine and nowhere else (#70, #85, #100). Re-encode the file; do NOT "
        "loosen the reader."
    )


def test_a_module_that_reconfigures_stdout_reconfigures_stderr_too():
    r"""#116: the refusal an operator reads is the one that arrived corrupted.

    `cli.main` reconfigured stdout to UTF-8 and said why -- a section mark on a
    cp1252 stream leaves a bare 0xA7, which is not valid UTF-8, so a consumer
    decoding the stream fails on the WHOLE read rather than losing one glyph
    (#43). `gate.main` prints its refusal to STDERR, which was never
    reconfigured, and on 2026-08-28 the dispatch gate blocked a dispatch with

        this dispatch is missing output path (docs/working-method.md ?12)

    A PreToolUse hook's stderr IS the refusal reason the harness surfaces, so
    this is the one message in the system whose only job is to be read by a
    human at the moment they are blocked.

    The rule is a pair, not a stream: reconfiguring one and not the other is
    the defect, and either both or neither is defensible.
    """
    for path in sorted((_ROOT / "src").rglob("*.py")):
        tree = ast.parse(_read(path), filename=str(path))
        streams = {
            node.func.value.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "reconfigure"
            and isinstance(node.func.value, ast.Attribute)
            and node.func.value.attr in {"stdout", "stderr"}
        }
        assert streams in ({"stdout", "stderr"}, set()), (
            f"{_rel(path)} reconfigures {sorted(streams)} and not the other. "
            r"A section mark on a cp1252 stream leaves a bare 0xA7; the stream "
            "left alone is the one that corrupts (#116)."
        )
