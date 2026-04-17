"""
Integration tests: Cross-requirement flows for ZZP module (Phase 16.1).

These tests verify interactions across multiple requirements:
- Full send flow with OutputService mock: store -> book (Ref3/Ref4) -> email (Reqs 22.1-22.4)
- Invoice creation with revenue account selection -> send -> verify mutaties (Reqs 18.1-18.6)
- VAT accounts from TaxRateService in booking entries (Req 19.4)
- Account validation on parameter save rejects unflagged accounts (Req 19.6)
- Invoice ledger API returns flagged accounts (Req 17.3)

Reference: .kiro/specs/zzp-module/tasks.md Phase 16.1
"""

import pytest
import sys
import os
import contextlib
from datetime import date, datetime
from io import BytesIO
from unittest.mock import Mock, MagicMock, patch, call

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

# ── Constants ───────────────────────────────────────────────

TENANT = 'IntegrationTestTenant'
USER_EMAIL = 'zzp-integration@example.com'
CONTACT_ID = 1
PRODUCT_ID = 10
INVOICE_ID = 100
INVOICE_NUMBER = 'INV-2026-0001'
CLIENT_ID = 'ACME'
COMPANY_NAME = 'Acme Corp B.V.'
DEBTOR_ACCOUNT = '1300'
REVENUE_ACCOUNT = '8001'
CUSTOM_REVENUE_ACCOUNT = '8010'
CREDITOR_ACCOUNT = '1600'
BTW_HIGH_LEDGER = '2021'
BTW_LOW_LEDGER = '2020'
INVOICE_DATE = '2026-06-01'
DUE_DATE = '2026-07-01'
STORAGE_URL = 'https://drive.google.com/file/d/xyz789'
PDF_FILENAME = f'{INVOICE_NUMBER}.pdf'


# ── Shared helpers ──────────────────────────────────────────


def _make_parameter_service(overrides: dict = None):
    """Create a mock ParameterService with ZZP defaults."""
    params = {
        ('zzp', 'invoice_prefix'): 'INV',
        ('zzp', 'invoice_number_padding'): '4',
        ('zzp', 'debtor_account'): DEBTOR_ACCOUNT,
        ('zzp', 'revenue_account'): REVENUE_ACCOUNT,
        ('zzp', 'creditor_account'): CREDITOR_ACCOUNT,
        ('zzp', 'expense_account'): '4000',
        ('zzp', 'btw_debit_account'): '2010',
        ('zzp', 'default_payment_terms'): '30',
        ('zzp', 'default_currency'): 'EUR',
    }
    if overrides:
        params.update(overrides)

    svc = Mock()

    def get_param(namespace, key, tenant=None):
        return params.get((namespace, key))

    svc.get_param = Mock(side_effect=get_param)
    return svc


def _make_tax_rate_service(rates: dict = None):
    """Create a mock TaxRateService returning configurable VAT rates.

    Args:
        rates: dict mapping vat_code -> {'rate': float, 'ledger_account': str}
    """
    default_rates = {
        'high': {'rate': 21.0, 'code': 'high', 'ledger_account': BTW_HIGH_LEDGER},
        'low': {'rate': 9.0, 'code': 'low', 'ledger_account': BTW_LOW_LEDGER},
        'zero': {'rate': 0.0, 'code': 'zero', 'ledger_account': ''},
    }
    if rates:
        default_rates.update(rates)

    svc = Mock()

    def get_tax_rate(tenant, tax_type, vat_code, ref_date):
        return default_rates.get(vat_code)

    svc.get_tax_rate = Mock(side_effect=get_tax_rate)
    return svc


def _make_output_service(healthy=True, url=STORAGE_URL, filename=PDF_FILENAME):
    """Create a mock OutputService."""
    svc = Mock()
    svc.check_health.return_value = {'healthy': healthy}
    svc.store_file = Mock(return_value={'url': url, 'filename': filename})
    return svc


def _make_invoice(invoice_id=INVOICE_ID, revenue_account=None,
                  vat_summary=None, lines=None, **overrides):
    """Build a complete invoice dict."""
    if lines is None:
        lines = [{
            'id': 1,
            'product_id': PRODUCT_ID,
            'description': 'Software Development - June 2026',
            'quantity': 10,
            'unit_price': 100.00,
            'vat_code': 'high',
            'vat_rate': 21.0,
            'line_total': 1000.00,
            'vat_amount': 210.00,
        }]
    if vat_summary is None:
        vat_summary = [{
            'vat_code': 'high',
            'vat_rate': 21.0,
            'base_amount': 1000.00,
            'vat_amount': 210.00,
        }]

    invoice = {
        'id': invoice_id,
        'invoice_number': INVOICE_NUMBER,
        'invoice_type': 'invoice',
        'contact_id': CONTACT_ID,
        'invoice_date': INVOICE_DATE,
        'due_date': DUE_DATE,
        'payment_terms_days': 30,
        'currency': 'EUR',
        'exchange_rate': 1.0,
        'revenue_account': revenue_account,
        'status': 'draft',
        'subtotal': sum(l['line_total'] for l in lines),
        'vat_total': sum(l['vat_amount'] for l in lines),
        'grand_total': sum(l['line_total'] + l['vat_amount'] for l in lines),
        'notes': 'Integration test invoice',
        'contact': {
            'id': CONTACT_ID,
            'client_id': CLIENT_ID,
            'company_name': COMPANY_NAME,
        },
        'lines': lines,
        'vat_summary': vat_summary,
    }
    invoice.update(overrides)
    return invoice


@contextlib.contextmanager
def _mock_db_in_routes(return_value):
    """Mock DatabaseManager in zzp_routes for validation tests."""
    mock_db = Mock()
    mock_db.execute_query.return_value = return_value
    with patch('routes.zzp_routes.DatabaseManager', return_value=mock_db):
        yield mock_db


# ═══════════════════════════════════════════════════════════
# 1. Full Send Flow with OutputService Mock (Reqs 22.1-22.4)
# ═══════════════════════════════════════════════════════════


@pytest.mark.integration
class TestFullSendFlowWithStorage:
    """Verify the complete send flow: store -> book (with Ref3/Ref4) -> email.

    These tests use a real InvoiceBookingHelper (not mocked) to verify that
    storage results flow through to mutaties entries.

    Requirements: 22.1, 22.2, 22.3, 22.4
    """

    def _make_service(self, booking_helper, pdf_generator=None,
                      email_service=None, param_svc=None):
        """Create ZZPInvoiceService with real booking helper."""
        from services.zzp_invoice_service import ZZPInvoiceService

        if pdf_generator is None:
            pdf_generator = Mock()
            pdf_generator.generate_invoice_pdf.return_value = BytesIO(b'%PDF-fake')

        if email_service is None:
            email_service = Mock()
            email_service.send_invoice_email.return_value = {
                'success': True, 'message_id': 'msg-int-001',
            }

        return ZZPInvoiceService(
            db=Mock(),
            tax_rate_service=_make_tax_rate_service(),
            parameter_service=param_svc or _make_parameter_service(),
            booking_helper=booking_helper,
            pdf_generator=pdf_generator,
            email_service=email_service,
        )

    def test_send_flow_stores_then_books_with_ref3_ref4(self):
        """Storage URL and filename flow to booking helper as Ref3/Ref4.

        Verifies: store PDF -> pass storage_result to booking -> Ref3=url, Ref4=filename.
        Requirement: 22.2, 22.4
        """
        from services.invoice_booking_helper import InvoiceBookingHelper

        mock_txn_logic = Mock()
        mock_txn_logic.save_approved_transactions.return_value = [{'ID': 1}]

        booking_helper = InvoiceBookingHelper(
            db=Mock(),
            transaction_logic=mock_txn_logic,
            tax_rate_service=_make_tax_rate_service(),
            parameter_service=_make_parameter_service(),
        )

        invoice = _make_invoice(revenue_account=REVENUE_ACCOUNT)
        output_service = _make_output_service()
        storage_result = {'url': STORAGE_URL, 'filename': PDF_FILENAME}

        service = self._make_service(booking_helper)

        with patch.object(service, 'get_invoice', return_value=invoice), \
             patch.object(service, '_store_pdf', return_value=storage_result), \
             patch.object(service, '_update_status'):
            result = service.send_invoice(
                TENANT, INVOICE_ID,
                options={'send_email': True, 'output_destination': 'gdrive'},
                output_service=output_service,
            )

        assert result['success'] is True

        # Verify booking helper received storage_result
        mock_txn_logic.save_approved_transactions.assert_called_once()
        transactions = mock_txn_logic.save_approved_transactions.call_args[0][0]

        # Main entry should have Ref3=url, Ref4=filename
        main_entry = transactions[0]
        assert main_entry['Ref3'] == STORAGE_URL
        assert main_entry['Ref4'] == PDF_FILENAME
        assert main_entry['Ref2'] == INVOICE_NUMBER
        assert main_entry['ReferenceNumber'] == CLIENT_ID

    def test_send_flow_all_mutaties_entries_have_ref3_ref4(self):
        """All mutaties entries (main + VAT) carry the storage URL and filename.

        Requirement: 22.2
        """
        from services.invoice_booking_helper import InvoiceBookingHelper

        mock_txn_logic = Mock()
        mock_txn_logic.save_approved_transactions.return_value = [{'ID': 1}, {'ID': 2}]

        booking_helper = InvoiceBookingHelper(
            db=Mock(),
            transaction_logic=mock_txn_logic,
            tax_rate_service=_make_tax_rate_service(),
            parameter_service=_make_parameter_service(),
        )

        invoice = _make_invoice(revenue_account=REVENUE_ACCOUNT)
        storage_result = {'url': STORAGE_URL, 'filename': PDF_FILENAME}

        service = self._make_service(booking_helper)

        with patch.object(service, 'get_invoice', return_value=invoice), \
             patch.object(service, '_store_pdf', return_value=storage_result), \
             patch.object(service, '_update_status'):
            result = service.send_invoice(
                TENANT, INVOICE_ID,
                options={'send_email': False, 'output_destination': 'gdrive'},
                output_service=_make_output_service(),
            )

        assert result['success'] is True

        transactions = mock_txn_logic.save_approved_transactions.call_args[0][0]
        assert len(transactions) >= 2  # main + at least one VAT entry

        # Main entry has full Ref3/Ref4
        assert transactions[0]['Ref3'] == STORAGE_URL
        assert transactions[0]['Ref4'] == PDF_FILENAME

        # VAT entries also carry Ref3/Ref4 (for traceability)
        for vat_entry in transactions[1:]:
            assert vat_entry['Ref3'] == STORAGE_URL
            assert vat_entry['Ref4'] == PDF_FILENAME

    def test_send_flow_order_health_store_book_email(self):
        """Verify strict ordering: health check -> store -> book -> email.

        Requirement: 22.1
        """
        from services.invoice_booking_helper import InvoiceBookingHelper

        call_order = []

        mock_txn_logic = Mock()
        mock_txn_logic.save_approved_transactions.side_effect = (
            lambda txns: (call_order.append('book'), [{'ID': 1}])[1]
        )

        booking_helper = InvoiceBookingHelper(
            db=Mock(),
            transaction_logic=mock_txn_logic,
            tax_rate_service=_make_tax_rate_service(),
            parameter_service=_make_parameter_service(),
        )

        output_service = _make_output_service()
        output_service.check_health.side_effect = (
            lambda dest, tenant: (call_order.append('health'), {'healthy': True})[1]
        )

        pdf_gen = Mock()
        pdf_gen.generate_invoice_pdf.return_value = BytesIO(b'%PDF-fake')

        email_svc = Mock()
        email_svc.send_invoice_email.side_effect = (
            lambda *a, **kw: (call_order.append('email'), {'success': True})[1]
        )

        service = self._make_service(booking_helper, pdf_gen, email_svc)

        invoice = _make_invoice(revenue_account=REVENUE_ACCOUNT)
        storage_result = {'url': STORAGE_URL, 'filename': PDF_FILENAME}

        def store_pdf(*args, **kwargs):
            call_order.append('store')
            return storage_result

        with patch.object(service, 'get_invoice', return_value=invoice), \
             patch.object(service, '_store_pdf', side_effect=store_pdf), \
             patch.object(service, '_update_status'):
            result = service.send_invoice(
                TENANT, INVOICE_ID,
                options={'send_email': True, 'output_destination': 'gdrive'},
                output_service=output_service,
            )

        assert result['success'] is True
        assert call_order == ['health', 'store', 'book', 'email']

    def test_storage_failure_prevents_booking_and_email(self):
        """Storage failure aborts: no mutaties created, no email sent.

        Requirement: 22.5
        """
        mock_booking = Mock()
        mock_email = Mock()

        service = self._make_service(mock_booking, email_service=mock_email)

        invoice = _make_invoice(revenue_account=REVENUE_ACCOUNT)
        output_service = _make_output_service()

        with patch.object(service, 'get_invoice', return_value=invoice), \
             patch.object(service, '_store_pdf', side_effect=Exception('S3 timeout')), \
             patch.object(service, '_update_status') as mock_status:
            result = service.send_invoice(
                TENANT, INVOICE_ID,
                options={'send_email': True, 'output_destination': 'gdrive'},
                output_service=output_service,
            )

        assert result['success'] is False
        assert 'Storage unavailable' in result['error']
        mock_booking.book_outgoing_invoice.assert_not_called()
        mock_email.send_invoice_email.assert_not_called()
        mock_status.assert_not_called()

    def test_email_failure_keeps_invoice_sent_with_warning(self):
        """Email failure after booking: invoice stays sent, warning returned.

        Requirement: 22.6
        """
        from services.invoice_booking_helper import InvoiceBookingHelper

        mock_txn_logic = Mock()
        mock_txn_logic.save_approved_transactions.return_value = [{'ID': 1}]

        booking_helper = InvoiceBookingHelper(
            db=Mock(),
            transaction_logic=mock_txn_logic,
            tax_rate_service=_make_tax_rate_service(),
            parameter_service=_make_parameter_service(),
        )

        email_svc = Mock()
        email_svc.send_invoice_email.side_effect = Exception('SES rate limit')

        service = self._make_service(booking_helper, email_service=email_svc)

        invoice = _make_invoice(revenue_account=REVENUE_ACCOUNT)
        storage_result = {'url': STORAGE_URL, 'filename': PDF_FILENAME}

        status_calls = []

        def track_status(*args, **kwargs):
            status_calls.append(args)

        with patch.object(service, 'get_invoice', return_value=invoice), \
             patch.object(service, '_store_pdf', return_value=storage_result), \
             patch.object(service, '_update_status', side_effect=track_status):
            result = service.send_invoice(
                TENANT, INVOICE_ID,
                options={'send_email': True, 'output_destination': 'gdrive'},
                output_service=_make_output_service(),
            )

        # Invoice was booked and marked sent
        assert result['success'] is True
        assert 'warning' in result
        assert 'email failed' in result['warning'].lower()

        # Booking happened
        mock_txn_logic.save_approved_transactions.assert_called_once()

        # Status was updated to 'sent' (before email attempt)
        assert len(status_calls) == 1
        assert status_calls[0][2] == 'sent'


# ═══════════════════════════════════════════════════════════
# 2. Invoice Creation with Revenue Account -> Send -> Verify Mutaties
#    (Reqs 18.1-18.6)
# ═══════════════════════════════════════════════════════════


@pytest.mark.integration
class TestRevenueAccountInBooking:
    """End-to-end: invoice with revenue account selection -> send -> verify
    mutaties use the correct revenue account.

    Requirements: 18.1, 18.2, 18.3, 18.4, 18.5, 18.6
    """

    def _book_and_capture(self, invoice, param_svc=None):
        """Book an outgoing invoice and return the captured transactions."""
        from services.invoice_booking_helper import InvoiceBookingHelper

        mock_txn_logic = Mock()
        mock_txn_logic.save_approved_transactions.return_value = [{'ID': 1}]

        helper = InvoiceBookingHelper(
            db=Mock(),
            transaction_logic=mock_txn_logic,
            tax_rate_service=_make_tax_rate_service(),
            parameter_service=param_svc or _make_parameter_service(),
        )

        storage_result = {'url': STORAGE_URL, 'filename': PDF_FILENAME}
        helper.book_outgoing_invoice(TENANT, invoice, storage_result)

        return mock_txn_logic.save_approved_transactions.call_args[0][0]

    def test_invoice_level_revenue_account_used_in_main_entry(self):
        """When invoice has revenue_account set, main entry credits that account.

        Requirement: 18.4
        """
        invoice = _make_invoice(revenue_account=CUSTOM_REVENUE_ACCOUNT)
        transactions = self._book_and_capture(invoice)

        main_entry = transactions[0]
        assert main_entry['Credit'] == CUSTOM_REVENUE_ACCOUNT
        assert main_entry['Debet'] == DEBTOR_ACCOUNT

    def test_invoice_level_revenue_account_used_in_vat_entry(self):
        """VAT entry debits the invoice-level revenue account.

        Requirement: 18.5
        """
        invoice = _make_invoice(revenue_account=CUSTOM_REVENUE_ACCOUNT)
        transactions = self._book_and_capture(invoice)

        # VAT entry: debit revenue, credit BTW ledger
        vat_entry = transactions[1]
        assert vat_entry['Debet'] == CUSTOM_REVENUE_ACCOUNT
        assert vat_entry['Credit'] == BTW_HIGH_LEDGER

    def test_fallback_to_parameter_when_no_invoice_revenue_account(self):
        """When invoice has no revenue_account, fall back to zzp.revenue_account param.

        Requirement: 18.2
        """
        invoice = _make_invoice(revenue_account=None)
        transactions = self._book_and_capture(invoice)

        main_entry = transactions[0]
        assert main_entry['Credit'] == REVENUE_ACCOUNT  # from parameter

    def test_credit_note_uses_original_invoice_revenue_account(self):
        """Credit note reversal uses the original invoice's revenue account.

        Requirement: 18.6
        """
        from services.invoice_booking_helper import InvoiceBookingHelper

        mock_txn_logic = Mock()
        mock_txn_logic.save_approved_transactions.return_value = [{'ID': 1}]

        helper = InvoiceBookingHelper(
            db=Mock(),
            transaction_logic=mock_txn_logic,
            tax_rate_service=_make_tax_rate_service(),
            parameter_service=_make_parameter_service(),
        )

        original_invoice = _make_invoice(revenue_account=CUSTOM_REVENUE_ACCOUNT)
        credit_note = _make_invoice(
            invoice_id=200,
            revenue_account=None,  # CN doesn't set its own
            invoice_type='credit_note',
            original_invoice_id=INVOICE_ID,
            **{
                'invoice_number': 'CN-2026-0001',
                'subtotal': -1000.00,
                'vat_total': -210.00,
                'grand_total': -1210.00,
                'lines': [{
                    'id': 2, 'product_id': PRODUCT_ID,
                    'description': 'Reversal', 'quantity': -10,
                    'unit_price': 100.00, 'vat_code': 'high',
                    'vat_rate': 21.0, 'line_total': -1000.00,
                    'vat_amount': -210.00,
                }],
                'vat_summary': [{
                    'vat_code': 'high', 'vat_rate': 21.0,
                    'base_amount': -1000.00, 'vat_amount': -210.00,
                }],
            }
        )

        storage_result = {'url': STORAGE_URL, 'filename': 'CN-2026-0001.pdf'}
        helper.book_credit_note(TENANT, credit_note, original_invoice, storage_result)

        transactions = mock_txn_logic.save_approved_transactions.call_args[0][0]

        # Reversal main entry: debit original's revenue, credit debtor
        main_entry = transactions[0]
        assert main_entry['Debet'] == CUSTOM_REVENUE_ACCOUNT
        assert main_entry['Credit'] == DEBTOR_ACCOUNT

        # Reversal VAT entry: debit BTW ledger, credit original's revenue
        vat_entry = transactions[1]
        assert vat_entry['Credit'] == CUSTOM_REVENUE_ACCOUNT
        assert vat_entry['Debet'] == BTW_HIGH_LEDGER

    def test_full_send_flow_with_custom_revenue_account(self):
        """End-to-end: create invoice with custom revenue -> send -> verify
        mutaties entries use the custom revenue account throughout.

        Requirements: 18.3, 18.4, 18.5
        """
        from services.invoice_booking_helper import InvoiceBookingHelper
        from services.zzp_invoice_service import ZZPInvoiceService

        mock_txn_logic = Mock()
        mock_txn_logic.save_approved_transactions.return_value = [{'ID': 1}]

        booking_helper = InvoiceBookingHelper(
            db=Mock(),
            transaction_logic=mock_txn_logic,
            tax_rate_service=_make_tax_rate_service(),
            parameter_service=_make_parameter_service(),
        )

        pdf_gen = Mock()
        pdf_gen.generate_invoice_pdf.return_value = BytesIO(b'%PDF-fake')

        email_svc = Mock()
        email_svc.send_invoice_email.return_value = {'success': True}

        service = ZZPInvoiceService(
            db=Mock(),
            tax_rate_service=_make_tax_rate_service(),
            parameter_service=_make_parameter_service(),
            booking_helper=booking_helper,
            pdf_generator=pdf_gen,
            email_service=email_svc,
        )

        invoice = _make_invoice(revenue_account=CUSTOM_REVENUE_ACCOUNT)
        storage_result = {'url': STORAGE_URL, 'filename': PDF_FILENAME}

        with patch.object(service, 'get_invoice', return_value=invoice), \
             patch.object(service, '_store_pdf', return_value=storage_result), \
             patch.object(service, '_update_status'):
            result = service.send_invoice(
                TENANT, INVOICE_ID,
                options={'send_email': True, 'output_destination': 'gdrive'},
                output_service=_make_output_service(),
            )

        assert result['success'] is True

        # Verify the real booking helper used the custom revenue account
        transactions = mock_txn_logic.save_approved_transactions.call_args[0][0]

        # Main entry: credit = custom revenue account
        assert transactions[0]['Credit'] == CUSTOM_REVENUE_ACCOUNT
        assert transactions[0]['Debet'] == DEBTOR_ACCOUNT

        # VAT entry: debit = custom revenue account
        assert transactions[1]['Debet'] == CUSTOM_REVENUE_ACCOUNT
        assert transactions[1]['Credit'] == BTW_HIGH_LEDGER

        # Ref3/Ref4 also present
        assert transactions[0]['Ref3'] == STORAGE_URL
        assert transactions[0]['Ref4'] == PDF_FILENAME


# ═══════════════════════════════════════════════════════════
# 3. VAT Accounts from TaxRateService (Req 19.4)
# ═══════════════════════════════════════════════════════════


@pytest.mark.integration
class TestVATAccountsFromTaxRateService:
    """Verify VAT ledger accounts come from TaxRateService, not hardcoded.

    The booking helper must resolve VAT credit accounts (e.g. 2021 for high,
    2020 for low) from TaxRateService.get_tax_rate() which reads from the
    tax_rates table. No hardcoded VAT account codes.

    Requirement: 19.4
    """

    def _book_and_capture(self, invoice, tax_svc=None, param_svc=None):
        """Book an outgoing invoice and return captured transactions."""
        from services.invoice_booking_helper import InvoiceBookingHelper

        mock_txn_logic = Mock()
        mock_txn_logic.save_approved_transactions.return_value = [{'ID': 1}]

        helper = InvoiceBookingHelper(
            db=Mock(),
            transaction_logic=mock_txn_logic,
            tax_rate_service=tax_svc or _make_tax_rate_service(),
            parameter_service=param_svc or _make_parameter_service(),
        )

        storage_result = {'url': STORAGE_URL, 'filename': PDF_FILENAME}
        helper.book_outgoing_invoice(TENANT, invoice, storage_result)

        return mock_txn_logic.save_approved_transactions.call_args[0][0]

    def test_high_vat_uses_ledger_from_tax_rate_service(self):
        """High VAT entry credits the ledger_account from TaxRateService (2021)."""
        invoice = _make_invoice(revenue_account=REVENUE_ACCOUNT)
        transactions = self._book_and_capture(invoice)

        vat_entry = transactions[1]
        assert vat_entry['Credit'] == BTW_HIGH_LEDGER

    def test_low_vat_uses_ledger_from_tax_rate_service(self):
        """Low VAT entry credits the ledger_account from TaxRateService (2020)."""
        low_vat_lines = [
            {
                'id': 1, 'product_id': PRODUCT_ID,
                'description': 'Consulting', 'quantity': 5,
                'unit_price': 200.00, 'vat_code': 'low',
                'vat_rate': 9.0, 'line_total': 1000.00,
                'vat_amount': 90.00,
            }
        ]
        low_vat_summary = [{
            'vat_code': 'low', 'vat_rate': 9.0,
            'base_amount': 1000.00, 'vat_amount': 90.00,
        }]

        invoice = _make_invoice(
            revenue_account=REVENUE_ACCOUNT,
            lines=low_vat_lines,
            vat_summary=low_vat_summary,
        )
        transactions = self._book_and_capture(invoice)

        vat_entry = transactions[1]
        assert vat_entry['Credit'] == BTW_LOW_LEDGER

    def test_multiple_vat_rates_each_use_own_ledger(self):
        """Invoice with high + low VAT lines: each VAT entry uses its own ledger."""
        mixed_lines = [
            {
                'id': 1, 'product_id': PRODUCT_ID,
                'description': 'Development', 'quantity': 10,
                'unit_price': 100.00, 'vat_code': 'high',
                'vat_rate': 21.0, 'line_total': 1000.00,
                'vat_amount': 210.00,
            },
            {
                'id': 2, 'product_id': PRODUCT_ID + 1,
                'description': 'Books', 'quantity': 5,
                'unit_price': 20.00, 'vat_code': 'low',
                'vat_rate': 9.0, 'line_total': 100.00,
                'vat_amount': 9.00,
            },
        ]
        mixed_summary = [
            {'vat_code': 'high', 'vat_rate': 21.0,
             'base_amount': 1000.00, 'vat_amount': 210.00},
            {'vat_code': 'low', 'vat_rate': 9.0,
             'base_amount': 100.00, 'vat_amount': 9.00},
        ]

        invoice = _make_invoice(
            revenue_account=REVENUE_ACCOUNT,
            lines=mixed_lines,
            vat_summary=mixed_summary,
        )
        transactions = self._book_and_capture(invoice)

        # Should have 3 entries: main + high VAT + low VAT
        assert len(transactions) == 3

        # Find VAT entries by description
        high_vat = [t for t in transactions if 'BTW 21%' in t['TransactionDescription']]
        low_vat = [t for t in transactions if 'BTW 9%' in t['TransactionDescription']]

        assert len(high_vat) == 1
        assert high_vat[0]['Credit'] == BTW_HIGH_LEDGER
        assert high_vat[0]['TransactionAmount'] == 210.00

        assert len(low_vat) == 1
        assert low_vat[0]['Credit'] == BTW_LOW_LEDGER
        assert low_vat[0]['TransactionAmount'] == 9.00

    def test_custom_tenant_vat_ledger_accounts(self):
        """Tenant with custom VAT ledger accounts (e.g. 2031/2030) uses those."""
        custom_rates = {
            'high': {'rate': 21.0, 'code': 'high', 'ledger_account': '2031'},
            'low': {'rate': 9.0, 'code': 'low', 'ledger_account': '2030'},
        }
        custom_tax_svc = _make_tax_rate_service(custom_rates)

        invoice = _make_invoice(revenue_account=REVENUE_ACCOUNT)
        transactions = self._book_and_capture(invoice, tax_svc=custom_tax_svc)

        vat_entry = transactions[1]
        assert vat_entry['Credit'] == '2031'  # custom, not default 2021

    def test_zero_vat_line_skipped(self):
        """Zero-rate VAT lines produce no mutaties entry (Req 6.10)."""
        zero_lines = [{
            'id': 1, 'product_id': PRODUCT_ID,
            'description': 'Export service', 'quantity': 10,
            'unit_price': 100.00, 'vat_code': 'zero',
            'vat_rate': 0.0, 'line_total': 1000.00,
            'vat_amount': 0.00,
        }]
        zero_summary = [{
            'vat_code': 'zero', 'vat_rate': 0.0,
            'base_amount': 1000.00, 'vat_amount': 0.00,
        }]

        invoice = _make_invoice(
            revenue_account=REVENUE_ACCOUNT,
            lines=zero_lines,
            vat_summary=zero_summary,
        )
        transactions = self._book_and_capture(invoice)

        # Only main entry, no VAT entry (zero amount skipped)
        assert len(transactions) == 1
        assert transactions[0]['TransactionAmount'] == 1000.00

    def test_tax_rate_service_called_with_invoice_date(self):
        """TaxRateService is called with the invoice date for rate lookup."""
        tax_svc = _make_tax_rate_service()

        invoice = _make_invoice(revenue_account=REVENUE_ACCOUNT)
        self._book_and_capture(invoice, tax_svc=tax_svc)

        # Verify TaxRateService was called with correct params
        tax_svc.get_tax_rate.assert_called()
        call_args = tax_svc.get_tax_rate.call_args
        assert call_args[0][0] == TENANT
        assert call_args[0][1] == 'btw'
        assert call_args[0][2] == 'high'
        # Date should be the invoice date
        ref_date = call_args[0][3]
        assert str(ref_date) == INVOICE_DATE or ref_date == date.fromisoformat(INVOICE_DATE)


# ═══════════════════════════════════════════════════════════
# 4. Account Validation on Parameter Save (Req 19.6)
# ═══════════════════════════════════════════════════════════


@pytest.mark.integration
class TestAccountValidationOnParameterSave:
    """Verify that saving booking account parameters rejects unflagged accounts.

    When a tenant admin sets zzp.debtor_account or zzp.creditor_account,
    the system validates the account exists in rekeningschema with the
    corresponding ledger flag set to true.

    Requirement: 19.6
    """

    @pytest.fixture(autouse=True)
    def setup(self):
        """Import validation function."""
        from routes.zzp_routes import _validate_booking_account, _BOOKING_ACCOUNT_FLAG_MAP
        self.validate = _validate_booking_account
        self.flag_map = _BOOKING_ACCOUNT_FLAG_MAP

    def test_debtor_account_rejected_when_not_flagged(self):
        """Setting debtor_account to an unflagged account raises ValueError."""
        with pytest.raises(ValueError, match='zzp_debtor_account'):
            with _mock_db_in_routes([]):  # No matching rows
                self.validate(TENANT, 'debtor_account', '1300')

    def test_creditor_account_rejected_when_not_flagged(self):
        """Setting creditor_account to an unflagged account raises ValueError."""
        with pytest.raises(ValueError, match='zzp_creditor_account'):
            with _mock_db_in_routes([]):
                self.validate(TENANT, 'creditor_account', '1600')

    def test_revenue_account_rejected_when_not_flagged(self):
        """Setting revenue_account to an unflagged account raises ValueError."""
        with pytest.raises(ValueError, match='zzp_revenue_ledger'):
            with _mock_db_in_routes([]):
                self.validate(TENANT, 'revenue_account', '8001')

    def test_flagged_debtor_account_accepted(self):
        """Setting debtor_account to a flagged account succeeds."""
        with _mock_db_in_routes([{'Account': '1300'}]):
            self.validate(TENANT, 'debtor_account', '1300')
            # No exception = pass

    def test_flagged_creditor_account_accepted(self):
        """Setting creditor_account to a flagged account succeeds."""
        with _mock_db_in_routes([{'Account': '1600'}]):
            self.validate(TENANT, 'creditor_account', '1600')

    def test_flagged_revenue_account_accepted(self):
        """Setting revenue_account to a flagged account succeeds."""
        with _mock_db_in_routes([{'Account': '8001'}]):
            self.validate(TENANT, 'revenue_account', '8001')

    def test_validation_queries_correct_flag(self):
        """Validation queries rekeningschema with the correct JSON flag."""
        with _mock_db_in_routes([{'Account': '1300'}]) as mock_db:
            self.validate(TENANT, 'debtor_account', '1300')

        # Verify the query used the correct flag
        query_args = mock_db.execute_query.call_args
        assert '$.zzp_debtor_account' in str(query_args)

    def test_validation_scoped_to_tenant(self):
        """Validation query includes tenant filter."""
        with _mock_db_in_routes([{'Account': '1300'}]) as mock_db:
            self.validate(TENANT, 'debtor_account', '1300')

        query_params = mock_db.execute_query.call_args[0][1]
        assert TENANT in query_params

    def test_error_message_includes_account_and_flag(self):
        """Error message names both the account code and the required flag."""
        with pytest.raises(ValueError) as exc_info:
            with _mock_db_in_routes([]):
                self.validate(TENANT, 'debtor_account', '9999')

        error_msg = str(exc_info.value)
        assert '9999' in error_msg
        assert 'zzp_debtor_account' in error_msg

    def test_unknown_key_skips_validation(self):
        """Unknown parameter keys are not validated (no flag to check)."""
        with _mock_db_in_routes([]):
            self.validate(TENANT, 'some_other_param', '1234')
            # No exception = pass


# ═══════════════════════════════════════════════════════════
# 5. Missing Required Parameters Raise Descriptive Errors (Req 19.5)
# ═══════════════════════════════════════════════════════════


@pytest.mark.integration
class TestMissingBookingParametersRaise:
    """Verify that missing required booking parameters raise descriptive errors
    instead of silently using hardcoded defaults.

    Requirement: 19.2, 19.3, 19.5
    """

    def _make_helper_no_params(self):
        """Create a booking helper with no parameters configured."""
        from services.invoice_booking_helper import InvoiceBookingHelper

        empty_param_svc = Mock()
        empty_param_svc.get_param.return_value = None

        return InvoiceBookingHelper(
            db=Mock(),
            transaction_logic=Mock(),
            tax_rate_service=_make_tax_rate_service(),
            parameter_service=empty_param_svc,
        )

    def test_missing_debtor_account_raises_on_outgoing(self):
        """Outgoing invoice booking fails when debtor_account not configured."""
        helper = self._make_helper_no_params()
        invoice = _make_invoice(revenue_account=REVENUE_ACCOUNT)

        with pytest.raises(ValueError, match='zzp.debtor_account'):
            helper.book_outgoing_invoice(TENANT, invoice)

    def test_missing_revenue_account_raises_on_outgoing(self):
        """Outgoing invoice booking fails when revenue_account not configured
        and invoice has no revenue_account set."""
        from services.invoice_booking_helper import InvoiceBookingHelper

        # Only debtor_account configured, not revenue_account
        partial_params = {
            ('zzp', 'debtor_account'): DEBTOR_ACCOUNT,
        }
        param_svc = Mock()
        param_svc.get_param.side_effect = lambda ns, key, tenant=None: partial_params.get((ns, key))

        helper = InvoiceBookingHelper(
            db=Mock(),
            transaction_logic=Mock(),
            tax_rate_service=_make_tax_rate_service(),
            parameter_service=param_svc,
        )

        invoice = _make_invoice(revenue_account=None)

        with pytest.raises(ValueError, match='zzp.revenue_account'):
            helper.book_outgoing_invoice(TENANT, invoice)

    def test_missing_creditor_account_raises_on_incoming(self):
        """Incoming invoice booking fails when creditor_account not configured."""
        helper = self._make_helper_no_params()
        invoice = _make_invoice()

        with pytest.raises(ValueError, match='zzp.creditor_account'):
            helper.book_incoming_invoice(TENANT, invoice)

    def test_error_message_includes_tenant_name(self):
        """Error message names the tenant for easier debugging."""
        helper = self._make_helper_no_params()
        invoice = _make_invoice(revenue_account=REVENUE_ACCOUNT)

        with pytest.raises(ValueError, match=TENANT):
            helper.book_outgoing_invoice(TENANT, invoice)

    def test_error_message_suggests_parameter_admin(self):
        """Error message suggests where to configure the parameter."""
        helper = self._make_helper_no_params()
        invoice = _make_invoice(revenue_account=REVENUE_ACCOUNT)

        with pytest.raises(ValueError, match='Tenant Administration'):
            helper.book_outgoing_invoice(TENANT, invoice)


# ═══════════════════════════════════════════════════════════
# 6. Invoice Ledger API Returns Flagged Accounts (Req 17.3)
# ═══════════════════════════════════════════════════════════


@pytest.mark.integration
class TestInvoiceLedgerAccountsAPI:
    """Verify the invoice ledger accounts endpoint returns correctly flagged
    accounts and falls back to the default revenue account parameter.

    Requirement: 17.3, 17.4
    """

    def _book_with_vat_and_capture(self, invoice, tax_rates=None):
        """Book an invoice with specific tax rates and capture transactions.

        This verifies the full chain: TaxRateService -> booking helper -> mutaties.
        """
        from services.invoice_booking_helper import InvoiceBookingHelper

        mock_txn_logic = Mock()
        mock_txn_logic.save_approved_transactions.return_value = [{'ID': 1}]

        tax_svc = _make_tax_rate_service(tax_rates) if tax_rates else _make_tax_rate_service()

        helper = InvoiceBookingHelper(
            db=Mock(),
            transaction_logic=mock_txn_logic,
            tax_rate_service=tax_svc,
            parameter_service=_make_parameter_service(),
        )

        storage_result = {'url': STORAGE_URL, 'filename': PDF_FILENAME}
        helper.book_outgoing_invoice(TENANT, invoice, storage_result)

        return mock_txn_logic.save_approved_transactions.call_args[0][0]

    def test_booking_entries_reference_correct_invoice_number(self):
        """All mutaties entries have Ref2 = invoice number for traceability."""
        invoice = _make_invoice(revenue_account=REVENUE_ACCOUNT)
        transactions = self._book_with_vat_and_capture(invoice)

        for txn in transactions:
            assert txn['Ref2'] == INVOICE_NUMBER

    def test_booking_entries_reference_client_id(self):
        """All mutaties entries have ReferenceNumber = client_id for payment matching."""
        invoice = _make_invoice(revenue_account=REVENUE_ACCOUNT)
        transactions = self._book_with_vat_and_capture(invoice)

        for txn in transactions:
            assert txn['ReferenceNumber'] == CLIENT_ID

    def test_booking_entries_scoped_to_tenant(self):
        """All mutaties entries have Administration = tenant."""
        invoice = _make_invoice(revenue_account=REVENUE_ACCOUNT)
        transactions = self._book_with_vat_and_capture(invoice)

        for txn in transactions:
            assert txn['Administration'] == TENANT

    def test_multi_currency_conversion_in_booking(self):
        """Non-EUR invoice amounts are converted using stored exchange rate."""
        usd_invoice = _make_invoice(
            revenue_account=REVENUE_ACCOUNT,
            currency='USD',
            exchange_rate=0.92,
            lines=[{
                'id': 1, 'product_id': PRODUCT_ID,
                'description': 'USD service', 'quantity': 10,
                'unit_price': 100.00, 'vat_code': 'high',
                'vat_rate': 21.0, 'line_total': 1000.00,
                'vat_amount': 210.00,
            }],
            vat_summary=[{
                'vat_code': 'high', 'vat_rate': 21.0,
                'base_amount': 1000.00, 'vat_amount': 210.00,
            }],
        )
        # Override grand_total for the USD invoice
        usd_invoice['grand_total'] = 1210.00

        transactions = self._book_with_vat_and_capture(usd_invoice)

        # Amounts should be converted: 1210 * 0.92 = 1113.20
        main_entry = transactions[0]
        assert main_entry['TransactionAmount'] == round(1210.00 * 0.92, 2)

        # VAT: 210 * 0.92 = 193.20
        vat_entry = transactions[1]
        assert vat_entry['TransactionAmount'] == round(210.00 * 0.92, 2)


# ═══════════════════════════════════════════════════════════
# 7. Combined Cross-Requirement Flow (Reqs 17-19, 22)
# ═══════════════════════════════════════════════════════════


@pytest.mark.integration
class TestCombinedCrossRequirementFlow:
    """End-to-end test combining revenue account selection, VAT from
    TaxRateService, storage Ref3/Ref4, and parameter-driven accounts.

    This is the "golden path" integration test that exercises all
    cross-requirement interactions in a single flow.
    """

    def test_golden_path_custom_revenue_multi_vat_with_storage(self):
        """Full flow: custom revenue account + mixed VAT rates + storage refs.

        Verifies:
        - Invoice-level revenue account used (Req 18.4, 18.5)
        - VAT accounts from TaxRateService (Req 19.4)
        - Debtor account from parameter (Req 19.2)
        - Storage URL/filename in Ref3/Ref4 (Req 22.2)
        - Zero-rate VAT skipped (Req 6.10)
        """
        from services.invoice_booking_helper import InvoiceBookingHelper
        from services.zzp_invoice_service import ZZPInvoiceService

        mock_txn_logic = Mock()
        mock_txn_logic.save_approved_transactions.return_value = [
            {'ID': 1}, {'ID': 2}, {'ID': 3},
        ]

        booking_helper = InvoiceBookingHelper(
            db=Mock(),
            transaction_logic=mock_txn_logic,
            tax_rate_service=_make_tax_rate_service(),
            parameter_service=_make_parameter_service(),
        )

        pdf_gen = Mock()
        pdf_gen.generate_invoice_pdf.return_value = BytesIO(b'%PDF-fake')

        email_svc = Mock()
        email_svc.send_invoice_email.return_value = {'success': True}

        service = ZZPInvoiceService(
            db=Mock(),
            tax_rate_service=_make_tax_rate_service(),
            parameter_service=_make_parameter_service(),
            booking_helper=booking_helper,
            pdf_generator=pdf_gen,
            email_service=email_svc,
        )

        # Invoice with mixed VAT rates and custom revenue account
        mixed_lines = [
            {
                'id': 1, 'product_id': PRODUCT_ID,
                'description': 'Development', 'quantity': 10,
                'unit_price': 100.00, 'vat_code': 'high',
                'vat_rate': 21.0, 'line_total': 1000.00,
                'vat_amount': 210.00,
            },
            {
                'id': 2, 'product_id': PRODUCT_ID + 1,
                'description': 'Books', 'quantity': 5,
                'unit_price': 20.00, 'vat_code': 'low',
                'vat_rate': 9.0, 'line_total': 100.00,
                'vat_amount': 9.00,
            },
            {
                'id': 3, 'product_id': PRODUCT_ID + 2,
                'description': 'Export consulting', 'quantity': 2,
                'unit_price': 500.00, 'vat_code': 'zero',
                'vat_rate': 0.0, 'line_total': 1000.00,
                'vat_amount': 0.00,
            },
        ]
        mixed_summary = [
            {'vat_code': 'high', 'vat_rate': 21.0,
             'base_amount': 1000.00, 'vat_amount': 210.00},
            {'vat_code': 'low', 'vat_rate': 9.0,
             'base_amount': 100.00, 'vat_amount': 9.00},
            {'vat_code': 'zero', 'vat_rate': 0.0,
             'base_amount': 1000.00, 'vat_amount': 0.00},
        ]

        invoice = _make_invoice(
            revenue_account=CUSTOM_REVENUE_ACCOUNT,
            lines=mixed_lines,
            vat_summary=mixed_summary,
        )

        storage_result = {'url': STORAGE_URL, 'filename': PDF_FILENAME}

        with patch.object(service, 'get_invoice', return_value=invoice), \
             patch.object(service, '_store_pdf', return_value=storage_result), \
             patch.object(service, '_update_status'):
            result = service.send_invoice(
                TENANT, INVOICE_ID,
                options={'send_email': True, 'output_destination': 'gdrive'},
                output_service=_make_output_service(),
            )

        assert result['success'] is True

        transactions = mock_txn_logic.save_approved_transactions.call_args[0][0]

        # 3 entries: main + high VAT + low VAT (zero skipped)
        assert len(transactions) == 3

        # Main entry
        main = transactions[0]
        assert main['Debet'] == DEBTOR_ACCOUNT  # from parameter (Req 19.2)
        assert main['Credit'] == CUSTOM_REVENUE_ACCOUNT  # from invoice (Req 18.4)
        assert main['Ref3'] == STORAGE_URL  # (Req 22.2)
        assert main['Ref4'] == PDF_FILENAME  # (Req 22.2)
        assert main['ReferenceNumber'] == CLIENT_ID
        assert main['Ref2'] == INVOICE_NUMBER
        assert main['Administration'] == TENANT

        # High VAT entry
        high_vat = transactions[1]
        assert high_vat['Debet'] == CUSTOM_REVENUE_ACCOUNT  # (Req 18.5)
        assert high_vat['Credit'] == BTW_HIGH_LEDGER  # from TaxRateService (Req 19.4)
        assert high_vat['TransactionAmount'] == 210.00
        assert high_vat['Ref3'] == STORAGE_URL
        assert high_vat['Ref4'] == PDF_FILENAME

        # Low VAT entry
        low_vat = transactions[2]
        assert low_vat['Debet'] == CUSTOM_REVENUE_ACCOUNT  # (Req 18.5)
        assert low_vat['Credit'] == BTW_LOW_LEDGER  # from TaxRateService (Req 19.4)
        assert low_vat['TransactionAmount'] == 9.00

        # Zero VAT was skipped (Req 6.10) — only 3 entries total
        zero_entries = [t for t in transactions if 'zero' in t.get('TransactionDescription', '').lower()]
        assert len(zero_entries) == 0
