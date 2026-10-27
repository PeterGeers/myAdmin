"""
Spec 03, Task 2.7 — edge/route tests for ``PUT /members/config/fields`` (Change-Op body).

These pin the observable security + routing + dispatch contract of the config#fields CHANGE-OP
write path end-to-end through the thin Members Lambda edge (``sam/members/handler/app.py`` +
``_dispatch.py`` + ``routes.py``), WITHOUT touching live AWS. The Change-Op service is injected
over an in-memory fake repository (no boto3, no DynamoDB) via the
``_dispatch.get_config_fields_crud_service`` seam the dispatch resolves through.

What each requirement maps to here (design C1/C2 + design-review Q7a):

- **One route, Change-Op body (Q7a):** ``PUT /members/config/fields`` carries a list of
  identity-keyed ops (``set_field`` / ``set_field_application`` / ``reset_field`` /
  ``delete_field`` / ``set_group`` / ``delete_group``); each op is dispatched to the matching
  ``ConfigFieldsCrudService`` method. The whole-overlay body is no longer accepted (→ 400).
- **Existing admin gate + tenant-from-token (steering 39):** no token → 401; a verified caller
  who lacks ``members:admin`` → 403 and the service is NEVER reached; ``tenant_id`` is the
  VERIFIED tenant, never the body.
- **Error mapping:** a ``ConfigFieldsCrudError`` (malformed envelope / out-of-surface attr) → a
  caller-safe 400; a ``StaleVersionError`` (version-conditional write lost the race) → 409.
- **No raw internals leaked (steering 39):** an unexpected error → a bodied generic 500.

Validates: Requirements R1, R2, R4, R6 (edge/dispatch slice).
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

from sam.members.domain.config_fields_crud_service import ConfigFieldsCrudService
from sam.members.handler import _dispatch as dispatch_mod
from sam.members.handler import app
from sam.members.repository.projection_config_write_repository import StaleVersionError

_TENANT = "h-dcn"
_VERSION = "2026-10-26T09:00:00+00:00"


# ── Fake apply_ops repository + real domain service (no boto3, no DynamoDB) ───────────


class FakeApplyOpsRepository:
    """In-memory stand-in for ``MembersConfigWriteRepository`` — records each ``apply_ops`` call.

    The Change-Op path through the real :class:`ConfigFieldsCrudService` is exercised end to end
    (op surface validation + placement + base-version resolution), but the atomic write is
    recorded instead of issued to DynamoDB. ``calls`` lets a test assert WHICH ops reached the
    repository (and under which tenant), and — on the rejection paths — that NO write happened.

    ``raise_stale`` makes the next ``apply_ops`` raise :class:`StaleVersionError` (the 409 path).
    """

    def __init__(self):
        self.calls = []
        self.raise_stale = False

    def apply_ops(self, tenant_id, config_id, ops, base_version, client_op_id=None):
        if self.raise_stale:
            raise StaleVersionError("row changed under the caller")
        self.calls.append(
            {
                "tenant_id": tenant_id,
                "config_id": config_id,
                "ops": [dict(op) for op in ops],
                "base_version": base_version,
                "client_op_id": client_op_id,
            }
        )
        return {"version": _VERSION, "idempotent_replay": False}


class FakeReader:
    """A reader whose resolved overlay is empty — so every op is a first-write CREATE.

    Returns the empty/never-authored wire shape, which the service reads as "no row yet"
    (base_version ``None``), the simplest deterministic placement for an edge/dispatch test.
    """

    def get_raw_fields_overlay(self, tenant_id, consistent_read=False):
        return {"fields": {}, "fixed_overrides": {}, "functional_groups": {}}


@pytest.fixture()
def repo() -> FakeApplyOpsRepository:
    return FakeApplyOpsRepository()


@pytest.fixture(autouse=True)
def inject_config_fields_crud_service(monkeypatch, repo):
    """Wire the EDGE's config#fields Change-Op seam to a real service over the fake repo.

    The dispatch resolves the service via ``_dispatch.get_config_fields_crud_service``
    (production builds it over the concrete write repository + a fresh projection reader). Patch
    THAT name so the write path reaches the fake — the service wraps the in-memory fake repo + a
    fake empty reader, so no AWS is touched. Rejection-path tests then assert ``repo.calls == []``.
    """
    service = ConfigFieldsCrudService(repo, reader=FakeReader())
    monkeypatch.setattr(
        dispatch_mod, "get_config_fields_crud_service", lambda: service
    )
    return service


# ── Auth helpers (verified API-GW-authorizer claims) ──────────────────────────────────


def _entitlement(tenant, capabilities):
    return json.dumps({"v": 1, "t": {tenant: list(capabilities)}})


def _event(
    *,
    tenant=_TENANT,
    capabilities=("members:admin",),
    email="admin@h-dcn.test",
    sub="admin-sub",
    body=None,
    with_auth=True,
):
    """A verified API-GW-authorizer ``PUT /members/config/fields`` event."""
    event = {
        "httpMethod": "PUT",
        "path": "/members/config/fields",
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


def _set_field_op():
    return {"op": "set_field", "key": "nickname", "attrs": {"label": "Nickname"}}


# ── Routing: the literal /members/config/fields wins over /{configId} ─────────────────


def test_config_fields_route_resolves_to_change_op_handler_not_generic_write():
    # The literal PUT /members/config/fields must resolve to write_config_fields (the Change-Op
    # route), NOT the generic write_config /{configId} route — the literal is declared first.
    from sam.members.handler.router import get_router

    match = get_router().resolve("PUT", "/members/config/fields")
    assert match.spec.name == "write_config_fields"


# ── Authentication + Tenant_Admin entitlement + tenant-from-token ─────────────────────


def test_config_fields_no_token_returns_401_no_write(repo):
    resp = app.handler(_event(body={"ops": [_set_field_op()]}, with_auth=False))
    assert resp["statusCode"] == 401
    assert repo.calls == []


def test_config_fields_non_admin_returns_403_and_never_writes(repo):
    # A verified members:write (NOT members:admin) caller → the route's members:admin gate denies
    # with 403, and the Change-Op service is NEVER reached.
    resp = app.handler(
        _event(
            capabilities=("members:write", "members:read"),
            body={"ops": [_set_field_op()]},
        )
    )
    assert resp["statusCode"] == 403
    assert repo.calls == []


def test_config_fields_tenant_resolved_from_token_not_body(repo):
    # Verify-before-trust (steering 39): a rogue body tenant_id can NEVER redirect the write — the
    # service is handed the VERIFIED tenant (h-dcn), not the body's "evil-tenant".
    body = {"tenant_id": "evil-tenant", "ops": [_set_field_op()]}
    resp = app.handler(_event(tenant=_TENANT, body=body))
    assert resp["statusCode"] == 200
    assert len(repo.calls) == 1
    assert repo.calls[0]["tenant_id"] == _TENANT


# ── Dispatch: each op kind reaches the matching service method ────────────────────────


def test_config_fields_set_field_dispatches_definition_op(repo):
    resp = app.handler(_event(body={"ops": [_set_field_op()]}))
    assert resp["statusCode"] == 200
    assert len(repo.calls) == 1
    # A variable field on an empty row is a CREATE: one SET of the whole entry under fields.<key>.
    ops = repo.calls[0]["ops"]
    assert ops[0]["action"] == "SET"
    assert ops[0]["path"] == ["fields", "nickname"]
    assert ops[0]["value"] == {"label": "Nickname"}


def test_config_fields_set_field_application_dispatches_application_op(repo):
    resp = app.handler(
        _event(
            body={
                "ops": [
                    {
                        "op": "set_field_application",
                        "key": "nickname",
                        "attrs": {"application_visible": True},
                    }
                ]
            }
        )
    )
    assert resp["statusCode"] == 200
    assert len(repo.calls) == 1
    assert repo.calls[0]["ops"][0]["value"] == {"application_visible": True}


def test_config_fields_set_group_dispatches_group_op(repo):
    resp = app.handler(
        _event(
            body={
                "ops": [
                    {"op": "set_group", "group": "personal", "attrs": {"order": 2}}
                ]
            }
        )
    )
    assert resp["statusCode"] == 200
    assert len(repo.calls) == 1
    assert repo.calls[0]["ops"][0]["path"][0] == "functional_groups"


def test_config_fields_delete_field_dispatches_remove_op(repo):
    resp = app.handler(
        _event(body={"ops": [{"op": "delete_field", "key": "nickname"}]})
    )
    assert resp["statusCode"] == 200
    assert len(repo.calls) == 1
    assert repo.calls[0]["ops"][0]["action"] == "REMOVE"
    assert repo.calls[0]["ops"][0]["path"] == ["fields", "nickname"]


def test_config_fields_multiple_ops_each_reach_the_repository(repo):
    # A Change-Op list with several ops applies each via the service (one apply_ops per op here).
    resp = app.handler(
        _event(
            body={
                "ops": [
                    _set_field_op(),
                    {"op": "set_group", "group": "personal", "attrs": {"order": 1}},
                ]
            }
        )
    )
    assert resp["statusCode"] == 200
    assert len(repo.calls) == 2
    env = _envelope(resp)
    assert env["data"]["success"] is True
    assert len(env["data"]["results"]) == 2


def test_config_fields_client_op_id_is_forwarded(repo):
    resp = app.handler(
        _event(body={"ops": [dict(_set_field_op(), client_op_id="op-123")]})
    )
    assert resp["statusCode"] == 200
    assert repo.calls[0]["client_op_id"] == "op-123"


# ── Error mapping: validation → 400, stale version → 409 ──────────────────────────────


def test_config_fields_whole_overlay_body_is_rejected_as_stale_client_409_no_write(repo):
    # Task 5.3a (design Slice 3): the RETIRED whole-overlay body a cached OLD SPA bundle sends
    # (`fields`/`overrides`/`functional_groups` as a whole record, no `ops` list) is now rejected
    # as a STALE CLIENT — a caller-safe 409 with the DISTINCT `errors.api.staleClient` code and NO
    # write — so the SPA renders a "reload the app" prompt instead of an obscure validation 400.
    resp = app.handler(
        _event(body={"fields": {}, "overrides": {}, "functional_groups": []})
    )
    assert resp["statusCode"] == 409
    assert repo.calls == []
    env = _envelope(resp)
    assert env["success"] is False
    assert env["code"] == "errors.api.staleClient"
    # Intelligible + actionable, and distinct from the generic ops-validation 400 and the
    # data-conflict 409 (`errors.api.conflict`).
    assert "reload" in env["error"].lower()
    assert env["code"] != "errors.validation.failed"
    assert env["code"] != "errors.api.conflict"


def test_config_fields_empty_ops_list_is_rejected_400(repo):
    resp = app.handler(_event(body={"ops": []}))
    assert resp["statusCode"] == 400
    assert repo.calls == []


def test_config_fields_unknown_op_token_is_rejected_400_no_write(repo):
    resp = app.handler(
        _event(body={"ops": [{"op": "drop_everything", "key": "x"}]})
    )
    assert resp["statusCode"] == 400
    assert repo.calls == []


def test_config_fields_out_of_surface_attr_is_rejected_400_no_write(repo):
    # set_field is DISJOINT from application attrs — an application_* key on set_field is rejected
    # by the service's surface guard (ConfigFieldsCrudError) → a caller-safe 400, no write.
    resp = app.handler(
        _event(
            body={
                "ops": [
                    {
                        "op": "set_field",
                        "key": "nickname",
                        "attrs": {"application_visible": True},
                    }
                ]
            }
        )
    )
    assert resp["statusCode"] == 400
    assert repo.calls == []


def test_config_fields_missing_identity_is_rejected_400(repo):
    resp = app.handler(_event(body={"ops": [{"op": "set_field", "attrs": {"label": "x"}}]}))
    assert resp["statusCode"] == 400
    assert repo.calls == []


# ── Task 5.3a: stale-SPA-bundle guard (whole-overlay body → intelligible "reload" 409) ──


@pytest.mark.parametrize(
    "stale_key, stale_value",
    [
        ("fields", {"nickname": {"label": "x"}}),
        ("overrides", {"personal.gender": {"label": "x"}}),
        ("fixed_overrides", {"personal.gender": {"label": "x"}}),
        ("functional_groups", {"personal": {"order": 1}}),
        ("functional_groups", [{"key": "personal", "order": 1}]),  # pre-migration LIST shape
        ("field_overlay", {"fields": {}, "overrides": {}}),
    ],
)
def test_config_fields_each_whole_overlay_key_is_a_stale_client_409_no_write(
    repo, stale_key, stale_value
):
    # Any of the retired raw-shape keys (steering 39) present on a write body — with no `ops`
    # list — is the stale-bundle signal: a distinct 409 `errors.api.staleClient`, never a write.
    resp = app.handler(_event(body={stale_key: stale_value}))
    assert resp["statusCode"] == 409, stale_key
    assert repo.calls == []
    env = _envelope(resp)
    assert env["code"] == "errors.api.staleClient", stale_key


def test_config_fields_empty_ops_list_is_still_the_generic_400_not_stale_client(repo):
    # DISTINCTNESS: a body that genuinely carries `ops` (just empty) is a malformed Change-Op
    # envelope — the GENERIC 400, NOT the stale-client 409. The guard must not swallow a
    # current-bundle empty-ops mistake as "reload the app".
    resp = app.handler(_event(body={"ops": []}))
    assert resp["statusCode"] == 400
    assert repo.calls == []
    env = _envelope(resp)
    assert env["code"] == "errors.validation.failed"


def test_config_fields_valid_change_op_body_still_works_alongside_the_guard(repo):
    # The guard only fires when there is NO usable `ops` list AND a whole-overlay key is present;
    # a valid Change-Op body dispatches normally to the service and writes (200).
    resp = app.handler(_event(body={"ops": [_set_field_op()]}))
    assert resp["statusCode"] == 200
    assert len(repo.calls) == 1


def test_config_fields_ops_present_wins_even_if_a_legacy_key_is_also_sent(repo):
    # Defensive: a transitional client that sends BOTH a real `ops` list and a stray legacy key
    # is treated as a VALID Change-Op write (the `ops` list is honored) — the guard only triggers
    # on the empty/absent-ops path, so a usable `ops` list is never mis-flagged as stale.
    resp = app.handler(
        _event(body={"ops": [_set_field_op()], "fields": {"nickname": {"label": "x"}}})
    )
    assert resp["statusCode"] == 200
    assert len(repo.calls) == 1


def test_config_fields_stale_client_409_carries_no_raw_internals(repo):
    # Steering 39: the "reload the app" body names only the stale-client condition + remedy — it
    # must NOT echo the raw-shape keys or any storage internals back to the caller.
    resp = app.handler(
        _event(body={"fields": {}, "overrides": {}, "functional_groups": {}})
    )
    assert resp["statusCode"] == 409
    body_text = resp["body"].lower()
    for leak in ("overrides", "fixed_overrides", "functional_groups", "field_overlay"):
        assert leak not in body_text


def test_config_fields_stale_client_guard_runs_after_auth_not_before(repo):
    # The guard is a dispatch-layer concern, downstream of auth: a stale whole-overlay body from
    # an UNauthenticated caller is still a 401 first (auth before body-shape), and no write.
    resp = app.handler(
        _event(body={"fields": {}, "functional_groups": {}}, with_auth=False)
    )
    assert resp["statusCode"] == 401
    assert repo.calls == []


def test_config_fields_stale_version_maps_to_409(repo):
    # The version-conditional write lost the race (row changed under the caller) → the service
    # surfaces StaleVersionError, which the edge maps to a caller-safe 409 "reload and retry".
    repo.raise_stale = True
    resp = app.handler(_event(body={"ops": [_set_field_op()]}))
    assert resp["statusCode"] == 409
    env = _envelope(resp)
    assert env["success"] is False
    assert env["code"] == "errors.api.conflict"


# ── No raw internals: unexpected error → bodied generic 500 (steering 39) ─────────────


def test_config_fields_unexpected_exception_returns_generic_500_not_str_e(
    monkeypatch, repo
):
    _SECRET = "boom: a secret internal detail that must NOT leak"

    class _BoomService:
        def set_field(self, *a, **k):
            raise RuntimeError(_SECRET)

    monkeypatch.setattr(
        dispatch_mod, "get_config_fields_crud_service", lambda: _BoomService()
    )
    resp = app.handler(_event(body={"ops": [_set_field_op()]}))
    assert resp["statusCode"] == 500
    env = _envelope(resp)
    assert env["success"] is False
    assert _SECRET not in resp["body"]
    assert "boom" not in resp["body"]
