"""
Architectural test: No direct S3 write/delete operations outside the Asset Gateway.

Enforces Requirement 9 (Exclusive Asset Gateway) by scanning source files for
direct boto3 S3 write/delete calls that should go through MediaAssetService.

Allow-listed files:
- media_asset_service.py: The exclusive gateway itself
- s3_shared_storage.py: Internal _upload_raw/_delete_raw methods
- s3_tenant_storage.py: Internal _upload_raw/_delete_raw methods
- storage_resolver.py: Folder marker creation (excluded from registry)
- tenant_admin_storage.py: Health check validation (connectivity test)
"""

import os
import re
from pathlib import Path

import pytest


# Files allowed to contain S3 write/delete operations
ALLOWED_FILES = {
    'media_asset_service.py',
    's3_shared_storage.py',
    's3_tenant_storage.py',
    'storage_resolver.py',
    'tenant_admin_storage.py',
}

# Patterns that indicate direct S3 write/delete operations
FORBIDDEN_PATTERNS = [
    re.compile(r'\bput_object\s*\('),
    re.compile(r'\bdelete_object\s*\('),
    re.compile(r'\bcopy_object\s*\('),
]

# Pattern descriptions for error messages
PATTERN_NAMES = {
    r'\bput_object\s*\(': 'put_object',
    r'\bdelete_object\s*\(': 'delete_object',
    r'\bcopy_object\s*\(': 'copy_object',
}


def _is_code_line(line: str) -> bool:
    """Check if a line is actual code (not a comment or docstring delimiter)."""
    stripped = line.strip()
    if stripped.startswith('#'):
        return False
    if stripped.startswith('"""') or stripped.startswith("'''"):
        return False
    return True


def _is_inside_string(line: str, match_start: int) -> bool:
    """
    Simple heuristic to check if a match position is inside a string literal.
    Counts unescaped quotes before the match position.
    """
    prefix = line[:match_start]
    # Count single and double quotes (not escaped)
    single_quotes = len(re.findall(r"(?<!\\)'", prefix))
    double_quotes = len(re.findall(r'(?<!\\)"', prefix))
    # If odd number of either quote type, we're inside a string
    return (single_quotes % 2 == 1) or (double_quotes % 2 == 1)


def _get_src_directory() -> Path:
    """Get the backend/src directory path."""
    # Navigate from tests/architecture/ up to backend/src/
    test_dir = Path(__file__).parent
    backend_dir = test_dir.parent.parent
    src_dir = backend_dir / 'src'
    return src_dir


def _scan_file(filepath: Path) -> list[dict]:
    """
    Scan a single Python file for forbidden S3 operation patterns.

    Returns a list of violations with file, line number, and content.
    """
    violations = []
    try:
        content = filepath.read_text(encoding='utf-8')
    except (UnicodeDecodeError, OSError):
        return violations

    in_multiline_string = False
    multiline_delimiter = None

    for line_num, line in enumerate(content.splitlines(), start=1):
        stripped = line.strip()

        # Track multiline string state (triple quotes)
        if not in_multiline_string:
            if stripped.startswith('"""') or stripped.startswith("'''"):
                delimiter = stripped[:3]
                # Check if it closes on the same line (e.g., """docstring""")
                rest = stripped[3:]
                if delimiter not in rest:
                    in_multiline_string = True
                    multiline_delimiter = delimiter
                continue
        else:
            if multiline_delimiter in stripped:
                in_multiline_string = False
                multiline_delimiter = None
            continue

        # Skip comment lines
        if not _is_code_line(line):
            continue

        # Check each forbidden pattern
        for pattern in FORBIDDEN_PATTERNS:
            match = pattern.search(line)
            if match and not _is_inside_string(line, match.start()):
                pattern_name = PATTERN_NAMES.get(pattern.pattern, pattern.pattern)
                violations.append({
                    'file': str(filepath),
                    'line': line_num,
                    'content': stripped,
                    'pattern': pattern_name,
                })

    return violations


@pytest.mark.architecture
def test_no_direct_s3_writes_outside_asset_gateway():
    """
    Verify that no Python file outside the allow-list contains direct
    S3 write/delete operations (put_object, delete_object, copy_object).

    This enforces Requirement 9: all S3 mutations must go through
    the MediaAssetService gateway.
    """
    src_dir = _get_src_directory()
    assert src_dir.exists(), f"Source directory not found: {src_dir}"

    all_violations = []

    for py_file in sorted(src_dir.rglob('*.py')):
        filename = py_file.name

        # Skip allowed files
        if filename in ALLOWED_FILES:
            continue

        # Skip __pycache__ directories
        if '__pycache__' in str(py_file):
            continue

        violations = _scan_file(py_file)
        all_violations.extend(violations)

    if all_violations:
        # Build a clear error message listing all violations
        msg_lines = [
            "",
            "=" * 70,
            "ARCHITECTURAL VIOLATION: Direct S3 write/delete operations detected!",
            "=" * 70,
            "",
            "All S3 write/delete operations must go through MediaAssetService.",
            f"Found {len(all_violations)} violation(s) in non-allowlisted files:",
            "",
        ]
        for v in all_violations:
            # Show path relative to src/ for readability
            rel_path = os.path.relpath(v['file'], str(src_dir))
            msg_lines.append(
                f"  {rel_path}:{v['line']} [{v['pattern']}]"
            )
            msg_lines.append(f"    > {v['content']}")
            msg_lines.append("")

        msg_lines.extend([
            "Allowed files: " + ", ".join(sorted(ALLOWED_FILES)),
            "",
            "To fix: route S3 operations through MediaAssetService or add",
            "the file to the ALLOWED_FILES set with justification.",
            "=" * 70,
        ])

        pytest.fail("\n".join(msg_lines))
