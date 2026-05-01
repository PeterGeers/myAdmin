"""
Unit tests for ClassificationRegistry
=======================================

Tests the classification registry module: loading, validation, CRUD,
stale failure detection, untriaged counting, and atomic persistence.
"""

from __future__ import annotations

import json
import os
from datetime import date

import pytest

from scripts.test_maintenance.classification_registry import (
    ClassificationRegistry,
    VALID_STATUSES,
    VALID_TRIAGE_DECISIONS,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def empty_registry_path(tmp_path):
    """Path to a fresh, empty registry JSON file."""
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
def populated_registry_path(tmp_path):
    """Path to a registry with a few pre-existing entries."""
    path = tmp_path / "test-classification-registry.json"
    data = {
        "version": "1.0",
        "last_updated": "2025-01-10T00:00:00Z",
        "tests": {
            "test_a.py::test_pass": {
                "category": "unit",
                "status": "passing",
                "failure_reason": "",
                "triage_decision": "",
                "triage_date": "",
                "target_fix_date": "",
                "root_cause": "",
                "notes": "",
            },
            "test_b.py::test_fail": {
                "category": "unit",
                "status": "failing",
                "failure_reason": "Real DB connection",
                "triage_decision": "fix",
                "triage_date": "2025-01-01",
                "target_fix_date": "2025-01-30",
                "root_cause": "database_mocking",
                "notes": "Needs mock_db",
            },
            "test_c.py::test_flaky": {
                "category": "integration",
                "status": "flaky",
                "failure_reason": "Intermittent timeout",
                "triage_decision": "quarantine",
                "triage_date": "2025-01-05",
                "target_fix_date": "",
                "root_cause": "environment_dependency",
                "notes": "",
            },
        },
        "metadata": {
            "total_tests": 3,
            "triaged": 2,
            "untriaged": 0,
            "by_status": {
                "passing": 1,
                "failing": 1,
                "skipped": 0,
                "flaky": 1,
                "quarantined": 0,
            },
        },
    }
    path.write_text(json.dumps(data), encoding="utf-8")
    return str(path)


# ---------------------------------------------------------------------------
# Loading tests
# ---------------------------------------------------------------------------

class TestRegistryLoading:
    """Tests for loading the registry from disk."""

    def test_load_existing_file(self, empty_registry_path):
        reg = ClassificationRegistry(empty_registry_path)
        assert reg.version == "1.0"
        assert reg.tests == {}

    def test_load_nonexistent_file_creates_empty(self, tmp_path):
        path = str(tmp_path / "does_not_exist.json")
        reg = ClassificationRegistry(path)
        assert reg.version == "1.0"
        assert reg.tests == {}
        assert reg.metadata["total_tests"] == 0

    def test_load_corrupted_file_creates_empty(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text("not valid json {{{", encoding="utf-8")
        reg = ClassificationRegistry(str(path))
        assert reg.tests == {}

    def test_load_populated_file(self, populated_registry_path):
        reg = ClassificationRegistry(populated_registry_path)
        assert len(reg.tests) == 3
        assert reg.get_test("test_a.py::test_pass")["status"] == "passing"


# ---------------------------------------------------------------------------
# Validation tests
# ---------------------------------------------------------------------------

class TestValidation:
    """Tests for validate_entry() — triage enforcement."""

    def test_passing_test_no_triage_required(self, empty_registry_path):
        reg = ClassificationRegistry(empty_registry_path)
        # Should not raise
        reg.validate_entry({"status": "passing"})

    def test_skipped_test_no_triage_required(self, empty_registry_path):
        reg = ClassificationRegistry(empty_registry_path)
        reg.validate_entry({"status": "skipped"})

    def test_failing_test_without_triage_raises(self, empty_registry_path):
        reg = ClassificationRegistry(empty_registry_path)
        with pytest.raises(ValueError, match="triage_decision"):
            reg.validate_entry({"status": "failing"})

    def test_failing_test_with_empty_triage_raises(self, empty_registry_path):
        reg = ClassificationRegistry(empty_registry_path)
        with pytest.raises(ValueError, match="triage_decision"):
            reg.validate_entry({"status": "failing", "triage_decision": ""})

    def test_failing_test_with_invalid_triage_raises(self, empty_registry_path):
        reg = ClassificationRegistry(empty_registry_path)
        with pytest.raises(ValueError, match="triage_decision"):
            reg.validate_entry({
                "status": "failing",
                "triage_decision": "ignore",
            })

    def test_failing_test_with_valid_triage_ok(self, empty_registry_path):
        reg = ClassificationRegistry(empty_registry_path)
        for decision in VALID_TRIAGE_DECISIONS:
            reg.validate_entry({
                "status": "failing",
                "triage_decision": decision,
            })

    def test_flaky_test_no_triage_required(self, empty_registry_path):
        reg = ClassificationRegistry(empty_registry_path)
        reg.validate_entry({"status": "flaky"})


# ---------------------------------------------------------------------------
# CRUD tests
# ---------------------------------------------------------------------------

class TestCRUD:
    """Tests for add_test() and get_test()."""

    def test_add_passing_test(self, empty_registry_path):
        reg = ClassificationRegistry(empty_registry_path)
        entry = {
            "category": "unit",
            "status": "passing",
            "failure_reason": "",
            "triage_decision": "",
            "triage_date": "",
            "target_fix_date": "",
            "root_cause": "",
            "notes": "",
        }
        reg.add_test("test_x.py::test_ok", entry)
        assert reg.get_test("test_x.py::test_ok") == entry
        assert reg.metadata["total_tests"] == 1
        assert reg.metadata["by_status"]["passing"] == 1

    def test_add_failing_test_with_triage(self, empty_registry_path):
        reg = ClassificationRegistry(empty_registry_path)
        entry = {
            "category": "unit",
            "status": "failing",
            "failure_reason": "DB connection",
            "triage_decision": "fix",
            "triage_date": "2025-01-15",
            "target_fix_date": "2025-01-30",
            "root_cause": "database_mocking",
            "notes": "Needs mock_db",
        }
        reg.add_test("test_y.py::test_fail", entry)
        assert reg.get_test("test_y.py::test_fail") == entry
        assert reg.metadata["by_status"]["failing"] == 1
        assert reg.metadata["triaged"] == 1

    def test_add_failing_test_without_triage_raises(self, empty_registry_path):
        reg = ClassificationRegistry(empty_registry_path)
        entry = {
            "category": "unit",
            "status": "failing",
            "failure_reason": "broken",
        }
        with pytest.raises(ValueError):
            reg.add_test("test_z.py::test_bad", entry)
        # Entry should NOT have been added
        assert reg.get_test("test_z.py::test_bad") is None

    def test_update_existing_test(self, populated_registry_path):
        reg = ClassificationRegistry(populated_registry_path)
        updated = {
            "category": "unit",
            "status": "passing",
            "failure_reason": "",
            "triage_decision": "",
            "triage_date": "",
            "target_fix_date": "",
            "root_cause": "",
            "notes": "Fixed!",
        }
        reg.add_test("test_b.py::test_fail", updated)
        assert reg.get_test("test_b.py::test_fail")["status"] == "passing"
        assert reg.metadata["by_status"]["failing"] == 0
        assert reg.metadata["by_status"]["passing"] == 2

    def test_get_nonexistent_test_returns_none(self, empty_registry_path):
        reg = ClassificationRegistry(empty_registry_path)
        assert reg.get_test("nonexistent") is None


# ---------------------------------------------------------------------------
# Stale failure detection
# ---------------------------------------------------------------------------

class TestStaleFailures:
    """Tests for get_stale_failures()."""

    def test_no_stale_failures_in_empty_registry(self, empty_registry_path):
        reg = ClassificationRegistry(empty_registry_path)
        assert reg.get_stale_failures() == []

    def test_detects_stale_failure(self, populated_registry_path):
        reg = ClassificationRegistry(populated_registry_path)
        # test_b has triage_date 2025-01-01, scan on 2025-01-20 = 19 days
        stale = reg.get_stale_failures(
            days_threshold=14, scan_date=date(2025, 1, 20)
        )
        assert len(stale) == 1
        assert stale[0]["test_id"] == "test_b.py::test_fail"
        assert stale[0]["days_failing"] == 19

    def test_not_stale_within_threshold(self, populated_registry_path):
        reg = ClassificationRegistry(populated_registry_path)
        # scan on 2025-01-10 = 9 days, under 14-day threshold
        stale = reg.get_stale_failures(
            days_threshold=14, scan_date=date(2025, 1, 10)
        )
        assert len(stale) == 0

    def test_custom_threshold(self, populated_registry_path):
        reg = ClassificationRegistry(populated_registry_path)
        # 7-day threshold, scan on 2025-01-10 = 9 days > 7
        stale = reg.get_stale_failures(
            days_threshold=7, scan_date=date(2025, 1, 10)
        )
        assert len(stale) == 1

    def test_passing_tests_not_flagged_as_stale(self, empty_registry_path):
        reg = ClassificationRegistry(empty_registry_path)
        reg.add_test("test_ok.py::test_pass", {
            "category": "unit",
            "status": "passing",
            "triage_date": "2024-01-01",
        })
        stale = reg.get_stale_failures(scan_date=date(2025, 6, 1))
        assert len(stale) == 0


# ---------------------------------------------------------------------------
# Untriaged count
# ---------------------------------------------------------------------------

class TestUntriagedCount:
    """Tests for get_untriaged_count()."""

    def test_zero_in_empty_registry(self, empty_registry_path):
        reg = ClassificationRegistry(empty_registry_path)
        assert reg.get_untriaged_count() == 0

    def test_zero_when_all_triaged(self, populated_registry_path):
        reg = ClassificationRegistry(populated_registry_path)
        assert reg.get_untriaged_count() == 0

    def test_counts_untriaged_failing_tests(self, empty_registry_path):
        """Manually insert a failing entry without triage to test counting.

        We bypass add_test() validation by writing directly to the data
        to simulate a legacy/imported entry.
        """
        reg = ClassificationRegistry(empty_registry_path)
        # Directly insert to bypass validation (simulating legacy data)
        reg._data["tests"]["legacy.py::test_old"] = {
            "category": "unit",
            "status": "failing",
            "failure_reason": "unknown",
            "triage_decision": "",
        }
        reg._refresh_metadata()
        assert reg.get_untriaged_count() == 1


# ---------------------------------------------------------------------------
# Persistence (save)
# ---------------------------------------------------------------------------

class TestPersistence:
    """Tests for save() with atomic writes."""

    def test_save_creates_file(self, tmp_path):
        path = str(tmp_path / "new_registry.json")
        reg = ClassificationRegistry(path)
        reg.add_test("test_a.py::test_ok", {
            "category": "unit",
            "status": "passing",
        })
        reg.save()

        assert os.path.isfile(path)
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        assert data["version"] == "1.0"
        assert "test_a.py::test_ok" in data["tests"]
        assert data["last_updated"]  # Should be set

    def test_save_updates_last_updated(self, empty_registry_path):
        reg = ClassificationRegistry(empty_registry_path)
        reg.save()

        with open(empty_registry_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        assert data["last_updated"] != ""

    def test_save_round_trip(self, tmp_path):
        """Save and reload should preserve all data."""
        path = str(tmp_path / "roundtrip.json")
        reg1 = ClassificationRegistry(path)
        reg1.add_test("test_x.py::test_one", {
            "category": "unit",
            "status": "passing",
            "notes": "all good",
        })
        reg1.add_test("test_y.py::test_two", {
            "category": "integration",
            "status": "failing",
            "triage_decision": "fix",
            "triage_date": "2025-01-15",
            "failure_reason": "timeout",
        })
        reg1.save()

        reg2 = ClassificationRegistry(path)
        assert len(reg2.tests) == 2
        assert reg2.get_test("test_x.py::test_one")["notes"] == "all good"
        assert reg2.get_test("test_y.py::test_two")["triage_decision"] == "fix"
        assert reg2.metadata["total_tests"] == 2
        assert reg2.metadata["by_status"]["passing"] == 1
        assert reg2.metadata["by_status"]["failing"] == 1

    def test_save_no_temp_files_left(self, tmp_path):
        """Atomic write should not leave .tmp files behind."""
        path = str(tmp_path / "clean.json")
        reg = ClassificationRegistry(path)
        reg.save()

        files = os.listdir(tmp_path)
        tmp_files = [f for f in files if f.endswith(".tmp")]
        assert tmp_files == []

    def test_save_creates_parent_directory(self, tmp_path):
        path = str(tmp_path / "subdir" / "nested" / "registry.json")
        reg = ClassificationRegistry(path)
        reg.save()
        assert os.path.isfile(path)


# ---------------------------------------------------------------------------
# Metadata refresh
# ---------------------------------------------------------------------------

class TestMetadataRefresh:
    """Tests for metadata recomputation."""

    def test_metadata_after_multiple_adds(self, empty_registry_path):
        reg = ClassificationRegistry(empty_registry_path)
        reg.add_test("t1", {"category": "unit", "status": "passing"})
        reg.add_test("t2", {"category": "unit", "status": "skipped"})
        reg.add_test("t3", {
            "category": "unit",
            "status": "failing",
            "triage_decision": "fix",
        })
        reg.add_test("t4", {"category": "unit", "status": "flaky"})
        reg.add_test("t5", {"category": "unit", "status": "quarantined"})

        meta = reg.metadata
        assert meta["total_tests"] == 5
        assert meta["by_status"]["passing"] == 1
        assert meta["by_status"]["skipped"] == 1
        assert meta["by_status"]["failing"] == 1
        assert meta["by_status"]["flaky"] == 1
        assert meta["by_status"]["quarantined"] == 1
        assert meta["triaged"] == 1
        assert meta["untriaged"] == 0
