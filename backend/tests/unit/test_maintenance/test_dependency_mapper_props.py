"""
Property-based tests for the Dependency Mapper.

Uses Hypothesis to verify universal properties of source-to-test mapping.
"""
import uuid

import pytest
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Tuple

from hypothesis import given, strategies as st, settings, HealthCheck

from scripts.test_maintenance.dependency_mapper import (
    DependencyMapper,
    _SKIP_MODULES,
)


# ---------------------------------------------------------------------------
# Helpers — file layout data structure and creation
# ---------------------------------------------------------------------------

@dataclass
class FileLayout:
    """Describes a generated file layout for property testing."""

    source_files: List[str] = field(default_factory=list)
    test_files: List[str] = field(default_factory=list)


def create_file_layout(root: Path, layout: FileLayout) -> None:
    """Materialise *layout* as real files under *root*."""
    src_dir = root / "src"
    test_dir = root / "tests"
    src_dir.mkdir(parents=True, exist_ok=True)
    test_dir.mkdir(parents=True, exist_ok=True)

    for name in layout.source_files:
        fp = src_dir / name
        fp.write_text(f"# source: {name}\n", encoding="utf-8")

    for name in layout.test_files:
        fp = test_dir / name
        fp.write_text(f"# test: {name}\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

# Valid Python identifiers that are not dunder names and not too long.
_python_identifier = (
    st.from_regex(r"[a-z][a-z0-9_]{0,20}", fullmatch=True)
    .filter(lambda s: s.isidentifier())
    .filter(lambda s: not s.startswith("__"))
    .filter(lambda s: s != "test")  # avoid bare "test" collisions
)


@st.composite
def st_file_layout(draw):
    """Generate a random :class:`FileLayout`.

    * Source files are valid ``<identifier>.py`` names (never ``__init__.py``).
    * Test files are a mix of ``test_<source>.py`` (matching some sources)
      and ``test_<random>.py`` (not matching any source).
    """
    # Draw unique source stems
    source_stems = draw(
        st.lists(
            _python_identifier,
            min_size=0,
            max_size=8,
            unique=True,
        )
    )
    source_files = [f"{stem}.py" for stem in source_stems]

    # Some test files that match sources (test_{stem}.py)
    if source_stems:
        matching_stems = draw(
            st.lists(
                st.sampled_from(source_stems),
                min_size=0,
                max_size=len(source_stems),
                unique=True,
            )
        )
    else:
        matching_stems = []

    # Some test files that do NOT match any source
    extra_test_stems = draw(
        st.lists(
            _python_identifier.filter(lambda s: s not in source_stems),
            min_size=0,
            max_size=4,
            unique=True,
        )
    )

    test_files = [f"test_{stem}.py" for stem in matching_stems + extra_test_stems]

    return FileLayout(source_files=source_files, test_files=test_files)


# ---------------------------------------------------------------------------
# Feature: test-maintenance-framework, Property 4: Dependency mapping completeness
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestDependencyMappingCompleteness:
    """Property 4: For any file layout, every source file appears in either
    the mapped set (has ≥1 test) or the untested set (has 0 tests),
    never both, never neither.
    """

    @given(file_layout=st_file_layout())
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_dependency_mapping_completeness(self, file_layout, tmp_path):
        """
        # Feature: test-maintenance-framework, Property 4: Dependency mapping completeness

        Every source file ends up in backend.keys().  Sources with at least
        one test are NOT in untested; sources with zero tests ARE in untested.

        **Validates: Requirements 2.1, 2.2, 6.5**
        """
        # Each Hypothesis example needs its own directory because tmp_path
        # is shared across all examples within a single test invocation.
        work_dir = tmp_path / uuid.uuid4().hex
        work_dir.mkdir()

        create_file_layout(work_dir, file_layout)

        mapper = DependencyMapper()
        dep_map = mapper.build_backend_map(
            source_dir=str(work_dir / "src"),
            test_dir=str(work_dir / "tests"),
        )

        # Build the expected set of source paths using the mapper's own
        # _to_relative helper so we compare apples to apples.
        src_dir = work_dir / "src"
        expected_sources = set()
        for name in file_layout.source_files:
            rel = DependencyMapper._to_relative(str(src_dir / name))
            expected_sources.add(rel)

        mapped_sources = set(dep_map.backend.keys())
        untested_sources = set(dep_map.untested)

        # 1. Every source file from the layout appears in backend.keys()
        assert mapped_sources == expected_sources, (
            f"Mapped keys do not match expected sources.\n"
            f"  Missing from map: {expected_sources - mapped_sources}\n"
            f"  Extra in map:     {mapped_sources - expected_sources}"
        )

        # 2. untested is a subset of mapped sources
        assert untested_sources <= mapped_sources, (
            f"Untested contains entries not in backend.keys():\n"
            f"  {untested_sources - mapped_sources}"
        )

        # 3. Sources with non-empty test lists are NOT in untested
        tested_sources = {src for src, tests in dep_map.backend.items() if tests}
        assert tested_sources & untested_sources == set(), (
            f"Sources appear in both tested and untested:\n"
            f"  {tested_sources & untested_sources}"
        )

        # 4. Sources with empty test lists ARE in untested
        empty_sources = {src for src, tests in dep_map.backend.items() if not tests}
        assert empty_sources == untested_sources, (
            f"Sources with empty test lists do not match untested list.\n"
            f"  Empty but not untested: {empty_sources - untested_sources}\n"
            f"  Untested but not empty: {untested_sources - empty_sources}"
        )

        # 5. The union of tested + untested covers all sources (completeness)
        assert tested_sources | untested_sources == mapped_sources, (
            f"Tested ∪ Untested does not cover all mapped sources.\n"
            f"  Missing: {mapped_sources - (tested_sources | untested_sources)}"
        )


# ---------------------------------------------------------------------------
# Helpers — import-based layout for Property 5
# ---------------------------------------------------------------------------

# Strategy for source module names that won't be filtered by _SKIP_MODULES.
# We use a prefix "mod_" to guarantee no collision with stdlib/third-party names.
_source_module_stem = (
    st.from_regex(r"mod_[a-z][a-z0-9]{0,12}", fullmatch=True)
    .filter(lambda s: s.isidentifier())
    .filter(lambda s: s not in _SKIP_MODULES)
)


@st.composite
def st_import_style(draw, module_name: str):
    """Pick a random import statement style for *module_name*.

    Returns a valid Python line that imports from the given module.
    """
    style = draw(st.sampled_from(["from_import", "plain_import"]))
    if style == "from_import":
        return f"from {module_name} import SomeClass\n"
    else:
        return f"import {module_name}\n"


@st.composite
def st_import_layout(draw):
    """Generate a layout where test files import source modules.

    * Source files are ``mod_<id>.py`` (never collide with _SKIP_MODULES).
    * Each source gets exactly one test file whose name does NOT follow
      ``test_<module>.py`` convention — this isolates import-based mapping
      from naming-convention mapping.
    * Each test file contains a valid import of its corresponding source module.

    Returns ``(source_stems, test_entries)`` where each test entry is
    ``(test_filename, file_content, imported_stem)``.
    """
    source_stems = draw(
        st.lists(_source_module_stem, min_size=1, max_size=6, unique=True)
    )

    test_entries = []
    for idx, stem in enumerate(source_stems):
        # Name the test file so it does NOT match test_{stem}.py.
        # Use a counter-based suffix to keep names unique.
        test_filename = f"test_check_{idx}_{uuid.uuid4().hex[:6]}.py"

        # Pick an import style
        import_line = draw(st_import_style(stem))
        content = f"# auto-generated test\n{import_line}\ndef test_placeholder():\n    pass\n"
        test_entries.append((test_filename, content, stem))

    return source_stems, test_entries


# ---------------------------------------------------------------------------
# Feature: test-maintenance-framework, Property 5: Import-based dependency mapping
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestImportBasedDependencyMapping:
    """Property 5: For any test file that contains an import referencing a
    source module, the DependencyMapper includes that test in the mapping
    for the corresponding source file.
    """

    @given(data=st_import_layout())
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_import_based_dependency_mapping(self, data, tmp_path):
        """
        # Feature: test-maintenance-framework, Property 5: Import-based dependency mapping

        For any test file with ``from {source_module} import ...`` or
        ``import {source_module}``, the mapper includes that test in the
        mapping for the corresponding source file.

        **Validates: Requirements 2.3**
        """
        source_stems, test_entries = data

        work_dir = tmp_path / uuid.uuid4().hex
        src_dir = work_dir / "src"
        test_dir = work_dir / "tests"
        src_dir.mkdir(parents=True, exist_ok=True)
        test_dir.mkdir(parents=True, exist_ok=True)

        # Create source files
        for stem in source_stems:
            (src_dir / f"{stem}.py").write_text(
                f"# source module: {stem}\nclass SomeClass:\n    pass\n",
                encoding="utf-8",
            )

        # Create test files with import statements
        for test_filename, content, _ in test_entries:
            (test_dir / test_filename).write_text(content, encoding="utf-8")

        # Build the map
        mapper = DependencyMapper()
        dep_map = mapper.build_backend_map(
            source_dir=str(src_dir),
            test_dir=str(test_dir),
        )

        # Verify: for each test entry, the test file appears in the mapping
        # for the source it imports.
        for test_filename, _, imported_stem in test_entries:
            src_rel = DependencyMapper._to_relative(
                str(src_dir / f"{imported_stem}.py")
            )
            test_rel = DependencyMapper._to_relative(
                str(test_dir / test_filename)
            )

            assert src_rel in dep_map.backend, (
                f"Source '{src_rel}' not found in backend map keys.\n"
                f"  Available keys: {list(dep_map.backend.keys())}"
            )

            mapped_tests = dep_map.backend[src_rel]
            assert test_rel in mapped_tests, (
                f"Test '{test_rel}' not found in mapping for source '{src_rel}'.\n"
                f"  Test imports module '{imported_stem}' but mapper did not detect it.\n"
                f"  Mapped tests: {mapped_tests}"
            )


# ---------------------------------------------------------------------------
# Helpers — frontend co-location layout for Property 6
# ---------------------------------------------------------------------------

# PascalCase component names: start with uppercase, then lowercase letters.
_pascal_case_name = (
    st.from_regex(r"[A-Z][a-z]{2,10}", fullmatch=True)
)


@st.composite
def st_frontend_colocation_layout(draw):
    """Generate a frontend file layout with co-located tests.

    Each component gets:
    - A source file: ``<Name>.tsx`` or ``<Name>.ts``
    - A co-located test using one of two patterns:
        a) Same directory: ``<Name>.test.tsx``
        b) ``__tests__/`` subdirectory: ``__tests__/<Name>.test.tsx``

    Returns ``(components)`` where each component is a tuple of
    ``(name, source_ext, test_pattern)`` with test_pattern being
    ``"same_dir"`` or ``"__tests__"``.
    """
    names = draw(
        st.lists(
            _pascal_case_name,
            min_size=1,
            max_size=8,
            unique=True,
        )
    )

    components: List[Tuple[str, str, str]] = []
    for name in names:
        source_ext = draw(st.sampled_from([".tsx", ".ts"]))
        test_pattern = draw(st.sampled_from(["same_dir", "__tests__"]))
        components.append((name, source_ext, test_pattern))

    return components


# ---------------------------------------------------------------------------
# Feature: test-maintenance-framework, Property 6: Frontend co-location mapping
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestFrontendColocationMapping:
    """Property 6: For any frontend source file with a co-located test file
    (either Component.test.tsx in the same directory or
    __tests__/Component.test.tsx), the DependencyMapper maps the source
    file to its co-located test file.
    """

    @given(components=st_frontend_colocation_layout())
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_frontend_colocation_mapping(self, components, tmp_path):
        """
        # Feature: test-maintenance-framework, Property 6: Frontend co-location mapping

        For any frontend source file (.tsx or .ts) with a co-located test
        file, build_frontend_map() maps the source to its test.

        **Validates: Requirements 2.4**
        """
        work_dir = tmp_path / uuid.uuid4().hex
        src_dir = work_dir / "src"
        src_dir.mkdir(parents=True, exist_ok=True)

        # Track expected mappings: source_rel -> test_rel
        expected_mappings: dict[str, str] = {}

        for name, source_ext, test_pattern in components:
            # Create source file
            source_file = src_dir / f"{name}{source_ext}"
            source_file.write_text(
                f"// Component: {name}\nexport const {name} = () => null;\n",
                encoding="utf-8",
            )

            # Create co-located test file
            if test_pattern == "same_dir":
                test_file = src_dir / f"{name}.test.tsx"
            else:  # __tests__
                tests_subdir = src_dir / "__tests__"
                tests_subdir.mkdir(parents=True, exist_ok=True)
                test_file = tests_subdir / f"{name}.test.tsx"

            test_file.write_text(
                f"// Test for {name}\nimport {{ {name} }} from '../{name}';\n"
                f"test('{name} renders', () => {{}});\n",
                encoding="utf-8",
            )

            src_rel = DependencyMapper._to_relative(str(source_file))
            test_rel = DependencyMapper._to_relative(str(test_file))
            expected_mappings[src_rel] = test_rel

        # Build the frontend map
        mapper = DependencyMapper()
        dep_map = mapper.build_frontend_map(
            source_dir=str(src_dir),
            test_dir=str(work_dir / "tests"),  # empty, no standalone tests
        )

        # Verify: each source file maps to its co-located test
        for src_rel, test_rel in expected_mappings.items():
            assert src_rel in dep_map.frontend, (
                f"Source '{src_rel}' not found in frontend map keys.\n"
                f"  Available keys: {list(dep_map.frontend.keys())}"
            )

            mapped_tests = dep_map.frontend[src_rel]
            assert test_rel in mapped_tests, (
                f"Test '{test_rel}' not found in mapping for source '{src_rel}'.\n"
                f"  Expected co-located test but mapper did not detect it.\n"
                f"  Mapped tests: {mapped_tests}"
            )
