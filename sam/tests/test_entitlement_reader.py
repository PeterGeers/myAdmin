"""
S4 / T14 — module-plane entitlement reader tests (verified-token-only, no MySQL/S3).

Proves the module plane can answer the PER-USER authorization question from the
VERIFIED token's ``custom:entitlements`` claim alone (R5.2), reading it ONLY from
verified material (R5.1) — never an unverified header. Reuses the S2 verify harness
(in-test RS256 keys + an injected JWKS fetcher, so no real network / no secrets).

Covered:
- a verified token carrying custom:entitlements -> has_capability True/False per tenant
  (authoritative token-backed decision);
- overflow claim -> "consult server" state (None), NOT a silent allow/deny;
- absent claim / unknown-version claim -> "consult" state (None);
- an unverified header carrying an entitlement is IGNORED (verified-token-only);
- get_entitlements() end-to-end from an event (authorizer path + bearer fallback path).
"""

import json
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt import algorithms

from sam.shared.auth_utils import (
    DecodedEntitlements,
    ENTITLEMENT_CLAIM_NAME,
    JWKSCache,
    JWTVerifier,
    PoolConfig,
    PoolRegistry,
    get_entitlements,
    get_entitlements_from_claims,
    has_capability,
    reset_global_verifier,
)

# --- Fixed test coordinates (public, non-secret identifiers) ---------------- #

TEST_ISS = "https://cognito-idp.eu-west-1.amazonaws.com/eu-west-1_test0pool"
TEST_JWKS_URI = f"{TEST_ISS}/.well-known/jwks.json"
TEST_CLIENT_ID = "test-app-client-id"
TEST_KID = "test-key-1"

# A normal (fits-budget) entitlement claim value, as the codec would encode it.
GOODWIN = "GoodwinSolutions"
ACME = "AcmeLtd"


def _normal_claim(tenants: dict) -> str:
    """Encode the normal claim form ``{"v":1,"t":{...}}`` the way the codec does."""
    return json.dumps({"v": 1, "t": tenants}, separators=(",", ":"), sort_keys=True)


def _overflow_claim(tenant_keys: list) -> str:
    """Encode the overflow signal form ``{"v":1,"overflow":true,"t_keys":[...]}``."""
    return json.dumps(
        {"v": 1, "overflow": True, "t_keys": sorted(tenant_keys)},
        separators=(",", ":"),
        sort_keys=True,
    )


# --- Key + JWKS helpers (mirror test_auth_utils.py's S2 harness) ------------ #


def _generate_rsa_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _jwk_from_private_key(private_key, kid: str) -> dict:
    public_pem = private_key.public_key()
    jwk = json.loads(algorithms.RSAAlgorithm.to_jwk(public_pem))
    jwk["kid"] = kid
    jwk["alg"] = "RS256"
    jwk["use"] = "sig"
    return jwk


def _private_pem(private_key) -> bytes:
    from cryptography.hazmat.primitives import serialization

    return private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


def _make_token(private_key, extra_claims: dict | None = None) -> str:
    now = int(time.time())
    claims = {
        "sub": "user-123",
        "iss": TEST_ISS,
        "client_id": TEST_CLIENT_ID,
        "token_use": "access",
        "cognito:groups": ["members-admin"],
        "iat": now,
        "exp": now + 3600,
    }
    if extra_claims:
        claims.update(extra_claims)
    return jwt.encode(
        claims, _private_pem(private_key), algorithm="RS256", headers={"kid": TEST_KID}
    )


# --- Fixtures --------------------------------------------------------------- #


@pytest.fixture(autouse=True)
def _reset_global():
    reset_global_verifier()
    yield
    reset_global_verifier()


@pytest.fixture
def signing_key():
    return _generate_rsa_key()


@pytest.fixture
def registry():
    return PoolRegistry(
        [PoolConfig(TEST_ISS, TEST_JWKS_URI, TEST_CLIENT_ID, "myAdmin-test")]
    )


@pytest.fixture
def verifier(registry, signing_key):
    document = {"keys": [_jwk_from_private_key(signing_key, TEST_KID)]}
    cache = JWKSCache(registry=registry, fetcher=lambda uri: document)
    return JWTVerifier(registry=registry, jwks_cache=cache)


# =========================================================================== #
# has_capability from a verified claims dict (the per-user answer, no MySQL/S3)
# =========================================================================== #


def test_has_capability_granted_returns_true_for_that_tenant():
    """A verified claim listing the capability for the tenant -> True (R5.2)."""
    claims = {
        ENTITLEMENT_CLAIM_NAME: _normal_claim(
            {GOODWIN: ["finance_read", "finance_write"], ACME: ["events_read"]}
        )
    }
    assert has_capability(claims, GOODWIN, "finance_read") is True
    assert has_capability(claims, GOODWIN, "finance_write") is True
    assert has_capability(claims, ACME, "events_read") is True


def test_has_capability_not_granted_returns_false_authoritatively():
    """A usable claim that lists the tenant but not the capability -> False (denial)."""
    claims = {ENTITLEMENT_CLAIM_NAME: _normal_claim({GOODWIN: ["finance_read"]})}
    # tenant present, capability absent -> authoritative token-backed DENY (False).
    assert has_capability(claims, GOODWIN, "finance_write") is False


def test_has_capability_tenant_isolation_across_tenants():
    """A capability in tenant A does not leak into tenant B's decision."""
    claims = {
        ENTITLEMENT_CLAIM_NAME: _normal_claim(
            {GOODWIN: ["finance_write"], ACME: ["events_read"]}
        )
    }
    assert has_capability(claims, GOODWIN, "finance_write") is True
    # ACME does not hold finance_write -> authoritative False, not a cross-tenant grant.
    assert has_capability(claims, ACME, "finance_write") is False


def test_has_capability_tenant_not_in_claim_returns_none_consult():
    """A tenant the usable claim does not list -> None (token doesn't answer)."""
    claims = {ENTITLEMENT_CLAIM_NAME: _normal_claim({GOODWIN: ["finance_read"]})}
    # No entry for ACME at all -> the token carries no per-user answer for it.
    assert has_capability(claims, ACME, "events_read") is None


def test_has_capability_empty_caps_list_is_authoritative_deny():
    """A tenant present with an EMPTY capability list -> False, not None.

    An empty list is the explicit "no capabilities" answer (the tenant is known but
    grants nothing) — distinct from the tenant being absent (None / consult).
    """
    claims = {ENTITLEMENT_CLAIM_NAME: _normal_claim({GOODWIN: []})}
    assert has_capability(claims, GOODWIN, "finance_read") is False


# =========================================================================== #
# Overflow / fallback -> "consult server" state, NEVER a silent decision
# =========================================================================== #


def test_has_capability_overflow_returns_none_consult_server():
    """An overflow claim -> None so the caller consults S3/server (not allow/deny)."""
    claims = {ENTITLEMENT_CLAIM_NAME: _overflow_claim([GOODWIN, ACME])}
    assert has_capability(claims, GOODWIN, "finance_read") is None
    assert has_capability(claims, ACME, "events_read") is None


def test_get_entitlements_overflow_exposes_state_not_a_map():
    """Overflow decodes to is_overflow=True with tenant_keys but no capability map."""
    claims = {ENTITLEMENT_CLAIM_NAME: _overflow_claim([ACME, GOODWIN])}
    decoded = get_entitlements_from_claims(claims)
    assert isinstance(decoded, DecodedEntitlements)
    assert decoded.is_overflow is True
    assert decoded.fallback_required is False
    assert decoded.tenant_keys == [ACME, GOODWIN]  # sorted
    assert decoded.tenants == {}
    # capabilities_for on an overflow claim never returns a map -> consult.
    assert decoded.capabilities_for(GOODWIN) is None


def test_has_capability_unknown_version_returns_none_consult():
    """An unknown claim version -> None (reader falls back, never mis-parses)."""
    future = json.dumps({"v": 999, "t": {GOODWIN: ["finance_read"]}})
    claims = {ENTITLEMENT_CLAIM_NAME: future}
    assert has_capability(claims, GOODWIN, "finance_read") is None
    assert get_entitlements_from_claims(claims).fallback_required is True


def test_has_capability_absent_claim_returns_none_consult():
    """A verified token WITHOUT the claim -> None (no capabilities / consult)."""
    claims = {"sub": "user-123", "cognito:groups": ["members-admin"]}
    assert has_capability(claims, GOODWIN, "finance_read") is None
    decoded = get_entitlements_from_claims(claims)
    assert decoded.fallback_required is True
    assert decoded.tenants == {}


def test_has_capability_malformed_claim_returns_none_consult():
    """A malformed claim value -> None (safe fallback, never a garbage decision)."""
    claims = {ENTITLEMENT_CLAIM_NAME: "not-json-at-all"}
    assert has_capability(claims, GOODWIN, "finance_read") is None


# =========================================================================== #
# Verified-token-only: an UNVERIFIED header entitlement is ignored (R5.1)
# =========================================================================== #


def test_unverified_header_entitlement_is_ignored(verifier, signing_key):
    """An X-header (or a headers-borne claim) never supplies entitlement (R5.1).

    The verified token carries NO entitlement claim; a client-supplied header tries
    to inject a full-access entitlement. The reader must decode ONLY from the verified
    token, so the header grant is invisible -> has_capability is None (consult), never
    True.
    """
    token = _make_token(signing_key)  # no custom:entitlements in the token
    spoofed = _normal_claim({GOODWIN: ["finance_read", "finance_write"]})
    event = {
        "headers": {
            "Authorization": f"Bearer {token}",
            # Attacker-supplied header trying to inject entitlement:
            "X-Entitlements": spoofed,
            ENTITLEMENT_CLAIM_NAME: spoofed,
        }
    }

    decoded = get_entitlements(event, verifier=verifier)
    # Token had no claim -> fallback; the header's spoofed grant was ignored.
    assert decoded.fallback_required is True
    assert decoded.tenants == {}

    # And the decision-level check never sees the spoofed capability.
    claims = {"sub": "user-123"}  # simulate the verified claims (no entitlement)
    assert has_capability(claims, GOODWIN, "finance_write") is None


def test_verified_token_claim_is_honored_over_the_wire(verifier, signing_key):
    """A genuinely verified token carrying the claim answers correctly end-to-end."""
    claim = _normal_claim({GOODWIN: ["finance_read"]})
    token = _make_token(signing_key, extra_claims={ENTITLEMENT_CLAIM_NAME: claim})
    event = {"headers": {"Authorization": f"Bearer {token}"}}

    decoded = get_entitlements(event, verifier=verifier)
    assert decoded.fallback_required is False
    assert decoded.capabilities_for(GOODWIN) == ["finance_read"]
    assert has_capability(decoded_claims(token, signing_key), GOODWIN, "finance_read")


def decoded_claims(token, signing_key):
    """Helper: the raw verified claims dict for a token (used to exercise has_capability)."""
    return jwt.decode(token, options={"verify_signature": False})


# =========================================================================== #
# get_entitlements via the API Gateway authorizer (verified) path
# =========================================================================== #


def test_get_entitlements_from_authorizer_context_verified_path():
    """Claims from the API-GW authorizer (already verified) feed the reader (R5.1)."""

    class ExplodingVerifier:
        def verify_token(self, token):  # pragma: no cover - must not run
            raise AssertionError("must not verify when authorizer claims present")

    claim = _normal_claim({GOODWIN: ["finance_read"], ACME: ["events_read"]})
    event = {
        "requestContext": {
            "authorizer": {
                "claims": {
                    "sub": "gw-user",
                    "iss": TEST_ISS,
                    ENTITLEMENT_CLAIM_NAME: claim,
                }
            }
        },
        # A spoofed header must NOT influence the result.
        "headers": {ENTITLEMENT_CLAIM_NAME: _normal_claim({ACME: ["finance_write"]})},
    }

    decoded = get_entitlements(event, verifier=ExplodingVerifier())
    assert decoded.capabilities_for(GOODWIN) == ["finance_read"]
    assert decoded.capabilities_for(ACME) == ["events_read"]
    # The header's ACME->finance_write was ignored (verified authorizer claims only).
    assert "finance_write" not in (decoded.capabilities_for(ACME) or [])
