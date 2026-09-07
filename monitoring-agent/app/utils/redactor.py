import re
from typing import List


class Redactor:
    """Redacts sensitive information from logs and output."""

    PATTERNS = [
        (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S), "[PRIVATE KEY REDACTED]"),
        (re.compile(r'(?i)(password|passwd|pwd)\s*[=:]\s*\S+'), r'\1=REDACTED'),
        (re.compile(r'(?i)(api[_-]?key|apikey)\s*[=:]\s*\S+'), r'\1=REDACTED'),
        (re.compile(r'(?i)(secret|token)\s*[=:]\s*\S+'), r'\1=REDACTED'),
        (re.compile(r'(?i)(ssh[_-]?key|private[_-]?key)\s*[=:]\s*\S+'), r'\1=REDACTED'),
        (re.compile(r'-----BEGIN (RSA |DSA |EC )?PRIVATE KEY-----'), '-----BEGIN PRIVATE KEY-----REDACTED'),
        (re.compile(r'(?i)(Bearer\s+[A-Za-z0-9\-._~+/]+=*)'), 'Bearer REDACTED'),
        (re.compile(r'(?i)(Authorization:\s*Basic\s+[A-Za-z0-9+/]+=*)'), 'Authorization: Basic REDACTED'),
        (re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'), 'EMAIL@REDACTED.com'),
        (re.compile(r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b'), 'IP.REDACTED'),
        (re.compile(r'(?i)(db[_-]?pass|database[_-]?pass)\s*[=:]\s*\S+'), r'\1=REDACTED'),
        (re.compile(r'(?i)connection[_-]?string\s*[=:]\s*\S+'), r'connection_string=REDACTED'),
    ]

    def redact(self, text: str) -> str:
        """Redact sensitive information from text."""
        result = text
        for pattern, replacement in self.PATTERNS:
            result = pattern.sub(replacement, result)
        return result

    def redact_dict(self, data: dict) -> dict:
        """Redact sensitive values in a dictionary."""
        redacted = {}
        for key, value in data.items():
            if isinstance(value, str):
                redacted[key] = self.redact(value)
            elif isinstance(value, dict):
                redacted[key] = self.redact_dict(value)
            elif isinstance(value, list):
                redacted[key] = [
                    self.redact_dict(item) if isinstance(item, dict)
                    else self.redact(item) if isinstance(item, str)
                    else item
                    for item in value
                ]
            else:
                redacted[key] = value
        return redacted


redactor = Redactor()
