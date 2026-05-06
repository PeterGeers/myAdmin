"""
Unit tests for btw_processor module.

Tests VAT account resolution, balance calculations, quarter aggregation,
report data preparation, and error handling.

Requirements: 1.3, 2.2, 2.1, 8.5
"""

import pytest
import pandas as pd
from unittest.mock import patch, MagicMock
from datetime import datetime

from btw_processor import BTWProcessor


class TestGetVatAccounts:
    """Tests for _get_vat_accounts method."""

    @pytest.fixture
    def processor(self, mock_db):
        """Create BTWProcessor with mocked DatabaseManager."""
        with patch('btw_processor.DatabaseManager', return_value=mock_db):
            proc = BTWProcessor(test_mode=True)
        return proc

    def test_get_vat_accounts_no_tax_rate_service_returns_defaults(self, processor):
        """Test default VAT accounts when no TaxRateService configured."""
        result = processor._get_vat_accounts('TestAdmin')
        assert result == ['2010', '2020', '2021']

    def test_get_vat_accounts_with_tax_rate_service_returns_ledger_accounts(self, mock_db):
        """Test VAT accounts from TaxRateService when available."""
        mock_tax_service = MagicMock()
        mock_tax_service.get_all_vat_codes.return_value = [
            {'ledger_account': '2010', 'code': 'zero'},
            {'ledger_account': '2020', 'code': 'high'},
            {'ledger_account': '2021', 'code': 'low'},
        ]
        with patch('btw_processor.DatabaseManager', return_value=mock_db):
            proc = BTWProcessor(test_mode=True, tax_rate_service=mock_tax_service)

        result = proc._get_vat_accounts('TestAdmin', reference_date='2024-06-30')
        assert result == ['2010', '2020', '2021']

    def test_get_vat_accounts_tax_service_empty_codes_returns_defaults(self, mock_db):
        """Test fallback to defaults when TaxRateService returns empty list."""
        mock_tax_service = MagicMock()
        mock_tax_service.get_all_vat_codes.return_value = []
        with patch('btw_processor.DatabaseManager', return_value=mock_db):
            proc = BTWProcessor(test_mode=True, tax_rate_service=mock_tax_service)

        result = proc._get_vat_accounts('TestAdmin', reference_date='2024-03-31')
        assert result == ['2010', '2020', '2021']

    def test_get_vat_accounts_filters_entries_without_ledger_account(self, mock_db):
        """Test that entries without ledger_account are excluded."""
        mock_tax_service = MagicMock()
        mock_tax_service.get_all_vat_codes.return_value = [
            {'ledger_account': '2010', 'code': 'zero'},
            {'ledger_account': None, 'code': 'exempt'},
            {'ledger_account': '2020', 'code': 'high'},
        ]
        with patch('btw_processor.DatabaseManager', return_value=mock_db):
            proc = BTWProcessor(test_mode=True, tax_rate_service=mock_tax_service)

        result = proc._get_vat_accounts('TestAdmin', reference_date='2024-06-30')
        assert result == ['2010', '2020']

    def test_get_vat_accounts_no_reference_date_returns_defaults(self, mock_db):
        """Test that without reference_date, defaults are returned even with service."""
        mock_tax_service = MagicMock()
        with patch('btw_processor.DatabaseManager', return_value=mock_db):
            proc = BTWProcessor(test_mode=True, tax_rate_service=mock_tax_service)

        result = proc._get_vat_accounts('TestAdmin', reference_date=None)
        assert result == ['2010', '2020', '2021']
        mock_tax_service.get_all_vat_codes.assert_not_called()


class TestGetReceivedVatAccounts:
    """Tests for _get_received_vat_accounts method."""

    @pytest.fixture
    def processor(self, mock_db):
        with patch('btw_processor.DatabaseManager', return_value=mock_db):
            proc = BTWProcessor(test_mode=True)
        return proc

    def test_get_received_vat_accounts_defaults_exclude_2010(self, processor):
        """Test default received accounts exclude primary account 2010."""
        result = processor._get_received_vat_accounts('TestAdmin')
        assert result == ['2020', '2021']
        assert '2010' not in result

    def test_get_received_vat_accounts_with_service(self, mock_db):
        """Test received accounts from TaxRateService exclude primary."""
        mock_tax_service = MagicMock()
        mock_tax_service.get_all_vat_codes.return_value = [
            {'ledger_account': '2010', 'code': 'zero'},
            {'ledger_account': '2020', 'code': 'high'},
            {'ledger_account': '2021', 'code': 'low'},
        ]
        with patch('btw_processor.DatabaseManager', return_value=mock_db):
            proc = BTWProcessor(test_mode=True, tax_rate_service=mock_tax_service)

        result = proc._get_received_vat_accounts('TestAdmin', reference_date='2024-06-30')
        assert '2010' not in result
        assert '2020' in result
        assert '2021' in result


class TestGetPrimaryVatAccount:
    """Tests for _get_primary_vat_account method."""

    @pytest.fixture
    def processor(self, mock_db):
        with patch('btw_processor.DatabaseManager', return_value=mock_db):
            proc = BTWProcessor(test_mode=True)
        return proc

    def test_get_primary_vat_account_default(self, processor):
        """Test default primary VAT account is 2010."""
        result = processor._get_primary_vat_account('TestAdmin')
        assert result == '2010'

    def test_get_primary_vat_account_from_service(self, mock_db):
        """Test primary account from TaxRateService with code 'zero'."""
        mock_tax_service = MagicMock()
        mock_tax_service.get_all_vat_codes.return_value = [
            {'ledger_account': '1500', 'code': 'zero'},
            {'ledger_account': '2020', 'code': 'high'},
        ]
        with patch('btw_processor.DatabaseManager', return_value=mock_db):
            proc = BTWProcessor(test_mode=True, tax_rate_service=mock_tax_service)

        result = proc._get_primary_vat_account('TestAdmin', reference_date='2024-06-30')
        assert result == '1500'

    def test_get_primary_vat_account_no_zero_code_returns_default(self, mock_db):
        """Test fallback to 2010 when no 'zero' code in service response."""
        mock_tax_service = MagicMock()
        mock_tax_service.get_all_vat_codes.return_value = [
            {'ledger_account': '2020', 'code': 'high'},
            {'ledger_account': '2021', 'code': 'low'},
        ]
        with patch('btw_processor.DatabaseManager', return_value=mock_db):
            proc = BTWProcessor(test_mode=True, tax_rate_service=mock_tax_service)

        result = proc._get_primary_vat_account('TestAdmin', reference_date='2024-06-30')
        assert result == '2010'


class TestCalculateBtwAmounts:
    """Tests for _calculate_btw_amounts method."""

    @pytest.fixture
    def processor(self, mock_db):
        with patch('btw_processor.DatabaseManager', return_value=mock_db):
            proc = BTWProcessor(test_mode=True)
        return proc

    def test_calculate_btw_amounts_positive_balance_te_ontvangen(self, processor):
        """Test positive balance produces 'te ontvangen' instruction."""
        balance_data = [
            {'Reknum': '2010', 'AccountName': 'BTW Af te dragen', 'amount': 500.0},
            {'Reknum': '2020', 'AccountName': 'BTW Hoog', 'amount': 300.0},
        ]
        quarter_data = [
            {'Reknum': '2020', 'AccountName': 'BTW Hoog', 'amount': 1200.0},
            {'Reknum': '2021', 'AccountName': 'BTW Laag', 'amount': 200.0},
        ]

        result = processor._calculate_btw_amounts(balance_data, quarter_data)

        assert result['total_balance'] == 800.0  # 500 + 300
        assert result['received_btw'] == 1400.0  # 1200 + 200
        assert result['prepaid_btw'] == 600.0  # 1400 - 800
        assert 'te ontvangen' in result['payment_instruction']
        assert '800' in result['payment_instruction']

    def test_calculate_btw_amounts_negative_balance_te_betalen(self, processor):
        """Test negative balance produces 'te betalen' instruction."""
        balance_data = [
            {'Reknum': '2010', 'AccountName': 'BTW Af te dragen', 'amount': -1000.0},
            {'Reknum': '2020', 'AccountName': 'BTW Hoog', 'amount': 400.0},
        ]
        quarter_data = [
            {'Reknum': '2020', 'AccountName': 'BTW Hoog', 'amount': 800.0},
            {'Reknum': '2021', 'AccountName': 'BTW Laag', 'amount': 100.0},
        ]

        result = processor._calculate_btw_amounts(balance_data, quarter_data)

        assert result['total_balance'] == -600.0  # -1000 + 400
        assert result['received_btw'] == 900.0  # 800 + 100
        assert 'te betalen' in result['payment_instruction']
        assert '600' in result['payment_instruction']

    def test_calculate_btw_amounts_zero_balance(self, processor):
        """Test zero balance produces 'te betalen' with zero amount."""
        balance_data = [
            {'Reknum': '2020', 'AccountName': 'BTW Hoog', 'amount': 0.0},
        ]
        quarter_data = [
            {'Reknum': '2020', 'AccountName': 'BTW Hoog', 'amount': 0.0},
        ]

        result = processor._calculate_btw_amounts(balance_data, quarter_data)

        assert result['total_balance'] == 0.0
        assert result['received_btw'] == 0.0
        assert result['prepaid_btw'] == 0.0

    def test_calculate_btw_amounts_empty_data_returns_zeros(self, processor):
        """Test empty input data returns zero calculations."""
        result = processor._calculate_btw_amounts([], [])

        assert result['total_balance'] == 0.0
        assert result['received_btw'] == 0.0
        assert result['prepaid_btw'] == 0.0
        assert '0' in result['payment_instruction']

    def test_calculate_btw_amounts_only_non_received_accounts(self, processor):
        """Test that accounts not in received list are excluded from received_btw."""
        balance_data = [
            {'Reknum': '2010', 'AccountName': 'BTW Af te dragen', 'amount': -500.0},
        ]
        quarter_data = [
            {'Reknum': '2010', 'AccountName': 'BTW Af te dragen', 'amount': -500.0},
            {'Reknum': '8001', 'AccountName': 'Revenue', 'amount': 5000.0},
        ]

        result = processor._calculate_btw_amounts(balance_data, quarter_data)

        # 2010 is not in received accounts (only 2020, 2021 are)
        assert result['received_btw'] == 0.0
        assert result['total_balance'] == -500.0

    def test_calculate_btw_amounts_with_administration_and_reference(self, mock_db):
        """Test calculation uses administration/reference_date for account lookup."""
        mock_tax_service = MagicMock()
        mock_tax_service.get_all_vat_codes.return_value = [
            {'ledger_account': '2010', 'code': 'zero'},
            {'ledger_account': '2020', 'code': 'high'},
            {'ledger_account': '2021', 'code': 'low'},
        ]
        with patch('btw_processor.DatabaseManager', return_value=mock_db):
            proc = BTWProcessor(test_mode=True, tax_rate_service=mock_tax_service)

        balance_data = [
            {'Reknum': '2020', 'AccountName': 'BTW Hoog', 'amount': 200.0},
        ]
        quarter_data = [
            {'Reknum': '2020', 'AccountName': 'BTW Hoog', 'amount': 500.0},
        ]

        result = proc._calculate_btw_amounts(
            balance_data, quarter_data,
            administration='TestAdmin', reference_date='2024-06-30'
        )

        assert result['total_balance'] == 200.0
        assert result['received_btw'] == 500.0


class TestGetBalanceData:
    """Tests for _get_balance_data method (balance retrieval with opening balance)."""

    @pytest.fixture
    def processor(self, mock_db):
        with patch('btw_processor.DatabaseManager', return_value=mock_db):
            proc = BTWProcessor(test_mode=True)
        return proc

    @patch('btw_processor.get_cache')
    def test_get_balance_data_with_opening_and_current_year(self, mock_get_cache, processor):
        """Test balance data combines opening balance and current year transactions."""
        mock_cache = MagicMock()
        mock_get_cache.return_value = mock_cache

        # Build a DataFrame with opening balance + current year transactions
        data = pd.DataFrame({
            'ReferenceNumber': ['Opening Balance', 'INV001', 'INV002'],
            'TransactionDate': ['2024-01-01', '2024-02-15', '2024-03-10'],
            'administration': ['TestAdmin', 'TestAdmin', 'TestAdmin'],
            'Reknum': ['2010', '2020', '2021'],
            'AccountName': ['BTW Af te dragen', 'BTW Hoog', 'BTW Laag'],
            'Amount': [-100.0, 300.0, 50.0],
            'jaar': [2024, 2024, 2024],
            'kwartaal': [1, 1, 1],
        })
        mock_cache.get_data.return_value = data

        result = processor._get_balance_data('TestAdmin', '2024-03-31')

        # Should have opening balance entry + current year grouped entries
        assert len(result) >= 1
        # Opening balance should be included (amount = -100)
        opening_entries = [r for r in result if r.get('Reknum') == 'Opening']
        assert len(opening_entries) == 1
        assert opening_entries[0]['amount'] == -100.0

    @patch('btw_processor.get_cache')
    def test_get_balance_data_no_opening_balance(self, mock_get_cache, processor):
        """Test balance data when no opening balance exists."""
        mock_cache = MagicMock()
        mock_get_cache.return_value = mock_cache

        data = pd.DataFrame({
            'ReferenceNumber': ['INV001', 'INV002'],
            'TransactionDate': ['2024-02-15', '2024-03-10'],
            'administration': ['TestAdmin', 'TestAdmin'],
            'Reknum': ['2020', '2021'],
            'AccountName': ['BTW Hoog', 'BTW Laag'],
            'Amount': [300.0, 50.0],
            'jaar': [2024, 2024],
            'kwartaal': [1, 1],
        })
        mock_cache.get_data.return_value = data

        result = processor._get_balance_data('TestAdmin', '2024-03-31')

        # No opening balance entry
        opening_entries = [r for r in result if r.get('Reknum') == 'Opening']
        assert len(opening_entries) == 0
        # Should have current year data
        assert len(result) == 2

    @patch('btw_processor.get_cache')
    def test_get_balance_data_cache_error_returns_empty(self, mock_get_cache, processor):
        """Test that cache errors return empty list."""
        mock_cache = MagicMock()
        mock_get_cache.return_value = mock_cache
        mock_cache.get_data.side_effect = Exception("Cache unavailable")

        result = processor._get_balance_data('TestAdmin', '2024-03-31')

        assert result == []

    @patch('btw_processor.get_cache')
    def test_get_balance_data_filters_by_administration(self, mock_get_cache, processor):
        """Test that balance data is filtered by administration prefix."""
        mock_cache = MagicMock()
        mock_get_cache.return_value = mock_cache

        data = pd.DataFrame({
            'ReferenceNumber': ['INV001', 'INV002'],
            'TransactionDate': ['2024-02-15', '2024-02-20'],
            'administration': ['TestAdmin', 'OtherAdmin'],
            'Reknum': ['2020', '2020'],
            'AccountName': ['BTW Hoog', 'BTW Hoog'],
            'Amount': [300.0, 999.0],
            'jaar': [2024, 2024],
            'kwartaal': [1, 1],
        })
        mock_cache.get_data.return_value = data

        result = processor._get_balance_data('TestAdmin', '2024-03-31')

        # Only TestAdmin data should be included
        amounts = [r['amount'] for r in result if r.get('Reknum') != 'Opening']
        assert 999.0 not in amounts


class TestGetQuarterData:
    """Tests for _get_quarter_data method (quarter aggregation)."""

    @pytest.fixture
    def processor(self, mock_db):
        with patch('btw_processor.DatabaseManager', return_value=mock_db):
            proc = BTWProcessor(test_mode=True)
        return proc

    @patch('btw_processor.get_cache')
    def test_get_quarter_data_filters_by_year_and_quarter(self, mock_get_cache, processor):
        """Test quarter data filters correctly by year and quarter."""
        mock_cache = MagicMock()
        mock_get_cache.return_value = mock_cache

        data = pd.DataFrame({
            'jaar': [2024, 2024, 2024, 2024],
            'kwartaal': [1, 1, 2, 1],
            'administration': ['TestAdmin', 'TestAdmin', 'TestAdmin', 'TestAdmin'],
            'Reknum': ['2020', '2021', '2020', '8001'],
            'AccountName': ['BTW Hoog', 'BTW Laag', 'BTW Hoog', 'Revenue'],
            'Amount': [500.0, 100.0, 300.0, 5000.0],
        })
        mock_cache.get_data.return_value = data

        result = processor._get_quarter_data('TestAdmin', 2024, 1)

        # Q1 only: 2020=500, 2021=100, 8001=5000 (Q2 excluded)
        account_nums = [r['Reknum'] for r in result]
        assert '2020' in account_nums
        assert '2021' in account_nums
        assert '8001' in account_nums
        # Verify amounts
        btw_hoog = next(r for r in result if r['Reknum'] == '2020')
        assert btw_hoog['amount'] == 500.0

    @patch('btw_processor.get_cache')
    def test_get_quarter_data_groups_by_account(self, mock_get_cache, processor):
        """Test that multiple transactions for same account are summed."""
        mock_cache = MagicMock()
        mock_get_cache.return_value = mock_cache

        data = pd.DataFrame({
            'jaar': [2024, 2024, 2024],
            'kwartaal': [1, 1, 1],
            'administration': ['TestAdmin', 'TestAdmin', 'TestAdmin'],
            'Reknum': ['2020', '2020', '2020'],
            'AccountName': ['BTW Hoog', 'BTW Hoog', 'BTW Hoog'],
            'Amount': [100.0, 200.0, 300.0],
        })
        mock_cache.get_data.return_value = data

        result = processor._get_quarter_data('TestAdmin', 2024, 1)

        assert len(result) == 1
        assert result[0]['Reknum'] == '2020'
        assert result[0]['amount'] == 600.0  # 100 + 200 + 300

    @patch('btw_processor.get_cache')
    def test_get_quarter_data_excludes_non_btw_non_revenue_accounts(self, mock_get_cache, processor):
        """Test that accounts outside BTW/revenue set are excluded."""
        mock_cache = MagicMock()
        mock_get_cache.return_value = mock_cache

        data = pd.DataFrame({
            'jaar': [2024, 2024, 2024],
            'kwartaal': [1, 1, 1],
            'administration': ['TestAdmin', 'TestAdmin', 'TestAdmin'],
            'Reknum': ['2020', '4000', '1300'],
            'AccountName': ['BTW Hoog', 'Expenses', 'Bank'],
            'Amount': [500.0, 1000.0, 2000.0],
        })
        mock_cache.get_data.return_value = data

        result = processor._get_quarter_data('TestAdmin', 2024, 1)

        account_nums = [r['Reknum'] for r in result]
        assert '2020' in account_nums
        assert '4000' not in account_nums
        assert '1300' not in account_nums

    @patch('btw_processor.get_cache')
    def test_get_quarter_data_cache_error_returns_empty(self, mock_get_cache, processor):
        """Test that cache errors return empty list."""
        mock_cache = MagicMock()
        mock_get_cache.return_value = mock_cache
        mock_cache.get_data.side_effect = Exception("Cache error")

        result = processor._get_quarter_data('TestAdmin', 2024, 1)

        assert result == []

    @patch('btw_processor.get_cache')
    def test_get_quarter_data_filters_by_administration(self, mock_get_cache, processor):
        """Test that quarter data is filtered by administration prefix."""
        mock_cache = MagicMock()
        mock_get_cache.return_value = mock_cache

        data = pd.DataFrame({
            'jaar': [2024, 2024],
            'kwartaal': [1, 1],
            'administration': ['TestAdmin', 'OtherAdmin'],
            'Reknum': ['2020', '2020'],
            'AccountName': ['BTW Hoog', 'BTW Hoog'],
            'Amount': [500.0, 999.0],
        })
        mock_cache.get_data.return_value = data

        result = processor._get_quarter_data('TestAdmin', 2024, 1)

        assert len(result) == 1
        assert result[0]['amount'] == 500.0


class TestGenerateBtwReport:
    """Tests for generate_btw_report method (end-to-end report generation)."""

    @pytest.fixture
    def processor(self, mock_db):
        with patch('btw_processor.DatabaseManager', return_value=mock_db):
            proc = BTWProcessor(test_mode=True)
        return proc

    @patch('btw_processor.get_cache')
    def test_generate_btw_report_success_q1(self, mock_get_cache, processor):
        """Test successful report generation for Q1."""
        mock_cache = MagicMock()
        mock_get_cache.return_value = mock_cache

        data = pd.DataFrame({
            'ReferenceNumber': ['INV001', 'INV002'],
            'TransactionDate': ['2024-02-15', '2024-03-10'],
            'administration': ['TestAdmin', 'TestAdmin'],
            'Reknum': ['2020', '2021'],
            'AccountName': ['BTW Hoog', 'BTW Laag'],
            'Amount': [300.0, 50.0],
            'jaar': [2024, 2024],
            'kwartaal': [1, 1],
        })
        mock_cache.get_data.return_value = data

        # Mock _get_last_btw_transaction to avoid real DB call
        with patch.object(processor, '_get_last_btw_transaction', return_value=None):
            result = processor.generate_btw_report('TestAdmin', 2024, 1)

        assert result['success'] is True
        assert 'html_report' in result
        assert 'transaction' in result
        assert 'calculations' in result
        assert result['quarter_end_date'] == '2024-03-31'

    @patch('btw_processor.get_cache')
    def test_generate_btw_report_success_q2(self, mock_get_cache, processor):
        """Test correct quarter end date for Q2 (June 30)."""
        mock_cache = MagicMock()
        mock_get_cache.return_value = mock_cache
        mock_cache.get_data.return_value = pd.DataFrame({
            'ReferenceNumber': [], 'TransactionDate': [],
            'administration': [], 'Reknum': [], 'AccountName': [],
            'Amount': [], 'jaar': [], 'kwartaal': [],
        })

        with patch.object(processor, '_get_last_btw_transaction', return_value=None):
            result = processor.generate_btw_report('TestAdmin', 2024, 2)

        assert result['success'] is True
        assert result['quarter_end_date'] == '2024-06-30'

    @patch('btw_processor.get_cache')
    def test_generate_btw_report_success_q3(self, mock_get_cache, processor):
        """Test correct quarter end date for Q3 (September 30)."""
        mock_cache = MagicMock()
        mock_get_cache.return_value = mock_cache
        mock_cache.get_data.return_value = pd.DataFrame({
            'ReferenceNumber': [], 'TransactionDate': [],
            'administration': [], 'Reknum': [], 'AccountName': [],
            'Amount': [], 'jaar': [], 'kwartaal': [],
        })

        with patch.object(processor, '_get_last_btw_transaction', return_value=None):
            result = processor.generate_btw_report('TestAdmin', 2024, 3)

        assert result['success'] is True
        assert result['quarter_end_date'] == '2024-09-30'

    @patch('btw_processor.get_cache')
    def test_generate_btw_report_success_q4(self, mock_get_cache, processor):
        """Test correct quarter end date for Q4 (December 31)."""
        mock_cache = MagicMock()
        mock_get_cache.return_value = mock_cache
        mock_cache.get_data.return_value = pd.DataFrame({
            'ReferenceNumber': [], 'TransactionDate': [],
            'administration': [], 'Reknum': [], 'AccountName': [],
            'Amount': [], 'jaar': [], 'kwartaal': [],
        })

        with patch.object(processor, '_get_last_btw_transaction', return_value=None):
            result = processor.generate_btw_report('TestAdmin', 2024, 4)

        assert result['success'] is True
        assert result['quarter_end_date'] == '2024-12-31'

    @patch('btw_processor.get_cache')
    def test_generate_btw_report_cache_error_returns_empty_data(self, mock_get_cache, processor):
        """Test that cache errors in sub-methods produce report with empty data."""
        mock_cache = MagicMock()
        mock_get_cache.return_value = mock_cache
        mock_cache.get_data.side_effect = Exception("Database unavailable")

        with patch.object(processor, '_get_last_btw_transaction', return_value=None):
            result = processor.generate_btw_report('TestAdmin', 2024, 1)

        # Sub-methods catch exceptions and return empty lists,
        # so report still succeeds with zero calculations
        assert result['success'] is True
        assert result['calculations']['total_balance'] == 0.0
        assert result['calculations']['received_btw'] == 0.0

    def test_generate_btw_report_unhandled_error_returns_failure(self, processor):
        """Test that unhandled exceptions in generate_btw_report return failure."""
        # Patch _get_balance_data to raise outside its own try/except
        with patch.object(processor, '_get_balance_data', side_effect=TypeError("unexpected")):
            result = processor.generate_btw_report('TestAdmin', 2024, 1)

        assert result['success'] is False
        assert 'error' in result
        assert 'unexpected' in result['error']


class TestGenerateHtmlReport:
    """Tests for _generate_html_report method (report formatting)."""

    @pytest.fixture
    def processor(self, mock_db):
        with patch('btw_processor.DatabaseManager', return_value=mock_db):
            proc = BTWProcessor(test_mode=True)
        return proc

    def test_generate_html_report_contains_administration(self, processor):
        """Test HTML report includes administration name."""
        balance_data = [{'Reknum': '2020', 'AccountName': 'BTW Hoog', 'amount': 100.0}]
        quarter_data = [{'Reknum': '2020', 'AccountName': 'BTW Hoog', 'amount': 200.0}]
        calculations = {
            'total_balance': 100.0,
            'received_btw': 200.0,
            'prepaid_btw': 100.0,
            'payment_instruction': '€100 te ontvangen',
        }

        result = processor._generate_html_report(
            'MyCompany', 2024, 1, '2024-03-31',
            balance_data, quarter_data, calculations
        )

        assert 'MyCompany' in result
        assert '2024' in result
        assert 'BTW aangifte' in result

    def test_generate_html_report_contains_table_data(self, processor):
        """Test HTML report includes balance and quarter data in tables."""
        balance_data = [
            {'Reknum': '2020', 'AccountName': 'BTW Hoog', 'amount': 500.0},
            {'Reknum': '2021', 'AccountName': 'BTW Laag', 'amount': 50.0},
        ]
        quarter_data = [
            {'Reknum': '8001', 'AccountName': 'Revenue High', 'amount': 3000.0},
        ]
        calculations = {
            'total_balance': 550.0,
            'received_btw': 0.0,
            'prepaid_btw': -550.0,
            'payment_instruction': '€550 te ontvangen',
        }

        result = processor._generate_html_report(
            'TestAdmin', 2024, 2, '2024-06-30',
            balance_data, quarter_data, calculations
        )

        assert 'BTW Hoog' in result
        assert 'BTW Laag' in result
        assert 'Revenue High' in result
        assert '€550 te ontvangen' in result

    def test_generate_html_report_escapes_html_entities(self, processor):
        """Test that special characters in data are HTML-escaped."""
        balance_data = [
            {'Reknum': '2020', 'AccountName': '<script>alert("xss")</script>', 'amount': 0.0},
        ]
        quarter_data = []
        calculations = {
            'total_balance': 0.0,
            'received_btw': 0.0,
            'prepaid_btw': 0.0,
            'payment_instruction': '€0 te betalen',
        }

        result = processor._generate_html_report(
            'TestAdmin', 2024, 1, '2024-03-31',
            balance_data, quarter_data, calculations
        )

        assert '<script>' not in result
        assert '&lt;script&gt;' in result

    def test_generate_html_report_contains_belastingdienst_link(self, processor):
        """Test HTML report includes link to belastingdienst."""
        result = processor._generate_html_report(
            'TestAdmin', 2024, 1, '2024-03-31', [], [], {
                'total_balance': 0.0, 'received_btw': 0.0,
                'prepaid_btw': 0.0, 'payment_instruction': '€0 te betalen',
            }
        )

        assert 'belastingdienst.nl' in result


class TestPrepareBtwTransaction:
    """Tests for _prepare_btw_transaction method."""

    @pytest.fixture
    def processor(self, mock_db):
        with patch('btw_processor.DatabaseManager', return_value=mock_db):
            proc = BTWProcessor(test_mode=True)
        return proc

    def test_prepare_btw_transaction_negative_balance_debit_2010(self, processor):
        """Test negative balance (te betalen) sets debit=2010, credit=1300."""
        calculations = {
            'total_balance': -500.0,
            'received_btw': 800.0,
            'prepaid_btw': 300.0,
            'payment_instruction': '€500 te betalen',
        }

        with patch.object(processor, '_get_last_btw_transaction', return_value=None):
            result = processor._prepare_btw_transaction('TestAdmin', 2024, 1, calculations)

        assert result['Debet'] == '2010'
        assert result['Credit'] == '1300'
        assert result['TransactionAmount'] == 500
        assert result['TransactionNumber'] == 'BTW'
        assert result['Ref2'] == '2024-Q1'
        assert result['Administration'] == 'TestAdmin'

    def test_prepare_btw_transaction_positive_balance_debit_1300(self, processor):
        """Test positive balance (te ontvangen) sets debit=1300, credit=2010."""
        calculations = {
            'total_balance': 300.0,
            'received_btw': 500.0,
            'prepaid_btw': 200.0,
            'payment_instruction': '€300 te ontvangen',
        }

        with patch.object(processor, '_get_last_btw_transaction', return_value=None):
            result = processor._prepare_btw_transaction('TestAdmin', 2024, 2, calculations)

        assert result['Debet'] == '1300'
        assert result['Credit'] == '2010'
        assert result['TransactionAmount'] == 300
        assert result['Ref2'] == '2024-Q2'

    def test_prepare_btw_transaction_contains_description(self, processor):
        """Test transaction description includes year and quarter."""
        calculations = {
            'total_balance': -100.0,
            'received_btw': 200.0,
            'prepaid_btw': 100.0,
            'payment_instruction': '€100 te betalen',
        }

        with patch.object(processor, '_get_last_btw_transaction', return_value=None):
            result = processor._prepare_btw_transaction('TestAdmin', 2024, 3, calculations)

        assert '2024' in result['TransactionDescription']
        assert 'Q3' in result['TransactionDescription']
        assert result['ReferenceNumber'] == 'BTW'


class TestSaveBtwTransaction:
    """Tests for save_btw_transaction method."""

    @pytest.fixture
    def processor(self, mock_db):
        with patch('btw_processor.DatabaseManager', return_value=mock_db):
            proc = BTWProcessor(test_mode=True)
        return proc

    def test_save_btw_transaction_success(self, processor):
        """Test successful transaction save returns transaction_id."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        processor.db.get_connection.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = None  # No duplicate
        mock_cursor.lastrowid = 42

        transaction = {
            'TransactionNumber': 'BTW',
            'TransactionDate': '2024-04-01',
            'TransactionDescription': 'BTW aangifte 2024 Q1',
            'TransactionAmount': 500,
            'Debet': '2010',
            'Credit': '1300',
            'ReferenceNumber': 'BTW',
            'Ref1': 'BTW aangifte TestAdmin',
            'Ref2': '2024-Q1',
            'Ref3': '€500 te betalen',
            'Ref4': 'Generated 2024-04-01',
            'Administration': 'TestAdmin',
        }

        result = processor.save_btw_transaction(transaction)

        assert result['success'] is True
        assert result['transaction_id'] == 42
        mock_conn.commit.assert_called_once()

    def test_save_btw_transaction_duplicate_detected(self, processor):
        """Test duplicate detection prevents double-save."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        processor.db.get_connection.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        # Duplicate found
        mock_cursor.fetchone.return_value = {'ID': 99}

        transaction = {
            'TransactionNumber': 'BTW',
            'TransactionDate': '2024-04-01',
            'TransactionDescription': 'BTW aangifte 2024 Q1',
            'TransactionAmount': 500,
            'Debet': '2010',
            'Credit': '1300',
            'ReferenceNumber': 'BTW',
            'Ref1': 'BTW aangifte TestAdmin',
            'Ref2': '2024-Q1',
            'Ref3': '€500 te betalen',
            'Ref4': 'Generated 2024-04-01',
            'Administration': 'TestAdmin',
        }

        result = processor.save_btw_transaction(transaction)

        assert result['success'] is False
        assert 'already exists' in result['error']
        mock_conn.commit.assert_not_called()

    def test_save_btw_transaction_db_error_returns_failure(self, processor):
        """Test database error returns failure with error message."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        processor.db.get_connection.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = None
        mock_cursor.execute.side_effect = [None, Exception("Insert failed")]

        transaction = {
            'TransactionNumber': 'BTW',
            'TransactionDate': '2024-04-01',
            'TransactionDescription': 'BTW aangifte 2024 Q1',
            'TransactionAmount': 500,
            'Debet': '2010',
            'Credit': '1300',
            'ReferenceNumber': 'BTW',
            'Ref1': 'BTW aangifte TestAdmin',
            'Ref2': '2024-Q1',
            'Ref3': '€500 te betalen',
            'Ref4': 'Generated 2024-04-01',
            'Administration': 'TestAdmin',
        }

        result = processor.save_btw_transaction(transaction)

        assert result['success'] is False
        assert 'Insert failed' in result['error']
        mock_conn.rollback.assert_called_once()


class TestUploadReportToDrive:
    """Tests for upload_report_to_drive method."""

    @pytest.fixture
    def processor(self, mock_db):
        with patch('btw_processor.DatabaseManager', return_value=mock_db):
            proc = BTWProcessor(test_mode=True)
        return proc

    @pytest.fixture
    def prod_processor(self, mock_db):
        with patch('btw_processor.DatabaseManager', return_value=mock_db):
            proc = BTWProcessor(test_mode=False)
        return proc

    def test_upload_report_test_mode_saves_locally(self, processor, temp_dir):
        """Test that test mode saves file locally."""
        html_content = '<html><body>Test Report</body></html>'
        filename = 'btw_report_2024_Q1.html'

        with patch('builtins.open', MagicMock()):
            result = processor.upload_report_to_drive(html_content, filename, 'TestAdmin')

        assert result['success'] is True
        assert result['location'] == 'local'
        assert 'localhost' in result['url']

    @patch('btw_processor.GoogleDriveService')
    def test_upload_report_production_mode_uploads_to_drive(self, mock_drive_class, prod_processor):
        """Test that production mode uploads to Google Drive."""
        mock_drive = MagicMock()
        mock_drive_class.return_value = mock_drive
        mock_drive.list_subfolders.return_value = [
            {'name': 'btw', 'id': 'btw_folder_123'}
        ]
        mock_drive.upload_file.return_value = {'url': 'https://drive.google.com/file/123'}

        html_content = '<html><body>Report</body></html>'
        result = prod_processor.upload_report_to_drive(html_content, 'report.html', 'TestAdmin')

        assert result['success'] is True
        assert result['location'] == 'google_drive'
        assert 'drive.google.com' in result['url']

    @patch('btw_processor.GoogleDriveService')
    def test_upload_report_production_no_btw_folder_returns_error(self, mock_drive_class, prod_processor):
        """Test error when BTW folder not found in Google Drive."""
        mock_drive = MagicMock()
        mock_drive_class.return_value = mock_drive
        mock_drive.list_subfolders.return_value = [
            {'name': 'invoices', 'id': 'inv_folder_123'}
        ]

        html_content = '<html><body>Report</body></html>'
        result = prod_processor.upload_report_to_drive(html_content, 'report.html', 'TestAdmin')

        assert result['success'] is False
        assert 'BTW folder not found' in result['error']

    def test_upload_report_exception_returns_failure(self, prod_processor):
        """Test that exceptions return failure."""
        with patch('btw_processor.GoogleDriveService', side_effect=Exception("Drive error")):
            result = prod_processor.upload_report_to_drive('<html></html>', 'report.html', 'TestAdmin')

        assert result['success'] is False
        assert 'Drive error' in result['error']


class TestGetVatAccountsDateConversion:
    """Tests for date conversion paths in VAT account methods."""

    def test_get_vat_accounts_with_date_object(self, mock_db):
        """Test _get_vat_accounts with a date object instead of string."""
        from datetime import date
        mock_tax_service = MagicMock()
        mock_tax_service.get_all_vat_codes.return_value = [
            {'ledger_account': '2010', 'code': 'zero'},
            {'ledger_account': '2020', 'code': 'high'},
        ]
        with patch('btw_processor.DatabaseManager', return_value=mock_db):
            proc = BTWProcessor(test_mode=True, tax_rate_service=mock_tax_service)

        result = proc._get_vat_accounts('TestAdmin', reference_date=date(2024, 6, 30))
        assert result == ['2010', '2020']

    def test_get_received_vat_accounts_with_date_object(self, mock_db):
        """Test _get_received_vat_accounts with a date object."""
        from datetime import date
        mock_tax_service = MagicMock()
        mock_tax_service.get_all_vat_codes.return_value = [
            {'ledger_account': '2010', 'code': 'zero'},
            {'ledger_account': '2020', 'code': 'high'},
            {'ledger_account': '2021', 'code': 'low'},
        ]
        with patch('btw_processor.DatabaseManager', return_value=mock_db):
            proc = BTWProcessor(test_mode=True, tax_rate_service=mock_tax_service)

        result = proc._get_received_vat_accounts('TestAdmin', reference_date=date(2024, 3, 31))
        assert '2010' not in result
        assert '2020' in result

    def test_get_primary_vat_account_with_date_object(self, mock_db):
        """Test _get_primary_vat_account with a date object."""
        from datetime import date
        mock_tax_service = MagicMock()
        mock_tax_service.get_all_vat_codes.return_value = [
            {'ledger_account': '2010', 'code': 'zero'},
        ]
        with patch('btw_processor.DatabaseManager', return_value=mock_db):
            proc = BTWProcessor(test_mode=True, tax_rate_service=mock_tax_service)

        result = proc._get_primary_vat_account('TestAdmin', reference_date=date(2024, 6, 30))
        assert result == '2010'


class TestGetLastBtwTransaction:
    """Tests for _get_last_btw_transaction method."""

    @pytest.fixture
    def processor(self, mock_db):
        with patch('btw_processor.DatabaseManager', return_value=mock_db):
            proc = BTWProcessor(test_mode=True)
        return proc

    def test_get_last_btw_transaction_returns_result(self, processor):
        """Test successful retrieval of last BTW transaction."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        processor.db.get_connection.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = {
            'ID': 100,
            'TransactionNumber': 'BTW',
            'TransactionDate': '2024-01-15',
        }

        result = processor._get_last_btw_transaction('TestAdmin')

        assert result is not None
        assert result['ID'] == 100

    def test_get_last_btw_transaction_no_result(self, processor):
        """Test when no BTW transaction exists."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        processor.db.get_connection.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = None

        result = processor._get_last_btw_transaction('TestAdmin')

        assert result is None

    def test_get_last_btw_transaction_exception_returns_none(self, processor):
        """Test that exceptions return None."""
        processor.db.get_connection.side_effect = Exception("DB error")

        result = processor._get_last_btw_transaction('TestAdmin')

        assert result is None
