"""
Unit tests for DriftDetector
=============================

Tests specific examples and edge cases for signature drift and key drift
detection, complementing the property-based tests.

Requirements: 6.2, 6.3
"""

from __future__ import annotations

import textwrap

import pytest

from scripts.test_maintenance.drift_detector import (
    DriftDetector,
    DriftIssue,
    DriftReport,
    VALID_DRIFT_TYPES,
    VALID_SEVERITIES,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _FakeDependencyMap:
    """Minimal dependency map for testing."""

    def __init__(self, backend=None, frontend=None):
        self.backend = backend or {}
        self.frontend = frontend or {}
        self.untested = []


def _write_py(tmp_path, filename, content):
    """Write a Python file and return its path as a string."""
    f = tmp_path / filename
    f.write_text(textwrap.dedent(content), encoding="utf-8")
    return str(f)


# ---------------------------------------------------------------------------
# Signature drift tests
# ---------------------------------------------------------------------------

class TestSignatureDrift:
    """Tests for detect_signature_drift()."""

    def test_detects_removed_parameter(self, tmp_path):
        """When a source function removes a parameter that the test still
        uses as a keyword argument, drift is detected.
        """
        src = _write_py(tmp_path, "service.py", """\
            def process_transaction(amount, currency):
                return amount * 1.0
        """)

        test = _write_py(tmp_path, "test_service.py", """\
            def test_process():
                result = process_transaction(amount=100, currency='EUR', fee=5)
                assert result > 0
        """)

        detector = DriftDetector(_FakeDependencyMap())
        issues = detector.detect_signature_drift(src, [test])

        assert len(issues) >= 1
        sig_issues = [i for i in issues if i.drift_type == "signature_change"]
        assert len(sig_issues) >= 1
        assert "fee" in sig_issues[0].old_value

    def test_no_drift_when_params_match(self, tmp_path):
        """No drift when test keyword arguments match source parameters."""
        src = _write_py(tmp_path, "service.py", """\
            def calculate(amount, rate, period):
                return amount * rate * period
        """)

        test = _write_py(tmp_path, "test_service.py", """\
            def test_calculate():
                result = calculate(amount=100, rate=0.05, period=12)
                assert result > 0
        """)

        detector = DriftDetector(_FakeDependencyMap())
        issues = detector.detect_signature_drift(src, [test])
        assert len(issues) == 0

    def test_detects_renamed_parameter(self, tmp_path):
        """When a parameter is renamed in source but the test uses the old
        name, drift is detected.
        """
        # Source has 'account_number' but test uses 'account'
        src = _write_py(tmp_path, "banking.py", """\
            def get_balance(account_number, date):
                return 0.0
        """)

        test = _write_py(tmp_path, "test_banking.py", """\
            def test_balance():
                result = get_balance(account='NL01', date='2025-01-01')
                assert result >= 0
        """)

        detector = DriftDetector(_FakeDependencyMap())
        issues = detector.detect_signature_drift(src, [test])

        assert len(issues) >= 1
        assert any("account" in i.old_value for i in issues)

    def test_skips_private_functions(self, tmp_path):
        """Private functions (single underscore prefix) are skipped."""
        src = _write_py(tmp_path, "service.py", """\
            def _internal_helper(x, y):
                return x + y

            def public_method(data):
                return data
        """)

        test = _write_py(tmp_path, "test_service.py", """\
            def test_helper():
                result = _internal_helper(x=1, y=2, z=3)
                assert result > 0
        """)

        detector = DriftDetector(_FakeDependencyMap())
        issues = detector.detect_signature_drift(src, [test])

        # _internal_helper should be skipped (private)
        assert len(issues) == 0

    def test_handles_nonexistent_source(self, tmp_path):
        """Nonexistent source file returns empty list."""
        test = _write_py(tmp_path, "test_service.py", """\
            def test_something():
                pass
        """)

        detector = DriftDetector(_FakeDependencyMap())
        issues = detector.detect_signature_drift(
            "/nonexistent/source.py", [test]
        )
        assert issues == []

    def test_handles_nonexistent_test(self, tmp_path):
        """Nonexistent test file returns empty list."""
        src = _write_py(tmp_path, "service.py", """\
            def process(data):
                return data
        """)

        detector = DriftDetector(_FakeDependencyMap())
        issues = detector.detect_signature_drift(
            src, ["/nonexistent/test.py"]
        )
        assert issues == []

    def test_handles_syntax_error_in_source(self, tmp_path):
        """Source file with syntax error returns empty list."""
        src = tmp_path / "broken.py"
        src.write_text("def broken(:\n    pass", encoding="utf-8")

        test = _write_py(tmp_path, "test_broken.py", """\
            def test_broken():
                pass
        """)

        detector = DriftDetector(_FakeDependencyMap())
        issues = detector.detect_signature_drift(str(src), [test])
        assert issues == []

    def test_multiple_test_files(self, tmp_path):
        """Drift is detected across multiple test files."""
        src = _write_py(tmp_path, "service.py", """\
            def process(data, mode):
                return data
        """)

        test1 = _write_py(tmp_path, "test_service1.py", """\
            def test_process_v1():
                result = process(data='x', mode='fast', verbose=True)
                assert result
        """)

        test2 = _write_py(tmp_path, "test_service2.py", """\
            def test_process_v2():
                result = process(data='y', mode='slow', debug=True)
                assert result
        """)

        detector = DriftDetector(_FakeDependencyMap())
        issues = detector.detect_signature_drift(src, [test1, test2])

        assert len(issues) >= 2
        test_files = {i.test_file for i in issues}
        assert test1 in test_files
        assert test2 in test_files


# ---------------------------------------------------------------------------
# Key drift tests
# ---------------------------------------------------------------------------

class TestKeyDrift:
    """Tests for detect_key_drift()."""

    def test_detects_removed_dict_key(self, tmp_path):
        """When source returns different keys than what the test expects,
        drift is detected.
        """
        src = _write_py(tmp_path, "service.py", """\
            def get_report():
                return {
                    'account_number': '123',
                    'balance': 100.0,
                    'currency': 'EUR',
                }
        """)

        test = _write_py(tmp_path, "test_service.py", """\
            def test_report():
                result = {
                    'Account': '123',
                    'balance': 100.0,
                    'currency': 'EUR',
                }
                assert result['Account'] == '123'
        """)

        detector = DriftDetector(_FakeDependencyMap())
        issues = detector.detect_key_drift(src, [test])

        # 'Account' is in test but not in source (source has 'account_number')
        key_issues = [i for i in issues if i.drift_type == "key_rename"]
        assert len(key_issues) >= 1
        assert any("Account" in i.old_value for i in key_issues)

    def test_no_drift_when_keys_match(self, tmp_path):
        """No drift when test dict keys match source dict keys."""
        src = _write_py(tmp_path, "service.py", """\
            def get_data():
                return {
                    'first_date': '2025-01-01',
                    'last_date': '2025-12-31',
                    'total': 42,
                }
        """)

        test = _write_py(tmp_path, "test_service.py", """\
            def test_data():
                result = {
                    'first_date': '2025-01-01',
                    'last_date': '2025-12-31',
                    'total': 42,
                }
                assert result['first_date'] == '2025-01-01'
        """)

        detector = DriftDetector(_FakeDependencyMap())
        issues = detector.detect_key_drift(src, [test])
        assert len(issues) == 0

    def test_detects_renamed_key_real_example(self, tmp_path):
        """Real-world example: year_end_service changed 'first_date' key.

        The drift detector requires >=60% key overlap between source and
        test dicts before flagging mismatches (to avoid false positives).
        We include enough shared keys to meet that threshold.
        """
        src = _write_py(tmp_path, "year_end_service.py", """\
            def get_first_year():
                return {
                    'start_date': '2020-01-01',
                    'end_date': '2020-12-31',
                    'year': 2020,
                    'status': 'active',
                    'count': 12,
                }
        """)

        test = _write_py(tmp_path, "test_year_end_service.py", """\
            def test_get_first_year():
                mock_result = {
                    'first_date': '2020-01-01',
                    'end_date': '2020-12-31',
                    'year': 2020,
                    'status': 'active',
                    'count': 12,
                }
                assert mock_result['first_date'] == '2020-01-01'
        """)

        detector = DriftDetector(_FakeDependencyMap())
        issues = detector.detect_key_drift(src, [test])

        key_issues = [i for i in issues if i.drift_type == "key_rename"]
        # 'first_date' is in test but not in source (renamed from 'start_date')
        old_values = {i.old_value for i in key_issues}
        assert "first_date" in old_values or "start_date" in old_values

    def test_handles_empty_source(self, tmp_path):
        """Empty source file returns empty list."""
        src = tmp_path / "empty.py"
        src.write_text("", encoding="utf-8")

        test = _write_py(tmp_path, "test_empty.py", """\
            def test_something():
                data = {'key': 'value'}
                assert data
        """)

        detector = DriftDetector(_FakeDependencyMap())
        issues = detector.detect_key_drift(str(src), [test])
        assert issues == []


# ---------------------------------------------------------------------------
# detect_all_drift tests
# ---------------------------------------------------------------------------

class TestDetectAllDrift:
    """Tests for detect_all_drift() using the dependency map."""

    def test_scans_all_mapped_pairs(self, tmp_path):
        """detect_all_drift iterates over all backend map entries."""
        src = _write_py(tmp_path, "service.py", """\
            def process(data, mode):
                return {'result': data}
        """)

        test = _write_py(tmp_path, "test_service.py", """\
            def test_process():
                result = process(data='x', mode='fast', old_param=True)
                assert result
        """)

        dep_map = _FakeDependencyMap(
            backend={str(tmp_path / "service.py"): [str(tmp_path / "test_service.py")]}
        )
        detector = DriftDetector(dep_map)
        issues = detector.detect_all_drift()

        assert len(issues) >= 1

    def test_skips_unmapped_sources(self, tmp_path):
        """Sources with no test files are skipped."""
        src = _write_py(tmp_path, "service.py", """\
            def process(data):
                return data
        """)

        dep_map = _FakeDependencyMap(
            backend={str(tmp_path / "service.py"): []}
        )
        detector = DriftDetector(dep_map)
        issues = detector.detect_all_drift()
        assert issues == []

    def test_handles_errors_gracefully(self, tmp_path):
        """Errors in individual file analysis don't crash the full scan."""
        dep_map = _FakeDependencyMap(
            backend={"/nonexistent/source.py": ["/nonexistent/test.py"]}
        )
        detector = DriftDetector(dep_map)
        issues = detector.detect_all_drift()
        assert issues == []


# ---------------------------------------------------------------------------
# DriftReport tests
# ---------------------------------------------------------------------------

class TestDriftReport:
    """Tests for generate_drift_report()."""

    def test_empty_report(self):
        """Empty issues list produces empty report."""
        detector = DriftDetector(_FakeDependencyMap())
        report = detector.generate_drift_report([])

        assert report.issues == []
        assert report.files_analyzed == 0
        assert report.source_files == []
        assert report.test_files == []

    def test_report_aggregates_files(self):
        """Report correctly aggregates unique source and test files."""
        issues = [
            DriftIssue(
                source_file="src/a.py",
                test_file="tests/test_a.py",
                line_number=5,
                drift_type="signature_change",
                severity="high",
                old_value="old",
                new_value="new",
                description="Param changed",
            ),
            DriftIssue(
                source_file="src/a.py",
                test_file="tests/test_b.py",
                line_number=10,
                drift_type="key_rename",
                severity="medium",
                old_value="old_key",
                new_value="new_key",
                description="Key renamed",
            ),
            DriftIssue(
                source_file="src/b.py",
                test_file="tests/test_b.py",
                line_number=15,
                drift_type="signature_change",
                severity="high",
                old_value="param",
                new_value="new_param",
                description="Param renamed",
            ),
        ]

        detector = DriftDetector(_FakeDependencyMap())
        report = detector.generate_drift_report(issues)

        assert len(report.issues) == 3
        assert report.files_analyzed == 4  # a.py, b.py, test_a.py, test_b.py
        assert sorted(report.source_files) == ["src/a.py", "src/b.py"]
        assert sorted(report.test_files) == ["tests/test_a.py", "tests/test_b.py"]
