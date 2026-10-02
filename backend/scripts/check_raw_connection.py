"""CI lint rule: flag any raw ``get_connection`` / ``_get_connection`` escape (Req 2, 6.3).

Sibling to ``check_db_imports.py``. Where that script bans ``import mysql.connector``
outside the abstraction layer, this one bans the *Raw_Connection_Pattern*: taking the
result of ``get_connection(...)`` (or the now-private ``_get_connection(...)``) and
manually managing the cursor/connection lifecycle
(``conn = db.get_connection(); ...; conn.close()``), instead of using the
context-managed API (``get_cursor()`` / ``transaction()``).

ZERO-TOLERANCE / SEALED (Req 6.3, 2.5): the migration is COMPLETE. ``get_connection`` has
been privatized to ``_get_connection`` (task 12.1) and every real caller in ``backend/src``
has been migrated to the context-managed API. ``PENDING_SITES`` is therefore permanently
empty and MUST remain so — a module-load guard (``assert PENDING_SITES == set()``) fails
loudly if anyone tries to re-open the allow-list.

Detection is AST-based. A violation is a ``get_connection`` **or** ``_get_connection`` call
appearing as the value of:
  * an ``Assign``     — ``conn = <any>.get_connection()``
  * an ``AnnAssign``  — ``conn: Any = <any>._get_connection()``
  * a ``Return``      — ``return <any>.get_connection()`` (the old wrapper-method shape)

Both the public and private names are flagged: external code must call NEITHER. The match
keys ONLY on the method/function name — it fires for ANY receiver
(``db.``, ``self.db.``, ``self.``, an aliased ``db_manager.``, or the bare name). The
original narrow "``db``/``self``/``self.db`` only" receiver matcher silently missed real
aliased sites (e.g. ``db_manager.get_connection()``) — any-receiver closes that gap.

Scope decision — call-in-argument-position is deliberately NOT flagged. A call used purely
as an argument (``pd.read_sql(q, db.get_connection())``) and a ``with`` header
(``with db.get_connection() as c:``) are neither an assignment nor a return and are left
alone. Rationale: assignment + return already cover every escape-hatch shape that existed
in the codebase (wrapper / probe / pandas), the privatization + full migration leave ZERO
real sites of any shape, and widening to argument position would only add false-positive
surface against the pool-object calls living in the excluded files below. The pre-existing
"not flagged as a `with` header / bare expression / call argument" behavior is preserved.

The only files that legitimately touch these names are internal and are listed in
``ALLOWED_FILES`` (see below); for ``backend/src`` at large the scan now reports ZERO
matches.

Usage:
    python backend/scripts/check_raw_connection.py            # scan SCAN_DIRS (CI)
    python backend/scripts/check_raw_connection.py [path ...] # check only given files

Exit code 0 = clean, 1 = violations found.
"""

import ast
import sys
from pathlib import Path

# Files never scanned for this pattern — their `_get_connection()` / pool `.get_connection()`
# call is the legitimate internal use the abstraction layer is built around, NOT a
# migration target:
#   - database.py: defines DatabaseManager._get_connection (the private raw accessor) and
#     its get_cursor() fallback assigns `conn = self._get_connection()` by design
#     (Req 2.4, 6.1). It also owns the `_legacy_pool.get_connection()` pool call.
#   - str_database.py: STRDatabase(DatabaseManager) calls its own inherited
#     self._get_connection() in __init__ — a subclass using its base accessor, the same
#     legitimate-internal category as database.py.
#   - scalability_manager.py: AdvancedConnectionPool.get_connection(pool_type) is a
#     DIFFERENT API — a @contextmanager pool accessor (`self.pools[...].get_connection()`,
#     `return self.connection_pool.get_connection(pool_type)`), NOT the DatabaseManager
#     raw accessor. With any-receiver + return detection these pool calls would otherwise
#     be flagged; they are legitimate internal pool plumbing, so the file is excluded.
ALLOWED_FILES = {
    'backend/src/database.py',
    'backend/src/str_database.py',
    'backend/src/scalability_manager.py',
}

# Post-migration allow-list — PERMANENTLY EMPTY (Req 2.5, 6.3). The migration is complete
# and `get_connection` has been privatized, so there are no known-pending files left. This
# set MUST remain empty: the module-load guard below (`assert PENDING_SITES == set()`)
# fails loudly if anyone re-opens it. A file is NEVER re-added — fix the call site instead.
PENDING_SITES = set()

# Zero-tolerance seal (Req 2.5, 6.3): the allow-list can never silently grow again.
assert PENDING_SITES == set(), (
    "allow-list must be empty post-migration — the get_connection() escape hatch is "
    "sealed; migrate the offending call site to get_cursor()/transaction() instead of "
    "re-adding it to PENDING_SITES"
)

# Directories to skip during scanning (mirrors check_db_imports.EXCLUDED_DIRS).
EXCLUDED_DIRS = {
    '.venv', 'venv', 'env', '.env',
    'node_modules',
    '.git',
    '__pycache__',
    '.hypothesis',
    '.tox',
    '.mypy_cache',
    '.pytest_cache',
    'mysql_data',
    '.kiro',
}

# Project directories to scan. The Raw_Connection_Pattern migration is scoped to
# backend/src production call sites only (backend/scripts and backend/tests are out of
# scope per the design), so the scan root is backend/src.
SCAN_DIRS = ['backend/src']

# The replacement guidance appended to every violation message.
_HINT = (
    "raw get_connection()/_get_connection() escape — replace with "
    "'with db.get_cursor() as (cursor, conn):' (reads) or "
    "'with db.transaction() as (cursor, conn):' (writes)"
)


# Both the public accessor and its privatized form are banned for external callers
# (Req 6.3): external code must use NEITHER — only the context-managed API.
_BANNED_NAMES = frozenset({'get_connection', '_get_connection'})


def _is_get_connection_call(value: ast.expr) -> bool:
    """Return True if ``value`` is a call to ``get_connection`` / ``_get_connection``.

    ZERO-TOLERANCE, ANY-RECEIVER: the match keys ONLY on the called method/function name
    being ``get_connection`` or ``_get_connection``. It fires for every shape —
      * bare name:            ``get_connection(...)`` / ``_get_connection(...)``
      * any attribute access: ``<anything>.get_connection(...)`` /
                              ``<anything>._get_connection(...)``
    regardless of the receiver (``db``, ``self``, ``self.db``, an aliased ``db_manager``,
    a chained ``self.foo.bar``, …). The original narrow matcher restricted receivers to
    ``db``/``self``/``self.db`` and silently missed aliased sites such as
    ``db_manager.get_connection()``; keying on the name alone closes that gap. The only
    legitimate ``.get_connection()`` pool-object calls (AdvancedConnectionPool) live in
    the ALLOWED_FILES above and are excluded there, not by restricting receivers here.
    """
    if not isinstance(value, ast.Call):
        return False

    func = value.func

    # Bare name:  get_connection(...) / _get_connection(...)
    if isinstance(func, ast.Name):
        return func.id in _BANNED_NAMES

    # Attribute access:  <any receiver>.get_connection(...) / ._get_connection(...)
    if isinstance(func, ast.Attribute):
        return func.attr in _BANNED_NAMES

    return False


def check_file(filepath: Path, allowed_files: set[str] | None = None,
               pending_sites: set[str] | None = None) -> list[str]:
    """Return list of violation messages for a single file.

    Args:
        filepath: Path to the Python file to check.
        allowed_files: Files never scanned (legitimate internal use). Defaults to
            ALLOWED_FILES. A matching file returns an empty list.
        pending_sites: Known-pending files to skip (the shrinking allow-list). Defaults
            to PENDING_SITES. A matching file returns an empty list.

    Returns:
        List of violation message strings. Empty if the file is clean, allowed, or
        pending.
    """
    if allowed_files is None:
        allowed_files = ALLOWED_FILES
    if pending_sites is None:
        pending_sites = PENDING_SITES

    rel = filepath.as_posix().replace('\\', '/').lstrip('./')
    if rel in allowed_files or rel in pending_sites:
        return []

    violations = []
    try:
        tree = ast.parse(filepath.read_text(encoding='utf-8'))
    except (SyntaxError, PermissionError, UnicodeDecodeError):
        return violations

    # Flag the escape hatch wherever its result is CAPTURED: an assignment
    # (``conn = ...``), an annotated assignment (``conn: Any = ...``), or a return
    # (``return ...`` — the old wrapper-method shape). Call-in-argument-position and
    # ``with`` headers are intentionally NOT captured (see module docstring).
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.Return)):
            if node.value is not None and _is_get_connection_call(node.value):
                violations.append(f"{filepath}:{node.lineno}: {_HINT}")

    return violations


def _iter_py_files(root: Path, excluded_dirs: set[str] | None = None):
    """Yield .py files under root, skipping excluded directories.

    Args:
        root: Directory to scan recursively.
        excluded_dirs: Directory names to skip. Defaults to EXCLUDED_DIRS.

    Yields:
        Path objects for each .py file found.
    """
    if excluded_dirs is None:
        excluded_dirs = EXCLUDED_DIRS

    for entry in sorted(root.iterdir()):
        if entry.is_dir():
            if entry.name in excluded_dirs:
                continue
            yield from _iter_py_files(entry, excluded_dirs)
        elif entry.is_file() and entry.suffix == '.py':
            yield entry


def scan(root: Path, allowed_files: set[str] | None = None,
         pending_sites: set[str] | None = None,
         excluded_dirs: set[str] | None = None) -> list[str]:
    """Scan all .py files under root for Raw_Connection_Pattern violations.

    Args:
        root: Directory to scan recursively (e.g. ``Path('backend/src')``).
        allowed_files: Always-allowed files (posix-style, repo-root-relative). Defaults
            to ALLOWED_FILES.
        pending_sites: Known-pending files to skip. Defaults to PENDING_SITES.
        excluded_dirs: Directory names to skip. Defaults to EXCLUDED_DIRS.

    Returns:
        List of all violation message strings found.
    """
    if allowed_files is None:
        allowed_files = ALLOWED_FILES
    if pending_sites is None:
        pending_sites = PENDING_SITES

    all_violations = []
    for py_file in _iter_py_files(root, excluded_dirs):
        all_violations.extend(check_file(py_file, allowed_files, pending_sites))
    return all_violations


def main(argv=None):
    """CLI entry point.

    With no arguments, scans SCAN_DIRS (CI behavior). With one or more path arguments,
    checks only those files (single-file capability for the file-save hook, Req 1.7).
    Exits 0 when clean, 1 when violations are found.

    Args:
        argv: Optional explicit argument list. When None (the default, used by the
            ``__main__`` CLI call), falls back to ``sys.argv[1:]``. Tests pass an
            explicit list (``main([])`` for full-scan, ``main(['path.py'])`` for
            single-file) so pytest's own argv never leaks in.
    """
    paths = sys.argv[1:] if argv is None else argv
    all_violations = []

    if paths:
        # Single-file (or explicit-file-list) mode.
        for arg in paths:
            py_file = Path(arg)
            if not py_file.is_file() or py_file.suffix != '.py':
                continue
            all_violations.extend(check_file(py_file))
    else:
        # Full-scan mode (CI): walk SCAN_DIRS from repo root.
        root = Path('.')
        for scan_dir in SCAN_DIRS:
            dir_path = root / scan_dir
            if not dir_path.is_dir():
                continue
            all_violations.extend(scan(dir_path))

    if all_violations:
        print(f"Found {len(all_violations)} raw get_connection()/_get_connection() escape(s):\n")
        for v in all_violations:
            print(f"  [FAIL] {v}")
        print(
            "\nThe get_connection()/_get_connection() escape hatch is SEALED. These calls "
            "must go through the context-managed API: "
            "'with db.get_cursor() as (cursor, conn):' for reads, "
            "'with db.transaction() as (cursor, conn):' for writes. "
            "Do NOT re-add files to PENDING_SITES — migrate the call site."
        )
        sys.exit(1)
    else:
        print("[OK] No raw get_connection()/_get_connection() escape patterns found outside allowed files.")
        sys.exit(0)


if __name__ == '__main__':
    main()
