"""
S5 Task 1.0 — tests for the Members module scaffold: route map + router + thin handler.

These pin the scaffold's observable contract (the surface is wired, the bodies are stubs):

- the route map is the **union of h-dcn's ~18 handler behaviours**, grouped correctly, with
  unique ``(method, path)`` pairs and names (parity-audit source of truth, design C1);
- the internal router resolves ``(method, path)`` → the right route + extracts path params,
  answers 405 for a known path with the wrong method, and 404 for an unknown path;
- the thin handler entry point returns 404 / 405 accordingly and **501** for a resolved but
  not-yet-implemented route (route exists, behaviour pending) — never a 500;
- the repository interface is keyed by ``tenant_id`` on every method (structural isolation),
  and the stub raises rather than pretending persistence exists.

Validates: Requirements R1.1, R1.2
"""

from __future__ import annotations

import json

import pytest

from sam.members.handler import app
from sam.members.handler.router import (
    MethodNotAllowed,
    NoRouteMatch,
    RouteMatch,
    Router,
)
from sam.members.handler.routes import (
    ROUTES,
    RouteGroup,
    route_names,
    routes_by_group,
)
from sam.members.repository import MembersRepository
from sam.members.repository.members_repository import _StubMembersRepository

# ── Route map: the union of ~18 h-dcn behaviours ──────────────────────────────────────


def test_route_map_covers_eighteen_behaviours_total():
    # h-dcn's ~18 per-action handlers collapse into 18 internal routes, plus the resolved
    # field-config read (task 3.3, R2.3/R2.4) = 19, plus the two Lidmaatschap Beheer catalog
    # READ routes (task 3.4, R2.4 — list + get) = 21, plus the three catalog WRITE routes
    # (task 5.3, R2.4/R1.4 — create + update + soft-delete) = 24, plus the five member
    # analytics-set CRUD routes (F-012 — create + list + get + update + delete) = 29, plus
    # the two preferred-list routes (R11.2 — get + save) = 31, plus the two per-user
    # column-preferences routes (session-columns R6 — get + save) = 33, plus the five stored
    # mail-template CRUD routes (pivot-output-actions R2 task 2.3 — create + list + get +
    # update + delete) = 38, plus the two analytics-set DELIVERY routes
    # (pivot-output-actions R3 task 3.3 - set + clear) = 40, plus the analytics-set deliver
    # route (pivot-output-actions R4 task 4.2 — run a set's stored delivery now) = 41.
    # ...plus the five schedule CRUD routes (pivot-output-actions R5 task 5.2 — create + list
    # + get + update + delete) = 46, plus the stateless ad-hoc send route
    # (mail-spec task 2.1 — POST /members/mail/send) = 47, plus the two send-run STATUS read
    # routes (mail-spec task 3.2 — GET /members/mail-runs list + GET /members/mail-runs/{run_id})
    # = 49, plus the send-run manual-DELETE route (mail-spec task 3.3, R9.6 retention —
    # DELETE /members/mail-runs/{run_id}) = 50.
    assert len(ROUTES) == 50


def test_route_map_groups_match_the_design_c1_counts():
    # Member CRUD 8 + field-config 1 · membership lifecycle 7 · delegates 2 · payments 1 ·
    # catalog reads 2 (list + get, task 3.4) + catalog writes 3 (create + update + delete,
    # task 5.3) = 5 · analytics 14 (sets: create+list+get+update+delete, F-012; preferred
    # list: get+save, R11.2; column preferences: get+save, session-columns R6; stored mail
    # templates: create+list+get+update+delete, pivot-output-actions R2 task 2.3).
    assert len(routes_by_group(RouteGroup.MEMBER)) == 9
    assert len(routes_by_group(RouteGroup.MEMBERSHIP)) == 7
    assert len(routes_by_group(RouteGroup.DELEGATE)) == 2
    assert len(routes_by_group(RouteGroup.PAYMENT)) == 1
    assert len(routes_by_group(RouteGroup.CATALOG)) == 5
    # analytics 22: sets 5 (create+list+get+update+delete, F-012); preferred list 2
    # (get+save, R11.2); column preferences 2 (get+save, session-columns R6); stored mail
    # templates 5 (create+list+get+update+delete, pivot-output-actions R2 task 2.3); the two
    # analytics-set delivery routes (set+clear, pivot-output-actions R3 task 3.3); the
    # analytics-set deliver route (deliver, pivot-output-actions R4 task 4.2); the five
    # schedule CRUD routes (create+list+get+update+delete, pivot-output-actions R5 task 5.2);
    # the stateless ad-hoc send route (send_ad_hoc_mail, mail-spec task 2.1); the two send-run
    # STATUS read routes (list_mail_runs + get_mail_run, mail-spec task 3.2); the send-run
    # manual-DELETE route (delete_mail_run, mail-spec task 3.3, R9.6 retention).
    assert len(routes_by_group(RouteGroup.ANALYTICS)) == 26


def test_route_map_includes_each_named_behaviour():
    expected = {
        # member CRUD
        "create_member",
        "list_members",
        "list_members_filtered",
        "export_members",
        "get_self",
        "get_field_config",
        "get_member",
        "update_member",
        "delete_member",
        # membership lifecycle
        "create_membership",
        "list_memberships",
        "get_membership",
        "update_membership",
        "delete_membership",
        "transition_membership",
        "bulk_transition_memberships",
        # delegates
        "manage_delegates",
        "send_delegate_invitation",
        # payments
        "get_member_payments",
        # Lidmaatschap Beheer catalog reads (task 3.4)
        "list_membership_types",
        "get_membership_type",
        # Lidmaatschap Beheer catalog writes (task 5.3)
        "create_membership_type",
        "update_membership_type",
        "deactivate_membership_type",
        # Member analytics-sets CRUD (F-012)
        "create_analytics_set",
        "list_analytics_sets",
        "get_analytics_set",
        "update_analytics_set",
        "delete_analytics_set",
        # Per-user preferred list (R11.2)
        "get_preferred_list",
        "save_preferred_list",
        # Per-user overview column preferences (session-columns R6)
        "get_column_preferences",
        "save_column_preferences",
        # Stored mail templates CRUD (pivot-output-actions R2 task 2.3)
        "create_template",
        "list_templates",
        "get_template",
        "update_template",
        "delete_template",
        # Analytics-set delivery block set/clear (pivot-output-actions R3 task 3.3)
        "set_analytics_set_delivery",
        "clear_analytics_set_delivery",
        # Analytics-set deliver (R4 task 4.2)
        "deliver_analytics_set",
        # Schedule CRUD (pivot-output-actions R5 task 5.2)
        "create_schedule",
        "list_schedules",
        "get_schedule",
        "update_schedule",
        "delete_schedule",
        # Stateless ad-hoc send (mail-spec task 2.1 — POST /members/mail/send)
        "send_ad_hoc_mail",
        # Send-run STATUS reads (mail-spec task 3.2 — GET /members/mail-runs[/{run_id}])
        "list_mail_runs",
        "get_mail_run",
        # Send-run manual DELETE (mail-spec task 3.3, R9.6 — DELETE /members/mail-runs/{run_id})
        "delete_mail_run",
    }
    assert set(route_names()) == expected


def test_route_map_has_no_duplicate_endpoints_or_names():
    endpoints = [(s.method.value, s.path) for s in ROUTES]
    names = [s.name for s in ROUTES]
    assert len(endpoints) == len(set(endpoints))
    assert len(names) == len(set(names))


def test_every_route_is_gated_by_capability_or_self_service():
    # A route with no gate would be an unguarded surface — the map forbids it. A route is
    # gated by a single `capability`, an any-of `capabilities_any` set (R11.3), self-service,
    # or a combination.
    for spec in ROUTES:
        assert (
            spec.capability is not None
            or bool(spec.capabilities_any)
            or spec.self_service
        ), f"route {spec.name} has no gate"


# ── Router: dispatch + path params ────────────────────────────────────────────────────


@pytest.fixture()
def router() -> Router:
    return Router()


def test_resolve_collection_get_returns_list_members(router):
    match = router.resolve("GET", "/members")
    assert isinstance(match, RouteMatch)
    assert match.spec.name == "list_members"
    assert match.path_params == {}


def test_resolve_item_get_extracts_member_id_path_param(router):
    match = router.resolve("GET", "/members/M-42")
    assert isinstance(match, RouteMatch)
    assert match.spec.name == "get_member"
    assert match.path_params == {"member_id": "M-42"}


def test_resolve_nested_path_extracts_all_params(router):
    match = router.resolve("POST", "/members/M-1/memberships/MS-9/transition")
    assert isinstance(match, RouteMatch)
    assert match.spec.name == "transition_membership"
    assert match.path_params == {"member_id": "M-1", "membership_id": "MS-9"}


def test_resolve_static_before_param_prefers_literal_route(router):
    # /members/export and /members/me are literal and must win over /members/{member_id}.
    assert router.resolve("GET", "/members/export").spec.name == "export_members"
    assert router.resolve("GET", "/members/me").spec.name == "get_self"
    # /members/field-config is literal too and must win over /members/{member_id}.
    assert (
        router.resolve("GET", "/members/field-config").spec.name == "get_field_config"
    )


def test_resolve_is_case_insensitive_on_method(router):
    assert router.resolve("get", "/members").spec.name == "list_members"


def test_resolve_ignores_trailing_slash(router):
    assert router.resolve("GET", "/members/").spec.name == "list_members"


def test_resolve_wrong_method_returns_method_not_allowed(router):
    result = router.resolve("DELETE", "/members")
    assert isinstance(result, MethodNotAllowed)
    # /members supports GET (list) and POST (create).
    assert set(result.allowed_methods) == {"GET", "POST"}


def test_resolve_unknown_path_raises_no_route_match(router):
    with pytest.raises(NoRouteMatch):
        router.resolve("GET", "/does/not/exist")


def test_every_declared_route_resolves_to_itself(router):
    # Round-trip: each declared route, given a concrete path, resolves back to its name.
    for spec in ROUTES:
        concrete = spec.path
        for placeholder in (
            "member_id",
            "membership_id",
            "type_code",
            "template_id",
            "schedule_id",
        ):
            concrete = concrete.replace(f"{{{placeholder}}}", "X")
        match = router.resolve(spec.method.value, concrete)
        assert isinstance(match, RouteMatch)
        assert match.spec.name == spec.name


# ── Thin handler entry point (scaffold contract: routed, stubbed → 501) ───────────────


def _entitlement_claim(tenant: str, capabilities: list[str]) -> str:
    """Build a verified ``custom:entitlements`` claim value granting caps for one tenant."""
    return json.dumps({"v": 1, "t": {tenant: capabilities}})


def _authorized_event(
    method: str,
    path: str,
    *,
    tenant: str = "h-dcn",
    capabilities: tuple[str, ...] = (
        "members:read",
        "members:write",
        "members:export",
        "members:admin",
    ),
    body=None,
) -> dict:
    """An API-GW-authorizer event whose VERIFIED claims entitle the caller (task 3.0 gate).

    The auth edge now enforces verified claims + entitlement, so the routing/501 contract
    is only reachable by an authenticated + authorized caller. We supply the verified
    authorizer context (no re-verification needed) carrying groups + the entitlement claim.
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
                    "sub": "user-1",
                    "cognito:groups": ["Members_CRUD"],
                    "custom:entitlements": _entitlement_claim(
                        tenant, list(capabilities)
                    ),
                }
            }
        },
    }


def test_handler_write_route_now_dispatches_to_the_domain(monkeypatch):
    # Task 5.2 implements the WRITE routes: a resolved write route is no longer the honest-501
    # stub — it dispatches to the domain service (here a spy) and shapes its result. This pins
    # the scaffold's routing→dispatch contract for a write without a live table.
    captured = {}

    class _Spy:
        def update_member(self, tenant_id, member_id, body, allowed_scopes, **kw):
            captured.update(tenant_id=tenant_id, member_id=member_id, body=dict(body))
            return {"member_id": member_id, "ok": True}

    monkeypatch.setattr(app, "_get_membership_service", lambda: _Spy())
    resp = app.handler(_authorized_event("PUT", "/members/M-1", body={"personal": {}}))
    assert resp["statusCode"] == 200
    assert captured["tenant_id"] == "h-dcn"
    assert captured["member_id"] == "M-1"


def test_handler_unknown_path_returns_404():
    # Routing precedes auth, so an unknown path is 404 regardless of credentials.
    resp = app.handler(_authorized_event("GET", "/nope"))
    assert resp["statusCode"] == 404


def test_handler_wrong_method_returns_405_with_allow_header():
    # Routing precedes auth, so a wrong method is 405 regardless of credentials.
    resp = app.handler(_authorized_event("DELETE", "/members"))
    assert resp["statusCode"] == 405
    assert "Allow" in resp["headers"]
    assert set(resp["headers"]["Allow"].split(", ")) == {"GET", "POST"}


def test_handler_supports_http_api_v2_event_shape(monkeypatch):
    # The HTTP-API-v2 shape (requestContext.http + rawPath + jwt authorizer) must parse and
    # route the same as the v1 shape. get_self is a pure self-service read (task 3.2); with a
    # matching own record it now returns 200 (routing + parsing + dispatch all wired).
    class _FakeService:
        def get_self(self, tenant_id, requester_sub):
            assert tenant_id == "h-dcn"
            return {"member_id": "self-1", "sub": requester_sub}

    monkeypatch.setattr(app, "_get_membership_service", lambda: _FakeService())

    event = {
        "requestContext": {
            "http": {"method": "GET", "path": "/members/me"},
            "authorizer": {
                "jwt": {
                    "claims": {
                        "sub": "v2-user",
                        "cognito:groups": ["Members_Read"],
                        # Even a self-service route still establishes tenant context from
                        # the verified entitlement (verify-before-trust).
                        "custom:entitlements": _entitlement_claim(
                            "h-dcn", ["members:read"]
                        ),
                    }
                }
            },
        },
        "rawPath": "/members/me",
        "headers": {},
    }
    resp = app.handler(event)
    assert resp["statusCode"] == 200
    assert json.loads(resp["body"])["data"]["member_id"] == "self-1"


# ── Repository interface: structural tenant isolation + honest stub ───────────────────


def test_stub_repository_satisfies_the_protocol():
    assert isinstance(_StubMembersRepository(), MembersRepository)


def test_every_repository_method_is_keyed_by_tenant_id():
    import inspect

    # Every public repository method must take tenant_id as its first real argument —
    # this is the structural guarantee behind Property 1 (no cross-tenant access).
    for name, member in inspect.getmembers(_StubMembersRepository, inspect.isfunction):
        if name.startswith("_"):
            continue
        params = list(inspect.signature(member).parameters)
        assert params[:2] == ["self", "tenant_id"], (
            f"{name} is not keyed by tenant_id first"
        )


def test_stub_repository_methods_raise_not_implemented():
    repo = _StubMembersRepository()
    with pytest.raises(NotImplementedError):
        repo.get_member("h-dcn", "M-1")
    with pytest.raises(NotImplementedError):
        repo.list_members("h-dcn")
