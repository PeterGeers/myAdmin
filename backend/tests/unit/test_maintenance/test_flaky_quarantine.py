"""
Unit tests for FlakyQuarantine
================================

Tests the flaky quarantine module: flaky detection, quarantine lifecycle,
quarantine reporting, persistence, and classification registry integration.

Requirements: 5.1, 5.3, 8.2, 8.4
"""

from __future__ import annotations

import json
import os

import pytest

from scripts.test_maintenance.flaky_quarantine import (
    FlakyQuarantine,
    QuarantineEntry,
    QuarantineReport,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def registry_path(tmp_path):
    """Path to a fresh, empty classification registry JSON file."""
    path = tmp_path / "test-classification-registry.json"
    data = {
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
    }
    path.write_text(json.dumps(data), encoding="utf-8")
    return str(path)


@pytest.fixture
def quarantine_log_path(tmp_path):
    """Path to a fresh quarantine log file (does not exist yet)."""
    return str(tmp_path / "quarantine-log.json")


@pytest.fixture
def fq(registry_path, quarantine_log_path):
    """A fresh FlakyQuarantine instance with empty registry and log."""
    return FlakyQuarantine(registry_path, quarantine_log_path)


# ---------------------------------------------------------------------------
# Flaky detection tests
# ---------------------------------------------------------------------------

class TestFlakyDetection:
    """Tests for detect_flaky() — requirement 5.1."""

    def test_only_passes_not_flaky(self, fq):
        """A test with only passing results is NOT flaky."""
        fq.record_result("test_a", passed=True, run_id="run-1")
        fq.record_result("test_a", passed=True, run_id="run-2")
        assert fq.detect_flaky("test_a") is False

    def test_only_fails_not_flaky(self, fq):
        """A test with only failing results is NOT flaky."""
        fq.record_result("test_b", passed=False, run_id="run-1")
        fq.record_result("test_b", passed=False, run_id="run-2")
        assert fq.detect_flaky("test_b") is False

    def test_pass_and_fail_different_runs_not_flaky(self, fq):
        """A test with pass and fail in DIFFERENT run_ids is NOT flaky."""
        fq.record_result("test_c", passed=True, run_id="run-1")
        fq.record_result("test_c", passed=False, run_id="run-2")
        assert fq.detect_flaky("test_c") is False

    def test_pass_and_fail_same_run_is_flaky(self, fq):
        """A test with pass and fail in the SAME run_id IS flaky."""
        fq.record_result("test_d", passed=True, run_id="run-1")
        fq.record_result("test_d", passed=False, run_id="run-1")
        assert fq.detect_flaky("test_d") is True

    def test_unknown_test_id_not_flaky(self, fq):
        """detect_flaky returns False for an unknown test_id."""
        assert fq.detect_flaky("nonexistent_test") is False


# ---------------------------------------------------------------------------
# Quarantine lifecycle tests
# ---------------------------------------------------------------------------

class TestQuarantineLifecycle:
    """Tests for quarantine(), record_result(), check_restoration() — requirements 5.3, 5.4."""

    def test_quarantine_creates_entry(self, fq):
        """Quarantining a test creates an entry in the report."""
        fq.quarantine("test_e", reason="Intermittent timeout")
        report = fq.get_quarantine_report()
        assert len(report.entries) == 1
        assert report.entries[0].test_id == "test_e"

    def test_quarantine_entry_status(self, fq):
        """Quarantine entry has status 'quarantined'."""
        fq.quarantine("test_f", reason="Flaky network")
        report = fq.get_quarantine_report()
        assert report.entries[0].status == "quarantined"

    def test_quarantine_entry_has_reason_and_date(self, fq):
        """Quarantine entry has a non-empty reason and a valid date."""
        fq.quarantine("test_g", reason="Random failure")
        report = fq.get_quarantine_report()
        entry = report.entries[0]
        assert entry.reason == "Random failure"
        assert entry.quarantine_date  # non-empty
        # Validate ISO date format (YYYY-MM-DD)
        parts = entry.quarantine_date.split("-")
        assert len(parts) == 3
        assert len(parts[0]) == 4  # year

    def test_recording_passes_increments_consecutive(self, fq):
        """Recording passes on a quarantined test increments consecutive_passes."""
        fq.quarantine("test_h", reason="Flaky")
        fq.record_result("test_h", passed=True, run_id="run-1")
        fq.record_result("test_h", passed=True, run_id="run-2")
        report = fq.get_quarantine_report()
        assert report.entries[0].consecutive_passes == 2

    def test_recording_fail_resets_consecutive(self, fq):
        """Recording a fail on a quarantined test resets consecutive_passes to 0."""
        fq.quarantine("test_i", reason="Flaky")
        fq.record_result("test_i", passed=True, run_id="run-1")
        fq.record_result("test_i", passed=True, run_id="run-2")
        fq.record_result("test_i", passed=False, run_id="run-3")
        report = fq.get_quarantine_report()
        assert report.entries[0].consecutive_passes == 0

    def test_check_restoration_false_below_threshold(self, fq):
        """check_restoration returns False with < 3 consecutive passes."""
        fq.quarantine("test_j", reason="Flaky")
        fq.record_result("test_j", passed=True, run_id="run-1")
        fq.record_result("test_j", passed=True, run_id="run-2")
        assert fq.check_restoration("test_j") is False

    def test_check_restoration_true_at_threshold(self, fq):
        """check_restoration returns True with >= 3 consecutive passes."""
        fq.quarantine("test_k", reason="Flaky")
        fq.record_result("test_k", passed=True, run_id="run-1")
        fq.record_result("test_k", passed=True, run_id="run-2")
        fq.record_result("test_k", passed=True, run_id="run-3")
        assert fq.check_restoration("test_k") is True

    def test_restoration_changes_status(self, fq):
        """Restoration changes the entry status to 'restored'."""
        fq.quarantine("test_l", reason="Flaky")
        for i in range(3):
            fq.record_result("test_l", passed=True, run_id=f"run-{i}")
        fq.check_restoration("test_l")
        report = fq.get_quarantine_report()
        assert report.entries[0].status == "restored"

    def test_re_quarantine_restored_test(self, fq):
        """A previously restored test can be re-quarantined."""
        fq.quarantine("test_m", reason="First quarantine")
        for i in range(3):
            fq.record_result("test_m", passed=True, run_id=f"run-{i}")
        fq.check_restoration("test_m")
        assert fq.get_quarantine_report().entries[0].status == "restored"

        # Re-quarantine
        fq.quarantine("test_m", reason="Flaky again")
        report = fq.get_quarantine_report()
        assert report.entries[0].status == "quarantined"
        assert report.entries[0].reason == "Flaky again"
        assert report.entries[0].consecutive_passes == 0


# ---------------------------------------------------------------------------
# Quarantine report tests
# ---------------------------------------------------------------------------

class TestQuarantineReport:
    """Tests for get_quarantine_report() — requirement 5.5."""

    def test_empty_report(self, fq):
        """A new instance produces an empty report."""
        report = fq.get_quarantine_report()
        assert report.entries == []
        assert report.total_quarantined == 0
        assert report.total_restored == 0

    def test_report_counts(self, fq):
        """Report correctly counts quarantined and restored entries."""
        fq.quarantine("test_n", reason="Flaky A")
        fq.quarantine("test_o", reason="Flaky B")
        # Restore test_o
        for i in range(3):
            fq.record_result("test_o", passed=True, run_id=f"run-{i}")
        fq.check_restoration("test_o")

        report = fq.get_quarantine_report()
        assert report.total_quarantined == 1
        assert report.total_restored == 1
        assert len(report.entries) == 2

    def test_report_entries_have_required_fields(self, fq):
        """Report entries have all required fields."""
        fq.quarantine("test_p", reason="Timeout")
        report = fq.get_quarantine_report()
        entry = report.entries[0]
        assert hasattr(entry, "test_id")
        assert hasattr(entry, "reason")
        assert hasattr(entry, "quarantine_date")
        assert hasattr(entry, "last_failure_message")
        assert hasattr(entry, "consecutive_passes")
        assert hasattr(entry, "status")


# ---------------------------------------------------------------------------
# Persistence tests
# ---------------------------------------------------------------------------

class TestPersistence:
    """Tests for quarantine log persistence via atomic writes."""

    def test_quarantine_saves_to_disk(self, registry_path, quarantine_log_path):
        """Quarantining a test persists the log to disk."""
        fq = FlakyQuarantine(registry_path, quarantine_log_path)
        fq.quarantine("test_q", reason="Flaky")
        assert os.path.isfile(quarantine_log_path)

        with open(quarantine_log_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        assert len(data["entries"]) == 1
        assert data["entries"][0]["test_id"] == "test_q"

    def test_data_survives_reload(self, registry_path, quarantine_log_path):
        """Data persists across save and reload."""
        fq1 = FlakyQuarantine(registry_path, quarantine_log_path)
        fq1.quarantine("test_r", reason="Intermittent")
        fq1.record_result("test_r", passed=True, run_id="run-1")

        # Reload from disk
        fq2 = FlakyQuarantine(registry_path, quarantine_log_path)
        report = fq2.get_quarantine_report()
        assert len(report.entries) == 1
        assert report.entries[0].test_id == "test_r"
        assert report.entries[0].reason == "Intermittent"
        assert report.entries[0].consecutive_passes == 1

    def test_no_temp_files_after_save(self, registry_path, tmp_path):
        """Atomic write should not leave .tmp files behind."""
        log_path = str(tmp_path / "clean-quarantine.json")
        fq = FlakyQuarantine(registry_path, log_path)
        fq.quarantine("test_s", reason="Flaky")

        files = os.listdir(tmp_path)
        tmp_files = [f for f in files if f.endswith(".tmp")]
        assert tmp_files == []


# ---------------------------------------------------------------------------
# Registry integration tests
# ---------------------------------------------------------------------------

class TestRegistryIntegration:
    """Tests for classification registry updates on quarantine/restore."""

    def test_quarantine_updates_registry(self, registry_path, quarantine_log_path):
        """Quarantining a test updates the classification registry."""
        fq = FlakyQuarantine(registry_path, quarantine_log_path)
        fq.quarantine("test_t", reason="Flaky network call")

        # Read the registry directly to verify
        with open(registry_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        assert "test_t" in data["tests"]
        assert data["tests"]["test_t"]["status"] == "quarantined"

    def test_restoration_updates_registry(self, registry_path, quarantine_log_path):
        """Restoring a test updates the classification registry to passing."""
        fq = FlakyQuarantine(registry_path, quarantine_log_path)
        fq.quarantine("test_u", reason="Flaky")
        for i in range(3):
            fq.record_result("test_u", passed=True, run_id=f"run-{i}")
        fq.check_restoration("test_u")

        # Read the registry directly to verify
        with open(registry_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        assert "test_u" in data["tests"]
        assert data["tests"]["test_u"]["status"] == "passing"
