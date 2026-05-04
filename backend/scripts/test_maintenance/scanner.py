"""
Test Health Scanner — main orchestrator
========================================

Coordinates all analysis components (MockViolationDetector, ComplianceChecker,
DependencyMapper) and produces structured reports.

The scanner analyses backend test files for mock violations and compliance
issues, maps source files to tests, and identifies untested sources.  It
outputs machine-readable JSON and human-readable console summaries.

Components wired in Phase 3:
    - MockViolationDetector  (mock violations)
    - ComplianceChecker      (compliance violations)
    - DependencyMapper       (untested sources)

Components wired in Phase 4:
    - DriftDetector          (source-test drift)
    - FrontendScanner        (frontend test analysis)

CLI interface::

    # Full scan
    python -m backend.scripts.test_maintenance.scanner

    # Maintenance session mode
    python -m backend.scripts.test_maintenance.scanner --maintenance-session

    # Generate baseline
    python -m backend.scripts.test_maintenance.scanner --baseline

    # Frontend only
    python -m backend.scripts.test_maintenance.scanner --frontend-only
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .mock_violation_detector import (
    MockViolation,
    MockViolationDetector,
)
from .compliance_checker import (
    ComplianceChecker,
    ComplianceViolation,
)
from .dependency_mapper import (
    DependencyMapper,
    DependencyMap,
)
from .drift_detector import (
    DriftDetector,
    DriftIssue,
)
from .frontend_scanner import (
    FrontendScanner,
    FrontendViolation,
)
from .classification_registry import (
    ClassificationRegistry,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class CategorySummary:
    """Test counts for a single category (unit, integration, etc.)."""

    total: int = 0
    passing: int = 0
    failing: int = 0
    skipped: int = 0
    flaky: int = 0
    quarantined: int = 0


@dataclass
class ScanSummary:
    """Aggregate summary of the scan."""

    total_test_files: int = 0
    total_tests: int = 0
    passing: int = 0
    failing: int = 0
    skipped: int = 0
    flaky: int = 0
    quarantined: int = 0
    by_category: Dict[str, CategorySummary] = field(default_factory=dict)
    issues_by_severity: Dict[str, int] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)


@dataclass
class StaleFailure:
    """A test that has been failing for more than 14 days."""

    test_id: str
    failure_reason: str
    first_failure_date: str
    days_failing: int


@dataclass
class ScanReport:
    """Complete output of a scanner run."""

    timestamp: str = ""
    scan_duration_seconds: float = 0.0
    summary: ScanSummary = field(default_factory=ScanSummary)
    mock_violations: List[MockViolation] = field(default_factory=list)
    drift_issues: List[DriftIssue] = field(default_factory=list)
    compliance_violations: List[ComplianceViolation] = field(
        default_factory=list
    )
    frontend_violations: List[FrontendViolation] = field(default_factory=list)
    untested_sources: List[str] = field(default_factory=list)
    stale_failures: List[StaleFailure] = field(default_factory=list)


@dataclass
class BaselineSnapshot:
    """Initial snapshot of all currently failing tests."""

    timestamp: str = ""
    failing_tests: Dict[str, str] = field(default_factory=dict)
    total_failing: int = 0


@dataclass
class MaintenanceWorkItem:
    """A single item in the maintenance work list."""

    file_path: str = ""
    issue_type: str = ""
    root_cause: str = ""
    severity: str = ""
    description: str = ""
    suggested_fix: str = ""
    effort_estimate: str = ""


@dataclass
class MaintenanceWorkList:
    """Prioritised list of fixes grouped by root cause."""

    timestamp: str = ""
    items_by_root_cause: Dict[str, List[MaintenanceWorkItem]] = field(
        default_factory=dict
    )
    total_items: int = 0
    effort_by_category: Dict[str, str] = field(default_factory=dict)


@dataclass
class SessionSummary:
    """Comparison of two scan reports (before/after a maintenance session)."""

    tests_fixed: int = 0
    tests_newly_broken: int = 0
    tests_newly_quarantined: int = 0
    remaining_violations: int = 0
    session_id: str = ""
    started_at: str = ""
    completed_at: str = ""
    fixes_by_root_cause: Dict[str, int] = field(default_factory=dict)
    remaining_backlog: int = 0


# ---------------------------------------------------------------------------
# Severity ordering for work list prioritisation
# ---------------------------------------------------------------------------

_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}

# Root cause mapping from violation types
_ROOT_CAUSE_MAP = {
    "db_import": "database_mocking",
    "env_leak": "environment_dependency",
    "real_connection": "database_mocking",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class TestHealthScanner:
    """Main orchestrator for test health analysis.

    Coordinates MockViolationDetector, ComplianceChecker, and
    DependencyMapper to produce a comprehensive ScanReport.
    """

    __test__ = False  # Prevent pytest from collecting this as a test class

    def __init__(
        self,
        config_path: Optional[str] = None,
        registry_path: Optional[str] = None,
    ) -> None:
        """
        Args:
            config_path: Path to ``test-compliance-rules.json``.
                Defaults to ``backend/tests/test-compliance-rules.json``.
            registry_path: Path to ``test-classification-registry.json``.
                Defaults to ``backend/tests/test-classification-registry.json``.
        """
        if config_path is None:
            config_path = os.path.join(
                "backend", "tests", "test-compliance-rules.json"
            )
        if registry_path is None:
            registry_path = os.path.join(
                "backend", "tests", "test-classification-registry.json"
            )
        self._config_path = config_path
        self._registry_path = registry_path
        self._mock_detector = MockViolationDetector()
        self._compliance_checker = ComplianceChecker(config_path)
        self._dep_mapper = DependencyMapper()
        self._drift_detector: Optional[DriftDetector] = None
        self._frontend_scanner = FrontendScanner()
        self._registry = ClassificationRegistry(registry_path)

    # ------------------------------------------------------------------
    # Core scan
    # ------------------------------------------------------------------

    def scan(
        self,
        backend_test_dir: str = "backend/tests",
        frontend_src_dir: str = "frontend/src",
        frontend_test_dir: str = "frontend/tests",
        maintenance_session: bool = False,
    ) -> ScanReport:
        """Run full scan and return structured report.

        Args:
            backend_test_dir: Root directory for backend tests.
            frontend_src_dir: Root directory for frontend source.
            frontend_test_dir: Root directory for frontend tests.
            maintenance_session: If ``True``, include maintenance work list.

        Returns:
            A :class:`ScanReport` with all detected issues.
        """
        start = time.monotonic()
        report = ScanReport(
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        # --- Mock violations -----------------------------------------------
        backend_test_files = self._collect_test_files(
            backend_test_dir, suffix=".py"
        )
        unit_test_files = [
            f for f in backend_test_files
            if _is_unit_test(f)
        ]

        for test_file in unit_test_files:
            violations = self._mock_detector.analyze_file(test_file)
            report.mock_violations.extend(violations)

        # --- Compliance violations -----------------------------------------
        for test_file in backend_test_files:
            violations = self._compliance_checker.check_backend_test(test_file)
            report.compliance_violations.extend(violations)

        # Check route files for blueprint compliance
        route_dir = os.path.join("backend", "src", "routes")
        if os.path.isdir(route_dir):
            route_files = self._collect_test_files(route_dir, suffix=".py")
            for route_file in route_files:
                violations = self._compliance_checker.check_backend_route(
                    route_file
                )
                report.compliance_violations.extend(violations)

        # --- Dependency mapping (untested sources) -------------------------
        dep_map = None
        try:
            dep_map = self._dep_mapper.build_backend_map()
            report.untested_sources = list(dep_map.untested)
        except Exception as exc:
            logger.warning(
                "Dependency mapping failed: %s — skipping untested sources",
                exc,
            )

        # --- Drift detection -----------------------------------------------
        if dep_map is not None:
            try:
                self._drift_detector = DriftDetector(dep_map)
                drift_issues = self._drift_detector.detect_all_drift()
                report.drift_issues = drift_issues
            except Exception as exc:
                logger.warning(
                    "Drift detection failed: %s — skipping drift issues",
                    exc,
                )

        # --- Frontend scanning ---------------------------------------------
        try:
            frontend_report = self._frontend_scanner.scan_directory(
                frontend_src_dir
            )
            report.frontend_violations = frontend_report.violations
        except Exception as exc:
            logger.warning(
                "Frontend scanning failed: %s — skipping frontend violations",
                exc,
            )

        # --- Summary -------------------------------------------------------
        report.summary = self._build_summary(report, backend_test_files)

        # --- Stale failure detection (from classification registry) --------
        try:
            stale_entries = self._registry.get_stale_failures()
            for entry in stale_entries:
                sf = StaleFailure(
                    test_id=entry["test_id"],
                    failure_reason=entry["entry"].get("failure_reason", ""),
                    first_failure_date=entry["entry"].get("triage_date", ""),
                    days_failing=entry["days_failing"],
                )
                report.stale_failures.append(sf)
        except Exception as exc:
            logger.warning(
                "Stale failure detection failed: %s — skipping", exc
            )

        # --- Untriaged warning ---------------------------------------------
        try:
            untriaged_count = self._registry.get_untriaged_count()
            if untriaged_count > 10:
                report.summary.warnings.append(
                    f"WARNING: {untriaged_count} failing tests have no "
                    f"triage decision"
                )
        except Exception as exc:
            logger.warning(
                "Untriaged count check failed: %s — skipping", exc
            )

        report.scan_duration_seconds = round(time.monotonic() - start, 3)

        return report

    # ------------------------------------------------------------------
    # Baseline
    # ------------------------------------------------------------------

    def generate_baseline(
        self,
        backend_test_dir: str = "backend/tests",
        frontend_src_dir: str = "frontend/src",
        frontend_test_dir: str = "frontend/tests",
    ) -> BaselineSnapshot:
        """Create initial snapshot of all currently failing tests.

        Runs the scanner and records all mock violations and compliance
        violations as the baseline.  Also populates the classification
        registry with failing tests so they can be tracked for triage.

        Args:
            backend_test_dir: Root directory for backend tests.
            frontend_src_dir: Root directory for frontend source.
            frontend_test_dir: Root directory for frontend tests.
        """
        report = self.scan(
            backend_test_dir=backend_test_dir,
            frontend_src_dir=frontend_src_dir,
            frontend_test_dir=frontend_test_dir,
        )
        failing: Dict[str, str] = {}

        for v in report.mock_violations:
            test_id = f"{v.file_path}:{v.line_number}"
            failing[test_id] = v.description

        for v in report.compliance_violations:
            test_id = f"{v.file_path}:{v.line_number}"
            failing[test_id] = f"[{v.rule_id}] {v.expected_pattern}"

        # Populate classification registry with failing tests
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        for test_id, reason in failing.items():
            try:
                self._registry.add_test(test_id, {
                    "category": "unit",
                    "status": "failing",
                    "failure_reason": reason,
                    "triage_decision": "fix",
                    "triage_date": today,
                    "notes": "Auto-populated by baseline snapshot",
                })
            except Exception as exc:
                logger.warning(
                    "Failed to add %s to registry: %s", test_id, exc
                )

        try:
            self._registry.save()
        except Exception as exc:
            logger.warning("Failed to save registry: %s", exc)

        snapshot = BaselineSnapshot(
            timestamp=datetime.now(timezone.utc).isoformat(),
            failing_tests=failing,
            total_failing=len(failing),
        )

        # Persist baseline
        self._save_report(snapshot, "baseline")

        return snapshot

    # ------------------------------------------------------------------
    # Maintenance work list
    # ------------------------------------------------------------------

    def generate_maintenance_worklist(self) -> MaintenanceWorkList:
        """Generate prioritised fix list grouped by root cause."""
        report = self.scan()
        items_by_cause: Dict[str, List[MaintenanceWorkItem]] = {}

        # Mock violations → work items
        for v in report.mock_violations:
            root_cause = _ROOT_CAUSE_MAP.get(v.violation_type, "other")
            item = MaintenanceWorkItem(
                file_path=v.file_path,
                issue_type=v.violation_type,
                root_cause=root_cause,
                severity=v.severity,
                description=v.description,
                suggested_fix=v.suggested_fix,
                effort_estimate="15-30 min per test",
            )
            items_by_cause.setdefault(root_cause, []).append(item)

        # Compliance violations → work items
        for v in report.compliance_violations:
            root_cause = "convention_violation"
            item = MaintenanceWorkItem(
                file_path=v.file_path,
                issue_type=v.rule_id,
                root_cause=root_cause,
                severity=v.severity,
                description=f"[{v.rule_id}] {v.expected_pattern}",
                suggested_fix=f"See {v.convention_reference}",
                effort_estimate="5-15 min per file",
            )
            items_by_cause.setdefault(root_cause, []).append(item)

        # Drift issues → work items
        for v in report.drift_issues:
            root_cause_map = {
                "signature_change": "signature_change",
                "key_rename": "key_mismatch",
                "return_type_change": "signature_change",
            }
            root_cause = root_cause_map.get(v.drift_type, "other")
            item = MaintenanceWorkItem(
                file_path=v.test_file,
                issue_type=v.drift_type,
                root_cause=root_cause,
                severity=v.severity,
                description=v.description,
                suggested_fix=f"Update test to match source: {v.source_file}",
                effort_estimate="10-20 min per test",
            )
            items_by_cause.setdefault(root_cause, []).append(item)

        # Frontend violations → work items
        for v in report.frontend_violations:
            root_cause = f"frontend_{v.violation_type}"
            item = MaintenanceWorkItem(
                file_path=v.file_path,
                issue_type=v.violation_type,
                root_cause=root_cause,
                severity=v.severity,
                description=v.description,
                suggested_fix=v.suggested_fix,
                effort_estimate="10-20 min per file",
            )
            items_by_cause.setdefault(root_cause, []).append(item)

        # Sort within each group by severity
        for cause in items_by_cause:
            items_by_cause[cause].sort(
                key=lambda i: _SEVERITY_ORDER.get(i.severity, 99)
            )

        total = sum(len(items) for items in items_by_cause.values())

        return MaintenanceWorkList(
            timestamp=datetime.now(timezone.utc).isoformat(),
            items_by_root_cause=items_by_cause,
            total_items=total,
            effort_by_category={
                "database_mocking": "15-30 min per test",
                "environment_dependency": "10-20 min per test",
                "convention_violation": "5-15 min per file",
                "signature_change": "10-20 min per test",
                "key_mismatch": "10-20 min per test",
                "frontend_missing_msw": "10-20 min per file",
                "frontend_missing_provider": "5-10 min per file",
                "frontend_stale_import": "5-10 min per file",
            },
        )

    # ------------------------------------------------------------------
    # Session summary
    # ------------------------------------------------------------------

    def generate_session_summary(
        self, before: ScanReport, after: ScanReport
    ) -> SessionSummary:
        """Compare two reports to produce a maintenance session summary."""
        before_files = {v.file_path for v in before.mock_violations}
        after_files = {v.file_path for v in after.mock_violations}

        before_compliance = {
            (v.file_path, v.rule_id) for v in before.compliance_violations
        }
        after_compliance = {
            (v.file_path, v.rule_id) for v in after.compliance_violations
        }

        fixed_mock = before_files - after_files
        new_mock = after_files - before_files
        fixed_compliance = before_compliance - after_compliance
        new_compliance = after_compliance - before_compliance

        remaining = (
            len(after.mock_violations) + len(after.compliance_violations)
        )

        return SessionSummary(
            tests_fixed=len(fixed_mock) + len(fixed_compliance),
            tests_newly_broken=len(new_mock) + len(new_compliance),
            tests_newly_quarantined=0,
            remaining_violations=remaining,
            remaining_backlog=remaining,
        )

    # ------------------------------------------------------------------
    # Maintenance session lifecycle
    # ------------------------------------------------------------------

    def run_maintenance_session(
        self, before_report: ScanReport
    ) -> MaintenanceWorkList:
        """Start a maintenance session: generate and save the work list.

        This is the entry point for the maintenance session workflow.
        It generates a prioritised work list from the current scan state,
        saves it as a report, and returns it.

        Args:
            before_report: The scan report taken before the session starts.

        Returns:
            A :class:`MaintenanceWorkList` with prioritised fixes.
        """
        worklist = self.generate_maintenance_worklist()
        self._save_report(worklist, "maintenance_worklist")
        return worklist

    def complete_maintenance_session(
        self,
        before_report: ScanReport,
        after_report: ScanReport,
    ) -> SessionSummary:
        """Complete a maintenance session: summarise and persist results.

        Compares the before and after reports, computes fixes by root
        cause, saves the session summary report, and appends an entry
        to the session history file.

        Args:
            before_report: The scan report taken before the session.
            after_report:  The scan report taken after fixes.

        Returns:
            A :class:`SessionSummary` with session results.
        """
        summary = self.generate_session_summary(before_report, after_report)

        # Compute fixes by root cause
        before_items = self._violations_by_root_cause(before_report)
        after_items = self._violations_by_root_cause(after_report)
        fixes_by_root_cause: Dict[str, int] = {}
        for cause, before_count in before_items.items():
            after_count = after_items.get(cause, 0)
            fixed = max(0, before_count - after_count)
            if fixed > 0:
                fixes_by_root_cause[cause] = fixed

        now = datetime.now(timezone.utc)
        summary.session_id = now.strftime("%Y%m%d_%H%M%S")
        summary.completed_at = now.isoformat()
        if not summary.started_at:
            summary.started_at = before_report.timestamp or now.isoformat()
        summary.fixes_by_root_cause = fixes_by_root_cause

        self._save_report(summary, "session_summary")
        self._save_session_history(summary)

        return summary

    # ------------------------------------------------------------------
    # Session history persistence
    # ------------------------------------------------------------------

    def _save_session_history(self, summary: SessionSummary) -> Optional[str]:
        """Append a session entry to the session history file.

        Loads existing history from
        ``backend/tests/reports/session_history.json`` (or creates a new
        one), appends the current session, and writes back atomically.

        Returns the output path, or ``None`` on failure.
        """
        reports_dir = os.path.join("backend", "tests", "reports")
        os.makedirs(reports_dir, exist_ok=True)
        history_path = os.path.join(reports_dir, "session_history.json")

        # Load existing history
        history: Dict[str, Any] = {"sessions": []}
        if os.path.isfile(history_path):
            try:
                with open(history_path, "r", encoding="utf-8") as fh:
                    history = json.load(fh)
            except (OSError, json.JSONDecodeError) as exc:
                logger.warning(
                    "Could not load session history: %s — starting fresh",
                    exc,
                )
                history = {"sessions": []}

        # Build session entry
        entry = {
            "session_id": summary.session_id,
            "started_at": summary.started_at,
            "completed_at": summary.completed_at,
            "tests_fixed": summary.tests_fixed,
            "tests_quarantined": summary.tests_newly_quarantined,
            "tests_deleted": 0,
            "remaining_backlog": summary.remaining_backlog,
            "fixes_by_root_cause": summary.fixes_by_root_cause,
        }
        history["sessions"].append(entry)

        # Atomic write
        try:
            tmp_path = history_path + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as fh:
                json.dump(history, fh, indent=2, default=str)
            os.replace(tmp_path, history_path)
            logger.info("Session history updated: %s", history_path)
            return history_path
        except OSError as exc:
            logger.error("Failed to save session history: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Internal: root cause counting
    # ------------------------------------------------------------------

    def _violations_by_root_cause(
        self, report: ScanReport
    ) -> Dict[str, int]:
        """Count violations per root cause in a report."""
        counts: Dict[str, int] = {}
        for v in report.mock_violations:
            cause = _ROOT_CAUSE_MAP.get(v.violation_type, "other")
            counts[cause] = counts.get(cause, 0) + 1
        for v in report.compliance_violations:
            counts["convention_violation"] = (
                counts.get("convention_violation", 0) + 1
            )
        for v in report.drift_issues:
            drift_map = {
                "signature_change": "signature_change",
                "key_rename": "key_mismatch",
                "return_type_change": "signature_change",
            }
            cause = drift_map.get(v.drift_type, "other")
            counts[cause] = counts.get(cause, 0) + 1
        return counts

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _collect_test_files(
        self, directory: str, suffix: str = ".py"
    ) -> List[str]:
        """Recursively collect files with *suffix* under *directory*."""
        files: List[str] = []
        dir_path = Path(directory)

        if not dir_path.is_dir():
            logger.warning("Directory does not exist: %s", directory)
            return files

        for root, _dirs, filenames in os.walk(directory):
            # Skip __pycache__ and hidden directories
            _dirs[:] = [
                d for d in _dirs
                if not d.startswith(".") and d != "__pycache__"
            ]
            for fname in filenames:
                if fname.endswith(suffix) and not fname.startswith("."):
                    files.append(os.path.join(root, fname))

        return sorted(files)

    def _build_summary(
        self,
        report: ScanReport,
        test_files: List[str],
    ) -> ScanSummary:
        """Build a ScanSummary from the report data."""
        issues_by_severity: Dict[str, int] = {}

        for v in report.mock_violations:
            issues_by_severity[v.severity] = (
                issues_by_severity.get(v.severity, 0) + 1
            )

        for v in report.compliance_violations:
            sev = v.severity
            issues_by_severity[sev] = issues_by_severity.get(sev, 0) + 1

        for v in report.drift_issues:
            sev = v.severity
            issues_by_severity[sev] = issues_by_severity.get(sev, 0) + 1

        for v in report.frontend_violations:
            sev = v.severity
            issues_by_severity[sev] = issues_by_severity.get(sev, 0) + 1

        return ScanSummary(
            total_test_files=len(test_files),
            issues_by_severity=issues_by_severity,
        )

    def _save_report(self, data: Any, label: str) -> Optional[str]:
        """Save a report/snapshot to the reports directory.

        Uses atomic writes (write to temp, then rename) for safety.
        Returns the output path, or ``None`` on failure.
        """
        reports_dir = os.path.join("backend", "tests", "reports")
        os.makedirs(reports_dir, exist_ok=True)

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"{label}_{timestamp}.json"
        output_path = os.path.join(reports_dir, filename)

        try:
            # Atomic write: write to temp file, then rename
            tmp_path = output_path + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as fh:
                json.dump(asdict(data), fh, indent=2, default=str)
            os.replace(tmp_path, output_path)
            logger.info("Report saved to %s", output_path)
            return output_path
        except OSError as exc:
            logger.error("Failed to save report: %s", exc)
            return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_unit_test(file_path: str) -> bool:
    """Return ``True`` if *file_path* is inside a ``unit/`` test directory."""
    normalised = file_path.replace("\\", "/")
    return "/unit/" in normalised or "/tests/unit" in normalised


# ---------------------------------------------------------------------------
# CLI interface
# ---------------------------------------------------------------------------

def _build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Test Health Scanner — analyse test files for issues",
    )
    parser.add_argument(
        "--maintenance-session",
        action="store_true",
        help="Generate a prioritised maintenance work list",
    )
    parser.add_argument(
        "--baseline",
        action="store_true",
        help="Generate a baseline snapshot of current failures",
    )
    parser.add_argument(
        "--frontend-only",
        action="store_true",
        help="Scan only frontend test files",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to test-compliance-rules.json",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entry point.

    Returns:
        Exit code: 0 = clean, 1 = issues found, 2 = scanner error.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    parser = _build_cli_parser()
    args = parser.parse_args(argv)

    try:
        scanner = TestHealthScanner(config_path=args.config)

        if args.baseline:
            snapshot = scanner.generate_baseline()
            print(f"\nBaseline snapshot created: {snapshot.total_failing} "
                  f"failing tests recorded.")
            return 0

        if args.maintenance_session:
            worklist = scanner.generate_maintenance_worklist()
            scanner._save_report(worklist, "maintenance_worklist")

            print(f"\n=== Maintenance Session Work List ===")
            print(f"Total items: {worklist.total_items}")
            print()

            for cause, items in worklist.items_by_root_cause.items():
                effort = worklist.effort_by_category.get(cause, "unknown")
                print(f"  [{cause}] — {len(items)} item(s), "
                      f"effort: {effort}")
                for item in items:
                    print(f"    [{item.severity:8s}] {item.file_path}")
                    print(f"             {item.description}")
                print()

            if worklist.effort_by_category:
                print("Effort estimates by category:")
                for cat, est in sorted(
                    worklist.effort_by_category.items()
                ):
                    print(f"  {cat}: {est}")

            return 0

        # Default: full scan
        report = scanner.scan()

        # Save JSON + Markdown reports
        from .report_generator import ReportGenerator
        gen = ReportGenerator(report)
        saved = gen.save()
        if saved.get("json"):
            print(f"\nJSON report saved:     {saved['json']}")
        if saved.get("markdown"):
            print(f"Markdown report saved: {saved['markdown']}")

        # Print summary
        print("\n=== Test Health Scanner Report ===")
        print(f"Timestamp: {report.timestamp}")
        print(f"Duration:  {report.scan_duration_seconds}s")
        print(f"Test files scanned: {report.summary.total_test_files}")
        print(f"\nMock violations:       {len(report.mock_violations)}")
        print(f"Drift issues:          {len(report.drift_issues)}")
        print(f"Compliance violations: {len(report.compliance_violations)}")
        print(f"Frontend violations:   {len(report.frontend_violations)}")
        print(f"Untested sources:      {len(report.untested_sources)}")
        print(f"Stale failures:        {len(report.stale_failures)}")

        if report.stale_failures:
            print("\nStale failures (> 14 days):")
            for sf in report.stale_failures:
                print(f"  {sf.test_id} — {sf.days_failing} days "
                      f"(since {sf.first_failure_date})")

        if report.summary.warnings:
            print()
            for warning in report.summary.warnings:
                print(warning)

        if report.summary.issues_by_severity:
            print("\nIssues by severity:")
            _SEVERITY_DISPLAY_ORDER = [
                "critical", "forbidden", "high", "medium",
                "required", "recommended", "low",
            ]
            for sev in _SEVERITY_DISPLAY_ORDER:
                count = report.summary.issues_by_severity.get(sev, 0)
                if count:
                    print(f"  {sev}: {count}")
            # Any severities not in the predefined order
            for sev, count in sorted(report.summary.issues_by_severity.items()):
                if sev not in _SEVERITY_DISPLAY_ORDER:
                    print(f"  {sev}: {count}")

        total_issues = (
            len(report.mock_violations)
            + len(report.drift_issues)
            + len(report.compliance_violations)
            + len(report.frontend_violations)
        )
        return 1 if total_issues > 0 else 0

    except Exception as exc:
        logger.error("Scanner error: %s", exc, exc_info=True)
        return 2


if __name__ == "__main__":
    sys.exit(main())
