"""Unit tests for import_analyzer.py — Python import parsing via AST."""

import os
import textwrap
from pathlib import Path

import pytest

from scripts.test_maintenance.import_analyzer import (
    ImportInfo,
    analyze_file,
    resolve_relative_import,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_py(tmp_path: Path, name: str, source: str) -> Path:
    """Write a Python file under *tmp_path* and return its path."""
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(source), encoding="utf-8")
    return p


def _make_package(tmp_path: Path, *parts: str) -> None:
    """Create nested package directories with __init__.py files."""
    current = tmp_path
    for part in parts:
        current = current / part
        current.mkdir(exist_ok=True)
        (current / "__init__.py").write_text("", encoding="utf-8")


# ---------------------------------------------------------------------------
# analyze_file — basic import extraction
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestAnalyzeFileBasicImports:
    """Test extraction of plain ``import`` statements."""

    def test_plain_import(self, tmp_path: Path) -> None:
        f = _write_py(tmp_path, "mod.py", "import os\n")
        result = analyze_file(f)
        assert len(result) == 1
        info = result[0]
        assert info.module_name == "os"
        assert info.imported_names == []
        assert info.is_relative is False
        assert info.resolved_path == "os"
        assert info.line_number == 1

    def test_multiple_plain_imports(self, tmp_path: Path) -> None:
        f = _write_py(tmp_path, "mod.py", "import os, sys\n")
        result = analyze_file(f)
        assert len(result) == 2
        assert result[0].module_name == "os"
        assert result[1].module_name == "sys"

    def test_dotted_import(self, tmp_path: Path) -> None:
        f = _write_py(tmp_path, "mod.py", "import os.path\n")
        result = analyze_file(f)
        assert len(result) == 1
        assert result[0].module_name == "os.path"
        assert result[0].resolved_path == "os.path"


@pytest.mark.unit
class TestAnalyzeFileFromImports:
    """Test extraction of ``from ... import`` statements."""

    def test_from_import(self, tmp_path: Path) -> None:
        f = _write_py(tmp_path, "mod.py", "from os.path import join, exists\n")
        result = analyze_file(f)
        assert len(result) == 1
        info = result[0]
        assert info.module_name == "os.path"
        assert info.imported_names == ["join", "exists"]
        assert info.is_relative is False
        assert info.resolved_path == "os.path"

    def test_from_import_star(self, tmp_path: Path) -> None:
        f = _write_py(tmp_path, "mod.py", "from os.path import *\n")
        result = analyze_file(f)
        assert len(result) == 1
        assert result[0].imported_names == ["*"]

    def test_mixed_imports(self, tmp_path: Path) -> None:
        source = """\
            import json
            from pathlib import Path
            import os
        """
        f = _write_py(tmp_path, "mod.py", source)
        result = analyze_file(f)
        assert len(result) == 3
        assert result[0].module_name == "json"
        assert result[1].module_name == "pathlib"
        assert result[1].imported_names == ["Path"]
        assert result[2].module_name == "os"


# ---------------------------------------------------------------------------
# analyze_file — relative imports
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestAnalyzeFileRelativeImports:
    """Test extraction and resolution of relative imports."""

    def test_single_dot_relative(self, tmp_path: Path) -> None:
        _make_package(tmp_path, "pkg")
        f = _write_py(
            tmp_path, "pkg/mod.py", "from .utils import helper\n"
        )
        result = analyze_file(f)
        assert len(result) == 1
        info = result[0]
        assert info.is_relative is True
        assert info.module_name == "utils"
        assert info.imported_names == ["helper"]
        assert info.resolved_path == "pkg.utils"

    def test_double_dot_relative(self, tmp_path: Path) -> None:
        _make_package(tmp_path, "pkg", "sub")
        f = _write_py(
            tmp_path, "pkg/sub/mod.py", "from ..other import thing\n"
        )
        result = analyze_file(f)
        assert len(result) == 1
        info = result[0]
        assert info.is_relative is True
        assert info.resolved_path == "pkg.other"

    def test_bare_dot_import(self, tmp_path: Path) -> None:
        """``from . import name`` — module is None."""
        _make_package(tmp_path, "pkg")
        f = _write_py(tmp_path, "pkg/mod.py", "from . import sibling\n")
        result = analyze_file(f)
        assert len(result) == 1
        info = result[0]
        assert info.is_relative is True
        assert info.module_name == ""
        assert info.imported_names == ["sibling"]
        # Resolved to the package itself
        assert info.resolved_path == "pkg"


# ---------------------------------------------------------------------------
# analyze_file — error handling
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestAnalyzeFileErrorHandling:
    """Test graceful handling of bad inputs."""

    def test_nonexistent_file(self, tmp_path: Path) -> None:
        result = analyze_file(tmp_path / "does_not_exist.py")
        assert result == []

    def test_syntax_error(self, tmp_path: Path) -> None:
        f = _write_py(tmp_path, "bad.py", "def broken(\n")
        result = analyze_file(f)
        assert result == []

    @pytest.mark.skipif(
        os.name == "nt",
        reason="chmod(0o000) does not restrict reads on Windows",
    )
    def test_permission_denied(self, tmp_path: Path) -> None:
        f = _write_py(tmp_path, "secret.py", "import os\n")
        f.chmod(0o000)
        try:
            result = analyze_file(f)
            assert result == []
        finally:
            # Restore permissions so tmp_path cleanup works.
            f.chmod(0o644)

    def test_empty_file(self, tmp_path: Path) -> None:
        f = _write_py(tmp_path, "empty.py", "")
        result = analyze_file(f)
        assert result == []

    def test_file_with_only_comments(self, tmp_path: Path) -> None:
        f = _write_py(tmp_path, "comments.py", "# just a comment\n")
        result = analyze_file(f)
        assert result == []


# ---------------------------------------------------------------------------
# resolve_relative_import
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestResolveRelativeImport:
    """Test the standalone relative import resolver."""

    def test_level_zero_passthrough(self) -> None:
        assert resolve_relative_import("os", 0, "pkg") == "os"

    def test_single_dot_with_module(self) -> None:
        result = resolve_relative_import("utils", 1, "backend.src.services")
        assert result == "backend.src.services.utils"

    def test_single_dot_no_module(self) -> None:
        result = resolve_relative_import(None, 1, "backend.src.services")
        assert result == "backend.src.services"

    def test_double_dot_with_module(self) -> None:
        result = resolve_relative_import("helpers", 2, "backend.src.services")
        assert result == "backend.src.helpers"

    def test_triple_dot(self) -> None:
        # level=3 in package "a.b.c" → go up 2 levels → base is "a"
        result = resolve_relative_import("top", 3, "a.b.c")
        assert result == "a.top"

    def test_level_exceeds_depth(self) -> None:
        result = resolve_relative_import("x", 5, "a.b")
        assert result is None

    def test_empty_package(self) -> None:
        result = resolve_relative_import("mod", 1, "")
        assert result == "mod"

    def test_double_dot_no_module(self) -> None:
        result = resolve_relative_import(None, 2, "a.b.c")
        assert result == "a.b"


# ---------------------------------------------------------------------------
# analyze_file — line numbers
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestLineNumbers:
    """Verify that line numbers are correctly captured."""

    def test_line_numbers_match(self, tmp_path: Path) -> None:
        source = """\
            # line 1
            import os
            # line 3
            from pathlib import Path
            # line 5
            import json
        """
        f = _write_py(tmp_path, "mod.py", source)
        result = analyze_file(f)
        assert len(result) == 3
        assert result[0].line_number == 2
        assert result[1].line_number == 4
        assert result[2].line_number == 6


# ---------------------------------------------------------------------------
# analyze_file — real-world patterns
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestRealWorldPatterns:
    """Test patterns commonly found in the myAdmin codebase."""

    def test_database_import(self, tmp_path: Path) -> None:
        source = """\
            from database import DatabaseManager
            from dialect_helpers import dialect
            from db_exceptions import DatabaseError, IntegrityError
        """
        f = _write_py(tmp_path, "mod.py", source)
        result = analyze_file(f)
        assert len(result) == 3
        assert result[0].module_name == "database"
        assert result[0].imported_names == ["DatabaseManager"]
        assert result[1].module_name == "dialect_helpers"
        assert result[2].module_name == "db_exceptions"
        assert result[2].imported_names == ["DatabaseError", "IntegrityError"]

    def test_test_file_imports(self, tmp_path: Path) -> None:
        source = """\
            import pytest
            from unittest.mock import patch, MagicMock
            from banking_processor import BankingProcessor
        """
        f = _write_py(tmp_path, "test_banking.py", source)
        result = analyze_file(f)
        assert len(result) == 3
        modules = [r.module_name for r in result]
        assert "pytest" in modules
        assert "unittest.mock" in modules
        assert "banking_processor" in modules

    def test_conditional_import_still_extracted(self, tmp_path: Path) -> None:
        """Imports inside if/try blocks are still found by ast.walk."""
        source = """\
            try:
                import optional_lib
            except ImportError:
                optional_lib = None
        """
        f = _write_py(tmp_path, "mod.py", source)
        result = analyze_file(f)
        assert len(result) == 1
        assert result[0].module_name == "optional_lib"
