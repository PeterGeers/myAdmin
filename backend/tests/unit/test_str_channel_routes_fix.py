"""
Unit tests for STR channel routes fix — verifying hardcoded account resolution
is replaced with authoritative sources (rekeningschema.parameters and TaxRateService).

Requirements: 2.3, 2.4, 3.3
"""

import pytest
import json
import sys
import os
from unittest.mock import patch, MagicMock
from flask import Flask

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))


def _bypass_cognito_required(**decorator_kwargs):
    """Mock cognito_required to inject user_email and user_roles without JWT validation."""
    def decorator(f):
        import functools

        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            kwargs['user_email'] = 'test@example.com'
            kwargs['user_roles'] = ['STR_CRUD']
            return f(*args, **kwargs)
        return wrapper
    return decorator


def _bypass_tenant_required(**decorator_kwargs):
    """Mock tenant_required to inject tenant and user_tenants without JWT validation."""
    def decorator(f):
        import functools

        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            kwargs['tenant'] = 'TestTenant'
            kwargs['user_tenants'] = ['TestTenant']
            return f(*args, **kwargs)
        return wrapper
    return decorator


def _bypass_function_guard(*guard_args, **guard_kwargs):
    """Mock function_guard to pass through without checking."""
    def decorator(f):
        import functools

        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            return f(*args, **kwargs)
        return wrapper
    return decorator


# Patch decorators BEFORE importing the module under test
with patch('auth.cognito_utils.cognito_required', _bypass_cognito_required):
    with patch('auth.tenant_context.tenant_required', _bypass_tenant_required):
        with patch('services.function_guard.function_guard', _bypass_function_guard):
            # Force reimport with patched decorators
            if 'str_channel_routes' in sys.modules:
                del sys.modules['str_channel_routes']
            from str_channel_routes import str_channel_bp


@pytest.fixture
def app():
    """Create Flask app for testing."""
    app = Flask(__name__)
    app.config['TESTING'] = True
    app.register_blueprint(str_channel_bp, url_prefix='/api/str-channel')
    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()


def _wire_get_cursor(mock_db):
    """Wire mock_db.get_cursor() as a context manager yielding (cursor, conn).

    Mirrors the context-managed read API (`with db.get_cursor() as (cursor, conn):`).
    Returns the mock cursor so tests can set fetchall side effects / inspect calls.
    """
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    cm = MagicMock()
    cm.__enter__.return_value = (mock_cursor, mock_conn)
    cm.__exit__.return_value = False
    mock_db.get_cursor.return_value = cm
    return mock_cursor


def _mock_channel_data(administration='TestTenant'):
    """Return sample channel data rows as returned by the DB cursor."""
    return [
        {
            'administration': administration,
            'ReferenceNumber': 'AirBnB',
            'Reknum': '1600',
            'TransactionAmount': -1090.0,
        }
    ]


class TestRevenueAccountFromFlag:
    """6.1 — Revenue account resolved from $.str_revenue_account flag."""

    @patch('str_channel_routes.TaxRateService')
    @patch('str_channel_routes.DatabaseManager')
    def test_revenue_account_resolved_from_flag(
        self, mock_db_cls, mock_tax_cls, client
    ):
        """Revenue account comes from rekeningschema $.str_revenue_account flag,
        not hardcoded '8003'."""
        mock_db = MagicMock()
        mock_db_cls.return_value = mock_db
        mock_cursor = _wire_get_cursor(mock_db)

        # Cursor returns: 1) channel data, 2) str_revenue_account rows
        channel_data = _mock_channel_data()
        str_revenue_rows = [{'Account': '8050'}]  # Non-standard account
        mock_cursor.fetchall.side_effect = [channel_data, str_revenue_rows]

        mock_tax_svc = MagicMock()
        mock_tax_cls.return_value = mock_tax_svc
        mock_tax_svc.get_tax_rate.return_value = {
            'rate': 9.0,
            'ledger_account': '2021',
            'description': 'BTW accommodation low',
        }

        response = client.post(
            '/api/str-channel/calculate',
            content_type='application/json',
            data=json.dumps({
                'year': 2025, 'month': 6,
                'administration': 'TestTenant', 'test_mode': True,
            }),
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True

        transactions = data['transactions']
        assert len(transactions) == 2

        revenue_tx = transactions[0]
        vat_tx = transactions[1]

        # Revenue Credit must be the resolved account, not '8003'
        assert revenue_tx['Credit'] == '8050'
        assert revenue_tx['Credit'] != '8003'

        # VAT Debet must also be the resolved account
        assert vat_tx['Debet'] == '8050'
        assert vat_tx['Debet'] != '8003'

    @patch('str_channel_routes.TaxRateService')
    @patch('str_channel_routes.DatabaseManager')
    def test_400_when_str_revenue_account_not_configured(
        self, mock_db_cls, mock_tax_cls, client
    ):
        """Returns 400 when no account has $.str_revenue_account flag."""
        mock_db = MagicMock()
        mock_db_cls.return_value = mock_db
        mock_cursor = _wire_get_cursor(mock_db)

        channel_data = _mock_channel_data()
        str_revenue_rows = []  # No account with the flag
        mock_cursor.fetchall.side_effect = [channel_data, str_revenue_rows]

        response = client.post(
            '/api/str-channel/calculate',
            content_type='application/json',
            data=json.dumps({
                'year': 2025, 'month': 6,
                'administration': 'TestTenant', 'test_mode': True,
            }),
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['success'] is False
        assert 'str_revenue_account' in data['error'].lower()

    @patch('str_channel_routes.TaxRateService')
    @patch('str_channel_routes.DatabaseManager')
    def test_str_revenue_query_uses_json_extract(
        self, mock_db_cls, mock_tax_cls, client
    ):
        """The rekeningschema query uses JSON_EXTRACT for $.str_revenue_account."""
        mock_db = MagicMock()
        mock_db_cls.return_value = mock_db
        mock_cursor = _wire_get_cursor(mock_db)

        channel_data = _mock_channel_data()
        str_revenue_rows = [{'Account': '8003'}]
        mock_cursor.fetchall.side_effect = [channel_data, str_revenue_rows]

        mock_tax_svc = MagicMock()
        mock_tax_cls.return_value = mock_tax_svc
        mock_tax_svc.get_tax_rate.return_value = {
            'rate': 9.0, 'ledger_account': '2021',
        }

        client.post(
            '/api/str-channel/calculate',
            content_type='application/json',
            data=json.dumps({
                'year': 2025, 'month': 6,
                'administration': 'TestTenant', 'test_mode': True,
            }),
        )

        # The second execute call should be the str_revenue_account query
        calls = mock_cursor.execute.call_args_list
        assert len(calls) >= 2
        str_revenue_sql = calls[1][0][0]
        assert 'JSON_EXTRACT' in str_revenue_sql
        assert 'str_revenue_account' in str_revenue_sql
        assert 'rekeningschema' in str_revenue_sql

        # Verify administration parameter is passed
        str_revenue_params = calls[1][0][1]
        assert 'TestTenant' in str_revenue_params


class TestTaxRateServiceIntegration:
    """6.2 — TaxRateService replaces date-branching VAT logic."""

    @patch('str_channel_routes.TaxRateService')
    @patch('str_channel_routes.DatabaseManager')
    def test_tax_rate_service_called_with_correct_params(
        self, mock_db_cls, mock_tax_cls, client
    ):
        """TaxRateService.get_tax_rate() is called with
        (administration, 'btw', 'accommodation', transaction_date)."""
        mock_db = MagicMock()
        mock_db_cls.return_value = mock_db
        mock_cursor = _wire_get_cursor(mock_db)

        channel_data = _mock_channel_data()
        str_revenue_rows = [{'Account': '8003'}]
        mock_cursor.fetchall.side_effect = [channel_data, str_revenue_rows]

        mock_tax_svc = MagicMock()
        mock_tax_cls.return_value = mock_tax_svc
        mock_tax_svc.get_tax_rate.return_value = {
            'rate': 9.0, 'ledger_account': '2021',
            'description': 'BTW accommodation low',
        }

        response = client.post(
            '/api/str-channel/calculate',
            content_type='application/json',
            data=json.dumps({
                'year': 2025, 'month': 9,
                'administration': 'TestTenant', 'test_mode': True,
            }),
        )

        assert response.status_code == 200

        # Verify TaxRateService was instantiated with the DatabaseManager
        mock_tax_cls.assert_called_once_with(mock_db)

        # Verify get_tax_rate called with correct args
        from datetime import date
        expected_date = date(2025, 9, 30)
        mock_tax_svc.get_tax_rate.assert_called_once_with(
            'TestTenant', 'btw_accommodation', 'high', expected_date
        )

    @patch('str_channel_routes.TaxRateService')
    @patch('str_channel_routes.DatabaseManager')
    def test_400_when_no_btw_accommodation_rate(
        self, mock_db_cls, mock_tax_cls, client
    ):
        """Returns 400 when TaxRateService has no accommodation rate."""
        mock_db = MagicMock()
        mock_db_cls.return_value = mock_db
        mock_cursor = _wire_get_cursor(mock_db)

        channel_data = _mock_channel_data()
        str_revenue_rows = [{'Account': '8003'}]
        mock_cursor.fetchall.side_effect = [channel_data, str_revenue_rows]

        mock_tax_svc = MagicMock()
        mock_tax_cls.return_value = mock_tax_svc
        mock_tax_svc.get_tax_rate.return_value = None  # No rate configured

        response = client.post(
            '/api/str-channel/calculate',
            content_type='application/json',
            data=json.dumps({
                'year': 2025, 'month': 6,
                'administration': 'TestTenant', 'test_mode': True,
            }),
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert data['success'] is False
        assert 'btw accommodation rate' in data['error'].lower()

    @patch('str_channel_routes.TaxRateService')
    @patch('str_channel_routes.DatabaseManager')
    def test_vat_account_from_tax_rate_service(
        self, mock_db_cls, mock_tax_cls, client
    ):
        """VAT account in journal entries comes from TaxRateService,
        not hardcoded '2020' or '2021'."""
        mock_db = MagicMock()
        mock_db_cls.return_value = mock_db
        mock_cursor = _wire_get_cursor(mock_db)

        channel_data = _mock_channel_data()
        str_revenue_rows = [{'Account': '8003'}]
        mock_cursor.fetchall.side_effect = [channel_data, str_revenue_rows]

        mock_tax_svc = MagicMock()
        mock_tax_cls.return_value = mock_tax_svc
        # Use a non-standard VAT account to prove it comes from config
        mock_tax_svc.get_tax_rate.return_value = {
            'rate': 15.0,
            'ledger_account': '2099',
            'description': 'Custom VAT rate',
        }

        response = client.post(
            '/api/str-channel/calculate',
            content_type='application/json',
            data=json.dumps({
                'year': 2025, 'month': 6,
                'administration': 'TestTenant', 'test_mode': True,
            }),
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        transactions = data['transactions']

        vat_tx = transactions[1]
        assert vat_tx['Credit'] == '2099'
        assert vat_tx['Credit'] != '2020'
        assert vat_tx['Credit'] != '2021'

        # Verify VAT amount uses the resolved rate (15%)
        # 1090 / 115 * 15 = 142.17 (rounded)
        expected_vat = round((1090.0 / 115.0) * 15.0, 2)
        assert vat_tx['TransactionAmount'] == expected_vat


class TestJournalEntryAccounts:
    """Journal entries use resolved accounts, not hardcoded values."""

    @patch('str_channel_routes.TaxRateService')
    @patch('str_channel_routes.DatabaseManager')
    def test_journal_entries_use_resolved_accounts(
        self, mock_db_cls, mock_tax_cls, client
    ):
        """All journal entries use resolved revenue and VAT accounts."""
        mock_db = MagicMock()
        mock_db_cls.return_value = mock_db
        mock_cursor = _wire_get_cursor(mock_db)

        channel_data = [
            {
                'administration': 'TestTenant',
                'ReferenceNumber': 'AirBnB',
                'Reknum': '1600',
                'TransactionAmount': -1210.0,
            },
            {
                'administration': 'TestTenant',
                'ReferenceNumber': 'Booking.com',
                'Reknum': '1600',
                'TransactionAmount': -605.0,
            },
        ]
        str_revenue_rows = [{'Account': '8099'}]
        mock_cursor.fetchall.side_effect = [channel_data, str_revenue_rows]

        mock_tax_svc = MagicMock()
        mock_tax_cls.return_value = mock_tax_svc
        mock_tax_svc.get_tax_rate.return_value = {
            'rate': 21.0,
            'ledger_account': '2099',
        }

        response = client.post(
            '/api/str-channel/calculate',
            content_type='application/json',
            data=json.dumps({
                'year': 2026, 'month': 3,
                'administration': 'TestTenant', 'test_mode': True,
            }),
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        transactions = data['transactions']
        assert len(transactions) == 4  # 2 channels × 2 transactions

        # AirBnB revenue
        assert transactions[0]['Credit'] == '8099'
        assert transactions[0]['Debet'] == '1600'
        assert transactions[0]['TransactionAmount'] == 1210.0

        # AirBnB VAT (1210 / 121 * 21 = 210)
        assert transactions[1]['Debet'] == '8099'
        assert transactions[1]['Credit'] == '2099'
        assert transactions[1]['TransactionAmount'] == 210.0

        # Booking.com revenue
        assert transactions[2]['Credit'] == '8099'
        assert transactions[2]['TransactionAmount'] == 605.0

        # Booking.com VAT (605 / 121 * 21 = 105)
        assert transactions[3]['Debet'] == '8099'
        assert transactions[3]['Credit'] == '2099'
        assert transactions[3]['TransactionAmount'] == 105.0


class TestPreservation:
    """Req 3.3 — Standard config produces identical results."""

    @patch('str_channel_routes.TaxRateService')
    @patch('str_channel_routes.DatabaseManager')
    def test_preservation_standard_config_pre_2026(
        self, mock_db_cls, mock_tax_cls, client
    ):
        """When config resolves to same accounts as old hardcoded values
        (8003 + 9%/2021 pre-2026), results are identical."""
        mock_db = MagicMock()
        mock_db_cls.return_value = mock_db
        mock_cursor = _wire_get_cursor(mock_db)

        channel_data = _mock_channel_data()
        str_revenue_rows = [{'Account': '8003'}]
        mock_cursor.fetchall.side_effect = [channel_data, str_revenue_rows]

        mock_tax_svc = MagicMock()
        mock_tax_cls.return_value = mock_tax_svc
        mock_tax_svc.get_tax_rate.return_value = {
            'rate': 9.0, 'ledger_account': '2021',
        }

        response = client.post(
            '/api/str-channel/calculate',
            content_type='application/json',
            data=json.dumps({
                'year': 2025, 'month': 9,
                'administration': 'TestTenant', 'test_mode': True,
            }),
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        transactions = data['transactions']

        # Revenue: same as old hardcoded behavior
        rev = transactions[0]
        assert rev['Credit'] == '8003'
        assert rev['Debet'] == '1600'
        assert rev['TransactionAmount'] == 1090.0

        # VAT: 1090 / 109 * 9 = 90.0 — same as old hardcoded behavior
        vat = transactions[1]
        assert vat['Debet'] == '8003'
        assert vat['Credit'] == '2021'
        assert vat['TransactionAmount'] == 90.0

    @patch('str_channel_routes.TaxRateService')
    @patch('str_channel_routes.DatabaseManager')
    def test_preservation_standard_config_post_2026(
        self, mock_db_cls, mock_tax_cls, client
    ):
        """When config resolves to same accounts as old hardcoded values
        (8003 + 21%/2020 post-2026), results are identical."""
        mock_db = MagicMock()
        mock_db_cls.return_value = mock_db
        mock_cursor = _wire_get_cursor(mock_db)

        channel_data = _mock_channel_data()
        str_revenue_rows = [{'Account': '8003'}]
        mock_cursor.fetchall.side_effect = [channel_data, str_revenue_rows]

        mock_tax_svc = MagicMock()
        mock_tax_cls.return_value = mock_tax_svc
        mock_tax_svc.get_tax_rate.return_value = {
            'rate': 21.0, 'ledger_account': '2020',
        }

        response = client.post(
            '/api/str-channel/calculate',
            content_type='application/json',
            data=json.dumps({
                'year': 2026, 'month': 3,
                'administration': 'TestTenant', 'test_mode': True,
            }),
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        transactions = data['transactions']

        # Revenue: same as old hardcoded behavior
        rev = transactions[0]
        assert rev['Credit'] == '8003'
        assert rev['TransactionAmount'] == 1090.0

        # VAT: 1090 / 121 * 21 = 189.26 — same as old hardcoded behavior
        vat = transactions[1]
        assert vat['Debet'] == '8003'
        assert vat['Credit'] == '2020'
        expected_vat = round((1090.0 / 121.0) * 21.0, 2)
        assert vat['TransactionAmount'] == expected_vat


def _wire_transaction(mock_db):
    """Wire mock_db.transaction() as a context manager yielding (cursor, conn).

    Mirrors the context-managed write API (`with db.transaction() as (cursor, conn):`),
    which auto-commits once on clean exit. Returns (mock_cursor, mock_conn, cm).
    """
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    cm = MagicMock()
    cm.__enter__.return_value = (mock_cursor, mock_conn)
    cm.__exit__.return_value = False
    mock_db.transaction.return_value = cm
    return mock_cursor, mock_conn, cm


class TestSaveCommitDurability:
    """Req 3.6 — /save must COMMIT the batch insert, via transaction() (not get_cursor()).

    The decorators are bypassed at module import, so these requests reach the DB code
    path and let us assert the write is durable, not just that the route returns 200.
    """

    def _transactions(self, administration='TestTenant'):
        return [
            {
                'TransactionDate': '2025-01-31',
                'TransactionNumber': 'AirBnB 2025-01-31',
                'TransactionDescription': 'AirBnB omzet 2025-01-31',
                'TransactionAmount': 1090.0,
                'Debet': '1600', 'Credit': '8003',
                'ReferenceNumber': 'AirBnB',
                'Ref1': 'BnB 202501', 'Ref2': '', 'Ref3': '', 'Ref4': '',
                'Administration': administration,
            },
            {
                'TransactionDate': '2025-01-31',
                'TransactionNumber': 'AirBnB 2025-01-31',
                'TransactionDescription': 'AirBnB Btw 2025-01-31',
                'TransactionAmount': 90.0,
                'Debet': '8003', 'Credit': '2021',
                'ReferenceNumber': 'AirBnB',
                'Ref1': 'BnB 202501', 'Ref2': '', 'Ref3': '', 'Ref4': '',
                'Administration': administration,
            },
        ]

    @patch('str_channel_routes.DatabaseManager')
    def test_save_commits_via_transaction(self, mock_db_cls, client):
        """The batch insert runs inside transaction() (auto-commit), never get_cursor()."""
        mock_db = MagicMock()
        mock_db_cls.return_value = mock_db
        mock_cursor, mock_conn, mock_cm = _wire_transaction(mock_db)

        response = client.post(
            '/api/str-channel/save',
            content_type='application/json',
            data=json.dumps({
                'transactions': self._transactions('TestTenant'),
                'test_mode': True,
            }),
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['saved_count'] == 2

        # Durability: committed via transaction() (one transaction, commit-at-end),
        # NOT get_cursor() which would silently lose the writes.
        mock_db.transaction.assert_called_once()
        mock_cm.__enter__.assert_called_once()
        mock_db.get_cursor.assert_not_called()

        # Correct INSERTs executed inside the transaction, one per row.
        assert mock_cursor.execute.call_count == 2
        for call in mock_cursor.execute.call_args_list:
            sql = call[0][0]
            assert 'INSERT INTO' in sql
            assert 'mutaties' in sql
        # The administration value is carried through into the row params.
        first_params = mock_cursor.execute.call_args_list[0][0][1]
        assert 'TestTenant' in first_params

    @patch('str_channel_routes.DatabaseManager')
    def test_save_single_transaction_boundary_commit(self, mock_db_cls, client):
        """A single-row save still goes through exactly one transaction()."""
        mock_db = MagicMock()
        mock_db_cls.return_value = mock_db
        mock_cursor, mock_conn, mock_cm = _wire_transaction(mock_db)

        response = client.post(
            '/api/str-channel/save',
            content_type='application/json',
            data=json.dumps({
                'transactions': self._transactions('TestTenant')[:1],
                'test_mode': True,
            }),
        )

        assert response.status_code == 200
        assert json.loads(response.data)['saved_count'] == 1
        mock_db.transaction.assert_called_once()
        assert mock_cursor.execute.call_count == 1
        mock_db.get_cursor.assert_not_called()


if __name__ == '__main__':
    pytest.main([__file__])
