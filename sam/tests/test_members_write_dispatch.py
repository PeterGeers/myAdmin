"""
S5 Task 5.2 — tests for the Members handler **WRITE-route dispatch** + the domain write path.

These pin the write path end-to-end through the thin edge (design C1 write → C2/C5/C6):

- **create_member** validates (fixed fields + h-dcn ``validate_member`` hook), stamps the
  authoritative ``tenant_id`` (never the body — verify-before-trust, Property 2), sets the
  initial lifecycle state from the tenant's config, and persists via a single ``PutItem``;
  ``member_number`` is a plain optional string, so a duplicate is allowed (s5k removed the
  uniqueness guard) and an absent one simply persists empty;
- **update_member** partial-updates a scoped member and denies an out-of-scope write with a
  **403** (Property 4);
- **transition** applies the lifecycle engine — an allowed move is **200** (and the state is
  persisted), a denied move is **409** (guards/graph), and the ``on_transition`` hook only
  fires on success;
- **delete_member** removes the member record via a single ``DeleteItem``;
- **delegates** are self-service (a member manages their OWN set) and tenant-scoped.

The domain service is exercised over the SAME in-memory ``FakeDynamoTable`` +
``DynamoDbMembersRepository`` the repository tests use — which genuinely enforces the
transactional conditional-write uniqueness — so the conflict/concurrency path (Property 6) is
tested for real, not mocked. Auth is supplied as verified API-GW-authorizer claims (task-3.0
gate); the service is wired with h-dcn's lifecycle config + hook registry (task 5.0 / 5.1).

Validates: Requirements R1.4, R3.3 (design C1 write, C2, C5, C6; Property 2, 4, 6)
"""

from __future__ import annotations

import json
import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
_BACKEND_SRC = os.path.join(_REPO_ROOT, "backend", "src")
if _BACKEND_SRC not in sys.path:
    sys.path.insert(0, _BACKEND_SRC)

from sam.members.handler import app
from sam.members.domain.lifecycle_config import (
    HDCN_LIFECYCLE_CONFIG,
    StaticLifecycleConfigProvider,
)
from sam.members.domain.membership_service import MembershipService
from sam.members.domain.membership_type_catalog import MembershipTypeEntry
from sam.members.domain.tenant_hooks import HookName, TenantHookRegistry
from sam.members.tenants.hdcn.hooks import register_hdcn_hooks
from sam.members.repository.members_repository import DynamoDbMembersRepository

# The faithful in-memory DynamoDB fake (transactional conditional writes + atomic counter).
from sam.tests.test_members_repository import FakeDynamoTable


# ── Service wired like production: real repo over the fake table + h-dcn config/hooks ──


@pytest.fixture()
def table() -> FakeDynamoTable:
    return FakeDynamoTable()


@pytest.fixture()
def repo(table) -> DynamoDbMembersRepository:
    return DynamoDbMembersRepository(table=table, client=table.meta.client)


@pytest.fixture()
def hooks() -> TenantHookRegistry:
    return register_hdcn_hooks(TenantHookRegistry())


def _seed_hdcn_catalog(repo) -> None:
    """Seed the h-dcn Lidmaatschap Beheer catalog with the types these write tests reference.

    Task 5.3 made the ``membership_type`` reference check authoritative on create/update: a
    member's type must point at a LIVE catalog entry. These write tests build members with
    ``membership_type="erelid"``, so the catalog must carry an active ``erelid`` entry for the
    create to succeed (the same coupling h-dcn seeds as data in task 4.2). Seed a small live
    set + one retired type so the reference-integrity tests below have both to exercise.
    """
    for code, active in (("erelid", True), ("donateur", True), ("retired_type", False)):
        repo.save_membership_type(
            "h-dcn",
            MembershipTypeEntry(
                tenant_id="h-dcn",
                type_code=code,
                label={"nl": code, "en": code},
                active=active,
            ),
        )


# ── Projected scope grants (S5b task 8.3, design C5) ──────────────────────────────────
#
# The caller's scope now comes from the PROJECTED ``scopegrant#`` rows (design C5), keyed by
# the caller's verified EMAIL — NOT the token groups. Map the write-path scope intents to
# projected grants: all-access → region ["*"], Noord → ["Noord"], and a Members_CRUD holder
# with NO region grant is ABSENT (deny-by-default).

_EMAIL_ALL = "all@h-dcn.test"          # all-access → region ["*"]
_EMAIL_NOORD = "noord@h-dcn.test"      # scoped to Noord
_EMAIL_NOGRANT = "nogrant@h-dcn.test"  # holds Members_CRUD but NO region grant → deny

_HDCN_GRANTS = {
    ("h-dcn", _EMAIL_ALL): {"region": ["*"]},
    ("h-dcn", _EMAIL_NOORD): {"region": ["Noord"]},
    # _EMAIL_NOGRANT deliberately absent → deny-by-default (R2.6).
}


@pytest.fixture(autouse=True)
def inject_service(monkeypatch, repo, hooks):
    """Wire a MembershipService exactly as _get_membership_service does (lifecycle + hooks)."""
    from sam.tests.conftest import FakeScopeGrantsReader

    _seed_hdcn_catalog(repo)
    service = MembershipService(
        repo,
        lifecycle_provider=StaticLifecycleConfigProvider({"h-dcn": HDCN_LIFECYCLE_CONFIG}),
        tenant_hooks=hooks,
    )
    monkeypatch.setattr(app, "_get_membership_service", lambda: service)
    monkeypatch.setattr(
        app, "_SCOPE_GRANTS_READER_OVERRIDE", FakeScopeGrantsReader(_HDCN_GRANTS)
    )
    return service


# ── Auth helpers (verified API-GW-authorizer claims) ──────────────────────────────────


def _entitlement(tenant, capabilities):
    return json.dumps({"v": 1, "t": {tenant: capabilities}})


def _event(method, path, *, tenant="h-dcn",
           capabilities=("members:read", "members:write", "members:admin", "members:export"),
           email=_EMAIL_ALL, groups=(), sub="admin-sub", body=None):
    """A verified API-GW-authorizer event. Scope is driven by ``email`` (projected grants,
    design C5), not ``groups``.
    """
    return {
        "httpMethod": method,
        "path": path,
        "headers": {},
        "queryStringParameters": None,
        "body": json.dumps(body) if body is not None else None,
        "requestContext": {
            "authorizer": {
                "claims": {
                    "sub": sub,
                    "email": email,
                    "cognito:groups": list(groups),
                    "custom:entitlements": _entitlement(tenant, list(capabilities)),
                }
            }
        },
    }


def _data(resp):
    return json.loads(resp["body"]).get("data")


def _valid_member_body(*, region="Noord", member_number=None, status=None, membership_type="erelid"):
    membership = {"membership_type": membership_type, "joined_date": "2024-01-01"}
    if member_number is not None:
        membership["member_number"] = member_number
    if status is not None:
        membership["status"] = status
    # S5d D1/R3.4: scope is a PLAIN member field — h-dcn's `region` dimension binds to the
    # tenant-added `overlay.region` field, a scalar (no retired `scope_values` bucket).
    return {
        "personal": {"first_name": "Alex", "last_name": "de Vries", "email": "alex@example.com"},
        "membership": membership,
        "overlay": {"region": region},
    }


# ── create_member ─────────────────────────────────────────────────────────────────────


def test_create_member_valid_returns_200_and_persists(repo):
    body = _valid_member_body(member_number="1001")
    body["member_id"] = "M-1"
    resp = app.handler(_event("POST", "/members", groups=("Regio_All",), body=body))
    assert resp["statusCode"] == 200
    # Persisted under the authoritative tenant.
    stored = repo.get_member("h-dcn", "M-1")
    assert stored is not None
    assert stored["membership"]["member_number"] == "1001"


def test_create_member_ignores_body_tenant_id(repo):
    # Verify-before-trust (Property 2): a body tenant_id can NEVER redirect the write.
    body = _valid_member_body(member_number="1002")
    body["member_id"] = "M-9"
    body["tenant_id"] = "evil-tenant"
    resp = app.handler(_event("POST", "/members", groups=("Regio_All",), body=body))
    assert resp["statusCode"] == 200
    assert repo.get_member("h-dcn", "M-9") is not None
    assert repo.get_member("evil-tenant", "M-9") is None


def test_create_member_with_no_member_number_saves_empty(repo):
    # s5k: NO auto-generation. A body without member_number saves with an EMPTY number (a valid
    # member — sponsors/clubs/numberless). Status still defaults to the config's initial state.
    body = _valid_member_body()
    body["member_id"] = "M-2"
    body["membership"].pop("member_number", None)
    resp = app.handler(_event("POST", "/members", groups=("Regio_All",), body=body))
    assert resp["statusCode"] == 200
    stored = repo.get_member("h-dcn", "M-2")
    assert not stored["membership"].get("member_number")  # empty / absent — no L-000001
    # Initial lifecycle state from HDCN_LIFECYCLE_CONFIG (application).
    assert stored["membership"]["status"] == "application"


def test_create_member_duplicate_number_is_allowed(repo):
    # s5k: the member-number uniqueness guard was removed — a duplicate number is a
    # data-quality concern, NOT a write-time conflict. Both creates succeed (200).
    body1 = _valid_member_body(member_number="2001")
    body1["member_id"] = "M-3"
    assert app.handler(_event("POST", "/members", body=body1))["statusCode"] == 200
    body2 = _valid_member_body(member_number="2001")
    body2["member_id"] = "M-4"
    resp = app.handler(_event("POST", "/members", body=body2))
    assert resp["statusCode"] == 200


def test_create_member_missing_required_fields_returns_422():
    # No personal.first_name / email → fixed-field validation fails → 422 with per-field errors.
    resp = app.handler(_event("POST", "/members", body={"member_id": "M-x", "membership": {"member_number": "9"}}))
    assert resp["statusCode"] == 422
    errors = json.loads(resp["body"])["errors"]
    assert "personal.first_name" in errors


def test_create_active_member_without_motor_fails_hdcn_hook_422():
    # h-dcn validate_member hook: an ACTIVE member must record a motorcycle (Rung-3, 5.1).
    body = _valid_member_body(member_number="3001", status="active")
    body["member_id"] = "M-5"
    resp = app.handler(_event("POST", "/members", body=body))
    assert resp["statusCode"] == 422
    assert "overlay.motor" in json.loads(resp["body"])["errors"]


def test_create_active_member_with_motor_passes(repo):
    body = _valid_member_body(member_number="3002", status="active")
    body["member_id"] = "M-6"
    body["overlay"] = {"motor": "Honda CB500"}
    resp = app.handler(_event("POST", "/members", body=body))
    assert resp["statusCode"] == 200
    assert repo.get_member("h-dcn", "M-6") is not None


# ── update_member (partial + scope) ─────────────────────────────────────────────────


def test_update_member_partial_updates_only_supplied_fields(repo):
    body = _valid_member_body(member_number="4001")
    body["member_id"] = "M-7"
    app.handler(_event("POST", "/members", body=body))
    # Partial update of just the first name.
    resp = app.handler(
        _event("PUT", "/members/M-7", groups=("Regio_All",), body={"personal": {"first_name": "Alexandra"}})
    )
    assert resp["statusCode"] == 200
    stored = repo.get_member("h-dcn", "M-7")
    assert stored["personal"]["first_name"] == "Alexandra"
    # Untouched fields survive the merge.
    assert stored["personal"]["email"] == "alex@example.com"
    assert stored["membership"]["member_number"] == "4001"


def test_update_member_out_of_scope_returns_403(repo):
    # Seed a Zuid member, then a Noord-scoped caller tries to update it → 403 (Property 4).
    body = _valid_member_body(region="Zuid", member_number="4002")
    body["member_id"] = "M-8"
    app.handler(_event("POST", "/members", body=body))  # admin creates
    resp = app.handler(
        _event("PUT", "/members/M-8", email=_EMAIL_NOORD, body={"personal": {"first_name": "Nope"}})
    )
    assert resp["statusCode"] == 403


def test_update_missing_member_returns_404():
    resp = app.handler(_event("PUT", "/members/ghost", body={"personal": {"first_name": "x"}}))
    assert resp["statusCode"] == 404


# ── transition (lifecycle engine + hook) ────────────────────────────────────────────


def test_transition_allowed_returns_200_and_persists(repo):
    # Seed a pending member with the fields the pending→active guard requires, then activate.
    body = _valid_member_body(member_number="5001", status="pending")
    body["member_id"] = "M-10"
    app.handler(_event("POST", "/members", body=body))
    resp = app.handler(
        _event("POST", "/members/M-10/memberships/MS-1/transition", body={"to_state": "active"})
    )
    assert resp["statusCode"] == 200
    assert repo.get_member("h-dcn", "M-10")["membership"]["status"] == "active"


def test_transition_denied_by_guard_returns_409(repo):
    # application→pending requires context.approved == True; omit it → denied (409), and the
    # state is NOT mutated.
    body = _valid_member_body(member_number="5002", status="application")
    body["member_id"] = "M-11"
    app.handler(_event("POST", "/members", body=body))
    resp = app.handler(
        _event("POST", "/members/M-11/memberships/MS-1/transition", body={"to_state": "pending"})
    )
    assert resp["statusCode"] == 409
    assert repo.get_member("h-dcn", "M-11")["membership"]["status"] == "application"


def test_transition_approved_application_moves_to_pending(repo):
    body = _valid_member_body(member_number="5003", status="application")
    body["member_id"] = "M-12"
    app.handler(_event("POST", "/members", body=body))
    resp = app.handler(
        _event(
            "POST",
            "/members/M-12/memberships/MS-1/transition",
            body={"to_state": "pending", "context": {"approved": True}},
        )
    )
    assert resp["statusCode"] == 200
    assert repo.get_member("h-dcn", "M-12")["membership"]["status"] == "pending"


def test_transition_undeclared_edge_returns_409(repo):
    body = _valid_member_body(member_number="5004", status="application")
    body["member_id"] = "M-13"
    app.handler(_event("POST", "/members", body=body))
    # application→active is not in the graph → denied.
    resp = app.handler(
        _event("POST", "/members/M-13/memberships/MS-1/transition", body={"to_state": "active"})
    )
    assert resp["statusCode"] == 409


def test_transition_missing_to_state_returns_422(repo):
    body = _valid_member_body(member_number="5005", status="pending")
    body["member_id"] = "M-14"
    app.handler(_event("POST", "/members", body=body))
    resp = app.handler(
        _event("POST", "/members/M-14/memberships/MS-1/transition", body={})
    )
    assert resp["statusCode"] == 422


def test_transition_fires_on_transition_hook_only_on_success(monkeypatch, repo):
    # Register an on_transition spy for h-dcn; it must fire on an allowed move and NOT on a
    # denied one.
    fired = []
    hooks = register_hdcn_hooks(TenantHookRegistry())
    hooks.register(
        HookName.ON_TRANSITION,
        "h-dcn",
        lambda tid, member, frm, to: fired.append((frm.value, to.value)),
    )
    service = MembershipService(
        repo,
        lifecycle_provider=StaticLifecycleConfigProvider({"h-dcn": HDCN_LIFECYCLE_CONFIG}),
        tenant_hooks=hooks,
    )
    monkeypatch.setattr(app, "_get_membership_service", lambda: service)

    body = _valid_member_body(member_number="5006", status="application")
    body["member_id"] = "M-15"
    app.handler(_event("POST", "/members", body=body))

    # Denied move: application→active is not in the graph → hook must NOT fire.
    denied = app.handler(
        _event("POST", "/members/M-15/memberships/MS-1/transition", body={"to_state": "active"})
    )
    assert denied["statusCode"] == 409
    assert fired == []

    # Allowed move: application→pending (approved) → hook fires.
    allowed = app.handler(
        _event(
            "POST",
            "/members/M-15/memberships/MS-1/transition",
            body={"to_state": "pending", "context": {"approved": True}},
        )
    )
    assert allowed["statusCode"] == 200
    assert ("application", "pending") in fired


# ── bulk transition ───────────────────────────────────────────────────────────────────


def test_bulk_transition_reports_per_item_outcomes(repo):
    for i, mid in enumerate(("M-20", "M-21"), start=1):
        body = _valid_member_body(member_number=f"60{i}", status="pending")
        body["member_id"] = mid
        app.handler(_event("POST", "/members", body=body))
    resp = app.handler(
        _event("POST", "/memberships/transition",
               body={"to_state": "active", "member_ids": ["M-20", "M-21", "ghost"]})
    )
    assert resp["statusCode"] == 200
    data = _data(resp)
    assert data["succeeded"] == 2
    assert data["failed"] == 1


# ── delete_member (frees the number) ──────────────────────────────────────────────────


def test_delete_member_frees_the_number(repo):
    body = _valid_member_body(member_number="7001")
    body["member_id"] = "M-30"
    app.handler(_event("POST", "/members", body=body))
    resp = app.handler(_event("DELETE", "/members/M-30", groups=("Regio_All",)))
    assert resp["statusCode"] == 200
    assert repo.get_member("h-dcn", "M-30") is None
    # The freed number can be reclaimed by a new member (no orphaned guard).
    body2 = _valid_member_body(member_number="7001")
    body2["member_id"] = "M-31"
    assert app.handler(_event("POST", "/members", body=body2))["statusCode"] == 200


# ── memberships ───────────────────────────────────────────────────────────────────────


def test_create_and_update_membership(repo):
    body = _valid_member_body(member_number="8001")
    body["member_id"] = "M-40"
    app.handler(_event("POST", "/members", body=body))
    resp = app.handler(
        _event("POST", "/members/M-40/memberships",
               body={"membership_id": "MS-1", "status": "active"})
    )
    assert resp["statusCode"] == 200
    assert repo.get_membership("h-dcn", "M-40", "MS-1")["status"] == "active"
    # Partial update.
    resp = app.handler(
        _event("PUT", "/members/M-40/memberships/MS-1", body={"status": "suspended"})
    )
    assert resp["statusCode"] == 200
    assert repo.get_membership("h-dcn", "M-40", "MS-1")["status"] == "suspended"


def test_delete_membership_removes_it(repo):
    body = _valid_member_body(member_number="8002")
    body["member_id"] = "M-41"
    app.handler(_event("POST", "/members", body=body))
    app.handler(_event("POST", "/members/M-41/memberships", body={"membership_id": "MS-9"}))
    resp = app.handler(_event("DELETE", "/members/M-41/memberships/MS-9", groups=("Regio_All",)))
    assert resp["statusCode"] == 200
    assert repo.get_membership("h-dcn", "M-41", "MS-9") is None


# ── delegates (self-service) ────────────────────────────────────────────────────────


def test_manage_delegates_replaces_the_set(repo):
    body = _valid_member_body(member_number="9001")
    body["member_id"] = "M-50"
    app.handler(_event("POST", "/members", body=body))
    resp = app.handler(
        _event("PUT", "/members/M-50/delegates", body={"delegates": [{"email": "d@x.com"}]})
    )
    assert resp["statusCode"] == 200
    assert repo.list_member_delegates("h-dcn", "M-50") == [{"email": "d@x.com"}]


def test_manage_delegates_self_service_own_record_without_scope(repo):
    # A member with no region grant (Members_CRUD → deny scope) manages their OWN delegates.
    body = _valid_member_body(region="Zuid", member_number="9002")
    body["member_id"] = "M-51"
    body["sub"] = "member-51-sub"
    app.handler(_event("POST", "/members", body=body))  # admin creates
    resp = app.handler(
        _event(
            "PUT",
            "/members/M-51/delegates",
            email=_EMAIL_NOGRANT,
            groups=("Members_CRUD",),
            sub="member-51-sub",
            body={"delegates": [{"email": "self@x.com"}]},
        )
    )
    assert resp["statusCode"] == 200


def test_send_delegate_invitation_records_intent(repo):
    body = _valid_member_body(member_number="9003")
    body["member_id"] = "M-52"
    app.handler(_event("POST", "/members", body=body))
    resp = app.handler(
        _event("POST", "/members/M-52/delegates/invitations", body={"delegate_email": "invite@x.com"})
    )
    assert resp["statusCode"] == 200
    stored = repo.list_member_delegates("h-dcn", "M-52")
    assert any(d.get("email") == "invite@x.com" and d.get("status") == "invited" for d in stored)


def test_send_delegate_invitation_missing_email_returns_422(repo):
    body = _valid_member_body(member_number="9004")
    body["member_id"] = "M-53"
    app.handler(_event("POST", "/members", body=body))
    resp = app.handler(_event("POST", "/members/M-53/delegates/invitations", body={}))
    assert resp["statusCode"] == 422


# ── member number is a plain string: NO uniqueness guard (s5k) ────────────────────────


def test_duplicate_member_number_across_members_is_allowed(table):
    # s5k: the member-number uniqueness guard was removed. Two members with the SAME number
    # both persist — a duplicate is a data-quality concern, not a write-time conflict.
    lifecycle = StaticLifecycleConfigProvider({"h-dcn": HDCN_LIFECYCLE_CONFIG})
    hooks = register_hdcn_hooks(TenantHookRegistry())
    repo_a = DynamoDbMembersRepository(table=table, client=table.meta.client)
    repo_b = DynamoDbMembersRepository(table=table, client=table.meta.client)
    svc_a = MembershipService(repo_a, lifecycle_provider=lifecycle, tenant_hooks=hooks)
    svc_b = MembershipService(repo_b, lifecycle_provider=lifecycle, tenant_hooks=hooks)

    b1 = _valid_member_body(member_number="12345")
    b1["member_id"] = "M-A"
    svc_a.create_member("h-dcn", b1, {"region": ["*"]})

    b2 = _valid_member_body(member_number="12345")
    b2["member_id"] = "M-B"
    svc_b.create_member("h-dcn", b2, {"region": ["*"]})  # no raise

    # Both records stand — same number, distinct members.
    assert repo_a.get_member("h-dcn", "M-A") is not None
    assert repo_a.get_member("h-dcn", "M-B") is not None

# ── Task 4.8 (6b + 7b): authoritative WRITE gates surfaced through the EDGE ────────────
#
# The service-level gates for value-level role-restricted enums (R4.12) and show_when
# "hidden-not-required" (R4.12) are pinned directly in
# ``test_members_resolved_field_surface.py``. THESE tests close the matrix by proving the
# SAME two gates surface with the correct HTTP status through the FULL handler dispatch
# (design C1 write → C2/C5): a disallowed role-restricted enum value → **422** (the domain
# rejects it; the edge maps MemberValidationError → 422), and a field hidden by an unmet
# ``show_when`` is NOT demanded → **200** (the server never 422s for the missing hidden
# field). The frontend legs (options filtered by role; hidden field not rendered/required)
# live in ``frontend/src/components/members/fieldForm.test.ts``.

from sam.members.domain.field_resolver import StaticOverlayProvider  # noqa: E402
from sam.tests.test_members_resolved_field_surface import (  # noqa: E402
    _overlay_with_groups_and_options,
)


def _overlay_service_over(table) -> MembershipService:
    """A MembershipService wired exactly like production (real repo over the fake table +
    h-dcn lifecycle/hooks) BUT with the task-4.4 overlay that carries a role-gated ``tier``
    enum and a ``show_when``-gated ``motor_brand`` field. The catalog is seeded with the
    ``gewoon`` (hides motor_brand) + ``motor`` (shows motor_brand) types the overlay's
    show_when keys off.
    """
    repo = DynamoDbMembersRepository(table=table, client=table.meta.client)
    for code in ("gewoon", "motor"):
        repo.save_membership_type(
            "h-dcn",
            MembershipTypeEntry(
                tenant_id="h-dcn", type_code=code, label={"nl": code, "en": code}, active=True
            ),
        )
    return MembershipService(
        repo,
        overlay_provider=StaticOverlayProvider({"h-dcn": _overlay_with_groups_and_options()}),
        lifecycle_provider=StaticLifecycleConfigProvider({"h-dcn": HDCN_LIFECYCLE_CONFIG}),
        tenant_hooks=register_hdcn_hooks(TenantHookRegistry()),
    )


@pytest.fixture()
def overlay_service(monkeypatch, table):
    """Swap the autouse ``inject_service`` wiring for the overlay-carrying service (edge tests)."""
    service = _overlay_service_over(table)
    monkeypatch.setattr(app, "_get_membership_service", lambda: service)
    from sam.tests.conftest import FakeScopeGrantsReader

    monkeypatch.setattr(
        app, "_SCOPE_GRANTS_READER_OVERRIDE", FakeScopeGrantsReader(_HDCN_GRANTS)
    )
    return service


def _overlay_member_body(*, membership_type="gewoon", tier=None, motor_brand=None, member_id="MO-1"):
    body = {
        "member_id": member_id,
        "personal": {"first_name": "Sam", "last_name": "Jansen", "email": "sam@example.com"},
        "membership": {
            # The overlay's fixed_override sets a tenant member-number format (Nr-0001).
            "member_number": "Nr-0001",
            "membership_type": membership_type,
            "joined_date": "2024-01-01",
        },
    }
    # S5d D1/R3.4: the scope field (region) is a PLAIN `overlay.region` field now (a scalar) —
    # no retired `scope_values` bucket. It rides in the same `overlay` bucket as club details.
    overlay = {"region": "Noord"}
    if tier is not None:
        overlay["tier"] = tier
    if motor_brand is not None:
        overlay["motor_brand"] = motor_brand
    body["overlay"] = overlay
    return body


def test_create_role_restricted_enum_value_denied_role_returns_422(overlay_service):
    # (6b) A caller WITHOUT Members_CRUD sets the role-restricted "premium" tier → the DOMAIN
    # rejects it and the edge surfaces 422 with the per-field error (never a silent accept).
    body = _overlay_member_body(tier="premium", member_id="MO-1")
    resp = app.handler(
        _event("POST", "/members", groups=("Members_Read",), body=body)
    )
    assert resp["statusCode"] == 422
    assert "overlay.tier" in json.loads(resp["body"])["errors"]


def test_create_role_restricted_enum_value_allowed_role_returns_200(overlay_service):
    # A caller holding Members_CRUD MAY set "premium" → 200.
    body = _overlay_member_body(tier="premium", member_id="MO-2")
    resp = app.handler(
        _event("POST", "/members", groups=("Members_CRUD", "Regio_All"), body=body)
    )
    assert resp["statusCode"] == 200


def test_create_open_enum_value_allowed_for_any_role_returns_200(overlay_service):
    # The unrestricted "standard" option is allowed for any caller → 200.
    body = _overlay_member_body(tier="standard", member_id="MO-3")
    resp = app.handler(
        _event("POST", "/members", groups=("Members_Read", "Regio_All"), body=body)
    )
    assert resp["statusCode"] == 200


def test_create_omitting_hidden_show_when_field_succeeds_200(overlay_service):
    # (7b) motor_brand is REQUIRED but only shown for a "motor" membership. A "gewoon" member
    # hides it → omitting motor_brand must SUCCEED (200); the server must NOT 422 for the
    # missing hidden field (the mirror of the frontend not rendering/requiring it).
    body = _overlay_member_body(membership_type="gewoon", member_id="MO-4")
    resp = app.handler(
        _event("POST", "/members", groups=("Members_CRUD", "Regio_All"), body=body)
    )
    assert resp["statusCode"] == 200


def test_create_omitting_visible_show_when_field_returns_422(overlay_service):
    # The mirror: a "motor" member SHOWS motor_brand → it is required; omitting it → 422.
    body = _overlay_member_body(membership_type="motor", member_id="MO-5")
    resp = app.handler(
        _event("POST", "/members", groups=("Members_CRUD", "Regio_All"), body=body)
    )
    assert resp["statusCode"] == 422
    assert "overlay.motor_brand" in json.loads(resp["body"])["errors"]
