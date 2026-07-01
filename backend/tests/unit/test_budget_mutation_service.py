"""Unit tests for BudgetMutationService.

Tests cover:
- Monetary utilities (round_monetary, divide_annual)
- Budget version CRUD (create, delete, transition_status, activate)
- Budget line CRUD (create, update, delete)
"""

import pytest
from decimal import Decimal
from unittest.mock import MagicMock, patch

from services.budget_mutation_service import BudgetMutationService
from db_exceptions import IntegrityError


@pytest.fixture
def mock_db():
    """Create a mock DatabaseManager."""
    return MagicMock()


@pytest.fixture
def service(mock_db):
    """Create a BudgetMutationService with mocked DB."""
    return BudgetMutationService(db=mock_db)


# ---------------------------------------------------------------------------
# Monetary Utilities
# ---------------------------------------------------------------------------

class TestRoundMonetary:
    """Tests for round_monetary static method."""

    def test_rounds_to_two_decimals(self):
        result = BudgetMutationService.round_monetary(Decimal('10.125'))
        assert result == Decimal('10.12')  # Banker's rounding: .5 rounds to even

    def test_rounds_up_when_above_half(self):
        result = BudgetMutationService.round_monetary(Decimal('10.126'))
        assert result == Decimal('10.13')

    def test_no_change_when_already_two_decimals(self):
        result = BudgetMutationService.round_monetary(Decimal('99.99'))
        assert result == Decimal('99.99')

    def test_bankers_rounding_rounds_to_even(self):
        # 10.135 → rounds to 10.14 (nearest even)
        result = BudgetMutationService.round_monetary(Decimal('10.135'))
        assert result == Decimal('10.14')

        # 10.145 → rounds to 10.14 (nearest even)
        result = BudgetMutationService.round_monetary(Decimal('10.145'))
        assert result == Decimal('10.14')


class TestDivideAnnual:
    """Tests for divide_annual static method."""

    def test_even_division(self):
        amounts = BudgetMutationService.divide_annual(Decimal('1200.00'))
        assert len(amounts) == 12
        assert all(a == Decimal('100.00') for a in amounts)

    def test_sum_equals_original(self):
        amounts = BudgetMutationService.divide_annual(Decimal('1000.00'))
        assert sum(amounts) == Decimal('1000.00')

    def test_remainder_absorbed_by_last_month(self):
        # 100 / 12 = 8.33 * 12 = 99.96, remainder = 0.04
        amounts = BudgetMutationService.divide_annual(Decimal('100.00'))
        assert sum(amounts) == Decimal('100.00')
        # First 11 months should be equal
        assert all(a == amounts[0] for a in amounts[:11])

    def test_custom_month_count(self):
        amounts = BudgetMutationService.divide_annual(Decimal('100.00'), months=4)
        assert len(amounts) == 4
        assert sum(amounts) == Decimal('100.00')


# ---------------------------------------------------------------------------
# Budget Version Management
# ---------------------------------------------------------------------------

class TestCreateVersion:
    """Tests for create_version."""

    def test_success(self, service, mock_db):
        mock_db.execute_query.return_value = 42
        result = service.create_version('TenantA', 'Q1 Budget', 2026)
        assert result['success'] is True
        assert result['data']['id'] == 42
        assert result['data']['status'] == 'Draft'
        assert result['data']['is_active'] is False

    def test_duplicate_returns_error(self, service, mock_db):
        mock_db.execute_query.side_effect = IntegrityError("Duplicate entry")
        result = service.create_version('TenantA', 'Q1 Budget', 2026)
        assert result['success'] is False
        assert 'already exists' in result['error']


class TestDeleteVersion:
    """Tests for delete_version."""

    def test_success_for_draft(self, service, mock_db):
        mock_db.execute_query.side_effect = [
            [{'id': 1, 'status': 'Draft'}],  # SELECT
            None,  # DELETE
        ]
        result = service.delete_version('TenantA', 1)
        assert result['success'] is True

    def test_not_found(self, service, mock_db):
        mock_db.execute_query.return_value = []
        result = service.delete_version('TenantA', 999)
        assert result['success'] is False
        assert 'not found' in result['error']

    def test_cannot_delete_approved(self, service, mock_db):
        mock_db.execute_query.return_value = [{'id': 1, 'status': 'Approved'}]
        result = service.delete_version('TenantA', 1)
        assert result['success'] is False
        assert 'Draft' in result['error']


class TestTransitionStatus:
    """Tests for transition_status."""

    def test_approve_draft(self, service, mock_db):
        mock_db.execute_query.side_effect = [
            [{'id': 1, 'name': 'Budget', 'fiscal_year': 2026,
              'status': 'Draft', 'is_active': False,
              'status_changed_at': None, 'created_at': None, 'updated_at': None}],
            None,  # UPDATE
        ]
        result = service.transition_status('TenantA', 1, 'approve')
        assert result['success'] is True
        assert result['data']['status'] == 'Approved'

    def test_invalid_action(self, service, mock_db):
        result = service.transition_status('TenantA', 1, 'invalid')
        assert result['success'] is False
        assert 'Invalid action' in result['error']

    def test_cannot_approve_approved(self, service, mock_db):
        mock_db.execute_query.return_value = [
            {'id': 1, 'name': 'Budget', 'fiscal_year': 2026,
             'status': 'Approved', 'is_active': True,
             'status_changed_at': None, 'created_at': None, 'updated_at': None}
        ]
        result = service.transition_status('TenantA', 1, 'approve')
        assert result['success'] is False
        assert 'Cannot transition' in result['error']

    def test_not_found(self, service, mock_db):
        mock_db.execute_query.return_value = []
        result = service.transition_status('TenantA', 999, 'approve')
        assert result['success'] is False
        assert 'not found' in result['error']


class TestActivateVersion:
    """Tests for activate_version."""

    def test_activate_approved(self, service, mock_db):
        mock_db.execute_query.side_effect = [
            [{'id': 1, 'name': 'Budget', 'fiscal_year': 2026,
              'status': 'Approved', 'is_active': False}],
            None,  # UPDATE
        ]
        result = service.activate_version('TenantA', 1, active=True)
        assert result['success'] is True
        assert result['data']['is_active'] is True

    def test_cannot_activate_draft(self, service, mock_db):
        mock_db.execute_query.return_value = [
            {'id': 1, 'name': 'Budget', 'fiscal_year': 2026,
             'status': 'Draft', 'is_active': False}
        ]
        result = service.activate_version('TenantA', 1, active=True)
        assert result['success'] is False
        assert 'Approved or Revised' in result['error']

    def test_deactivate_any_status(self, service, mock_db):
        mock_db.execute_query.side_effect = [
            [{'id': 1, 'name': 'Budget', 'fiscal_year': 2026,
              'status': 'Draft', 'is_active': True}],
            None,
        ]
        result = service.activate_version('TenantA', 1, active=False)
        assert result['success'] is True
        assert result['data']['is_active'] is False

    def test_not_found(self, service, mock_db):
        mock_db.execute_query.return_value = []
        result = service.activate_version('TenantA', 999)
        assert result['success'] is False
        assert 'not found' in result['error']
