"""
Working tenant filtering tests using proper authentication.

Post-S2 (T5/T7) reality: the Flask plane trusts identity ONLY from a
cryptographically **verified** token. An unsigned/base64-only bearer token is no
longer decoded — the T5 verifier rejects it with 401. So these tests drive the
authenticated path the way it works in production: they install a fake
``JWTVerifier`` at the ``cognito_utils._get_jwt_verifier`` seam that returns the
*verified* claims (email, ``cognito:groups``, ``custom:tenants``). This is the same
pattern used by the T7 header-trust tests (``test_s2_header_trust.py``).

Because both the credential extraction (``extract_user_credentials``) and the tenant
list (``get_verified_tenants``) route through that single seam, one fake verifier
gives a consistent verified identity for auth + tenant scoping. Per-tenant roles are
resolved from the DB (``role_cache.get_tenant_roles``); that lookup is stubbed here
so the tests exercise tenant *filtering*, not DB role plumbing.

No unverified header is ever a source of truth: ``X-Tenant`` is only a selector,
validated against the verified ``custom:tenants`` list.
"""

import pytest
import json
import base64
from contextlib import contextmanager
from unittest.mock import patch, MagicMock
from flask import Flask
from bnb_routes import bnb_bp
from str_channel_routes import str_channel_bp
from str_invoice_routes import str_invoice_bp


class _FakeVerifier:
    """Stand-in JWTVerifier: returns the VERIFIED claims for a known token string.

    The verifier is the source of truth (never headers / never base64). A test hands
    us the exact verified payload a real signed token would produce; unknown tokens
    raise, mirroring a rejected signature.
    """

    def __init__(self, claims_by_token):
        self._claims_by_token = claims_by_token

    def verify_token(self, token):
        from auth.jwt_verifier import InvalidTokenError

        if token in self._claims_by_token:
            return self._claims_by_token[token]
        raise InvalidTokenError("invalid signature")


@contextmanager
def _verified_identity(*, token, email, tenants, tenant_roles):
    """Install a verified identity for ``token`` across the auth seams.

    * ``cognito_utils._get_jwt_verifier`` -> fake verifier yielding the given
      email / groups / custom:tenants (drives both auth and the tenant list).
    * ``auth.role_cache.get_tenant_roles`` -> the caller's per-tenant roles, so the
      permission check passes without a real DB.
    """
    from auth import cognito_utils, role_cache

    payload = {
        "sub": "test-user-id",
        "email": email,
        "cognito:groups": list(tenant_roles),
        "custom:tenants": list(tenants),
    }
    fake = _FakeVerifier({token: payload})

    with patch.object(cognito_utils, "_get_jwt_verifier", return_value=fake), \
        patch.object(role_cache, "get_tenant_roles", return_value=list(tenant_roles)):
        yield


class TestTenantFilteringWithAuth:
    """Test tenant filtering with proper (verified-JWT) authentication"""

    @pytest.fixture
    def app(self):
        """Create Flask app with all blueprints for testing"""
        app = Flask(__name__)
        app.config['TESTING'] = True
        app.register_blueprint(bnb_bp, url_prefix='/api/bnb')
        app.register_blueprint(str_channel_bp, url_prefix='/api/str-channel')
        app.register_blueprint(str_invoice_bp, url_prefix='/api/str-invoice')
        return app

    @pytest.fixture
    def client(self, app):
        """Create test client"""
        return app.test_client()

    def make_bearer(self, email):
        """An opaque bearer string; its trust comes from the fake verifier, not its bytes.

        Deliberately NOT a decodable base64 JWT — proving the verified path never
        relies on reading the token body (verified-JWT-only, no base64 trust).
        """
        return f"verified-token-for-{email}"

    @patch('bnb_routes.DatabaseManager')
    def test_bnb_listing_data_with_valid_auth(self, mock_db_manager, client):
        """BNB listing data with a VERIFIED token + tenant filtering passes auth."""
        token = self.make_bearer("test@example.com")

        # Mock database operations
        mock_db = MagicMock()
        mock_conn = MagicMock()
        mock_cursor = MagicMock()

        mock_db_manager.return_value = mock_db
        mock_db.get_connection.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor

        # Mock successful query result
        mock_cursor.fetchall.return_value = [
            {'listing': 'Test Property', 'administration': 'PeterPrive', 'revenue': 1000}
        ]

        with _verified_identity(
            token=token,
            email="test@example.com",
            tenants=["PeterPrive"],
            tenant_roles=["STR_Read"],
        ):
            response = client.get(
                '/api/bnb/bnb-listing-data',
                headers={
                    'Authorization': f'Bearer {token}',
                    'X-Tenant': 'PeterPrive',
                    'Content-Type': 'application/json'
                }
            )

        # Verified caller: past auth (200) or a downstream server error (500),
        # but NOT an auth error (401/403).
        assert response.status_code in [200, 500]

        if response.status_code == 200:
            data = json.loads(response.data)
            assert data.get('success') is True

    @patch('str_invoice_routes.DatabaseManager')
    def test_str_search_booking_with_valid_auth(self, mock_db_manager, client):
        """STR search booking with a VERIFIED token + tenant filtering passes auth."""
        token = self.make_bearer("test@example.com")

        # Mock database operations
        mock_db = MagicMock()
        mock_conn = MagicMock()
        mock_cursor = MagicMock()

        mock_db_manager.return_value = mock_db
        mock_db.get_connection.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor

        # Mock successful query result
        mock_cursor.fetchall.return_value = [
            {
                'reservationCode': 'TEST123',
                'guestName': 'Test Guest',
                'administration': 'PeterPrive',
                'checkinDate': '2024-01-15'
            }
        ]

        with _verified_identity(
            token=token,
            email="test@example.com",
            tenants=["PeterPrive"],
            tenant_roles=["STR_Read"],
        ):
            response = client.get(
                '/api/str-invoice/search-booking?query=test',
                headers={
                    'Authorization': f'Bearer {token}',
                    'X-Tenant': 'PeterPrive',
                    'Content-Type': 'application/json'
                }
            )

        # Should succeed (200) or fail with server error (500) but not auth error (401/403)
        assert response.status_code in [200, 500]

        if response.status_code == 200:
            data = json.loads(response.data)
            assert data.get('success') is True
            assert 'bookings' in data

    def test_unauthorized_access_blocked(self, client):
        """Requests without an Authorization header are blocked (401)."""
        # Make request without Authorization header
        response = client.get('/api/bnb/bnb-listing-data')

        # Should return 401 (unauthorized)
        assert response.status_code == 401
        data = json.loads(response.data)
        assert 'error' in data

    def test_unsigned_base64_token_rejected(self, client):
        """A base64-only (unsigned) token is NOT trusted — verified-JWT-only (401).

        This is the S2 T5 guarantee: with the verifier active, an attacker-crafted
        base64 payload claiming broad tenant/role access is rejected outright.
        """
        from auth import cognito_utils

        header = base64.urlsafe_b64encode(
            json.dumps({"alg": "RS256", "kid": "x"}).encode()
        ).decode().rstrip('=')
        body = base64.urlsafe_b64encode(
            json.dumps({
                "email": "attacker@example.com",
                "cognito:groups": ["Administrators"],
                "custom:tenants": ["PeterPrive", "GoodwinSolutions"],
            }).encode()
        ).decode().rstrip('=')
        forged = f"{header}.{body}.not-a-real-signature"

        class _RejectingVerifier:
            def verify_token(self, token):
                from auth.jwt_verifier import InvalidTokenError
                raise InvalidTokenError("invalid signature")

        with patch.object(
            cognito_utils, "_get_jwt_verifier", return_value=_RejectingVerifier()
        ):
            response = client.get(
                '/api/bnb/bnb-listing-data',
                headers={
                    'Authorization': f'Bearer {forged}',
                    'X-Tenant': 'PeterPrive',
                    'Content-Type': 'application/json'
                }
            )

        assert response.status_code == 401

    def test_invalid_tenant_access_blocked(self, client):
        """A verified caller selecting a tenant outside their list is blocked (403)."""
        token = self.make_bearer("test@example.com")

        # Verified token authorizes PeterPrive only; caller selects GoodwinSolutions.
        with _verified_identity(
            token=token,
            email="test@example.com",
            tenants=["PeterPrive"],
            tenant_roles=["STR_Read"],
        ):
            response = client.get(
                '/api/bnb/bnb-listing-data',
                headers={
                    'Authorization': f'Bearer {token}',
                    'X-Tenant': 'GoodwinSolutions',  # Unauthorized tenant
                    'Content-Type': 'application/json'
                }
            )

        # Should return 403 (forbidden) — tenant not in the VERIFIED custom:tenants.
        assert response.status_code == 403
        data = json.loads(response.data)
        assert 'error' in data
        assert 'Access denied to tenant' in data['error']

    def test_multi_tenant_user_access(self, client):
        """A verified multi-tenant user can select any tenant in their list."""
        token = self.make_bearer("multi@example.com")

        with _verified_identity(
            token=token,
            email="multi@example.com",
            tenants=["PeterPrive", "GoodwinSolutions"],
            tenant_roles=["STR_Read"],
        ):
            response1 = client.get(
                '/api/bnb/bnb-listing-data',
                headers={
                    'Authorization': f'Bearer {token}',
                    'X-Tenant': 'PeterPrive',
                    'Content-Type': 'application/json'
                }
            )
            response2 = client.get(
                '/api/bnb/bnb-listing-data',
                headers={
                    'Authorization': f'Bearer {token}',
                    'X-Tenant': 'GoodwinSolutions',
                    'Content-Type': 'application/json'
                }
            )

        # Both should succeed or fail with server error (but not auth error)
        assert response1.status_code in [200, 500]
        assert response2.status_code in [200, 500]

    def test_role_based_access_control(self, client):
        """Role-based access control works for a VERIFIED caller with STR_Read."""
        token = self.make_bearer("reader@example.com")

        with _verified_identity(
            token=token,
            email="reader@example.com",
            tenants=["PeterPrive"],
            tenant_roles=["STR_Read"],
        ):
            response = client.get(
                '/api/bnb/bnb-listing-data',
                headers={
                    'Authorization': f'Bearer {token}',
                    'X-Tenant': 'PeterPrive',
                    'Content-Type': 'application/json'
                }
            )

        # Should succeed or fail with server error (but not permission error)
        assert response.status_code in [200, 500]


class TestTenantFilteringLogic:
    """Test the core tenant filtering logic without HTTP requests"""
    
    def test_tenant_sql_filter_generation(self):
        """Test SQL filter generation for tenant filtering"""
        from auth.tenant_context import add_tenant_filter
        
        # Test basic query
        query = "SELECT * FROM mutaties"
        params = []
        
        filtered_query, filtered_params = add_tenant_filter(query, params, "PeterPrive")
        
        assert "WHERE administration = %s" in filtered_query
        assert "PeterPrive" in filtered_params
        
        # Test query with existing WHERE clause
        query = "SELECT * FROM mutaties WHERE TransactionDate > %s"
        params = ["2024-01-01"]
        
        filtered_query, filtered_params = add_tenant_filter(query, params, "PeterPrive")
        
        assert "AND administration = %s" in filtered_query
        assert len(filtered_params) == 2
        assert filtered_params[0] == "2024-01-01"
        assert filtered_params[1] == "PeterPrive"
    
    def test_tenant_access_validation(self):
        """Test tenant access validation logic"""
        from auth.tenant_context import validate_tenant_access
        
        user_tenants = ["PeterPrive", "GoodwinSolutions"]
        
        # Test valid access
        is_authorized, error = validate_tenant_access(user_tenants, "PeterPrive")
        assert is_authorized is True
        assert error is None
        
        # Test invalid access
        is_authorized, error = validate_tenant_access(user_tenants, "UnauthorizedTenant")
        assert is_authorized is False
        assert error is not None
        assert "Access denied to tenant" in error['error']
        
        # Test missing tenant
        is_authorized, error = validate_tenant_access(user_tenants, None)
        assert is_authorized is False
        assert error is not None
        assert "No tenant specified" in error['error']
    
    def test_jwt_tenant_extraction(self):
        """Tenant extraction via the base64 fallback (verifier absent, local dev).

        When no Cognito verifier is configured, ``get_user_tenants`` reads the
        base64 body — the documented local-dev/test fallback (see
        ``test_s2_header_trust.py``). With a verifier present, an unsigned token
        would instead be rejected; that verified-JWT-only behaviour is covered by
        ``test_unsigned_base64_token_rejected``.
        """
        from auth import cognito_utils
        from auth.tenant_context import get_user_tenants

        # Create a test JWT token
        header = {"alg": "RS256", "typ": "JWT"}
        payload = {
            "email": "test@example.com",
            "custom:tenants": json.dumps(["PeterPrive", "GoodwinSolutions"])
        }

        header_encoded = base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip('=')
        payload_encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip('=')

        jwt_token = f"{header_encoded}.{payload_encoded}.signature"

        # Extract tenants via the no-verifier fallback path.
        with patch.object(cognito_utils, "_get_jwt_verifier", return_value=None):
            tenants = get_user_tenants(jwt_token)

        assert len(tenants) == 2
        assert "PeterPrive" in tenants
        assert "GoodwinSolutions" in tenants


def test_comprehensive_tenant_filtering_integration():
    """Comprehensive integration test of tenant filtering system"""
    print("\n" + "="*70)
    print("COMPREHENSIVE TENANT FILTERING INTEGRATION TEST")
    print("="*70)
    
    # Test 1: JWT Token Structure (a Cognito-shaped payload, base64-encoded)
    print("1. Testing JWT token creation and parsing...")
    header = base64.urlsafe_b64encode(
        json.dumps({"alg": "RS256", "typ": "JWT", "kid": "test-key-id"}).encode()
    ).decode().rstrip('=')
    body = base64.urlsafe_b64encode(
        json.dumps({
            "email": "test@example.com",
            "cognito:groups": ["STR_Read"],
            "custom:tenants": json.dumps(["PeterPrive", "GoodwinSolutions"]),
        }).encode()
    ).decode().rstrip('=')
    token = f"{header}.{body}.signature"

    # Verify token structure
    parts = token.split('.')
    assert len(parts) == 3, "JWT should have 3 parts"
    print("✅ JWT token structure valid")

    # Test 2: Tenant extraction via the no-verifier fallback (local dev/test path)
    print("2. Testing tenant extraction from JWT (base64 fallback)...")
    from auth import cognito_utils
    from auth.tenant_context import get_user_tenants
    with patch.object(cognito_utils, "_get_jwt_verifier", return_value=None):
        tenants = get_user_tenants(token)
    assert len(tenants) >= 1, "Should extract at least one tenant"
    print(f"✅ Extracted tenants: {tenants}")
    
    # Test 3: SQL filter generation
    print("3. Testing SQL filter generation...")
    from auth.tenant_context import add_tenant_filter
    query = "SELECT * FROM mutaties"
    filtered_query, params = add_tenant_filter(query, [], "PeterPrive")
    assert "administration = %s" in filtered_query
    assert "PeterPrive" in params
    print("✅ SQL filter generation working")
    
    # Test 4: Access validation
    print("4. Testing access validation...")
    from auth.tenant_context import validate_tenant_access
    is_authorized, error = validate_tenant_access(["PeterPrive"], "PeterPrive")
    assert is_authorized is True
    print("✅ Access validation working")
    
    # Test 5: Role-based permissions
    print("5. Testing role-based permissions...")
    from auth.cognito_utils import get_permissions_for_roles
    permissions = get_permissions_for_roles(["STR_Read"])
    assert len(permissions) > 0, "STR_Read should have permissions"
    print(f"✅ STR_Read permissions: {permissions[:3]}...")  # Show first 3
    
    print("="*70)
    print("✅ ALL TENANT FILTERING COMPONENTS WORKING CORRECTLY")
    print("="*70)

    # No return value: pytest treats a returned truthy value as a warning.
    assert True


if __name__ == '__main__':
    # Run the comprehensive integration test
    test_comprehensive_tenant_filtering_integration()
    
    # Run pytest
    pytest.main([__file__, '-v', '-s'])