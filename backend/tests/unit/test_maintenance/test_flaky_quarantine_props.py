"""
Property-based tests for the Flaky Test Quarantine.

Uses Hypothesis to verify universal properties of flaky test detection
and quarantine lifecycle management.
"""
import json
import uuid
from collections import defaultdict

import pytest
from hypothesis import given, strategies as st, settings, HealthCheck

from scripts.test_maintenance.flaky_quarantine import FlakyQuarantine


# ---------------------------------------------------------------------------
# Helpers — file setup
# ---------------------------------------------------------------------------

def _create_empty_files(tmp_path):
    """Create the empty registry and quarantine log files needed by
    FlakyQuarantine, and return (registry_path, quarantine_log_path)."""
    registry_path = str(tmp_path / "test-classification-registry.json")
    quarantine_log_path = str(tmp_path / "quarantine-log.json")

    # Empty registry
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

    # Empty quarantine log
    with open(quarantine_log_path, "w", encoding="utf-8") as fh:
        json.dump({"version": "1.0", "entries": []}, fh)

    return registry_path, quarantine_log_path


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

# A single test execution result: (passed: bool, run_id: str)
_run_id = st.text(
    alphabet="abcdef0123456789",
    min_size=4,
    max_size=8,
)

_result_entry = st.tuples(st.booleans(), _run_id)

# A sequence of results for a single test
_result_sequence = st.lists(_result_entry, min_size=1, max_size=20)


# ---------------------------------------------------------------------------
# Feature: test-maintenance-framework, Property 10: Flaky test detection
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestFlakyTestDetection:
    """Property 10: For any sequence of test execution results where a
    single test has both passing and failing results within the same code
    state (same run_id), the FlakyQuarantine marks that test as flaky.
    """

    @given(results=_result_sequence)
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_flaky_detection(self, results, tmp_path):
        """
        # Feature: test-maintenance-framework, Property 10: Flaky test detection

        For any sequence of (passed, run_id) results recorded for a test,
        detect_flaky() returns True if and only if at least one run_id
        has both a pass and a fail.

        **Validates: Requirements 5.1**
        """
        work_dir = tmp_path / uuid.uuid4().hex
        work_dir.mkdir()

        registry_path, quarantine_log_path = _create_empty_files(work_dir)
        fq = FlakyQuarantine(
            registry_path=registry_path,
            quarantine_log_path=quarantine_log_path,
        )

        test_id = "backend/tests/unit/test_example.py::test_something"

        # Record all results
        for passed, run_id in results:
            fq.record_result(test_id, passed=passed, run_id=run_id)

        # Compute expected flakiness: any run_id with both pass and fail
        by_run = defaultdict(lambda: {"pass": False, "fail": False})
        for passed, run_id in results:
            if passed:
                by_run[run_id]["pass"] = True
            else:
                by_run[run_id]["fail"] = True

        expected_flaky = any(
            s["pass"] and s["fail"] for s in by_run.values()
        )

        actual_flaky = fq.detect_flaky(test_id)

        assert actual_flaky == expected_flaky, (
            f"detect_flaky() returned {actual_flaky}, expected {expected_flaky}.\n"
            f"  Results: {results}\n"
            f"  By run_id: {dict(by_run)}"
        )


# ---------------------------------------------------------------------------
# Additional strategies for Property 11
# ---------------------------------------------------------------------------

# A non-empty reason string for quarantining
_reason = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z")),
    min_size=1,
    max_size=40,
)

# A unique test name suffix (combined with a prefix to form a test_id)
_test_suffix = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz_",
    min_size=3,
    max_size=15,
)


# ---------------------------------------------------------------------------
# Feature: test-maintenance-framework, Property 11: Quarantine lifecycle integrity
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestQuarantineLifecycleIntegrity:
    """Property 11: For any sequence of quarantine and restore operations,
    the quarantine report SHALL list exactly the tests currently in
    quarantined status, each with a non-empty reason, a valid ISO 8601
    quarantine_date, and a last_failure_message.  A quarantined test SHALL
    be restored only after recording 3 or more consecutive passes.

    **Validates: Requirements 5.3, 5.4, 5.5**
    """

    @given(
        test_suffixes=st.lists(
            _test_suffix,
            min_size=1,
            max_size=5,
            unique=True,
        ),
        reasons=st.lists(_reason, min_size=5, max_size=5),
        pass_counts=st.lists(
            st.integers(min_value=0, max_value=6),
            min_size=5,
            max_size=5,
        ),
    )
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_quarantine_lifecycle(
        self, test_suffixes, reasons, pass_counts, tmp_path
    ):
        """
        # Feature: test-maintenance-framework, Property 11: Quarantine lifecycle integrity

        For any set of tests that are quarantined and then receive a
        variable number of consecutive pass results:

        1. The quarantine report lists exactly the tests with status
           "quarantined" (not restored ones) in its quarantined count.
        2. Each quarantined entry has a non-empty reason, a valid
           quarantine_date (YYYY-MM-DD format), and a last_failure_message
           (string, possibly empty).
        3. A test is NOT restored until it has >= 3 consecutive passes.
        4. After 3+ consecutive passes, check_restoration() returns True.

        **Validates: Requirements 5.3, 5.4, 5.5**
        """
        work_dir = tmp_path / uuid.uuid4().hex
        work_dir.mkdir()

        registry_path, quarantine_log_path = _create_empty_files(work_dir)
        fq = FlakyQuarantine(
            registry_path=registry_path,
            quarantine_log_path=quarantine_log_path,
        )

        # Build unique test IDs from the generated suffixes
        test_ids = [
            f"backend/tests/unit/test_{s}.py::test_{s}"
            for s in test_suffixes
        ]

        # --- Step 1: Record a failure for each test so quarantine() can
        #     capture a last_failure_message, then quarantine them. ---
        for i, test_id in enumerate(test_ids):
            reason = reasons[i % len(reasons)]
            fq.record_result(test_id, passed=False, run_id="run_init")
            fq.quarantine(test_id, reason=reason)

        # --- Step 2: Record consecutive passes for each test. ---
        for i, test_id in enumerate(test_ids):
            num_passes = pass_counts[i % len(pass_counts)]
            for p in range(num_passes):
                fq.record_result(
                    test_id, passed=True, run_id=f"run_pass_{p}"
                )

        # --- Step 3: Attempt restoration for every test. ---
        restoration_results = {}
        for test_id in test_ids:
            restoration_results[test_id] = fq.check_restoration(test_id)

        # --- Step 4: Get the quarantine report and verify properties. ---
        report = fq.get_quarantine_report()

        # Build expected sets
        expected_quarantined = set()
        expected_restored = set()
        for i, test_id in enumerate(test_ids):
            num_passes = pass_counts[i % len(pass_counts)]
            if num_passes >= 3:
                expected_restored.add(test_id)
            else:
                expected_quarantined.add(test_id)

        # 4a. Report quarantined count matches expected
        actual_quarantined_ids = {
            e.test_id for e in report.entries if e.status == "quarantined"
        }
        actual_restored_ids = {
            e.test_id for e in report.entries if e.status == "restored"
        }

        assert actual_quarantined_ids == expected_quarantined, (
            f"Quarantined set mismatch.\n"
            f"  Expected quarantined: {expected_quarantined}\n"
            f"  Actual quarantined:   {actual_quarantined_ids}\n"
            f"  Pass counts: {pass_counts[:len(test_ids)]}"
        )
        assert actual_restored_ids == expected_restored, (
            f"Restored set mismatch.\n"
            f"  Expected restored: {expected_restored}\n"
            f"  Actual restored:   {actual_restored_ids}"
        )

        assert report.total_quarantined == len(expected_quarantined)
        assert report.total_restored == len(expected_restored)

        # 4b. Each entry has valid fields
        import re
        date_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}$")

        for entry in report.entries:
            # Non-empty reason
            assert entry.reason, (
                f"Entry for {entry.test_id} has empty reason"
            )
            # Valid YYYY-MM-DD quarantine_date
            assert date_pattern.match(entry.quarantine_date), (
                f"Entry for {entry.test_id} has invalid quarantine_date: "
                f"{entry.quarantine_date!r}"
            )
            # last_failure_message is a string (may be empty)
            assert isinstance(entry.last_failure_message, str), (
                f"Entry for {entry.test_id} has non-string "
                f"last_failure_message: {type(entry.last_failure_message)}"
            )

        # 4c. A test is NOT restored until >= 3 consecutive passes
        for i, test_id in enumerate(test_ids):
            num_passes = pass_counts[i % len(pass_counts)]
            restored = restoration_results[test_id]
            if num_passes < 3:
                assert not restored, (
                    f"{test_id} was restored with only {num_passes} "
                    f"consecutive passes (need >= 3)"
                )
            else:
                # 4d. After 3+ consecutive passes, check_restoration()
                #     returns True
                assert restored, (
                    f"{test_id} was NOT restored despite {num_passes} "
                    f"consecutive passes (>= 3)"
                )
