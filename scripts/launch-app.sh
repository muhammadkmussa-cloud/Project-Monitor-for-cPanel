#!/usr/bin/env bash
set -euo pipefail
PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
APP_URL=http://localhost:3005
STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/project-monitor"
mkdir -p "$STATE_DIR"
chmod 700 "$STATE_DIR"
umask 077
exec >>"$STATE_DIR/launcher.log" 2>&1

fail() {
    echo "$(date --iso-8601=seconds): $1"
    zenity --error --title="Project Monitor" --text="$1

Details: $STATE_DIR/launcher.log" || true
    exit 1
}

ready() {
    curl --noproxy '*' --fail --silent --max-time 3 "$APP_URL/health" >/dev/null &&
        curl --noproxy '*' --fail --silent --max-time 3 "$APP_URL/" >/dev/null
}

command -v google-chrome >/dev/null || fail "Google Chrome is required to open Project Monitor."
# Serialize startup when the shortcut is clicked more than once.
exec 9>"$STATE_DIR/launcher.lock"
flock -w 180 9 || fail "Another Project Monitor startup is still in progress. Try again shortly."
if ! ready; then
    notify-send "Project Monitor" "Starting the dashboard. This may take a minute." || true
    if ! bash "$PROJECT_DIR/scripts/start.sh"; then
        fail "Project Monitor could not start. Check that Docker is running and your account can access it. Existing data volumes must be present."
    fi
    deadline=$((SECONDS + 120))
    until ready; do
        (( SECONDS < deadline )) || fail "The dashboard is not ready yet. Check the Project Monitor containers, then try again."
        sleep 2
    done
fi
flock -u 9
exec 9>&-
# Reuse the normal Chrome profile so the dashboard's saved login is available.
exec google-chrome --app="$APP_URL/" --class=ProjectMonitor
