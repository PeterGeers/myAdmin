"""
S4 T16 (amended, Option A) — acceptance integration test: token carries
entitlement (read from the S3 DynamoDB projection), reader authorizes.

Feature: s4-token-entitlement-projection (acceptance; gates the production step T18).

End-to-end, cross-plane acceptance for S4, exercising the real pieces together
against the LOCAL ``dynamodb-local`` projection table (the T0/S3 seam) with
OFFLINE-signed tokens (no network, no live Cognito — deterministic, mirroring the
S2/S3 harness). This replaces the original Docker-MySQL drive: after Design
amendment A the handler reads the DynamoDB projection, not MySQL.

  1. Handler stamps custom:entitlements (reading the projection for the event's
     ``custom:tenants``) on BOTH id + access token generations, additively
     (pre-existing cognito:groups / custom:tenants untouched, R2.4).
  2. The module-plane reader authorizes from the VERIFIED token (R5.1/R5.2): a held
     capability -> True, an unheld one -> False, a tenant not in the token -> None.
  3. Consistency check (R4.1): the token's per-tenant caps equal the shared T1
     resolver's answer over the same projection rows the handler read (one rule,
     two carriers — only the source of the rows changed to the projection).

Placement: backend/tests/integration/ (auto-marked integration). Imports the sam
handler/reader via sys.path (repo root + backend/src), like the sam tests + the
PreTokenGen Lambda. Skips cleanly if local DynamoDB is unreachable on :8000.
"""

import json
import os
import socket
import sys
import time
import uuid

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

import jwt as pyjwt
from jwt import algorithms

_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
_BACKEND_SRC = os.path.join(_REPO_ROOT, "backend", "src")
for _p in (_REPO_ROOT, _BACKEND_SRC):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from sam.pretokengen import handler as handler_mod  # noqa: E402
from sam.pretokengen.projection_governance_reader import (  # noqa: E402
    ProjectionGovernanceReader,
)
from sam.shared.auth_utils import (  # noqa: E402
    JWKSCache,
    JWTVerifier,
    PoolConfig,
    PoolRegistry,
    get_entitlements,
    has_capability,
)
from sam.shared.entitlement_claim import CLAIM_NAME, decode_entitlements  # noqa: E402

from auth.cognito_utils import ROLE_PERMISSIONS  # noqa: E402
from auth.entitlement_resolver import resolve_entitlement  # noqa: E402
from services import projection_schema as schema  # noqa: E402
from services.module_registry import MODULE_REGISTRY  # noqa: E402


# --- Local DynamoDB coordinates (offline emulator, never real AWS) --------- #

_DDB_ENDPOINT = os.environ.get("AWS_ENDPOINT_URL_DYNAMODB", "http://localhost:8000")
_DDB_REGION = os.environ.get("AWS_REGION", "eu-west-1")
_PROJECTION_TABLE = os.environ.get(
    "GOVERNANCE_PROJECTION_TABLE", "test_governance_projection"
)

# A synthetic (obviously-fake) user + tenant seeded for this run — never real PII.
_SEEDED_EMAIL = "s4-e2e@example.invalid"
_SEEDED_TENANT = "S4-E2E-TENANT"

_TEST_ISS = "https://cognito-idp.eu-west-1.amazonaws.com/eu-west-1_xyrlzfqbl"
_TEST_JWKS_URI = f"{_TEST_ISS}/.well-known/jwks.json"
_TEST_CLIENT_ID = "test-app-client-id"
_TEST_KID = "s4-test-key-1"


def _ddb_reachable() -> bool:
    host_port = _DDB_ENDPOINT.split("//", 1)[-1]
    host, _, port = host_port.partition(":")
    port = int(port or "8000")
    s = socket.socket()
    s.settimeout(3)
    try:
        s.connect((host, port))
        return True
    except OSError:
        return False
    finally:
        s.close()


pytestmark = pytest.mark.skipif(
    not _ddb_reachable(),
    reason=(
        f"local DynamoDB not reachable at {_DDB_ENDPOINT} "
        "(start the dynamodb-local container to run the S4 e2e)"
    ),
)


# --- Choose a granting role from the module registry so caps are non-empty -- #


def _pick_module_and_role():
    """Return an (active_module_name, granting_role) pair from MODULE_REGISTRY.

    Uses a real registry module + one of its ``required_roles`` whose role
    expands to non-empty capabilities via ROLE_PERMISSIONS, so the resolver yields
    non-empty capabilities for the seeded tenant (a genuine positive case).
    """
    for module_name, descriptor in MODULE_REGISTRY.items():
        required = (descriptor or {}).get("required_roles") or []
        for role in required:
            if ROLE_PERMISSIONS.get(role):
                return module_name, role
    pytest.skip(
        "MODULE_REGISTRY has no module with a capability-granting required_role"
    )


# --- DynamoDB fixture: build the table handle + seed/cleanup this run's items #


def _local_table():
    import boto3

    resource = boto3.resource(
        "dynamodb",
        endpoint_url=_DDB_ENDPOINT,
        region_name=_DDB_REGION,
        aws_access_key_id="local",
        aws_secret_access_key="local",
        aws_session_token="local",
    )
    return resource.Table(_PROJECTION_TABLE)


def _ensure_table(table):
    """Create the projection table if the seed script hasn't been run yet."""
    import boto3
    from botocore.exceptions import ClientError

    client = table.meta.client
    try:
        client.describe_table(TableName=_PROJECTION_TABLE)
        return
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "ResourceNotFoundException":
            raise

    boto3.resource(
        "dynamodb",
        endpoint_url=_DDB_ENDPOINT,
        region_name=_DDB_REGION,
        aws_access_key_id="local",
        aws_secret_access_key="local",
        aws_session_token="local",
    ).create_table(
        TableName=_PROJECTION_TABLE,
        KeySchema=[
            {"AttributeName": schema.PARTITION_KEY_ATTR, "KeyType": "HASH"},
            {"AttributeName": schema.SORT_KEY_ATTR, "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": schema.PARTITION_KEY_ATTR, "AttributeType": "S"},
            {"AttributeName": schema.SORT_KEY_ATTR, "AttributeType": "S"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )
    client.get_waiter("table_exists").wait(TableName=_PROJECTION_TABLE)


@pytest.fixture
def seeded_projection():
    """Seed the local projection partition for this run's tenant, then clean up.

    Uses a unique per-run tenant id so parallel/repeat runs never collide, and
    deletes exactly the seeded items afterwards (no prod copy, no cross-test
    residue).
    """
    module_name, role = _pick_module_and_role()
    tenant = f"{_SEEDED_TENANT}-{uuid.uuid4().hex[:8]}"

    table = _local_table()
    _ensure_table(table)

    items = [
        {
            schema.PARTITION_KEY_ATTR: tenant,
            schema.SORT_KEY_ATTR: schema.build_sort_key(schema.RECORD_TYPE_TENANT),
            schema.VERSION_ATTR: 1,
        },
        {
            schema.PARTITION_KEY_ATTR: tenant,
            schema.SORT_KEY_ATTR: schema.build_sort_key(
                schema.RECORD_TYPE_MODULE, module_name
            ),
            "is_active": True,
            schema.VERSION_ATTR: 1,
        },
        {
            schema.PARTITION_KEY_ATTR: tenant,
            schema.SORT_KEY_ATTR: schema.build_sort_key(
                schema.RECORD_TYPE_ROLE, _SEEDED_EMAIL, role
            ),
            "role": role,
            schema.VERSION_ATTR: 1,
        },
    ]
    for item in items:
        table.put_item(Item=item)

    yield {"tenant": tenant, "module": module_name, "role": role, "table": table}

    for item in items:
        table.delete_item(
            Key={
                schema.PARTITION_KEY_ATTR: item[schema.PARTITION_KEY_ATTR],
                schema.SORT_KEY_ATTR: item[schema.SORT_KEY_ATTR],
            }
        )


# --- Offline token signing (RS256, in-test keys) --------------------------- #


def _generate_rsa_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _jwk_from_private_key(private_key, kid: str) -> dict:
    jwk = json.loads(algorithms.RSAAlgorithm.to_jwk(private_key.public_key()))
    jwk["kid"] = kid
    jwk["alg"] = "RS256"
    jwk["use"] = "sig"
    return jwk


def _private_pem(private_key) -> bytes:
    return private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


def _sign_token(private_key, extra_claims: dict) -> str:
    now = int(time.time())
    claims = {
        "sub": "user-s4-e2e",
        "iss": _TEST_ISS,
        "client_id": _TEST_CLIENT_ID,
        "token_use": "access",
        "iat": now,
        "exp": now + 3600,
    }
    claims.update(extra_claims)
    return pyjwt.encode(
        claims, _private_pem(private_key), algorithm="RS256", headers={"kid": _TEST_KID}
    )


@pytest.fixture
def signing_key():
    return _generate_rsa_key()


@pytest.fixture
def verifier(signing_key):
    registry = PoolRegistry(
        [
            PoolConfig(
                iss=_TEST_ISS,
                jwks_uri=_TEST_JWKS_URI,
                audience=_TEST_CLIENT_ID,
                pool_label="myAdmin-test",
            )
        ]
    )
    document = {"keys": [_jwk_from_private_key(signing_key, _TEST_KID)]}
    cache = JWKSCache(registry=registry, fetcher=lambda _uri: document)
    return JWTVerifier(registry=registry, jwks_cache=cache)


@pytest.fixture(autouse=True)
def _projection_env_and_cache(monkeypatch):
    """Point the handler's reader at local DynamoDB + reset the cold-start cache."""
    monkeypatch.setenv("AWS_ENDPOINT_URL_DYNAMODB", _DDB_ENDPOINT)
    monkeypatch.setenv("AWS_REGION", _DDB_REGION)
    monkeypatch.setenv("GOVERNANCE_PROJECTION_TABLE", _PROJECTION_TABLE)
    # Dummy creds so boto3 signs requests against the emulator (never real AWS).
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "local")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "local")
    handler_mod._reader_cache = None
    yield
    handler_mod._reader_cache = None


def _v2_event(email: str, tenant: str) -> dict:
    return {
        "version": "2",
        "triggerSource": "TokenGeneration_HostedAuth",
        "userPoolId": "eu-west-1_xyrlzfqbl",
        "request": {
            "userAttributes": {
                "email": email,
                "sub": "user-s4-e2e",
                "custom:tenants": tenant,
            },
            "groupConfiguration": {"groupsToOverride": ["Administrators"]},
        },
        "response": {
            "claimsAndScopeOverrideDetails": {
                "idTokenGeneration": {
                    "claimsToAddOrOverride": {
                        "cognito:groups": "Administrators",
                        "custom:tenants": tenant,
                    }
                },
                "accessTokenGeneration": {
                    "claimsToAddOrOverride": {
                        "cognito:groups": "Administrators",
                    }
                },
            }
        },
    }


def _stamped_claim(result: dict, generation: str) -> str:
    gen = result["response"]["claimsAndScopeOverrideDetails"][generation]
    return gen["claimsToAddOrOverride"][CLAIM_NAME]


def test_handler_stamps_entitlement_from_projection_additively(seeded_projection):
    tenant = seeded_projection["tenant"]
    event = _v2_event(_SEEDED_EMAIL, tenant)
    result = handler_mod.handler(event, context=None)

    id_claim = _stamped_claim(result, "idTokenGeneration")
    access_claim = _stamped_claim(result, "accessTokenGeneration")
    assert id_claim == access_claim

    decoded = decode_entitlements(id_claim)
    assert decoded.fallback_required is False
    assert decoded.is_overflow is False
    assert tenant in decoded.tenants
    assert decoded.tenants[tenant], "expected non-empty capabilities"

    id_over = result["response"]["claimsAndScopeOverrideDetails"]["idTokenGeneration"][
        "claimsToAddOrOverride"
    ]
    assert id_over["cognito:groups"] == "Administrators"
    assert id_over["custom:tenants"] == tenant


def test_module_reader_authorizes_from_verified_token(
    seeded_projection, signing_key, verifier
):
    tenant = seeded_projection["tenant"]
    result = handler_mod.handler(_v2_event(_SEEDED_EMAIL, tenant), context=None)
    claim_value = _stamped_claim(result, "accessTokenGeneration")
    decoded = decode_entitlements(claim_value)
    caps = decoded.tenants[tenant]
    assert caps, "expected the seeded grant to yield capabilities"

    token = _sign_token(signing_key, {CLAIM_NAME: claim_value})
    event = {"headers": {"Authorization": f"Bearer {token}"}}

    verified = get_entitlements(event, verifier=verifier)
    assert verified.fallback_required is False
    assert verified.capabilities_for(tenant) == caps

    held = caps[0]
    verified_claims = verifier.verify_token(token)
    assert has_capability(verified_claims, tenant, held) is True
    assert (
        has_capability(verified_claims, tenant, "definitely_not_a_real_cap") is False
    )
    assert has_capability(verified_claims, "SomeOtherTenant", held) is None


def test_token_answer_matches_shared_resolver(seeded_projection):
    """R4.1 — the token's caps equal the resolver's over the SAME projection rows."""
    tenant = seeded_projection["tenant"]

    # Read the same rows the handler reads, via the same reader, then resolve.
    reader = ProjectionGovernanceReader()
    roles_by_tenant = reader.get_user_roles_by_tenant(_SEEDED_EMAIL, [tenant])
    active_modules_by_tenant = reader.get_active_modules_by_tenant([tenant])
    resolver_map = resolve_entitlement(
        roles_by_tenant, active_modules_by_tenant, MODULE_REGISTRY
    )

    result = handler_mod.handler(_v2_event(_SEEDED_EMAIL, tenant), context=None)
    token_decoded = decode_entitlements(_stamped_claim(result, "idTokenGeneration"))

    assert set(token_decoded.tenants) == set(resolver_map)
    for t, caps in resolver_map.items():
        assert sorted(token_decoded.tenants[t]) == sorted(caps), t
