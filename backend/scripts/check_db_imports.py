"""CI lint rule: flag direct mysql.connector imports outside the abstraction layer.

Scans all .py files using AST parsing and reports any `import mysql.connector`
or `from mysql.connector ...` statement found outside the allowed files.

Usage:
    python backend/scripts/check_db_imports.py

Exit code 0 = clean, 1 = violations found.
"""

import ast
import sys
from pathlib import Path

# Configurable allowed files (relative to project root, posix-style paths)
ALLOWED_FILES = {
    'backend/src/database.py',
    'backend/src/scalability_manager.py',
}

# Directories to skip during scanning (virtual envs, dependencies, caches, etc.)
EXCLUDED_DIRS = {
    '.venv', 'venv', 'env', '.env',
    'node_modules',
    '.git',
    '__pycache__',
    '.hypothesis',
    '.tox',
    '.mypy_cache',
    '.pytest_cache',
    'mysql_data',
    '.kiro',
}

# Project directories to scan
SCAN_DIRS = ['backend', 'scripts']


def check_file(filepath: Path, allowed_files: set[str] | None = None) -> list[str]:
    """Return list of violation messages for a single file.

    Args:
        filepath: Path to the Python file to check.
        allowed_files: Optional set of allowed file paths (posix-style).
                       If provided and filepath matches, returns empty list.
                       If None, no allow-list filtering is applied.

    Returns:
        List of violation message strings. Empty if file is clean or allowed.
    """
    if allowed_files is not None:
        rel = str(filepath.as_posix())
        if rel in allowed_files:
            return []

    violations = []
    try:
        tree = ast.parse(filepath.read_text(encoding='utf-8'))
    except (SyntaxError, PermissionError, UnicodeDecodeError):
        return violations

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == 'mysql.connector' or alias.name.startswith('mysql.connector.'):
                    violations.append(
                        f"{filepath}:{node.lineno}: direct import '{alias.name}' — "
                        f"use 'from database import DatabaseManager' or "
                        f"'from db_exceptions import DatabaseError' instead"
                    )
        elif isinstance(node, ast.ImportFrom):
            if node.module and (
                node.module == 'mysql.connector'
                or node.module.startswith('mysql.connector.')
            ):
                violations.append(
                    f"{filepath}:{node.lineno}: direct import from '{node.module}' — "
                    f"use 'from database import DatabaseManager' or "
                    f"'from db_exceptions import DatabaseError' instead"
                )
    return violations


def _iter_py_files(root: Path, excluded_dirs: set[str] | None = None):
    """Yield .py files under root, skipping excluded directories.

    Args:
        root: Directory to scan recursively.
        excluded_dirs: Directory names to skip. Defaults to EXCLUDED_DIRS.

    Yields:
        Path objects for each .py file found.
    """
    if excluded_dirs is None:
        excluded_dirs = EXCLUDED_DIRS

    for entry in sorted(root.iterdir()):
        if entry.is_dir():
            if entry.name in excluded_dirs:
                continue
            yield from _iter_py_files(entry, excluded_dirs)
        elif entry.is_file() and entry.suffix == '.py':
            yield entry


def scan_directory(root: Path, allowed_files: set[str] | None = None,
                   excluded_dirs: set[str] | None = None) -> list[str]:
    """Scan all .py files under root for mysql.connector import violations.

    Args:
        root: Directory to scan recursively.
        allowed_files: Set of allowed file paths (posix-style, relative to root).
                       Defaults to ALLOWED_FILES if None.
        excluded_dirs: Directory names to skip. Defaults to EXCLUDED_DIRS.

    Returns:
        List of all violation message strings found.
    """
    if allowed_files is None:
        allowed_files = ALLOWED_FILES

    all_violations = []
    for py_file in _iter_py_files(root, excluded_dirs):
        rel = str(py_file.relative_to(root).as_posix())
        if rel in allowed_files:
            continue
        all_violations.extend(check_file(py_file))
    return all_violations


def main():
    """CLI entry point. Scans project directories and exits with appropriate code."""
    root = Path('.')
    all_violations = []

    for scan_dir in SCAN_DIRS:
        dir_path = root / scan_dir
        if not dir_path.is_dir():
            continue
        for py_file in _iter_py_files(dir_path):
            rel = str(py_file.as_posix())
            if rel in ALLOWED_FILES:
                continue
            all_violations.extend(check_file(py_file))

    if all_violations:
        print(f"Found {len(all_violations)} mysql.connector import violation(s):\n")
        for v in all_violations:
            print(f"  ❌ {v}")
        print(f"\nAll database access must go through DatabaseManager (database.py).")
        sys.exit(1)
    else:
        print("✅ No direct mysql.connector imports found outside allowed files.")
        sys.exit(0)


if __name__ == '__main__':
    main()
