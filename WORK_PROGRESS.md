# Monitoring improvements

Each step requires isolated verification and an independent agent review before the next step starts.

1. Persistent log positions and duplicate prevention — reviewed and passed (12 focused tests)
2. Configurable bounded scheduling and monitoring health — reviewed; 10 tests passed
3. CPU/RAM/disk/inode monitoring — reviewed; 10 focused tests passed
4. Application contracts and opt-in synthetic checks — reviewed; 8 focused tests passed
5. Incident severity, persistence and stable recovery — reviewed; 33 regression tests and UI build passed
6. Incident-specific fix verification and controlled rollback — reviewed; 29 regression tests passed
7. Reviewed repair templates and exact file diffs — reviewed; 13 focused tests passed
8. Isolated staging rehearsal, deployment and operational documentation — completed; 101 regression tests, builds, migrations, rollout and health checks passed

Preserve existing volumes, Telegram ownership (Nextbyte stopped), and 14:00 EAT backups. No unapproved real remediation during testing.
