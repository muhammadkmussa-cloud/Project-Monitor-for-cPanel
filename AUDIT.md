# Project Monitor audit and fixes

Date: 2026-09-06 (Africa/Nairobi).
Scope: the running local Docker stack, FastAPI backend, React dashboard, database migrations, authentication/tenant boundaries, SSH and remediation, n8n workflows, backups, deployment scripts, dependencies, and tests. This directory has no Git history. The pre-change source snapshot and data backups are retained under `backups/`.

## Fixed

- **Authorization and tenant isolation:** centralized access rules prevent self-promotion and unauthorized mutations. Tenant lists, analytics, and resource lookups enforce ownership. Tokens resolve current account roles/status on each request. Disabled client accounts cannot access tenant data; active platform administrators retain access to administer inactive clients.
- **Authentication and credentials:** JSON login avoids passwords in query strings; password hashes are excluded from user responses. New passwords use scrypt; legacy passwords upgrade on successful login. API keys enforce expiration, account status and explicit scopes. Newly issued keys default to read access; existing empty-scope keys retain their owner's role for compatibility. Login throttling no longer trusts forged forwarding headers or groups unrelated users by JWT prefix. Default signing/encryption secrets are rejected.
- **Remediation controls:** execution requires a matching, unexpired, recorded approval and an open incident, uses the stored project target, respects disabled remediation, and reserves a proposal once to prevent replay. No implicit local execution. Unrecognized commands, missing backup/content, and unsupported verification fail explicitly. Rejections invalidate approvals. Backup paths and checksums are validated and duplicate basenames remain distinct.
- **SSH:** verify host keys through `/keys/known_hosts`; quote project paths; support current Paramiko key APIs; drain command output with size/time limits; report failed statistics calls as failures.
- **Database/API contracts:** isolate application preferences in `platform_settings` without overwriting historical n8n settings; preserve existing preferences. Fix client JSON and plan serialization, project create/update fields, invalid reference handling, and fresh-install administrator bootstrap. Add one-run-per-proposal constraint.
- **Monitoring:** replace the disconnected workflow branches with an authenticated scheduled backend cycle. Check only enabled/due projects, lock against overlapping checks, deduplicate monitoring incidents, and resolve those incidents on recovery. Manual scans queue actual work. Diagnosis creates reviewable proposals; the workflow never approves or executes fixes. API keys live in encrypted n8n credentials instead of workflow headers. Legacy workflows are archived and marked unsupported.
- **Dashboard:** validate saved login tokens; show API errors; hide administrative controls from tenant users; repair incident diagnosis/approval display, client plans and settings persistence. Charts use recorded incidents and health checks. Unknown uptime displays as unavailable. Database and Redis health probes test the actual services.
- **Persistence/deployment:** preserve the four existing external volumes and encryption secrets; retain the daily 14:00 EAT backup schedule and desktop launcher. Restrict PostgreSQL/Redis host ports to loopback. Backend runs as UID 1000 with writable remediation backups. Lock dependencies and use reproducible frontend installation. Repair production Nginx rendering and certificate bootstrap/renewal scripts.

## Validation

- Final candidate backend: **28 passed, 29 skipped**. The skipped legacy tests require an explicitly configured live URL and were not allowed to mutate this installation. Five existing `datetime.utcnow()` deprecation warnings remain.
- Regression coverage includes two-tenant access, privilege escalation, deleted/disabled accounts, inactive-client administrator access, hash disclosure, API-key expiry/scopes, settings/client/project contracts, approval matching, execution replay, scan deduplication/recovery, shell quoting, and backup integrity.
- PostgreSQL backup restored successfully into an isolated database. Migrations 004/005 also passed against that restored database, preserving its project, users and application preference. n8n backup SQLite integrity checked. This is not a full disaster-recovery rehearsal of every external integration.
- Backend image builds with `pip check` clean. All 49 locked Python packages checked against PyPI metadata with no reported advisories at audit time. Frontend upgraded and rebuilt; npm reported zero vulnerabilities after installation. These checks do not cover every operating-system package or prove absence of unknown vulnerabilities.
- Browser login and all six main pages (dashboard, projects, incidents, analytics, clients, settings) exercised against isolated synthetic data: no JavaScript exceptions or failed API requests. A discovered client-plan serialization problem was fixed and added to regression coverage.
- Live deployment: all five containers healthy; all 12 authenticated read-only API checks returned 200. Existing 1 project, 3 users, 1 application preference and 1 encrypted project credential preserved; credential decryption verified without exposing its contents. Backend UID 1000 can write its backup volume and read trusted SSH host keys. Updated dashboard login page loads at port 3005. n8n workflow published using supported import/publish commands and restarted to register its schedule.

The first two scheduled executions after deployment completed successfully. The first recorded HTTP 200 with 2,123 ms response time and 72 days of certificate validity: a latency warning, not an outage, prepared for human approval; the next respected the configured 300-second project interval. Temporary audit containers, networks, and the disposable restored database were removed.

## Recovery material

- Initial online backup: `backups/20260906T190619Z-cw6ik_x8/`.
- Immediate pre-deployment backup: `backups/20260906T202813Z-h5vcslkb/`.
- Post-update verified backup: `backups/20260906T203352Z-ujlpiwbg/`.
- Original source archive: `backups/source-before-audit-20260906T220621.tar.gz`.
- Original running application images tagged `project-monitor-agent:before-audit` and `project-monitor-frontend:before-audit`.

These files contain secrets; keep them private. Database migrations are additive; do not drop tables or delete volumes to roll back an application image. Restoring n8n requires its matching SQLite snapshot and encryption configuration; see `docs/local-setup.md`.

## Limits and remaining work

- No real remote remediation, rollback, production certificate issuance, or outbound notification was executed as an audit test. Remote SSH operations now require an existing trusted host key. Validate a recovery procedure on a designated staging project before relying on automated operational changes.
- Some advanced billing/report metrics are still estimates or incomplete. Daily report scheduling is disabled in the UI, and unimplemented retention cleanup returns 501 instead of claiming deletion/archival. The core dashboard uses actual stored measurements.
- Some auxiliary SSH services still use synchronous calls within async methods; high-concurrency remote operations need further load testing and worker isolation.
- Backups remain on this computer unless copied elsewhere. Cron runs at 2 PM only when the host and Docker are running; it does not catch up missed runs. Off-device backup storage is not configured.
- The application still uses browser token storage and HTTP for local access. The production TLS path was repaired in source but has not been deployed to a public domain during this audit.
