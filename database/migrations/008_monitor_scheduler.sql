ALTER TABLE projects ADD COLUMN IF NOT EXISTS monitoring_config JSONB NOT NULL DEFAULT '{}';
CREATE TABLE IF NOT EXISTS project_check_state (
 project_id UUID NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
 check_kind TEXT NOT NULL,
 next_due_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 last_started_at TIMESTAMPTZ,
 last_completed_at TIMESTAMPTZ,
 last_success_at TIMESTAMPTZ,
 lease_until TIMESTAMPTZ,
 lease_token UUID,
 consecutive_errors INTEGER NOT NULL DEFAULT 0,
 last_error TEXT,
 last_result JSONB,
 PRIMARY KEY(project_id,check_kind)
);
CREATE TABLE IF NOT EXISTS monitoring_worker_state (
 worker_name TEXT PRIMARY KEY,
 last_heartbeat TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
