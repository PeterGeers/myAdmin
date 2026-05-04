"""
Property-based tests for the Classification Registry.

Uses Hypothesis to verify universal properties of the classification
registry's stale failure detection, triage enforcement, and untriaged
warning threshold.
"""
import json
import uuid

import pytest
from hypothesis import given, strategies as st, settings, HealthCheck

from scripts.test_maintenance.classification_registry import (
    ClassificationRegistry,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_empty_registry(tmp_path):
    """Create an empty classification registry JSON file and return its path."""
    registry_path = str(tmp_path / "test-classification-registry.json")
    with open(registry_path, "w", encoding="utf-8") as fh:
        json.dump(
            {
                "version": "1.0",
                "last_updated": "",
                "tests": {},
                "metadata": {
                    "total_tests": 0,
                    "triaged": 0,
                    "untriaged": 0,
                    "by_status": {
                        "passing": 0,
                        "failing": 0,
                        "skipped": 0,
                        "flaky": 0,
                        "quarantined": 0,
                    },
                },
            },
            fh,
        )
    return registry_path


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

# Dates within a reasonable range
_date_strategy = st.dates(
    min_value=__import__("datetime").date(2024, 1, 1),
    max_value=__import__("datetime").date(2026, 1, 1),
)

# A valid triage decision (required for failing entries)
_triage_decision = st.sampled_from(["fix", "quarantine", "delete"])


# ---------------------------------------------------------------------------
# Feature: test-maintenance-framework, Property 16: Stale failure escalation
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestStaleFailureEscalation:
    """Property 16: For any test entry in the classification registry with
    a failure date more than 14 days before the current scan date, the
    registry SHALL include that test in the stale_failures list.

    **Validates: Requirements 8.2**
    """

    @given(
        triage_date=_date_strategy,
        scan_date=_date_strategy,
        triage_decision=_triage_decision,
    )
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_stale_failure_escalation(
        self, triage_date, scan_date, triage_decision, tmp_path
    ):
        """
        # Feature: test-maintenance-framework, Property 16: Stale failure escalation

        For any failing test entry with a triage_date and a scan_date
        where scan_date >= triage_date, the entry appears in
        get_stale_failures() if and only if (scan_date - triage_date) > 14
        days.  Each stale failure has the correct days_failing value.

        **Validates: Requirements 8.2**
        """
        from hypothesis import assume
        # scan_date must be >= triage_date for meaningful staleness check
        assume(scan_date >= triage_date)

        work_dir = tmp_path / uuid.uuid4().hex
        work_dir.mkdir()

        registry_path = _create_empty_registry(work_dir)
        registry = ClassificationRegistry(registry_path)

        test_id = "backend/tests/unit/test_example.py::test_something"

        # Add a failing test entry with the generated triage_date
        entry = {
            "category": "unit",
            "status": "failing",
            "failure_reason": "Some failure",
            "triage_decision": triage_decision,
            "triage_date": triage_date.isoformat(),
            "target_fix_date": "",
            "root_cause": "",
            "notes": "",
        }
        registry.add_test(test_id, entry)

        # Query stale failures
        stale_failures = registry.get_stale_failures(
            days_threshold=14, scan_date=scan_date,
        )

        days_diff = (scan_date - triage_date).days
        stale_ids = {sf["test_id"] for sf in stale_failures}

        if days_diff > 14:
            # Test MUST appear in stale_failures
            assert test_id in stale_ids, (
                f"Test should be stale (days_diff={days_diff} > 14) "
                f"but was not in stale_failures.\n"
                f"  triage_date={triage_date}, scan_date={scan_date}"
            )
            # Verify days_failing is correct
            match = [sf for sf in stale_failures if sf["test_id"] == test_id]
            assert len(match) == 1
            assert match[0]["days_failing"] == days_diff, (
                f"days_failing mismatch: expected {days_diff}, "
                f"got {match[0]['days_failing']}"
            )
        else:
            # Test must NOT appear in stale_failures
            assert test_id not in stale_ids, (
                f"Test should NOT be stale (days_diff={days_diff} <= 14) "
                f"but was found in stale_failures.\n"
                f"  triage_date={triage_date}, scan_date={scan_date}"
            )


# ---------------------------------------------------------------------------
# Feature: test-maintenance-framework, Property 17: Triage enforcement
# ---------------------------------------------------------------------------

# Strategy: invalid triage decisions (None, empty string, or arbitrary strings
# that are NOT in {"fix", "quarantine", "delete"})
_invalid_triage_decision = st.one_of(
    st.none(),
    st.just(""),
    st.text(min_size=1, max_size=30).filter(
        lambda s: s not in {"fix", "quarantine", "delete"}
    ),
)


@pytest.mark.unit
class TestTriageEnforcement:
    """Property 17: For any attempt to add a failing test to the Test
    Classification Registry without a triage_decision field (one of
    "fix", "quarantine", or "delete"), the registry SHALL reject the
    addition and return a validation error.

    **Validates: Requirements 8.4**
    """

    @given(triage_decision=_invalid_triage_decision)
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_failing_test_without_valid_triage_is_rejected(
        self, triage_decision, tmp_path
    ):
        """
        # Feature: test-maintenance-framework, Property 17: Triage enforcement

        For any failing test entry whose triage_decision is None, empty, or
        not in {"fix", "quarantine", "delete"}, add_test() raises ValueError.

        **Validates: Requirements 8.4**
        """
        work_dir = tmp_path / uuid.uuid4().hex
        work_dir.mkdir()

        registry_path = _create_empty_registry(work_dir)
        registry = ClassificationRegistry(registry_path)

        test_id = f"backend/tests/unit/test_example.py::test_{uuid.uuid4().hex}"

        entry = {
            "category": "unit",
            "status": "failing",
            "failure_reason": "Some failure",
            "triage_decision": triage_decision,
            "triage_date": "",
            "target_fix_date": "",
            "root_cause": "",
            "notes": "",
        }

        with pytest.raises(ValueError):
            registry.add_test(test_id, entry)

        # Verify the test was NOT added to the registry
        assert registry.get_test(test_id) is None, (
            f"Registry should have rejected the entry with "
            f"triage_decision={triage_decision!r}, but it was added."
        )

    @given(triage_decision=_triage_decision)
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_failing_test_with_valid_triage_is_accepted(
        self, triage_decision, tmp_path
    ):
        """
        # Feature: test-maintenance-framework, Property 17: Triage enforcement

        For any failing test entry whose triage_decision IS one of
        {"fix", "quarantine", "delete"}, add_test() succeeds without error.

        **Validates: Requirements 8.4**
        """
        work_dir = tmp_path / uuid.uuid4().hex
        work_dir.mkdir()

        registry_path = _create_empty_registry(work_dir)
        registry = ClassificationRegistry(registry_path)

        test_id = f"backend/tests/unit/test_example.py::test_{uuid.uuid4().hex}"

        entry = {
            "category": "unit",
            "status": "failing",
            "failure_reason": "Some failure",
            "triage_decision": triage_decision,
            "triage_date": "2025-01-15",
            "target_fix_date": "",
            "root_cause": "",
            "notes": "",
        }

        # Should NOT raise
        registry.add_test(test_id, entry)

        # Verify the test WAS added
        stored = registry.get_test(test_id)
        assert stored is not None, (
            f"Registry should have accepted the entry with "
            f"triage_decision={triage_decision!r}, but it was not found."
        )
        assert stored["triage_decision"] == triage_decision


# ---------------------------------------------------------------------------
# Feature: test-maintenance-framework, Property 18: Untriaged warning threshold
# ---------------------------------------------------------------------------

UNTRIAGED_WARNING_THRESHOLD = 10


@pytest.mark.unit
class TestUntriagedWarningThreshold:
    """Property 18: For any ScanReport where the count of failing tests
    without a triage_decision exceeds 10, the report summary SHALL include
    a warning message indicating the number of untriaged failures.

    **Validates: Requirements 8.5**
    """

    @given(
        num_untriaged=st.integers(min_value=0, max_value=20),
        num_triaged=st.integers(min_value=0, max_value=10),
    )
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_untriaged_count_and_threshold(
        self, num_untriaged, num_triaged, tmp_path
    ):
        """
        # Feature: test-maintenance-framework, Property 18: Untriaged warning threshold

        For any combination of untriaged and triaged failing tests,
        get_untriaged_count() returns exactly the number of failing tests
        without a valid triage_decision.  When that count exceeds 10, a
        warning SHOULD be generated (the scanner integration is tested
        separately in test_scanner.py; here we verify the count and
        threshold condition).

        **Validates: Requirements 8.5**
        """
        work_dir = tmp_path / uuid.uuid4().hex
        work_dir.mkdir()

        registry_path = _create_empty_registry(work_dir)
        registry = ClassificationRegistry(registry_path)

        # Insert untriaged failing entries (bypass validation by writing
        # directly to _data["tests"], then refresh metadata)
        for i in range(num_untriaged):
            test_id = f"backend/tests/unit/test_u{i}.py::test_untriaged_{i}"
            registry._data["tests"][test_id] = {
                "category": "unit",
                "status": "failing",
                "failure_reason": f"Untriaged failure {i}",
                # No triage_decision — this is the untriaged case
            }

        # Insert triaged failing entries (these have a valid triage_decision)
        for i in range(num_triaged):
            test_id = f"backend/tests/unit/test_t{i}.py::test_triaged_{i}"
            registry._data["tests"][test_id] = {
                "category": "unit",
                "status": "failing",
                "failure_reason": f"Triaged failure {i}",
                "triage_decision": "fix",
                "triage_date": "2025-01-15",
            }

        registry._refresh_metadata()

        # --- Verify get_untriaged_count() ---
        actual_untriaged = registry.get_untriaged_count()
        assert actual_untriaged == num_untriaged, (
            f"Expected get_untriaged_count()={num_untriaged}, "
            f"got {actual_untriaged} "
            f"(num_triaged={num_triaged})"
        )

        # --- Verify threshold condition ---
        # The scanner adds a warning when untriaged > 10.  We verify the
        # condition here at the registry level: the count correctly
        # reflects whether the threshold is exceeded.
        exceeds_threshold = actual_untriaged > UNTRIAGED_WARNING_THRESHOLD

        if num_untriaged > UNTRIAGED_WARNING_THRESHOLD:
            assert exceeds_threshold, (
                f"Threshold should be exceeded: "
                f"untriaged={actual_untriaged} > {UNTRIAGED_WARNING_THRESHOLD}"
            )
        else:
            assert not exceeds_threshold, (
                f"Threshold should NOT be exceeded: "
                f"untriaged={actual_untriaged} <= {UNTRIAGED_WARNING_THRESHOLD}"
            )

        # --- Verify metadata consistency ---
        assert registry.metadata["untriaged"] == num_untriaged, (
            f"metadata['untriaged'] mismatch: "
            f"expected {num_untriaged}, got {registry.metadata['untriaged']}"
        )
        assert registry.metadata["triaged"] == num_triaged, (
            f"metadata['triaged'] mismatch: "
            f"expected {num_triaged}, got {registry.metadata['triaged']}"
        )
