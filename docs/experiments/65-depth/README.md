# #65, the depth experiment: built, sized, and not run here

**Answered from the corpus on 2026-08-26, before the arms were paid for.**
#65 was filed on a premise, and the premise is a pooled number.

## What #65 asked

> The packing rule (§11.4) is applied to dispatches with a **52-call median**.
> Every arm anyone has run sat at a packed depth of 15 calls or fewer. Both
> break-even bands — 72-196 calls on the standard tool schema, 35-97 on a
> trimmed one — are extrapolations of 3-13x beyond any depth that has been
> compared. So: one agent over k slices against k agents over one slice each,
> on a task sized so the **packed arm takes at least 50 calls**.

## Two measurements, and they point the same way

**1. The 52-call median is not this repo's.** `depth.py` breaks the call counts
out by the project the session ran in — the split §11.4's own limits mention
("62 of the 84 runs come from a single project's audit fleet") and nobody had
counted:

| project | n | median | p90 | max | at or over 35 calls |
|---|---|---|---|---|---|
| model-migration-kit | 62 | **57.5** | 88.8 | 118 | **52** |
| **agent-yield** | 29 | **5.0** | 22.0 | **30** | **0** |
| Pictures | 7 | 27.0 | 108.0 | 108 | 3 |
| pooled | 102 | 44.0 | 81.1 | 118 | 56 |

**Zero of this repo's 29 dispatches reach even the FLOOR of the cheaper band.**
The longest dispatch agent-yield has ever made is 30 calls, against a break-even
that starts at 35 and, on the schema this repo actually dispatches on, at 72. So
in this repo the rule *never split on cost* is not an untested extrapolation —
it is untestable, because the depth where it could be wrong does not occur here.
The depth exists in the other project's fleet, and that is where a depth
experiment would have to be run.

Within agent-yield the brief does not explain the difference either: `agents`
reports briefed n=10 median 4 calls against un-briefed n=17 median 5. **Depth is
a property of the work, not of the brief.**

**2. An audit task cannot be sized up to depth 50 here anyway.** One packed
pilot ran (`results/pilot-packed-trimmed.json`): one agent, 23 slices, 46 of
this repo's 49 python files.

- It issued **49 Read blocks in 15 calls — 3.27 files per call**, and 2.42 tool
  uses per API call overall.
- Clean depth, with the two harness defects below removed: **~24 calls**.
- **Slices share files.** Cutting the same 49 files into 49 slices, or 100, adds
  no file to open and so adds no call. The packed arm's depth scales with
  **unique artifacts opened divided by the batch width**, not with the slice
  count.

A task that decomposes into k independent slices is exactly the task whose
packed agent batches its tool calls. That is not a flaw in the task; it is the
thing packing buys, measured.

## What the pilot cost, and what it found in the harness

$6.79 in list-price equivalents, 50 calls, and two defects that would have
voided every run of the matrix:

- **Every python invocation is refused headless.** Not the `.venv` symlink — a
  bare `python3 -V` returns `This command requires approval` under `claude -p`.
  16 of the packed agent's 36 calls went on diagnosing and working around it.
  Fixed with `--allowedTools Bash`, which is a permission rule and leaves the
  tool schema — the thing the two arms vary — untouched.
- **The packed agent dispatched an agent of its own** to run the test commands,
  at `spawnDepth: 2`. A packed agent that fans out is not packed. Both arm
  briefs now forbid it and `score.compliance` detects it from the harness's own
  `agent-<id>.meta.json`; run against the pilot it returns
  `sub_dispatches: 1, ok: False`, so the detector is checked against a real
  violation rather than a constructed one.

A third, smaller one: `pyproject.toml` already sets `addopts = "-q"`, so the
slice command's own `-q` made it `-qq` and suppressed the very count the slice
has to report.

## What is here, and it is runnable

Everything except the arms, and the arms are one command each.

| | |
|---|---|
| `build-corpus.py` | the tree at a pinned sha with **14 docstring defects seeded**, each contradicted by a named constant in its own module. Refuses any seed that is not inside a module docstring or that matches other than exactly once, and verifies the suite still passes on the result — so the per-slice test command measures depth and not the seed. |
| `ground-truth.json` | the pin, the 14 substitutions, and the match pattern each is scored by. |
| `task.md`, `arm-packed.md`, `arm-split.md` | the shared task and the two METHOD paragraphs, which are the only difference between the arms. |
| `run.sh` | one run: rebuilds the corpus, runs the arm at one of the two tool schemas, measures. |
| `measure.py` | list dollars and **`packed_depth`**, per agent — the sizing number the ticket makes a void condition. |
| `score.py` | seeds found, coverage, and compliance read from the transcripts. |
| `table.py` | the arm comparison and the 1.25x bar. |
| `depth.py` | the corpus measurement above. |
| `tests/test_arms_65.py` | the scorer validated **before** any arm runs: 14/14 on an arm that quotes every seed, 0 on an arm that finds nothing, and 0 on plausible findings that are not the seeds. |

**Why the ground truth is seeded rather than found**, and it is a real limit:
#47's bar rested on two hand-verified defects, which is too thin to separate two
arms — one arm finding one more is a 50% swing. Fourteen seeds fix the power and
cost realism: a seeded defect is not drawn from the distribution of real
docstring drift, and 14 across 23 slices is a denser field than any real audit.
It supports a within-experiment comparison of two arms on identical text. It does
not support a claim about how many real defects an audit finds.
