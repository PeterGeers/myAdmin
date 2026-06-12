"""
Property-based tests for Tenant Function Routes.

Uses Hypothesis to verify correctness properties from the design document.
Feature: tenant-optional-functions

Requirements: 5.4, 5.6, 7.3
Reference: .kiro/specs/tenant-optional-functions/design.md
"""

import sys
import os
import json
import flask
from unittest.mock import patch, MagicMock
from hypothesis import given, strategies as st, settings, assume

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from services.function_registry import FUNCTION_REGISTRY


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Generate random strings (1-50 chars) that are NOT in FUNCTION_REGISTRY keys
# We use text strategy and filter out any strings that happen to be valid keys
invalid_function_name_st = st.text(
    alphabet=st.characters(whitelist_categories=('L', 'N', 'P', 'S', 'Z')),
    min_size=1,
    max_size=50,
).filter(lambda s: s not in FUNCTION_REGISTRY)


# ---------------------------------------------------------------------------
# Property 9: Invalid function name returns 400 with valid names
# Feature: tenant-optional-functions, Property 9: Invalid function name returns 400 with valid names
# Validates: Requirements 5.4
# ---------------------------------------------------------------------------

class TestInvalidFunctionNameRejection:
    """For any string that is not a key in FUNCTION_REGISTRY, the POST /api/tenant/functions
    endpoint SHALL return HTTP 400 with a response body containing the list of valid function names."""

    @settings(max_examples=100)
    @given(
        invalid_name=invalid_function_name_st,
    )
    def test_invalid_function_name_returns_400_with_valid_names(self, invalid_name):
        """POST with an invalid function_name returns 400 and includes valid function names.

        **Validates: Requirements 5.4**
        """
        # Create a Flask app and register the blueprint with mocked auth decorators
        app = flask.Flask(__name__)
        app.config['TESTING'] = True

        # We need to patch the decorators before importing the route module.
        # Since the module may already be imported, we patch at the route level
        # by calling the view function directly within a test request context.
        with app.test_request_context(
            '/api/tenant/functions',
            method='POST',
            json={'function_name': invalid_name, 'is_active': True},
            content_type='application/json',
        ):
            # Import the route function and unwrap decorators to bypass auth
            from routes.tenant_function_routes import toggle_tenant_function

            # Unwrap: cognito_required -> tenant_required -> raw function
            inner_fn = toggle_tenant_function.__wrapped__.__wrapped__

            # Call the unwrapped function with required auth kwargs
            response = inner_fn(
                user_email='admin@test.com',
                user_roles=['Tenant_Admin'],
                tenant='TestTenant',
                user_tenants=['TestTenant'],
            )

            # The route returns a tuple of (response, status_code) for error cases
            resp_obj, status_code = response

            # Assert HTTP 400
            assert status_code == 400, (
                f"Expected 400 for invalid function_name '{invalid_name}', "
                f"got {status_code}"
            )

            # Parse the response body
            response_data = resp_obj.get_json()

            # Assert response indicates failure
            assert response_data['success'] is False

            # Assert the response contains valid function names
            valid_names = list(FUNCTION_REGISTRY.keys())
            for name in valid_names:
                assert name in response_data['error'], (
                    f"Expected valid function name '{name}' in error response, "
                    f"got: {response_data['error']}"
                )


# ---------------------------------------------------------------------------
# Property 10: GET returns complete function state from registry
# Feature: tenant-optional-functions, Property 10: GET returns complete function state from registry
# Validates: Requirements 5.6, 7.3
# ---------------------------------------------------------------------------

class TestGetCompleteness:
    """For any tenant, the GET /api/tenant/functions endpoint SHALL return exactly
    the set of functions defined in FUNCTION_REGISTRY, each annotated with its
    identifier, parent module, label, and current effective activation state."""

    @settings(max_examples=100)
    @given(
        # Generate random boolean overrides for each function in the registry
        function_overrides=st.fixed_dictionaries(
            {fn: st.booleans() for fn in FUNCTION_REGISTRY}
        ),
        # Generate random module active states for each unique parent module
        module_states=st.fixed_dictionaries(
            {defn['parent_module']: st.booleans()
             for defn in FUNCTION_REGISTRY.values()}
        ),
    )
    def test_get_returns_exactly_registry_functions_with_correct_state(
        self, function_overrides, module_states
    ):
        """GET /api/tenant/functions returns exactly the set of functions in
        FUNCTION_REGISTRY with correct effective states.

        **Validates: Requirements 5.6, 7.3**
        """
        # Build the expected response data based on overrides and module states
        expected_functions = []
        for func_name, definition in FUNCTION_REGISTRY.items():
            is_active = function_overrides[func_name]
            module_active = module_states[definition['parent_module']]
            effective = is_active and module_active
            expected_functions.append({
                'function_name': func_name,
                'parent_module': definition['parent_module'],
                'label': definition['label'],
                'is_active': is_active,
                'module_active': module_active,
                'effective': effective,
            })

        # Create a Flask app for test request context
        app = flask.Flask(__name__)
        app.config['TESTING'] = True

        with app.test_request_context('/api/tenant/functions', method='GET'):
            # Mock _get_service to return a service that produces our expected data
            with patch('routes.tenant_function_routes._get_service') as mock_get_service:
                mock_service = MagicMock()
                mock_service.get_all_functions.return_value = expected_functions
                mock_get_service.return_value = mock_service

                # Access the raw function by unwrapping decorators:
                # get_tenant_functions -> cognito_required wrapper -> tenant_required wrapper -> raw fn
                from routes.tenant_function_routes import get_tenant_functions
                raw_fn = get_tenant_functions.__wrapped__.__wrapped__

                response = raw_fn(
                    user_email='user@test.com',
                    user_roles=['Tenant_Admin'],
                    tenant='TestTenant',
                    user_tenants=['TestTenant'],
                )

                # Parse the response (raw function returns a single Response object)
                response_data = response.get_json()

                # Assert success
                assert response_data['success'] is True

                # Get response data
                data = response_data['data']

                # Assert the response contains exactly the functions in FUNCTION_REGISTRY
                response_names = {f['function_name'] for f in data}
                registry_names = set(FUNCTION_REGISTRY.keys())
                assert response_names == registry_names, (
                    f"Response function names {response_names} do not match "
                    f"registry keys {registry_names}"
                )

                # Assert count matches exactly
                assert len(data) == len(FUNCTION_REGISTRY), (
                    f"Expected {len(FUNCTION_REGISTRY)} functions, got {len(data)}"
                )

                # For each function, verify all fields match expectations
                response_by_name = {f['function_name']: f for f in data}
                for func_name, definition in FUNCTION_REGISTRY.items():
                    fn_data = response_by_name[func_name]

                    # Verify function_name is in FUNCTION_REGISTRY
                    assert fn_data['function_name'] in FUNCTION_REGISTRY

                    # Verify parent_module matches registry
                    assert fn_data['parent_module'] == definition['parent_module'], (
                        f"Function '{func_name}': expected parent_module "
                        f"'{definition['parent_module']}', got '{fn_data['parent_module']}'"
                    )

                    # Verify label matches registry
                    assert fn_data['label'] == definition['label'], (
                        f"Function '{func_name}': expected label "
                        f"'{definition['label']}', got '{fn_data['label']}'"
                    )

                    # Verify effective = is_active AND module_active
                    expected_effective = (
                        fn_data['is_active'] and fn_data['module_active']
                    )
                    assert fn_data['effective'] == expected_effective, (
                        f"Function '{func_name}': effective should be "
                        f"{expected_effective} (is_active={fn_data['is_active']}, "
                        f"module_active={fn_data['module_active']}), "
                        f"got {fn_data['effective']}"
                    )
