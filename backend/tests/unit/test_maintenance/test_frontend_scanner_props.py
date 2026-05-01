"""
Property-based tests for FrontendScanner
=========================================

Uses Hypothesis to verify that the frontend scanner correctly detects
missing MSW handlers, missing provider wrappers, and stale imports.

Properties tested:
    - Property 19: Frontend MSW detection
    - Property 20: Frontend provider detection
    - Property 21: Frontend stale import detection
"""

from __future__ import annotations

import os
import textwrap

import pytest
from hypothesis import given, settings, HealthCheck, strategies as st

from scripts.test_maintenance.frontend_scanner import (
    FrontendScanner,
    FrontendViolation,
    VALID_VIOLATION_TYPES,
    VALID_SEVERITIES,
)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# HTTP call patterns to inject into test files
_st_http_call = st.sampled_from([
    "fetch('/api/users')",
    "axios.get('/api/data')",
    "axios.post('/api/submit', data)",
    "axios.put('/api/update', data)",
    "axios.delete('/api/remove')",
    "axios.patch('/api/patch', data)",
    "api.get('/users')",
    "api.post('/submit', payload)",
])

# MSW setup patterns
_st_msw_setup = st.sampled_from([
    "const server = setupServer(\n  http.get('/api/users', () => HttpResponse.json([]))\n)",
    "const server = setupServer(\n  rest.get('/api/data', (req, res, ctx) => res(ctx.json([])))\n)",
    "server.use(http.post('/api/submit', () => HttpResponse.json({})))",
    "server.listen()",
])

# Component names for imports
_st_component_name = st.from_regex(r"[A-Z][a-zA-Z]{2,15}", fullmatch=True)


# ---------------------------------------------------------------------------
# Helpers — generate test file content
# ---------------------------------------------------------------------------

def _build_tsx_test(
    *,
    http_calls: list[str] | None = None,
    msw_setup: str | None = None,
    use_direct_render: bool = False,
    use_test_utils_render: bool = False,
    relative_imports: list[str] | None = None,
    alias_imports: list[str] | None = None,
) -> str:
    """Build a synthetic TypeScript test file."""
    lines: list[str] = []

    # Imports
    if use_direct_render:
        lines.append(
            "import { render, screen } from '@testing-library/react';"
        )
    elif use_test_utils_render:
        lines.append(
            "import { render, screen } from '../test-utils';"
        )
    else:
        lines.append("import { screen } from '@testing-library/react';")

    lines.append("import { describe, it, expect } from 'vitest';")

    if relative_imports:
        for imp in relative_imports:
            lines.append(f"import {{ default as Comp }} from '{imp}';")

    if alias_imports:
        for imp in alias_imports:
            lines.append(f"import {{ default as Comp }} from '{imp}';")

    if msw_setup:
        lines.append("import { setupServer } from 'msw/node';")
        lines.append("import { http, HttpResponse } from 'msw';")

    lines.append("")

    # MSW setup
    if msw_setup:
        lines.append(msw_setup)
        lines.append("")

    # Test body
    lines.append("describe('Component', () => {")
    lines.append("  it('should render', () => {")

    if http_calls:
        for call in http_calls:
            lines.append(f"    const result = {call};")

    lines.append("    expect(true).toBe(true);")
    lines.append("  });")
    lines.append("});")
    lines.append("")

    return "\n".join(lines)


def _write_test_file(tmp_path, content, filename="Component.test.tsx"):
    """Write a test file and return its path."""
    test_file = tmp_path / filename
    test_file.write_text(content, encoding="utf-8")
    return str(test_file)


# ---------------------------------------------------------------------------
# Property 19: Frontend MSW detection
# ---------------------------------------------------------------------------

# Feature: test-maintenance-framework, Property 19: Frontend MSW detection
class TestFrontendMSWDetection:
    """For any TypeScript test file with HTTP calls without MSW setup,
    the scanner flags it.
    """

    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.too_slow],
    )
    @given(
        http_calls=st.lists(_st_http_call, min_size=1, max_size=4),
    )
    def test_http_calls_without_msw_are_flagged(
        self,
        tmp_path_factory,
        http_calls,
    ):
        """Test files with HTTP calls but no MSW setup should be flagged."""
        tmp_path = tmp_path_factory.mktemp("msw")

        content = _build_tsx_test(http_calls=http_calls)
        test_file = _write_test_file(tmp_path, content)

        scanner = FrontendScanner(source_dir=str(tmp_path))
        violations = scanner.analyze_file(test_file)

        msw_violations = [
            v for v in violations if v.violation_type == "missing_msw"
        ]
        assert len(msw_violations) > 0, (
            f"Expected missing_msw violation for HTTP calls {http_calls}. "
            f"Content:\n{content}"
        )

        for v in msw_violations:
            assert v.file_path == test_file
            assert v.violation_type in VALID_VIOLATION_TYPES
            assert v.severity in VALID_SEVERITIES
            assert v.line_number > 0
            assert v.description
            assert v.suggested_fix

    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.too_slow],
    )
    @given(
        http_calls=st.lists(_st_http_call, min_size=1, max_size=3),
        msw_setup=_st_msw_setup,
    )
    def test_http_calls_with_msw_are_not_flagged(
        self,
        tmp_path_factory,
        http_calls,
        msw_setup,
    ):
        """Test files with HTTP calls AND MSW setup should NOT be flagged."""
        tmp_path = tmp_path_factory.mktemp("msw_ok")

        content = _build_tsx_test(
            http_calls=http_calls,
            msw_setup=msw_setup,
        )
        test_file = _write_test_file(tmp_path, content)

        scanner = FrontendScanner(source_dir=str(tmp_path))
        violations = scanner.analyze_file(test_file)

        msw_violations = [
            v for v in violations if v.violation_type == "missing_msw"
        ]
        assert len(msw_violations) == 0, (
            f"Expected no missing_msw violations when MSW is set up. "
            f"Got: {[(v.line_number, v.description) for v in msw_violations]}"
        )

    def test_no_http_calls_no_violations(self, tmp_path):
        """A test file without HTTP calls should not trigger MSW violations."""
        content = _build_tsx_test()
        test_file = _write_test_file(tmp_path, content)

        scanner = FrontendScanner(source_dir=str(tmp_path))
        violations = scanner.analyze_file(test_file)

        msw_violations = [
            v for v in violations if v.violation_type == "missing_msw"
        ]
        assert len(msw_violations) == 0

    def test_nonexistent_file_no_violations(self):
        """A nonexistent file should produce zero violations."""
        scanner = FrontendScanner()
        violations = scanner.analyze_file("/nonexistent/test.test.tsx")
        assert violations == []

    def test_non_test_file_no_violations(self, tmp_path):
        """A non-test file should produce zero violations."""
        regular_file = tmp_path / "Component.tsx"
        regular_file.write_text("export default function Comp() {}", encoding="utf-8")

        scanner = FrontendScanner(source_dir=str(tmp_path))
        violations = scanner.analyze_file(str(regular_file))
        assert violations == []


# ---------------------------------------------------------------------------
# Property 20: Frontend provider detection
# ---------------------------------------------------------------------------

# Feature: test-maintenance-framework, Property 20: Frontend provider detection
class TestFrontendProviderDetection:
    """For any test file importing render from @testing-library/react
    instead of test-utils, the scanner flags it.
    """

    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.too_slow],
    )
    @given(
        has_http_calls=st.booleans(),
    )
    def test_direct_render_import_is_flagged(
        self,
        tmp_path_factory,
        has_http_calls,
    ):
        """Test files importing render from @testing-library/react should
        be flagged.
        """
        tmp_path = tmp_path_factory.mktemp("provider")

        http_calls = ["fetch('/api/data')"] if has_http_calls else None
        msw_setup = (
            "const server = setupServer(\n"
            "  http.get('/api/data', () => HttpResponse.json([]))\n)"
        ) if has_http_calls else None

        content = _build_tsx_test(
            use_direct_render=True,
            http_calls=http_calls,
            msw_setup=msw_setup,
        )
        test_file = _write_test_file(tmp_path, content)

        scanner = FrontendScanner(source_dir=str(tmp_path))
        violations = scanner.analyze_file(test_file)

        provider_violations = [
            v for v in violations if v.violation_type == "missing_provider"
        ]
        assert len(provider_violations) > 0, (
            f"Expected missing_provider violation for direct render import. "
            f"Content:\n{content}"
        )

        for v in provider_violations:
            assert v.violation_type in VALID_VIOLATION_TYPES
            assert v.severity in VALID_SEVERITIES
            assert v.line_number > 0
            assert "render" in v.description.lower() or "test-utils" in v.description.lower()

    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.too_slow],
    )
    @given(
        has_http_calls=st.booleans(),
    )
    def test_test_utils_render_import_is_not_flagged(
        self,
        tmp_path_factory,
        has_http_calls,
    ):
        """Test files importing render from test-utils should NOT be flagged."""
        tmp_path = tmp_path_factory.mktemp("provider_ok")

        http_calls = ["fetch('/api/data')"] if has_http_calls else None
        msw_setup = (
            "const server = setupServer(\n"
            "  http.get('/api/data', () => HttpResponse.json([]))\n)"
        ) if has_http_calls else None

        content = _build_tsx_test(
            use_test_utils_render=True,
            http_calls=http_calls,
            msw_setup=msw_setup,
        )
        test_file = _write_test_file(tmp_path, content)

        scanner = FrontendScanner(source_dir=str(tmp_path))
        violations = scanner.analyze_file(test_file)

        provider_violations = [
            v for v in violations if v.violation_type == "missing_provider"
        ]
        assert len(provider_violations) == 0, (
            f"Expected no missing_provider violations for test-utils import. "
            f"Got: {[(v.line_number, v.description) for v in provider_violations]}"
        )

    def test_no_render_import_no_violations(self, tmp_path):
        """A test file without any render import should not trigger
        provider violations.
        """
        content = _build_tsx_test()
        test_file = _write_test_file(tmp_path, content)

        scanner = FrontendScanner(source_dir=str(tmp_path))
        violations = scanner.analyze_file(test_file)

        provider_violations = [
            v for v in violations if v.violation_type == "missing_provider"
        ]
        assert len(provider_violations) == 0


# ---------------------------------------------------------------------------
# Property 21: Frontend stale import detection
# ---------------------------------------------------------------------------

# Feature: test-maintenance-framework, Property 21: Frontend stale import detection
class TestFrontendStaleImportDetection:
    """For any test file importing from a non-existent path, the scanner
    flags it.
    """

    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.too_slow],
    )
    @given(
        component_name=_st_component_name,
    )
    def test_stale_relative_import_is_flagged(
        self,
        tmp_path_factory,
        component_name,
    ):
        """Test files with relative imports to non-existent files should
        be flagged.
        """
        tmp_path = tmp_path_factory.mktemp("stale")

        # Create a test file that imports from a non-existent relative path
        content = _build_tsx_test(
            relative_imports=[f"./{component_name}"],
        )
        test_file = _write_test_file(tmp_path, content)

        scanner = FrontendScanner(source_dir=str(tmp_path))
        violations = scanner.analyze_file(test_file)

        stale_violations = [
            v for v in violations if v.violation_type == "stale_import"
        ]
        assert len(stale_violations) > 0, (
            f"Expected stale_import violation for non-existent import "
            f"'./{component_name}'. Content:\n{content}"
        )

        for v in stale_violations:
            assert v.violation_type in VALID_VIOLATION_TYPES
            assert v.severity in VALID_SEVERITIES
            assert v.line_number > 0
            assert v.description
            assert v.suggested_fix

    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.too_slow],
    )
    @given(
        component_name=_st_component_name,
    )
    def test_valid_relative_import_is_not_flagged(
        self,
        tmp_path_factory,
        component_name,
    ):
        """Test files with relative imports to existing files should NOT
        be flagged.
        """
        tmp_path = tmp_path_factory.mktemp("valid")

        # Create the component file that the test imports
        comp_file = tmp_path / f"{component_name}.tsx"
        comp_file.write_text(
            f"export default function {component_name}() {{ return null; }}",
            encoding="utf-8",
        )

        content = _build_tsx_test(
            relative_imports=[f"./{component_name}"],
        )
        test_file = _write_test_file(tmp_path, content)

        scanner = FrontendScanner(source_dir=str(tmp_path))
        violations = scanner.analyze_file(test_file)

        stale_violations = [
            v for v in violations if v.violation_type == "stale_import"
        ]
        assert len(stale_violations) == 0, (
            f"Expected no stale_import violations for existing import "
            f"'./{component_name}'. "
            f"Got: {[(v.line_number, v.description) for v in stale_violations]}"
        )

    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.too_slow],
    )
    @given(
        component_name=_st_component_name,
    )
    def test_stale_alias_import_is_flagged(
        self,
        tmp_path_factory,
        component_name,
    ):
        """Test files with @/ alias imports to non-existent files should
        be flagged.
        """
        tmp_path = tmp_path_factory.mktemp("stale_alias")

        # Create source_dir but NOT the component
        src_dir = tmp_path / "src"
        src_dir.mkdir()

        content = _build_tsx_test(
            alias_imports=[f"@/components/{component_name}"],
        )
        test_file = _write_test_file(tmp_path, content)

        scanner = FrontendScanner(source_dir=str(src_dir))
        violations = scanner.analyze_file(test_file)

        stale_violations = [
            v for v in violations if v.violation_type == "stale_import"
        ]
        assert len(stale_violations) > 0, (
            f"Expected stale_import violation for non-existent alias import "
            f"'@/components/{component_name}'. Content:\n{content}"
        )

    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.too_slow],
    )
    @given(
        component_name=_st_component_name,
    )
    def test_valid_alias_import_is_not_flagged(
        self,
        tmp_path_factory,
        component_name,
    ):
        """Test files with @/ alias imports to existing files should NOT
        be flagged.
        """
        tmp_path = tmp_path_factory.mktemp("valid_alias")

        # Create source_dir with the component
        src_dir = tmp_path / "src"
        components_dir = src_dir / "components"
        components_dir.mkdir(parents=True)

        comp_file = components_dir / f"{component_name}.tsx"
        comp_file.write_text(
            f"export default function {component_name}() {{ return null; }}",
            encoding="utf-8",
        )

        content = _build_tsx_test(
            alias_imports=[f"@/components/{component_name}"],
        )
        test_file = _write_test_file(tmp_path, content)

        scanner = FrontendScanner(source_dir=str(src_dir))
        violations = scanner.analyze_file(test_file)

        stale_violations = [
            v for v in violations if v.violation_type == "stale_import"
        ]
        assert len(stale_violations) == 0, (
            f"Expected no stale_import violations for existing alias import "
            f"'@/components/{component_name}'. "
            f"Got: {[(v.line_number, v.description) for v in stale_violations]}"
        )

    def test_node_modules_import_not_checked(self, tmp_path):
        """Imports from node_modules (no ./ or @/ prefix) should not be
        checked for staleness.
        """
        content = textwrap.dedent("""\
            import React from 'react';
            import { render } from '@testing-library/react';
            import { vi } from 'vitest';

            describe('Test', () => {
              it('works', () => {
                expect(true).toBe(true);
              });
            });
        """)
        test_file = _write_test_file(tmp_path, content)

        scanner = FrontendScanner(source_dir=str(tmp_path))
        violations = scanner.analyze_file(test_file)

        stale_violations = [
            v for v in violations if v.violation_type == "stale_import"
        ]
        assert len(stale_violations) == 0


# ---------------------------------------------------------------------------
# Cross-cutting: violation field validation
# ---------------------------------------------------------------------------

class TestFrontendViolationFields:
    """All FrontendViolation instances must have valid fields."""

    def test_violation_dataclass_fields(self):
        """FrontendViolation dataclass has all required fields."""
        v = FrontendViolation(
            file_path="test.test.tsx",
            line_number=1,
            violation_type="missing_msw",
            severity="high",
            description="Test violation",
            suggested_fix="Fix it",
        )
        assert v.file_path == "test.test.tsx"
        assert v.line_number == 1
        assert v.violation_type == "missing_msw"
        assert v.severity == "high"
        assert v.description == "Test violation"
        assert v.suggested_fix == "Fix it"
        assert v.violation_type in VALID_VIOLATION_TYPES
        assert v.severity in VALID_SEVERITIES
