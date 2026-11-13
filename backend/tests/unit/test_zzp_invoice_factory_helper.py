"""Direct unit tests for services/zzp_invoice_factory.py.

Covers invoice-from-time-entries validation/line building, copying the last
invoice (date advancing), and the date-advance helper.

Reference: .kiro/specs/ZZP/zzp-module/design.md section 5.3
"""

from datetime import date
from unittest.mock import Mock

import pytest

from services.zzp_invoice_factory import ZZPInvoiceFactoryHelper

TENANT = "test_admin"
ENTRY = {
    "contact_id": 5,
    "is_billed": False,
    "product_id": None,
    "description": None,
    "entry_date": "2026-04-01",
    "hours": "2.5",
    "hourly_rate": "80",
}


def _factory(rows=None):
    db = Mock()
    db.execute_query.return_value = []
    if rows:
        db.execute_query.side_effect = rows
    return ZZPInvoiceFactoryHelper(db), db


def _time_service(entry=None):
    svc = Mock()
    svc.get_entry.return_value = dict(ENTRY, **(entry or {}))
    return svc


class TestCreateFromTimeEntries:
    def test_time_tracking_service_is_required(self):
        factory, _ = _factory()
        with pytest.raises(RuntimeError, match="TimeTrackingService required"):
            factory.create_invoice_from_time_entries(
                TENANT, 5, [1], {}, "tester", create_invoice_fn=Mock()
            )

    def test_missing_entry_is_rejected(self):
        factory, _ = _factory()
        tracker = Mock()
        tracker.get_entry.return_value = None
        with pytest.raises(ValueError, match="not found"):
            factory.create_invoice_from_time_entries(
                TENANT, 5, [9], {}, "tester", Mock(), tracker
            )

    def test_already_billed_entry_is_rejected(self):
        factory, _ = _factory()
        tracker = _time_service({"is_billed": True})
        with pytest.raises(ValueError, match="already billed"):
            factory.create_invoice_from_time_entries(
                TENANT, 5, [1], {}, "tester", Mock(), tracker
            )

    def test_entry_from_other_contact_is_rejected(self):
        factory, _ = _factory()
        tracker = _time_service({"contact_id": 9})
        with pytest.raises(ValueError, match="different contact"):
            factory.create_invoice_from_time_entries(
                TENANT, 5, [1], {}, "tester", Mock(), tracker
            )

    def test_lines_are_built_and_entries_marked_billed(self):
        factory, _ = _factory()
        tracker = _time_service()
        create = Mock(return_value={"id": 11})

        invoice = factory.create_invoice_from_time_entries(
            TENANT, 5, [1], {}, "tester", create, tracker
        )

        assert invoice == {"id": 11}
        payload = create.call_args[0][1]
        assert payload["contact_id"] == 5
        assert payload["lines"] == [
            {
                "product_id": None,
                "description": "Uren 2026-04-01",
                "quantity": 2.5,
                "unit_price": 80.0,
                "vat_code": "high",
            }
        ]
        tracker.mark_as_billed.assert_called_once_with(TENANT, [1], 11)

    def test_product_vat_code_is_used_when_present(self):
        factory, _ = _factory(rows=[[{"vat_code": "low"}]])
        tracker = _time_service({"product_id": 3})
        create = Mock(return_value={"id": 12})

        factory.create_invoice_from_time_entries(
            TENANT, 5, [1], {}, "tester", create, tracker
        )

        assert create.call_args[0][1]["lines"][0]["vat_code"] == "low"


class TestCopyLastInvoice:
    def test_no_previous_invoice_raises(self):
        factory, _ = _factory(rows=[[]])
        with pytest.raises(ValueError, match="No previous invoice"):
            factory.copy_last_invoice(TENANT, 5, "tester", Mock())

    def test_lines_are_copied_and_source_id_recorded(self):
        last = {
            "id": 3,
            "invoice_date": "2026-01-31",
            "payment_terms_days": 14,
            "currency": "EUR",
            "revenue_account": "8000",
            "notes": "n",
        }
        lines = [
            {
                "product_id": None,
                "description": "Werk",
                "quantity": "1",
                "unit_price": "10",
                "vat_code": "high",
                "sort_order": 0,
            }
        ]
        factory, _db = _factory(rows=[[last], lines])
        factory._advance_date = Mock(return_value=date(2026, 2, 28))
        create = Mock(return_value={"id": 4})

        invoice = factory.copy_last_invoice(TENANT, 5, "tester", create)

        assert invoice == {"id": 4, "copied_from_invoice_id": 3}
        payload = create.call_args[0][1]
        assert payload["invoice_date"] == "2026-02-28"
        assert payload["payment_terms_days"] == 14
        assert payload["lines"][0]["description"] == "Werk"


class TestAdvanceDate:
    def test_gap_between_last_two_invoices_is_reused(self):
        factory, _db = _factory(
            rows=[[{"invoice_date": "2026-03-01"}, {"invoice_date": "2026-02-01"}]]
        )
        assert factory._advance_date(TENANT, 5, date(2026, 3, 1)) == date(2026, 3, 29)

    def test_single_invoice_defaults_to_one_month(self):
        factory, _db = _factory(rows=[[{"invoice_date": "2026-03-01"}]])
        assert factory._advance_date(TENANT, 5, date(2026, 3, 1)) == date(2026, 4, 1)

    def test_end_of_month_is_clamped(self):
        factory, _db = _factory(rows=[])
        assert factory._advance_date(TENANT, 5, date(2026, 1, 31)) == date(2026, 2, 28)

    def test_december_rolls_into_next_year(self):
        factory, _db = _factory(rows=[])
        assert factory._advance_date(TENANT, 5, date(2025, 12, 15)) == date(2026, 1, 15)
