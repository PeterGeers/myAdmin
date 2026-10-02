"""Unit tests for the CI lint rule that flags the Raw_Connection_Pattern.

Sibling to ``test_check_db_imports.py``. Where that suite tests the ban on direct
``mysql.connector`` imports, this one tests ``check_raw_connection.py``: the AST guard
that flags capturing the result of ``get_connection(...)`` / ``_get_connection(...)``
instead of using the context-managed API (``get_cursor()`` / ``transaction()``).

ZERO-TOLERANCE (Req 6.3, 2.5): ``get_connection`` was privatized to ``_get_connection``
and every real caller migrated, so the guard now (a) flags BOTH names, (b) matches ANY
receiver (not just ``db``/``self``/``self.db``), (c) flags ``return`` forms in addition
to assignments, and (d) keeps ``PENDING_SITES`` permanently empty.

Tests cover (Property 4 — guard soundness & completeness; Property 5 — allow-list empty):
- Both names flagged: ``get_connection`` AND the private ``_get_connection``.
- ANY receiver flagged, including the aliased ``db_manager.get_connection()`` that the
  old narrow matcher missed; plus ``db.``, ``self.db.``, ``self.``, bare name.
- ``AnnAssign`` form (``conn: Any = db.get_connection()``) detected.
- ``Return`` form (``return self.db.get_connection()``) detected.
- NO false positive when the result is not captured: inside a ``with`` header, a bare
  expression statement, or passed directly as a call argument.
- The always-excluded internal files (ALLOWED_FILES: ``database.py``, ``str_database.py``,
  ``scalability_manager.py``) are never flagged.
- ``PENDING_SITES`` is empty and stays empty (the migration is sealed).

Requirements: 2.1, 2.3, 2.4, 2.5, 6.3
"""

import textwrap
from pathlib import Path

import pytest

# Add backend/scripts to path so we can import the lint module (mirrors
# test_check_db_imports.py — conftest does not put scripts on the path).
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / 'scripts'))

from check_raw_connection import (  # noqa: E402
    check_file,
    scan,
    ALLOWED_FILES,
    PENDING_SITES,
    EXCLUDED_DIRS,
    SCAN_DIRS,
)


def _write(tmp_path: Path, name: str, body: str) -> Path:
    """Write a dedented snippet to a .py file under tmp_path and return the path."""
    f = tmp_path / name
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(textwrap.dedent(body), encoding="utf-8")
    return f


def _rel_key(filepath: Path) -> str:
    """Reproduce the allow-list key `check_file` derives from a path.

    `check_file` matches against ``filepath.as_posix().replace('\\\\', '/').lstrip('./')``,
    so to put a temp (absolute) path on an allow-list in a test we must key it the same
    way — otherwise the leading-'/' strip means our set entry never matches.
    """
    return filepath.as_posix().replace('\\', '/').lstrip('./')


class TestReceiverForms:
    """Each accepted receiver form of the Raw_Connection_Pattern is detected."""

    def test_bare_name_get_connection_is_flagged(self, tmp_path):
        """`conn = get_connection()` (bare name) is flagged."""
        f = _write(tmp_path, "bare.py", """\
            def handler():
                conn = get_connection()
                return conn
        """)
        violations = check_file(f, allowed_files=set(), pending_sites=set())
        assert len(violations) == 1
        assert ":2:" in violations[0]

    def test_db_dot_get_connection_is_flagged(self, tmp_path):
        """`conn = db.get_connection()` is flagged."""
        f = _write(tmp_path, "dbdot.py", """\
            def handler(db):
                conn = db.get_connection()
                return conn
        """)
        violations = check_file(f, allowed_files=set(), pending_sites=set())
        assert len(violations) == 1

    def test_self_db_dot_get_connection_is_flagged(self, tmp_path):
        """`conn = self.db.get_connection()` is flagged."""
        f = _write(tmp_path, "selfdbdot.py", """\
            class Svc:
                def run(self):
                    conn = self.db.get_connection()
                    return conn
        """)
        violations = check_file(f, allowed_files=set(), pending_sites=set())
        assert len(violations) == 1

    def test_self_dot_get_connection_is_flagged(self, tmp_path):
        """`conn = self.get_connection()` is flagged."""
        f = _write(tmp_path, "selfdot.py", """\
            class Svc:
                def run(self):
                    conn = self.get_connection()
                    return conn
        """)
        violations = check_file(f, allowed_files=set(), pending_sites=set())
        assert len(violations) == 1

    def test_annassign_form_is_flagged(self, tmp_path):
        """`conn: Any = db.get_connection()` (AnnAssign) is flagged."""
        f = _write(tmp_path, "ann.py", """\
            from typing import Any

            def handler(db):
                conn: Any = db.get_connection()
                return conn
        """)
        violations = check_file(f, allowed_files=set(), pending_sites=set())
        assert len(violations) == 1

    def test_aliased_receiver_get_connection_is_flagged(self, tmp_path):
        """`conn = db_manager.get_connection()` (aliased receiver) is flagged.

        This is the gap the original narrow (db/self/self.db-only) matcher MISSED,
        causing 5 real sites to be dropped from the inventory. Any-receiver closes it.
        """
        f = _write(tmp_path, "aliased.py", """\
            def handler(db_manager):
                conn = db_manager.get_connection()
                return conn
        """)
        violations = check_file(f, allowed_files=set(), pending_sites=set())
        assert len(violations) == 1

    def test_chained_receiver_get_connection_is_flagged(self, tmp_path):
        """A deeper chained receiver `self.foo.bar.get_connection()` is still flagged."""
        f = _write(tmp_path, "chained.py", """\
            class Svc:
                def run(self):
                    conn = self.foo.bar.get_connection()
                    return conn
        """)
        violations = check_file(f, allowed_files=set(), pending_sites=set())
        assert len(violations) == 1


class TestPrivateName:
    """The privatized `_get_connection` name is banned for external callers too (Req 6.3)."""

    def test_bare_private_name_is_flagged(self, tmp_path):
        """`conn = _get_connection()` (bare private name) is flagged."""
        f = _write(tmp_path, "barepriv.py", """\
            def handler():
                conn = _get_connection()
                return conn
        """)
        violations = check_file(f, allowed_files=set(), pending_sites=set())
        assert len(violations) == 1

    def test_db_dot_private_name_is_flagged(self, tmp_path):
        """`conn = db._get_connection()` is flagged."""
        f = _write(tmp_path, "dbdotpriv.py", """\
            def handler(db):
                conn = db._get_connection()
                return conn
        """)
        violations = check_file(f, allowed_files=set(), pending_sites=set())
        assert len(violations) == 1

    def test_self_private_name_annassign_is_flagged(self, tmp_path):
        """`conn: Any = self._get_connection()` (AnnAssign, private) is flagged."""
        f = _write(tmp_path, "selfpriv.py", """\
            from typing import Any

            class Svc:
                def run(self):
                    conn: Any = self._get_connection()
                    return conn
        """)
        violations = check_file(f, allowed_files=set(), pending_sites=set())
        assert len(violations) == 1


class TestReturnForm:
    """`return <any>.get_connection()` / ._get_connection() — the wrapper shape — is flagged."""

    def test_return_self_db_get_connection_is_flagged(self, tmp_path):
        """`return self.db.get_connection()` is flagged (Return node, not Assign)."""
        f = _write(tmp_path, "retself.py", """\
            class Svc:
                def get(self):
                    return self.db.get_connection()
        """)
        violations = check_file(f, allowed_files=set(), pending_sites=set())
        assert len(violations) == 1

    def test_return_db_private_name_is_flagged(self, tmp_path):
        """`return db._get_connection()` is flagged."""
        f = _write(tmp_path, "retpriv.py", """\
            def get_conn(db):
                return db._get_connection()
        """)
        violations = check_file(f, allowed_files=set(), pending_sites=set())
        assert len(violations) == 1

    def test_return_bare_name_is_flagged(self, tmp_path):
        """`return get_connection()` (bare name) is flagged."""
        f = _write(tmp_path, "retbare.py", """\
            def get_conn():
                return get_connection()
        """)
        violations = check_file(f, allowed_files=set(), pending_sites=set())
        assert len(violations) == 1


class TestNoFalsePositiveOnNonAssignment:
    """Calls to get_connection() that are not assignments must not be flagged."""

    def test_call_inside_with_header_not_flagged(self, tmp_path):
        """A `with` statement — no assignment of get_connection()'s result — is clean.

        The real migration shape is `with db.get_cursor() as (c, conn):`; here we also
        confirm a `with db.get_connection() ...` header itself is not an Assign/AnnAssign
        node and so is never flagged.
        """
        f = _write(tmp_path, "withblock.py", """\
            def handler(db):
                with db.get_cursor() as (cursor, conn):
                    cursor.execute("SELECT 1")
                with db.get_connection() as conn:
                    conn.ping()
        """)
        violations = check_file(f, allowed_files=set(), pending_sites=set())
        assert violations == []

    def test_bare_expression_call_not_flagged(self, tmp_path):
        """A bare `get_connection()` expression statement (result discarded) is clean."""
        f = _write(tmp_path, "bareexpr.py", """\
            def handler(db):
                db.get_connection()
                get_connection()
        """)
        violations = check_file(f, allowed_files=set(), pending_sites=set())
        assert violations == []

    def test_call_passed_as_argument_not_flagged(self, tmp_path):
        """`get_connection()` passed directly as a call argument is not an assignment."""
        f = _write(tmp_path, "asarg.py", """\
            import pandas as pd

            def handler(db, query):
                return pd.read_sql(query, db.get_connection())
        """)
        violations = check_file(f, allowed_files=set(), pending_sites=set())
        assert violations == []


class TestAllowedFiles:
    """ALLOWED_FILES (e.g. database.py) are never scanned even with a raw pattern."""

    def test_database_py_internal_use_not_flagged(self, tmp_path):
        """database.py's own `conn = self._get_connection()` is legitimate internal use."""
        f = _write(tmp_path, "database.py", """\
            class DatabaseManager:
                def get_cursor(self):
                    conn = self._get_connection()
                    return conn
        """)
        rel = _rel_key(f)
        violations = check_file(f, allowed_files={rel}, pending_sites=set())
        assert violations == []

    def test_scalability_manager_pool_call_not_flagged_when_allowed(self, tmp_path):
        """scalability_manager.py's AdvancedConnectionPool pool calls are legitimate.

        Its `self.pools[...].get_connection()` and `return ...get_connection(pool_type)`
        are a DIFFERENT API (a pool @contextmanager), not the DatabaseManager accessor,
        so the file is in ALLOWED_FILES and never flagged despite any-receiver matching.
        """
        f = _write(tmp_path, "scalability_manager.py", """\
            class AdvancedConnectionPool:
                def get_connection(self, pool_type="primary"):
                    connection = self.pools[pool_type].get_connection()
                    return connection
        """)
        rel = _rel_key(f)
        violations = check_file(f, allowed_files={rel}, pending_sites=set())
        assert violations == []

    def test_default_allowed_files_contains_internal_files(self):
        """The default ALLOWED_FILES includes all three legitimate-internal files."""
        assert 'backend/src/database.py' in ALLOWED_FILES
        assert 'backend/src/str_database.py' in ALLOWED_FILES
        assert 'backend/src/scalability_manager.py' in ALLOWED_FILES


class TestAllowListRespectedAndShrinks:
    """PENDING_SITES is respected; shrinking it surfaces the file (Property 5)."""

    def test_pending_file_is_skipped(self, tmp_path):
        """A file whose relative path is in `pending` is skipped (returns no violations)."""
        f = _write(tmp_path, "pending.py", """\
            def handler(db):
                conn = db.get_connection()
                return conn
        """)
        rel = _rel_key(f)
        violations = check_file(f, allowed_files=set(), pending_sites={rel})
        assert violations == []

    def test_same_file_flagged_when_removed_from_pending(self, tmp_path):
        """Removing the file from `pending` surfaces its violation (monotonic shrink)."""
        f = _write(tmp_path, "pending.py", """\
            def handler(db):
                conn = db.get_connection()
                return conn
        """)
        # Same file, same content: in the allow-list -> clean; out of it -> flagged.
        assert check_file(f, allowed_files=set(), pending_sites={_rel_key(f)}) == []
        violations = check_file(f, allowed_files=set(), pending_sites=set())
        assert len(violations) == 1


class TestScan:
    """scan() aggregates check_file over a directory tree."""

    def test_scan_flags_violation_outside_allow_lists(self, tmp_path):
        """scan finds a raw pattern in a file not in allowed/pending."""
        _write(tmp_path, "a.py", """\
            def handler(db):
                conn = db.get_connection()
                return conn
        """)
        _write(tmp_path, "clean.py", """\
            def handler(db):
                with db.get_cursor() as (cursor, conn):
                    cursor.execute("SELECT 1")
        """)
        violations = scan(tmp_path, allowed_files=set(), pending_sites=set())
        assert len(violations) == 1
        assert "a.py" in violations[0]

    def test_scan_respects_pending_and_shrink(self, tmp_path):
        """scan skips a pending file; dropping it from pending surfaces the violation."""
        src = tmp_path / "backend" / "src"
        f = _write(src, "pending.py", """\
            def handler(db):
                conn = db.get_connection()
                return conn
        """)
        # scan() delegates to check_file, which keys on the full (stripped) posix path.
        rel = _rel_key(f)
        assert scan(tmp_path, allowed_files=set(), pending_sites={rel}) == []
        assert len(scan(tmp_path, allowed_files=set(), pending_sites=set())) == 1

    def test_scan_skips_excluded_dirs(self, tmp_path):
        """scan skips EXCLUDED_DIRS (e.g. __pycache__)."""
        cache = tmp_path / "__pycache__"
        _write(cache, "mod.py", """\
            def handler(db):
                conn = db.get_connection()
                return conn
        """)
        violations = scan(tmp_path, allowed_files=set(), pending_sites=set())
        assert violations == []


class TestDefaultConfig:
    """Default module-level configuration sanity checks."""

    def test_pending_sites_is_empty(self):
        """PENDING_SITES is permanently empty post-migration (Req 2.5, 6.3, Property 5).

        The migration is complete and the allow-list is sealed; it must never grow again.
        (The module-load `assert PENDING_SITES == set()` guard enforces this at import.)
        """
        assert PENDING_SITES == set()

    def test_pending_sites_uses_posix_paths(self):
        """Any PENDING_SITES entry (should be none) would use posix repo-root paths."""
        for path in PENDING_SITES:
            assert '\\' not in path, f"Path {path} uses backslashes"
            assert path.startswith('backend/src/'), path

    def test_scan_dirs_targets_backend_src(self):
        """SCAN_DIRS is scoped to backend/src production call sites."""
        assert 'backend/src' in SCAN_DIRS

    def test_excluded_dirs_contains_common_noise(self):
        """EXCLUDED_DIRS covers the usual non-source directories."""
        assert '__pycache__' in EXCLUDED_DIRS
        assert '.venv' in EXCLUDED_DIRS
