"""
slug-prefix SAM-owned — dispatch/edge tests for POST /members/application-form/prefix.

Mirrors `test_slug_author_dispatch.py` (the slug route's sibling) end to end:
  * members:admin gate — unauthenticated → 401, unentitled → 403, tenant-not-in-entitlement → 403,
    service NEVER reached;
  * tenant_id from the verified token, never the body: the service is handed the VERIFIED tenant;
  * a valid author dispatches `set_public_prefix(verified_tenant, body_prefix)`;
  * a missing `prefix` body key → 400 (malformed request), no dispatch;
  * `SlugAuthorRejected` (format/reserved) → 422 with the caller-safe detail (no str(e) leak);
  * `StaleVersionError` → 409 (reload-and-retry).

The prefix route claims NO marker (a prefix is a namespace, not a public address), so there is NO
foreign-owner 409 conflict case — unlike the slug route.
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

from sam.members.domain.config_fields_crud_service import SlugAuthorRejected
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
    """A verified API-GW-authorizer ``POST /members/application-form/prefix`` event."""
    if omit_body_key:
        raw_body = json.dumps({"not_prefix": "x"})
    elif body is not None:
        raw_body = json.dumps(body)
    else:
        raw_body = None
    event = {
        "httpMethod": "POST",
        "path": "/members/application-form/prefix",
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


class _SpyPrefixService:
    """Records set_public_prefix() calls + returns a result (or raises a configured error)."""

    def __init__(self, *, raises=None, result=None):
        self.calls = []
        self._raises = raises
        self._result = result if result is not None else {"version": "v-next"}

    def set_public_prefix(self, tenant_id, prefix, *, client_op_id=None):
        self.calls.append({"tenant_id": tenant_id, "prefix": prefix})
        if self._raises is not None:
            raise self._raises
        return self._result


@pytest.fixture()
def spy():
    return _SpyPrefixService()


@pytest.fixture(autouse=True)
def inject_prefix_service(monkeypatch, spy):
    """Wire the edge's config#fields service seam (which owns set_public_prefix) to the spy."""
    monkeypatch.setattr(dispatch_mod, "get_config_fields_crud_service", lambda: spy)
    return spy


# ── Auth gate ──────────────────────────────────────────────────────────────────────


def test_handler_no_token_returns_401_and_never_authors(spy):
    resp = app.handler(_event(with_auth=False, body={"prefix": "h-dcn"}))
    assert resp["statusCode"] == 401
    assert spy.calls == []


def test_handler_non_admin_returns_403_and_never_authors(spy):
    resp = app.handler(
        _event(
            capabilities=("members:write", "members:read", "members:export"),
            body={"prefix": "h-dcn"},
        )
    )
    assert resp["statusCode"] == 403
    assert spy.calls == []


def test_handler_tenant_not_in_entitlement_returns_403(spy):
    resp = app.handler(
        _event(
            tenant="other-tenant", capabilities=("members:read",), body={"prefix": "x"}
        )
    )
    assert resp["statusCode"] == 403
    assert spy.calls == []


# ── Dispatch wiring: verified tenant, body prefix ────────────────────────────────────


def test_handler_admin_dispatches_with_verified_tenant_and_body_prefix(spy):
    resp = app.handler(_event(body={"prefix": "h-dcn"}))
    assert resp["statusCode"] == 200
    assert spy.calls == [{"tenant_id": _TENANT, "prefix": "h-dcn"}]


def test_handler_tenant_is_verified_not_body(spy):
    resp = app.handler(_event(body={"prefix": "h-dcn", "tenant_id": "evil-tenant"}))
    assert resp["statusCode"] == 200
    assert spy.calls == [{"tenant_id": _TENANT, "prefix": "h-dcn"}]


def test_handler_clear_with_null_dispatches_none(spy):
    resp = app.handler(_event(body={"prefix": None}))
    assert resp["statusCode"] == 200
    assert spy.calls == [{"tenant_id": _TENANT, "prefix": None}]


def test_handler_missing_prefix_key_is_400_no_dispatch(spy):
    resp = app.handler(_event(omit_body_key=True))
    assert resp["statusCode"] == 400
    assert spy.calls == []


# ── Error mapping ────────────────────────────────────────────────────────────────────


def test_handler_prefix_rejected_is_422_with_caller_safe_detail(monkeypatch):
    spy = _SpyPrefixService(
        raises=SlugAuthorRejected(
            "slug must be lowercase, contain only letters, numbers, and hyphens"
        )
    )
    monkeypatch.setattr(dispatch_mod, "get_config_fields_crud_service", lambda: spy)
    resp = app.handler(_event(body={"prefix": "H-DCN"}))
    assert resp["statusCode"] == 422
    env = _envelope(resp)
    assert env["success"] is False
    assert env["code"] == "errors.validation.failed"
    assert "lowercase" in env["error"]


def test_handler_stale_version_is_409_reload(monkeypatch):
    spy = _SpyPrefixService(raises=StaleVersionError("version conflict"))
    monkeypatch.setattr(dispatch_mod, "get_config_fields_crud_service", lambda: spy)
    resp = app.handler(_event(body={"prefix": "h-dcn"}))
    assert resp["statusCode"] == 409
    assert _envelope(resp)["code"] == "errors.api.conflict"
