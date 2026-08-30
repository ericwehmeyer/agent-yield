# Three of the five triage roles have no label in this tracker

The tracker carries 21 labels: accessibility, bug, documentation, duplicate,
enhancement, good first issue, help wanted, invalid, question, task, blocked,
windows, macos, priority:high, ready-for-agent, wontfix and the five
`wayfinder:` types. Of the five canonical triage roles the skills speak in,
`wontfix` and `ready-for-agent` exist under their own names. This file maps
each role to a label that is really there, or records that none is.

| Label in mattpocock/skills | Label in our tracker | Meaning                                                       |
| -------------------------- | -------------------- | ------------------------------------------------------------- |
| `needs-triage`             | none                 | An issue carrying no role label is the untriaged state         |
| `needs-info`               | `blocked`            | Waiting on someone else, the reporter included; an approximate fit |
| `ready-for-agent`          | `ready-for-agent`    | Root cause is stated, the fix has a named file, and no operator judgment remains |
| `ready-for-human`          | none                 | Requires human implementation                                  |
| `wontfix`                  | `wontfix`            | Will not be actioned                                           |

`ready-for-human` still has no equivalent. `ready-for-agent` was created on
2026-08-30 because without it `scripts/pick-issue.py` could never select
anything: an issue that is ready read exactly like one nobody had looked at,
and every available proxy for readiness measures how well an issue is written
rather than whether it is ready.

Its description is the definition, and all three clauses have to hold: **root
cause is stated, the fix has a named file, and no operator judgment remains.**
An issue failing any one of them is refused rather than guessed at. Two rules
keep it honest and nothing enforces either -- apply it at triage rather than in
a sweep, because a bulk application records the sweep and not the issue, and
remove it when a blocker appears, because the label is a claim about the past
and its age is the only honest measure of its decay. It never means
"important": `priority:high` means that, and one label carrying both is how
readiness stops being checkable.

When a skill mentions a role (e.g. "apply the AFK-ready triage label"), use the
corresponding label string from this table, and where the row says none, apply
no label and say in a comment what the state is.

Labels that exist were preferred over labels that would have to be created:
more than 40 open issues already carry `task`, `bug` or `blocked`, which is the
vocabulary in observed use. Two labels were created anyway, once refusing to
create them started costing something -- `ready-for-agent`, because the picker
had no other way to select, and `macos`, because the claim was one-directional.
`ready-for-human` is the gap still open, and it costs nothing yet: no tool
reads it.

`priority:high` was created on 2026-08-30 for #128, a warning the other machine
has to read before its next pull rather than during its next triage. It
expresses urgency, not readiness, so it closes neither gap above.
`scripts/pick-issue.py` is the only thing that sorts by it, and it sorts on
nothing else: `priority:high` first, then oldest.

## The two machine labels are a claim, not a role

`windows` and `macos` sit outside the triage table because they record who is
holding an issue, not what state it is in. They became symmetric on 2026-08-30,
when `macos` was created alongside `ready-for-agent`. Before that the Mac could
claim nothing, so two unattended pickers would both have seen every unclaimed
issue and raced for it. Each box refuses the other's label and takes its own; a
box that is neither, such as a Linux runner, takes only what nobody claimed.
