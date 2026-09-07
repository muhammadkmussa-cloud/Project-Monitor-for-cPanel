# Environment Variables

## Required

| Variable | Description | Default |
|----------|-------------|---------|
| `POSTGRES_PASSWORD` | PostgreSQL password | `changeme` |
| `JWT_SECRET` | JWT token signing secret (64-char hex) | `changeme` |
| `API_SECRET_KEY` | API key signing secret | `changeme` |

## PostgreSQL

| Variable | Description | Default |
|----------|-------------|---------|
| `POSTGRES_DB` | Database name | `project_monitor` |
| `POSTGRES_USER` | Database user | `monitor_admin` |
| `POSTGRES_PASSWORD` | Database password | `changeme` |
| `DATABASE_URL` | Full connection URL | auto-constructed |

## Redis

| Variable | Description | Default |
|----------|-------------|---------|
| `REDIS_URL` | Redis connection URL | `redis://redis:6379/0` |

## DeepSeek AI (optional)

| Variable | Description | Default |
|----------|-------------|---------|
| `DEEPSEEK_API_KEY` | DeepSeek API key | empty |
| `DEEPSEEK_MODEL` | Model name | `deepseek-chat` |
| `DEEPSEEK_BASE_URL` | API base URL | `https://api.deepseek.com` |

## Telegram (optional)

| Variable | Description | Default |
|----------|-------------|---------|
| `TELEGRAM_BOT_TOKEN` | Telegram bot token | empty |
| `TELEGRAM_CHAT_ID` | Telegram chat ID | empty |
| `TELEGRAM_ENABLED` | Enable notifications | `true` |

## Email (optional)

| Variable | Description | Default |
|----------|-------------|---------|
| `SMTP_HOST` | SMTP server | empty |
| `SMTP_PORT` | SMTP port | `587` |
| `SMTP_USER` | SMTP username | empty |
| `SMTP_PASSWORD` | SMTP password | empty |
| `SMTP_FROM` | Sender email | empty |
| `EMAIL_ENABLED` | Enable email | `true` |

## Slack (optional)

| Variable | Description | Default |
|----------|-------------|---------|
| `SLACK_WEBHOOK_URL` | Slack webhook URL | empty |
| `SLACK_BOT_TOKEN` | Slack bot token | empty |
| `SLACK_ENABLED` | Enable Slack | `true` |

## SSH

| Variable | Description | Default |
|----------|-------------|---------|
| `SSH_TIMEOUT` | SSH timeout (seconds) | `30` |
| `SSH_RETRY_ATTEMPTS` | SSH retry count | `3` |

## Remediation

| Variable | Description | Default |
|----------|-------------|---------|
| `AUTO_REMEDIATION_ENABLED` | Enable auto-remediation | `true` |
| `REQUIRE_HUMAN_APPROVAL_ABOVE` | Safety level for approval | `moderate` |
| `MAX_REMEDIATION_ATTEMPTS` | Max attempts before rollback | `3` |

## Data Retention

| Variable | Description | Default |
|----------|-------------|---------|
| `DATA_RETENTION_DAYS` | Days to retain data | `90` |
| `ARCHIVE_ENABLED` | Enable archival | `true` |

## Monitoring Thresholds

| Variable | Description | Default |
|----------|-------------|---------|
| `DISK_WARNING_THRESHOLD` | Disk warning % | `75` |
| `DISK_CRITICAL_THRESHOLD` | Disk critical % | `90` |
| `CPU_WARNING_THRESHOLD` | CPU warning % | `80` |
| `CPU_CRITICAL_THRESHOLD` | CPU critical % | `95` |
| `RAM_WARNING_THRESHOLD` | RAM warning % | `80` |
| `RAM_CRITICAL_THRESHOLD` | RAM critical % | `95` |
| `SSL_WARNING_DAYS` | SSL expiry warning days | `30` |
| `SSL_CRITICAL_DAYS` | SSL expiry critical days | `7` |
| `RESPONSE_TIME_WARNING_MS` | Response time warning (ms) | `2000` |
| `RESPONSE_TIME_CRITICAL_MS` | Response time critical (ms) | `5000` |

## Production Only

| Variable | Description | Default |
|----------|-------------|---------|
| `DOMAIN_NAME` | Domain for SSL/nginx | `localhost` |
