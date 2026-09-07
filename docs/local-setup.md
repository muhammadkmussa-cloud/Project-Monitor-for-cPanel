# Local Setup

## Prerequisites

- Docker and Docker Compose
- Git

## Quick Start

```bash
# 1. Clone the repository
git clone <repository-url>
cd project_monitor

# 2. Create environment file
cp .env.example .env

# 3. Edit .env with your configuration
# Minimum required:
# - POSTGRES_PASSWORD (change from default)
# - N8N_ENCRYPTION_KEY (generate random hex)
# - DEEPSEEK_API_KEY (from DeepSeek dashboard)
# - TELEGRAM_BOT_TOKEN (from BotFather)
# - TELEGRAM_CHAT_ID (your chat ID)

# 4. Start all services using the existing persistent volumes
bash scripts/start.sh

# 5. Verify services are running
docker compose ps

# 6. Check health
curl http://localhost:8080/health
```

## Default Ports

| Service | Port | URL |
|---------|------|-----|
| Dashboard | 3005 | http://localhost:3005 |
| PostgreSQL | 25432 | localhost:25432 |
| Redis | 26379 | localhost:26379 |
| Monitoring Agent | 8080 | http://localhost:8080 |
| n8n | 5678 | http://localhost:5678 |

## Initial n8n Setup

1. Open http://localhost:5678
2. Create owner account
3. Go to Settings > API
4. Generate API key
5. Update N8N_API_KEY in .env
6. Restart: `docker compose restart n8n`

## Monitoring workflow

`n8n/workflows/unified_monitoring.json` is the maintained workflow. It calls
`POST /api/v1/monitoring/run` every minute; the backend checks only projects whose
configured interval has elapsed. The backend deduplicates incidents and prepares
proposals for review. Monitoring never approves or executes a fix automatically.

In a new n8n installation, create an HTTP Header Auth credential named **Project
Monitor Backend** with header `X-API-Key`, using a key from an admin account with
`monitoring:write` permission. Import the workflow, select that credential, and
activate it. The current installation is configured through n8n's encrypted
credential store. The old examples in `n8n/legacy-workflows/` are unsupported
reference material and must not be activated.

The dashboard's manual scan queues a backend scan directly. Public onboarding
webhooks are not part of the maintained workflow; use the authenticated dashboard.

## Applying upgrades

Database initialization scripts run only for an empty volume. Existing
installations require explicit migration application; never delete volumes to
apply a schema change. The audit upgrade adds `platform_settings` and a unique
proposal-execution index using migrations 004 and 005. Back up before applying
migrations. Fresh installations also use the corrected migration 003.

## SSH and remediation

SSH verifies the server against `/keys/known_hosts`. Add only independently
verified host keys to the host's `.ssh/known_hosts`; an unknown or changed host
key produces an error instead of being trusted automatically. Credentials stay
encrypted with the existing `API_SECRET_KEY`, which must be preserved in backups.

Remediation must be enabled explicitly on the project. Execution requires a
matching, unexpired approval of a concrete plan and always uses that project's
stored SSH connection. Each proposal can execute only once. The command policy
allows basic diagnostic commands and a small set of approved restart/cache
operations; unknown commands are blocked. Local shell execution is disabled.
A failed execution is not reported as rolled back or verified. A new plan is
required after a failed or interrupted run; review the server first.

## Database Access

```bash
# Connect to PostgreSQL
docker compose exec postgres psql -U monitor_admin -d project_monitor

# List tables
\dt

# Check schema
\d projects
```

## Logs

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f monitoring-agent
docker compose logs -f n8n
docker compose logs -f postgres
```

## Desktop app access

Open **Project Monitor** from the Ubuntu applications menu or double-click
`Project Monitor.desktop` on the desktop. It opens Chrome in app window mode
at `http://localhost:3005`, reusing the normal browser profile. If the dashboard
is unavailable, the launcher runs `scripts/start.sh` and waits for readiness.
Startup errors appear in a dialog and are logged in
`~/.local/state/project-monitor/launcher.log`. Closing the window leaves the
monitoring services running; use the stop script below to stop them.

## Stopping services

```bash
# Stop safely; preserve containers and data
bash scripts/stop.sh

# Start again, using the same project and volumes
bash scripts/start.sh
```

The local Compose file fixes the project name to `project_monitor` and treats its
four existing volumes as external. Compose will not remove them, even with
`down -v`. Explicit Docker volume deletion or disk loss can still destroy data.
Do not delete volumes to troubleshoot startup. If a volume is missing, the start
script fails instead of creating an empty replacement. On a genuinely new
installation, create the four volumes explicitly with `docker volume create`
using the names in `docker-compose.yml`; on an existing installation, recover
the missing volume or restore a backup instead.

## Backing up the running local installation

```bash
python3 scripts/backup.py
```

Backups are private timestamped directories under `backups/`. A `COMPLETE` file
is written only after all steps succeed. They include a PostgreSQL custom-format
dump, an online SQLite snapshot of n8n, n8n files including its encryption config,
the remediation backup volume, `.env`, and the local Compose configuration.
Redis cache and host SSH keys are not included; preserve the host SSH keys
separately. Copy completed backups to another disk or private backup service.
Backups are never automatically expired.

### Automatic local backups

The host user's crontab runs `scripts/automatic-backup.sh` daily at 14:00 (2:00 PM)
in the host timezone (Africa/Nairobi, EAT). Docker and this computer must be
running at that time; cron does not catch up a run missed while powered off.
The wrapper prevents overlapping scheduled jobs and records a private log for
each run under `backups/logs/`. No email or external notifications are sent.

```bash
# Inspect the installed schedule
crontab -l
# Check the most recent automatic run
cat backups/last-automatic-backup.txt
# Run the same job manually
bash scripts/automatic-backup.sh
```

The crontab uses this project's absolute path. Update it if the project moves.
The scheduled job backs up running services and does not start stopped servers.

The script verifies the PostgreSQL archive listing and SQLite integrity, but
does not perform a full restore test. It leaves services running, so the databases
and n8n binary files are captured at slightly different times. For an exact
cross-service snapshot, arrange a maintenance window before backup.

To recover, stop the application writers, restore `postgres.dump` with
`pg_restore` into a clean PostgreSQL database, and restore `n8n-files.tar.gz`
plus `n8n.sqlite` (as `database.sqlite`) into the n8n data volume. Restore the
matching `.env` and n8n encryption config; do not reuse stale SQLite WAL/SHM
files. Preserve the n8n container user's ownership and start the services only
after verification. Restore into separate volumes first to avoid overwriting
recoverable live data. These local scripts do not change production deployment.

## Troubleshooting

### Services won't start
- Check Docker is running
- Verify ports are not in use
- Check `.env` configuration

### PostgreSQL connection refused
- Wait for health check to pass
- Verify POSTGRES_PASSWORD matches in all services

### n8n can't connect to agent
- Ensure both are on same Docker network
- Use service names (not localhost) for internal communication


## Monitoring workflow after the audit

The active workflow checks due projects every minute through an encrypted n8n
HTTP Header Auth credential named **Project Monitor Backend**. Each project's
configured interval still determines when it is checked. The workflow prepares
incidents for review and never approves or executes remediation.

When importing an updated workflow on this single-instance n8n installation,
import it normally, run `n8n publish:workflow --id=1`, then restart n8n to register
the published schedule. The import option `--activeState=fromJson` is unsupported
in this deployment mode. Keep the credential assignment and existing n8n data
volume; do not activate files from `n8n/legacy-workflows/`.

PostgreSQL and Redis host ports are bound to `127.0.0.1`; Docker services continue
to use `postgres:5432` and `redis:6379`. Application ports remain 3005, 8080 and
5678. See [the audit report](../AUDIT.md) for changes, verification and limits.
