"""#47's secondary, and #52's answer: WHERE do the tokens sit, and what did they cost?

The token ranking and the dollar ranking of the three arms disagree in sign.
This script is the reconciliation, and it now uses the repo's own instrument
rather than reimplementing one:

  * `ingest.load_records` -- which, since #53, keeps each call's TERMINAL record
    rather than its first. The old count of this script's `output` column was
    short by up to 5.3x, and short in proportion to how much an arm dispatched.
  * `pricing.price_records` -- which, since #55, reproduces the CLI's own
    `total_cost_usd` to the cent, including the 1h/5m cache-write split that
    subagents and parents do not share.

The weighted-token column this script used to print is GONE. It was dollars
divided by a base rate, computed three ways wrong, and its 22% spread across
arms was the symptom. Dollars are the unit; the archive had them all along.

The four #33 arms read from `tests/fixtures/arms-33/`, which is committed. The
two #47 baton1 arms read from a scratch worktree's transcripts, which are
volatile -- if they are gone, the run says so rather than quietly dropping an
arm. Their `-p` output is already lost; their dollars below are the recorded
figures.
"""
import json
import statistics
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "src"))
from agent_yield.ingest import incomplete_calls, load_records  # noqa: E402
from agent_yield.pricing import price_records  # noqa: E402
from agent_yield.usage import Usage  # noqa: E402

FIXTURES = REPO / "tests" / "fixtures" / "arms-33"
TRUTH = json.loads((FIXTURES / "ground-truth.json").read_text())["arms"]

# The #47 worktree, whose `-p` output no longer exists. These two dollar figures
# are the ones recorded when the arms ran.
WORKTREE = (Path.home() / ".claude" / "projects" /
            "-private-tmp-claude-501--Users-ericw-IdeaProjects-agent-yield"
            "-b87046ab-1d77-46eb-8014-870cc270d8c9-scratchpad-ay47")
RECORDED = {"baton1-r1": 1.78, "baton1-r2": 1.84}


def worktree_files(session: str) -> list[Path]:
    files = [WORKTREE / f"{session}.jsonl"]
    subagents = WORKTREE / session / "subagents"
    if subagents.is_dir():
        files += sorted(subagents.glob("agent-*.jsonl"))
    return [path for path in files if path.exists()]


ARMS = [
    ("baton-r1", [FIXTURES / "baton-r1.jsonl"]),
    ("baton-r2", [FIXTURES / "baton-r2.jsonl"]),
    ("baton1-r1", worktree_files("33333333-0000-4000-8000-000000003010")),
    ("baton1-r2", worktree_files("33333333-0000-4000-8000-000000003020")),
    ("reader-r1", [FIXTURES / "reader-r1.jsonl"]),
    ("reader-r2", [FIXTURES / "reader-r2.jsonl"]),
]

print(f"{'arm':11}{'calls':>6}{'inc':>5}{'create':>10}{'5m %':>7}{'read':>12}"
      f"{'output':>9}{'raw total':>12}{'$':>8}")
rows: dict[str, tuple[Usage, float]] = {}
for name, paths in ARMS:
    if not paths:
        print(f"{name:11}  -- transcripts gone, arm skipped --")
        continue
    records = load_records(paths)
    total = Usage.zero()
    for record in records:
        total = total + record.usage
    dollars = (TRUTH[name]["total_cost_usd"] if name in TRUTH
               else RECORDED[name])
    rows[name] = (total, dollars)
    share = 100 * total.cache_creation_5m / total.cache_creation_tokens
    print(f"{name:11}{len(records):>6}{incomplete_calls(records):>5}"
          f"{total.cache_creation_tokens:>10,}{share:>6.1f}%"
          f"{total.cache_read_tokens:>12,}{total.output_tokens:>9,}"
          f"{total.total:>12,}{dollars:>8.2f}")

print()
print("A transcript-only price, against the bill. The gap is not slack: it is")
print("the priced value of the output in calls whose terminal record was never")
print("written (`inc` above), plus the Haiku spend no transcript records.")
for name, (_total, dollars) in rows.items():
    priced = price_records(load_records(dict(ARMS)[name]))
    print(f"  {name:11} priced {priced.dollars:>7.4f}   billed {dollars:>7.4f}"
          f"   gap {dollars - priced.dollars:>7.4f}")

print()
print(f"{'arm':11}{'raw mean':>12}{'output mean':>13}{'$ mean':>9}")
by_arm: dict[str, list[tuple[Usage, float]]] = {}
for name, row in rows.items():
    by_arm.setdefault(name.split("-r")[0], []).append(row)
for arm, values in by_arm.items():
    print(f"{arm:11}{statistics.fmean(v[0].total for v in values):>12,.0f}"
          f"{statistics.fmean(v[0].output_tokens for v in values):>13,.0f}"
          f"{statistics.fmean(v[1] for v in values):>9.2f}")


def mean_dollars(arm: str) -> float:
    return statistics.fmean(v[1] for v in by_arm[arm])


def mean_raw(arm: str) -> float:
    return statistics.fmean(v[0].total for v in by_arm[arm])


print()
print(f"#33 headline, raw tokens      reader/baton = "
      f"{mean_raw('reader') / mean_raw('baton'):.2f}x")
print(f"#33 headline, DOLLARS         reader/baton = "
      f"{mean_dollars('reader') / mean_dollars('baton'):.2f}x")
if "baton1" in by_arm:
    print(f"#47 packing, raw tokens       baton1/baton = "
          f"{mean_raw('baton1') / mean_raw('baton'):.2f}x")
    print(f"#47 packing, DOLLARS          baton1/baton = "
          f"{mean_dollars('baton1') / mean_dollars('baton'):.2f}x")
