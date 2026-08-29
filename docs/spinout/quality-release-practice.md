# A quality and release practice built agent-first, with disposable Azure as its proving ground

Written 2026-08-29 13:30 EDT, rewritten 13:36 EDT when the scope turned out to
be five prototypes rather than one. A scoping note for a project that does not
belong in `agent-yield`, captured here so it does not evaporate the way the
roster grill's Q10 did. It moves to its own repo when it has a name.

## What this is, and it is not an infrastructure tool

The project is a **quality and release engineering practice, done agent-first**.
Its output is a set of working prototypes plus the judgement about which ones
earn their keep. Azure infrastructure is not the product; it is the substrate
the prototypes are tested against, which is why it has to be cheap and
disposable.

Five parts, and the last one is the one with a business problem already
attached:

1. **Data testing** -- contracts, expectations and drift on real pipelines.
2. **AI testing** -- how you test a non-deterministic system without pinning it
   to a golden output that will be wrong next release.
3. **Automated testing** -- the conventional layer, where the question is what
   an agent can write that a human would keep.
4. **Build and deploy** -- the whole path, not the pieces.
5. **Greenfield data quality practice** -- because the existing data lake has
   sewage in it, and cleaning it in place has already lost to starting clean.

## Why it is not part of agent-yield

`agent-yield` divides spend by what survived: tokens against commits that
lasted. This project divides different pairs, one per prototype, and cloud
dollars against infrastructure correctly stood up and torn down is only the
substrate's pair. Sharing a repo would mean sharing a definition of `yield`,
and these do not share one.

What transfers is the method: pre-register the prediction, mark what is
measured against what is chosen, and score against the number written down
beforehand.

## Each prototype needs a denominator before it needs code

This is the discipline `agent-yield` earned the hard way, and it is the thing
most likely to be skipped here. A prototype with no denominator produces a demo
that everyone agrees is impressive and nobody can act on.

| prototype | numerator, the cost | denominator, what counts as working |
|---|---|---|
| data testing | agent tokens plus pipeline runs | defects caught before a consumer saw them, against defects found downstream |
| AI testing | tokens plus eval runs | regressions caught, against false alarms raised -- both, because a flaky suite gets muted |
| automated testing | tokens to author | tests still in the suite after 30 days and not skipped |
| build and deploy | tokens plus minutes of pipeline | deploys that needed no human touch, against total |
| data quality | tokens plus storage | fields with an enforced contract, against fields consumed |

Every denominator in that table is CHOSEN, and none is measured. That is the
honest state of a project on its first day. The first real task per prototype
is measuring the current value, because a target with no baseline is a wish.

## The substrate: teardown is the test, not the cleanup

An agent that provisions Azure infrastructure from IaC is a solved shape. An
agent that reliably destroys it is not, and the failure is asymmetric in a way
that costs money:

- A build that fails is visible in a minute. The agent errors, nothing runs.
- A teardown that fails is silent. `destroy` returns zero having skipped a
  resource outside its state, and the bill arrives in thirty days.

So **teardown is the test.** A run that provisions correctly and leaks one
public IP has failed, and the harness says so on the day rather than at invoice
time.

Frugality is an intention until it has a check that fails. Three, none measured
yet:

1. **Cost per run**, from Azure Cost Management scoped to a run-tagged resource
   group, read after teardown.
2. **Residual after teardown**: enumerate what still carries the run's tag once
   `destroy` reports success. The bar is zero, and any other answer is a defect
   rather than a variance.
3. **Time to teardown**, wall-clock from build-complete to residual-zero. A run
   torn down four hours late costs four hours.

Number 2 makes the other two honest. Without it, cost per run looks excellent
right up until it does not.

## Build, use, or borrow the IaC

A fork, not a detail:

- **Borrow** an existing IaC repo (Azure Verified Modules, or a team's own) and
  compose. Cheapest to start, and it inherits whatever teardown discipline the
  source has, which may be none.
- **Build** minimal Terraform or Bicep per scenario. Full control of the
  destroy path, and every scenario is new code to be wrong in.
- **Both**: borrow modules, author the composition and the teardown contract.

The deciding question is whether a borrowed module can be trusted to destroy
what it created. One module, one hour, answerable by experiment.

## What is measured and what is chosen

MEASURED: nothing. No number in this document came from a run.

CHOSEN: that teardown verification is a first-class outcome rather than a
cleanup step. That every prototype states its denominator before it is built.
That the stack is Azure, ADO, Playwright and Jira, the operator's own. That
data quality starts greenfield rather than remediating the existing lake.

## Now what

1. **Write the residual check first.** Tag-scoped enumeration against a
   subscription, expected empty. It is the one component that must exist before
   an agent is allowed to provision anything.
2. **Price one scenario by hand.** Smallest useful thing up, torn down, read
   Cost Management. That number is the baseline every later claim is measured
   against.
3. Answer borrow-or-build with the one-module experiment.
4. **Pick one prototype and measure its denominator's current value** before
   building it. Data quality is the candidate, because the sewage is already
   costing something that can be counted.
5. Then, and not before, give an agent the build-use-destroy loop.

Steps 3 through 5 are blocked on step 1. An agent that can create Azure
resources before anything can prove they were destroyed is the expensive
version of this project.
