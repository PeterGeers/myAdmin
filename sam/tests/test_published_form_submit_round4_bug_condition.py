"""
Bugfix spec `bugfix-published-form-submit` — Round 4, Task 13: the bug-condition EXPLORATION test.

Branch: `bugfix/published-form-submit-round4`. Property 7 (Round-4 Bug Condition).

This test ENCODES THE EXPECTED (Round-4-fixed) behaviour, so on the CURRENT code it MUST FAIL — each
failure is the counterexample proving the bug. After the fix (tasks 15.x) the SAME assertions PASS
unchanged. DO NOT fix the test or the code when it fails.

Facets:
  * IAM               — `MembersPublicFunction` must not grant `s3:GetObject` under an `s3:prefix`
                        Condition (GetObject requests carry no `s3:prefix`, so the condition is false
                        -> live AccessDenied on `_slugs/{slug}`), and GetObject on `_slugs/*` must be
                        granted by an UNCONDITIONED statement.
  * PREFLIGHT_ROUTE   — explicit `Method: OPTIONS` events on both public paths, and no static `Cors`
                        on `MembersPublicApi` (the SAM mock responder cannot echo the per-slug host).
  * PREFLIGHT_HANDLER — the real `public_app.handler` must answer OPTIONS from the form's own slug host
                        with 200/204, ACAO == origin (never `*`), and allow methods/headers.

Validates (bugfix): Requirements 10.1, 10.2, 11.1, 11.2, 11.3 (Round 4 exploration)
"""

from __future__ import annotations

import os
import sys

import yaml

_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
_BACKEND_SRC = os.path.join(_REPO_ROOT, "backend", "src")
if _BACKEND_SRC not in sys.path:
    sys.path.insert(0, _BACKEND_SRC)

from sam.members.handler import public_app  # noqa: E402
from sam.members.repository.slug_marker_store import SlugMarker  # noqa: E402
from sam.tests.test_public_api_stack_contract import (  # noqa: E402
    _TEMPLATE_PATH,
    _CfnLoader,
    _CfnTag,
)
from sam.tests.test_published_form_submit_round3_bug_condition import (  # noqa: E402
    _FakeEmbedOriginReader,
    _FakeSlugReader,
)

_SLUG = "hdcn-aanmelden"
_TENANT = "h-dcn"
_ORIGIN = "https://hdcn-aanmelden.jabaki.nl"
_BASELINE = "https://aanmelden-test.jabaki.nl"
_SLUG_OBJECTS_ARN = "arn:aws:s3:::${LandingPagesBucket}/_slugs/*"
_PUBLIC_PATHS = (
    "/public/members/{tenant_slug}/field-config",
    "/public/members/{tenant_slug}/applications",
)


def _template() -> dict:
    with open(_TEMPLATE_PATH, "rb") as fh:
        return yaml.load(fh, Loader=_CfnLoader)


def _public_fn_props() -> dict:
    return _template()["Resources"]["MembersPublicFunction"]["Properties"]


def _statements() -> list[dict]:
    out: list[dict] = []
    for policy in _public_fn_props()["Policies"]:
        if isinstance(policy, dict):
            stmts = policy.get("Statement", [])
            out.extend(stmts if isinstance(stmts, list) else [stmts])
    return out


def _as_list(value) -> list:
    return value if isinstance(value, list) else [value]


def _has_action(stmt: dict, action: str) -> bool:
    return action in _as_list(stmt.get("Action", []))


def _resource_strings(stmt: dict) -> list[str]:
    res = []
    for r in _as_list(stmt.get("Resource", [])):
        res.append(r.value if isinstance(r, _CfnTag) and r.tag == "Sub" else r)
    return res


def _condition_mentions_prefix(stmt: dict) -> bool:
    return "s3:prefix" in repr(stmt.get("Condition", {}))


# ── IAM ────────────────────────────────────────────────────────────────────────────────


def test_iam_getobject_is_not_under_an_s3_prefix_condition_and_slug_objects_unconditioned():
    """IAM facet. CURRENT: one statement combines GetObject + ListBucket under `s3:prefix` -> FAILS."""
    stmts = _statements()

    offenders = [
        s.get("Sid")
        for s in stmts
        if _has_action(s, "s3:GetObject") and _condition_mentions_prefix(s)
    ]
    assert not offenders, (
        "BUG (IAM facet): statement(s) "
        f"{offenders!r} grant s3:GetObject under a Condition on s3:prefix. GetObject requests carry "
        "no s3:prefix key, so the condition is false and the grant never applies (live: CloudWatch "
        "AccessDenied s3:GetObject on .../_slugs/hdcn-aanmelden -> 500)."
    )

    unconditioned = [
        s
        for s in stmts
        if _has_action(s, "s3:GetObject")
        and "Condition" not in s
        and _SLUG_OBJECTS_ARN in _resource_strings(s)
    ]
    assert unconditioned, (
        "BUG (IAM facet): no UNCONDITIONED statement grants s3:GetObject on "
        f"{_SLUG_OBJECTS_ARN!r}."
    )


# ── PREFLIGHT_ROUTE ────────────────────────────────────────────────────────────────────


def test_preflight_route_options_events_exist_and_no_static_cors():
    """PREFLIGHT_ROUTE facet. CURRENT: no OPTIONS events; static `Cors` block present -> FAILS."""
    tpl = _template()
    events = _public_fn_props().get("Events", {})
    options_paths = {
        ev["Properties"]["Path"]
        for ev in events.values()
        if str(ev["Properties"].get("Method", "")).lower() == "options"
        and isinstance(ev["Properties"].get("RestApiId"), _CfnTag)
        and ev["Properties"]["RestApiId"].value == "MembersPublicApi"
    }
    missing = [p for p in _PUBLIC_PATHS if p not in options_paths]
    assert not missing, (
        "BUG (PREFLIGHT_ROUTE facet): MembersPublicFunction has no Method: OPTIONS event on "
        f"{missing!r} (OPTIONS paths found: {sorted(options_paths)!r}). Live: curl OPTIONS returns "
        "an EMPTY Access-Control-Allow-Origin from API Gateway's static mock responder."
    )

    cors = tpl["Resources"]["MembersPublicApi"]["Properties"].get("Cors")
    assert cors is None or "AllowOrigin" not in cors, (
        "BUG (PREFLIGHT_ROUTE facet): MembersPublicApi still declares a static Cors AllowOrigin "
        f"({cors!r}); SAM generates a mock OPTIONS responder that can never echo the per-slug host."
    )


# ── PREFLIGHT_HANDLER ──────────────────────────────────────────────────────────────────


def test_preflight_handler_echoes_form_origin_with_allow_methods_and_headers(
    monkeypatch,
):
    """PREFLIGHT_HANDLER facet. CURRENT: the Lambda does not handle OPTIONS -> FAILS."""
    monkeypatch.setenv(public_app.ALLOWED_ORIGINS_ENV, _BASELINE)
    monkeypatch.delenv(public_app.APEX_ENV, raising=False)
    monkeypatch.setattr(
        public_app,
        "S3SlugMarkerStore",
        lambda *a, **k: _FakeSlugReader(
            {_SLUG: _TENANT},
            {
                _SLUG: SlugMarker(
                    owner_plane="sam",
                    kind="application_form",
                    tenant_id=_TENANT,
                    resource_ref="config#fields",
                )
            },
        ),
    )
    monkeypatch.setattr(
        public_app, "MembersProjectionReader", lambda *a, **k: _FakeEmbedOriginReader()
    )

    resp = public_app.handler(
        {
            "httpMethod": "OPTIONS",
            "path": f"/public/members/{_SLUG}/applications",
            "headers": {
                "Origin": _ORIGIN,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
            "queryStringParameters": None,
            "body": None,
            "isBase64Encoded": False,
        }
    )

    headers = {k.lower(): v for k, v in (resp.get("headers") or {}).items()}
    assert resp["statusCode"] in (200, 204), (
        f"BUG (PREFLIGHT_HANDLER facet): OPTIONS not answered as a preflight: status "
        f"{resp['statusCode']!r}, headers={headers!r}."
    )
    acao = headers.get("access-control-allow-origin")
    assert acao == _ORIGIN and acao != "*", (
        f"BUG (PREFLIGHT_HANDLER facet): ACAO={acao!r}, expected {_ORIGIN!r} (never '*')."
    )
    assert "post" in headers.get("access-control-allow-methods", "").lower(), (
        f"Allow-Methods lacks POST: {headers.get('access-control-allow-methods')!r}"
    )
    assert "content-type" in headers.get("access-control-allow-headers", "").lower(), (
        f"Allow-Headers lacks Content-Type: {headers.get('access-control-allow-headers')!r}"
    )
