#!/usr/bin/env bash
#
# Register, inspect or remove the launchd agent that runs
# scripts/run-unattended.py on an interval. The macOS half of
# scripts/install-scheduler.ps1, and deliberately as thin: every guard lives in
# run-unattended.py, where pytest can reach it. A scheduler entry that carried
# policy would be policy nothing can test.
#
# WHY launchd AND NOT cron. cron is still on macOS and still runs. It also does
# not fire a tick the machine slept through, records no exit status, and makes
# no single-instance promise -- three of the four guarantees #177 asks for,
# absent. launchd is the native scheduler and Apple has called cron deprecated
# for years.
#
# WHERE launchd DOES NOT MATCH TASK SCHEDULER. Three of the four guarantees
# port as plist keys or better. The fourth does not exist:
#
#   MultipleInstances IgnoreNew -> launchd will not start a second copy of a
#       job while one is running, so ticks coalesce. Asserted rather than
#       assumed: the guarantee that actually holds is the lock file in
#       run-unattended.py, which survives a reboot, a second scheduler entry
#       and a hand-run from a shell. launchd's behaviour is the belt.
#   StartWhenAvailable -> StartInterval fires on wake when the tick was slept
#       through. This is launchd's default and needs no key.
#   ExecutionTimeLimit 2h -> NO EQUIVALENT. There is no plist key that caps a
#       job's wall clock, so the cap moves into the invocation: perl sets an
#       alarm and execs the runner, and a pending alarm survives exec while
#       SIGALRM's default disposition is to terminate. Measured on macOS 26.6.2
#       (2026-08-30): `perl -e 'alarm shift; exec @ARGV' 2 sleep 30` exits 142
#       after 2 seconds. run-unattended.py's own --timeout caps the `claude`
#       call at 3600s; this caps everything around it.
#   AllowStartIfOnBatteries / DontStopIfGoingOnBatteries -> no equivalent and
#       none needed. launchd runs StartInterval jobs on battery already.
#
# WHY THE PLIST CARRIES A PATH. A LaunchAgent does not inherit an interactive
# shell's PATH; it gets launchd's, which on a stock box is /usr/bin:/bin:
# /usr/sbin:/sbin and holds no `claude`. The Windows task runs in the
# interactive session precisely so a scheduled `claude -p` gets the same PATH,
# the same install and the same hooks an interactive run gets -- that is #28's
# first open question, and a job that answered it from a different environment
# would answer a different question. So the installing shell's PATH is written
# into the plist, and this file is machine state for the same reason the
# rendered .claude/settings.json is.
#
# Exit 0 on success, 1 on a refusal that names its reason, 2 when --status
# finds nothing registered.

set -euo pipefail

INTERVAL_MINUTES=60
LABEL='com.agent-yield.unattended'
COMMIT=1
SIGNING_KEY="${AGENT_YIELD_SIGNING_KEY:-}"
SIGNING_EMAIL="${AGENT_YIELD_SIGNING_EMAIL:-}"
MODE=install

# Two hours, the number install-scheduler.ps1 passes to ExecutionTimeLimit.
TIMEOUT_SECONDS=7200

# An interval under this is a loop, not a schedule -- the same refusal the
# Windows installer makes, at the same number.
MIN_INTERVAL_MINUTES=5

usage() {
    cat <<'USAGE'
usage: scripts/install-scheduler.sh [options]

  --interval-minutes N   how often to fire (default 60, refuses under 5)
  --label NAME           launchd label (default com.agent-yield.unattended)
  --signing-key FPR      the loop's own key, never the operator's (#171)
  --signing-email ADDR   author/committer address for those commits
  --no-commit            register with --no-commit: work is left in the tree
  --dry-run              print the plist and change nothing
  --status               print the registered agent and its last result
  --run-now              fire one run immediately, change nothing else
  --uninstall            remove the agent
  -h, --help             this

  --signing-key and --signing-email default to $AGENT_YIELD_SIGNING_KEY and
  $AGENT_YIELD_SIGNING_EMAIL. A scheduled job carries no environment of its
  own, which is why they go on the argument line, where --status shows them.
USAGE
}

fail() { echo "refused: $1" >&2; exit 1; }
warn() { echo "$1" >&2; }

while [ $# -gt 0 ]; do
    case "$1" in
        --interval-minutes) INTERVAL_MINUTES="${2:-}"; shift 2 ;;
        --label)            LABEL="${2:-}"; shift 2 ;;
        --signing-key)      SIGNING_KEY="${2:-}"; shift 2 ;;
        --signing-email)    SIGNING_EMAIL="${2:-}"; shift 2 ;;
        --no-commit)        COMMIT=0; shift ;;
        --commit)           COMMIT=1; shift ;;
        --dry-run)          MODE=dry-run; shift ;;
        --status)           MODE=status; shift ;;
        --run-now)          MODE=run-now; shift ;;
        --uninstall)        MODE=uninstall; shift ;;
        -h|--help)          usage; exit 0 ;;
        *)                  echo "unknown option: $1" >&2; usage >&2; exit 1 ;;
    esac
done

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(dirname "$HERE")"
PYTHON="$REPO/.venv/bin/python"
RUNNER="$REPO/scripts/run-unattended.py"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
DOMAIN="gui/$(id -u)"
OUT_LOG="$REPO/.agent-yield/scheduler.log"
ERR_LOG="$REPO/.agent-yield/scheduler.err"

case "$LABEL" in
    ''|*/*) fail "a launchd label cannot be empty or contain '/'" ;;
esac

# --- status ---------------------------------------------------------------

if [ "$MODE" = status ]; then
    if [ ! -f "$PLIST" ]; then
        echo "no agent named '$LABEL' is registered ($PLIST does not exist)"
        exit 2
    fi
    echo "label     $LABEL"
    echo "plist     $PLIST"
    if listing="$(launchctl list "$LABEL" 2>/dev/null)"; then
        pid="$(printf '%s\n' "$listing" | sed -n 's/.*"PID" = \([0-9]*\);/\1/p')"
        last="$(printf '%s\n' "$listing" | sed -n 's/.*"LastExitStatus" = \(-*[0-9]*\);/\1/p')"
        echo "loaded    yes (pid ${pid:-none}, last exit ${last:-unknown})"
    else
        echo "loaded    NO -- the plist exists but is not bootstrapped into $DOMAIN"
    fi
    interval="$(/usr/libexec/PlistBuddy -c 'Print :StartInterval' "$PLIST" 2>/dev/null || echo '?')"
    echo "interval  ${interval}s"
    echo "action    $(/usr/libexec/PlistBuddy -c 'Print :ProgramArguments' "$PLIST" 2>/dev/null \
        | sed -n '2,$p' | sed '$d' | sed 's/^ *//' | tr '\n' ' ')"
    for log in "$OUT_LOG" "$ERR_LOG"; do
        if [ -s "$log" ]; then
            echo "--- $log, last 5 lines ---"
            tail -n 5 "$log"
        fi
    done
    exit 0
fi

# --- run now --------------------------------------------------------------

if [ "$MODE" = run-now ]; then
    [ -f "$PLIST" ] || fail "no agent named '$LABEL' is registered"
    launchctl kickstart -k "$DOMAIN/$LABEL"
    echo "kicked '$LABEL'. Watch it: tail -f '$OUT_LOG'"
    exit 0
fi

# --- uninstall ------------------------------------------------------------

if [ "$MODE" = uninstall ]; then
    if [ ! -f "$PLIST" ]; then
        echo "nothing to remove: no agent named '$LABEL'"
        exit 0
    fi
    launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
    rm -f "$PLIST"
    echo "removed '$LABEL' and $PLIST"
    exit 0
fi

# --- refusals -------------------------------------------------------------

# Refuse rather than register something that cannot run. An agent that fires
# hourly against a missing interpreter is a silent failure with a schedule.
case "$INTERVAL_MINUTES" in
    ''|*[!0-9]*) fail "--interval-minutes wants a whole number, got '$INTERVAL_MINUTES'" ;;
esac
[ "$INTERVAL_MINUTES" -ge "$MIN_INTERVAL_MINUTES" ] \
    || fail "an interval under $MIN_INTERVAL_MINUTES minutes is a loop, not a schedule"
[ -x "$PYTHON" ] || fail "$PYTHON does not exist or is not executable"
[ -f "$RUNNER" ] || fail "$RUNNER does not exist"

# Warnings go to stderr so that --dry-run's stdout is a plist and nothing
# else. `plutil -lint` on the piped output is how this installer is tested.
if ! command -v claude >/dev/null 2>&1; then
    warn "warning: 'claude' is not on this shell's PATH, and the agent inherits"
    warn "         this shell's PATH by copy rather than by session. Fix the PATH"
    warn "         and re-run this installer, or every run will fail at the same"
    warn "         line into $ERR_LOG."
fi

if [ "$COMMIT" -eq 1 ] && [ -z "$SIGNING_KEY" ]; then
    warn "warning: no --signing-key, so this agent will not commit. Its runs will"
    warn "         leave work in the tree and the next one refuses on the"
    warn "         dirty-tree guard. See #171."
fi

# --- the plist ------------------------------------------------------------

xml_escape() {
    printf '%s' "$1" | sed -e 's/&/\&amp;/g' -e 's/</\&lt;/g' -e 's/>/\&gt;/g'
}

ARGS=("/usr/bin/perl" "-e" 'alarm shift; exec @ARGV' "$TIMEOUT_SECONDS" \
      "$PYTHON" "$RUNNER")
if [ "$COMMIT" -eq 0 ]; then ARGS+=("--no-commit"); fi
if [ -n "$SIGNING_KEY" ]; then ARGS+=("--signing-key" "$SIGNING_KEY"); fi
if [ -n "$SIGNING_EMAIL" ]; then ARGS+=("--signing-email" "$SIGNING_EMAIL"); fi

program_arguments=""
for arg in "${ARGS[@]}"; do
    program_arguments+="        <string>$(xml_escape "$arg")</string>
"
done

PLIST_XML="<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<!DOCTYPE plist PUBLIC \"-//Apple//DTD PLIST 1.0//EN\" \"http://www.apple.com/DTDs/PropertyList-1.0.dtd\">
<plist version=\"1.0\">
<dict>
    <key>Label</key>
    <string>$(xml_escape "$LABEL")</string>
    <key>ProgramArguments</key>
    <array>
$program_arguments    </array>
    <key>WorkingDirectory</key>
    <string>$(xml_escape "$REPO")</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>$(xml_escape "$PATH")</string>
        <key>HOME</key>
        <string>$(xml_escape "$HOME")</string>
    </dict>
    <key>StartInterval</key>
    <integer>$((INTERVAL_MINUTES * 60))</integer>
    <key>RunAtLoad</key>
    <false/>
    <key>StandardOutPath</key>
    <string>$(xml_escape "$OUT_LOG")</string>
    <key>StandardErrorPath</key>
    <string>$(xml_escape "$ERR_LOG")</string>
</dict>
</plist>
"

if [ "$MODE" = dry-run ]; then
    echo "$PLIST_XML"
    echo "would write $PLIST and bootstrap it into $DOMAIN"
    exit 0
fi

mkdir -p "$HOME/Library/LaunchAgents" "$REPO/.agent-yield"

verb=registered
if [ -f "$PLIST" ]; then
    verb=replaced
    launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
fi

printf '%s' "$PLIST_XML" > "$PLIST"
plutil -lint "$PLIST" >/dev/null || fail "the plist this wrote does not parse; $PLIST left in place to read"
launchctl bootstrap "$DOMAIN" "$PLIST"

echo "$verb '$LABEL': ${ARGS[*]}"
echo "every $INTERVAL_MINUTES minutes; RunAtLoad is off, so the first run is one interval out"
if [ "$COMMIT" -eq 0 ]; then
    echo "commit mode: off"
elif [ -n "$SIGNING_KEY" ]; then
    echo "commit mode: ON, signed by $SIGNING_KEY"
else
    echo "commit mode: off -- no signing key"
fi
echo "wall-clock cap: ${TIMEOUT_SECONDS}s, held by perl's alarm and not by launchd"
echo ""
echo "stop it any time:  touch '$REPO/.agent-yield/STOP'"
echo "check on it:       scripts/install-scheduler.sh --status"
echo "fire one now:      scripts/install-scheduler.sh --run-now"
echo "read what it did:  tail -n 5 '$REPO/.agent-yield/unattended.jsonl'"
