"""Unit tests for BudgetQueryService.

Tests cover:
- Monetary rounding utility
- Period parsing (_parse_period)
- Month summation (_sum_months)
- Version listing (list_versions)
- Line listing (list_lines)
"""

import pytest
from decimal import Decimal
from unittest.mock import MagicMock, patch
from datetime import datetime

from services.budget_query_service import BudgetQueryService


@pytest.fixture
def mock_db():
    """Create a mock DatabaseManager."""
    return MagicMock()


@pytest.fixture
def service(mock_db):
    """Create a BudgetQueryService with mocked DB."""
    return BudgetQueryService(db=mock_db)


# ---------------------------------------------------------------------------
# Monetary Utility
# ---------------------------------------------------------------------------

class TestRoundMonetary:
    """Tests for round_monetary static method."""

    def test_rounds_to_two_decimals(self):
        assert BudgetQueryService.round_monetary(Decimal('5.555')) == Decimal('5.56')

    def test_no_change_when_exact(self):
        assert BudgetQueryService.round_monetary(Decimal('10.00')) == Decimal('10.00')


# ---------------------------------------------------------------------------
# Period Parsing
# ---------------------------------------------------------------------------

class TestParsePeriod:
    """Tests for _parse_period."""

    def test_single_month(self, service):
        assert service._parse_period('month-1') == [1]
        assert service._parse_period('month-6') == [6]
        assert service._parse_period('month-12') == [12]

    def test_quarter(self, service):
        assert service._parse_period('q1') == [1, 2, 3]
        assert service._parse_period('q2') == [4, 5, 6]
        assert service._parse_period('q3') == [7, 8, 9]
        assert service._parse_period('q4') == [10, 11, 12]

    def test_full_year(self, service):
        assert service._parse_period('full') == list(range(1, 13))

    def test_ytd_returns_up_to_current_month(self, service):
        result = service._parse_period('ytd')
        current_month = datetime.now().month
        assert result == list(range(1, current_month + 1))

    def test_invalid_defaults_to_full(self, service):
        assert service._parse_period('garbage') == list(range(1, 13))
        assert service._parse_period('') == list(range(1, 13))

    def test_invalid_month_number_defaults_to_full(self, service):
        assert service._parse_period('month-0') == list(range(1, 13))
        assert service._parse_period('month-13') == list(range(1, 13))


# ---------------------------------------------------------------------------
# Month Summation
# ---------------------------------------------------------------------------

class TestSumMonths:
    """Tests for _sum_months static method."""

    def test_sum_all_months(self):
        row = {f'm{i:02d}': Decimal('100.00') for i in range(1, 13)}
        result = BudgetQueryService._sum_months(row)
        assert result == Decimal('1200.00')

    def test_sum_specific_months(self):
        row = {f'm{i:02d}': Decimal(str(i * 10)) for i in range(1, 13)}
        # Sum months 1-3 (Q1): 10 + 20 + 30 = 60
        result = BudgetQueryService._sum_months(row, months=[1, 2, 3])
        assert result == Decimal('60')

    def test_missing_month_defaults_to_zero(self):
        row = {'m01': Decimal('50.00')}  # Only month 1 present
        result = BudgetQueryService._sum_months(row)
        assert result == Decimal('50.00')

    def test_none_values_treated_as_zero(self):
        row = {f'm{i:02d}': None for i in range(1, 13)}
        row['m01'] = Decimal('25.00')
        result = BudgetQueryService._sum_months(row)
        assert result == Decimal('25.00')


# ---------------------------------------------------------------------------
# List Versions
# ---------------------------------------------------------------------------

class TestListVersions:
    """Tests for list_versions."""

    def test_returns_all_versions(self, service, mock_db):
        mock_db.execute_query.return_value = [
            {'id': 1, 'name': 'Budget A', 'fiscal_year': 2026, 'status': 'Draft'},
            {'id': 2, 'name': 'Budget B', 'fiscal_year': 2025, 'status': 'Approved'},
        ]
        result = service.list_versions('TenantA')
        assert result['success'] is True
        assert len(result['data']) == 2

    def test_filters_by_year(self, service, mock_db):
        mock_db.execute_query.return_value = [
            {'id': 1, 'name': 'Budget A', 'fiscal_year': 2026, 'status': 'Draft'},
        ]
        result = service.list_versions('TenantA', year=2026)
        assert result['success'] is True
        # Verify year was passed in params
        call_args = mock_db.execute_query.call_args[0]
        assert 2026 in call_args[1]

    def test_empty_result(self, service, mock_db):
        mock_db.execute_query.return_value = []
        result = service.list_versions('TenantA')
        assert result['success'] is True
        assert result['data'] == []

    def test_none_result_treated_as_empty(self, service, mock_db):
        mock_db.execute_query.return_value = None
        result = service.list_versions('TenantA')
        assert result['success'] is True
        assert result['data'] == []


# ---------------------------------------------------------------------------
# List Lines
# ---------------------------------------------------------------------------

class TestListLines:
    """Tests for list_lines."""

    def test_returns_lines_for_version(self, service, mock_db):
        mock_db.execute_query.return_value = [
            {'id': 1, 'account_code': '4000', 'period_mode': 'Monthly',
             'month_01': Decimal('100.00')},
        ]
        result = service.list_lines('TenantA', version_id=1)
        assert result['success'] is True
        assert len(result['data']) == 1
        assert result['data'][0]['account_code'] == '4000'

    def test_empty_version(self, service, mock_db):
        mock_db.execute_query.return_value = []
        result = service.list_lines('TenantA', version_id=999)
        assert result['success'] is True
        assert result['data'] == []

    def test_tenant_isolation_in_query(self, service, mock_db):
        mock_db.execute_query.return_value = []
        service.list_lines('TenantB', version_id=5)
        call_args = mock_db.execute_query.call_args[0]
        assert 'TenantB' in call_args[1]
