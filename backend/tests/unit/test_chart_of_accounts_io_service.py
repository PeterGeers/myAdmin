"""Direct unit tests for services/chart_of_accounts_io_service.py.

Covers Excel export shape/filename/count and the import upsert path
(insert vs update), plus the parse-error envelope.

Reference: .kiro/specs/missing-py-tests/design.md
"""

from io import BytesIO
from unittest.mock import Mock

import openpyxl

from services.chart_of_accounts_io_service import (
    EXCEL_HEADERS,
    ChartOfAccountsIOService,
)

TENANT = "test_admin"


def _workbook_bytes(rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(EXCEL_HEADERS)
    for row in rows:
        ws.append(row)
    out = BytesIO()
    wb.save(out)
    out.seek(0)
    return out


class TestExport:
    def test_rows_headers_and_count(self):
        db = Mock()
        db.execute_query.return_value = [
            {
                "Account": "1000",
                "AccountName": "Kas",
                "AccountLookup": "1000",
                "SubParent": "",
                "Parent": "",
                "VW": "",
                "Belastingaangifte": "",
                "bank_account": 1,
            }
        ]
        stream, filename, count = ChartOfAccountsIOService(db).export_to_excel(TENANT)

        assert count == 1
        assert filename.startswith("chart_of_accounts_" + TENANT)
        assert filename.endswith(".xlsx")
        assert stream.tell() == 0

        ws = openpyxl.load_workbook(stream).active
        rows = list(ws.iter_rows(values_only=True))
        assert list(rows[0]) == EXCEL_HEADERS
        assert rows[1][0] == "1000"
        assert rows[1][1] == "Kas"
        assert rows[1][7] == 1

    def test_tenant_scoped_query_parameters(self):
        db = Mock()
        db.execute_query.return_value = []
        _stream, _name, count = ChartOfAccountsIOService(db).export_to_excel(TENANT)
        assert count == 0
        assert db.execute_query.call_args[0][1] == (TENANT,)


class TestImport:
    def test_unparseable_stream_returns_error_envelope(self):
        result = ChartOfAccountsIOService(Mock()).import_from_excel(
            TENANT, BytesIO(b"not an excel file")
        )
        assert result["success"] is False
        assert result["error"] == "Failed to parse Excel file"

    def test_wrong_headers_are_rejected(self):
        wb = openpyxl.Workbook()
        wb.active.append(["Nope"])
        stream = BytesIO()
        wb.save(stream)
        stream.seek(0)

        result = ChartOfAccountsIOService(Mock()).import_from_excel(TENANT, stream)
        assert result["success"] is False
        assert result["error"] == "Invalid Excel format"

    def test_missing_account_or_name_collects_errors(self):
        stream = _workbook_bytes(
            [
                [None, "Naam", None, None, None, None, None, None],
                ["1000", None, None, None, None, None, None, None],
            ]
        )
        result = ChartOfAccountsIOService(Mock()).import_from_excel(TENANT, stream)
        assert result["success"] is False
        assert result["parsed"] == 0
        assert result["errors"] == [
            "Row 2: Account number required",
            "Row 3: Account name required",
        ]

    def test_new_account_is_inserted(self):
        db = Mock()
        db.execute_query.side_effect = [[], Mock()]
        stream = _workbook_bytes([["1000", "Kas", "1000", "", "", "", "", None]])

        result = ChartOfAccountsIOService(db).import_from_excel(TENANT, stream)

        assert result == {"success": True, "imported": 1, "updated": 0, "total": 1}
        insert_sql = db.execute_query.call_args_list[1][0][0]
        assert "INSERT INTO rekeningschema" in insert_sql

    def test_existing_account_is_updated(self):
        db = Mock()
        db.execute_query.side_effect = [[{"1": 1}], Mock()]
        stream = _workbook_bytes([["1000", "Kas", "1000", "", "", "", "", None]])

        result = ChartOfAccountsIOService(db).import_from_excel(TENANT, stream)

        assert result == {"success": True, "imported": 0, "updated": 1, "total": 1}
        update_sql = db.execute_query.call_args_list[1][0][0]
        assert "UPDATE rekeningschema" in update_sql

    def test_bank_flag_serialises_parameters_json(self):
        db = Mock()
        db.execute_query.side_effect = [[], Mock()]
        stream = _workbook_bytes([["1000", "Bank", "NL01", "", "", "", "", 1]])

        ChartOfAccountsIOService(db).import_from_excel(TENANT, stream)

        params = db.execute_query.call_args_list[1][0][1]
        assert '"bank_account": true' in params[-1]
        assert '"iban": "NL01"' in params[-1]
