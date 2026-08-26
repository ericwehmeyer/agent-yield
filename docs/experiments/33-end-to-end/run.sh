#!/usr/bin/env bash
# One arm of #33, end to end: the audit turn, then five fixed follow-up turns.
#
#   run.sh baton 1
#   run.sh reader 1
#   run.sh baton1 1     # #47: the baton arm with the packing fixed at one agent
#
# Both arms get IDENTICAL flags. The only difference is which arm-*.md is
# prepended to the shared task, because a flag difference (allowing `Agent` in
# one arm and not the other) would change the tool schema and so the token
# count, and this experiment is a token count.
#
# The five follow-up turns are the point. A parent that read everything carries
# it on every later call; a parent that dispatched carries only what came back.
# Measuring only the audit turn would measure the wrong half of the claim.
set -euo pipefail

ARM="${1:?arm: baton|reader}"
REP="${2:?replicate: 1|2}"
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../../.." && pwd)"

case "$ARM" in
  baton)  ARMNUM=1 ;;
  reader) ARMNUM=2 ;;
  baton1) ARMNUM=3 ;;   # #47: the baton, but ONE agent for all 19 modules
  *) echo "arm must be baton, reader or baton1" >&2; exit 2 ;;
esac
SID="33333333-0000-4000-8000-00000000${ARMNUM}0${REP}0"

OUT="$REPO/.agent-yield/experiments/33/$ARM-r$REP"
mkdir -p "$OUT"
echo "$SID" > "$OUT/session-id"

# --setting-sources user: this repo's own SessionStart hook would inject a
#   handoff into the arm and consume it. An experiment must not eat the state
#   the next session needs, and an injection is not part of either arm.
# --model opus, one model, both arms.
# --disallowedTools: read-only, identically for both arms.
COMMON=(--output-format json --model opus --setting-sources user
        --disallowedTools Edit Write NotebookEdit WebFetch WebSearch
        --max-budget-usd 25)

snap () {  # $1 = turn label
  python3 "$HERE/measure.py" "$SID" --cwd "$REPO" \
      --snapshot-dir "$OUT/snapshots" --label "$1" > "$OUT/cumulative-$1.json"
  echo "  cumulative after $1: $(cat "$OUT/cumulative-$1.json")"
}

echo "== $ARM r$REP  session $SID"
{ cat "$HERE/arm-$ARM.md"; echo; cat "$HERE/task.md"; } > "$OUT/turn-1-prompt.md"

echo "-- turn 1 (the audit)"
claude -p "${COMMON[@]}" --session-id "$SID" < "$OUT/turn-1-prompt.md" > "$OUT/turn-1.json"
snap t1

n=1
while IFS= read -r line; do
  [ -z "$line" ] && continue
  n=$((n + 1))
  echo "-- turn $n"
  printf '%s\n' "$line" > "$OUT/turn-$n-prompt.md"
  claude -p "${COMMON[@]}" --resume "$SID" < "$OUT/turn-$n-prompt.md" > "$OUT/turn-$n.json"
  snap "t$n"
done < "$HERE/tail.txt"

echo "== $ARM r$REP done"
