"""
Unit tests for ComplianceChecker
=================================

Tests rule loading, matching, and specific compliance patterns.
"""

from __future__ import annotations

import json
import textwrap

import pytest

from scripts.test_maintenance.compliance_checker import (
    ComplianceChecker,
    ComplianceViolation,
    ComplianceRule,
    VALID_SEVERITIES,
)


@pytest.fixture
def rules_file(tmp_path):
    """Create a test compliance rules JSON file."""
    rules = {
        "version": "1.0",
        "rules": {
            "backend_unit": {
                "required": [
                    {
                        "id": "BU001",
                        "name": "use_shared_mock_db",
                        "description": "Unit tests must use shared mock_db fixture",
                        "pattern": "mock_db",
                        "anti_patterns": [
                            "MagicMock.*cursor",
                            "mysql\\.connector",
                            "DatabaseManager\\(test_mode",
                        ],
                        "reference": "conftest.py",
                    },
                    {
                        "id": "BU002",
                        "name": "pytest_marker_required",
                        "description": "All test files must have pytest markers",
                        "pattern": "@pytest\\.mark\\.(unit|integration|api|e2e)",
                        "reference": "pytest.ini",
                    },
                    {
                        "id": "BU003",
                        "name": "no_sys_path_manipulation",
                        "description": "Tests must not manipulate sys.path",
                        "anti_patterns": [
                            "sys\\.path\\.append",
                            "sys\\.path\\.insert",
                        ],
                        "reference": "conftest.py",
                    },
                ],
                "recommended": [
                    {
                        "id": "BU004",
                        "name": "use_mock_env",
                        "description": "Use mock_env fixture",
                        "pattern": "mock_env",
                        "anti_patterns": ["load_dotenv", "os\\.environ\\["],
                        "reference": "conftest.py",
                    },
                ],
                "forbidden": [
                    {
                        "id": "BU005",
                        "name": "no_real_db_in_unit",
                        "description": "No mysql.connector in unit tests",
                        "anti_patterns": [
                            "import mysql\\.connector",
                            "from mysql\\.connector",
                        ],
                        "reference": "database-patterns.md",
                    },
                ],
            },
            "frontend_unit": {
                "required": [
                    {
                        "id": "FU001",
                        "name": "use_test_utils_render",
                        "description": "Use test-utils render",
                        "pattern": "from.*test-utils.*import.*render|import.*from.*test-utils|import.*from.*@/test-utils",
                        "anti_patterns": [
                            "from '@testing-library/react' import.*render",
                        ],
                        "reference": "test-utils.tsx",
                    },
                ],
            },
            "backend_route": {
                "required": [
                    {
                        "id": "BR001",
                        "name": "blueprint_naming",
                        "description": "Blueprint with _bp suffix",
                        "pattern": "_bp\\s*=\\s*Blueprint",
                        "reference": "structure.md",
                    },
                ],
            },
        },
    }
    path = tmp_path / "test-compliance-rules.json"
    path.write_text(json.dumps(rules), encoding="utf-8")
    return str(path)


class TestRuleLoading:
    """Tests for loading and parsing rules from JSON."""

    def test_loads_all_categories(self, rules_file):
        checker = ComplianceChecker(rules_file)
        assert "backend_unit" in checker.rules
        assert "frontend_unit" in checker.rules
        assert "backend_route" in checker.rules

    def test_loads_required_rules(self, rules_file):
        checker = ComplianceChecker(rules_file)
        required = checker.rules["backend_unit"]["required"]
        assert len(required) == 3
        assert required[0].id == "BU001"
        assert required[1].id == "BU002"
        assert required[2].id == "BU003"

    def test_loads_recommended_rules(self, rules_file):
        checker = ComplianceChecker(rules_file)
        recommended = checker.rules["backend_unit"]["recommended"]
        assert len(recommended) == 1
        assert recommended[0].id == "BU004"

    def test_loads_forbidden_rules(self, rules_file):
        checker = ComplianceChecker(rules_file)
        forbidden = checker.rules["backend_unit"]["forbidden"]
        assert len(forbidden) == 1
        assert forbidden[0].id == "BU005"

    def test_missing_file_uses_defaults(self):
        checker = ComplianceChecker("/nonexistent/rules.json")
        assert checker.rules is not None
        # Should have at least the default marker rule
        assert "backend_unit" in checker.rules

    def test_invalid_json_uses_defaults(self, tmp_path):
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("not valid json {{{", encoding="utf-8")
        checker = ComplianceChecker(str(bad_file))
        assert checker.rules is not None


class TestBackendUnitChecks:
    """Tests for backend unit test compliance checking."""

    def test_missing_marker_flagged(self, rules_file, tmp_path):
        """File without pytest marker outside auto-marking dir is flagged."""
        f = tmp_path / "test_no_marker.py"
        f.write_text("def test_x():\n    pass\n")
        checker = ComplianceChecker(rules_file)
        violations = checker.check_backend_test(str(f))
        marker_v = [v for v in violations if v.rule_id == "BU002"]
        assert len(marker_v) > 0

    def test_marker_present_not_flagged(self, rules_file, tmp_path):
        """File with pytest marker is not flagged for BU002."""
        f = tmp_path / "test_marked.py"
        f.write_text(textwrap.dedent("""\
            import pytest
            @pytest.mark.unit
            def test_x():
                pass
        """))
        checker = ComplianceChecker(rules_file)
        violations = checker.check_backend_test(str(f))
        marker_v = [v for v in violations if v.rule_id == "BU002"]
        assert len(marker_v) == 0

    def test_auto_marking_dir_exempt(self, rules_file, tmp_path):
        """File in unit/ directory is exempt from marker check."""
        unit_dir = tmp_path / "unit"
        unit_dir.mkdir()
        f = unit_dir / "test_auto.py"
        f.write_text("def test_x():\n    pass\n")
        checker = ComplianceChecker(rules_file)
        violations = checker.check_backend_test(str(f))
        marker_v = [v for v in violations if v.rule_id == "BU002"]
        assert len(marker_v) == 0

    def test_sys_path_manipulation_flagged(self, rules_file, tmp_path):
        """sys.path.append is flagged as anti-pattern."""
        f = tmp_path / "test_syspath.py"
        f.write_text(textwrap.dedent("""\
            import sys
            sys.path.append('/some/path')
            def test_x():
                pass
        """))
        checker = ComplianceChecker(rules_file)
        violations = checker.check_backend_test(str(f))
        syspath_v = [v for v in violations if v.rule_id == "BU003"]
        assert len(syspath_v) > 0

    def test_forbidden_mysql_import_flagged(self, rules_file, tmp_path):
        """Forbidden rule: import mysql.connector is flagged."""
        f = tmp_path / "test_mysql.py"
        f.write_text("import mysql.connector\n\ndef test_x(): pass\n")
        checker = ComplianceChecker(rules_file)
        violations = checker.check_backend_test(str(f))
        mysql_v = [v for v in violations if v.rule_id == "BU005"]
        assert len(mysql_v) > 0
        assert mysql_v[0].severity == "forbidden"

    def test_recommended_mock_env_anti_pattern(self, rules_file, tmp_path):
        """Recommended rule: load_dotenv flagged when mock_env absent."""
        f = tmp_path / "test_env.py"
        f.write_text(textwrap.dedent("""\
            from dotenv import load_dotenv
            load_dotenv()
            def test_x():
                pass
        """))
        checker = ComplianceChecker(rules_file)
        violations = checker.check_backend_test(str(f))
        env_v = [v for v in violations if v.rule_id == "BU004"]
        assert len(env_v) > 0
        assert env_v[0].severity == "recommended"

    def test_recommended_not_flagged_when_pattern_present(
        self, rules_file, tmp_path
    ):
        """Recommended rule: no violation when mock_env is used."""
        f = tmp_path / "test_env_ok.py"
        f.write_text(textwrap.dedent("""\
            def test_x(mock_env):
                pass
        """))
        checker = ComplianceChecker(rules_file)
        violations = checker.check_backend_test(str(f))
        env_v = [v for v in violations if v.rule_id == "BU004"]
        assert len(env_v) == 0

    def test_comment_lines_not_flagged(self, rules_file, tmp_path):
        """Anti-patterns in comments should not be flagged."""
        f = tmp_path / "test_comments.py"
        f.write_text(textwrap.dedent("""\
            # import mysql.connector  -- this is a comment
            def test_x():
                pass
        """))
        checker = ComplianceChecker(rules_file)
        violations = checker.check_backend_test(str(f))
        mysql_v = [v for v in violations if v.rule_id == "BU005"]
        assert len(mysql_v) == 0


class TestBackendRouteChecks:
    """Tests for backend route file compliance checking."""

    def test_blueprint_with_bp_suffix_passes(self, rules_file, tmp_path):
        f = tmp_path / "routes.py"
        f.write_text(textwrap.dedent("""\
            from flask import Blueprint
            banking_bp = Blueprint('banking', __name__)
        """))
        checker = ComplianceChecker(rules_file)
        violations = checker.check_backend_route(str(f))
        bp_v = [v for v in violations if v.rule_id == "BR001"]
        assert len(bp_v) == 0

    def test_missing_blueprint_flagged(self, rules_file, tmp_path):
        f = tmp_path / "routes.py"
        f.write_text(textwrap.dedent("""\
            from flask import Flask
            app = Flask(__name__)
        """))
        checker = ComplianceChecker(rules_file)
        violations = checker.check_backend_route(str(f))
        bp_v = [v for v in violations if v.rule_id == "BR001"]
        assert len(bp_v) > 0


class TestFrontendChecks:
    """Tests for frontend test file compliance checking."""

    def test_test_utils_render_passes(self, rules_file, tmp_path):
        f = tmp_path / "Component.test.tsx"
        f.write_text(
            "import { render } from '@/test-utils';\n"
            "test('renders', () => { render(<Comp />); });\n"
        )
        checker = ComplianceChecker(rules_file)
        violations = checker.check_frontend_test(str(f))
        render_v = [v for v in violations if v.rule_id == "FU001"]
        assert len(render_v) == 0

    def test_bare_render_flagged(self, rules_file, tmp_path):
        f = tmp_path / "Component.test.tsx"
        f.write_text(
            "import { render } from '@testing-library/react';\n"
            "test('renders', () => { render(<Comp />); });\n"
        )
        checker = ComplianceChecker(rules_file)
        violations = checker.check_frontend_test(str(f))
        # Should be flagged because test-utils pattern is missing
        render_v = [v for v in violations if v.rule_id == "FU001"]
        assert len(render_v) > 0


class TestViolationFields:
    """Tests that all violations have valid fields."""

    def test_all_fields_populated(self, rules_file, tmp_path):
        f = tmp_path / "test_all.py"
        f.write_text("import mysql.connector\ndef test_x(): pass\n")
        checker = ComplianceChecker(rules_file)
        violations = checker.check_backend_test(str(f))
        for v in violations:
            assert isinstance(v.file_path, str) and v.file_path
            assert isinstance(v.line_number, int) and v.line_number >= 0
            assert isinstance(v.rule_id, str) and v.rule_id
            assert v.severity in VALID_SEVERITIES
            assert isinstance(v.convention_reference, str)

    def test_nonexistent_file_returns_empty(self, rules_file):
        checker = ComplianceChecker(rules_file)
        violations = checker.check_backend_test("/nonexistent/test.py")
        assert violations == []
