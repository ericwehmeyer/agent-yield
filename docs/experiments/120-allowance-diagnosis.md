# Issue #120: one code path writes allowance.jsonl, and two conditions gate it

Exactly 1 code path in `src/` appends to `.agent-yield/allowance.jsonl`, it is
gated on 2 conditions, and the first of those conditions is not a wiring
question at all. `.agent-yield/` currently holds 0 rows of allowance data
because the file does not exist, while `statusline-cache.json` in the same
directory is 52 bytes with an mtime of 17:06 EDT on 2026-08-29. Both figures
are measured. The statusline ran, wrote one of its two files, and skipped the
other.

#120 is titled as a wiring bug. The wiring is fixed. What remains is a payload
bug: the denominator the allowance module calibrates against is not present in
what this client sends.

## The write needs a `rate_limits` dict, and returns None without one

`src/agent_yield/statusline.py:547-551` is the whole writer:

```python
allowance = read_allowance(payload)
if allowance is not None and writing:
    held = load_allowance(SNAPSHOT_PATH)
    append_allowance(SNAPSHOT_PATH, allowance, held[-1] if held else None)
```

`read_allowance` (`src/agent_yield/allowance.py:99-127`) refuses in two places
before it can return a `Snapshot`:

- line 106-108: `payload.get("rate_limits")` must be a `dict`, else `None`.
- line 109-111: `rate_limits.seven_day.used_percentage` must be a real number
  (`_percentage`, line 83-89, rejects `bool` and non-numerics), else `None`.

So a payload with no `rate_limits` key, or with `rate_limits` present but
`seven_day.used_percentage` null, produces `None`, and line 548 skips the
append silently. That refusal is deliberate and documented at
`allowance.py:100-105`: recording a missing field as 0% "would read as a fresh
allowance". The module is behaving as designed. `tests/test_allowance.py`
passes 12 of 12 on this behaviour.

The evidence that this client omits the field is inferential, not measured.
What is measured: `~/.claude/statusline.ps1:78-81` carries a comment stating
that `context_window.remaining_percentage` arrives null from this client, which
establishes that this client does drop payload fields the tool expects. What
is not measured: the actual key set of a live payload. `.agent-yield/` contains
`boundary-probe.jsonl` and `resume-probe.jsonl` but no `statusline-probe.jsonl`,
so no render has ever recorded what arrives.

## The probe cannot be run by hand, which is why the key set is still unknown

`agent-yield statusline --probe` writes the key set, and `statusline.py:562`
guards it as `if probing and writing`. `--no-write` therefore suppresses the
probe as well as the allowance append, and the comment at lines 489-491 says
that is intentional: a hand-made payload's key set is a claim about the
harness's contract that the harness never made. Under CLAUDE.md and #69, a
hand render without `--no-write` is forbidden.

Now what: the only way to settle this is to add `--probe` to the
`statusLine.command` in `~/.claude/settings.json` for one real session, then
read `.agent-yield/statusline-probe.jsonl`. That is an operator edit to the
boundary file, not an agent edit. It is one flag, and it costs one session.

## The relative SNAPSHOT_PATH is a latent portability risk, not this defect

`allowance.py:47` defines `SNAPSHOT_PATH = Path(".agent-yield") /
"allowance.jsonl"` and `statusline.py:114` defines `CACHE_PATH =
Path(".agent-yield") / "statusline-cache.json"`. Both are bare relative paths,
both are resolved the same way, and both are resolved inside the same process
on the same render: `_cache_write` (line 247-250) and `append`
(`allowance.py:143-149`) each call `Path(path).parent.mkdir` and open relative
to the process cwd. There is no difference in how the two are anchored.

That makes `statusline-cache.json` landing in the repo's `.agent-yield/` a
measurement, not a coincidence: at 17:06 EDT the statusline process's cwd was
the repo root, so `SNAPSHOT_PATH` would have resolved to the repo root too. The
cwd is not what stopped the row. The relative path is still a defect waiting
for the day a statusline renders from a different cwd, and it deserves its own
issue rather than a mention in #120, because fixing it would not produce a
single row today.

## Nothing else writes the file

Grep across `src/` for `append_allowance`, `SNAPSHOT_PATH`, and
`allowance.jsonl` returns 4 non-definition hits. Three are in
`statusline.py:547-550`, the writer above. The fourth, `cli.py:599`, uses
`SNAPSHOT_PATH` only as the `--log` default for `agent-yield allowance`, and
`_cmd_allowance` (`cli.py:320-343`) calls `allowance_module.load` and prints.
It never writes. There is no second producer, no hook, and no backfill path.

## What to do

The fix is the smaller half of the work. If the probe shows `rate_limits`
absent, the allowance denominator is unobtainable on this client and #120
should be closed as not-a-bug against a new issue tracking the payload gap. If
the probe shows `rate_limits` present but shaped differently from
`{seven_day: {used_percentage: int}}`, the fix is in `_percentage` and
`read_allowance` and is roughly 5 to 10 lines.

Either way, the change worth making regardless is observability: `read_allowance`
returning `None` is currently indistinguishable from a payload that had no
movement, and the operator sees neither. One line at `statusline.py:548`
recording the refusal reason, in the probe log rather than the allowance log,
would have answered #120 without a diagnosis.
