# Architecture

## System Overview

Project Monitor is a multi-project monitoring platform built with three core layers:

```
Internet
   |
   v
┌─────────────────────────────────────────┐
│              Docker Network              │
├─────────────────────────────────────────┤
│                                         │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐│
│  │   n8n   │  │Monitoring│  │PostgreSQL││
│  │         │  │  Agent   │  │         ││
│  └────┬────┘  └────┬────┘  └─────────┘│
│       │            │                   │
│       └──────┬─────┘                   │
│              │                         │
│         ┌────┴────┐                    │
│         │  Redis  │                    │
│         └─────────┘                    │
└─────────────────────────────────────────┘
```

## Layer 1: n8n (Orchestration)

Responsible for:
- Scheduling monitoring checks
- Project iteration
- Workflow execution
- Notification delivery
- Approval handling
- Incident orchestration

## Layer 2: Monitoring Agent (Backend Service)

Python/FastAPI application handling:
- SSH connections to monitored servers
- Controlled command execution
- Log collection and processing
- Health checks
- Server diagnostics
- Incident detection
- AI diagnosis integration
- Telegram notifications

## Layer 3: PostgreSQL (Data)

Stores:
- Projects and clients
- Monitoring configurations
- Incidents and events
- AI diagnoses
- Audit logs
- System health

## Data Flow

```
CRON Trigger
    |
    v
Get Enabled Projects
    |
    v
Loop Projects
    |
    +---> Health Check
    +---> Collect Metrics
    +---> Collect Logs
    |
    v
Detect Incident?
    |
    +---> NO: Record Health
    +---> YES: Create Incident
              |
              v
         AI Diagnosis
              |
              v
         Severity Decision
              |
              +---> LOW: Auto-resolve
              +---> HIGH: Alert user
              +---> CRITICAL: Request approval
```

## Security Model

### Safety Levels

1. **SAFE**: Read-only operations (auto-approved)
2. **APPROVAL_REQUIRED**: Modifications (human approval needed)
3. **BLOCKED**: Destructive operations (never allowed)

### Credential Isolation

- Per-project SSH keys
- Encrypted credential storage
- No cross-client access
- Secrets redacted from AI

## Multi-Tenancy

Every important record includes:
- `client_id`: Tenant isolation
- `project_id`: Project scoping

## Database Schema

16 tables covering:
- `clients`, `projects`, `project_credentials`
- `monitoring_checks`, `incidents`, `incident_events`
- `ai_diagnoses`, `fix_proposals`, `approvals`
- `backup_records`, `remediation_runs`, `verification_runs`
- `deployments`, `audit_logs`, `notifications`, `system_health`
