"""Direct unit tests for services/zzp_invoice_numbering.py.

Covers sequence allocation under a single row-locked transaction, padding
from the parameter system, and prefix resolution defaults.

Reference: .kiro/specs/ZZP/zzp-module/design.md section 5.3 (Req 5)
"""

from unittest.mock import MagicMock, Mock

from services.zzp_invoice_numbering import ZZPInvoiceNumberingHelper

TENANT = "test_admin"


def _db(existing_row=None):
    db = Mock()
    cursor = Mock()
    cursor.fetchone.return_value = existing_row
    ctx = MagicMock()
    ctx.__enter__.return_value = (cursor, Mock())
    db.transaction.return_value = ctx
    return db, cursor


def _params(values=None):
    values = values or {}
    svc = Mock()
    svc.get_param.side_effect = lambda ns, key, tenant=None: values.get(key)
    return svc


class TestGenerateInvoiceNumber:
    def test_first_invoice_inserts_sequence_row(self):
        db, cursor = _db()
        helper = ZZPInvoiceNumberingHelper(db)
        number = helper.generate_invoice_number(TENANT, "INV", 2026)
        assert number == "INV-2026-0001"
        insert_sql = cursor.execute.call_args_list[1][0][0]
        assert "INSERT INTO invoice_number_sequences" in insert_sql

    def test_existing_row_is_incremented(self):
        db, cursor = _db({"last_sequence": 41})
        helper = ZZPInvoiceNumberingHelper(db)
        assert helper.generate_invoice_number(TENANT, "INV", 2026) == "INV-2026-0042"
        update_sql = cursor.execute.call_args_list[1][0][0]
        assert "UPDATE invoice_number_sequences" in update_sql

    def test_locking_select_runs_inside_one_transaction(self):
        db, cursor = _db()
        helper = ZZPInvoiceNumberingHelper(db)
        helper.generate_invoice_number(TENANT, "INV", 2026)
        assert db.transaction.call_count == 1
        select_sql = cursor.execute.call_args_list[0][0][0]
        assert "FOR UPDATE" in select_sql

    def test_padding_comes_from_parameters(self):
        db, _cursor = _db()
        helper = ZZPInvoiceNumberingHelper(db, _params({"invoice_number_padding": 6}))
        assert helper.generate_invoice_number(TENANT, "INV", 2026) == "INV-2026-000001"

    def test_credit_note_prefix_can_be_used(self):
        db, _cursor = _db()
        helper = ZZPInvoiceNumberingHelper(db)
        assert helper.generate_invoice_number(TENANT, "CN", 2025) == "CN-2025-0001"


class TestPrefixes:
    def test_defaults(self):
        helper = ZZPInvoiceNumberingHelper(Mock())
        assert helper.get_invoice_prefix(TENANT) == "INV"
        assert helper.get_credit_note_prefix(TENANT) == "CN"

    def test_configured_prefixes(self):
        params = _params({"invoice_prefix": "F", "credit_note_prefix": "CR"})
        helper = ZZPInvoiceNumberingHelper(Mock(), params)
        assert helper.get_invoice_prefix(TENANT) == "F"
        assert helper.get_credit_note_prefix(TENANT) == "CR"
