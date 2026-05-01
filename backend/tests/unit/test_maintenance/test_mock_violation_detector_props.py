"""
Property-based tests for MockViolationDetector
===============================================

Uses Hypothesis to verify that the detector correctly identifies all
mock violations and produces no false positives for properly mocked code.

Properties tested:
    - Property 1: Mock violation detection accuracy
    - Property 2: Issue completeness invariant
"""

from __future__ import annotations

import os
import tempfile
import textwrap

import pytest
from hypothesis import given, settings, HealthCheck, strategies as st

from scripts.test_maintenance.mock_violation_detector import (
    MockViolation,
    MockViolationDetector,
    VALID_SEVERITIES,
    VALID_VIOLATION_TYPES,
)


# ---------------------------------------------------------------------------
# Helpers — generate test file content with controlled violations
# ---------------------------------------------------------------------------

def _build_test_source(
    *,
    has_mysql_import: bool = False,
    has_mysql_from_import: bool = False,
    has_env_leak: bool = False,
    has_hardcoded_db_name: bool = False,
    has_real_connection: bool = False,
    has_db_manager_test_mode: bool = False,
    has_setup_test_table: bool = False,
    has_proper_mock_db: bool = False,
    has_patch_dict_env: bool = False,
    has_mock_env_fixture: bool = False,
    has_patched_mysql: bool = False,
    has_patched_db_manager: bool = False,
) -> str:
    """Build a synthetic test file with the requested violation patterns.

    Each boolean flag toggles a specific pattern on or off.  The "proper"
    flags add correctly-mocked code that should NOT trigger violations.
    """
    lines = [
        "import os",
        "import pytest",
        "from unittest.mock import patch, MagicMock",
        "",
    ]

    # --- Violation patterns ------------------------------------------------

    if has_mysql_import:
        lines.append("import mysql.connector")

    if has_mysql_from_import:
        lines.append("from mysql.connector import connect")

    lines.append("")

    if has_patched_mysql:
        lines.append("@patch('mysql.connector.connect')")

    if has_patched_db_manager:
        lines.append("@patch('database.DatabaseManager')")

    if has_mock_env_fixture:
        lines.append("def test_with_mock_env(mock_env):")
    else:
        lines.append("def test_example():")

    if has_patch_dict_env:
        lines.append("    with patch.dict(os.environ, {'DB_NAME': 'test'}):")
        if has_env_leak:
            # env leak inside patch.dict — should NOT be flagged
            lines.append("        name = os.environ['DB_NAME']")
        lines.append("        pass")
    elif has_env_leak:
        lines.append("    name = os.environ['DB_NAME']")

    if has_hardcoded_db_name:
        if has_patch_dict_env or has_mock_env_fixture:
            # Inside safe context — should NOT be flagged
            lines.append("    db = 'testfinance'  # mock_env")
        else:
            lines.append("    db = 'testfinance'")

    if has_real_connection:
        lines.append("    conn = mysql.connector.connect(host='localhost')")

    if has_db_manager_test_mode:
        lines.append("    dm = DatabaseManager(test_mode=True)")

    if has_proper_mock_db:
        lines.append("    # Uses mock_db fixture — no violations expected")
        lines.append("    mock_db.execute_query.return_value = []")

    lines.append("    assert True")
    lines.append("")

    if has_setup_test_table:
        lines.append("@pytest.fixture")
        lines.append("def setup_test_table():")
        lines.append("    # Creates real tables in the database")
        lines.append("    yield")
        lines.append("")

    return "\n".join(lines)


def _write_temp_py(source: str) -> str:
    """Write *source* to a temporary ``.py`` file and return its path.

    The caller is responsible for cleanup (or can rely on OS temp cleanup).
    """
    fd, path = tempfile.mkstemp(suffix=".py", prefix="test_prop_")
    try:
        os.write(fd, source.encode("utf-8"))
    finally:
        os.close(fd)
    return path


# ---------------------------------------------------------------------------
# Property 1: Mock violation detection accuracy
# ---------------------------------------------------------------------------

# Feature: test-maintenance-framework, Property 1: Mock violation detection accuracy
class TestMockViolationDetectionAccuracy:
    """For any test file content with zero or more violations, the detector
    correctly identifies all violations and produces no false positives for
    properly mocked code.
    """

    @settings(max_examples=100)
    @given(
        has_mysql_import=st.booleans(),
        has_mysql_from_import=st.booleans(),
        has_env_leak=st.booleans(),
        has_hardcoded_db_name=st.booleans(),
        has_real_connection=st.booleans(),
        has_db_manager_test_mode=st.booleans(),
        has_setup_test_table=st.booleans(),
    )
    def test_violations_detected_for_unguarded_patterns(
        self,
        has_mysql_import,
        has_mysql_from_import,
        has_env_leak,
        has_hardcoded_db_name,
        has_real_connection,
        has_db_manager_test_mode,
        has_setup_test_table,
    ):
        """Violations are detected when anti-patterns appear without mocking."""
        source = _build_test_source(
            has_mysql_import=has_mysql_import,
            has_mysql_from_import=has_mysql_from_import,
            has_env_leak=has_env_leak,
            has_hardcoded_db_name=has_hardcoded_db_name,
            has_real_connection=has_real_connection,
            has_db_manager_test_mode=has_db_manager_test_mode,
            has_setup_test_table=has_setup_test_table,
        )

        path = _write_temp_py(source)
        try:
            detector = MockViolationDetector()
            violations = detector.analyze_file(path)
            violation_types = [v.violation_type for v in violations]

            # db_import violations
            if has_mysql_import or has_mysql_from_import:
                assert "db_import" in violation_types, (
                    f"Expected db_import violation for mysql import. "
                    f"Source:\n{source}"
                )

            # env_leak violations
            if has_env_leak or has_hardcoded_db_name:
                assert "env_leak" in violation_types, (
                    f"Expected env_leak violation. "
                    f"Source:\n{source}"
                )

            # real_connection violations
            if has_real_connection or has_db_manager_test_mode or has_setup_test_table:
                assert "real_connection" in violation_types, (
                    f"Expected real_connection violation. "
                    f"Source:\n{source}"
                )
        finally:
            os.unlink(path)

    @settings(max_examples=100)
    @given(
        has_proper_mock_db=st.booleans(),
        use_patch_dict=st.booleans(),
        use_mock_env=st.booleans(),
        use_patched_mysql=st.booleans(),
        use_patched_db_manager=st.booleans(),
    )
    def test_no_false_positives_for_properly_mocked_code(
        self,
        has_proper_mock_db,
        use_patch_dict,
        use_mock_env,
        use_patched_mysql,
        use_patched_db_manager,
    ):
        """Properly mocked code should produce zero violations."""
        source = _build_test_source(
            has_proper_mock_db=has_proper_mock_db,
            has_patch_dict_env=use_patch_dict,
            has_mock_env_fixture=use_mock_env,
            has_patched_mysql=use_patched_mysql,
            has_patched_db_manager=use_patched_db_manager,
        )

        path = _write_temp_py(source)
        try:
            detector = MockViolationDetector()
            violations = detector.analyze_file(path)

            assert len(violations) == 0, (
                f"Expected no violations for properly mocked code, "
                f"got {len(violations)}: "
                f"{[(v.violation_type, v.description) for v in violations]}.\n"
                f"Source:\n{source}"
            )
        finally:
            os.unlink(path)

    @settings(max_examples=50)
    @given(
        has_mysql_import=st.booleans(),
        has_env_leak=st.booleans(),
    )
    def test_patched_patterns_suppress_violations(
        self,
        has_mysql_import,
        has_env_leak,
    ):
        """When anti-patterns are properly patched, they should not be flagged."""
        source = _build_test_source(
            has_mysql_import=has_mysql_import,
            has_env_leak=has_env_leak,
            # Env leaks inside patch.dict are safe
            has_patch_dict_env=has_env_leak,
            # mysql.connector.connect patched
            has_patched_mysql=True,
        )

        path = _write_temp_py(source)
        try:
            detector = MockViolationDetector()
            violations = detector.analyze_file(path)

            # Env leaks inside patch.dict should not be flagged
            env_violations = [v for v in violations if v.violation_type == "env_leak"]
            if has_env_leak:
                assert len(env_violations) == 0, (
                    f"Env leak inside patch.dict should not be flagged. "
                    f"Violations: {[(v.line_number, v.description) for v in env_violations]}"
                )
        finally:
            os.unlink(path)

    def test_empty_file_produces_no_violations(self, tmp_path):
        """An empty test file should produce zero violations."""
        test_file = tmp_path / "test_empty.py"
        test_file.write_text("", encoding="utf-8")

        detector = MockViolationDetector()
        violations = detector.analyze_file(str(test_file))
        assert violations == []

    def test_nonexistent_file_produces_no_violations(self):
        """A nonexistent file should produce zero violations."""
        detector = MockViolationDetector()
        violations = detector.analyze_file("/nonexistent/test_foo.py")
        assert violations == []

    def test_non_python_file_produces_no_violations(self, tmp_path):
        """A non-Python file should produce zero violations."""
        test_file = tmp_path / "test_file.txt"
        test_file.write_text("import mysql.connector", encoding="utf-8")

        detector = MockViolationDetector()
        violations = detector.analyze_file(str(test_file))
        assert violations == []

    def test_syntax_error_file_produces_no_violations(self, tmp_path):
        """A file with syntax errors should produce zero violations."""
        test_file = tmp_path / "test_broken.py"
        test_file.write_text("def broken(:\n    pass", encoding="utf-8")

        detector = MockViolationDetector()
        violations = detector.analyze_file(str(test_file))
        assert violations == []



# ---------------------------------------------------------------------------
# Property 2: Issue completeness invariant
# ---------------------------------------------------------------------------

# Feature: test-maintenance-framework, Property 2: Issue completeness invariant
class TestIssueCompletenessInvariant:
    """For any detected issue, it has a valid severity and all required fields.

    Every MockViolation must have:
    - file_path (non-empty string)
    - line_number (positive integer)
    - violation_type in VALID_VIOLATION_TYPES
    - severity in VALID_SEVERITIES
    - description (non-empty string)
    - suggested_fix (non-empty string)
    """

    @settings(max_examples=100)
    @given(
        has_mysql_import=st.booleans(),
        has_mysql_from_import=st.booleans(),
        has_env_leak=st.booleans(),
        has_hardcoded_db_name=st.booleans(),
        has_real_connection=st.booleans(),
        has_db_manager_test_mode=st.booleans(),
        has_setup_test_table=st.booleans(),
    )
    def test_all_violations_have_valid_fields(
        self,
        has_mysql_import,
        has_mysql_from_import,
        has_env_leak,
        has_hardcoded_db_name,
        has_real_connection,
        has_db_manager_test_mode,
        has_setup_test_table,
    ):
        """Every violation produced by the detector has all required fields
        with valid values."""
        source = _build_test_source(
            has_mysql_import=has_mysql_import,
            has_mysql_from_import=has_mysql_from_import,
            has_env_leak=has_env_leak,
            has_hardcoded_db_name=has_hardcoded_db_name,
            has_real_connection=has_real_connection,
            has_db_manager_test_mode=has_db_manager_test_mode,
            has_setup_test_table=has_setup_test_table,
        )

        path = _write_temp_py(source)
        try:
            detector = MockViolationDetector()
            violations = detector.analyze_file(path)

            for v in violations:
                # file_path must be non-empty
                assert isinstance(v.file_path, str) and v.file_path, (
                    f"Violation has empty file_path: {v}"
                )

                # line_number must be a positive integer
                assert isinstance(v.line_number, int) and v.line_number > 0, (
                    f"Violation has invalid line_number={v.line_number}: {v}"
                )

                # violation_type must be in the valid set
                assert v.violation_type in VALID_VIOLATION_TYPES, (
                    f"Violation has invalid type '{v.violation_type}', "
                    f"expected one of {VALID_VIOLATION_TYPES}: {v}"
                )

                # severity must be in the valid set
                assert v.severity in VALID_SEVERITIES, (
                    f"Violation has invalid severity '{v.severity}', "
                    f"expected one of {VALID_SEVERITIES}: {v}"
                )

                # description must be non-empty
                assert isinstance(v.description, str) and v.description.strip(), (
                    f"Violation has empty description: {v}"
                )

                # suggested_fix must be non-empty
                assert isinstance(v.suggested_fix, str) and v.suggested_fix.strip(), (
                    f"Violation has empty suggested_fix: {v}"
                )
        finally:
            os.unlink(path)

    def test_violation_dataclass_fields_exist(self):
        """MockViolation dataclass has all required fields."""
        v = MockViolation(
            file_path="test.py",
            line_number=1,
            violation_type="db_import",
            severity="critical",
            description="Test violation",
            suggested_fix="Fix it",
        )
        assert v.file_path == "test.py"
        assert v.line_number == 1
        assert v.violation_type == "db_import"
        assert v.severity == "critical"
        assert v.description == "Test violation"
        assert v.suggested_fix == "Fix it"
