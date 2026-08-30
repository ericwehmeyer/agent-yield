# agent-yield

This repo measures what agent sessions cost against what they ship. Its own
finding applies to this file: every API call re-reads it, so it is short on
purpose. Add a line here only when an agent gets something wrong without one.

## The interpreter with pytest is `.venv/Scripts/python.exe`

Bare `python` has none. Pass `-rs`, never `-q`: `pyproject.toml` already sets
`addopts = "-q"`, so a second one is `-q -q` and double quiet drops the
`716 passed` line entirely. A run that prints dots and exits 0 cannot be told
from one that collected nothing.

```
.venv/Scripts/python.exe -m pytest -rs                    # whole suite
.venv/Scripts/python.exe -m pytest tests/test_gate.py -rs  # one file
.venv/Scripts/agent-yield.exe --help                       # the CLI
```

CI runs `python -m pytest -rs` across windows/macos/ubuntu and Python 3.11 and
3.14. It deliberately sets no `PYTHONUTF8` and no `PYTHONIOENCODING`: a cp1252
stdout is the class of defect the matrix exists to catch, so a workflow that
sets the encoding measures a machine nobody has. `-rs` is not decoration
either. A skipped arm that prints nothing reads as a passing one (#29).

`.github/workflows/test.yml` needs `fetch-depth: 0`. `tests/test_arms_65.py`
exports a pinned sha with `git archive`, and a depth-1 clone holds one commit.

## Rendering the status line by hand writes to disk

`agent-yield statusline` appends the payload's `rate_limits` to
`.agent-yield/allowance.jsonl`, which is real calibration input. A synthesized
test payload therefore puts invented numbers into real data, silently. One did
on 2026-08-26 (#69). Pass `--no-write` for any hand render.

`agent-yield resume` prints the last handoff without consuming it.
`resume --hook` archives it as it injects.

## Prose follows docs/style.md, charts follow docs/style-charts.md

Both are enforced in review. The rules broken most often:

- Lead with the finding as a number, not with the method or the context.
- Reach *now what*. A document that stops at *what* is a lab notebook.
- Say which numbers are measured and which are chosen. That distinction is the
  whole value of this repo.
- Real digits. `249,257`, never "about a quarter million", when the figure is
  measured.
- Two em dashes per page, at most one bold claim per paragraph. Never
  *importantly*, *notably*, *crucially*, *it is worth noting*.
- Headings are sentences carrying the argument, not labels.

A chart with no measured value on the canvas is a table or a sentence instead
(`style-charts.md` rule 1).

## Agents write files; the parent commits

Parallel agents share one working tree, so letting them all commit produces
`index.lock` races and commits that mix three tasks. Agents write files and run
only their own test file. The parent runs that test itself, stages **named
paths**, and commits. Never `git add -A` while agents are live. One commit per
task, with `Closes #N`.

The parent dispatches and decides rather than reading. In the session that
measured this, the parent was 81% of 3.5M tokens and seven agents were 19%.

A brief carries line ranges rather than filenames **and an explicit "do not
explore"** — the gate scores those two as one marker, because a range without
the prohibition is not the intervention that was measured — plus a named output
path and a stated return contract. Full rules: `docs/working-method.md` §3 and
§12.

## Some expectations are pinned, and relaxing one hides a defect

`tests/fixtures/arms-33/` and `arms-81/` carry `ground-truth.json`, including a
pinned commit sha. The case-study figures are regression tests: the parser must
reproduce 136,449 context-per-call and the 12,385,765 median agent, or it is
wrong.

`tests/test_portability_guard.py` is the half CI cannot cover. Scored against
the five platform defects found on 2026-08-26, the three-OS matrix would have
caught one.

A test whose expectation is derived from the code under test proves nothing.
That is how #51 survived a fix to the same function.

## Two machines push to this repo

A Mac and this Windows box both commit to `main` and file issues against it.
Pull before touching `docs/NEXT.md` or anything else under `docs/`.

**After a pull, run `agent-yield harness --check`.** The hooks are rendered
per machine from `.claude/settings.template.json`; the live
`.claude/settings.json` is machine state and is not tracked. `--check` exits 1
on drift and names a file rendered on the other box. `--install` writes it, and
refuses unless the live file is already a rendered copy -- `--force` past that
only once the diff is one you made.
A pull once replaced one machine's four working hooks with the other's and
said nothing, because git overwrites ignored files silently (#125, ADR-0002).

## Agent skills

### Issue tracker

GitHub Issues on `ericwehmeyer/agent-yield`, via the `gh` CLI. See
`docs/agents/issue-tracker.md`.

### Triage labels

The five canonical roles, each label string equal to its name. See
`docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` and `docs/adr/` at the repo root, both now created.
See `docs/agents/domain.md`.
