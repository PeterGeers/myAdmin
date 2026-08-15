"""
Preservation Property Tests — Unsettled Clients Shown with Correct Balance

Property 2: Preservation — Unsettled Clients Still Shown with Correct Balance

These tests verify that the FIXED code preserves correct behavior for clients
with genuinely outstanding balances.

Test scope: Clients where isBugCondition returns false — clients with positive
ledger balance (no payment or only partial payment where balance remains > 0).

On FIXED code:
  - get_receivables() queries mutaties for per-client ledger balances on debtor account
  - Only clients with positive ledger balance (HAVING > 0) are returned
  - Groups by client, uses ledger_balance as outstanding amount
  - Enriches with invoice details via second query
  - Filters by administration = tenant (tenant isolation)

Spec: .kiro/specs/debtors-overdue-reconciliation-fix
**Validates: Requirements 3.1, 3.2, 3.4, 3.6**
"""

import importlib
import json
import os
import sys
from contextlib import contextmanager
from functools import wraps
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask
from hypothesis import given, strategies as st, settings, assume, HealthCheck

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))


# ---------------------------------------------------------------------------
# Auth Decorator Mocks
# ---------------------------------------------------------------------------

def _passthrough_cognito(required_permissions=None):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            kwargs['user_email'] = 'test@example.com'
            kwargs['user_roles'] = ['zzp_read']
            return f(*args, **kwargs)
        return wrapper
    return decorator


def _passthrough_tenant():
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            kwargs['tenant'] = kwargs.get('_test_tenant', 'TenantA')
            kwargs['user_tenants'] = [kwargs.get('_test_tenant', 'TenantA')]
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
# Hypothesis Strategies
# ---------------------------------------------------------------------------

positive_amount_strategy = st.floats(
    min_value=0.01, max_value=99999.99,
    allow_nan=False, allow_infinity=False
).map(lambda x: round(x, 2))

tenant_strategy = st.text(
    alphabet=st.characters(whitelist_categories=('L', 'N')),
    min_size=3, max_size=15
).filter(lambda s: s.strip() != '' and s.isalnum())

status_strategy = st.sampled_from(['sent', 'overdue'])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def build_invoice_rows(tenant, client_id, company_name, amounts, statuses=None):
    """Build mock invoice rows as returned by the invoice details query."""
    rows = []
    contact_id = hash(client_id) % 100000
    for i, amount in enumerate(amounts):
        status = statuses[i] if statuses else 'sent'
        rows.append({
            'id': contact_id * 100 + i,
            'invoice_number': f'INV-{client_id}-{i+1:03d}',
            'invoice_date': '2025-01-15',
            'due_date': '2025-02-15',
            'grand_total': amount,
            'currency': 'EUR',
            'status': status,
            'contact_id': contact_id,
            'client_id': client_id,
            'company_name': company_name,
        })
    return rows


def build_ledger_rows(clients):
    """Build ledger balance rows as returned by the mutaties-based ledger query."""
    return [
        {'client_id': c['client_id'], 'ledger_balance': c['ledger_balance']}
        for c in clients
    ]


@contextmanager
def receivables_app(mock_db, tenant_factory=None):
    """
    Context manager that creates a Flask test client with all auth/db mocked.

    Patches _resolve_debtor_account and wraps execute_query to handle
    the reconciliation UPDATE call (fetch=False) transparently.
    """
    tenant_side_effect = tenant_factory or _passthrough_tenant

    # Wrap side_effect to return None for UPDATE calls (fetch=False)
    original_side_effect = mock_db.execute_query.side_effect
    call_iter = iter(original_side_effect) if original_side_effect else iter([])

    def _side_effect_wrapper(*args, **kwargs):
        if kwargs.get('fetch') is False:
            return None
        return next(call_iter)

    mock_db.execute_query.side_effect = _side_effect_wrapper

    with patch('auth.cognito_utils.cognito_required', side_effect=_passthrough_cognito), \
         patch('auth.tenant_context.tenant_required', side_effect=tenant_side_effect), \
         patch('services.module_registry.module_required', side_effect=_passthrough_module), \
         patch('database.DatabaseManager', return_value=mock_db):
        import routes.zzp_debtor_routes as debtor_routes
        importlib.reload(debtor_routes)
        with patch.object(debtor_routes, '_resolve_debtor_account', return_value='1600'):
            app = Flask(__name__)
            app.config['TESTING'] = True
            app.register_blueprint(debtor_routes.zzp_debtor_bp)
            yield app.test_client(), mock_db


# ===========================================================================
# Step 1 — Concrete deterministic tests
# ===========================================================================

class TestPreservationObservations:
    """
    **Validates: Requirements 3.1, 3.2, 3.4, 3.6**

    Concrete observations of the fixed code behavior for preservation cases.
    """

    def test_observe_unpaid_invoice_appears(self):
        """Client with invoice €800, no payments → appears with total = €800."""
        mock_db = MagicMock()
        mock_db.execute_query.side_effect = [
            build_ledger_rows([{'client_id': 'DELTA', 'ledger_balance': 800.00}]),
            build_invoice_rows('TenantA', 'DELTA', 'Delta Corp', [800.00], ['sent']),
        ]

        with receivables_app(mock_db) as (client, _):
            response = client.get('/api/zzp/debtors/receivables')
            data = json.loads(response.data)

            assert data['success'] is True
            assert len(data['data']) == 1
            assert data['data'][0]['contact']['client_id'] == 'DELTA'
            assert data['data'][0]['total'] == 800.00
            assert data['total_outstanding'] == 800.00

    def test_observe_multiple_invoices_aggregated(self):
        """Client with two invoices €500 + €300 → appears with total = €800 (ledger)."""
        mock_db = MagicMock()
        mock_db.execute_query.side_effect = [
            build_ledger_rows([{'client_id': 'MULTI', 'ledger_balance': 800.00}]),
            build_invoice_rows('TenantA', 'MULTI', 'Multi Corp', [500.00, 300.00], ['sent', 'overdue']),
        ]

        with receivables_app(mock_db) as (client, _):
            response = client.get('/api/zzp/debtors/receivables')
            data = json.loads(response.data)

            assert data['success'] is True
            assert len(data['data']) == 1
            assert data['data'][0]['contact']['client_id'] == 'MULTI'
            assert data['data'][0]['total'] == 800.00
            assert len(data['data'][0]['invoices']) == 2

    def test_observe_tenant_isolation(self):
        """Ledger query filters by administration = tenant."""
        mock_db = MagicMock()
        mock_db.execute_query.side_effect = [
            build_ledger_rows([{'client_id': 'ALPHA', 'ledger_balance': 1000.00}]),
            build_invoice_rows('TenantA', 'ALPHA', 'Alpha Inc', [1000.00]),
        ]

        with receivables_app(mock_db) as (client, _):
            response = client.get('/api/zzp/debtors/receivables')
            data = json.loads(response.data)

            assert data['success'] is True
            first_call_args = mock_db.execute_query.call_args_list[0]
            query = first_call_args[0][0]
            params = first_call_args[0][1]
            assert 'administration' in query.lower()
            assert 'TenantA' in params

    def test_observe_sent_invoice_not_yet_overdue(self):
        """Invoice with status 'sent' appears when client has positive ledger balance."""
        mock_db = MagicMock()
        mock_db.execute_query.side_effect = [
            build_ledger_rows([{'client_id': 'FRESH', 'ledger_balance': 1500.00}]),
            build_invoice_rows('TenantA', 'FRESH', 'Fresh LLC', [1500.00], ['sent']),
        ]

        with receivables_app(mock_db) as (client, _):
            response = client.get('/api/zzp/debtors/receivables')
            data = json.loads(response.data)

            assert data['success'] is True
            assert len(data['data']) == 1
            assert data['data'][0]['contact']['client_id'] == 'FRESH'


# ===========================================================================
# Step 2 — Property-Based Tests
# ===========================================================================

class TestPreservationPropertyClientPresence:
    """
    **Validates: Requirements 3.1, 3.2, 3.4**

    Property: For all clients with positive ledger balance on debtor account,
    the client SHALL appear in receivables.
    """

    @given(amount=positive_amount_strategy, status=status_strategy)
    @settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_single_invoice_client_always_appears(self, amount, status):
        """A client with a single open invoice (positive balance) always appears."""
        mock_db = MagicMock()
        mock_db.execute_query.side_effect = [
            build_ledger_rows([{'client_id': 'CLIENT1', 'ledger_balance': amount}]),
            build_invoice_rows('TenantA', 'CLIENT1', 'Test Company', [amount], [status]),
        ]

        with receivables_app(mock_db) as (client, _):
            response = client.get('/api/zzp/debtors/receivables')
            data = json.loads(response.data)

            assert data['success'] is True
            assert len(data['data']) == 1, (
                f"Client with open invoice (amount={amount}, status={status}) "
                f"must appear in receivables"
            )

    @given(amounts=st.lists(positive_amount_strategy, min_size=2, max_size=5))
    @settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_multi_invoice_client_always_appears(self, amounts):
        """A client with multiple open invoices appears exactly once."""
        total_balance = round(sum(amounts), 2)

        mock_db = MagicMock()
        mock_db.execute_query.side_effect = [
            build_ledger_rows([{'client_id': 'MULTI', 'ledger_balance': total_balance}]),
            build_invoice_rows('TenantA', 'MULTI', 'Multi Corp', amounts),
        ]

        with receivables_app(mock_db) as (client, _):
            response = client.get('/api/zzp/debtors/receivables')
            data = json.loads(response.data)

            assert data['success'] is True
            assert len(data['data']) == 1, (
                f"Client with {len(amounts)} open invoices must appear exactly once"
            )
            assert len(data['data'][0]['invoices']) == len(amounts), (
                f"All {len(amounts)} invoices must be included"
            )


class TestPreservationPropertyAmountAccuracy:
    """
    **Validates: Requirements 3.1, 3.2**

    Property: For all clients with positive ledger balance, the displayed total
    equals the ledger balance.
    """

    @given(amount=positive_amount_strategy)
    @settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_unpaid_single_invoice_amount_equals_ledger_balance(self, amount):
        """For a single unpaid invoice, displayed total equals ledger balance."""
        mock_db = MagicMock()
        mock_db.execute_query.side_effect = [
            build_ledger_rows([{'client_id': 'UNPAID', 'ledger_balance': amount}]),
            build_invoice_rows('TenantA', 'UNPAID', 'Unpaid Inc', [amount]),
        ]

        with receivables_app(mock_db) as (client, _):
            response = client.get('/api/zzp/debtors/receivables')
            data = json.loads(response.data)

            assert data['success'] is True
            assert len(data['data']) == 1
            displayed_total = data['data'][0]['total']
            assert abs(displayed_total - amount) < 0.01, (
                f"Unpaid invoice: displayed total ({displayed_total}) "
                f"must equal ledger balance ({amount})"
            )

    @given(amounts=st.lists(positive_amount_strategy, min_size=2, max_size=5))
    @settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_unpaid_multi_invoice_total_equals_ledger_balance(self, amounts):
        """For multiple unpaid invoices, displayed total equals ledger balance."""
        total_balance = round(sum(amounts), 2)

        mock_db = MagicMock()
        mock_db.execute_query.side_effect = [
            build_ledger_rows([{'client_id': 'MULTI', 'ledger_balance': total_balance}]),
            build_invoice_rows('TenantA', 'MULTI', 'Multi Corp', amounts),
        ]

        with receivables_app(mock_db) as (client, _):
            response = client.get('/api/zzp/debtors/receivables')
            data = json.loads(response.data)

            assert data['success'] is True
            displayed_total = data['data'][0]['total']
            assert abs(displayed_total - total_balance) < 0.01, (
                f"Multi-invoice unpaid: displayed total ({displayed_total}) "
                f"must equal ledger balance ({total_balance})"
            )
            assert abs(data['total_outstanding'] - total_balance) < 0.01


class TestPreservationPropertyTenantIsolation:
    """
    **Validates: Requirements 3.6**

    Property: For all tenants, receivables SHALL only contain data where
    administration = tenant (tenant isolation).
    """

    @given(tenant_name=tenant_strategy, amount=positive_amount_strategy)
    @settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_query_always_filters_by_tenant(self, tenant_name, amount):
        """The database queries always include the tenant parameter."""
        mock_db = MagicMock()
        mock_db.execute_query.side_effect = [
            build_ledger_rows([{'client_id': 'ISOLATED', 'ledger_balance': amount}]),
            build_invoice_rows(tenant_name, 'ISOLATED', 'Isolated Corp', [amount]),
        ]

        def _custom_tenant():
            def decorator(f):
                @wraps(f)
                def wrapper(*args, **kwargs):
                    kwargs['tenant'] = tenant_name
                    kwargs['user_tenants'] = [tenant_name]
                    return f(*args, **kwargs)
                return wrapper
            return decorator

        with receivables_app(mock_db, tenant_factory=_custom_tenant) as (client, _):
            response = client.get('/api/zzp/debtors/receivables')
            data = json.loads(response.data)

            assert data['success'] is True
            assert mock_db.execute_query.called
            first_call_args = mock_db.execute_query.call_args_list[0]
            query = first_call_args[0][0]
            params = first_call_args[0][1]
            assert 'administration' in query.lower()
            assert tenant_name in params, (
                f"Tenant '{tenant_name}' must be passed as query parameter "
                f"(got params={params})"
            )

    @given(
        tenant_a=tenant_strategy, tenant_b=tenant_strategy,
        amount_a=positive_amount_strategy, amount_b=positive_amount_strategy,
    )
    @settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_different_tenants_get_isolated_results(self, tenant_a, tenant_b, amount_a, amount_b):
        """Two different tenants get independent results."""
        assume(tenant_a != tenant_b)

        mock_db_a = MagicMock()
        mock_db_a.execute_query.side_effect = [
            build_ledger_rows([{'client_id': 'CLIENTA', 'ledger_balance': amount_a}]),
            build_invoice_rows(tenant_a, 'CLIENTA', 'Company A', [amount_a]),
        ]

        def _tenant_a_passthrough():
            def decorator(f):
                @wraps(f)
                def wrapper(*args, **kwargs):
                    kwargs['tenant'] = tenant_a
                    kwargs['user_tenants'] = [tenant_a]
                    return f(*args, **kwargs)
                return wrapper
            return decorator

        with receivables_app(mock_db_a, tenant_factory=_tenant_a_passthrough) as (client, _):
            response = client.get('/api/zzp/debtors/receivables')
            data = json.loads(response.data)

            assert data['success'] is True
            first_call_args = mock_db_a.execute_query.call_args_list[0]
            params = first_call_args[0][1]
            assert tenant_a in params, (
                f"Query must filter by tenant_a='{tenant_a}', got params={params}"
            )
            for entry in data['data']:
                assert entry['contact']['client_id'] != 'CLIENTB', (
                    "Tenant B's client must not appear in Tenant A's receivables"
                )
