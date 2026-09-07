#!/bin/bash
# ==================================================
# Project Monitor - PostgreSQL Backup Script
# ==================================================
# Run via cron: 0 2 * * * /path/to/backup-db.sh
# ==================================================

set -e

BACKUP_DIR="/opt/project-monitor/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/db_backup_$TIMESTAMP.sql.gz"

mkdir -p "$BACKUP_DIR"

# Dump and compress
docker exec project_monitor-postgres-1 pg_dump \
    -U monitor_admin \
    -d project_monitor \
    --no-owner \
    --no-privileges \
    | gzip > "$BACKUP_FILE"

# Keep only last 30 days of backups
find "$BACKUP_DIR" -name "db_backup_*.sql.gz" -mtime +30 -delete

echo "[$(date)] Backup completed: $BACKUP_FILE ($(du -h "$BACKUP_FILE" | cut -f1))"
