"""The dispatch-length audit: what each dispatch was briefed to do, and what it cost.

Issue #18 Part C. Two rubrics need scoring and neither could be, because the
two halves of a dispatch live in different files:

- **§11's length rule** -- cost is superlinear in the length of one unit of
  work (agents fit `calls^1.54`), so cap a dispatch at ~10 calls and split.
  **The "and split" half was retracted 2026-08-25 by §11.1** -- splitting the
  same task cost 54% more. The cap is now a length flag only.
  The call count is only in the *child's* transcript.
- **§12's brief rubric** -- three markers visible in the dispatch prompt. The
  prompt is only in the *parent's* transcript.

Joining them is what makes either rubric scorable, and it is also the thing
that could not be done before, because **hooks do not fire inside a subagent**:
`gate` sees the prompt and never learns what it cost. This is the post-hoc
half, and it is the only half that can see part (b) of the brief at all.

## The join is a heuristic, and it is labelled one

There is **no structural link** from a dispatch to the agent it started.
Measured on this corpus, not assumed:

- the parent's `tool_use` block carries an `id` (`toolu_...`) that appears
  nowhere in the child's transcript;
- the child's first record has **`parentUuid: null`** -- it is a root, not a
  continuation of the line that dispatched it;
- the child does carry `sessionId` and `attributionAgent` (the subagent type).

So the join is: **same session, same subagent type, child's first record
within `MAX_JOIN_LAG_SECONDS` after the dispatch, nearest first.** On the 12
dispatches and 12 agent transcripts on record the lag was 1.4-1.6s and the
match was 1:1 in both sessions (7/7 and 5/5). That is a good join and it is
still a guess: it will mismatch if two dispatches of the same type are issued
within the lag window. When it cannot match, it reports `unlinked` rather
than picking one -- a wrong join here would attribute one agent's cost to
another's brief, which is worse than a gap.

`agent-yield agents --unlinked` shows what did not join, because a join whose
failures are invisible is indistinguishable from one that always works. That
is the same lesson as issue #29, one file over.

## Exemptions

`Explore` and `Plan` dispatches are *supposed* to lack the brief markers --
exploring is what they are for. They are excluded from the brief scoring and
from the pass/fail counts, and shown separately, because folding them in
manufactures a population of "failed briefs" that are nothing of the kind.
This is the same `BRIEF_EXEMPT_TYPES` `gate` uses, imported rather than
copied, so the pre-dispatch warning and the post-hoc audit cannot drift.
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass
from pathlib import Path

from .discovery import find_transcripts, main_transcript_dir, subagent_transcript_dirs
from .gate import BRIEF_EXEMPT_TYPES, DispatchRequest, missing_markers
from .records import dedup, parse_line
from .usage import Usage

__all__ = [
    "MAX_JOIN_LAG_SECONDS",
    "DISPATCH_CALL_CAP",
    "Dispatch",
    "AgentRun",
    "Audit",
    "read_dispatches",
    "read_agent_runs",
    "join",
    "render",
]

DISPATCH_TOOLS = ("Agent", "Task")

# Measured 1.4-1.6s across 12 dispatches. The window is wide enough to absorb
# a slow start and narrow enough that two same-type dispatches would have to
# be issued within two minutes to collide -- at which point `join` reports
# both as ambiguous rather than guessing.
MAX_JOIN_LAG_SECONDS = 120.0

# RETRACTED JUSTIFICATION, 2026-08-25. This constant used to cite §11's
# "one 27-call agent cost 1,879,466 against 840,036 for three 9-call agents".
# That 840,036 was arithmetic on a split nobody ran. §11.1 ran it: the same
# task as three agents cost 385,109 against 249,944 as one -- splitting cost
# 54% MORE, because each extra agent pays ~19,800 tokens of re-entry before it
# reads anything and a split does not divide the call count (5 calls became 12).
#
# The cap stays, with a smaller claim: it flags long dispatches, which are
# where the money is concentrated, and says nothing about what splitting one
# would save. Soft by design -- this module reports, it refuses nothing.
DISPATCH_CALL_CAP = 10


@dataclass(frozen=True)
class Dispatch:
    """One `Agent`/`Task` tool_use, read from the parent's transcript."""

    session_id: str | None
    tool_use_id: str | None
    timestamp: dt.datetime | None
    subagent_type: str | None
    model: str | None
    description: str | None
    prompt: str | None
    cwd: str | None = None

    @property
    def project(self) -> str:
        """The last path segment of the dispatching session's cwd.

        Not decoration. The first run of this audit pooled every project on
        the machine and reported briefed dispatches at 6 calls against 57 --
        a 9.5x effect that was entirely project: all 61 long un-briefed
        dispatches came from one repo's audit fleet, and all 4 briefed ones
        from another repo. Within a single project the difference vanished
        (6.0 vs 6.5). A pooled comparison across projects is a confound, so
        this field exists to make refusing one possible.
        """
        if not self.cwd:
            return "?"
        return self.cwd.rstrip("/").rsplit("/", 1)[-1] or "?"

    @property
    def exempt(self) -> bool:
        return (self.subagent_type or "").lower() in BRIEF_EXEMPT_TYPES

    @property
    def missing(self) -> tuple[str, ...]:
        return missing_markers(
            DispatchRequest(
                subagent_type=self.subagent_type,
                model=self.model,
                description=self.description,
                prompt=self.prompt,
            )
        )


@dataclass(frozen=True)
class AgentRun:
    """One subagent transcript: what the child actually did."""

    session_id: str | None
    agent_id: str | None
    started: dt.datetime | None
    subagent_type: str | None
    calls: int
    total: Usage
    context: int
    incomplete: int = 0
    """Calls whose terminal record was never written.

    `total.output_tokens` is a lower bound by exactly these calls' worth, so
    anything pricing a run must say so rather than present the figure as
    exact. See `pricing.price_records`.
    """

    @property
    def context_per_call(self) -> float | None:
        return self.context / self.calls if self.calls else None


@dataclass(frozen=True)
class Audit:
    """A dispatch joined to what it cost, or to nothing."""

    dispatch: Dispatch
    run: AgentRun | None

    @property
    def over_cap(self) -> bool:
        return self.run is not None and self.run.calls > DISPATCH_CALL_CAP

    @property
    def briefed(self) -> bool:
        """All three visible markers present. Meaningless for exempt types."""
        return not self.dispatch.missing


def _timestamp(raw: object) -> dt.datetime | None:
    if not isinstance(raw, str) or not raw:
        return None
    try:
        parsed = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _iter_json(path: Path):
    try:
        with path.open(encoding="utf-8", errors="replace") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except (ValueError, RecursionError):
                    continue
                if isinstance(payload, dict):
                    yield payload
    except OSError:
        return


def read_dispatches(paths: list[Path]) -> list[Dispatch]:
    """Every `Agent`/`Task` tool_use in the given main transcripts."""
    out: list[Dispatch] = []
    for path in paths:
        for payload in _iter_json(path):
            message = payload.get("message")
            if not isinstance(message, dict):
                continue
            content = message.get("content")
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") != "tool_use":
                    continue
                if block.get("name") not in DISPATCH_TOOLS:
                    continue
                tool_input = block.get("input")
                if not isinstance(tool_input, dict):
                    tool_input = {}
                out.append(Dispatch(
                    session_id=payload.get("sessionId") or payload.get("session_id"),
                    tool_use_id=block.get("id"),
                    timestamp=_timestamp(payload.get("timestamp")),
                    subagent_type=tool_input.get("subagent_type"),
                    model=tool_input.get("model"),
                    description=tool_input.get("description"),
                    prompt=tool_input.get("prompt"),
                    cwd=payload.get("cwd"),
                ))
    out.sort(key=lambda d: (d.session_id or "", d.timestamp or dt.datetime.min.replace(tzinfo=dt.timezone.utc)))
    return out


def read_agent_runs(paths: list[Path]) -> list[AgentRun]:
    """One run per subagent transcript, deduped by `records.dedup`.

    IT USED TO SAY "deduped the way `ingest` dedups" and hold its own copy of
    the loop. #53 fixed the rule in `ingest`; this copy kept the FIRST record
    of each group for another day, undercounting subagent output tokens 8.7x
    across 163 transcripts here -- 388,893 against 3,395,515 -- with the call
    count identical, because only `output_tokens` differs between the copies.
    That is #53's signature exactly, one file over, and #61 is why there is
    now one implementation instead of a sentence claiming there is.


    A `tasks/*.output` file is not necessarily a transcript: on this corpus
    only 12 of 15 parsed as JSONL, the rest being plain-text write-ups an
    agent was asked to produce (§8). Those yield no records and are skipped
    rather than counted as zero-call runs.
    """
    runs: list[AgentRun] = []
    for path in paths:
        agent_id: str | None = None
        session_id: str | None = None
        subagent_type: str | None = None
        started: dt.datetime | None = None
        parsed: list = []
        for payload in _iter_json(path):
            if agent_id is None:
                agent_id = payload.get("agentId")
            if session_id is None:
                session_id = payload.get("sessionId")
            if subagent_type is None and payload.get("attributionAgent"):
                subagent_type = payload.get("attributionAgent")
            stamp = _timestamp(payload.get("timestamp"))
            if stamp is not None and (started is None or stamp < started):
                started = stamp
            record = parse_line(json.dumps(payload))
            if record is not None:
                parsed.append(record)

        records = dedup(parsed)
        calls = len(records)
        total = Usage.zero()
        context = 0
        for record in records:
            total = total + record.usage
            context += (
                record.usage.input_tokens
                + record.usage.cache_read_tokens
                + record.usage.cache_creation_tokens
            )

        if calls == 0:
            continue
        runs.append(AgentRun(
            session_id=session_id,
            agent_id=agent_id,
            started=started,
            subagent_type=subagent_type,
            calls=calls,
            total=total,
            context=context,
            incomplete=sum(1 for r in records if r.incomplete),
        ))
    runs.sort(key=lambda r: (r.session_id or "", r.started or dt.datetime.min.replace(tzinfo=dt.timezone.utc)))
    return runs


def join(
    dispatches: list[Dispatch],
    runs: list[AgentRun],
    max_lag_seconds: float = MAX_JOIN_LAG_SECONDS,
) -> tuple[list[Audit], list[AgentRun]]:
    """Match each dispatch to the run it most likely started.

    Same session, same subagent type, child starting within `max_lag_seconds`
    *after* the dispatch, nearest first. Each run is claimed at most once.
    Returns the audits and the runs nothing claimed -- see the module
    docstring on why the failures are returned rather than swallowed.
    """
    unclaimed = list(runs)
    audits: list[Audit] = []
    for dispatch in dispatches:
        best: AgentRun | None = None
        best_lag: float | None = None
        for run in unclaimed:
            if run.session_id != dispatch.session_id:
                continue
            if (run.subagent_type or "") != (dispatch.subagent_type or ""):
                continue
            if dispatch.timestamp is None or run.started is None:
                continue
            lag = (run.started - dispatch.timestamp).total_seconds()
            if lag < 0 or lag > max_lag_seconds:
                continue
            if best_lag is None or lag < best_lag:
                best, best_lag = run, lag
        if best is not None:
            unclaimed.remove(best)
        audits.append(Audit(dispatch=dispatch, run=best))
    return audits, unclaimed


def _num(value: float | None) -> str:
    return "-" if value is None else f"{round(value):,}"


def render(
    audits: list[Audit],
    orphans: list[AgentRun],
    show_unlinked: bool = False,
) -> str:
    """The audit, as the two rubrics it exists to score."""
    lines: list[str] = []
    scored = [a for a in audits if not a.dispatch.exempt]
    exempt = [a for a in audits if a.dispatch.exempt]
    linked = [a for a in scored if a.run is not None]

    lines.append(f"{len(audits)} dispatch(es), {len(linked)} joined to a transcript")
    if exempt:
        types = sorted({a.dispatch.subagent_type or "?" for a in exempt})
        lines.append(
            f"  {len(exempt)} exempt ({', '.join(types)}) -- exploratory work is "
            "supposed to lack the markers"
        )
    lines.append("")

    header = f"  {'type':16} {'calls':>6} {'ctx/call':>10} {'total':>12}  brief"
    lines.append(header)
    for audit in scored:
        d, r = audit.dispatch, audit.run
        calls = f"{r.calls}" if r else "-"
        cap = "!" if audit.over_cap else " "
        ctx = _num(r.context_per_call) if r else "-"
        tot = _num(r.total.total) if r else "unlinked"
        brief = "ok" if audit.briefed else "missing " + ", ".join(d.missing)
        lines.append(
            f"  {(d.subagent_type or '?')[:16]:16} {calls:>5}{cap} {ctx:>10} "
            f"{tot:>12}  {brief}"
        )
        if d.description:
            lines.append(f"      {d.description[:68]}")

    if linked:
        over = [a for a in linked if a.over_cap]
        lines.append("")
        lines.append(
            f"§11 length: {len(over)}/{len(linked)} over the {DISPATCH_CALL_CAP}-call "
            f"cap (max {max(a.run.calls for a in linked)}) -- a length flag, not "
            f"a saving: see §11.1, where splitting cost 54% more"
        )
        briefed = [a for a in linked if a.briefed]
        lines.append(
            f"§12 brief:  {len(briefed)}/{len(linked)} carried all three markers"
        )
        lines.extend(_brief_effect(linked))

    if orphans:
        lines.append("")
        lines.append(
            f"{len(orphans)} agent transcript(s) matched no dispatch "
            "-- the join is a heuristic (see module docstring)"
        )
        if show_unlinked:
            for run in orphans:
                lines.append(
                    f"  {(run.agent_id or '?')[:18]:18} {run.calls:>4} calls  "
                    f"{_num(run.context_per_call):>10} ctx/call  "
                    f"session {(run.session_id or '?')[:8]}"
                )
    return "\n".join(lines)


def _brief_effect(linked: list[Audit]) -> list[str]:
    """Does the brief predict the length? Only ask within one project.

    THE FIRST RUN OF THIS AUDIT GOT THIS WRONG, and the wrong answer was
    published before anyone checked. Pooled over every project on the
    machine it reported briefed dispatches at a median 6 calls against 57
    un-briefed -- 9.5x, and entirely spurious. All 61 long un-briefed
    dispatches were one repo's audit fleet; all 4 briefed ones were another
    repo. Within a single project the effect vanished: 6.0 against 6.5, with
    the briefed dispatches carrying MORE context.

    So the pooled comparison is withheld whenever the two groups do not
    share a project, and the per-project rows are printed instead. A tool
    that reports a headline it cannot support is worse than one that
    reports nothing: the number gets quoted, and this one was, in two
    issue comments, within the hour.
    """
    briefed = [a for a in linked if a.briefed]
    unbriefed = [a for a in linked if not a.briefed]
    if not briefed or not unbriefed:
        return []

    out = ["", "brief vs length, per project (pooling across projects is a confound):"]
    projects = sorted({a.dispatch.project for a in linked})
    comparable = 0
    for project in projects:
        here = [a for a in linked if a.dispatch.project == project]
        b = [a for a in here if a.briefed]
        u = [a for a in here if not a.briefed]
        if b and u:
            comparable += 1
            out.append(
                f"  {project[:24]:24} briefed n={len(b):<3} median "
                f"{_median([a.run.calls for a in b]):>3} calls   "
                f"un-briefed n={len(u):<3} median "
                f"{_median([a.run.calls for a in u]):>3} calls"
            )
        else:
            side = "briefed" if b else "un-briefed"
            out.append(
                f"  {project[:24]:24} {len(here)} dispatch(es), all {side} "
                "-- no within-project comparison"
            )
    if comparable == 0:
        out.append(
            "  no project has both groups, so there is NO comparison here "
            "-- any pooled number would be measuring the project, not the brief"
        )
    return out


def _median(values: list[int]) -> int:
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return round((ordered[mid - 1] + ordered[mid]) / 2)


def audit(
    main_paths: list[Path] | None = None,
    agent_paths: list[Path] | None = None,
) -> tuple[list[Audit], list[AgentRun]]:
    """Read both sides from their default locations and join them."""
    if main_paths is None:
        main_paths = find_transcripts([main_transcript_dir()])
    if agent_paths is None:
        agent_paths = find_transcripts(subagent_transcript_dirs())
    return join(read_dispatches(main_paths), read_agent_runs(agent_paths))
