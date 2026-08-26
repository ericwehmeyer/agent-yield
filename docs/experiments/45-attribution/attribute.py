"""Which machine made this commit? (issue #45)

Two machines work this repo through GitHub (§7). Every git-denominated metric in
`report` divides one machine's tokens by two machines' commits -- #44 measured
that error at 25x, and the daily report's "24% worse" rested on it -- RE-RUN
2026-08-26 on the reflog denominator, that figure is 225% worse, and two of the
report's three ratios reverse sign (#45's obligation, #67; do not quote 24%,
0.59x, 0.61x or 5,267). #45 proposed
the fix: correlate commit timestamps against this machine's calls, +/- 6 min,
with `unknown` a real outcome. The dashboard review (2026-08-26) warned that the
acceptance check must not be a hand execution of the rule itself.

**It is not a heuristic problem. Git does record the machine, and the record is
the reflog.** `.git/logs/HEAD` is per-clone and never pushed: it holds a
`commit:` line for every commit this clone created and a `rebase ... (pick)`
line for every one it replayed. Nothing arriving over the wire gets either. So
this file measures the proposed heuristic AGAINST the reflog, which is evidence
of a different kind, and reports how far off it is.

THREE OUTCOMES, because two would be a lie:

    LOCAL    the reflog shows this clone creating that sha
    FOREIGN  the reflog covers that moment and does not
    UNKNOWN  the commit predates the reflog -- this clone did not exist yet, so
             its silence is not evidence

WHAT THE REFLOG CANNOT DO, stated before the numbers rather than after:

* It **expires** (`gc.reflogExpire`, 90 days reachable / 30 unreachable). This
  answers "who made it" for recent work, which is what a daily report asks, and
  it will not answer it for a quarter-old commit.
* **A rebase re-commits.** When the other machine rebases work authored here,
  the sha it publishes was created there, and this clone never saw the original.
  Author date survives a rebase and committer date does not, which is why both
  are reported and why the heuristic below is scored against both.
* It is **per clone**. Each machine can compute its own set; combining them is a
  transport question, not a measurement one -- and the denominator this repo
  actually needs is "commits from THIS machine", which one clone can answer
  alone.

    python3 docs/experiments/45-attribution/attribute.py [--repo PATH]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from bisect import bisect_left
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from agent_yield.discovery import default_roots, find_transcripts
from agent_yield.ingest import load_records

QUIET = dt.timedelta(hours=2)   # past this, silence stops being evidence of anything

def created_here(action: str) -> bool:
    """Does this reflog action mean THIS CLONE WROTE THIS SHA?

    Read the verb, not the message: the subject after the first colon is the
    commit's own text and contains anything. The verbs that write a sha are
    `commit`, `commit (amend)`, any `(pick)` -- a rebase or `pull --rebase`
    replaying work, which mints a sha that exists nowhere else -- and a bare
    `rebase (continue)`, which is how a conflicted pick finishes. **That last one
    is easy to miss and this file did miss it**, marking three commits this clone
    made as foreign: #52, #56 and #57, the same three whose subjects the rebase
    ate (§7). The verbs that only MOVE the tip -- `(start)`, `(finish)`, `reset`,
    `pull`, `clone`, `(abort)` -- create nothing, and a foreign sha arrives under
    exactly those.
    """
    verb = action.split(":", 1)[0].strip()
    return (verb.startswith("commit")
            or verb.endswith("(pick)")
            or verb.endswith("(continue)"))


@dataclass(frozen=True)
class Commit:
    sha: str
    authored: dt.datetime
    committed: dt.datetime
    subject: str

    @property
    def rewritten(self) -> bool:
        return self.authored != self.committed


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True,
                          text=True, encoding="utf-8", errors="replace").stdout


def read_commits(repo: Path) -> list[Commit]:
    commits = []
    for line in _git(repo, "log", "--format=%H|%aI|%cI|%s").splitlines():
        parts = line.split("|", 3)
        if len(parts) != 4:
            continue
        sha, authored, committed, subject = parts
        commits.append(Commit(
            sha,
            dt.datetime.fromisoformat(authored).astimezone(dt.timezone.utc),
            dt.datetime.fromisoformat(committed).astimezone(dt.timezone.utc),
            subject,
        ))
    return commits


def reflog(repo: Path) -> tuple[set[str], dt.datetime | None]:
    """(shas this clone created, when the reflog begins).

    The second value is what makes UNKNOWN honest: before it, this clone did not
    exist and its silence says nothing about who made anything.
    """
    created: set[str] = set()
    earliest: dt.datetime | None = None
    for line in _git(repo, "reflog", "show", "--date=iso-strict", "--format=%H|%gd|%gs",
                     "HEAD").splitlines():
        parts = line.split("|", 2)
        if len(parts) != 3:
            continue
        sha, when, action = parts
        match = re.search(r"\{(.+?)\}", when)
        if match:
            try:
                stamp = dt.datetime.fromisoformat(match.group(1)).astimezone(dt.timezone.utc)
                earliest = stamp if earliest is None else min(earliest, stamp)
            except ValueError:
                pass
        if created_here(action):
            created.add(sha)
    return created, earliest


def truth_label(commit: Commit, created: set[str], begins: dt.datetime | None) -> str:
    if commit.sha in created:
        return "LOCAL"
    if begins is None or commit.committed < begins:
        return "UNKNOWN"
    return "FOREIGN"


def local_call_times() -> list[dt.datetime]:
    """Every call this machine made, across every project: the unit is the machine."""
    records = load_records(find_transcripts(default_roots()))
    return sorted(r.timestamp for r in records if r.timestamp)


def nearest(times: list[dt.datetime], when: dt.datetime) -> dt.timedelta | None:
    if not times:
        return None
    i = bisect_left(times, when)
    gaps = []
    if i < len(times):
        gaps.append(times[i] - when)
    if i:
        gaps.append(when - times[i - 1])
    return min(gaps)


def guess(when: dt.datetime, calls: list[dt.datetime], window: dt.timedelta) -> str:
    """#45's proposed rule: was this machine busy near the commit?"""
    gap = nearest(calls, when)
    if gap is None or gap > QUIET:
        return "UNKNOWN"
    return "LOCAL" if gap <= window else "FOREIGN"


def score(commits: list[Commit], truth: dict[str, str], calls: list[dt.datetime],
          stamp: str, window: dt.timedelta) -> dict:
    guessed = {c.sha: guess(getattr(c, stamp), calls, window) for c in commits}
    judged = [c.sha for c in commits if truth[c.sha] != "UNKNOWN"]
    agree = sum(1 for s in judged if guessed[s] == truth[s])
    said_local = [s for s in judged if guessed[s] == "LOCAL"]
    really_local = [s for s in judged if truth[s] == "LOCAL"]
    tp = len(set(said_local) & set(really_local))
    return {
        "window_min": int(window.total_seconds() // 60),
        "local": sum(1 for v in guessed.values() if v == "LOCAL"),
        "foreign": sum(1 for v in guessed.values() if v == "FOREIGN"),
        "unknown": sum(1 for v in guessed.values() if v == "UNKNOWN"),
        "judged": len(judged),
        "accuracy": agree / len(judged) if judged else 0.0,
        "precision": tp / len(said_local) if said_local else 0.0,
        "recall": tp / len(really_local) if really_local else 0.0,
        "over": len(said_local) / len(really_local) if really_local else 0.0,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[3])
    args = ap.parse_args(argv)

    commits = read_commits(args.repo)
    created, begins = reflog(args.repo)
    truth = {c.sha: truth_label(c, created, begins) for c in commits}
    calls = local_call_times()

    counts = {v: sum(1 for x in truth.values() if x == v)
              for v in ("LOCAL", "FOREIGN", "UNKNOWN")}
    print(f"{len(commits)} commits; this clone's reflog begins {begins:%Y-%m-%d %H:%M} UTC")
    print(f"{len(calls):,} calls from this machine, {calls[0].date()} to {calls[-1].date()}\n")
    print("GROUND TRUTH, from .git/logs/HEAD -- a record git keeps per clone and never pushes")
    print(f"  LOCAL    {counts['LOCAL']:>4}   this clone created the sha "
          f"({sum(1 for c in commits if c.sha in created and not c.rewritten)} original, "
          f"{sum(1 for c in commits if c.sha in created and c.rewritten)} replayed by a rebase)")
    print(f"  FOREIGN  {counts['FOREIGN']:>4}   the reflog covers that moment and does not")
    print(f"  UNKNOWN  {counts['UNKNOWN']:>4}   older than this clone -- not attributable, and said so")

    print("\n#45's PROPOSED RULE, SCORED AGAINST IT (author time, which a rebase preserves)")
    print(f"{'window':>8}{'LOCAL':>8}{'FOREIGN':>9}{'UNKNOWN':>9}"
          f"{'accuracy':>10}{'precision':>11}{'over-attributes':>17}")
    for minutes in (1, 2, 5, 6, 10, 30):
        r = score(commits, truth, calls, "authored", dt.timedelta(minutes=minutes))
        print(f"{minutes:>6}m{r['local']:>8}{r['foreign']:>9}{r['unknown']:>9}"
              f"{r['accuracy']:>10.1%}{r['precision']:>11.1%}{r['over']:>16.2f}x")

    print("\nAND ON COMMITTER TIME, which is what #45 wrote down")
    for minutes in (6,):
        r = score(commits, truth, calls, "committed", dt.timedelta(minutes=minutes))
        print(f"{minutes:>6}m{r['local']:>8}{r['foreign']:>9}{r['unknown']:>9}"
              f"{r['accuracy']:>10.1%}{r['precision']:>11.1%}{r['over']:>16.2f}x")

    six = score(commits, truth, calls, "authored", dt.timedelta(minutes=6))
    print(f"\nWHY IT FAILS, and it is not a tuning problem: at every window from 1 to 30")
    print("minutes the rule calls almost everything LOCAL. Both machines work the same")
    print("hours -- that is what §7's queue is FOR -- so 'this machine was busy near the")
    print(f"commit' is true of a foreign commit too. At #45's own 6 minutes it claims")
    print(f"{six['local']} of {len(commits)} commits for this machine when {counts['LOCAL']} are its:")
    print(f"a {six['over']:.2f}x over-attribution, in the numerator's favour, silently.")

    rewritten = [c for c in commits if c.rewritten]
    drift = sorted(c.committed - c.authored for c in rewritten)
    print(f"\nA SECOND REASON THE PROPOSED STAMP IS WRONG: {len(rewritten)} of {len(commits)} "
          f"({len(rewritten) / len(commits):.0%}) commits")
    print(f"carry a rewritten committer stamp -- a rebase moved it by {drift[len(drift)//2]} at the")
    print(f"median and up to {drift[-1]}. Committer time is when history was last")
    print("touched, by whoever touched it. Author time is when the work was done.")

    misses = [c for c in commits
              if truth[c.sha] == "FOREIGN"
              and guess(c.authored, calls, dt.timedelta(minutes=6)) == "LOCAL"]
    print(f"\n  {len(misses)} foreign commits the rule claims as local. The first six:")
    for c in misses[:6]:
        gap = nearest(calls, c.authored)
        print(f"    {c.sha[:7]} {c.authored:%m-%d %H:%M}  nearest local call {gap}"
              f"  {c.subject[:44]}")

    out = Path(__file__).parent / "attribution.json"
    out.write_text(json.dumps({
        "commits": len(commits),
        "calls": len(calls),
        "reflog_begins": begins.isoformat() if begins else None,
        "truth_counts": counts,
        "rewritten_committer_stamps": len(rewritten),
        "rule_at_6min_author": six,
        "labels": {c.sha[:7]: truth[c.sha] for c in commits},
    }, indent=1) + "\n", encoding="utf-8")
    print(f"\nwritten: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
