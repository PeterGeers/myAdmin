"""
Property-based tests for the Report Generator.

Uses Hypothesis to verify universal properties of report serialization
and deserialization round-trips.
"""
from dataclasses import asdict

import pytest
from hypothesis import given, strategies as st, settings, HealthCheck

from scripts.test_maintenance.scanner import (
    CategorySummary,
    ScanReport,
    ScanSummary,
    StaleFailure,
)
from scripts.test_maintenance.mock_violation_detector import MockViolation
from scripts.test_maintenance.drift_detector import DriftIssue
from scripts.test_maintenance.compliance_checker import ComplianceViolation
from scripts.test_maintenance.frontend_scanner import FrontendViolation
from scripts.test_maintenance.dependency_mapper import DependencyMap
from scripts.test_maintenance.report_generator import ReportGenerator


# ---------------------------------------------------------------------------
# Hypothesis strategies — atomic building blocks
# ---------------------------------------------------------------------------

# Safe text that avoids surrogates and null bytes (JSON-safe)
_safe_text = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "P", "Z"),
        blacklist_characters="\x00",
    ),
    min_size=0,
    max_size=30,
)

_nonempty_text = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "P", "Z"),
        blacklist_characters="\x00",
    ),
    min_size=1,
    max_size=30,
)

_severity = st.sampled_from(["critical", "high", "medium", "low"])

_nonneg_int = st.integers(min_value=0, max_value=1000)

_nonneg_float = st.floats(
    min_value=0.0, max_value=10000.0, allow_nan=False, allow_infinity=False,
)

_line_number = st.integers(min_value=0, max_value=5000)


# ---------------------------------------------------------------------------
# Hypothesis strategies — dataclass builders
# ---------------------------------------------------------------------------

@st.composite
def st_category_summary(draw):
    """Generate an arbitrary CategorySummary."""
    return CategorySummary(
        total=draw(_nonneg_int),
        passing=draw(_nonneg_int),
        failing=draw(_nonneg_int),
        skipped=draw(_nonneg_int),
        flaky=draw(_nonneg_int),
        quarantined=draw(_nonneg_int),
    )


@st.composite
def st_scan_summary(draw):
    """Generate an arbitrary ScanSummary with nested CategorySummary dicts."""
    cat_keys = draw(st.lists(_nonempty_text, min_size=0, max_size=3, unique=True))
    by_category = {}
    for key in cat_keys:
        by_category[key] = draw(st_category_summary())

    sev_keys = draw(st.lists(
        st.sampled_from(["critical", "high", "medium", "low"]),
        min_size=0,
        max_size=4,
        unique=True,
    ))
    issues_by_severity = {k: draw(_nonneg_int) for k in sev_keys}

    warnings = draw(st.lists(_safe_text, min_size=0, max_size=3))

    return ScanSummary(
        total_test_files=draw(_nonneg_int),
        total_tests=draw(_nonneg_int),
        passing=draw(_nonneg_int),
        failing=draw(_nonneg_int),
        skipped=draw(_nonneg_int),
        flaky=draw(_nonneg_int),
        quarantined=draw(_nonneg_int),
        by_category=by_category,
        issues_by_severity=issues_by_severity,
        warnings=warnings,
    )


@st.composite
def st_mock_violation(draw):
    """Generate an arbitrary MockViolation."""
    return MockViolation(
        file_path=draw(_nonempty_text),
        line_number=draw(_line_number),
        violation_type=draw(st.sampled_from(["db_import", "env_leak", "real_connection"])),
        severity=draw(_severity),
        description=draw(_safe_text),
        suggested_fix=draw(_safe_text),
    )


@st.composite
def st_drift_issue(draw):
    """Generate an arbitrary DriftIssue."""
    return DriftIssue(
        source_file=draw(_nonempty_text),
        test_file=draw(_nonempty_text),
        line_number=draw(_line_number),
        drift_type=draw(st.sampled_from(["signature_change", "key_rename", "return_type_change"])),
        severity=draw(_severity),
        old_value=draw(_safe_text),
        new_value=draw(_safe_text),
        description=draw(_safe_text),
    )


@st.composite
def st_compliance_violation(draw):
    """Generate an arbitrary ComplianceViolation."""
    return ComplianceViolation(
        file_path=draw(_nonempty_text),
        line_number=draw(_line_number),
        rule_id=draw(_nonempty_text),
        severity=draw(st.sampled_from(["required", "recommended", "forbidden"])),
        expected_pattern=draw(_safe_text),
        actual_pattern=draw(_safe_text),
        convention_reference=draw(_safe_text),
    )


@st.composite
def st_frontend_violation(draw):
    """Generate an arbitrary FrontendViolation."""
    return FrontendViolation(
        file_path=draw(_nonempty_text),
        line_number=draw(_line_number),
        violation_type=draw(st.sampled_from(["missing_msw", "missing_provider", "stale_import"])),
        severity=draw(_severity),
        description=draw(_safe_text),
        suggested_fix=draw(_safe_text),
    )


@st.composite
def st_stale_failure(draw):
    """Generate an arbitrary StaleFailure."""
    return StaleFailure(
        test_id=draw(_nonempty_text),
        failure_reason=draw(_safe_text),
        first_failure_date=draw(_nonempty_text),
        days_failing=draw(st.integers(min_value=0, max_value=365)),
    )


@st.composite
def st_scan_report(draw):
    """Generate an arbitrary ScanReport with all nested structures."""
    return ScanReport(
        timestamp=draw(_safe_text),
        scan_duration_seconds=draw(_nonneg_float),
        summary=draw(st_scan_summary()),
        mock_violations=draw(st.lists(st_mock_violation(), min_size=0, max_size=3)),
        drift_issues=draw(st.lists(st_drift_issue(), min_size=0, max_size=3)),
        compliance_violations=draw(st.lists(st_compliance_violation(), min_size=0, max_size=3)),
        frontend_violations=draw(st.lists(st_frontend_violation(), min_size=0, max_size=3)),
        untested_sources=draw(st.lists(_safe_text, min_size=0, max_size=3)),
        stale_failures=draw(st.lists(st_stale_failure(), min_size=0, max_size=3)),
    )


@st.composite
def st_dependency_map(draw):
    """Generate an arbitrary DependencyMap."""
    backend_keys = draw(st.lists(_nonempty_text, min_size=0, max_size=3, unique=True))
    backend = {}
    for key in backend_keys:
        backend[key] = draw(st.lists(_nonempty_text, min_size=0, max_size=3))

    frontend_keys = draw(st.lists(_nonempty_text, min_size=0, max_size=3, unique=True))
    frontend = {}
    for key in frontend_keys:
        frontend[key] = draw(st.lists(_nonempty_text, min_size=0, max_size=3))

    untested = draw(st.lists(_safe_text, min_size=0, max_size=3))

    return DependencyMap(
        backend=backend,
        frontend=frontend,
        untested=untested,
    )


# ---------------------------------------------------------------------------
# Feature: test-maintenance-framework, Property 3: Report serialization round-trip
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestReportSerializationRoundTrip:
    """Property 3: For any ScanReport or DependencyMap, serializing to JSON
    and deserializing back produces an equivalent object with all fields
    preserved.

    **Validates: Requirements 1.5, 2.5**
    """

    @given(report=st_scan_report())
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_scan_report_round_trip(self, report):
        """
        # Feature: test-maintenance-framework, Property 3: Report serialization round-trip

        For any ScanReport, from_json(to_json(report)) produces an
        equivalent object (compared via dataclasses.asdict).

        **Validates: Requirements 1.5, 2.5**
        """
        gen = ReportGenerator(report)
        json_str = gen.to_json()
        restored = ReportGenerator.from_json(json_str)

        original_dict = asdict(report)
        restored_dict = asdict(restored)

        assert original_dict == restored_dict, (
            f"Round-trip mismatch.\n"
            f"  Original keys: {sorted(original_dict.keys())}\n"
            f"  Restored keys: {sorted(restored_dict.keys())}"
        )

    @given(dep_map=st_dependency_map())
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_dependency_map_round_trip(self, dep_map):
        """
        # Feature: test-maintenance-framework, Property 3: Report serialization round-trip

        For any DependencyMap, serializing to JSON and back preserves all
        fields.

        **Validates: Requirements 1.5, 2.5**
        """
        import json

        original_dict = asdict(dep_map)
        json_str = json.dumps(original_dict, indent=2)
        restored_dict = json.loads(json_str)

        restored = DependencyMap(
            backend=restored_dict["backend"],
            frontend=restored_dict["frontend"],
            untested=restored_dict["untested"],
        )

        assert asdict(restored) == original_dict, (
            f"DependencyMap round-trip mismatch.\n"
            f"  Original: {original_dict}\n"
            f"  Restored: {asdict(restored)}"
        )

    @given(report=st_scan_report())
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_nested_category_summary_preserved(self, report):
        """
        # Feature: test-maintenance-framework, Property 3: Report serialization round-trip

        Round-trip preserves nested structures: CategorySummary entries
        within ScanSummary.by_category survive serialization.

        **Validates: Requirements 1.5, 2.5**
        """
        gen = ReportGenerator(report)
        json_str = gen.to_json()
        restored = ReportGenerator.from_json(json_str)

        # Verify by_category keys match
        assert set(report.summary.by_category.keys()) == set(
            restored.summary.by_category.keys()
        ), (
            f"by_category keys mismatch.\n"
            f"  Original: {sorted(report.summary.by_category.keys())}\n"
            f"  Restored: {sorted(restored.summary.by_category.keys())}"
        )

        # Verify each CategorySummary matches
        for cat_name, original_cs in report.summary.by_category.items():
            restored_cs = restored.summary.by_category[cat_name]
            assert asdict(original_cs) == asdict(restored_cs), (
                f"CategorySummary mismatch for '{cat_name}'.\n"
                f"  Original: {asdict(original_cs)}\n"
                f"  Restored: {asdict(restored_cs)}"
            )


# ---------------------------------------------------------------------------
# Import for Property 13
# ---------------------------------------------------------------------------
from scripts.test_maintenance.report_generator import compute_trend


# ---------------------------------------------------------------------------
# Feature: test-maintenance-framework, Property 13: Report trend computation
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestReportTrendComputation:
    """Property 13: For any two ScanReports, trend correctly computes
    fixed = (failing before ∩ passing after),
    newly_broken = (passing before ∩ failing after).

    **Validates: Requirements 7.2, 7.4, 10.3**
    """

    @given(before=st_scan_report(), after=st_scan_report())
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_fixed_equals_before_minus_after(self, before, after):
        """
        # Feature: test-maintenance-framework, Property 13: Report trend computation

        For any two ScanReports, trend.tests_fixed equals the count of
        mock violation file_paths in before but not in after PLUS
        compliance violation (file_path, rule_id) pairs in before but not
        in after.

        **Validates: Requirements 7.2, 7.4, 10.3**
        """
        trend = compute_trend(before, after)

        before_mock_keys = {v.file_path for v in before.mock_violations}
        after_mock_keys = {v.file_path for v in after.mock_violations}
        fixed_mock = before_mock_keys - after_mock_keys

        before_comp_keys = {(v.file_path, v.rule_id) for v in before.compliance_violations}
        after_comp_keys = {(v.file_path, v.rule_id) for v in after.compliance_violations}
        fixed_comp = before_comp_keys - after_comp_keys

        expected_fixed = len(fixed_mock) + len(fixed_comp)
        assert trend.tests_fixed == expected_fixed, (
            f"tests_fixed mismatch: got {trend.tests_fixed}, expected {expected_fixed}\n"
            f"  fixed_mock={fixed_mock}, fixed_comp={fixed_comp}"
        )

    @given(before=st_scan_report(), after=st_scan_report())
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_newly_broken_equals_after_minus_before(self, before, after):
        """
        # Feature: test-maintenance-framework, Property 13: Report trend computation

        For any two ScanReports, trend.tests_newly_broken equals the count
        of mock violation file_paths in after but not in before PLUS
        compliance violation (file_path, rule_id) pairs in after but not
        in before.

        **Validates: Requirements 7.2, 7.4, 10.3**
        """
        trend = compute_trend(before, after)

        before_mock_keys = {v.file_path for v in before.mock_violations}
        after_mock_keys = {v.file_path for v in after.mock_violations}
        new_mock = after_mock_keys - before_mock_keys

        before_comp_keys = {(v.file_path, v.rule_id) for v in before.compliance_violations}
        after_comp_keys = {(v.file_path, v.rule_id) for v in after.compliance_violations}
        new_comp = after_comp_keys - before_comp_keys

        expected_newly_broken = len(new_mock) + len(new_comp)
        assert trend.tests_newly_broken == expected_newly_broken, (
            f"tests_newly_broken mismatch: got {trend.tests_newly_broken}, expected {expected_newly_broken}\n"
            f"  new_mock={new_mock}, new_comp={new_comp}"
        )

    @given(before=st_scan_report(), after=st_scan_report())
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_newly_quarantined_equals_stale_diff(self, before, after):
        """
        # Feature: test-maintenance-framework, Property 13: Report trend computation

        For any two ScanReports, trend.tests_newly_quarantined equals the
        count of stale failure test_ids in after but not in before.

        **Validates: Requirements 7.2, 7.4, 10.3**
        """
        trend = compute_trend(before, after)

        before_stale_ids = {sf.test_id for sf in before.stale_failures}
        after_stale_ids = {sf.test_id for sf in after.stale_failures}
        new_quarantined = after_stale_ids - before_stale_ids

        expected = len(new_quarantined)
        assert trend.tests_newly_quarantined == expected, (
            f"tests_newly_quarantined mismatch: got {trend.tests_newly_quarantined}, expected {expected}\n"
            f"  new_quarantined={new_quarantined}"
        )

    @given(before=st_scan_report(), after=st_scan_report())
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_trend_regressions_count_matches(self, before, after):
        """
        # Feature: test-maintenance-framework, Property 13: Report trend computation

        For any two ScanReports, len(trend.regressions) equals
        trend.tests_newly_broken.

        **Validates: Requirements 7.2, 7.4, 10.3**
        """
        trend = compute_trend(before, after)

        assert len(trend.regressions) == trend.tests_newly_broken, (
            f"regressions count mismatch: len(regressions)={len(trend.regressions)}, "
            f"tests_newly_broken={trend.tests_newly_broken}"
        )

    @given(before=st_scan_report(), after=st_scan_report())
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_trend_improvements_count_matches(self, before, after):
        """
        # Feature: test-maintenance-framework, Property 13: Report trend computation

        For any two ScanReports, len(trend.improvements) equals
        trend.tests_fixed.

        **Validates: Requirements 7.2, 7.4, 10.3**
        """
        trend = compute_trend(before, after)

        assert len(trend.improvements) == trend.tests_fixed, (
            f"improvements count mismatch: len(improvements)={len(trend.improvements)}, "
            f"tests_fixed={trend.tests_fixed}"
        )


# ---------------------------------------------------------------------------
# Feature: test-maintenance-framework, Property 14: Summary category completeness
# ---------------------------------------------------------------------------


@st.composite
def st_consistent_category_summary(draw):
    """Generate a CategorySummary where total = passing + failing + skipped + flaky + quarantined."""
    passing = draw(_nonneg_int)
    failing = draw(_nonneg_int)
    skipped = draw(_nonneg_int)
    flaky = draw(_nonneg_int)
    quarantined = draw(_nonneg_int)
    total = passing + failing + skipped + flaky + quarantined
    return CategorySummary(
        total=total,
        passing=passing,
        failing=failing,
        skipped=skipped,
        flaky=flaky,
        quarantined=quarantined,
    )


@pytest.mark.unit
class TestSummaryCategoryCompleteness:
    """Property 14: For any test results across categories, the summary has
    a CategorySummary per category where total = passing + failing + skipped
    + flaky + quarantined.

    **Validates: Requirements 7.1**
    """

    @given(cs=st_consistent_category_summary())
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_category_total_equals_sum_of_parts(self, cs):
        """
        # Feature: test-maintenance-framework, Property 14: Summary category completeness

        For any CategorySummary where total = passing + failing + skipped +
        flaky + quarantined (generated that way), verify the invariant holds.

        **Validates: Requirements 7.1**
        """
        expected_total = cs.passing + cs.failing + cs.skipped + cs.flaky + cs.quarantined
        assert cs.total == expected_total, (
            f"CategorySummary total mismatch: total={cs.total}, "
            f"sum={expected_total} "
            f"(passing={cs.passing}, failing={cs.failing}, skipped={cs.skipped}, "
            f"flaky={cs.flaky}, quarantined={cs.quarantined})"
        )

    @given(summary=st_scan_summary())
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_all_categories_present_in_summary(self, summary):
        """
        # Feature: test-maintenance-framework, Property 14: Summary category completeness

        For any ScanSummary with by_category populated, every category key
        has a valid CategorySummary with non-negative fields.

        **Validates: Requirements 7.1**
        """
        for cat_name, cs in summary.by_category.items():
            assert isinstance(cs, CategorySummary), (
                f"Category '{cat_name}' is not a CategorySummary: {type(cs)}"
            )
            assert cs.total >= 0, f"Category '{cat_name}' has negative total: {cs.total}"
            assert cs.passing >= 0, f"Category '{cat_name}' has negative passing: {cs.passing}"
            assert cs.failing >= 0, f"Category '{cat_name}' has negative failing: {cs.failing}"
            assert cs.skipped >= 0, f"Category '{cat_name}' has negative skipped: {cs.skipped}"
            assert cs.flaky >= 0, f"Category '{cat_name}' has negative flaky: {cs.flaky}"
            assert cs.quarantined >= 0, f"Category '{cat_name}' has negative quarantined: {cs.quarantined}"

    @given(cs=st_category_summary())
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_category_summary_fields_non_negative(self, cs):
        """
        # Feature: test-maintenance-framework, Property 14: Summary category completeness

        For any CategorySummary, all fields (total, passing, failing,
        skipped, flaky, quarantined) are non-negative integers.

        **Validates: Requirements 7.1**
        """
        for field_name in ("total", "passing", "failing", "skipped", "flaky", "quarantined"):
            value = getattr(cs, field_name)
            assert isinstance(value, int), (
                f"CategorySummary.{field_name} is not an int: {type(value)}"
            )
            assert value >= 0, (
                f"CategorySummary.{field_name} is negative: {value}"
            )


# ---------------------------------------------------------------------------
# Import for Property 15
# ---------------------------------------------------------------------------
from scripts.test_maintenance.report_generator import TrendReport


# ---------------------------------------------------------------------------
# Feature: test-maintenance-framework, Property 15: Markdown report structure
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestMarkdownReportStructure:
    """Property 15: For any ScanReport, the markdown contains a title,
    summary table, and conditional sections (regressions, improvements,
    mock violations, quarantine) only when the corresponding data is
    present.

    **Validates: Requirements 7.5**
    """

    @given(report=st_scan_report())
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_markdown_always_has_title_and_summary(self, report):
        """
        # Feature: test-maintenance-framework, Property 15: Markdown report structure

        For any ScanReport, the markdown always contains
        "# Test Health Scanner Report" and "## Summary".

        **Validates: Requirements 7.5**
        """
        gen = ReportGenerator(report)
        md = gen.to_markdown()

        assert "# Test Health Scanner Report" in md, (
            "Markdown missing title '# Test Health Scanner Report'"
        )
        assert "## Summary" in md, (
            "Markdown missing '## Summary' section"
        )

    @given(report=st_scan_report())
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_markdown_has_mock_violations_section_when_present(self, report):
        """
        # Feature: test-maintenance-framework, Property 15: Markdown report structure

        For any ScanReport with non-empty mock_violations, the markdown
        contains "## Mock Violations". For empty mock_violations, it does
        NOT contain "## Mock Violations".

        **Validates: Requirements 7.5**
        """
        gen = ReportGenerator(report)
        md = gen.to_markdown()

        if report.mock_violations:
            assert "## Mock Violations" in md, (
                f"Markdown missing '## Mock Violations' despite "
                f"{len(report.mock_violations)} violation(s)"
            )
        else:
            assert "## Mock Violations" not in md, (
                "Markdown contains '## Mock Violations' but "
                "mock_violations is empty"
            )

    @given(report=st_scan_report())
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_markdown_has_quarantine_section_when_present(self, report):
        """
        # Feature: test-maintenance-framework, Property 15: Markdown report structure

        For any ScanReport with non-empty stale_failures, the markdown
        contains "## Quarantine". For empty stale_failures, it does NOT
        contain "## Quarantine".

        **Validates: Requirements 7.5**
        """
        gen = ReportGenerator(report)
        md = gen.to_markdown()

        if report.stale_failures:
            assert "## Quarantine" in md, (
                f"Markdown missing '## Quarantine' despite "
                f"{len(report.stale_failures)} stale failure(s)"
            )
        else:
            assert "## Quarantine" not in md, (
                "Markdown contains '## Quarantine' but "
                "stale_failures is empty"
            )

    @given(
        before=st_scan_report(),
        extra_violation=st_mock_violation(),
    )
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_markdown_has_regressions_when_trend_has_regressions(
        self, before, extra_violation,
    ):
        """
        # Feature: test-maintenance-framework, Property 15: Markdown report structure

        Generate two ScanReports where after has a mock violation not in
        before. Compute trend, pass to to_markdown(trend=trend). Verify
        "## Regressions" appears in the markdown.

        **Validates: Requirements 7.5**
        """
        # Ensure the extra violation's file_path is not already in before
        before_paths = {v.file_path for v in before.mock_violations}
        unique_path = extra_violation.file_path
        while unique_path in before_paths:
            unique_path = unique_path + "_new"
        extra = MockViolation(
            file_path=unique_path,
            line_number=extra_violation.line_number,
            violation_type=extra_violation.violation_type,
            severity=extra_violation.severity,
            description=extra_violation.description,
            suggested_fix=extra_violation.suggested_fix,
        )

        # Build 'after' with the extra violation added
        after = ScanReport(
            timestamp=before.timestamp,
            scan_duration_seconds=before.scan_duration_seconds,
            summary=before.summary,
            mock_violations=list(before.mock_violations) + [extra],
            drift_issues=list(before.drift_issues),
            compliance_violations=list(before.compliance_violations),
            frontend_violations=list(before.frontend_violations),
            untested_sources=list(before.untested_sources),
            stale_failures=list(before.stale_failures),
        )

        trend = compute_trend(before, after)
        gen = ReportGenerator(after)
        md = gen.to_markdown(trend=trend)

        assert "## Regressions" in md, (
            f"Markdown missing '## Regressions' despite "
            f"{len(trend.regressions)} regression(s)"
        )

    @given(
        after=st_scan_report(),
        extra_violation=st_mock_violation(),
    )
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_markdown_has_improvements_when_trend_has_improvements(
        self, after, extra_violation,
    ):
        """
        # Feature: test-maintenance-framework, Property 15: Markdown report structure

        Generate two ScanReports where before has a mock violation not in
        after. Compute trend, pass to to_markdown(trend=trend). Verify
        "## Improvements" appears in the markdown.

        **Validates: Requirements 7.5**
        """
        # Ensure the extra violation's file_path is not already in after
        after_paths = {v.file_path for v in after.mock_violations}
        unique_path = extra_violation.file_path
        while unique_path in after_paths:
            unique_path = unique_path + "_old"
        extra = MockViolation(
            file_path=unique_path,
            line_number=extra_violation.line_number,
            violation_type=extra_violation.violation_type,
            severity=extra_violation.severity,
            description=extra_violation.description,
            suggested_fix=extra_violation.suggested_fix,
        )

        # Build 'before' with the extra violation that was fixed
        before = ScanReport(
            timestamp=after.timestamp,
            scan_duration_seconds=after.scan_duration_seconds,
            summary=after.summary,
            mock_violations=list(after.mock_violations) + [extra],
            drift_issues=list(after.drift_issues),
            compliance_violations=list(after.compliance_violations),
            frontend_violations=list(after.frontend_violations),
            untested_sources=list(after.untested_sources),
            stale_failures=list(after.stale_failures),
        )

        trend = compute_trend(before, after)
        gen = ReportGenerator(after)
        md = gen.to_markdown(trend=trend)

        assert "## Improvements" in md, (
            f"Markdown missing '## Improvements' despite "
            f"{len(trend.improvements)} improvement(s)"
        )
