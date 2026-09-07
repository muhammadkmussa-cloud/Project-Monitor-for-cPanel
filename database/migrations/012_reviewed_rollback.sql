ALTER TABLE remediation_runs ADD COLUMN IF NOT EXISTS rollback_started_at TIMESTAMPTZ;
ALTER TABLE remediation_runs ADD COLUMN IF NOT EXISTS rollback_result JSONB;
