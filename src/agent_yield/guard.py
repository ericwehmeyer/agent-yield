"""PreToolUse guard: refuse a tree-wide `git add`, and nothing else.

Parallel agents share one working tree. `git add -A` from one of them stages
whatever the other six happened to have written a second earlier, so the commit
mixes three tasks and no agent can be held to its own diff. CLAUDE.md states the
rule -- agents write files, the parent stages *named paths* -- and this hook is
what makes the rule hold when an agent forgets it.

Why a subcommand and not a matcher
----------------------------------
It lives in `src/` behind `agent-yield guard`, as `gate` and `boundary` already
do, rather than as a loose script under `.claude/hooks/`. `.gitignore` ignores
`.claude/`, so a hook kept there is untracked, unreviewable, untestable by CI
and invisible to the other machine that pushes to this repo (#115) -- which is
a poor home for executable code that gates every tool call.

The rule used to live in `settings.json` as permission-style matchers,
`"if": "Bash(git add -A*)"` and `"if": "Bash(git add --all*)"`. Those match the
command string, not the command, and they do not scope: on 2026-08-28 these four
real commands, none of which contains `git add` as a thing being run, were all
REFUSED:

    cat <<EOF ... EOF
    gh issue create --body "$(cat <<EOF ...)"
    a multi-line python heredoc script
    for f in a b; do grep -n "pat" "$f"; done

The third and fourth cost the most: `docs/agents/issue-tracker.md` tells agents
to file tickets with a heredoc body, so the guard blocked this repo's own
documented way to file a ticket. A guard that fires on unrelated commands gets
switched off, and a switched-off guard catches nothing. A guard that misses an
exotic shape is recoverable -- the parent still reviews what was staged. So the
matcher below is deliberately narrow and deliberately literal.

What it matches
---------------
Heredoc bodies are stripped first (`<<WORD`, `<<-WORD`, `<<'WORD'`, up to the
terminator line, or to end of input if unterminated). The remaining text is
tokenized with quote tracking, split on unquoted `&&`, `||`, `;`, `|`, `&` and
newline, and each resulting command is inspected. A command is refused when:

  * its first word is an unquoted `git` (leading `VAR=value` assignments are
    skipped), and
  * after git's own options (`-C <path>`, `-c <kv>`, `--git-dir=...`, and other
    leading dashed words) the subcommand is `add`, and
  * an argument is `-A`, `--all`, a short cluster containing `A` (`-vA`), or a
    bare `.` pathspec.

So it catches `git add -A`, `git add --all`, `git add .`, `git add -A -- .`,
`git add --verbose -A`, `git -C /some/path add -A`, and any of those following
`&&`, `;`, `|` or a newline.

What it knowingly does NOT match
--------------------------------
  * anything inside a quoted argument or a heredoc body, including a body that
    is really executed (`bash <<EOF ... git add -A ... EOF`) -- this is the
    exemption the whole rewrite exists for;
  * command substitution: `$(git add -A)`, `` `git add -A` ``;
  * indirection: `eval "git add -A"`, `sh -c 'git add -A'`, `g=git; $g add -A`,
    `xargs git add`, a shell function or a git alias such as `git stage -A`;
  * other tree-wide pathspecs: `git add -u`, `git add :/`, `git add '*'`,
    `git add ..`, `git add $PWD`;
  * a command whose quotes do not balance -- the tokenizer gives up and allows.

Never blocks on its own failure: a stdin read error, a UTF-8 decode error, a
JSON parse error, a non-Bash tool or a missing command all exit 0. Exit 2 is the
only thing that blocks, and only the shapes listed above produce it.
"""
from __future__ import annotations

import json
import re
import sys
from typing import TextIO

from .hookio import read_payload

REFUSAL = (
    "Refused: this stages the whole working tree.\n"
    "Parallel agents share one working tree, so `git add -A`, `git add --all` "
    "and `git add .` stage another agent's files into your commit.\n"
    "Stage named paths instead: `git add path/one.py path/two.py`.\n"
    "See CLAUDE.md, 'Agents write files; the parent commits'."
)

# <<EOF / <<-EOF / <<'EOF' / <<"EOF", capturing the delimiter word.
_HEREDOC = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")

_OPERATORS = ("&&", "||", ";", "|", "&", "\n")

# git's own options that swallow the following word.
_GIT_OPTS_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path"}


def strip_heredocs(command: str) -> str:
    """Drop every heredoc body. A body is data, never a command being run."""
    lines = command.split("\n")
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        out.append(line)
        delimiters = [m.group(2) for m in _HEREDOC.finditer(line)]
        i += 1
        for delimiter in delimiters:
            while i < len(lines) and lines[i].strip() != delimiter:
                i += 1
            i += 1  # consume the terminator line too (or run off the end)
    return "\n".join(out)


def tokenize(text: str) -> list[tuple[str, bool]] | None:
    """Split into (word, was_quoted) pairs. None if the quotes do not balance."""
    tokens: list[tuple[str, bool]] = []
    word = ""
    quoted = False
    started = False
    quote: str | None = None
    i = 0
    while i < len(text):
        ch = text[i]
        if quote:
            if ch == "\\" and quote == '"' and i + 1 < len(text):
                word += text[i + 1]
                i += 2
                continue
            if ch == quote:
                quote = None
            else:
                word += ch
            i += 1
            continue
        if ch in ("'", '"'):
            quote = ch
            quoted = True
            started = True
            i += 1
            continue
        if ch == "\\" and i + 1 < len(text):
            word += text[i + 1]
            started = True
            i += 2
            continue
        if ch in " \t\r":
            if started:
                tokens.append((word, quoted))
            word, quoted, started = "", False, False
            i += 1
            continue
        two = text[i:i + 2]
        if two in ("&&", "||"):
            if started:
                tokens.append((word, quoted))
            word, quoted, started = "", False, False
            tokens.append((two, False))
            i += 2
            continue
        if ch in ";|&\n":
            if started:
                tokens.append((word, quoted))
            word, quoted, started = "", False, False
            tokens.append((ch, False))
            i += 1
            continue
        word += ch
        started = True
        i += 1
    if quote:
        return None
    if started:
        tokens.append((word, quoted))
    return tokens


def split_commands(tokens: list[tuple[str, bool]]) -> list[list[tuple[str, bool]]]:
    commands: list[list[tuple[str, bool]]] = [[]]
    for word, was_quoted in tokens:
        if not was_quoted and word in _OPERATORS:
            commands.append([])
        else:
            commands[-1].append((word, was_quoted))
    return [c for c in commands if c]


def stages_whole_tree(command: list[tuple[str, bool]]) -> bool:
    words = list(command)
    while words and not words[0][1] and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", words[0][0]):
        words.pop(0)  # leading FOO=bar assignments
    if not words:
        return False
    head, head_quoted = words[0]
    if head_quoted or head != "git":
        return False

    args = words[1:]
    i = 0
    while i < len(args):  # skip git's own options to reach the subcommand
        word = args[i][0]
        if not word.startswith("-"):
            break
        if word in _GIT_OPTS_WITH_VALUE:
            i += 2
        else:
            i += 1
    if i >= len(args) or args[i][0] != "add":
        return False

    for word, _ in args[i + 1:]:
        if word in ("-A", "--all", "."):
            return True
        if re.fullmatch(r"-[A-Za-z]+", word) and "A" in word:
            return True
    return False


def main(stdin: TextIO | None = None) -> int:
    """Exit 2 to refuse, 0 for everything else including its own failures.

    Through `hookio.read_payload`, not `sys.stdin`: on Windows CPython hands a
    hook a cp1252 stdin with `surrogateescape` errors, so a payload naming a
    non-ASCII path arrives corrupt and NOTHING raises (audit N3). `stdin` is
    the injected test seam, matching `gate.main`.
    """
    try:
        raw = read_payload(stdin)
    except (OSError, ValueError):
        return 0
    try:
        payload = json.loads(raw)
    except ValueError:
        return 0
    if not isinstance(payload, dict):
        return 0
    if payload.get("tool_name") != "Bash":
        return 0

    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return 0
    command = tool_input.get("command")
    if not isinstance(command, str) or not command.strip():
        return 0

    tokens = tokenize(strip_heredocs(command))
    if tokens is None:
        return 0
    if any(stages_whole_tree(c) for c in split_commands(tokens)):
        sys.stderr.write(REFUSAL + "\n")
        return 2
    return 0

