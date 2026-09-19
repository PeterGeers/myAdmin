"""
S5 Task 2.1 — verification: entitle the pilot tenant and confirm the projection
answers for the ``members`` module.

Feature: s5-members-first-migration (Step 2, C7). Requirements R4.2, R6.1.

This is the test-proven verification the task calls for. Entitling a tenant is a
config/data operation against a live MySQL/S3 environment, so the DELIVERABLE for
task 2.1 is a test that proves the plumbing answers correctly WITHOUT a live AWS or
MySQL/Cognito. It exercises the REAL pieces end-to-end with in-memory fakes:

    activate_module (MySQL plane, tenant_modules)
        -> build_projection_items (the S3 one-directional projection builder)
        -> ProjectionGovernanceReader (reads the projection back — the SAME reader
           the PreTokenGen Lambda + entitlement toolkit use)
        -> resolve_entitlement (the ONE shared resolver: roles ∩ active modules → caps)
        -> encode_entitlements / decode (the token claim carrier)
        -> has_capability (sam/shared/auth_utils — the toolkit the Members handler
           edge, task 3.0, will gate on)

Cross-plane placement (backend/tests/integration/) mirrors the existing S4 e2e
(``test_s4_token_entitlement_e2e.py``): it imports the sam-plane reader + toolkit
via sys.path (repo root + backend/src) and the backend-plane resolver/codec/registry.
Unlike that test it uses NO dynamodb-local and NO MySQL — a mock ``DatabaseManager``
records the ``tenant_modules`` write and an in-memory ``FakeTable`` (mirroring
``sam/tests/test_projection_governance_reader.py``) stands in for the projection.

Scoping guardrails honoured:
- ``h-dcn`` appears ONLY as TEST data here; no production code path hardcodes it.
- Entitlement is backing-agnostic — ``MEMBERS`` is sam-backed and activates with no
  code change (design C7); the test asserts that INSERT path is reached.
"""

import os
import sys
from unittest.mock import Mock

# repo root + backend/src on sys.path (mirrors the S4 e2e + sam tests) so BOTH the
# sam-plane (sam.shared / sam.pretokengen) and backend-plane imports resolve.
_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
_BACKEND_SRC = os.path.join(_REPO_ROOT, "backend", "src")
for _p in (_REPO_ROOT, _BACKEND_SRC):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest  # noqa: E402

from sam.pretokengen.projection_governance_reader import (  # noqa: E402
    ProjectionGovernanceReader,
)
from sam.shared.auth_utils import has_capability  # noqa: E402
from sam.shared.entitlement_claim import CLAIM_NAME  # noqa: E402

from auth.entitlement_resolver import resolve_entitlement  # noqa: E402
from auth.cognito_utils import ROLE_PERMISSIONS  # noqa: E402
from services import projection_schema as schema  # noqa: E402
from services.module_registry import (  # noqa: E402
    MODULE_REGISTRY,
    activate_module,
    module_backing,
)
from services.projection_builder import build_projection_items  # noqa: E402
from auth.entitlement_claim_codec import encode_entitlements  # noqa: E402


# --- Test data (h-dcn is TEST data ONLY — never a hardcoded production value) --- #

PILOT_TENANT = "h-dcn"
MEMBER_ADMIN_EMAIL = "pilot-admin@example.invalid"
MODULE_NAME = "MEMBERS"  # the MODULE_REGISTRY key (task 2.0)

# The capability vocabulary the Members handler routes declare and the handler edge
# (task 3.0) gates on — mirrors sam/members/handler/routes.py CAP_MEMBERS_*.
CAP_READ = "members:read"
CAP_WRITE = "members:write"
CAP_EXPORT = "members:export"
CAP_ADMIN = "members:admin"


# --- In-memory projection table (mirrors sam/tests/test_projection_governance_reader) --- #


class FakeTable:
    """In-memory stand-in for a boto3 DynamoDB Table (query side only).

    ``query(KeyConditionExpression=Key(pk).eq(tenant))`` returns ONLY that
    partition's items, exactly like the projection reader's tenant-scoped read
    (the tenancy boundary a real table + IAM ``LeadingKeys`` enforces). No live AWS.
    """

    def __init__(self):
        self.store: dict[tuple, dict] = {}

    def put(self, item: dict) -> None:
        key = (item[schema.PARTITION_KEY_ATTR], item[schema.SORT_KEY_ATTR])
        self.store[key] = dict(item)

    def query(self, KeyConditionExpression=None):
        expr = KeyConditionExpression.get_expression()
        tenant_id = expr["values"][1]
        items = [dict(v) for k, v in self.store.items() if k[0] == tenant_id]
        return {"Items": items}


def _mock_db_recording_tenant_modules():
    """A mock DatabaseManager that records the tenant_modules INSERT (no real MySQL).

    Returns ``(db, inserts)`` where ``inserts`` collects the (tenant, module,
    is_active-intent) tuples the INSERT ... ON DUPLICATE KEY UPDATE path writes. The
    connection guard in tests/unit/conftest is irrelevant here (integration plane),
    but we still never open a real connection — everything is a Mock side_effect.
    """
    inserts: list[tuple] = []

    def execute_query(query, params=None, fetch=True, commit=False, pool_type="primary"):
        sql = " ".join(query.strip().upper().split())
        if sql.startswith("INSERT INTO TENANT_MODULES"):
            # params == (tenant, module_name, activated_by)
            inserts.append((params[0], params[1]))
            return 1
        # has_module dependency checks / anything else: no rows.
        return []

    db = Mock()
    db.execute_query = Mock(side_effect=execute_query)
    db._inserts = inserts
    return db, inserts


def _project_and_read(tenant_modules_rows, role_rows):
    """Run the REAL projection builder, load a FakeTable, read it back.

    Returns ``(active_modules_by_tenant, roles_by_tenant)`` exactly as the toolkit /
    PreTokenGen Lambda would obtain them from the S3 projection.
    """
    tenant_row = {"administration": PILOT_TENANT, "version": 1}
    items = build_projection_items(tenant_row, tenant_modules_rows, role_rows)

    table = FakeTable()
    for item in items:
        table.put(item.to_dynamodb_item())

    reader = ProjectionGovernanceReader(table=table)
    roles_by_tenant = reader.get_user_roles_by_tenant(
        MEMBER_ADMIN_EMAIL, [PILOT_TENANT]
    )
    active_by_tenant = reader.get_active_modules_by_tenant([PILOT_TENANT])
    return active_by_tenant, roles_by_tenant


def _claims_from_entitlement(entitlement_map):
    """Encode a resolved entitlement into a verified-claims dict (token carrier)."""
    return {CLAIM_NAME: encode_entitlements(entitlement_map)}


# --------------------------------------------------------------------------- #
# 0 — Precondition: MEMBERS is registered sam-backed (task 2.0) with generic roles
# --------------------------------------------------------------------------- #


def test_members_module_is_registered_sam_backed_with_generic_roles():
    assert MODULE_NAME in MODULE_REGISTRY
    assert module_backing(MODULE_NAME) == "sam"
    assert set(MODULE_REGISTRY[MODULE_NAME]["required_roles"]) == {
        "Members_CRUD",
        "Members_Read",
        "Members_Export",
    }


# --------------------------------------------------------------------------- #
# 1 — Entitlement is backing-agnostic: activate_module writes tenant_modules
# --------------------------------------------------------------------------- #


def test_activate_module_entitles_sam_backed_members_via_tenant_modules():
    """A sam-backed module entitles exactly like a flask one — the INSERT path runs
    with NO code change (design C7). We assert the tenant_modules write happened for
    the pilot tenant + MEMBERS (the value flows in as a param — never hardcoded)."""
    db, inserts = _mock_db_recording_tenant_modules()

    ok = activate_module(db, PILOT_TENANT, MODULE_NAME, activated_by="test")

    assert ok is True
    assert (PILOT_TENANT, MODULE_NAME) in inserts


# --------------------------------------------------------------------------- #
# 2 — The S3 projection carries the tenant's members module + roles
# --------------------------------------------------------------------------- #


def test_projection_carries_members_module_and_roles_for_entitled_tenant():
    tenant_modules_rows = [
        {"module_name": MODULE_NAME, "is_active": True, "version": 1},
    ]
    role_rows = [
        {"email": MEMBER_ADMIN_EMAIL, "role": "Members_CRUD", "version": 1},
    ]

    active_by_tenant, roles_by_tenant = _project_and_read(
        tenant_modules_rows, role_rows
    )

    # The projection carries MEMBERS as an ACTIVE module for the pilot tenant...
    assert active_by_tenant == {PILOT_TENANT: [MODULE_NAME]}
    # ...and the tenant's Members role for the calling user.
    assert roles_by_tenant == {PILOT_TENANT: ["Members_CRUD"]}


def test_projection_omits_inactive_members_module():
    """Entitlement withdrawn (is_active False) => module absent from active set —
    the fail-safe/reversible property the pilot relies on."""
    tenant_modules_rows = [
        {"module_name": MODULE_NAME, "is_active": False, "version": 1},
    ]
    role_rows = [
        {"email": MEMBER_ADMIN_EMAIL, "role": "Members_CRUD", "version": 1},
    ]

    active_by_tenant, _ = _project_and_read(tenant_modules_rows, role_rows)

    assert active_by_tenant == {PILOT_TENANT: []}


# --------------------------------------------------------------------------- #
# 3 — has_capability resolves correctly from the projection-backed entitlement
# --------------------------------------------------------------------------- #


def test_has_capability_resolves_members_caps_for_crud_role():
    """The whole chain: projection -> resolver -> token claim -> has_capability.

    A Members_CRUD holder on an entitled tenant must get every members capability the
    handler edge gates on (read/write/export/admin), and has_capability must return
    an authoritative True for each."""
    tenant_modules_rows = [
        {"module_name": MODULE_NAME, "is_active": True, "version": 1},
    ]
    role_rows = [
        {"email": MEMBER_ADMIN_EMAIL, "role": "Members_CRUD", "version": 1},
    ]

    active_by_tenant, roles_by_tenant = _project_and_read(
        tenant_modules_rows, role_rows
    )
    entitlement = resolve_entitlement(
        roles_by_tenant, active_by_tenant, MODULE_REGISTRY
    )

    # The resolver produced the members caps for the pilot tenant (not empty).
    assert sorted(entitlement[PILOT_TENANT]) == sorted(
        [CAP_READ, CAP_WRITE, CAP_EXPORT, CAP_ADMIN]
    )

    claims = _claims_from_entitlement(entitlement)
    for cap in (CAP_READ, CAP_WRITE, CAP_EXPORT, CAP_ADMIN):
        assert has_capability(claims, PILOT_TENANT, cap) is True


def test_has_capability_read_role_grants_read_only():
    """Members_Read is read-only: read True, write/admin authoritative False."""
    tenant_modules_rows = [
        {"module_name": MODULE_NAME, "is_active": True, "version": 1},
    ]
    role_rows = [
        {"email": MEMBER_ADMIN_EMAIL, "role": "Members_Read", "version": 1},
    ]

    active_by_tenant, roles_by_tenant = _project_and_read(
        tenant_modules_rows, role_rows
    )
    entitlement = resolve_entitlement(
        roles_by_tenant, active_by_tenant, MODULE_REGISTRY
    )
    claims = _claims_from_entitlement(entitlement)

    assert has_capability(claims, PILOT_TENANT, CAP_READ) is True
    # Present, usable claim that lists the tenant but NOT these caps => authoritative
    # False (not None). This is the token answering "denied", never a silent allow.
    assert has_capability(claims, PILOT_TENANT, CAP_WRITE) is False
    assert has_capability(claims, PILOT_TENANT, CAP_ADMIN) is False


def test_has_capability_denies_when_module_not_entitled():
    """If MEMBERS is NOT active, the Members role grants nothing — the module gate
    (roles ∩ active modules) drops it, so has_capability is an authoritative False
    even though the user holds the role. Entitlement is what unlocks the caps."""
    tenant_modules_rows = [
        {"module_name": MODULE_NAME, "is_active": False, "version": 1},
    ]
    role_rows = [
        {"email": MEMBER_ADMIN_EMAIL, "role": "Members_CRUD", "version": 1},
    ]

    active_by_tenant, roles_by_tenant = _project_and_read(
        tenant_modules_rows, role_rows
    )
    entitlement = resolve_entitlement(
        roles_by_tenant, active_by_tenant, MODULE_REGISTRY
    )

    # Tenant key present (user belongs there) but with an empty cap list.
    assert entitlement[PILOT_TENANT] == []
    claims = _claims_from_entitlement(entitlement)
    assert has_capability(claims, PILOT_TENANT, CAP_READ) is False


def test_has_capability_returns_none_for_tenant_not_in_token():
    """A tenant the token does not carry => None ("token can't answer; consult S3/
    server or deny") — never mistaken for a decision (verify-before-trust)."""
    entitlement = {PILOT_TENANT: [CAP_READ]}
    claims = _claims_from_entitlement(entitlement)

    assert has_capability(claims, "some-other-tenant", CAP_READ) is None


# --------------------------------------------------------------------------- #
# 4 — Vocabulary consistency: resolver caps == the handler's declared capabilities
# --------------------------------------------------------------------------- #


def test_members_role_permissions_use_the_handler_capability_vocabulary():
    """The caps the resolver can emit for Members roles are exactly the members:*
    tokens the handler routes gate on — one vocabulary, no drift between the auth
    resolver and the Members module's route declarations (C7)."""
    emitted = set()
    for role in ("Members_Read", "Members_CRUD", "Members_Export"):
        emitted.update(ROLE_PERMISSIONS[role])

    assert emitted == {CAP_READ, CAP_WRITE, CAP_EXPORT, CAP_ADMIN}
    # All are namespaced to the module (no bare tokens leaking cross-module).
    assert all(cap.startswith("members:") for cap in emitted)
