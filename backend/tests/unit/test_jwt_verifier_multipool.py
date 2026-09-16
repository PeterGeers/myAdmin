"""
Unit tests for multi-pool JWT verification (S2 / T5, R1.2, R3).

The verifier resolves the issuing pool from the token's ``iss`` claim via the
issuer->pool registry (T3) and verifies the RS256 signature + claims against THAT
pool's JWKS through the fail-fast T4 cache. These tests cover the design's
verification test matrix at the multi-pool level:

    | Case                                   | Expected |
    | -------------------------------------- | -------- |
    | Valid token from a registered pool     | accept   |
    | Wrong / unknown issuer                 | 401      |
    | Wrong audience                         | 401      |
    | Expired token                          | 401      |
    | Tampered signature                     | 401      |
    | Unknown kid after one refetch          | 401      |
    | Token routed to the CORRECT pool's keys| accept   |

No real network is used: a fake in-memory JWKS fetcher is injected into the T4
cache. RS256 test keys are generated in-test. No ``load_dotenv``; the registry is
built directly from :class:`PoolConfig` entries.
"""

import json
import time

import jwt as pyjwt
import pytest
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from auth.jwks_cache import JWKSCache
from auth.jwt_verifier import (
    InvalidTokenError,
    JWTVerifier,
    TokenExpiredError,
)
from auth.pool_registry import PoolRegistry
from auth.test_pool_config import PoolConfig


# --- Two registered pools (the standing test pool + a second pool) ---

POOL_A_ISS = "https://cognito-idp.eu-west-1.amazonaws.com/eu-west-1_PoolAAA"
POOL_A_AUD = "client-a"
POOL_A_JWKS = "https://cognito-idp.eu-west-1.amazonaws.com/eu-west-1_PoolAAA/.well-known/jwks.json"

POOL_B_ISS = "https://cognito-idp.eu-west-1.amazonaws.com/eu-west-1_PoolBBB"
POOL_B_AUD = "client-b"
POOL_B_JWKS = "https://cognito-idp.eu-west-1.amazonaws.com/eu-west-1_PoolBBB/.well-known/jwks.json"

UNKNOWN_ISS = "https://cognito-idp.eu-west-1.amazonaws.com/eu-west-1_NotRegistered"


# Distinct signing keys per pool so a token signed for one pool cannot verify
# against the other's JWKS.
_KEY_A = rsa.generate_private_key(65537, 2048, default_backend())
_KEY_B = rsa.generate_private_key(65537, 2048, default_backend())
_KEY_ROTATED = rsa.generate_private_key(65537, 2048, default_backend())


# --- Helpers ---


def _pem(private_key):
    return private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


def _jwk(public_key, kid):
    from jwt.algorithms import RSAAlgorithm

    d = json.loads(RSAAlgorithm.to_jwk(public_key))
    d["kid"] = kid
    d["alg"] = "RS256"
    d["use"] = "sig"
    return d


def _sign(payload, private_key, kid, algorithm="RS256"):
    return pyjwt.encode(
        payload, _pem(private_key), algorithm=algorithm, headers={"kid": kid, "alg": algorithm}
    )


def _payload(iss, aud=None, client_id=None, exp_offset=3600, sub="user-1"):
    p = {
        "sub": sub,
        "iss": iss,
        "exp": int(time.time()) + exp_offset,
        "iat": int(time.time()),
    }
    if aud is not None:
        p["aud"] = aud
    if client_id is not None:
        p["client_id"] = client_id
    return p


def _registry():
    return PoolRegistry(
        [
            PoolConfig(iss=POOL_A_ISS, jwks_uri=POOL_A_JWKS, audience=POOL_A_AUD, pool_label="pool-a"),
            PoolConfig(iss=POOL_B_ISS, jwks_uri=POOL_B_JWKS, audience=POOL_B_AUD, pool_label="pool-b"),
        ]
    )


class _FakeFetcher:
    """In-memory JWKS fetcher keyed by jwks_uri (no network).

    Maps each pool's ``jwks_uri`` to a JWKS document. ``set_keys`` can swap a pool's
    published keys to simulate rotation.
    """

    def __init__(self):
        self._docs = {}
        self.calls = []

    def set_keys(self, jwks_uri, *keys):
        self._docs[jwks_uri] = {"keys": list(keys)}

    def __call__(self, jwks_uri):
        self.calls.append(jwks_uri)
        return self._docs[jwks_uri]


def _make_verifier(fetcher):
    registry = _registry()
    cache = JWKSCache(registry=registry, fetcher=fetcher, ttl_seconds=3600)
    return JWTVerifier(registry=registry, jwks_cache=cache)


def _fetcher_with_both_pools():
    fetcher = _FakeFetcher()
    fetcher.set_keys(POOL_A_JWKS, _jwk(_KEY_A.public_key(), "kid-a"))
    fetcher.set_keys(POOL_B_JWKS, _jwk(_KEY_B.public_key(), "kid-b"))
    return fetcher


# =============================================================================
# Multi-pool resolution + verification matrix
# **Validates: Requirements 1.2, 3**
# =============================================================================


class TestMultiPoolResolution:
    def test_token_from_pool_a_verifies_against_pool_a(self):
        """A token issued by Pool A verifies against Pool A's JWKS. (R3.1)"""
        # **Validates: Requirements 1.2, 3**
        fetcher = _fetcher_with_both_pools()
        verifier = _make_verifier(fetcher)

        token = _sign(_payload(POOL_A_ISS, client_id=POOL_A_AUD), _KEY_A, "kid-a")
        result = verifier.verify_token(token)

        assert result["iss"] == POOL_A_ISS
        assert result["sub"] == "user-1"
        # Only Pool A's JWKS was fetched — resolution routed by iss.
        assert POOL_A_JWKS in fetcher.calls
        assert POOL_B_JWKS not in fetcher.calls

    def test_token_from_pool_b_verifies_against_pool_b(self):
        """A token issued by Pool B verifies against Pool B's JWKS (correct routing)."""
        # **Validates: Requirements 1.2, 3**
        fetcher = _fetcher_with_both_pools()
        verifier = _make_verifier(fetcher)

        token = _sign(_payload(POOL_B_ISS, client_id=POOL_B_AUD), _KEY_B, "kid-b")
        result = verifier.verify_token(token)

        assert result["iss"] == POOL_B_ISS
        assert POOL_B_JWKS in fetcher.calls

    def test_token_signed_for_pool_a_but_claiming_pool_b_iss_is_rejected(self):
        """A token signed by Pool A's key but with Pool B's iss fails signature (401).

        Selecting the pool by iss routes to Pool B's keys, which never signed this
        token — no partial trust across pools (R1.3).
        """
        # **Validates: Requirements 1.2, 1.3, 3**
        fetcher = _fetcher_with_both_pools()
        verifier = _make_verifier(fetcher)

        # iss says Pool B (so Pool B keys are used) but it's signed with Pool A's key.
        token = _sign(_payload(POOL_B_ISS, client_id=POOL_B_AUD), _KEY_A, "kid-b")
        with pytest.raises(InvalidTokenError) as exc:
            verifier.verify_token(token)
        assert exc.value.http_status == 401

    def test_unknown_issuer_rejected_401(self):
        """A token whose iss is not in the registry is rejected with 401. (R3.1)"""
        # **Validates: Requirements 1.3, 3**
        fetcher = _fetcher_with_both_pools()
        verifier = _make_verifier(fetcher)

        token = _sign(_payload(UNKNOWN_ISS, client_id=POOL_A_AUD), _KEY_A, "kid-a")
        with pytest.raises(InvalidTokenError) as exc:
            verifier.verify_token(token)
        assert exc.value.http_status == 401
        # No JWKS fetch happened for an unknown issuer (never guess an endpoint).
        assert fetcher.calls == []

    def test_wrong_audience_rejected_401(self):
        """A token with an audience that doesn't match the pool is rejected (401)."""
        # **Validates: Requirements 1.2, 1.3**
        fetcher = _fetcher_with_both_pools()
        verifier = _make_verifier(fetcher)

        token = _sign(_payload(POOL_A_ISS, client_id="some-other-client"), _KEY_A, "kid-a")
        with pytest.raises(InvalidTokenError) as exc:
            verifier.verify_token(token)
        assert exc.value.http_status == 401
        assert "audience" in exc.value.message.lower()

    def test_expired_token_rejected_401(self):
        """An expired token (beyond the 30s leeway) is rejected with 401."""
        # **Validates: Requirements 1.2, 1.3**
        fetcher = _fetcher_with_both_pools()
        verifier = _make_verifier(fetcher)

        token = _sign(
            _payload(POOL_A_ISS, client_id=POOL_A_AUD, exp_offset=-120), _KEY_A, "kid-a"
        )
        with pytest.raises(TokenExpiredError) as exc:
            verifier.verify_token(token)
        assert exc.value.http_status == 401

    def test_tampered_signature_rejected_401(self):
        """A token whose signature is altered is rejected with 401."""
        # **Validates: Requirements 1.2, 1.3**
        fetcher = _fetcher_with_both_pools()
        verifier = _make_verifier(fetcher)

        token = _sign(_payload(POOL_A_ISS, client_id=POOL_A_AUD), _KEY_A, "kid-a")
        # Tamper at the BYTE level so the change is guaranteed to alter the signature
        # (replacing trailing base64url chars can leave the decoded bytes unchanged).
        import base64 as _b64

        head, body, sig = token.split(".")
        raw = bytearray(_b64.urlsafe_b64decode(sig + "=" * (-len(sig) % 4)))
        raw[len(raw) // 2] ^= 0xFF
        tampered_sig = _b64.urlsafe_b64encode(bytes(raw)).rstrip(b"=").decode()
        tampered = f"{head}.{body}.{tampered_sig}"
        with pytest.raises(InvalidTokenError) as exc:
            verifier.verify_token(tampered)
        assert exc.value.http_status == 401

    def test_wrong_key_signature_rejected_401(self):
        """A token signed with a key the pool does not publish is rejected (401)."""
        # **Validates: Requirements 1.2, 1.3**
        fetcher = _fetcher_with_both_pools()
        verifier = _make_verifier(fetcher)

        # Signed with the rotated key but presented under kid-a (Pool A's published key).
        token = _sign(_payload(POOL_A_ISS, client_id=POOL_A_AUD), _KEY_ROTATED, "kid-a")
        with pytest.raises(InvalidTokenError) as exc:
            verifier.verify_token(token)
        assert exc.value.http_status == 401

    def test_non_rs256_algorithm_rejected_401(self):
        """A token using a non-RS256 algorithm is rejected with 401."""
        # **Validates: Requirements 1.2, 1.3**
        fetcher = _fetcher_with_both_pools()
        verifier = _make_verifier(fetcher)

        token = pyjwt.encode(
            _payload(POOL_A_ISS, client_id=POOL_A_AUD),
            "shared-secret",
            algorithm="HS256",
            headers={"kid": "kid-a", "alg": "HS256"},
        )
        with pytest.raises(InvalidTokenError) as exc:
            verifier.verify_token(token)
        assert exc.value.http_status == 401


# =============================================================================
# Rotation: unknown kid triggers a single refetch, then accept/401
# **Validates: Requirements 3**
# =============================================================================


class TestRotationThroughCache:
    def test_unknown_kid_refetched_once_then_accepts(self):
        """A rotated kid absent from the cached set triggers one refetch, then accepts."""
        # **Validates: Requirements 3**
        fetcher = _FakeFetcher()
        # Initially Pool A publishes only kid-a.
        fetcher.set_keys(POOL_A_JWKS, _jwk(_KEY_A.public_key(), "kid-a"))
        fetcher.set_keys(POOL_B_JWKS, _jwk(_KEY_B.public_key(), "kid-b"))
        verifier = _make_verifier(fetcher)

        # Warm the cache with a kid-a token.
        warm = _sign(_payload(POOL_A_ISS, client_id=POOL_A_AUD), _KEY_A, "kid-a")
        verifier.verify_token(warm)

        # Pool A rotates: now publishes kid-a AND a new kid-rotated.
        fetcher.set_keys(
            POOL_A_JWKS,
            _jwk(_KEY_A.public_key(), "kid-a"),
            _jwk(_KEY_ROTATED.public_key(), "kid-rotated"),
        )

        token = _sign(_payload(POOL_A_ISS, client_id=POOL_A_AUD), _KEY_ROTATED, "kid-rotated")
        result = verifier.verify_token(token)
        assert result["iss"] == POOL_A_ISS

    def test_unknown_kid_after_refetch_rejected_401(self):
        """A kid still absent after the single refetch is rejected with 401. (R3.3)"""
        # **Validates: Requirements 1.3, 3**
        fetcher = _fetcher_with_both_pools()
        verifier = _make_verifier(fetcher)

        # kid-nope is never published by Pool A.
        token = _sign(_payload(POOL_A_ISS, client_id=POOL_A_AUD), _KEY_ROTATED, "kid-nope")
        with pytest.raises(InvalidTokenError) as exc:
            verifier.verify_token(token)
        assert exc.value.http_status == 401
        assert exc.value.message == "Token signing key not found"


# =============================================================================
# Backward-compatible single-pool construction
# =============================================================================


class TestSinglePoolBackwardCompat:
    def test_single_pool_factory_builds_one_entry_registry(self):
        """from_single_pool builds a working one-entry registry verifier."""
        verifier = JWTVerifier.from_single_pool(
            user_pool_id="eu-west-1_PoolAAA",
            region="eu-west-1",
            app_client_id=POOL_A_AUD,
        )
        assert verifier.issuer == POOL_A_ISS
        assert POOL_A_ISS in verifier._registry

    def test_legacy_positional_constructor_still_works(self):
        """The historical positional constructor still constructs a verifier."""
        verifier = JWTVerifier("eu-west-1_PoolAAA", "eu-west-1", POOL_A_AUD)
        assert verifier.app_client_id == POOL_A_AUD
        assert POOL_A_ISS in verifier._registry

    def test_no_args_raises(self):
        """Constructing with neither a registry nor single-pool args raises."""
        with pytest.raises(ValueError):
            JWTVerifier()
