#!/usr/bin/env python
"""Work one ready issue without a human present, or refuse and say why.

    python scripts/run-unattended.py --dry-run   # pick, build the brief, stop
    python scripts/run-unattended.py             # pick, claim, run `claude -p`

Exit 0 when a run finished or when there was correctly nothing to do. Exit 1
when a guard refused. Exit 2 when the allowance band says stop.

WHY THIS IS NOT JUST `claude -p "$(pick-issue)"`. Four things stand between the
picker naming an issue and a machine working it unattended, and each is a way
the loop degrades when nobody is watching:

  - **An off switch that does not require killing a process.** `.agent-yield/STOP`
    is a file the operator drops from any shell. It is checked first, before
    the tracker is read, so stopping the loop costs nothing and works even when
    the network does not.
  - **One run at a time.** A scheduler that fires while the last run is still
    going produces two sessions editing one working tree. The lock is a file
    carrying a pid and a start time; a lock older than --lock-max-age-hours is
    broken and the break is reported, because a lock nothing can clear turns
    one crash into a permanently dead loop. #172 is the same defect one level
    up, against the claim label.
  - **A clean tree to start from.** An unattended session that begins on top of
    the last one's uncommitted work cannot tell its own changes from inherited
    ones, and neither can the reader of the diff.
  - **A priced result.** `--output-format json` returns the session's own token
    and dollar figures, and every run appends one row to
    `.agent-yield/unattended.jsonl`. A loop this repo cannot price is the
    defect this repo is about.

WHAT IT DELIBERATELY DOES NOT DO. It does not commit. This box signs with a
YubiKey configured UIF Sign=off behind an 8-hour PIN cache, so a commit from an
unattended run carries the operator's signature with no physical act -- the
signature stops asserting the one thing a signature asserts. #171 holds that
decision. Until it is made, a run leaves its work in the tree and the next run
refuses on the dirty-tree guard until a human has looked, which is the loop
running at the speed of review on purpose. `--commit` flips it, and reading
#171 before passing it is the point of the flag being off.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agent_yield.state import anchored, project_root  # noqa: E402

STOP_FILE = Path(".agent-yield/STOP")
LOCK_FILE = Path(".agent-yield/unattended.lock")
LOG_FILE = Path(".agent-yield/unattended.jsonl")

PICKER = Path(__file__).resolve().parent / "pick-issue.py"

# Keyed the same way `pick-issue.py` keys it, and imported from nowhere because
# duplicating two entries is cheaper than a scripts package. A platform that is
# neither gets None and claims nothing.
MACHINE_LABELS = {"Windows": "windows", "Darwin": "macos"}

# The picker's first line is `#113 title...`. Parsed rather than re-derived, so
# there is one implementation of eligibility and this is not a second opinion.
PICKED = re.compile(r"^#(\d+)\s+(.*)$")

# Enough to read the repo, change it, and run its own test file. Not enough to
# push, install, or reach the network. Stated here rather than in the boundary
# file because `~/.claude/settings.json` is the operator's edit, and a runner
# that widens the operator's standing allowlist to do its job has widened it
# for every interactive session too.
ALLOWED_TOOLS = (
    "Read,Grep,Glob,Edit,Write,TodoWrite,"
    "Bash(.venv/Scripts/python.exe -m pytest*),"
    "Bash(python -m pytest*),"
    "Bash(git status*),Bash(git diff*)"
)


def now() -> datetime:
    return datetime.now(timezone.utc)


def stop_requested(root: Path) -> str | None:
    """The operator's own words from the STOP file, or None."""
    path = anchored(STOP_FILE, root)
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    return text or "STOP file present"


def tree_is_dirty(root: Path) -> str | None:
    """The porcelain lines when the tree is not clean, else None."""
    out = subprocess.run(["git", "status", "--porcelain"], cwd=root,
                         capture_output=True, text=True)
    if out.returncode != 0:
        return f"git status failed: {out.stderr.strip()}"
    return out.stdout.strip() or None


def take_lock(root: Path, max_age_hours: float) -> tuple[Path, str | None]:
    """Claim the single-run lock, or raise RuntimeError naming the holder.

    Returns the lock path and, when an expired lock was broken, a line saying
    so -- the break is reported rather than performed silently, because a
    scheduler that quietly steps over its own lock has no lock.
    """
    path = anchored(LOCK_FILE, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    broke = None
    if path.exists():
        try:
            held = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            held = {}
        started = held.get("started_at", "")
        try:
            age_hours = (now() - datetime.fromisoformat(started)).total_seconds() / 3600
        except (TypeError, ValueError):
            age_hours = None
        if age_hours is None or age_hours < max_age_hours:
            raise RuntimeError(
                f"a run is already holding {path} (pid {held.get('pid', '?')}, "
                f"started {started or 'unknown'}). Delete it if that run is gone."
            )
        broke = (f"broke a lock {age_hours:.1f}h old (pid {held.get('pid', '?')}), "
                 f"past the {max_age_hours}h limit")
    path.write_text(json.dumps({"pid": os.getpid(),
                                "started_at": now().isoformat()}), encoding="utf-8")
    return path, broke


def pick(python: str) -> tuple[int, str]:
    out = subprocess.run([python, str(PICKER)], capture_output=True, text=True)
    return out.returncode, (out.stdout + out.stderr).strip()


def parse_pick(stdout: str) -> tuple[int, str]:
    """The issue number and title from the picker's first line."""
    lines = stdout.splitlines()
    first = lines[0].strip() if lines else ""
    match = PICKED.match(first)
    if not match:
        raise ValueError(
            f"picker exited 0 but its first line is not an issue: {first!r}")
    return int(match.group(1)), match.group(2).strip()


def issue_body(number: int) -> str:
    """The issue, followed by its comments in order.

    Comments are not commentary here. Triage lands in them: #113 carries a
    second deliverable folded in from #122 as a comment, and #168's whole
    reason for being workable is a decision posted as one. A brief built from
    the body alone dispatches an agent against a stale reading of the task,
    and the agent has no way to know that.
    """
    out = subprocess.run(
        ["gh", "issue", "view", str(number), "--json", "body,comments"],
        capture_output=True, text=True)
    if out.returncode != 0:
        return ""
    try:
        data = json.loads(out.stdout)
    except ValueError:
        return ""
    parts = [(data.get("body") or "").strip()]
    for comment in data.get("comments") or []:
        text = (comment.get("body") or "").strip()
        if text:
            parts.append(f"## Comment, added later and part of the task\n\n{text}")
    return "\n\n".join(part for part in parts if part)


def claim(number: int, label: str | None) -> str | None:
    """Label the issue for this box so the other one's picker skips it."""
    if not label:
        return f"unclaimed: {platform.system()} has no machine label"
    out = subprocess.run(["gh", "issue", "edit", str(number), "--add-label", label],
                         capture_output=True, text=True)
    return None if out.returncode == 0 else f"claim failed: {out.stderr.strip()}"


def build_brief(number: int, title: str, body: str, may_commit: bool) -> str:
    """The dispatch brief, carrying section 3's contract in as many words."""
    ending = (
        f"Commit on a branch named `unattended/{number}`, one commit, message "
        f"ending `Closes #{number}`. Do not push. Do not touch `main`."
        if may_commit else
        "Do NOT commit and do NOT push. Leave the change in the working tree; "
        "a human reviews it before anything is committed (#171)."
    )
    return f"""You are an unattended session. No human will answer a question, so a
question is a failed run. When the issue is not actionable as written, stop and
say so in one line rather than guessing.

# The task: issue #{number}

{title}

{body}

# Contract

- Read `CLAUDE.md` first. The interpreter with pytest is
  `.venv/Scripts/python.exe`, and `-rs` is required on every pytest run.
- **Do not explore.** The issue above names the file and the root cause. Open
  what it names and what that file imports. A repository-wide search is a
  failed brief, not diligence.
- Write the fix and the test that fails without it. Run only the test file you
  touched, plus any file the issue names.
- {ending}
- Finish by printing: the files you changed, the exact pytest command you ran,
  and its final summary line. If you did not run it, say that instead of
  implying you did.
"""


def run_claude(brief: str, cwd: Path, permission_mode: str, timeout: int,
               claude: str) -> dict:
    """Invoke `claude -p` and return its JSON result, or a shaped failure."""
    cmd = [claude, "-p", brief, "--output-format", "json",
           "--permission-mode", permission_mode, "--allowed-tools", ALLOWED_TOOLS]
    started = time.monotonic()
    elapsed = lambda: int((time.monotonic() - started) * 1000)  # noqa: E731
    try:
        out = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                             timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"is_error": True, "error": f"timed out after {timeout}s",
                "duration_ms": elapsed()}
    except FileNotFoundError:
        return {"is_error": True, "error": f"{claude} is not on PATH",
                "duration_ms": elapsed()}
    if not out.stdout.strip():
        return {"is_error": True, "duration_ms": elapsed(),
                "error": (out.stderr or f"exit {out.returncode}, no output").strip()[:2000]}
    try:
        return json.loads(out.stdout)
    except ValueError:
        return {"is_error": True, "error": "output was not JSON",
                "raw": out.stdout[:2000], "duration_ms": elapsed()}


def summarise(result: dict) -> dict:
    """The figures worth keeping from a `claude -p` JSON result."""
    usage = result.get("usage") or {}
    return {
        "session_id": result.get("session_id"),
        "num_turns": result.get("num_turns"),
        "duration_ms": result.get("duration_ms"),
        "total_cost_usd": result.get("total_cost_usd"),
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "cache_read_input_tokens": usage.get("cache_read_input_tokens"),
        "cache_creation_input_tokens": usage.get("cache_creation_input_tokens"),
        "is_error": bool(result.get("is_error")),
        "error": result.get("error"),
    }


def log_row(root: Path, row: dict) -> Path:
    path = anchored(LOG_FILE, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")
    return path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true",
                    help="pick and print the brief; claim nothing, run nothing")
    ap.add_argument("--commit", action="store_true",
                    help="let the run commit on a branch. Read #171 first")
    ap.add_argument("--allow-dirty", action="store_true",
                    help="start on top of uncommitted work anyway")
    ap.add_argument("--permission-mode", default="acceptEdits",
                    help="passed to claude -p (default: acceptEdits)")
    ap.add_argument("--timeout", type=int, default=3600,
                    help="seconds before the run is killed (default: 3600)")
    ap.add_argument("--lock-max-age-hours", type=float, default=4.0,
                    help="a lock older than this is broken and the break reported")
    ap.add_argument("--python", default=sys.executable,
                    help="interpreter for the picker")
    ap.add_argument("--claude", default=os.environ.get("AGENT_YIELD_CLAUDE", "claude"),
                    help="the claude executable")
    args = ap.parse_args(argv)

    root = project_root()
    started_at = now().isoformat()

    stop = stop_requested(root)
    if stop:
        print(f"refused: STOP file present -- {stop}")
        return 1

    code, out = pick(args.python)
    if code == 2:
        print(out or "STOP: the allowance band says stop")
        return 2
    if code != 0:
        print(out or "nothing picked")
        return 0                      # nothing to do is the normal night
    number, title = parse_pick(out)

    dirty = None if args.allow_dirty else tree_is_dirty(root)
    if dirty:
        print(f"refused: the working tree is not clean, so #{number} was not started.\n"
              f"{dirty}\nReview and commit it, or pass --allow-dirty.")
        return 1

    brief = build_brief(number, title, issue_body(number), args.commit)

    if args.dry_run:
        print(f"#{number} {title}\n--- brief, {len(brief)} chars ---\n{brief}")
        return 0

    try:
        lock, broke = take_lock(root, args.lock_max_age_hours)
    except RuntimeError as exc:
        print(f"refused: {exc}")
        return 1
    if broke:
        print(broke)

    claim_note = claim(number, MACHINE_LABELS.get(platform.system()))
    if claim_note:
        print(claim_note)
    print(f"#{number} {title}")
    print(f"running claude -p, timeout {args.timeout}s, mode {args.permission_mode}")
    try:
        result = run_claude(brief, root, args.permission_mode, args.timeout, args.claude)
    finally:
        lock.unlink(missing_ok=True)

    row = {"started_at": started_at, "finished_at": now().isoformat(),
           "issue": number, "title": title, "committed": args.commit,
           "permission_mode": args.permission_mode, "claim_note": claim_note,
           "brief_chars": len(brief), **summarise(result)}
    path = log_row(root, row)

    if row["is_error"]:
        print(f"run failed: {row['error']}")
        print(f"logged to {path}")
        return 1
    cost = row["total_cost_usd"]
    priced = f", ${cost:.4f}" if isinstance(cost, (int, float)) else ""
    print(f"done in {row['num_turns']} turns{priced}")
    print(f"logged to {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
