#!/usr/bin/env bash
set -euo pipefail
umask 077
export PATH=/usr/local/bin:/usr/bin:/bin
PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"
mkdir -p backups/logs

# Prevent overlapping scheduled runs.
exec 9>backups/.automatic-backup.lock
flock -n 9 || exit 0

LOG_FILE="backups/logs/$(date -u +%Y%m%dT%H%M%SZ).log"
exec >>"$LOG_FILE" 2>&1
echo "Started: $(date --iso-8601=seconds)"
if python3 -u scripts/backup.py; then
    echo "SUCCESS: $(date --iso-8601=seconds)"
    printf 'SUCCESS %s %s\n' "$(date --iso-8601=seconds)" "$LOG_FILE" >backups/.last-automatic-backup.tmp
    mv backups/.last-automatic-backup.tmp backups/last-automatic-backup.txt
else
    result=$?
    echo "FAILED (exit $result): $(date --iso-8601=seconds)"
    printf 'FAILED %s %s\n' "$(date --iso-8601=seconds)" "$LOG_FILE" >backups/.last-automatic-backup.tmp
    mv backups/.last-automatic-backup.tmp backups/last-automatic-backup.txt
    exit "$result"
fi
