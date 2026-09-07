#!/usr/bin/env bash
set -euo pipefail
PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"
# Fail rather than silently creating an empty database if storage is missing.
for volume in project_monitor_pgdata project_monitor_redisdata project_monitor_backups project_monitor_n8n_data; do
    docker volume inspect "$volume" >/dev/null
done
docker compose -p project_monitor -f docker-compose.yml up -d
