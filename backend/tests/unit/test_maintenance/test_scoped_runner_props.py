"""

Property-based tests for the Scoped Test Runner.


Uses Hypothesis to verify that scoped test selection correctly maps

changed files to their corresponding tests via the dependency map,

and that unmapped changes appear in untested_changes.
"""

import json
import uuid


import pytest

from typing import Dict, List, Set, Tuple


from hypothesis import given, strategies as st, settings, HealthCheck


from scripts.test_maintenance.scoped_runner import (

    ScopedTestRunner,
    RunResult,
)

from scripts.test_maintenance.dependency_mapper import DependencyMap



# ---------------------------------------------------------------------------

# Hypothesis strategies

# ---------------------------------------------------------------------------


# Valid Python-style path segments (lowercase identifiers).

_path_segment = st.from_regex(r"[a-z][a-z0-9_]{1,15}", fullmatch=True)



@st.composite

def st_backend_source_path(draw):

    """Generate a backend source file path like ``backend/src/module.py``."""

    module = draw(_path_segment)

    subdir = draw(st.sampled_from(["", "routes/", "services/", "auth/"]))

    return f"backend/src/{subdir}{module}.py"



@st.composite

def st_backend_test_path(draw):

    """Generate a backend test file path like ``backend/tests/unit/test_module.py``."""

    module = draw(_path_segment)

    category = draw(st.sampled_from(["unit", "integration", "api"]))

    return f"backend/tests/{category}/test_{module}.py"



@st.composite

def st_frontend_source_path(draw):

    """Generate a frontend source file path like ``frontend/src/components/Widget.tsx``."""

    name = draw(st.from_regex(r"[A-Z][a-z]{2,10}", fullmatch=True))

    subdir = draw(st.sampled_from(["components/", "pages/", "hooks/", "services/"]))

    ext = draw(st.sampled_from([".tsx", ".ts"]))

    return f"frontend/src/{subdir}{name}{ext}"



@st.composite

def st_frontend_test_path(draw):

    """Generate a frontend test file path like ``frontend/src/components/Widget.test.tsx``."""

    name = draw(st.from_regex(r"[A-Z][a-z]{2,10}", fullmatch=True))

    subdir = draw(st.sampled_from(["components/", "pages/", "hooks/", "services/"]))

    return f"frontend/src/{subdir}{name}.test.tsx"



@st.composite

def st_dependency_map(draw):

    """Generate a random dependency map with backend and frontend mappings.


    Returns ``(backend_map, frontend_map, all_mapped_sources)`` where:

    - backend_map: ``{source_path: [test_paths]}``

    - frontend_map: ``{source_path: [test_paths]}``

    - all_mapped_sources: set of all source paths that have at least one test
    """

    # Generate backend mappings: source -> [tests]

    num_backend = draw(st.integers(min_value=0, max_value=6))

    backend_map: Dict[str, List[str]] = {}

    for _ in range(num_backend):

        src = draw(st_backend_source_path())

        if src in backend_map:
            continue

        num_tests = draw(st.integers(min_value=1, max_value=3))

        tests = []

        for _ in range(num_tests):

            t = draw(st_backend_test_path())

            if t not in tests:

                tests.append(t)

        backend_map[src] = tests


    # Generate frontend mappings: source -> [tests]

    num_frontend = draw(st.integers(min_value=0, max_value=6))

    frontend_map: Dict[str, List[str]] = {}

    for _ in range(num_frontend):

        src = draw(st_frontend_source_path())

        if src in frontend_map:
            continue

        num_tests = draw(st.integers(min_value=1, max_value=3))

        tests = []

        for _ in range(num_tests):

            t = draw(st_frontend_test_path())

            if t not in tests:

                tests.append(t)

        frontend_map[src] = tests


    return backend_map, frontend_map



@st.composite

def st_changed_files(draw, backend_map, frontend_map):

    """Generate a set of changed files — some mapped, some unmapped.


    Returns ``(changed_files, mapped_backend, mapped_frontend, unmapped)``

    where:

    - changed_files: the full list of changed file paths

    - mapped_backend: subset of changed files that exist in backend_map

    - mapped_frontend: subset of changed files that exist in frontend_map

    - unmapped: subset of changed files not in either map
    """

    all_backend_sources = list(backend_map.keys())

    all_frontend_sources = list(frontend_map.keys())


    # Pick some mapped backend sources

    if all_backend_sources:

        mapped_be = draw(

            st.lists(

                st.sampled_from(all_backend_sources),

                min_size=0,

                max_size=min(len(all_backend_sources), 4),

                unique=True,
            )
        )

    else:

        mapped_be = []


    # Pick some mapped frontend sources

    if all_frontend_sources:

        mapped_fe = draw(

            st.lists(

                st.sampled_from(all_frontend_sources),

                min_size=0,

                max_size=min(len(all_frontend_sources), 4),

                unique=True,
            )
        )

    else:

        mapped_fe = []


    # Generate some unmapped files (not in either map)

    all_mapped = set(all_backend_sources) | set(all_frontend_sources)

    num_unmapped = draw(st.integers(min_value=0, max_value=4))

    unmapped = []

    for _ in range(num_unmapped):

        # Generate a path that is guaranteed not to be in the maps

        unmapped_path = draw(

            st.sampled_from([

                st_backend_source_path(),

                st_frontend_source_path(),

            ]).flatmap(lambda s: s)
        )

        if unmapped_path not in all_mapped and unmapped_path not in unmapped:

            unmapped.append(unmapped_path)


    changed = mapped_be + mapped_fe + unmapped

    return changed, set(mapped_be), set(mapped_fe), unmapped



# ---------------------------------------------------------------------------

# Helpers

# ---------------------------------------------------------------------------


def write_dependency_map_json(

    path: str,

    backend_map: Dict[str, List[str]],

    frontend_map: Dict[str, List[str]],

) -> None:

    """Write a dependency map JSON file at *path*."""

    data = {

        "version": "1.0.0",

        "generated_at": "2025-01-01T00:00:00+00:00",

        "backend": backend_map,

        "frontend": frontend_map,

        "untested": [],

    }

    import pathlib

    p = pathlib.Path(path)

    p.parent.mkdir(parents=True, exist_ok=True)

    p.write_text(json.dumps(data, indent=2), encoding="utf-8")



# ---------------------------------------------------------------------------

# Feature: test-maintenance-framework, Property 7: Scoped test selection correctness

# ---------------------------------------------------------------------------


@pytest.mark.unit

class TestScopedTestSelectionCorrectness:

    """Property 7: For any dependency map and changed files, selected tests

    equal the union of mapped tests, and unmapped changes appear in

    untested_changes.
    """


    @given(data=st.data())

    @settings(

        max_examples=100,

        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )

    def test_scoped_test_selection_correctness(self, data, tmp_path):
        """

        # Feature: test-maintenance-framework, Property 7: Scoped test selection correctness


        For any dependency map and any subset of changed source files:

        1. The selected backend tests equal the union of all test files

           mapped to the changed backend source files.

        2. The selected frontend files correspond to changed frontend

           source files that have mappings.

        3. Changed files not present in the dependency map appear in

           untested_changes.


        **Validates: Requirements 3.1, 3.3, 6.1**
        """

        # Step 1: Generate a random dependency map

        backend_map, frontend_map = data.draw(st_dependency_map())


        # Step 2: Generate changed files (some mapped, some not)

        changed, mapped_be, mapped_fe, unmapped = data.draw(

            st_changed_files(backend_map, frontend_map)
        )


        # Skip trivial case where nothing changed

        if not changed:
            return


        # Step 3: Write the dependency map to a temp JSON file

        work_dir = tmp_path / uuid.uuid4().hex

        work_dir.mkdir(parents=True, exist_ok=True)

        map_path = str(work_dir / "dep-map.json")

        write_dependency_map_json(map_path, backend_map, frontend_map)


        # Step 4: Create a ScopedTestRunner with that map

        runner = ScopedTestRunner(dependency_map_path=map_path)


        # Step 5: Call _select_tests directly to test selection logic

        # (avoids subprocess execution)

        normalised = [runner._normalise(f) for f in changed]

        selected_be, selected_fe, untested = runner._select_tests(normalised)


        # Step 6: Compute expected results


        # Expected backend tests: union of all test files for changed

        # backend sources that are in the map

        expected_backend_tests: Set[str] = set()

        for f in changed:

            norm_f = runner._normalise(f)

            if norm_f in backend_map:

                tests = backend_map[norm_f]

                if tests:

                    expected_backend_tests.update(tests)


        # Expected frontend files: changed frontend sources that are in

        # the map and have non-empty test lists

        expected_frontend_files: Set[str] = set()

        for f in changed:

            norm_f = runner._normalise(f)

            if norm_f in frontend_map:

                tests = frontend_map[norm_f]

                if tests:

                    expected_frontend_files.add(norm_f)


        # Expected untested: changed files not found in either map

        # (or found but with empty test lists)

        expected_untested: Set[str] = set()

        for f in changed:

            norm_f = runner._normalise(f)

            found = False

            if norm_f in backend_map and backend_map[norm_f]:

                found = True

            if norm_f in frontend_map and frontend_map[norm_f]:

                found = True

            if not found:

                expected_untested.add(norm_f)


        # Step 7: Verify properties


        # Property 7a: Selected backend tests == expected union

        assert selected_be == expected_backend_tests, (

            f"Backend test selection mismatch.\n"

            f"  Selected:  {sorted(selected_be)}\n"

            f"  Expected:  {sorted(expected_backend_tests)}\n"

            f"  Changed:   {changed}\n"

            f"  Map keys:  {list(backend_map.keys())}"
        )


        # Property 7b: Selected frontend files == expected set

        assert selected_fe == expected_frontend_files, (

            f"Frontend file selection mismatch.\n"

            f"  Selected:  {sorted(selected_fe)}\n"

            f"  Expected:  {sorted(expected_frontend_files)}\n"

            f"  Changed:   {changed}\n"

            f"  Map keys:  {list(frontend_map.keys())}"
        )


        # Property 7c: Untested changes == expected unmapped files

        assert set(untested) == expected_untested, (

            f"Untested changes mismatch.\n"

            f"  Actual:    {sorted(untested)}\n"

            f"  Expected:  {sorted(expected_untested)}\n"

            f"  Changed:   {changed}"
        )


        # Property 7d: Every changed file is accounted for — it either

        # contributed tests or appears in untested (no file is lost)

        accounted = set()

        for f in changed:

            norm_f = runner._normalise(f)

            if norm_f in backend_map and backend_map[norm_f]:

                accounted.add(norm_f)

            if norm_f in frontend_map and frontend_map[norm_f]:

                accounted.add(norm_f)

        accounted |= set(untested)


        all_normalised = {runner._normalise(f) for f in changed}

        assert accounted == all_normalised, (

            f"Not all changed files are accounted for.\n"

            f"  Missing: {all_normalised - accounted}"
        )

