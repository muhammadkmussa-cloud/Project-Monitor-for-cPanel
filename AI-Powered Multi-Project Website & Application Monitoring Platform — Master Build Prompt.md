You are a senior DevOps engineer, backend engineer, automation architect, security engineer, and n8n specialist.

Build a production-ready, extensible, AI-powered website and application monitoring platform using n8n as the orchestration layer.

The system will initially be developed and tested locally on my computer and later deployed to an Oracle Cloud Always Free VM.

The architecture must therefore be portable and Dockerized from the beginning.

The long-term goal is to use the platform both for:

1. Monitoring and maintaining my own websites and applications.
2. Running a future monitoring/DevOps service where multiple customers can connect many websites and applications hosted on cPanel.

The platform must be designed as a centralized multi-project supervisor.

Do NOT create a separate n8n workflow for every project.

A single platform must be able to monitor many projects through a project registry/database.

==================================================
1. PRIMARY OBJECTIVE
==================================================

Create an AI-powered project supervisor that continuously monitors registered websites and applications.

For every registered project, the system should be able to:

- monitor website availability
- monitor application health
- monitor APIs
- monitor SSL certificates
- monitor response time
- monitor server resources
- connect to cPanel servers
- connect using SSH keys
- optionally use cPanel API
- optionally use SFTP
- retrieve application and server logs
- detect errors
- detect crashes
- detect repeated failures
- diagnose problems using DeepSeek
- determine severity
- determine probable root cause
- propose a fix
- explain the evidence behind the diagnosis
- create a backup before changes
- request human approval
- apply an approved fix
- test the application afterward
- rollback automatically if verification fails
- notify me of the result
- maintain a complete audit trail

The system must prioritize safety.

The AI must never have unrestricted destructive access to servers.

==================================================
2. DEVELOPMENT APPROACH
==================================================

Development must happen locally first.

The complete system must be Dockerized so it can later be deployed to Oracle Cloud with minimal changes.

The same configuration should work in:

LOCAL DEVELOPMENT
↓
TESTING
↓
ORACLE CLOUD

Use environment variables and secrets instead of hardcoded configuration.

Create:

- docker-compose.yml
- .env.example
- Dockerfiles where necessary
- database migrations/schema
- setup scripts
- development documentation
- production deployment documentation
- Oracle Cloud deployment documentation

Do not hardcode:

- passwords
- API keys
- SSH private keys
- Telegram tokens
- database credentials
- DeepSeek credentials
- customer credentials

==================================================
3. ORACLE CLOUD TARGET
==================================================

The production deployment target is Oracle Cloud Always Free.

Design the system to run efficiently on an Oracle Cloud Always Free Ampere VM.

Target initial deployment:

- 2 OCPU
- 12 GB RAM
- Ubuntu
- Docker
- persistent storage

The architecture must be lightweight enough to operate comfortably within these constraints.

The monitoring platform itself must be separated logically into services so resource usage can be controlled.

The expected architecture is approximately:

Internet
   |
   v
Oracle Cloud VM
   |
   +-- Reverse Proxy / HTTPS
   |
   +-- n8n
   |
   +-- PostgreSQL
   |
   +-- Redis if required
   |
   +-- Monitoring/Agent Service
   |
   +-- Supporting services

Do not design the first version around expensive cloud infrastructure.

Keep the system simple, efficient, portable, and easy to upgrade later.

==================================================
4. CORE ARCHITECTURE
==================================================

Build the platform around these layers.

LAYER 1 — N8N

n8n is the orchestration and workflow layer.

Responsible for:

- scheduling
- project iteration
- workflow execution
- notifications
- approval handling
- calling services
- reporting
- incident orchestration

LAYER 2 — MONITORING / AGENT SERVICE

Create a dedicated backend/service for controlled server operations.

This service should handle:

- SSH connections
- controlled command execution
- log collection
- file inspection
- health checks
- server diagnostics
- application diagnostics
- Git inspection
- backups
- remediation
- rollback
- verification

Do NOT make n8n responsible for unrestricted low-level server administration.

LAYER 3 — DATABASE

Use PostgreSQL.

PostgreSQL stores:

- projects
- clients
- monitoring configurations
- incidents
- logs metadata
- diagnoses
- proposed fixes
- approvals
- remediation runs
- backups
- deployments
- audit logs
- monitoring history

==================================================
5. MULTI-PROJECT DESIGN
==================================================

The system must use a Project Registry.

The user must be able to add a project without modifying the core monitoring workflows.

Example:

Project 001
Project 002
Project 003
Project 004
...
Project N

The monitoring engine should automatically process all enabled projects.

Create a projects table with at least:

- project_id
- client_id
- project_name
- domain
- server_host
- ssh_port
- ssh_username
- credential_reference
- connection_type
- project_path
- application_type
- framework
- environment
- health_check_url
- repository_url
- repository_branch
- monitoring_enabled
- remediation_enabled
- auto_restart_enabled
- log_locations
- check_interval
- created_at
- updated_at
- last_check_at
- current_status

Do not store plaintext secrets in PostgreSQL.

==================================================
6. FUTURE MULTI-TENANT DESIGN
==================================================

Even though the first version may only be used by me, design the data model for future customers.

Every important record should be associated with:

- client_id
- project_id

Potential future tenants:

Client A
- Site 1
- Site 2
- API 1

Client B
- Site 1
- Site 2
- Site 3

Client C
- Site 1

Prevent cross-client access.

A project belonging to Client A must never be accessible through Client B's workflows or credentials.

==================================================
7. PROJECT ONBOARDING
==================================================

Create an onboarding mechanism that allows a new project to be registered easily.

The eventual user experience should be:

ADD PROJECT

Project Name
Domain

Connection Type:

- SSH
- cPanel API
- SFTP

Server Host
Port
Username
Credential

Application Type:

- PHP
- Laravel
- WordPress
- Node.js
- Python
- Static
- API
- Other

Project Path

Health Check URL

Repository URL

Monitoring Interval

Monitoring Enabled

Remediation Enabled

After registration:

TEST CONNECTION

Then automatically perform safe discovery.

==================================================
8. PROJECT DISCOVERY
==================================================

When a project is first connected, perform read-only discovery.

Determine where possible:

- operating system
- CPU information
- RAM
- disk usage
- PHP version
- Node version
- Python version
- framework
- project structure
- active processes
- application process
- Git repository
- Git branch
- latest commit
- common log locations
- configured application logs
- health endpoint
- web server type
- database availability
- Redis availability where applicable

Never modify anything during discovery.

==================================================
9. CONNECTION METHODS
==================================================

Primary method:

SSH using SSH keys.

Prefer SSH over FTP because SSH allows diagnostics and controlled remediation.

Secondary method:

cPanel API.

Fallback:

SFTP.

FTP should not be the preferred management mechanism.

Use secure credential references.

Support a distinct credential per project/server whenever practical.

Do not use one master SSH credential for every customer.

==================================================
10. MONITORING ENGINE
==================================================

Create a configurable monitoring engine.

Monitor websites and applications continuously.

WEBSITE MONITORING

Check:

- HTTP status
- HTTPS availability
- response time
- redirect behavior
- DNS resolution
- SSL certificate
- SSL expiration
- uptime

APPLICATION MONITORING

Check:

- application process
- health endpoint
- API endpoints
- database connectivity
- Redis connectivity
- queues
- background workers
- application response

SERVER MONITORING

Check:

- CPU
- RAM
- disk
- load
- process count
- network
- available storage

LOG MONITORING

Monitor relevant logs such as:

- Apache logs
- Nginx logs
- cPanel logs where appropriate
- PHP errors
- Laravel logs
- Node logs
- Python logs
- WordPress logs
- application logs
- deployment logs
- queue/worker logs

Do not send entire log files to DeepSeek.

Retrieve relevant recent entries and intelligently summarize/deduplicate them before AI analysis.

==================================================
11. HEARTBEAT / HEALTH CHECK SYSTEM
==================================================

Every project should have a health endpoint where possible.

Example:

GET /health

Expected:

{
  "status": "ok"
}

For APIs, support richer checks such as:

{
  "status": "ok",
  "database": "ok",
  "redis": "ok"
}

The system should distinguish between:

- website up
- website down
- application down
- API down
- database failure
- Redis failure
- worker failure

Do not simply classify everything as "website down."

==================================================
12. INCIDENT DETECTION
==================================================

Detect:

- HTTP 500
- HTTP 502
- HTTP 503
- connection refused
- connection timeout
- PHP fatal errors
- unhandled exceptions
- Node crashes
- Python exceptions
- database failures
- Redis failures
- queue failures
- disk exhaustion
- memory exhaustion
- deployment failures
- missing dependencies
- permission problems
- missing environment variables
- missing files
- configuration errors
- certificate problems

Create incident deduplication.

If the same error occurs 10,000 times, it must not generate 10,000 separate alerts.

Create an error signature/fingerprint system.

==================================================
13. INCIDENT DATABASE
==================================================

Create an incidents table with:

- incident_id
- project_id
- client_id
- timestamp
- category
- severity
- status
- error_signature
- raw_error_reference
- affected_component
- first_seen
- last_seen
- occurrence_count
- diagnosis
- evidence
- proposed_fix
- confidence
- approval_status
- remediation_status
- verification_status
- rollback_status
- resolved_at

Possible status values:

OPEN
INVESTIGATING
AWAITING_APPROVAL
APPROVED
REMEDIATING
RESOLVED
FAILED
ROLLED_BACK
IGNORED

==================================================
14. DEEPSEEK AI
==================================================

Use the DeepSeek API as the main AI diagnosis engine.

Use structured responses and tool/function calling where appropriate.

The AI must receive only the minimum information required.

Never send:

- SSH private keys
- passwords
- API tokens
- complete .env files
- secrets
- credentials

Redact secrets before sending logs or file contents to DeepSeek.

==================================================
15. AI TOOL SYSTEM
==================================================

Do not give DeepSeek unrestricted SSH access.

Create controlled tools/functions such as:

get_project_status()
get_recent_logs()
get_error_logs()
get_server_stats()
get_process_status()
inspect_process()
read_file()
list_directory()
get_git_status()
get_recent_commits()
get_git_diff()
run_health_check()
run_safe_test()
create_backup()
generate_patch()
apply_patch()
restart_application()
rollback()
verify_application()

The tool layer must enforce permissions.

The AI can request a tool, but the tool layer decides whether the action is allowed.

==================================================
16. AI DIAGNOSIS PROMPT
==================================================

The AI should act as a senior DevOps/SRE engineer.

For every incident, ask the AI to determine:

- what happened
- when it started
- what changed before the incident
- affected component
- likely root cause
- evidence supporting the diagnosis
- alternative possible causes
- severity
- confidence
- proposed fix
- files affected
- commands required
- risks
- rollback plan
- verification plan

The AI must explicitly state when evidence is insufficient.

The AI must never invent server state.

The AI must never assume a command succeeded without receiving the actual command result.

==================================================
17. REQUIRED AI RESPONSE FORMAT
==================================================

Use structured JSON similar to:

{
  "severity": "HIGH",
  "category": "APPLICATION_ERROR",
  "root_cause": "...",
  "evidence": [
    "...",
    "..."
  ],
  "affected_component": "...",
  "confidence": 0.91,
  "proposed_fix": "...",
  "files_affected": [],
  "commands_required": [],
  "risk_level": "MEDIUM",
  "rollback_plan": "...",
  "verification_plan": [],
  "requires_human_approval": true
}

Validate the response before processing it.

If the AI returns malformed output, do not execute anything.

==================================================
18. FIX SAFETY LEVELS
==================================================

Create a strict remediation policy.

LEVEL 1 — SAFE / READ-ONLY

Examples:

- inspect logs
- inspect files
- check disk
- inspect processes
- HTTP request
- health check
- Git status
- Git diff
- non-destructive tests

These can run automatically.

LEVEL 2 — APPROVAL REQUIRED

Examples:

- edit source code
- edit configuration
- edit .env variables
- install packages
- deploy
- run migrations
- restart production application
- restart services
- modify Apache/Nginx settings
- delete files
- change permissions

These must require explicit approval.

LEVEL 3 — BLOCKED

Examples:

- delete a production database
- drop tables
- delete entire projects
- modify SSH security configuration
- expose credentials
- disable security protections
- modify another customer's project

These should be blocked by default.

==================================================
19. HUMAN APPROVAL
==================================================

Use n8n's approval/wait capabilities.

Initially use Telegram.

When an incident requires Level 2 action, send a Telegram notification.

Example message:

PROJECT ALERT

Project:
Al-Kiswah Website

Status:
CRITICAL

Detected:
PHP Fatal Error

AI Diagnosis:
Missing dependency after recent deployment.

Confidence:
94%

Proposed Fix:
Reinstall dependency and rebuild application.

Risk:
MEDIUM

Backup:
REQUIRED

Rollback:
Available

Approval:
[APPROVE]
[REJECT]

The actual buttons must be connected to n8n approval logic.

Never apply Level 2 remediation without explicit approval.

==================================================
20. BACKUPS
==================================================

Before every approved production modification:

1. Confirm the incident still exists.
2. Create a backup/checkpoint.
3. Record backup location.
4. Record timestamp.
5. Record planned changes.
6. Record incident ID.
7. Apply the fix.

Whenever possible, use Git as a checkpoint when the project is Git-managed.

Do not overwrite unrelated uncommitted changes.

==================================================
21. GIT INTEGRATION
==================================================

When Git is available:

Collect:

- current branch
- current commit
- recent commits
- uncommitted changes
- recent diff
- deployment history where available

Use Git information during diagnosis.

For example:

If an error appeared immediately after a deployment and the latest commit modified the affected component, report that relationship as evidence.

Do not claim causality with certainty unless the evidence supports it.

==================================================
22. REMEDIATION ENGINE
==================================================

After approval:

1. Re-check the project.
2. Confirm the incident still exists.
3. Create backup.
4. Apply ONLY the approved change.
5. Capture command output.
6. Run tests.
7. Run health check.
8. Inspect relevant logs again.
9. Compare system state before and after.
10. Determine whether the incident is resolved.
11. Keep the change only if verification passes.
12. Roll back automatically if verification fails.
13. Notify the user.

==================================================
23. POST-FIX VERIFICATION
==================================================

Do not consider a fix successful merely because the shell command returned exit code 0.

Verify:

- HTTP status
- health endpoint
- API endpoint
- response time
- application process
- database connection
- Redis connection where applicable
- worker status
- relevant logs
- error recurrence

Example:

Before:

HTTP 500

After:

HTTP 200
API healthy
Database healthy
No repeated fatal errors

Only then mark the incident RESOLVED.

==================================================
24. AUTOMATIC ROLLBACK
==================================================

If post-fix verification fails:

1. Stop further remediation.
2. Record failure.
3. Execute rollback.
4. Verify again.
5. Mark incident ROLLED_BACK.
6. Alert the user immediately.
7. Include the exact reason the fix failed.

Never repeatedly attempt the same failed fix without human intervention.

==================================================
25. NOTIFICATIONS
==================================================

Use Telegram initially.

Notify for:

- critical outage
- high-severity incident
- repeated application crash
- SSL expiration warning
- high disk usage
- remediation approval request
- successful remediation
- failed remediation
- automatic rollback

Prevent notification spam.

Group repeated incidents.

==================================================
26. REPORTING
==================================================

Create scheduled reports.

DAILY REPORT

Include:

- total projects
- healthy projects
- warning projects
- critical projects
- incidents
- resolved incidents
- unresolved incidents
- remediation actions
- rollbacks
- uptime
- SSL warnings
- resource warnings

WEEKLY REPORT

Include trends such as:

- most problematic projects
- repeated error categories
- successful remediation rate
- failed remediation rate
- rollback rate
- uptime trends
- average response time
- incident frequency

==================================================
27. AUDIT LOGGING
==================================================

Every important action must be recorded.

Create an audit_logs table.

Record:

- timestamp
- client_id
- project_id
- incident_id
- user
- workflow
- AI decision
- tool requested
- command
- result
- approval
- backup
- changes
- verification
- rollback
- final status

Never store secret values in audit logs.

Redact credentials from command output.

==================================================
28. N8N WORKFLOW STRUCTURE
==================================================

Do NOT create one giant workflow.

Create reusable workflows/sub-workflows:

01_PROJECT_REGISTRY
02_PROJECT_DISCOVERY
03_HEALTH_MONITOR
04_LOG_COLLECTOR
05_ERROR_DETECTOR
06_AI_DIAGNOSTIC_ENGINE
07_FIX_PROPOSAL
08_HUMAN_APPROVAL
09_BACKUP_ENGINE
10_REMEDIATION_ENGINE
11_POST_FIX_VERIFICATION
12_ROLLBACK_ENGINE
13_ALERTING
14_DAILY_REPORT
15_WEEKLY_REPORT
16_AUDIT_LOGGING

Use project_id and incident_id to connect workflow executions.

==================================================
29. WORKFLOW EXECUTION MODEL
==================================================

Main monitoring flow:

CRON
↓
GET ENABLED PROJECTS
↓
LOOP PROJECTS
↓
HEALTH CHECK
↓
COLLECT METRICS
↓
COLLECT RECENT LOGS
↓
DETECT INCIDENT
↓
IF NO INCIDENT
    RECORD HEALTH
ELSE
    CREATE/UPDATE INCIDENT
↓
AI DIAGNOSIS
↓
SEVERITY DECISION
↓
SAFE?
    YES → controlled automated action
    NO → approval request
↓
APPROVAL
↓
BACKUP
↓
REMEDIATION
↓
VERIFICATION
↓
SUCCESS?
    YES → RESOLVED
    NO → ROLLBACK
↓
NOTIFICATION
↓
AUDIT LOG
```

==================================================
30. PROJECT HEALTH STATES
==================================================

Use consistent states:

HEALTHY
WARNING
DEGRADED
CRITICAL
DOWN
UNKNOWN

Example:

HEALTHY
HTTP 200
health endpoint healthy

WARNING
SSL expires soon

DEGRADED
HTTP 200 but response time significantly increased

CRITICAL
Application health endpoint failing

DOWN
Website unreachable

UNKNOWN
Monitoring server cannot connect

==================================================
31. RESOURCE THRESHOLDS
==================================================

Make thresholds configurable per project.

Examples:

Disk:

WARNING > 75%
CRITICAL > 90%

CPU:

WARNING > configurable threshold
CRITICAL > configurable threshold

RAM:

WARNING > configurable threshold
CRITICAL > configurable threshold

SSL:

WARNING when certificate is approaching expiration
CRITICAL when expiration is imminent/expired

Do not hardcode thresholds throughout the workflow.

Store them in project configuration.

==================================================
32. SECURITY ARCHITECTURE
==================================================

Apply least privilege.

Use:

- per-project SSH keys
- restricted server users
- restricted command execution
- secure credential storage
- secret redaction
- audit logs
- explicit approval gates
- allowlisted commands where practical

Do not expose:

- private keys
- passwords
- API tokens
- environment secrets

to the DeepSeek model.

The AI may receive:

- redacted configuration
- relevant error output
- selected source snippets
- selected log lines
- Git information

only when necessary.

==================================================
33. COMMAND EXECUTION SECURITY
==================================================

Do not execute arbitrary AI-generated shell commands blindly.

Create a command policy layer.

For every command:

1. Parse requested command.
2. Determine command category.
3. Determine risk.
4. Check policy.
5. Require approval if necessary.
6. Execute with timeout.
7. Capture output.
8. Redact secrets.
9. Store audit record.

Do not allow command chaining to bypass safety controls.

==================================================
34. LOG PROCESSING
==================================================

Build intelligent log processing.

Pipeline:

RAW LOGS
↓
FILTER
↓
DEDUPLICATE
↓
ERROR SIGNATURE
↓
CONTEXT EXTRACTION
↓
RELEVANT LOG WINDOW
↓
REDACT SECRETS
↓
AI

Capture enough surrounding context to diagnose issues without sending enormous logs.

==================================================
35. COST / RESOURCE EFFICIENCY
==================================================

The system must be optimized for the Oracle Free Tier.

Do NOT call DeepSeek unnecessarily.

First use deterministic checks.

Example:

HTTP failure
↓
Check application
↓
Check process
↓
Check logs
↓
Only then call DeepSeek if diagnosis is required.

Cache repeated diagnostics where appropriate.

Do not send identical errors repeatedly to the AI.

Batch reporting where possible.

==================================================
36. OBSERVABILITY OF THE MONITORING PLATFORM
==================================================

The monitoring platform must monitor itself.

Track:

- n8n health
- PostgreSQL health
- monitoring-agent health
- disk
- memory
- CPU
- queue backlog
- failed workflow executions
- failed SSH connections
- failed AI calls

Create an internal supervisor check.

If the monitoring system itself becomes unhealthy, notify the administrator.

==================================================
37. FUTURE BUSINESS PLATFORM
==================================================

The architecture should be ready for a future SaaS monitoring business.

Potential future features:

CLIENT DASHBOARD
PROJECT DASHBOARD
INCIDENT DASHBOARD
UPTIME DASHBOARD
SSL DASHBOARD
AI DIAGNOSIS
REMEDIATION HISTORY
AUDIT HISTORY
TEAM MEMBERS
NOTIFICATION SETTINGS
BILLING
PLAN LIMITS

Potential plans:

Starter
Business
Agency
Enterprise

Do not implement complex billing initially unless necessary.

Design for it without overengineering the first version.

==================================================
38. CUSTOMER ISOLATION
==================================================

Every customer's project credentials and data must be isolated.

A customer should never be able to:

- see another customer's project
- see another customer's logs
- execute commands on another customer's server
- access another customer's credentials

Implement this at the application/database layer rather than relying solely on UI restrictions.

==================================================
39. FAILURE HANDLING
==================================================

Every workflow must handle:

- SSH timeout
- SSH authentication failure
- server unavailable
- invalid credentials
- malformed logs
- AI timeout
- AI malformed JSON
- API rate limiting
- command timeout
- command failure
- backup failure
- test failure
- rollback failure
- notification failure
- database failure

A failed monitoring action must never accidentally trigger destructive remediation.

==================================================
40. DATABASE SCHEMA
==================================================

Create proper migrations/schema for at least:

clients
projects
project_credentials
monitoring_checks
incidents
incident_events
ai_diagnoses
fix_proposals
approvals
backup_records
remediation_runs
verification_runs
deployments
audit_logs
notifications
system_health

Use foreign keys and indexes appropriately.

Add indexes for:

project_id
client_id
incident_id
status
timestamp
created_at

==================================================
41. LOCAL DEVELOPMENT
==================================================

Provide a simple local setup.

The goal should be something similar to:

git clone ...
cd project
cp .env.example .env
docker compose up -d

Then provide access to:

n8n
PostgreSQL
monitoring service

Document default local ports and configuration.

Do not require a complicated setup unless absolutely necessary.

==================================================
42. ORACLE DEPLOYMENT
==================================================

Provide a complete Oracle Cloud deployment guide.

It must cover:

- creating the Oracle Always Free VM
- selecting Ubuntu
- configuring networking
- SSH access
- opening only required ports
- installing Docker
- cloning the project
- configuring environment variables
- starting Docker Compose
- configuring HTTPS
- securing n8n
- persistent storage
- backup strategy
- restart policy
- logs
- monitoring
- update procedure

The deployment must survive reboot.

Use Docker restart policies appropriately.

==================================================
43. DOMAIN / HTTPS
==================================================

The production deployment should support a domain such as:

monitor.example.com

Use a reverse proxy with HTTPS.

Do not expose n8n unnecessarily to the public internet without authentication and TLS.

==================================================
44. FIRST RELEASE STRATEGY
==================================================

Implement in phases.

PHASE 1

Build:

- Docker environment
- PostgreSQL
- n8n
- project registry
- SSH connectivity
- project discovery
- website monitoring
- health checks
- log collection
- incident detection
- DeepSeek diagnosis
- Telegram alerts

NO AUTOMATIC PRODUCTION MODIFICATIONS YET.

PHASE 2

Add:

- AI fix proposals
- Telegram approval
- backups
- Git checkpoints
- controlled remediation

PHASE 3

Add:

- verification
- automatic rollback
- advanced monitoring
- reports
- system self-monitoring

PHASE 4

Prepare for:

- multi-client dashboard
- authentication
- client isolation
- billing
- plans
- SaaS deployment

==================================================
45. TESTING
==================================================

Do not consider the system complete until it has been tested with intentionally created failures.

Create test scenarios such as:

TEST 1
Website unavailable.

Expected:
Detect outage → alert.

TEST 2
Application throws a known error.

Expected:
Detect → collect logs → DeepSeek diagnosis → proposed fix.

TEST 3
Application process stops.

Expected:
Detect → identify process failure → propose restart.

TEST 4
Disk usage exceeds threshold.

Expected:
Warning/critical alert.

TEST 5
Broken deployment.

Expected:
Detect regression → inspect Git → diagnose.

TEST 6
Approved remediation.

Expected:
Backup → fix → test → report.

TEST 7
Failed remediation.

Expected:
Backup → fix → verification fails → rollback → alert.

TEST 8
Repeated identical error.

Expected:
Deduplicate incident and prevent alert spam.

TEST 9
SSH unavailable.

Expected:
Mark project UNKNOWN and notify appropriately without remediation.

TEST 10
Malformed DeepSeek response.

Expected:
Do not execute remediation.

==================================================
46. TEST SECURITY BOUNDARIES
==================================================

Explicitly test that the AI cannot:

- delete a database
- access another project
- read private keys
- expose passwords
- bypass approval
- execute blocked commands
- modify unrelated files

Test command-policy enforcement.

==================================================
47. DOCUMENTATION
==================================================

Create documentation for:

README
Architecture
Local setup
Environment variables
n8n setup
Database
SSH setup
cPanel setup
DeepSeek setup
Telegram setup
Project onboarding
Monitoring
Incident handling
Approval system
Remediation
Rollback
Security
Oracle deployment
Troubleshooting
Adding new monitoring types
Adding new application frameworks

==================================================
48. ENVIRONMENT VARIABLES
==================================================

Create a comprehensive .env.example.

Possible variables include:

DATABASE_URL
N8N_ENCRYPTION_KEY
DEEPSEEK_API_KEY
DEEPSEEK_MODEL
TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID
APP_BASE_URL
MONITORING_API_URL
JWT_SECRET if the management API needs authentication
REDIS_URL if Redis is used

Never commit the real .env.

==================================================
49. CODE QUALITY
==================================================

Write production-quality code.

Requirements:

- clear project structure
- strong error handling
- validation
- logging
- typing where appropriate
- modular services
- reusable components
- secure defaults
- comments for complex sections
- no unnecessary dependencies

Do not overengineer.

Prefer simple, understandable systems.

==================================================
50. DESIGN PHILOSOPHY
==================================================

The core philosophy is:

OBSERVE
↓
UNDERSTAND
↓
PROPOSE
↓
APPROVE
↓
BACKUP
↓
CHANGE
↓
VERIFY
↓
ROLLBACK IF NECESSARY
↓
REPORT

Never:

OBSERVE
↓
GUESS
↓
CHANGE PRODUCTION

The AI must act as an intelligent assistant/operator, not as an uncontrolled root user.

==================================================
51. FINAL ACCEPTANCE CRITERIA
==================================================

The project is complete only when:

1. Multiple projects can be registered.
2. Projects can use SSH credentials independently.
3. New projects do not require new workflows.
4. The system can monitor websites.
5. The system can monitor applications.
6. The system can retrieve logs.
7. The system can detect incidents.
8. DeepSeek can diagnose incidents.
9. Diagnoses include evidence and confidence.
10. The AI cannot directly perform unrestricted destructive actions.
11. Level 2 actions require approval.
12. Telegram approval works.
13. Backups occur before approved modifications.
14. Verification occurs after remediation.
15. Failed remediation triggers rollback.
16. Rollback is verified.
17. Notifications are delivered.
18. Audit logs are recorded.
19. Secrets are protected.
20. The entire system runs locally through Docker.
21. The same system can be deployed to Oracle Cloud.
22. The monitoring server can monitor itself.
23. The system is structured for future multi-client SaaS use.

==================================================
52. IMPLEMENTATION ORDER
==================================================

Do not attempt to build everything in one giant step.

Implement sequentially.

STEP 1
Create the repository and folder structure.

STEP 2
Create Docker Compose and local infrastructure.

STEP 3
Create PostgreSQL schema and migrations.

STEP 4
Create project registry.

STEP 5
Create secure credential handling.

STEP 6
Create SSH connectivity.

STEP 7
Create project discovery.

STEP 8
Create health monitoring.

STEP 9
Create log collection.

STEP 10
Create incident detection.

STEP 11
Integrate DeepSeek.

STEP 12
Create AI diagnosis.

STEP 13
Create Telegram notifications.

STEP 14
Create approval system.

STEP 15
Create backup/checkpoint system.

STEP 16
Create remediation engine.

STEP 17
Create verification.

STEP 18
Create rollback.

STEP 19
Create reporting.

STEP 20
Create monitoring-platform self-health.

STEP 21
Run complete test scenarios.

STEP 22
Harden security.

STEP 23
Prepare Oracle deployment.

STEP 24
Deploy to Oracle Cloud.

STEP 25
Connect the first real projects.

IMPORTANT:

At every phase, keep the existing functionality working.

Do not jump ahead and create destructive automation before the monitoring and approval systems have been fully tested.

Begin by inspecting the local development environment and repository.

Then create the project structure and implementation plan.

After each major phase, test the implementation before moving to the next phase.

Do not fabricate successful tests.

Report exactly what has been implemented, what has been tested, what failed, and what remains.

### One change I'd make when you give this to your agent

Don't give the agent the instruction to build the **entire thing in one shot** and let it run wild. Give it the master prompt above as the **specification**, then tell it to execute the phases sequentially.

Your first agent command after pasting the master prompt should be:

Use the master specification above as the source of truth.

Do NOT build the entire system at once.

Start with Phase 1 only.

First inspect the current local environment and repository, then create the project structure, Docker Compose setup, PostgreSQL schema/migrations, n8n setup, environment configuration, and basic documentation.

Do not implement production remediation yet.

After completing Phase 1, run the available tests and verify that the local infrastructure starts correctly.

Report:
1. Files created
2. Services created
3. Database schema created
4. Docker services running
5. Tests performed
6. Test results
7. Problems found
8. Exact next phase

Do not claim anything works unless you actually tested it.

That way, your agent has the **full destination**, but it builds the system safely one layer at a time.