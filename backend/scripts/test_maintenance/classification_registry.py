"""
Classification Registry
========================

Manages the test classification registry (``test-classification-registry.json``),
which tracks every test's category, status, triage decision, and metadata.

Key behaviours:

* **Triage enforcement** — failing tests *must* have a ``triage_decision``
  (``"fix"``, ``"quarantine"``, or ``"delete"``).  Attempting to add a failing
  entry without one raises ``ValueError``.
* **Stale failure detection** — surfaces tests that have been failing longer
  than a configurable threshold (default 14 days).
* **Atomic writes** — persists via write-to-temp-then-rename to avoid
  corrupting the registry on crash.

The registry is wired into ``scanner.py`` in task 11.5.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Valid values for key fields
VALID_STATUSES = {"passing", "failing", "skipped", "flaky", "quarantined"}
VALID_TRIAGE_DECISIONS = {"fix", "quarantine", "delete"}
VALID_CATEGORIES = {"unit", "integration", "api", "e2e"}

# Statuses that require a triage decision
_TRIAGE_REQUIRED_STATUSES = {"failing"}


def _empty_registry() -> Dict[str, Any]:
    """Return a blank registry structure."""
    return {
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


class ClassificationRegistry:
    """Manages the test classification registry JSON file.

    Parameters
    ----------
    registry_path:
        Path to the ``test-classification-registry.json`` file.
        If the file does not exist, an empty registry is created in memory
        (call :meth:`save` to persist it).
    """

    def __init__(self, registry_path: str) -> None:
        self._path = registry_path
        self._data: Dict[str, Any] = self._load()

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def _load(self) -> Dict[str, Any]:
        """Load the registry from disk, or return an empty one."""
        if not os.path.isfile(self._path):
            logger.info(
                "Registry file not found at %s — starting empty", self._path
            )
            return _empty_registry()

        try:
            with open(self._path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            # Basic structural validation
            if not isinstance(data.get("tests"), dict):
                logger.warning("Invalid registry structure — resetting")
                return _empty_registry()
            return data
        except (json.JSONDecodeError, OSError) as exc:
            logger.error("Failed to load registry: %s — starting empty", exc)
            return _empty_registry()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def validate_entry(self, entry: Dict[str, Any]) -> None:
        """Validate a single registry entry.

        Raises
        ------
        ValueError
            If the entry has ``status`` in ``{"failing"}`` but no valid
            ``triage_decision``.
        """
        status = entry.get("status", "")
        triage = entry.get("triage_decision")

        if status in _TRIAGE_REQUIRED_STATUSES:
            if not triage or triage not in VALID_TRIAGE_DECISIONS:
                raise ValueError(
                    f"Failing tests must have a triage_decision "
                    f"(one of {sorted(VALID_TRIAGE_DECISIONS)}), "
                    f"got {triage!r}"
                )

    def add_test(self, test_id: str, entry: Dict[str, Any]) -> None:
        """Add or update a test entry in the registry.

        Parameters
        ----------
        test_id:
            Unique test identifier, e.g.
            ``"backend/tests/unit/test_foo.py::TestBar::test_baz"``.
        entry:
            Dictionary with keys such as ``category``, ``status``,
            ``failure_reason``, ``triage_decision``, ``triage_date``,
            ``target_fix_date``, ``root_cause``, ``notes``.

        Raises
        ------
        ValueError
            If validation fails (e.g. failing test without triage_decision).
        """
        self.validate_entry(entry)
        self._data["tests"][test_id] = entry
        self._refresh_metadata()

    def get_test(self, test_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a test entry by ID, or ``None`` if not found."""
        return self._data["tests"].get(test_id)

    def get_stale_failures(
        self,
        days_threshold: int = 14,
        scan_date: Optional[date] = None,
    ) -> List[Dict[str, Any]]:
        """Return tests that have been failing longer than *days_threshold*.

        Parameters
        ----------
        days_threshold:
            Number of days after which a failing test is considered stale.
        scan_date:
            Reference date for staleness calculation.  Defaults to today.

        Returns
        -------
        list[dict]
            Each dict contains ``test_id``, ``entry``, and ``days_failing``.
        """
        if scan_date is None:
            scan_date = date.today()

        stale: List[Dict[str, Any]] = []
        for test_id, entry in self._data["tests"].items():
            if entry.get("status") != "failing":
                continue
            triage_date_str = entry.get("triage_date", "")
            if not triage_date_str:
                continue
            try:
                triage_date = date.fromisoformat(triage_date_str)
            except (ValueError, TypeError):
                continue

            days_failing = (scan_date - triage_date).days
            if days_failing > days_threshold:
                stale.append({
                    "test_id": test_id,
                    "entry": entry,
                    "days_failing": days_failing,
                })

        return stale

    def get_untriaged_count(self) -> int:
        """Return the number of failing tests without a triage_decision."""
        count = 0
        for entry in self._data["tests"].values():
            if entry.get("status") == "failing":
                triage = entry.get("triage_decision")
                if not triage or triage not in VALID_TRIAGE_DECISIONS:
                    count += 1
        return count

    def save(self) -> None:
        """Persist the registry to disk using atomic writes.

        Writes to a temporary file in the same directory, then renames
        to the target path.  This prevents corruption if the process
        crashes mid-write.
        """
        self._data["last_updated"] = datetime.now(timezone.utc).isoformat()
        self._refresh_metadata()

        target_dir = os.path.dirname(self._path) or "."
        os.makedirs(target_dir, exist_ok=True)

        # Atomic write: temp file → rename
        fd, tmp_path = tempfile.mkstemp(
            dir=target_dir, suffix=".tmp", prefix=".registry_"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(self._data, fh, indent=2, ensure_ascii=False)
                fh.write("\n")
            os.replace(tmp_path, self._path)
            logger.info("Registry saved to %s", self._path)
        except BaseException:
            # Clean up temp file on failure
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    # ------------------------------------------------------------------
    # Properties for convenient access
    # ------------------------------------------------------------------

    @property
    def tests(self) -> Dict[str, Dict[str, Any]]:
        """Direct access to the tests dictionary."""
        return self._data["tests"]

    @property
    def metadata(self) -> Dict[str, Any]:
        """Direct access to the metadata dictionary."""
        return self._data["metadata"]

    @property
    def version(self) -> str:
        """Registry schema version."""
        return self._data.get("version", "1.0")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _refresh_metadata(self) -> None:
        """Recompute metadata counters from the current tests dict."""
        tests = self._data["tests"]
        by_status: Dict[str, int] = {
            "passing": 0,
            "failing": 0,
            "skipped": 0,
            "flaky": 0,
            "quarantined": 0,
        }
        triaged = 0
        untriaged = 0

        for entry in tests.values():
            status = entry.get("status", "")
            if status in by_status:
                by_status[status] += 1

            if entry.get("status") == "failing":
                triage = entry.get("triage_decision")
                if triage and triage in VALID_TRIAGE_DECISIONS:
                    triaged += 1
                else:
                    untriaged += 1
            elif entry.get("triage_decision"):
                triaged += 1

        self._data["metadata"] = {
            "total_tests": len(tests),
            "triaged": triaged,
            "untriaged": untriaged,
            "by_status": by_status,
        }
