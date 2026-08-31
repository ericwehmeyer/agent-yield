# Four of the five triage roles carry a label, and the fifth is the absence of one

The tracker carries 23 labels: accessibility, bug, documentation, duplicate,
enhancement, good first issue, help wanted, invalid, question, task, blocked,
windows, macos, priority:high, needs-planning, ready-for-agent,
ready-for-human, wontfix and the five `wayfinder:` types. Of the five canonical
triage roles the skills speak in, `wontfix`, `ready-for-agent` and
`ready-for-human` exist under their own names. `needs-triage` is the one still
mapped to nothing, and it needs no label: an issue carrying no role label is
already the untriaged state. This file maps each role to a label that is really
there, or records that none is.

| Label in mattpocock/skills | Label in our tracker | Meaning                                                       |
| -------------------------- | -------------------- | ------------------------------------------------------------- |
| `needs-triage`             | none                 | An issue carrying no role label is the untriaged state         |
| `needs-info`               | `blocked`            | Waiting on someone else, the reporter included; an approximate fit |
| none                       | `needs-planning`     | The approach is undecided; a plan has to be written before an agent can take it |
| `ready-for-agent`          | `ready-for-agent`    | Root cause is stated, the fix has a named file, and no operator judgment remains |
| `ready-for-human`          | `ready-for-human`    | Requires human hands: an operator edit, a physical act, or a decision only the operator can make |
| `wontfix`                  | `wontfix`            | Will not be actioned                                           |

`needs-planning` runs the other way: a label here with no role in the skills'
vocabulary, because the state it names, an issue whose approach is undecided,
was not one the five roles separated from untriaged. `blocked` was already
spoken for by waiting on someone else, and the two are not the same wait.

`ready-for-agent` was created on 2026-08-30 because without it
`scripts/pick-issue.py` could never select anything: an issue that is ready
read exactly like one nobody had looked at, and every available proxy for
readiness measures how well an issue is written rather than whether it is
ready.

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
vocabulary in observed use. Four were created anyway on 2026-08-30, each one
at the point where refusing to create it started costing something.
`ready-for-agent`, because the picker had no other way to select. `macos`,
because the claim was one-directional. `ready-for-human`, because #170 put work
in front of an unattended runner the same day this file recorded the gap as
costing nothing, and an issue needing human hands stopped being
distinguishable from one nobody had triaged; #171 is the worked example, and it
turns on a YubiKey touch policy no script can set. `needs-planning`, because
the undecided state is where most of the hard issues in this tracker actually
sit.

Neither new label is in `scripts/pick-issue.py`'s `READY_LABELS`, which is
`ready-for-agent` and `wayfinder:research`, so an issue carrying one is passed
over rather than selected. Confirmed with `--explain` on 2026-08-30 rather than
by reading the source: of the four issues carrying `needs-planning`, #172, #174
and #175 each come back "no human has marked it ready for an agent", and #176
is refused one check earlier as claimed by windows. `ready-for-human` has no
issue carrying it yet.

`priority:high` was created on 2026-08-30 for #128, a warning the other machine
has to read before its next pull rather than during its next triage. It
expresses urgency, not readiness, so it was never a candidate for either gap
the four above were created to close.
`scripts/pick-issue.py` is the only thing that sorts by it, and it sorts on
nothing else: `priority:high` first, then oldest.

## The two machine labels are a claim, not a role

`windows` and `macos` sit outside the triage table because they record who is
holding an issue, not what state it is in. They became symmetric on 2026-08-30,
when `macos` was created alongside `ready-for-agent`. Before that the Mac could
claim nothing, so two unattended pickers would both have seen every unclaimed
issue and raced for it. Each box refuses the other's label and takes its own; a
box that is neither, such as a Linux runner, takes only what nobody claimed.
