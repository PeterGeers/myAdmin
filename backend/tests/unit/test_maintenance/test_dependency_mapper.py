"""Unit tests for dependency_mapper.py — source-to-test mapping.


Tests the DependencyMapper class with concrete examples covering naming

conventions, import analysis, frontend co-location, save/load, and edge cases.


Requirements: 2.1, 2.3, 2.4, 3.1, 3.5
"""


import json

import textwrap

from pathlib import Path


import pytest


from scripts.test_maintenance.dependency_mapper import (

    DependencyMap,

    DependencyMapper,
    SelectedTests,
)



# ---------------------------------------------------------------------------

# Helpers

# ---------------------------------------------------------------------------


def _write_file(base: Path, rel_path: str, content: str = "") -> Path:

    """Create a file at *base / rel_path* with optional content."""

    p = base / rel_path

    p.parent.mkdir(parents=True, exist_ok=True)

    p.write_text(textwrap.dedent(content), encoding="utf-8")

    return p



# ---------------------------------------------------------------------------

# 1. Naming convention matching

# ---------------------------------------------------------------------------


@pytest.mark.unit

class TestNamingConventionMapping:

    """Verify that ``banking_processor.py`` maps to ``test_banking_processor.py``."""


    def test_simple_naming_match(self, tmp_path: Path) -> None:

        """Source ``banking_processor.py`` maps to ``test_banking_processor.py``."""

        _write_file(tmp_path, "src/banking_processor.py", "# source\n")

        _write_file(tmp_path, "tests/test_banking_processor.py", "# test\n")


        mapper = DependencyMapper()

        dep_map = mapper.build_backend_map(

            source_dir=str(tmp_path / "src"),

            test_dir=str(tmp_path / "tests"),
        )


        # Find the source key (relative path)

        src_keys = list(dep_map.backend.keys())

        assert len(src_keys) == 1

        tests = dep_map.backend[src_keys[0]]

        assert len(tests) == 1

        assert "test_banking_processor" in tests[0]


    def test_multiple_sources_with_matching_tests(self, tmp_path: Path) -> None:

        """Multiple source files each map to their corresponding test."""

        _write_file(tmp_path, "src/banking_processor.py", "# source\n")

        _write_file(tmp_path, "src/year_end_service.py", "# source\n")

        _write_file(tmp_path, "tests/test_banking_processor.py", "# test\n")

        _write_file(tmp_path, "tests/test_year_end_service.py", "# test\n")


        mapper = DependencyMapper()

        dep_map = mapper.build_backend_map(

            source_dir=str(tmp_path / "src"),

            test_dir=str(tmp_path / "tests"),
        )


        assert len(dep_map.backend) == 2

        for src, tests in dep_map.backend.items():

            assert len(tests) >= 1, f"Source {src} should have at least one test"


    def test_test_in_subdirectory(self, tmp_path: Path) -> None:

        """Test file in a subdirectory still matches by naming convention."""

        _write_file(tmp_path, "src/audit_logger.py", "# source\n")

        _write_file(

            tmp_path, "tests/unit/test_audit_logger.py", "# test\n"
        )


        mapper = DependencyMapper()

        dep_map = mapper.build_backend_map(

            source_dir=str(tmp_path / "src"),

            test_dir=str(tmp_path / "tests"),
        )


        src_keys = list(dep_map.backend.keys())

        assert len(src_keys) == 1

        tests = dep_map.backend[src_keys[0]]

        assert len(tests) == 1

        assert "test_audit_logger" in tests[0]



# ---------------------------------------------------------------------------

# 2. Import analysis

# ---------------------------------------------------------------------------


@pytest.mark.unit

class TestImportAnalysisMapping:

    """Verify import-based mapping when naming convention doesn't match."""


    def test_import_based_mapping(self, tmp_path: Path) -> None:

        """Test file imports a source module — should be mapped via import analysis."""

        _write_file(

            tmp_path,

            "src/invoice_parser.py",

            """\

            class InvoiceParser:
                pass

            """,
        )

        # Test file name does NOT follow test_{module}.py convention

        _write_file(

            tmp_path,

            "tests/test_parsing_integration.py",

            """\

            from invoice_parser import InvoiceParser


            def test_parse():
                pass

            """,
        )


        mapper = DependencyMapper()

        dep_map = mapper.build_backend_map(

            source_dir=str(tmp_path / "src"),

            test_dir=str(tmp_path / "tests"),
        )


        src_keys = list(dep_map.backend.keys())

        assert len(src_keys) == 1

        tests = dep_map.backend[src_keys[0]]

        assert len(tests) >= 1

        assert any("test_parsing_integration" in t for t in tests)


    def test_plain_import_mapping(self, tmp_path: Path) -> None:

        """``import module_name`` style also triggers import-based mapping."""

        _write_file(tmp_path, "src/config_loader.py", "# source\n")

        _write_file(

            tmp_path,

            "tests/test_app_config.py",

            """\

            import config_loader


            def test_load():
                pass

            """,
        )


        mapper = DependencyMapper()

        dep_map = mapper.build_backend_map(

            source_dir=str(tmp_path / "src"),

            test_dir=str(tmp_path / "tests"),
        )


        src_keys = list(dep_map.backend.keys())

        assert len(src_keys) == 1

        tests = dep_map.backend[src_keys[0]]

        assert any("test_app_config" in t for t in tests)



# ---------------------------------------------------------------------------

# 3. Frontend co-location

# ---------------------------------------------------------------------------


@pytest.mark.unit

class TestFrontendColocation:

    """Verify frontend co-located test file mapping."""


    def test_colocated_test_tsx(self, tmp_path: Path) -> None:

        """``Component.tsx`` maps to ``Component.test.tsx`` in the same dir."""

        _write_file(

            tmp_path,

            "src/BankingDashboard.tsx",

            "export const BankingDashboard = () => null;\n",
        )

        _write_file(

            tmp_path,

            "src/BankingDashboard.test.tsx",

            "test('renders', () => {});\n",
        )


        mapper = DependencyMapper()

        dep_map = mapper.build_frontend_map(

            source_dir=str(tmp_path / "src"),

            test_dir=str(tmp_path / "standalone_tests"),  # empty
        )


        src_keys = list(dep_map.frontend.keys())

        assert len(src_keys) == 1

        tests = dep_map.frontend[src_keys[0]]

        assert len(tests) == 1

        assert "BankingDashboard.test.tsx" in tests[0]


    def test_colocated_test_ts(self, tmp_path: Path) -> None:

        """``utils.ts`` maps to ``utils.test.ts`` in the same dir."""

        _write_file(

            tmp_path, "src/formatCurrency.ts", "export function formatCurrency() {}\n"
        )

        _write_file(

            tmp_path, "src/formatCurrency.test.ts", "test('formats', () => {});\n"
        )


        mapper = DependencyMapper()

        dep_map = mapper.build_frontend_map(

            source_dir=str(tmp_path / "src"),

            test_dir=str(tmp_path / "tests"),
        )


        src_keys = list(dep_map.frontend.keys())

        assert len(src_keys) == 1

        tests = dep_map.frontend[src_keys[0]]

        assert len(tests) == 1

        assert "formatCurrency.test.ts" in tests[0]



# ---------------------------------------------------------------------------

# 4. Frontend __tests__ directory

# ---------------------------------------------------------------------------


@pytest.mark.unit

class TestFrontendTestsDirectory:

    """Verify ``__tests__/Component.test.tsx`` pattern."""


    def test_tests_subdirectory_mapping(self, tmp_path: Path) -> None:

        """Source maps to test in ``__tests__/`` subdirectory."""

        _write_file(

            tmp_path,

            "src/InvoiceTable.tsx",

            "export const InvoiceTable = () => null;\n",
        )

        _write_file(

            tmp_path,

            "src/__tests__/InvoiceTable.test.tsx",

            "test('renders table', () => {});\n",
        )


        mapper = DependencyMapper()

        dep_map = mapper.build_frontend_map(

            source_dir=str(tmp_path / "src"),

            test_dir=str(tmp_path / "tests"),
        )


        src_keys = list(dep_map.frontend.keys())

        assert len(src_keys) == 1

        tests = dep_map.frontend[src_keys[0]]

        assert len(tests) == 1

        assert "InvoiceTable.test.tsx" in tests[0]

        assert "__tests__" in tests[0]


    def test_both_colocated_and_tests_dir(self, tmp_path: Path) -> None:

        """Source with both co-located and __tests__ test files maps to both."""

        _write_file(

            tmp_path,

            "src/Widget.tsx",

            "export const Widget = () => null;\n",
        )

        _write_file(

            tmp_path,

            "src/Widget.test.tsx",

            "test('colocated', () => {});\n",
        )

        _write_file(

            tmp_path,

            "src/__tests__/Widget.test.tsx",

            "test('in __tests__', () => {});\n",
        )


        mapper = DependencyMapper()

        dep_map = mapper.build_frontend_map(

            source_dir=str(tmp_path / "src"),

            test_dir=str(tmp_path / "tests"),
        )


        src_keys = list(dep_map.frontend.keys())

        assert len(src_keys) == 1

        tests = dep_map.frontend[src_keys[0]]

        assert len(tests) == 2



# ---------------------------------------------------------------------------

# 5. Untested sources

# ---------------------------------------------------------------------------


@pytest.mark.unit

class TestUntestedSources:

    """Verify that source files with no tests appear in ``untested``."""


    def test_source_without_test_is_untested(self, tmp_path: Path) -> None:

        _write_file(tmp_path, "src/orphan_module.py", "# no test\n")


        mapper = DependencyMapper()

        dep_map = mapper.build_backend_map(

            source_dir=str(tmp_path / "src"),

            test_dir=str(tmp_path / "tests"),
        )


        assert len(dep_map.untested) == 1

        assert "orphan_module" in dep_map.untested[0]


    def test_mixed_tested_and_untested(self, tmp_path: Path) -> None:

        _write_file(tmp_path, "src/covered.py", "# has test\n")

        _write_file(tmp_path, "src/uncovered.py", "# no test\n")

        _write_file(tmp_path, "tests/test_covered.py", "# test\n")


        mapper = DependencyMapper()

        dep_map = mapper.build_backend_map(

            source_dir=str(tmp_path / "src"),

            test_dir=str(tmp_path / "tests"),
        )


        assert len(dep_map.untested) == 1

        assert "uncovered" in dep_map.untested[0]


    def test_frontend_untested(self, tmp_path: Path) -> None:

        _write_file(

            tmp_path, "src/Lonely.tsx", "export const Lonely = () => null;\n"
        )


        mapper = DependencyMapper()

        dep_map = mapper.build_frontend_map(

            source_dir=str(tmp_path / "src"),

            test_dir=str(tmp_path / "tests"),
        )


        assert len(dep_map.untested) == 1

        assert "Lonely" in dep_map.untested[0]



# ---------------------------------------------------------------------------

# 6. save_map() and load

# ---------------------------------------------------------------------------


@pytest.mark.unit

class TestSaveAndLoadMap:

    """Verify that saving and loading the JSON map preserves data."""


    def test_save_and_reload(self, tmp_path: Path) -> None:

        _write_file(tmp_path, "src/banking_processor.py", "# source\n")

        _write_file(tmp_path, "tests/test_banking_processor.py", "# test\n")


        mapper = DependencyMapper()

        mapper.build_backend_map(

            source_dir=str(tmp_path / "src"),

            test_dir=str(tmp_path / "tests"),
        )


        out_path = str(tmp_path / "output" / "dep-map.json")

        mapper.save_map(out_path)


        # Reload and verify

        data = json.loads(Path(out_path).read_text(encoding="utf-8"))

        assert data["version"] == "1.0.0"

        assert "generated_at" in data

        assert isinstance(data["backend"], dict)

        assert isinstance(data["frontend"], dict)

        assert isinstance(data["untested"], list)


        # Backend map should have our source

        assert len(data["backend"]) == 1

        src_key = list(data["backend"].keys())[0]

        assert "banking_processor" in src_key

        assert len(data["backend"][src_key]) == 1


    def test_save_creates_parent_directories(self, tmp_path: Path) -> None:

        mapper = DependencyMapper()

        mapper.build_backend_map(

            source_dir=str(tmp_path / "empty_src"),

            test_dir=str(tmp_path / "empty_tests"),
        )


        deep_path = str(tmp_path / "a" / "b" / "c" / "map.json")

        mapper.save_map(deep_path)

        assert Path(deep_path).exists()



# ---------------------------------------------------------------------------

# 7. get_tests_for_files()

# ---------------------------------------------------------------------------


@pytest.mark.unit

class TestGetTestsForFiles:

    """Verify that changed files correctly resolve to test files."""


    def test_changed_file_resolves_to_tests(self, tmp_path: Path) -> None:

        _write_file(tmp_path, "src/banking_processor.py", "# source\n")

        _write_file(tmp_path, "src/year_end_service.py", "# source\n")

        _write_file(tmp_path, "tests/test_banking_processor.py", "# test\n")

        _write_file(tmp_path, "tests/test_year_end_service.py", "# test\n")


        mapper = DependencyMapper()

        mapper.build_backend_map(

            source_dir=str(tmp_path / "src"),

            test_dir=str(tmp_path / "tests"),
        )


        # Get the actual relative key for banking_processor

        src_key = None

        for k in mapper._map.backend:

            if "banking_processor" in k:

                src_key = k

                break

        assert src_key is not None


        selection = mapper.get_tests_for_files([src_key])

        assert len(selection.backend_tests) >= 1

        assert any("test_banking_processor" in t for t in selection.backend_tests)


    def test_unmapped_file_in_untested_changes(self, tmp_path: Path) -> None:

        mapper = DependencyMapper()

        mapper.build_backend_map(

            source_dir=str(tmp_path / "src"),

            test_dir=str(tmp_path / "tests"),
        )


        selection = mapper.get_tests_for_files(["nonexistent/file.py"])

        assert len(selection.untested_changes) == 1


    def test_mixed_mapped_and_unmapped(self, tmp_path: Path) -> None:

        _write_file(tmp_path, "src/known.py", "# source\n")

        _write_file(tmp_path, "tests/test_known.py", "# test\n")


        mapper = DependencyMapper()

        mapper.build_backend_map(

            source_dir=str(tmp_path / "src"),

            test_dir=str(tmp_path / "tests"),
        )


        src_key = list(mapper._map.backend.keys())[0]

        selection = mapper.get_tests_for_files([src_key, "unknown/file.py"])

        assert len(selection.backend_tests) >= 1

        assert "unknown/file.py" in selection.untested_changes



# ---------------------------------------------------------------------------

# 8. get_untested_sources()

# ---------------------------------------------------------------------------


@pytest.mark.unit

class TestGetUntestedSources:

    """Verify get_untested_sources() returns the correct list."""


    def test_returns_untested_list(self, tmp_path: Path) -> None:

        _write_file(tmp_path, "src/tested.py", "# has test\n")

        _write_file(tmp_path, "src/untested.py", "# no test\n")

        _write_file(tmp_path, "tests/test_tested.py", "# test\n")


        mapper = DependencyMapper()

        mapper.build_backend_map(

            source_dir=str(tmp_path / "src"),

            test_dir=str(tmp_path / "tests"),
        )


        untested = mapper.get_untested_sources()

        assert len(untested) == 1

        assert "untested" in untested[0]


    def test_all_tested_returns_empty(self, tmp_path: Path) -> None:

        _write_file(tmp_path, "src/module_a.py", "# source\n")

        _write_file(tmp_path, "tests/test_module_a.py", "# test\n")


        mapper = DependencyMapper()

        mapper.build_backend_map(

            source_dir=str(tmp_path / "src"),

            test_dir=str(tmp_path / "tests"),
        )


        assert mapper.get_untested_sources() == []



# ---------------------------------------------------------------------------

# 9. Edge cases

# ---------------------------------------------------------------------------


@pytest.mark.unit

class TestEdgeCases:

    """Edge cases: empty dirs, orphan tests, __init__.py exclusion."""


    def test_empty_source_directory(self, tmp_path: Path) -> None:

        (tmp_path / "src").mkdir()

        (tmp_path / "tests").mkdir()


        mapper = DependencyMapper()

        dep_map = mapper.build_backend_map(

            source_dir=str(tmp_path / "src"),

            test_dir=str(tmp_path / "tests"),
        )


        assert dep_map.backend == {}

        assert dep_map.untested == []


    def test_init_py_excluded_from_sources(self, tmp_path: Path) -> None:

        _write_file(tmp_path, "src/__init__.py", "")

        _write_file(tmp_path, "src/real_module.py", "# source\n")


        mapper = DependencyMapper()

        dep_map = mapper.build_backend_map(

            source_dir=str(tmp_path / "src"),

            test_dir=str(tmp_path / "tests"),
        )


        # Only real_module should appear, not __init__

        assert len(dep_map.backend) == 1

        key = list(dep_map.backend.keys())[0]

        assert "real_module" in key


    def test_test_file_with_no_matching_source(self, tmp_path: Path) -> None:

        """Orphan test files don't cause errors."""

        (tmp_path / "src").mkdir()

        _write_file(tmp_path, "tests/test_orphan.py", "# orphan test\n")


        mapper = DependencyMapper()

        dep_map = mapper.build_backend_map(

            source_dir=str(tmp_path / "src"),

            test_dir=str(tmp_path / "tests"),
        )


        assert dep_map.backend == {}


    def test_frontend_spec_files_excluded(self, tmp_path: Path) -> None:

        """Files with ``.spec.`` in the name are excluded from sources."""

        _write_file(

            tmp_path, "src/App.tsx", "export const App = () => null;\n"
        )

        _write_file(

            tmp_path, "src/App.spec.tsx", "test('spec', () => {});\n"
        )


        mapper = DependencyMapper()

        dep_map = mapper.build_frontend_map(

            source_dir=str(tmp_path / "src"),

            test_dir=str(tmp_path / "tests"),
        )


        # Only App.tsx should be a source, not App.spec.tsx

        assert len(dep_map.frontend) == 1

        key = list(dep_map.frontend.keys())[0]

        assert "App.tsx" in key

        assert ".spec." not in key


    def test_declaration_files_excluded(self, tmp_path: Path) -> None:

        """TypeScript ``.d.ts`` files are excluded from sources."""

        _write_file(tmp_path, "src/types.d.ts", "declare module 'x';\n")

        _write_file(tmp_path, "src/App.tsx", "export const App = () => null;\n")


        mapper = DependencyMapper()

        dep_map = mapper.build_frontend_map(

            source_dir=str(tmp_path / "src"),

            test_dir=str(tmp_path / "tests"),
        )


        assert len(dep_map.frontend) == 1

        key = list(dep_map.frontend.keys())[0]

        assert ".d.ts" not in key



# ---------------------------------------------------------------------------

# 10. Missing directories

# ---------------------------------------------------------------------------


@pytest.mark.unit

class TestMissingDirectories:

    """Non-existent source/test directories should return empty maps."""


    def test_missing_source_dir(self, tmp_path: Path) -> None:

        mapper = DependencyMapper()

        dep_map = mapper.build_backend_map(

            source_dir=str(tmp_path / "nonexistent_src"),

            test_dir=str(tmp_path / "nonexistent_tests"),
        )


        assert dep_map.backend == {}

        assert dep_map.untested == []


    def test_missing_frontend_dirs(self, tmp_path: Path) -> None:

        mapper = DependencyMapper()

        dep_map = mapper.build_frontend_map(

            source_dir=str(tmp_path / "no_src"),

            test_dir=str(tmp_path / "no_tests"),
        )


        assert dep_map.frontend == {}

        assert dep_map.untested == []


    def test_source_exists_but_test_dir_missing(self, tmp_path: Path) -> None:

        _write_file(tmp_path, "src/module.py", "# source\n")


        mapper = DependencyMapper()

        dep_map = mapper.build_backend_map(

            source_dir=str(tmp_path / "src"),

            test_dir=str(tmp_path / "nonexistent_tests"),
        )


        # Source should be mapped but with no tests → untested

        assert len(dep_map.backend) == 1

        assert len(dep_map.untested) == 1

