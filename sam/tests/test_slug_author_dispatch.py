"""
bugfix-slug-lifecycle Task 3.1 — the SAM slug-author ROUTE + dispatch + edge error mapping.

Parent spec: `.kiro/specs/Members/14 - public-pages-multi-tenant-serving`.
Bugfix spec: `.kiro/specs/Members/14 .../bugfix-slug-lifecycle` (design.md §Fix Implementation).

These pin the observable security + routing + error-mapping contract of the MISSING
client-reachable SAM slug WRITE (defect B) end-to-end through the thin Members Lambda edge
(`sam/members/handler/app.py` + `_dispatch*.py` + `routes.py`) — WITHOUT touching live AWS:

  * members:admin + self_service=False gate: a non-admin caller is rejected (403) and the slug
    service is NEVER reached;
  * tenant_id from the verified token, never the body: the service is handed the VERIFIED tenant;
  * a valid author dispatches `set_form_slug(verified_tenant, body_slug)` and shapes the result;
  * a missing `slug` body key → 400 (malformed request), no dispatch;
  * `SlugAuthorRejected` (format/prefix) → 422 with the caller-safe detail (no str(e) leak);
  * `SlugAuthorConflict` (foreign owner) → 409 generic message (never the raw SlugTaken);
  * `StaleVersionError` (row changed) → 409 reload-and-retry.

The edge's `get_config_fields_crud_service` accessor is monkeypatched to a spy (the documented
test seam), so no AWS is touched.

Validates (bugfix): Requirements 2.3, 2.4, 3.3, 3.4
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

from sam.members.domain.config_fields_crud_service import (
    SlugAuthorConflict,
    SlugAuthorRejected,
)
from sam.members.handler import _dispatch as dispatch_mod
from sam.members.handler import app
from sam.members.repository.projection_config_write_repository import StaleVersionError

_TENANT = "h-dcn"


def _entitlement(tenant, capabilities):
    return json.dumps({"v": 1, "t": {tenant: list(capabilities)}})


def _event(
    *,
    tenant=_TENANT,
    capabilities=("members:admin",),
    sub="admin-sub",
    body=None,
    with_auth=True,
    omit_body_key=False,
):
    """A verified API-GW-authorizer ``POST /members/application-form/slug`` event."""
    if omit_body_key:
        raw_body = json.dumps({"not_slug": "x"})
    elif body is not None:
        raw_body = json.dumps(body)
    else:
        raw_body = None
    event = {
        "httpMethod": "POST",
        "path": "/members/application-form/slug",
        "headers": {},
        "queryStringParameters": None,
        "body": raw_body,
    }
    if with_auth:
        event["requestContext"] = {
            "authorizer": {
                "claims": {
                    "sub": sub,
                    "custom:entitlements": _entitlement(tenant, capabilities),
                }
            }
        }
    return event


def _envelope(resp):
    return json.loads(resp["body"])


class _SpySlugService:
    """Records set_form_slug() calls + returns a result (or raises a configured error)."""

    def __init__(self, *, raises=None, result=None):
        self.calls = []
        self._raises = raises
        self._result = result if result is not None else {"version": "v-next"}

    def set_form_slug(self, tenant_id, slug, *, client_op_id=None):
        self.calls.append({"tenant_id": tenant_id, "slug": slug})
        if self._raises is not None:
            raise self._raises
        return self._result


@pytest.fixture()
def spy():
    return _SpySlugService()


@pytest.fixture(autouse=True)
def inject_slug_service(monkeypatch, spy):
    """Wire the edge's config#fields service seam (which owns set_form_slug) to the spy."""
    monkeypatch.setattr(dispatch_mod, "get_config_fields_crud_service", lambda: spy)
    return spy


# ── Auth gate ──────────────────────────────────────────────────────────────────────


def test_handler_no_token_returns_401_and_never_authors(spy):
    resp = app.handler(_event(with_auth=False, body={"slug": "h-dcn-x"}))
    assert resp["statusCode"] == 401
    assert spy.calls == []


def test_handler_non_admin_returns_403_and_never_authors(spy):
    resp = app.handler(
        _event(
            capabilities=("members:write", "members:read", "members:export"),
            body={"slug": "h-dcn-x"},
        )
    )
    assert resp["statusCode"] == 403
    assert spy.calls == []


def test_handler_tenant_not_in_entitlement_returns_403(spy):
    resp = app.handler(
        _event(
            tenant="other-tenant", capabilities=("members:read",), body={"slug": "x"}
        )
    )
    assert resp["statusCode"] == 403
    assert spy.calls == []


# ── Dispatch wiring: verified tenant, body slug ──────────────────────────────────────


def test_handler_admin_dispatches_with_verified_tenant_and_body_slug(spy):
    resp = app.handler(_event(body={"slug": "h-dcn-aanmelden"}))
    assert resp["statusCode"] == 200
    assert spy.calls == [{"tenant_id": _TENANT, "slug": "h-dcn-aanmelden"}]


def test_handler_tenant_is_verified_not_body(spy):
    # A rogue body tenant_id can never redirect the author target — the dispatch uses the
    # VERIFIED tenant only.
    resp = app.handler(_event(body={"slug": "h-dcn-x", "tenant_id": "evil-tenant"}))
    assert resp["statusCode"] == 200
    assert spy.calls == [{"tenant_id": _TENANT, "slug": "h-dcn-x"}]


def test_handler_clear_with_null_dispatches_none(spy):
    resp = app.handler(_event(body={"slug": None}))
    assert resp["statusCode"] == 200
    assert spy.calls == [{"tenant_id": _TENANT, "slug": None}]


def test_handler_missing_slug_key_is_400_no_dispatch(spy):
    resp = app.handler(_event(omit_body_key=True))
    assert resp["statusCode"] == 400
    assert spy.calls == []


# ── Error mapping ────────────────────────────────────────────────────────────────────


def test_handler_slug_rejected_is_422_with_caller_safe_detail(monkeypatch):
    spy = _SpySlugService(
        raises=SlugAuthorRejected(
            "slug must start with this tenant's public prefix 'h-dcn'"
        )
    )
    monkeypatch.setattr(dispatch_mod, "get_config_fields_crud_service", lambda: spy)
    resp = app.handler(_event(body={"slug": "other-apply"}))
    assert resp["statusCode"] == 422
    env = _envelope(resp)
    assert env["success"] is False
    assert env["code"] == "errors.validation.failed"
    # The caller-safe detail is surfaced; no raw internals / stack.
    assert "public prefix" in env["error"]


def test_handler_foreign_owner_conflict_is_409_generic(monkeypatch):
    spy = _SpySlugService(raises=SlugAuthorConflict("h-dcn-aanmelden"))
    monkeypatch.setattr(dispatch_mod, "get_config_fields_crud_service", lambda: spy)
    resp = app.handler(_event(body={"slug": "h-dcn-aanmelden"}))
    assert resp["statusCode"] == 409
    env = _envelope(resp)
    assert env["success"] is False
    assert env["code"] == "errors.application.slugConflict"
    # Generic message — the raw slug / SlugTaken is NOT echoed.
    assert "h-dcn-aanmelden" not in env["error"]


def test_handler_stale_version_is_409_reload(monkeypatch):
    spy = _SpySlugService(raises=StaleVersionError("version conflict"))
    monkeypatch.setattr(dispatch_mod, "get_config_fields_crud_service", lambda: spy)
    resp = app.handler(_event(body={"slug": "h-dcn-x"}))
    assert resp["statusCode"] == 409
    assert _envelope(resp)["code"] == "errors.api.conflict"
