#!/usr/bin/env sh
# Does this machine still carry the boundary deadlock closed by #130?
#
# The hooks are rendered per machine and `.claude/settings.json` is not
# tracked, so no other box can answer this by reading the repo. Run it here.
#
#   sh scripts/boundary-audit.sh [--root DIR]
#
# Exit 0 clean, 1 action needed, 2 the audit could not run.

set -u
ROOT=.
while [ $# -gt 0 ]; do
  case $1 in
    --root) ROOT=${2:-}; shift 2 ;;
    -h|--help) sed -n '2,10p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done
cd "$ROOT" 2>/dev/null || { echo "no such root: $ROOT" >&2; exit 2; }

# Bare `python` has no agent_yield and PATH is rarely the venv, so resolve
# both from the project first. Getting this wrong makes check 1 report the
# defect on a machine that is already fixed.
PY=
AY=
for c in .venv/bin/python .venv/Scripts/python.exe; do
  [ -x "$c" ] && { PY=$c; break; }
done
for c in .venv/bin/agent-yield .venv/Scripts/agent-yield.exe; do
  [ -x "$c" ] && { AY=$c; break; }
done
[ -n "$PY" ] || PY=$(command -v python3 || command -v python || echo "")
[ -n "$AY" ] || AY=$(command -v agent-yield || echo "")

LIVE=.claude/settings.json
PROBE=.agent-yield/boundary-probe.jsonl
status=0
note() { printf '%s\n' "$*"; }
fail() { printf 'ACTION  %s\n' "$*"; status=1; }
ok()   { printf 'ok      %s\n' "$*"; }

note "machine: $(uname -s 2>/dev/null || echo unknown) $(uname -m 2>/dev/null || true)"
note "repo:    $(git rev-parse --short HEAD 2>/dev/null || echo 'not a git repo')"
note ""

# 1. Does the live hook enforce, and does the installed code carry the fix?
if [ ! -f "$LIVE" ]; then
  fail "$LIVE is missing -- run 'agent-yield harness --install'"
elif grep -q 'boundary --enforce' "$LIVE"; then
  if [ -z "$PY" ]; then
    fail "no interpreter found -- cannot tell whether the fix is installed"
  elif "$PY" -c 'import agent_yield.boundary as b; raise SystemExit(0 if hasattr(b, "REFUSAL_SPENT_PATH") else 1)' 2>/dev/null; then
    ok "boundary --enforce is live, and the installed code has the one-shot fix"
  else
    fail "boundary --enforce is live WITHOUT the #130 fix: every prompt is"
    fail "  refused once the boundary trips, including 'agent-yield handoff'."
    fail "  Escapes today: prefix a prompt with '!', set"
    fail "  AGENT_YIELD_BOUNDARY_OVERRIDE=1, or run the handoff in another"
    fail "  terminal. Pull main and reinstall to clear this."
  fi
else
  ok "boundary hook is advisory here, not --enforce"
fi

# 2. Hook drift. --check exits 1 on a difference and names the foreign render.
if [ -n "$AY" ]; then
  if "$AY" harness --check >/dev/null 2>&1; then
    ok "hooks match the template, rendered for this machine"
  else
    fail "harness --check reports drift -- run it directly to see the diff"
  fi
else
  fail "no agent-yield executable found under .venv or on PATH"
fi

# 3. Has this machine actually been refused?
#
# Not from the probe log. `--probe` forces advisory mode (#152), so an
# enforcing hook never wrote a row there and its silence means nothing.
REFUSALS=.agent-yield/boundary-refusals.jsonl
if [ -f "$REFUSALS" ]; then
  n=$(grep -c '"exit_code": 2' "$REFUSALS" 2>/dev/null) || true
  if [ "${n:-0}" -gt 0 ]; then
    fail "$REFUSALS records ${n:-0} real refusal(s) -- read them, each cost a turn"
  else
    ok "$REFUSALS exists and holds no refusals"
  fi
else
  note "note    no refusal log yet; it is created the first time one happens"
fi
if [ -f "$PROBE" ]; then
  probed=$(grep -c '"refusal_probe": true' "$PROBE" 2>/dev/null) || true
  note "note    $PROBE holds ${probed:-0} deliberate measurement(s), and cannot"
  note "        record refusals under --enforce at all -- that is #152"
fi

# 4. The new per-session sentinel must never be committed.
if git check-ignore -q .agent-yield/boundary-refusal-spent 2>/dev/null; then
  ok ".agent-yield/ is ignored, so the refusal sentinel stays out of git"
else
  fail ".agent-yield/ is NOT ignored here -- session state would be committed"
fi

note ""
[ "$status" -eq 0 ] && note "clean" || note "action needed above"
exit "$status"
