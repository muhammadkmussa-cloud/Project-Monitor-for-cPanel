from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID


class ProjectCreate(BaseModel):
    client_id: UUID
    project_name: str = Field(..., max_length=255)
    domain: Optional[str] = None
    server_host: Optional[str] = None
    ssh_port: int = Field(default=22, ge=1, le=65535)
    ssh_username: Optional[str] = None
    credential_reference: Optional[str] = None
    connection_type: str = "ssh"
    project_path: Optional[str] = None
    application_type: str = "other"
    framework: Optional[str] = None
    environment: str = "production"
    health_check_url: Optional[str] = None
    repository_url: Optional[str] = None
    repository_branch: str = "main"
    monitoring_enabled: bool = True
    remediation_enabled: bool = False
    auto_restart_enabled: bool = False
    log_locations: List[str] = []
    check_interval: int = Field(default=300, ge=60, le=86400)
    thresholds: Dict[str, Any] = {}


class ProjectResponse(BaseModel):
    project_id: UUID
    client_id: UUID
    project_name: str
    domain: Optional[str]
    server_host: Optional[str]
    ssh_port: int = Field(default=22, ge=1, le=65535)
    ssh_username: Optional[str] = None
    connection_type: str
    project_path: Optional[str] = None
    health_check_url: Optional[str] = None
    application_type: str
    framework: Optional[str] = None
    environment: str
    monitoring_enabled: bool
    check_interval: int = Field(default=300, ge=60, le=86400)
    current_status: str
    remediation_enabled: bool = False
    created_at: datetime
    updated_at: datetime
    last_check_at: Optional[datetime]


class IncidentCreate(BaseModel):
    project_id: UUID
    client_id: UUID
    category: str
    severity: str
    error_signature: Optional[str] = None
    raw_error_reference: Optional[str] = None
    affected_component: Optional[str] = None
    details: Dict[str, Any] = {}


class IncidentResponse(BaseModel):
    incident_id: UUID
    project_id: UUID
    client_id: UUID
    category: str
    severity: str
    status: str
    error_signature: Optional[str]
    affected_component: Optional[str]
    first_seen: datetime
    last_seen: datetime
    occurrence_count: int
    created_at: datetime


class HealthCheckResult(BaseModel):
    status: str
    http_status_code: Optional[int] = None
    response_time_ms: Optional[int] = None
    ssl_days_remaining: Optional[int] = None
    details: Dict[str, Any] = {}


class ServerStats(BaseModel):
    cpu_percent: float
    memory_percent: float
    disk_percent: float
    load_average: List[float]
    uptime: int
    details: Dict[str, Any] = {}


class DiscoveryResult(BaseModel):
    os_info: str
    cpu_info: str
    memory_total: str
    disk_info: str
    php_version: Optional[str] = None
    node_version: Optional[str] = None
    python_version: Optional[str] = None
    framework: Optional[str] = None
    web_server: Optional[str] = None
    git_info: Optional[Dict[str, Any]] = None
    project_structure: List[str] = []
    log_locations: List[str] = []


class LogEntry(BaseModel):
    timestamp: Optional[str] = None
    level: str
    message: str
    source: Optional[str] = None
    metadata: Dict[str, Any] = {}


class SSHTestResult(BaseModel):
    success: bool
    message: str
    host: Optional[str] = None
    username: Optional[str] = None
    os_info: Optional[str] = None


class DiagnosisRequest(BaseModel):
    incident_id: UUID
    include_logs: bool = True
    include_server_stats: bool = True
    include_git_info: bool = True


class DiagnosisResponse(BaseModel):
    diagnosis_id: UUID
    incident_id: UUID
    severity: str
    category: str
    root_cause: str
    evidence: List[str]
    affected_component: str
    confidence: float
    proposed_fix: str
    files_affected: List[str]
    commands_required: List[str]
    risk_level: str
    rollback_plan: str
    verification_plan: List[str]
    requires_human_approval: bool
    created_at: datetime


class ApprovalRequest(BaseModel):
    incident_id: UUID
    diagnosis_id: UUID
    action: str  # approve, reject, manual
    notes: Optional[str] = None


class ApprovalResponse(BaseModel):
    approval_id: UUID
    incident_id: UUID
    diagnosis_id: UUID
    action: str
    status: str
    approved_by: Optional[str]
    approved_at: Optional[datetime]
    notes: Optional[str]


class RemediationPlanRequest(BaseModel):
    incident_id: UUID
    diagnosis_id: UUID
    approval_id: Optional[UUID] = None
    server_connection: Optional[Dict[str, Any]] = None


class RemediationActionItem(BaseModel):
    action_type: str
    description: str
    command: Optional[str] = None
    file_path: Optional[str] = None
    content: Optional[str] = None
    requires_approval: bool = False
    safety_level: str = "safe"


class RemediationPlanResponse(BaseModel):
    plan_id: UUID
    incident_id: UUID
    actions: List[RemediationActionItem]
    total_actions: int
    requires_approval: bool
    status: str
    created_at: datetime


class RemediationExecuteRequest(BaseModel):
    plan_id: UUID
    incident_id: UUID
    approval_id: Optional[UUID] = None
    server_connection: Optional[Dict[str, Any]] = None
    expected_url: Optional[str] = None


class RemediationResultResponse(BaseModel):
    result_id: UUID
    incident_id: UUID
    plan_id: UUID
    success: bool
    status: str
    executed_actions: int
    failed_actions: int
    backup_id: Optional[str]
    verification_passed: Optional[bool]
    verification_outcome: str = "UNAVAILABLE"
    verification_details: Dict[str, Any] = {}
    rolled_back: bool
    results: List[Dict[str, Any]]
    created_at: datetime


class BackupResponse(BaseModel):
    backup_id: str
    incident_id: str
    created_at: str
    files_backed_up: int
    files_failed: int
    status: str


class RollbackRequest(BaseModel):
    incident_id: UUID
    backup_id: str
    server_connection: Optional[Dict[str, Any]] = None


class VerificationResult(BaseModel):
    check_name: str
    passed: bool
    details: Dict[str, Any] = {}
    error: Optional[str] = None


class NotificationRequest(BaseModel):
    incident_id: UUID
    message: str
    severity: str = "info"
    channel: str = "telegram"


class CredentialCreate(BaseModel):
    name: str = "default"
    credential_type: str = "ssh"  # ssh | sftp
    host: Optional[str] = None
    port: int = 22
    username: Optional[str] = None
    password: Optional[str] = None
    private_key: Optional[str] = None
    key_path: Optional[str] = None


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=1024)

class UserCreate(BaseModel):
    client_id: UUID
    email: str = Field(min_length=3, max_length=255)
    name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=10, max_length=1024)
    role: str = 'user'

class APIKeyCreate(BaseModel):
    user_id: UUID
    name: str = Field(min_length=1, max_length=255)
    permissions: Optional[List[str]] = None
    expires_in_days: int = Field(default=90, ge=1, le=365)
