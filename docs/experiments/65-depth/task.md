Audit this checkout, one SLICE at a time.

The slice list is FIXED. There are 23 slices, one per module. Audit exactly
these, no others, no fewer:

    agents  allowance  attribution  boundary  cli  discovery  gate  handoff
    hookio  ingest  interventions  modes  outcomes  predict  pricing  records
    report  report_html  resume  session  statusline  thresholds  usage

Every slice is the same three steps and the same three sources. For a slice
named `X`:

  1. Read `src/agent_yield/X.py`.
  2. Read that module's test file: `tests/test_X.py`, except for the one slice
     whose test file is named differently -- `hookio` is tested by
     `tests/test_hook_stdin_encoding.py`.
  3. Run that slice's test command, exactly as written, from the repository
     root, and read the count it prints:

         PYTHONPATH=src .venv/bin/python -m pytest tests/test_X.py

     (for `hookio`: `PYTHONPATH=src .venv/bin/python -m pytest
     tests/test_hook_stdin_encoding.py`)

A **claim** is a statement in that module's own docstring -- the string literal
at the top of the file, before the first import -- that asserts something
checkable about *that module's* code: a name, a number, a default, a behaviour,
a rule the code is said to follow. Sentences of pure motivation, history or
opinion are not claims.

For each slice report:

  - `claims`: how many checkable claims the module docstring makes.
  - `mismatches`: every claim the code in that same module contradicts, as
    `{"claim": "...", "why": "..."}` -- `claim` quotes at most 15 words of the
    docstring, `why` says in one sentence what the code does instead.
  - `tests_passed`: the number of tests that passed in step 3.
  - `uncovered`: how many of the `claims` are exercised by NO test in that
    slice's test file.

Return ONE JSON object and nothing else -- no prose before it, no fences:

    {"slices": [{"module": "<name>.py", "claims": <int>, "tests_passed": <int>,
                 "uncovered": <int>,
                 "mismatches": [{"claim": "...", "why": "..."}]}]}

Every slice named above must appear exactly once, keyed by `<name>.py`. A slice
whose docstring makes no checkable claim still appears, with `"claims": 0`.

Do not modify any file. Do not use git. Do not run the suite as a whole -- the
per-slice test command is part of the slice.
