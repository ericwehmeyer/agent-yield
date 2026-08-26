# Portability audit: the sixth instance, and what would actually have caught the first five

## Recommendation

**CI, plus about sixty lines of test, and no `portability.py`.** The decisive number is
this: running the suite as it stands on `windows-latest` would have caught **one** of the
five specimens -- the symlink one, and only because it raises. The other four fail by
succeeding differently, and CI cannot see a difference nothing asserts. What catches them
is cheaper than an abstraction layer and available today: a grep-style guard test that
fails on the raw primitive (catches specimens 2, 3, 4, 5 -- and fires on a real hit in
`tests/test_outcomes.py:21` the first time it runs), a six-line stdin/stdout fixture that
decodes as cp1252 so the encoding class of bug reproduces on Linux (catches 3 and 4 and
the unlisted inbound twin of both), and an eight-line table of path shapes for
`project_slug` (catches 1, which was hand-rolled string surgery and which no wrapper
would have touched). Together: 5 of 5. A `portability.py` catches **0 of 5** on its own,
because nothing stops the next author from calling `subprocess.run` directly -- it only
reaches 4 of 5 once the guard test exists to force its use, at which point the guard is
doing the work and the seam is just where the code happens to live. Ship #50 first, but
ship it in the same PR as the guard test, or it will be scored as "portability handled"
while catching twenty percent.

Eleven new risks below. Six are silent. The worst is that specimen 1 is still live
through a second mechanism -- proven on this machine, not inferred.

---

## Findings, most-silent-first

### N1. `find_session` returns `None` for the whole project if the cwd's case differs -- proven

`src/agent_yield/session.py:82-89` (`project_slug`, case-preserving) and
`src/agent_yield/session.py:144` (`p.parent.name == project_slug(cwd)`, `==`).

Windows path case is not canonical. `os.getcwd()` returns whatever case was used to
enter the directory; the filesystem accepts `c:\users\...` and does not fold it back.
Measured here, same shell, same repo, two minutes apart:

```
== as Claude Code sees it ==            == after a lowercase cd ==
getcwd : C:\Users\ewehm\repos\...       getcwd : C:\users\ewehm\repos\...
slug   : C--Users-ewehm-repos-...       slug   : C--users-ewehm-repos-...
found  : ...7d5bf3a1-....jsonl          found  : None
```

`status` then prints `no session transcript found -- nothing to measure` and exits 0.
`handoff` writes a handoff with no cost in it. `boundary` and `statusline` measure
nothing. This is specimen 1's exact failure -- an exact string comparison against a
directory name the OS did not promise to spell the same way -- reached by a different
route, and the fix for specimen 1 did not close it. Any launcher that supplies a cwd
(a shortcut, a Makefile, a git-bash `cd`, a hook payload's `cwd` value) can trigger it.

Fix: casefold both sides of the comparison on Windows only, or normalise the slug through
`os.path.normcase`. Do **not** lowercase unconditionally -- macOS paths are
case-sensitive to Claude Code's own directory naming.

### N2. `consume` still loses the handoff on Windows, and throws away text it already read -- proven

`src/agent_yield/handoff.py:363` (reads the text) and `:376` (`os.replace`, inside
`except OSError: return None`).

Switching to `os.replace` fixed #42's `FileExistsError` half. It did not fix the other
Windows-only half: `os.replace` raises `PermissionError` (an `OSError`) when either file
is open by another process. An editor, a backup agent, Defender's real-time scan, or a
second `agent-yield` invocation is enough. Reproduced:

```
consume while archive is open -> None
handoff still on disk       -> True
consume after close         -> '# live\n'
```

`resume --hook` then records `no_handoff` and injects nothing -- the same silent report
#42 was filed about. On POSIX this cannot happen; `rename(2)` over an open file always
succeeds, which is why the bug class only exists on one platform.

There is a second bug stacked on it that is not about portability at all: the text was
successfully read at line 363. Returning `None` discards a handoff the function is
holding, in order to report an archiving failure. Return the text, and report the failed
archive separately -- injecting twice is a smaller harm than injecting nothing, and the
`.loaded` sentinel is a convenience, not a correctness invariant.

### N3. Every hook reads `sys.stdin` with no encoding -- the inbound twin of #41 and #43 -- proven

`src/agent_yield/boundary.py:291`, `src/agent_yield/gate.py:244`,
`src/agent_yield/resume.py:217`, `src/agent_yield/statusline.py:364`.

Measured on this machine (CPython 3.14.4, `utf8_mode 0`):

```
stdin  cp1252 surrogateescape
stdout cp1252 surrogateescape
stderr cp1252 backslashreplace
```

Hook payloads are UTF-8 JSON produced by node. Fed a payload whose `transcript_path` is
`C:\Users\José\s.jsonl`:

```
want : 'C:\\Users\\Jos\xe9\\s.jsonl'
got  : 'C:\\Users\\Jos\xc3\xa9\\s.jsonl'
SURVIVED: False
```

Nothing raises -- `surrogateescape` absorbs the undefined code points -- so the corruption
is pure and silent. `resolve_transcript` then finds no such file, falls through to
`session_id`, and if N1 is also in play returns `None`; every hook swallows the outcome in
`except Exception: return 0`. This is exactly specimen 3's defect on the other side of the
process boundary, and neither #41 nor #43 covers it. Any operator whose Windows account
name, repo path, or prompt carries a non-ASCII character is affected, permanently and
without a symptom.

Fix: `sys.stdin.reconfigure(encoding="utf-8", errors="replace")` at each hook entry, or
read `sys.stdin.buffer` and decode explicitly.

### N4. The transcript walk silently drops subtrees past MAX_PATH

`src/agent_yield/discovery.py:79` and `:82` (`root.rglob(...)`), consumed by
`ingest.py:136` and `agents.py`.

Measured on this machine, today:

```
C:\Users\ewehm\.claude\projects            940 files, longest path 166 chars
C:\Users\ewehm\AppData\Local\Temp\claude   108625 files, longest path 288 chars
```

288 is already past the 260-character `MAX_PATH` limit. It works here only because
`LongPathsEnabled = 1` in the registry, which is **off by default** on stock Windows and
is a per-machine setting nobody in this repo controls. With it off, `scandir` fails on
those subtrees, `glob` swallows `OSError` (confirmed: the stdlib `glob` module catches
`OSError` in six places on the scandir path), and `find_transcripts` returns a shorter
list with no error. `ingest` then reports a smaller call count. Undercounting is the one
error this tool's own docstrings say it exists to prevent, and here it happens with a
clean exit 0.

Fix is cheap and does not require solving long paths: have `find_transcripts` count the
roots it walked and the directories it could not enter, and have `ingest` print that
count. A silent zero and a real zero must not look the same.

### N5. The home-directory redaction leaks the account name on UNC paths

`src/agent_yield/report_html.py:108-113` (`_repo`).

The function already handles drive letters and both separators -- someone did this one
properly. UNC defeats it: `\\server\Users\ada` splits to `["server", "Users", "ada"]`,
which is three segments rather than two, so the `len(parts) == 2` home check does not fire
and the function returns `"ada"`. Same for `\\wsl.localhost\Ubuntu\home\eric` -> `"eric"`.
The entire purpose of the function is to keep a person's name off a page that may be
shared, and a Windows network path or a WSL mount walks straight past it.

Latent rather than live: `render_html` is not wired to any CLI subcommand
(`grep -n html src/agent_yield/cli.py` returns nothing). Fix before it is, not after.

### N6. `sys.stdout` raises on unmappable characters, and the hooks are safe only by accident

This is #43, with two corrections worth adding to the issue.

First, the failure is loud, not silent. `sys.stdout.errors` is `surrogateescape`, which
covers lone surrogates and **not** unmappable characters:

```
RAISED UnicodeEncodeError 'charmap' codec can't encode character '\u2192'
```

Exposed `print` sites in `src/agent_yield/cli.py`: `:107` (intervention names, read from
`interventions.toml`), `:238` and `:267` (the handoff body -- commit subjects and dirty
paths, verbatim), `:285` (the output path). Today the repo's git subjects are clean (0 of
them would raise) and `interventions.toml` is clean, but `README.md` already contains `≈`
and `→`. The first commit subject or intervention name with an arrow in it turns
`agent-yield report` into a traceback.

Second, and more important: **the hooks are protected by an accident.** `boundary.py:320`,
`gate.py:260` and `resume.py:246` all emit through `json.dumps`, which defaults to
`ensure_ascii=True` and therefore emits pure ASCII. Anyone who adds `ensure_ascii=False`
for readability silently breaks every hook on Windows. Worth a comment at each site.
`sys.stderr.errors` is `backslashreplace`, so the exit-2 refusal path is genuinely safe.

Fix is one line in `cli.main`: `sys.stdout.reconfigure(encoding="utf-8", errors="replace")`.

### N7. The test suite calls the banned primitive, in the file that bans it

`tests/test_outcomes.py:21`:

```python
subprocess.run(["git", *args], cwd=cwd, env=env, capture_output=True, text=True, check=True)
```

`text=True`, no `encoding=` -- specimen 3 exactly -- sixty lines above
`test_git_output_is_decoded_as_utf8_not_the_locale_codepage`, which exists to assert that
this never happens. It passes today only because the helper captures output it then
discards. The moment anyone reads `result.stdout` from it, #41 is back. It is also the
best available evidence that a grep-guard has work to do on day one rather than being a
ceremonial check on already-clean code.

### N8. No test anywhere exercises a real decode path

Every hook test injects `io.StringIO`: `tests/test_boundary.py:124,130,166,173,181,195,218,244,248,262`,
`tests/test_gate.py:74,80,86,90,91,100,164,170,176,188`, `tests/test_resume.py:33,105`,
`tests/test_handoff.py:318`, `tests/test_cli.py:342,349`.

`StringIO` carries no encoding at all. The `stdin=` parameter on `main()` is good design
and the right seam -- it is simply a transparent one, so the class of bug that owns two of
the five specimens is structurally invisible to the suite on every platform. This is why
specimen 3 had to be found through a *subprocess* test rather than a hook test, and why N3
has never been noticed. The fixture in Slice 3 below is the whole fix, and it is six lines.

### N9. The git test helper strips the environment down to `PATH`

`tests/test_outcomes.py:14-19` builds `env` from `PATH` plus four identity variables. It
drops `SystemRoot`, `TEMP`, and `USERPROFILE`. It works with this git build; a stripped
environment is a documented way to break child processes on Windows that need
`SystemRoot`, and the failure would present as an unreproducible CI flake on one platform.
Add `SystemRoot` when `os.name == "nt"`.

### N10. Three `find_session` tests derive their expectation from the code under test

`tests/test_session.py:252,267,285,296` use `Path("/repo/mine")` as a stand-in cwd. On
Windows that is `\repo\mine` and slugs to `-repo-mine`; the fixture builds the directory
by calling `project_slug` itself, so both sides move together and the assertion holds on
either platform while testing neither. Not wrong, but it is the precise shape that made
specimen 1 invisible for as long as it was: the expected value is computed by the function
being tested. `test_project_slug_handles_windows_separators` (`:211`) is the good pattern
-- literal input, literal expected output, both platforms asserted in one test -- and it
is the pattern Slice 4 extends.

### N11. CRLF in every file this tool writes (benign today, worth one line)

`ingest.py:150` (`calls.jsonl`), `handoff.py:330` (`handoff.md`), `modes.py:83`
(`session-modes.toml`), `boundary.py:229`, `resume.py:199`, `statusline.py:333` (the probe
JSONLs), `statusline.py:154` (the cache). None pass `newline=""`, so all get `\r\n` on
Windows. Every internal reader goes through `read_text` + `splitlines()`, which normalises,
and `json.loads` tolerates a trailing `\r`, so nothing breaks. Listed because these files
are this tool's record of its own measurements, they differ byte-for-byte by platform, and
`statusline._slice:107` already opens one of these trees in `"rb"` and slices by byte
offset. One `newline="\n"` per site closes it.

### Checked and clean

Reported so the audit is falsifiable rather than a list of what went wrong.

- All five `subprocess.run` sites carry `encoding="utf-8", errors="replace"`
  (`outcomes.py:29,136,142,149`, `handoff.py:66`). Specimen 3 is properly fixed in `src/`.
- No `shell=True` anywhere; every invocation passes an argument list.
- Every `open`/`read_text`/`write_text` in `src/` carries `encoding=` -- eighteen sites, all
  checked.
- `src/` contains exactly one non-ASCII codepoint, `§` (U+00A7, sixteen occurrences), which
  *is* cp1252-encodable, so no source literal can trip N6.
- `discovery.py:57-59` already guards `os.getuid` with `getattr` rather than `sys.platform`.
- `outcomes.py:51-56` and `handoff.py:73-80` already anchor git's approxidate to UTC;
  `records.py:24-28` buckets days in UTC deliberately. The timezone class is handled.
- `os.environ`'s case-insensitivity on Windows is unobservable here: both override
  variables are read through a module constant and set in tests through the same constant.
- Both skips in the suite are **named** (`test_discovery.py:22`, `test_ingest.py:87`) and
  `test_ingest.py:64` parametrizes so the copy arm always runs on an unprivileged box. This
  is the correct handling of specimen 5 and should be the model for any future skip.

---

## Mechanisms, with the specimen-catch count for each

The five specimens: **S1** `project_slug` string surgery, **S2** `Path.rename` overwrite,
**S3** `subprocess text=True`, **S4** `sys.stdout` cp1252, **S5** `symlink_to` WinError 1314.

| Mechanism | Catches | Cost | Notes |
|---|---|---|---|
| CI matrix alone (#50) | **1/5** -- S5 | one workflow file | Catches only what raises |
| `portability.py` alone | **0/5** | ~150 lines + churn | Nothing forces its use |
| `portability.py` + guard test | 4/5 -- S2,S3,S4,S5 | ~200 lines | Guard does the work; seam is where code lives |
| **Guard test alone** | **4/5** -- S2,S3,S4,S5 | **~30 lines** | Fires at the moment the line is typed |
| **Hostile-encoding fixture** | **2/5** -- S3,S4 (+N3) | **~6 lines** | Reproduces the class on Linux, no CI needed |
| **Path-shape table** | **1/5** -- S1 (+N1) | **~8 lines** | The only mechanism that catches S1 |
| Guard + fixture + table + CI | **5/5** | ~60 lines + workflow | Recommended |

**Why CI alone scores 1/5.** Take them one at a time against the suite *as it stood before
each fix*. S1: pre-fix `project_slug` returned a Windows path unchanged, and a test written
from POSIX paths passes identically on both platforms -- red on neither. S2:
`test_consume_a_second_time_returns_none` does consume twice, but the first consume removes
`handoff.md`, so the second never reaches the rename -- green on Windows. S3: no test used
a non-ASCII commit subject until the fix added one -- green. S4: nothing asserts stdout
bytes -- green. S5: the symlink arm raises `WinError 1314` -- **red**. One. CI is an
execution substrate; it finds only what something already asserts, and three of the five
specimens fail by succeeding.

**Why a seam does not help with S1.** Specimen 1 was `str(path).replace(...)` chained five
times. There is no stdlib call to wrap. Moving that code into `portability.project_slug`
changes the import line and nothing else -- the bug was a missing case, not a missing
abstraction, and the fix that landed is the same five lines with two more `.replace` calls
in them. N1 above proves the point twice over: the *fixed* function is still wrong, in the
same file, for a reason a wrapper would not have addressed either. The eight-line table of
path shapes is what catches both.

**Why the guard test beats the seam it would enforce.** A guard test fails on the author's
machine, in under a second, on the line just typed, with a message naming the specimen it
protects. A seam fails nowhere; it is a convention, and conventions in this repo are
already documented in `working-method.md` and already routinely missed. The guard is also
honest about its own limits in a way a seam is not: it can only ban what it can grep for,
so writing it forces you to enumerate exactly which primitives you claim to have handled.

**Better than either, and nobody raised it: make the hostile case reproducible on Linux.**
A `TextIOWrapper` over a `BytesIO` of UTF-8 bytes, declared `encoding="cp1252"`, turns the
entire encoding class -- S3, S4, N3 -- into a test that fails on Ubuntu at the author's
desk with no Windows box in the loop. Six lines. This is strictly better than forcing a
hostile code page in CI (`chcp 932`, `PYTHONLEGACYWINDOWSSTDIO=1`), which is one more thing
that only runs remotely and only on one leg of the matrix.

**Property tests over path shapes: yes, but as a table, not a library.** `hypothesis`
generating path strings would spend its budget on shapes Claude Code never produces. Eight
literal rows -- POSIX, Windows drive, lowercase drive, mixed-case components, UNC, WSL
mount, trailing separator, bare `~` -- catch S1, N1 and N5, and read as documentation.

**Making the primitives unimportable: no.** An import hook or a `__getattr__` shim that
raises on `subprocess.run` is more machinery than the bugs justify, breaks tooling, and
would have to be disabled inside the portability module itself. The guard test gets the
same result by reading the source.

---

## Sequenced plan

Independently checkable slices. Every acceptance check prints under ten lines.

### Slice 1 -- CI matrix (#50). *Catches: S5.*

`.github/workflows/test.yml`: `windows-latest` / `macos-latest` / `ubuntu-latest`,
Python 3.11 and 3.14, `pip install -e .`, `pytest -q`. Nothing more; this slice is
substrate, not measurement.

```
gh run list --limit 3 --json name,conclusion -q '.[]|[.name,.conclusion]|@tsv'
```

### Slice 2 -- the guard test. *Catches: S2, S3, S4, S5. Ships in the same PR as Slice 1.*

`tests/test_portability_guard.py`, roughly thirty lines, reading `src/` and `tests/` as
text. One rule per specimen, each with the issue number in its failure message:

- every `subprocess.run(` / `Popen(` call carries `encoding=` (S3 -- **fires on
  `tests/test_outcomes.py:21` today**, so fix N7 in this slice)
- no `text=True` without `encoding=` on the same call (S3)
- no `.rename(` on a `Path` -- use `os.replace` (S2)
- `cli.main` contains a `sys.stdout.reconfigure` line (S4)
- every `.symlink_to(` in `tests/` is inside a function that also mentions `skip` (S5)

Sequencing note: this slice is why #50 must not ship alone. CI catches 1/5; CI plus this
catches 4/5 (5/5 with slices 3 and 4). Merging #50 by itself invites the entry
"portability: CI added" in `NEXT.md`, which is the retracted-lever failure this repo keeps
writing down.

```
python -m pytest tests/test_portability_guard.py -q 2>&1 | tail -3
```

### Slice 3 -- hostile-encoding stream fixture. *Catches: S3, S4, and N3.*

`tests/conftest.py`:

```python
def cp1252_stdin(payload):
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return io.TextIOWrapper(io.BytesIO(raw), encoding="cp1252", errors="surrogateescape")
```

Add one test per hook feeding a payload whose `transcript_path` and `cwd` carry a non-ASCII
character, asserting the value survives. Fails on Linux today. Then fix N3 by reconfiguring
stdin at each of the four entry points.

```
python -m pytest -q -k cp1252 2>&1 | tail -3
```

### Slice 4 -- path-shape table, and case-fold the slug comparison. *Catches: S1 and N1.*

Extend `test_project_slug_handles_windows_separators` into a `parametrize` table of the
eight literal shapes. Add a test that `find_session` matches when only the cwd's case
differs. Then normalise both sides of `session.py:144` through `os.path.normcase`.

```
cd /c/users/ewehm/repos/agent-yield && python -c "from agent_yield.session import find_session as f; print('found' if f() else 'NONE -- N1 still live')"
```

### Slice 5 -- `consume` keeps the text it has already read. *Closes N2.*

Return the text when `os.replace` fails; report the archive failure on stderr. Test with the
archive held open by a live file handle -- that test fails on Windows today and passes
vacuously on POSIX, so mark it with a named `skipif`, the way `test_ingest.py:87` does.

```
python -m pytest -q -k "consume" 2>&1 | tail -3
```

### Slice 6 -- one line in `cli.main`. *Closes N6 / #43.*

`sys.stdout.reconfigure(encoding="utf-8", errors="replace")`. Add the comment at
`boundary.py:320`, `gate.py:260`, `resume.py:246` explaining that `ensure_ascii=True` is
load-bearing on Windows.

```
python -c "import sys;sys.argv=['x'];from agent_yield.cli import main" && python -m agent_yield.cli predict 2>&1 | tail -2
```

### Slice 7 -- make an unwalkable root visible. *Closes N4.*

`find_transcripts` counts directories it could not enter; `ingest` prints the count when it
is non-zero. No attempt to solve long paths -- just refuse to let a partial walk look like a
complete one.

```
python -m agent_yield.cli ingest --dest .agent-yield/calls.jsonl 2>&1 | tail -3
```

### Slice 8 -- UNC in `_repo`, and `newline="\n"`. *Closes N5 and N11.*

Two small edits, worth one slice together because neither is urgent and both are one-line.
Do N5 before `render_html` is wired to a subcommand, not after.

```
python -m pytest -q tests/test_report_html.py 2>&1 | tail -3
```

---

## On the sequencing question

Agree that #50 goes first, disagree with the stated reason. "A seam without execution just
relocates untested code" is true and understates it: **execution without assertions
relocates nothing and finds almost nothing either.** CI on this suite scores 1 of 5. The
right argument for CI-first is that three of the four mechanisms recommended here are
tests, and a test that only ever runs on the author's machine is a test that only ever runs
on one platform -- CI is the substrate the rest need. But the substrate is not the
measurement, and #50 merged alone would be a lever that looks like coverage and delivers
twenty percent of it. Slices 1 and 2 are one PR.
