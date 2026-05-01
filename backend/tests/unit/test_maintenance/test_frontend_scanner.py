"""
Unit tests for FrontendScanner
================================

Tests specific examples and edge cases for frontend test analysis,
complementing the property-based tests.

Requirements: 9.1, 9.2
"""

from __future__ import annotations

import textwrap

import pytest

from scripts.test_maintenance.frontend_scanner import (
    FrontendScanner,
    FrontendViolation,
    FrontendScanReport,
    VALID_VIOLATION_TYPES,
    VALID_SEVERITIES,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_test(tmp_path, filename, content):
    """Write a test file and return its path as a string."""
    f = tmp_path / filename
    f.write_text(textwrap.dedent(content), encoding="utf-8")
    return str(f)


# ---------------------------------------------------------------------------
# MSW detection tests
# ---------------------------------------------------------------------------

class TestMSWDetection:
    """Tests for missing MSW handler detection."""

    def test_detects_bare_fetch(self, tmp_path):
        """A test with fetch() but no MSW setup should be flagged."""
        test_file = _write_test(tmp_path, "Api.test.tsx", """\
            import { render, screen } from '../test-utils';
            import { describe, it, expect } from 'vitest';

            describe('ApiComponent', () => {
              it('loads data', async () => {
                const response = await fetch('/api/users');
                const data = await response.json();
                expect(data).toBeDefined();
              });
            });
        """)

        scanner = FrontendScanner(source_dir=str(tmp_path))
        violations = scanner.analyze_file(test_file)

        msw = [v for v in violations if v.violation_type == "missing_msw"]
        assert len(msw) == 1
        assert msw[0].severity == "high"
        assert "fetch" in msw[0].description.lower() or "HTTP" in msw[0].description

    def test_detects_axios_calls(self, tmp_path):
        """A test with axios calls but no MSW setup should be flagged."""
        test_file = _write_test(tmp_path, "Service.test.ts", """\
            import axios from 'axios';
            import { describe, it, expect } from 'vitest';

            describe('Service', () => {
              it('fetches data', async () => {
                const result = await axios.get('/api/data');
                expect(result.data).toBeDefined();
              });

              it('posts data', async () => {
                const result = await axios.post('/api/submit', { name: 'test' });
                expect(result.status).toBe(200);
              });
            });
        """)

        scanner = FrontendScanner(source_dir=str(tmp_path))
        violations = scanner.analyze_file(test_file)

        msw = [v for v in violations if v.violation_type == "missing_msw"]
        assert len(msw) == 1

    def test_no_violation_with_msw_setup(self, tmp_path):
        """A test with fetch() AND MSW setup should NOT be flagged."""
        test_file = _write_test(tmp_path, "Api.test.tsx", """\
            import { render, screen } from '../test-utils';
            import { setupServer } from 'msw/node';
            import { http, HttpResponse } from 'msw';

            const server = setupServer(
              http.get('/api/users', () => HttpResponse.json([{ id: 1 }]))
            );

            beforeAll(() => server.listen());
            afterEach(() => server.resetHandlers());
            afterAll(() => server.close());

            describe('ApiComponent', () => {
              it('loads data', async () => {
                const response = await fetch('/api/users');
                const data = await response.json();
                expect(data).toHaveLength(1);
              });
            });
        """)

        scanner = FrontendScanner(source_dir=str(tmp_path))
        violations = scanner.analyze_file(test_file)

        msw = [v for v in violations if v.violation_type == "missing_msw"]
        assert len(msw) == 0

    def test_no_violation_without_http_calls(self, tmp_path):
        """A test without HTTP calls should NOT trigger MSW violations."""
        test_file = _write_test(tmp_path, "Button.test.tsx", """\
            import { render, screen } from '../test-utils';

            describe('Button', () => {
              it('renders', () => {
                render(<button>Click</button>);
                expect(screen.getByText('Click')).toBeDefined();
              });
            });
        """)

        scanner = FrontendScanner(source_dir=str(tmp_path))
        violations = scanner.analyze_file(test_file)

        msw = [v for v in violations if v.violation_type == "missing_msw"]
        assert len(msw) == 0

    def test_comments_are_ignored(self, tmp_path):
        """HTTP calls in comments should not trigger violations."""
        test_file = _write_test(tmp_path, "Comment.test.tsx", """\
            import { describe, it, expect } from 'vitest';

            // const response = await fetch('/api/users');
            /* axios.get('/api/data') */

            describe('Test', () => {
              it('works', () => {
                expect(true).toBe(true);
              });
            });
        """)

        scanner = FrontendScanner(source_dir=str(tmp_path))
        violations = scanner.analyze_file(test_file)

        msw = [v for v in violations if v.violation_type == "missing_msw"]
        assert len(msw) == 0


# ---------------------------------------------------------------------------
# Provider detection tests
# ---------------------------------------------------------------------------

class TestProviderDetection:
    """Tests for missing provider wrapper detection."""

    def test_detects_direct_render_import(self, tmp_path):
        """Importing render from @testing-library/react should be flagged."""
        test_file = _write_test(tmp_path, "Component.test.tsx", """\
            import { render, screen } from '@testing-library/react';

            describe('Component', () => {
              it('renders', () => {
                render(<div>Hello</div>);
                expect(screen.getByText('Hello')).toBeDefined();
              });
            });
        """)

        scanner = FrontendScanner(source_dir=str(tmp_path))
        violations = scanner.analyze_file(test_file)

        provider = [v for v in violations if v.violation_type == "missing_provider"]
        assert len(provider) == 1
        assert provider[0].severity == "medium"
        assert "test-utils" in provider[0].description.lower() or "render" in provider[0].description.lower()

    def test_no_violation_with_test_utils(self, tmp_path):
        """Importing render from test-utils should NOT be flagged."""
        test_file = _write_test(tmp_path, "Component.test.tsx", """\
            import { render, screen } from '../test-utils';

            describe('Component', () => {
              it('renders', () => {
                render(<div>Hello</div>);
                expect(screen.getByText('Hello')).toBeDefined();
              });
            });
        """)

        scanner = FrontendScanner(source_dir=str(tmp_path))
        violations = scanner.analyze_file(test_file)

        provider = [v for v in violations if v.violation_type == "missing_provider"]
        assert len(provider) == 0

    def test_no_violation_without_render(self, tmp_path):
        """A test that doesn't import render should NOT be flagged."""
        test_file = _write_test(tmp_path, "Utils.test.ts", """\
            import { describe, it, expect } from 'vitest';

            describe('Utils', () => {
              it('adds numbers', () => {
                expect(1 + 1).toBe(2);
              });
            });
        """)

        scanner = FrontendScanner(source_dir=str(tmp_path))
        violations = scanner.analyze_file(test_file)

        provider = [v for v in violations if v.violation_type == "missing_provider"]
        assert len(provider) == 0

    def test_detects_render_with_other_imports(self, tmp_path):
        """Direct render import is detected even with other imports."""
        test_file = _write_test(tmp_path, "Complex.test.tsx", """\
            import React from 'react';
            import { render, screen, fireEvent } from '@testing-library/react';
            import userEvent from '@testing-library/user-event';

            describe('Complex', () => {
              it('handles click', () => {
                render(<button>Click</button>);
              });
            });
        """)

        scanner = FrontendScanner(source_dir=str(tmp_path))
        violations = scanner.analyze_file(test_file)

        provider = [v for v in violations if v.violation_type == "missing_provider"]
        assert len(provider) == 1


# ---------------------------------------------------------------------------
# Stale import detection tests
# ---------------------------------------------------------------------------

class TestStaleImportDetection:
    """Tests for stale import detection."""

    def test_detects_stale_relative_import(self, tmp_path):
        """A relative import to a non-existent file should be flagged."""
        test_file = _write_test(tmp_path, "Component.test.tsx", """\
            import { render } from '../test-utils';
            import MyComponent from './MyComponent';

            describe('MyComponent', () => {
              it('renders', () => {
                render(<MyComponent />);
              });
            });
        """)

        scanner = FrontendScanner(source_dir=str(tmp_path))
        violations = scanner.analyze_file(test_file)

        stale = [v for v in violations if v.violation_type == "stale_import"]
        # ./MyComponent doesn't exist
        assert len(stale) >= 1
        assert any("MyComponent" in v.description for v in stale)

    def test_no_violation_for_existing_import(self, tmp_path):
        """A relative import to an existing file should NOT be flagged."""
        # Create the component file
        comp = tmp_path / "MyComponent.tsx"
        comp.write_text("export default function MyComponent() { return null; }", encoding="utf-8")

        test_file = _write_test(tmp_path, "MyComponent.test.tsx", """\
            import { render } from '../test-utils';
            import MyComponent from './MyComponent';

            describe('MyComponent', () => {
              it('renders', () => {
                render(<MyComponent />);
              });
            });
        """)

        scanner = FrontendScanner(source_dir=str(tmp_path))
        violations = scanner.analyze_file(test_file)

        stale = [v for v in violations if v.violation_type == "stale_import"]
        # Filter out only stale imports for MyComponent (not test-utils)
        my_comp_stale = [v for v in stale if "MyComponent" in v.description]
        assert len(my_comp_stale) == 0

    def test_detects_stale_alias_import(self, tmp_path):
        """An @/ alias import to a non-existent file should be flagged."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()

        test_file = _write_test(tmp_path, "Dashboard.test.tsx", """\
            import Dashboard from '@/pages/Dashboard';

            describe('Dashboard', () => {
              it('renders', () => {
                expect(true).toBe(true);
              });
            });
        """)

        scanner = FrontendScanner(source_dir=str(src_dir))
        violations = scanner.analyze_file(test_file)

        stale = [v for v in violations if v.violation_type == "stale_import"]
        assert len(stale) >= 1
        assert any("Dashboard" in v.description for v in stale)

    def test_no_violation_for_node_modules(self, tmp_path):
        """Imports from node_modules should NOT be checked."""
        test_file = _write_test(tmp_path, "Test.test.tsx", """\
            import React from 'react';
            import { render } from '@testing-library/react';
            import { vi } from 'vitest';
            import axios from 'axios';

            describe('Test', () => {
              it('works', () => {
                expect(true).toBe(true);
              });
            });
        """)

        scanner = FrontendScanner(source_dir=str(tmp_path))
        violations = scanner.analyze_file(test_file)

        stale = [v for v in violations if v.violation_type == "stale_import"]
        assert len(stale) == 0

    def test_handles_index_file_imports(self, tmp_path):
        """Importing a directory with an index file should NOT be flagged."""
        # Create directory with index.ts
        comp_dir = tmp_path / "components"
        comp_dir.mkdir()
        (comp_dir / "index.ts").write_text(
            "export { default } from './Button';", encoding="utf-8"
        )

        test_file = _write_test(tmp_path, "Components.test.tsx", """\
            import Components from './components';

            describe('Components', () => {
              it('exports', () => {
                expect(Components).toBeDefined();
              });
            });
        """)

        scanner = FrontendScanner(source_dir=str(tmp_path))
        violations = scanner.analyze_file(test_file)

        stale = [v for v in violations if v.violation_type == "stale_import"]
        comp_stale = [v for v in stale if "components" in v.description]
        assert len(comp_stale) == 0


# ---------------------------------------------------------------------------
# scan_directory tests
# ---------------------------------------------------------------------------

class TestScanDirectory:
    """Tests for scan_directory()."""

    def test_scans_all_test_files(self, tmp_path):
        """scan_directory finds and analyzes all test files."""
        _write_test(tmp_path, "A.test.tsx", """\
            import { render } from '@testing-library/react';
            describe('A', () => { it('works', () => {}); });
        """)
        _write_test(tmp_path, "B.test.ts", """\
            describe('B', () => { it('works', () => {}); });
        """)
        # Non-test file should be skipped
        (tmp_path / "utils.ts").write_text("export const x = 1;", encoding="utf-8")

        scanner = FrontendScanner(source_dir=str(tmp_path))
        report = scanner.scan_directory(str(tmp_path))

        assert isinstance(report, FrontendScanReport)
        assert report.files_scanned == 2
        assert len(report.test_files) == 2

    def test_empty_directory(self, tmp_path):
        """Empty directory produces empty report."""
        scanner = FrontendScanner(source_dir=str(tmp_path))
        report = scanner.scan_directory(str(tmp_path))

        assert report.files_scanned == 0
        assert report.violations == []

    def test_nonexistent_directory(self, tmp_path):
        """Nonexistent directory produces empty report."""
        scanner = FrontendScanner(source_dir=str(tmp_path))
        report = scanner.scan_directory("/nonexistent/dir")

        assert report.files_scanned == 0
        assert report.violations == []


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Edge case tests."""

    def test_nonexistent_file(self):
        """Nonexistent file returns empty list."""
        scanner = FrontendScanner()
        violations = scanner.analyze_file("/nonexistent/test.test.tsx")
        assert violations == []

    def test_non_test_file(self, tmp_path):
        """Non-test file returns empty list."""
        f = tmp_path / "Component.tsx"
        f.write_text("export default function Comp() {}", encoding="utf-8")

        scanner = FrontendScanner(source_dir=str(tmp_path))
        violations = scanner.analyze_file(str(f))
        assert violations == []

    def test_empty_test_file(self, tmp_path):
        """Empty test file returns empty list."""
        f = tmp_path / "Empty.test.tsx"
        f.write_text("", encoding="utf-8")

        scanner = FrontendScanner(source_dir=str(tmp_path))
        violations = scanner.analyze_file(str(f))
        assert violations == []

    def test_multiple_violation_types(self, tmp_path):
        """A single file can have multiple violation types."""
        test_file = _write_test(tmp_path, "Bad.test.tsx", """\
            import { render, screen } from '@testing-library/react';
            import BadComponent from './BadComponent';

            describe('Bad', () => {
              it('does everything wrong', async () => {
                render(<BadComponent />);
                const data = await fetch('/api/bad');
                expect(data).toBeDefined();
              });
            });
        """)

        scanner = FrontendScanner(source_dir=str(tmp_path))
        violations = scanner.analyze_file(test_file)

        types = {v.violation_type for v in violations}
        # Should have at least missing_msw and missing_provider
        assert "missing_msw" in types
        assert "missing_provider" in types
        # stale_import for ./BadComponent (doesn't exist)
        assert "stale_import" in types
