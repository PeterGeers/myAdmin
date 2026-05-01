"""

Dependency Mapper — source-to-test mapping

===========================================


Maps source files to their corresponding test files using a combination of

naming conventions, import analysis, and co-location patterns.  The resulting

:class:`DependencyMap` is consumed by the Scoped Test Runner to execute only

the tests affected by a set of changed files.


Mapping strategies (in priority order):


1. **Naming convention** — ``backend/src/banking_processor.py`` →

   ``backend/tests/unit/test_banking_processor.py``

2. **Import analysis** — parse test file AST for

   ``from banking_processor import …`` or ``import banking_processor``

3. **Service / route mapping** — subdirectory-aware variant of (1)

4. **Frontend co-location** — ``Component.tsx`` →

   ``Component.test.tsx`` or ``__tests__/Component.test.tsx``


Only stdlib + :mod:`import_analyzer` dependencies are used.


Requirements: 2.1, 2.2, 2.3, 2.4, 2.5
"""

from __future__ import annotations


import json

import logging
import os

from dataclasses import dataclass, field

from datetime import datetime, timezone

from pathlib import Path

from typing import Dict, List, Optional, Set


from .import_analyzer import (

    ImportInfo,

    analyze_file,

)


logger = logging.getLogger(__name__)


# Current schema version for the persisted JSON map.

_MAP_VERSION = "1.0.0"



# ---------------------------------------------------------------------------

# Data structures

# ---------------------------------------------------------------------------


@dataclass

class DependencyMap:

    """Source-to-test mapping for both backend and frontend.


    Attributes:

        backend:  ``{source_path: [test_paths]}`` for Python backend files.

        frontend: ``{source_path: [test_paths]}`` for TS/TSX frontend files.

        untested: Source files that have no corresponding test files.
    """


    backend: Dict[str, List[str]] = field(default_factory=dict)

    frontend: Dict[str, List[str]] = field(default_factory=dict)

    untested: List[str] = field(default_factory=list)



@dataclass
class SelectedTests:

    """Result of mapping changed files to the tests that should run.


    Attributes:

        backend_tests:     Backend test file paths to execute.

        frontend_tests:    Frontend test file paths to execute.

        untested_changes:  Changed files that have no test coverage.
    """


    backend_tests: List[str] = field(default_factory=list)

    frontend_tests: List[str] = field(default_factory=list)

    untested_changes: List[str] = field(default_factory=list)



# ---------------------------------------------------------------------------

# DependencyMapper

# ---------------------------------------------------------------------------


class DependencyMapper:

    """Maps source files to test files using imports and naming conventions."""


    def __init__(self) -> None:

        self._map = DependencyMap()


    # -- public API ---------------------------------------------------------


    def build_backend_map(

        self,

        source_dir: str = "backend/src",

        test_dir: str = "backend/tests",

    ) -> DependencyMap:

        """Build source-to-test mapping for backend.


        Scans *source_dir* for ``.py`` source files and *test_dir* for

        ``test_*.py`` test files, then matches them using naming conventions

        and import analysis.
        """

        source_files = self._collect_python_sources(source_dir)

        test_files = self._collect_python_tests(test_dir)


        # Build a reverse index: module_stem -> [test_paths]

        name_index = self._build_name_index(test_files)

        import_index = self._build_import_index(test_files)


        backend_map: Dict[str, List[str]] = {}


        for src in source_files:

            src_rel = self._to_relative(src)

            stem = Path(src).stem  # e.g. "banking_processor"

            matched_tests: Set[str] = set()


            # Strategy 1: naming convention  test_{stem}.py

            if stem in name_index:

                matched_tests.update(name_index[stem])


            # Strategy 2: import analysis

            if stem in import_index:

                matched_tests.update(import_index[stem])


            backend_map[src_rel] = sorted(matched_tests)


        self._map.backend = backend_map

        self._refresh_untested()
        return self._map


    def build_frontend_map(

        self,

        source_dir: str = "frontend/src",

        test_dir: str = "frontend/tests",

    ) -> DependencyMap:

        """Build source-to-test mapping for frontend.


        Scans *source_dir* for ``.tsx`` / ``.ts`` source files and matches

        them to co-located test files (``*.test.tsx``, ``*.test.ts``) and

        ``__tests__/`` directory patterns.  Also scans *test_dir* for
        standalone test files.
        """

        source_files = self._collect_frontend_sources(source_dir)

        colocated_tests = self._collect_frontend_tests_colocated(source_dir)

        standalone_tests = self._collect_frontend_tests_standalone(test_dir)

        all_tests = colocated_tests | standalone_tests


        frontend_map: Dict[str, List[str]] = {}


        for src in source_files:

            src_rel = self._to_relative(src)

            stem = Path(src).stem  # e.g. "BankingDashboard"

            src_dir_path = Path(src).parent

            matched_tests: Set[str] = set()


            # Strategy 4a: co-located  Component.test.tsx / .test.ts

            for ext in (".test.tsx", ".test.ts"):

                candidate = src_dir_path / f"{stem}{ext}"

                cand_rel = self._to_relative(str(candidate))

                if cand_rel in all_tests:

                    matched_tests.add(cand_rel)


            # Strategy 4b: __tests__/ directory

            tests_subdir = src_dir_path / "__tests__"

            for ext in (".test.tsx", ".test.ts"):

                candidate = tests_subdir / f"{stem}{ext}"

                cand_rel = self._to_relative(str(candidate))

                if cand_rel in all_tests:

                    matched_tests.add(cand_rel)


            # Strategy 4c: standalone tests in test_dir matching by name

            for t in standalone_tests:

                t_stem = Path(t).stem  # e.g. "BankingDashboard.test"

                # Remove .test suffix to get component name

                base = t_stem.rsplit(".test", 1)[0] if ".test" in t_stem else t_stem

                if base == stem:

                    matched_tests.add(t)


            frontend_map[src_rel] = sorted(matched_tests)


        self._map.frontend = frontend_map

        self._refresh_untested()
        return self._map


    def get_tests_for_files(

        self, changed_files: list[str]

    ) -> SelectedTests:

        """Given changed files, return which tests to run.


        Uses the combined backend + frontend maps built by previous calls

        to :meth:`build_backend_map` and :meth:`build_frontend_map`.
        """

        backend_tests: Set[str] = set()

        frontend_tests: Set[str] = set()

        untested_changes: List[str] = []


        for f in changed_files:

            rel = self._to_relative(f)

            found = False


            if rel in self._map.backend:

                tests = self._map.backend[rel]

                if tests:

                    backend_tests.update(tests)

                    found = True


            if rel in self._map.frontend:

                tests = self._map.frontend[rel]

                if tests:

                    frontend_tests.update(tests)

                    found = True


            if not found:

                untested_changes.append(rel)

        return SelectedTests(

            backend_tests=sorted(backend_tests),

            frontend_tests=sorted(frontend_tests),

            untested_changes=sorted(untested_changes),

        )


    def get_untested_sources(self) -> list[str]:

        """Return source files with no corresponding test files."""

        return list(self._map.untested)


    def save_map(self, output_path: str) -> None:

        """Persist mapping as JSON for Scoped Test Runner consumption."""

        data = {

            "version": _MAP_VERSION,

            "generated_at": datetime.now(timezone.utc).isoformat(),

            "backend": self._map.backend,

            "frontend": self._map.frontend,

            "untested": self._map.untested,

        }

        out = Path(output_path)

        out.parent.mkdir(parents=True, exist_ok=True)

        out.write_text(json.dumps(data, indent=2), encoding="utf-8")

        logger.info("Dependency map saved to %s", output_path)


    # -- private helpers: file collection -----------------------------------


    @staticmethod

    def _collect_python_sources(source_dir: str) -> List[str]:

        """Collect ``.py`` source files (excluding ``__init__.py``)."""

        results: List[str] = []

        root = Path(source_dir)

        if not root.is_dir():

            logger.warning("Source directory does not exist: %s", source_dir)
            return results

        for p in root.rglob("*.py"):

            if p.name == "__init__.py":
                continue

            results.append(str(p))

        return sorted(results)


    @staticmethod

    def _collect_python_tests(test_dir: str) -> List[str]:

        """Collect ``test_*.py`` files under *test_dir*."""

        results: List[str] = []

        root = Path(test_dir)

        if not root.is_dir():

            logger.warning("Test directory does not exist: %s", test_dir)
            return results

        for p in root.rglob("test_*.py"):

            results.append(str(p))

        return sorted(results)


    @staticmethod

    def _collect_frontend_sources(source_dir: str) -> List[str]:

        """Collect ``.tsx`` / ``.ts`` source files (excluding tests)."""

        results: List[str] = []

        root = Path(source_dir)

        if not root.is_dir():

            logger.warning("Source directory does not exist: %s", source_dir)
            return results

        for p in root.rglob("*"):

            if not p.is_file():
                continue

            if p.suffix not in (".tsx", ".ts"):
                continue

            # Skip test files and declaration files

            if ".test." in p.name or ".spec." in p.name:
                continue

            if p.name.endswith(".d.ts"):
                continue

            # Skip __tests__ directories

            if "__tests__" in p.parts:
                continue

            results.append(str(p))

        return sorted(results)


    @staticmethod

    def _collect_frontend_tests_colocated(source_dir: str) -> Set[str]:

        """Collect co-located frontend test files within *source_dir*."""

        results: Set[str] = set()

        root = Path(source_dir)

        if not root.is_dir():
            return results

        for p in root.rglob("*"):

            if not p.is_file():
                continue

            if ".test." in p.name or ".spec." in p.name:

                rel = DependencyMapper._to_relative(str(p))

                results.add(rel)

            elif "__tests__" in p.parts and p.suffix in (".tsx", ".ts"):

                rel = DependencyMapper._to_relative(str(p))

                results.add(rel)
        return results


    @staticmethod

    def _collect_frontend_tests_standalone(test_dir: str) -> Set[str]:

        """Collect standalone frontend test files under *test_dir*."""

        results: Set[str] = set()

        root = Path(test_dir)

        if not root.is_dir():
            return results

        for p in root.rglob("*"):

            if not p.is_file():
                continue

            if p.suffix in (".tsx", ".ts"):

                rel = DependencyMapper._to_relative(str(p))

                results.add(rel)
        return results


    # -- private helpers: indexing ------------------------------------------


    @staticmethod

    def _build_name_index(test_files: List[str]) -> Dict[str, List[str]]:

        """Build ``{module_stem: [test_rel_paths]}`` from naming convention.


        ``test_banking_processor.py`` → key ``banking_processor``.
        """

        index: Dict[str, List[str]] = {}

        for tf in test_files:

            rel = DependencyMapper._to_relative(tf)

            stem = Path(tf).stem  # e.g. "test_banking_processor"

            if stem.startswith("test_"):

                module_stem = stem[5:]  # strip "test_"

                index.setdefault(module_stem, []).append(rel)

        return index


    @staticmethod

    def _build_import_index(test_files: List[str]) -> Dict[str, List[str]]:

        """Build ``{module_stem: [test_rel_paths]}`` from import analysis.


        Parses each test file's imports and maps imported module stems back

        to source files.  Handles circular-import detection by tracking

        visited files.
        """

        index: Dict[str, List[str]] = {}

        visited: Set[str] = set()


        for tf in test_files:

            abs_path = str(Path(tf).resolve())

            if abs_path in visited:

                logger.warning(

                    "Circular reference detected for %s — skipping", tf

                )
                continue

            visited.add(abs_path)


            try:

                imports = analyze_file(tf)

            except Exception:

                logger.warning(

                    "Failed to analyze imports for %s — skipping", tf

                )
                continue


            rel = DependencyMapper._to_relative(tf)

            for imp in imports:

                module = imp.resolved_path or imp.module_name

                if not module:
                    continue

                # Extract the leaf module name

                leaf = module.rsplit(".", 1)[-1]

                # Skip stdlib / test-framework modules

                if leaf in _SKIP_MODULES:
                    continue

                index.setdefault(leaf, []).append(rel)


        # Deduplicate

        for key in index:

            index[key] = sorted(set(index[key]))


        return index


    # -- private helpers: utilities -----------------------------------------


    @staticmethod

    def _to_relative(path: str) -> str:

        """Normalise *path* to a forward-slash relative path from the project root."""

        p = Path(path)

        try:

            rel = p.resolve().relative_to(Path.cwd().resolve())

        except ValueError:

            # Already relative or outside cwd — just normalise separators

            rel = p

        return str(rel).replace("\\", "/")


    def _refresh_untested(self) -> None:

        """Recompute the ``untested`` list from current maps."""

        untested: List[str] = []

        for src, tests in self._map.backend.items():

            if not tests:

                untested.append(src)

        for src, tests in self._map.frontend.items():

            if not tests:

                untested.append(src)

        self._map.untested = sorted(untested)



# ---------------------------------------------------------------------------

# Modules to skip during import-based mapping (stdlib / test infra)

# ---------------------------------------------------------------------------


_SKIP_MODULES: Set[str] = {

    # stdlib

    "os", "sys", "json", "re", "ast", "io", "csv", "math", "copy",

    "time", "datetime", "pathlib", "logging", "typing", "collections",

    "functools", "itertools", "contextlib", "dataclasses", "enum",

    "abc", "textwrap", "tempfile", "shutil", "hashlib", "hmac",

    "base64", "uuid", "decimal", "fractions", "statistics",

    "unittest", "mock", "warnings", "traceback", "inspect",

    "importlib", "pkgutil", "subprocess", "threading", "multiprocessing",

    "socket", "http", "urllib", "email", "html", "xml",

    "sqlite3", "configparser", "argparse", "getpass", "glob",

    "fnmatch", "struct", "array", "queue", "heapq", "bisect",

    "pprint", "string", "operator", "secrets",

    # test frameworks

    "pytest", "hypothesis", "conftest",

    # common third-party that are not project source

    "flask", "flask_cors", "waitress", "boto3", "botocore",

    "jwt", "jose", "cryptography", "requests", "responses",

    "pandas", "numpy", "openpyxl", "pdfplumber", "pypdf",

    "flasgger", "marshmallow", "werkzeug", "jinja2",

    "mysql", "connector",

}

