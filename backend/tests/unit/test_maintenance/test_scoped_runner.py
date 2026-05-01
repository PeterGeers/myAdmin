"""Unit tests for scoped_runner.py — change-based test selection.


Tests the ScopedTestRunner class, CLI argument parsing, output parsers,

dependency map loading, and fallback behavior.


Requirements: 3.1, 3.5
"""


import json

import subprocess

import textwrap

from pathlib import Path

from unittest.mock import MagicMock, patch


import pytest


from scripts.test_maintenance.scoped_runner import (

    ScopedTestRunner,
    RunResult,

    _build_parser,

    _get_git_changed_files,

    _parse_pytest_summary,

    _parse_vitest_summary,

    main,

)



# ---------------------------------------------------------------------------

# Helpers

# ---------------------------------------------------------------------------


def _write_dep_map(path: Path, backend: dict = None, frontend: dict = None) -> str:

    """Write a dependency map JSON and return its path as a string."""

    data = {

        "version": "1.0.0",

        "generated_at": "2025-01-01T00:00:00+00:00",

        "backend": backend or {},

        "frontend": frontend or {},

        "untested": [],

    }

    path.parent.mkdir(parents=True, exist_ok=True)

    path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    return str(path)



# ---------------------------------------------------------------------------

# 1. CLI argument parsing

# ---------------------------------------------------------------------------


@pytest.mark.unit

class TestBuildParser:

    """Test ``_build_parser()`` with various argument combinations."""


    def test_full_flag(self) -> None:

        parser = _build_parser()

        args = parser.parse_args(["--full"])

        assert args.full is True

        assert args.git_diff is False

        assert args.files == []


    def test_git_diff_flag(self) -> None:

        parser = _build_parser()

        args = parser.parse_args(["--git-diff"])

        assert args.git_diff is True

        assert args.full is False


    def test_custom_map_path(self) -> None:

        parser = _build_parser()

        args = parser.parse_args(["--map", "/custom/path.json", "file.py"])

        assert args.map_path == "/custom/path.json"

        assert args.files == ["file.py"]


    def test_positional_files(self) -> None:

        parser = _build_parser()

        args = parser.parse_args(["src/a.py", "src/b.py"])

        assert args.files == ["src/a.py", "src/b.py"]

        assert args.full is False

        assert args.git_diff is False


    def test_no_arguments(self) -> None:

        parser = _build_parser()

        args = parser.parse_args([])

        assert args.files == []

        assert args.full is False

        assert args.git_diff is False

        assert args.map_path is None


    def test_combined_flags(self) -> None:

        parser = _build_parser()

        args = parser.parse_args(["--full", "--map", "my-map.json"])

        assert args.full is True

        assert args.map_path == "my-map.json"


    def test_git_diff_with_map(self) -> None:

        parser = _build_parser()

        args = parser.parse_args(["--git-diff", "--map", "custom.json"])

        assert args.git_diff is True

        assert args.map_path == "custom.json"



# ---------------------------------------------------------------------------

# 2. Dependency map loading

# ---------------------------------------------------------------------------


@pytest.mark.unit

class TestDependencyMapLoading:

    """Test loading valid JSON, missing file, and corrupted JSON."""


    def test_load_valid_map(self, tmp_path: Path) -> None:

        map_path = _write_dep_map(

            tmp_path / "dep-map.json",

            backend={"backend/src/mod.py": ["backend/tests/unit/test_mod.py"]},

        )


        runner = ScopedTestRunner(dependency_map_path=map_path)

        assert runner._map_loaded is True

        assert runner._dep_map is not None

        assert "backend/src/mod.py" in runner._dep_map.backend


    def test_load_missing_file(self, tmp_path: Path) -> None:

        runner = ScopedTestRunner(

            dependency_map_path=str(tmp_path / "nonexistent.json")

        )

        assert runner._map_loaded is False

        assert runner._dep_map is None


    def test_load_corrupted_json(self, tmp_path: Path) -> None:

        bad_file = tmp_path / "bad.json"

        bad_file.parent.mkdir(parents=True, exist_ok=True)

        bad_file.write_text("{invalid json!!!", encoding="utf-8")


        runner = ScopedTestRunner(dependency_map_path=str(bad_file))

        assert runner._map_loaded is False

        assert runner._dep_map is None


    def test_load_empty_file(self, tmp_path: Path) -> None:

        empty_file = tmp_path / "empty.json"

        empty_file.parent.mkdir(parents=True, exist_ok=True)

        empty_file.write_text("", encoding="utf-8")


        runner = ScopedTestRunner(dependency_map_path=str(empty_file))

        assert runner._map_loaded is False



# ---------------------------------------------------------------------------

# 3. Fallback behavior

# ---------------------------------------------------------------------------


@pytest.mark.unit

class TestFallbackBehavior:

    """When dependency map is missing, fallback finds tests in the same dir."""


    def test_fallback_finds_tests_in_same_directory(self, tmp_path: Path) -> None:

        """Without a map, tests in the same directory as the changed file are found."""

        # Create a source file and a test file in the same directory

        src_dir = tmp_path / "backend" / "src"

        src_dir.mkdir(parents=True)

        (src_dir / "module.py").write_text("# source\n", encoding="utf-8")

        (src_dir / "test_module.py").write_text("# test\n", encoding="utf-8")


        runner = ScopedTestRunner(

            dependency_map_path=str(tmp_path / "nonexistent.json")

        )

        assert runner._map_loaded is False


        fallback = runner._fallback_tests(str(src_dir / "module.py"))

        assert len(fallback) == 1

        assert "test_module" in fallback[0]


    def test_fallback_no_tests_in_directory(self, tmp_path: Path) -> None:

        src_dir = tmp_path / "backend" / "src"

        src_dir.mkdir(parents=True)

        (src_dir / "lonely.py").write_text("# no tests here\n", encoding="utf-8")


        runner = ScopedTestRunner(

            dependency_map_path=str(tmp_path / "nonexistent.json")

        )


        fallback = runner._fallback_tests(str(src_dir / "lonely.py"))

        assert fallback == []


    def test_fallback_nonexistent_directory(self, tmp_path: Path) -> None:

        runner = ScopedTestRunner(

            dependency_map_path=str(tmp_path / "nonexistent.json")

        )


        fallback = runner._fallback_tests("nonexistent/dir/file.py")

        assert fallback == []



# ---------------------------------------------------------------------------

# 4. Test selection with map

# ---------------------------------------------------------------------------


@pytest.mark.unit

class TestSelectTestsWithMap:

    """Create a dependency map JSON, load it, verify _select_tests()."""


    def test_backend_selection(self, tmp_path: Path) -> None:

        map_path = _write_dep_map(

            tmp_path / "dep-map.json",

            backend={

                "backend/src/banking.py": [

                    "backend/tests/unit/test_banking.py",

                    "backend/tests/integration/test_banking_int.py",

                ],

                "backend/src/config.py": [

                    "backend/tests/unit/test_config.py",

                ],

            },

        )


        runner = ScopedTestRunner(dependency_map_path=map_path)

        be_tests, fe_files, untested = runner._select_tests(

            ["backend/src/banking.py"]

        )


        assert len(be_tests) == 2

        assert "backend/tests/unit/test_banking.py" in be_tests

        assert "backend/tests/integration/test_banking_int.py" in be_tests

        assert len(fe_files) == 0

        assert len(untested) == 0


    def test_frontend_selection(self, tmp_path: Path) -> None:

        map_path = _write_dep_map(

            tmp_path / "dep-map.json",

            frontend={

                "frontend/src/components/Widget.tsx": [

                    "frontend/src/components/Widget.test.tsx",

                ],

            },

        )


        runner = ScopedTestRunner(dependency_map_path=map_path)

        be_tests, fe_files, untested = runner._select_tests(

            ["frontend/src/components/Widget.tsx"]

        )


        assert len(be_tests) == 0

        assert "frontend/src/components/Widget.tsx" in fe_files

        assert len(untested) == 0


    def test_unmapped_file_goes_to_untested(self, tmp_path: Path) -> None:

        map_path = _write_dep_map(tmp_path / "dep-map.json")


        runner = ScopedTestRunner(dependency_map_path=map_path)

        be_tests, fe_files, untested = runner._select_tests(

            ["backend/src/unknown.py"]

        )


        assert len(be_tests) == 0

        assert len(fe_files) == 0

        assert "backend/src/unknown.py" in untested


    def test_mixed_backend_frontend_and_unmapped(self, tmp_path: Path) -> None:

        map_path = _write_dep_map(

            tmp_path / "dep-map.json",

            backend={"backend/src/a.py": ["backend/tests/unit/test_a.py"]},

            frontend={"frontend/src/B.tsx": ["frontend/src/B.test.tsx"]},

        )


        runner = ScopedTestRunner(dependency_map_path=map_path)

        be_tests, fe_files, untested = runner._select_tests(

            ["backend/src/a.py", "frontend/src/B.tsx", "unknown/file.py"]

        )


        assert "backend/tests/unit/test_a.py" in be_tests

        assert "frontend/src/B.tsx" in fe_files

        assert "unknown/file.py" in untested



# ---------------------------------------------------------------------------

# 5. pytest output parsing

# ---------------------------------------------------------------------------


@pytest.mark.unit

class TestParsePytestSummary:

    """Test ``_parse_pytest_summary()`` with various output formats."""


    def test_passed_only(self) -> None:

        output = "5 passed in 1.23s"

        executed, passed, failed = _parse_pytest_summary(output)

        assert executed == 5

        assert passed == 5

        assert failed == 0


    def test_passed_and_failed(self) -> None:

        output = "3 passed, 2 failed in 2.50s"

        executed, passed, failed = _parse_pytest_summary(output)

        assert executed == 5

        assert passed == 3

        assert failed == 2


    def test_with_errors(self) -> None:

        output = "10 passed, 1 failed, 2 error in 5.00s"

        executed, passed, failed = _parse_pytest_summary(output)

        assert executed == 13

        assert passed == 10

        assert failed == 3  # 1 failed + 2 error


    def test_empty_output(self) -> None:

        executed, passed, failed = _parse_pytest_summary("")

        assert executed == 0

        assert passed == 0

        assert failed == 0


    def test_no_summary_line(self) -> None:

        output = "collecting ... \nsome random output\n"

        executed, passed, failed = _parse_pytest_summary(output)

        assert executed == 0


    def test_multiline_output(self) -> None:

        output = (

            "FAILED test_a.py::test_one\n"

            "FAILED test_b.py::test_two\n"

            "2 failed, 8 passed in 3.14s\n"

        )

        executed, passed, failed = _parse_pytest_summary(output)

        assert passed == 8

        assert failed == 2



# ---------------------------------------------------------------------------

# 6. vitest output parsing

# ---------------------------------------------------------------------------


@pytest.mark.unit

class TestParseVitestSummary:

    """Test ``_parse_vitest_summary()`` with various output formats."""


    def test_all_passed(self) -> None:

        output = "Tests  5 passed (5)"

        executed, passed, failed = _parse_vitest_summary(output)

        assert executed == 5

        assert passed == 5

        assert failed == 0


    def test_passed_and_failed(self) -> None:

        output = "Tests  3 passed | 2 failed (5)"

        executed, passed, failed = _parse_vitest_summary(output)

        assert executed == 5

        assert passed == 3

        assert failed == 2


    def test_empty_output(self) -> None:

        executed, passed, failed = _parse_vitest_summary("")

        assert executed == 0

        assert passed == 0

        assert failed == 0


    def test_no_total_in_parens(self) -> None:

        """When total is missing, executed = passed + failed."""

        output = "Tests  4 passed | 1 failed"

        executed, passed, failed = _parse_vitest_summary(output)

        assert executed == 5

        assert passed == 4

        assert failed == 1


    def test_only_failed(self) -> None:

        output = "Tests  3 failed (3)"

        executed, passed, failed = _parse_vitest_summary(output)

        assert executed == 3

        assert passed == 0

        assert failed == 3



# ---------------------------------------------------------------------------

# 7. main() function — CLI entry point

# ---------------------------------------------------------------------------


@pytest.mark.unit

class TestMainFunction:

    """Test the CLI entry point with mocked subprocess."""


    @patch("scripts.test_maintenance.scoped_runner.subprocess.run")

    def test_main_with_files(self, mock_run: MagicMock, tmp_path: Path) -> None:

        """Providing file arguments runs scoped tests."""

        map_path = _write_dep_map(

            tmp_path / "dep-map.json",

            backend={"backend/src/mod.py": ["backend/tests/unit/test_mod.py"]},

        )


        mock_run.return_value = subprocess.CompletedProcess(

            args=[], returncode=0,

            stdout="1 passed in 0.5s", stderr="",

        )


        exit_code = main(["--map", map_path, "backend/src/mod.py"])

        assert exit_code == 0

        assert mock_run.called


    @patch("scripts.test_maintenance.scoped_runner.subprocess.run")

    def test_main_full_flag(self, mock_run: MagicMock, tmp_path: Path) -> None:

        """``--full`` runs the complete test suite."""

        map_path = _write_dep_map(tmp_path / "dep-map.json")


        mock_run.return_value = subprocess.CompletedProcess(

            args=[], returncode=0,

            stdout="10 passed in 5.0s", stderr="",

        )


        exit_code = main(["--full", "--map", map_path])

        assert exit_code == 0


    def test_main_no_args_returns_2(self) -> None:

        """No arguments prints help and returns exit code 2."""

        exit_code = main([])

        assert exit_code == 2


    @patch("scripts.test_maintenance.scoped_runner._get_git_changed_files")

    def test_main_git_diff_no_changes(self, mock_git: MagicMock) -> None:

        """``--git-diff`` with no changes returns 0."""

        mock_git.return_value = []

        exit_code = main(["--git-diff"])

        assert exit_code == 0


    @patch("scripts.test_maintenance.scoped_runner.subprocess.run")

    def test_main_with_failures_returns_1(

        self, mock_run: MagicMock, tmp_path: Path

    ) -> None:

        """When tests fail, main returns exit code 1."""

        map_path = _write_dep_map(

            tmp_path / "dep-map.json",

            backend={"backend/src/mod.py": ["backend/tests/unit/test_mod.py"]},

        )


        mock_run.return_value = subprocess.CompletedProcess(

            args=[], returncode=1,

            stdout="1 failed, 2 passed in 1.0s", stderr="",

        )


        exit_code = main(["--map", map_path, "backend/src/mod.py"])

        assert exit_code == 1



# ---------------------------------------------------------------------------

# 8. Edge cases

# ---------------------------------------------------------------------------


@pytest.mark.unit

class TestEdgeCases:

    """Edge cases: empty changed files, all unmapped, mixed changes."""


    def test_empty_changed_files(self, tmp_path: Path) -> None:

        map_path = _write_dep_map(tmp_path / "dep-map.json")

        runner = ScopedTestRunner(dependency_map_path=map_path)


        be_tests, fe_files, untested = runner._select_tests([])

        assert be_tests == set()

        assert fe_files == set()

        assert untested == []


    def test_all_files_unmapped(self, tmp_path: Path) -> None:

        map_path = _write_dep_map(tmp_path / "dep-map.json")

        runner = ScopedTestRunner(dependency_map_path=map_path)


        be_tests, fe_files, untested = runner._select_tests(

            ["a.py", "b.py", "c.py"]

        )

        assert be_tests == set()

        assert fe_files == set()

        assert len(untested) == 3


    def test_duplicate_tests_deduplicated(self, tmp_path: Path) -> None:

        """Two changed files mapping to the same test produce no duplicates."""

        map_path = _write_dep_map(

            tmp_path / "dep-map.json",

            backend={

                "backend/src/a.py": ["backend/tests/unit/test_shared.py"],

                "backend/src/b.py": ["backend/tests/unit/test_shared.py"],

            },

        )


        runner = ScopedTestRunner(dependency_map_path=map_path)

        be_tests, _, _ = runner._select_tests(

            ["backend/src/a.py", "backend/src/b.py"]

        )


        # Should be a set with one entry, not duplicated

        assert len(be_tests) == 1

        assert "backend/tests/unit/test_shared.py" in be_tests


    def test_test_run_result_defaults(self) -> None:

        """TestRunResult has sensible defaults."""
        result = RunResult()

        assert result.tests_executed == 0

        assert result.tests_passed == 0

        assert result.tests_failed == 0

        assert result.untested_changes == []

        assert result.duration_seconds == 0.0

        assert result.backend_result is None

        assert result.frontend_result is None



# ---------------------------------------------------------------------------

# _get_git_changed_files

# ---------------------------------------------------------------------------


@pytest.mark.unit

class TestGetGitChangedFiles:

    """Test git diff helper with mocked subprocess."""


    @patch("scripts.test_maintenance.scoped_runner.subprocess.run")

    def test_returns_changed_files(self, mock_run: MagicMock) -> None:

        mock_run.return_value = subprocess.CompletedProcess(

            args=[], returncode=0,

            stdout="backend/src/a.py\nbackend/src/b.py\n", stderr="",

        )

        result = _get_git_changed_files()

        assert result == ["backend/src/a.py", "backend/src/b.py"]


    @patch("scripts.test_maintenance.scoped_runner.subprocess.run")

    def test_git_error_returns_empty(self, mock_run: MagicMock) -> None:

        mock_run.return_value = subprocess.CompletedProcess(

            args=[], returncode=1, stdout="", stderr="fatal: not a git repo",

        )

        result = _get_git_changed_files()

        assert result == []


    @patch(

        "scripts.test_maintenance.scoped_runner.subprocess.run",

        side_effect=FileNotFoundError("git not found"),

    )

    def test_git_not_installed(self, mock_run: MagicMock) -> None:

        result = _get_git_changed_files()

        assert result == []


    @patch("scripts.test_maintenance.scoped_runner.subprocess.run")

    def test_empty_diff(self, mock_run: MagicMock) -> None:

        mock_run.return_value = subprocess.CompletedProcess(

            args=[], returncode=0, stdout="", stderr="",

        )

        result = _get_git_changed_files()

        assert result == []

