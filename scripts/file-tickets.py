#!/usr/bin/env python
"""File a set of dependent tickets to GitHub from one TOML plan.

    python scripts/file-tickets.py plan.toml --dry-run   # what it would file
    python scripts/file-tickets.py plan.toml             # file it

Exit 0 when every ticket exists and every dependency edge is set. Exit 1 when
`gh` fails. Exit 2 when the plan itself is wrong, which is a different kind of
problem and worth a different code: nothing was sent.

WHY THE EDGES ARE SET THROUGH THE API AND NOT WRITTEN IN THE BODY. A "Blocked
by" heading in an issue body is prose. `scripts/pick-issue.py` gates on the
`blockedBy` field GitHub returns, so a set of tickets carrying only the heading
is a set where every ticket is eligible at once. Filing #184 through #190 on
2026-08-30 hit exactly that: seven tickets, six of them blocked in the body,
and the picker reported all seven eligible until the real edges were added --
which would have let an unattended run wire CI to a check nothing had tagged
yet. So this script writes both, from the same field, and the heading is
generated rather than typed. Two copies that can disagree is one copy too many.

WHY IT ADOPTS RATHER THAN REFUSES. A run that dies filing ticket 4 of 7 leaves
three tickets behind, and a script that then refuses to run again because those
titles exist has made the operator finish by hand. Instead an existing title is
adopted: its number is reused for the placeholders and it is not re-created.
That makes the script resumable and makes double-filing impossible for the same
reason. `--strict` restores the refusal for a plan that must be new.

THE PLAN FILE

    repo   = "owner/name"          # optional, defaults to the current remote
    parent = 183                   # optional, rendered as a Parent section
    label  = "ready-for-agent"     # optional, applied to every ticket

    [[ticket]]
    key        = "walk"            # referenced elsewhere as {{walk}}
    title      = "..."
    blocked_by = []                # keys, not numbers
    body       = '''...'''

`{{key}}` anywhere in a body becomes that ticket's issue number once it has
one, so write `#{{walk}}`. `{{parent}}` becomes the parent's number. A body may
only reference a ticket defined above it: tickets are filed in file order, and
a reference to a ticket that does not exist yet cannot be resolved. That rule
also makes a dependency cycle unrepresentable rather than detected.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path

PLACEHOLDER = re.compile(r"\{\{([A-Za-z0-9_.-]+)\}\}")

# The two sections this script owns. An author writing either one by hand gets
# a second source of truth for the same fact, so both are generated and the
# plan carries only the middle of the body.
PARENT_HEADING = "## Parent"
BLOCKED_HEADING = "## Blocked by"
NO_BLOCKERS = "None (can start immediately)."


class PlanError(Exception):
    """The plan is wrong. Nothing has been sent."""


def load_plan(path: Path) -> dict:
    """Parse and validate the plan. Raises PlanError, which exits 2."""
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise PlanError(f"no such plan file: {path}") from None
    except tomllib.TOMLDecodeError as exc:
        raise PlanError(f"{path} is not valid TOML: {exc}") from None

    tickets = data.get("ticket")
    if not isinstance(tickets, list) or not tickets:
        raise PlanError(f"{path} defines no [[ticket]] tables")

    seen: dict[str, int] = {}
    for position, ticket in enumerate(tickets, start=1):
        for field in ("key", "title", "body"):
            value = ticket.get(field)
            if not isinstance(value, str) or not value.strip():
                raise PlanError(f"ticket {position} has no {field}")
        key = ticket["key"]
        if key in seen:
            raise PlanError(f"duplicate key {key!r}: tickets "
                            f"{seen[key]} and {position}")
        blocked = ticket.get("blocked_by", [])
        if not isinstance(blocked, list):
            raise PlanError(f"ticket {key}: blocked_by must be a list of keys")
        for blocker in blocked:
            if blocker not in seen:
                raise PlanError(
                    f"ticket {key} is blocked by {blocker!r}, which is not "
                    "defined above it. Blockers are filed first, so they come "
                    "first in the file.")
        seen[key] = position

    if data.get("parent") is not None and not isinstance(data["parent"], int):
        raise PlanError("parent must be an issue number")
    return data


def render_body(ticket: dict, parent: int | None, resolved: dict[str, int]) -> str:
    """The body as it will be posted: parent, the author's middle, blockers.

    Pure, so the substitution rule is testable without a tracker.
    """
    middle = ticket["body"].strip()
    known = dict(resolved)
    if parent is not None:
        known["parent"] = parent

    def swap(match: re.Match[str]) -> str:
        key = match.group(1)
        return str(known[key]) if key in known else match.group(0)

    middle = PLACEHOLDER.sub(swap, middle)

    parts = []
    if parent is not None:
        parts.append(f"{PARENT_HEADING}\n\n#{parent}")
    parts.append(middle)
    blockers = ticket.get("blocked_by", [])
    if blockers:
        lines = "\n".join(f"- #{resolved[key]}" for key in blockers)
    else:
        lines = f"- {NO_BLOCKERS}"
    parts.append(f"{BLOCKED_HEADING}\n\n{lines}")
    return "\n\n".join(parts) + "\n"


def unresolved(text: str) -> list[str]:
    """Placeholders still standing. Any one of them means do not post."""
    return sorted(set(PLACEHOLDER.findall(text)))


def gh(args: list[str]) -> tuple[int, str, str]:
    out = subprocess.run(["gh", *args], capture_output=True, text=True,
                         encoding="utf-8", errors="replace")
    return out.returncode, out.stdout, out.stderr


def gh_json(args: list[str]):
    code, stdout, stderr = gh(args)
    if code != 0:
        raise RuntimeError(f"gh {' '.join(args[:3])} failed: {stderr.strip()}")
    return json.loads(stdout or "null")


def existing_by_title(repo: str, limit: int = 300) -> dict[str, int]:
    """Every issue title on the tracker, open or closed, to its number."""
    rows = gh_json(["issue", "list", "--repo", repo, "--state", "all",
                    "--limit", str(limit), "--json", "number,title"]) or []
    return {row["title"]: row["number"] for row in rows}


def create_issue(repo: str, title: str, body: str, label: str | None) -> int:
    args = ["issue", "create", "--repo", repo, "--title", title, "--body", body]
    if label:
        args += ["--label", label]
    code, stdout, stderr = gh(args)
    if code != 0:
        raise RuntimeError(f"could not create {title!r}: {stderr.strip()}")
    url = stdout.strip().splitlines()[-1]
    return int(url.rstrip("/").split("/")[-1])


def issue_id(repo: str, number: int) -> int:
    """The database id, which is what the dependencies endpoint takes."""
    return gh_json(["api", f"repos/{repo}/issues/{number}", "--jq", ".id"])


def blockers_now(repo: str, number: int) -> set[int]:
    """Edges already on the issue, so a re-run adds each one at most once."""
    data = gh_json(["issue", "view", str(number), "--repo", repo,
                    "--json", "blockedBy"]) or {}
    nodes = data.get("blockedBy") or {}
    if isinstance(nodes, dict):
        nodes = nodes.get("nodes") or []
    return {node["number"] for node in nodes if isinstance(node, dict)}


def add_dependency(repo: str, number: int, blocker_id: int) -> None:
    code, _, stderr = gh(["api", "--method", "POST",
                          f"repos/{repo}/issues/{number}/dependencies/blocked_by",
                          "-F", f"issue_id={blocker_id}"])
    if code != 0:
        raise RuntimeError(f"could not block #{number}: {stderr.strip()}")


def default_repo() -> str:
    # `--json` without `--jq`: with a jq filter gh prints the bare string
    # `owner/name`, which is not JSON and which `gh_json` cannot parse.
    data = gh_json(["repo", "view", "--json", "nameWithOwner"]) or {}
    return data["nameWithOwner"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("plan", type=Path, help="the TOML plan file")
    parser.add_argument("--repo", help="owner/name, default the current remote")
    parser.add_argument("--label", help="override the plan's label")
    parser.add_argument("--dry-run", action="store_true",
                        help="resolve and validate, send nothing")
    parser.add_argument("--strict", action="store_true",
                        help="refuse if any title already exists")
    args = parser.parse_args(argv)

    try:
        plan = load_plan(args.plan)
    except PlanError as exc:
        print(f"plan refused: {exc}")
        return 2

    tickets = plan["ticket"]
    parent = plan.get("parent")
    label = args.label or plan.get("label")

    try:
        repo = args.repo or plan.get("repo") or default_repo()
        existing = {} if args.dry_run else existing_by_title(repo)
    except RuntimeError as exc:
        print(str(exc))
        return 1

    if args.strict:
        clash = [t["title"] for t in tickets if t["title"] in existing]
        if clash:
            print("refusing: --strict, and these titles already exist")
            for title in clash:
                print(f"  {title}")
            return 1

    resolved: dict[str, int] = {}
    adopted: set[str] = set()
    try:
        for position, ticket in enumerate(tickets, start=1):
            body = render_body(ticket, parent, resolved)
            left = unresolved(body)
            if left:
                print(f"plan refused: ticket {ticket['key']} references "
                      f"{', '.join(left)}, which is not defined above it")
                return 2
            blockers = ", ".join(f"#{resolved[k]}"
                                 for k in ticket.get("blocked_by", []))
            if args.dry_run:
                # Keys, not the placeholder numbers: a dry run has no numbers
                # to report, and printing the sentinel reads as a real edge to
                # issue -1.
                keys = ", ".join(ticket.get("blocked_by", []))
                print(f"[dry] {position}. {ticket['title'][:72]}"
                      f"  <- {keys or 'none'}")
                resolved[ticket["key"]] = -position
                continue
            if ticket["title"] in existing:
                number = existing[ticket["title"]]
                adopted.add(ticket["key"])
                print(f"#{number}  exists, adopted  {ticket['title'][:60]}")
            else:
                number = create_issue(repo, ticket["title"], body, label)
                print(f"#{number}  filed  {ticket['title'][:60]}"
                      f"  <- {blockers or 'none'}")
            resolved[ticket["key"]] = number
    except RuntimeError as exc:
        print(str(exc))
        return 1

    if args.dry_run:
        edges = sum(len(t.get("blocked_by", [])) for t in tickets)
        print(f"[dry] {len(tickets)} ticket(s), {edges} dependency edge(s), "
              "nothing sent")
        return 0

    # Edges last and separately, because a ticket cannot block anything until
    # it has a number, and because a re-run has to be able to repair a set that
    # was filed but never linked.
    added = 0
    try:
        for ticket in tickets:
            blockers = ticket.get("blocked_by", [])
            if not blockers:
                continue
            number = resolved[ticket["key"]]
            have = blockers_now(repo, number)
            for key in blockers:
                blocker = resolved[key]
                if blocker in have:
                    continue
                add_dependency(repo, number, issue_id(repo, blocker))
                print(f"  #{number} blocked by #{blocker}")
                added += 1
    except RuntimeError as exc:
        print(str(exc))
        return 1

    filed = len(tickets) - len(adopted)
    print(f"{filed} filed, {len(adopted)} adopted, {added} edge(s) added")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
