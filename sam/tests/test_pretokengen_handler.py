"""
S4 D2 / T11 (amended, Option A) — unit tests for the Pool A Pre-Token-Generation
Lambda handler, reading the S3 DynamoDB projection (NOT MySQL).

Covers the happy path (R2.1, R2.2, R2.4):

- a mocked Cognito V2 event + a faked projection table produce the expected
  ``custom:entitlements`` claim on BOTH the id-token and access-token generation;
- the user's tenants come from the event's verified ``custom:tenants`` claim
  (``_identify_tenants``), across Cognito delivery shapes;
- existing claims (``cognito:groups`` / ``custom:tenants``) are left untouched
  (additive-only, R2.4);
- an empty/absent ``custom:tenants`` → an empty entitlement claim (valid, not an
  error);
- the claim decodes back (via the shared T4 codec) to the resolver's answer, i.e.
  the Lambda reuses the shared resolver/codec rather than reimplementing them.

DynamoDB is faked (an in-memory table) — no live AWS, no MySQL, no mocks of the
resolver or codec (they are the real shared logic). Config resolution is bypassed
by injecting a reader over the fake table, so these tests need no env wiring (the
fail-fast config + fail-safe path are exercised by the fail-safe test module).
"""

import os
import sys

import pytest

# repo root on sys.path (mirrors sam/conftest.py) so `sam.pretokengen` imports.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from sam.pretokengen import handler as handler_mod
from sam.pretokengen.projection_governance_reader import ProjectionGovernanceReader

# The shared codec/resolver the handler reuses — imported here to assert the
# stamped claim round-trips to the resolver's answer (one rule, two carriers).
_BACKEND_SRC = os.path.join(_REPO_ROOT, "backend", "src")
if _BACKEND_SRC not in sys.path:
    sys.path.insert(0, _BACKEND_SRC)

from auth.entitlement_claim_codec import CLAIM_NAME, decode_entitlements
from auth.entitlement_resolver import resolve_entitlement
from services import projection_schema as schema
from services.module_registry import MODULE_REGISTRY


# ---------------------------------------------------------------------------
# In-memory fake projection table
# ---------------------------------------------------------------------------


class FakeTable:
    """In-memory boto3 DynamoDB Table stand-in (query side, tenant-scoped)."""

    def __init__(self):
        self.store: dict[tuple, dict] = {}

    def put(self, item: dict) -> None:
        key = (item[schema.PARTITION_KEY_ATTR], item[schema.SORT_KEY_ATTR])
        self.store[key] = dict(item)

    def query(self, KeyConditionExpression=None):
        tenant_id = KeyConditionExpression.get_expression()["values"][1]
        return {"Items": [dict(v) for k, v in self.store.items() if k[0] == tenant_id]}


def _role_item(tenant_id, email, role):
    return {
        schema.PARTITION_KEY_ATTR: tenant_id,
        schema.SORT_KEY_ATTR: schema.build_sort_key(
            schema.RECORD_TYPE_ROLE, email, role
        ),
        "role": role,
        schema.VERSION_ATTR: 1,
    }


def _module_item(tenant_id, module_name, is_active=True):
    return {
        schema.PARTITION_KEY_ATTR: tenant_id,
        schema.SORT_KEY_ATTR: schema.build_sort_key(
            schema.RECORD_TYPE_MODULE, module_name
        ),
        "is_active": is_active,
        schema.VERSION_ATTR: 1,
    }


def make_v2_event(
    email, tenants="ExampleTenant", existing_id_claims=None, existing_access_claims=None
):
    """Build a Cognito V2 Pre-Token-Generation event.

    ``tenants`` is placed on ``userAttributes["custom:tenants"]`` (the shape the
    handler reads); pass a list, a JSON string, a scalar, or ``None`` to omit it.
    ``existing_*_claims`` seed pre-existing claimsToAddOrOverride on a generation.
    """
    id_gen = {}
    access_gen = {}
    if existing_id_claims is not None:
        id_gen["claimsToAddOrOverride"] = dict(existing_id_claims)
    if existing_access_claims is not None:
        access_gen["claimsToAddOrOverride"] = dict(existing_access_claims)

    user_attributes = {"email": email, "sub": "sub-123"}
    if tenants is not None:
        user_attributes["custom:tenants"] = tenants

    return {
        "version": "2",
        "triggerSource": "TokenGeneration_HostedAuth",
        "userPoolId": "eu-west-1_xyrlzfqbl",
        "request": {
            "userAttributes": user_attributes,
            "groupConfiguration": {"groupsToOverride": ["Administrators"]},
        },
        "response": {
            "claimsAndScopeOverrideDetails": {
                "idTokenGeneration": id_gen,
                "accessTokenGeneration": access_gen,
            }
        },
    }


@pytest.fixture
def patch_reader(monkeypatch):
    """Make ``handler._build_reader`` return a reader over a FakeTable.

    Bypasses config resolution + the real DynamoDB client so the happy-path tests
    are pure (the fail-safe module covers config/fail-safe).
    """

    def _install(table):
        reader = ProjectionGovernanceReader(table=table)
        monkeypatch.setattr(handler_mod, "_build_reader", lambda: reader)
        return table

    return _install


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestHandlerHappyPath:
    def test_stamps_expected_claim_on_both_id_and_access_tokens(self, patch_reader):
        email = "admin@example.com"
        table = FakeTable()
        table.put(_role_item("ExampleTenant", email, "Finance_CRUD"))
        table.put(_role_item("ExampleTenant", email, "STR_Read"))
        table.put(_module_item("ExampleTenant", "FIN", is_active=True))
        table.put(_module_item("ExampleTenant", "STR", is_active=True))
        patch_reader(table)

        event = make_v2_event(email, tenants="ExampleTenant")
        result = handler_mod.handler(event, context=None)

        details = result["response"]["claimsAndScopeOverrideDetails"]
        id_claims = details["idTokenGeneration"]["claimsToAddOrOverride"]
        access_claims = details["accessTokenGeneration"]["claimsToAddOrOverride"]

        # Same claim present on BOTH generations (R2.1 — access token carries it).
        assert CLAIM_NAME in id_claims
        assert CLAIM_NAME in access_claims
        assert id_claims[CLAIM_NAME] == access_claims[CLAIM_NAME]

        # The stamped claim decodes to the SHARED resolver's answer (reuse, not
        # a reimplementation).
        expected_map = resolve_entitlement(
            {"ExampleTenant": ["Finance_CRUD", "STR_Read"]},
            {"ExampleTenant": ["FIN", "STR"]},
            MODULE_REGISTRY,
        )
        decoded = decode_entitlements(id_claims[CLAIM_NAME])
        assert not decoded.fallback_required
        assert not decoded.is_overflow
        assert decoded.tenants == expected_map

    def test_existing_claims_are_untouched(self, patch_reader):
        """R2.4 — additive only: cognito:groups / custom:tenants unchanged."""
        table = FakeTable()
        table.put(_role_item("ExampleTenant", "admin@example.com", "Finance_CRUD"))
        table.put(_module_item("ExampleTenant", "FIN", is_active=True))
        patch_reader(table)

        existing = {
            "cognito:groups": "Administrators",
            "custom:tenants": "ExampleTenant",
        }
        event = make_v2_event(
            "admin@example.com",
            tenants="ExampleTenant",
            existing_id_claims=existing,
            existing_access_claims=existing,
        )
        result = handler_mod.handler(event, context=None)

        details = result["response"]["claimsAndScopeOverrideDetails"]
        for gen in ("idTokenGeneration", "accessTokenGeneration"):
            claims = details[gen]["claimsToAddOrOverride"]
            assert claims["cognito:groups"] == "Administrators"
            assert claims["custom:tenants"] == "ExampleTenant"
            assert CLAIM_NAME in claims  # our claim added alongside

    def test_tenants_read_from_custom_tenants_json_string(self, patch_reader):
        """R2.4 — the tenant list comes from ``custom:tenants`` (Cognito shapes)."""
        table = FakeTable()
        table.put(_role_item("TenantA", "u@example.com", "Finance_CRUD"))
        table.put(_module_item("TenantA", "FIN", is_active=True))
        table.put(_role_item("TenantB", "u@example.com", "STR_CRUD"))
        table.put(_module_item("TenantB", "STR", is_active=True))
        patch_reader(table)

        # JSON-encoded list is one of Cognito's real delivery shapes.
        event = make_v2_event("u@example.com", tenants='["TenantA","TenantB"]')
        result = handler_mod.handler(event, context=None)
        claim = result["response"]["claimsAndScopeOverrideDetails"][
            "idTokenGeneration"
        ]["claimsToAddOrOverride"][CLAIM_NAME]
        decoded = decode_entitlements(claim)

        assert set(decoded.tenants.keys()) == {"TenantA", "TenantB"}

    def test_empty_custom_tenants_yields_empty_entitlement_claim(self, patch_reader):
        """Absent/empty custom:tenants → empty entitlement (valid, not an error)."""
        table = FakeTable()
        # Even if the table holds data, no tenants means nothing is resolvable.
        table.put(_role_item("TenantA", "u@example.com", "Finance_CRUD"))
        table.put(_module_item("TenantA", "FIN", is_active=True))
        patch_reader(table)

        event = make_v2_event("u@example.com", tenants=None)
        result = handler_mod.handler(event, context=None)

        claim = result["response"]["claimsAndScopeOverrideDetails"][
            "idTokenGeneration"
        ]["claimsToAddOrOverride"][CLAIM_NAME]
        decoded = decode_entitlements(claim)
        # A valid, empty entitlement — the claim is stamped, just with no tenants.
        assert not decoded.fallback_required
        assert not decoded.is_overflow
        assert decoded.tenants == {}

    def test_multi_tenant_user_resolves_per_tenant(self, patch_reader):
        """A user in two tenants gets a per-tenant map; inactive-module role dropped."""
        table = FakeTable()
        table.put(_role_item("TenantA", "multi@example.com", "Finance_CRUD"))
        table.put(_module_item("TenantA", "FIN", is_active=True))
        table.put(_role_item("TenantB", "multi@example.com", "STR_CRUD"))
        # TenantB has STR role but STR is NOT active -> no caps for TenantB.
        table.put(_module_item("TenantB", "STR", is_active=False))
        patch_reader(table)

        event = make_v2_event("multi@example.com", tenants=["TenantA", "TenantB"])
        result = handler_mod.handler(event, context=None)
        claim = result["response"]["claimsAndScopeOverrideDetails"][
            "idTokenGeneration"
        ]["claimsToAddOrOverride"][CLAIM_NAME]
        decoded = decode_entitlements(claim)

        assert set(decoded.tenants.keys()) == {"TenantA", "TenantB"}
        assert decoded.tenants["TenantA"], "active FIN grants caps"
        assert decoded.tenants["TenantB"] == [], "inactive STR grants nothing"

    def test_stamps_when_response_containers_arrive_as_null(self, patch_reader):
        """Regression (S5c task 5.5): the REAL Cognito V2 event delivers the
        ``response`` containers **present but null** — ``claimsAndScopeOverrideDetails``
        and each generation block are JSON ``null`` (Python ``None``), NOT empty
        dicts. A plain ``setdefault`` returned that existing ``None`` and the next
        ``.setdefault`` raised ``'NoneType' object has no attribute 'setdefault'``,
        which blocked login on ``myAdmin-test``. The handler must coerce
        present-but-null containers to dicts and still stamp the claim on BOTH
        generations."""
        email = "admin@example.com"
        table = FakeTable()
        table.put(_role_item("ExampleTenant", email, "Finance_CRUD"))
        table.put(_module_item("ExampleTenant", "FIN", is_active=True))
        patch_reader(table)

        # The real Cognito shape: response present, but the details/generation
        # blocks are null rather than pre-seeded empty dicts.
        event = make_v2_event(email, tenants="ExampleTenant")
        event["response"] = {"claimsAndScopeOverrideDetails": None}

        result = handler_mod.handler(event, context=None)

        details = result["response"]["claimsAndScopeOverrideDetails"]
        for gen in ("idTokenGeneration", "accessTokenGeneration"):
            claims = details[gen]["claimsToAddOrOverride"]
            assert CLAIM_NAME in claims, f"claim must be stamped on {gen}"

    def test_stamps_when_generation_blocks_arrive_as_null(self, patch_reader):
        """Same regression at the next level: ``claimsAndScopeOverrideDetails`` is a
        dict but each generation block is ``None`` — still must be coerced + stamped."""
        email = "admin@example.com"
        table = FakeTable()
        table.put(_role_item("ExampleTenant", email, "Finance_CRUD"))
        table.put(_module_item("ExampleTenant", "FIN", is_active=True))
        patch_reader(table)

        event = make_v2_event(email, tenants="ExampleTenant")
        event["response"] = {
            "claimsAndScopeOverrideDetails": {
                "idTokenGeneration": None,
                "accessTokenGeneration": None,
            }
        }

        result = handler_mod.handler(event, context=None)

        details = result["response"]["claimsAndScopeOverrideDetails"]
        for gen in ("idTokenGeneration", "accessTokenGeneration"):
            claims = details[gen]["claimsToAddOrOverride"]
            assert CLAIM_NAME in claims, f"claim must be stamped on {gen}"


class TestUserIdentification:
    def test_missing_identity_raises(self, patch_reader):
        patch_reader(FakeTable())
        event = make_v2_event("admin@example.com")
        event["request"]["userAttributes"] = {}  # no email, no sub
        with pytest.raises(ValueError):
            handler_mod.handler(event, context=None)

    def test_falls_back_to_sub_when_no_email(self, patch_reader):
        """With no email, the sub keys the role filter; roles keyed by sub resolve."""
        table = FakeTable()
        # Role items projected under the sub (the only identity available).
        table.put(_role_item("TenantA", "sub-xyz", "Finance_CRUD"))
        table.put(_module_item("TenantA", "FIN", is_active=True))
        patch_reader(table)

        event = make_v2_event("admin@example.com", tenants="TenantA")
        event["request"]["userAttributes"] = {
            "sub": "sub-xyz",
            "custom:tenants": "TenantA",
        }
        result = handler_mod.handler(event, context=None)

        claim = result["response"]["claimsAndScopeOverrideDetails"][
            "idTokenGeneration"
        ]["claimsToAddOrOverride"][CLAIM_NAME]
        decoded = decode_entitlements(claim)
        # The role filtered to the sub resolved into TenantA's entitlement.
        assert decoded.tenants["TenantA"], "sub-keyed role resolved"
