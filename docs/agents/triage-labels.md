# Four of the five triage roles have no label in this tracker

The tracker carries 14 labels: accessibility, bug, documentation, duplicate,
enhancement, good first issue, help wanted, invalid, question, task, blocked,
windows, priority:high and wontfix. Of the five canonical triage roles the skills speak in,
only `wontfix` exists under its own name. This file maps each role to a label
that is really there, or records that none is.

| Label in mattpocock/skills | Label in our tracker | Meaning                                                       |
| -------------------------- | -------------------- | ------------------------------------------------------------- |
| `needs-triage`             | none                 | An issue carrying no role label is the untriaged state         |
| `needs-info`               | `blocked`            | Waiting on someone else, the reporter included; an approximate fit |
| `ready-for-agent`          | none                 | Fully specified, ready for an AFK agent                        |
| `ready-for-human`          | none                 | Requires human implementation                                  |
| `wontfix`                  | `wontfix`            | Will not be actioned                                           |

`ready-for-agent` and `ready-for-human` have no equivalent, so triage cannot
currently express "fully specified, ready for an agent" at all, and an issue
that is ready reads exactly like one that has never been looked at.

When a skill mentions a role (e.g. "apply the AFK-ready triage label"), use the
corresponding label string from this table, and where the row says none, apply
no label and say in a comment what the state is.

Labels that exist were preferred over labels that would have to be created:
more than 40 open issues already carry `task`, `bug` or `blocked`, which is the
vocabulary in observed use. Closing the two gaps above means creating labels,
not editing this file.

`priority:high` is the one label since created, on 2026-08-30, for #128 -- a
warning the other machine has to read before its next pull rather than during
its next triage. It expresses urgency, not readiness, so it closes neither gap
above. Nothing sorts by it; it exists so that one issue is not read in the order
it was filed.
