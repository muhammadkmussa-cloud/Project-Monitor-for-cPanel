from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import model_validator
from functools import lru_cache


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql://monitor_admin:changeme@postgres:5432/project_monitor"

    # Redis
    redis_url: str = "redis://redis:6379/0"

    # Monitoring Agent
    monitoring_agent_host: str = "0.0.0.0"
    monitoring_agent_port: int = 8000

    # DeepSeek AI
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-chat"
    deepseek_base_url: str = "https://api.deepseek.com"

    # Telegram
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    telegram_enabled: bool = True

    # Backup
    local_backup_path: str = "/app/backups"

    # Remediation
    auto_remediation_enabled: bool = True
    require_human_approval_above: str = "moderate"
    max_remediation_attempts: int = 3

    # Verification
    verification_delay_seconds: int = 30
    max_verification_attempts: int = 3

    # Email
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    email_enabled: bool = True

    # Slack
    slack_webhook_url: str = ""
    slack_bot_token: str = ""
    slack_enabled: bool = True

    # Data Retention
    data_retention_days: int = 90
    archive_enabled: bool = True

    # Rate Limiting
    rate_limit_enabled: bool = True
    rate_limit_default: int = 100
    rate_limit_window: int = 60

    # Multi-Tenancy
    multi_tenancy_enabled: bool = True

    # SSH
    ssh_known_hosts: str = "/keys/known_hosts"
    ssh_timeout: int = 30
    ssh_retry_attempts: int = 3

    # Security
    cors_origins: str = "http://localhost:3005,http://127.0.0.1:3005"
    n8n_base_url: str = "http://n8n:5678"
    jwt_secret: str = "changeme"
    api_secret_key: str = "changeme"

    # Thresholds
    disk_warning_threshold: int = 75
    disk_critical_threshold: int = 90
    cpu_warning_threshold: int = 80
    cpu_critical_threshold: int = 95
    ram_warning_threshold: int = 80
    ram_critical_threshold: int = 95
    ssl_warning_days: int = 30
    ssl_critical_days: int = 7
    response_time_warning_ms: int = 2000
    response_time_critical_ms: int = 5000

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")

    @model_validator(mode="after")
    def validate_secrets(self):
        if len(self.jwt_secret) < 32 or self.api_secret_key == "changeme":
            raise ValueError("Set a JWT_SECRET of at least 32 characters and a non-default API_SECRET_KEY")
        return self


@lru_cache()
def get_settings() -> Settings:
    return Settings()
