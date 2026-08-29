# The four hooks ship and the 553,001 bytes they wrote do not

Decided 2026-08-29, committed at `6d35b47`. Supersedes nothing.

## A repo that measures agent sessions was not versioning the thing doing the measuring

`.gitignore` carried `.claude/`, which hid four hooks: the SessionStart handoff
inject, the PreToolUse gate on `Agent`, the `guard` on `Bash`, and the
UserPromptSubmit boundary check. Every finding in this repo was produced under
that configuration and none of it was reviewable in a diff or reproducible on
the Mac.

## The pattern is `.claude/*`, and changing it back to `.claude/` silently breaks the negations

```
.claude/*
!.claude/settings.json
!.claude/hooks/
.claude/hooks/probe-log.jsonl
```

Git does not descend into an excluded directory. Write `.claude/` and the two
negations below it are never read, so the hooks vanish again with no error and
no diff. **The trailing `/*` is load-bearing.** It reads like a typo and will
attract a tidying hand; this file exists mostly to stop that hand.

## Configuration ships, state does not, and the line runs between them

`settings.json` and `hooks/probe.py` change what a measurement means, so they
are versioned. `probe-log.jsonl` is what a measurement produced: 2,363
invocations, 553,001 bytes, both measured. It stays out, along with
`settings.local.json`, `worktrees/` and the `.bak` files, which describe one
machine rather than the method.

That boundary is chosen. A defensible alternative was to commit the probe log
as evidence, since it is the record that settled whether `PreToolUse` fires on
the main thread's dispatch call. The log grows on every tool call and would
have made the repo's history unreadable, so the finding was written into issue
#122 instead and the log left where it fell.

## The committed file does not run on the Mac, and that was accepted

`settings.json` hard-codes `C:/Users/ewehm/repos/agent-yield/.venv/Scripts/`.
The Mac cannot execute it as written. Shipping a file that needs a path edit
beats shipping nothing, because a wrong path is visible and an absent hook is
not. Making the paths portable belongs to #119.

## What would reopen this

A harness that merges project `settings.json` with the user one rather than
replacing it, which would let the repo carry only the hooks and leave paths to
each machine. Failing that, evidence that the negation pattern breaks on a
git version either machine actually runs.
