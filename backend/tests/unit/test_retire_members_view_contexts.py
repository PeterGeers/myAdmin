"""
Unit tests for the Members ``view_contexts`` retirement migration (Phase-2 step d).

Paired test for ``backend/src/migrations/retire_members_view_contexts.py`` (task 5.1).
Covers task 5.3: dry-run makes NO change; ``--apply`` deletes ONLY the targeted rows;
an idempotent re-run (nothing left to delete) is a safe no-op.

The ``migrate()`` entrypoint takes an injectable ``db`` handle, so these tests drive it
with the ``mock_db`` fixture (a mocked ``DatabaseManager``) from ``tests/conftest.py`` —
no real DB connection (the autouse connection guard in ``tests/unit/conftest.py`` raises
on a real connect). ``db.execute_query`` is the single DB seam: it is called once with a
parameterized ``SELECT COUNT(*)`` (``fetch=True``) for the scan, and — only on apply with
rows present — once more with a parameterized ``DELETE`` (``fetch=False, commit=True``).

Scoping is asserted through the query PARAMETERS: the WHERE clause binds
``scope='tenant'``, ``namespace='members'``, ``key='view_contexts'`` via ``%s``
placeholders — never a hardcoded tenant name, never string interpolation — so unrelated
params (other namespaces/keys, the surviving ``default_page_size``) cannot match.

Validates: Requirements 2.1, 2.6
Reference: .kiro/specs/Members/members-config-projection-and-cleanup/
"""

import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from migrations.retire_members_view_contexts import migrate

# The exact parameter tuple the migration must bind for BOTH the COUNT and the DELETE.
# (scope, namespace, key) — parameterized, no hardcoded tenant.
_EXPECTED_PARAMS = ("tenant", "members", "view_contexts")


def _count_rows(n):
    """Shape the SELECT COUNT(*) result the way execute_query(fetch=True) returns it:
    a list of dict rows with the ``n`` alias from the migration's COUNT query."""
    return [{"n": n}]


# ---------------------------------------------------------------------------
# DRY-RUN (default) makes NO change
# ---------------------------------------------------------------------------

def test_migrate_dry_run_with_matching_rows_counts_but_deletes_nothing(mock_db):
    """Dry-run scans N>0 rows, reports deleted=0, and issues NO DELETE.

    Validates: Requirements 2.1
    """
    mock_db.execute_query.return_value = _count_rows(3)

    summary = migrate(mock_db, dry_run=True)

    assert summary == {"scanned": 3, "deleted": 0}

    # Exactly ONE query ran — the SELECT COUNT scan. No DELETE was issued.
    mock_db.execute_query.assert_called_once()
    sql = mock_db.execute_query.call_args[0][0]
    assert "SELECT COUNT(*)" in sql
    assert "DELETE" not in sql.upper()

    # The scan was parameterized and read-only (fetch=True, no commit write).
    params = mock_db.execute_query.call_args[0][1]
    assert params == _EXPECTED_PARAMS
    assert mock_db.execute_query.call_args.kwargs.get("fetch") is True

    # Belt-and-suspenders: no call anywhere issued a DELETE or a committing write.
    for call in mock_db.execute_query.call_args_list:
        assert "DELETE" not in call.args[0].upper()
        assert call.kwargs.get("commit") is not True


def test_migrate_dry_run_is_the_default_mode(mock_db):
    """``migrate(db)`` with no dry_run arg defaults to dry-run — never writes.

    Validates: Requirements 2.1
    """
    mock_db.execute_query.return_value = _count_rows(5)

    summary = migrate(mock_db)  # dry_run defaults to True

    assert summary == {"scanned": 5, "deleted": 0}
    mock_db.execute_query.assert_called_once()
    assert "DELETE" not in mock_db.execute_query.call_args[0][0].upper()


# ---------------------------------------------------------------------------
# --APPLY deletes ONLY the targeted rows
# ---------------------------------------------------------------------------

def test_migrate_apply_deletes_only_targeted_rows_with_parameterized_query(mock_db):
    """Apply issues the parameterized DELETE bound to exactly the three target
    params and reports deleted == scanned.

    Validates: Requirements 2.1
    """
    # First execute_query call = COUNT (3 rows); second = DELETE (rowcount 3).
    mock_db.execute_query.side_effect = [_count_rows(3), 3]

    summary = migrate(mock_db, dry_run=False)

    assert summary == {"scanned": 3, "deleted": 3}

    # Two calls: the COUNT scan, then the DELETE.
    assert mock_db.execute_query.call_count == 2
    count_call, delete_call = mock_db.execute_query.call_args_list

    # The COUNT scan is parameterized and read-only.
    assert "SELECT COUNT(*)" in count_call.args[0]
    assert count_call.args[1] == _EXPECTED_PARAMS

    # The DELETE targets the parameters table, uses %s placeholders bound to the
    # three target values — NOT a hardcoded tenant, NOT string interpolation —
    # and is a committing write (fetch=False, commit=True).
    delete_sql = delete_call.args[0]
    assert "DELETE FROM parameters" in delete_sql
    assert "%s" in delete_sql
    assert delete_sql.count("%s") == 3  # one placeholder per bound param
    assert delete_call.args[1] == _EXPECTED_PARAMS
    assert delete_call.kwargs.get("fetch") is False
    assert delete_call.kwargs.get("commit") is True

    # Scoping lives in the WHERE clause params, so unrelated rows cannot match:
    # no tenant name, no other namespace/key is interpolated into the SQL text.
    assert "scope" in delete_sql
    assert "namespace" in delete_sql
    assert "`key`" in delete_sql
    # Nothing tenant-specific or namespace-specific is baked into the literal SQL.
    assert "members.view_contexts" not in delete_sql


def test_migrate_apply_reports_actual_deleted_rowcount(mock_db):
    """The summary ``deleted`` reflects the DELETE rowcount returned by the DB,
    not merely the scanned count.

    Validates: Requirements 2.1
    """
    # Scan sees 4, DELETE reports 4 affected rows.
    mock_db.execute_query.side_effect = [_count_rows(4), 4]

    summary = migrate(mock_db, dry_run=False)

    assert summary == {"scanned": 4, "deleted": 4}


# ---------------------------------------------------------------------------
# IDEMPOTENT re-run is a no-op
# ---------------------------------------------------------------------------

def test_migrate_apply_with_no_rows_is_idempotent_noop(mock_db):
    """When the scan finds 0 rows (already deleted), apply deletes nothing and
    issues NO DELETE — a safe, idempotent re-run.

    Validates: Requirements 2.1, 2.6
    """
    mock_db.execute_query.return_value = _count_rows(0)

    summary = migrate(mock_db, dry_run=False)

    assert summary == {"scanned": 0, "deleted": 0}

    # Only the COUNT scan ran; the apply short-circuited before any DELETE.
    mock_db.execute_query.assert_called_once()
    only_sql = mock_db.execute_query.call_args[0][0]
    assert "SELECT COUNT(*)" in only_sql
    assert "DELETE" not in only_sql.upper()


def test_migrate_dry_run_with_no_rows_is_noop(mock_db):
    """A dry-run against an already-retired surface (0 rows) is a clean no-op.

    Validates: Requirements 2.1, 2.6
    """
    mock_db.execute_query.return_value = _count_rows(0)

    summary = migrate(mock_db, dry_run=True)

    assert summary == {"scanned": 0, "deleted": 0}
    mock_db.execute_query.assert_called_once()
    assert "DELETE" not in mock_db.execute_query.call_args[0][0].upper()
