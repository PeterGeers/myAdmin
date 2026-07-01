"""Unit tests for BankingService.

Tests cover:
- Account lookup logic (get_lookups)
- Transaction categorization (apply_patterns)
- IBAN validation (validate_iban_tenant)
- Mutation retrieval and update (get_mutaties, update_mutatie)
"""

import pytest
from unittest.mock import patch, MagicMock, Mock
from services.banking_service import BankingService


@pytest.fixture
def service(mock_db):
    """Create a BankingService with mocked DatabaseManager and BankingProcessor."""
    with patch('services.banking_service.DatabaseManager', return_value=mock_db):
        with patch('services.banking_mutatie_service.DatabaseManager', return_value=mock_db):
            with patch('services.banking_service.BankingProcessor') as MockProcessor:
                mock_processor = MagicMock()
                MockProcessor.return_value = mock_processor
                svc = BankingService(test_mode=True)
                svc._mock_db = mock_db
                svc._mock_processor = mock_processor
                yield svc


# ---------------------------------------------------------------------------
# validate_iban_tenant
# ---------------------------------------------------------------------------

class TestValidateIbanTenant:
    """Tests for IBAN-tenant validation."""

    def test_iban_matches_tenant(self, service):
        """IBAN belongs to requested tenant — valid."""
        service._mock_db.get_bank_account_lookups.return_value = [
            {'rekeningNummer': 'NL80RABO0107936917', 'administration': 'TenantA'}
        ]
        result = service.validate_iban_tenant('NL80RABO0107936917', 'TenantA')
        assert result['valid'] is True
        assert result['tenant'] == 'TenantA'

    def test_iban_belongs_to_different_tenant(self, service):
        """IBAN belongs to another tenant — access denied."""
        service._mock_db.get_bank_account_lookups.return_value = [
            {'rekeningNummer': 'NL80RABO0107936917', 'administration': 'TenantB'}
        ]
        result = service.validate_iban_tenant('NL80RABO0107936917', 'TenantA')
        assert result['valid'] is False
        assert 'Access denied' in result['error']
        assert result['tenant'] == 'TenantB'

    def test_iban_not_found_in_lookups(self, service):
        """IBAN not registered — allow processing with warning."""
        service._mock_db.get_bank_account_lookups.return_value = []
        result = service.validate_iban_tenant('NL99UNKN0000000001', 'TenantA')
        assert result['valid'] is True
        assert result['tenant'] is None
        assert 'warning' in result

    def test_iban_validation_exception(self, service):
        """Database error during validation — returns invalid."""
        service._mock_db.get_bank_account_lookups.side_effect = RuntimeError('DB down')
        result = service.validate_iban_tenant('NL80RABO0107936917', 'TenantA')
        assert result['valid'] is False
        assert 'DB down' in result['error']


# ---------------------------------------------------------------------------
# get_lookups
# ---------------------------------------------------------------------------

class TestGetLookups:
    """Tests for account lookup retrieval."""

    def test_returns_sorted_accounts_from_recent_transactions(self, service):
        """Extracts and sorts unique debet/credit codes from recent transactions."""
        with patch('services.banking_service.DatabaseManager') as MockDB:
            mock_local_db = MagicMock()
            MockDB.return_value = mock_local_db
            mock_local_db.get_bank_account_lookups.return_value = [
                {'rekeningNummer': 'NL80RABO0107936917', 'administration': 'T1'}
            ]
            mock_local_db.get_credit_card_lookups.return_value = []
            mock_local_db.get_exchange_rate_account.return_value = []
            mock_local_db.get_recent_transactions.return_value = [
                {'Debet': '1300', 'Credit': '8000', 'TransactionDescription': 'Payment A'},
                {'Debet': '4000', 'Credit': '1300', 'TransactionDescription': 'Payment B'},
                {'Debet': '1300', 'Credit': '4000', 'TransactionDescription': 'Payment A'},
            ]

            result = service.get_lookups('T1')

        assert result['success'] is True
        assert '1300' in result['accounts']
        assert '4000' in result['accounts']
        assert '8000' in result['accounts']
        # Accounts should be sorted
        assert result['accounts'] == sorted(result['accounts'])

    def test_returns_unique_descriptions(self, service):
        """Descriptions from recent transactions are unique and sorted."""
        with patch('services.banking_service.DatabaseManager') as MockDB:
            mock_local_db = MagicMock()
            MockDB.return_value = mock_local_db
            mock_local_db.get_bank_account_lookups.return_value = []
            mock_local_db.get_credit_card_lookups.return_value = []
            mock_local_db.get_exchange_rate_account.return_value = []
            mock_local_db.get_recent_transactions.return_value = [
                {'Debet': '1300', 'Credit': None, 'TransactionDescription': 'Fuel purchase'},
                {'Debet': None, 'Credit': '1300', 'TransactionDescription': 'Albert Heijn'},
                {'Debet': '4000', 'Credit': '1300', 'TransactionDescription': 'Fuel purchase'},
            ]

            result = service.get_lookups('T1')

        assert result['success'] is True
        assert result['descriptions'] == ['Albert Heijn', 'Fuel purchase']

    def test_includes_bank_accounts(self, service):
        """Bank accounts returned from lookup query are forwarded."""
        with patch('services.banking_service.DatabaseManager') as MockDB:
            mock_local_db = MagicMock()
            MockDB.return_value = mock_local_db
            mock_local_db.get_bank_account_lookups.return_value = [
                {'rekeningNummer': 'NL80RABO0107936917', 'administration': 'T1'}
            ]
            mock_local_db.get_credit_card_lookups.return_value = [
                {'rekeningNummer': 'NL99VISA0000000001', 'administration': 'T1'}
            ]
            mock_local_db.get_exchange_rate_account.return_value = [{'Account': '9100'}]
            mock_local_db.get_recent_transactions.return_value = []

            result = service.get_lookups('T1')

        assert result['success'] is True
        assert result['bank_accounts'][0]['rekeningNummer'] == 'NL80RABO0107936917'
        assert result['credit_card_accounts'][0]['rekeningNummer'] == 'NL99VISA0000000001'
        assert result['exchange_rate_account'] == '9100'

    def test_exchange_rate_account_none_when_empty(self, service):
        """exchange_rate_account is None when no record found."""
        with patch('services.banking_service.DatabaseManager') as MockDB:
            mock_local_db = MagicMock()
            MockDB.return_value = mock_local_db
            mock_local_db.get_bank_account_lookups.return_value = []
            mock_local_db.get_credit_card_lookups.return_value = []
            mock_local_db.get_exchange_rate_account.return_value = []
            mock_local_db.get_recent_transactions.return_value = []

            result = service.get_lookups('T1')

        assert result['success'] is True
        assert result['exchange_rate_account'] is None

    def test_get_lookups_handles_exception(self, service):
        """Exception during lookup returns error dict."""
        with patch('services.banking_service.DatabaseManager') as MockDB:
            MockDB.return_value.get_bank_account_lookups.side_effect = RuntimeError('fail')

            result = service.get_lookups('T1')

        assert result['success'] is False
        assert 'fail' in result['error']


# ---------------------------------------------------------------------------
# apply_patterns
# ---------------------------------------------------------------------------

class TestApplyPatterns:
    """Tests for transaction categorization via pattern matching."""

    def test_empty_transactions_returns_error(self, service):
        """No transactions provided — returns error."""
        result = service.apply_patterns([], 'TenantA')
        assert result['success'] is False
        assert 'No transactions' in result['error']

    def test_enhanced_mode_delegates_to_processor(self, service):
        """Enhanced mode calls BankingProcessor.apply_enhanced_patterns."""
        transactions = [{'TransactionDescription': 'Albert Heijn'}]
        with patch('services.banking_service.BankingProcessor') as MockProc:
            mock_proc = MagicMock()
            MockProc.return_value = mock_proc
            mock_proc.apply_enhanced_patterns.return_value = (
                [{'TransactionDescription': 'Albert Heijn', 'Credit': '4000'}],
                {'matched': 1}
            )

            result = service.apply_patterns(transactions, 'TenantA', use_enhanced=True)

        assert result['success'] is True
        assert result['method'] == 'enhanced'
        assert result['transactions'][0]['Credit'] == '4000'

    def test_sets_administration_on_transactions(self, service):
        """Adds administration field to transactions without one."""
        transactions = [{'TransactionDescription': 'Test'}]
        with patch('services.banking_service.BankingProcessor') as MockProc:
            mock_proc = MagicMock()
            MockProc.return_value = mock_proc
            mock_proc.apply_enhanced_patterns.return_value = (transactions, {})

            service.apply_patterns(transactions, 'MyTenant', use_enhanced=True)

        assert transactions[0]['administration'] == 'MyTenant'

    def test_legacy_mode_matches_debet_pattern(self, service):
        """Legacy mode matches description to debet pattern and assigns Credit."""
        transactions = [
            {'TransactionDescription': 'Kuwait fuel purchase', 'Credit': ''}
        ]
        with patch('services.banking_service.DatabaseManager') as MockDB:
            mock_local_db = MagicMock()
            MockDB.return_value = mock_local_db
            mock_local_db.get_patterns.return_value = [
                {
                    'referenceNumber': 'Kuwait',
                    'debet': '1200',
                    'credit': '4000',
                    'administration': 'TenantA'
                }
            ]

            result = service.apply_patterns(transactions, 'TenantA', use_enhanced=False)

        assert result['success'] is True
        assert result['method'] == 'legacy'
        assert transactions[0]['Credit'] == '4000'
        assert transactions[0]['ReferenceNumber'] == 'Kuwait'

    def test_legacy_mode_matches_credit_pattern(self, service):
        """Legacy mode matches credit pattern when Debet is empty."""
        transactions = [
            {'TransactionDescription': 'Income ACME Corp', 'Credit': '1300', 'Debet': ''}
        ]
        with patch('services.banking_service.DatabaseManager') as MockDB:
            mock_local_db = MagicMock()
            MockDB.return_value = mock_local_db
            mock_local_db.get_patterns.return_value = [
                {
                    'referenceNumber': 'ACME',
                    'debet': '8000',
                    'credit': '1200',
                    'administration': 'TenantA'
                }
            ]

            result = service.apply_patterns(transactions, 'TenantA', use_enhanced=False)

        assert result['success'] is True
        assert transactions[0]['Debet'] == '8000'

    def test_legacy_mode_no_match(self, service):
        """Legacy mode leaves transaction unchanged when no pattern matches."""
        transactions = [
            {'TransactionDescription': 'Unknown vendor XYZ', 'Credit': ''}
        ]
        with patch('services.banking_service.DatabaseManager') as MockDB:
            mock_local_db = MagicMock()
            MockDB.return_value = mock_local_db
            mock_local_db.get_patterns.return_value = [
                {
                    'referenceNumber': 'Albert',
                    'debet': '1200',
                    'credit': '4000',
                    'administration': 'TenantA'
                }
            ]

            result = service.apply_patterns(transactions, 'TenantA', use_enhanced=False)

        assert result['success'] is True
        assert transactions[0].get('ReferenceNumber') is None

    def test_apply_patterns_exception(self, service):
        """Exception during pattern matching returns error."""
        transactions = [{'TransactionDescription': 'Test'}]
        with patch('services.banking_service.BankingProcessor') as MockProc:
            MockProc.side_effect = RuntimeError('processor boom')

            result = service.apply_patterns(transactions, 'T1', use_enhanced=True)

        assert result['success'] is False
        assert 'processor boom' in result['error']


# ---------------------------------------------------------------------------
# get_mutaties
# ---------------------------------------------------------------------------

class TestGetMutaties:
    """Tests for mutation retrieval."""

    def _setup_cursor(self, service, rows, total=None):
        """Helper to configure mock cursor for get_mutaties."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        # First call is COUNT, second is the SELECT
        if total is None:
            total = len(rows)
        mock_cursor.fetchone.return_value = {'total': total}
        mock_cursor.fetchall.return_value = rows
        service._mock_db.get_connection.return_value = mock_conn
        return mock_cursor

    def test_returns_mutaties_for_tenant(self, service):
        """Returns records filtered by tenant."""
        rows = [
            {'ID': 1, 'TransactionDate': None, 'Administration': 'T1'}
        ]
        self._setup_cursor(service, rows, total=1)

        result = service.get_mutaties(
            filters={'years': ['2025']},
            tenant='T1',
            user_tenants=['T1']
        )

        assert result['success'] is True
        assert result['count'] == 1
        assert result['total'] == 1

    def test_access_denied_for_non_accessible_tenant(self, service):
        """Denies access if requested administration not in user_tenants."""
        result = service.get_mutaties(
            filters={'administration': 'OtherTenant'},
            tenant='T1',
            user_tenants=['T1', 'T2']
        )

        assert result['success'] is False
        assert 'Access denied' in result['error']

    def test_pagination_metadata(self, service):
        """Returns correct pagination metadata."""
        rows = [{'ID': i, 'TransactionDate': None} for i in range(10)]
        self._setup_cursor(service, rows, total=50)

        result = service.get_mutaties(
            filters={'years': ['2025'], 'limit': '10', 'offset': '0'},
            tenant='T1',
            user_tenants=['T1']
        )

        assert result['success'] is True
        assert result['limit'] == 10
        assert result['offset'] == 0
        assert result['has_more'] is True

    def test_converts_dates_to_iso_format(self, service):
        """TransactionDate objects are converted to ISO strings."""
        from datetime import date
        rows = [{'ID': 1, 'TransactionDate': date(2025, 3, 15)}]
        self._setup_cursor(service, rows, total=1)

        result = service.get_mutaties(
            filters={'years': ['2025']},
            tenant='T1',
            user_tenants=['T1']
        )

        assert result['mutaties'][0]['TransactionDate'] == '2025-03-15'


# ---------------------------------------------------------------------------
# update_mutatie
# ---------------------------------------------------------------------------

class TestUpdateMutatie:
    """Tests for mutation update."""

    def _setup_update_cursor(self, service, existing_record):
        """Helper to configure mock cursor for update_mutatie."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = existing_record
        service._mock_db.get_connection.return_value = mock_conn
        return mock_cursor, mock_conn

    def test_update_success(self, service):
        """Updates record that belongs to current tenant."""
        cursor, conn = self._setup_update_cursor(
            service, {'administration': 'T1'}
        )

        data = {
            'TransactionNumber': '123',
            'TransactionDate': '2025-01-15',
            'TransactionDescription': 'Updated',
            'TransactionAmount': 100.0,
            'Debet': '1300',
            'Credit': '8000',
            'ReferenceNumber': 'REF1',
            'Ref1': 'NL80RABO0107936917',
            'Ref2': '001',
            'Ref3': None,
            'Ref4': None,
        }
        result = service.update_mutatie(42, data, 'T1')

        assert result['success'] is True
        conn.commit.assert_called_once()

    def test_update_record_not_found(self, service):
        """Returns error when record does not exist."""
        self._setup_update_cursor(service, None)

        result = service.update_mutatie(999, {}, 'T1')

        assert result['success'] is False
        assert 'not found' in result['error']

    def test_update_access_denied_different_tenant(self, service):
        """Denies update when record belongs to another tenant."""
        self._setup_update_cursor(service, {'administration': 'OtherTenant'})

        result = service.update_mutatie(42, {}, 'T1')

        assert result['success'] is False
        assert 'Access denied' in result['error']

    def test_update_forces_tenant_in_query(self, service):
        """Administration field is always set to current tenant (defense in depth)."""
        cursor, conn = self._setup_update_cursor(
            service, {'administration': 'T1'}
        )

        data = {
            'TransactionNumber': '1',
            'TransactionDate': '2025-01-01',
            'TransactionDescription': 'x',
            'TransactionAmount': 10,
            'Debet': '1300',
            'Credit': '8000',
            'ReferenceNumber': '',
            'Ref1': 'NL80RABO0107936917',
            'Ref2': '1',
            'Ref3': None,
            'Ref4': None,
        }
        service.update_mutatie(42, data, 'T1')

        # The last param before mutatie_id should be the tenant
        call_args = cursor.execute.call_args_list[-1]
        params = call_args[0][1]
        # params[-2] should be 'T1' (administration), params[-1] is mutatie_id
        assert params[-2] == 'T1'
        assert params[-1] == 42
