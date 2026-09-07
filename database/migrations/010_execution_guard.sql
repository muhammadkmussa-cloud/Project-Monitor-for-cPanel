-- Keep an incident's command execution and verification mutually exclusive.
CREATE UNIQUE INDEX IF NOT EXISTS remediation_one_active_incident
ON remediation_runs(incident_id) WHERE status='IN_PROGRESS';
ALTER TABLE remediation_runs ADD COLUMN IF NOT EXISTS baseline JSONB;
ALTER TABLE remediation_runs ADD COLUMN IF NOT EXISTS execution_finished_at TIMESTAMPTZ;
ALTER TABLE remediation_runs ADD COLUMN IF NOT EXISTS commands_succeeded BOOLEAN;
ALTER TABLE remediation_runs ADD COLUMN IF NOT EXISTS verification_context JSONB;
CREATE UNIQUE INDEX IF NOT EXISTS verification_one_per_run ON verification_runs(run_id);
