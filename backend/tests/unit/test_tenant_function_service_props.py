"""
Property-based tests for Tenant Function Service.

Uses hypothesis to verify correctness properties from the design document.
Feature: tenant-optional-functions

Requirements: 2.3, 2.4, 6.2, 6.3
Reference: .kiro/specs/tenant-optional-functions/design.md
"""

import sys
import os
import pytest
from unittest.mock import MagicMock, patch
from hypothesis import given, strategies as st, settings, assume

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from services.tenant_function_service import TenantFunctionService
from services.function_registry import FUNCTION_REGISTRY


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Valid tenant names (non-empty strings representing administration names)
tenant_st = st.text(
    alphabet=st.characters(whitelist_categories=('L', 'N'), whitelist_characters='_-'),
    min_size=1,
    max_size=50,
)

# Function names drawn from the actual registry keys
function_name_st = st.sampled_from(list(FUNCTION_REGISTRY.keys()))

# Boolean states for is_active
bool_st = st.booleans()


# ---------------------------------------------------------------------------
# Property 2: Default state resolution when no override exists
# Feature: tenant-optional-functions, Property 2: Default state resolution when no override exists
# Validates: Requirements 2.3
# ---------------------------------------------------------------------------

class TestDefaultStateResolution:
    """For any function in FUNCTION_REGISTRY and any tenant with no corresponding
    row in tenant_functions, get_function_state() SHALL return the default_enabled
    value defined in the registry."""

    @settings(max_examples=100, deadline=None)
    @given(
        tenant=tenant_st,
        function_name=function_name_st,
    )
    def test_returns_registry_default_when_no_override(self, tenant, function_name):
        """
        When the database has no override row for a tenant/function pair,
        get_function_state returns the registry's default_enabled value.

        **Validates: Requirements 2.3**
        """
        # Mock DB to return empty result (no override row exists)
        mock_db = MagicMock()
        mock_db.execute_query.return_value = []

        # Mock has_module to return True (so module check passes)
        with patch('services.tenant_function_service.has_module', return_value=True):
            service = TenantFunctionService(mock_db)
            result = service.get_function_state(tenant, function_name)

        expected = FUNCTION_REGISTRY[function_name]['default_enabled']
        assert result == expected, (
            f"Expected default_enabled={expected} for function '{function_name}' "
            f"and tenant '{tenant}', but got {result}"
        )


# ---------------------------------------------------------------------------
# Property 3: Write failure preserves existing state
# Feature: tenant-optional-functions, Property 3: Write failure preserves existing state
# Validates: Requirements 2.4
# ---------------------------------------------------------------------------

class TestWriteFailurePreservesState:
    """For any tenant and function with an existing activation state, if a
    database write operation fails during set_function_state(), then a
    subsequent get_function_state() call SHALL return the original state
    unchanged."""

    @settings(max_examples=100, deadline=None)
    @given(
        tenant=tenant_st,
        function_name=function_name_st,
        original_state=bool_st,
        new_value=bool_st,
    )
    def test_write_failure_preserves_state(
        self, tenant, function_name, original_state, new_value
    ):
        """A failed write does not alter the state returned by subsequent reads.

        **Validates: Requirements 2.4**
        """
        # Create a mock DB that differentiates between reads and writes
        mock_db = MagicMock()

        def mock_execute_query(query, params=None, fetch=True, commit=False):
            # Writes: INSERT/UPDATE — simulate failure
            if not fetch or commit:
                raise Exception("Simulated DB write failure")
            # Reads: SELECT — return the original state
            if 'SELECT' in query.upper():
                return [{'is_active': original_state}]
            return []

        mock_db.execute_query.side_effect = mock_execute_query

        service = TenantFunctionService(mock_db)

        # 1. Record the initial state via get_function_state
        initial_state = service.get_function_state(tenant, function_name)
        assert initial_state == original_state

        # 2. Attempt to set a new value — should fail
        result = service.set_function_state(tenant, function_name, new_value, "test@test.com")
        assert result['success'] is False

        # 3. Read state again — should be unchanged
        state_after_failure = service.get_function_state(tenant, function_name)
        assert state_after_failure == initial_state


# ---------------------------------------------------------------------------
# Property 12: Inactive parent module overrides function toggle
# Feature: tenant-optional-functions, Property 12: Inactive parent module overrides function toggle
# Validates: Requirements 6.2, 6.3
# ---------------------------------------------------------------------------

class TestInactiveParentModuleOverride:
    """For any function whose is_active value is true in tenant_functions,
    if the function's parent module is inactive for the tenant, the effective
    state SHALL be false."""

    @settings(max_examples=100, deadline=None)
    @given(
        tenant=tenant_st,
        function_name=function_name_st,
    )
    def test_get_all_functions_effective_false_when_module_inactive(self, tenant, function_name):
        """
        When the DB returns is_active=True for a function but the parent module
        is inactive, the effective state in get_all_functions must be False.

        **Validates: Requirements 6.2, 6.3**
        """
        # Mock DB to return is_active=True for the function override
        mock_db = MagicMock()

        # Build override rows: all functions have is_active=True in the DB
        override_rows = [
            {'function_name': fn, 'is_active': 1}
            for fn in FUNCTION_REGISTRY.keys()
        ]
        mock_db.execute_query.return_value = override_rows

        # Mock has_module to always return False (parent module inactive)
        with patch('services.tenant_function_service.has_module', return_value=False):
            service = TenantFunctionService(mock_db)
            results = service.get_all_functions(tenant)

        # Every function should have effective=False despite is_active=True
        for func in results:
            assert func['is_active'] is True, (
                f"Expected is_active=True for '{func['function_name']}', "
                f"got {func['is_active']}"
            )
            assert func['module_active'] is False, (
                f"Expected module_active=False for '{func['function_name']}', "
                f"got {func['module_active']}"
            )
            assert func['effective'] is False, (
                f"Expected effective=False for '{func['function_name']}' "
                f"(is_active=True but module inactive), got {func['effective']}"
            )

    @settings(max_examples=100, deadline=None)
    @given(
        tenant=tenant_st,
        function_name=function_name_st,
    )
    def test_is_function_enabled_returns_false_when_module_inactive(self, tenant, function_name):
        """
        When the parent module is inactive, is_function_enabled must return
        (False, error_message) regardless of the function's toggle state.

        **Validates: Requirements 6.2, 6.3**
        """
        parent_module = FUNCTION_REGISTRY[function_name]['parent_module']

        # Mock DB to return is_active=True for the function override
        mock_db = MagicMock()
        mock_db.execute_query.return_value = [{'is_active': 1}]

        # Mock has_module to return False (parent module inactive)
        with patch('services.tenant_function_service.has_module', return_value=False):
            service = TenantFunctionService(mock_db)
            enabled, error_msg = service.is_function_enabled(tenant, function_name, parent_module)

        assert enabled is False, (
            f"Expected enabled=False for '{function_name}' with inactive module "
            f"'{parent_module}', but got enabled={enabled}"
        )
        assert error_msg is not None, (
            f"Expected an error message when module is inactive, got None"
        )
        assert parent_module in error_msg, (
            f"Error message should mention the inactive module '{parent_module}', "
            f"got: '{error_msg}'"
        )


# ---------------------------------------------------------------------------
# Property 8: Toggle round-trip persistence
# Feature: tenant-optional-functions, Property 8: Toggle round-trip persistence
# Validates: Requirements 5.2
# ---------------------------------------------------------------------------

class TestToggleRoundTrip:
    """For any valid function name and boolean value, after a successful
    set_function_state(tenant, function_name, is_active), a subsequent
    get_function_state(tenant, function_name) SHALL return the newly set
    is_active value."""

    @settings(max_examples=100, deadline=None)
    @given(
        tenant=tenant_st,
        function_name=function_name_st,
        is_active=st.booleans(),
    )
    def test_get_returns_value_after_successful_set(self, tenant, function_name, is_active):
        """
        After a successful set_function_state, get_function_state returns the new value.

        **Validates: Requirements 5.2**
        """
        # In-memory store simulating the tenant_functions table
        store = {}

        def mock_execute_query(query, params, fetch=True, commit=False):
            if 'INSERT INTO tenant_functions' in query:
                # INSERT ... ON DUPLICATE KEY UPDATE behavior
                # params: (tenant, function_name, is_active, user_email)
                key = (params[0], params[1])
                store[key] = params[2]
                return None
            elif 'SELECT is_active' in query:
                # SELECT from tenant_functions
                key = (params[0], params[1])
                if key in store:
                    return [{'is_active': store[key]}]
                return []
            return []

        mock_db = MagicMock()
        mock_db.execute_query.side_effect = mock_execute_query

        service = TenantFunctionService(mock_db)

        # Write the state
        result = service.set_function_state(tenant, function_name, is_active, "test@test.com")
        assert result['success'] is True, (
            f"set_function_state failed unexpectedly: {result}"
        )

        # Read back the state
        state = service.get_function_state(tenant, function_name)
        assert state == is_active, (
            f"Expected get_function_state to return {is_active} after successful set, "
            f"but got {state} for tenant='{tenant}', function='{function_name}'"
        )


# ---------------------------------------------------------------------------
# Property 11: Module deactivation/re-activation preserves function toggles
# Feature: tenant-optional-functions, Property 11: Module deactivation/re-activation preserves function toggles
# Validates: Requirements 6.1, 6.4
# ---------------------------------------------------------------------------

class TestModuleDeactivationPreservation:
    """For any tenant with function overrides stored in tenant_functions,
    deactivating and then re-activating the parent module SHALL result in
    the same function toggle states being effective as before deactivation —
    no manual re-enablement required."""

    @settings(max_examples=100, deadline=None)
    @given(
        tenant=tenant_st,
        function_name=function_name_st,
        toggle_state=st.booleans(),
    )
    def test_module_deactivation_preserves_toggle_state(self, tenant, function_name, toggle_state):
        """
        Simulates a module deactivation/re-activation cycle and verifies that
        stored function toggle states remain unchanged and become effective again.

        **Validates: Requirements 6.1, 6.4**
        """
        # In-memory store simulating tenant_functions table
        db_store = {}

        def mock_execute_query(query, params, fetch=True, commit=False):
            if 'INSERT INTO tenant_functions' in query:
                # Persist the toggle state
                admin, func_name, is_active, _user = params
                db_store[(admin, func_name)] = is_active
                return None
            elif 'SELECT is_active' in query and 'function_name' in query:
                # Single function lookup
                admin, func_name = params
                if (admin, func_name) in db_store:
                    return [{'is_active': db_store[(admin, func_name)]}]
                return []
            elif 'SELECT function_name, is_active' in query:
                # All functions for tenant
                admin = params[0]
                rows = []
                for (a, fn), active in db_store.items():
                    if a == admin:
                        rows.append({'function_name': fn, 'is_active': active})
                return rows
            return []

        mock_db = MagicMock()
        mock_db.execute_query.side_effect = mock_execute_query

        # Controllable module activation state
        module_active = [True]

        def mock_has_module(db, t, module_name):
            return module_active[0]

        with patch('services.tenant_function_service.has_module', side_effect=mock_has_module):
            service = TenantFunctionService(mock_db)

            # Step 1: Set function state while module is active
            result = service.set_function_state(tenant, function_name, toggle_state, 'test@test.com')
            assert result['success'] is True

            # Step 2: Verify function state with module active
            all_functions_before = service.get_all_functions(tenant)
            func_before = next(f for f in all_functions_before if f['function_name'] == function_name)

            assert func_before['is_active'] == toggle_state
            assert func_before['module_active'] is True
            assert func_before['effective'] == toggle_state  # effective = is_active AND module_active

            # Step 3: Simulate module DEACTIVATION
            module_active[0] = False

            all_functions_deactivated = service.get_all_functions(tenant)
            func_deactivated = next(
                f for f in all_functions_deactivated if f['function_name'] == function_name
            )

            # Req 6.1: is_active is preserved (not modified)
            assert func_deactivated['is_active'] == toggle_state, (
                f"Module deactivation modified is_active: expected {toggle_state}, "
                f"got {func_deactivated['is_active']}"
            )
            # Effective should be False since module is inactive
            assert func_deactivated['module_active'] is False
            assert func_deactivated['effective'] is False

            # Step 4: Simulate module RE-ACTIVATION
            module_active[0] = True

            all_functions_reactivated = service.get_all_functions(tenant)
            func_reactivated = next(
                f for f in all_functions_reactivated if f['function_name'] == function_name
            )

            # Req 6.4: Previously stored toggle states become effective again
            assert func_reactivated['is_active'] == toggle_state, (
                f"Module re-activation modified is_active: expected {toggle_state}, "
                f"got {func_reactivated['is_active']}"
            )
            assert func_reactivated['module_active'] is True
            assert func_reactivated['effective'] == toggle_state, (
                f"After re-activation, effective should equal is_active ({toggle_state}), "
                f"but got {func_reactivated['effective']}"
            )
