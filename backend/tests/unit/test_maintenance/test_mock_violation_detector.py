"""
Unit tests for MockViolationDetector
=====================================

Tests specific anti-pattern examples, edge cases, and real-world patterns
from the project's test files.
"""

from __future__ import annotations

import textwrap

import pytest

from scripts.test_maintenance.mock_violation_detector import (
    MockViolation,
    MockViolationDetector,
    VALID_SEVERITIES,
    VALID_VIOLATION_TYPES,
)


class TestDetectDbImports:
    """Tests for direct mysql.connector import detection."""

    def test_import_mysql_connector(self, tmp_path):
        f = tmp_path / "test_sample.py"
        f.write_text("import mysql.connector\n\ndef test_x(): pass\n")
        violations = MockViolationDetector().analyze_file(str(f))
        assert any(v.violation_type == "db_import" for v in violations)

    def test_from_mysql_connector_import(self, tmp_path):
        f = tmp_path / "test_sample.py"
        f.write_text("from mysql.connector import connect\n\ndef test_x(): pass\n")
        violations = MockViolationDetector().analyze_file(str(f))
        assert any(v.violation_type == "db_import" for v in violations)

    def test_import_mysql_connector_submodule(self, tmp_path):
        f = tmp_path / "test_sample.py"
        f.write_text("import mysql.connector.errors\n\ndef test_x(): pass\n")
        violations = MockViolationDetector().analyze_file(str(f))
        assert any(v.violation_type == "db_import" for v in violations)

    def test_no_mysql_import_clean(self, tmp_path):
        f = tmp_path / "test_sample.py"
        f.write_text("import os\n\ndef test_x(): pass\n")
        violations = MockViolationDetector().analyze_file(str(f))
        assert not any(v.violation_type == "db_import" for v in violations)


class TestDetectEnvLeaks:
    """Tests for environment variable leak detection."""

    def test_os_environ_db_name(self, tmp_path):
        f = tmp_path / "test_sample.py"
        f.write_text(textwrap.dedent("""\
            import os
            def test_x():
                name = os.environ['DB_NAME']
        """))
        violations = MockViolationDetector().analyze_file(str(f))
        assert any(v.violation_type == "env_leak" for v in violations)

    def test_os_environ_get_db_host(self, tmp_path):
        f = tmp_path / "test_sample.py"
        f.write_text(textwrap.dedent("""\
            import os
            def test_x():
                host = os.environ.get('DB_HOST')
        """))
        violations = MockViolationDetector().analyze_file(str(f))
        assert any(v.violation_type == "env_leak" for v in violations)

    def test_hardcoded_testfinance(self, tmp_path):
        f = tmp_path / "test_sample.py"
        f.write_text(textwrap.dedent("""\
            def test_x():
                db = 'testfinance'
        """))
        violations = MockViolationDetector().analyze_file(str(f))
        assert any(v.violation_type == "env_leak" for v in violations)

    def test_env_inside_patch_dict_not_flagged(self, tmp_path):
        f = tmp_path / "test_sample.py"
        f.write_text(textwrap.dedent("""\
            import os
            from unittest.mock import patch
            def test_x():
                with patch.dict(os.environ, {'DB_NAME': 'test'}):
                    name = os.environ['DB_NAME']
        """))
        violations = MockViolationDetector().analyze_file(str(f))
        env_violations = [v for v in violations if v.violation_type == "env_leak"]
        assert len(env_violations) == 0

    def test_env_with_mock_env_fixture_not_flagged(self, tmp_path):
        f = tmp_path / "test_sample.py"
        f.write_text(textwrap.dedent("""\
            import os
            def test_x(mock_env):
                name = os.environ['DB_NAME']
        """))
        violations = MockViolationDetector().analyze_file(str(f))
        env_violations = [v for v in violations if v.violation_type == "env_leak"]
        assert len(env_violations) == 0

    def test_setup_test_table_fixture(self, tmp_path):
        """Real anti-pattern: setup_test_table creates real DB tables."""
        f = tmp_path / "test_sample.py"
        f.write_text(textwrap.dedent("""\
            import pytest
            @pytest.fixture
            def setup_test_table():
                yield
        """))
        violations = MockViolationDetector().analyze_file(str(f))
        assert any(v.violation_type == "real_connection" for v in violations)


class TestDetectRealConnections:
    """Tests for real database connection detection."""

    def test_mysql_connector_connect_call(self, tmp_path):
        f = tmp_path / "test_sample.py"
        f.write_text(textwrap.dedent("""\
            import mysql.connector
            def test_x():
                conn = mysql.connector.connect(host='localhost')
        """))
        violations = MockViolationDetector().analyze_file(str(f))
        assert any(
            v.violation_type == "real_connection" for v in violations
        )

    def test_database_manager_test_mode(self, tmp_path):
        f = tmp_path / "test_sample.py"
        f.write_text(textwrap.dedent("""\
            from database import DatabaseManager
            def test_x():
                dm = DatabaseManager(test_mode=True)
        """))
        violations = MockViolationDetector().analyze_file(str(f))
        assert any(
            v.violation_type == "real_connection" for v in violations
        )

    def test_patched_mysql_not_flagged(self, tmp_path):
        f = tmp_path / "test_sample.py"
        f.write_text(textwrap.dedent("""\
            from unittest.mock import patch
            @patch('mysql.connector.connect')
            def test_x(mock_connect):
                pass
        """))
        violations = MockViolationDetector().analyze_file(str(f))
        real_conn = [v for v in violations if v.violation_type == "real_connection"]
        assert len(real_conn) == 0

    def test_patched_database_manager_not_flagged(self, tmp_path):
        f = tmp_path / "test_sample.py"
        f.write_text(textwrap.dedent("""\
            from unittest.mock import patch
            @patch('database.DatabaseManager')
            def test_x(mock_dm):
                dm = mock_dm.return_value
                dm.execute_query.return_value = []
        """))
        violations = MockViolationDetector().analyze_file(str(f))
        real_conn = [v for v in violations if v.violation_type == "real_connection"]
        assert len(real_conn) == 0


class TestEdgeCases:
    """Edge cases and error handling."""

    def test_binary_file_skipped(self, tmp_path):
        f = tmp_path / "test_binary.txt"
        f.write_bytes(b"\x00\x01\x02")
        violations = MockViolationDetector().analyze_file(str(f))
        assert violations == []

    def test_empty_file(self, tmp_path):
        f = tmp_path / "test_empty.py"
        f.write_text("")
        violations = MockViolationDetector().analyze_file(str(f))
        assert violations == []

    def test_all_violations_have_valid_severity(self, tmp_path):
        f = tmp_path / "test_all.py"
        f.write_text(textwrap.dedent("""\
            import mysql.connector
            import os
            def test_x():
                os.environ['DB_NAME']
                mysql.connector.connect()
                db = 'testfinance'
        """))
        violations = MockViolationDetector().analyze_file(str(f))
        for v in violations:
            assert v.severity in VALID_SEVERITIES
            assert v.violation_type in VALID_VIOLATION_TYPES
            assert v.file_path
            assert v.line_number > 0
            assert v.description
            assert v.suggested_fix
