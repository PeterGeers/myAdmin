"""
spec 15 (SAM Page Look-and-Feel) Task 8.1 — the Layer-1 authoring ROUTES + dispatch + edge
error-envelope mapping.

Spec: `.kiro/specs/Members/15 - sam-page-look-and-feel` (design C3 / C6, Error Handling table).

These pin the observable SECURITY + routing + caller-safe-error contract of the `members:admin`-
gated Layer-1 look-and-feel authoring surface (GET/PUT `/members/look-and-feel`) end-to-end through
the thin Members Lambda edge (`sam/members/handler/app.py` + `_dispatch*.py` + `routes.py`) —
WITHOUT touching live AWS:

  * the verified JWT is REQUIRED: a missing/invalid token → 401, and the service is NEVER reached;
  * `members:admin` + `self_service=False` gate: a non-admin caller → 403, service never reached;
  * `tenant_id` is derived from the VERIFIED token, NEVER the body: a rogue body `tenant_id` can
    never redirect the read/author target (verify-before-trust, steering 39);
  * a valid GET resolves the verified tenant's settings; a valid PUT authors ONE attribute value;
  * the caller-safe error envelope never leaks internals — the DELIBERATE domain errors map to:
      - `LookAndFeelValidationError` (unsupported attribute / out-of-set value / unknown page /
        missing `attribute`) → 422 identifying the rejected setting;
      - `CrossTenantCopyError` (copy source in another tenant) → 403 generic "not permitted";
      - `StaleVersionError` (row changed under the caller) → 409 reload-and-retry.

The edge's `get_look_and_feel_settings_service` accessor is monkeypatched to a spy (the documented
test seam), so no AWS is touched.

Validates: Requirements 2.4, 2.5, 3.4, 4.5, 8.1, 8.4, 9.4
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

from sam.members.domain.look_and_feel_settings_service import (
    CrossTenantCopyError,
    LookAndFeelValidationError,
)
from sam.members.handler import _dispatch as dispatch_mod
from sam.members.handler import app
from sam.members.repository.projection_config_write_repository import StaleVersionError

_TENANT = "h-dcn"


def _entitlement(tenant, capabilities):
    return json.dumps({"v": 1, "t": {tenant: list(capabilities)}})


def _event(
    *,
    method="PUT",
    tenant=_TENANT,
    capabilities=("members:admin",),
    sub="admin-sub",
    body=None,
    with_auth=True,
):
    """A verified API-GW-authorizer ``/members/look-and-feel`` event."""
    raw_body = json.dumps(body) if body is not None else None
    event = {
        "httpMethod": method,
        "path": "/members/look-and-feel",
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


class _SpyLookAndFeelService:
    """Records get/set/copy calls + returns a result (or raises a configured error)."""

    def __init__(self, *, raises=None, get_result=None, write_result=None):
        self.get_calls = []
        self.set_calls = []
        self.copy_calls = []
        self._raises = raises
        self._get_result = get_result if get_result is not None else {}
        self._write_result = (
            write_result if write_result is not None else {"version": "v-next"}
        )

    def get_settings(self, tenant_id, page_id="application_form"):
        self.get_calls.append({"tenant_id": tenant_id, "page_id": page_id})
        if self._raises is not None:
            raise self._raises
        return self._get_result

    def set_setting(self, tenant_id, page_id, attribute, value, *, client_op_id=None):
        self.set_calls.append(
            {
                "tenant_id": tenant_id,
                "page_id": page_id,
                "attribute": attribute,
                "value": value,
            }
        )
        if self._raises is not None:
            raise self._raises
        return self._write_result

    def copy_settings(
        self,
        tenant_id,
        source_page_id,
        target_page_id,
        *,
        source_tenant_id=None,
        client_op_id=None,
    ):
        self.copy_calls.append(
            {
                "tenant_id": tenant_id,
                "source_page_id": source_page_id,
                "target_page_id": target_page_id,
                "source_tenant_id": source_tenant_id,
            }
        )
        if self._raises is not None:
            raise self._raises
        return self._write_result


@pytest.fixture()
def spy():
    return _SpyLookAndFeelService()


@pytest.fixture(autouse=True)
def inject_look_and_feel_service(monkeypatch, spy):
    """Wire the edge's look-and-feel service seam to the spy (documented monkeypatch point)."""
    monkeypatch.setattr(
        dispatch_mod, "get_look_and_feel_settings_service", lambda: spy
    )
    return spy


# ── Auth gate (verified JWT required; members:admin; verified tenant) ────────────────


def test_handler_no_token_returns_401_and_never_reaches_service(spy):
    resp = app.handler(
        _event(with_auth=False, body={"attribute": "color_primary", "value": "#2D5F8A"})
    )
    assert resp["statusCode"] == 401
    assert spy.set_calls == []
    assert spy.get_calls == []


def test_handler_non_admin_returns_403_and_never_reaches_service(spy):
    resp = app.handler(
        _event(
            capabilities=("members:write", "members:read", "members:export"),
            body={"attribute": "color_primary", "value": "#2D5F8A"},
        )
    )
    assert resp["statusCode"] == 403
    assert spy.set_calls == []


def test_handler_get_non_admin_returns_403_and_never_reaches_service(spy):
    resp = app.handler(
        _event(method="GET", capabilities=("members:read", "members:export"))
    )
    assert resp["statusCode"] == 403
    assert spy.get_calls == []


def test_handler_tenant_not_in_entitlement_returns_403(spy):
    resp = app.handler(
        _event(
            tenant="other-tenant",
            capabilities=("members:read",),
            body={"attribute": "color_primary", "value": "#2D5F8A"},
        )
    )
    assert resp["statusCode"] == 403
    assert spy.set_calls == []


# ── Verified tenant (never the body) ─────────────────────────────────────────────────


def test_handler_get_resolves_with_verified_tenant(spy):
    spy._get_result = {"color_primary": "#2D5F8A"}
    resp = app.handler(_event(method="GET"))
    assert resp["statusCode"] == 200
    assert spy.get_calls == [{"tenant_id": _TENANT, "page_id": "application_form"}]
    assert _envelope(resp)["data"]["settings"] == {"color_primary": "#2D5F8A"}


def test_handler_set_dispatches_with_verified_tenant_and_body_attribute(spy):
    resp = app.handler(
        _event(body={"attribute": "color_primary", "value": "#2D5F8A"})
    )
    assert resp["statusCode"] == 200
    assert spy.set_calls == [
        {
            "tenant_id": _TENANT,
            "page_id": "application_form",
            "attribute": "color_primary",
            "value": "#2D5F8A",
        }
    ]


def test_handler_tenant_is_verified_not_body(spy):
    # A rogue body `tenant_id` can never redirect the author target — the dispatch uses the
    # VERIFIED tenant only (verify-before-trust, steering 39).
    resp = app.handler(
        _event(
            body={
                "attribute": "color_primary",
                "value": "#2D5F8A",
                "tenant_id": "evil-tenant",
            }
        )
    )
    assert resp["statusCode"] == 200
    assert spy.set_calls[0]["tenant_id"] == _TENANT


def test_handler_get_tenant_is_verified_not_body(spy):
    # The GET carries no tenant; even a query/body attempt resolves the VERIFIED tenant only.
    event = _event(method="GET")
    event["body"] = json.dumps({"tenant_id": "evil-tenant"})
    resp = app.handler(event)
    assert resp["statusCode"] == 200
    assert spy.get_calls == [{"tenant_id": _TENANT, "page_id": "application_form"}]


def test_handler_clear_with_null_value_dispatches_none(spy):
    resp = app.handler(_event(body={"attribute": "color_primary", "value": None}))
    assert resp["statusCode"] == 200
    assert spy.set_calls[0]["value"] is None


def test_handler_copy_dispatches_with_verified_tenant(spy):
    resp = app.handler(_event(body={"op": "copy"}))
    assert resp["statusCode"] == 200
    assert spy.copy_calls == [
        {
            "tenant_id": _TENANT,
            "source_page_id": "application_form",
            "target_page_id": "application_form",
            "source_tenant_id": None,
        }
    ]
    assert spy.set_calls == []


# ── Caller-safe error envelope (no internals leaked) ──────────────────────────────────


def test_handler_missing_attribute_key_is_422_no_dispatch(spy):
    # An author action with no `attribute` is malformed — surfaced as a caller-safe 422 via the
    # service's own validation error, NOT a silent no-op and NOT a dispatch.
    resp = app.handler(_event(body={"value": "#2D5F8A"}))
    assert resp["statusCode"] == 422
    assert spy.set_calls == []
    assert _envelope(resp)["success"] is False


def test_handler_unsupported_attribute_is_422_identifying_the_setting(monkeypatch):
    spy = _SpyLookAndFeelService(
        raises=LookAndFeelValidationError(
            "unsupported look-and-feel attribute 'not_real'"
        )
    )
    monkeypatch.setattr(
        dispatch_mod, "get_look_and_feel_settings_service", lambda: spy
    )
    resp = app.handler(_event(body={"attribute": "not_real", "value": "x"}))
    assert resp["statusCode"] == 422
    env = _envelope(resp)
    assert env["success"] is False
    assert env["code"] == "errors.validation.failed"
    # The caller-safe detail names the rejected setting (the client's own key), no stack/internals.
    assert "not_real" in env["error"]


def test_handler_invalid_value_is_422(monkeypatch):
    spy = _SpyLookAndFeelService(
        raises=LookAndFeelValidationError(
            "invalid value 'huge' for 'base_spacing': permitted values are "
            "['compact', 'normal', 'relaxed']"
        )
    )
    monkeypatch.setattr(
        dispatch_mod, "get_look_and_feel_settings_service", lambda: spy
    )
    resp = app.handler(_event(body={"attribute": "base_spacing", "value": "huge"}))
    assert resp["statusCode"] == 422
    assert _envelope(resp)["code"] == "errors.validation.failed"


def test_handler_cross_tenant_copy_is_403_generic(monkeypatch):
    spy = _SpyLookAndFeelService(
        raises=CrossTenantCopyError("copy is permitted only within a single tenant")
    )
    monkeypatch.setattr(
        dispatch_mod, "get_look_and_feel_settings_service", lambda: spy
    )
    resp = app.handler(
        _event(body={"op": "copy", "source_tenant_id": "other-tenant"})
    )
    assert resp["statusCode"] == 403
    env = _envelope(resp)
    assert env["success"] is False
    assert env["code"] == "errors.api.forbidden"
    # Generic — no cross-tenant information leak (the other tenant id is NOT echoed).
    assert "other-tenant" not in env["error"]


def test_handler_stale_version_is_409_reload(monkeypatch):
    spy = _SpyLookAndFeelService(raises=StaleVersionError("version conflict"))
    monkeypatch.setattr(
        dispatch_mod, "get_look_and_feel_settings_service", lambda: spy
    )
    resp = app.handler(
        _event(body={"attribute": "color_primary", "value": "#2D5F8A"})
    )
    assert resp["statusCode"] == 409
    assert _envelope(resp)["code"] == "errors.api.conflict"
