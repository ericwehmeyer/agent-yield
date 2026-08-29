# agent-yield

The domain is the cost of agent-written work: what a way of working spends,
against what survives. Terms here are the project's canonical vocabulary. Where
a term is defined by a threshold, the definition carries the number and marks it
measured or chosen; no other numbers belong here.

## Language

### The question

**Yield**:
The question the project asks: whether a way of working shipped more for less.
Never a quantity. Every computed figure runs in the cost direction, tokens per
unit shipped.
_Avoid_: efficiency, productivity, throughput

**Speedup**:
The ratio of a baseline way of working's cost to a treated one's, at fixed
output. Yield asks whether a way of working shipped more for less; Speedup is
the factor by which it did, and it is defined only when both arms shipped the
same thing.
_Avoid_: efficiency, gain, improvement, faster

### What is spent

**Call**:
One API request, and the atom of cost. A call's context is its input, cache-read
and cache-creation tokens together.
_Avoid_: request, turn, message

**Dispatch**:
The ask that starts an agent. It carries the brief, and it is the only half a
hook can see, so it is the only half that can be priced before the spending.
_Avoid_: spawn, task, subagent call

**Agent**:
The run a dispatch starts. Its cost is visible only in its own transcript, and
no structural link ties it back to its dispatch; the join is a heuristic.
_Avoid_: subagent (as a noun), child, worker

**Mode**:
The kind of work a session did, tagged by the operator and never inferred:
build, review, design, audit, ops.
_Avoid_: session type, work type, phase

### What survives

**Operator**:
The person whose way of working is being measured. Not the same as the machine
that made a commit: attribution identifies a clone, and one operator can work
from several.
_Avoid_: user, developer, author

**Project**:
A repository the operator works in. A call belongs to the project containing its
`cwd`.
_Avoid_: workspace, codebase, product

**Shipped**:
Code committed to a project.
_Avoid_: delivered, landed, output

**Survival**:
Whether shipped code is still present after the horizon, currently 7 days
(chosen, not measured). Surviving insertions are the denominator of every yield
figure.
_Avoid_: retention, persistence, stickiness

**Thrash**:
Shipped code that did not survive. The gap between insertions and surviving
insertions, and the project's only measure of wasted spend.
_Avoid_: churn, rework, waste

**Good**:
Of shipped code: survived, in a project whose suite passes. The project claims
no richer measure of quality, on purpose.
_Avoid_: quality, clean, well-written

### What is being tested

**Intervention**:
A change to how the work is done, recorded with a falsifiable prediction before
the outcome is known. A change recorded without a prediction is not one.
_Avoid_: process change, tweak, improvement

**Experiment**:
A controlled comparison run to settle a question, made of arms and scored
against its arms rather than against a day's record.
_Avoid_: trial, study

**Arm**:
One run of an experiment under a single condition.
_Avoid_: variant, branch, leg
