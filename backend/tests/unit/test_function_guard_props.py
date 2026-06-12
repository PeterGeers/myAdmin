"""
Property-based tests for Function Guard decorator.

Uses hypothesis to verify correctness properties from the design document.
Feature: tenant-optional-functions

Requirements: 3.1, 3.2, 3.3, 3.4
Reference: .kiro/specs/tenant-optional-functions/design.md
"""

import sys
import os
import flask
from unittest.mock import patch, MagicMock
from hypothesis import given, strategies as st, settings

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from services.function_registry import FUNCTION_REGISTRY
from services.function_guard import function_guard


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Generate random tenant names (non-empty strings that look like tenant identifiers)
tenant_st = st.from_regex(r'^[a-zA-Z][a-zA-Z0-9_]{1,30}$', fullmatch=True)

# Generate function names from the actual FUNCTION_REGISTRY keys
function_name_st = st.sampled_from(list(FUNCTION_REGISTRY.keys()))


# ---------------------------------------------------------------------------
# Property 4: Guard blocks disabled functions
# Feature: tenant-optional-functions, Property 4: Guard blocks disabled functions
# Validates: Requirements 3.1
# ---------------------------------------------------------------------------

class TestGuardBlocksDisabledFunctions:
    """For any function that is disabled for a tenant (function toggle inactive),
    the function_guard decorator SHALL return HTTP 403 without invoking the route handler."""

    @settings(max_examples=100)
    @given(
        tenant=tenant_st,
        function_name=function_name_st,
    )
    def test_guard_returns_403_when_function_disabled(self, tenant, function_name):
        """Guard blocks access and returns 403 when function is disabled for the tenant.

        **Validates: Requirements 3.1**
        """
        # Get the parent module for this function from the registry
        module_name = FUNCTION_REGISTRY[function_name]['parent_module']

        # Track whether the inner function was called
        inner_called = False

        @function_guard(function_name, module_name)
        def mock_route(*args, **kwargs):
            nonlocal inner_called
            inner_called = True
            return {'success': True}, 200

        # Create a Flask app and request context for jsonify to work
        app = flask.Flask(__name__)
        with app.test_request_context():
            mock_db = MagicMock()

            with patch('database.DatabaseManager', return_value=mock_db), \
                 patch('services.module_registry.has_module', return_value=True), \
                 patch('services.tenant_function_service.TenantFunctionService') as mock_service_cls:

                mock_service = MagicMock()
                mock_service.get_function_state.return_value = False
                mock_service_cls.return_value = mock_service

                result = mock_route(tenant=tenant)

                response, status_code = result
                assert status_code == 403
                assert inner_called is False

                response_data = response.get_json()
                assert response_data['success'] is False
                assert function_name in response_data['error']


# ---------------------------------------------------------------------------
# Property 5: Guard passes enabled functions
# Feature: tenant-optional-functions, Property 5: Guard passes enabled functions
# Validates: Requirements 3.2
# ---------------------------------------------------------------------------

class TestGuardPassesEnabledFunctions:
    """For any function that is enabled for a tenant (both function toggle active and
    parent module active), the function_guard decorator SHALL invoke the route handler
    with the original arguments unmodified."""

    @settings(max_examples=100)
    @given(
        tenant=tenant_st,
        function_name=function_name_st,
    )
    def test_guard_invokes_handler_when_function_enabled(self, tenant, function_name):
        """Guard passes through and invokes the route handler with original kwargs
        when both module and function are active.

        **Validates: Requirements 3.2**
        """
        module_name = FUNCTION_REGISTRY[function_name]['parent_module']

        inner_called = False
        received_kwargs = {}
        expected_return = {'success': True, 'data': 'test_result'}

        @function_guard(function_name, module_name)
        def mock_route(*args, **kwargs):
            nonlocal inner_called, received_kwargs
            inner_called = True
            received_kwargs = kwargs
            return expected_return

        app = flask.Flask(__name__)
        with app.test_request_context():
            mock_db = MagicMock()

            with patch('database.DatabaseManager', return_value=mock_db), \
                 patch('services.module_registry.has_module', return_value=True), \
                 patch('services.tenant_function_service.TenantFunctionService') as mock_service_cls:

                mock_service = MagicMock()
                mock_service.get_function_state.return_value = True
                mock_service_cls.return_value = mock_service

                result = mock_route(
                    tenant=tenant,
                    user_email='test@test.com',
                    user_roles=['Tenant_Admin'],
                    user_tenants=[tenant],
                )

                assert inner_called is True
                assert received_kwargs['tenant'] == tenant
                assert received_kwargs['user_email'] == 'test@test.com'
                assert received_kwargs['user_roles'] == ['Tenant_Admin']
                assert received_kwargs['user_tenants'] == [tenant]
                assert result == expected_return



# ---------------------------------------------------------------------------
# Property 6: Guard prioritizes module check over function check
# Feature: tenant-optional-functions, Property 6: Guard prioritizes module check over function check
# Validates: Requirements 3.3, 3.4
# ---------------------------------------------------------------------------

class TestGuardModulePriority:
    """For any function whose parent module is inactive for the tenant,
    the function_guard decorator SHALL return HTTP 403 with an error message
    identifying the inactive module by name, regardless of the function's own toggle state."""

    @settings(max_examples=100)
    @given(
        tenant=tenant_st,
        function_name=function_name_st,
        function_state=st.booleans(),
    )
    def test_guard_returns_module_error_when_module_inactive(
        self, tenant, function_name, function_state
    ):
        """
        Guard prioritizes module check over function check.
        When the parent module is inactive, the response identifies the module
        by name regardless of whether the function itself is enabled or disabled.

        **Validates: Requirements 3.3, 3.4**
        """
        # Get the parent module for this function from the registry
        module_name = FUNCTION_REGISTRY[function_name]['parent_module']

        # Track whether the inner function was called
        inner_called = False

        @function_guard(function_name, module_name)
        def mock_route(*args, **kwargs):
            nonlocal inner_called
            inner_called = True
            return {'success': True}, 200

        # Create a Flask app and request context for jsonify to work
        app = flask.Flask(__name__)
        with app.test_request_context():
            mock_db = MagicMock()

            # Patch at source modules where the local imports resolve from
            with patch('database.DatabaseManager', return_value=mock_db), \
                 patch('services.module_registry.has_module', return_value=False) as mock_has_module, \
                 patch('services.tenant_function_service.TenantFunctionService') as mock_service_cls:

                mock_service = MagicMock()
                # Set function state to a random boolean - proves it doesn't matter
                mock_service.get_function_state.return_value = function_state
                mock_service_cls.return_value = mock_service

                # Call the decorated function with tenant in kwargs
                result = mock_route(tenant=tenant)

                # Assert response is 403
                response, status_code = result
                assert status_code == 403

                # Assert inner function was NOT called
                assert inner_called is False

                # Verify the error message identifies the MODULE name (not the function)
                response_data = response.get_json()
                assert response_data['success'] is False
                assert module_name in response_data['error']

                # Verify has_module was called (module check happened)
                mock_has_module.assert_called_once_with(mock_db, tenant, module_name)

                # Verify TenantFunctionService was NOT used (no function check occurred)
                mock_service.get_function_state.assert_not_called()
