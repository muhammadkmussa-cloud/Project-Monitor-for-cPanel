CREATE TABLE IF NOT EXISTS incident_conditions (
 project_id UUID NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
 check_kind TEXT NOT NULL,
 condition_key TEXT NOT NULL,
 failure_count INTEGER NOT NULL DEFAULT 0,
 recovery_count INTEGER NOT NULL DEFAULT 0,
 incident_id UUID REFERENCES incidents(incident_id) ON DELETE SET NULL,
 first_failure_at TIMESTAMPTZ,
 last_observed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 last_evidence JSONB,
 PRIMARY KEY(project_id,check_kind,condition_key)
);
-- Preserve existing HTTP review episodes and let stable healthy observations
-- close them, without duplicating an already delivered legacy incident.
INSERT INTO incident_conditions(project_id,check_kind,condition_key,failure_count,incident_id,first_failure_at)
SELECT project_id,'http','http:legacy:'||incident_id::text,1,incident_id,first_seen
FROM incidents WHERE raw_error_reference='monitoring-cycle'
AND status NOT IN ('RESOLVED','IGNORED','ROLLED_BACK')
ON CONFLICT DO NOTHING;
