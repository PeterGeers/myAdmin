"""

Scoped Test Runner — change-based test selection
==================================================


Runs only the tests affected by a set of changed files, using the

dependency map produced by :mod:`dependency_mapper`.  Falls back to

running all tests in the changed file's directory when the map is

unavailable.


Backend tests are executed via ``pytest``; frontend tests via

``npx vitest --related``.  Only stdlib + :mod:`dependency_mapper`
dependencies are used.


Requirements: 3.1, 3.2, 3.3, 3.4, 3.5
"""

from __future__ import annotations

import argparse

import json
import logging
import re

import subprocess

import sys
import time

from dataclasses import dataclass, field

from pathlib import Path

from typing import List, Optional, Set


from .dependency_mapper import DependencyMap


logger = logging.getLogger(__name__)


# Default path for the persisted dependency map JSON.

_DEFAULT_MAP_PATH = "backend/tests/reports/dependency-map.json"


# Timeout for individual test runner processes (seconds).

_TEST_TIMEOUT = 600



# ---------------------------------------------------------------------------

# Data structures

# ---------------------------------------------------------------------------


@dataclass
class RunResult:
    """Result of a scoped (or full) test run."""

    backend_result: Optional[subprocess.CompletedProcess] = None
    frontend_result: Optional[subprocess.CompletedProcess] = None
    tests_executed: int = 0
    tests_passed: int = 0
    tests_failed: int = 0
    untested_changes: List[str] = field(default_factory=list)
    duration_seconds: float = 0.0


# ---------------------------------------------------------------------------
# ScopedTestRunner
# ---------------------------------------------------------------------------

class ScopedTestRunner:

    """Executes tests scoped to changed files.


    Uses the dependency map JSON produced by

    :class:`~backend.scripts.test_maintenance.dependency_mapper.DependencyMapper`

    to resolve which test files correspond to a set of changed source files.

    When the map is missing or corrupted, falls back to running all tests in

    the changed file's directory.
    """


    def __init__(self, dependency_map_path: str = None) -> None:

        self._map_path = dependency_map_path or _DEFAULT_MAP_PATH

        self._dep_map: Optional[DependencyMap] = None

        self._map_loaded = False

        self._load_dependency_map()


    # -- public API ---------------------------------------------------------


    def run(

        self,

        changed_files: list[str],

        full: bool = False,

    ) -> RunResult:

        """Run tests for changed files.


        Args:

            changed_files: List of changed file paths (relative to project root).

            full: If ``True``, run the complete test suite instead.


        Returns:

            A :class:`TestRunResult` summarising the execution.
        """

        start = time.monotonic()


        if full:

            return self._run_full_suite(start)


        # Normalise paths to forward-slash relative form.

        normalised = [self._normalise(f) for f in changed_files]


        # Resolve which tests to run.

        backend_tests, frontend_files, untested = self._select_tests(normalised)

        result = RunResult(untested_changes=untested)


        if backend_tests:

            result.backend_result = self._run_backend_tests(sorted(backend_tests))


        if frontend_files:

            result.frontend_result = self._run_frontend_tests(sorted(frontend_files))


        # Aggregate counts from subprocess output.

        self._aggregate_counts(result)

        result.duration_seconds = round(time.monotonic() - start, 2)
        return result


    # -- subprocess wrappers ------------------------------------------------


    def _run_backend_tests(

        self, test_files: list[str]

    ) -> subprocess.CompletedProcess:

        """Execute pytest with specific test files."""

        cmd = [sys.executable, "-m", "pytest", "-x", "-q", "--tb=short"] + test_files

        logger.info("Running backend tests: %s", " ".join(cmd))

        try:

            return subprocess.run(

                cmd,

                capture_output=True,

                text=True,

                timeout=_TEST_TIMEOUT,

            )

        except FileNotFoundError:

            logger.error(

                "pytest not found. Install with: pip install pytest"

            )

            return subprocess.CompletedProcess(

                args=cmd, returncode=2,

                stdout="", stderr="pytest not found. Install with: pip install pytest",

            )

        except subprocess.TimeoutExpired:

            logger.error("Backend test execution timed out after %ds", _TEST_TIMEOUT)

            return subprocess.CompletedProcess(

                args=cmd, returncode=2,

                stdout="", stderr=f"Test execution timed out after {_TEST_TIMEOUT}s",

            )


    def _run_frontend_tests(

        self, changed_files: list[str]

    ) -> subprocess.CompletedProcess:

        """Execute vitest --related with changed source files."""

        cmd = ["npx", "vitest", "--related", "--run"] + changed_files

        logger.info("Running frontend tests: %s", " ".join(cmd))

        try:

            return subprocess.run(

                cmd,

                capture_output=True,

                text=True,

                timeout=_TEST_TIMEOUT,

                cwd="frontend",

            )

        except FileNotFoundError:

            logger.error(

                "vitest not found. Install with: npm install -D vitest"

            )

            return subprocess.CompletedProcess(

                args=cmd, returncode=2,

                stdout="",

                stderr="vitest not found. Install with: npm install -D vitest",

            )

        except subprocess.TimeoutExpired:

            logger.error("Frontend test execution timed out after %ds", _TEST_TIMEOUT)

            return subprocess.CompletedProcess(

                args=cmd, returncode=2,

                stdout="",

                stderr=f"Test execution timed out after {_TEST_TIMEOUT}s",

            )


    # -- private helpers: test selection ------------------------------------


    def _select_tests(

        self, changed_files: list[str]

    ) -> tuple[Set[str], Set[str], List[str]]:

        """Resolve changed files to backend test files and frontend source files.


        Returns:

            ``(backend_test_files, frontend_source_files, untested_changes)``
        """

        backend_tests: Set[str] = set()

        frontend_files: Set[str] = set()

        untested: List[str] = []


        for f in changed_files:

            found = False


            if self._map_loaded and self._dep_map is not None:

                # Look up in the dependency map.

                if f in self._dep_map.backend:

                    tests = self._dep_map.backend[f]

                    if tests:

                        backend_tests.update(tests)

                        found = True


                if f in self._dep_map.frontend:

                    tests = self._dep_map.frontend[f]

                    if tests:

                        # For frontend, vitest --related wants the *source* files.

                        frontend_files.add(f)

                        found = True

            else:

                # Fallback: run all tests in the changed file's directory.

                fallback = self._fallback_tests(f)

                if fallback:

                    backend_tests.update(fallback)

                    found = True


            if not found:

                untested.append(f)


        return backend_tests, frontend_files, sorted(untested)


    def _fallback_tests(self, changed_file: str) -> List[str]:

        """Fallback: find test files in the same directory as *changed_file*.


        Used when the dependency map is missing or corrupted (Req 3.5).
        """

        parent = Path(changed_file).parent

        if not parent.is_dir():

            return []


        tests: List[str] = []

        for p in parent.iterdir():

            if p.is_file() and p.name.startswith("test_") and p.suffix == ".py":

                tests.append(self._normalise(str(p)))
        return tests


    # -- private helpers: full suite ----------------------------------------


    def _run_full_suite(self, start: float) -> RunResult:

        """Run the complete backend and frontend test suites."""
        result = RunResult()


        # Backend: pytest on the whole test directory.

        backend_cmd = [sys.executable, "-m", "pytest", "-q", "--tb=short"]

        try:

            result.backend_result = subprocess.run(

                backend_cmd,

                capture_output=True,

                text=True,

                timeout=_TEST_TIMEOUT,

            )

        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:

            logger.error("Full backend suite error: %s", exc)

            result.backend_result = subprocess.CompletedProcess(

                args=backend_cmd, returncode=2,

                stdout="", stderr=str(exc),

            )


        # Frontend: vitest --run (full).

        frontend_cmd = ["npx", "vitest", "--run"]

        try:

            result.frontend_result = subprocess.run(

                frontend_cmd,

                capture_output=True,

                text=True,

                timeout=_TEST_TIMEOUT,

                cwd="frontend",

            )

        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:

            logger.error("Full frontend suite error: %s", exc)

            result.frontend_result = subprocess.CompletedProcess(

                args=frontend_cmd, returncode=2,

                stdout="", stderr=str(exc),

            )


        self._aggregate_counts(result)

        result.duration_seconds = round(time.monotonic() - start, 2)
        return result


    # -- private helpers: dependency map loading ----------------------------


    def _load_dependency_map(self) -> None:

        """Load the dependency map JSON, or set fallback mode on failure."""

        path = Path(self._map_path)

        if not path.is_file():

            logger.warning(

                "Dependency map not found at %s — using directory fallback.",

                self._map_path,

            )
            return


        try:

            data = json.loads(path.read_text(encoding="utf-8"))

            self._dep_map = DependencyMap(

                backend=data.get("backend", {}),

                frontend=data.get("frontend", {}),

                untested=data.get("untested", []),

            )

            self._map_loaded = True

            logger.info("Loaded dependency map (version %s).", data.get("version"))

        except (json.JSONDecodeError, KeyError, TypeError) as exc:

            logger.warning(

                "Failed to parse dependency map at %s (%s) — using directory fallback.",

                self._map_path,

                exc,

            )


    # -- private helpers: result aggregation --------------------------------


    @staticmethod

    def _aggregate_counts(result: RunResult) -> None:

        """Parse pytest / vitest output to populate aggregate counts."""

        executed = 0

        passed = 0

        failed = 0


        if result.backend_result and result.backend_result.stdout:

            be = _parse_pytest_summary(result.backend_result.stdout)

            executed += be[0]

            passed += be[1]

            failed += be[2]


        if result.frontend_result and result.frontend_result.stdout:

            fe = _parse_vitest_summary(result.frontend_result.stdout)

            executed += fe[0]

            passed += fe[1]

            failed += fe[2]


        result.tests_executed = executed
        result.tests_passed = passed
        result.tests_failed = failed


    # -- private helpers: utilities -----------------------------------------


    @staticmethod

    def _normalise(path: str) -> str:

        """Normalise *path* to forward-slash relative form."""

        return str(Path(path)).replace("\\", "/")



# ---------------------------------------------------------------------------

# Output parsers

# ---------------------------------------------------------------------------


def _parse_pytest_summary(output: str) -> tuple[int, int, int]:

    """Extract (executed, passed, failed) from pytest ``-q`` output.


    Typical last line: ``5 passed, 2 failed in 1.23s``
    """

    executed = 0

    passed = 0

    failed = 0


    # Match patterns like "5 passed", "2 failed", "1 error"

    for match in re.finditer(r"(\d+)\s+(passed|failed|error)", output):

        count = int(match.group(1))

        kind = match.group(2)

        executed += count

        if kind == "passed":

            passed += count

        elif kind in ("failed", "error"):

            failed += count


    return executed, passed, failed



def _parse_vitest_summary(output: str) -> tuple[int, int, int]:

    """Extract (executed, passed, failed) from vitest output.


    Typical lines:

        ``Tests  5 passed | 1 failed (6)``

        ``Tests  3 passed (3)``
    """

    executed = 0

    passed = 0

    failed = 0


    pass_match = re.search(r"(\d+)\s+passed", output)

    fail_match = re.search(r"(\d+)\s+failed", output)

    total_match = re.search(r"\((\d+)\)", output)


    if pass_match:

        passed = int(pass_match.group(1))

    if fail_match:

        failed = int(fail_match.group(1))

    if total_match:

        executed = int(total_match.group(1))

    else:

        executed = passed + failed


    return executed, passed, failed



# ---------------------------------------------------------------------------

# Git helpers

# ---------------------------------------------------------------------------


def _get_git_changed_files() -> list[str]:

    """Return files changed relative to HEAD using ``git diff``."""

    try:

        proc = subprocess.run(

            ["git", "diff", "--name-only", "HEAD"],

            capture_output=True,

            text=True,

            timeout=30,

        )

        if proc.returncode != 0:

            logger.error("git diff failed: %s", proc.stderr.strip())

            return []

        return [

            line.strip()

            for line in proc.stdout.splitlines()

            if line.strip()

        ]

    except FileNotFoundError:

        logger.error("git is not installed or not on PATH.")

        return []

    except subprocess.TimeoutExpired:

        logger.error("git diff timed out.")

        return []



# ---------------------------------------------------------------------------

# CLI

# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:

    """Build the argument parser for the CLI."""

    parser = argparse.ArgumentParser(

        prog="scoped_runner",

        description="Run tests scoped to changed files.",

    )

    parser.add_argument(

        "files",

        nargs="*",

        help="Changed file paths (relative to project root).",

    )

    parser.add_argument(

        "--full",

        action="store_true",

        default=False,

        help="Run the complete test suite instead of scoped tests.",

    )

    parser.add_argument(

        "--git-diff",

        action="store_true",

        default=False,

        dest="git_diff",

        help="Auto-detect changed files from git diff HEAD.",

    )

    parser.add_argument(

        "--map",

        default=None,

        dest="map_path",

        help="Path to the dependency map JSON file.",

    )
    return parser



def main(argv: list[str] | None = None) -> int:

    """CLI entry point.


    Returns:

        Exit code: 0 = all tests passed, 1 = failures, 2 = runner error.
    """

    logging.basicConfig(

        level=logging.INFO,

        format="%(levelname)s: %(message)s",

    )


    parser = _build_parser()

    args = parser.parse_args(argv)


    # Determine changed files.

    changed_files: list[str] = []

    if args.full:

        # --full ignores file arguments.
        pass

    elif args.git_diff:

        changed_files = _get_git_changed_files()

        if not changed_files:

            print("No changed files detected from git diff.")

            return 0

        print(f"Detected {len(changed_files)} changed file(s) from git.")

    elif args.files:

        changed_files = args.files

    else:

        parser.print_help()

        return 2


    runner = ScopedTestRunner(dependency_map_path=args.map_path)

    result = runner.run(changed_files=changed_files, full=args.full)


    # Print summary.

    print()

    print("=" * 60)

    print("Scoped Test Runner — Summary")

    print("=" * 60)

    print(f"  Tests executed : {result.tests_executed}")

    print(f"  Passed         : {result.tests_passed}")

    print(f"  Failed         : {result.tests_failed}")

    print(f"  Duration       : {result.duration_seconds}s")


    if result.untested_changes:

        print()

        print("  Untested changes (no test coverage):")

        for f in result.untested_changes:

            print(f"    - {f}")


    print("=" * 60)


    if result.tests_failed > 0:

        return 1

    return 0



if __name__ == "__main__":

    sys.exit(main())

