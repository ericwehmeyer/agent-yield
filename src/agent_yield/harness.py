"""Render this machine's `.claude/settings.json` from a tracked template.

Why the live file is not the tracked one
---------------------------------------
It was, for one commit. `6d35b47` shipped `.claude/settings.json` so the four
hooks would be reviewable in a diff, and the file it shipped hard-coded
`C:/Users/ewehm/repos/agent-yield/.venv/Scripts/agent-yield.exe`. Pulling it
onto the Mac did not fail loudly. `.gitignore` still said `.claude/` at the
instant of checkout, git overwrites *ignored* files without a word because
ignored means expendable, and the Mac's four working hooks were gone with no
copy anywhere on the disk (#125).

So the tracked artefact is `settings.template.json`, which names no machine,
and the live file is rendered from it. ADR-0001's argument survives intact --
the instrument is configuration and must be diffable -- it just moves one level
up, to the file that is true on both machines rather than on one.

Two properties are load-bearing, and both were the bug
-----------------------------------------------------
**Relative to the project root.** The template stores `.venv` and nothing
above it, so no user name, drive letter or checkout location is ever written
down in a tracked file. The rendered command is absolute, resolved from the
root at render time -- not left relative. A hook's working directory is the
harness's to choose, not this repo's, and a relative command that is wrong
about it fails on every call and reports that failure nowhere. Derived from
the root is the property that matters; relative on disk is a different and
weaker one.

**OS-tolerant.** `.venv/bin/agent-yield` against `.venv/Scripts/agent-yield.exe`
is not a substitution one string absorbs, and reaching for an environment
variable only moves the problem (`$VAR` against `%VAR%`). The executable is
therefore found by *looking* -- the candidates are probed on disk, in an order
that puts this platform's convention first, and the platform default is only a
tiebreak for a venv that does not exist yet. A venv laid out unusually (an
msys-style `bin` on Windows) is found rather than assumed away.

Refusing beats overwriting, because that is the defect
------------------------------------------------------
`install()` will not replace a live file it does not recognise. A file whose
hooks match the template's *shape* -- same events, same matchers, same
arguments, some other machine's executable -- is a rendered file and is
replaced. Anything else is a hand edit or an unrelated configuration, and it is
reported rather than destroyed. Silently replacing a config that took work to
build is precisely what #125 is about, and a tool that fixes a defect by
committing it again has fixed nothing.

`settings.local.json` is unrendered, and is checked anyway
----------------------------------------------------------
It is machine state by design and this tool never writes it, but it wires hooks
onto the same tool calls the rendered file does. It ran
`.claude/hooks/probe.py` -- this repo's script -- under
`C:/Users/ewehm/repos/migration-kit/.venv/Scripts/python.exe`, another
checkout's virtualenv (#113). Rebuilding that unrelated venv would have broken
every tool call in this repo, and the 5s hook timeout means the symptom is
latency rather than an error anybody reads.

So `check()` reports a hook interpreter that lives outside this checkout. It
does not fix or rewrite the file: the fix is one token and belongs to whoever
owns that machine's local settings. Naming it is the part no machine was doing.
"""
from __future__ import annotations

import difflib
import json
import os
from pathlib import Path

PLACEHOLDER = "{{AGENT_YIELD}}"

TEMPLATE_PATH = Path(".claude") / "settings.template.json"
LIVE_PATH = Path(".claude") / "settings.json"
LOCAL_PATH = Path(".claude") / "settings.local.json"

VENV_DIR = Path(".venv")

# Every layout worth probing, as (bin directory, executable name). Ordered
# per-platform below; membership here is what makes an odd venv findable.
_LAYOUTS = (
    ("bin", "agent-yield"),
    ("Scripts", "agent-yield.exe"),
    ("Scripts", "agent-yield"),
    ("bin", "agent-yield.exe"),
)


class HarnessError(RuntimeError):
    """The harness cannot be rendered, and saying why beats writing a guess."""


def _candidates() -> tuple[tuple[str, str], ...]:
    """`_LAYOUTS` with this platform's convention first.

    Order matters only when two layouts both exist, which happens on a machine
    that has built the venv under both WSL and native Windows against one
    checkout. Preferring the running platform's own is the only defensible
    tiebreak: the hook is executed by this OS.
    """
    windows = os.name == "nt"
    preferred = "Scripts" if windows else "bin"
    return tuple(
        sorted(_LAYOUTS, key=lambda layout: 0 if layout[0] == preferred else 1)
    )


def resolve_executable(root: Path) -> Path | None:
    """The `agent-yield` console script inside `root`'s venv, or None.

    None rather than a guess. A rendered command pointing at a file that is not
    there is a hook that fails on every call, and the harness reports that
    failure in a place nobody reads -- which is how the Mac ran for 98 seconds
    on a Windows path without anything on screen saying so.
    """
    for bindir, name in _candidates():
        candidate = root / VENV_DIR / bindir / name
        if candidate.is_file():
            return candidate
    return None


def command_for(executable: Path) -> str:
    """The executable as it goes into a hook command string.

    POSIX separators on both platforms: forward slashes are what the Windows
    box has been executing since `6d35b47` and what it is known to accept, and
    changing a working invocation while fixing an unrelated defect is how a
    one-machine bug becomes a two-machine one.

    Quoted only when the path contains a space. An unquoted path with no space
    is byte-identical to what already runs on Windows, so this fix does not
    silently re-render that machine's hooks into a form nobody has tested.
    """
    text = executable.as_posix()
    return f'"{text}"' if " " in text else text


def render(template_text: str, executable: Path) -> str:
    """Substitute the placeholder, and refuse to emit anything unparseable.

    The substitution is textual so the rendered file keeps the template's own
    formatting and a diff between them reads as one changed token per hook. The
    result is parsed before it is returned: a template edited into invalid JSON
    would otherwise be discovered by the harness at session start, where the
    error is a hook that did not fire rather than a message.
    """
    if PLACEHOLDER not in template_text:
        raise HarnessError(
            f"{TEMPLATE_PATH} contains no {PLACEHOLDER}: nothing to render, and "
            "a template with the executable already baked in is the bug in #125"
        )
    rendered = template_text.replace(PLACEHOLDER, command_for(executable))
    try:
        json.loads(rendered)
    except json.JSONDecodeError as exc:
        raise HarnessError(f"rendered settings are not valid JSON: {exc}") from exc
    return rendered


def _split_executable(command: str) -> str:
    """The arguments of a hook command, with its executable removed.

    Used to compare two machines' files for sameness of *instrument*. The
    executable is the one token allowed to differ; everything after it --
    `resume --hook --probe`, `gate --enforce-brief` -- is the configuration,
    and a difference there is a real difference.
    """
    text = command.strip()
    if text.startswith('"'):
        end = text.find('"', 1)
        return text[end + 1:].strip() if end != -1 else ""
    _, _, rest = text.partition(" ")
    return rest.strip()


def _shape(document: str) -> object:
    """A settings document reduced to what must match across machines."""
    def strip(node: object) -> object:
        if isinstance(node, dict):
            out = {}
            for key, value in node.items():
                if key == "command" and isinstance(value, str):
                    out[key] = _split_executable(value)
                else:
                    out[key] = strip(value)
            return out
        if isinstance(node, list):
            return [strip(item) for item in node]
        return node

    return strip(json.loads(document))


def _same_shape(left: str, right: str) -> bool:
    try:
        return _shape(left) == _shape(right)
    except json.JSONDecodeError:
        return False


def _executables_in(document: str) -> list[str]:
    """Every hook command's executable, for diagnosing a foreign render."""
    found: list[str] = []

    def walk(node: object) -> None:
        if isinstance(node, dict):
            if node.get("type") == "command" and isinstance(node.get("command"), str):
                text = node["command"].strip()
                if text.startswith('"'):
                    end = text.find('"', 1)
                    found.append(text[1:end] if end != -1 else text[1:])
                else:
                    found.append(text.split(" ", 1)[0])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    try:
        walk(json.loads(document))
    except json.JSONDecodeError:
        return []
    return found


def _looks_absolute(text: str) -> bool:
    """Absolute under either OS's rules, not just the one running.

    `Path("C:/x").is_absolute()` is False on POSIX, so the check that matters
    most -- the Mac reading a Windows-authored local settings file -- is the one
    the standard test would skip. A bare `python` or a `.venv/...` relative to
    an unknown working directory is not judged here: it names no other checkout,
    and guessing what it resolves to would report a defect that may not exist.
    """
    if text.startswith(("/", "\\")):
        return True
    return len(text) > 2 and text[1] == ":" and text[2] in "/\\"


def _within(text: str, root: Path) -> bool:
    """Is this path token inside `root`? Compared as text, both ways round.

    A resolved comparison would need the path to exist, and the whole point is
    to name an interpreter that may well have been deleted. Case-insensitive on
    Windows because `C:/Users` and `c:/users` are one directory there.
    """
    prefix = root.as_posix().rstrip("/") + "/"
    candidate = text.replace("\\", "/")
    if os.name == "nt":
        prefix, candidate = prefix.casefold(), candidate.casefold()
    return candidate.startswith(prefix)


def foreign_interpreters(root: Path) -> list[str]:
    """Hook interpreters in `settings.local.json` that live outside this clone.

    Every one of these makes a tool call in this repo depend on a directory
    this repo does not own. Order preserved and duplicates dropped: the same
    interpreter usually wires several hooks, and repeating it makes the report
    longer without making it truer.
    """
    path = root / LOCAL_PATH
    if not path.is_file():
        return []
    found: list[str] = []
    for text in _executables_in(path.read_text(encoding="utf-8")):
        if not _looks_absolute(text) or _within(text, root):
            continue
        if text not in found:
            found.append(text)
    return found


def _foreign_interpreter_report(root: Path) -> str:
    """The #113 section of `check()`'s output, or empty when there is none."""
    foreign = foreign_interpreters(root)
    if not foreign:
        return ""
    lines = [
        f"FOREIGN INTERPRETER: {LOCAL_PATH} runs {len(foreign)} hook "
        f"{'command' if len(foreign) == 1 else 'commands'} under an executable "
        "outside this checkout, so every matching tool call here depends on "
        "another directory staying where it is:",
    ]
    lines.extend(f"  {text}" for text in foreign)
    lines.append(
        f"Point them at this clone's own venv ({root / VENV_DIR}). This tool "
        f"does not edit {LOCAL_PATH}, which is machine state."
    )
    return "\n".join(lines)


def _read_template(root: Path) -> str:
    path = root / TEMPLATE_PATH
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise HarnessError(f"no template at {path}") from exc


def _expected(root: Path) -> str:
    executable = resolve_executable(root)
    if executable is None:
        raise HarnessError(
            f"no agent-yield console script under {root / VENV_DIR}: build the "
            "venv first. Rendering a command that points at nothing would "
            "install hooks that fail on every call and say so nowhere."
        )
    return render(_read_template(root), executable)


def _diff(live: str, expected: str) -> str:
    return "".join(
        difflib.unified_diff(
            live.splitlines(keepends=True),
            expected.splitlines(keepends=True),
            fromfile="live",
            tofile="expected",
        )
    )


def install(root: Path, *, force: bool = False) -> tuple[int, str]:
    """Write the live settings for this machine. Returns (exit code, report)."""
    root = root.resolve()
    expected = _expected(root)
    live_path = root / LIVE_PATH
    template_text = _read_template(root)

    if live_path.is_file():
        live = live_path.read_text(encoding="utf-8")
        if live == expected:
            return 0, f"{LIVE_PATH} is already rendered for this machine"
        if not force and not _same_shape(live, template_text):
            return 1, (
                f"REFUSING to overwrite {LIVE_PATH}: it is not a rendered copy "
                f"of {TEMPLATE_PATH}, so replacing it would destroy a "
                "configuration this tool did not write. #125 is that exact "
                "mistake. Inspect it, then pass --force.\n\n"
                + _diff(live, expected)
            )

    live_path.parent.mkdir(parents=True, exist_ok=True)
    # newline="\n" is not decoration here: this file is compared byte for
    # byte against a template two machines share, and a CRLF render on
    # Windows would report drift against itself forever.
    live_path.write_text(expected, encoding="utf-8", newline="\n")
    return 0, f"rendered {LIVE_PATH} for this machine"


def check(root: Path) -> tuple[int, str]:
    """Report drift between the template and the live file.

    Two independent faults, reported together and both exiting 1. Drift is
    about the rendered file; a foreign interpreter is about the local one. A
    clone can easily have the second without the first, which is how #113 ran
    under a `--check` that said everything matched, until it was filed by hand
    on 2026-08-28.
    """
    root = root.resolve()
    expected = _expected(root)
    live_path = root / LIVE_PATH
    foreign_local = _foreign_interpreter_report(root)

    def report(*sections: str) -> str:
        return "\n\n".join(section for section in sections if section)

    if not live_path.is_file():
        return 1, report(
            f"{LIVE_PATH} is MISSING: this clone is running with none of "
            "its hooks. Run `agent-yield harness --install`.",
            foreign_local,
        )

    live = live_path.read_text(encoding="utf-8")
    if live == expected:
        matched = f"{LIVE_PATH} matches {TEMPLATE_PATH}, rendered for this machine"
        if foreign_local:
            return 1, report(matched, foreign_local)
        return 0, matched

    # #125's own signature, named rather than left inside a diff: every hook
    # points at an executable that is not on this disk. The file was rendered
    # somewhere else and travelled here.
    executables = _executables_in(live)
    absent = [text for text in executables if not Path(text).is_file()]
    lines = []
    if executables and len(absent) == len(executables):
        lines.append(
            "FOREIGN RENDER: every hook command names an executable that does "
            "not exist on this machine, so none of them can have fired:"
        )
        lines.extend(f"  {text}" for text in dict.fromkeys(absent))
        lines.append("")
    lines.append(f"{LIVE_PATH} DRIFTS from {TEMPLATE_PATH}:")
    lines.append("")
    lines.append(_diff(live, expected))
    return 1, report("\n".join(lines), foreign_local)


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="agent-yield harness")
    parser.add_argument("--root", default=".", help="project root (default: .)")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--install", action="store_true",
                      help="render the live settings for this machine")
    mode.add_argument("--check", action="store_true",
                      help="report drift; exit 1 on a difference (default)")
    parser.add_argument("--force", action="store_true",
                        help="with --install, replace a live file this tool "
                             "did not write")
    args = parser.parse_args(argv)

    root = Path(args.root)
    try:
        code, report = (install(root, force=args.force) if args.install
                        else check(root))
    except HarnessError as exc:
        print(str(exc))
        return 2
    print(report)
    return code
