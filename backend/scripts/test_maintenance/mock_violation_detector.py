"""
Mock Violation Detector — AST-based scanning for test anti-patterns
===================================================================

Detects unit tests that access real external resources (database connections,
environment variables, APIs) without proper mocking.  Uses the Python ``ast``
module for import and call detection, and regex for string-pattern matching.

Detection rules
---------------

+----------------------------------------------+----------+-----------------------------------+
| Pattern                                      | Severity | Type                              |
+==============================================+==========+===================================+
| ``import mysql.connector`` in unit test      | critical | db_import                         |
+----------------------------------------------+----------+-----------------------------------+
| ``from mysql.connector import …``            | critical | db_import                         |
+----------------------------------------------+----------+-----------------------------------+
| ``mysql.connector.connect(`` without @patch  | critical | real_connection                   |
+----------------------------------------------+----------+-----------------------------------+
| ``DatabaseManager(test_mode=True)`` w/o mock | critical | real_connection                   |
+----------------------------------------------+----------+-----------------------------------+
| ``os.environ['DB_NAME']`` without patch.dict | high     | env_leak                          |
+----------------------------------------------+----------+-----------------------------------+
| ``'testfinance'`` literal in unit test       | high     | env_leak                          |
+----------------------------------------------+----------+-----------------------------------+
| ``setup_test_table`` fixture creating tables | critical | real_connection                   |
+----------------------------------------------+----------+-----------------------------------+

Only stdlib dependencies are used: ``ast``, ``os``, ``re``, ``pathlib``,
``logging``, ``dataclasses``.
"""

from __future__ import annotations

import ast
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Set

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class MockViolation:
    """A single mock-related violation detected in a test file.

    Attributes:
        file_path: Path to the file containing the violation.
        line_number: 1-based line number where the violation occurs.
        violation_type: Category — ``"db_import"``, ``"env_leak"``,
            or ``"real_connection"``.
        severity: One of ``"critical"``, ``"high"``, ``"medium"``, ``"low"``.
        description: Human-readable explanation of the violation.
        suggested_fix: Recommended remediation.
    """

    file_path: str
    line_number: int
    violation_type: str
    severity: str
    description: str
    suggested_fix: str


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_SEVERITIES = {"critical", "high", "medium", "low"}
VALID_VIOLATION_TYPES = {"db_import", "env_leak", "real_connection"}

# Environment variable names that reference real database resources.
_DB_ENV_VARS: Set[str] = {
    "DB_HOST",
    "DB_PORT",
    "DB_USER",
    "DB_PASSWORD",
    "DB_NAME",
    "TEST_DB_NAME",
    "DATABASE_URL",
}

# Hardcoded database name literals that indicate a real-resource dependency.
_HARDCODED_DB_NAMES = re.compile(
    r"""(?:['"])(?:testfinance|finance)(?:['"])""",
    re.IGNORECASE,
)

# Pattern for ``setup_test_table`` fixture definitions that create real tables.
_SETUP_TABLE_PATTERN = re.compile(
    r"""def\s+setup_test_table\b""",
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class MockViolationDetector:
    """Detects real database/API/env usage in unit tests.

    The detector analyses Python test files using the ``ast`` module for
    structural checks (imports, function calls) and regex for string-level
    pattern matching (hardcoded DB names, fixture definitions).

    Typical usage::

        detector = MockViolationDetector()
        violations = detector.analyze_file("backend/tests/unit/test_foo.py")
        for v in violations:
            print(f"{v.file_path}:{v.line_number} [{v.severity}] {v.description}")
    """

    def analyze_file(self, file_path: str) -> List[MockViolation]:
        """Analyze a single test file for mock violations.

        Args:
            file_path: Path to the ``.py`` test file to analyze.

        Returns:
            A list of :class:`MockViolation` instances.  Returns an empty
            list when the file cannot be read or parsed.
        """
        path = Path(file_path)

        if not path.exists():
            logger.warning("File does not exist: %s", path)
            return []

        if not path.suffix == ".py":
            logger.debug("Skipping non-Python file: %s", path)
            return []

        try:
            source = path.read_text(encoding="utf-8")
        except (PermissionError, OSError) as exc:
            logger.error("Error reading file %s: %s", path, exc)
            return []

        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError as exc:
            logger.warning(
                "Syntax error in %s (line %s): %s — skipping file",
                path,
                exc.lineno,
                exc.msg,
            )
            return []

        file_str = str(path)
        violations: List[MockViolation] = []

        # Collect names that are patched in this file so we can suppress
        # false positives for properly-mocked code.
        patched_targets = _collect_patched_targets(tree, source)

        violations.extend(self.detect_db_imports(tree, file_str))
        violations.extend(self.detect_env_leaks(tree, source, file_str))
        violations.extend(
            self.detect_real_connections(tree, file_str, patched_targets)
        )

        return violations

    # ------------------------------------------------------------------
    # Detection methods
    # ------------------------------------------------------------------

    def detect_db_imports(
        self,
        ast_tree: ast.Module,
        file_path: str = "",
    ) -> List[MockViolation]:
        """Flag direct ``mysql.connector`` imports in unit tests.

        Detects both ``import mysql.connector`` and
        ``from mysql.connector import …`` statements.

        Args:
            ast_tree: Parsed AST of the test file.
            file_path: Path string used in violation reports.

        Returns:
            List of :class:`MockViolation` for each offending import.
        """
        violations: List[MockViolation] = []

        for node in ast.walk(ast_tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if _is_mysql_connector_module(alias.name):
                        violations.append(MockViolation(
                            file_path=file_path,
                            line_number=node.lineno,
                            violation_type="db_import",
                            severity="critical",
                            description=(
                                f"Direct import of '{alias.name}' in unit "
                                f"test. Unit tests must not import the "
                                f"database driver directly."
                            ),
                            suggested_fix=(
                                "Remove the mysql.connector import and use "
                                "the 'mock_db' fixture from conftest.py "
                                "instead: from database import DatabaseManager"
                            ),
                        ))

            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if _is_mysql_connector_module(module):
                    names = ", ".join(
                        alias.name for alias in (node.names or [])
                    )
                    violations.append(MockViolation(
                        file_path=file_path,
                        line_number=node.lineno,
                        violation_type="db_import",
                        severity="critical",
                        description=(
                            f"Direct import from '{module}' ({names}) in "
                            f"unit test. Unit tests must not import the "
                            f"database driver directly."
                        ),
                        suggested_fix=(
                            "Remove the mysql.connector import and use "
                            "the 'mock_db' fixture from conftest.py "
                            "instead."
                        ),
                    ))

        return violations

    def detect_env_leaks(
        self,
        ast_tree: ast.Module,
        source: str,
        file_path: str = "",
    ) -> List[MockViolation]:
        """Flag ``os.environ`` access to DB-related vars without ``patch.dict``.

        Also detects hardcoded database name literals (e.g. ``'testfinance'``)
        that are not inside a ``patch.dict`` context.

        Args:
            ast_tree: Parsed AST of the test file.
            source: Raw source text of the file (for regex matching).
            file_path: Path string used in violation reports.

        Returns:
            List of :class:`MockViolation` for each env-leak issue.
        """
        violations: List[MockViolation] = []

        # Collect line numbers that are inside a patch.dict context (or
        # inside a function that receives ``mock_env`` as a parameter) so
        # we can suppress false positives.
        patched_env_lines = _collect_patch_dict_lines(ast_tree)

        # --- AST-based: os.environ[KEY] and os.environ.get(KEY) ----------
        for node in ast.walk(ast_tree):
            env_var = _extract_environ_key(node)
            if env_var is not None and env_var in _DB_ENV_VARS:
                if node.lineno not in patched_env_lines:
                    violations.append(MockViolation(
                        file_path=file_path,
                        line_number=node.lineno,
                        violation_type="env_leak",
                        severity="high",
                        description=(
                            f"Access to os.environ['{env_var}'] without "
                            f"patch.dict context. This reads real "
                            f"environment variables at runtime."
                        ),
                        suggested_fix=(
                            "Use the 'mock_env' fixture from conftest.py, "
                            "or wrap the access in "
                            "patch.dict(os.environ, {…})."
                        ),
                    ))

        # --- Regex-based: hardcoded DB name literals ---------------------
        source_lines = source.splitlines()
        for line_idx, line in enumerate(source_lines, start=1):
            if line_idx in patched_env_lines:
                continue
            if _HARDCODED_DB_NAMES.search(line):
                # Skip lines that are inside a patch.dict call or a
                # mock_env fixture definition.
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                if "patch.dict" in line:
                    continue
                if "mock_env" in line:
                    continue
                # Skip lines that are assertions checking mock_env values
                if "assert" in line and "os.environ" in line:
                    continue
                violations.append(MockViolation(
                    file_path=file_path,
                    line_number=line_idx,
                    violation_type="env_leak",
                    severity="high",
                    description=(
                        "Hardcoded database name literal found. This "
                        "couples the test to a specific database name."
                    ),
                    suggested_fix=(
                        "Use the 'mock_env' fixture to provide database "
                        "names via environment variables instead of "
                        "hardcoding them."
                    ),
                ))

        # --- Regex-based: setup_test_table fixture -----------------------
        for line_idx, line in enumerate(source_lines, start=1):
            if _SETUP_TABLE_PATTERN.search(line):
                violations.append(MockViolation(
                    file_path=file_path,
                    line_number=line_idx,
                    violation_type="real_connection",
                    severity="critical",
                    description=(
                        "Fixture 'setup_test_table' creates real database "
                        "tables. Unit tests must not perform DDL against "
                        "a real database."
                    ),
                    suggested_fix=(
                        "Remove the setup_test_table fixture and use the "
                        "'mock_db' fixture from conftest.py instead."
                    ),
                ))

        return violations

    def detect_real_connections(
        self,
        ast_tree: ast.Module,
        file_path: str = "",
        patched_targets: Optional[Set[str]] = None,
    ) -> List[MockViolation]:
        """Flag ``DatabaseManager(test_mode=True)`` and
        ``mysql.connector.connect()`` calls without mocking.

        Args:
            ast_tree: Parsed AST of the test file.
            file_path: Path string used in violation reports.
            patched_targets: Set of dotted names that are patched in this
                file (e.g. ``{"database.DatabaseManager",
                "mysql.connector.connect"}``).  Used to suppress false
                positives.

        Returns:
            List of :class:`MockViolation` for each real-connection issue.
        """
        if patched_targets is None:
            patched_targets = set()

        violations: List[MockViolation] = []

        for node in ast.walk(ast_tree):
            if not isinstance(node, ast.Call):
                continue

            call_name = _get_call_name(node)
            if call_name is None:
                continue

            # --- mysql.connector.connect() ---
            if call_name == "mysql.connector.connect":
                if not _is_target_patched(
                    "mysql.connector.connect", patched_targets
                ):
                    violations.append(MockViolation(
                        file_path=file_path,
                        line_number=node.lineno,
                        violation_type="real_connection",
                        severity="critical",
                        description=(
                            "Direct call to mysql.connector.connect() "
                            "without a mock. This creates a real database "
                            "connection."
                        ),
                        suggested_fix=(
                            "Use the 'mock_db' fixture from conftest.py "
                            "instead of calling mysql.connector.connect() "
                            "directly."
                        ),
                    ))

            # --- DatabaseManager(test_mode=True) ---
            elif call_name in ("DatabaseManager", "database.DatabaseManager"):
                if _has_test_mode_true(node):
                    if not _is_target_patched(
                        "database.DatabaseManager", patched_targets
                    ) and not _is_target_patched(
                        "DatabaseManager", patched_targets
                    ):
                        violations.append(MockViolation(
                            file_path=file_path,
                            line_number=node.lineno,
                            violation_type="real_connection",
                            severity="critical",
                            description=(
                                "DatabaseManager(test_mode=True) creates a "
                                "real database connection. Unit tests must "
                                "not connect to real databases."
                            ),
                            suggested_fix=(
                                "Use the 'mock_db' fixture from conftest.py "
                                "instead of instantiating DatabaseManager "
                                "directly."
                            ),
                        ))

        return violations


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _is_mysql_connector_module(name: str) -> bool:
    """Return ``True`` if *name* is ``mysql.connector`` or a sub-module."""
    return name == "mysql.connector" or name.startswith("mysql.connector.")


def _get_call_name(node: ast.Call) -> Optional[str]:
    """Extract the dotted name of a function/class call, or ``None``.

    Handles simple names (``DatabaseManager(…)``) and attribute chains
    (``mysql.connector.connect(…)``).
    """
    func = node.func
    parts: List[str] = []

    while isinstance(func, ast.Attribute):
        parts.append(func.attr)
        func = func.value

    if isinstance(func, ast.Name):
        parts.append(func.id)
    else:
        return None

    parts.reverse()
    return ".".join(parts)


def _has_test_mode_true(call_node: ast.Call) -> bool:
    """Return ``True`` if the call has ``test_mode=True`` as a keyword arg."""
    for kw in call_node.keywords:
        if kw.arg == "test_mode":
            if isinstance(kw.value, ast.Constant) and kw.value.value is True:
                return True
    return False


def _extract_environ_key(node: ast.AST) -> Optional[str]:
    """If *node* is ``os.environ['KEY']`` or ``os.environ.get('KEY')``,
    return the key string.  Otherwise return ``None``.
    """
    # os.environ['KEY'] → ast.Subscript
    if isinstance(node, ast.Subscript):
        if _is_os_environ(node.value):
            key = _get_string_constant(node.slice)
            return key

    # os.environ.get('KEY') → ast.Call
    if isinstance(node, ast.Call):
        func = node.func
        if (
            isinstance(func, ast.Attribute)
            and func.attr == "get"
            and _is_os_environ(func.value)
            and node.args
        ):
            return _get_string_constant(node.args[0])

    return None


def _is_os_environ(node: ast.AST) -> bool:
    """Return ``True`` if *node* represents ``os.environ``."""
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "environ"
        and isinstance(node.value, ast.Name)
        and node.value.id == "os"
    )


def _get_string_constant(node: ast.AST) -> Optional[str]:
    """Extract a string constant from an AST node, or ``None``."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _collect_patched_targets(
    tree: ast.Module,
    source: str,
) -> Set[str]:
    """Collect dotted names that are patched via ``@patch`` or ``with patch``.

    This is a best-effort heuristic: it looks for ``patch('target')`` and
    ``patch.object(…)`` calls in decorators and ``with`` statements.

    Returns:
        A set of target strings (e.g. ``{"database.DatabaseManager",
        "mysql.connector.connect"}``).
    """
    targets: Set[str] = set()

    for node in ast.walk(tree):
        # @patch('some.target') decorator
        if isinstance(node, ast.Call):
            call_name = _get_call_name(node)
            if call_name in ("patch", "unittest.mock.patch", "mock.patch"):
                if node.args:
                    target = _get_string_constant(node.args[0])
                    if target:
                        targets.add(target)

    # Also scan source text for patch() calls that may be harder to
    # extract via AST (e.g. multi-line decorators).
    for match in re.finditer(
        r"""(?:@\s*)?patch\(\s*['"]([^'"]+)['"]\s*\)""",
        source,
    ):
        targets.add(match.group(1))

    return targets


def _collect_patch_dict_lines(tree: ast.Module) -> Set[int]:
    """Collect line numbers that are inside a ``patch.dict(os.environ, …)``
    context (decorator or ``with`` statement), or inside a function that
    accepts ``mock_env`` as a pytest fixture parameter.

    The ``mock_env`` fixture from conftest.py internally uses
    ``patch.dict(os.environ, …)``, so any function receiving it is safe.

    Returns a set of line numbers where env access is considered safe.
    """
    safe_lines: Set[int] = set()

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Decorator: @patch.dict(os.environ, {…})
            for decorator in node.decorator_list:
                if _is_patch_dict_environ(decorator):
                    for lineno in range(
                        node.lineno, _end_lineno(node) + 1
                    ):
                        safe_lines.add(lineno)

            # Fixture parameter: def test_foo(self, mock_env):
            if _has_mock_env_param(node):
                for lineno in range(
                    node.lineno, _end_lineno(node) + 1
                ):
                    safe_lines.add(lineno)

        # With statement: with patch.dict(os.environ, {…}):
        if isinstance(node, ast.With):
            for item in node.items:
                if _is_patch_dict_environ(item.context_expr):
                    for lineno in range(
                        node.lineno, _end_lineno(node) + 1
                    ):
                        safe_lines.add(lineno)

    return safe_lines


def _is_patch_dict_environ(node: ast.AST) -> bool:
    """Return ``True`` if *node* is a ``patch.dict(os.environ, …)`` call."""
    if not isinstance(node, ast.Call):
        return False

    call_name = _get_call_name(node)
    if call_name not in ("patch.dict", "unittest.mock.patch.dict", "mock.patch.dict"):
        return False

    # First argument should be os.environ
    if node.args:
        return _is_os_environ(node.args[0])

    return False


def _has_mock_env_param(node: ast.FunctionDef) -> bool:
    """Return ``True`` if the function has ``mock_env`` in its parameter list.

    The ``mock_env`` fixture from conftest.py uses ``patch.dict(os.environ)``
    internally, so any test function receiving it as a parameter is safe to
    access ``os.environ``.
    """
    for arg in node.args.args:
        if arg.arg == "mock_env":
            return True
    return False


def _is_target_patched(target: str, patched_targets: Set[str]) -> bool:
    """Check whether *target* (or a parent) is in *patched_targets*.

    For example, if ``"database.DatabaseManager"`` is patched, then
    ``"database.DatabaseManager"`` is considered patched.  We also check
    partial matches: patching ``"database.mysql.connector.connect"`` covers
    ``"mysql.connector.connect"``.
    """
    if target in patched_targets:
        return True

    # Check if any patched target ends with the target name.
    for patched in patched_targets:
        if patched.endswith(f".{target}") or patched.endswith(target):
            return True

    return False


def _end_lineno(node: ast.AST) -> int:
    """Return the end line number of an AST node.

    Falls back to ``node.lineno`` when ``end_lineno`` is not available
    (Python < 3.8, though we target 3.8+).
    """
    return getattr(node, "end_lineno", None) or getattr(node, "lineno", 0)
