import re
from typing import Optional


def validate_domain(domain: str) -> bool:
    """Validate a domain name."""
    pattern = re.compile(
        r'^(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$'
    )
    return bool(pattern.match(domain))


def validate_ip(ip: str) -> bool:
    """Validate an IPv4 address."""
    pattern = re.compile(
        r'^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$'
    )
    return bool(pattern.match(ip))


def validate_url(url: str) -> bool:
    """Validate a URL."""
    pattern = re.compile(
        r'^https?://(?:www\.)?[-a-zA-Z0-9@:%._+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b(?:[-a-zA-Z0-9()@:%_+.~#?&/=]*)$'
    )
    return bool(pattern.match(url))


def validate_ssh_port(port: int) -> bool:
    """Validate SSH port number."""
    return 1 <= port <= 65535


def validate_project_name(name: str) -> bool:
    """Validate project name."""
    return bool(name and len(name) <= 255 and name.strip())


def validate_severity(severity: str) -> bool:
    """Validate severity level."""
    return severity in ["LOW", "MEDIUM", "HIGH", "CRITICAL"]


def validate_incident_status(status: str) -> bool:
    """Validate incident status."""
    valid_statuses = [
        "OPEN", "INVESTIGATING", "AWAITING_APPROVAL", "APPROVED",
        "REMEDIATING", "RESOLVED", "FAILED", "ROLLED_BACK", "IGNORED"
    ]
    return status in valid_statuses


def validate_connection_type(conn_type: str) -> bool:
    """Validate connection type."""
    return conn_type in ["ssh", "cpanel_api", "sftp"]


def validate_application_type(app_type: str) -> bool:
    """Validate application type."""
    valid_types = [
        "php", "laravel", "wordpress", "nodejs",
        "python", "static", "api", "other"
    ]
    return app_type in valid_types
