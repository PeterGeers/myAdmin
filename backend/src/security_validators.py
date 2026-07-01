"""
Security Validators

Reusable validation and sanitization utilities for security checks:
- Input validation against injection patterns
- Input sanitization by field type
- SQL injection detection in queries
- File upload validation
- XSS vulnerability detection in templates
- Password strength checking

Extracted from security_audit.py to separate validators from audit reporting.
"""

import re
import os
import logging
from typing import Dict

import bleach

logger = logging.getLogger(__name__)

# Default validation patterns
INPUT_VALIDATION_RULES = {
    "username": r"^[a-zA-Z0-9_]{3,20}$",
    "email": r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$",
    "password": r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{8,}$",
    "filename": r"^[a-zA-Z0-9_\-\.]{1,255}$",
    "url": r"^(https?:\/\/)?([\da-z\.-]+)\.([a-z\.]{2,6})([\/\w \.-]*)*\/?$",
}


def validate_input(
    input_data, field_type, max_length=None, validation_rules=None
) -> Dict:
    """Validate input data against security rules."""
    if not input_data:
        return {"valid": False, "error": "Input cannot be empty"}

    rules = validation_rules or INPUT_VALIDATION_RULES

    # Check for common injection patterns
    injection_patterns = [
        r"[\'\";\\]",
        r"<script.*?>.*?</script>",
        r"javascript:",
        r"&#x?[0-9a-f]+;",
        r"/\*.*?\*/",
        r"{{.*?}}",
        r"(\b(ALTER|CREATE|DELETE|DROP|EXEC(UTE)?|INSERT( +INTO)?|MERGE|SELECT|UPDATE|UNION( +ALL)?)\b)",
        r"(\b(OR|AND)\b.*?=)",
    ]

    for pattern in injection_patterns:
        if re.search(pattern, str(input_data), re.IGNORECASE):
            return {"valid": False, "error": "Potential injection pattern detected"}

    # Validate against field type rules
    if field_type in rules:
        pattern = rules[field_type]
        if not re.match(pattern, str(input_data)):
            return {
                "valid": False,
                "error": f"Input does not match {field_type} pattern",
            }

    # Check length
    if max_length and len(str(input_data)) > max_length:
        return {
            "valid": False,
            "error": f"Input exceeds maximum length of {max_length} characters",
        }

    # Sanitize input
    sanitized = sanitize_input(input_data, field_type, rules)

    return {
        "valid": True,
        "original": str(input_data),
        "sanitized": sanitized,
        "length": len(str(input_data)),
    }


def sanitize_input(input_data, field_type="text", validation_rules=None) -> str:
    """Sanitize input data based on field type."""
    if not input_data:
        return ""

    rules = validation_rules or INPUT_VALIDATION_RULES
    input_str = str(input_data)

    if field_type == "html":
        allowed_tags = ["p", "br", "b", "i", "u", "em", "strong", "a", "ul", "ol", "li"]
        allowed_attrs = {"a": ["href", "title"]}
        return bleach.clean(
            input_str, tags=allowed_tags, attributes=allowed_attrs, strip=True
        )

    elif field_type == "url":
        if re.match(rules.get("url", ""), input_str):
            return input_str
        return ""

    elif field_type == "email":
        if re.match(rules.get("email", ""), input_str):
            return input_str.lower()
        return ""

    else:
        sanitized = bleach.clean(input_str, tags=[], attributes={}, strip=True)
        sanitized = re.sub(r"[\x00-\x1F\x7F]", "", sanitized)
        return sanitized.strip()


def check_sql_injection(query, params=None) -> Dict:
    """Check SQL query for potential injection vulnerabilities."""
    audit_result = {"query": query, "safe": True, "issues": [], "recommendations": []}

    if "+" in query or "STRING_CONCAT" in query.upper():
        audit_result["issues"].append(
            "Potential SQL injection: string concatenation detected"
        )
        audit_result["safe"] = False

    if re.search(r"\bFROM\s+\w+\s*\+\s*\w+", query, re.IGNORECASE):
        audit_result["issues"].append(
            "Potential SQL injection: dynamic table name detected"
        )
        audit_result["safe"] = False

    if params is None and re.search(r"VALUES\s*\([^)]*\)", query):
        audit_result["issues"].append(
            "Potential SQL injection: inline VALUES detected without parameters"
        )
        audit_result["safe"] = False

    injection_patterns = [
        r"1\s*=\s*1",
        r"OR\s+1\s*=\s*1",
        r"OR\s+\"\"=\"\"",
        r"OR\s+\'\'=\'\'",
        r"UNION\s+SELECT",
        r"EXEC\s+",
        r"DROP\s+TABLE",
        r"INSERT\s+INTO",
        r"DELETE\s+FROM",
    ]

    for pattern in injection_patterns:
        if re.search(pattern, query, re.IGNORECASE):
            audit_result["issues"].append(
                f"Potential SQL injection pattern detected: {pattern}"
            )
            audit_result["safe"] = False

    if not audit_result["safe"]:
        audit_result["recommendations"] = [
            "Use parameterized queries instead of string concatenation",
            "Use ORM methods instead of raw SQL when possible",
            "Validate all user input before using in queries",
            "Implement proper database user permissions",
            "Use prepared statements for all database operations",
        ]

    return audit_result


def validate_file_upload(file, allowed_types=None, max_size=None) -> Dict:
    """Validate file upload security."""
    if not file or not hasattr(file, "filename"):
        return {"valid": False, "error": "No file provided"}

    validation_result = {
        "filename": file.filename,
        "content_type": file.content_type,
        "size": len(file.read()) if hasattr(file, "read") else 0,
        "valid": True,
        "issues": [],
        "sanitized_filename": "",
    }

    if hasattr(file, "seek"):
        file.seek(0)

    filename, file_extension = os.path.splitext(file.filename)
    if not file_extension:
        validation_result["issues"].append("No file extension")
        validation_result["valid"] = False

    if allowed_types:
        if file_extension.lower() not in [f".{ext.lower()}" for ext in allowed_types]:
            validation_result["issues"].append(
                f"File type {file_extension} not allowed"
            )
            validation_result["valid"] = False

    if max_size and validation_result["size"] > max_size:
        validation_result["issues"].append(
            f"File size {validation_result['size']} exceeds maximum {max_size}"
        )
        validation_result["valid"] = False

    dangerous_extensions = [
        ".php",
        ".php3",
        ".php4",
        ".php5",
        ".phtml",
        ".pl",
        ".py",
        ".rb",
        ".asp",
        ".aspx",
        ".jsp",
        ".exe",
        ".bat",
        ".cmd",
        ".sh",
    ]
    if file_extension.lower() in dangerous_extensions:
        validation_result["issues"].append(
            f"Dangerous file type detected: {file_extension}"
        )
        validation_result["valid"] = False

    sanitized_filename = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", filename)
    validation_result["sanitized_filename"] = f"{sanitized_filename}{file_extension}"

    if validation_result["size"] > 0:
        file.seek(0)
        content = file.read(1024)

        malware_signatures = [b"<?php", b"<script>", b"eval(", b"javascript:", b"MZ"]

        for signature in malware_signatures:
            if signature in content:
                validation_result["issues"].append(
                    f"Potential malware signature detected: {signature}"
                )
                validation_result["valid"] = False

        file.seek(0)

    if validation_result["issues"]:
        validation_result["recommendations"] = [
            "Use strict file type validation",
            "Implement file size limits",
            "Scan files with antivirus software",
            "Store files outside web root with proper permissions",
            "Use random filenames to prevent directory traversal",
            "Implement virus scanning for uploaded files",
        ]

    return validation_result


def check_xss_vulnerabilities(template_content) -> Dict:
    """Check templates for XSS vulnerabilities."""
    xss_audit = {
        "template": template_content[:500] + "..."
        if len(template_content) > 500
        else template_content,
        "vulnerabilities": [],
        "safe": True,
        "recommendations": [],
    }

    unsafe_patterns = [
        (r"{{.*?}}", "Unsafe template variable interpolation"),
        (r"{\{.*?\}}", "Unsafe template expression"),
        (r"\|safe", "Unsafe filter usage"),
        (r"\|raw", "Unsafe raw filter"),
        (r"autoescape.*?false", "Autoescape disabled"),
        (r"Markup\(.*?\)", "Unsafe Markup usage"),
    ]

    for pattern, description in unsafe_patterns:
        if re.search(pattern, template_content):
            xss_audit["vulnerabilities"].append(description)
            xss_audit["safe"] = False

    if not re.search(r"\|escape|autoescape", template_content):
        xss_audit["vulnerabilities"].append("No output escaping detected")

    if not xss_audit["safe"]:
        xss_audit["recommendations"] = [
            "Use autoescaping in templates",
            "Escape all user-provided content",
            "Use safe filters instead of raw/unsafe",
            "Implement Content Security Policy headers",
            "Use template inheritance with proper escaping",
            "Sanitize all user input before rendering",
        ]

    return xss_audit


def check_password_strength(password) -> Dict:
    """Check password strength and security."""
    if not password:
        return {"strong": False, "score": 0, "issues": ["No password provided"]}

    strength_check = {
        "password": password,
        "length": len(password),
        "has_uppercase": bool(re.search(r"[A-Z]", password)),
        "has_lowercase": bool(re.search(r"[a-z]", password)),
        "has_digits": bool(re.search(r"[0-9]", password)),
        "has_special": bool(re.search(r"[^A-Za-z0-9]", password)),
        "common_password": False,
        "score": 0,
        "issues": [],
    }

    common_passwords = [
        "password",
        "123456",
        "12345678",
        "qwerty",
        "abc123",
        "password1",
    ]
    if password.lower() in common_passwords:
        strength_check["common_password"] = True
        strength_check["issues"].append("Common password detected")

    if strength_check["length"] >= 8:
        strength_check["score"] += 1
    if strength_check["length"] >= 12:
        strength_check["score"] += 1
    if strength_check["has_uppercase"]:
        strength_check["score"] += 1
    if strength_check["has_lowercase"]:
        strength_check["score"] += 1
    if strength_check["has_digits"]:
        strength_check["score"] += 1
    if strength_check["has_special"]:
        strength_check["score"] += 1

    if strength_check["length"] < 8:
        strength_check["issues"].append("Password too short (minimum 8 characters)")
    if not strength_check["has_uppercase"]:
        strength_check["issues"].append("No uppercase letters")
    if not strength_check["has_lowercase"]:
        strength_check["issues"].append("No lowercase letters")
    if not strength_check["has_digits"]:
        strength_check["issues"].append("No digits")
    if not strength_check["has_special"]:
        strength_check["issues"].append("No special characters")

    strength_check["strong"] = (
        strength_check["score"] >= 4 and not strength_check["issues"]
    )

    if not strength_check["strong"]:
        strength_check["recommendations"] = [
            "Use at least 12 characters",
            "Include uppercase and lowercase letters",
            "Add numbers and special characters",
            "Avoid common words and patterns",
            "Use a password manager to generate strong passwords",
            "Consider using passphrases instead of passwords",
        ]

    return strength_check
