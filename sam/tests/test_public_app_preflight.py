"""Round 4 (task 15.2): `public_app.handler` answers CORS preflight (OPTIONS) per origin.

Runs the REAL handler over fake slug-marker store / embed-origin reader (no AWS). Fail-closed:
ACAO is echoed only for an allowed origin; never `*`; abuse guards do not apply to OPTIONS.
"""

from __future__ import annotations

import pytest

from sam.members.handler import public_app
from sam.members.repository.slug_marker_store import SlugMarker
from sam.tests.test_published_form_submit_round2_bug_condition import (
    _FakeEmbedOriginReader,
    _FakeSlugReader,
)

_SLUG = "hdcn-aanmelden"
_TENANT = "h-dcn"
_SLUG_HOST = "https://hdcn-aanmelden.jabaki.nl"
_BASELINE = "https://aanmelden-test.jabaki.nl"
_APEX = "jabaki.nl"


@pytest.fixture(autouse=True)
def _edge(monkeypatch):
    monkeypatch.setenv(public_app.ALLOWED_ORIGINS_ENV, _BASELINE)
    monkeypatch.setenv(public_app.APEX_ENV, _APEX)
    marker = SlugMarker(
        owner_plane="sam",
        kind="application_form",
        tenant_id=_TENANT,
        resource_ref="config#fields",
    )
    monkeypatch.setattr(
        public_app,
        "S3SlugMarkerStore",
        lambda *a, **k: _FakeSlugReader({_SLUG: _TENANT}, {_SLUG: marker}),
    )
    monkeypatch.setattr(
        public_app, "MembersProjectionReader", lambda *a, **k: _FakeEmbedOriginReader()
    )


def _options(
    path_slug: str, origin: str | None, action: str = "applications", body=None
):
    headers = {"Access-Control-Request-Method": "POST"}
    if origin:
        headers["Origin"] = origin
    return public_app.handler(
        {
            "httpMethod": "OPTIONS",
            "path": f"/public/members/{path_slug}/{action}",
            "headers": headers,
            "body": body,
        }
    )


def _h(resp):
    return {k.lower(): v for k, v in resp["headers"].items()}


@pytest.mark.parametrize("action", ["applications", "field-config"])
def test_options_resolved_slug_host_is_echoed_with_preflight_headers(action):
    resp = _options(_SLUG, _SLUG_HOST, action)
    h = _h(resp)
    assert resp["statusCode"] == 204
    assert h["access-control-allow-origin"] == _SLUG_HOST
    assert h["access-control-allow-methods"] == "GET,POST,OPTIONS"
    assert h["access-control-allow-headers"] == "Content-Type"
    assert h["access-control-max-age"] == "600"
    assert h["vary"] == "Origin"


def test_options_baseline_origin_is_echoed():
    h = _h(_options(_SLUG, _BASELINE))
    assert h["access-control-allow-origin"] == _BASELINE


def test_options_foreign_origin_gets_no_acao():
    resp = _options(_SLUG, "https://evil.example")
    assert "access-control-allow-origin" not in _h(resp)
    assert resp["statusCode"] == 204


def test_options_unresolved_slug_gets_no_acao_for_slug_host():
    resp = _options("nope", "https://nope.jabaki.nl")
    assert "access-control-allow-origin" not in _h(resp)


def test_options_without_origin_gets_no_acao():
    assert "access-control-allow-origin" not in _h(_options(_SLUG, None))


def test_options_unknown_route_gets_no_acao():
    resp = public_app.handler(
        {
            "httpMethod": "OPTIONS",
            "path": "/public/other",
            "headers": {"Origin": _SLUG_HOST},
        }
    )
    assert "access-control-allow-origin" not in _h(resp)


def test_options_resolution_error_fails_closed_without_leak(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("secret-internal-detail")

    monkeypatch.setattr(public_app, "S3SlugMarkerStore", boom)
    resp = _options(_SLUG, _SLUG_HOST)
    assert "access-control-allow-origin" not in _h(resp)
    assert "secret-internal-detail" not in str(resp)


def test_options_never_returns_wildcard():
    for origin in (_SLUG_HOST, "https://evil.example", None):
        assert _h(_options(_SLUG, origin)).get("access-control-allow-origin") != "*"


def test_options_bypasses_honeypot_and_payload_guards():
    resp = _options(_SLUG, _SLUG_HOST, body='{"website": "spam"}')
    assert resp["statusCode"] == 204
    assert _h(resp)["access-control-allow-origin"] == _SLUG_HOST
