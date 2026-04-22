"""
Unit tests for Aangifte IB Generator

Tests the generate_table_rows function and helper functions.
"""

import pytest
from unittest.mock import Mock, MagicMock
from report_generators.aangifte_ib_generator import (
    generate_table_rows,
    _group_by_parent,
    _create_parent_row,
    _create_aangifte_row,
    _create_account_row,
    _create_resultaat_row,
    _create_grand_total_row,
    _fetch_and_create_account_rows
)


class TestGroupByParent:
    """Tests for _group_by_parent helper function"""
    
    def test_groups_data_by_parent(self):
        """Test that data is correctly grouped by Parent code"""
        report_data = [
            {'Parent': '1000', 'Aangifte': 'Liquide middelen', 'Amount': 100.0},
            {'Parent': '1000', 'Aangifte': 'Schulden', 'Amount': -50.0},
            {'Parent': '2000', 'Aangifte': 'BTW', 'Amount': 200.0}
        ]
        
        grouped = _group_by_parent(report_data)
        
        assert '1000' in grouped
        assert '2000' in grouped
        assert len(grouped['1000']) == 2
        assert len(grouped['2000']) == 1
    
    def test_handles_empty_data(self):
        """Test that empty data returns empty dict"""
        grouped = _group_by_parent([])
        assert grouped == {}


class TestCreateParentRow:
    """Tests for _create_parent_row helper function"""
    
    def test_creates_parent_row_with_correct_structure(self):
        """Test that parent row has correct structure"""
        row = _create_parent_row('1000', 88130.07)
        
        assert row['row_type'] == 'parent'
        assert row['parent'] == '1000'
        assert row['aangifte'] == ''
        assert row['description'] == ''
        assert row['amount'] == '88.130,07'
        assert row['amount_raw'] == 88130.07
        assert row['css_class'] == 'parent-row'
        assert row['indent_level'] == 0
    
    def test_handles_negative_amounts(self):
        """Test parent row with negative amount"""
        row = _create_parent_row('2000', -1430.31)
        
        assert row['amount'] == '-1.430,31'
        assert row['amount_raw'] == -1430.31


class TestCreateAangifteRow:
    """Tests for _create_aangifte_row helper function"""
    
    def test_creates_aangifte_row_with_correct_structure(self):
        """Test that aangifte row has correct structure"""
        row = _create_aangifte_row('Liquide middelen', 88262.80)
        
        assert row['row_type'] == 'aangifte'
        assert row['parent'] == ''
        assert row['aangifte'] == 'Liquide middelen'
        assert row['description'] == ''
        assert row['amount'] == '88.262,80'
        assert row['amount_raw'] == 88262.80
        assert row['css_class'] == 'aangifte-row'
        assert row['indent_level'] == 1
    
    def test_escapes_html_in_aangifte_name(self):
        """Test that HTML is escaped in aangifte name"""
        row = _create_aangifte_row('<script>alert("XSS")</script>', 100.0)
        
        assert '&lt;script&gt;' in row['aangifte']
        assert '<script>' not in row['aangifte']


class TestCreateAccountRow:
    """Tests for _create_account_row helper function"""
    
    def test_creates_account_row_with_correct_structure(self):
        """Test that account row has correct structure"""
        row = _create_account_row('1002', 'NL80RABO0107936917 RCRT', 6972.69)
        
        assert row['row_type'] == 'account'
        assert row['parent'] == ''
        assert row['aangifte'] == '1002'
        assert row['description'] == 'NL80RABO0107936917 RCRT'
        assert row['amount'] == '6.972,69'
        assert row['amount_raw'] == 6972.69
        assert row['css_class'] == 'account-row'
        assert row['indent_level'] == 2
    
    def test_escapes_html_in_account_details(self):
        """Test that HTML is escaped in account details"""
        row = _create_account_row('<b>1002</b>', '<i>Account</i>', 100.0)
        
        assert '&lt;b&gt;' in row['aangifte']
        assert '&lt;i&gt;' in row['description']


class TestCreateResultaatRow:
    """Tests for _create_resultaat_row helper function"""
    
    def test_creates_positive_resultaat_row(self):
        """Test resultaat row with positive amount"""
        row = _create_resultaat_row(28853.76)
        
        assert row['row_type'] == 'resultaat'
        assert row['parent'] == 'RESULTAAT'
        assert row['amount'] == '28.853,76'
        assert row['css_class'] == 'resultaat-positive'
    
    def test_creates_negative_resultaat_row(self):
        """Test resultaat row with negative amount"""
        row = _create_resultaat_row(-5000.00)
        
        assert row['row_type'] == 'resultaat'
        assert row['css_class'] == 'resultaat-negative'


class TestCreateGrandTotalRow:
    """Tests for _create_grand_total_row helper function"""
    
    def test_creates_grand_total_row(self):
        """Test grand total row structure"""
        row = _create_grand_total_row(0.0)
        
        assert row['row_type'] == 'grand_total'
        assert row['parent'] == 'GRAND TOTAL'
        assert row['amount'] == '0,00'
        assert row['css_class'] == 'grand-total'


class TestFetchAndCreateAccountRows:
    """Tests for _fetch_and_create_account_rows helper function"""
    
    def test_fetches_and_creates_account_rows(self):
        """Test that account details are fetched and rows created"""
        # Mock cache
        mock_cache = Mock()
        mock_cache.query_aangifte_ib_details.return_value = [
            {'Reknum': '1002', 'AccountName': 'Bank Account 1', 'Amount': 6972.69},
            {'Reknum': '1011', 'AccountName': 'Bank Account 2', 'Amount': 24971.44}
        ]
        
        rows = _fetch_and_create_account_rows(
            cache=mock_cache,
            year=2025,
            administration='GoodwinSolutions',
            parent='1000',
            aangifte='Liquide middelen',
            user_tenants=['GoodwinSolutions']
        )
        
        assert len(rows) == 2
        assert rows[0]['row_type'] == 'account'
        assert rows[0]['aangifte'] == '1002'
        assert rows[1]['aangifte'] == '1011'
        
        # Verify cache was called with correct parameters
        mock_cache.query_aangifte_ib_details.assert_called_once_with(
            year=2025,
            administration='GoodwinSolutions',
            parent='1000',
            aangifte='Liquide middelen',
            user_tenants=['GoodwinSolutions']
        )
    
    def test_filters_zero_amounts(self):
        """Test that zero amounts are filtered out"""
        mock_cache = Mock()
        mock_cache.query_aangifte_ib_details.return_value = [
            {'Reknum': '1002', 'AccountName': 'Bank Account 1', 'Amount': 6972.69},
            {'Reknum': '1003', 'AccountName': 'Zero Account', 'Amount': 0.0},
            {'Reknum': '1004', 'AccountName': 'Small Amount', 'Amount': 0.005}
        ]
        
        rows = _fetch_and_create_account_rows(
            cache=mock_cache,
            year=2025,
            administration='GoodwinSolutions',
            parent='1000',
            aangifte='Liquide middelen',
            user_tenants=['GoodwinSolutions']
        )
        
        # Only non-zero amounts should be included
        assert len(rows) == 1
        assert rows[0]['aangifte'] == '1002'
    
    def test_handles_cache_error_gracefully(self):
        """Test that cache errors don't crash the function"""
        mock_cache = Mock()
        mock_cache.query_aangifte_ib_details.side_effect = Exception("Cache error")
        
        rows = _fetch_and_create_account_rows(
            cache=mock_cache,
            year=2025,
            administration='GoodwinSolutions',
            parent='1000',
            aangifte='Liquide middelen',
            user_tenants=['GoodwinSolutions']
        )
        
        # Should return empty list on error
        assert rows == []


class TestGenerateTableRows:
    """Tests for main generate_table_rows function"""
    
    def test_generates_complete_hierarchical_structure(self):
        """Test that complete hierarchy is generated"""
        report_data = [
            {'Parent': '1000', 'Aangifte': 'Liquide middelen', 'Amount': 100.0, 'VW': 'N'},
            {'Parent': '8000', 'Aangifte': 'Revenue', 'Amount': -50.0, 'VW': 'Y'}  # P&L account
        ]
        
        mock_cache = Mock()
        mock_cache.query_aangifte_ib_details.return_value = [
            {'Reknum': '1002', 'AccountName': 'Bank Account', 'Amount': 100.0}
        ]
        
        rows = generate_table_rows(
            report_data=report_data,
            cache=mock_cache,
            year=2025,
            administration='GoodwinSolutions',
            user_tenants=['GoodwinSolutions']
        )
        
        # Should have: 2 parents + 2 aangiftes + accounts + resultaat + grand_total
        assert len(rows) > 4
        
        # Check row types are present
        row_types = [row['row_type'] for row in rows]
        assert 'parent' in row_types
        assert 'aangifte' in row_types
        assert 'account' in row_types
        assert 'resultaat' in row_types
        assert 'grand_total' in row_types
    
    def test_filters_zero_parent_totals(self):
        """Test that parent groups with zero total are filtered"""
        report_data = [
            {'Parent': '1000', 'Aangifte': 'Item1', 'Amount': 100.0, 'VW': 'N'},
            {'Parent': '1000', 'Aangifte': 'Item2', 'Amount': -100.0, 'VW': 'N'},  # Cancels out
            {'Parent': '2000', 'Aangifte': 'BTW', 'Amount': 50.0, 'VW': 'N'}
        ]
        
        mock_cache = Mock()
        mock_cache.query_aangifte_ib_details.return_value = []
        
        rows = generate_table_rows(
            report_data=report_data,
            cache=mock_cache,
            year=2025,
            administration='GoodwinSolutions',
            user_tenants=['GoodwinSolutions']
        )
        
        # Parent 1000 should be filtered (total = 0)
        parent_rows = [row for row in rows if row['row_type'] == 'parent']
        assert len(parent_rows) == 1
        assert parent_rows[0]['parent'] == '2000'
    
    def test_filters_zero_aangifte_amounts(self):
        """Test that aangifte items with zero amounts are filtered"""
        report_data = [
            {'Parent': '1000', 'Aangifte': 'Item1', 'Amount': 100.0, 'VW': 'N'},
            {'Parent': '1000', 'Aangifte': 'Item2', 'Amount': 0.005, 'VW': 'N'}  # Below threshold
        ]
        
        mock_cache = Mock()
        mock_cache.query_aangifte_ib_details.return_value = []
        
        rows = generate_table_rows(
            report_data=report_data,
            cache=mock_cache,
            year=2025,
            administration='GoodwinSolutions',
            user_tenants=['GoodwinSolutions']
        )
        
        # Only Item1 should be included
        aangifte_rows = [row for row in rows if row['row_type'] == 'aangifte']
        assert len(aangifte_rows) == 1
        assert aangifte_rows[0]['aangifte'] == 'Item1'
    
    def test_handles_empty_report_data(self):
        """Test that empty report data returns minimal structure"""
        mock_cache = Mock()
        
        rows = generate_table_rows(
            report_data=[],
            cache=mock_cache,
            year=2025,
            administration='GoodwinSolutions',
            user_tenants=['GoodwinSolutions']
        )
        
        # Should return empty list for empty data
        assert rows == []
    
    def test_calculates_resultaat_correctly(self):
        """Test that resultaat is calculated as sum of P&L accounts (VW='Y') only"""
        report_data = [
            {'Parent': '1000', 'Aangifte': 'Item1', 'Amount': 100.0, 'VW': 'N'},  # Balance sheet - excluded
            {'Parent': '8000', 'Aangifte': 'Item2', 'Amount': -30.0, 'VW': 'Y'},  # P&L - included
            {'Parent': '4000', 'Aangifte': 'Item3', 'Amount': 50.0, 'VW': 'Y'}    # P&L - included
        ]
        
        mock_cache = Mock()
        mock_cache.query_aangifte_ib_details.return_value = []
        
        rows = generate_table_rows(
            report_data=report_data,
            cache=mock_cache,
            year=2025,
            administration='GoodwinSolutions',
            user_tenants=['GoodwinSolutions']
        )
        
        # Find resultaat row
        resultaat_rows = [row for row in rows if row['row_type'] == 'resultaat']
        assert len(resultaat_rows) == 1
        assert resultaat_rows[0]['amount_raw'] == 20.0  # -30 + 50 (excludes 100 from balance sheet)
    
    def test_passes_user_tenants_to_cache(self):
        """Test that user_tenants is passed to cache for security"""
        report_data = [
            {'Parent': '1000', 'Aangifte': 'Liquide middelen', 'Amount': 100.0, 'VW': 'N'}
        ]
        
        mock_cache = Mock()
        mock_cache.query_aangifte_ib_details.return_value = []
        
        user_tenants = ['GoodwinSolutions', 'PeterPrive']
        
        generate_table_rows(
            report_data=report_data,
            cache=mock_cache,
            year=2025,
            administration='GoodwinSolutions',
            user_tenants=user_tenants
        )
        
        # Verify user_tenants was passed to cache
        call_args = mock_cache.query_aangifte_ib_details.call_args
        assert call_args.kwargs['user_tenants'] == user_tenants


class TestResultaatUsesVWField:
    """Tests that resultaat calculation uses VW='Y' field instead of Parent prefix.
    
    Validates: Requirements 2.8, 3.5
    """

    def test_resultaat_uses_vw_field(self):
        """Test generate_table_rows() uses VW='Y' for P&L classification"""
        report_data = [
            {'Parent': '1000', 'Aangifte': 'Bank', 'Amount': 500.0, 'VW': 'N'},
            {'Parent': '4000', 'Aangifte': 'Expenses', 'Amount': 200.0, 'VW': 'Y'},
            {'Parent': '8000', 'Aangifte': 'Revenue', 'Amount': -300.0, 'VW': 'Y'},
        ]

        mock_cache = Mock()
        mock_cache.query_aangifte_ib_details.return_value = []

        rows = generate_table_rows(
            report_data=report_data,
            cache=mock_cache,
            year=2025,
            administration='GoodwinSolutions',
            user_tenants=['GoodwinSolutions']
        )

        resultaat_rows = [r for r in rows if r['row_type'] == 'resultaat']
        assert len(resultaat_rows) == 1
        # Only VW='Y' items: 200.0 + (-300.0) = -100.0
        assert resultaat_rows[0]['amount_raw'] == -100.0

    def test_vw_wins_over_parent_prefix_disagreement(self):
        """Test that VW field takes precedence when VW and Parent prefix disagree.
        
        - Account with Parent='1000' (balance sheet prefix) but VW='Y' (P&L) → INCLUDED in resultaat
        - Account with Parent='8000' (P&L prefix) but VW='N' (balance sheet) → EXCLUDED from resultaat
        This proves the system uses VW, not Parent prefix.
        """
        report_data = [
            # Balance sheet Parent prefix, but VW says P&L → should be INCLUDED
            {'Parent': '1000', 'Aangifte': 'Unusual P&L in 1xxx', 'Amount': 150.0, 'VW': 'Y'},
            # P&L Parent prefix, but VW says Balance sheet → should be EXCLUDED
            {'Parent': '8000', 'Aangifte': 'Unusual BS in 8xxx', 'Amount': 250.0, 'VW': 'N'},
            # Normal P&L account → should be INCLUDED
            {'Parent': '4000', 'Aangifte': 'Normal expense', 'Amount': 100.0, 'VW': 'Y'},
        ]

        mock_cache = Mock()
        mock_cache.query_aangifte_ib_details.return_value = []

        rows = generate_table_rows(
            report_data=report_data,
            cache=mock_cache,
            year=2025,
            administration='GoodwinSolutions',
            user_tenants=['GoodwinSolutions']
        )

        resultaat_rows = [r for r in rows if r['row_type'] == 'resultaat']
        assert len(resultaat_rows) == 1
        # Only VW='Y' items: 150.0 (Parent 1000, VW Y) + 100.0 (Parent 4000, VW Y) = 250.0
        # The 250.0 with Parent 8000 but VW='N' is EXCLUDED
        assert resultaat_rows[0]['amount_raw'] == 250.0

    def test_resultaat_standard_dutch_chart(self):
        """Test resultaat calculation matches expected for standard Dutch chart of accounts.
        
        In the standard Dutch chart, VW='Y' accounts are 4xxx-9xxx (expenses and revenue).
        VW='N' accounts are 1xxx-3xxx (balance sheet).
        """
        report_data = [
            # Balance sheet accounts (VW='N') — excluded from resultaat
            {'Parent': '1000', 'Aangifte': 'Liquide middelen', 'Amount': 88262.80, 'VW': 'N'},
            {'Parent': '2000', 'Aangifte': 'BTW', 'Amount': -1430.31, 'VW': 'N'},
            {'Parent': '3000', 'Aangifte': 'Eigen vermogen', 'Amount': -50000.0, 'VW': 'N'},
            # P&L accounts (VW='Y') — included in resultaat
            {'Parent': '4000', 'Aangifte': 'Kosten', 'Amount': 12500.0, 'VW': 'Y'},
            {'Parent': '8000', 'Aangifte': 'Omzet', 'Amount': -45000.0, 'VW': 'Y'},
            {'Parent': '8000', 'Aangifte': 'Rente', 'Amount': -120.50, 'VW': 'Y'},
            {'Parent': '9000', 'Aangifte': 'Afschrijvingen', 'Amount': 3788.01, 'VW': 'Y'},
        ]

        mock_cache = Mock()
        mock_cache.query_aangifte_ib_details.return_value = []

        rows = generate_table_rows(
            report_data=report_data,
            cache=mock_cache,
            year=2025,
            administration='GoodwinSolutions',
            user_tenants=['GoodwinSolutions']
        )

        resultaat_rows = [r for r in rows if r['row_type'] == 'resultaat']
        assert len(resultaat_rows) == 1
        # Expected: 12500.0 + (-45000.0) + (-120.50) + 3788.01 = -28832.49
        expected_resultaat = 12500.0 + (-45000.0) + (-120.50) + 3788.01
        assert abs(resultaat_rows[0]['amount_raw'] - expected_resultaat) < 0.01

    def test_missing_vw_field_excluded_from_resultaat(self):
        """Test that items without VW field are excluded from resultaat calculation"""
        report_data = [
            {'Parent': '8000', 'Aangifte': 'Revenue', 'Amount': -500.0, 'VW': 'Y'},
            {'Parent': '4000', 'Aangifte': 'No VW field', 'Amount': 200.0},  # Missing VW
            {'Parent': '6000', 'Aangifte': 'Empty VW', 'Amount': 100.0, 'VW': ''},  # Empty VW
        ]

        mock_cache = Mock()
        mock_cache.query_aangifte_ib_details.return_value = []

        rows = generate_table_rows(
            report_data=report_data,
            cache=mock_cache,
            year=2025,
            administration='GoodwinSolutions',
            user_tenants=['GoodwinSolutions']
        )

        resultaat_rows = [r for r in rows if r['row_type'] == 'resultaat']
        assert len(resultaat_rows) == 1
        # Only the VW='Y' item is included: -500.0
        assert resultaat_rows[0]['amount_raw'] == -500.0
