"""
Property-based tests for ComplianceChecker
==========================================

Uses Hypothesis to verify compliance checking correctness.

Properties tested:
    - Property 25: Pytest marker detection
    - Property 26: Blueprint pattern detection
    - Property 27: Configurable compliance rules
"""

from __future__ import annotations

import json
import os
import tempfile

import pytest
from hypothesis import given, settings, strategies as st

from scripts.test_maintenance.compliance_checker import (
    AUTO_MARKING_DIRS,
    ComplianceChecker,
    ComplianceViolation,
    VALID_SEVERITIES,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_temp_file(content: str, suffix: str = ".py") -> str:
    """Write *content* to a temporary file and return its path."""
    fd, path = tempfile.mkstemp(suffix=suffix, prefix="test_prop_")
    try:
        os.write(fd, content.encode("utf-8"))
    finally:
        os.close(fd)
    return path


def _write_temp_json(data: dict) -> str:
    """Write *data* as JSON to a temporary file and return its path."""
    fd, path = tempfile.mkstemp(suffix=".json", prefix="rules_prop_")
    try:
        os.write(fd, json.dumps(data).encode("utf-8"))
    finally:
        os.close(fd)
    return path


def _make_rules_json(
    *,
    backend_unit_required: list | None = None,
    backend_unit_recommended: list | None = None,
    backend_unit_forbidden: list | None = None,
    frontend_unit_required: list | None = None,
    backend_route_required: list | None = None,
) -> dict:
    """Build a minimal rules JSON structure."""
    return {
        "version": "1.0",
        "rules": {
            "backend_unit": {
                "required": backend_unit_required or [],
                "recommended": backend_unit_recommended or [],
                "forbidden": backend_unit_forbidden or [],
            },
            "frontend_unit": {
                "required": frontend_unit_required or [],
            },
            "backend_route": {
                "required": backend_route_required or [],
            },
        },
    }


# Marker rule used in multiple tests
_MARKER_RULE = {
    "id": "BU002",
    "name": "pytest_marker_required",
    "description": "All test files must have pytest markers",
    "pattern": r"@pytest\.mark\.(unit|integration|api|e2e)",
    "reference": "backend/pytest.ini",
}

# Blueprint rule
_BLUEPRINT_RULE = {
    "id": "BR001",
    "name": "blueprint_naming",
    "description": "Route files must use Blueprint with _bp suffix",
    "pattern": r"_bp\s*=\s*Blueprint",
    "reference": ".kiro/steering/structure.md",
}


# ---------------------------------------------------------------------------
# Property 25: Pytest marker detection
# ---------------------------------------------------------------------------

# Feature: test-maintenance-framework, Property 25: Pytest marker detection
class TestPytestMarkerDetection:
    """For any backend test file lacking explicit markers and not in an
    auto-marking directory, the checker flags it as non-compliant.
    """

    @settings(max_examples=100)
    @given(
        has_marker=st.booleans(),
        marker_type=st.sampled_from(["unit", "integration", "api", "e2e"]),
    )
    def test_missing_marker_flagged_outside_auto_dir(
        self,
        has_marker,
        marker_type,
    ):
        """Files outside auto-marking dirs without markers are flagged."""
        lines = [
            "import pytest",
            "",
        ]
        if has_marker:
            lines.append(f"@pytest.mark.{marker_type}")
        lines.extend([
            "def test_something():",
            "    assert True",
        ])
        source = "\n".join(lines)

        # Write to a path that is NOT inside an auto-marking directory
        path = _write_temp_file(source)
        try:
            rules_json = _make_rules_json(
                backend_unit_required=[_MARKER_RULE]
            )
            rules_path = _write_temp_json(rules_json)
            try:
                checker = ComplianceChecker(rules_path)
                violations = checker.check_backend_test(path)

                marker_violations = [
                    v for v in violations if v.rule_id == "BU002"
                ]

                if has_marker:
                    assert len(marker_violations) == 0, (
                        f"File has @pytest.mark.{marker_type} but was "
                        f"flagged: {marker_violations}"
                    )
                else:
                    assert len(marker_violations) > 0, (
                        "File without marker should be flagged"
                    )
            finally:
                os.unlink(rules_path)
        finally:
            os.unlink(path)

    def test_auto_marking_dir_exempts_marker_check(self, tmp_path):
        """Files inside auto-marking directories are exempt from marker check."""
        unit_dir = tmp_path / "unit"
        unit_dir.mkdir()
        test_file = unit_dir / "test_example.py"
        test_file.write_text(
            "def test_something():\n    assert True\n",
            encoding="utf-8",
        )

        rules_json = _make_rules_json(
            backend_unit_required=[_MARKER_RULE]
        )
        rules_path = _write_temp_json(rules_json)
        try:
            checker = ComplianceChecker(rules_path)
            violations = checker.check_backend_test(str(test_file))

            marker_violations = [
                v for v in violations if v.rule_id == "BU002"
            ]
            assert len(marker_violations) == 0, (
                f"File in auto-marking dir 'unit/' should not be flagged "
                f"for missing marker: {marker_violations}"
            )
        finally:
            os.unlink(rules_path)

    @settings(max_examples=50)
    @given(
        dir_name=st.sampled_from(sorted(AUTO_MARKING_DIRS)),
    )
    def test_all_auto_marking_dirs_exempt(self, dir_name):
        """Every known auto-marking directory exempts the marker check."""
        # Use tempfile to avoid Hypothesis + tmp_path conflict
        base_dir = tempfile.mkdtemp(prefix="automark_")
        sub_dir = os.path.join(base_dir, dir_name)
        os.makedirs(sub_dir, exist_ok=True)
        test_file = os.path.join(sub_dir, "test_auto.py")

        with open(test_file, "w", encoding="utf-8") as fh:
            fh.write("def test_auto():\n    assert True\n")

        rules_json = _make_rules_json(
            backend_unit_required=[_MARKER_RULE]
        )
        rules_path = _write_temp_json(rules_json)
        try:
            checker = ComplianceChecker(rules_path)
            violations = checker.check_backend_test(test_file)

            marker_violations = [
                v for v in violations if v.rule_id == "BU002"
            ]
            assert len(marker_violations) == 0, (
                f"File in auto-marking dir '{dir_name}/' should not be "
                f"flagged: {marker_violations}"
            )
        finally:
            os.unlink(rules_path)
            os.unlink(test_file)


# ---------------------------------------------------------------------------
# Property 26: Blueprint pattern detection
# ---------------------------------------------------------------------------

# Feature: test-maintenance-framework, Property 26: Blueprint pattern detection
class TestBlueprintPatternDetection:
    """For any route file in backend/src/routes/, verify Blueprint with
    _bp suffix is detected.
    """

    @settings(max_examples=100)
    @given(
        bp_name=st.from_regex(r"[a-z][a-z0-9_]{2,15}", fullmatch=True),
        has_blueprint=st.booleans(),
    )
    def test_blueprint_with_bp_suffix_detected(
        self,
        bp_name,
        has_blueprint,
    ):
        """Files with Blueprint declarations using _bp suffix pass;
        files without are flagged."""
        if has_blueprint:
            source = (
                f"from flask import Blueprint\n\n"
                f"{bp_name}_bp = Blueprint('{bp_name}', __name__)\n"
            )
        else:
            source = (
                f"from flask import Flask\n\n"
                f"app = Flask(__name__)\n"
            )

        path = _write_temp_file(source)
        try:
            rules_json = _make_rules_json(
                backend_route_required=[_BLUEPRINT_RULE]
            )
            rules_path = _write_temp_json(rules_json)
            try:
                checker = ComplianceChecker(rules_path)
                violations = checker.check_backend_route(path)

                bp_violations = [
                    v for v in violations if v.rule_id == "BR001"
                ]

                if has_blueprint:
                    assert len(bp_violations) == 0, (
                        f"File with '{bp_name}_bp = Blueprint(...)' should "
                        f"not be flagged: {bp_violations}"
                    )
                else:
                    assert len(bp_violations) > 0, (
                        "File without Blueprint declaration should be flagged"
                    )
            finally:
                os.unlink(rules_path)
        finally:
            os.unlink(path)

    def test_blueprint_without_bp_suffix_flagged(self):
        """A Blueprint without _bp suffix is flagged."""
        source = (
            "from flask import Blueprint\n\n"
            "my_routes = Blueprint('my_routes', __name__)\n"
        )
        path = _write_temp_file(source)
        try:
            rules_json = _make_rules_json(
                backend_route_required=[_BLUEPRINT_RULE]
            )
            rules_path = _write_temp_json(rules_json)
            try:
                checker = ComplianceChecker(rules_path)
                violations = checker.check_backend_route(path)

                bp_violations = [
                    v for v in violations if v.rule_id == "BR001"
                ]
                assert len(bp_violations) > 0, (
                    "Blueprint without _bp suffix should be flagged"
                )
            finally:
                os.unlink(rules_path)
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# Property 27: Configurable compliance rules
# ---------------------------------------------------------------------------

# Feature: test-maintenance-framework, Property 27: Configurable compliance rules
class TestConfigurableComplianceRules:
    """For any valid rules JSON, the checker loads and applies all rules;
    changing rules changes detected violations.
    """

    @settings(max_examples=50)
    @given(
        anti_pattern=st.sampled_from([
            r"import mysql\.connector",
            r"from mysql\.connector",
            r"sys\.path\.append",
            r"load_dotenv",
        ]),
    )
    def test_forbidden_rule_detects_anti_pattern(self, anti_pattern):
        """A forbidden rule flags any matching anti-pattern."""
        # Build source that contains the anti-pattern
        # Use the raw string (un-escaped) for the source content
        raw_pattern = anti_pattern.replace(r"\.", ".")
        source = f"{raw_pattern}\n\ndef test_foo():\n    pass\n"

        path = _write_temp_file(source)
        try:
            rules_json = _make_rules_json(
                backend_unit_forbidden=[{
                    "id": "TEST001",
                    "name": "test_forbidden",
                    "description": "Test forbidden rule",
                    "anti_patterns": [anti_pattern],
                    "reference": "test",
                }]
            )
            rules_path = _write_temp_json(rules_json)
            try:
                checker = ComplianceChecker(rules_path)
                violations = checker.check_backend_test(path)

                test_violations = [
                    v for v in violations if v.rule_id == "TEST001"
                ]
                assert len(test_violations) > 0, (
                    f"Forbidden anti-pattern '{anti_pattern}' should be "
                    f"detected in source:\n{source}"
                )
            finally:
                os.unlink(rules_path)
        finally:
            os.unlink(path)

    def test_changing_rules_changes_violations(self):
        """Adding or removing rules changes which violations are detected."""
        source = (
            "import mysql.connector\n"
            "import sys\n"
            "sys.path.append('/foo')\n"
            "\ndef test_foo():\n    pass\n"
        )
        path = _write_temp_file(source)
        try:
            # Rules with only mysql forbidden
            rules_v1 = _make_rules_json(
                backend_unit_forbidden=[{
                    "id": "F001",
                    "name": "no_mysql",
                    "description": "No mysql",
                    "anti_patterns": [r"import mysql\.connector"],
                    "reference": "test",
                }]
            )
            rules_path_v1 = _write_temp_json(rules_v1)

            # Rules with mysql AND sys.path forbidden
            rules_v2 = _make_rules_json(
                backend_unit_forbidden=[
                    {
                        "id": "F001",
                        "name": "no_mysql",
                        "description": "No mysql",
                        "anti_patterns": [r"import mysql\.connector"],
                        "reference": "test",
                    },
                    {
                        "id": "F002",
                        "name": "no_sys_path",
                        "description": "No sys.path",
                        "anti_patterns": [r"sys\.path\.append"],
                        "reference": "test",
                    },
                ]
            )
            rules_path_v2 = _write_temp_json(rules_v2)

            try:
                checker_v1 = ComplianceChecker(rules_path_v1)
                violations_v1 = checker_v1.check_backend_test(path)
                rule_ids_v1 = {v.rule_id for v in violations_v1}

                checker_v2 = ComplianceChecker(rules_path_v2)
                violations_v2 = checker_v2.check_backend_test(path)
                rule_ids_v2 = {v.rule_id for v in violations_v2}

                # v1 should only have F001
                assert "F001" in rule_ids_v1
                assert "F002" not in rule_ids_v1

                # v2 should have both F001 and F002
                assert "F001" in rule_ids_v2
                assert "F002" in rule_ids_v2
            finally:
                os.unlink(rules_path_v1)
                os.unlink(rules_path_v2)
        finally:
            os.unlink(path)

    def test_empty_rules_produce_no_violations(self):
        """An empty rules file produces zero violations."""
        source = "import mysql.connector\n\ndef test_foo():\n    pass\n"
        path = _write_temp_file(source)
        try:
            rules_json = _make_rules_json()  # All empty
            rules_path = _write_temp_json(rules_json)
            try:
                checker = ComplianceChecker(rules_path)
                violations = checker.check_backend_test(path)
                assert len(violations) == 0, (
                    f"Empty rules should produce no violations, "
                    f"got: {violations}"
                )
            finally:
                os.unlink(rules_path)
        finally:
            os.unlink(path)

    def test_missing_rules_file_uses_defaults(self):
        """A missing rules file falls back to built-in defaults."""
        checker = ComplianceChecker("/nonexistent/rules.json")
        # Should not raise — falls back to defaults
        assert checker.rules is not None

    def test_all_violations_have_valid_fields(self):
        """Every violation has all required fields with valid values."""
        source = (
            "import mysql.connector\n"
            "sys.path.append('/foo')\n"
            "\ndef test_foo():\n    pass\n"
        )
        path = _write_temp_file(source)
        try:
            rules_json = _make_rules_json(
                backend_unit_forbidden=[{
                    "id": "F001",
                    "name": "no_mysql",
                    "description": "No mysql",
                    "anti_patterns": [r"import mysql\.connector"],
                    "reference": "test-ref",
                }],
                backend_unit_required=[{
                    "id": "R001",
                    "name": "no_sys_path",
                    "description": "No sys.path",
                    "anti_patterns": [r"sys\.path\.append"],
                    "reference": "test-ref-2",
                }],
            )
            rules_path = _write_temp_json(rules_json)
            try:
                checker = ComplianceChecker(rules_path)
                violations = checker.check_backend_test(path)

                for v in violations:
                    assert isinstance(v.file_path, str) and v.file_path
                    assert isinstance(v.line_number, int) and v.line_number >= 0
                    assert isinstance(v.rule_id, str) and v.rule_id
                    assert v.severity in VALID_SEVERITIES
                    assert isinstance(v.convention_reference, str)
            finally:
                os.unlink(rules_path)
        finally:
            os.unlink(path)
