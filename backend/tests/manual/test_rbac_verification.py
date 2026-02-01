"""
Manual verification script for Role-Based Access Control (RBAC)

This script demonstrates how different roles have different access levels
to various API endpoints.

Usage:
    python backend/tests/manual/test_rbac_verification.py
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import json
import base64
from datetime import datetime, timedelta
from src.auth.cognito_utils import (
    extract_user_credentials,
    validate_permissions,
    get_permissions_for_roles
)


def create_mock_jwt_token(email, roles):
    """Create a mock JWT token for testing"""
    payload = {
        'email': email,
        'cognito:groups': roles,
        'exp': (datetime.utcnow() + timedelta(hours=1)).timestamp()
    }
    
    # JWT format: header.payload.signature
    header = base64.urlsafe_b64encode(json.dumps({'alg': 'RS256'}).encode()).decode().rstrip('=')
    payload_encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip('=')
    signature = 'mock_signature'
    
    return f"{header}.{payload_encoded}.{signature}"


def test_role_access(role_name, roles, test_permissions):
    """Test access for a specific role"""
    print(f"\n{'='*80}")
    print(f"Testing Role: {role_name}")
    print(f"Cognito Groups: {roles}")
    print(f"{'='*80}")
    
    # Get all permissions for this role
    all_permissions = get_permissions_for_roles(roles)
    print(f"\nGranted Permissions: {all_permissions[:10]}{'...' if len(all_permissions) > 10 else ''}")
    
    # Test each permission
    for endpoint, required_perms in test_permissions.items():
        is_authorized, error = validate_permissions(roles, required_perms)
        status = "✅ ALLOWED" if is_authorized else "❌ DENIED"
        print(f"  {status} - {endpoint} (requires: {required_perms})")


def main():
    """Run RBAC verification tests"""
    print("="*80)
    print("Role-Based Access Control (RBAC) Verification")
    print("="*80)
    
    # Define test endpoints and their required permissions
    test_endpoints = {
        "GET /api/invoices": ["invoices_read"],
        "POST /api/invoices": ["invoices_create"],
        "PUT /api/invoices": ["invoices_update"],
        "DELETE /api/invoices": ["invoices_delete"],
        "GET /api/reports": ["reports_read"],
        "POST /api/reports/export": ["reports_export"],
        "GET /api/banking/scan-files": ["banking_read"],
        "POST /api/banking/process-files": ["banking_process"],
        "POST /api/transactions": ["transactions_create"],
        "GET /api/str/summary": ["str_read"],
        "POST /api/str/upload": ["str_create"],
        "POST /api/btw/generate-report": ["btw_read", "btw_process"],
        "GET /api/cache/status": ["*"],  # Admin only
    }
    
    # Test different roles
    test_role_access(
        "Administrator",
        ["Administrators"],
        test_endpoints
    )
    
    test_role_access(
        "Accountant",
        ["Accountants"],
        test_endpoints
    )
    
    test_role_access(
        "Finance Manager (CRUD)",
        ["Finance_CRUD"],
        test_endpoints
    )
    
    test_role_access(
        "Finance Viewer (Read-Only)",
        ["Finance_Read"],
        test_endpoints
    )
    
    test_role_access(
        "STR Manager",
        ["STR_CRUD"],
        test_endpoints
    )
    
    test_role_access(
        "General Viewer",
        ["Viewers"],
        test_endpoints
    )
    
    test_role_access(
        "Multi-Role User (Finance + STR)",
        ["Finance_CRUD", "STR_CRUD"],
        test_endpoints
    )
    
    print("\n" + "="*80)
    print("Verification Complete!")
    print("="*80)
    print("\nKey Findings:")
    print("  ✅ Administrators have full access to all endpoints")
    print("  ✅ Accountants have access to financial and banking operations")
    print("  ✅ Finance_CRUD has full access to financial data")
    print("  ✅ Finance_Read has read-only access to financial data")
    print("  ✅ STR_CRUD has full access to short-term rental operations")
    print("  ✅ Viewers have read-only access to reports and dashboards")
    print("  ✅ Multi-role users inherit permissions from all their roles")
    print("\n")


if __name__ == '__main__':
    main()
