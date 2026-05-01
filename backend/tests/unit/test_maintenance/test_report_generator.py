"""
Unit tests for ReportGenerator and maintenance session helpers
===============================================================

Tests JSON serialization/deserialization, Markdown rendering,
trend computation with concrete before/after examples, file
persistence, and the ``load_latest_report`` helper.

Requirements: 1.5, 7.2, 7.5, 10.1
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict

import pytest

from scripts.test_maintenance.scanner import (
    CategorySummary,
    ScanReport,
    ScanSummary,
    StaleFailure,
)
from scripts.test_maintenance.mock_violation_detector import MockViolation
from scripts.test_maintenance.compliance_checker import ComplianceViolation
from scripts.test_maintenance.report_generator import (
    ReportGenerator,
    TrendReport,
    compute_trend,
    load_latest_report,
)


# ---------------------------------------------------------------------------
# Helpers — reusable test data builders
# ---------------------------------------------------------------------------


def _make_summary(**overrides) -> ScanSummary:
    """Build a ScanSummary with sensible defaults."""
    defaults = dict(
        total_test_files=10,
        total_tests=42,
        passing=35,
        failing=5,
        skipped=2,
        flaky=0,
        quarantined=0,
        by_category={},
        issues_by_severity={},
        warnings=[],
    )
    defaults.update(overrides)
    return ScanSummary(**defaults)


def _make_report(**overrides) -> ScanReport:
    """Build a ScanReport with sensible defaults."""
    defaults = dict(
        timestamp="2025-06-01T12:00:00+00:00",
        scan_duration_seconds=1.234,
        summary=_make_summary(),
        mock_violations=[],
        drift_issues=[],
        compliance_violations=[],
        frontend_violations=[],
        untested_sources=[],
        stale_failures=[],
    )
    defaults.update(overrides)
    return ScanReport(**defaults)


def _make_mock_violation(**overrides) -> MockViolation:
    defaults = dict(
        file_path="tests/unit/test_bad.py",
        line_number=5,
        violation_type="db_import",
        severity="critical",
        description="Direct mysql.connector import",
        suggested_fix="Use mock_db fixture",
    )
    defaults.update(overrides)
    return MockViolation(**defaults)


def _make_compliance_violation(**overrides) -> ComplianceViolation:
    defaults = dict(
        file_path="tests/unit/test_bad.py",
        line_number=10,
        rule_id="BU005",
        severity="forbidden",
        expected_pattern="no mysql.connector",
        actual_pattern="import mysql.connector",
        convention_reference="test-compliance-rules",
    )
    defaults.update(overrides)
    return ComplianceViolation(**defaults)


def _make_stale_failure(**overrides) -> StaleFailure:
    defaults = dict(
        test_id="test_old.py::test_stale",
        failure_reason="broken mock",
        first_failure_date="2025-01-01",
        days_failing=30,
    )
    defaults.update(overrides)
    return StaleFailure(**defaults)


# ===================================================================
# TestReportGeneratorJSON
# ===================================================================


@pytest.mark.unit
class TestReportGeneratorJSON:
    """JSON serialization and deserialization tests."""

    def test_to_json_returns_valid_json(self):
        """to_json() output is valid JSON."""
        report = _make_report()
        gen = ReportGenerator(report)
        json_str = gen.to_json()

        parsed = json.loads(json_str)
        assert isinstance(parsed, dict)

    def test_to_json_contains_all_fields(self):
        """JSON output contains every top-level ScanReport field."""
        report = _make_report()
        gen = ReportGenerator(report)
        parsed = json.loads(gen.to_json())

        expected_keys = {
            "timestamp",
            "scan_duration_seconds",
            "summary",
            "mock_violations",
            "drift_issues",
            "compliance_violations",
            "frontend_violations",
            "untested_sources",
            "stale_failures",
        }
        assert expected_keys.issubset(parsed.keys()), (
            f"Missing keys: {expected_keys - parsed.keys()}"
        )

    def test_from_json_reconstructs_report(self):
        """Serialize → deserialize produces an equivalent ScanReport."""
        report = _make_report(
            mock_violations=[_make_mock_violation()],
            compliance_violations=[_make_compliance_violation()],
            stale_failures=[_make_stale_failure()],
            summary=_make_summary(
                by_category={"unit": CategorySummary(total=10, passing=8, failing=2)},
                issues_by_severity={"critical": 1},
            ),
        )
        gen = ReportGenerator(report)
        json_str = gen.to_json()
        restored = ReportGenerator.from_json(json_str)

        assert asdict(restored) == asdict(report)

    def test_from_json_handles_empty_report(self):
        """from_json works with a default (empty) ScanReport."""
        report = ScanReport()
        gen = ReportGenerator(report)
        json_str = gen.to_json()
        restored = ReportGenerator.from_json(json_str)

        assert asdict(restored) == asdict(report)


# ===================================================================
# TestReportGeneratorMarkdown
# ===================================================================


@pytest.mark.unit
class TestReportGeneratorMarkdown:
    """Markdown rendering tests."""

    def test_markdown_contains_title(self):
        """Markdown output starts with the report title."""
        gen = ReportGenerator(_make_report())
        md = gen.to_markdown()
        assert "# Test Health Scanner Report" in md

    def test_markdown_contains_summary_table(self):
        """Markdown contains the Summary section with table headers."""
        gen = ReportGenerator(_make_report())
        md = gen.to_markdown()
        assert "## Summary" in md
        assert "| Metric | Count |" in md
        assert "Total tests" in md

    def test_markdown_includes_mock_violations_when_present(self):
        """Mock Violations section appears when violations exist."""
        report = _make_report(mock_violations=[_make_mock_violation()])
        gen = ReportGenerator(report)
        md = gen.to_markdown()
        assert "## Mock Violations" in md
        assert "1" in md  # count
        assert "test_bad.py" in md

    def test_markdown_excludes_mock_violations_when_empty(self):
        """Mock Violations section is absent when no violations."""
        gen = ReportGenerator(_make_report())
        md = gen.to_markdown()
        assert "## Mock Violations" not in md

    def test_markdown_includes_regressions_with_trend(self):
        """Regressions section appears when trend has regressions."""
        trend = TrendReport(
            tests_newly_broken=1,
            regressions=["New mock violation: tests/unit/test_new.py"],
        )
        gen = ReportGenerator(_make_report())
        md = gen.to_markdown(trend=trend)
        assert "## Regressions" in md
        assert "1" in md
        assert "test_new.py" in md

    def test_markdown_includes_improvements_with_trend(self):
        """Improvements section appears when trend has improvements."""
        trend = TrendReport(
            tests_fixed=2,
            improvements=[
                "Mock violation fixed: tests/unit/test_a.py",
                "Compliance violation fixed: tests/unit/test_b.py (BU005)",
            ],
        )
        gen = ReportGenerator(_make_report())
        md = gen.to_markdown(trend=trend)
        assert "## Improvements" in md
        assert "2" in md
        assert "test_a.py" in md


# ===================================================================
# TestComputeTrend
# ===================================================================


@pytest.mark.unit
class TestComputeTrend:
    """Trend computation with concrete before/after examples."""

    def test_trend_detects_fixed_mock_violations(self):
        """Violation in before but not after → tests_fixed=1."""
        before = _make_report(
            mock_violations=[_make_mock_violation(file_path="test_a.py")],
        )
        after = _make_report(mock_violations=[])

        trend = compute_trend(before, after)
        assert trend.tests_fixed == 1
        assert trend.tests_newly_broken == 0

    def test_trend_detects_new_mock_violations(self):
        """Violation in after but not before → tests_newly_broken=1."""
        before = _make_report(mock_violations=[])
        after = _make_report(
            mock_violations=[_make_mock_violation(file_path="test_new.py")],
        )

        trend = compute_trend(before, after)
        assert trend.tests_newly_broken == 1
        assert trend.tests_fixed == 0

    def test_trend_detects_fixed_compliance_violations(self):
        """Compliance violation in before but not after → fixed."""
        before = _make_report(
            compliance_violations=[
                _make_compliance_violation(
                    file_path="test_c.py", rule_id="BU005",
                ),
            ],
        )
        after = _make_report(compliance_violations=[])

        trend = compute_trend(before, after)
        assert trend.tests_fixed == 1

    def test_trend_detects_new_stale_failures(self):
        """Stale failure in after but not before → newly_quarantined=1."""
        before = _make_report(stale_failures=[])
        after = _make_report(
            stale_failures=[_make_stale_failure(test_id="test_x::test_stale")],
        )

        trend = compute_trend(before, after)
        assert trend.tests_newly_quarantined == 1

    def test_trend_no_changes(self):
        """Same violations in both reports → all zeros."""
        violation = _make_mock_violation(file_path="test_same.py")
        before = _make_report(mock_violations=[violation])
        after = _make_report(mock_violations=[violation])

        trend = compute_trend(before, after)
        assert trend.tests_fixed == 0
        assert trend.tests_newly_broken == 0
        assert trend.tests_newly_quarantined == 0

    def test_trend_regressions_list_populated(self):
        """Regressions list contains human-readable descriptions."""
        before = _make_report(mock_violations=[])
        after = _make_report(
            mock_violations=[_make_mock_violation(file_path="test_reg.py")],
        )

        trend = compute_trend(before, after)
        assert len(trend.regressions) == 1
        assert "test_reg.py" in trend.regressions[0]


# ===================================================================
# TestLoadLatestReport
# ===================================================================


@pytest.mark.unit
class TestLoadLatestReport:
    """Tests for the load_latest_report() helper."""

    def test_load_latest_report_returns_none_for_empty_dir(self, tmp_path):
        """Empty directory returns None."""
        result = load_latest_report(str(tmp_path))
        assert result is None

    def test_load_latest_report_loads_most_recent(self, tmp_path):
        """With two scan_*.json files, the latest (by name) is loaded."""
        # Create two reports with different timestamps
        older = _make_report(timestamp="2025-01-01T00:00:00+00:00")
        newer = _make_report(timestamp="2025-06-15T12:00:00+00:00")

        older_path = tmp_path / "scan_20250101_000000.json"
        newer_path = tmp_path / "scan_20250615_120000.json"

        older_path.write_text(
            ReportGenerator(older).to_json(), encoding="utf-8",
        )
        newer_path.write_text(
            ReportGenerator(newer).to_json(), encoding="utf-8",
        )

        result = load_latest_report(str(tmp_path))
        assert result is not None
        assert result.timestamp == "2025-06-15T12:00:00+00:00"

    def test_load_latest_report_handles_corrupt_file(self, tmp_path):
        """Invalid JSON in the latest file returns None."""
        corrupt_path = tmp_path / "scan_20250601_000000.json"
        corrupt_path.write_text("NOT VALID JSON {{{", encoding="utf-8")

        result = load_latest_report(str(tmp_path))
        assert result is None


# ===================================================================
# TestReportGeneratorSave
# ===================================================================


@pytest.mark.unit
class TestReportGeneratorSave:
    """Tests for the save() file persistence method."""

    def test_save_creates_json_and_markdown_files(self, tmp_path):
        """save() creates both .json and .md files."""
        gen = ReportGenerator(_make_report())
        results = gen.save(str(tmp_path))

        assert results["json"] is not None
        assert results["markdown"] is not None
        assert os.path.isfile(results["json"])
        assert os.path.isfile(results["markdown"])

    def test_save_json_file_is_valid(self, tmp_path):
        """Saved JSON file can be loaded and parsed."""
        gen = ReportGenerator(_make_report())
        results = gen.save(str(tmp_path))

        with open(results["json"], "r", encoding="utf-8") as fh:
            parsed = json.loads(fh.read())

        assert isinstance(parsed, dict)
        assert "timestamp" in parsed
        assert "summary" in parsed

    def test_save_filenames_contain_timestamp(self, tmp_path):
        """Filenames match the scan_YYYYMMDD_HHMMSS pattern."""
        gen = ReportGenerator(_make_report())
        results = gen.save(str(tmp_path))

        pattern = re.compile(r"scan_\d{8}_\d{6}\.(json|md)$")
        json_name = os.path.basename(results["json"])
        md_name = os.path.basename(results["markdown"])

        assert pattern.search(json_name), (
            f"JSON filename '{json_name}' does not match expected pattern"
        )
        assert pattern.search(md_name), (
            f"Markdown filename '{md_name}' does not match expected pattern"
        )
