# A builder that cannot leave infrastructure running is the only kind worth costing

Written 2026-08-29 13:30 EDT. This is a scoping note for a project that does
not belong in `agent-yield`, captured here so it does not evaporate the way the
roster grill's Q10 did. It moves to its own repo when it has a name.

## Why it is not part of agent-yield

`agent-yield` divides spend by what survived: tokens against commits that
lasted. This project divides a different pair. Its numerator is dollars of
cloud spend and its denominator is infrastructure correctly provisioned and
then correctly destroyed. Sharing a repo would mean sharing a definition of
`yield`, and these two do not share one.

What does transfer is the method: pre-register the prediction, name what is
measured against what is chosen, and score the result against the number
written down beforehand.

## The thing that makes it hard is teardown, not build

An agent that provisions Azure infrastructure from IaC is a solved shape. An
agent that reliably destroys it is not, and the failure is asymmetric in a way
that costs real money:

- A build that fails is visible within a minute. The agent errors, nothing
  runs, the operator sees it.
- A teardown that fails is silent. `terraform destroy` returns zero having
  skipped a resource outside its state. The bill arrives in thirty days.

That asymmetry is the whole design constraint. **Teardown is not cleanup after
the test; teardown is the test.** A run that provisions correctly and leaks one
public IP has failed, and the harness has to say so on the day, not at invoice
time.

## What frugality means as a measurable, not an intention

"Keep it inexpensive" is an intention until it has a number attached and a
check that fails. Three candidates, and none is measured yet:

1. **Cost per run.** Azure Cost Management, scoped to a resource group tagged
   for the run, read after teardown. Chosen bar, per run, in dollars.
2. **Residual after teardown.** Enumerate what exists in the subscription
   carrying the run's tag, after `destroy` reports success. The bar is zero and
   any other answer is a defect, not a variance.
3. **Time to teardown.** A run that is torn down four hours late costs four
   hours. Wall-clock from build-complete to residual-zero.

Number 2 is the one that makes the other two honest. Without it, cost per run
looks excellent right up until it does not.

## Build, use, or borrow the IaC

The question is open and it is a fork, not a detail:

- **Borrow**: point the agent at an existing IaC repo (Azure Verified Modules,
  or a team's own) and have it compose. Cheapest to start, and it inherits
  whatever teardown discipline the source has, which may be none.
- **Build**: the agent authors minimal Terraform or Bicep per scenario. Full
  control of the destroy path, and every scenario is new code to be wrong in.
- **Both**: borrow modules, author the composition and the teardown contract.

The deciding question is whether a borrowed module can be trusted to destroy
what it created. That is answerable by experiment, on one module, in an hour.

## What is measured and what is chosen

MEASURED: nothing yet. This document has no numbers in it, which is the
honest state of a project on its first day.

CHOSEN: that teardown verification is a first-class outcome rather than a
cleanup step. That the denominator is provisioned-and-destroyed rather than
provisioned. That the target stack is Azure, ADO, Playwright and Jira, which is
the operator's own working stack.

## Now what

1. **Price one scenario by hand before automating any of it.** Stand up the
   smallest useful thing, tear it down, read Cost Management. That number is
   the baseline every later claim is measured against, and without it there is
   nothing to beat.
2. **Write the residual check first.** Tag-scoped enumeration against a
   subscription, expected empty. It is the one component that must exist
   before an agent is allowed to provision anything.
3. Answer the borrow-or-build fork with the one-module experiment above.
4. Then, and not before, give an agent the build-use-destroy loop.

Steps 3 and 4 are blocked on step 2. An agent that can create Azure resources
before anything can prove they were destroyed is the expensive version of this
project.
