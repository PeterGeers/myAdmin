"""
Compliance Checker — configurable rule engine for test conventions
==================================================================

Validates test and source files against project conventions defined in a
JSON rules file (``test-compliance-rules.json``).  Rules are categorised as
**required**, **recommended**, or **forbidden** and grouped by file type
(``backend_unit``, ``frontend_unit``, ``backend_route``).

Only stdlib dependencies are used: ``ast``, ``json``, ``logging``,
``os``, ``pathlib``, ``re``, ``dataclasses``.
"""

from __future__ import annotations

import ast
import json
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ComplianceViolation:
    """A single compliance violation detected in a file.

    Attributes:
        file_path:             Path to the file containing the violation.
        line_number:           1-based line number (0 when file-level).
        rule_id:               Identifier from the rules JSON (e.g. ``BU001``).
        severity:              ``"required"``, ``"recommended"``, or
                               ``"forbidden"``.
        expected_pattern:      The pattern the file should match.
        actual_pattern:        What was actually found (or ``""``).
        convention_reference:  Pointer to project docs for the convention.
    """

    file_path: str
    line_number: int
    rule_id: str
    severity: str
    expected_pattern: str
    actual_pattern: str
    convention_reference: str


VALID_SEVERITIES = {"required", "recommended", "forbidden"}

# Directories that trigger auto-marking via ``pytest_collection_modifyitems``
# in the project's root conftest.py.  Files inside these directories do NOT
# need explicit ``@pytest.mark.*`` decorators.
AUTO_MARKING_DIRS = {
    "unit",
    "integration",
    "api",
    "e2e",
    "performance",
    "database",
    "patterns",
    "manual",
}


# ---------------------------------------------------------------------------
# Rule representation
# ---------------------------------------------------------------------------

@dataclass
class ComplianceRule:
    """Internal representation of a single compliance rule."""

    id: str
    name: str
    description: str
    pattern: Optional[str] = None
    anti_patterns: List[str] = field(default_factory=list)
    reference: str = ""


# ---------------------------------------------------------------------------
# Default built-in rules (fallback when JSON is missing / invalid)
# ---------------------------------------------------------------------------

_DEFAULT_RULES: Dict[str, Dict[str, List[Dict[str, Any]]]] = {
    "backend_unit": {
        "required": [
            {
                "id": "BU002",
                "name": "pytest_marker_required",
                "description": "All test files must have pytest markers",
                "pattern": r"@pytest\.mark\.(unit|integration|api|e2e)",
                "reference": "backend/pytest.ini",
            },
        ],
        "recommended": [],
        "forbidden": [],
    },
    "frontend_unit": {"required": [], "recommended": [], "forbidden": []},
    "backend_route": {"required": [], "recommended": [], "forbidden": []},
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class ComplianceChecker:
    """Checks test and source files against project framework conventions.

    Loads rules from a JSON configuration file.  If the file is missing or
    invalid, falls back to a minimal set of built-in defaults.

    Typical usage::

        checker = ComplianceChecker("backend/tests/test-compliance-rules.json")
        violations = checker.check_backend_test("backend/tests/unit/test_foo.py")
        for v in violations:
            print(f"[{v.rule_id}] {v.expected_pattern}")
    """

    def __init__(self, rules_path: str) -> None:
        """Load rules from *rules_path*.

        Args:
            rules_path: Path to the ``test-compliance-rules.json`` file.
        """
        self._rules_path = rules_path
        self._rules = self._load_rules(rules_path)

    # ------------------------------------------------------------------
    # Public check methods
    # ------------------------------------------------------------------

    def check_backend_test(self, file_path: str) -> List[ComplianceViolation]:
        """Check a backend test file against ``backend_unit`` rules.

        Args:
            file_path: Path to the ``.py`` test file.

        Returns:
            List of :class:`ComplianceViolation` instances.
        """
        return self._check_file(file_path, "backend_unit")

    def check_frontend_test(self, file_path: str) -> List[ComplianceViolation]:
        """Check a frontend test file against ``frontend_unit`` rules.

        Args:
            file_path: Path to the ``.ts`` / ``.tsx`` test file.

        Returns:
            List of :class:`ComplianceViolation` instances.
        """
        return self._check_file(file_path, "frontend_unit")

    def check_backend_route(self, file_path: str) -> List[ComplianceViolation]:
        """Check a backend route file against ``backend_route`` rules.

        Args:
            file_path: Path to the ``.py`` route file.

        Returns:
            List of :class:`ComplianceViolation` instances.
        """
        return self._check_file(file_path, "backend_route")

    # ------------------------------------------------------------------
    # Accessors (useful for testing)
    # ------------------------------------------------------------------

    @property
    def rules(self) -> Dict[str, Dict[str, List[ComplianceRule]]]:
        """Return the loaded rules dictionary."""
        return self._rules

    # ------------------------------------------------------------------
    # Internal implementation
    # ------------------------------------------------------------------

    def _load_rules(
        self, rules_path: str
    ) -> Dict[str, Dict[str, List[ComplianceRule]]]:
        """Load and parse the rules JSON file.

        Returns a dict keyed by category (``backend_unit``, etc.), each
        containing ``required``, ``recommended``, and ``forbidden`` lists
        of :class:`ComplianceRule`.
        """
        raw: Dict[str, Dict[str, List[Dict[str, Any]]]]

        try:
            with open(rules_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            raw = data.get("rules", {})
        except (FileNotFoundError, json.JSONDecodeError, OSError) as exc:
            logger.warning(
                "Could not load compliance rules from %s: %s — "
                "falling back to built-in defaults.",
                rules_path,
                exc,
            )
            raw = _DEFAULT_RULES

        result: Dict[str, Dict[str, List[ComplianceRule]]] = {}

        for category, severities in raw.items():
            result[category] = {}
            for severity in ("required", "recommended", "forbidden"):
                rule_dicts = severities.get(severity, [])
                result[category][severity] = [
                    ComplianceRule(
                        id=rd.get("id", "UNKNOWN"),
                        name=rd.get("name", ""),
                        description=rd.get("description", ""),
                        pattern=rd.get("pattern"),
                        anti_patterns=rd.get("anti_patterns", []),
                        reference=rd.get("reference", ""),
                    )
                    for rd in rule_dicts
                ]

        return result

    def _check_file(
        self, file_path: str, category: str
    ) -> List[ComplianceViolation]:
        """Run all rules for *category* against *file_path*."""
        path = Path(file_path)

        if not path.exists():
            logger.warning("File does not exist: %s", path)
            return []

        try:
            source = path.read_text(encoding="utf-8")
        except (PermissionError, OSError) as exc:
            logger.error("Error reading file %s: %s", path, exc)
            return []

        category_rules = self._rules.get(category, {})
        violations: List[ComplianceViolation] = []

        # --- Required rules ------------------------------------------------
        for rule in category_rules.get("required", []):
            violations.extend(
                self._check_required_rule(rule, source, file_path, path)
            )

        # --- Recommended rules ---------------------------------------------
        for rule in category_rules.get("recommended", []):
            violations.extend(
                self._check_recommended_rule(rule, source, file_path, path)
            )

        # --- Forbidden rules -----------------------------------------------
        for rule in category_rules.get("forbidden", []):
            violations.extend(
                self._check_forbidden_rule(rule, source, file_path)
            )

        return violations

    # ------------------------------------------------------------------
    # Rule checking helpers
    # ------------------------------------------------------------------

    def _check_required_rule(
        self,
        rule: ComplianceRule,
        source: str,
        file_path: str,
        path: Path,
    ) -> List[ComplianceViolation]:
        """Check a *required* rule.

        For required rules with a ``pattern``, the file must contain at
        least one match.  Special handling for ``pytest_marker_required``:
        files in auto-marking directories are exempt.

        Anti-patterns are also checked — each match is a violation.
        """
        violations: List[ComplianceViolation] = []

        # Special case: pytest marker rule
        if rule.name == "pytest_marker_required":
            if self._is_in_auto_marking_dir(path):
                # Auto-marked by conftest.py — no explicit marker needed
                return violations

        # Check that the required pattern is present
        if rule.pattern:
            if not re.search(rule.pattern, source):
                violations.append(ComplianceViolation(
                    file_path=file_path,
                    line_number=0,
                    rule_id=rule.id,
                    severity="required",
                    expected_pattern=rule.pattern,
                    actual_pattern="",
                    convention_reference=rule.reference,
                ))

        # Check anti-patterns
        violations.extend(
            self._check_anti_patterns(rule, source, file_path, "required")
        )

        return violations

    def _check_recommended_rule(
        self,
        rule: ComplianceRule,
        source: str,
        file_path: str,
        path: Path,
    ) -> List[ComplianceViolation]:
        """Check a *recommended* rule.

        Same logic as required, but severity is ``"recommended"``.
        Anti-patterns trigger violations only when the recommended
        pattern is absent.
        """
        violations: List[ComplianceViolation] = []

        # Only flag anti-patterns when the recommended pattern is absent
        has_pattern = rule.pattern and re.search(rule.pattern, source)

        if not has_pattern:
            violations.extend(
                self._check_anti_patterns(
                    rule, source, file_path, "recommended"
                )
            )

        return violations

    def _check_forbidden_rule(
        self,
        rule: ComplianceRule,
        source: str,
        file_path: str,
    ) -> List[ComplianceViolation]:
        """Check a *forbidden* rule.

        Every anti-pattern match is a violation.
        """
        return self._check_anti_patterns(
            rule, source, file_path, "forbidden"
        )

    def _check_anti_patterns(
        self,
        rule: ComplianceRule,
        source: str,
        file_path: str,
        severity: str,
    ) -> List[ComplianceViolation]:
        """Find all anti-pattern matches in *source* and return violations."""
        violations: List[ComplianceViolation] = []
        source_lines = source.splitlines()

        for anti_pattern in rule.anti_patterns:
            try:
                regex = re.compile(anti_pattern)
            except re.error as exc:
                logger.warning(
                    "Invalid regex in rule %s anti_pattern '%s': %s",
                    rule.id,
                    anti_pattern,
                    exc,
                )
                continue

            for line_idx, line in enumerate(source_lines, start=1):
                # Skip comment lines
                stripped = line.strip()
                if stripped.startswith("#") or stripped.startswith("//"):
                    continue

                if regex.search(line):
                    violations.append(ComplianceViolation(
                        file_path=file_path,
                        line_number=line_idx,
                        rule_id=rule.id,
                        severity=severity,
                        expected_pattern=rule.pattern or "",
                        actual_pattern=anti_pattern,
                        convention_reference=rule.reference,
                    ))

        return violations

    @staticmethod
    def _is_in_auto_marking_dir(path: Path) -> bool:
        """Return ``True`` if *path* is inside an auto-marking directory.

        The project's ``conftest.py`` auto-marks tests based on their
        directory (``unit/``, ``integration/``, ``api/``, ``e2e/``, etc.).
        """
        parts = path.parts
        for part in parts:
            if part.lower() in AUTO_MARKING_DIRS:
                return True
        return False
