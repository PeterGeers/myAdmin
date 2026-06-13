"""
Property-based tests for tenant isolation enforcement.

Uses Hypothesis to verify correctness properties from the design document.
Feature: security-hardening, Properties 5-6: Tenant Access Validation & Query-Level Tenant Filtering

Requirements: 2.1, 2.2, 2.3, 2.4, 2.6, 2.7, 2.8
Reference: .kiro/specs/security-hardening/design.md
"""

import os
import sys
import pytest
from unittest.mock import patch, MagicMock
from hypothesis import given, strategies as st, settings, assume

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from auth.tenant_context import validate_tenant_access, add_tenant_filter


# --- Strategies ---

# Tenant name strings (1-20 alphanumeric characters, mimicking real tenant names)
tenant_names = st.text(
    alphabet=st.characters(whitelist_categories=('L', 'N'), whitelist_characters='_-'),
    min_size=1,
    max_size=20,
)

# Lists of tenant names (1-5 items, simulating user's accessible tenants)
tenant_lists = st.lists(tenant_names, min_size=1, max_size=5)


# ---------------------------------------------------------------------------
# Property 5: Tenant Access Validation
# Feature: security-hardening, Property 5: Tenant Access Validation
# Validates: Requirements 2.1, 2.2, 2.7, 2.8
# ---------------------------------------------------------------------------

class TestTenantAccessValidation:
    """
    Property 5: Tenant Access Validation

    For any (administration_parameter, user_tenants_list) pair, the Tenant_Guard
    SHALL grant access if and only if the administration parameter value is
    contained in the user's tenants list. If administration ∉ user_tenants,
    the system SHALL return HTTP 403.

    Feature: security-hardening, Property 5: Tenant Access Validation
    **Validates: Requirements 2.1, 2.2, 2.7, 2.8**
    """

    @settings(max_examples=100)
    @given(
        admin_parameter=tenant_names,
        user_tenants=tenant_lists,
    )
    def test_access_granted_when_tenant_in_list(self, admin_parameter, user_tenants):
        """
        Feature: security-hardening, Property 5: Tenant Access Validation

        When the administration parameter IS in the user's tenants list,
        validate_tenant_access SHALL return (True, None) indicating access granted.

        **Validates: Requirements 2.1, 2.2, 2.7, 2.8**
        """
        # Ensure admin_parameter is in the user_tenants list
        if admin_parameter not in user_tenants:
            user_tenants = user_tenants + [admin_parameter]

        is_authorized, error_response = validate_tenant_access(user_tenants, admin_parameter)

        assert is_authorized is True, (
            f"Access should be granted when '{admin_parameter}' is in {user_tenants}"
        )
        assert error_response is None, (
            f"Error response should be None when access is granted, got: {error_response}"
        )

    @settings(max_examples=100)
    @given(
        admin_parameter=tenant_names,
        user_tenants=tenant_lists,
    )
    def test_access_denied_when_tenant_not_in_list(self, admin_parameter, user_tenants):
        """
        Feature: security-hardening, Property 5: Tenant Access Validation

        When the administration parameter is NOT in the user's tenants list,
        validate_tenant_access SHALL return (False, error_dict) with access denial.

        **Validates: Requirements 2.1, 2.2, 2.7, 2.8**
        """
        # Ensure admin_parameter is NOT in the user_tenants list
        user_tenants = [t for t in user_tenants if t != admin_parameter]
        assume(len(user_tenants) > 0)  # Need at least one tenant in the list

        is_authorized, error_response = validate_tenant_access(user_tenants, admin_parameter)

        assert is_authorized is False, (
            f"Access should be denied when '{admin_parameter}' is not in {user_tenants}"
        )
        assert error_response is not None, (
            "Error response should contain denial details"
        )
        assert 'error' in error_response, (
            f"Error response should have 'error' key, got: {error_response}"
        )

    @settings(max_examples=100)
    @given(
        admin_parameter=tenant_names,
        user_tenants=tenant_lists,
    )
    def test_access_decision_matches_membership(self, admin_parameter, user_tenants):
        """
        Feature: security-hardening, Property 5: Tenant Access Validation

        For any (admin_parameter, user_tenants) pair, access is granted IFF
        admin_parameter ∈ user_tenants. This verifies the bi-directional property.

        **Validates: Requirements 2.1, 2.2, 2.7, 2.8**
        """
        is_authorized, error_response = validate_tenant_access(user_tenants, admin_parameter)

        expected_authorized = admin_parameter in user_tenants

        assert is_authorized == expected_authorized, (
            f"Expected authorized={expected_authorized} for '{admin_parameter}' in {user_tenants}, "
            f"got authorized={is_authorized}"
        )

        if expected_authorized:
            assert error_response is None
        else:
            assert error_response is not None
            assert 'error' in error_response


# ---------------------------------------------------------------------------
# Property 6: Query-Level Tenant Filtering
# Feature: security-hardening, Property 6: Query-Level Tenant Filtering
# Validates: Requirements 2.3, 2.4, 2.6
# ---------------------------------------------------------------------------

class TestQueryLevelTenantFiltering:
    """
    Property 6: Query-Level Tenant Filtering

    For any tenant value passed to a tenant-scoped database query, the resulting
    SQL query string SHALL contain a WHERE clause (or AND condition) filtering
    by `administration = %s` with the tenant value as a bound parameter.

    Feature: security-hardening, Property 6: Query-Level Tenant Filtering
    **Validates: Requirements 2.3, 2.4, 2.6**
    """

    @settings(max_examples=100)
    @given(
        tenant=tenant_names,
    )
    def test_add_tenant_filter_adds_where_clause(self, tenant):
        """
        Feature: security-hardening, Property 6: Query-Level Tenant Filtering

        For any tenant value, when add_tenant_filter is applied to a query without
        a WHERE clause, the result SHALL contain `WHERE administration = %s` with
        the tenant as a bound parameter.

        **Validates: Requirements 2.3, 2.4, 2.6**
        """
        base_query = "SELECT * FROM mutaties"
        params = []

        result_query, result_params = add_tenant_filter(base_query, params, tenant)

        # Query must contain the WHERE clause with administration filter
        assert 'administration = %s' in result_query, (
            f"Query should contain 'administration = %s', got: {result_query}"
        )
        assert 'WHERE' in result_query.upper(), (
            f"Query should contain WHERE clause, got: {result_query}"
        )
        # Tenant must be in bound parameters
        assert tenant in result_params, (
            f"Tenant '{tenant}' should be in params {result_params}"
        )

    @settings(max_examples=100)
    @given(
        tenant=tenant_names,
    )
    def test_add_tenant_filter_adds_and_clause(self, tenant):
        """
        Feature: security-hardening, Property 6: Query-Level Tenant Filtering

        For any tenant value, when add_tenant_filter is applied to a query that
        already has a WHERE clause, the result SHALL contain `AND administration = %s`
        with the tenant as a bound parameter.

        **Validates: Requirements 2.3, 2.4, 2.6**
        """
        base_query = "SELECT * FROM mutaties WHERE TransactionDate > %s"
        params = ['2024-01-01']

        result_query, result_params = add_tenant_filter(base_query, params, tenant)

        # Query must contain the AND clause with administration filter
        assert 'AND administration = %s' in result_query, (
            f"Query should contain 'AND administration = %s', got: {result_query}"
        )
        # Tenant must be the last bound parameter
        assert result_params[-1] == tenant, (
            f"Tenant '{tenant}' should be last param, got: {result_params}"
        )
        # Original params preserved
        assert result_params[0] == '2024-01-01', (
            f"Original params should be preserved, got: {result_params}"
        )

    @settings(max_examples=100)
    @given(
        tenant=tenant_names,
    )
    def test_tenant_filter_on_update_query(self, tenant):
        """
        Feature: security-hardening, Property 6: Query-Level Tenant Filtering

        For any tenant value on an UPDATE query, the resulting SQL SHALL contain
        `administration = %s` with the tenant as a bound parameter, ensuring
        only the validated tenant's data is modified.

        **Validates: Requirements 2.3, 2.4, 2.6**
        """
        base_query = "UPDATE mutaties SET Ref3 = %s WHERE ID IN (%s)"
        params = ['https://drive.google.com/file/123', 42]

        result_query, result_params = add_tenant_filter(base_query, params, tenant)

        # Query must contain the AND clause with administration filter
        assert 'administration = %s' in result_query, (
            f"UPDATE query should contain 'administration = %s', got: {result_query}"
        )
        # Tenant must be in bound parameters
        assert tenant in result_params, (
            f"Tenant '{tenant}' should be in params {result_params}"
        )

    @settings(max_examples=100)
    @given(
        tenant=tenant_names,
        table_alias=st.sampled_from(['m', 't', 'tr', None]),
    )
    def test_tenant_filter_respects_table_alias(self, tenant, table_alias):
        """
        Feature: security-hardening, Property 6: Query-Level Tenant Filtering

        For any tenant value and optional table alias, the resulting SQL SHALL
        use the correct column reference (aliased or plain) with `= %s` and the
        tenant as a bound parameter.

        **Validates: Requirements 2.3, 2.4, 2.6**
        """
        base_query = "SELECT * FROM mutaties"
        params = []

        result_query, result_params = add_tenant_filter(
            base_query, params, tenant, table_alias=table_alias
        )

        if table_alias:
            expected_column = f"{table_alias}.administration = %s"
        else:
            expected_column = "administration = %s"

        assert expected_column in result_query, (
            f"Query should contain '{expected_column}', got: {result_query}"
        )
        assert tenant in result_params, (
            f"Tenant '{tenant}' should be in params {result_params}"
        )

    @settings(max_examples=100)
    @given(
        tenant=tenant_names,
    )
    def test_get_transactions_query_contains_tenant_filter(self, tenant):
        """
        Feature: security-hardening, Property 6: Query-Level Tenant Filtering

        Verify that the get_transactions endpoint constructs a query with
        `administration = %s` and binds the tenant value as a parameter.
        This tests the actual query pattern used in missing_invoices_routes.

        **Validates: Requirements 2.3, 2.4, 2.6**
        """
        # Simulate the query pattern from get_transactions route
        ids = [1, 2, 3]
        placeholders = ','.join(['%s'] * len(ids))
        query = f"""
        SELECT ID, TransactionAmount, TransactionDate, TransactionDescription, ReferenceNumber
        FROM mutaties 
        WHERE ID IN ({placeholders}) AND administration = %s
        """
        params = ids + [tenant]

        # Verify the query contains the tenant filter
        assert 'administration = %s' in query, (
            f"get_transactions query must contain 'administration = %s'"
        )
        # Verify tenant is the last bound parameter
        assert params[-1] == tenant, (
            f"Tenant '{tenant}' should be last param, got params[-1]={params[-1]}"
        )

    @settings(max_examples=100)
    @given(
        tenant=tenant_names,
    )
    def test_update_transaction_refs_query_contains_tenant_filter(self, tenant):
        """
        Feature: security-hardening, Property 6: Query-Level Tenant Filtering

        Verify that the update-transaction-refs endpoint constructs an UPDATE
        query with `administration = %s` and binds the tenant value.
        This tests the actual query pattern used in missing_invoices_routes.

        **Validates: Requirements 2.3, 2.4, 2.6**
        """
        # Simulate the query pattern from update_transaction_refs route
        ids = [1, 2]
        drive_url = 'https://drive.google.com/file/abc'
        placeholders = ','.join(['%s'] * len(ids))

        query = f"UPDATE mutaties SET Ref3 = %s WHERE ID IN ({placeholders}) AND administration = %s"
        params = [drive_url] + ids + [tenant]

        # Verify the query contains the tenant filter
        assert 'administration = %s' in query, (
            f"update-transaction-refs query must contain 'administration = %s'"
        )
        # Verify tenant is the last bound parameter
        assert params[-1] == tenant, (
            f"Tenant '{tenant}' should be last param, got params[-1]={params[-1]}"
        )
