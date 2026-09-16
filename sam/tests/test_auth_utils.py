"""
Module-plane JWT verification tests (S2 / T8) — self-contained, no real network.

Mirrors the S2 test matrix (design.md) for the module plane's shared verifier:

    valid signature/iss/aud, not expired        -> accept
    tampered / invalid signature                -> 401
    wrong issuer (unknown pool)                 -> 401
    wrong audience / client_id                  -> 401
    expired token                               -> 401
    unknown kid (rotation): refetch once, still -> 401
    API-GW-authorizer verified claims           -> returned WITHOUT re-verification
    base64-only "token" (unsigned)              -> NOT trusted (401)

RS256 keys are generated in-test; the JWKS fetch is injected (a fake fetcher), so no
real network is used and no secrets are involved. Nothing here imports backend/src.
"""

import base64
import json
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt import algorithms

from sam.shared.auth_utils import (
    InvalidTokenError,
    JWKSCache,
    JWTVerifier,
    PoolConfig,
    PoolRegistry,
    PoolRegistryError,
    VerifiedIdentity,
    get_groups,
    get_verified_claims,
    get_verified_identity,
    load_pool_registry,
    reset_global_verifier,
)

# --- Fixed test coordinates (public, non-secret identifiers) ---------------- #

TEST_ISS = "https://cognito-idp.eu-west-1.amazonaws.com/eu-west-1_test0pool"
TEST_JWKS_URI = f"{TEST_ISS}/.well-known/jwks.json"
TEST_CLIENT_ID = "test-app-client-id"
TEST_KID = "test-key-1"
ROTATED_KID = "test-key-2"


# --- Key + JWKS helpers ----------------------------------------------------- #


def _generate_rsa_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _jwk_from_private_key(private_key, kid: str) -> dict:
    """Public JWK (with kid) derived from an RSA private key, for the JWKS document."""
    public_pem = private_key.public_key()
    jwk_json = algorithms.RSAAlgorithm.to_jwk(public_pem)
    jwk = json.loads(jwk_json)
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


def _make_token(
    private_key,
    kid: str = TEST_KID,
    iss: str = TEST_ISS,
    client_id: str = TEST_CLIENT_ID,
    exp_delta: int = 3600,
    extra_claims: dict | None = None,
) -> str:
    now = int(time.time())
    claims = {
        "sub": "user-123",
        "iss": iss,
        "client_id": client_id,
        "token_use": "access",
        "cognito:groups": ["members-admin", "webshop-manager"],
        "iat": now,
        "exp": now + exp_delta,
    }
    if extra_claims:
        claims.update(extra_claims)
    return jwt.encode(
        claims,
        _private_pem(private_key),
        algorithm="RS256",
        headers={"kid": kid},
    )


# --- Fixtures --------------------------------------------------------------- #


@pytest.fixture(autouse=True)
def _reset_global():
    """Ensure no global verifier leaks across tests (execution-env isolation)."""
    reset_global_verifier()
    yield
    reset_global_verifier()


@pytest.fixture
def signing_key():
    return _generate_rsa_key()


@pytest.fixture
def registry():
    return PoolRegistry(
        [
            PoolConfig(
                iss=TEST_ISS,
                jwks_uri=TEST_JWKS_URI,
                audience=TEST_CLIENT_ID,
                pool_label="myAdmin-test",
            )
        ]
    )


@pytest.fixture
def jwks_document(signing_key):
    return {"keys": [_jwk_from_private_key(signing_key, TEST_KID)]}


@pytest.fixture
def verifier(registry, jwks_document):
    """Verifier whose JWKS 'fetch' returns our in-test document (no network)."""
    cache = JWKSCache(registry=registry, fetcher=lambda uri: jwks_document)
    return JWTVerifier(registry=registry, jwks_cache=cache)


# --- Verification matrix ---------------------------------------------------- #


def test_verify_token_valid_signature_returns_claims(verifier, signing_key):
    token = _make_token(signing_key)
    payload = verifier.verify_token(token)
    assert payload["sub"] == "user-123"
    assert payload["iss"] == TEST_ISS
    assert payload["client_id"] == TEST_CLIENT_ID


def test_verify_token_tampered_signature_rejected(verifier, signing_key):
    token = _make_token(signing_key)
    # Tamper at the BYTE level so the change is guaranteed to alter the signature.
    # (Flipping a single trailing base64url char is unreliable: the last char only
    # encodes a few bits, so it can decode to the same signature bytes and still
    # verify.) Decode, flip a byte in the middle, re-encode.
    head, payload_seg, sig = token.split(".")
    pad = "=" * (-len(sig) % 4)
    raw = bytearray(base64.urlsafe_b64decode(sig + pad))
    mid = len(raw) // 2
    raw[mid] ^= 0xFF  # guaranteed different signature bytes
    bad_sig = base64.urlsafe_b64encode(bytes(raw)).rstrip(b"=").decode()
    tampered = f"{head}.{payload_seg}.{bad_sig}"
    with pytest.raises(InvalidTokenError):
        verifier.verify_token(tampered)


def test_verify_token_wrong_issuer_signed_by_other_pool_rejected(verifier):
    """A token whose iss is not in the registry is rejected (unknown pool -> 401)."""
    other_key = _generate_rsa_key()
    token = _make_token(other_key, iss="https://evil.example.com/pool")
    with pytest.raises(InvalidTokenError):
        verifier.verify_token(token)


def test_verify_token_wrong_audience_rejected(verifier, signing_key):
    token = _make_token(signing_key, client_id="some-other-client")
    with pytest.raises(InvalidTokenError):
        verifier.verify_token(token)


def test_verify_token_expired_rejected(verifier, signing_key):
    # Expired well beyond the 30s leeway.
    token = _make_token(signing_key, exp_delta=-3600)
    with pytest.raises(InvalidTokenError):
        verifier.verify_token(token)


def test_verify_token_unknown_kid_refetches_once_then_rejects(registry, signing_key):
    """Unknown kid triggers exactly one refetch; still unknown -> 401 (rotation)."""
    document = {"keys": [_jwk_from_private_key(signing_key, TEST_KID)]}
    fetch_calls = {"n": 0}

    def counting_fetcher(uri):
        fetch_calls["n"] += 1
        return document  # never contains ROTATED_KID

    cache = JWKSCache(registry=registry, fetcher=counting_fetcher)
    verifier = JWTVerifier(registry=registry, jwks_cache=cache)

    token = _make_token(signing_key, kid=ROTATED_KID)
    with pytest.raises(InvalidTokenError):
        verifier.verify_token(token)

    # One populate + one rotation refetch = exactly 2 fetches (never per-request loop).
    assert fetch_calls["n"] == 2


def test_verify_token_unknown_kid_refetch_finds_rotated_key_accepts(registry, signing_key):
    """If the refetch surfaces the new kid, the token verifies (rotation success)."""
    old_only = {"keys": [_jwk_from_private_key(signing_key, TEST_KID)]}
    rotated_key = _generate_rsa_key()
    rotated_doc = {
        "keys": [
            _jwk_from_private_key(signing_key, TEST_KID),
            _jwk_from_private_key(rotated_key, ROTATED_KID),
        ]
    }
    docs = [old_only, rotated_doc]
    call = {"n": 0}

    def rotating_fetcher(uri):
        doc = docs[min(call["n"], len(docs) - 1)]
        call["n"] += 1
        return doc

    cache = JWKSCache(registry=registry, fetcher=rotating_fetcher)
    verifier = JWTVerifier(registry=registry, jwks_cache=cache)

    token = _make_token(rotated_key, kid=ROTATED_KID)
    payload = verifier.verify_token(token)
    assert payload["sub"] == "user-123"
    assert call["n"] == 2  # populate (old only) + one refetch (now has rotated kid)


def test_verify_token_warm_cache_does_not_refetch(verifier, signing_key):
    """Two verifications of a known kid fetch JWKS once (warm reuse, not per request)."""
    calls = {"n": 0}

    doc = {"keys": [_jwk_from_private_key(signing_key, TEST_KID)]}

    def counting_fetcher(uri):
        calls["n"] += 1
        return doc

    registry = PoolRegistry(
        [PoolConfig(TEST_ISS, TEST_JWKS_URI, TEST_CLIENT_ID, "myAdmin-test")]
    )
    cache = JWKSCache(registry=registry, fetcher=counting_fetcher)
    v = JWTVerifier(registry=registry, jwks_cache=cache)

    token = _make_token(signing_key)
    v.verify_token(token)
    v.verify_token(token)
    assert calls["n"] == 1


# --- base64-only NOT trusted ------------------------------------------------ #


def test_base64_only_unsigned_token_is_not_trusted(verifier):
    """An unsigned 'alg: none' JWT (base64-only payload) must be rejected, not decoded."""
    header = {"alg": "none", "kid": TEST_KID}

    def b64(obj):
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b"=").decode()

    claims = {
        "sub": "attacker",
        "iss": TEST_ISS,
        "client_id": TEST_CLIENT_ID,
        "cognito:groups": ["members-admin"],
        "exp": int(time.time()) + 3600,
    }
    unsigned = f"{b64(header)}.{b64(claims)}."  # empty signature
    with pytest.raises(InvalidTokenError):
        verifier.verify_token(unsigned)


def test_get_verified_claims_fallback_verifies_bearer_not_base64(verifier, signing_key):
    """The no-authorizer fallback runs full verification; a bogus bearer -> 401."""
    valid_token = _make_token(signing_key)
    event = {"headers": {"Authorization": f"Bearer {valid_token}"}}
    claims = get_verified_claims(event, verifier=verifier)
    assert claims["sub"] == "user-123"

    # A well-formed-but-unsigned token on the fallback path is rejected.
    bogus_event = {"headers": {"Authorization": "Bearer not.a.real.jwt"}}
    with pytest.raises(InvalidTokenError):
        get_verified_claims(bogus_event, verifier=verifier)


# --- API Gateway Cognito authorizer preferred path -------------------------- #


def test_get_verified_claims_uses_authorizer_context_without_reverification():
    """When API GW verified the token, claims are returned without re-verifying.

    We pass a verifier that would raise if called, proving the authorizer path does
    not re-run verification.
    """

    class ExplodingVerifier:
        def verify_token(self, token):  # pragma: no cover - must not be called
            raise AssertionError("verifier must not run when authorizer claims present")

    event = {
        "requestContext": {
            "authorizer": {
                "claims": {
                    "sub": "gw-user",
                    "iss": TEST_ISS,
                    "cognito:groups": "[events-admin members-viewer]",
                }
            }
        }
    }
    claims = get_verified_claims(event, verifier=ExplodingVerifier())
    assert claims["sub"] == "gw-user"


def test_get_verified_claims_http_api_v2_jwt_authorizer_path():
    """HTTP API v2 shape (authorizer.jwt.claims) is also honored without re-verify."""

    class ExplodingVerifier:
        def verify_token(self, token):  # pragma: no cover
            raise AssertionError("must not verify when jwt.claims present")

    event = {
        "requestContext": {
            "authorizer": {"jwt": {"claims": {"sub": "v2-user", "iss": TEST_ISS}}}
        }
    }
    claims = get_verified_claims(event, verifier=ExplodingVerifier())
    assert claims["sub"] == "v2-user"


def test_get_verified_claims_missing_token_rejected(verifier):
    with pytest.raises(InvalidTokenError):
        get_verified_claims({"headers": {}}, verifier=verifier)


# --- roles from verified cognito:groups (no header trust) ------------------- #


def test_get_groups_from_list_claim():
    assert get_groups({"cognito:groups": ["a", "b"]}) == ["a", "b"]


def test_get_groups_from_authorizer_bracketed_string():
    # API Gateway can surface list claims as a bracketed, space-separated string.
    assert get_groups({"cognito:groups": "[events-admin members-viewer]"}) == [
        "events-admin",
        "members-viewer",
    ]


def test_get_groups_absent_returns_empty():
    assert get_groups({"sub": "x"}) == []


# --- registry fail-fast (config-not-code, no defaults) ---------------------- #


def test_load_pool_registry_missing_pool_keys_raises():
    with pytest.raises(PoolRegistryError):
        load_pool_registry(environ={})


def test_load_pool_registry_missing_pool_var_raises():
    env = {
        "COGNITO_POOL_KEYS": "TEST",
        "TEST_COGNITO_ISSUER": TEST_ISS,
        # missing the other three required vars
    }
    with pytest.raises(PoolRegistryError):
        load_pool_registry(environ=env)


def test_load_pool_registry_full_env_builds_registry():
    env = {
        "COGNITO_POOL_KEYS": "TEST",
        "TEST_COGNITO_ISSUER": TEST_ISS,
        "TEST_COGNITO_JWKS_URI": TEST_JWKS_URI,
        "TEST_COGNITO_CLIENT_ID": TEST_CLIENT_ID,
        "TEST_COGNITO_POOL_LABEL": "myAdmin-test",
    }
    reg = load_pool_registry(environ=env)
    assert TEST_ISS in reg
    assert reg.require(TEST_ISS).audience == TEST_CLIENT_ID


# --- T9: no client-supplied header is trusted for identity/roles (R2.1, R2.2) --- #


def test_x_enhanced_groups_header_has_no_effect_on_groups(verifier, signing_key):
    """An X-Enhanced-Groups header must NOT influence the groups (R2.1, R2.2).

    Groups equal exactly the verified token's cognito:groups regardless of any
    client-supplied header claiming elevated roles.
    """
    token = _make_token(signing_key)  # token groups: members-admin, webshop-manager
    event = {
        "headers": {
            "Authorization": f"Bearer {token}",
            "X-Enhanced-Groups": "SysAdmin,SuperUser",
            "X-Tenant": "attacker-tenant",
        }
    }

    claims = get_verified_claims(event, verifier=verifier)
    groups = get_groups(claims)

    # Exactly the verified token's groups — the header's SysAdmin claim is ignored.
    assert groups == ["members-admin", "webshop-manager"]
    assert "SysAdmin" not in groups
    assert "SuperUser" not in groups


def test_get_verified_identity_ignores_enhanced_groups_header(verifier, signing_key):
    """get_verified_identity() derives roles only from the verified token (R2.2)."""
    token = _make_token(signing_key)
    event = {
        "headers": {
            "Authorization": f"Bearer {token}",
            "X-Enhanced-Groups": "SysAdmin",
        }
    }

    identity = get_verified_identity(event, verifier=verifier)

    assert isinstance(identity, VerifiedIdentity)
    assert identity.sub == "user-123"
    assert identity.groups == ["members-admin", "webshop-manager"]
    assert "SysAdmin" not in identity.groups


def test_groups_empty_when_token_has_none_even_with_header(verifier, signing_key):
    """A token with no cognito:groups yields [] — never header-derived (R2.1)."""
    token = _make_token(signing_key, extra_claims={"cognito:groups": []})
    event = {
        "headers": {
            "Authorization": f"Bearer {token}",
            "X-Enhanced-Groups": "SysAdmin,Admin",
        }
    }

    identity = get_verified_identity(event, verifier=verifier)

    # Empty groups from the token stay empty; the header does not fill them in.
    assert identity.groups == []


def test_get_verified_identity_from_authorizer_context_no_header_trust():
    """Identity/roles come from API-GW-verified claims, never from headers (R2.1)."""

    class ExplodingVerifier:
        def verify_token(self, token):  # pragma: no cover - must not be called
            raise AssertionError("verifier must not run when authorizer claims present")

    event = {
        "headers": {"X-Enhanced-Groups": "SysAdmin"},
        "requestContext": {
            "authorizer": {
                "claims": {
                    "sub": "gw-user",
                    "email": "gw@example.com",
                    "iss": TEST_ISS,
                    "cognito:groups": "[events-admin members-viewer]",
                }
            }
        },
    }

    identity = get_verified_identity(event, verifier=ExplodingVerifier())

    assert identity.sub == "gw-user"
    assert identity.email == "gw@example.com"
    assert identity.groups == ["events-admin", "members-viewer"]
    assert "SysAdmin" not in identity.groups


def test_get_verified_identity_carries_no_tenant_field():
    """VerifiedIdentity exposes no tenant (tenant-from-token deferred to S5, R2.4)."""
    identity = VerifiedIdentity(sub="s", email=None, groups=[], claims={})
    assert not hasattr(identity, "tenant")
    assert not hasattr(identity, "tenant_id")


# --- T11: headers have no effect on the authorization DECISION (module plane) --- #
#
# The module plane has no permission-mapping/tenant layer in S2 (tenant deferred to
# S5), so the authorization *decision* here is the set of roles the verified identity
# resolves to: an access check is "does the verified identity hold role X?". These
# assert at that decision level, not merely the raw groups list:
#   (a) X-Enhanced-Groups with elevated roles → same role decision as without it;
#   (b) X-Tenant has no effect on identity/roles (module plane has no tenant handling);
#   (c) a role the token does NOT grant stays denied with the header present, and a
#       role the token DOES grant is allowed regardless of header presence/absence.


def _has_role(identity, role: str) -> bool:
    """The module-plane 'decision': is ``role`` present in the verified identity?"""
    return role in identity.groups


def test_enhanced_groups_header_yields_same_role_decision_as_no_header(
    verifier, signing_key
):
    """(a) Elevated X-Enhanced-Groups → identical role decision as without the header."""
    token = _make_token(signing_key)  # verified groups: members-admin, webshop-manager

    event_plain = {"headers": {"Authorization": f"Bearer {token}"}}
    event_spoof = {
        "headers": {
            "Authorization": f"Bearer {token}",
            "X-Enhanced-Groups": "SysAdmin,Administrators",
        }
    }

    identity_plain = get_verified_identity(event_plain, verifier=verifier)
    identity_spoof = get_verified_identity(event_spoof, verifier=verifier)

    # Same decision: identical resolved roles regardless of the header.
    assert identity_plain.groups == identity_spoof.groups
    # The spoofed elevated roles are NOT granted.
    assert _has_role(identity_spoof, "SysAdmin") is False
    assert _has_role(identity_spoof, "Administrators") is False
    # The genuinely-verified roles are unchanged.
    assert _has_role(identity_spoof, "members-admin") is True


def test_x_tenant_header_has_no_effect_on_identity_or_roles(verifier, signing_key):
    """(b) X-Tenant is inert on the module plane (no tenant handling; tenant → S5)."""
    token = _make_token(signing_key)

    without = get_verified_identity(
        {"headers": {"Authorization": f"Bearer {token}"}}, verifier=verifier
    )
    with_hdr = get_verified_identity(
        {
            "headers": {
                "Authorization": f"Bearer {token}",
                "X-Tenant": "attacker-tenant",
            }
        },
        verifier=verifier,
    )

    # Identity + roles are byte-for-byte the same; X-Tenant changed nothing.
    assert with_hdr.sub == without.sub
    assert with_hdr.groups == without.groups
    # And the module plane still exposes no tenant (deferred to S5, R2.4).
    assert not hasattr(with_hdr, "tenant")
    assert not hasattr(with_hdr, "tenant_id")


def test_header_cannot_grant_a_role_the_token_lacks(verifier, signing_key):
    """(c) A role absent from the verified token stays denied even with the header."""
    # Token grants members-admin / webshop-manager but NOT SysAdmin.
    token = _make_token(signing_key)

    denied_plain = get_verified_identity(
        {"headers": {"Authorization": f"Bearer {token}"}}, verifier=verifier
    )
    denied_spoof = get_verified_identity(
        {
            "headers": {
                "Authorization": f"Bearer {token}",
                "X-Enhanced-Groups": "SysAdmin",
            }
        },
        verifier=verifier,
    )

    # Deny stays deny: the header did not turn the missing role into a granted one.
    assert _has_role(denied_plain, "SysAdmin") is False
    assert _has_role(denied_spoof, "SysAdmin") is False
    assert _has_role(denied_spoof, "SysAdmin") == _has_role(denied_plain, "SysAdmin")


def test_verified_role_is_allowed_regardless_of_header_presence(verifier, signing_key):
    """(c) A role the token DOES grant is allowed with or without headers (inert)."""
    token = _make_token(signing_key)  # grants members-admin

    allowed_no_hdr = get_verified_identity(
        {"headers": {"Authorization": f"Bearer {token}"}}, verifier=verifier
    )
    allowed_with_hdr = get_verified_identity(
        {
            "headers": {
                "Authorization": f"Bearer {token}",
                # A header that tries to DOWNGRADE must also be ignored.
                "X-Enhanced-Groups": "members-viewer",
                "X-Tenant": "some-tenant",
            }
        },
        verifier=verifier,
    )

    assert _has_role(allowed_no_hdr, "members-admin") is True
    assert _has_role(allowed_with_hdr, "members-admin") is True
    assert _has_role(allowed_with_hdr, "members-admin") == _has_role(
        allowed_no_hdr, "members-admin"
    )
