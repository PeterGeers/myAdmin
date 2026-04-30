"""Unit tests for the CI lint rule that flags direct mysql.connector imports.

Tests cover:
- Detection of `import mysql.connector` violations
- Detection of `from mysql.connector import ...` violations
- Allowed files are properly skipped
- Configurable allowed files list
- Clean files produce no violations
- Syntax errors are handled gracefully

Requirements: 10.1, 10.2, 10.3
"""

import textwrap
from pathlib import Path

import pytest

# Add backend/scripts to path so we can import the lint module
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / 'scripts'))

from check_db_imports import check_file, scan_directory, ALLOWED_FILES, EXCLUDED_DIRS, SCAN_DIRS, _iter_py_files


class TestCheckFile:
    """Tests for the check_file function."""

    def test_catches_import_mysql_connector(self, tmp_path):
        """check_file detects `import mysql.connector`."""
        f = tmp_path / "bad.py"
        f.write_text("import mysql.connector\n", encoding="utf-8")
        violations = check_file(f)
        assert len(violations) == 1
        assert "direct import 'mysql.connector'" in violations[0]
        assert "DatabaseManager" in violations[0]

    def test_catches_import_mysql_connector_submodule(self, tmp_path):
        """check_file detects `import mysql.connector.pooling`."""
        f = tmp_path / "bad.py"
        f.write_text("import mysql.connector.pooling\n", encoding="utf-8")
        violations = check_file(f)
        assert len(violations) == 1
        assert "mysql.connector.pooling" in violations[0]

    def test_catches_from_mysql_connector_import(self, tmp_path):
        """check_file detects `from mysql.connector import Error`."""
        f = tmp_path / "bad.py"
        f.write_text("from mysql.connector import Error\n", encoding="utf-8")
        violations = check_file(f)
        assert len(violations) == 1
        assert "direct import from 'mysql.connector'" in violations[0]

    def test_catches_from_mysql_connector_submodule_import(self, tmp_path):
        """check_file detects `from mysql.connector.pooling import MySQLConnectionPool`."""
        f = tmp_path / "bad.py"
        f.write_text(
            "from mysql.connector.pooling import MySQLConnectionPool\n",
            encoding="utf-8",
        )
        violations = check_file(f)
        assert len(violations) == 1
        assert "mysql.connector.pooling" in violations[0]

    def test_catches_multiple_violations(self, tmp_path):
        """check_file detects multiple violations in a single file."""
        f = tmp_path / "bad.py"
        f.write_text(textwrap.dedent("""\
            import mysql.connector
            from mysql.connector import Error
            from mysql.connector.pooling import MySQLConnectionPool
        """), encoding="utf-8")
        violations = check_file(f)
        assert len(violations) == 3

    def test_clean_file_no_violations(self, tmp_path):
        """check_file returns empty list for a file with no mysql.connector imports."""
        f = tmp_path / "clean.py"
        f.write_text(textwrap.dedent("""\
            from database import DatabaseManager
            from db_exceptions import DatabaseError
            import os
            import json
        """), encoding="utf-8")
        violations = check_file(f)
        assert violations == []

    def test_ignores_unrelated_mysql_imports(self, tmp_path):
        """check_file ignores imports that are not mysql.connector."""
        f = tmp_path / "other.py"
        f.write_text("import mysql\n", encoding="utf-8")
        violations = check_file(f)
        assert violations == []

    def test_handles_syntax_error_gracefully(self, tmp_path):
        """check_file returns empty list for files with syntax errors."""
        f = tmp_path / "broken.py"
        f.write_text("def foo(\n", encoding="utf-8")
        violations = check_file(f)
        assert violations == []

    def test_reports_line_number(self, tmp_path):
        """check_file includes the correct line number in violation messages."""
        f = tmp_path / "bad.py"
        f.write_text(textwrap.dedent("""\
            import os
            import json
            import mysql.connector
        """), encoding="utf-8")
        violations = check_file(f)
        assert len(violations) == 1
        assert ":3:" in violations[0]

    def test_allowed_files_parameter_skips_file(self, tmp_path):
        """check_file skips files in the allowed_files set."""
        f = tmp_path / "database.py"
        f.write_text("import mysql.connector\n", encoding="utf-8")
        rel_path = str(f.as_posix())
        violations = check_file(f, allowed_files={rel_path})
        assert violations == []

    def test_allowed_files_parameter_none_checks_all(self, tmp_path):
        """check_file with allowed_files=None checks all files (no filtering)."""
        f = tmp_path / "any.py"
        f.write_text("import mysql.connector\n", encoding="utf-8")
        violations = check_file(f, allowed_files=None)
        assert len(violations) == 1

    def test_empty_file(self, tmp_path):
        """check_file returns empty list for an empty file."""
        f = tmp_path / "empty.py"
        f.write_text("", encoding="utf-8")
        violations = check_file(f)
        assert violations == []

    def test_descriptive_error_message(self, tmp_path):
        """Violation messages include the correct import path guidance."""
        f = tmp_path / "bad.py"
        f.write_text("import mysql.connector\n", encoding="utf-8")
        violations = check_file(f)
        assert "from database import DatabaseManager" in violations[0]
        assert "from db_exceptions import DatabaseError" in violations[0]


class TestScanDirectory:
    """Tests for the scan_directory function."""

    def test_finds_violations_across_files(self, tmp_path):
        """scan_directory finds violations in multiple files."""
        (tmp_path / "a.py").write_text("import mysql.connector\n", encoding="utf-8")
        (tmp_path / "b.py").write_text("from mysql.connector import Error\n", encoding="utf-8")
        (tmp_path / "c.py").write_text("import os\n", encoding="utf-8")
        violations = scan_directory(tmp_path, allowed_files=set())
        assert len(violations) == 2

    def test_skips_allowed_files(self, tmp_path):
        """scan_directory skips files in the allowed set."""
        src = tmp_path / "backend" / "src"
        src.mkdir(parents=True)
        db_file = src / "database.py"
        db_file.write_text("import mysql.connector\n", encoding="utf-8")
        other = src / "routes.py"
        other.write_text("import mysql.connector\n", encoding="utf-8")

        allowed = {"backend/src/database.py"}
        violations = scan_directory(tmp_path, allowed_files=allowed)
        assert len(violations) == 1
        assert "routes.py" in violations[0]

    def test_configurable_allowed_files(self, tmp_path):
        """scan_directory accepts a custom allowed_files set."""
        custom = tmp_path / "custom"
        custom.mkdir()
        f = custom / "my_db.py"
        f.write_text("import mysql.connector\n", encoding="utf-8")

        # With custom allowed set that includes this file
        violations = scan_directory(tmp_path, allowed_files={"custom/my_db.py"})
        assert len(violations) == 0

        # Without the file in allowed set
        violations = scan_directory(tmp_path, allowed_files=set())
        assert len(violations) == 1

    def test_scans_subdirectories(self, tmp_path):
        """scan_directory recursively scans subdirectories."""
        sub = tmp_path / "deep" / "nested"
        sub.mkdir(parents=True)
        f = sub / "bad.py"
        f.write_text("import mysql.connector\n", encoding="utf-8")
        violations = scan_directory(tmp_path, allowed_files=set())
        assert len(violations) == 1

    def test_clean_directory(self, tmp_path):
        """scan_directory returns empty list for a clean directory."""
        (tmp_path / "clean.py").write_text("import os\n", encoding="utf-8")
        violations = scan_directory(tmp_path, allowed_files=set())
        assert violations == []

    def test_empty_directory(self, tmp_path):
        """scan_directory returns empty list for an empty directory."""
        violations = scan_directory(tmp_path, allowed_files=set())
        assert violations == []

    def test_skips_excluded_directories(self, tmp_path):
        """scan_directory skips directories in EXCLUDED_DIRS by default."""
        # Create a .venv dir with a violation
        venv = tmp_path / ".venv" / "lib"
        venv.mkdir(parents=True)
        (venv / "connector.py").write_text("import mysql.connector\n", encoding="utf-8")
        # Create a project file with a violation
        (tmp_path / "app.py").write_text("import mysql.connector\n", encoding="utf-8")

        violations = scan_directory(tmp_path, allowed_files=set())
        assert len(violations) == 1
        assert "app.py" in violations[0]

    def test_skips_node_modules(self, tmp_path):
        """scan_directory skips node_modules directory."""
        nm = tmp_path / "node_modules" / "some_pkg"
        nm.mkdir(parents=True)
        (nm / "index.py").write_text("import mysql.connector\n", encoding="utf-8")

        violations = scan_directory(tmp_path, allowed_files=set())
        assert violations == []

    def test_skips_pycache(self, tmp_path):
        """scan_directory skips __pycache__ directories."""
        cache = tmp_path / "__pycache__"
        cache.mkdir()
        (cache / "mod.py").write_text("import mysql.connector\n", encoding="utf-8")

        violations = scan_directory(tmp_path, allowed_files=set())
        assert violations == []

    def test_custom_excluded_dirs(self, tmp_path):
        """scan_directory accepts custom excluded_dirs set."""
        mydir = tmp_path / "skipme"
        mydir.mkdir()
        (mydir / "bad.py").write_text("import mysql.connector\n", encoding="utf-8")

        # With custom exclusion
        violations = scan_directory(tmp_path, allowed_files=set(), excluded_dirs={"skipme"})
        assert violations == []

        # Without exclusion
        violations = scan_directory(tmp_path, allowed_files=set(), excluded_dirs=set())
        assert len(violations) == 1


class TestDefaultAllowedFiles:
    """Tests for the default ALLOWED_FILES configuration."""

    def test_default_allowed_files_contains_database(self):
        """ALLOWED_FILES includes database.py."""
        assert 'backend/src/database.py' in ALLOWED_FILES

    def test_default_allowed_files_contains_scalability_manager(self):
        """ALLOWED_FILES includes scalability_manager.py."""
        assert 'backend/src/scalability_manager.py' in ALLOWED_FILES

    def test_allowed_files_uses_posix_paths(self):
        """ALLOWED_FILES uses forward-slash paths for cross-platform compatibility."""
        for path in ALLOWED_FILES:
            assert '\\' not in path, f"Path {path} uses backslashes"


class TestExcludedDirsConfig:
    """Tests for the EXCLUDED_DIRS and SCAN_DIRS configuration."""

    def test_excluded_dirs_contains_venv(self):
        """EXCLUDED_DIRS includes .venv."""
        assert '.venv' in EXCLUDED_DIRS

    def test_excluded_dirs_contains_node_modules(self):
        """EXCLUDED_DIRS includes node_modules."""
        assert 'node_modules' in EXCLUDED_DIRS

    def test_excluded_dirs_contains_pycache(self):
        """EXCLUDED_DIRS includes __pycache__."""
        assert '__pycache__' in EXCLUDED_DIRS

    def test_excluded_dirs_contains_git(self):
        """EXCLUDED_DIRS includes .git."""
        assert '.git' in EXCLUDED_DIRS

    def test_scan_dirs_contains_backend(self):
        """SCAN_DIRS includes backend."""
        assert 'backend' in SCAN_DIRS

    def test_scan_dirs_contains_scripts(self):
        """SCAN_DIRS includes scripts."""
        assert 'scripts' in SCAN_DIRS


class TestMainExitCodes:
    """Tests for the main() function exit codes."""

    def test_main_exits_1_on_violations(self, tmp_path, monkeypatch):
        """main() exits with code 1 when violations are found."""
        # main() scans SCAN_DIRS (backend, scripts), so create that structure
        backend_dir = tmp_path / "backend"
        backend_dir.mkdir()
        f = backend_dir / "bad.py"
        f.write_text("import mysql.connector\n", encoding="utf-8")

        monkeypatch.chdir(tmp_path)

        from check_db_imports import main
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1

    def test_main_exits_0_on_clean(self, tmp_path, monkeypatch):
        """main() exits with code 0 when no violations are found."""
        backend_dir = tmp_path / "backend"
        backend_dir.mkdir()
        f = backend_dir / "clean.py"
        f.write_text("import os\n", encoding="utf-8")

        monkeypatch.chdir(tmp_path)

        from check_db_imports import main
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0

    def test_main_exits_0_when_no_scan_dirs_exist(self, tmp_path, monkeypatch):
        """main() exits with code 0 when scan directories don't exist."""
        monkeypatch.chdir(tmp_path)

        from check_db_imports import main
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0
