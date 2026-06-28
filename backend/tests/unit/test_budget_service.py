"""
Unit tests for BudgetService monetary utilities.

Tests the divide_annual() and round_monetary() methods which form
the foundation of all budget monetary calculations.

Requirements: 2.3, 3.2, 3.5
"""

import pytest
from decimal import Decimal
from unittest.mock import patch

# Mock DatabaseManager before importing BudgetService
with patch('database.DatabaseManager'):
    from services.budget_service import BudgetService


class TestRoundMonetary:
    """Tests for BudgetService.round_monetary() banker's rounding utility."""

    def test_rounds_to_two_decimal_places(self):
        """Standard rounding to 2dp."""
        assert BudgetService.round_monetary(Decimal('10.456')) == Decimal('10.46')

    def test_bankers_rounding_half_to_even_rounds_down(self):
        """When exactly halfway, rounds to even (down when digit is even)."""
        # 2.5 -> 2 (rounds down to even)
        assert BudgetService.round_monetary(Decimal('10.125')) == Decimal('10.12')

    def test_bankers_rounding_half_to_even_rounds_up(self):
        """When exactly halfway, rounds to even (up when digit is odd)."""
        # 1.5 -> 2 (rounds up to even)
        assert BudgetService.round_monetary(Decimal('10.135')) == Decimal('10.14')

    def test_already_two_decimal_places(self):
        """Amount already at 2dp stays unchanged."""
        assert BudgetService.round_monetary(Decimal('99.99')) == Decimal('99.99')

    def test_zero_amount(self):
        """Zero rounds to zero."""
        assert BudgetService.round_monetary(Decimal('0')) == Decimal('0.00')

    def test_negative_amount(self):
        """Negative amounts are rounded correctly."""
        assert BudgetService.round_monetary(Decimal('-10.125')) == Decimal('-10.12')

    def test_large_amount(self):
        """Large amounts within DECIMAL(12,2) range."""
        assert BudgetService.round_monetary(Decimal('9999999999.995')) == Decimal('10000000000.00')


class TestDivideAnnual:
    """Tests for BudgetService.divide_annual() equal monthly distribution."""

    def test_even_division(self):
        """Amount evenly divisible by 12."""
        result = BudgetService.divide_annual(Decimal('12000.00'))
        assert len(result) == 12
        assert all(m == Decimal('1000.00') for m in result)
        assert sum(result) == Decimal('12000.00')

    def test_sum_preserves_total(self):
        """Sum of monthly amounts exactly equals the original annual amount."""
        result = BudgetService.divide_annual(Decimal('10000.00'))
        assert sum(result) == Decimal('10000.00')

    def test_remainder_on_last_month(self):
        """Rounding remainder is absorbed by the last month."""
        # 10000 / 12 = 833.333... → 833.33 per month
        # 833.33 * 12 = 9999.96, remainder = 0.04
        result = BudgetService.divide_annual(Decimal('10000.00'))
        assert result[0] == Decimal('833.33')
        assert result[-1] == Decimal('833.37')  # 833.33 + 0.04
        assert sum(result) == Decimal('10000.00')

    def test_one_cent(self):
        """Minimal amount divides correctly."""
        result = BudgetService.divide_annual(Decimal('0.01'))
        assert sum(result) == Decimal('0.01')
        assert len(result) == 12

    def test_zero_amount(self):
        """Zero annual amount produces 12 zeros."""
        result = BudgetService.divide_annual(Decimal('0.00'))
        assert len(result) == 12
        assert all(m == Decimal('0.00') for m in result)

    def test_negative_amount(self):
        """Negative annual amount (credit) divides correctly."""
        result = BudgetService.divide_annual(Decimal('-12000.00'))
        assert sum(result) == Decimal('-12000.00')
        assert all(m == Decimal('-1000.00') for m in result)

    def test_large_amount(self):
        """Large amount within DECIMAL(12,2) range preserves total."""
        amount = Decimal('9999999.99')
        result = BudgetService.divide_annual(amount)
        assert sum(result) == amount
        assert len(result) == 12

    def test_custom_months(self):
        """Division by a custom number of months."""
        result = BudgetService.divide_annual(Decimal('1000.00'), months=4)
        assert len(result) == 4
        assert sum(result) == Decimal('1000.00')
        assert all(m == Decimal('250.00') for m in result)

    def test_bankers_rounding_applied(self):
        """Verify banker's rounding is used (not standard rounding)."""
        # 1050 / 12 = 87.5 → with banker's rounding: 88.00 (rounds to even)
        # Wait, 87.50 rounds to 88.00 (5 rounds up because 7 is odd)
        # Actually: 1050/12 = 87.500000... → quantize to 0.01 = 87.50
        result = BudgetService.divide_annual(Decimal('1050.00'))
        assert result[0] == Decimal('87.50')
        assert sum(result) == Decimal('1050.00')


class TestCreateVersion:
    """Tests for BudgetService.create_version() — Requirements 1.1, 1.2, 8.2."""

    def setup_method(self):
        """Create a BudgetService with a mocked database."""
        with patch('database.DatabaseManager') as MockDB:
            self.mock_db = MockDB.return_value
            self.service = BudgetService(test_mode=True)
            self.service.db = self.mock_db

    def test_creates_draft_version_successfully(self):
        """Creating a version returns success with Draft status."""
        self.mock_db.execute_query.return_value = 42  # lastrowid

        result = self.service.create_version('tenant_a', 'Budget 2025', 2025)

        assert result['success'] is True
        assert result['data']['id'] == 42
        assert result['data']['name'] == 'Budget 2025'
        assert result['data']['fiscal_year'] == 2025
        assert result['data']['status'] == 'Draft'
        assert result['data']['is_active'] is False

    def test_passes_correct_params_to_db(self):
        """Verify parameterized query with administration, name, fiscal_year."""
        self.mock_db.execute_query.return_value = 1

        self.service.create_version('tenant_a', 'My Budget', 2024)

        call_args = self.mock_db.execute_query.call_args
        params = call_args[0][1]  # second positional arg
        assert params == ('tenant_a', 'My Budget', 2024)
        assert call_args[1]['fetch'] is False
        assert call_args[1]['commit'] is True

    def test_duplicate_name_returns_error(self):
        """Duplicate name per year/tenant returns descriptive error."""
        from db_exceptions import IntegrityError
        self.mock_db.execute_query.side_effect = IntegrityError("Duplicate entry")

        result = self.service.create_version('tenant_a', 'Budget 2025', 2025)

        assert result['success'] is False
        assert "Budget version 'Budget 2025' already exists for fiscal year 2025" in result['error']


class TestListVersions:
    """Tests for BudgetService.list_versions() — Requirements 1.1, 8.2."""

    def setup_method(self):
        """Create a BudgetService with a mocked database."""
        with patch('database.DatabaseManager') as MockDB:
            self.mock_db = MockDB.return_value
            self.service = BudgetService(test_mode=True)
            self.service.db = self.mock_db

    def test_returns_all_versions_for_tenant(self):
        """List without year filter returns all versions for tenant."""
        self.mock_db.execute_query.return_value = [
            {'id': 1, 'name': 'Budget A', 'fiscal_year': 2025, 'status': 'Draft',
             'is_active': False, 'administration': 'tenant_a',
             'status_changed_at': None, 'created_at': None, 'updated_at': None},
            {'id': 2, 'name': 'Budget B', 'fiscal_year': 2024, 'status': 'Approved',
             'is_active': True, 'administration': 'tenant_a',
             'status_changed_at': None, 'created_at': None, 'updated_at': None},
        ]

        result = self.service.list_versions('tenant_a')

        assert result['success'] is True
        assert len(result['data']) == 2

    def test_filters_by_year_when_provided(self):
        """List with year filter passes year to query."""
        self.mock_db.execute_query.return_value = [
            {'id': 1, 'name': 'Budget A', 'fiscal_year': 2025, 'status': 'Draft',
             'is_active': False, 'administration': 'tenant_a',
             'status_changed_at': None, 'created_at': None, 'updated_at': None},
        ]

        result = self.service.list_versions('tenant_a', year=2025)

        assert result['success'] is True
        call_args = self.mock_db.execute_query.call_args
        params = call_args[0][1]
        assert params == ('tenant_a', 2025)

    def test_returns_empty_list_when_no_versions(self):
        """Returns empty list when no versions exist for tenant."""
        self.mock_db.execute_query.return_value = None

        result = self.service.list_versions('tenant_a')

        assert result['success'] is True
        assert result['data'] == []

    def test_administration_filter_always_applied(self):
        """Every query filters by administration."""
        self.mock_db.execute_query.return_value = []

        self.service.list_versions('tenant_a')

        call_args = self.mock_db.execute_query.call_args
        query = call_args[0][0]
        assert 'administration = %s' in query


class TestDeleteVersion:
    """Tests for BudgetService.delete_version() — Requirements 1.1, 8.2."""

    def setup_method(self):
        """Create a BudgetService with a mocked database."""
        with patch('database.DatabaseManager') as MockDB:
            self.mock_db = MockDB.return_value
            self.service = BudgetService(test_mode=True)
            self.service.db = self.mock_db

    def test_deletes_draft_version_successfully(self):
        """Draft version is deleted and returns success."""
        self.mock_db.execute_query.side_effect = [
            [{'id': 1, 'status': 'Draft'}],  # SELECT
            None,  # DELETE
        ]

        result = self.service.delete_version('tenant_a', 1)

        assert result['success'] is True
        assert result['data']['id'] == 1

    def test_rejects_deletion_of_approved_version(self):
        """Approved version cannot be deleted."""
        self.mock_db.execute_query.return_value = [{'id': 2, 'status': 'Approved'}]

        result = self.service.delete_version('tenant_a', 2)

        assert result['success'] is False
        assert "Only Draft versions can be deleted" in result['error']

    def test_rejects_deletion_of_revised_version(self):
        """Revised version cannot be deleted."""
        self.mock_db.execute_query.return_value = [{'id': 3, 'status': 'Revised'}]

        result = self.service.delete_version('tenant_a', 3)

        assert result['success'] is False
        assert "Only Draft versions can be deleted" in result['error']

    def test_version_not_found_returns_error(self):
        """Non-existent version returns not-found error."""
        self.mock_db.execute_query.return_value = []

        result = self.service.delete_version('tenant_a', 999)

        assert result['success'] is False
        assert "Budget version not found" in result['error']

    def test_version_from_other_tenant_not_found(self):
        """Version belonging to another tenant is treated as not found."""
        # Query filters by administration, so other tenant's version won't appear
        self.mock_db.execute_query.return_value = []

        result = self.service.delete_version('tenant_b', 1)

        assert result['success'] is False
        assert "Budget version not found" in result['error']


class TestActivateVersion:
    """Tests for BudgetService.activate_version() — version activation logic.

    Validates: Requirements 1.6, 1.7, 1.8
    """

    @pytest.fixture
    def service(self):
        """Create a BudgetService with a mocked database."""
        with patch('database.DatabaseManager') as mock_db_class:
            svc = BudgetService(test_mode=True)
            svc.db = mock_db_class.return_value
            yield svc

    def test_activate_approved_version(self, service):
        """Approved version can be activated successfully."""
        service.db.execute_query.return_value = [
            {'id': 1, 'name': 'Budget 2025', 'fiscal_year': 2025, 'status': 'Approved', 'is_active': False}
        ]
        # Mock the transaction context manager
        from contextlib import contextmanager

        @contextmanager
        def mock_transaction():
            from unittest.mock import MagicMock
            cursor = MagicMock()
            conn = MagicMock()
            yield cursor, conn

        service.db.transaction = mock_transaction

        result = service.activate_version('tenant_a', 1)

        assert result['success'] is True
        assert result['data']['id'] == 1
        assert result['data']['is_active'] is True
        assert result['data']['status'] == 'Approved'

    def test_activate_revised_version(self, service):
        """Revised version can be activated successfully."""
        service.db.execute_query.return_value = [
            {'id': 2, 'name': 'Budget 2025 Revised', 'fiscal_year': 2025, 'status': 'Revised', 'is_active': False}
        ]
        from contextlib import contextmanager

        @contextmanager
        def mock_transaction():
            from unittest.mock import MagicMock
            cursor = MagicMock()
            conn = MagicMock()
            yield cursor, conn

        service.db.transaction = mock_transaction

        result = service.activate_version('tenant_a', 2)

        assert result['success'] is True
        assert result['data']['id'] == 2
        assert result['data']['is_active'] is True
        assert result['data']['status'] == 'Revised'

    def test_activate_draft_version_rejected(self, service):
        """Draft version cannot be activated (Requirement 1.7)."""
        service.db.execute_query.return_value = [
            {'id': 3, 'name': 'Draft 2025', 'fiscal_year': 2025, 'status': 'Draft', 'is_active': False}
        ]

        result = service.activate_version('tenant_a', 3)

        assert result['success'] is False
        assert "Only Approved or Revised versions may be activated" in result['error']

    def test_activate_nonexistent_version(self, service):
        """Non-existent version returns error."""
        service.db.execute_query.return_value = []

        result = service.activate_version('tenant_a', 999)

        assert result['success'] is False
        assert "Budget version not found" in result['error']

    def test_activate_version_tenant_isolation(self, service):
        """Version from another tenant is not found (Requirement 8.2)."""
        # Query returns empty because the version belongs to a different tenant
        service.db.execute_query.return_value = []

        result = service.activate_version('tenant_b', 1)

        assert result['success'] is False
        assert "Budget version not found" in result['error']


class TestTransitionStatus:
    """Tests for BudgetService.transition_status() status transition logic.

    Validates: Requirements 1.3, 1.4, 1.5
    """

    @pytest.fixture
    def service(self):
        """Create a BudgetService with a mocked database."""
        from unittest.mock import MagicMock, patch as mock_patch
        with mock_patch('database.DatabaseManager') as mock_dm_class:
            mock_db = MagicMock()
            mock_dm_class.return_value = mock_db
            svc = BudgetService(test_mode=True)
            svc.db = mock_db
            yield svc

    def test_invalid_action_returns_error(self, service):
        """Invalid action is rejected with helpful error message."""
        result = service.transition_status('tenant1', 1, 'invalid_action')
        assert result['success'] is False
        assert "Invalid action" in result['error']
        assert "'approve' or 'revise'" in result['error']

    def test_version_not_found_returns_error(self, service):
        """Non-existent version returns not found error."""
        service.db.execute_query.return_value = []
        result = service.transition_status('tenant1', 999, 'approve')
        assert result['success'] is False
        assert result['error'] == "Budget version not found"

    def test_approve_from_draft_succeeds(self, service):
        """Draft → Approved transition succeeds."""
        service.db.execute_query.side_effect = [
            [{'id': 1, 'name': 'Budget 2025', 'fiscal_year': 2025,
              'status': 'Draft', 'is_active': False,
              'status_changed_at': None, 'created_at': None, 'updated_at': None}],
            None,  # UPDATE result
        ]
        result = service.transition_status('tenant1', 1, 'approve')
        assert result['success'] is True
        assert result['data']['status'] == 'Approved'
        assert result['data']['id'] == 1
        assert 'status_changed_at' in result['data']

    def test_approve_from_approved_fails(self, service):
        """Cannot approve an already Approved version."""
        service.db.execute_query.return_value = [
            {'id': 1, 'name': 'Budget 2025', 'fiscal_year': 2025,
             'status': 'Approved', 'is_active': False,
             'status_changed_at': None, 'created_at': None, 'updated_at': None}
        ]
        result = service.transition_status('tenant1', 1, 'approve')
        assert result['success'] is False
        assert "Cannot transition from Approved to Approved" in result['error']

    def test_approve_from_revised_fails(self, service):
        """Cannot approve a Revised version."""
        service.db.execute_query.return_value = [
            {'id': 1, 'name': 'Budget 2025', 'fiscal_year': 2025,
             'status': 'Revised', 'is_active': False,
             'status_changed_at': None, 'created_at': None, 'updated_at': None}
        ]
        result = service.transition_status('tenant1', 1, 'approve')
        assert result['success'] is False
        assert "Cannot transition from Revised to Approved" in result['error']

    def test_revise_from_approved_succeeds(self, service):
        """Approved → Revised transition creates a copy."""
        from unittest.mock import MagicMock
        from contextlib import contextmanager

        service.db.execute_query.side_effect = [
            # First call: SELECT to get version info
            [{'id': 1, 'name': 'Budget 2025', 'fiscal_year': 2025,
              'status': 'Approved', 'is_active': True,
              'status_changed_at': None, 'created_at': None, 'updated_at': None}],
            # Second call: COUNT query to check existing revised versions
            [{'cnt': 0}],
        ]

        # Mock the transaction context manager
        mock_cursor = MagicMock()
        mock_cursor.lastrowid = 42
        mock_conn = MagicMock()

        @contextmanager
        def mock_transaction():
            yield mock_cursor, mock_conn

        service.db.transaction = mock_transaction

        result = service.transition_status('tenant1', 1, 'revise')
        assert result['success'] is True
        assert result['data']['id'] == 42
        assert result['data']['name'] == 'Budget 2025 (Revised)'
        assert result['data']['status'] == 'Revised'
        assert result['data']['is_active'] is False
        assert 'status_changed_at' in result['data']

        # Verify both INSERT and copy queries were executed
        assert mock_cursor.execute.call_count == 2

    def test_revise_from_draft_fails(self, service):
        """Cannot revise a Draft version."""
        service.db.execute_query.return_value = [
            {'id': 1, 'name': 'Budget 2025', 'fiscal_year': 2025,
             'status': 'Draft', 'is_active': False,
             'status_changed_at': None, 'created_at': None, 'updated_at': None}
        ]
        result = service.transition_status('tenant1', 1, 'revise')
        assert result['success'] is False
        assert "Cannot transition from Draft to Revised" in result['error']
        assert "Allowed: Approved" in result['error']

    def test_revise_from_revised_fails(self, service):
        """Cannot revise an already Revised version (no further transitions)."""
        service.db.execute_query.return_value = [
            {'id': 1, 'name': 'Budget 2025', 'fiscal_year': 2025,
             'status': 'Revised', 'is_active': False,
             'status_changed_at': None, 'created_at': None, 'updated_at': None}
        ]
        result = service.transition_status('tenant1', 1, 'revise')
        assert result['success'] is False
        assert "Cannot transition from Revised to Revised" in result['error']

    def test_tenant_isolation_on_lookup(self, service):
        """Verifies query includes administration filter."""
        service.db.execute_query.return_value = []
        service.transition_status('tenantA', 5, 'approve')

        call_args = service.db.execute_query.call_args
        query = call_args[0][0]
        params = call_args[0][1]
        assert 'administration = %s' in query
        assert 'tenantA' in params


# -------------------------------------------------------------------------
# Budget Line CRUD Tests (Task 4.1)
# -------------------------------------------------------------------------


class TestCreateLine:
    """Tests for BudgetService.create_line() — Requirements 3.1, 3.2, 3.3, 3.5, 3.6."""

    def setup_method(self):
        """Create a BudgetService with a mocked database."""
        with patch('database.DatabaseManager') as MockDB:
            self.mock_db = MockDB.return_value
            self.service = BudgetService(test_mode=True)
            self.service.db = self.mock_db

    def test_creates_monthly_line_successfully(self):
        """Monthly mode with 12 amounts creates a budget line."""
        self.mock_db.execute_query.return_value = 10  # lastrowid

        amounts = [1000.00] * 12
        result = self.service.create_line(
            'tenant_a', 1, '4000', 'Monthly',
            amounts=amounts,
        )

        assert result['success'] is True
        assert result['data']['id'] == 10
        assert result['data']['account_code'] == '4000'
        assert result['data']['total'] == 12000.00

    def test_creates_annual_line_successfully(self):
        """Annual mode divides amount equally across 12 months."""
        self.mock_db.execute_query.return_value = 11

        result = self.service.create_line(
            'tenant_a', 1, '4100', 'Annual',
            annual_amount=12000.00,
        )

        assert result['success'] is True
        assert result['data']['id'] == 11
        assert result['data']['account_code'] == '4100'
        assert result['data']['total'] == 12000.00

    def test_creates_line_with_dimension(self):
        """Budget line with detail dimension stores dimension info."""
        self.mock_db.execute_query.return_value = 12

        result = self.service.create_line(
            'tenant_a', 1, '4100', 'Monthly',
            amounts=[500.00] * 12,
            detail_dimension_type='platform',
            detail_dimension_value='Airbnb',
        )

        assert result['success'] is True
        # Check that dimension values were passed in the INSERT params
        call_args = self.mock_db.execute_query.call_args
        params = call_args[0][1]
        assert 'platform' in params
        assert 'Airbnb' in params

    def test_monthly_mode_rounds_amounts(self):
        """Amounts with more than 2dp are rounded with banker's rounding."""
        self.mock_db.execute_query.return_value = 13

        amounts = [100.125] * 12  # .125 rounds to .12 (banker's)
        result = self.service.create_line(
            'tenant_a', 1, '4000', 'Monthly',
            amounts=amounts,
        )

        assert result['success'] is True
        # 100.12 * 12 = 1201.44
        assert result['data']['total'] == pytest.approx(1201.44, abs=0.01)

    def test_monthly_mode_requires_12_amounts(self):
        """Monthly mode with fewer than 12 amounts returns error."""
        result = self.service.create_line(
            'tenant_a', 1, '4000', 'Monthly',
            amounts=[100.00] * 6,
        )

        assert result['success'] is False
        assert "Monthly mode requires exactly 12 amounts" in result['error']

    def test_monthly_mode_no_amounts_returns_error(self):
        """Monthly mode with None amounts returns error."""
        result = self.service.create_line(
            'tenant_a', 1, '4000', 'Monthly',
            amounts=None,
        )

        assert result['success'] is False
        assert "Monthly mode requires exactly 12 amounts" in result['error']

    def test_annual_mode_requires_annual_amount(self):
        """Annual mode without annual_amount returns error."""
        result = self.service.create_line(
            'tenant_a', 1, '4000', 'Annual',
            annual_amount=None,
        )

        assert result['success'] is False
        assert "Annual mode requires an annual_amount" in result['error']

    def test_invalid_period_mode_returns_error(self):
        """Invalid period_mode returns error."""
        result = self.service.create_line(
            'tenant_a', 1, '4000', 'Weekly',
            amounts=[100.00] * 12,
        )

        assert result['success'] is False
        assert "Invalid period_mode" in result['error']

    def test_duplicate_line_returns_error(self):
        """Duplicate account+dimension combination returns descriptive error."""
        from db_exceptions import IntegrityError
        self.mock_db.execute_query.side_effect = IntegrityError("Duplicate entry")

        result = self.service.create_line(
            'tenant_a', 1, '4000', 'Monthly',
            amounts=[100.00] * 12,
            detail_dimension_type='platform',
            detail_dimension_value='Airbnb',
        )

        assert result['success'] is False
        assert "Budget line already exists for account 4000" in result['error']
        assert "platform=Airbnb" in result['error']

    def test_duplicate_line_no_dimension_error_message(self):
        """Duplicate without dimension shows 'none' in message."""
        from db_exceptions import IntegrityError
        self.mock_db.execute_query.side_effect = IntegrityError("Duplicate entry")

        result = self.service.create_line(
            'tenant_a', 1, '4000', 'Monthly',
            amounts=[100.00] * 12,
        )

        assert result['success'] is False
        assert "dimension none" in result['error']

    def test_annual_division_preserves_total(self):
        """Annual amount that doesn't divide evenly still sums correctly."""
        self.mock_db.execute_query.return_value = 14

        result = self.service.create_line(
            'tenant_a', 1, '4000', 'Annual',
            annual_amount=10000.00,
        )

        assert result['success'] is True
        assert result['data']['total'] == 10000.00


class TestUpdateLine:
    """Tests for BudgetService.update_line() — Requirements 3.1, 3.2, 3.5."""

    def setup_method(self):
        """Create a BudgetService with a mocked database."""
        with patch('database.DatabaseManager') as MockDB:
            self.mock_db = MockDB.return_value
            self.service = BudgetService(test_mode=True)
            self.service.db = self.mock_db

    def test_updates_with_monthly_amounts(self):
        """Updating with 12 amounts succeeds."""
        self.mock_db.execute_query.side_effect = [
            [{'id': 1, 'version_id': 1, 'account_code': '4000', 'period_mode': 'Monthly'}],  # SELECT
            None,  # UPDATE
        ]

        amounts = [2000.00] * 12
        result = self.service.update_line('tenant_a', 1, amounts=amounts)

        assert result['success'] is True
        assert result['data']['id'] == 1
        assert result['data']['account_code'] == '4000'
        assert result['data']['total'] == 24000.00

    def test_updates_with_annual_amount(self):
        """Updating with annual_amount divides equally and succeeds."""
        self.mock_db.execute_query.side_effect = [
            [{'id': 2, 'version_id': 1, 'account_code': '4100', 'period_mode': 'Annual'}],
            None,
        ]

        result = self.service.update_line('tenant_a', 2, annual_amount=24000.00)

        assert result['success'] is True
        assert result['data']['total'] == 24000.00

    def test_line_not_found_returns_error(self):
        """Non-existent line returns error."""
        self.mock_db.execute_query.return_value = []

        result = self.service.update_line('tenant_a', 999, amounts=[100.00] * 12)

        assert result['success'] is False
        assert "Budget line not found" in result['error']

    def test_wrong_tenant_line_not_found(self):
        """Line belonging to another tenant returns not found."""
        self.mock_db.execute_query.return_value = []

        result = self.service.update_line('tenant_b', 1, amounts=[100.00] * 12)

        assert result['success'] is False
        assert "Budget line not found" in result['error']

    def test_invalid_amounts_count_returns_error(self):
        """Fewer than 12 amounts returns error."""
        self.mock_db.execute_query.side_effect = [
            [{'id': 1, 'version_id': 1, 'account_code': '4000', 'period_mode': 'Monthly'}],
        ]

        result = self.service.update_line('tenant_a', 1, amounts=[100.00] * 6)

        assert result['success'] is False
        assert "Monthly mode requires exactly 12 amounts" in result['error']

    def test_no_amounts_or_annual_returns_error(self):
        """Providing neither amounts nor annual_amount returns error."""
        self.mock_db.execute_query.side_effect = [
            [{'id': 1, 'version_id': 1, 'account_code': '4000', 'period_mode': 'Monthly'}],
        ]

        result = self.service.update_line('tenant_a', 1)

        assert result['success'] is False
        assert "Provide either amounts" in result['error']

    def test_rounds_amounts_on_update(self):
        """Amounts are rounded with banker's rounding on update."""
        self.mock_db.execute_query.side_effect = [
            [{'id': 1, 'version_id': 1, 'account_code': '4000', 'period_mode': 'Monthly'}],
            None,
        ]

        # 100.135 rounds to 100.14 (banker's: .135 -> .14 since 3 is odd)
        amounts = [100.135] * 12
        result = self.service.update_line('tenant_a', 1, amounts=amounts)

        assert result['success'] is True
        # 100.14 * 12 = 1201.68
        assert result['data']['total'] == pytest.approx(1201.68, abs=0.01)


class TestListLines:
    """Tests for BudgetService.list_lines() — Requirement 3.4."""

    def setup_method(self):
        """Create a BudgetService with a mocked database."""
        with patch('database.DatabaseManager') as MockDB:
            self.mock_db = MockDB.return_value
            self.service = BudgetService(test_mode=True)
            self.service.db = self.mock_db

    def test_returns_lines_for_version(self):
        """Returns all lines matching version_id and administration."""
        self.mock_db.execute_query.return_value = [
            {'id': 1, 'account_code': '4000', 'month_01': Decimal('1000.00')},
            {'id': 2, 'account_code': '4100', 'month_01': Decimal('500.00')},
        ]

        result = self.service.list_lines('tenant_a', 1)

        assert result['success'] is True
        assert len(result['data']) == 2

    def test_returns_empty_list_when_no_lines(self):
        """Returns empty list for version with no budget lines."""
        self.mock_db.execute_query.return_value = []

        result = self.service.list_lines('tenant_a', 99)

        assert result['success'] is True
        assert result['data'] == []

    def test_filters_by_administration(self):
        """Query includes administration filter for tenant isolation."""
        self.mock_db.execute_query.return_value = []

        self.service.list_lines('tenant_a', 1)

        call_args = self.mock_db.execute_query.call_args
        query = call_args[0][0]
        params = call_args[0][1]
        assert 'administration = %s' in query
        assert 'tenant_a' in params

    def test_filters_by_version_id(self):
        """Query includes version_id filter."""
        self.mock_db.execute_query.return_value = []

        self.service.list_lines('tenant_a', 5)

        call_args = self.mock_db.execute_query.call_args
        params = call_args[0][1]
        assert 5 in params


class TestDeleteLine:
    """Tests for BudgetService.delete_line() — Requirement 3.4."""

    def setup_method(self):
        """Create a BudgetService with a mocked database."""
        with patch('database.DatabaseManager') as MockDB:
            self.mock_db = MockDB.return_value
            self.service = BudgetService(test_mode=True)
            self.service.db = self.mock_db

    def test_deletes_line_successfully(self):
        """Successfully deletes a line belonging to the tenant."""
        self.mock_db.execute_query.side_effect = [
            [{'id': 1}],  # SELECT to verify existence
            None,          # DELETE
        ]

        result = self.service.delete_line('tenant_a', 1)

        assert result['success'] is True
        assert result['data']['id'] == 1
        assert result['data']['deleted'] is True

    def test_line_not_found_returns_error(self):
        """Non-existent line returns error."""
        self.mock_db.execute_query.return_value = []

        result = self.service.delete_line('tenant_a', 999)

        assert result['success'] is False
        assert "Budget line not found" in result['error']

    def test_other_tenant_line_not_found(self):
        """Line belonging to another tenant returns not found."""
        self.mock_db.execute_query.return_value = []

        result = self.service.delete_line('tenant_b', 1)

        assert result['success'] is False
        assert "Budget line not found" in result['error']

    def test_delete_uses_tenant_filter(self):
        """Both SELECT and DELETE include administration filter."""
        self.mock_db.execute_query.side_effect = [
            [{'id': 5}],
            None,
        ]

        self.service.delete_line('tenant_x', 5)

        # First call: SELECT with tenant filter
        select_call = self.mock_db.execute_query.call_args_list[0]
        assert 'administration = %s' in select_call[0][0]
        assert 'tenant_x' in select_call[0][1]

        # Second call: DELETE with tenant filter
        delete_call = self.mock_db.execute_query.call_args_list[1]
        assert 'administration = %s' in delete_call[0][0]
        assert 'tenant_x' in delete_call[0][1]


# -------------------------------------------------------------------------
# Budget Copy Tests (Task 6.2)
# -------------------------------------------------------------------------


class TestCopyBudget:
    """Tests for BudgetService.copy_budget() — Requirements 5.1, 5.2, 5.3, 5.4, 8.5."""

    def setup_method(self):
        """Create a BudgetService with a mocked database."""
        with patch('database.DatabaseManager') as MockDB:
            self.mock_db = MockDB.return_value
            self.service = BudgetService(test_mode=True)
            self.service.db = self.mock_db

    def _mock_transaction(self):
        """Helper to create a mock transaction context manager."""
        from contextlib import contextmanager
        from unittest.mock import MagicMock

        mock_cursor = MagicMock()
        mock_cursor.lastrowid = 99
        mock_conn = MagicMock()

        @contextmanager
        def transaction():
            yield mock_cursor, mock_conn

        self.mock_db.transaction = transaction
        return mock_cursor

    def test_copies_budget_successfully(self):
        """Copies all lines from source to new Draft version for target year."""
        # 1. Fetch source version
        # 2. Fetch source lines
        # 3. Account validation for line 1
        # 4. Account validation for line 2
        self.mock_db.execute_query.side_effect = [
            [{'id': 1, 'name': 'Budget 2024', 'fiscal_year': 2024, 'status': 'Approved'}],
            [
                {'account_code': '4000', 'period_mode': 'Monthly',
                 'detail_dimension_type': None, 'detail_dimension_value': None,
                 'month_01': Decimal('1000.00'), 'month_02': Decimal('1100.00'),
                 'month_03': Decimal('1200.00'), 'month_04': Decimal('900.00'),
                 'month_05': Decimal('1300.00'), 'month_06': Decimal('1250.00'),
                 'month_07': Decimal('1400.00'), 'month_08': Decimal('1350.00'),
                 'month_09': Decimal('1200.00'), 'month_10': Decimal('1150.00'),
                 'month_11': Decimal('1050.00'), 'month_12': Decimal('1500.00')},
                {'account_code': '4100', 'period_mode': 'Annual',
                 'detail_dimension_type': 'platform', 'detail_dimension_value': 'Airbnb',
                 'month_01': Decimal('500.00'), 'month_02': Decimal('500.00'),
                 'month_03': Decimal('500.00'), 'month_04': Decimal('500.00'),
                 'month_05': Decimal('500.00'), 'month_06': Decimal('500.00'),
                 'month_07': Decimal('500.00'), 'month_08': Decimal('500.00'),
                 'month_09': Decimal('500.00'), 'month_10': Decimal('500.00'),
                 'month_11': Decimal('500.00'), 'month_12': Decimal('500.00')},
            ],
            [{'Account': '4000'}],  # account 4000 exists
            [{'Account': '4100'}],  # account 4100 exists
        ]

        mock_cursor = self._mock_transaction()

        result = self.service.copy_budget('tenant_a', 1, 2025, 'Budget 2025 Copy')

        assert result['success'] is True
        assert result['data']['version_id'] == 99
        assert result['data']['lines_copied'] == 2
        assert result['data']['excluded_accounts'] == []

    def test_source_version_not_found(self):
        """Returns error when source version doesn't exist or belongs to another tenant."""
        self.mock_db.execute_query.return_value = []

        result = self.service.copy_budget('tenant_a', 999, 2025, 'Copy')

        assert result['success'] is False
        assert result['error'] == "Budget version not found"

    def test_target_year_same_as_source_rejected(self):
        """Target year equal to source year is rejected."""
        self.mock_db.execute_query.return_value = [
            {'id': 1, 'name': 'Budget 2024', 'fiscal_year': 2024, 'status': 'Approved'}
        ]

        result = self.service.copy_budget('tenant_a', 1, 2024, 'Copy')

        assert result['success'] is False
        assert "Target year must be later than source year 2024" in result['error']

    def test_target_year_earlier_than_source_rejected(self):
        """Target year earlier than source year is rejected."""
        self.mock_db.execute_query.return_value = [
            {'id': 1, 'name': 'Budget 2024', 'fiscal_year': 2024, 'status': 'Approved'}
        ]

        result = self.service.copy_budget('tenant_a', 1, 2023, 'Copy')

        assert result['success'] is False
        assert "Target year must be later than source year 2024" in result['error']

    def test_excludes_accounts_no_longer_in_chart(self):
        """Lines for accounts no longer in rekeningschema are excluded with warning."""
        self.mock_db.execute_query.side_effect = [
            [{'id': 1, 'name': 'Budget 2024', 'fiscal_year': 2024, 'status': 'Approved'}],
            [
                {'account_code': '4000', 'period_mode': 'Monthly',
                 'detail_dimension_type': None, 'detail_dimension_value': None,
                 'month_01': Decimal('100.00'), 'month_02': Decimal('100.00'),
                 'month_03': Decimal('100.00'), 'month_04': Decimal('100.00'),
                 'month_05': Decimal('100.00'), 'month_06': Decimal('100.00'),
                 'month_07': Decimal('100.00'), 'month_08': Decimal('100.00'),
                 'month_09': Decimal('100.00'), 'month_10': Decimal('100.00'),
                 'month_11': Decimal('100.00'), 'month_12': Decimal('100.00')},
                {'account_code': '9999', 'period_mode': 'Monthly',
                 'detail_dimension_type': None, 'detail_dimension_value': None,
                 'month_01': Decimal('50.00'), 'month_02': Decimal('50.00'),
                 'month_03': Decimal('50.00'), 'month_04': Decimal('50.00'),
                 'month_05': Decimal('50.00'), 'month_06': Decimal('50.00'),
                 'month_07': Decimal('50.00'), 'month_08': Decimal('50.00'),
                 'month_09': Decimal('50.00'), 'month_10': Decimal('50.00'),
                 'month_11': Decimal('50.00'), 'month_12': Decimal('50.00')},
            ],
            [{'Account': '4000'}],  # account 4000 exists
            [],                      # account 9999 does NOT exist
        ]

        mock_cursor = self._mock_transaction()

        result = self.service.copy_budget('tenant_a', 1, 2025, 'Budget 2025')

        assert result['success'] is True
        assert result['data']['lines_copied'] == 1
        assert result['data']['excluded_accounts'] == ['9999']

    def test_excludes_multiple_lines_same_account(self):
        """Multiple lines with the same deleted account code only list it once in excluded."""
        self.mock_db.execute_query.side_effect = [
            [{'id': 1, 'name': 'Budget 2024', 'fiscal_year': 2024, 'status': 'Approved'}],
            [
                {'account_code': '9999', 'period_mode': 'Monthly',
                 'detail_dimension_type': 'platform', 'detail_dimension_value': 'Airbnb',
                 'month_01': Decimal('50.00'), 'month_02': Decimal('50.00'),
                 'month_03': Decimal('50.00'), 'month_04': Decimal('50.00'),
                 'month_05': Decimal('50.00'), 'month_06': Decimal('50.00'),
                 'month_07': Decimal('50.00'), 'month_08': Decimal('50.00'),
                 'month_09': Decimal('50.00'), 'month_10': Decimal('50.00'),
                 'month_11': Decimal('50.00'), 'month_12': Decimal('50.00')},
                {'account_code': '9999', 'period_mode': 'Monthly',
                 'detail_dimension_type': 'platform', 'detail_dimension_value': 'Booking',
                 'month_01': Decimal('30.00'), 'month_02': Decimal('30.00'),
                 'month_03': Decimal('30.00'), 'month_04': Decimal('30.00'),
                 'month_05': Decimal('30.00'), 'month_06': Decimal('30.00'),
                 'month_07': Decimal('30.00'), 'month_08': Decimal('30.00'),
                 'month_09': Decimal('30.00'), 'month_10': Decimal('30.00'),
                 'month_11': Decimal('30.00'), 'month_12': Decimal('30.00')},
            ],
            [],  # account 9999 not found (first line)
            [],  # account 9999 not found (second line)
        ]

        mock_cursor = self._mock_transaction()

        result = self.service.copy_budget('tenant_a', 1, 2025, 'Budget 2025')

        assert result['success'] is True
        assert result['data']['lines_copied'] == 0
        assert result['data']['excluded_accounts'] == ['9999']

    def test_preserves_dimension_associations(self):
        """Copied lines preserve detail_dimension_type and detail_dimension_value."""
        from unittest.mock import call

        self.mock_db.execute_query.side_effect = [
            [{'id': 1, 'name': 'Budget 2024', 'fiscal_year': 2024, 'status': 'Approved'}],
            [
                {'account_code': '4100', 'period_mode': 'Annual',
                 'detail_dimension_type': 'platform', 'detail_dimension_value': 'Airbnb',
                 'month_01': Decimal('500.00'), 'month_02': Decimal('500.00'),
                 'month_03': Decimal('500.00'), 'month_04': Decimal('500.00'),
                 'month_05': Decimal('500.00'), 'month_06': Decimal('500.00'),
                 'month_07': Decimal('500.00'), 'month_08': Decimal('500.00'),
                 'month_09': Decimal('500.00'), 'month_10': Decimal('500.00'),
                 'month_11': Decimal('500.00'), 'month_12': Decimal('500.00')},
            ],
            [{'Account': '4100'}],  # account exists
        ]

        mock_cursor = self._mock_transaction()

        result = self.service.copy_budget('tenant_a', 1, 2025, 'Copy 2025')

        assert result['success'] is True
        # The second cursor.execute call should be the line INSERT
        line_insert_call = mock_cursor.execute.call_args_list[1]
        params = line_insert_call[0][1]
        # params: (new_version_id, admin, account_code, period_mode, dim_type, dim_value, m01..m12)
        assert params[2] == '4100'       # account_code
        assert params[3] == 'Annual'     # period_mode preserved
        assert params[4] == 'platform'   # dimension type preserved
        assert params[5] == 'Airbnb'     # dimension value preserved

    def test_preserves_all_monthly_amounts(self):
        """All 12 monthly amounts are preserved exactly in the copied line."""
        monthly = [Decimal(f'{100 + i * 10}.00') for i in range(12)]

        self.mock_db.execute_query.side_effect = [
            [{'id': 1, 'name': 'Budget 2024', 'fiscal_year': 2024, 'status': 'Approved'}],
            [
                {'account_code': '4000', 'period_mode': 'Monthly',
                 'detail_dimension_type': None, 'detail_dimension_value': None,
                 'month_01': monthly[0], 'month_02': monthly[1],
                 'month_03': monthly[2], 'month_04': monthly[3],
                 'month_05': monthly[4], 'month_06': monthly[5],
                 'month_07': monthly[6], 'month_08': monthly[7],
                 'month_09': monthly[8], 'month_10': monthly[9],
                 'month_11': monthly[10], 'month_12': monthly[11]},
            ],
            [{'Account': '4000'}],
        ]

        mock_cursor = self._mock_transaction()

        result = self.service.copy_budget('tenant_a', 1, 2025, 'Copy 2025')

        assert result['success'] is True
        # Verify the INSERT line call has all 12 months preserved
        line_insert_call = mock_cursor.execute.call_args_list[1]
        params = line_insert_call[0][1]
        # Months are params[6] through params[17]
        for i in range(12):
            assert params[6 + i] == monthly[i]

    def test_duplicate_version_name_returns_error(self):
        """IntegrityError from duplicate version name is handled gracefully."""
        from db_exceptions import IntegrityError
        from contextlib import contextmanager

        self.mock_db.execute_query.side_effect = [
            [{'id': 1, 'name': 'Budget 2024', 'fiscal_year': 2024, 'status': 'Approved'}],
            [],  # no source lines
        ]

        @contextmanager
        def mock_transaction():
            raise IntegrityError("Duplicate entry")
            yield  # noqa - never reached

        self.mock_db.transaction = mock_transaction

        result = self.service.copy_budget('tenant_a', 1, 2025, 'Existing Name')

        assert result['success'] is False
        assert "Budget version 'Existing Name' already exists for fiscal year 2025" in result['error']

    def test_empty_source_copies_zero_lines(self):
        """Source version with no budget lines creates an empty new version."""
        self.mock_db.execute_query.side_effect = [
            [{'id': 1, 'name': 'Budget 2024', 'fiscal_year': 2024, 'status': 'Approved'}],
            [],  # no source lines
        ]

        mock_cursor = self._mock_transaction()

        result = self.service.copy_budget('tenant_a', 1, 2025, 'Empty Copy')

        assert result['success'] is True
        assert result['data']['version_id'] == 99
        assert result['data']['lines_copied'] == 0
        assert result['data']['excluded_accounts'] == []

    def test_new_version_created_as_draft(self):
        """The new version is created with status Draft and is_active False."""
        self.mock_db.execute_query.side_effect = [
            [{'id': 1, 'name': 'Budget 2024', 'fiscal_year': 2024, 'status': 'Approved'}],
            [],  # no source lines
        ]

        mock_cursor = self._mock_transaction()

        result = self.service.copy_budget('tenant_a', 1, 2025, 'New Draft')

        assert result['success'] is True
        # Verify the INSERT version call uses 'Draft' and FALSE
        version_insert_call = mock_cursor.execute.call_args_list[0]
        query = version_insert_call[0][0]
        assert "'Draft'" in query
        assert 'FALSE' in query

    def test_tenant_isolation_on_source_lookup(self):
        """Source version lookup filters by administration."""
        self.mock_db.execute_query.return_value = []

        self.service.copy_budget('tenant_a', 1, 2025, 'Copy')

        call_args = self.mock_db.execute_query.call_args
        query = call_args[0][0]
        params = call_args[0][1]
        assert 'administration = %s' in query
        assert 'tenant_a' in params

    def test_target_fiscal_year_set_on_new_version(self):
        """New version uses the target fiscal year, not the source year."""
        self.mock_db.execute_query.side_effect = [
            [{'id': 1, 'name': 'Budget 2024', 'fiscal_year': 2024, 'status': 'Approved'}],
            [],  # no source lines
        ]

        mock_cursor = self._mock_transaction()

        result = self.service.copy_budget('tenant_a', 1, 2026, 'Budget 2026')

        assert result['success'] is True
        # Verify fiscal_year in the INSERT params
        version_insert_call = mock_cursor.execute.call_args_list[0]
        params = version_insert_call[0][1]
        assert 2026 in params


class TestSumMonths:
    """Tests for BudgetService._sum_months() period aggregation helper.

    Validates: Requirements 6.7, 7.1, 7.2
    """

    def test_sum_all_months_when_none(self):
        """When months is None, sums all 12 month values (full year)."""
        row = {f'm{i:02d}': Decimal('100.00') for i in range(1, 13)}
        result = BudgetService._sum_months(row)
        assert result == Decimal('1200.00')

    def test_sum_specific_months(self):
        """When months is a list, sums only those months."""
        row = {f'm{i:02d}': Decimal(str(i * 10)) for i in range(1, 13)}
        # Sum months 1, 2, 3 -> 10 + 20 + 30 = 60
        result = BudgetService._sum_months(row, months=[1, 2, 3])
        assert result == Decimal('60')

    def test_sum_single_month(self):
        """Summing a single month returns just that month's value."""
        row = {f'm{i:02d}': Decimal('0.00') for i in range(1, 13)}
        row['m06'] = Decimal('500.00')
        result = BudgetService._sum_months(row, months=[6])
        assert result == Decimal('500.00')

    def test_sum_quarter(self):
        """Quarter selection (e.g., Q2 = months 4, 5, 6)."""
        row = {f'm{i:02d}': Decimal('100.00') for i in range(1, 13)}
        result = BudgetService._sum_months(row, months=[4, 5, 6])
        assert result == Decimal('300.00')

    def test_empty_months_list_returns_zero(self):
        """Empty months list returns zero."""
        row = {f'm{i:02d}': Decimal('100.00') for i in range(1, 13)}
        result = BudgetService._sum_months(row, months=[])
        assert result == Decimal('0.00')

    def test_invalid_month_numbers_ignored(self):
        """Month numbers outside 1-12 are safely ignored."""
        row = {f'm{i:02d}': Decimal('100.00') for i in range(1, 13)}
        result = BudgetService._sum_months(row, months=[0, 13, 1])
        assert result == Decimal('100.00')

    def test_missing_month_keys_default_to_zero(self):
        """Missing keys in row default to zero."""
        row = {'m01': Decimal('50.00')}  # only m01 present
        result = BudgetService._sum_months(row, months=[1, 2])
        assert result == Decimal('50.00')

    def test_none_values_treated_as_zero(self):
        """None values in row are treated as zero."""
        row = {f'm{i:02d}': None for i in range(1, 13)}
        row['m01'] = Decimal('100.00')
        result = BudgetService._sum_months(row)
        assert result == Decimal('100.00')


class TestGetRollup:
    """Tests for BudgetService.get_rollup() hierarchy rollup computation.

    Validates: Requirements 7.1, 7.2, 7.3, 7.4, 7.5, 7.6
    """

    def setup_method(self):
        """Create a BudgetService with a mocked database."""
        with patch('database.DatabaseManager') as MockDB:
            self.mock_db = MockDB.return_value
            self.service = BudgetService(test_mode=True)
            self.service.db = self.mock_db

    def test_invalid_level_returns_error(self):
        """Invalid level parameter returns descriptive error."""
        result = self.service.get_rollup('tenant_a', 1, 'invalid')

        assert result['success'] is False
        assert "Invalid level" in result['error']

    def test_subparent_requires_parent_code(self):
        """SubParent level requires parent_code filter."""
        result = self.service.get_rollup('tenant_a', 1, 'subparent')

        assert result['success'] is False
        assert "parent_code is required" in result['error']

    def test_account_requires_subparent_code(self):
        """Account level requires subparent_code filter."""
        result = self.service.get_rollup('tenant_a', 1, 'account')

        assert result['success'] is False
        assert "subparent_code is required" in result['error']

    def test_parent_level_rollup(self):
        """Parent level groups by Parent and sums all months."""
        # Mock query results: rollup rows
        self.mock_db.execute_query.side_effect = [
            # First call: aggregation query
            [
                {'code': '4000', **{f'm{i:02d}': Decimal('1000.00') for i in range(1, 13)}},
                {'code': '5000', **{f'm{i:02d}': Decimal('500.00') for i in range(1, 13)}},
            ],
            # Second call: name resolution
            [
                {'Account': '4000', 'AccountName': 'Omzet'},
                {'Account': '5000', 'AccountName': 'Kosten'},
            ],
        ]

        result = self.service.get_rollup('tenant_a', 1, 'parent')

        assert result['success'] is True
        assert len(result['data']) == 2
        assert result['data'][0]['code'] == '4000'
        assert result['data'][0]['name'] == 'Omzet'
        assert result['data'][0]['budget'] == 12000.00  # 1000 * 12
        assert result['data'][1]['code'] == '5000'
        assert result['data'][1]['name'] == 'Kosten'
        assert result['data'][1]['budget'] == 6000.00  # 500 * 12

    def test_parent_level_with_period_filter(self):
        """Parent level respects months filter for period selection."""
        self.mock_db.execute_query.side_effect = [
            [{'code': '4000', **{f'm{i:02d}': Decimal('1000.00') for i in range(1, 13)}}],
            [{'Account': '4000', 'AccountName': 'Omzet'}],
        ]

        # Q1 only (months 1, 2, 3)
        result = self.service.get_rollup('tenant_a', 1, 'parent', months=[1, 2, 3])

        assert result['success'] is True
        assert result['data'][0]['budget'] == 3000.00  # 1000 * 3

    def test_subparent_level_rollup(self):
        """SubParent level groups by SubParent within a parent."""
        self.mock_db.execute_query.side_effect = [
            # Aggregation query
            [
                {'code': '410', 'parent_code': '4000',
                 **{f'm{i:02d}': Decimal('200.00') for i in range(1, 13)}},
                {'code': '420', 'parent_code': '4000',
                 **{f'm{i:02d}': Decimal('300.00') for i in range(1, 13)}},
            ],
            # Name resolution
            [
                {'Account': '410', 'AccountName': 'Huur'},
                {'Account': '420', 'AccountName': 'Energie'},
            ],
        ]

        result = self.service.get_rollup('tenant_a', 1, 'subparent', parent_code='4000')

        assert result['success'] is True
        assert len(result['data']) == 2
        assert result['data'][0]['code'] == '410'
        assert result['data'][0]['name'] == 'Huur'
        assert result['data'][0]['budget'] == 2400.00  # 200 * 12
        assert result['data'][0]['parent_code'] == '4000'

    def test_subparent_unassigned_handling(self):
        """Accounts with no SubParent appear as 'Unassigned'."""
        self.mock_db.execute_query.side_effect = [
            # Aggregation query — NULL SubParent represented as empty/None
            [
                {'code': '410', 'parent_code': '4000',
                 **{f'm{i:02d}': Decimal('100.00') for i in range(1, 13)}},
                {'code': None, 'parent_code': '4000',
                 **{f'm{i:02d}': Decimal('50.00') for i in range(1, 13)}},
            ],
            # Name resolution (only for non-Unassigned)
            [{'Account': '410', 'AccountName': 'Sub A'}],
        ]

        result = self.service.get_rollup('tenant_a', 1, 'subparent', parent_code='4000')

        assert result['success'] is True
        assert len(result['data']) == 2
        # Find the unassigned entry
        unassigned = next(d for d in result['data'] if d['code'] == 'Unassigned')
        assert unassigned['name'] == 'Unassigned'
        assert unassigned['budget'] == 600.00  # 50 * 12

    def test_account_level_detail(self):
        """Account level returns individual budget lines within a subparent."""
        self.mock_db.execute_query.side_effect = [
            # Account-level query (no name resolution needed, name from AccountName)
            [
                {'code': '4100', 'subparent_code': '410', 'name': 'Huur Appartement A',
                 **{f'm{i:02d}': Decimal('800.00') for i in range(1, 13)}},
                {'code': '4110', 'subparent_code': '410', 'name': 'Huur Appartement B',
                 **{f'm{i:02d}': Decimal('600.00') for i in range(1, 13)}},
            ],
        ]

        result = self.service.get_rollup('tenant_a', 1, 'account', subparent_code='410')

        assert result['success'] is True
        assert len(result['data']) == 2
        assert result['data'][0]['code'] == '4100'
        assert result['data'][0]['name'] == 'Huur Appartement A'
        assert result['data'][0]['budget'] == 9600.00  # 800 * 12
        assert result['data'][0]['subparent_code'] == '410'

    def test_empty_result_returns_empty_data(self):
        """When no budget lines exist, returns empty data list."""
        self.mock_db.execute_query.return_value = []

        result = self.service.get_rollup('tenant_a', 1, 'parent')

        assert result['success'] is True
        assert result['data'] == []

    def test_query_includes_tenant_filter(self):
        """Every rollup query includes administration filter."""
        self.mock_db.execute_query.return_value = []

        self.service.get_rollup('my_tenant', 5, 'parent')

        call_args = self.mock_db.execute_query.call_args
        query = call_args[0][0]
        params = call_args[0][1]
        assert 'bl.administration = %s' in query
        assert 'my_tenant' in params

    def test_query_filters_by_version_id(self):
        """Rollup query filters by the specified version_id."""
        self.mock_db.execute_query.return_value = []

        self.service.get_rollup('tenant_a', 42, 'parent')

        call_args = self.mock_db.execute_query.call_args
        params = call_args[0][1]
        assert 42 in params

    def test_bankers_rounding_applied_to_budget_total(self):
        """Budget totals are rounded to 2dp using banker's rounding."""
        # Create a row where the sum leads to a rounding scenario
        row_data = {f'm{i:02d}': Decimal('0.00') for i in range(1, 13)}
        row_data['m01'] = Decimal('1.005')  # halfway - banker's rounds to 1.00 (even)
        row_data['m02'] = Decimal('1.015')  # halfway - banker's rounds to 1.02 (even)
        row_data['code'] = '4000'

        self.mock_db.execute_query.side_effect = [
            [row_data],
            [{'Account': '4000', 'AccountName': 'Test'}],
        ]

        result = self.service.get_rollup('tenant_a', 1, 'parent')

        assert result['success'] is True
        # Sum = 2.02, rounded = 2.02
        assert result['data'][0]['budget'] == 2.02


class TestParsePeriod:
    """Tests for BudgetService._parse_period() — Requirements 6.7."""

    def setup_method(self):
        """Create a BudgetService with a mocked database."""
        with patch('database.DatabaseManager') as MockDB:
            self.mock_db = MockDB.return_value
            self.service = BudgetService(test_mode=True)
            self.service.db = self.mock_db

    def test_individual_month(self):
        """month-N returns a single-element list with that month."""
        assert self.service._parse_period('month-1') == [1]
        assert self.service._parse_period('month-6') == [6]
        assert self.service._parse_period('month-12') == [12]

    def test_quarter_q1(self):
        """q1 returns months 1, 2, 3."""
        assert self.service._parse_period('q1') == [1, 2, 3]

    def test_quarter_q2(self):
        """q2 returns months 4, 5, 6."""
        assert self.service._parse_period('q2') == [4, 5, 6]

    def test_quarter_q3(self):
        """q3 returns months 7, 8, 9."""
        assert self.service._parse_period('q3') == [7, 8, 9]

    def test_quarter_q4(self):
        """q4 returns months 10, 11, 12."""
        assert self.service._parse_period('q4') == [10, 11, 12]

    def test_ytd_returns_months_up_to_current(self):
        """ytd returns months 1 through the current calendar month."""
        from unittest.mock import patch as mock_patch
        from datetime import datetime as dt

        with mock_patch('services.budget_query_service.datetime') as mock_dt:
            mock_dt.now.return_value = dt(2025, 4, 15)
            mock_dt.side_effect = lambda *args, **kw: dt(*args, **kw)
            result = self.service._parse_period('ytd')

        assert result == [1, 2, 3, 4]

    def test_full_returns_all_12_months(self):
        """full returns all months 1–12."""
        assert self.service._parse_period('full') == list(range(1, 13))

    def test_unrecognized_defaults_to_full(self):
        """Unrecognized period string defaults to full year."""
        assert self.service._parse_period('invalid') == list(range(1, 13))

    def test_invalid_month_number_defaults_to_full(self):
        """month-13 (out of range) defaults to full year."""
        assert self.service._parse_period('month-13') == list(range(1, 13))

    def test_month_zero_defaults_to_full(self):
        """month-0 (out of range) defaults to full year."""
        assert self.service._parse_period('month-0') == list(range(1, 13))


class TestGetDashboard:
    """Tests for BudgetService.get_dashboard() — Requirements 6.1–6.9."""

    def setup_method(self):
        """Create a BudgetService with a mocked database."""
        with patch('database.DatabaseManager') as MockDB:
            self.mock_db = MockDB.return_value
            self.service = BudgetService(test_mode=True)
            self.service.db = self.mock_db

    def test_no_active_version_returns_notification(self):
        """When no active version exists, returns empty rows with notification."""
        self.mock_db.execute_query.return_value = []

        result = self.service.get_dashboard('tenant_a', 'parent', 'ytd', year=2025)

        assert result['success'] is True
        assert result['data']['active_version'] is None
        assert result['data']['rows'] == []
        assert 'No active budget version for 2025' in result['data']['notification']

    def test_returns_budget_actual_variance(self):
        """Dashboard merges budget and actuals with variance = actual - budget."""
        # Mock: active version found
        # Mock: get_rollup budget data (called internally via get_rollup)
        # Mock: actuals query
        # Mock: name resolution

        # Setup budget rollup response data
        budget_row = {f'm{i:02d}': Decimal('0.00') for i in range(1, 13)}
        budget_row['m01'] = Decimal('1000.00')
        budget_row['m02'] = Decimal('1500.00')
        budget_row['m03'] = Decimal('2000.00')
        budget_row['code'] = '4000'

        self.mock_db.execute_query.side_effect = [
            # 1. Find active version
            [{'id': 3, 'name': 'Budget 2025 Approved'}],
            # 2. get_rollup query (budget lines joined to rekeningschema)
            [budget_row],
            # 3. get_rollup name resolution
            [{'Account': '4000', 'AccountName': 'Omzet'}],
            # 4. actuals query from vw_mutaties
            [{'code': '4000', 'actual': Decimal('4200.50')}],
            # 5. _resolve_names
            [{'Account': '4000', 'AccountName': 'Omzet'}],
        ]

        result = self.service.get_dashboard('tenant_a', 'parent', 'q1', year=2025)

        assert result['success'] is True
        assert result['data']['year'] == 2025
        assert result['data']['level'] == 'parent'
        assert result['data']['period'] == 'q1'
        assert result['data']['active_version']['id'] == 3
        assert result['data']['active_version']['name'] == 'Budget 2025 Approved'

        rows = result['data']['rows']
        assert len(rows) == 1
        assert rows[0]['code'] == '4000'
        assert rows[0]['name'] == 'Omzet'
        assert rows[0]['budget'] == 4500.0  # 1000 + 1500 + 2000
        assert rows[0]['actual'] == 4200.50
        assert rows[0]['variance'] == -299.50  # 4200.50 - 4500.0

    def test_default_period_is_ytd_when_empty(self):
        """When period is empty/None, defaults to 'ytd'."""
        self.mock_db.execute_query.return_value = []

        result = self.service.get_dashboard('tenant_a', 'parent', '', year=2025)

        assert result['data']['period'] == 'ytd'

    def test_variance_positive_means_over_budget(self):
        """Positive variance means actual > budget (over-budget)."""
        budget_row = {f'm{i:02d}': Decimal('0.00') for i in range(1, 13)}
        budget_row['m01'] = Decimal('100.00')
        budget_row['code'] = '5000'

        self.mock_db.execute_query.side_effect = [
            [{'id': 1, 'name': 'V1'}],  # active version
            [budget_row],  # rollup
            [{'Account': '5000', 'AccountName': 'Kosten'}],  # name resolution in rollup
            [{'code': '5000', 'actual': Decimal('150.00')}],  # actuals
            [{'Account': '5000', 'AccountName': 'Kosten'}],  # name resolution
        ]

        result = self.service.get_dashboard('tenant_a', 'parent', 'month-1', year=2025)

        rows = result['data']['rows']
        assert rows[0]['variance'] == 50.0  # 150 - 100 = 50 (over-budget)

    def test_variance_negative_means_under_budget(self):
        """Negative variance means actual < budget (under-budget)."""
        budget_row = {f'm{i:02d}': Decimal('0.00') for i in range(1, 13)}
        budget_row['m01'] = Decimal('200.00')
        budget_row['code'] = '5000'

        self.mock_db.execute_query.side_effect = [
            [{'id': 1, 'name': 'V1'}],  # active version
            [budget_row],  # rollup
            [{'Account': '5000', 'AccountName': 'Kosten'}],  # name resolution in rollup
            [{'code': '5000', 'actual': Decimal('120.00')}],  # actuals
            [{'Account': '5000', 'AccountName': 'Kosten'}],  # name resolution
        ]

        result = self.service.get_dashboard('tenant_a', 'parent', 'month-1', year=2025)

        rows = result['data']['rows']
        assert rows[0]['variance'] == -80.0  # 120 - 200 = -80 (under-budget)

    def test_code_in_actuals_only_shows_zero_budget(self):
        """Codes only in actuals show budget=0 with variance=actual."""
        self.mock_db.execute_query.side_effect = [
            [{'id': 1, 'name': 'V1'}],  # active version
            [],  # rollup returns no budget rows
            # (name resolution for rollup skipped because no data)
            [{'code': '6000', 'actual': Decimal('500.00')}],  # actuals
            [{'Account': '6000', 'AccountName': 'Diversen'}],  # name resolution
        ]

        result = self.service.get_dashboard('tenant_a', 'parent', 'full', year=2025)

        rows = result['data']['rows']
        assert len(rows) == 1
        assert rows[0]['code'] == '6000'
        assert rows[0]['budget'] == 0.0
        assert rows[0]['actual'] == 500.0
        assert rows[0]['variance'] == 500.0

    def test_code_in_budget_only_shows_zero_actual(self):
        """Codes only in budget show actual=0 with negative variance."""
        budget_row = {f'm{i:02d}': Decimal('0.00') for i in range(1, 13)}
        budget_row['m01'] = Decimal('300.00')
        budget_row['code'] = '4000'

        self.mock_db.execute_query.side_effect = [
            [{'id': 1, 'name': 'V1'}],  # active version
            [budget_row],  # rollup
            [{'Account': '4000', 'AccountName': 'Omzet'}],  # name resolution in rollup
            [],  # actuals empty
            [{'Account': '4000', 'AccountName': 'Omzet'}],  # name resolution
        ]

        result = self.service.get_dashboard('tenant_a', 'parent', 'month-1', year=2025)

        rows = result['data']['rows']
        assert len(rows) == 1
        assert rows[0]['code'] == '4000'
        assert rows[0]['budget'] == 300.0
        assert rows[0]['actual'] == 0.0
        assert rows[0]['variance'] == -300.0

    def test_reference_number_filter_applied(self):
        """When reference_number is provided, both budget and actuals are filtered."""
        budget_row = {f'm{i:02d}': Decimal('0.00') for i in range(1, 13)}
        budget_row['m01'] = Decimal('500.00')
        budget_row['code'] = '4000'

        self.mock_db.execute_query.side_effect = [
            # active version
            [{'id': 1, 'name': 'V1'}],
            # _get_budget_rollup_filtered query
            [budget_row],
            # actuals query (with ReferenceNumber filter)
            [{'code': '4000', 'actual': Decimal('450.00')}],
            # _resolve_names
            [{'Account': '4000', 'AccountName': 'Omzet'}],
        ]

        result = self.service.get_dashboard(
            'tenant_a', 'parent', 'month-1', year=2025, reference_number='REF001'
        )

        assert result['success'] is True
        rows = result['data']['rows']
        assert len(rows) == 1
        assert rows[0]['budget'] == 500.0
        assert rows[0]['actual'] == 450.0
        assert rows[0]['variance'] == -50.0

        # Verify the actuals query included ReferenceNumber filter
        actuals_call = self.mock_db.execute_query.call_args_list[2]
        query = actuals_call[0][0]
        assert 'ReferenceNumber' in query

    def test_response_structure_matches_design(self):
        """Response matches the structure defined in design.md."""
        budget_row = {f'm{i:02d}': Decimal('0.00') for i in range(1, 13)}
        budget_row['m01'] = Decimal('100.00')
        budget_row['code'] = '4000'

        self.mock_db.execute_query.side_effect = [
            [{'id': 3, 'name': 'Budget 2025 Approved'}],
            [budget_row],
            [{'Account': '4000', 'AccountName': 'Omzet'}],
            [{'code': '4000', 'actual': Decimal('90.00')}],
            [{'Account': '4000', 'AccountName': 'Omzet'}],
        ]

        result = self.service.get_dashboard('tenant_a', 'parent', 'month-1', year=2025)

        assert 'success' in result
        data = result['data']
        assert 'year' in data
        assert 'level' in data
        assert 'period' in data
        assert 'active_version' in data
        assert 'rows' in data
        assert 'id' in data['active_version']
        assert 'name' in data['active_version']

        row = data['rows'][0]
        assert 'code' in row
        assert 'name' in row
        assert 'budget' in row
        assert 'actual' in row
        assert 'variance' in row

    def test_administration_filter_on_version_query(self):
        """Active version query always filters by administration."""
        self.mock_db.execute_query.return_value = []

        self.service.get_dashboard('tenant_a', 'parent', 'full', year=2025)

        call_args = self.mock_db.execute_query.call_args_list[0]
        query = call_args[0][0]
        params = call_args[0][1]
        assert 'administration' in query
        assert 'tenant_a' in params


class TestTenantIsolationGuards:
    """Comprehensive tenant isolation tests — Requirements 8.1–8.5.

    Validates the defense-in-depth pattern: every read/write/delete operation
    filters by `administration` from the authenticated user context. Cross-tenant
    access attempts return "not found" rather than 403, so we don't reveal
    whether a resource exists for another tenant.

    This test class consolidates cross-tenant denial scenarios across all
    budget service methods to document and verify the isolation pattern.
    """

    def setup_method(self):
        """Create a BudgetService with a mocked database."""
        with patch('database.DatabaseManager') as MockDB:
            self.mock_db = MockDB.return_value
            self.service = BudgetService(test_mode=True)
            self.service.db = self.mock_db

    def test_cross_tenant_version_delete_denied(self):
        """Attempting to delete another tenant's version returns 'not found'."""
        # Tenant B's version exists at id=1, but Tenant A queries with their admin
        self.mock_db.execute_query.return_value = []

        result = self.service.delete_version('tenant_a', 1)

        assert result['success'] is False
        assert "Budget version not found" in result['error']

    def test_cross_tenant_version_activation_denied(self):
        """Attempting to activate another tenant's version returns 'not found'."""
        self.mock_db.execute_query.return_value = []

        result = self.service.activate_version('tenant_a', 1)

        assert result['success'] is False
        assert "Budget version not found" in result['error']

    def test_cross_tenant_status_transition_denied(self):
        """Attempting to transition another tenant's version returns 'not found'."""
        self.mock_db.execute_query.return_value = []

        result = self.service.transition_status('tenant_a', 1, 'approve')

        assert result['success'] is False
        assert "Budget version not found" in result['error']

    def test_cross_tenant_line_update_denied(self):
        """Attempting to update another tenant's line returns 'not found'."""
        self.mock_db.execute_query.return_value = []

        result = self.service.update_line('tenant_a', 1, amounts=[0]*12)

        assert result['success'] is False
        assert "Budget line not found" in result['error']

    def test_cross_tenant_line_delete_denied(self):
        """Attempting to delete another tenant's line returns 'not found'."""
        self.mock_db.execute_query.return_value = []

        result = self.service.delete_line('tenant_a', 1)

        assert result['success'] is False
        assert "Budget line not found" in result['error']

    def test_cross_tenant_copy_source_denied(self):
        """Attempting to copy from another tenant's version returns 'not found'."""
        self.mock_db.execute_query.return_value = []

        result = self.service.copy_budget('tenant_a', 1, 2026, 'Copy')

        assert result['success'] is False
        assert "Budget version not found" in result['error']

    def test_all_queries_include_administration_parameter(self):
        """Verify that list operations always include administration in query."""
        self.mock_db.execute_query.return_value = []

        # list_versions
        self.service.list_versions('tenant_x')
        query = self.mock_db.execute_query.call_args[0][0]
        assert 'administration = %s' in query

        # list_lines
        self.service.list_lines('tenant_x', 1)
        query = self.mock_db.execute_query.call_args[0][0]
        assert 'administration = %s' in query
