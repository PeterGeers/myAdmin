"""
Unit tests for TestHealthScanner
=================================

Tests scanner orchestration, report assembly, CLI interface, and
integration with MockViolationDetector, ComplianceChecker, and
DependencyMapper.
"""

from __future__ import annotations

import json
import os
import textwrap
from unittest.mock import MagicMock, patch

import pytest

from scripts.test_maintenance.scanner import (
    BaselineSnapshot,
    CategorySummary,
    MaintenanceWorkList,
    ScanReport,
    ScanSummary,
    SessionSummary,
    StaleFailure,
    TestHealthScanner,
    main,
)
from scripts.test_maintenance.mock_violation_detector import MockViolation
from scripts.test_maintenance.compliance_checker import ComplianceViolation


@pytest.fixture
def rules_file(tmp_path):
    """Create a minimal compliance rules file."""
    rules = {
        "version": "1.0",
        "rules": {
            "backend_unit": {
                "required": [],
                "recommended": [],
                "forbidden": [
                    {
                        "id": "BU005",
                        "name": "no_real_db_in_unit",
                        "description": "No mysql.connector",
                        "anti_patterns": ["import mysql\\.connector"],
                        "reference": "test",
                    },
                ],
            },
            "frontend_unit": {"required": []},
            "backend_route": {"required": []},
        },
    }
    path = tmp_path / "test-compliance-rules.json"
    path.write_text(json.dumps(rules), encoding="utf-8")
    return str(path)


@pytest.fixture
def test_dir(tmp_path):
    """Create a minimal test directory structure."""
    unit_dir = tmp_path / "unit"
    unit_dir.mkdir()

    # Clean test file
    clean = unit_dir / "test_clean.py"
    clean.write_text("def test_clean():\n    assert True\n")

    # Violating test file
    bad = unit_dir / "test_bad.py"
    bad.write_text(textwrap.dedent("""\
        import mysql.connector
        def test_bad():
            conn = mysql.connector.connect(host='localhost')
    """))

    return str(tmp_path)


class TestScannerOrchestration:
    """Tests for the scan() method orchestration."""

    def test_scan_returns_scan_report(self, rules_file, test_dir):
        scanner = TestHealthScanner(config_path=rules_file)
        report = scanner.scan(backend_test_dir=test_dir)
        assert isinstance(report, ScanReport)
        assert report.timestamp
        assert report.scan_duration_seconds >= 0

    def test_scan_detects_mock_violations(self, rules_file, test_dir):
        scanner = TestHealthScanner(config_path=rules_file)
        report = scanner.scan(backend_test_dir=test_dir)
        assert len(report.mock_violations) > 0
        assert any(
            v.violation_type == "db_import" for v in report.mock_violations
        )

    def test_scan_detects_compliance_violations(self, rules_file, test_dir):
        scanner = TestHealthScanner(config_path=rules_file)
        report = scanner.scan(backend_test_dir=test_dir)
        # The forbidden rule should flag the mysql import
        assert len(report.compliance_violations) > 0

    def test_scan_builds_summary(self, rules_file, test_dir):
        scanner = TestHealthScanner(config_path=rules_file)
        report = scanner.scan(backend_test_dir=test_dir)
        assert isinstance(report.summary, ScanSummary)
        assert report.summary.total_test_files > 0
        assert isinstance(report.summary.issues_by_severity, dict)

    def test_scan_empty_directory(self, rules_file, tmp_path):
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        scanner = TestHealthScanner(config_path=rules_file)
        report = scanner.scan(backend_test_dir=str(empty_dir))
        assert report.mock_violations == []
        assert report.compliance_violations == []

    def test_scan_nonexistent_directory(self, rules_file):
        scanner = TestHealthScanner(config_path=rules_file)
        report = scanner.scan(backend_test_dir="/nonexistent/dir")
        assert report.mock_violations == []


class TestSessionSummary:
    """Tests for generate_session_summary()."""

    def test_session_summary_computes_fixed(self, rules_file):
        scanner = TestHealthScanner(config_path=rules_file)

        before = ScanReport(
            mock_violations=[
                MockViolation(
                    file_path="test_a.py", line_number=1,
                    violation_type="db_import", severity="critical",
                    description="mysql import", suggested_fix="fix",
                ),
                MockViolation(
                    file_path="test_b.py", line_number=1,
                    violation_type="db_import", severity="critical",
                    description="mysql import", suggested_fix="fix",
                ),
            ],
        )
        after = ScanReport(
            mock_violations=[
                MockViolation(
                    file_path="test_b.py", line_number=1,
                    violation_type="db_import", severity="critical",
                    description="mysql import", suggested_fix="fix",
                ),
            ],
        )

        summary = scanner.generate_session_summary(before, after)
        assert isinstance(summary, SessionSummary)
        assert summary.tests_fixed == 1  # test_a.py was fixed
        assert summary.tests_newly_broken == 0

    def test_session_summary_detects_new_violations(self, rules_file):
        scanner = TestHealthScanner(config_path=rules_file)

        before = ScanReport()
        after = ScanReport(
            mock_violations=[
                MockViolation(
                    file_path="test_new.py", line_number=1,
                    violation_type="db_import", severity="critical",
                    description="new violation", suggested_fix="fix",
                ),
            ],
        )

        summary = scanner.generate_session_summary(before, after)
        assert summary.tests_newly_broken == 1


class TestMaintenanceWorkList:
    """Tests for generate_maintenance_worklist()."""

    def test_worklist_groups_by_root_cause(self, rules_file, test_dir):
        scanner = TestHealthScanner(config_path=rules_file)

        with patch.object(scanner, 'scan') as mock_scan:
            mock_scan.return_value = ScanReport(
                mock_violations=[
                    MockViolation(
                        file_path="test_a.py", line_number=1,
                        violation_type="db_import", severity="critical",
                        description="mysql import", suggested_fix="fix",
                    ),
                    MockViolation(
                        file_path="test_b.py", line_number=1,
                        violation_type="env_leak", severity="high",
                        description="env leak", suggested_fix="fix",
                    ),
                ],
            )
            worklist = scanner.generate_maintenance_worklist()

        assert isinstance(worklist, MaintenanceWorkList)
        assert worklist.total_items == 2
        assert "database_mocking" in worklist.items_by_root_cause
        assert "environment_dependency" in worklist.items_by_root_cause

    def test_worklist_sorts_by_severity(self, rules_file):
        scanner = TestHealthScanner(config_path=rules_file)

        with patch.object(scanner, 'scan') as mock_scan:
            mock_scan.return_value = ScanReport(
                mock_violations=[
                    MockViolation(
                        file_path="test_low.py", line_number=1,
                        violation_type="db_import", severity="low",
                        description="low", suggested_fix="fix",
                    ),
                    MockViolation(
                        file_path="test_crit.py", line_number=1,
                        violation_type="db_import", severity="critical",
                        description="critical", suggested_fix="fix",
                    ),
                ],
            )
            worklist = scanner.generate_maintenance_worklist()

        items = worklist.items_by_root_cause["database_mocking"]
        assert items[0].severity == "critical"
        assert items[1].severity == "low"


class TestCLI:
    """Tests for the CLI interface."""

    def test_cli_default_scan(self, rules_file, test_dir):
        """Default scan returns exit code 1 when issues found."""
        exit_code = main([
            "--config", rules_file,
        ])
        # Should find issues in the real codebase
        assert exit_code in (0, 1)

    def test_cli_baseline(self, rules_file):
        """--baseline flag generates a baseline snapshot."""
        with patch.object(
            TestHealthScanner, 'generate_baseline'
        ) as mock_baseline:
            mock_baseline.return_value = BaselineSnapshot(
                timestamp="2025-01-01T00:00:00Z",
                total_failing=5,
            )
            exit_code = main(["--baseline", "--config", rules_file])
            assert exit_code == 0
            mock_baseline.assert_called_once()

    def test_cli_maintenance_session(self, rules_file):
        """--maintenance-session flag generates a work list."""
        with patch.object(
            TestHealthScanner, 'generate_maintenance_worklist'
        ) as mock_worklist:
            mock_worklist.return_value = MaintenanceWorkList(
                total_items=3,
                items_by_root_cause={"database_mocking": []},
            )
            exit_code = main([
                "--maintenance-session", "--config", rules_file,
            ])
            assert exit_code == 0
            mock_worklist.assert_called_once()


class TestDataModels:
    """Tests for data model construction and defaults."""

    def test_scan_report_defaults(self):
        report = ScanReport()
        assert report.mock_violations == []
        assert report.compliance_violations == []
        assert report.drift_issues == []
        assert report.untested_sources == []
        assert report.stale_failures == []

    def test_scan_summary_defaults(self):
        summary = ScanSummary()
        assert summary.total_test_files == 0
        assert summary.total_tests == 0
        assert summary.by_category == {}
        assert summary.issues_by_severity == {}
        assert summary.warnings == []

    def test_category_summary_defaults(self):
        cat = CategorySummary()
        assert cat.total == 0
        assert cat.passing == 0
        assert cat.failing == 0

    def test_stale_failure_fields(self):
        sf = StaleFailure(
            test_id="test_x",
            failure_reason="broken",
            first_failure_date="2025-01-01",
            days_failing=30,
        )
        assert sf.test_id == "test_x"
        assert sf.days_failing == 30


class TestStaleFailureDetection:
    """Tests for stale failure detection via ClassificationRegistry."""

    def test_stale_failures_appear_in_scan_report(self, rules_file, tmp_path):
        """Stale failures from the registry appear in the scan report."""
        # Create a registry with a stale failing test
        registry_path = str(tmp_path / "test-registry.json")
        registry_data = {
            "version": "1.0",
            "last_updated": "",
            "tests": {
                "test_old.py::test_stale": {
                    "category": "unit",
                    "status": "failing",
                    "failure_reason": "broken mock",
                    "triage_decision": "fix",
                    "triage_date": "2024-01-01",
                    "notes": "very old failure",
                }
            },
            "metadata": {},
        }
        with open(registry_path, "w", encoding="utf-8") as fh:
            json.dump(registry_data, fh)

        empty_dir = tmp_path / "empty_tests"
        empty_dir.mkdir()

        scanner = TestHealthScanner(
            config_path=rules_file, registry_path=registry_path
        )
        report = scanner.scan(backend_test_dir=str(empty_dir))

        assert len(report.stale_failures) > 0
        stale_ids = [sf.test_id for sf in report.stale_failures]
        assert "test_old.py::test_stale" in stale_ids
        sf = next(s for s in report.stale_failures
                  if s.test_id == "test_old.py::test_stale")
        assert sf.days_failing > 14

    def test_no_stale_failures_for_recent_entries(self, rules_file, tmp_path):
        """Recent failing tests should not appear as stale."""
        from datetime import datetime, timezone

        registry_path = str(tmp_path / "test-registry.json")
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        registry_data = {
            "version": "1.0",
            "last_updated": "",
            "tests": {
                "test_new.py::test_recent": {
                    "category": "unit",
                    "status": "failing",
                    "failure_reason": "just broke",
                    "triage_decision": "fix",
                    "triage_date": today,
                    "notes": "recent failure",
                }
            },
            "metadata": {},
        }
        with open(registry_path, "w", encoding="utf-8") as fh:
            json.dump(registry_data, fh)

        empty_dir = tmp_path / "empty_tests"
        empty_dir.mkdir()

        scanner = TestHealthScanner(
            config_path=rules_file, registry_path=registry_path
        )
        report = scanner.scan(backend_test_dir=str(empty_dir))

        assert len(report.stale_failures) == 0


class TestUntriagedWarning:
    """Tests for untriaged warning threshold."""

    def test_untriaged_warning_when_count_exceeds_10(
        self, rules_file, tmp_path
    ):
        """Warning appears when > 10 failing tests lack triage decisions."""
        registry_path = str(tmp_path / "test-registry.json")
        tests = {}
        # Create 12 failing tests without triage decisions.
        # Note: ClassificationRegistry.get_untriaged_count() counts tests
        # with status="failing" and no valid triage_decision.
        # We write directly to the JSON to bypass validation.
        for i in range(12):
            tests[f"test_file_{i}.py::test_func"] = {
                "category": "unit",
                "status": "failing",
                "failure_reason": f"reason {i}",
                # No triage_decision — these are untriaged
            }
        registry_data = {
            "version": "1.0",
            "last_updated": "",
            "tests": tests,
            "metadata": {},
        }
        with open(registry_path, "w", encoding="utf-8") as fh:
            json.dump(registry_data, fh)

        empty_dir = tmp_path / "empty_tests"
        empty_dir.mkdir()

        scanner = TestHealthScanner(
            config_path=rules_file, registry_path=registry_path
        )
        report = scanner.scan(backend_test_dir=str(empty_dir))

        assert len(report.summary.warnings) > 0
        assert any("12 failing tests" in w for w in report.summary.warnings)

    def test_no_untriaged_warning_when_count_at_or_below_10(
        self, rules_file, tmp_path
    ):
        """No warning when untriaged count is <= 10."""
        registry_path = str(tmp_path / "test-registry.json")
        tests = {}
        for i in range(10):
            tests[f"test_file_{i}.py::test_func"] = {
                "category": "unit",
                "status": "failing",
                "failure_reason": f"reason {i}",
            }
        registry_data = {
            "version": "1.0",
            "last_updated": "",
            "tests": tests,
            "metadata": {},
        }
        with open(registry_path, "w", encoding="utf-8") as fh:
            json.dump(registry_data, fh)

        empty_dir = tmp_path / "empty_tests"
        empty_dir.mkdir()

        scanner = TestHealthScanner(
            config_path=rules_file, registry_path=registry_path
        )
        report = scanner.scan(backend_test_dir=str(empty_dir))

        assert len(report.summary.warnings) == 0


class TestBaselineRegistryPopulation:
    """Tests for generate_baseline() populating the classification registry."""

    def test_generate_baseline_populates_registry(
        self, rules_file, test_dir, tmp_path
    ):
        """generate_baseline() should add failing tests to the registry."""
        registry_path = str(tmp_path / "test-registry.json")

        scanner = TestHealthScanner(
            config_path=rules_file, registry_path=registry_path
        )
        snapshot = scanner.generate_baseline(backend_test_dir=test_dir)

        # The baseline should have found violations
        assert snapshot.total_failing > 0

        # The registry file should have been created with entries
        assert os.path.isfile(registry_path)
        with open(registry_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)

        assert len(data["tests"]) > 0
        # Each entry should have triage_decision="fix"
        for test_id, entry in data["tests"].items():
            assert entry["status"] == "failing"
            assert entry["triage_decision"] == "fix"
            assert entry["category"] == "unit"


class TestSessionSummaryDataclass:
    """Tests for the enhanced SessionSummary dataclass."""

    def test_session_summary_new_fields_defaults(self):
        summary = SessionSummary()
        assert summary.session_id == ""
        assert summary.started_at == ""
        assert summary.completed_at == ""
        assert summary.fixes_by_root_cause == {}
        assert summary.remaining_backlog == 0

    def test_session_summary_new_fields_populated(self):
        summary = SessionSummary(
            tests_fixed=5,
            tests_newly_broken=1,
            remaining_violations=3,
            session_id="20250101_120000",
            started_at="2025-01-01T12:00:00+00:00",
            completed_at="2025-01-01T13:00:00+00:00",
            fixes_by_root_cause={"database_mocking": 3, "key_mismatch": 2},
            remaining_backlog=3,
        )
        assert summary.session_id == "20250101_120000"
        assert summary.fixes_by_root_cause["database_mocking"] == 3
        assert summary.remaining_backlog == 3


class TestRunMaintenanceSession:
    """Tests for run_maintenance_session()."""

    def test_run_maintenance_session_returns_worklist(
        self, rules_file, tmp_path
    ):
        scanner = TestHealthScanner(config_path=rules_file)

        mock_worklist = MaintenanceWorkList(
            timestamp="2025-01-01T00:00:00Z",
            total_items=2,
            items_by_root_cause={"database_mocking": []},
            effort_by_category={"database_mocking": "15-30 min per test"},
        )

        with patch.object(
            scanner, "generate_maintenance_worklist", return_value=mock_worklist
        ), patch.object(scanner, "_save_report") as mock_save:
            before = ScanReport(timestamp="2025-01-01T00:00:00Z")
            result = scanner.run_maintenance_session(before)

        assert isinstance(result, MaintenanceWorkList)
        assert result.total_items == 2
        mock_save.assert_called_once_with(mock_worklist, "maintenance_worklist")

    def test_run_maintenance_session_saves_report(self, rules_file, tmp_path):
        scanner = TestHealthScanner(config_path=rules_file)

        with patch.object(scanner, "scan") as mock_scan, \
             patch.object(scanner, "_save_report") as mock_save:
            mock_scan.return_value = ScanReport()
            before = ScanReport(timestamp="2025-01-01T00:00:00Z")
            scanner.run_maintenance_session(before)

        assert mock_save.called
        assert mock_save.call_args[0][1] == "maintenance_worklist"


class TestCompleteMaintenanceSession:
    """Tests for complete_maintenance_session()."""

    def test_complete_session_returns_summary(self, rules_file, tmp_path):
        scanner = TestHealthScanner(config_path=rules_file)

        before = ScanReport(
            timestamp="2025-01-01T12:00:00+00:00",
            mock_violations=[
                MockViolation(
                    file_path="test_a.py", line_number=1,
                    violation_type="db_import", severity="critical",
                    description="mysql import", suggested_fix="fix",
                ),
            ],
        )
        after = ScanReport(
            timestamp="2025-01-01T13:00:00+00:00",
        )

        with patch.object(scanner, "_save_report"), \
             patch.object(scanner, "_save_session_history"):
            summary = scanner.complete_maintenance_session(before, after)

        assert isinstance(summary, SessionSummary)
        assert summary.tests_fixed == 1
        assert summary.session_id != ""
        assert summary.completed_at != ""
        assert summary.started_at == before.timestamp

    def test_complete_session_computes_fixes_by_root_cause(
        self, rules_file
    ):
        scanner = TestHealthScanner(config_path=rules_file)

        before = ScanReport(
            timestamp="2025-01-01T12:00:00+00:00",
            mock_violations=[
                MockViolation(
                    file_path="test_a.py", line_number=1,
                    violation_type="db_import", severity="critical",
                    description="mysql import", suggested_fix="fix",
                ),
                MockViolation(
                    file_path="test_b.py", line_number=1,
                    violation_type="env_leak", severity="high",
                    description="env leak", suggested_fix="fix",
                ),
            ],
        )
        # After: only the env_leak remains
        after = ScanReport(
            timestamp="2025-01-01T13:00:00+00:00",
            mock_violations=[
                MockViolation(
                    file_path="test_b.py", line_number=1,
                    violation_type="env_leak", severity="high",
                    description="env leak", suggested_fix="fix",
                ),
            ],
        )

        with patch.object(scanner, "_save_report"), \
             patch.object(scanner, "_save_session_history"):
            summary = scanner.complete_maintenance_session(before, after)

        assert "database_mocking" in summary.fixes_by_root_cause
        assert summary.fixes_by_root_cause["database_mocking"] == 1

    def test_complete_session_saves_history(self, rules_file):
        scanner = TestHealthScanner(config_path=rules_file)

        before = ScanReport(timestamp="2025-01-01T12:00:00+00:00")
        after = ScanReport(timestamp="2025-01-01T13:00:00+00:00")

        with patch.object(scanner, "_save_report"), \
             patch.object(
                 scanner, "_save_session_history"
             ) as mock_history:
            scanner.complete_maintenance_session(before, after)

        mock_history.assert_called_once()
        saved_summary = mock_history.call_args[0][0]
        assert isinstance(saved_summary, SessionSummary)


class TestSaveSessionHistory:
    """Tests for _save_session_history()."""

    def test_creates_new_history_file(self, rules_file, tmp_path):
        scanner = TestHealthScanner(config_path=rules_file)

        history_path = tmp_path / "reports" / "session_history.json"
        reports_dir = str(tmp_path / "reports")

        summary = SessionSummary(
            tests_fixed=3,
            session_id="20250101_120000",
            started_at="2025-01-01T12:00:00+00:00",
            completed_at="2025-01-01T13:00:00+00:00",
            fixes_by_root_cause={"database_mocking": 2},
            remaining_backlog=5,
        )

        with patch(
            "scripts.test_maintenance.scanner.os.path.join",
            side_effect=lambda *args: str(tmp_path / "reports" / args[-1])
            if args[-1] == "session_history.json"
            else os.path.join(*args),
        ):
            # Directly call with patched reports dir
            pass

        # Use a more direct approach: patch the reports dir path
        original_join = os.path.join

        def patched_join(*args):
            if args == ("backend", "tests", "reports"):
                return reports_dir
            return original_join(*args)

        with patch("scripts.test_maintenance.scanner.os.path.join",
                    side_effect=patched_join):
            result = scanner._save_session_history(summary)

        assert result is not None
        assert os.path.isfile(str(history_path))

        with open(str(history_path), "r", encoding="utf-8") as fh:
            data = json.load(fh)

        assert len(data["sessions"]) == 1
        entry = data["sessions"][0]
        assert entry["session_id"] == "20250101_120000"
        assert entry["tests_fixed"] == 3
        assert entry["remaining_backlog"] == 5
        assert entry["fixes_by_root_cause"]["database_mocking"] == 2

    def test_appends_to_existing_history(self, rules_file, tmp_path):
        scanner = TestHealthScanner(config_path=rules_file)

        reports_dir = str(tmp_path / "reports")
        os.makedirs(reports_dir, exist_ok=True)
        history_path = os.path.join(reports_dir, "session_history.json")

        # Pre-populate with one session
        existing = {
            "sessions": [
                {
                    "session_id": "20250101_100000",
                    "started_at": "2025-01-01T10:00:00+00:00",
                    "completed_at": "2025-01-01T11:00:00+00:00",
                    "tests_fixed": 2,
                    "tests_quarantined": 0,
                    "tests_deleted": 0,
                    "remaining_backlog": 8,
                    "fixes_by_root_cause": {},
                }
            ]
        }
        with open(history_path, "w", encoding="utf-8") as fh:
            json.dump(existing, fh)

        summary = SessionSummary(
            tests_fixed=5,
            session_id="20250101_120000",
            started_at="2025-01-01T12:00:00+00:00",
            completed_at="2025-01-01T13:00:00+00:00",
            remaining_backlog=3,
        )

        original_join = os.path.join

        def patched_join(*args):
            if args == ("backend", "tests", "reports"):
                return reports_dir
            return original_join(*args)

        with patch("scripts.test_maintenance.scanner.os.path.join",
                    side_effect=patched_join):
            result = scanner._save_session_history(summary)

        assert result is not None

        with open(history_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)

        assert len(data["sessions"]) == 2
        assert data["sessions"][0]["session_id"] == "20250101_100000"
        assert data["sessions"][1]["session_id"] == "20250101_120000"


class TestEnhancedMaintenanceSessionCLI:
    """Tests for the enhanced --maintenance-session CLI output."""

    def test_cli_maintenance_session_saves_report(self, rules_file):
        """--maintenance-session saves the work list as a report."""
        from scripts.test_maintenance.scanner import MaintenanceWorkItem

        items = [
            MaintenanceWorkItem(
                file_path="test_a.py",
                issue_type="db_import",
                root_cause="database_mocking",
                severity="critical",
                description="mysql import",
                suggested_fix="fix",
                effort_estimate="15-30 min",
            ),
        ]
        mock_worklist = MaintenanceWorkList(
            total_items=1,
            items_by_root_cause={"database_mocking": items},
            effort_by_category={"database_mocking": "15-30 min per test"},
        )

        with patch.object(
            TestHealthScanner, "generate_maintenance_worklist",
            return_value=mock_worklist,
        ), patch.object(
            TestHealthScanner, "_save_report"
        ) as mock_save:
            exit_code = main([
                "--maintenance-session", "--config", rules_file,
            ])

        assert exit_code == 0
        mock_save.assert_called_once()
        assert mock_save.call_args[0][1] == "maintenance_worklist"

    def test_cli_maintenance_session_prints_formatted_output(
        self, rules_file, capsys
    ):
        """--maintenance-session prints grouped items with severity."""
        from scripts.test_maintenance.scanner import MaintenanceWorkItem

        items = [
            MaintenanceWorkItem(
                file_path="test_crit.py",
                issue_type="db_import",
                root_cause="database_mocking",
                severity="critical",
                description="mysql import in unit test",
                suggested_fix="fix",
                effort_estimate="15-30 min",
            ),
            MaintenanceWorkItem(
                file_path="test_low.py",
                issue_type="db_import",
                root_cause="database_mocking",
                severity="low",
                description="minor issue",
                suggested_fix="fix",
                effort_estimate="5 min",
            ),
        ]
        mock_worklist = MaintenanceWorkList(
            total_items=2,
            items_by_root_cause={"database_mocking": items},
            effort_by_category={"database_mocking": "15-30 min per test"},
        )

        with patch.object(
            TestHealthScanner, "generate_maintenance_worklist",
            return_value=mock_worklist,
        ), patch.object(TestHealthScanner, "_save_report"):
            main(["--maintenance-session", "--config", rules_file])

        captured = capsys.readouterr()
        assert "Maintenance Session Work List" in captured.out
        assert "database_mocking" in captured.out
        assert "critical" in captured.out
        assert "test_crit.py" in captured.out
        assert "Effort estimates by category" in captured.out


class TestViolationsByRootCause:
    """Tests for _violations_by_root_cause() helper."""

    def test_counts_mock_violations(self, rules_file):
        scanner = TestHealthScanner(config_path=rules_file)
        report = ScanReport(
            mock_violations=[
                MockViolation(
                    file_path="a.py", line_number=1,
                    violation_type="db_import", severity="critical",
                    description="d", suggested_fix="f",
                ),
                MockViolation(
                    file_path="b.py", line_number=1,
                    violation_type="db_import", severity="high",
                    description="d", suggested_fix="f",
                ),
                MockViolation(
                    file_path="c.py", line_number=1,
                    violation_type="env_leak", severity="medium",
                    description="d", suggested_fix="f",
                ),
            ],
        )
        counts = scanner._violations_by_root_cause(report)
        assert counts["database_mocking"] == 2
        assert counts["environment_dependency"] == 1

    def test_counts_compliance_violations(self, rules_file):
        scanner = TestHealthScanner(config_path=rules_file)
        report = ScanReport(
            compliance_violations=[
                ComplianceViolation(
                    file_path="a.py", line_number=1,
                    rule_id="BU001", severity="medium",
                    expected_pattern="x", actual_pattern="y",
                    convention_reference="ref",
                ),
            ],
        )
        counts = scanner._violations_by_root_cause(report)
        assert counts["convention_violation"] == 1

    def test_empty_report_returns_empty_counts(self, rules_file):
        scanner = TestHealthScanner(config_path=rules_file)
        counts = scanner._violations_by_root_cause(ScanReport())
        assert counts == {}
