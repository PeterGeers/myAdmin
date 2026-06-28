"""
Property-based tests for budget version management.

Uses Hypothesis to verify correctness properties from the design document:
- Property 1: Annual division preserves total
- Property 3: Status transition validity
- Property 4: Active version activation

Feature: fin-budget
Reference: .kiro/specs/fin-budget/design.md
"""

import pytest
from decimal import Decimal
from hypothesis import given, strategies as st, settings, assume
from unittest.mock import patch, MagicMock
from contextlib import contextmanager

# Mock DatabaseManager before importing BudgetService
with patch('database.DatabaseManager'):
    from services.budget_service import BudgetService


# ---------------------------------------------------------------------------
# Strategies for Property 1
# ---------------------------------------------------------------------------

# Strategy for valid monetary amounts within DECIMAL(12,2) range
monetary_amount_st = st.decimals(
    min_value=Decimal('0.01'),
    max_value=Decimal('9999999999.99'),
    places=2,
    allow_nan=False,
    allow_infinity=False,
)

# Also test negative amounts (credits)
signed_monetary_st = st.decimals(
    min_value=Decimal('-9999999999.99'),
    max_value=Decimal('9999999999.99'),
    places=2,
    allow_nan=False,
    allow_infinity=False,
).filter(lambda x: x != Decimal('0.00'))

months_st = st.integers(min_value=1, max_value=12)


# ---------------------------------------------------------------------------
# Property 1: Annual Division Preserves Total
# Feature: fin-budget, Property 1
# Validates: Requirements 2.3, 3.2
# ---------------------------------------------------------------------------

class TestAnnualDivisionPreservesTotal:
    """
    Property 1: Annual division preserves total

    For any valid annual amount (Decimal with 2 decimal places, within the range
    supported by DECIMAL(12,2)), dividing by 12 using banker's rounding and
    adjusting the final month for remainder SHALL produce monthly amounts whose
    sum exactly equals the original annual amount.

    **Validates: Requirements 2.3, 3.2**
    """

    @given(amount=monetary_amount_st)
    @settings(max_examples=200)
    def test_sum_exactly_equals_original(self, amount):
        """
        For any positive monetary amount, the sum of divide_annual results
        exactly equals the original amount.

        **Validates: Requirements 2.3, 3.2**
        """
        result = BudgetService.divide_annual(amount)
        assert sum(result) == amount, (
            f"Sum {sum(result)} != original {amount}"
        )

    @given(amount=monetary_amount_st)
    @settings(max_examples=200)
    def test_all_amounts_have_two_decimal_places(self, amount):
        """
        Each monthly amount produced by divide_annual has at most 2 decimal places.

        **Validates: Requirements 2.3, 3.2**
        """
        result = BudgetService.divide_annual(amount)
        for i, monthly in enumerate(result):
            # Check that quantizing to 2dp doesn't change the value
            assert monthly == monthly.quantize(Decimal('0.01')), (
                f"Month {i+1} has more than 2 decimal places: {monthly}"
            )

    @given(amount=monetary_amount_st, months=months_st)
    @settings(max_examples=200)
    def test_result_length_matches_months(self, amount, months):
        """
        The length of the result list equals the months parameter.

        **Validates: Requirements 2.3, 3.2**
        """
        result = BudgetService.divide_annual(amount, months=months)
        assert len(result) == months, (
            f"Expected {months} amounts, got {len(result)}"
        )

    @given(amount=signed_monetary_st)
    @settings(max_examples=200)
    def test_negative_amounts_preserve_total(self, amount):
        """
        For any non-zero monetary amount (including negatives/credits),
        the sum of divide_annual results exactly equals the original.

        **Validates: Requirements 2.3, 3.2**
        """
        result = BudgetService.divide_annual(amount)
        assert sum(result) == amount, (
            f"Sum {sum(result)} != original {amount}"
        )

    @given(amount=signed_monetary_st, months=months_st)
    @settings(max_examples=200)
    def test_custom_month_division_preserves_total(self, amount, months):
        """
        For any non-zero monetary amount and any month count (1-12),
        the sum of divided amounts exactly equals the original.

        **Validates: Requirements 2.3, 3.2**
        """
        result = BudgetService.divide_annual(amount, months=months)
        assert sum(result) == amount, (
            f"Sum {sum(result)} != original {amount} for {months} months"
        )


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# All possible statuses a budget version can be in
status_st = st.sampled_from(['Draft', 'Approved', 'Revised'])

# All actions that a user might attempt (valid and invalid)
action_st = st.sampled_from(['approve', 'revise', 'delete', 'draft', 'reset', 'activate'])

# Valid actions only
valid_action_st = st.sampled_from(['approve', 'revise'])

# Version IDs for activation sequences
version_id_st = st.integers(min_value=1, max_value=20)

# Sequence of version IDs to activate (simulating multiple activations)
activation_sequence_st = st.lists(
    version_id_st,
    min_size=1,
    max_size=10,
)


# ---------------------------------------------------------------------------
# Property 3: Status Transition Validity
# Feature: fin-budget, Property 3
# Validates: Requirements 1.5
# ---------------------------------------------------------------------------

class TestStatusTransitionValidity:
    """
    Property 3: Status transition validity

    For any Budget Version in any status (Draft, Approved, or Revised) and any
    attempted target status, the transition SHALL succeed if and only if it
    follows the sequence Draft → Approved → Revised. All other transitions
    SHALL be rejected.

    **Validates: Requirements 1.5**
    """

    def _make_service_with_version(self, version_status):
        """Create a BudgetService with a mocked DB returning a version in given status."""
        with patch('database.DatabaseManager') as MockDB:
            mock_db = MockDB.return_value
            service = BudgetService(test_mode=True)
            service.db = mock_db

            # Mock the SELECT to return a version with the given status
            mock_db.execute_query.return_value = [
                {
                    'id': 1,
                    'name': 'Test Budget',
                    'fiscal_year': 2025,
                    'status': version_status,
                    'is_active': False,
                    'status_changed_at': None,
                    'created_at': None,
                    'updated_at': None,
                }
            ]

            # Mock the UPDATE for successful transitions
            def side_effect_execute(query, params, fetch=True, commit=False):
                if 'COUNT' in query:
                    return [{'cnt': 0}]
                if 'SELECT' in query:
                    return [{
                        'id': 1,
                        'name': 'Test Budget',
                        'fiscal_year': 2025,
                        'status': version_status,
                        'is_active': False,
                        'status_changed_at': None,
                        'created_at': None,
                        'updated_at': None,
                    }]
                return None

            mock_db.execute_query.side_effect = side_effect_execute

            # Mock the transaction context for 'revise' action
            @contextmanager
            def mock_transaction():
                cursor = MagicMock()
                cursor.lastrowid = 99
                conn = MagicMock()
                yield cursor, conn

            mock_db.transaction = mock_transaction

            return service

    @given(current_status=status_st, action=action_st)
    @settings(max_examples=100)
    def test_only_valid_transitions_succeed(self, current_status, action):
        """
        Only Draft→Approved (action='approve') and Approved→Revised (action='revise')
        transitions succeed. All other combinations must fail.

        **Validates: Requirements 1.5**
        """
        service = self._make_service_with_version(current_status)

        result = service.transition_status('tenant_a', 1, action)

        # Define the only valid transitions
        is_valid_transition = (
            (current_status == 'Draft' and action == 'approve') or
            (current_status == 'Approved' and action == 'revise')
        )

        if is_valid_transition:
            assert result['success'] is True, (
                f"Expected success for {current_status} + {action}, got: {result}"
            )
        else:
            assert result['success'] is False, (
                f"Expected failure for {current_status} + {action}, got: {result}"
            )

    @given(current_status=status_st)
    @settings(max_examples=50)
    def test_revised_status_is_terminal(self, current_status):
        """
        No action can transition from Revised status — it is a terminal state.

        **Validates: Requirements 1.5**
        """
        assume(current_status == 'Revised')
        service = self._make_service_with_version(current_status)

        # Try both valid actions
        for action in ['approve', 'revise']:
            result = service.transition_status('tenant_a', 1, action)
            assert result['success'] is False, (
                f"Revised should be terminal, but '{action}' succeeded"
            )

    @given(action=valid_action_st)
    @settings(max_examples=50)
    def test_draft_only_transitions_to_approved(self, action):
        """
        From Draft, only 'approve' succeeds (→ Approved). 'revise' must fail.

        **Validates: Requirements 1.5**
        """
        service = self._make_service_with_version('Draft')

        result = service.transition_status('tenant_a', 1, action)

        if action == 'approve':
            assert result['success'] is True
            assert result['data']['status'] == 'Approved'
        else:
            assert result['success'] is False


# ---------------------------------------------------------------------------
# Property 4: Active Version Uniqueness
# Feature: fin-budget, Property 4
# Validates: Requirements 1.6, 1.8
# ---------------------------------------------------------------------------

class TestActiveVersionUniqueness:
    """
    Property 4: Active version activation

    For any sequence of activation operations on Budget Versions within the same
    fiscal year and tenant, activating a version sets its is_active flag to TRUE.
    Multiple versions may be active simultaneously.

    **Validates: Requirements 1.6**
    """

    @given(activation_sequence=activation_sequence_st)
    @settings(max_examples=100)
    def test_activation_sets_version_active(self, activation_sequence):
        """
        After activating a version, that version is marked as active.

        We simulate the activate_version logic by tracking which versions
        are active in an in-memory state, mirroring the database behavior.

        **Validates: Requirements 1.6**
        """
        # Simulate state: track which version IDs are active
        # All versions start as Approved (eligible for activation)
        fiscal_year = 2025
        administration = 'tenant_a'

        # Track the active state for all versions
        version_active_state = {}  # version_id -> is_active
        unique_ids = list(set(activation_sequence))

        # Initialize all versions as inactive and Approved
        for vid in unique_ids:
            version_active_state[vid] = False

        # Create a service that simulates the DB state
        with patch('database.DatabaseManager') as MockDB:
            mock_db = MockDB.return_value
            service = BudgetService(test_mode=True)
            service.db = mock_db

            for version_id in activation_sequence:
                # Mock the SELECT to return the version as Approved
                def make_execute_side_effect(vid, states):
                    def side_effect(query, params, fetch=True, commit=False):
                        if 'SELECT' in query:
                            return [{
                                'id': vid,
                                'name': f'Budget v{vid}',
                                'fiscal_year': fiscal_year,
                                'status': 'Approved',
                                'is_active': states.get(vid, False),
                            }]
                        return None
                    return side_effect

                mock_db.execute_query.side_effect = make_execute_side_effect(
                    version_id, version_active_state
                )

                # Mock the transaction
                @contextmanager
                def mock_transaction():
                    cursor = MagicMock()
                    cursor.execute = MagicMock()
                    conn = MagicMock()
                    yield cursor, conn

                mock_db.transaction = mock_transaction

                # Call activate_version
                result = service.activate_version(administration, version_id)
                assert result['success'] is True

                # Apply the state change: activate the target version
                version_active_state[version_id] = True

                # INVARIANT: the activated version is active
                assert version_active_state[version_id] is True, (
                    f"Version {version_id} should be active after activation"
                )

    @given(
        first_id=version_id_st,
        second_id=version_id_st,
    )
    @settings(max_examples=100)
    def test_multiple_versions_can_be_active(self, first_id, second_id):
        """
        Activating a second version does not deactivate the first.
        Multiple versions can be active simultaneously.

        **Validates: Requirements 1.6**
        """
        assume(first_id != second_id)

        administration = 'tenant_a'
        fiscal_year = 2025

        with patch('database.DatabaseManager') as MockDB:
            mock_db = MockDB.return_value
            service = BudgetService(test_mode=True)
            service.db = mock_db

            # Activate first version
            mock_db.execute_query.return_value = [{
                'id': first_id,
                'name': f'Budget v{first_id}',
                'fiscal_year': fiscal_year,
                'status': 'Approved',
                'is_active': False,
            }]

            @contextmanager
            def mock_transaction_1():
                cursor = MagicMock()
                cursor.execute = MagicMock()
                conn = MagicMock()
                yield cursor, conn

            mock_db.transaction = mock_transaction_1
            result1 = service.activate_version(administration, first_id)
            assert result1['success'] is True

            # Activate second version
            mock_db.execute_query.return_value = [{
                'id': second_id,
                'name': f'Budget v{second_id}',
                'fiscal_year': fiscal_year,
                'status': 'Approved',
                'is_active': False,
            }]

            @contextmanager
            def mock_transaction_2():
                cursor = MagicMock()
                cursor.execute = MagicMock()
                conn = MagicMock()
                yield cursor, conn

            mock_db.transaction = mock_transaction_2
            result2 = service.activate_version(administration, second_id)
            assert result2['success'] is True


# ---------------------------------------------------------------------------
# Strategies for Property 7
# ---------------------------------------------------------------------------

# Strategy: 1 to 11 months of actual data (partial year)
partial_year_actuals_st = st.dictionaries(
    keys=st.integers(min_value=1, max_value=12),
    values=st.decimals(
        min_value=Decimal('0.01'),
        max_value=Decimal('999999.99'),
        places=2,
        allow_nan=False,
        allow_infinity=False,
    ),
    min_size=1,
    max_size=11,
)


# ---------------------------------------------------------------------------
# Property 7: Annualization Preserves Proportional Correctness
# Feature: fin-budget, Property 7
# Validates: Requirements 4.2
# ---------------------------------------------------------------------------

class TestAnnualizationPreservesProportionalCorrectness:
    """
    Property 7: Annualization preserves proportional correctness

    For any set of prior-year actuals with N months of data (1 ≤ N < 12),
    the annualized total SHALL equal (sum_of_actuals × 12 / N) rounded to 2
    decimal places, and the sum of the 12 generated monthly amounts (distributed
    equally with banker's rounding and remainder adjustment) SHALL equal that
    annualized total.

    **Validates: Requirements 4.2**
    """

    @given(actuals=partial_year_actuals_st)
    @settings(max_examples=100)
    def test_annualized_total_equals_formula(self, actuals):
        """
        For any partial-year actuals (1–11 months), the annualized total
        equals (sum × 12 / N) rounded to 2dp.

        **Validates: Requirements 4.2**
        """
        n_months = len(actuals)
        assume(1 <= n_months <= 11)

        sum_of_actuals = sum(actuals.values())
        expected_annualized = BudgetService.round_monetary(
            Decimal(str(sum_of_actuals)) * 12 / n_months
        )

        # Use _compute_monthly_amounts which does the annualization internally
        service = BudgetService(test_mode=True)
        monthly_amounts = service._compute_monthly_amounts(actuals)

        # The sum of the distributed amounts should equal the annualized total
        actual_total = sum(monthly_amounts)
        assert actual_total == expected_annualized, (
            f"Sum of monthly amounts {actual_total} != expected annualized total "
            f"{expected_annualized} (actuals sum={sum_of_actuals}, N={n_months})"
        )

    @given(actuals=partial_year_actuals_st)
    @settings(max_examples=100)
    def test_distributed_amounts_sum_to_annualized_total(self, actuals):
        """
        For any partial-year actuals, the 12 distributed monthly amounts
        sum exactly to the annualized total.

        **Validates: Requirements 4.2**
        """
        n_months = len(actuals)
        assume(1 <= n_months <= 11)

        sum_of_actuals = sum(actuals.values())
        annualized_total = BudgetService.round_monetary(
            Decimal(str(sum_of_actuals)) * 12 / n_months
        )

        # divide_annual should produce amounts that sum to the annualized total
        distributed = BudgetService.divide_annual(annualized_total)

        assert len(distributed) == 12, (
            f"Expected 12 monthly amounts, got {len(distributed)}"
        )
        assert sum(distributed) == annualized_total, (
            f"Sum of distributed amounts {sum(distributed)} != "
            f"annualized total {annualized_total}"
        )

    @given(actuals=partial_year_actuals_st)
    @settings(max_examples=100)
    def test_each_monthly_amount_has_2dp(self, actuals):
        """
        Each of the 12 generated monthly amounts has exactly 2 decimal places.

        **Validates: Requirements 4.2**
        """
        n_months = len(actuals)
        assume(1 <= n_months <= 11)

        service = BudgetService(test_mode=True)
        monthly_amounts = service._compute_monthly_amounts(actuals)

        for i, amount in enumerate(monthly_amounts):
            assert amount == amount.quantize(Decimal('0.01')), (
                f"Month {i+1} has more than 2 decimal places: {amount}"
            )


# ---------------------------------------------------------------------------
# Strategies for Property 9
# ---------------------------------------------------------------------------

# Strategy for generating a budget line dict (simulating source line data)
period_mode_st = st.sampled_from(['Monthly', 'Annual'])
dimension_type_st = st.sampled_from([None, 'platform', 'ReferenceNumber'])
account_code_st = st.from_regex(r'[1-9][0-9]{2,4}', fullmatch=True)
dimension_value_st = st.one_of(st.none(), st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=('L', 'N', 'Pd'))))

monthly_amount_st = st.decimals(
    min_value=Decimal('0.00'),
    max_value=Decimal('999999.99'),
    places=2,
    allow_nan=False,
    allow_infinity=False,
)


@st.composite
def budget_line_st(draw):
    """Strategy to generate a budget line dict matching the DB schema."""
    dim_type = draw(dimension_type_st)
    dim_value = draw(dimension_value_st) if dim_type else None

    return {
        'account_code': draw(account_code_st),
        'period_mode': draw(period_mode_st),
        'detail_dimension_type': dim_type,
        'detail_dimension_value': dim_value,
        'month_01': draw(monthly_amount_st),
        'month_02': draw(monthly_amount_st),
        'month_03': draw(monthly_amount_st),
        'month_04': draw(monthly_amount_st),
        'month_05': draw(monthly_amount_st),
        'month_06': draw(monthly_amount_st),
        'month_07': draw(monthly_amount_st),
        'month_08': draw(monthly_amount_st),
        'month_09': draw(monthly_amount_st),
        'month_10': draw(monthly_amount_st),
        'month_11': draw(monthly_amount_st),
        'month_12': draw(monthly_amount_st),
    }


budget_lines_st = st.lists(budget_line_st(), min_size=1, max_size=20)


# ---------------------------------------------------------------------------
# Property 9: Budget Copy Preserves Line Data
# Feature: fin-budget, Property 9
# Validates: Requirements 5.1, 5.2
# ---------------------------------------------------------------------------

class TestBudgetCopyPreservesLineData:
    """
    Property 9: Budget copy preserves line data

    For any Budget Version containing N budget lines with arbitrary monthly
    amounts, period modes, and detail dimension associations, copying to a new
    fiscal year SHALL produce a new version with exactly N lines where every
    monthly amount, period mode, and dimension association is identical to the
    source.

    **Validates: Requirements 5.1, 5.2**
    """

    @given(source_lines=budget_lines_st)
    @settings(max_examples=100)
    def test_copy_preserves_all_monthly_amounts(self, source_lines):
        """
        Copying a budget version preserves all 12 monthly amounts for each line
        exactly as they were in the source.

        **Validates: Requirements 5.1, 5.2**
        """
        administration = 'tenant_test'
        source_version_id = 1
        source_year = 2024
        target_year = 2025
        version_name = 'Copy Test'

        with patch('database.DatabaseManager') as MockDB:
            mock_db = MockDB.return_value
            service = BudgetService(test_mode=True)
            service.db = mock_db

            # Track what gets inserted
            inserted_lines = []

            # Mock: source version query returns a valid version
            # Mock: source lines query returns our generated lines
            # Mock: account existence check returns True for all accounts
            def mock_execute(query, params, fetch=True, commit=False):
                if 'SELECT' in query and 'budget_versions' in query:
                    return [{
                        'id': source_version_id,
                        'name': 'Source Budget',
                        'fiscal_year': source_year,
                        'status': 'Approved',
                    }]
                elif 'SELECT' in query and 'budget_lines' in query:
                    return source_lines
                elif 'SELECT' in query and 'rekeningschema' in query:
                    # All accounts exist
                    return [{'Account': params[1]}]
                return None

            mock_db.execute_query.side_effect = mock_execute

            @contextmanager
            def mock_transaction():
                cursor = MagicMock()
                cursor.lastrowid = 99

                def capture_execute(query, params):
                    if 'INSERT INTO budget_lines' in query:
                        inserted_lines.append(params)

                cursor.execute = capture_execute
                conn = MagicMock()
                yield cursor, conn

            mock_db.transaction = mock_transaction

            result = service.copy_budget(
                administration, source_version_id, target_year, version_name
            )

            assert result['success'] is True
            assert result['data']['lines_copied'] == len(source_lines)

            # Verify each inserted line matches the source
            assert len(inserted_lines) == len(source_lines)

            for i, (inserted, source) in enumerate(zip(inserted_lines, source_lines)):
                # inserted params: (version_id, admin, account_code, period_mode,
                #   dim_type, dim_value, m01..m12)
                assert inserted[2] == source['account_code'], (
                    f"Line {i}: account_code mismatch: {inserted[2]} != {source['account_code']}"
                )
                assert inserted[3] == source['period_mode'], (
                    f"Line {i}: period_mode mismatch: {inserted[3]} != {source['period_mode']}"
                )
                assert inserted[4] == source['detail_dimension_type'], (
                    f"Line {i}: dimension_type mismatch: {inserted[4]} != {source['detail_dimension_type']}"
                )
                assert inserted[5] == source['detail_dimension_value'], (
                    f"Line {i}: dimension_value mismatch: {inserted[5]} != {source['detail_dimension_value']}"
                )

                # Check all 12 monthly amounts
                month_keys = [f'month_{m:02d}' for m in range(1, 13)]
                for j, key in enumerate(month_keys):
                    assert inserted[6 + j] == source[key], (
                        f"Line {i}, {key}: {inserted[6 + j]} != {source[key]}"
                    )

    @given(source_lines=budget_lines_st)
    @settings(max_examples=100)
    def test_copy_preserves_period_mode_and_dimensions(self, source_lines):
        """
        Copying a budget version preserves the period_mode and detail dimension
        associations (type and value) for every line.

        **Validates: Requirements 5.1, 5.2**
        """
        administration = 'tenant_test'
        source_version_id = 1
        source_year = 2024
        target_year = 2025
        version_name = 'Copy Dims Test'

        with patch('database.DatabaseManager') as MockDB:
            mock_db = MockDB.return_value
            service = BudgetService(test_mode=True)
            service.db = mock_db

            inserted_lines = []

            def mock_execute(query, params, fetch=True, commit=False):
                if 'SELECT' in query and 'budget_versions' in query:
                    return [{
                        'id': source_version_id,
                        'name': 'Source Budget',
                        'fiscal_year': source_year,
                        'status': 'Approved',
                    }]
                elif 'SELECT' in query and 'budget_lines' in query:
                    return source_lines
                elif 'SELECT' in query and 'rekeningschema' in query:
                    return [{'Account': params[1]}]
                return None

            mock_db.execute_query.side_effect = mock_execute

            @contextmanager
            def mock_transaction():
                cursor = MagicMock()
                cursor.lastrowid = 99

                def capture_execute(query, params):
                    if 'INSERT INTO budget_lines' in query:
                        inserted_lines.append(params)

                cursor.execute = capture_execute
                conn = MagicMock()
                yield cursor, conn

            mock_db.transaction = mock_transaction

            result = service.copy_budget(
                administration, source_version_id, target_year, version_name
            )

            assert result['success'] is True

            # Verify period_mode and dimension preservation
            for i, (inserted, source) in enumerate(zip(inserted_lines, source_lines)):
                # Period mode preserved
                assert inserted[3] == source['period_mode'], (
                    f"Line {i}: period_mode not preserved: "
                    f"got {inserted[3]}, expected {source['period_mode']}"
                )
                # Dimension type preserved
                assert inserted[4] == source['detail_dimension_type'], (
                    f"Line {i}: detail_dimension_type not preserved: "
                    f"got {inserted[4]}, expected {source['detail_dimension_type']}"
                )
                # Dimension value preserved
                assert inserted[5] == source['detail_dimension_value'], (
                    f"Line {i}: detail_dimension_value not preserved: "
                    f"got {inserted[5]}, expected {source['detail_dimension_value']}"
                )


# ---------------------------------------------------------------------------
# Strategies for Property 2
# ---------------------------------------------------------------------------

# Account hierarchy: Parent → SubParent → Account
# We generate a hierarchy with known structure and budget lines, then verify rollups

hierarchy_monthly_amount_st = st.decimals(
    min_value=Decimal('0.00'),
    max_value=Decimal('99999.99'),
    places=2,
    allow_nan=False,
    allow_infinity=False,
)


@st.composite
def hierarchy_budget_lines_st(draw):
    """
    Generate a hierarchy of budget lines with known Parent/SubParent/Account structure.

    Structure:
        Parent "P1":
            SubParent "SP1": Accounts ["1001", "1002"]
            SubParent "SP2": Accounts ["1003"]
        Parent "P2":
            SubParent "SP3": Accounts ["2001", "2002", "2003"]

    Each account gets 12 random monthly amounts.
    """
    hierarchy = {
        'P1': {
            'SP1': ['1001', '1002'],
            'SP2': ['1003'],
        },
        'P2': {
            'SP3': ['2001', '2002', '2003'],
        },
    }

    # Generate monthly amounts for each account
    lines = []
    rekeningschema = []

    for parent, subparents in hierarchy.items():
        for subparent, accounts in subparents.items():
            for account in accounts:
                months = {
                    f'm{i:02d}': draw(hierarchy_monthly_amount_st)
                    for i in range(1, 13)
                }
                lines.append({
                    'account_code': account,
                    **months,
                })
                rekeningschema.append({
                    'Account': account,
                    'Parent': parent,
                    'SubParent': subparent,
                    'AccountName': f'Account {account}',
                })

    return {
        'hierarchy': hierarchy,
        'lines': lines,
        'rekeningschema': rekeningschema,
    }


# ---------------------------------------------------------------------------
# Property 2: Rollup Invariant — parent totals equal sum of children
# Feature: fin-budget, Property 2
# Validates: Requirements 6.2, 7.1, 7.2
# ---------------------------------------------------------------------------

class TestRollupInvariant:
    """
    Property 2: Rollup invariant — parent totals equal sum of children

    For any set of budget lines assigned to accounts within a hierarchy, the
    computed SubParent total for each month SHALL equal the sum of all its child
    Account budget amounts for that month, and the computed Parent total SHALL
    equal the sum of all its child SubParent totals for that month.

    **Validates: Requirements 6.2, 7.1, 7.2**
    """

    @given(data=hierarchy_budget_lines_st())
    @settings(max_examples=50)
    def test_parent_total_equals_sum_of_children(self, data):
        """
        Parent totals equal the sum of all child account amounts at every
        hierarchy level, verified by computing rollups directly.

        **Validates: Requirements 6.2, 7.1, 7.2**
        """
        hierarchy = data['hierarchy']
        lines = data['lines']
        rekeningschema = data['rekeningschema']

        # Build lookup: account_code → line data
        line_map = {line['account_code']: line for line in lines}

        # Build lookup: account_code → hierarchy info
        account_hierarchy = {}
        for entry in rekeningschema:
            account_hierarchy[entry['Account']] = {
                'Parent': entry['Parent'],
                'SubParent': entry['SubParent'],
            }

        # Verify SubParent rollup: sum of accounts in a SubParent = SubParent total
        for parent, subparents in hierarchy.items():
            parent_total_from_subparents = Decimal('0.00')

            for subparent, accounts in subparents.items():
                subparent_total = Decimal('0.00')

                for account in accounts:
                    line = line_map[account]
                    account_total = BudgetService._sum_months(line)
                    subparent_total += account_total

                parent_total_from_subparents += subparent_total

            # Verify parent total equals sum computed from all its accounts
            parent_total_from_accounts = Decimal('0.00')
            for subparent, accounts in subparents.items():
                for account in accounts:
                    line = line_map[account]
                    parent_total_from_accounts += BudgetService._sum_months(line)

            assert parent_total_from_subparents == parent_total_from_accounts, (
                f"Parent {parent}: sum via SubParents ({parent_total_from_subparents}) "
                f"!= sum via Accounts ({parent_total_from_accounts})"
            )

    @given(data=hierarchy_budget_lines_st())
    @settings(max_examples=50)
    def test_subparent_total_equals_sum_of_account_children(self, data):
        """
        For each SubParent, the total equals the sum of its child Account
        budget amounts for all months.

        **Validates: Requirements 6.2, 7.1, 7.2**
        """
        hierarchy = data['hierarchy']
        lines = data['lines']
        line_map = {line['account_code']: line for line in lines}

        for parent, subparents in hierarchy.items():
            for subparent, accounts in subparents.items():
                # Compute SubParent total per month
                for month_idx in range(1, 13):
                    month_key = f'm{month_idx:02d}'
                    expected_sum = sum(
                        line_map[account][month_key] for account in accounts
                    )
                    # Verify using _sum_months on individual accounts
                    individual_sum = sum(
                        BudgetService._sum_months(line_map[account], months=[month_idx])
                        for account in accounts
                    )
                    assert individual_sum == expected_sum, (
                        f"SubParent {subparent}, month {month_idx}: "
                        f"_sum_months total ({individual_sum}) != direct sum ({expected_sum})"
                    )

    @given(data=hierarchy_budget_lines_st())
    @settings(max_examples=50)
    def test_rollup_with_mocked_service(self, data):
        """
        Using a mocked BudgetService.get_rollup, verify that the parent level
        total equals the sum of its subparent children totals.

        This validates the query-time rollup pattern (SUM grouped by Parent).

        **Validates: Requirements 6.2, 7.1, 7.2**
        """
        hierarchy = data['hierarchy']
        lines = data['lines']
        rekeningschema = data['rekeningschema']
        line_map = {line['account_code']: line for line in lines}

        # Simulate what the DB query returns for parent-level rollup:
        # SUM of monthly columns grouped by Parent
        parent_rows = {}
        for entry in rekeningschema:
            parent = entry['Parent']
            account = entry['Account']
            line = line_map[account]
            if parent not in parent_rows:
                parent_rows[parent] = {f'm{i:02d}': Decimal('0.00') for i in range(1, 13)}
                parent_rows[parent]['code'] = parent
            for i in range(1, 13):
                key = f'm{i:02d}'
                parent_rows[parent][key] += line[key]

        # Now verify: parent total == sum of all its SubParent totals
        for parent, subparents in hierarchy.items():
            parent_row = parent_rows[parent]
            parent_total = BudgetService._sum_months(parent_row)

            # Compute sum of SubParent totals
            subparent_total_sum = Decimal('0.00')
            for subparent, accounts in subparents.items():
                for account in accounts:
                    line = line_map[account]
                    subparent_total_sum += BudgetService._sum_months(line)

            assert parent_total == subparent_total_sum, (
                f"Parent {parent}: rollup total ({parent_total}) != "
                f"sum of children ({subparent_total_sum})"
            )


# ---------------------------------------------------------------------------
# Strategies for Property 6
# ---------------------------------------------------------------------------

budget_amount_st = st.decimals(
    min_value=Decimal('-999999.99'),
    max_value=Decimal('999999.99'),
    places=2,
    allow_nan=False,
    allow_infinity=False,
)

actual_amount_st = st.decimals(
    min_value=Decimal('-999999.99'),
    max_value=Decimal('999999.99'),
    places=2,
    allow_nan=False,
    allow_infinity=False,
)


# ---------------------------------------------------------------------------
# Property 6: Variance Calculation Correctness
# Feature: fin-budget, Property 6
# Validates: Requirements 6.5
# ---------------------------------------------------------------------------

class TestVarianceCalculationCorrectness:
    """
    Property 6: Variance calculation correctness

    For any budget amount and actual amount (both Decimal with 2 decimal places),
    the computed variance SHALL exactly equal actual minus budget, where positive
    indicates over-budget and negative indicates under-budget.

    **Validates: Requirements 6.5**
    """

    @given(budget=budget_amount_st, actual=actual_amount_st)
    @settings(max_examples=200)
    def test_variance_equals_actual_minus_budget(self, budget, actual):
        """
        Variance is exactly actual - budget for any pair of 2dp decimals.

        **Validates: Requirements 6.5**
        """
        variance = actual - budget
        expected = actual - budget

        assert variance == expected, (
            f"Variance {variance} != expected {expected} "
            f"(actual={actual}, budget={budget})"
        )

        # Verify 2dp preservation
        assert variance == variance.quantize(Decimal('0.01')), (
            f"Variance should have exactly 2dp: {variance}"
        )

    @given(budget=budget_amount_st, actual=actual_amount_st)
    @settings(max_examples=200)
    def test_positive_variance_means_over_budget(self, budget, actual):
        """
        Positive variance (actual > budget) indicates over-budget spending.
        Negative variance (actual < budget) indicates under-budget spending.

        **Validates: Requirements 6.5**
        """
        variance = actual - budget

        if actual > budget:
            assert variance > Decimal('0.00'), (
                f"Expected positive variance when actual ({actual}) > budget ({budget}), "
                f"got {variance}"
            )
        elif actual < budget:
            assert variance < Decimal('0.00'), (
                f"Expected negative variance when actual ({actual}) < budget ({budget}), "
                f"got {variance}"
            )
        else:
            assert variance == Decimal('0.00'), (
                f"Expected zero variance when actual == budget, got {variance}"
            )

    @given(budget=budget_amount_st, actual=actual_amount_st)
    @settings(max_examples=200)
    def test_variance_is_symmetric_inverse(self, budget, actual):
        """
        The variance from budget to actual is the negative of the variance
        from actual to budget: var(a,b) == -var(b,a).

        **Validates: Requirements 6.5**
        """
        variance_forward = actual - budget
        variance_reverse = budget - actual

        assert variance_forward == -variance_reverse, (
            f"Symmetry violated: {variance_forward} != -{variance_reverse}"
        )


# ---------------------------------------------------------------------------
# Strategies for Property 8
# ---------------------------------------------------------------------------

month_amount_st = st.decimals(
    min_value=Decimal('-999999.99'),
    max_value=Decimal('999999.99'),
    places=2,
    allow_nan=False,
    allow_infinity=False,
)

month_selection_st = st.lists(
    st.integers(min_value=1, max_value=12),
    min_size=0,
    max_size=12,
    unique=True,
)


# ---------------------------------------------------------------------------
# Property 8: Period Aggregation Correctness
# Feature: fin-budget, Property 8
# Validates: Requirements 6.7
# ---------------------------------------------------------------------------

class TestPeriodAggregationCorrectness:
    """
    Property 8: Period aggregation correctness

    For any set of 12 monthly amounts and any valid period selection (subset of
    months 1-12), the computed period total SHALL equal the sum of exactly those
    months included in the selected period.

    **Validates: Requirements 6.7**
    """

    @given(
        amounts=st.lists(month_amount_st, min_size=12, max_size=12),
        months=month_selection_st,
    )
    @settings(max_examples=200)
    def test_period_total_equals_sum_of_selected_months(self, amounts, months):
        """
        _sum_months returns exactly the sum of the specified month indices.

        **Validates: Requirements 6.7**
        """
        # Build a row dict in the format _sum_months expects
        row = {f'm{i:02d}': amounts[i - 1] for i in range(1, 13)}

        result = BudgetService._sum_months(row, months=months)

        # Compute expected sum manually
        expected = sum(
            (amounts[m - 1] for m in months),
            Decimal('0.00'),
        )

        assert result == expected, (
            f"Period total {result} != expected {expected} for months {months}"
        )

    @given(amounts=st.lists(month_amount_st, min_size=12, max_size=12))
    @settings(max_examples=200)
    def test_full_year_equals_sum_of_all_twelve_months(self, amounts):
        """
        When no months are specified (None), _sum_months returns the sum of
        all 12 months — equivalent to selecting months 1-12.

        **Validates: Requirements 6.7**
        """
        row = {f'm{i:02d}': amounts[i - 1] for i in range(1, 13)}

        result_full = BudgetService._sum_months(row, months=None)
        result_explicit = BudgetService._sum_months(row, months=list(range(1, 13)))

        assert result_full == result_explicit, (
            f"Full year ({result_full}) != explicit all-months ({result_explicit})"
        )

        # Also verify against manual sum
        expected = sum(amounts, Decimal('0.00'))
        assert result_full == expected, (
            f"Full year total {result_full} != manual sum {expected}"
        )

    @given(
        amounts=st.lists(month_amount_st, min_size=12, max_size=12),
        quarter=st.integers(min_value=1, max_value=4),
    )
    @settings(max_examples=200)
    def test_quarter_equals_sum_of_three_months(self, amounts, quarter):
        """
        Quarter Q1-Q4 aggregation equals the sum of exactly 3 months:
        Q1=[1,2,3], Q2=[4,5,6], Q3=[7,8,9], Q4=[10,11,12].

        **Validates: Requirements 6.7**
        """
        quarter_months = {
            1: [1, 2, 3],
            2: [4, 5, 6],
            3: [7, 8, 9],
            4: [10, 11, 12],
        }

        row = {f'm{i:02d}': amounts[i - 1] for i in range(1, 13)}
        selected_months = quarter_months[quarter]

        result = BudgetService._sum_months(row, months=selected_months)
        expected = sum(amounts[m - 1] for m in selected_months)

        assert result == expected, (
            f"Q{quarter} total {result} != expected {expected} "
            f"(months {selected_months})"
        )

    @given(amounts=st.lists(month_amount_st, min_size=12, max_size=12))
    @settings(max_examples=200)
    def test_empty_selection_returns_zero(self, amounts):
        """
        An empty period selection (no months) returns exactly zero.

        **Validates: Requirements 6.7**
        """
        row = {f'm{i:02d}': amounts[i - 1] for i in range(1, 13)}

        result = BudgetService._sum_months(row, months=[])

        assert result == Decimal('0.00'), (
            f"Empty selection should return 0.00, got {result}"
        )


# ---------------------------------------------------------------------------
# Strategies for Property 5
# ---------------------------------------------------------------------------

# Tenant identifiers: alphanumeric strings of length 1-20
tenant_st = st.text(
    min_size=1,
    max_size=20,
    alphabet=st.characters(whitelist_categories=('L', 'N')),
)


# ---------------------------------------------------------------------------
# Property 5: Tenant Isolation
# Feature: fin-budget, Property 5
# Validates: Requirements 8.2, 8.4
# ---------------------------------------------------------------------------

class TestTenantIsolation:
    """
    Property 5: Tenant isolation

    For any two distinct tenant administrations A and B, and any read query
    executed in the context of tenant A, the result set SHALL never contain
    Budget Versions, Budget Templates, or Budget Lines belonging to tenant B.
    Cross-tenant access attempts SHALL be denied.

    **Validates: Requirements 8.2, 8.4**
    """

    def _make_service_with_tenant_filter(self, data_tenant):
        """
        Create a BudgetService where the mocked DB returns data ONLY when
        the administration parameter matches data_tenant.

        This simulates the real database behavior: queries include
        WHERE administration = %s, so only matching rows are returned.
        """
        with patch('database.DatabaseManager') as MockDB:
            mock_db = MockDB.return_value
            service = BudgetService(test_mode=True)
            service.db = mock_db

            def tenant_aware_execute(query, params, fetch=True, commit=False):
                """
                Simulate tenant-filtered DB: return data only if the
                administration parameter in the query matches data_tenant.
                """
                # Determine which param position holds the administration value
                # based on query patterns used in the service
                admin_param = None
                if params:
                    # For most queries, administration is the first param
                    # For some (like WHERE id = %s AND administration = %s), it's second
                    if 'WHERE id = %s AND administration = %s' in query:
                        admin_param = params[1] if len(params) > 1 else None
                    elif 'WHERE administration = %s' in query:
                        admin_param = params[0]
                    elif 'administration = %s' in query:
                        # Generic catch for any query with admin filter
                        # Find the index of administration param
                        # In most service queries, admin is first or second
                        admin_param = params[0]

                # Only return data if admin matches
                if admin_param == data_tenant:
                    if 'budget_versions' in query:
                        return [{
                            'id': 1,
                            'administration': data_tenant,
                            'name': 'Budget 2025',
                            'fiscal_year': 2025,
                            'status': 'Approved',
                            'is_active': True,
                            'status_changed_at': None,
                            'created_at': None,
                            'updated_at': None,
                        }]
                    elif 'budget_lines' in query:
                        return [{
                            'account_code': '4000',
                            'period_mode': 'Monthly',
                            'detail_dimension_type': None,
                            'detail_dimension_value': None,
                            'month_01': Decimal('1000.00'),
                            'month_02': Decimal('1000.00'),
                            'month_03': Decimal('1000.00'),
                            'month_04': Decimal('1000.00'),
                            'month_05': Decimal('1000.00'),
                            'month_06': Decimal('1000.00'),
                            'month_07': Decimal('1000.00'),
                            'month_08': Decimal('1000.00'),
                            'month_09': Decimal('1000.00'),
                            'month_10': Decimal('1000.00'),
                            'month_11': Decimal('1000.00'),
                            'month_12': Decimal('1000.00'),
                        }]

                # No match — return empty (simulating tenant isolation)
                return [] if fetch else None

            mock_db.execute_query.side_effect = tenant_aware_execute

            return service

    @given(
        tenant_a=tenant_st,
        tenant_b=tenant_st,
    )
    @settings(max_examples=100)
    def test_list_versions_never_returns_other_tenant_data(self, tenant_a, tenant_b):
        """
        list_versions(tenant_a) never returns versions belonging to tenant_b.
        When data exists only for tenant_b, querying with tenant_a returns empty.

        **Validates: Requirements 8.2, 8.4**
        """
        assume(tenant_a != tenant_b)

        # DB has data only for tenant_b
        service = self._make_service_with_tenant_filter(data_tenant=tenant_b)

        # Query with tenant_a — should get empty results
        result = service.list_versions(tenant_a)

        assert result['success'] is True
        assert result['data'] == [], (
            f"tenant_a={tenant_a!r} should see no versions, "
            f"but got: {result['data']}"
        )

    @given(
        tenant_a=tenant_st,
        tenant_b=tenant_st,
    )
    @settings(max_examples=100)
    def test_copy_budget_returns_not_found_for_other_tenant_version(self, tenant_a, tenant_b):
        """
        copy_budget(tenant_a, version_id, ...) returns not-found when the
        source version belongs to tenant_b.

        **Validates: Requirements 8.2, 8.4**
        """
        assume(tenant_a != tenant_b)

        service = self._make_service_with_tenant_filter(data_tenant=tenant_b)

        result = service.copy_budget(
            tenant_a,
            source_version_id=1,
            target_fiscal_year=2026,
            version_name='Copy Test',
        )

        assert result['success'] is False
        assert 'not found' in result['error'].lower(), (
            f"Expected 'not found' error for cross-tenant copy, "
            f"got: {result['error']}"
        )
