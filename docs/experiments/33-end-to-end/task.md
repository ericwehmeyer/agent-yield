Audit the module docstring of every module in `src/agent_yield` against the code
in that same module.

The module list is FIXED. Audit exactly these 19, no others, no fewer:

    agents.py   boundary.py   cli.py       discovery.py  gate.py
    handoff.py  ingest.py     interventions.py           modes.py
    outcomes.py predict.py    records.py   report.py     report_html.py
    resume.py   session.py    statusline.py              thresholds.py
    usage.py

A **claim** is a statement in that module's own docstring -- the string literal
at the top of the file, before the first import -- that asserts something
checkable about *that module's* code: a name, a number, a behaviour, a rule the
code is said to follow. Sentences of pure motivation, history or opinion are not
claims.

For each module report:

  - `claims`: how many checkable claims the docstring makes.
  - `mismatches`: every claim the code in that module contradicts, as
    `{"claim": "...", "why": "..."}` -- `claim` quotes at most 15 words of the
    docstring, `why` says in one sentence what the code does instead.

Return ONE JSON object and nothing else -- no prose before it, no fences:

    {"modules": [{"module": "<name>.py", "claims": <int>,
                  "mismatches": [{"claim": "...", "why": "..."}]}]}

Every module named above must appear exactly once. A module whose docstring
makes no checkable claim still appears, with `"claims": 0`.

Do not modify any file. Do not run the test suite. Do not use git.
