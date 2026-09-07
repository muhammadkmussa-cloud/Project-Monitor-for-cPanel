# Telegram incident reviews

New website and application-log incidents enter a PostgreSQL review queue. The
worker starts processing within its two-second polling interval; SSH evidence
collection and AI diagnosis take additional time. Delivery is attempted as soon
as the proposal is prepared. Network/processing failures are retried after a
minute; pending work survives restarts.

Telegram receives a readable summary plus a JSON attachment containing the full
proposed commands, explanation, root cause/evidence, risk/confidence, rollback
and verification plan, incident details, and all stored project metadata.
Credential fields and recognized embedded secrets are redacted. The attachment
is part of the review: read its exact steps before approving.

The buttons belong to one delivered review message, one proposal and its saved
target. Only the configured private-chat owner can decide. Reviews expire after
24 hours. Changed proposals/targets, closed incidents, and repeated decisions
are rejected. The reviewed project directory is used for approved commands.

- **Approve:** records the decision and queues the attached executable commands
  through existing safety checks. A proposal can execute only once.
- **Reject:** records rejection and marks the incident ignored. It runs nothing.
- **Manual review required:** the AI could not provide an executable plan, the
  plan contains unsupported actions, or project remediation is disabled.
  Approve records review only; it does not override these restrictions.

A completion message distinguishes command execution from verified recovery.
The regular monitoring cycle continues to determine website recovery. No
arbitrary AI-generated script or file edit is enabled by this change.

Callbacks use outbound Telegram `getUpdates` polling, so this local deployment
needs no public webhook. Do not configure a second poller or a webhook for the
same bot. The update offset, decisions and delivery states are persistent.
Delivery is at least once: a crash after Telegram receives a message but before
the database stores its ID can produce a duplicate; only the stored message ID
can approve the proposal. A recorded execution claim is never automatically
replayed after an interrupted run.

Operational review state:

```sql
SELECT state, attempts, last_error, updated_at FROM incident_reviews;
```

The log scanner now recognizes exception-only lines and reports failed SSH log
reads as failures. Log scans still run every ten minutes, while website checks
respect each project's configured interval. "Immediate" proposal processing
starts after detection; it is not continuous request-by-request monitoring.

Validation: 43 isolated tests passed, including unauthorized clicks, message
binding, expiry, changed targets/proposals, rejection, manual-only proposals,
delivery failure, one-time execution, log incident enqueueing, and quoted
project-directory handling. Live SSH remediation was not performed as a test.

Telegram API reference: https://core.telegram.org/bots/api#getupdates

Live validation: Telegram accepted both the full metadata attachment and the
plain-text review with Approve/Reject buttons (test message 204). Test callbacks
are explicitly non-executing. Actual approval/rejection transitions and remote
execution replay protection were validated against a disposable database with
SSH execution mocked. No real remote fix was executed during setup.

Historical pre-deployment backup: `backups/20260906T211427Z-slgg6pgj/`.
Historical rollback image label: `project-monitor-agent:before-telegram-review`.

On 2026-09-07, the owner requested stopping `nextbyte-renderer` and assigning
its shared Telegram bot to Project Monitor. The Nextbyte container was stopped
without deleting its media volume. Project Monitor polling is enabled through
`platform_settings['telegram.polling_enabled']`. Restarting a competing consumer
will cause Project Monitor to pause polling on Telegram's conflict response;
stop the other consumer before re-enabling this setting.

## Verified execution outcomes
Approved executions capture a frozen project target and verification specification before commands run. Results are reported as `VERIFIED`, `STILL_FAILING`, or `UNAVAILABLE`; command exit status alone is never presented as recovery. A failed action stops later actions. File patches require an exact reviewed hash, encrypted backup, atomic replacement, and guarded rollback only when explicitly reviewed. Rollback and verification state are durable and recoverable after a worker restart.

Monitoring intervals are configurable per project; the default log interval is ten minutes. The current isolated regression suite has 101 passing tests. Application contracts are disabled until a project supplies its expected checks, and automatic service restarts require an explicit `metadata.repair_services` allowlist. The final rehearsal used disposable database, HTTP, and mocked SSH fixtures; no production repair command was executed.
