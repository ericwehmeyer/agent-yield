# A fact about the other machine has to be asked for, because nothing in the repo records it

Decided 2026-08-30, committed with #150. Extends ADR-0001 and ADR-0002, which
established what is machine state. This one says how to find out what it holds.

## Three defects in five days all reduce to one machine guessing about another

ADR-0002 recorded a pull replacing four working hooks with four that cannot
run, inside 98 seconds, silently. #130 is the same shape from the other side:
`boundary --enforce` refused every prompt including the `agent-yield handoff`
the refusal prescribed, and whether the Mac carried that defect was
unanswerable from Windows, because `.claude/settings.json` is rendered per
machine and is not tracked. A session was lost to it on 2026-08-30 at 11:45
EDT: 88 calls, 220,658 tokens of context, nothing written down.

The common term is not hooks. It is that the repo is the only channel between
the machines, and the repo deliberately does not carry the facts in question.
Section 7 says GitHub is the queue, and that remains right for work. A queue
moves tasks; it cannot answer a question.

## Inference from this box is not just unavailable, it is wrong in the dangerous direction

`scripts/boundary-audit.sh` reported the deadlock on a machine that was
already fixed, on its own first run. The cause was two lines: bare `python`
has no `agent_yield` and PATH is rarely the venv, so the probe for the fix
failed and was read as the fix being absent. That is a false alarm, which is
survivable. The same class of error with the branches swapped is a machine
told it is clean while it is refusing its operator's prompts.

So the rule is not "prefer asking". It is that a claim about another machine's
state has exactly one admissible source: that machine.

## The decision

A question about a machine's local state is answered by a session on that
machine, in one of two forms.

**Ask the session.** `ListAgents` shows sessions on other machines over Remote
Control. Send the check, and require the output verbatim rather than a
summary — a paraphrase is inference again, one step removed. Delivery to the
Mac session was confirmed at 12:12 EDT on 2026-08-30; the round trip is not
yet measured, and this ADR does not claim a latency or a reliability figure it
does not have.

**Ship the check as a script, never as a list of commands.** The four-step
checklist on #130 became `sh scripts/boundary-audit.sh`, exit 0 clean and 1
action needed. A checklist is executed differently by each reader and produces
prose; a script produces the same lines on both boxes and an exit code a hook
can act on. This is also what makes the first form safe: what crosses the wire
is a script name, not four commands the receiving session might adapt.

## What this does not license

Asking another session to do something this session was refused. Permission
decisions are per-session and per-machine, and routing a blocked action to a
peer launders the operator's refusal. The peer is a source of facts about
itself and a place to run committed scripts. It is not a way around a
boundary, which is the entire subject of the defect that prompted this.

## What would falsify it

A machine whose audit passes while it is in fact broken -- meaning the script
checks the wrong property, and the answer is a better script rather than a
return to inference. Or a reply that arrives so late that the operator pastes
the output by hand first, which would say the queue was adequate and the
channel is not worth maintaining.
