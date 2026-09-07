-- ==================================================
-- Project Monitor - Database Schema
-- Migration 001: Initial Schema
-- ==================================================

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ==================================================
-- ENUM TYPES
-- ==================================================

CREATE TYPE client_status AS ENUM ('active', 'inactive', 'suspended');
CREATE TYPE project_status AS ENUM ('HEALTHY', 'WARNING', 'DEGRADED', 'CRITICAL', 'DOWN', 'UNKNOWN');
CREATE TYPE connection_type AS ENUM ('ssh', 'cpanel_api', 'sftp');
CREATE TYPE application_type AS ENUM ('php', 'laravel', 'wordpress', 'nodejs', 'python', 'static', 'api', 'other');
CREATE TYPE incident_status AS ENUM ('OPEN', 'INVESTIGATING', 'AWAITING_APPROVAL', 'APPROVED', 'REMEDIATING', 'RESOLVED', 'FAILED', 'ROLLED_BACK', 'IGNORED');
CREATE TYPE incident_category AS ENUM (
    'HTTP_ERROR', 'APPLICATION_ERROR', 'DATABASE_FAILURE', 'REDIS_FAILURE',
    'PROCESS_CRASH', 'SSL_ERROR', 'DNS_ERROR', 'DISK_FULL',
    'MEMORY_EXHAUSTION', 'CPU_OVERLOAD', 'DEPLOYMENT_FAILURE',
    'CONFIGURATION_ERROR', 'PERMISSION_ERROR', 'DEPENDENCY_ERROR',
    'NETWORK_ERROR', 'UNKNOWN'
);
CREATE TYPE severity_level AS ENUM ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL');
CREATE TYPE approval_status AS ENUM ('PENDING', 'APPROVED', 'REJECTED', 'EXPIRED');
CREATE TYPE remediation_status AS ENUM ('PENDING', 'IN_PROGRESS', 'COMPLETED', 'FAILED', 'ROLLED_BACK');
CREATE TYPE verification_status AS ENUM ('PENDING', 'PASSED', 'FAILED', 'SKIPPED');
CREATE TYPE safety_level AS ENUM ('SAFE', 'APPROVAL_REQUIRED', 'BLOCKED');
CREATE TYPE notification_status AS ENUM ('PENDING', 'SENT', 'FAILED', 'SKIPPED');

-- ==================================================
-- TABLES
-- ==================================================

-- 1. clients - Multi-tenant client registry
CREATE TABLE clients (
    client_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    client_name VARCHAR(255) NOT NULL,
    email VARCHAR(255),
    phone VARCHAR(50),
    company VARCHAR(255),
    status client_status DEFAULT 'active',
    settings JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 2. projects - Core project registry
CREATE TABLE projects (
    project_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    client_id UUID NOT NULL REFERENCES clients(client_id) ON DELETE CASCADE,
    project_name VARCHAR(255) NOT NULL,
    domain VARCHAR(255),
    server_host VARCHAR(255),
    ssh_port INTEGER DEFAULT 22,
    ssh_username VARCHAR(100),
    credential_reference VARCHAR(255),
    connection_type connection_type DEFAULT 'ssh',
    project_path VARCHAR(1024),
    application_type application_type DEFAULT 'other',
    framework VARCHAR(100),
    environment VARCHAR(50) DEFAULT 'production',
    health_check_url VARCHAR(2048),
    repository_url VARCHAR(2048),
    repository_branch VARCHAR(100) DEFAULT 'main',
    monitoring_enabled BOOLEAN DEFAULT TRUE,
    remediation_enabled BOOLEAN DEFAULT FALSE,
    auto_restart_enabled BOOLEAN DEFAULT FALSE,
    log_locations JSONB DEFAULT '[]',
    check_interval INTEGER DEFAULT 300,
    thresholds JSONB DEFAULT '{}',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    last_check_at TIMESTAMPTZ,
    current_status project_status DEFAULT 'UNKNOWN'
);

-- 3. project_credentials - Encrypted SSH/API credentials
CREATE TABLE project_credentials (
    credential_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_id UUID NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    credential_name VARCHAR(255) NOT NULL,
    credential_type VARCHAR(50) NOT NULL,
    encrypted_data JSONB NOT NULL,
    last_rotated_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 4. monitoring_checks - Check results history
CREATE TABLE monitoring_checks (
    check_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_id UUID NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    client_id UUID NOT NULL REFERENCES clients(client_id) ON DELETE CASCADE,
    check_type VARCHAR(50) NOT NULL,
    status project_status NOT NULL,
    response_time_ms INTEGER,
    http_status_code INTEGER,
    ssl_days_remaining INTEGER,
    disk_usage_percent NUMERIC(5,2),
    cpu_usage_percent NUMERIC(5,2),
    memory_usage_percent NUMERIC(5,2),
    details JSONB DEFAULT '{}',
    checked_at TIMESTAMPTZ DEFAULT NOW()
);

-- 5. incidents - Incident tracking
CREATE TABLE incidents (
    incident_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_id UUID NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    client_id UUID NOT NULL REFERENCES clients(client_id) ON DELETE CASCADE,
    category incident_category NOT NULL,
    severity severity_level NOT NULL,
    status incident_status DEFAULT 'OPEN',
    error_signature VARCHAR(512),
    raw_error_reference TEXT,
    affected_component VARCHAR(255),
    first_seen TIMESTAMPTZ DEFAULT NOW(),
    last_seen TIMESTAMPTZ DEFAULT NOW(),
    occurrence_count INTEGER DEFAULT 1,
    diagnosis TEXT,
    evidence JSONB DEFAULT '[]',
    proposed_fix TEXT,
    confidence NUMERIC(3,2),
    approval_status approval_status,
    remediation_status remediation_status,
    verification_status verification_status,
    rollback_status VARCHAR(50),
    resolved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 6. incident_events - Incident lifecycle events
CREATE TABLE incident_events (
    event_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    incident_id UUID NOT NULL REFERENCES incidents(incident_id) ON DELETE CASCADE,
    event_type VARCHAR(50) NOT NULL,
    description TEXT,
    metadata JSONB DEFAULT '{}',
    created_by VARCHAR(100) DEFAULT 'system',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 7. ai_diagnoses - DeepSeek diagnosis records
CREATE TABLE ai_diagnoses (
    diagnosis_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    incident_id UUID NOT NULL REFERENCES incidents(incident_id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    model_used VARCHAR(100),
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    diagnosis JSONB NOT NULL,
    confidence NUMERIC(3,2),
    severity_assessment severity_level,
    root_cause TEXT,
    evidence JSONB DEFAULT '[]',
    proposed_fix TEXT,
    affected_files JSONB DEFAULT '[]',
    commands_required JSONB DEFAULT '[]',
    risk_level VARCHAR(20),
    rollback_plan TEXT,
    verification_plan JSONB DEFAULT '[]',
    requires_human_approval BOOLEAN DEFAULT TRUE,
    raw_response TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 8. fix_proposals - AI-proposed fixes
CREATE TABLE fix_proposals (
    proposal_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    incident_id UUID NOT NULL REFERENCES incidents(incident_id) ON DELETE CASCADE,
    diagnosis_id UUID REFERENCES ai_diagnoses(diagnosis_id),
    project_id UUID NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    proposal_summary TEXT NOT NULL,
    detailed_steps JSONB DEFAULT '[]',
    safety_level safety_level DEFAULT 'APPROVAL_REQUIRED',
    estimated_impact TEXT,
    estimated_duration VARCHAR(50),
    prerequisites JSONB DEFAULT '[]',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ
);

-- 9. approvals - Human approval records
CREATE TABLE approvals (
    approval_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    proposal_id UUID NOT NULL REFERENCES fix_proposals(proposal_id) ON DELETE CASCADE,
    incident_id UUID NOT NULL REFERENCES incidents(incident_id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    client_id UUID NOT NULL REFERENCES clients(client_id) ON DELETE CASCADE,
    status approval_status DEFAULT 'PENDING',
    requested_by VARCHAR(100) DEFAULT 'system',
    approved_by VARCHAR(100),
    approval_method VARCHAR(50),
    notes TEXT,
    requested_at TIMESTAMPTZ DEFAULT NOW(),
    responded_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ
);

-- 10. backup_records - Pre-remediation backups
CREATE TABLE backup_records (
    backup_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_id UUID NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    incident_id UUID REFERENCES incidents(incident_id),
    backup_type VARCHAR(50) NOT NULL,
    backup_location VARCHAR(1024),
    backup_size_bytes BIGINT,
    git_commit_hash VARCHAR(40),
    git_branch VARCHAR(100),
    files_backed_up JSONB DEFAULT '[]',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ
);

-- 11. remediation_runs - Fix execution records
CREATE TABLE remediation_runs (
    run_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    incident_id UUID NOT NULL REFERENCES incidents(incident_id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    proposal_id UUID REFERENCES fix_proposals(proposal_id),
    approval_id UUID REFERENCES approvals(approval_id),
    backup_id UUID REFERENCES backup_records(backup_id),
    status remediation_status DEFAULT 'PENDING',
    steps_executed JSONB DEFAULT '[]',
    commands_run JSONB DEFAULT '[]',
    output_log TEXT,
    error_log TEXT,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 12. verification_runs - Post-fix verification
CREATE TABLE verification_runs (
    verification_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    run_id UUID NOT NULL REFERENCES remediation_runs(run_id) ON DELETE CASCADE,
    incident_id UUID NOT NULL REFERENCES incidents(incident_id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    status verification_status DEFAULT 'PENDING',
    checks_performed JSONB DEFAULT '[]',
    checks_passed JSONB DEFAULT '[]',
    checks_failed JSONB DEFAULT '[]',
    http_status_before INTEGER,
    http_status_after INTEGER,
    health_status_before VARCHAR(50),
    health_status_after VARCHAR(50),
    notes TEXT,
    verified_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 13. deployments - Deployment tracking
CREATE TABLE deployments (
    deployment_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_id UUID NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    client_id UUID NOT NULL REFERENCES clients(client_id) ON DELETE CASCADE,
    deployment_type VARCHAR(50),
    git_commit_hash VARCHAR(40),
    git_branch VARCHAR(100),
    git_author VARCHAR(255),
    git_message TEXT,
    status VARCHAR(50) DEFAULT 'deployed',
    deployed_at TIMESTAMPTZ DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'
);

-- 14. audit_logs - Complete audit trail
CREATE TABLE audit_logs (
    log_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    client_id UUID REFERENCES clients(client_id),
    project_id UUID REFERENCES projects(project_id),
    incident_id UUID REFERENCES incidents(incident_id),
    user_action VARCHAR(100),
    workflow VARCHAR(100),
    action_type VARCHAR(50) NOT NULL,
    tool_requested VARCHAR(100),
    command_executed TEXT,
    command_output TEXT,
    approval_status VARCHAR(50),
    backup_reference VARCHAR(255),
    changes_made JSONB DEFAULT '{}',
    verification_result VARCHAR(50),
    rollback_performed BOOLEAN DEFAULT FALSE,
    final_status VARCHAR(50),
    ip_address INET,
    user_agent TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 15. notifications - Alert history
CREATE TABLE notifications (
    notification_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    client_id UUID REFERENCES clients(client_id),
    project_id UUID REFERENCES projects(project_id),
    incident_id UUID REFERENCES incidents(incident_id),
    channel VARCHAR(50) NOT NULL,
    recipient VARCHAR(255),
    subject VARCHAR(500),
    message TEXT NOT NULL,
    status notification_status DEFAULT 'PENDING',
    sent_at TIMESTAMPTZ,
    error_message TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 16. system_health - Platform self-monitoring
CREATE TABLE system_health (
    health_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    component VARCHAR(100) NOT NULL,
    status VARCHAR(50) NOT NULL,
    response_time_ms INTEGER,
    details JSONB DEFAULT '{}',
    checked_at TIMESTAMPTZ DEFAULT NOW()
);

-- ==================================================
-- INDEXES
-- ==================================================

-- Projects
CREATE INDEX idx_projects_client_id ON projects(client_id);
CREATE INDEX idx_projects_status ON projects(current_status);
CREATE INDEX idx_projects_monitoring_enabled ON projects(monitoring_enabled);
CREATE INDEX idx_projects_domain ON projects(domain);

-- Monitoring checks
CREATE INDEX idx_checks_project_id ON monitoring_checks(project_id);
CREATE INDEX idx_checks_client_id ON monitoring_checks(client_id);
CREATE INDEX idx_checks_checked_at ON monitoring_checks(checked_at);
CREATE INDEX idx_checks_status ON monitoring_checks(status);

-- Incidents
CREATE INDEX idx_incidents_project_id ON incidents(project_id);
CREATE INDEX idx_incidents_client_id ON incidents(client_id);
CREATE INDEX idx_incidents_status ON incidents(status);
CREATE INDEX idx_incidents_severity ON incidents(severity);
CREATE INDEX idx_incidents_category ON incidents(category);
CREATE INDEX idx_incidents_error_signature ON incidents(error_signature);
CREATE INDEX idx_incidents_created_at ON incidents(created_at);
CREATE INDEX idx_incidents_first_seen ON incidents(first_seen);

-- Incident events
CREATE INDEX idx_events_incident_id ON incident_events(incident_id);
CREATE INDEX idx_events_created_at ON incident_events(created_at);

-- AI diagnoses
CREATE INDEX idx_diagnoses_incident_id ON ai_diagnoses(incident_id);
CREATE INDEX idx_diagnoses_project_id ON ai_diagnoses(project_id);

-- Fix proposals
CREATE INDEX idx_proposals_incident_id ON fix_proposals(incident_id);

-- Approvals
CREATE INDEX idx_approvals_incident_id ON approvals(incident_id);
CREATE INDEX idx_approvals_status ON approvals(status);

-- Audit logs
CREATE INDEX idx_audit_project_id ON audit_logs(project_id);
CREATE INDEX idx_audit_client_id ON audit_logs(client_id);
CREATE INDEX idx_audit_incident_id ON audit_logs(incident_id);
CREATE INDEX idx_audit_created_at ON audit_logs(created_at);
CREATE INDEX idx_audit_action_type ON audit_logs(action_type);

-- Notifications
CREATE INDEX idx_notifications_project_id ON notifications(project_id);
CREATE INDEX idx_notifications_status ON notifications(status);

-- System health
CREATE INDEX idx_health_component ON system_health(component);
CREATE INDEX idx_health_checked_at ON system_health(checked_at);

-- ==================================================
-- FUNCTIONS
-- ==================================================

-- Auto-update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Apply updated_at triggers
CREATE TRIGGER update_clients_updated_at BEFORE UPDATE ON clients
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_projects_updated_at BEFORE UPDATE ON projects
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_credentials_updated_at BEFORE UPDATE ON project_credentials
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_incidents_updated_at BEFORE UPDATE ON incidents
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- 17. users - System users (owner, admin, viewer, etc.)
CREATE TABLE users (
    user_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    client_id UUID NOT NULL REFERENCES clients(client_id) ON DELETE CASCADE,
    email VARCHAR(255) NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL,
    password_hash VARCHAR(512) NOT NULL,
    role VARCHAR(50) NOT NULL DEFAULT 'viewer',
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    mfa_enabled BOOLEAN DEFAULT FALSE,
    preferences JSONB DEFAULT '{}',
    last_login TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 18. api_keys - API authentication keys
CREATE TABLE api_keys (
    key_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    client_id UUID NOT NULL REFERENCES clients(client_id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    key_hash VARCHAR(512) NOT NULL,
    permissions JSONB DEFAULT '[]',
    role VARCHAR(50),
    status VARCHAR(20) DEFAULT 'active',
    last_used TIMESTAMPTZ,
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 19. settings - Platform settings
CREATE TABLE settings (
    setting_key VARCHAR(255) PRIMARY KEY,
    setting_value JSONB NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_users_client_id ON users(client_id);
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_role ON users(role);
CREATE INDEX idx_api_keys_user_id ON api_keys(user_id);
CREATE INDEX idx_api_keys_hash ON api_keys(key_hash);

CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ==================================================
-- SEED DATA (Default client for initial setup)
-- ==================================================

INSERT INTO clients (client_id, client_name, email, company, status)
VALUES ('00000000-0000-0000-0000-000000000001', 'Default Client', 'admin@localhost', 'Internal', 'active')
ON CONFLICT (client_id) DO NOTHING;
