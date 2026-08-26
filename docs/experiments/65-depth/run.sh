#!/usr/bin/env bash
# One run of #65: one arm, at one tool schema, one replicate.
#
#   run.sh packed trimmed 1
#   run.sh split  full    2
#
# THE CORPUS IS REBUILT FOR EVERY RUN, from the pinned sha, with the fourteen
# docstring defects re-seeded. Two reasons and both are bars: the full-schema arm
# holds Edit and Write, so a run must not be able to leave the next one a
# different tree; and a rebuilt corpus makes "the arms did the same work" a fact
# about bytes rather than about ordering.
#
# --allowedTools Bash, both arms: headless, every python invocation returns
#   "This command requires approval" and the per-slice test command cannot run
#   at all. It is a PERMISSION rule, not a schema change -- the tool list the
#   model sees is untouched, which is what keeps the two schemas the only
#   difference between a full run and a trimmed one.
#
# The two schemas are the difference #63 measured at 2.1x in the arrival price:
#   trimmed  five tools removed, exactly as #33 and #47 ran
#   full     nothing removed -- the schema this repo's fleet actually dispatches on
# Nothing else differs. The arm paragraph and the schema are the only two knobs.
set -euo pipefail

ARM="${1:?arm: packed|split}"
SCHEMA="${2:?schema: trimmed|full}"
REP="${3:?replicate: 1|2}"
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../../.." && pwd)"
CORPUS="${CORPUS65:-/private/tmp/claude-501/agent-yield-65-corpus}"

case "$ARM" in
  packed) ARMNUM=1 ;;
  split)  ARMNUM=2 ;;
  *) echo "arm must be packed or split" >&2; exit 2 ;;
esac
case "$SCHEMA" in
  trimmed) SCHNUM=1; EXTRA=(--disallowedTools Edit Write NotebookEdit WebFetch WebSearch) ;;
  full)    SCHNUM=2; EXTRA=() ;;
  *) echo "schema must be trimmed or full" >&2; exit 2 ;;
esac
SID="65656565-0000-4000-8000-0000000${ARMNUM}${SCHNUM}0${REP}0"

OUT="$REPO/.agent-yield/experiments/65/$ARM-$SCHEMA-r$REP"
mkdir -p "$OUT"
echo "$SID" > "$OUT/session-id"
echo "$CORPUS" > "$OUT/corpus-path"

echo "== $ARM/$SCHEMA r$REP  session $SID"
echo "-- rebuilding corpus at $CORPUS"
"$REPO/.venv/bin/python" "$HERE/build-corpus.py" "$CORPUS" --no-test > "$OUT/corpus.json"

# --setting-sources user: this repo's own SessionStart hook would inject a handoff
#   into the arm and consume it. An experiment must not eat the state the next
#   session needs, and an injection is not part of either arm.
# --model opus, one model, every arm.
COMMON=(--output-format json --model opus --setting-sources user
        --allowedTools Bash --max-budget-usd 40)

{ cat "$HERE/arm-$ARM.md"; echo; cat "$HERE/task.md"; } > "$OUT/turn-1-prompt.md"

echo "-- turn 1 (the audit)"
( cd "$CORPUS" && claude -p "${COMMON[@]}" "${EXTRA[@]}" --session-id "$SID" ) \
    < "$OUT/turn-1-prompt.md" > "$OUT/turn-1.json"

"$REPO/.venv/bin/python" "$HERE/measure.py" "$SID" --cwd "$CORPUS" \
    --snapshot-dir "$OUT/snapshots" --label t1 > "$OUT/measured.json"
echo "  measured: $(cat "$OUT/measured.json")"
echo "  cli cost: $("$REPO/.venv/bin/python" -c "import json,sys; print(json.load(open(sys.argv[1])).get('total_cost_usd'))" "$OUT/turn-1.json")"
echo "== $ARM/$SCHEMA r$REP done"
