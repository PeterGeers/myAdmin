"""
Integration test: Full ZZP invoice lifecycle.

Flow: create contact → create product → create invoice → send (PDF + book + email)
      → payment check → verify paid.

Tests the service layer with a mocked database, verifying the complete happy-path
lifecycle of an outgoing invoice from creation through payment matching.

Reference: .kiro/specs/zzp-module/tasks.md Phase 9.1
"""

import pytest
import sys
import os
from datetime import date, datetime
from io import BytesIO
from unittest.mock import Mock, MagicMock, patch, call

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

# ── Constants ───────────────────────────────────────────────

TENANT = 'TestTenant'
USER_EMAIL = 'zzp-user@example.com'
CONTACT_ID = 1
PRODUCT_ID = 10
INVOICE_ID = 100
INVOICE_NUMBER = 'INV-2026-0001'
CLIENT_ID = 'ACME'
COMPANY_NAME = 'Acme Corp'
PRODUCT_CODE = 'DEV-001'
DEBTOR_ACCOUNT = '1300'
REVENUE_ACCOUNT = '8000'
BTW_LEDGER_ACCOUNT = '2021'
INVOICE_DATE = '2026-06-01'
DUE_DATE = '2026-07-01'
UNIT_PRICE = 100.00
QUANTITY = 10
VAT_RATE = 21.0
LINE_TOTAL = 1000.00
VAT_AMOUNT = 210.00
GRAND_TOTAL = 1210.00


# ── Fixtures ────────────────────────────────────────────────


@pytest.fixture
def mock_db():
    """Mock database with execute_query and connection support."""
    db = Mock()
    db.execute_query = Mock()
    # For invoice number generation (uses get_connection)
    mock_conn = Mock()
    mock_cursor = Mock(dictionary=True)
    mock_cursor.fetchone.return_value = None  # No existing sequence
    mock_conn.cursor.return_value = mock_cursor
    db.get_connection = Mock(return_value=mock_conn)
    return db


@pytest.fixture
def mock_tax_rate_service():
    """TaxRateService that returns 21% for 'high' VAT code."""
    svc = Mock()
    svc.get_tax_rate.return_value = {
        'rate': VAT_RATE,
        'code': 'high',
        'ledger_account': BTW_LEDGER_ACCOUNT,
    }
    return svc


@pytest.fixture
def mock_parameter_service():
    """ParameterService returning ZZP configuration values."""
    params = {
        ('zzp', 'invoice_prefix'): 'INV',
        ('zzp', 'invoice_number_padding'): '4',
        ('zzp', 'debtor_account'): DEBTOR_ACCOUNT,
        ('zzp', 'revenue_account'): REVENUE_ACCOUNT,
        ('zzp', 'default_payment_terms'): '30',
        ('zzp', 'default_currency'): 'EUR',
    }

    svc = Mock()

    def get_param(namespace, key, tenant=None):
        return params.get((namespace, key))

    svc.get_param = Mock(side_effect=get_param)
    return svc


@pytest.fixture
def mock_pdf_generator():
    """PDFGeneratorService that returns fake PDF bytes."""
    svc = Mock()
    svc.generate_invoice_pdf.return_value = BytesIO(b'%PDF-1.4-fake-content')
    return svc


@pytest.fixture
def mock_email_service():
    """InvoiceEmailService that returns success."""
    svc = Mock()
    svc.send_invoice_email.return_value = {'success': True, 'message_id': 'msg-123'}
    return svc


@pytest.fixture
def mock_output_service():
    """OutputService for storage health check and PDF storage."""
    svc = Mock()
    svc.check_health.return_value = {'healthy': True}
    svc.store_file = Mock(return_value={
        'url': 'https://drive.google.com/file/d/abc123',
        'filename': f'{INVOICE_NUMBER}.pdf',
    })
    return svc


@pytest.fixture
def mock_booking_helper():
    """InvoiceBookingHelper mock."""
    helper = Mock()
    helper.book_outgoing_invoice.return_value = [
        {'ID': 1, 'TransactionDescription': f'Factuur {INVOICE_NUMBER} {CLIENT_ID}'}
    ]
    return helper


@pytest.fixture
def contact_data():
    """Sample contact creation data."""
    return {
        'client_id': CLIENT_ID,
        'company_name': COMPANY_NAME,
        'contact_type': 'client',
        'contact_person': 'John Doe',
        'street_address': 'Keizersgracht 100',
        'postal_code': '1015 AA',
        'city': 'Amsterdam',
        'country': 'NL',
        'emails': [{'email': 'billing@acme.nl', 'is_primary': True}],
    }


@pytest.fixture
def product_data():
    """Sample product creation data."""
    return {
        'product_code': PRODUCT_CODE,
        'name': 'Software Development',
        'description': 'Custom software development services',
        'product_type': 'service',
        'unit_price': UNIT_PRICE,
        'vat_code': 'high',
        'unit_of_measure': 'uur',
    }


@pytest.fixture
def invoice_data():
    """Sample invoice creation data with one line."""
    return {
        'contact_id': CONTACT_ID,
        'invoice_date': INVOICE_DATE,
        'payment_terms_days': 30,
        'currency': 'EUR',
        'notes': 'Development services June 2026',
        'lines': [
            {
                'product_id': PRODUCT_ID,
                'description': 'Software Development - June 2026',
                'quantity': QUANTITY,
                'unit_price': UNIT_PRICE,
                'vat_code': 'high',
            }
        ],
    }


# ── Full Flow Integration Test ──────────────────────────────


@pytest.mark.integration
class TestZZPFullInvoiceFlow:
    """End-to-end test: contact → product → invoice → send → payment → paid."""

    def _setup_db_for_contact_create(self, mock_db):
        """Configure mock_db responses for contact creation."""
        # create_contact: INSERT returns contact_id
        # get_contact (after create): returns the contact
        # _get_emails: returns emails
        # _check_client_id_unique: returns empty (no duplicate)
        pass  # Handled in the side_effect chain

    def _build_full_invoice(self):
        """Build a complete invoice dict as returned by get_invoice."""
        return {
            'id': INVOICE_ID,
            'invoice_number': INVOICE_NUMBER,
            'invoice_type': 'invoice',
            'contact_id': CONTACT_ID,
            'invoice_date': INVOICE_DATE,
            'due_date': DUE_DATE,
            'payment_terms_days': 30,
            'currency': 'EUR',
            'exchange_rate': 1.0,
            'revenue_account': REVENUE_ACCOUNT,
            'status': 'draft',
            'subtotal': LINE_TOTAL,
            'vat_total': VAT_AMOUNT,
            'grand_total': GRAND_TOTAL,
            'notes': 'Development services June 2026',
            'contact': {
                'id': CONTACT_ID,
                'client_id': CLIENT_ID,
                'company_name': COMPANY_NAME,
            },
            'lines': [
                {
                    'id': 1,
                    'product_id': PRODUCT_ID,
                    'description': 'Software Development - June 2026',
                    'quantity': QUANTITY,
                    'unit_price': UNIT_PRICE,
                    'vat_code': 'high',
                    'vat_rate': VAT_RATE,
                    'line_total': LINE_TOTAL,
                    'vat_amount': VAT_AMOUNT,
                }
            ],
            'vat_summary': [
                {
                    'vat_code': 'high',
                    'vat_rate': VAT_RATE,
                    'base_amount': LINE_TOTAL,
                    'vat_amount': VAT_AMOUNT,
                }
            ],
        }

    def test_full_lifecycle_happy_path(
        self,
        mock_db,
        mock_tax_rate_service,
        mock_parameter_service,
        mock_pdf_generator,
        mock_email_service,
        mock_output_service,
        mock_booking_helper,
        contact_data,
        product_data,
        invoice_data,
    ):
        """
        Full lifecycle: create contact → create product → create invoice
        → send invoice → payment check → verify paid.
        """
        from services.contact_service import ContactService
        from services.product_service import ProductService
        from services.zzp_invoice_service import ZZPInvoiceService
        from services.payment_check_helper import PaymentCheckHelper

        # ── Step 1: Create Contact ──────────────────────────

        contact_service = ContactService(mock_db, parameter_service=mock_parameter_service)

        created_contact = {
            'id': CONTACT_ID,
            'client_id': CLIENT_ID,
            'company_name': COMPANY_NAME,
            'contact_type': 'client',
            'contact_person': 'John Doe',
            'street_address': 'Keizersgracht 100',
            'postal_code': '1015 AA',
            'city': 'Amsterdam',
            'country': 'NL',
            'is_active': True,
            'emails': [{'email': 'billing@acme.nl', 'is_primary': True}],
        }

        # Mock: _check_client_id_unique (no rows = unique)
        # Mock: INSERT returns contact_id
        # Mock: get_contact returns the created contact
        # Mock: _get_emails returns emails
        mock_db.execute_query.side_effect = [
            # _check_client_id_unique: SELECT returns empty
            [],
            # INSERT INTO contacts: returns contact_id
            CONTACT_ID,
            # _save_emails: INSERT (no return needed)
            None,
            # get_contact: SELECT * FROM contacts
            [created_contact],
            # _get_emails: SELECT from contact_emails
            [{'email': 'billing@acme.nl', 'is_primary': True}],
        ]

        # Patch validate_fields and _validate_contact_type to avoid parameter lookups
        with patch.object(contact_service, 'validate_fields'), \
             patch.object(contact_service, '_validate_contact_type'), \
             patch.object(contact_service, 'strip_hidden_fields', side_effect=lambda t, c: c):
            result_contact = contact_service.create_contact(TENANT, contact_data, USER_EMAIL)

        assert result_contact['id'] == CONTACT_ID
        assert result_contact['client_id'] == CLIENT_ID
        assert result_contact['company_name'] == COMPANY_NAME

        # ── Step 2: Create Product ──────────────────────────

        product_service = ProductService(
            mock_db,
            tax_rate_service=mock_tax_rate_service,
            parameter_service=mock_parameter_service,
        )

        created_product = {
            'id': PRODUCT_ID,
            'product_code': PRODUCT_CODE,
            'name': 'Software Development',
            'product_type': 'service',
            'unit_price': UNIT_PRICE,
            'vat_code': 'high',
            'unit_of_measure': 'uur',
            'is_active': True,
        }

        mock_db.execute_query.side_effect = [
            # _check_product_code_unique: SELECT returns empty
            [],
            # INSERT INTO products: returns product_id
            PRODUCT_ID,
            # get_product: SELECT * FROM products
            [created_product],
        ]

        with patch.object(product_service, 'validate_fields'), \
             patch.object(product_service, '_validate_vat_code'), \
             patch.object(product_service, '_validate_product_type'), \
             patch.object(product_service, 'strip_hidden_fields', side_effect=lambda t, p: p):
            result_product = product_service.create_product(TENANT, product_data, USER_EMAIL)

        assert result_product['id'] == PRODUCT_ID
        assert result_product['product_code'] == PRODUCT_CODE

        # ── Step 3: Create Invoice ──────────────────────────

        invoice_service = ZZPInvoiceService(
            db=mock_db,
            tax_rate_service=mock_tax_rate_service,
            parameter_service=mock_parameter_service,
            booking_helper=mock_booking_helper,
            pdf_generator=mock_pdf_generator,
            email_service=mock_email_service,
        )

        full_invoice = self._build_full_invoice()

        mock_db.execute_query.side_effect = [
            # Validate contact exists: SELECT id FROM contacts
            [{'id': CONTACT_ID}],
            # INSERT INTO invoices: returns invoice_id
            INVOICE_ID,
            # _save_lines: INSERT INTO invoice_lines (one line)
            None,
            # _update_totals: UPDATE invoices SET subtotal...
            None,
            # _update_totals: SELECT from vw_invoice_vat_summary
            [{'vat_code': 'high', 'vat_rate': VAT_RATE,
              'base_amount': LINE_TOTAL, 'vat_amount': VAT_AMOUNT}],
            # get_invoice: _get_invoice_raw SELECT
            [full_invoice],
            # get_invoice: contact lookup
            [{'id': CONTACT_ID, 'client_id': CLIENT_ID, 'company_name': COMPANY_NAME}],
            # get_invoice: lines lookup
            full_invoice['lines'],
            # get_invoice: vat_summary lookup
            full_invoice['vat_summary'],
        ]

        # Patch _generate_invoice_number to avoid connection-based logic
        with patch.object(invoice_service, '_generate_invoice_number',
                          return_value=INVOICE_NUMBER), \
             patch.object(invoice_service, '_default_payment_terms', return_value=30), \
             patch.object(invoice_service, '_default_currency', return_value='EUR'), \
             patch.object(invoice_service, '_get_default_revenue_account',
                          return_value=REVENUE_ACCOUNT), \
             patch.object(invoice_service, 'validate_fields'):
            result_invoice = invoice_service.create_invoice(TENANT, invoice_data, USER_EMAIL)

        assert result_invoice['id'] == INVOICE_ID
        assert result_invoice['invoice_number'] == INVOICE_NUMBER
        assert result_invoice['status'] == 'draft'
        assert result_invoice['grand_total'] == GRAND_TOTAL
        assert result_invoice['contact']['client_id'] == CLIENT_ID

        # ── Step 4: Send Invoice ────────────────────────────
        # Flow: health check → PDF → store → book → update status → email

        sent_invoice = {**full_invoice, 'status': 'sent'}

        mock_db.execute_query.side_effect = [
            # get_invoice (inside send_invoice): _get_invoice_raw
            [full_invoice],
            # get_invoice: contact lookup
            [{'id': CONTACT_ID, 'client_id': CLIENT_ID, 'company_name': COMPANY_NAME}],
            # get_invoice: lines lookup
            full_invoice['lines'],
            # get_invoice: vat_summary lookup
            full_invoice['vat_summary'],
            # _update_status: UPDATE invoices SET status='sent'
            None,
        ]

        # Mock _store_pdf to return storage result
        storage_result = {
            'url': 'https://drive.google.com/file/d/abc123',
            'filename': f'{INVOICE_NUMBER}.pdf',
        }

        with patch.object(invoice_service, '_store_pdf', return_value=storage_result), \
             patch.object(invoice_service, '_update_status') as mock_update_status:
            send_result = invoice_service.send_invoice(
                TENANT, INVOICE_ID,
                options={'send_email': True, 'output_destination': 'gdrive'},
                output_service=mock_output_service,
            )

        # Verify send was successful
        assert send_result['success'] is True
        assert send_result['invoice_number'] == INVOICE_NUMBER

        # Verify health check was called
        mock_output_service.check_health.assert_called_once_with('gdrive', TENANT)

        # Verify PDF was generated
        mock_pdf_generator.generate_invoice_pdf.assert_called_once()
        pdf_call_args = mock_pdf_generator.generate_invoice_pdf.call_args
        assert pdf_call_args[0][0] == TENANT

        # Verify booking helper was called with correct invoice data
        mock_booking_helper.book_outgoing_invoice.assert_called_once()
        booking_call = mock_booking_helper.book_outgoing_invoice.call_args
        assert booking_call[0][0] == TENANT  # tenant
        assert booking_call[0][1]['invoice_number'] == INVOICE_NUMBER  # invoice
        assert booking_call[0][2] == storage_result  # storage_result

        # Verify status was updated to 'sent'
        mock_update_status.assert_called_once()
        status_call = mock_update_status.call_args
        assert status_call[0][0] == TENANT
        assert status_call[0][1] == INVOICE_ID
        assert status_call[0][2] == 'sent'

        # Verify email was sent
        mock_email_service.send_invoice_email.assert_called_once()
        email_call = mock_email_service.send_invoice_email.call_args
        assert email_call[0][0] == TENANT
        assert email_call[0][1]['invoice_number'] == INVOICE_NUMBER
        # Verify PDF attachment was included
        attachments = email_call[0][2]
        assert len(attachments) == 1
        assert attachments[0]['filename'] == f'{INVOICE_NUMBER}.pdf'
        assert attachments[0]['content_type'] == 'application/pdf'

        # ── Step 5: Payment Check ───────────────────────────
        # Simulate bank transaction matching by ReferenceNumber (= client_id)

        payment_check = PaymentCheckHelper(mock_db)

        # Open invoices query returns our sent invoice
        open_invoices = [{
            'id': INVOICE_ID,
            'invoice_number': INVOICE_NUMBER,
            'grand_total': GRAND_TOTAL,
            'status': 'sent',
            'currency': 'EUR',
            'exchange_rate': 1.0,
            'client_id': CLIENT_ID,
        }]

        # Bank transaction matching the invoice amount (within tolerance)
        bank_transactions = [{
            'ID': 5001,
            'TransactionDate': '2026-06-15',
            'TransactionAmount': str(GRAND_TOTAL),  # Exact match
            'TransactionDescription': f'Payment {CLIENT_ID}',
        }]

        mock_db.execute_query.side_effect = [
            # run_payment_check: SELECT open invoices
            open_invoices,
            # _match_invoice: SELECT bank transactions for client_id
            bank_transactions,
            # _match_invoice: UPDATE invoices SET status='paid'
            None,
        ]

        payment_result = payment_check.run_payment_check(TENANT)

        # ── Step 6: Verify Paid ─────────────────────────────

        assert payment_result['success'] is True
        assert payment_result['matched'] == 1
        assert payment_result['partial'] == 0
        assert payment_result['unmatched'] == 0

        # Verify the detail shows exact match
        detail = payment_result['details'][0]
        assert detail['invoice_number'] == INVOICE_NUMBER
        assert detail['match_type'] == 'exact'
        assert detail['bank_txn_id'] == 5001
        assert abs(detail['bank_amount'] - GRAND_TOTAL) < 0.01
        assert detail['message'] == 'Payment matched'

        # Verify the UPDATE to 'paid' was issued
        update_calls = [
            c for c in mock_db.execute_query.call_args_list
            if c[0][0] and "UPDATE invoices SET status = 'paid'" in str(c[0][0])
        ]
        assert len(update_calls) == 1
        assert update_calls[0][0][1] == (INVOICE_ID, TENANT)

    def test_full_lifecycle_payment_within_tolerance(
        self,
        mock_db,
        mock_tax_rate_service,
        mock_parameter_service,
        mock_pdf_generator,
        mock_email_service,
        mock_output_service,
        mock_booking_helper,
    ):
        """Payment check matches when bank amount is within €0.01 tolerance."""
        from services.payment_check_helper import PaymentCheckHelper

        payment_check = PaymentCheckHelper(mock_db)

        open_invoices = [{
            'id': INVOICE_ID,
            'invoice_number': INVOICE_NUMBER,
            'grand_total': GRAND_TOTAL,
            'status': 'sent',
            'currency': 'EUR',
            'exchange_rate': 1.0,
            'client_id': CLIENT_ID,
        }]

        # Bank amount differs by €0.005 (within €0.01 tolerance)
        bank_transactions = [{
            'ID': 5002,
            'TransactionDate': '2026-06-16',
            'TransactionAmount': str(GRAND_TOTAL + 0.005),
            'TransactionDescription': f'Payment {CLIENT_ID}',
        }]

        mock_db.execute_query.side_effect = [
            open_invoices,
            bank_transactions,
            None,  # UPDATE status to paid
        ]

        result = payment_check.run_payment_check(TENANT)

        assert result['success'] is True
        assert result['matched'] == 1
        assert result['details'][0]['match_type'] == 'exact'

    def test_full_lifecycle_no_bank_transaction_unmatched(
        self,
        mock_db,
    ):
        """Payment check returns unmatched when no bank transactions exist."""
        from services.payment_check_helper import PaymentCheckHelper

        payment_check = PaymentCheckHelper(mock_db)

        open_invoices = [{
            'id': INVOICE_ID,
            'invoice_number': INVOICE_NUMBER,
            'grand_total': GRAND_TOTAL,
            'status': 'sent',
            'currency': 'EUR',
            'exchange_rate': 1.0,
            'client_id': CLIENT_ID,
        }]

        mock_db.execute_query.side_effect = [
            open_invoices,
            [],  # No bank transactions
        ]

        result = payment_check.run_payment_check(TENANT)

        assert result['success'] is True
        assert result['matched'] == 0
        assert result['unmatched'] == 1
        assert result['details'][0]['match_type'] == 'none'

    def test_send_invoice_booking_uses_correct_accounts(
        self,
        mock_db,
        mock_tax_rate_service,
        mock_parameter_service,
        mock_pdf_generator,
        mock_email_service,
        mock_output_service,
    ):
        """Verify booking helper receives correct account references from parameters."""
        from services.invoice_booking_helper import InvoiceBookingHelper

        mock_transaction_logic = Mock()
        mock_transaction_logic.save_approved_transactions.return_value = [{'ID': 1}]

        booking_helper = InvoiceBookingHelper(
            db=mock_db,
            transaction_logic=mock_transaction_logic,
            tax_rate_service=mock_tax_rate_service,
            parameter_service=mock_parameter_service,
        )

        invoice = self._build_full_invoice()
        storage_result = {
            'url': 'https://drive.google.com/file/d/abc123',
            'filename': f'{INVOICE_NUMBER}.pdf',
        }

        result = booking_helper.book_outgoing_invoice(TENANT, invoice, storage_result)

        # Verify transaction_logic was called
        mock_transaction_logic.save_approved_transactions.assert_called_once()
        transactions = mock_transaction_logic.save_approved_transactions.call_args[0][0]

        # Main entry: debit debtor (1300), credit revenue (8000)
        main_entry = transactions[0]
        assert main_entry['Debet'] == DEBTOR_ACCOUNT
        assert main_entry['Credit'] == REVENUE_ACCOUNT
        assert main_entry['TransactionAmount'] == GRAND_TOTAL
        assert main_entry['ReferenceNumber'] == CLIENT_ID
        assert main_entry['Ref2'] == INVOICE_NUMBER
        assert main_entry['Ref3'] == storage_result['url']

        # VAT entry: debit revenue, credit BTW ledger (2021)
        vat_entry = transactions[1]
        assert vat_entry['Debet'] == REVENUE_ACCOUNT
        assert vat_entry['Credit'] == BTW_LEDGER_ACCOUNT
        assert vat_entry['TransactionAmount'] == VAT_AMOUNT

    def test_full_lifecycle_credit_note_flow(
        self,
        mock_db,
        mock_tax_rate_service,
        mock_parameter_service,
        mock_pdf_generator,
        mock_email_service,
        mock_output_service,
        mock_booking_helper,
    ):
        """
        Full lifecycle: create invoice (draft) → send invoice (sent)
        → create credit note → send credit note → original marked credited.

        Reference: .kiro/specs/zzp-module/tasks.md Phase 9.1
        """
        from services.zzp_invoice_service import ZZPInvoiceService

        CN_ID = 200
        CN_NUMBER = 'CN-2026-0001'

        invoice_service = ZZPInvoiceService(
            db=mock_db,
            tax_rate_service=mock_tax_rate_service,
            parameter_service=mock_parameter_service,
            booking_helper=mock_booking_helper,
            pdf_generator=mock_pdf_generator,
            email_service=mock_email_service,
        )

        full_invoice = self._build_full_invoice()

        # ── Step 1: Create Invoice (draft) ──────────────────
        mock_db.execute_query.side_effect = [
            # Validate contact exists
            [{'id': CONTACT_ID}],
            # INSERT INTO invoices
            INVOICE_ID,
            # _save_lines
            None,
            # _update_totals: UPDATE
            None,
            # _update_totals: SELECT vat_summary
            [{'vat_code': 'high', 'vat_rate': VAT_RATE,
              'base_amount': LINE_TOTAL, 'vat_amount': VAT_AMOUNT}],
            # get_invoice: _get_invoice_raw
            [full_invoice],
            # get_invoice: contact
            [{'id': CONTACT_ID, 'client_id': CLIENT_ID, 'company_name': COMPANY_NAME}],
            # get_invoice: lines
            full_invoice['lines'],
            # get_invoice: vat_summary
            full_invoice['vat_summary'],
        ]

        invoice_data = {
            'contact_id': CONTACT_ID,
            'invoice_date': INVOICE_DATE,
            'payment_terms_days': 30,
            'currency': 'EUR',
            'lines': [
                {
                    'product_id': PRODUCT_ID,
                    'description': 'Software Development - June 2026',
                    'quantity': QUANTITY,
                    'unit_price': UNIT_PRICE,
                    'vat_code': 'high',
                }
            ],
        }

        with patch.object(invoice_service, '_generate_invoice_number',
                          return_value=INVOICE_NUMBER), \
             patch.object(invoice_service, '_default_payment_terms', return_value=30), \
             patch.object(invoice_service, '_default_currency', return_value='EUR'), \
             patch.object(invoice_service, '_get_default_revenue_account',
                          return_value=REVENUE_ACCOUNT), \
             patch.object(invoice_service, 'validate_fields'):
            result_invoice = invoice_service.create_invoice(TENANT, invoice_data, USER_EMAIL)

        assert result_invoice['id'] == INVOICE_ID
        assert result_invoice['status'] == 'draft'

        # ── Step 2: Send Invoice (draft → sent) ────────────
        storage_result = {
            'url': 'https://drive.google.com/file/d/abc123',
            'filename': f'{INVOICE_NUMBER}.pdf',
        }

        mock_db.execute_query.side_effect = [
            # get_invoice (inside send_invoice): _get_invoice_raw
            [full_invoice],
            # get_invoice: contact
            [{'id': CONTACT_ID, 'client_id': CLIENT_ID, 'company_name': COMPANY_NAME}],
            # get_invoice: lines
            full_invoice['lines'],
            # get_invoice: vat_summary
            full_invoice['vat_summary'],
            # _update_status
            None,
        ]

        with patch.object(invoice_service, '_store_pdf', return_value=storage_result), \
             patch.object(invoice_service, '_update_status') as mock_update_status:
            send_result = invoice_service.send_invoice(
                TENANT, INVOICE_ID,
                options={'send_email': True, 'output_destination': 'gdrive'},
                output_service=mock_output_service,
            )

        assert send_result['success'] is True
        assert send_result['invoice_number'] == INVOICE_NUMBER
        mock_output_service.check_health.assert_called_once_with('gdrive', TENANT)
        mock_booking_helper.book_outgoing_invoice.assert_called_once()

        # Verify status updated to 'sent'
        mock_update_status.assert_called_once()
        assert mock_update_status.call_args[0][2] == 'sent'

        # ── Step 3: Create Credit Note ──────────────────────
        sent_invoice = {**full_invoice, 'status': 'sent'}
        credit_note = {
            'id': CN_ID,
            'invoice_number': CN_NUMBER,
            'invoice_type': 'credit_note',
            'contact_id': CONTACT_ID,
            'invoice_date': '2026-07-01',
            'due_date': '2026-07-31',
            'payment_terms_days': 30,
            'currency': 'EUR',
            'exchange_rate': 1.0,
            'revenue_account': REVENUE_ACCOUNT,
            'status': 'draft',
            'subtotal': -LINE_TOTAL,
            'vat_total': -VAT_AMOUNT,
            'grand_total': -GRAND_TOTAL,
            'notes': f'Creditnota voor {INVOICE_NUMBER}',
            'original_invoice_id': INVOICE_ID,
            'contact': {
                'id': CONTACT_ID,
                'client_id': CLIENT_ID,
                'company_name': COMPANY_NAME,
            },
            'lines': [
                {
                    'id': 2,
                    'product_id': PRODUCT_ID,
                    'description': 'Software Development - June 2026',
                    'quantity': -QUANTITY,
                    'unit_price': UNIT_PRICE,
                    'vat_code': 'high',
                    'vat_rate': VAT_RATE,
                    'line_total': -LINE_TOTAL,
                    'vat_amount': -VAT_AMOUNT,
                }
            ],
            'vat_summary': [
                {
                    'vat_code': 'high',
                    'vat_rate': VAT_RATE,
                    'base_amount': -LINE_TOTAL,
                    'vat_amount': -VAT_AMOUNT,
                }
            ],
        }

        mock_db.execute_query.side_effect = [
            # get_invoice (original): _get_invoice_raw
            [sent_invoice],
            # get_invoice (original): contact
            [{'id': CONTACT_ID, 'client_id': CLIENT_ID, 'company_name': COMPANY_NAME}],
            # get_invoice (original): lines
            sent_invoice['lines'],
            # get_invoice (original): vat_summary
            sent_invoice['vat_summary'],
            # INSERT INTO invoices (credit note)
            CN_ID,
            # _save_lines
            None,
            # _update_totals: UPDATE
            None,
            # _update_totals: SELECT vat_summary
            [{'vat_code': 'high', 'vat_rate': VAT_RATE,
              'base_amount': -LINE_TOTAL, 'vat_amount': -VAT_AMOUNT}],
            # get_invoice (credit note): _get_invoice_raw
            [credit_note],
            # get_invoice (credit note): contact
            [{'id': CONTACT_ID, 'client_id': CLIENT_ID, 'company_name': COMPANY_NAME}],
            # get_invoice (credit note): lines
            credit_note['lines'],
            # get_invoice (credit note): vat_summary
            credit_note['vat_summary'],
        ]

        with patch.object(invoice_service, '_generate_invoice_number',
                          return_value=CN_NUMBER):
            result_cn = invoice_service.create_credit_note(TENANT, INVOICE_ID, USER_EMAIL)

        assert result_cn['id'] == CN_ID
        assert result_cn['invoice_number'] == CN_NUMBER
        assert result_cn['invoice_type'] == 'credit_note'
        assert result_cn['original_invoice_id'] == INVOICE_ID
        assert result_cn['status'] == 'draft'
        assert result_cn['grand_total'] == -GRAND_TOTAL

        # ── Step 4: Send Credit Note ────────────────────────
        cn_storage_result = {
            'url': 'https://drive.google.com/file/d/cn456',
            'filename': f'{CN_NUMBER}.pdf',
        }

        # Reset mocks for the send
        mock_output_service.check_health.reset_mock()
        mock_booking_helper.book_outgoing_invoice.reset_mock()
        mock_booking_helper.book_credit_note = Mock(return_value=[
            {'ID': 2, 'TransactionDescription': f'Creditnota {CN_NUMBER} {CLIENT_ID}'}
        ])

        mock_db.execute_query.side_effect = [
            # get_invoice (credit note inside send_invoice): _get_invoice_raw
            [credit_note],
            # get_invoice (credit note): contact
            [{'id': CONTACT_ID, 'client_id': CLIENT_ID, 'company_name': COMPANY_NAME}],
            # get_invoice (credit note): lines
            credit_note['lines'],
            # get_invoice (credit note): vat_summary
            credit_note['vat_summary'],
            # get_invoice (original, for book_credit_note): _get_invoice_raw
            [sent_invoice],
            # get_invoice (original): contact
            [{'id': CONTACT_ID, 'client_id': CLIENT_ID, 'company_name': COMPANY_NAME}],
            # get_invoice (original): lines
            sent_invoice['lines'],
            # get_invoice (original): vat_summary
            sent_invoice['vat_summary'],
            # _update_status (original → credited)
            None,
            # _update_status (credit note → sent)
            None,
        ]

        with patch.object(invoice_service, '_store_pdf', return_value=cn_storage_result), \
             patch.object(invoice_service, '_update_status') as mock_cn_update_status:
            cn_send_result = invoice_service.send_invoice(
                TENANT, CN_ID,
                options={'send_email': True, 'output_destination': 'gdrive'},
                output_service=mock_output_service,
            )

        # Verify credit note send was successful
        assert cn_send_result['success'] is True
        assert cn_send_result['invoice_number'] == CN_NUMBER

        # Verify health check was called for credit note send
        mock_output_service.check_health.assert_called_once_with('gdrive', TENANT)

        # Verify booking helper booked the credit note (not outgoing invoice)
        mock_booking_helper.book_credit_note.assert_called_once()
        cn_booking_call = mock_booking_helper.book_credit_note.call_args
        assert cn_booking_call[0][0] == TENANT
        assert cn_booking_call[0][1]['invoice_number'] == CN_NUMBER
        # Original invoice passed as third arg
        assert cn_booking_call[0][2]['invoice_number'] == INVOICE_NUMBER
        # Storage result passed as fourth arg
        assert cn_booking_call[0][3] == cn_storage_result

        # ── Step 5: Verify original invoice marked 'credited' ──
        # _update_status should have been called twice:
        # 1. original invoice → 'credited'
        # 2. credit note → 'sent'
        assert mock_cn_update_status.call_count == 2

        # First call: original invoice marked credited
        credited_call = mock_cn_update_status.call_args_list[0]
        assert credited_call[0][0] == TENANT
        assert credited_call[0][1] == INVOICE_ID
        assert credited_call[0][2] == 'credited'

        # Second call: credit note marked sent
        sent_call = mock_cn_update_status.call_args_list[1]
        assert sent_call[0][0] == TENANT
        assert sent_call[0][1] == CN_ID
        assert sent_call[0][2] == 'sent'

        # Verify email was sent for credit note
        mock_email_service.send_invoice_email.assert_called()
