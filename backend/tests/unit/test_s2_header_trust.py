"""
S2 T7 — Flask plane: no trust in unverified headers (R2).

These tests prove that on the Flask plane:
  * roles come only from the VERIFIED token's ``cognito:groups`` — an
    ``X-Enhanced-Groups`` header has no effect and is not even advertised in CORS
    (R2.1, R2.2);
  * the tenant authorization list comes only from the VERIFIED token's
    ``custom:tenants`` — an ``X-Tenant`` value not in that verified list is rejected
    (R2.1, R2.3);
  * ``X-Tenant`` remains only a *selector* validated against the verified list.

All Cognito/verifier interactions are mocked; no real network or DB is used.

**Validates: Requirements R2.1, R2.2, R2.3**
"""

import base64
import json
from unittest.mock import patch

import pytest


def _make_token(payload: dict) -> str:
    """Build a syntactically valid (unsigned) JWT for shape tests."""
    header = (
        base64.urlsafe_b64encode(json.dumps({"alg": "RS256"}).encode())
        .decode()
        .rstrip("=")
    )
    body = (
        base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    )
    return f"{header}.{body}.sig"


class TestCorsDoesNotAdvertiseEnhancedGroups:
    """R2.1/R2.2: X-Enhanced-Groups is no longer an accepted header."""

    def test_cors_allow_headers_excludes_x_enhanced_groups(self):
        from auth.cognito_utils import cors_headers

        allow_headers = cors_headers()["Access-Control-Allow-Headers"]

        assert "X-Enhanced-Groups" not in allow_headers
        # Still advertises the headers we legitimately use.
        assert "Authorization" in allow_headers
        assert "Content-Type" in allow_headers


class TestRolesComeFromVerifiedTokenOnly:
    """R2.2: roles derive from verified cognito:groups, never from a header."""

    def test_x_enhanced_groups_header_has_no_effect_on_roles(self):
        from auth import cognito_utils

        class FakeVerifier:
            def verify_token(self, token):
                # The verified token grants exactly Finance_Read.
                return {
                    "email": "user@test.com",
                    "cognito:groups": ["Finance_Read"],
                }

        headers = {
            "authorization": "Bearer some.jwt.token",
            # Attacker-supplied elevated groups — must be ignored entirely.
            "X-Enhanced-Groups": "Administrators,SysAdmin",
        }
        event = {"headers": headers}

        with patch.object(
            cognito_utils, "_get_jwt_verifier", return_value=FakeVerifier()
        ):
            email, roles, error = cognito_utils.extract_user_credentials(event)

        assert error is None
        assert email == "user@test.com"
        # Roles are exactly what the verified token said — the header did nothing.
        assert roles == ["Finance_Read"]
        assert "Administrators" not in roles
        assert "SysAdmin" not in roles


class TestTenantListComesFromVerifiedTokenOnly:
    """R2.3: the tenant authorization list comes from the verified token."""

    def test_get_verified_tenants_uses_verifier_payload(self):
        from auth import cognito_utils

        class FakeVerifier:
            def verify_token(self, token):
                return {"custom:tenants": ["GoodwinSolutions", "PeterPrive"]}

        with patch.object(
            cognito_utils, "_get_jwt_verifier", return_value=FakeVerifier()
        ):
            tenants = cognito_utils.get_verified_tenants("some.jwt.token")

        assert tenants == ["GoodwinSolutions", "PeterPrive"]

    def test_get_verified_tenants_returns_none_when_verifier_absent(self):
        """Verifier not configured -> signal caller to use the dev/test fallback."""
        from auth import cognito_utils

        with patch.object(cognito_utils, "_get_jwt_verifier", return_value=None):
            assert cognito_utils.get_verified_tenants("some.jwt.token") is None

    def test_get_user_tenants_reads_from_verified_token(self):
        """tenant_context.get_user_tenants uses the verified list when available."""
        from auth import cognito_utils
        from auth.tenant_context import get_user_tenants

        class FakeVerifier:
            def verify_token(self, token):
                return {"custom:tenants": ["GoodwinSolutions"]}

        with patch.object(
            cognito_utils, "_get_jwt_verifier", return_value=FakeVerifier()
        ):
            tenants = get_user_tenants("some.jwt.token")

        assert tenants == ["GoodwinSolutions"]

    def test_get_user_tenants_denies_when_verification_fails(self):
        """A token that fails verification yields NO tenants (never trusts base64)."""
        from auth import cognito_utils
        from auth.tenant_context import get_user_tenants

        class BadVerifier:
            def verify_token(self, token):
                raise ValueError("bad signature")

        # A token whose UNVERIFIED base64 body claims broad tenant access.
        forged = _make_token({"custom:tenants": ["GoodwinSolutions", "PeterPrive"]})

        with patch.object(
            cognito_utils, "_get_jwt_verifier", return_value=BadVerifier()
        ):
            tenants = get_user_tenants(forged)

        # The forged/base64 claim is ignored because verification failed.
        assert tenants == []

    def test_get_user_tenants_falls_back_to_base64_when_verifier_absent(self):
        """Local dev / tests without Cognito env: base64 fallback still works."""
        from auth import cognito_utils
        from auth.tenant_context import get_user_tenants

        token = _make_token({"custom:tenants": ["GoodwinSolutions"]})

        with patch.object(cognito_utils, "_get_jwt_verifier", return_value=None):
            tenants = get_user_tenants(token)

        assert tenants == ["GoodwinSolutions"]


class TestUnauthorizedXTenantRejected:
    """R2.1/R2.3: X-Tenant not in the verified list is rejected (selector only)."""

    def test_validate_tenant_access_rejects_tenant_outside_verified_list(self):
        from auth.tenant_context import validate_tenant_access

        # Verified token authorizes only GoodwinSolutions.
        verified_tenants = ["GoodwinSolutions"]

        # Attacker sets X-Tenant to a tenant they are NOT authorized for.
        is_ok, error = validate_tenant_access(verified_tenants, "PeterPrive")

        assert is_ok is False
        assert error is not None
        assert "Access denied" in error["error"]

    def test_x_tenant_selector_within_verified_list_is_allowed(self):
        from auth.tenant_context import validate_tenant_access

        verified_tenants = ["GoodwinSolutions", "PeterPrive"]

        is_ok, error = validate_tenant_access(verified_tenants, "PeterPrive")

        assert is_ok is True
        assert error is None


class TestHeadersHaveNoEffectOnAuthorizationDecision:
    """T11 (R2): headers cannot change the authorization DECISION — Flask plane.

    These assert at the decision level (the roles/permissions the auth layer computes
    and the allow/deny outcome), not merely the returned groups list:
      (a) X-Enhanced-Groups with elevated roles yields the SAME decision as no header;
      (c) a request denied without headers stays denied WITH them, and a request
          allowed by the verified token is allowed regardless of header presence;
      (d) X-Enhanced-Groups + X-Tenant together are inert — roles come from verified
          cognito:groups, tenant from verified custom:tenants.
    """

    def _extract_roles(self, verified_groups, headers):
        """Run extract_user_credentials with a verifier granting ``verified_groups``."""
        from auth import cognito_utils

        class FakeVerifier:
            def verify_token(self, token):
                return {"email": "user@test.com", "cognito:groups": list(verified_groups)}

        event = {"headers": headers}
        with patch.object(
            cognito_utils, "_get_jwt_verifier", return_value=FakeVerifier()
        ):
            return cognito_utils.extract_user_credentials(event)

    def test_enhanced_groups_header_yields_same_decision_as_no_header(self):
        """(a) Elevated X-Enhanced-Groups → identical roles + permissions as without it."""
        from auth.cognito_utils import get_permissions_for_roles

        base_headers = {"authorization": "Bearer some.jwt.token"}
        spoofed_headers = {
            "authorization": "Bearer some.jwt.token",
            # Attacker claims SysAdmin / Administrators via the header.
            "X-Enhanced-Groups": "SysAdmin,Administrators",
        }

        email_a, roles_a, err_a = self._extract_roles(["Finance_Read"], base_headers)
        email_b, roles_b, err_b = self._extract_roles(["Finance_Read"], spoofed_headers)

        # Same identity + same roles: the header made no difference.
        assert err_a is None and err_b is None
        assert email_a == email_b == "user@test.com"
        assert roles_a == roles_b == ["Finance_Read"]

        # The DECISION (resolved permissions) is identical, and never elevated.
        perms_a = sorted(get_permissions_for_roles(roles_a))
        perms_b = sorted(get_permissions_for_roles(roles_b))
        assert perms_a == perms_b
        # A Finance_Read caller must not get the wildcard (SysAdmin) grant.
        assert "*" not in perms_b

    def test_header_cannot_turn_a_deny_into_an_allow(self):
        """(c) Verified token lacks the required permission → denied, header can't fix it."""
        from auth.cognito_utils import validate_permissions

        # Finance_Read grants finance_read but NOT finance_create (a write op).
        required = ["finance_create"]

        # Verified token only grants Finance_Read (no write). Deny WITHOUT any header.
        _, roles_plain, _ = self._extract_roles(["Finance_Read"], {
            "authorization": "Bearer some.jwt.token",
        })
        ok_plain, err_plain = validate_permissions(roles_plain, required)

        # Same verified token, now WITH a spoofed elevated header. Still denied.
        _, roles_spoof, _ = self._extract_roles(["Finance_Read"], {
            "authorization": "Bearer some.jwt.token",
            "X-Enhanced-Groups": "SysAdmin,Administrators",
        })
        ok_spoof, err_spoof = validate_permissions(roles_spoof, required)

        assert ok_plain is False and err_plain is not None
        assert ok_spoof is False and err_spoof is not None
        # The header did not turn the deny into an allow.
        assert ok_spoof == ok_plain

    def test_verified_allow_is_inert_to_header_presence(self):
        """(c) A caller the verified token allows is allowed regardless of headers."""
        from auth.cognito_utils import get_permissions_for_roles, validate_permissions

        # Administrators from the VERIFIED token grants the wildcard ("*").
        required = ["finance_create"]

        _, roles_no_hdr, _ = self._extract_roles(["Administrators"], {
            "authorization": "Bearer some.jwt.token",
        })
        _, roles_with_hdr, _ = self._extract_roles(["Administrators"], {
            "authorization": "Bearer some.jwt.token",
            # An X-Enhanced-Groups that DOWNGRADES — must also be ignored.
            "X-Enhanced-Groups": "Finance_Read",
        })

        ok_no_hdr, _ = validate_permissions(roles_no_hdr, required)
        ok_with_hdr, _ = validate_permissions(roles_with_hdr, required)

        assert ok_no_hdr is True
        assert ok_with_hdr is True  # header presence/absence is inert
        # Wildcard comes from the verified Administrators role either way.
        assert "*" in get_permissions_for_roles(roles_with_hdr)

    def test_combined_enhanced_groups_and_tenant_headers_are_inert(self):
        """(d) X-Enhanced-Groups + X-Tenant together have no effect on the decision."""
        from auth import cognito_utils
        from auth.cognito_utils import get_permissions_for_roles
        from auth.tenant_context import validate_tenant_access

        class FakeVerifier:
            def verify_token(self, token):
                # Verified token: Finance_Read role, single authorized tenant.
                return {
                    "email": "user@test.com",
                    "cognito:groups": ["Finance_Read"],
                    "custom:tenants": ["GoodwinSolutions"],
                }

        headers = {
            "authorization": "Bearer some.jwt.token",
            "X-Enhanced-Groups": "SysAdmin,Administrators",  # spoofed elevation
            "X-Tenant": "PeterPrive",  # tenant NOT in verified custom:tenants
        }
        event = {"headers": headers}

        with patch.object(
            cognito_utils, "_get_jwt_verifier", return_value=FakeVerifier()
        ):
            _, roles, err = cognito_utils.extract_user_credentials(event)
            verified_tenants = cognito_utils.get_verified_tenants("some.jwt.token")

        # Roles from verified cognito:groups only — not the header.
        assert err is None
        assert roles == ["Finance_Read"]
        assert "*" not in get_permissions_for_roles(roles)

        # Tenant list from verified custom:tenants only — the X-Tenant header value
        # is not in it, so selecting it is denied (403-shaped).
        assert verified_tenants == ["GoodwinSolutions"]
        ok, tenant_err = validate_tenant_access(verified_tenants, "PeterPrive")
        assert ok is False
        assert tenant_err is not None
        assert "Access denied" in tenant_err["error"]

        # And the tenant the verified token DOES authorize is allowed regardless.
        ok_good, _ = validate_tenant_access(verified_tenants, "GoodwinSolutions")
        assert ok_good is True


class TestNormalizeTenantsClaim:
    """Shape adapter for custom:tenants — accepts list / JSON / escaped forms."""

    def test_list_passthrough(self):
        from auth.cognito_utils import _normalize_tenants_claim

        assert _normalize_tenants_claim(["A", "B"]) == ["A", "B"]

    def test_json_string(self):
        from auth.cognito_utils import _normalize_tenants_claim

        assert _normalize_tenants_claim('["A","B"]') == ["A", "B"]

    def test_escaped_json_string(self):
        from auth.cognito_utils import _normalize_tenants_claim

        assert _normalize_tenants_claim('[\\"A\\",\\"B\\"]') == ["A", "B"]

    def test_single_string(self):
        from auth.cognito_utils import _normalize_tenants_claim

        assert _normalize_tenants_claim("A") == ["A"]

    def test_empty(self):
        from auth.cognito_utils import _normalize_tenants_claim

        assert _normalize_tenants_claim([]) == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
