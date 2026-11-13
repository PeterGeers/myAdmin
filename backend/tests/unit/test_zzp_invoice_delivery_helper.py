"""Direct unit tests for services/zzp_invoice_delivery.py.

Covers draft-only guards, PDF preview/storage, the send-flow ordering
(health check, PDF, storage, booking, status, email) and the soft-failure
email path.

Reference: .kiro/specs/ZZP/zzp-module/design.md section 14.7
"""

from io import BytesIO
from unittest.mock import Mock

import pytest

from services.zzp_invoice_delivery import ZZPInvoiceDeliveryHelper

TENANT = "test_admin"
DRAFT = {
    "id": 1,
    "invoice_number": "INV-2026-0001",
    "status": "draft",
    "invoice_type": "invoice",
    "contact": {"client_id": "C1"},
}


def _helper(**kwargs):
    db = Mock()
    return ZZPInvoiceDeliveryHelper(db=db, **kwargs), db


def _getter(invoice=None):
    value = dict(DRAFT if invoice is None else invoice)
    return lambda tenant, invoice_id: value if invoice_id == 1 else None


class TestPreview:
    def test_missing_invoice_raises(self):
        helper, _db = _helper()
        getter = _getter()
        with pytest.raises(ValueError, match="Invoice not found"):
            helper.preview_invoice(TENANT, 2, getter)

    def test_only_drafts_can_be_previewed(self):
        helper, _db = _helper()
        getter = _getter(dict(DRAFT, status="sent"))
        with pytest.raises(ValueError, match="Only draft invoices"):
            helper.preview_invoice(TENANT, 1, getter)

    def test_generator_must_be_configured(self):
        helper, _db = _helper()
        getter = _getter()
        with pytest.raises(RuntimeError, match="not configured"):
            helper.preview_invoice(TENANT, 1, getter)

    def test_preview_returns_generator_output(self):
        pdf = Mock()
        pdf.generate_preview_pdf.return_value = BytesIO(b"pdf")
        helper, _db = _helper(pdf_generator=pdf)
        assert helper.preview_invoice(TENANT, 1, _getter()).getvalue() == b"pdf"

    def test_generator_error_is_wrapped(self):
        pdf = Mock()
        pdf.generate_preview_pdf.side_effect = RuntimeError("boom")
        helper, _db = _helper(pdf_generator=pdf)
        getter = _getter()
        with pytest.raises(RuntimeError, match="PDF generation failed"):
            helper.preview_invoice(TENANT, 1, getter)


class TestEmailPreview:
    def test_missing_invoice_raises(self):
        helper, _db = _helper(email_service=Mock())
        getter = _getter()
        with pytest.raises(ValueError, match="Invoice not found"):
            helper.get_email_preview(TENANT, 2, getter)

    def test_non_draft_is_rejected(self):
        helper, _db = _helper(email_service=Mock())
        getter = _getter(dict(DRAFT, status="sent"))
        with pytest.raises(ValueError, match="Only draft invoices"):
            helper.get_email_preview(TENANT, 1, getter)

    def test_email_service_must_be_configured(self):
        helper, _db = _helper()
        getter = _getter()
        with pytest.raises(RuntimeError, match="not configured"):
            helper.get_email_preview(TENANT, 1, getter)

    def test_preview_is_delegated(self):
        email = Mock()
        email.compose_email_preview.return_value = {"subject": "Factuur"}
        helper, _db = _helper(email_service=email)
        getter = _getter()
        assert helper.get_email_preview(TENANT, 1, getter) == {"subject": "Factuur"}


class TestGetInvoicePdf:
    def test_missing_invoice_returns_none(self):
        helper, _db = _helper()
        getter = _getter()
        assert helper.get_invoice_pdf(TENANT, 2, getter) is None

    def test_stored_pdf_is_returned(self):
        helper, db = _helper()
        db.execute_query.return_value = [{"Ref3": "https://x/1.pdf", "Ref4": "f.pdf"}]
        getter = _getter()
        assert helper.get_invoice_pdf(TENANT, 1, getter) == {
            "url": "https://x/1.pdf",
            "filename": "f.pdf",
        }

    def test_missing_pdf_is_regenerated_as_copy(self):
        pdf = Mock()
        pdf.generate_copy_invoice_pdf.return_value = BytesIO(b"copy")
        helper, db = _helper(pdf_generator=pdf)
        db.execute_query.return_value = []
        getter = _getter()
        result = helper.get_invoice_pdf(TENANT, 1, getter)
        assert result["filename"] == "INV-2026-0001_COPY.pdf"
        assert result["content_type"] == "application/pdf"

    def test_without_generator_returns_none(self):
        helper, db = _helper()
        db.execute_query.return_value = []
        getter = _getter()
        assert helper.get_invoice_pdf(TENANT, 1, getter) is None


def _send_helper(healthy=True, store_url="u", email_ok=True):
    pdf = Mock()
    pdf.generate_invoice_pdf.return_value = BytesIO(b"pdf")
    out = Mock()
    out.check_health.return_value = {"healthy": healthy, "reason": "down"}
    out.handle_output.return_value = {"url": store_url}
    booking = Mock()
    email = Mock()
    email.send_invoice_email.return_value = {"success": email_ok, "error": "smtp"}
    helper = ZZPInvoiceDeliveryHelper(
        db=Mock(),
        pdf_generator=pdf,
        booking_helper=booking,
        email_service=email,
    )
    return helper, out, pdf, booking, email


class TestSendInvoice:
    def test_missing_invoice_raises(self):
        helper, out, _pdf, _b, _e = _send_helper()
        getter = _getter()
        with pytest.raises(ValueError, match="not found"):
            helper.send_invoice(TENANT, 2, {}, getter, out)

    def test_non_draft_is_rejected(self):
        helper, out, _pdf, _b, _e = _send_helper()
        getter = _getter(dict(DRAFT, status="sent"))
        with pytest.raises(ValueError, match="Only draft invoices"):
            helper.send_invoice(TENANT, 1, {}, getter, out)

    def test_unhealthy_storage_stops_before_pdf(self):
        helper, out, pdf, _b, _e = _send_helper(healthy=False)
        getter = _getter()
        result = helper.send_invoice(TENANT, 1, {}, getter, out)
        assert result["success"] is False
        assert "Storage unavailable" in result["error"]
        pdf.generate_invoice_pdf.assert_not_called()

    def test_storage_failure_reports_error(self):
        helper, out, _pdf, _b, _e = _send_helper(store_url="")
        getter = _getter()
        result = helper.send_invoice(TENANT, 1, {}, getter, out)
        assert result["success"] is False
        assert "no URL returned" in result["error"]

    def test_happy_path_books_status_and_emails(self):
        helper, out, _pdf, booking, email = _send_helper()
        getter = _getter()
        result = helper.send_invoice(TENANT, 1, {}, getter, out)
        assert result == {"success": True, "invoice_number": "INV-2026-0001"}
        booking.book_outgoing_invoice.assert_called_once()
        email.send_invoice_email.assert_called_once()
        update_sql = helper.db.execute_query.call_args[0][0]
        assert "UPDATE invoices SET status" in update_sql

    def test_email_failure_is_a_soft_warning(self):
        helper, out, _pdf, _booking, _email = _send_helper(email_ok=False)
        getter = _getter()
        result = helper.send_invoice(TENANT, 1, {}, getter, out)
        assert result["success"] is True
        assert "email failed" in result["warning"]

    def test_send_email_false_skips_email(self):
        helper, out, _pdf, _booking, email = _send_helper()
        getter = _getter()
        helper.send_invoice(TENANT, 1, {"send_email": False}, getter, out)
        email.send_invoice_email.assert_not_called()
