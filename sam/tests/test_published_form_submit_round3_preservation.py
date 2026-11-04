"""
Bugfix spec `bugfix-published-form-submit` - Round 3, Task 10: the PRESERVATION property tests.

Property 6 (Preservation, Round 3). Observation-first: every assertion was OBSERVED on the CURRENT
(pre-Round-3-fix) code and MUST PASS NOW. The Round-3 fix (tasks 11.x) wires the production consent
provider, applies slug-host CORS on 422/500, adds a script fallback and persists publish state; it
must NOT change:

  * R9.1 - consent gate (`accepted is True`) and stamp shape `{version, accepted_at, locale}`;
  * R9.2 - CORS fail-closed for a FOREIGN origin on the 422 and 500 branches (never echoed, never
           `*`); the abuse-guard 400 and unknown-route 404 branches keep today's behaviour;
  * R9.3 - a notice-less tenant renders no consent control (byte-stable golden);
  * R9.4 - publish result shape and the `{slug}/index.html` + `{slug}/form.json` writes.

Deliberately NOT asserted: that the resolved slug host is dropped on 422/500 (that is the bug task
11.2 flips). Round-2 assertions are reused via import, not duplicated.

Validates (bugfix): Requirements 9.1, 9.2, 9.3, 9.4
"""

from __future__ import annotations

import json
import os
import sys
from contextlib import contextmanager

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
_BACKEND_SRC = os.path.join(_REPO_ROOT, "backend", "src")
if _BACKEND_SRC not in sys.path:
    sys.path.insert(0, _BACKEND_SRC)

from sam.members.domain._membership_errors import MemberValidationError  # noqa: E402
from sam.members.domain.application_form_render import (  # noqa: E402
    render_application_form_page,
)
from sam.members.domain.application_publish import (  # noqa: E402
    PUBLIC_API_BASE_ENV_VAR,
    ApplicationPublishService,
)
from sam.members.domain.application_readiness import (  # noqa: E402
    StaticMailReadinessProvider,
)
from sam.members.domain.membership_service import MembershipService  # noqa: E402
from sam.members.handler import public_app  # noqa: E402
from sam.members.repository.slug_marker_store import SlugMarker  # noqa: E402

# Reuse sibling fakes/helpers (no duplication of the Round-2 assertions).
from sam.tests.test_application_publish_dispatch import (  # noqa: E402
    FakeFieldConfigReader,
    FakeSlugReader as _PublishSlugReader,
)
from sam.tests.test_page_shell_parity import (  # noqa: E402
    _read_fixture,
    _render_canonical_page,
)
from sam.tests.test_public_app_edge import (  # noqa: E402
    _FakeApplicationService,
    _proxy_event,
)
from sam.tests.test_published_form_submit_round2_bug_condition import (  # noqa: E402
    _FakeEmbedOriginReader,
    _FakeSlugReader,
)
from sam.tests.test_published_form_submit_round2_preservation import (  # noqa: E402
    _TENANT as _R2_TENANT,
    _service as _consent_service,
    _submission,
)

_SLUG = "hdcn-aanmelden"
_TENANT_ID = "h-dcn-tenant"
_BASELINE = "https://aanmelden-test.jabaki.nl"
_APPLICATIONS = f"/public/members/{_SLUG}/applications"


# ══════════════════════════════════════════════════════════════════════════════════════
# R9.1 - consent gate + stamp unchanged
# ══════════════════════════════════════════════════════════════════════════════════════


@settings(max_examples=40)
@given(
    accepted=st.one_of(
        st.booleans(),
        st.sampled_from(["true", "1", "yes", ""]),
        st.integers(min_value=0, max_value=3),
        st.none(),
    )
)
def test_preserve_gate_true_only_for_accepted_is_true(accepted):
    """R9.1: `_consent_is_affirmative` is true only for `accepted is True`."""
    assert MembershipService._consent_is_affirmative({"accepted": accepted}) is (
        accepted is True
    )


def test_preserve_stamp_keys_and_server_resolved_version():
    """R9.1: the stamp is exactly {version, accepted_at, locale}; version is server-resolved."""
    svc = _consent_service(consent_version="2026-01-notice")
    rec = svc.create_application(
        _R2_TENANT,
        _submission(),
        session_key="s1",
        consent={"accepted": True, "notice_version": "client-spoofed"},
    )
    assert set(rec["consent"].keys()) == {"version", "accepted_at", "locale"}
    assert rec["consent"]["version"] == "2026-01-notice"


# ══════════════════════════════════════════════════════════════════════════════════════
# R9.2 - CORS fail-closed on the 422 / 500 error branches (+ 400 / 404 unchanged)
# ══════════════════════════════════════════════════════════════════════════════════════


class _GenericFailureService(_FakeApplicationService):
    """Ready service whose submit raises an unexpected (non-validation) error -> 500 branch."""

    def create_application(self, *args, **kwargs):
        raise RuntimeError("boom")


@contextmanager
def _edge(service):
    """Run the REAL `public_app.handler` over fake marker store / embed reader / service."""
    mp = pytest.MonkeyPatch()
    try:
        mp.setenv(public_app.ALLOWED_ORIGINS_ENV, _BASELINE)
        mp.setattr(
            public_app,
            "S3SlugMarkerStore",
            lambda *a, **k: _FakeSlugReader(
                {_SLUG: _TENANT_ID},
                {
                    _SLUG: SlugMarker(
                        owner_plane="sam",
                        kind="application_form",
                        tenant_id=_TENANT_ID,
                        resource_ref="config#fields",
                    )
                },
            ),
        )
        mp.setattr(
            public_app, "MembersProjectionReader", lambda *a, **k: _FakeEmbedOriginReader({})
        )
        mp.setattr(public_app, "_application_service", lambda: service)
        yield
    finally:
        mp.undo()


def _ready_service(cls=_FakeApplicationService):
    from sam.tests.test_public_app_edge import _whitelisted_schema

    return cls(ready_tenants={_TENANT_ID: _whitelisted_schema(_TENANT_ID)})


def _post(origin, body):
    return public_app.handler(
        _proxy_event("POST", _APPLICATIONS, body=body, headers={"Origin": origin})
    )


def _acao(resp):
    return resp.get("headers", {}).get("Access-Control-Allow-Origin")


_INVALID_BODY = {"fields": {"email": "not-an-email"}}
_VALID_BODY = {"fields": {"email": "a@b.nl"}}


@pytest.mark.parametrize(
    "service_cls, body, status",
    [
        (_FakeApplicationService, _INVALID_BODY, 422),  # MemberValidationError
        (_GenericFailureService, _VALID_BODY, 500),  # generic Exception
    ],
)
def test_preserve_foreign_jabaki_origin_not_echoed_on_422_and_500(
    service_cls, body, status
):
    with _edge(_ready_service(service_cls)):
        resp = _post("https://evil.jabaki.nl", body)
    assert resp["statusCode"] == status
    acao = _acao(resp)
    assert acao is None or acao == _BASELINE  # never echoed
    assert acao != "*"
    assert acao != "https://evil.jabaki.nl"


@settings(max_examples=40, deadline=None)
@given(
    sub=st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789-", min_size=1, max_size=12).filter(
        lambda s: s != _SLUG and s != "aanmelden-test"
    ),
    apex=st.sampled_from(["jabaki.nl", "example.com", "evil.net"]),
    failing=st.booleans(),
)
def test_preserve_random_foreign_origin_never_echoed_nor_wildcard_on_errors(
    sub, apex, failing
):
    """R9.2: any foreign origin is never echoed / never `*` on the 422 and 500 branches."""
    origin = f"https://{sub}.{apex}"
    cls, body = (
        (_GenericFailureService, _VALID_BODY) if failing else (_FakeApplicationService, _INVALID_BODY)
    )
    with _edge(_ready_service(cls)):
        resp = _post(origin, body)
    assert resp["statusCode"] == (500 if failing else 422)
    acao = _acao(resp)
    assert acao != "*"
    assert acao != origin


def test_preserve_422_actually_raises_member_validation_error_path():
    # Guard the observation: the 422 above is the MemberValidationError branch, not something else.
    svc = _ready_service()
    with pytest.raises(MemberValidationError):
        svc.create_application(_TENANT_ID, _INVALID_BODY, "s1")


def test_preserve_abuse_guard_400_keeps_current_cors_behaviour():
    honeypot = {"fields": {"email": "a@b.nl"}, "website": "spam"}
    with _edge(_ready_service()):
        foreign = _post("https://evil.jabaki.nl", honeypot)
        baseline = _post(_BASELINE, honeypot)
    assert foreign["statusCode"] == 400 and baseline["statusCode"] == 400
    assert _acao(foreign) is None
    assert _acao(baseline) == _BASELINE  # static baseline echoed exactly


def test_preserve_unknown_route_404_keeps_current_cors_behaviour():
    def get(origin):
        return public_app.handler(
            _proxy_event("GET", "/public/members/nope/unknown", headers={"Origin": origin})
        )

    with _edge(_ready_service()):
        foreign = get("https://evil.jabaki.nl")
        baseline = get(_BASELINE)
    assert foreign["statusCode"] == 404 and baseline["statusCode"] == 404
    assert _acao(foreign) is None
    assert _acao(baseline) == _BASELINE


# ══════════════════════════════════════════════════════════════════════════════════════
# R9.3 - notice-less render unchanged
# ══════════════════════════════════════════════════════════════════════════════════════


def test_preserve_notice_less_render_is_byte_stable_golden():
    # The canonical config carries notice.version = None -> byte-identical to the committed golden.
    assert _render_canonical_page() == _read_fixture()


@settings(max_examples=40)
@given(
    notice=st.one_of(
        st.just(None),
        st.just({}),
        st.just({"version": None}),
        st.just({"version": "   "}),
        st.just({"version": None, "text": {"nl": "tekst"}}),
    ),
    locales=st.sampled_from([["nl"], ["nl", "en"]]),
)
def test_preserve_notice_less_config_renders_no_consent_control(notice, locales):
    config = {
        "tenant_id": "h-dcn",
        "fields": [
            {"key": "email", "type": "email", "label": {"nl": "E-mail"}, "required": True}
        ],
        "functional_groups": [],
        "locales": locales,
    }
    if notice is not None:
        config["notice"] = notice
    html = render_application_form_page(
        config,
        head_meta={"title": "t"},
        slug=_SLUG,
        public_api_base="https://api.test.example",
    )
    markup = html.split("<script", 1)[0]
    assert 'data-field="consent"' not in markup
    assert 'name="consent"' not in markup
    assert "data-notice-version" not in markup


# ══════════════════════════════════════════════════════════════════════════════════════
# R9.4 - publish result shape + artifact writes unchanged
# ══════════════════════════════════════════════════════════════════════════════════════


class _RecordingWriter:
    def __init__(self):
        self.calls = []

    def publish_artifacts(self, slug, *, index_html, form_json):
        self.calls.append((slug, index_html, form_json))


def test_preserve_publish_result_shape_and_artifact_writes(monkeypatch):
    monkeypatch.setenv(PUBLIC_API_BASE_ENV_VAR, "https://api.jabaki.nl")
    writer = _RecordingWriter()
    svc = ApplicationPublishService(
        slug_reader=_PublishSlugReader("hdcn-application-form"),
        readiness_provider=StaticMailReadinessProvider({"h-dcn": (True, "h-dcn.nl")}),
        field_config_reader=FakeFieldConfigReader(1),
        artifact_writer=writer,
    )
    result = svc.publish("h-dcn")

    assert set(result.keys()) == {"success", "slug", "published_version", "published_at"}
    assert result["success"] is True
    assert result["slug"] == "hdcn-application-form"
    assert isinstance(result["published_version"], int)
    assert isinstance(result["published_at"], str) and result["published_at"]

    # Exactly one writer call carries {slug}/index.html + {slug}/form.json (the writer owns keys).
    assert len(writer.calls) == 1
    slug, index_html, form_json = writer.calls[0]
    assert slug == "hdcn-application-form"
    assert index_html.startswith("<!DOCTYPE html>")
    assert isinstance(form_json, bytes)
    assert json.loads(form_json.decode("utf-8"))["tenant_id"] == "h-dcn"
