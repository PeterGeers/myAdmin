"""
Log Sanitizer Utility

Provides masking functions to prevent sensitive values (API keys, passwords,
encryption keys, OAuth secrets, JWT keys) from appearing in application logs.

Usage:
    from utils.log_sanitizer import mask_sensitive_value

    # Returns "[REDACTED]" for known sensitive key patterns
    safe_value = mask_sensitive_value("api_key", "sk-abc123...")
"""

import re
from typing import Any


# Patterns that indicate a key name holds sensitive data.
# Case-insensitive matching is applied at check time.
SENSITIVE_KEY_PATTERNS = [
    re.compile(r"api[_\-\s]?key", re.IGNORECASE),
    re.compile(r"password", re.IGNORECASE),
    re.compile(r"encryption[_\-\s]?key", re.IGNORECASE),
    re.compile(r"oauth[_\-\s]?(client[_\-\s]?)?secret", re.IGNORECASE),
    re.compile(r"jwt[_\-\s]?(signing[_\-\s]?)?key", re.IGNORECASE),
    re.compile(r"secret[_\-\s]?key", re.IGNORECASE),
    re.compile(r"access[_\-\s]?token", re.IGNORECASE),
    re.compile(r"refresh[_\-\s]?token", re.IGNORECASE),
    re.compile(r"private[_\-\s]?key", re.IGNORECASE),
    re.compile(r"client[_\-\s]?secret", re.IGNORECASE),
]

REDACTED = "[REDACTED]"


def mask_sensitive_value(key: str, value: Any) -> str:
    """
    Mask a value if the key name matches known sensitive patterns.

    Args:
        key: The configuration/variable key name (e.g., "api_key", "db_password")
        value: The value associated with the key

    Returns:
        "[REDACTED]" if the key matches a sensitive pattern, otherwise str(value).
    """
    if is_sensitive_key(key):
        return REDACTED
    return str(value)


def is_sensitive_key(key: str) -> bool:
    """
    Check if a key name matches any known sensitive pattern.

    Args:
        key: The key name to check

    Returns:
        True if the key matches a sensitive pattern, False otherwise.
    """
    for pattern in SENSITIVE_KEY_PATTERNS:
        if pattern.search(key):
            return True
    return False
