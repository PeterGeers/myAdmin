"""
Report Generator — JSON and Markdown output
============================================

Produces machine-readable JSON and human-readable Markdown reports from
:class:`ScanReport` data.  Supports serialization round-trips (JSON →
object → JSON) and timestamped file storage in ``backend/tests/reports/``.

Only stdlib dependencies are used: ``dataclasses``, ``json``, ``logging``,
``os``, ``pathlib``, ``datetime``.

Requirements: 1.5, 7.3, 7.5
"""

from __future__ import annotations

import glob
import json
import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .scanner import (
    CategorySummary,
    ScanReport,
    ScanSummary,
    StaleFailure,
)
from .mock_violation_detector import MockViolation
from .drift_detector import DriftIssue
from .compliance_checker import ComplianceViolation
from .frontend_scanner import FrontendViolation

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class TrendReport:
    """Result of comparing two :class:`ScanReport` instances (before/after).

    Attributes:
        tests_fixed: Number of violations present in *before* but absent in *after*.
        tests_newly_broken: Number of violations present in *after* but absent in *before*.
        tests_newly_quarantined: Stale failures in *after* but not in *before*.
        regressions: Human-readable descriptions of newly broken items.
        improvements: Human-readable descriptions of fixed items.
    """

    tests_fixed: int = 0
    tests_newly_broken: int = 0
    tests_newly_quarantined: int = 0
    regressions: List[str] = field(default_factory=list)
    improvements: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Public API — standalone functions
# ---------------------------------------------------------------------------


def compute_trend(before: ScanReport, after: ScanReport) -> TrendReport:
    """Compare two :class:`ScanReport` instances and compute a trend.

    *Fixed* means a violation was present in *before* but absent in *after*.
    *Newly broken* means a violation is present in *after* but was absent in
    *before*.  *Newly quarantined* means a stale failure appears in *after*
    but not in *before*.

    Mock violations are keyed by ``file_path``; compliance violations are
    keyed by ``(file_path, rule_id)``.

    Args:
        before: The earlier scan report.
        after:  The later scan report.

    Returns:
        A :class:`TrendReport` summarising the differences.
    """
    # -- mock violations (keyed by file_path) ------------------------------
    before_mock_keys = {v.file_path for v in before.mock_violations}
    after_mock_keys = {v.file_path for v in after.mock_violations}

    fixed_mock = before_mock_keys - after_mock_keys
    new_mock = after_mock_keys - before_mock_keys

    # -- compliance violations (keyed by (file_path, rule_id)) -------------
    before_comp_keys = {
        (v.file_path, v.rule_id) for v in before.compliance_violations
    }
    after_comp_keys = {
        (v.file_path, v.rule_id) for v in after.compliance_violations
    }

    fixed_comp = before_comp_keys - after_comp_keys
    new_comp = after_comp_keys - before_comp_keys

    # -- stale failures (keyed by test_id) ---------------------------------
    before_stale_ids = {sf.test_id for sf in before.stale_failures}
    after_stale_ids = {sf.test_id for sf in after.stale_failures}

    new_quarantined = after_stale_ids - before_stale_ids

    # -- build human-readable lists ----------------------------------------
    improvements: List[str] = []
    for fp in sorted(fixed_mock):
        improvements.append(f"Mock violation fixed: {fp}")
    for fp, rid in sorted(fixed_comp):
        improvements.append(f"Compliance violation fixed: {fp} ({rid})")

    regressions: List[str] = []
    for fp in sorted(new_mock):
        regressions.append(f"New mock violation: {fp}")
    for fp, rid in sorted(new_comp):
        regressions.append(f"New compliance violation: {fp} ({rid})")

    tests_fixed = len(fixed_mock) + len(fixed_comp)
    tests_newly_broken = len(new_mock) + len(new_comp)
    tests_newly_quarantined = len(new_quarantined)

    return TrendReport(
        tests_fixed=tests_fixed,
        tests_newly_broken=tests_newly_broken,
        tests_newly_quarantined=tests_newly_quarantined,
        regressions=regressions,
        improvements=improvements,
    )


def load_latest_report(
    reports_dir: str = "backend/tests/reports",
) -> Optional[ScanReport]:
    """Load the most recent ``scan_*.json`` report from *reports_dir*.

    Files are sorted lexicographically by name (which embeds a timestamp)
    so the last entry is the most recent.

    Args:
        reports_dir: Directory containing historical scan reports.

    Returns:
        The deserialized :class:`ScanReport`, or ``None`` if no reports
        exist or the latest file cannot be read.
    """
    pattern = os.path.join(reports_dir, "scan_*.json")
    files = sorted(glob.glob(pattern))
    if not files:
        logger.info("No previous scan reports found in %s", reports_dir)
        return None

    latest = files[-1]
    try:
        with open(latest, "r", encoding="utf-8") as fh:
            json_str = fh.read()
        report = ReportGenerator.from_json(json_str)
        logger.info("Loaded previous report from %s", latest)
        return report
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        logger.warning(
            "Failed to load previous report %s: %s", latest, exc,
        )
        return None


# ---------------------------------------------------------------------------
# Public API — ReportGenerator class
# ---------------------------------------------------------------------------


class ReportGenerator:
    """Generate JSON and Markdown reports from a :class:`ScanReport`.

    Args:
        report: The scan report to render.

    Example::

        gen = ReportGenerator(report)
        print(gen.to_markdown())
        gen.save("backend/tests/reports")
    """

    def __init__(self, report: ScanReport) -> None:
        self._report = report

    # ------------------------------------------------------------------
    # JSON serialization
    # ------------------------------------------------------------------

    def to_json(self, indent: int = 2) -> str:
        """Serialize the full :class:`ScanReport` to a JSON string.

        Uses :func:`dataclasses.asdict` for conversion.  All fields are
        preserved so the output can be deserialized back via
        :meth:`from_json`.

        Args:
            indent: JSON indentation level.  Defaults to ``2``.

        Returns:
            A JSON string representing the complete report.
        """
        return json.dumps(asdict(self._report), indent=indent, default=str)

    @staticmethod
    def from_json(json_str: str) -> ScanReport:
        """Deserialize a JSON string back into a :class:`ScanReport`.

        Handles nested dataclasses (``MockViolation``, ``DriftIssue``,
        ``ComplianceViolation``, ``FrontendViolation``, ``StaleFailure``,
        ``ScanSummary``, ``CategorySummary``).

        Args:
            json_str: A JSON string previously produced by :meth:`to_json`.

        Returns:
            A reconstructed :class:`ScanReport`.
        """
        data: Dict[str, Any] = json.loads(json_str)
        return _dict_to_scan_report(data)

    # ------------------------------------------------------------------
    # Markdown rendering
    # ------------------------------------------------------------------

    def to_markdown(self, trend: Optional[TrendReport] = None) -> str:
        """Render the report as a Markdown string.

        Sections included:

        - Summary table (total tests, passing, failing, skipped, flaky,
          quarantined)
        - Issues by severity table
        - Regressions (if *trend* is provided and has regressions)
        - Improvements (if *trend* is provided and has improvements)
        - Mock violations (if any)
        - Drift issues (if any)
        - Compliance violations (if any)
        - Frontend violations (if any)
        - Quarantine / stale failures section (if any)
        - Untested sources section (if any)

        Args:
            trend: Optional trend comparison to include regression /
                improvement sections.

        Returns:
            A Markdown-formatted string.
        """
        rpt = self._report
        parts: List[str] = []

        # Title
        parts.append("# Test Health Scanner Report")
        parts.append("")
        parts.append(f"**Timestamp:** {rpt.timestamp}  ")
        parts.append(
            f"**Scan duration:** {rpt.scan_duration_seconds:.3f}s"
        )
        parts.append("")

        # Summary table
        parts.append("## Summary")
        parts.append("")
        parts.append("| Metric | Count |")
        parts.append("|--------|------:|")
        parts.append(
            f"| Total test files | {rpt.summary.total_test_files} |"
        )
        parts.append(f"| Total tests | {rpt.summary.total_tests} |")
        parts.append(f"| Passing | {rpt.summary.passing} |")
        parts.append(f"| Failing | {rpt.summary.failing} |")
        parts.append(f"| Skipped | {rpt.summary.skipped} |")
        parts.append(f"| Flaky | {rpt.summary.flaky} |")
        parts.append(f"| Quarantined | {rpt.summary.quarantined} |")
        parts.append("")

        # Issues by severity
        if rpt.summary.issues_by_severity:
            parts.append("### Issues by Severity")
            parts.append("")
            parts.append("| Severity | Count |")
            parts.append("|----------|------:|")
            for sev in ("critical", "high", "medium", "low"):
                count = rpt.summary.issues_by_severity.get(sev, 0)
                if count > 0:
                    parts.append(f"| {sev} | {count} |")
            # Include any non-standard severities
            for sev, count in sorted(
                rpt.summary.issues_by_severity.items()
            ):
                if sev not in ("critical", "high", "medium", "low"):
                    parts.append(f"| {sev} | {count} |")
            parts.append("")

        # Category breakdown
        if rpt.summary.by_category:
            parts.append("### By Category")
            parts.append("")
            parts.append(
                "| Category | Total | Passing | Failing "
                "| Skipped | Flaky | Quarantined |"
            )
            parts.append(
                "|----------|------:|--------:|--------:"
                "|--------:|------:|------------:|"
            )
            for cat, cs in sorted(rpt.summary.by_category.items()):
                parts.append(
                    f"| {cat} | {cs.total} | {cs.passing} | {cs.failing} "
                    f"| {cs.skipped} | {cs.flaky} | {cs.quarantined} |"
                )
            parts.append("")

        # Regressions (from trend comparison)
        if trend and trend.regressions:
            parts.append("## Regressions")
            parts.append("")
            parts.append(
                f"**{len(trend.regressions)}** regression(s) detected "
                f"since previous scan."
            )
            parts.append("")
            for desc in trend.regressions:
                parts.append(f"- {desc}")
            parts.append("")

        # Improvements (from trend comparison)
        if trend and trend.improvements:
            parts.append("## Improvements")
            parts.append("")
            parts.append(
                f"**{len(trend.improvements)}** improvement(s) since "
                f"previous scan."
            )
            parts.append("")
            for desc in trend.improvements:
                parts.append(f"- {desc}")
            parts.append("")

        # Mock violations
        if rpt.mock_violations:
            parts.append("## Mock Violations")
            parts.append("")
            parts.append(
                f"**{len(rpt.mock_violations)}** mock violation(s) detected."
            )
            parts.append("")
            parts.append(
                "| File | Line | Type | Severity | Description |"
            )
            parts.append(
                "|------|-----:|------|----------|-------------|"
            )
            for v in rpt.mock_violations:
                desc = _escape_md(v.description)
                parts.append(
                    f"| {v.file_path} | {v.line_number} "
                    f"| {v.violation_type} | {v.severity} | {desc} |"
                )
            parts.append("")

        # Drift issues
        if rpt.drift_issues:
            parts.append("## Drift Issues")
            parts.append("")
            parts.append(
                f"**{len(rpt.drift_issues)}** drift issue(s) detected."
            )
            parts.append("")
            parts.append(
                "| Source | Test | Line | Type | Severity | Description |"
            )
            parts.append(
                "|--------|------|-----:|------|----------|-------------|"
            )
            for d in rpt.drift_issues:
                desc = _escape_md(d.description)
                parts.append(
                    f"| {d.source_file} | {d.test_file} "
                    f"| {d.line_number} | {d.drift_type} "
                    f"| {d.severity} | {desc} |"
                )
            parts.append("")

        # Compliance violations
        if rpt.compliance_violations:
            parts.append("## Compliance Violations")
            parts.append("")
            parts.append(
                f"**{len(rpt.compliance_violations)}** compliance "
                f"violation(s) detected."
            )
            parts.append("")
            parts.append(
                "| File | Line | Rule | Severity | Expected |"
            )
            parts.append(
                "|------|-----:|------|----------|----------|"
            )
            for c in rpt.compliance_violations:
                expected = _escape_md(c.expected_pattern)
                parts.append(
                    f"| {c.file_path} | {c.line_number} "
                    f"| {c.rule_id} | {c.severity} | {expected} |"
                )
            parts.append("")

        # Frontend violations
        if rpt.frontend_violations:
            parts.append("## Frontend Violations")
            parts.append("")
            parts.append(
                f"**{len(rpt.frontend_violations)}** frontend "
                f"violation(s) detected."
            )
            parts.append("")
            parts.append(
                "| File | Line | Type | Severity | Description |"
            )
            parts.append(
                "|------|-----:|------|----------|-------------|"
            )
            for f in rpt.frontend_violations:
                desc = _escape_md(f.description)
                parts.append(
                    f"| {f.file_path} | {f.line_number} "
                    f"| {f.violation_type} | {f.severity} | {desc} |"
                )
            parts.append("")

        # Stale failures / quarantine
        if rpt.stale_failures:
            parts.append("## Quarantine — Stale Failures")
            parts.append("")
            parts.append(
                f"**{len(rpt.stale_failures)}** test(s) failing for "
                f">14 days."
            )
            parts.append("")
            parts.append(
                "| Test ID | Days Failing | First Failure | Reason |"
            )
            parts.append(
                "|---------|------------:|---------------|--------|"
            )
            for sf in rpt.stale_failures:
                reason = _escape_md(sf.failure_reason)
                parts.append(
                    f"| {sf.test_id} | {sf.days_failing} "
                    f"| {sf.first_failure_date} | {reason} |"
                )
            parts.append("")

        # Untested sources
        if rpt.untested_sources:
            parts.append("## Untested Sources")
            parts.append("")
            parts.append(
                f"**{len(rpt.untested_sources)}** source file(s) "
                f"with no corresponding tests."
            )
            parts.append("")
            for src in sorted(rpt.untested_sources):
                parts.append(f"- `{src}`")
            parts.append("")

        # Warnings
        if rpt.summary.warnings:
            parts.append("## Warnings")
            parts.append("")
            for w in rpt.summary.warnings:
                parts.append(f"- {w}")
            parts.append("")

        return "\n".join(parts)

    # ------------------------------------------------------------------
    # File persistence
    # ------------------------------------------------------------------

    def save(
        self,
        output_dir: str = "backend/tests/reports",
    ) -> Dict[str, Optional[str]]:
        """Save both JSON and Markdown reports with timestamped filenames.

        Files are written atomically (write to ``.tmp``, then rename).

        Args:
            output_dir: Directory to write reports into.

        Returns:
            A dict with ``"json"`` and ``"markdown"`` keys mapping to the
            saved file paths (or ``None`` on failure).
        """
        os.makedirs(output_dir, exist_ok=True)

        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        json_path = os.path.join(output_dir, f"scan_{ts}.json")
        md_path = os.path.join(output_dir, f"scan_{ts}.md")

        results: Dict[str, Optional[str]] = {
            "json": None,
            "markdown": None,
        }

        results["json"] = _atomic_write(json_path, self.to_json())
        results["markdown"] = _atomic_write(md_path, self.to_markdown())

        return results


# ---------------------------------------------------------------------------
# Internal helpers — deserialization
# ---------------------------------------------------------------------------


def _dict_to_scan_report(data: Dict[str, Any]) -> ScanReport:
    """Reconstruct a :class:`ScanReport` from a plain dict."""
    summary_data = data.get("summary", {})
    summary = _dict_to_scan_summary(summary_data)

    mock_violations = [
        MockViolation(**v) for v in data.get("mock_violations", [])
    ]
    drift_issues = [
        DriftIssue(**d) for d in data.get("drift_issues", [])
    ]
    compliance_violations = [
        ComplianceViolation(**c)
        for c in data.get("compliance_violations", [])
    ]
    frontend_violations = [
        FrontendViolation(**f)
        for f in data.get("frontend_violations", [])
    ]
    stale_failures = [
        StaleFailure(**s) for s in data.get("stale_failures", [])
    ]

    return ScanReport(
        timestamp=data.get("timestamp", ""),
        scan_duration_seconds=data.get("scan_duration_seconds", 0.0),
        summary=summary,
        mock_violations=mock_violations,
        drift_issues=drift_issues,
        compliance_violations=compliance_violations,
        frontend_violations=frontend_violations,
        untested_sources=data.get("untested_sources", []),
        stale_failures=stale_failures,
    )


def _dict_to_scan_summary(data: Dict[str, Any]) -> ScanSummary:
    """Reconstruct a :class:`ScanSummary` from a plain dict."""
    by_category: Dict[str, CategorySummary] = {}
    for cat_name, cat_data in data.get("by_category", {}).items():
        by_category[cat_name] = CategorySummary(**cat_data)

    return ScanSummary(
        total_test_files=data.get("total_test_files", 0),
        total_tests=data.get("total_tests", 0),
        passing=data.get("passing", 0),
        failing=data.get("failing", 0),
        skipped=data.get("skipped", 0),
        flaky=data.get("flaky", 0),
        quarantined=data.get("quarantined", 0),
        by_category=by_category,
        issues_by_severity=data.get("issues_by_severity", {}),
        warnings=data.get("warnings", []),
    )


# ---------------------------------------------------------------------------
# Internal helpers — Markdown
# ---------------------------------------------------------------------------


def _escape_md(text: str) -> str:
    """Escape pipe characters for Markdown table cells."""
    return text.replace("|", "\\|").replace("\n", " ")


# ---------------------------------------------------------------------------
# Internal helpers — file I/O
# ---------------------------------------------------------------------------


def _atomic_write(path: str, content: str) -> Optional[str]:
    """Write *content* to *path* atomically via a temp file.

    Returns the path on success, ``None`` on failure.
    """
    tmp_path = path + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.replace(tmp_path, path)
        logger.info("Report saved to %s", path)
        return path
    except OSError as exc:
        logger.error("Failed to save report to %s: %s", path, exc)
        # Clean up temp file if it exists
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        return None
