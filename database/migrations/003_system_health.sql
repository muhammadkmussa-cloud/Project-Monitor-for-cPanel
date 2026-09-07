-- Migration 001 already creates system_health. Keep one latest row per component
-- for the health service's ON CONFLICT update.
CREATE UNIQUE INDEX IF NOT EXISTS system_health_component_unique ON system_health(component);
