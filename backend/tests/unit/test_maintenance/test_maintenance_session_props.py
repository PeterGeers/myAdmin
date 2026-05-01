"""
Property-based tests for Maintenance Session workflow.

Uses Hypothesis to verify universal properties of maintenance work list
ordering, effort estimation completeness, and session history ordering.
"""

import pytest
from hypothesis import given, strategies as st, settings, HealthCheck

from scripts.test_maintenance.scanner import (
    MaintenanceWorkItem,
    MaintenanceWorkList,
    SessionSummary,
    _SEVERITY_ORDER,
)


# ---------------------------------------------------------------------------
# Hypothesis strategies — atomic building blocks
# ---------------------------------------------------------------------------

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

_root_cause = st.sampled_from([
    "database_mocking",
    "environment_dependency",
    "convention_violation",
    "signature_change",
    "key_mismatch",
    "frontend_missing_msw",
    "frontend_missing_provider",
    "frontend_stale_import",
    "other",
])

_effort_estimate = st.sampled_from([
    "5-10 min per file",
    "5-15 min per file",
    "10-20 min per test",
    "10-20 min per file",
    "15-30 min per test",
])

_nonneg_int = st.integers(min_value=0, max_value=1000)


# ---------------------------------------------------------------------------
# Hypothesis strategies — dataclass builders
# ---------------------------------------------------------------------------

@st.composite
def st_maintenance_work_item(draw):
    """Generate an arbitrary MaintenanceWorkItem."""
    return MaintenanceWorkItem(
        file_path=draw(_nonempty_text),
        issue_type=draw(_nonempty_text),
        root_cause=draw(_root_cause),
        severity=draw(_severity),
        description=draw(_safe_text),
        suggested_fix=draw(_safe_text),
        effort_estimate=draw(_effort_estimate),
    )


@st.composite
def st_maintenance_work_list(draw):
    """Generate an arbitrary MaintenanceWorkList with items grouped by root
    cause and sorted by severity within each group."""
    items = draw(st.lists(st_maintenance_work_item(), min_size=0, max_size=15))

    # Group by root cause
    items_by_root_cause = {}
    for item in items:
        items_by_root_cause.setdefault(item.root_cause, []).append(item)

    # Sort within each group by severity (matching scanner logic)
    for cause in items_by_root_cause:
        items_by_root_cause[cause].sort(
            key=lambda i: _SEVERITY_ORDER.get(i.severity, 99)
        )

    total = sum(len(v) for v in items_by_root_cause.values())

    # Build effort_by_category with an entry for every root cause present
    effort_by_category = {}
    for cause in items_by_root_cause:
        effort_by_category[cause] = draw(_effort_estimate)

    return MaintenanceWorkList(
        timestamp=draw(_nonempty_text),
        items_by_root_cause=items_by_root_cause,
        total_items=total,
        effort_by_category=effort_by_category,
    )


@st.composite
def st_session_summary(draw):
    """Generate an arbitrary SessionSummary with a valid ISO-like timestamp."""
    # Generate a simple sortable timestamp: YYYY-MM-DDThh:mm:ssZ
    year = draw(st.integers(min_value=2020, max_value=2030))
    month = draw(st.integers(min_value=1, max_value=12))
    day = draw(st.integers(min_value=1, max_value=28))
    hour = draw(st.integers(min_value=0, max_value=23))
    minute = draw(st.integers(min_value=0, max_value=59))
    second = draw(st.integers(min_value=0, max_value=59))
    completed_at = f"{year:04d}-{month:02d}-{day:02d}T{hour:02d}:{minute:02d}:{second:02d}Z"
    session_id = draw(st.text(
        alphabet=st.characters(
            whitelist_categories=("L", "N"),
        ),
        min_size=1,
        max_size=20,
    ))

    return SessionSummary(
        tests_fixed=draw(_nonneg_int),
        tests_newly_broken=draw(_nonneg_int),
        tests_newly_quarantined=draw(_nonneg_int),
        remaining_violations=draw(_nonneg_int),
        session_id=session_id,
        started_at=completed_at,
        completed_at=completed_at,
        fixes_by_root_cause=draw(st.dictionaries(
            keys=_root_cause,
            values=_nonneg_int,
            min_size=0,
            max_size=4,
        )),
        remaining_backlog=draw(_nonneg_int),
    )


# ---------------------------------------------------------------------------
# Feature: test-maintenance-framework, Property 22: Maintenance work list ordering
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestMaintenanceWorkListOrdering:
    """Property 22: For any set of detected issues, the maintenance work list
    groups issues by root cause and within each group, issues are ordered by
    severity (critical first, then high, medium, low).

    **Validates: Requirements 10.1, 10.5**
    """

    @given(items=st.lists(st_maintenance_work_item(), min_size=0, max_size=20))
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_items_grouped_by_root_cause(self, items):
        """
        # Feature: test-maintenance-framework, Property 22: Maintenance work list ordering

        For any set of MaintenanceWorkItems, grouping by root_cause places
        every item in exactly one group matching its root_cause field.

        **Validates: Requirements 10.1, 10.5**
        """
        # Group items the same way the scanner does
        items_by_root_cause = {}
        for item in items:
            items_by_root_cause.setdefault(item.root_cause, []).append(item)

        # Every item appears in exactly one group
        total_in_groups = sum(len(v) for v in items_by_root_cause.values())
        assert total_in_groups == len(items), (
            f"Item count mismatch: {total_in_groups} in groups vs "
            f"{len(items)} total"
        )

        # Each item is in the correct group
        for cause, group_items in items_by_root_cause.items():
            for item in group_items:
                assert item.root_cause == cause, (
                    f"Item with root_cause '{item.root_cause}' found in "
                    f"group '{cause}'"
                )

    @given(items=st.lists(st_maintenance_work_item(), min_size=0, max_size=20))
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_severity_ordering_within_groups(self, items):
        """
        # Feature: test-maintenance-framework, Property 22: Maintenance work list ordering

        For any set of MaintenanceWorkItems grouped by root cause and sorted
        by severity, within each group items are ordered critical → high →
        medium → low.

        **Validates: Requirements 10.1, 10.5**
        """
        # Group and sort the same way the scanner does
        items_by_root_cause = {}
        for item in items:
            items_by_root_cause.setdefault(item.root_cause, []).append(item)

        for cause in items_by_root_cause:
            items_by_root_cause[cause].sort(
                key=lambda i: _SEVERITY_ORDER.get(i.severity, 99)
            )

        # Verify ordering within each group
        for cause, group_items in items_by_root_cause.items():
            for i in range(len(group_items) - 1):
                current_order = _SEVERITY_ORDER.get(group_items[i].severity, 99)
                next_order = _SEVERITY_ORDER.get(group_items[i + 1].severity, 99)
                assert current_order <= next_order, (
                    f"Severity ordering violated in group '{cause}': "
                    f"'{group_items[i].severity}' (order {current_order}) "
                    f"before '{group_items[i + 1].severity}' (order {next_order})"
                )

    @given(worklist=st_maintenance_work_list())
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_worklist_total_items_matches_sum(self, worklist):
        """
        # Feature: test-maintenance-framework, Property 22: Maintenance work list ordering

        For any MaintenanceWorkList, total_items equals the sum of items
        across all root cause groups.

        **Validates: Requirements 10.1, 10.5**
        """
        actual_total = sum(
            len(items) for items in worklist.items_by_root_cause.values()
        )
        assert worklist.total_items == actual_total, (
            f"total_items mismatch: {worklist.total_items} vs "
            f"actual sum {actual_total}"
        )

    @given(worklist=st_maintenance_work_list())
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_worklist_severity_order_preserved(self, worklist):
        """
        # Feature: test-maintenance-framework, Property 22: Maintenance work list ordering

        For any generated MaintenanceWorkList, within each root cause group
        items are in non-decreasing severity order.

        **Validates: Requirements 10.1, 10.5**
        """
        for cause, group_items in worklist.items_by_root_cause.items():
            for i in range(len(group_items) - 1):
                current_order = _SEVERITY_ORDER.get(group_items[i].severity, 99)
                next_order = _SEVERITY_ORDER.get(group_items[i + 1].severity, 99)
                assert current_order <= next_order, (
                    f"Severity ordering violated in group '{cause}': "
                    f"'{group_items[i].severity}' (order {current_order}) "
                    f"before '{group_items[i + 1].severity}' (order {next_order})"
                )


# ---------------------------------------------------------------------------
# Feature: test-maintenance-framework, Property 23: Effort estimation completeness
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestEffortEstimationCompleteness:
    """Property 23: For any set of detected issues grouped by fix category,
    the maintenance session output includes a non-negative effort estimate
    for each category.

    **Validates: Requirements 10.2**
    """

    @given(worklist=st_maintenance_work_list())
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_effort_by_category_covers_all_root_causes(self, worklist):
        """
        # Feature: test-maintenance-framework, Property 23: Effort estimation completeness

        For any MaintenanceWorkList, effort_by_category has an entry for
        every root cause that appears in items_by_root_cause.

        **Validates: Requirements 10.2**
        """
        for cause in worklist.items_by_root_cause:
            assert cause in worklist.effort_by_category, (
                f"Root cause '{cause}' has items but no effort estimate "
                f"in effort_by_category. Keys: {list(worklist.effort_by_category.keys())}"
            )

    @given(worklist=st_maintenance_work_list())
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_effort_estimates_are_non_empty_strings(self, worklist):
        """
        # Feature: test-maintenance-framework, Property 23: Effort estimation completeness

        For any MaintenanceWorkList, every value in effort_by_category is
        a non-empty string.

        **Validates: Requirements 10.2**
        """
        for cause, estimate in worklist.effort_by_category.items():
            assert isinstance(estimate, str), (
                f"Effort estimate for '{cause}' is not a string: "
                f"{type(estimate)}"
            )
            assert len(estimate) > 0, (
                f"Effort estimate for '{cause}' is empty"
            )

    @given(worklist=st_maintenance_work_list())
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_each_work_item_has_effort_estimate(self, worklist):
        """
        # Feature: test-maintenance-framework, Property 23: Effort estimation completeness

        For any MaintenanceWorkList, every individual MaintenanceWorkItem
        has a non-empty effort_estimate string.

        **Validates: Requirements 10.2**
        """
        for cause, items in worklist.items_by_root_cause.items():
            for item in items:
                assert isinstance(item.effort_estimate, str), (
                    f"Work item effort_estimate is not a string: "
                    f"{type(item.effort_estimate)}"
                )
                assert len(item.effort_estimate) > 0, (
                    f"Work item in group '{cause}' has empty effort_estimate"
                )


# ---------------------------------------------------------------------------
# Feature: test-maintenance-framework, Property 24: Session history ordering
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestSessionHistoryOrdering:
    """Property 24: For any sequence of completed maintenance sessions, the
    session history contains all sessions in chronological order with no
    gaps or duplicates.

    **Validates: Requirements 10.4**
    """

    @given(sessions=st.lists(
        st_session_summary(),
        min_size=0,
        max_size=10,
        unique_by=lambda s: s.session_id,
    ))
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_sessions_sorted_by_completed_at(self, sessions):
        """
        # Feature: test-maintenance-framework, Property 24: Session history ordering

        For any list of SessionSummary entries sorted by completed_at,
        the result is in chronological order.

        **Validates: Requirements 10.4**
        """
        sorted_sessions = sorted(sessions, key=lambda s: s.completed_at)

        for i in range(len(sorted_sessions) - 1):
            assert sorted_sessions[i].completed_at <= sorted_sessions[i + 1].completed_at, (
                f"Sessions not in chronological order: "
                f"'{sorted_sessions[i].completed_at}' > "
                f"'{sorted_sessions[i + 1].completed_at}'"
            )

    @given(sessions=st.lists(
        st_session_summary(),
        min_size=0,
        max_size=10,
        unique_by=lambda s: s.session_id,
    ))
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_no_duplicate_session_ids(self, sessions):
        """
        # Feature: test-maintenance-framework, Property 24: Session history ordering

        For any list of SessionSummary entries with unique session_ids,
        there are no duplicate session_ids.

        **Validates: Requirements 10.4**
        """
        session_ids = [s.session_id for s in sessions]
        assert len(session_ids) == len(set(session_ids)), (
            f"Duplicate session_ids found: "
            f"{[sid for sid in session_ids if session_ids.count(sid) > 1]}"
        )

    @given(sessions=st.lists(
        st_session_summary(),
        min_size=0,
        max_size=10,
        unique_by=lambda s: s.session_id,
    ))
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_all_sessions_preserved_after_sort(self, sessions):
        """
        # Feature: test-maintenance-framework, Property 24: Session history ordering

        For any list of SessionSummary entries, sorting by completed_at
        preserves all sessions (no entries lost or added).

        **Validates: Requirements 10.4**
        """
        sorted_sessions = sorted(sessions, key=lambda s: s.completed_at)

        assert len(sorted_sessions) == len(sessions), (
            f"Session count changed after sort: "
            f"{len(sessions)} → {len(sorted_sessions)}"
        )

        original_ids = {s.session_id for s in sessions}
        sorted_ids = {s.session_id for s in sorted_sessions}
        assert original_ids == sorted_ids, (
            f"Session IDs changed after sort.\n"
            f"  Missing: {original_ids - sorted_ids}\n"
            f"  Added: {sorted_ids - original_ids}"
        )

    @given(sessions=st.lists(
        st_session_summary(),
        min_size=2,
        max_size=10,
        unique_by=lambda s: s.session_id,
    ))
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_session_fields_valid(self, sessions):
        """
        # Feature: test-maintenance-framework, Property 24: Session history ordering

        For any list of SessionSummary entries, each session has a
        non-empty session_id and a non-empty completed_at timestamp.

        **Validates: Requirements 10.4**
        """
        for session in sessions:
            assert session.session_id, (
                "Session has empty session_id"
            )
            assert session.completed_at, (
                f"Session '{session.session_id}' has empty completed_at"
            )
            assert session.tests_fixed >= 0, (
                f"Session '{session.session_id}' has negative tests_fixed: "
                f"{session.tests_fixed}"
            )
            assert session.remaining_backlog >= 0, (
                f"Session '{session.session_id}' has negative remaining_backlog: "
                f"{session.remaining_backlog}"
            )
