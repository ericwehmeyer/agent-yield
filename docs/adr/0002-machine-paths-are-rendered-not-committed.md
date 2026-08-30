# A path that names a machine cannot be committed, and one that did cost four hooks in 98 seconds

Decided 2026-08-29, committed with #125. Amends ADR-0001, which still holds
everywhere it is not corrected below.

## The instrument was versioned and the machine came with it

ADR-0001 argued that the four hooks are configuration rather than state, so
they ship. That argument is right and is kept. What shipped alongside them was
`C:/Users/ewehm/repos/agent-yield/.venv/Scripts/agent-yield.exe`, four times,
and it is not configuration. It is a user name, a drive letter, a checkout
location and a venv layout, none of which is a property of this project.

Pulling that file onto the Mac at `d4cbb0c` replaced four hooks that were
working with four that cannot run. The Mac's own copy was gone, and no backup
of it exists on the disk or in any of the 24 session transcripts. Three probe
records timestamp how narrow the window was:

| record | UTC |
|---|---|
| last `SessionStart` under the Mac's own hooks | `01:23:47.484183` |
| last `UserPromptSubmit` under them | `01:25:35.495108` |
| the pull | `01:25` |

## Git deleted it silently because the file was ignored, and that is by design

`.gitignore` said `.claude/` at the instant of checkout. Git refuses to clobber
an untracked file and overwrites an **ignored** one without a word, because
ignored means expendable. The same commit rewrote the pattern to `.claude/*`
with a negation, but checkout decides using the rules in force before the merge.
The file was expendable when it was replaced and precious one instant later.

This is worth stating plainly because ADR-0001 predicted the opposite:
*"Shipping a file that needs a path edit beats shipping nothing, because a
wrong path is visible and an absent hook is not."* A wrong path in an ignored
file is neither visible nor absent. It is a deletion.

## The decision: the template is tracked, the rendered file is not

`.claude/settings.template.json` carries the four hooks with the executable
replaced by `{{AGENT_YIELD}}`. `agent-yield harness --install` renders
`.claude/settings.json` for whichever machine runs it, and that rendered file
returns to being ignored. ADR-0001's diffability argument moves up one level,
to the file that is true on both machines instead of on one.

Two properties are load-bearing, and each was half the defect.

**The path is derived from the project root, never written down.** The template
stores `.venv` and nothing above it, so no tracked byte names a home directory.
The rendered command is absolute, resolved from the root at render time. It is
deliberately not left relative: a hook's working directory belongs to the
harness, and a relative command that is wrong about it fails on every call and
says so nowhere. *Derived from the root* is the property that matters; *relative
on disk* is a weaker one that trades a real guarantee for a cosmetic one.

**The layout is found by looking, not by branching.** `bin/agent-yield` against
`Scripts/agent-yield.exe` is resolved by probing four candidate layouts on
disk, ordered with the running platform's convention first. A branch on
`os.name` would have declared a msys-style `bin/` venv on Windows absent; the
probe finds it. The platform default survives only as a tiebreak when two
layouts both exist.

## Three alternatives were rejected, and one of them is tempting

**One portable command string.** `$CLAUDE_PROJECT_DIR/...` expands under `sh`
and not under `cmd`, where it is `%VAR%`; a launcher pair resolved through
`PATHEXT` would work in `cmd` and not in `sh`. Every version of this needs a
Windows console to verify and the Mac does not have one, so choosing it would
have meant shipping an untested fix for a defect whose entire content is
untested cross-platform assumptions.

**A committed file per OS.** It doubles the artefact that must stay in step and
gives no answer for the third machine. The drift the repo actually suffers from
is between the file and the harness, not between two files.

**Rendering into `settings.local.json`.** Structurally cleaner, since git can
never track it. Rejected because the Mac's four hooks are known to have fired
from `settings.json` and are not known to fire from anywhere else, and this
change had already destroyed one working configuration.

## Consequences, including one that lands on the other machine

`git rm --cached .claude/settings.json` means the Windows box's next pull
**deletes its live hook file**, which is the same failure mirrored. It is
accepted because the recovery is one command and the deletion is loud — a
tracked file disappearing shows in `git status` where an overwritten ignored
one does not. The Windows box runs `agent-yield harness --install` once, and
`tests/test_harness.py` pins the four command strings so that render is
byte-identical to what it has been measuring under.

`agent-yield harness --check` is the drift check #119 asks each machine to run
and paste. It exits 1 on a difference and names the case where every hook
command points at an executable that is not on this disk, rather than leaving
that thirteen lines into a diff.

`install()` refuses to overwrite a live file whose hooks do not match the
template's shape. A tool that fixes a silent overwrite by silently overwriting
has fixed nothing.

## What would reopen this

A harness that resolves the project's own venv itself, which would let the
command be `agent-yield ...` with no path at all. Failing that, evidence that
one command string genuinely runs on both machines, measured on both rather
than reasoned about on one.
