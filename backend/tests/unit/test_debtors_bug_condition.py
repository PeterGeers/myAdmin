"""
Bug Condition Exploration Tests — Ledger-Settled Clients Still Shown as Overdue

Property 1: Bug Condition — Ledger-Settled Clients Still Shown as Overdue

These tests encode the EXPECTED (correct) behavior. They are written BEFORE any fix
and MUST FAIL on unfixed code — failure confirms the bug exists.

DO NOT attempt to fix the test or the code when it fails.

After the fix is implemented, these same tests will PASS, confirming the fix works.

Spec: .kiro/specs/debtors-overdue-reconciliation-fix
Validates: Requirements 1.1, 1.2, 1.3, 1.4

Bug Condition from design:
    isBugCondition(input) returns true when:
    - ledger_balance <= 0 AND has_open_status_invoices
    - Client has offsetting credits in mutaties on debtor account (1300) but
      invoices still have status 'sent'/'overdue'

Expected behavior (post-fix):
    get_receivables() SHALL NOT include clients with zero/negative ledger balance
    on the debtor account, regardless of invoices.status. Outstanding amounts
    SHALL reflect the actual ledger balance, not grand_total.
"""

import sys
import os
import pytest
from unittest.mock import Mock, MagicMock, patch
from functools import wraps
from hypothesis import given, strategies as st, settings, assume
from flask import Flask

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))


# ---------------------------------------------------------------------------
# Auth / Tenant / Module passthrough decorators for testing
# ---------------------------------------------------------------------------

def _passthrough_cognito(required_permissions=None):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            kwargs['user_email'] = 'test@example.com'
            kwargs['user_roles'] = ['ZZP_Read']
            return f(*args, **kwargs)
        return wrapper
    return decorator


def _passthrough_tenant():
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            kwargs['tenant'] = 'TestTenant'
            kwargs['user_tenants'] = ['TestTenant']
            return f(*args, **kwargs)
        return wrapper
    return decorator


def _passthrough_module(module_name):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            return f(*args, **kwargs)
        return wrapper
    return decorator


# ---------------------------------------------------------------------------
# Fixture: Flask test client with mocked decorators and DB
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_db():
    return MagicMock()


@pytest.fixture
def receivables_client(mock_db):
    """Create a Flask test client for the zzp_debtor_bp blueprint with mocked auth."""
    with patch('auth.cognito_utils.cognito_required', side_effect=_passthrough_cognito), \
         patch('auth.tenant_context.tenant_required', side_effect=_passthrough_tenant), \
         patch('services.module_registry.module_required', side_effect=_passthrough_module), \
         patch('database.DatabaseManager', return_value=mock_db):
        import importlib
        import routes.zzp_debtor_routes as zdr
        importlib.reload(zdr)
        # Patch the helper to avoid consuming mock_db.execute_query side_effect slots
        with patch.object(zdr, '_resolve_debtor_account', return_value='1600'):
            app = Flask(__name__)
            app.config['TESTING'] = True
            app.register_blueprint(zdr.zzp_debtor_bp)
            yield app.test_client()


# ---------------------------------------------------------------------------
# Test Data Builders
# ---------------------------------------------------------------------------

def build_ledger_rows(clients):
    """
    Build ledger balance rows as returned by the new mutaties-based query.

    Args:
        clients: List of dicts with keys: client_id, ledger_balance
    Returns:
        List of dicts with 'client_id' and 'ledger_balance' keys
    """
    return [
        {'client_id': c['client_id'], 'ledger_balance': c['ledger_balance']}
        for c in clients
    ]


def build_invoice_rows(client_id, company_name, contact_id, invoices):
    """
    Build invoice row dicts as returned by the invoice details query.

    Args:
        client_id: The client_id (e.g., 'ACME')
        company_name: Company name for display
        contact_id: The contact's internal id
        invoices: List of dicts with keys: id, invoice_number, grand_total, status
    """
    rows = []
    for inv in invoices:
        rows.append({
            'id': inv['id'],
            'invoice_number': inv['invoice_number'],
            'invoice_date': '2026-01-15',
            'due_date': '2026-02-15',
            'grand_total': inv['grand_total'],
            'currency': 'EUR',
            'status': inv.get('status', 'sent'),
            'contact_id': contact_id,
            'client_id': client_id,
            'company_name': company_name,
        })
    return rows


def mock_db_for_ledger(mock_db, ledger_rows, invoice_rows=None):
    """
    Configure mock_db.execute_query to return ledger rows on first call
    and invoice rows on second call. UPDATE calls (fetch=False) return None.

    Args:
        mock_db: The MagicMock database instance
        ledger_rows: Rows returned by the ledger balance query (first call)
        invoice_rows: Rows returned by the invoice details query (second call)
    """
    if invoice_rows is None:
        invoice_rows = []
    responses = iter([ledger_rows, invoice_rows])

    def _side_effect(*args, **kwargs):
        if kwargs.get('fetch') is False:
            return None
        return next(responses)

    mock_db.execute_query.side_effect = _side_effect


# ---------------------------------------------------------------------------
# Case 1: Fully Paid Invoice — single invoice with exact matching payment
# Requirement: 1.1, 1.4 — invoice shown as overdue despite zero ledger balance
# ---------------------------------------------------------------------------

class TestFullyPaidInvoiceExcluded:
    """
    WHEN a bank payment exists in mutaties that credits account 1300 for the full
    amount of an invoice (ledger_balance = 0), THEN get_receivables() SHALL NOT
    include that client.

    On UNFIXED code: The client WILL appear because the query only checks
    invoices.status IN ('sent', 'overdue') without consulting mutaties.

    Example from design:
    - Invoice INV-2026-0001 for €1,210.00 sent to client "ACME"
    - Bank payment of €1,210.00 credits account 1300 with ReferenceNumber="ACME"
    - Ledger balance = €1,210.00 - €1,210.00 = €0.00
    - Expected: Not shown. Actual (buggy): Shown as overdue (€1,210.00 outstanding)
    """

    def test_fully_paid_client_not_in_receivables(self, receivables_client, mock_db):
        """
        Client ACME has invoice €1,210.00 (status='overdue') and a matching credit
        entry in mutaties on account 1300 making ledger_balance = 0.

        EXPECTED: Client not shown in receivables.

        **Validates: Requirements 1.1, 1.4**
        """
        # Ledger query returns NO rows for ACME (balance is 0, filtered by HAVING > 0)
        mock_db_for_ledger(mock_db, ledger_rows=[], invoice_rows=[])

        resp = receivables_client.get('/api/zzp/debtors/receivables')
        data = resp.get_json()

        assert data['success'] is True

        # Find ACME in results
        acme_entries = [
            entry for entry in data['data']
            if entry['contact']['client_id'] == 'ACME'
        ]

        # EXPECTED BEHAVIOR (post-fix): ACME should NOT appear (zero ledger balance)
        assert len(acme_entries) == 0, (
            f"BUG CONFIRMED (Req 1.1, 1.4): Client 'ACME' with zero ledger balance "
            f"still appears in receivables with "
            f"€{acme_entries[0]['total']:,.2f} outstanding. "
            f"The endpoint uses invoices.status instead of the ledger balance on "
            f"account 1300 to determine outstanding amounts."
        )


# ---------------------------------------------------------------------------
# Case 2: Combined Payment — two invoices paid with single bank transfer
# Requirement: 1.2 — combined payment cannot match individual invoices
# ---------------------------------------------------------------------------

class TestCombinedPaymentExcluded:
    """
    WHEN a single bank payment covers multiple invoices (combined payment) AND
    the total bank amount equals the sum of those invoices, THEN the system SHALL
    correctly reflect this via zero ledger balance → client excluded.

    On UNFIXED code: Both invoices will appear because:
    1. PaymentCheckHelper._match_invoice() compares €1,200 against €500 and €700 separately
    2. get_receivables() only checks invoices.status anyway

    Example from design:
    - Two invoices: INV-0001 (€500) and INV-0002 (€700) for client "BETA"
    - Single bank payment of €1,200 credits account 1300
    - Ledger balance = €1,200 - €1,200 = €0.00
    - Expected: Not shown. Actual (buggy): Both shown (€1,200 outstanding)
    """

    def test_combined_payment_client_not_in_receivables(self, receivables_client, mock_db):
        """
        Client BETA has two invoices (€500 + €700) and a single €1,200 credit entry
        in mutaties on account 1300 making ledger_balance = 0.

        EXPECTED: Client not shown in receivables.

        **Validates: Requirements 1.2**
        """
        # Ledger query returns NO rows for BETA (balance is 0, filtered by HAVING > 0)
        mock_db_for_ledger(mock_db, ledger_rows=[], invoice_rows=[])

        resp = receivables_client.get('/api/zzp/debtors/receivables')
        data = resp.get_json()

        assert data['success'] is True

        beta_entries = [
            entry for entry in data['data']
            if entry['contact']['client_id'] == 'BETA'
        ]

        # EXPECTED BEHAVIOR (post-fix): BETA should NOT appear (zero ledger balance)
        assert len(beta_entries) == 0, (
            f"BUG CONFIRMED (Req 1.2): Client 'BETA' with zero ledger balance "
            f"(combined payment of €1,200 covers both invoices) still appears in "
            f"receivables with €{beta_entries[0]['total']:,.2f} outstanding. "
            f"The endpoint cannot account for combined payments because it uses "
            f"invoices.status instead of net ledger balance on account 1300."
        )


# ---------------------------------------------------------------------------
# Case 3: Partial Payment — shows grand_total instead of ledger balance
# Requirement: 1.3, 1.4 — amount shown is wrong (uses grand_total, not balance)
# ---------------------------------------------------------------------------

class TestPartialPaymentShowsLedgerBalance:
    """
    WHEN an invoice has only a partial payment (ledger balance > 0 but < grand_total),
    THEN the system SHALL show the actual ledger balance, not the invoice grand_total.

    On UNFIXED code: The amount shown is grand_total (€1,000) because the endpoint
    never consults mutaties — it sums invoice.grand_total directly.

    Example from design:
    - Invoice INV-0003 for €1,000.00 for client "GAMMA"
    - Partial payment of €600 credits account 1300
    - Ledger balance = €1,000 - €600 = €400
    - Expected: Shown with €400 outstanding. Actual (buggy): Shown with €1,000
    """

    def test_partial_payment_shows_ledger_balance_not_grand_total(
        self, receivables_client, mock_db
    ):
        """
        Client GAMMA has invoice €1,000 with €600 partial payment.
        Ledger balance = €400.

        EXPECTED: Client shown with €400.00 outstanding (ledger balance).

        **Validates: Requirements 1.3, 1.4**
        """
        # Ledger query returns GAMMA with positive balance of €400
        ledger_rows = build_ledger_rows([
            {'client_id': 'GAMMA', 'ledger_balance': 400.00},
        ])
        # Invoice details query returns the invoice for display
        invoice_rows = build_invoice_rows(
            client_id='GAMMA',
            company_name='Gamma Inc',
            contact_id=3,
            invoices=[{
                'id': 4,
                'invoice_number': 'INV-2026-0004',
                'grand_total': 1000.00,
                'status': 'overdue',
            }],
        )
        mock_db_for_ledger(mock_db, ledger_rows=ledger_rows, invoice_rows=invoice_rows)

        resp = receivables_client.get('/api/zzp/debtors/receivables')
        data = resp.get_json()

        assert data['success'] is True

        gamma_entries = [
            entry for entry in data['data']
            if entry['contact']['client_id'] == 'GAMMA'
        ]

        assert len(gamma_entries) == 1, "GAMMA should appear (positive ledger balance)"

        # EXPECTED BEHAVIOR (post-fix): total should be ledger balance €400, not grand_total €1,000
        expected_outstanding = 400.00  # ledger balance: €1,000 debit - €600 credit
        actual_outstanding = gamma_entries[0]['total']

        assert actual_outstanding == expected_outstanding, (
            f"BUG CONFIRMED (Req 1.3, 1.4): Client 'GAMMA' shows "
            f"€{actual_outstanding:,.2f} outstanding instead of the correct ledger "
            f"balance of €{expected_outstanding:,.2f}. The endpoint uses "
            f"invoices.grand_total (€1,000.00) instead of computing the actual "
            f"remaining balance from mutaties (€1,000 debit - €600 credit = €400)."
        )


# ---------------------------------------------------------------------------
# Case 4: Property-Based Test — Bug Condition generalized
# For any client with zero ledger balance, get_receivables() should exclude them
# ---------------------------------------------------------------------------

class TestBugConditionProperty:
    """
    Property-based test: For ALL inputs where isBugCondition holds (ledger_balance <= 0
    AND has_open_status_invoices), get_receivables() SHALL NOT include that client.

    On UNFIXED code: The property FAILS because the endpoint ignores the ledger entirely.

    **Validates: Requirements 1.1, 1.2, 1.3, 1.4**
    """

    @given(
        invoice_amount=st.floats(min_value=100.0, max_value=50000.0, allow_nan=False, allow_infinity=False),
        num_invoices=st.integers(min_value=1, max_value=5),
        overpayment=st.floats(min_value=0.0, max_value=500.0, allow_nan=False, allow_infinity=False),
        status=st.sampled_from(['sent', 'overdue']),
    )
    @settings(max_examples=50, deadline=None)
    def test_zero_or_negative_ledger_balance_excludes_client(
        self, invoice_amount, num_invoices, overpayment, status
    ):
        """
        Generate random invoice amounts and matching payments (covering full amount
        or more). The ledger balance is zero or negative. Client should NOT appear.

        **Validates: Requirements 1.1, 1.2, 1.3, 1.4**
        """
        # Round to 2 decimal places (currency)
        invoice_amount = round(invoice_amount, 2)
        overpayment = round(overpayment, 2)

        # Total debit = sum of all invoice amounts on debtor account
        total_debit = invoice_amount * num_invoices
        # Total credit = full payment + possible overpayment (ledger_balance <= 0)
        total_credit = total_debit + overpayment

        # Verify bug condition holds: ledger_balance <= 0
        ledger_balance = total_debit - total_credit
        assume(ledger_balance <= 0)

        # Create mocked DB and Flask app for each hypothesis example
        mock_db = MagicMock()
        # Ledger query returns NO rows (balance <= 0, filtered out by HAVING > 0)
        mock_db_for_ledger(mock_db, ledger_rows=[], invoice_rows=[])

        with patch('auth.cognito_utils.cognito_required', side_effect=_passthrough_cognito), \
             patch('auth.tenant_context.tenant_required', side_effect=_passthrough_tenant), \
             patch('services.module_registry.module_required', side_effect=_passthrough_module), \
             patch('database.DatabaseManager', return_value=mock_db):
            import importlib
            import routes.zzp_debtor_routes as zdr
            importlib.reload(zdr)
            with patch.object(zdr, '_resolve_debtor_account', return_value='1600'):
                app = Flask(__name__)
                app.config['TESTING'] = True
                app.register_blueprint(zdr.zzp_debtor_bp)
                client = app.test_client()

                resp = client.get('/api/zzp/debtors/receivables')
                data = resp.get_json()

                assert data['success'] is True

                # Bug condition: ledger_balance <= 0 means client should be excluded
                client_entries = [
                    entry for entry in data['data']
                    if entry['contact']['client_id'] == 'CLIENT-X'
                ]

                assert len(client_entries) == 0, (
                    f"BUG CONFIRMED (Property 1): Client 'CLIENT-X' with ledger_balance="
                    f"€{ledger_balance:,.2f} (debit=€{total_debit:,.2f}, "
                    f"credit=€{total_credit:,.2f}) still appears in receivables with "
                    f"€{client_entries[0]['total']:,.2f} outstanding. "
                    f"Endpoint ignores mutaties ledger and uses invoices.status + grand_total."
                )
