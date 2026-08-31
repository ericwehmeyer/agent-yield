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

WHO A COMMIT FROM THIS LOOP IS SIGNED BY. It is signed by a key that is not the
operator's (#171). The operator's key lives on a YubiKey; while its touch policy
reads `UIF Sign=off`, anything on the box that reaches `git commit` signs as a
person with no physical act, so the signature asserts nothing about presence.
The loop therefore carries its own on-disk key with its own uid, forced through
`GIT_CONFIG_*` on this process only -- the operator's interactive git is never
reconfigured. Two things follow, and the second is the point:

  - A reader can tell the two actors apart in `git log --show-signature`, by
    key and by author, without trusting anything the loop says about itself.
  - The operator's key is now free to require a touch. Once `UIF Sign=on`, that
    signature means a human was physically there, which is the only claim a
    signature was ever making.

Every commit also carries an `Unattended-Run:` trailer holding the run id that
`.agent-yield/unattended.jsonl` is keyed by, so a commit resolves to the run
that made it, its cost and its brief. Trailers sit inside the commit object, so
the signature covers them. After the run, the commits it made are checked for
both the key and the trailer, and a commit missing either is reported.

No key configured means no commits. The runner says so and leaves the work in
the tree rather than signing as whoever the box's git config names.
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
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agent_yield.state import anchored, project_root  # noqa: E402

STOP_FILE = Path(".agent-yield/STOP")
LOCK_FILE = Path(".agent-yield/unattended.lock")
LOG_FILE = Path(".agent-yield/unattended.jsonl")

PICKER = Path(__file__).resolve().parent / "pick-issue.py"

# #171. The fingerprint is machine state -- a key on this disk, named nowhere in
# the repository -- so it arrives by environment, set on the scheduled task and
# rendered per machine like the hooks are. A clone that sets neither still runs;
# it just does not commit.
SIGNING_KEY_ENV = "AGENT_YIELD_SIGNING_KEY"
SIGNING_EMAIL_ENV = "AGENT_YIELD_SIGNING_EMAIL"
SIGNING_NAME = "agent-yield unattended"

# The join between a commit and the row that priced the run that made it.
TRAILER = "Unattended-Run"

# A key that expires mid-loop fails at 03:00 into a log nobody reads, so the
# refusal happens early and by name. Two weeks is enough notice to renew a key
# by hand on a machine the operator visits daily.
EXPIRY_WARNING_DAYS = 14

# Keyed the same way `pick-issue.py` keys it, and imported from nowhere because
# duplicating two entries is cheaper than a scripts package. A platform that is
# neither gets None and claims nothing.
MACHINE_LABELS = {"Windows": "windows", "Darwin": "macos"}

# The picker's first line is `#113 title...`. Parsed rather than re-derived, so
# there is one implementation of eligibility and this is not a second opinion.
PICKED = re.compile(r"^#(\d+)\s+(.*)$")

# Enough to read the repo, change it, and run its own test file. Not enough to
# A denylist, which is the weaker shape, and it is forced rather than chosen.
#
# This was an allowlist until 2026-08-30. It did nothing. Four measured arms on
# #176: `--allowed-tools Read` still ran Bash under `acceptEdits` AND under
# `default`, with `permission_denials` empty both times -- the flag ADDS
# permissions and never subtracts them. The first unattended run made five Bash
# calls and two PowerShell calls outside a list that named neither, and nothing
# denied anything.
#
# `--disallowed-tools` does work, takes the same `Tool(pattern*)` syntax, and
# populates `permission_denials`. So the guard is enumerate-the-bad, with the
# known weakness that anything not enumerated is permitted. The stronger form
# is a `permissions.deny` block in `.claude/settings.template.json` that an
# unattended run cannot widen; #176 holds that.
#
# Two rules for editing this list. Nothing here may be the only thing standing
# between the loop and a mistake that costs money or leaves the machine -- push,
# publish, install, network. And every entry is a line the brief should never
# have led the run toward in the first place, so a non-empty `permission_denials`
# in the log is a finding about the brief, not only about the guard.
DISALLOWED_TOOLS = ",".join((
    # Leaving the machine.
    "Bash(git push*)", "Bash(gh pr*)", "Bash(gh release*)", "Bash(gh repo*)",
    "Bash(curl*)", "Bash(wget*)", "Bash(scp*)", "Bash(ssh*)",
    "WebFetch", "WebSearch",
    # Signing as the operator with no physical act. #171 holds the decision;
    # until it is made the runner's own brief forbids this and so does this.
    "Bash(git commit*)", "Bash(git tag*)",   # see disallowed_tools()
    # Changing what the next run is, or what it runs on.
    "Bash(pip install*)", "Bash(npm install*)", "Bash(schtasks*)",
    "Bash(Register-ScheduledTask*)",
    "Edit(.claude/**)", "Write(.claude/**)",
    "Edit(//c/Users/ewehm/.claude/**)", "Write(//c/Users/ewehm/.claude/**)",
    # Rewriting history, or the guard that stopped the last run.
    "Bash(git reset --hard*)", "Bash(git checkout --*)", "Bash(git clean*)",
    "Write(.agent-yield/STOP)", "Edit(.agent-yield/STOP)",
))

def disallowed_tools(may_commit: bool) -> str:
    """The denylist for one run. `git commit` leaves it only when signing works.

    Dropping an entry from a denylist is the dangerous direction, so it is done
    in one named place against one condition: a resolved signing identity. With
    no key the loop cannot commit as itself, and committing as whoever the box's
    git config names is the thing #171 is about -- so the entry stays and the
    brief tells the run to leave its work in the tree.

    `git tag` never comes out. Nothing in the loop's remit tags a release.
    """
    if not may_commit:
        return DISALLOWED_TOOLS
    return ",".join(t for t in DISALLOWED_TOOLS.split(",")
                    if t != "Bash(git commit*)")


# --- signing: who the loop is, and how a commit resolves to a run (#171) ---

def _gpg() -> str:
    """The gpg git itself would use, so the expiry check reads the same keyring."""
    out = subprocess.run(["git", "config", "--get", "gpg.program"],
                         capture_output=True, text=True,
                         encoding="utf-8", errors="replace")
    return out.stdout.strip() or "gpg"


def key_expiry(fingerprint: str, gpg: str | None = None) -> datetime | None:
    """When this key expires, or None for no expiry and for no such key.

    Colon format because the human-readable listing is localised and the field
    order is not promised. On a `pub` record field 7 is the expiry as a unix
    timestamp, empty when the key does not expire.
    """
    out = subprocess.run([gpg or _gpg(), "--with-colons", "--list-keys", fingerprint],
                         capture_output=True, text=True,
                         encoding="utf-8", errors="replace")
    if out.returncode != 0:
        return None
    for line in out.stdout.splitlines():
        parts = line.split(":")
        if parts and parts[0] == "pub":
            stamp = parts[6] if len(parts) > 6 else ""
            if stamp.isdigit():
                return datetime.fromtimestamp(int(stamp), tz=timezone.utc)
            return None
    return None


def signing_identity(key: str | None, email: str | None) -> tuple[dict | None, str]:
    """Resolve the loop's identity, or explain in one line why there is none.

    Returns (identity, note). A None identity is not an error: the run proceeds
    without committing, which is the pre-#171 behaviour and is what any clone
    that has not been given a key should do.
    """
    if not key:
        return None, (f"not committing: no {SIGNING_KEY_ENV}. Commits from this "
                      "loop are signed by their own key, never the operator's (#171).")
    expires = key_expiry(key)
    if expires is not None:
        # Rounded up, not truncated. `timedelta.days` floors, so a key with
        # 23 hours left reports 0 and reads as expiring today when it expires
        # tomorrow. Erring long on the notice is the harmless direction.
        seconds = (expires - now()).total_seconds()
        left = -int(-seconds // 86400)
        if left < 0:
            return None, (f"not committing: signing key {key[-16:]} expired "
                          f"{expires:%Y-%m-%d}. Renew it, or the loop signs nothing.")
        if left <= EXPIRY_WARNING_DAYS:
            return ({"key": key, "email": email, "expires": expires.isoformat()},
                    f"signing key {key[-16:]} expires in {left} day(s), "
                    f"{expires:%Y-%m-%d}. Renew it before it stops the loop.")
    return {"key": key, "email": email,
            "expires": expires.isoformat() if expires else None}, ""


def signing_env(identity: dict, base: dict | None = None) -> dict:
    """`GIT_CONFIG_*` for the child only, so no config file is touched.

    Numbered git config overrides apply to every git invocation in the process
    tree and nowhere else. Writing `user.signingkey` into `.git/config` instead
    would reconfigure the operator's own commits in this clone, which is a
    worse bug than the one being fixed.
    """
    env = dict(os.environ if base is None else base)
    pairs = [("user.signingkey", identity["key"]), ("commit.gpgsign", "true")]
    env["GIT_CONFIG_COUNT"] = str(len(pairs))
    for i, (k, v) in enumerate(pairs):
        env[f"GIT_CONFIG_KEY_{i}"], env[f"GIT_CONFIG_VALUE_{i}"] = k, v
    if identity.get("email"):
        for role in ("AUTHOR", "COMMITTER"):
            env[f"GIT_{role}_NAME"] = SIGNING_NAME
            env[f"GIT_{role}_EMAIL"] = identity["email"]
    return env


def refs_now(root: Path) -> set[str]:
    """Every commit reachable from any ref, as the before-picture of a run."""
    out = subprocess.run(["git", "rev-list", "--all"], cwd=root,
                         capture_output=True, text=True,
                         encoding="utf-8", errors="replace")
    return set(out.stdout.split()) if out.returncode == 0 else set()


def audit_commits(root: Path, before: set[str], identity: dict | None,
                  run_id: str) -> tuple[list[str], list[str]]:
    """(shas the run added, complaints about each).

    Checked after the fact rather than trusted. Everything that enforces this
    -- the environment, the denylist, the brief -- is something a run could
    step around without meaning to, and a commit is only evidence of who made
    it if somebody looks. `%G?` is `G` for a good signature and `U` for good
    but untrusted, which is what an unattended key with no ownertrust returns.
    """
    added = sorted(refs_now(root) - before)
    # `%B`, not `%(trailers:key=...)`. Git's trailer parser reads only the final
    # paragraph, and the brief also asks for `Closes #N`, which has no colon and
    # so is not trailer-shaped -- it ends the block and pushes `Unattended-Run:`
    # into a paragraph git ignores. Measured on a321c43: the line is in the
    # message and `%(trailers)` returns empty. Every unattended commit would
    # have been reported unattributed, and a check that always complains is a
    # check nobody reads.
    fmt = "%G?%x09%GK%x09%B"
    problems: list[str] = []
    for sha in added:
        out = subprocess.run(["git", "show", "--no-patch", "--format=" + fmt, sha],
                             cwd=root, capture_output=True, text=True,
                             encoding="utf-8", errors="replace")
        fields = out.stdout.split("\t", 2)
        status = fields[0].strip() if fields else ""
        key = fields[1].strip() if len(fields) > 1 else ""
        message = fields[2] if len(fields) > 2 else ""
        if identity is None:
            problems.append(f"{sha[:7]} was committed by a run that had no "
                            "signing identity and was told not to commit")
            continue
        if status not in ("G", "U"):
            problems.append(f"{sha[:7]} is not signed ({status or 'no signature'})")
        elif key and not identity["key"].endswith(key):
            problems.append(f"{sha[:7]} is signed by {key}, which is not the "
                            "loop's key -- read it before trusting the author")
        if f"{TRAILER}: {run_id}" not in message:
            problems.append(f"{sha[:7]} carries no `{TRAILER}: {run_id}` trailer, "
                            "so it does not resolve to a priced run")
    return added, problems


# Numbers that appear in prose the run added, which #175 exists because of.
# No trailing \b: the figures that went wrong were written `62.1ms` and
# `156.8ms`, and a word boundary after the last digit does not exist there.
# Thousands separators are part of the number because `docs/style.md` requires
# them -- `249,257`, never "about a quarter million" -- so `3,232` is one
# figure and not two.
FIGURE = re.compile(r"\b\d[\d,]*\.\d+|\b\d[\d,]*\b")
YEAR = re.compile(r"^(?:19|20)\d\d$")
PROSE_SUFFIXES = (".md", ".html", ".txt", ".rst")


def _is_claim(text: str) -> bool:
    """Would a reader take this as a measurement rather than a count of two?

    A decimal, a thousands separator, or three or more digits. Years are
    excluded by shape: `2026` is a date in every case that matters here, and a
    list a reviewer stops reading is worse than one figure fewer in it.
    """
    if YEAR.match(text):
        return False
    return "." in text or "," in text or len(text) >= 3


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


def build_brief(number: int, title: str, body: str, may_commit: bool,
                run_id: str = "") -> str:
    """The dispatch brief, carrying section 3's contract in as many words."""
    ending = (
        f"Commit on a branch named `unattended/{number}`, one commit, message "
        f"ending `Closes #{number}`, and a last line reading exactly "
        f"`{TRAILER}: {run_id}` -- it is what resolves this commit to the run "
        f"that priced it, and a commit without it is reported as unattributed. "
        f"Do not push. Do not touch `main`. The signing key is already set for "
        f"you and is not the operator's; do not pass `-S`, `--no-gpg-sign` or "
        f"any `-c user.*` of your own (#171)."
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
- **Every number you write down has to come from a command you ran in this
  session.** If the task wants a measured figure, run the thing that measures
  it and quote its output. If you cannot run it, write that the figure is
  unmeasured and name the command someone should run. A plausible number is
  worse than a missing one here: this repository's entire claim is the
  difference between measured and chosen, and prose that says "this is
  measured" about a figure you produced from context is the one defect that
  cannot be caught by reading it. A run that invents a figure has failed even
  if everything else in it is correct.
- {ending}
- Finish by printing: the files you changed, the exact pytest command you ran,
  and its final summary line. If you did not run it, say that instead of
  implying you did.
"""


def run_claude(brief: str, cwd: Path, permission_mode: str, timeout: int,
               claude: str, denied: str = DISALLOWED_TOOLS,
               env: dict | None = None) -> dict:
    """Invoke `claude -p` and return its JSON result, or a shaped failure."""
    cmd = [claude, "-p", brief, "--output-format", "json",
           "--permission-mode", permission_mode,
           "--disallowed-tools", denied]
    started = time.monotonic()
    elapsed = lambda: int((time.monotonic() - started) * 1000)  # noqa: E731
    try:
        out = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                             timeout=timeout, env=env)
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


def figures_added_to_prose(root: Path) -> list[str]:
    """Numbers the run introduced into prose files, newest diff only.

    #175 is why this exists. The first unattended run wrote five hook timings
    into an ADR as measured, derived a bold 40% cross-machine claim from them,
    and added the sentence `docs/style.md` asks for -- "the 62.1ms is measured,
    the choice is chosen" -- around numbers that were never measured. Only one
    of the six came from anywhere real. The prose passed the style guide, which
    is the problem: the guide tests fluency, and fluency is free.

    This does not judge whether a figure is true. Nothing here can. It lists
    what a reviewer has to check, so that checking is not contingent on someone
    noticing there was something to check.
    """
    out = subprocess.run(["git", "diff", "-U0"], cwd=root,
                         capture_output=True, text=True)
    if out.returncode != 0:
        return []
    found: list[str] = []
    interesting = False
    for line in out.stdout.splitlines():
        if line.startswith("+++ "):
            interesting = line.rstrip().endswith(PROSE_SUFFIXES)
        elif interesting and line.startswith("+"):
            found.extend(f for f in FIGURE.findall(line) if _is_claim(f))
    seen: dict[str, None] = {}
    for figure in found:
        seen.setdefault(figure, None)
    return list(seen)


def summarise(result: dict) -> dict:
    """The figures worth keeping from a `claude -p` JSON result."""
    usage = result.get("usage") or {}
    denials = result.get("permission_denials") or []
    return {
        # Non-empty exactly when the brief walked the run into the denylist,
        # which is a finding about the brief as much as about the guard.
        "permission_denials": [d.get("tool_name") for d in denials
                               if isinstance(d, dict)],
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
    ap.add_argument("--no-commit", dest="commit", action="store_false",
                    help="leave the work in the tree for a human to commit")
    ap.add_argument("--commit", dest="commit", action="store_true",
                    help="commit on a branch, signed by the loop's own key (default)")
    ap.set_defaults(commit=True)
    ap.add_argument("--signing-key", default=os.environ.get(SIGNING_KEY_ENV),
                    help=f"fingerprint of the loop's own key (default: ${SIGNING_KEY_ENV})")
    ap.add_argument("--signing-email", default=os.environ.get(SIGNING_EMAIL_ENV),
                    help=f"author/committer address for the loop (default: ${SIGNING_EMAIL_ENV})")
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

    identity, note = (signing_identity(args.signing_key, args.signing_email)
                      if args.commit else (None, ""))
    if note:
        print(note)
    may_commit = args.commit and identity is not None
    run_id = uuid.uuid4().hex[:12]
    brief = build_brief(number, title, issue_body(number), may_commit, run_id)

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
    if may_commit:
        print(f"run {run_id}, committing as {SIGNING_NAME} "
              f"<{identity['email']}> signed by {identity['key'][-16:]}")
    before = refs_now(root)
    try:
        result = run_claude(brief, root, args.permission_mode, args.timeout,
                            args.claude, disallowed_tools(may_commit),
                            signing_env(identity) if may_commit else None)
    finally:
        lock.unlink(missing_ok=True)

    committed, complaints = audit_commits(root, before, identity, run_id)
    figures = figures_added_to_prose(root)
    row = {"started_at": started_at, "finished_at": now().isoformat(),
           "issue": number, "title": title, "committed": may_commit,
           "run_id": run_id, "signing_key": identity["key"] if identity else None,
           "commits": committed, "commit_problems": complaints,
           "permission_mode": args.permission_mode, "claim_note": claim_note,
           "brief_chars": len(brief), "figures_added": figures,
           **summarise(result)}
    path = log_row(root, row)

    if row["is_error"]:
        print(f"run failed: {row['error']}")
        print(f"logged to {path}")
        return 1
    cost = row["total_cost_usd"]
    priced = f", ${cost:.4f}" if isinstance(cost, (int, float)) else ""
    print(f"done in {row['num_turns']} turns{priced}")
    if committed:
        print(f"{len(committed)} commit(s): {', '.join(s[:7] for s in committed)}")
    for complaint in complaints:
        print(f"COMMIT PROBLEM: {complaint}")
    if row["permission_denials"]:
        print(f"denied: {', '.join(row['permission_denials'])} -- "
              "the brief led it somewhere the guard refused")
    if figures:
        print(f"{len(figures)} figure(s) added to prose, unverified: "
              f"{', '.join(figures[:12])}")
        print("Check each against the command that produced it before "
              "committing (#175).")
    print(f"logged to {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
