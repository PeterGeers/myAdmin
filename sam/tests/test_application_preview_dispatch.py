"""
Application Form Builder, Task 1.5 — edge/route tests for the server-side LIVE PREVIEW
``POST /members/application-preview`` (spec 11, R7.2 / R9.2; design §5.3, §6, §10, §11).

These pin the observable contract of the preview route end-to-end through the thin Members
Lambda edge (``sam/members/handler/app.py`` + ``_dispatch.py`` + ``routes.py``), WITHOUT
touching live AWS. They are the dedicated behavioral complement to the route-MAP assertions
in ``test_members_routes.py`` (which only pin that ``preview_application`` is wired/named):

- **Filter parity (R7.2 / R9.2, correctness property 4):** the route returns EXACTLY the
  schema the server's ``MembershipService.get_public_field_config`` produces for an
  EQUIVALENT saved config — the SAME single filtering authority the public form reads
  through, so the in-app preview can never drift from the public render. The preview service
  is injected over the SAME in-memory fakes the public field-config read test
  (``test_public_field_config.py``) uses, so "equivalent saved config" is literally the same
  overlay/catalog/consent the public read filters; the route's 200 ``data`` must equal that
  read's output byte-for-byte.
- **``members:admin``-gated (R9.2):** no token → 401; a verified caller who holds
  ``members:write`` (NOT ``members:admin``) for the active tenant → 403, and the preview
  service is NEVER reached (verify-before-trust; the injected spy records no call).
- **Never writes (R7.2 / R9.2, READ-ONLY):** on the success path the ONLY method the route
  calls on the (spied) preview service is ``get_public_field_config`` — no put/write/mutation
  of any kind — mirroring the design's "READ-ONLY by construction, no DynamoDB mutation".

Validates: Requirements R7.2, R9.2
"""

from __future__ import annotations

import json
import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from sam.members.domain.application_readiness import StaticMailReadinessProvider
from sam.members.domain.application_service import ApplicationService
from sam.members.domain.consent_notice import StaticConsentNoticeProvider
from sam.members.domain.field_resolver import StaticOverlayProvider
from sam.members.domain.membership_service import MembershipService
from sam.members.handler import _dispatch as dispatch_mod
from sam.members.handler import app

# Reuse the EXACT public field-config fixtures so "an equivalent saved config" is literally
# the same overlay/catalog/consent the public read (test_public_field_config.py) filters —
# giving us a real parity oracle, not a hand-rolled approximation.
from sam.tests.test_field_config_endpoint import FakeCatalogRepository, _entry
from sam.tests.test_public_field_config import _overlay_public_form

_TENANT = "h-dcn"


# ── The parity oracle: a real MembershipService over in-memory fakes (no AWS) ─────────


def _oracle_service() -> MembershipService:
    """The SAME send-ready membership service the public field-config test wires.

    Its :meth:`get_public_field_config` is BOTH the preview route's implementation (injected
    below) AND the parity oracle the test asserts against — so the test proves the route
    reuses the one server filter verbatim (zero drift)."""
    repo = FakeCatalogRepository()
    repo.add_type(_TENANT, _entry(_TENANT, "gewoon", order=10))
    repo.add_type(_TENANT, _entry(_TENANT, "erelid", order=20))
    return MembershipService(
        repo,
        overlay_provider=StaticOverlayProvider({_TENANT: _overlay_public_form()}),
        consent_notice_provider=StaticConsentNoticeProvider({_TENANT: "v3"}),
    )


class _PreviewSpy:
    """A preview-service stand-in that records EVERY method call, delegating the read.

    Proves the route is READ-ONLY: on the success path the ONLY method invoked is
    ``get_public_field_config`` (recorded in ``calls``); any write/mutation would show up as a
    different recorded name (or an ``AttributeError`` on an un-stubbed writer the route tried
    to call). Delegates the read to a real oracle service so the returned schema is the genuine
    filter output (parity)."""

    def __init__(self, inner: MembershipService):
        self._inner = inner
        self.calls: list[str] = []

    def get_public_field_config(self, tenant_id):
        self.calls.append("get_public_field_config")
        return self._inner.get_public_field_config(tenant_id)

    def __getattr__(self, name):
        # Any OTHER attribute access (e.g. a write method the route should never call) is
        # recorded and raises — a read-only route must never reach for one.
        if name.startswith("_"):
            raise AttributeError(name)
        self.__dict__.setdefault("calls", []).append(f"UNEXPECTED:{name}")
        raise AttributeError(f"preview route must not call '{name}' (READ-ONLY, R7.2)")


@pytest.fixture()
def oracle() -> MembershipService:
    return _oracle_service()


@pytest.fixture()
def preview_spy(oracle) -> _PreviewSpy:
    return _PreviewSpy(oracle)


@pytest.fixture()
def inject_preview_service(monkeypatch, preview_spy):
    """Wire the EDGE's preview seam to the spy over the in-memory oracle (no AWS).

    The dispatch resolves the preview service via ``_dispatch.get_application_preview_service``
    (production delegates to ``app.build_application_preview_service`` over a body-overlay
    provider). Patch THAT accessor so the route reaches the spy — the overlay body still flows
    through the route, but the service is our in-memory parity oracle instead of a
    DynamoDB-backed build. Returns the spy so a test can assert the call ledger."""
    monkeypatch.setattr(
        dispatch_mod,
        "get_application_preview_service",
        lambda overlay_provider: preview_spy,
    )
    return preview_spy


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
    """A verified API-GW-authorizer ``POST /members/application-preview`` event.

    ``capabilities`` drives the ``members:admin`` gate; ``with_auth=False`` omits the authorizer
    context entirely (the no-token 401 case). ``body`` is the WORKING ``field_overlay`` the
    builder would debounce to the route."""
    event = {
        "httpMethod": "POST",
        "path": "/members/application-preview",
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


def _working_overlay():
    """A plausible WORKING field_overlay body (what the builder debounces, R7.2).

    The injected oracle serves its OWN overlay, so this body's exact content does not change
    the parity assertion — it exists so the route parses a real body on its way to the (patched)
    service, exercising the wire path end to end."""
    return {
        "fields": {"nickname": {"key": "nickname", "type": "string"}},
        "fixed_overrides": {},
        "functional_groups": [],
    }


# ── Filter parity: route returns get_public_field_config's schema (R7.2 / R9.2) ───────


def test_preview_returns_get_public_field_config_parity(inject_preview_service, oracle):
    # The route's 200 `data` is EXACTLY what the server's get_public_field_config produces for
    # the equivalent saved config — the one filtering authority, no client-side mirror to drift
    # (correctness property 4). The oracle is the SAME service the public field-config read uses.
    resp = app.handler(_event(body=_working_overlay()))
    assert resp["statusCode"] == 200
    env = _envelope(resp)
    assert env["success"] is True
    # Byte-for-byte parity with the public read's schema (filter parity, R7.2 / R9.2).
    assert env["data"] == oracle.get_public_field_config(_TENANT)


def test_preview_parity_matches_the_public_application_service_facade(
    inject_preview_service, oracle
):
    # The public form reads through the ApplicationService facade (which only ADDS the
    # send-ready gate — spec 10). For a send-ready tenant the facade returns the SAME schema the
    # engine does, so the admin preview equals what a public applicant would get (R7 intent).
    # Supply a send-ready provider so the facade passes through (the default is fail-closed).
    facade = ApplicationService(
        oracle,
        mail_readiness_provider=StaticMailReadinessProvider({_TENANT: (True, "h-dcn.nl")}),
    )
    resp = app.handler(_event(body=_working_overlay()))
    assert resp["statusCode"] == 200
    assert _envelope(resp)["data"] == facade.get_public_field_config(_TENANT)


def test_preview_schema_exposes_only_application_visible_fields(inject_preview_service):
    # A spot-check on the returned contract: the preview shows ONLY the fields put on the form
    # (last_name is in the resolved config but not application_visible → absent), proving the
    # route really ran the public FILTER and did not echo the raw overlay back.
    resp = app.handler(_event(body=_working_overlay()))
    assert resp["statusCode"] == 200
    keys = {f["key"] for f in _envelope(resp)["data"]["fields"]}
    assert keys == {"first_name", "email", "membership_type", "shirt_size", "nickname"}
    assert "last_name" not in keys


# ── members:admin-gated (R9.2) ────────────────────────────────────────────────────────


def test_preview_no_token_returns_401_and_never_reaches_the_service(preview_spy, monkeypatch):
    # No authorizer context → the edge cannot authenticate → 401 BEFORE the preview runs. We
    # still wire the spy so we can prove it was never called (the schema was never produced).
    monkeypatch.setattr(
        dispatch_mod, "get_application_preview_service", lambda overlay_provider: preview_spy
    )
    resp = app.handler(_event(body=_working_overlay(), with_auth=False))
    assert resp["statusCode"] == 401
    assert preview_spy.calls == []  # auth failed before the preview path


def test_preview_non_admin_returns_403_and_never_reaches_the_service(preview_spy, monkeypatch):
    # A verified caller holding members:write (NOT members:admin) for the tenant → the route's
    # members:admin gate denies with 403, and the preview service is NEVER reached (R9.2).
    monkeypatch.setattr(
        dispatch_mod, "get_application_preview_service", lambda overlay_provider: preview_spy
    )
    resp = app.handler(
        _event(capabilities=("members:write", "members:read"), body=_working_overlay())
    )
    assert resp["statusCode"] == 403
    assert preview_spy.calls == []


def test_preview_tenant_not_in_entitlement_returns_403(preview_spy, monkeypatch):
    # The token entitles a DIFFERENT tenant with no members:admin for the active one → 403,
    # preview never reached.
    monkeypatch.setattr(
        dispatch_mod, "get_application_preview_service", lambda overlay_provider: preview_spy
    )
    resp = app.handler(
        _event(tenant="other-tenant", capabilities=("members:read",), body=_working_overlay())
    )
    assert resp["statusCode"] == 403
    assert preview_spy.calls == []


# ── READ-ONLY: the route NEVER writes / mutates (R7.2 / R9.2) ─────────────────────────


def test_preview_success_calls_only_get_public_field_config_no_write(inject_preview_service):
    # READ-ONLY by construction: the ONLY method the route invokes on the preview service is
    # get_public_field_config — no put/write/mutation of any kind (any other call would be
    # recorded as UNEXPECTED and raise). This is the no-DynamoDB-mutation guarantee (design §5.3).
    spy = inject_preview_service
    resp = app.handler(_event(body=_working_overlay()))
    assert resp["statusCode"] == 200
    assert spy.calls == ["get_public_field_config"]


def test_preview_tenant_resolved_from_token_not_body(inject_preview_service):
    # Verify-before-trust: a rogue body tenant_id can never redirect the preview — the route
    # reads the VERIFIED tenant (h-dcn) and the oracle only answers for h-dcn, so a mismatched
    # body tenant cannot make it read another tenant's config. The 200 parity holds for h-dcn.
    body = _working_overlay()
    body["tenant_id"] = "evil-tenant"
    resp = app.handler(_event(tenant=_TENANT, body=body))
    assert resp["statusCode"] == 200
    # The schema answered is h-dcn's (the verified tenant), not the rogue body tenant's.
    assert _envelope(resp)["data"]["tenant_id"] == _TENANT
