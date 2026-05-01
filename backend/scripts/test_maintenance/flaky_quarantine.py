"""
Flaky Test Quarantine
======================

Detects and tracks flaky tests — tests that pass on some runs and fail on
others within the same code state.  Manages the quarantine lifecycle:

1. **Record** test results keyed by ``(test_id, run_id)``.
2. **Detect** flakiness when a test has both pass *and* fail for the same
   ``run_id`` (same code state).
3. **Quarantine** a test with a reason, date, and last failure message.
4. **Restore** a test after it passes consistently (default 3 consecutive
   passes).

Persistence is via ``quarantine-log.json`` using atomic writes (write to
temp file, then ``os.replace``).

The class optionally interacts with :class:`ClassificationRegistry` to
update test status when quarantining or restoring.

Requirements: 5.1, 5.2, 5.3, 5.4, 5.5
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .classification_registry import (
    ClassificationRegistry,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class QuarantineEntry:
    """A single quarantined test entry."""

    test_id: str
    reason: str
    quarantine_date: str  # ISO 8601 date string (YYYY-MM-DD)
    last_failure_message: str
    consecutive_passes: int
    status: str  # "quarantined" or "restored"


@dataclass
class QuarantineReport:
    """Summary report of all quarantined tests."""

    entries: List[QuarantineEntry] = field(default_factory=list)
    total_quarantined: int = 0
    total_restored: int = 0


# ---------------------------------------------------------------------------
# Internal types
# ---------------------------------------------------------------------------

@dataclass
class _TestResult:
    """A single recorded test execution result."""

    passed: bool
    run_id: str


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class FlakyQuarantine:
    """Manages flaky test detection and quarantine lifecycle.

    Parameters
    ----------
    registry_path:
        Path to the ``test-classification-registry.json`` used by
        :class:`ClassificationRegistry`.
    quarantine_log_path:
        Path to the ``quarantine-log.json`` file for persistence.
    """

    def __init__(self, registry_path: str, quarantine_log_path: str) -> None:
        self._registry = ClassificationRegistry(registry_path)
        self._log_path = quarantine_log_path
        self._log_data = self._load_log()

        # In-memory result history: test_id -> list of _TestResult
        self._results: Dict[str, List[_TestResult]] = {}

    # ------------------------------------------------------------------
    # Public methods
    # ------------------------------------------------------------------

    def record_result(self, test_id: str, passed: bool, run_id: str) -> None:
        """Record a test execution result for flakiness tracking.

        Parameters
        ----------
        test_id:
            Unique test identifier, e.g.
            ``"backend/tests/unit/test_foo.py::test_bar"``.
        passed:
            Whether the test passed.
        run_id:
            Identifier for the test run / code state.  Results with the
            same ``run_id`` are considered to be from the same code state.
        """
        result = _TestResult(passed=passed, run_id=run_id)
        self._results.setdefault(test_id, []).append(result)

        # Update consecutive pass tracking for quarantined tests
        entry = self._find_entry(test_id)
        if entry is not None and entry.status == "quarantined":
            if passed:
                entry.consecutive_passes += 1
            else:
                entry.consecutive_passes = 0
                entry.last_failure_message = (
                    f"Failed during run {run_id}"
                )
            self._save_log()

    def detect_flaky(self, test_id: str) -> bool:
        """Check if a test has shown flaky behaviour.

        A test is flaky if it has both a pass *and* a fail result for the
        same ``run_id`` (same code state).

        Parameters
        ----------
        test_id:
            The test to check.

        Returns
        -------
        bool
            ``True`` if the test is flaky.
        """
        results = self._results.get(test_id, [])
        if not results:
            return False

        # Group results by run_id
        by_run: Dict[str, Dict[str, bool]] = {}
        for r in results:
            state = by_run.setdefault(r.run_id, {"pass": False, "fail": False})
            if r.passed:
                state["pass"] = True
            else:
                state["fail"] = True

        # Flaky if any run_id has both pass and fail
        return any(
            s["pass"] and s["fail"] for s in by_run.values()
        )

    def quarantine(self, test_id: str, reason: str) -> None:
        """Mark a test as quarantined.

        Creates a new quarantine entry (or re-quarantines a restored one)
        and updates the classification registry.

        Parameters
        ----------
        test_id:
            The test to quarantine.
        reason:
            Human-readable reason for quarantining.
        """
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # Determine last failure message from recorded results
        last_failure = ""
        results = self._results.get(test_id, [])
        for r in reversed(results):
            if not r.passed:
                last_failure = f"Failed during run {r.run_id}"
                break

        existing = self._find_entry(test_id)
        if existing is not None:
            # Re-quarantine a previously restored test
            existing.reason = reason
            existing.quarantine_date = today
            existing.last_failure_message = last_failure
            existing.consecutive_passes = 0
            existing.status = "quarantined"
        else:
            entry = QuarantineEntry(
                test_id=test_id,
                reason=reason,
                quarantine_date=today,
                last_failure_message=last_failure,
                consecutive_passes=0,
                status="quarantined",
            )
            self._log_data["entries"].append(asdict(entry))

        self._save_log()

        # Update classification registry
        self._update_registry(test_id, status="quarantined", reason=reason)

    def check_restoration(
        self, test_id: str, consecutive_passes: int = 3
    ) -> bool:
        """Check if a quarantined test should be restored.

        A test is eligible for restoration when it has accumulated at
        least *consecutive_passes* consecutive passes.  If eligible, the
        entry's status is updated to ``"restored"`` and the registry is
        updated.

        Parameters
        ----------
        test_id:
            The test to check.
        consecutive_passes:
            Number of consecutive passes required for restoration.

        Returns
        -------
        bool
            ``True`` if the test was restored (or was already restored).
        """
        entry = self._find_entry(test_id)
        if entry is None:
            return False

        if entry.status == "restored":
            return True

        if entry.consecutive_passes >= consecutive_passes:
            entry.status = "restored"
            self._save_log()
            self._update_registry(test_id, status="passing", reason=None)
            return True

        return False

    def get_quarantine_report(self) -> QuarantineReport:
        """Generate a report of all quarantined tests.

        Returns
        -------
        QuarantineReport
            Contains all entries and summary counts.
        """
        entries: List[QuarantineEntry] = []
        total_quarantined = 0
        total_restored = 0

        for raw in self._log_data.get("entries", []):
            entry = QuarantineEntry(
                test_id=raw["test_id"],
                reason=raw["reason"],
                quarantine_date=raw["quarantine_date"],
                last_failure_message=raw["last_failure_message"],
                consecutive_passes=raw["consecutive_passes"],
                status=raw["status"],
            )
            entries.append(entry)
            if entry.status == "quarantined":
                total_quarantined += 1
            elif entry.status == "restored":
                total_restored += 1

        return QuarantineReport(
            entries=entries,
            total_quarantined=total_quarantined,
            total_restored=total_restored,
        )

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def _load_log(self) -> Dict[str, Any]:
        """Load the quarantine log from disk, or return an empty one."""
        if not os.path.isfile(self._log_path):
            logger.info(
                "Quarantine log not found at %s — starting empty",
                self._log_path,
            )
            return {"version": "1.0", "entries": []}

        try:
            with open(self._log_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if not isinstance(data.get("entries"), list):
                logger.warning(
                    "Invalid quarantine log structure — resetting"
                )
                return {"version": "1.0", "entries": []}
            return data
        except (json.JSONDecodeError, OSError) as exc:
            logger.error(
                "Failed to load quarantine log: %s — starting empty", exc
            )
            return {"version": "1.0", "entries": []}

    def _save_log(self) -> None:
        """Persist the quarantine log using atomic writes.

        Writes to a temporary file in the same directory, then renames
        to the target path to prevent corruption on crash.
        """
        target_dir = os.path.dirname(self._log_path) or "."
        os.makedirs(target_dir, exist_ok=True)

        fd, tmp_path = tempfile.mkstemp(
            dir=target_dir, suffix=".tmp", prefix=".quarantine_"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(self._log_data, fh, indent=2, ensure_ascii=False)
                fh.write("\n")
            os.replace(tmp_path, self._log_path)
            logger.debug("Quarantine log saved to %s", self._log_path)
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _find_entry(self, test_id: str) -> Optional[QuarantineEntry]:
        """Find a quarantine entry by test ID.

        Returns a *mutable* reference — changes to the returned object
        are reflected in ``self._log_data`` because we update the raw
        dict in-place.
        """
        for raw in self._log_data.get("entries", []):
            if raw.get("test_id") == test_id:
                # Return a proxy that writes back to the raw dict
                return _EntryProxy(raw)  # type: ignore[return-value]
        return None

    def _update_registry(
        self,
        test_id: str,
        status: str,
        reason: Optional[str],
    ) -> None:
        """Update the classification registry for a quarantined/restored test."""
        try:
            entry_data: Dict[str, Any] = {
                "category": "unit",
                "status": status,
                "failure_reason": reason or "",
                "notes": (
                    f"Quarantined: {reason}" if status == "quarantined"
                    else "Restored after consecutive passes"
                ),
            }
            # Failing/quarantined tests need a triage_decision for the
            # registry's validation.  "quarantine" is a valid decision.
            if status == "quarantined":
                entry_data["triage_decision"] = "quarantine"
                entry_data["triage_date"] = datetime.now(
                    timezone.utc
                ).strftime("%Y-%m-%d")

            self._registry.add_test(test_id, entry_data)
            self._registry.save()
        except Exception as exc:
            # Registry update is best-effort; don't break quarantine ops
            logger.warning(
                "Failed to update classification registry for %s: %s",
                test_id,
                exc,
            )


class _EntryProxy:
    """Thin proxy that makes a raw dict behave like a QuarantineEntry.

    Attribute reads/writes go directly to the underlying dict so that
    mutations are persisted when ``_save_log()`` serialises ``_log_data``.
    """

    _FIELDS = {
        "test_id", "reason", "quarantine_date",
        "last_failure_message", "consecutive_passes", "status",
    }

    def __init__(self, raw: Dict[str, Any]) -> None:
        # Use object.__setattr__ to avoid triggering our __setattr__
        object.__setattr__(self, "_raw", raw)

    def __getattr__(self, name: str) -> Any:
        raw = object.__getattribute__(self, "_raw")
        if name in _EntryProxy._FIELDS:
            return raw.get(name)
        raise AttributeError(name)

    def __setattr__(self, name: str, value: Any) -> None:
        raw = object.__getattribute__(self, "_raw")
        if name in _EntryProxy._FIELDS:
            raw[name] = value
        else:
            object.__setattr__(self, name, value)
