"""
Spec 02, Task 1.7 — edge/route tests for ``PUT /members/config/{configId}``.

These pin the observable security + routing contract of the SAM-owned config WRITE path
end-to-end through the thin Members Lambda edge (``sam/members/handler/app.py`` +
``_dispatch.py`` + ``routes.py``, Task 1.6), WITHOUT touching live AWS. The write repository
is never reached on the rejection paths; on the success path the config-write domain service
is injected over an in-memory fake repository (no boto3, no DynamoDB) via the same
``_dispatch.get_config_write_service`` seam the dispatch resolves through.

What each requirement maps to here (design §API contract, Components 1/2):

- **Verified-JWT + Tenant_Admin entitlement (R3.1, R3.3):** no token → 401; a verified caller
  who lacks ``members:admin`` for the active tenant → 403, and the write path is NEVER entered
  (the injected service records no call).
- **tenant_id resolved from the token, not the body (R3.2):** a body carrying a rogue
  ``tenant_id`` can never redirect the write — the service is handed the VERIFIED tenant.
- **Closed config-id write surface (R2.2, R2.5):** ``configId ∈ {fields, scope, mail}`` is
  accepted; ``views`` and any unknown id are rejected with a 400 (the implementation's choice
  within the design's "400 or 404" latitude) and NO write happens (Config_Views_Residue never
  authored).
- **Success envelope (R1.1, R1.3):** a valid write returns a 200 whose body carries
  ``{success, configId, version}`` — the authoritative row-level Version_Stamp.
- **Unexpected-exception path (R17.1, R17.2 / steering 35):** an unanticipated error inside the
  write path becomes a BODIED, generic 500 — never ``str(e)``, never an empty 502.

Validates: Requirements 1.1, 1.3, 2.2, 2.5, 3.1, 3.2, 3.3, 17.1, 17.2
"""

from __future__ import annotations

import json
import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
_BACKEND_SRC = os.path.join(_REPO_ROOT, "backend", "src")
if _BACKEND_SRC not in sys.path:
    sys.path.insert(0, _BACKEND_SRC)

from sam.members.domain.config_write_service import (
    ConfigWriteService,
    ConfigWriteValidationError,
)
from sam.members.handler import _dispatch as dispatch_mod
from sam.members.handler import app

_TENANT = "h-dcn"
_VERSION = "2026-10-12T09:00:00+00:00"


# ── Fake write repository + injected real domain service (no boto3, no DynamoDB) ──────


class FakeWriteRepository:
    """In-memory stand-in for ``MembersConfigWriteRepository`` — records the put, no I/O.

    The put path through the real :class:`ConfigWriteService` is exercised end to end (shape +
    version stamp), but persistence is recorded in a list instead of DynamoDB. ``calls`` lets a
    test assert that an AUTHORITATIVE tenant was written (R3.2) and — crucially for the rejection
    paths — that NO write happened at all (R2.5, R3.3).
    """

    def __init__(self):
        self.calls = []

    def put_config(self, tenant_id, config_id, attributes, version):
        self.calls.append(
            {
                "tenant_id": tenant_id,
                "config_id": config_id,
                "attributes": attributes,
                "version": version,
            }
        )
        return {
            "tenant_id": tenant_id,
            "config_id": config_id,
            "version": version,
            **attributes,
        }


@pytest.fixture()
def repo() -> FakeWriteRepository:
    return FakeWriteRepository()


@pytest.fixture(autouse=True)
def inject_config_write_service(monkeypatch, repo):
    """Wire the EDGE's config-write seam to a real service over the fake repo (deterministic stamp).

    The dispatch (``_dispatch.dispatch_route``) resolves the service via the module-local
    ``get_config_write_service`` in ``_dispatch`` (production builds it over the concrete write
    repository). Patch THAT name so the write path reaches the fake — here the service wraps the
    in-memory fake and a pinned version minter so the 200 body's ``version`` is assertable and no
    AWS is touched. Every test shares this seam; the rejection-path tests then assert
    ``repo.calls == []``.
    """
    service = ConfigWriteService(repo, version_fn=lambda: _VERSION)
    monkeypatch.setattr(dispatch_mod, "get_config_write_service", lambda: service)
    return service


# ── Auth helpers (verified API-GW-authorizer claims) ──────────────────────────────────


def _entitlement(tenant, capabilities):
    return json.dumps({"v": 1, "t": {tenant: list(capabilities)}})


def _event(
    config_id,
    *,
    tenant=_TENANT,
    capabilities=("members:admin",),
    email="admin@h-dcn.test",
    sub="admin-sub",
    body=None,
    with_auth=True,
):
    """A verified API-GW-authorizer ``PUT /members/config/{configId}`` event.

    ``capabilities`` drives the Tenant_Admin gate (the route requires ``members:admin``);
    ``with_auth=False`` omits the authorizer context entirely (the no-token 401 case).
    """
    event = {
        "httpMethod": "PUT",
        "path": f"/members/config/{config_id}",
        "headers": {},
        "queryStringParameters": None,
        "body": json.dumps(body) if body is not None else None,
    }
    if with_auth:
        event["requestContext"] = {
            "authorizer": {
                "claims": {
                    "sub": sub,
                    "email": email,
                    "custom:entitlements": _entitlement(tenant, capabilities),
                }
            }
        }
    return event


def _envelope(resp):
    return json.loads(resp["body"])


def _valid_fields_body():
    return {
        "fields": {"nickname": {"key": "nickname", "type": "string"}},
        "overrides": {},
        "functional_groups": [],
    }


# ── Authentication + Tenant_Admin entitlement (R3.1, R3.3) ────────────────────────────


def test_write_config_no_token_returns_401(repo):
    # No authorizer context, no bearer header → the edge cannot authenticate → 401, no write.
    resp = app.handler(_event("fields", body=_valid_fields_body(), with_auth=False))
    assert resp["statusCode"] == 401
    assert repo.calls == []  # auth failed before the write path


def test_write_config_non_admin_returns_403_and_never_writes(repo):
    # A verified caller holding members:write (NOT members:admin) for the tenant → the route's
    # members:admin gate denies with 403, and the config-write service is NEVER reached (R3.3).
    resp = app.handler(
        _event(
            "fields",
            capabilities=("members:write", "members:read"),
            body=_valid_fields_body(),
        )
    )
    assert resp["statusCode"] == 403
    assert repo.calls == []


def test_write_config_tenant_not_in_entitlement_returns_403(repo):
    # The token entitles tenant "other-tenant"; the X-Tenant selector is absent and the single
    # entitled tenant is not the one being addressed via admin — the caller holds no members:admin
    # for the active tenant → 403, no write.
    resp = app.handler(
        _event(
            "fields",
            tenant="other-tenant",
            capabilities=("members:read",),
            body=_valid_fields_body(),
        )
    )
    assert resp["statusCode"] == 403
    assert repo.calls == []


def test_write_config_admin_valid_write_returns_200(repo):
    # A verified Tenant_Admin writing a SAM-owned config row via the GENERIC route (scope) → 200
    # with the authoritative version, and the write path IS entered (one put recorded).
    # (config#fields now has its OWN Change-Op route — spec 03 Task 2.7 — so the generic
    # write_config door is exercised here with `scope`, which it still serves.)
    resp = app.handler(_event("scope", body={"dimensions": []}))
    assert resp["statusCode"] == 200
    assert len(repo.calls) == 1


# ── tenant_id resolved from the token, not the body (R3.2) ────────────────────────────


def test_write_config_tenant_resolved_from_token_not_body(repo):
    # Verify-before-trust: a rogue body tenant_id can NEVER redirect the write. The service is
    # handed the VERIFIED tenant (h-dcn), not the "evil-tenant" the body carries. Exercised via
    # the generic route with `scope` (config#fields has its own route now — spec 03 Task 2.7).
    body = {"dimensions": [], "tenant_id": "evil-tenant"}
    resp = app.handler(_event("scope", tenant=_TENANT, body=body))
    assert resp["statusCode"] == 200
    assert len(repo.calls) == 1
    assert repo.calls[0]["tenant_id"] == _TENANT
    # The rogue tenant was never written under, and is not carried into the attributes either.
    assert repo.calls[0]["tenant_id"] != "evil-tenant"
    assert "tenant_id" not in repo.calls[0]["attributes"]


# ── Closed config-id write surface — accept {fields,scope,mail}, reject views/unknown ─


# NOTE (spec 03 Task 2.7): `fields` is NO LONGER served by this generic /{configId} route — it
# has its own literal Change-Op route (PUT /members/config/fields → write_config_fields), declared
# BEFORE this generic route so the literal wins. The generic write_config door now serves exactly
# {scope, mail}; its config#fields dispatch tests live in test_config_fields_change_op_dispatch.py.
@pytest.mark.parametrize("config_id", ["scope", "mail"])
def test_write_config_accepts_the_generic_sam_owned_ids(repo, config_id):
    # The generic-route ids are ACCEPTED (pass the closed-set gate). `scope` (3.3) and `mail`
    # (5.1) have wired validators; the key assertion is that neither is rejected as an unknown id
    # (no 400 from the closed-set guard). An empty-ish body is valid tenant-wide / fail-closed.
    resp = app.handler(_event(config_id, body={}))
    assert resp["statusCode"] != 400


def test_write_config_fields_id_is_handled_by_the_change_op_route_not_the_generic_service(repo):
    # spec 03 Task 2.7 / design-review Q7a: PUT /members/config/fields resolves to the dedicated
    # Change-Op route, NOT this generic write_config door. The OLD whole-overlay body is no longer
    # accepted there and the generic config-write service (this fixture's repo) is NEVER reached
    # for `fields`. Task 5.3a: that retired whole-overlay body (`_valid_fields_body` is exactly
    # the `fields`/`overrides`/`functional_groups` whole record) is now rejected as a STALE CLIENT
    # — an intelligible 409 `errors.api.staleClient` "reload the app", not the generic 400.
    from sam.members.handler.router import get_router

    assert get_router().resolve("PUT", "/members/config/fields").spec.name == (
        "write_config_fields"
    )
    resp = app.handler(_event("fields", body=_valid_fields_body()))
    assert resp["statusCode"] == 409
    assert json.loads(resp["body"])["code"] == "errors.api.staleClient"
    assert [c for c in repo.calls if c["config_id"] == "fields"] == []


# ── config#fields is STRUCTURALLY excluded from the generic whole-object door (Task 7.1) ──
#
# spec 03 Task 7.1 (R1.5 / R11.1): the dangerous whole-object `config#fields` replace must not be
# reachable from a client. The primary structural enforcement is that the GENERIC `write_config`
# route (`PUT /members/config/{configId}` → whole-row `put_config`) no longer accepts `fields` at
# all — `config#fields` is writable ONLY via the Change-Op route (`write_config_fields` →
# `apply_ops`). The literal-route-wins ordering already sends `/members/config/fields` to the
# Change-Op door; this makes the exclusion a STRUCTURAL guarantee (belt-and-braces), so even a
# request that reaches the generic branch with `configId=fields` is rejected before any
# `put_config`. `scope`/`mail` keep their whole-object contract.


def test_generic_write_config_surface_excludes_fields_but_keeps_scope_and_mail():
    # The generic whole-object route's closed set must NOT contain `fields` (Task 7.1) while still
    # serving `scope` and `mail`. This is the structural invariant behind the dispatch rejection.
    from services import projection_schema as schema

    assert schema.CONFIG_ID_FIELDS not in dispatch_mod._WRITABLE_CONFIG_IDS
    assert schema.CONFIG_ID_SCOPE in dispatch_mod._WRITABLE_CONFIG_IDS
    assert schema.CONFIG_ID_MAIL in dispatch_mod._WRITABLE_CONFIG_IDS


def test_generic_write_config_branch_rejects_fields_and_never_reaches_put_config(repo):
    # Belt-and-braces: even if a `configId=fields` request reached the GENERIC `write_config`
    # dispatch branch directly (bypassing the literal-route-wins ordering), it is rejected with a
    # caller-safe ConfigWriteValidationError (→ 400) BEFORE any `put_config`. The whole-row replace
    # is structurally unreachable for `config#fields` from a request (Task 7.1 / R1.5 / R11.1).
    from sam.members.handler.app import RequestContext
    from sam.members.handler._http import ParsedRequest
    from sam.members.handler.routes import ROUTES

    write_config_spec = next(r for r in ROUTES if r.name == "write_config")
    ctx = RequestContext(
        tenant_id=_TENANT,
        sub="admin-sub",
        capability="members:admin",
        path_params={"configId": "fields"},
    )
    request = ParsedRequest(
        method="PUT",
        path="/members/config/fields",
        headers={},
        query={},
        body=_valid_fields_body(),
    )

    with pytest.raises(ConfigWriteValidationError):
        dispatch_mod.dispatch_route(
            service=None, spec=write_config_spec, request=request, ctx=ctx
        )
    # The whole-object write path was never entered for `fields`.
    assert [c for c in repo.calls if c["config_id"] == "fields"] == []


def test_write_config_scope_is_persisted_end_to_end(repo):
    # Task 3.3: with the scope validator wired, a `{dimensions:[…]}` body round-trips the FULL
    # edge → service → repository path (the gap found in the task-3 reconciliation: the frontend
    # mirror + the repository-direct round-trip test did not exercise this seam, so PUT scope
    # 500'd). A valid scope write now returns 200 and reaches the repository with config_id=scope.
    body = {
        "dimensions": [
            {
                "key": "region",
                "field": "region",
                "enabled": True,
                "values": ["Noord", "Zuid"],
            }
        ]
    }
    resp = app.handler(_event("scope", body=body))
    assert resp["statusCode"] == 200
    assert repo.calls[0]["config_id"] == "scope"
    assert repo.calls[0]["attributes"] == {"dimensions": body["dimensions"]}


def test_write_config_scope_empty_dimensions_persists_tenant_wide(repo):
    # R8.5/R1.6: an empty dimensions body is a valid tenant-wide scope write (200, persisted).
    resp = app.handler(_event("scope", body={"dimensions": []}))
    assert resp["statusCode"] == 200
    assert repo.calls[0]["config_id"] == "scope"
    assert repo.calls[0]["attributes"] == {"dimensions": []}


def test_write_config_scope_malformed_body_is_caller_safe_400_no_write(repo):
    # A malformed scope body (dimensions not a list) is a DELIBERATE caller-safe 400 from the
    # service validator — not a 500 — and nothing is persisted.
    resp = app.handler(_event("scope", body={"dimensions": "not-a-list"}))
    assert resp["statusCode"] == 400
    assert repo.calls == []


def test_write_config_mail_is_persisted_end_to_end(repo):
    # Task 5.1: with the mail validator wired, a config#mail body round-trips the FULL
    # edge → service → repository path. A valid mail write returns 200 and persists the
    # fail-closed-shaped scalars with config_id=mail.
    body = {
        "mail_enabled": True,
        "mail_certified": True,
        "mail_domain": "h-dcn.nl",
        "mail_local_part": "info",
        "mail_reply_to_default": "reply@h-dcn.nl",
    }
    resp = app.handler(_event("mail", body=body))
    assert resp["statusCode"] == 200
    assert repo.calls[0]["config_id"] == "mail"
    attrs = repo.calls[0]["attributes"]
    assert attrs["mail_enabled"] is True
    assert attrs["mail_domain"] == "h-dcn.nl"
    assert attrs["mail_reply_to_default"] == "reply@h-dcn.nl"


def test_write_config_mail_empty_body_persists_fail_closed(repo):
    # An empty mail body is valid (fail-closed defaults) → 200, persisted.
    resp = app.handler(_event("mail", body={}))
    assert resp["statusCode"] == 200
    assert repo.calls[0]["config_id"] == "mail"
    assert repo.calls[0]["attributes"]["mail_enabled"] is False


def test_write_config_views_is_rejected_with_no_write(repo):
    # `views` is RETIRED — the write surface is closed to exactly {fields, scope, mail}; `views`
    # is rejected at the route with a 400 and NO write (Config_Views_Residue is never authored,
    # R2.5).
    resp = app.handler(_event("views", body=_valid_fields_body()))
    assert resp["statusCode"] == 400
    assert repo.calls == []


def test_write_config_unknown_id_is_rejected_with_no_write(repo):
    # An id outside the closed set → rejected at the route (400) with no write (R2.2).
    resp = app.handler(_event("bogus", body=_valid_fields_body()))
    assert resp["statusCode"] == 400
    assert repo.calls == []


def test_write_config_unknown_id_rejection_is_caller_safe_400(repo):
    # The closed-set rejection is a DELIBERATE, caller-safe validation error (not a 500): the
    # envelope carries success:false and a stable validation code.
    resp = app.handler(_event("views", body=_valid_fields_body()))
    assert resp["statusCode"] == 400
    env = _envelope(resp)
    assert env["success"] is False
    assert env["code"] == "errors.validation.failed"


# ── Success envelope: {success, configId, version} 200 (R1.1, R1.3) ───────────────────


def test_write_config_success_returns_configid_and_authoritative_version(repo):
    # A valid write returns 200 whose data echoes the configId and the authoritative Version_Stamp
    # the service stamped (R1.3). The envelope is the platform {success:true, data} shape.
    # Exercised via the generic route with `scope` (config#fields has its own route now, 2.7).
    resp = app.handler(_event("scope", body={"dimensions": []}))
    assert resp["statusCode"] == 200
    env = _envelope(resp)
    assert env["success"] is True
    assert env["data"]["success"] is True
    assert env["data"]["configId"] == "scope"
    assert env["data"]["version"] == _VERSION
    # The authoritative version the caller sees is the SAME stamp written to the row.
    assert repo.calls[0]["version"] == _VERSION


# ── Unexpected-exception path: bodied generic 500, never str(e) (R17.1, R17.2) ────────


def test_write_config_unexpected_exception_returns_generic_500_not_str_e(
    monkeypatch, repo
):
    # SAM-plane error conventions (steering 35): an UNANTICIPATED error inside the write path
    # becomes a BODIED, generic 500 — never an empty 502, and the internal exception text is
    # NEVER echoed to the client.
    _SECRET = "boom: a secret internal stack detail that must NOT leak"

    class _BoomService:
        def put_config(self, *a, **k):
            raise RuntimeError(_SECRET)

    monkeypatch.setattr(
        dispatch_mod, "get_config_write_service", lambda: _BoomService()
    )

    # Exercised via the generic route with `scope` (config#fields has its own route now, 2.7).
    resp = app.handler(_event("scope", body={"dimensions": []}))
    assert resp["statusCode"] == 500
    env = _envelope(resp)
    assert env["success"] is False
    assert env["error"] == "Internal error"
    assert env["code"] == "errors.api.serverError"
    # The caught-exception path echoes NOTHING of the internal error (no str(e) leak).
    assert "boom" not in resp["body"]
    assert _SECRET not in resp["body"]
