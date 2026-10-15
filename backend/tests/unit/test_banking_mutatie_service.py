"""Unit tests for BankingMutatieService (direct).

High-risk DB/money service: paginated transaction query + tenant-forced update.
BankingService delegates to this class, but this file exercises it directly so
the money/tenant/error behavior is pinned at its own seam.

Covers:
- Tenant scoping on reads: 'all' with a single tenant, 'all' with multiple
  tenants (IN-list), explicit administration access-denied path
- Pagination metadata (limit cap, has_more) and date → ISO coercion
- update_mutatie: success commits via transaction(), record-not-found and
  cross-tenant access-denied abort BEFORE any write, and the UPDATE always
  forces `administration` to the current tenant (defense in depth)
- Exception paths return {'success': False, 'error': ...}

Uses a mocked DatabaseManager (unit conftest guard blocks real connections).
"""

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from services.banking_mutatie_service import BankingMutatieService


@pytest.fixture
def service(mock_db):
    """BankingMutatieService whose DatabaseManager() resolves to the shared mock."""
    with patch(
        "services.banking_mutatie_service.DatabaseManager", return_value=mock_db
    ):
        svc = BankingMutatieService()
        svc._mock_db = mock_db
        yield svc


def _setup_read_cursor(service, rows, total):
    """Configure the get_cursor_only() read context manager."""
    cursor = MagicMock()
    cursor.fetchone.return_value = {"total": total}
    cursor.fetchall.return_value = rows
    cm = MagicMock()
    cm.__enter__.return_value = cursor
    cm.__exit__.return_value = False
    service._mock_db.get_cursor_only.return_value = cm
    return cursor


def _setup_write_cursor(service, existing_record):
    """Configure the transaction() write context manager."""
    cursor = MagicMock()
    conn = MagicMock()
    cursor.fetchone.return_value = existing_record
    cm = MagicMock()
    cm.__enter__.return_value = (cursor, conn)
    cm.__exit__.return_value = False
    service._mock_db.transaction.return_value = cm
    return cursor


# ---------------------------------------------------------------------------
# get_mutaties — tenant scoping
# ---------------------------------------------------------------------------

class TestGetMutatiesTenantScoping:
    def test_all_with_single_tenant_filters_to_that_tenant(self, service):
        """administration='all' + one accessible tenant → equality filter on it."""
        cursor = _setup_read_cursor(service, rows=[{"ID": 1, "TransactionDate": None}], total=1)

        result = service.get_mutaties(
            filters={"administration": "all", "years": [""]},
            tenant="T1",
            user_tenants=["T1"],
        )

        assert result["success"] is True
        # COUNT query is scoped to the single tenant. (get_mutaties reuses one
        # params list for COUNT then extends it with [limit, offset] for the
        # SELECT, so the captured list starts with the WHERE params.)
        count_params = cursor.execute.call_args_list[0][0][1]
        assert count_params[:1] == ["T1"]

    def test_all_with_multiple_tenants_uses_in_list(self, service):
        """administration='all' + multiple tenants → IN (...) over all of them."""
        cursor = _setup_read_cursor(service, rows=[], total=0)

        service.get_mutaties(
            filters={"administration": "all", "years": [""]},
            tenant="T1",
            user_tenants=["T1", "T2", "T3"],
        )

        count_sql = cursor.execute.call_args_list[0][0][0]
        count_params = cursor.execute.call_args_list[0][0][1]
        assert "administration IN (%s,%s,%s)" in count_sql
        assert count_params[:3] == ["T1", "T2", "T3"]

    def test_explicit_administration_not_in_user_tenants_denied(self, service):
        """Requesting an administration the user cannot access → access denied, no query."""
        result = service.get_mutaties(
            filters={"administration": "OtherTenant", "years": [""]},
            tenant="T1",
            user_tenants=["T1", "T2"],
        )

        assert result["success"] is False
        assert result["error"] == "Access denied to administration"
        # No DB read should have happened on the denied path.
        service._mock_db.get_cursor_only.assert_not_called()

    def test_explicit_administration_in_user_tenants_filters_to_it(self, service):
        """A permitted explicit administration → equality filter on exactly that value."""
        cursor = _setup_read_cursor(service, rows=[{"ID": 7, "TransactionDate": None}], total=1)

        result = service.get_mutaties(
            filters={"administration": "T2", "years": [""]},
            tenant="T1",
            user_tenants=["T1", "T2"],
        )

        assert result["success"] is True
        count_params = cursor.execute.call_args_list[0][0][1]
        assert count_params[:1] == ["T2"]


# ---------------------------------------------------------------------------
# get_mutaties — pagination & formatting
# ---------------------------------------------------------------------------

class TestGetMutatiesPagination:
    def test_pagination_metadata_has_more_true(self, service):
        rows = [{"ID": i, "TransactionDate": None} for i in range(10)]
        _setup_read_cursor(service, rows=rows, total=50)

        result = service.get_mutaties(
            filters={"administration": "all", "years": [""], "limit": "10", "offset": "0"},
            tenant="T1",
            user_tenants=["T1"],
        )

        assert result["limit"] == 10
        assert result["offset"] == 0
        assert result["count"] == 10
        assert result["total"] == 50
        assert result["has_more"] is True

    def test_limit_capped_at_100000(self, service):
        """An abusive limit is capped; the SELECT LIMIT param reflects the cap."""
        cursor = _setup_read_cursor(service, rows=[], total=0)

        result = service.get_mutaties(
            filters={"administration": "all", "years": [""], "limit": "999999"},
            tenant="T1",
            user_tenants=["T1"],
        )

        assert result["limit"] == 100000
        # The second execute (SELECT) appends [limit, offset]; limit must be capped.
        select_params = cursor.execute.call_args_list[1][0][1]
        assert select_params[-2] == 100000  # limit
        assert select_params[-1] == 0  # offset

    def test_date_coerced_to_iso_string(self, service):
        _setup_read_cursor(
            service,
            rows=[{"ID": 1, "TransactionDate": date(2025, 3, 15)}],
            total=1,
        )

        result = service.get_mutaties(
            filters={"administration": "all", "years": [""]},
            tenant="T1",
            user_tenants=["T1"],
        )

        assert result["mutaties"][0]["TransactionDate"] == "2025-03-15"

    def test_db_error_returns_failure(self, service):
        """A DB exception is swallowed into {'success': False, 'error': ...}."""
        service._mock_db.get_cursor_only.side_effect = RuntimeError("connection lost")

        result = service.get_mutaties(
            filters={"administration": "all", "years": [""]},
            tenant="T1",
            user_tenants=["T1"],
        )

        assert result["success"] is False
        assert "connection lost" in result["error"]


# ---------------------------------------------------------------------------
# update_mutatie — tenant force & abort paths
# ---------------------------------------------------------------------------

VALID_UPDATE = {
    "TransactionNumber": "T001",
    "TransactionDate": "2025-01-15",
    "TransactionDescription": "Updated",
    "TransactionAmount": 123.45,
    "Debet": "1300",
    "Credit": "8000",
    "ReferenceNumber": "REF1",
    "Ref1": "NL80RABO0107936917",
    "Ref2": "001",
    "Ref3": None,
    "Ref4": None,
}


class TestUpdateMutatie:
    def test_update_success_commits_via_transaction(self, service):
        cursor = _setup_write_cursor(service, {"administration": "T1"})

        result = service.update_mutatie(42, dict(VALID_UPDATE), "T1")

        assert result["success"] is True
        service._mock_db.transaction.assert_called_once()
        update_calls = [c for c in cursor.execute.call_args_list if "UPDATE" in c[0][0]]
        assert len(update_calls) == 1

    def test_update_preserves_amount_exactly(self, service):
        """Money value is passed through to the UPDATE unmodified."""
        cursor = _setup_write_cursor(service, {"administration": "T1"})

        service.update_mutatie(42, dict(VALID_UPDATE), "T1")

        update_call = [c for c in cursor.execute.call_args_list if "UPDATE" in c[0][0]][0]
        params = update_call[0][1]
        # Param order mirrors the UPDATE: amount is the 4th SET value.
        assert params[3] == 123.45

    def test_update_record_not_found_aborts(self, service):
        cursor = _setup_write_cursor(service, None)

        result = service.update_mutatie(999, dict(VALID_UPDATE), "T1")

        assert result["success"] is False
        assert "not found" in result["error"].lower()
        # Guard returns before any UPDATE executes.
        update_calls = [c for c in cursor.execute.call_args_list if "UPDATE" in c[0][0]]
        assert update_calls == []

    def test_update_cross_tenant_denied_aborts(self, service):
        cursor = _setup_write_cursor(service, {"administration": "OtherTenant"})

        result = service.update_mutatie(42, dict(VALID_UPDATE), "T1")

        assert result["success"] is False
        assert "Access denied" in result["error"]
        update_calls = [c for c in cursor.execute.call_args_list if "UPDATE" in c[0][0]]
        assert update_calls == []

    def test_update_forces_current_tenant_in_write(self, service):
        """Even if payload tried another administration, the write forces `tenant`."""
        cursor = _setup_write_cursor(service, {"administration": "T1"})

        service.update_mutatie(42, dict(VALID_UPDATE), "T1")

        update_call = [c for c in cursor.execute.call_args_list if "UPDATE" in c[0][0]][0]
        params = update_call[0][1]
        # Trailing params: (..., administration, mutatie_id)
        assert params[-2] == "T1"
        assert params[-1] == 42

    def test_update_exception_returns_failure(self, service):
        service._mock_db.transaction.side_effect = RuntimeError("deadlock")

        result = service.update_mutatie(42, dict(VALID_UPDATE), "T1")

        assert result["success"] is False
        assert "deadlock" in result["error"]
