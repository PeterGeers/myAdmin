"""
Bugfix spec `bugfix-published-form-submit` — Round 3, Task 9: the bug-condition EXPLORATION test.

Bugfix spec: `.kiro/specs/Members/14 .../bugfix-published-form-submit` (design.md "Round 3").
Branch: `bugfix/published-form-submit-round3`.

WHAT THIS TEST IS
-----------------
The EXPLORATION test for Property 5 (Round-3 Bug Condition). Round 2 deployed, yet TEST is still a
dead end for the applicant. This test ENCODES THE EXPECTED (Round-3-fixed) behaviour across the four
confirmed facets of `isBugConditionR3`, so on the CURRENT code it MUST FAIL — each failure is the
counterexample proving the Round-3 bug exists. After the Round-3 fix (tasks 11.x) the SAME assertions
PASS unchanged. DO NOT fix the test or the code when it fails.

  * WIRING        — the REAL production service `app._get_membership_service()` must expose the
                    tenant's `config#mail` consent notice `{version, text}` through
                    `get_public_field_config`. (Defect 1 — no `consent_notice_provider` is passed
                    to `MembershipService(...)`, so the empty `StaticConsentNoticeProvider` wins.)
  * CORS_ERROR    — the REAL `public_app.handler` must echo `Access-Control-Allow-Origin` on the 422
                    (`MemberValidationError`) for the form's own slug host. (Defect 2 — the 422
                    branch calls `_apply_cors_origin(..)` with no tenant/slug, so the header drops.)
  * FALLBACK      — the rendered submit script must route a 422 entry whose target element is
                    missing to the form-level message area. (Defect 3 — `showFieldError` returns
                    silently when no wrapper is found, so the message is dropped.)
  * PUBLISH_STATE — after a successful publish the stored `config#fields` row must carry
                    `published_version` / `published_at`, and a second publish yields version 2.
                    (Defect 4 — publish computes the values but never persists them.)

WHY THE EARLIER TESTS MISSED IT (steering 39 — prove against the real shape)
-------------------------------------------------------------------------
Round 1/2 tests injected a consent provider straight into `MembershipService`, so they never
exercised the production composition root. The WIRING facet therefore builds the service via
`app._get_membership_service()` itself and patches ONLY the reader seam
(`app._new_projection_reader` -> a real `MembersProjectionReader` over an in-memory table that holds
a real h-dcn-shaped `config#mail` row). It never injects a consent provider into the service.

CONCRETE FALLBACK MARKER (so task 11.3 can satisfy it, and this test can check it)
---------------------------------------------------------------------------------
In the embedded submit script, the `showFieldError(name, message)` function's "no wrapper found"
branch (`if (!wrap) { ... }`) MUST NOT be a bare `return;`. It must route the message to the
form-level message area — i.e. that branch must reference the form-level status element
(`status`, the `.form-status` node) or call `neutral(`. The test extracts the `if (!wrap) { ... }`
block inside `showFieldError` and asserts it contains one of those two tokens. The artifact is
rendered for a config WITHOUT a notice so there is no `[data-field="consent"]` target at all.

PUBLISH_STATE SEAM NOTE
-----------------------
`_build_publish_service` is the single place that wires the publish service to the fake
`config#fields` store. Today `ApplicationPublishService` has no persistence collaborator, so nothing
can write to the store; task 11.4 adds one (mirroring `set_form_slug`) and adapts ONLY this helper.
The assertions stay as written.

Validates (bugfix): Requirements 7.1, 7.2, 7.3, 7.4 (Round 3 exploration)
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import sys
from html.parser import HTMLParser

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
_BACKEND_SRC = os.path.join(_REPO_ROOT, "backend", "src")
if _BACKEND_SRC not in sys.path:
    sys.path.insert(0, _BACKEND_SRC)

from services import projection_schema as schema  # noqa: E402

from sam.members.domain._membership_errors import MemberValidationError  # noqa: E402
from sam.members.handler import app, public_app  # noqa: E402
from sam.members.repository.projection_config_reader import (  # noqa: E402
    MembersProjectionReader,
)
from sam.members.repository.slug_marker_store import SlugMarker  # noqa: E402

_SLUG = "hdcn-aanmelden"
_APEX = "jabaki.nl"
_CANONICAL_HOST = "https://aanmelden-test.jabaki.nl"
_TENANT = "h-dcn"


# ══════════════════════════════════════════════════════════════════════════════════════
# FACET: WIRING — Defect 1 / isBugConditionR3(facet=WIRING)
# ══════════════════════════════════════════════════════════════════════════════════════


class _FakeTable:
    """In-memory stand-in for a boto3 DynamoDB Table (query side) — same as the Round-2 sibling."""

    def __init__(self):
        self.store: dict[tuple, dict] = {}

    def put(self, item: dict) -> None:
        key = (item[schema.PARTITION_KEY_ATTR], item[schema.SORT_KEY_ATTR])
        self.store[key] = dict(item)

    def query(self, KeyConditionExpression=None):
        expr = KeyConditionExpression.get_expression()
        tenant_id = expr["values"][1]
        items = [dict(v) for k, v in self.store.items() if k[0] == tenant_id]
        return {"Items": items}


def _hdcn_config_mail_row(version: str, text: dict) -> dict:
    """A real h-dcn-shaped `config#mail` row (the shape `build_config_mail_row` produces)."""
    return {
        schema.PARTITION_KEY_ATTR: _TENANT,
        schema.SORT_KEY_ATTR: schema.build_sort_key(schema.RECORD_TYPE_CONFIG, "mail"),
        "mail_enabled": True,
        "consent_notice": {"version": version, "text": dict(text)},
        schema.VERSION_ATTR: 1,
    }


@contextlib.contextmanager
def _production_service_over(table):
    """Build the REAL production service and patch ONLY the reader seam.

    Resets the `_SERVICE` singleton before AND after, and swaps `app._new_projection_reader` for a
    real `MembersProjectionReader` over `table`. No consent provider is injected into the service.
    """
    saved_service = app._SERVICE
    saved_reader_factory = app._new_projection_reader
    app._SERVICE = None
    app._new_projection_reader = lambda: MembersProjectionReader(table=table)
    try:
        yield app._get_membership_service()
    finally:
        app._SERVICE = saved_service
        app._new_projection_reader = saved_reader_factory


_NOTICE_VERSION = st.sampled_from(["2026-01", "2", "notice-7"])
_NOTICE_TEXT = st.fixed_dictionaries(
    {
        "nl": st.sampled_from(["Ik ga akkoord met de privacyverklaring.", "Akkoord."]),
        "en": st.sampled_from(["I accept the privacy notice.", "Agreed."]),
    }
)


@settings(max_examples=6, deadline=None)
@given(version=_NOTICE_VERSION, text=_NOTICE_TEXT)
def test_wiring_production_service_exposes_tenant_consent_notice(version, text):
    """WIRING facet: `app._get_membership_service()` must serve the tenant's `{version, text}`.

    CURRENT: no provider is wired at the composition root -> version None, no text -> FAILS.

    Validates (bugfix): Requirement 8.1
    """
    table = _FakeTable()
    table.put(_hdcn_config_mail_row(version, text))

    # Precondition (real shape): the notice genuinely lives in SAM and the real reader reads it.
    real = MembersProjectionReader(table=table).get_consent_notice(_TENANT)
    assert real == {"version": version, "text": text}

    with _production_service_over(table) as svc:
        notice = svc.get_public_field_config(_TENANT).get("notice") or {}

    assert notice.get("version") == version and notice.get("text") == text, (
        "BUG (WIRING facet): the production service built by app._get_membership_service() does "
        f"not expose the tenant's consent notice. Expected {{version: {version!r}, text: {text!r}}}, "
        f"served notice={notice!r}. Counterexample: MembershipService(...) is constructed without "
        "consent_notice_provider, so the empty StaticConsentNoticeProvider is used; the published "
        "form shows no consent text and the stamp has no version."
    )


# ══════════════════════════════════════════════════════════════════════════════════════
# FACET: CORS_ERROR — Defect 2 / isBugConditionR3(facet=CORS_ERROR)
# ══════════════════════════════════════════════════════════════════════════════════════


class _FakeSlugReader:
    """Fake `S3SlugMarkerStore`: resolves the published SAM application-form slug to its tenant."""

    def __init__(self, by_slug: dict[str, str], markers: dict[str, SlugMarker]):
        self._by_slug = dict(by_slug)
        self._markers = dict(markers)

    def resolve_slug(self, slug):
        return self._by_slug.get(slug) if isinstance(slug, str) and slug else None

    def resolve(self, slug):
        if not isinstance(slug, str) or not slug:
            return None
        return self._markers.get(slug.strip().lower())


class _FakeEmbedOriginReader:
    """`MembersProjectionReader` stand-in: no tenant embed origins (the Defect-2 case)."""

    def get_application_embed_origins(self, tenant_id):
        return []


class _RaisingApplicationService:
    """`ApplicationService` stand-in whose submit raises the consent `MemberValidationError` (422)."""

    def create_application(
        self, tenant_id, body, session_key, *, locale=None, consent=None
    ):
        raise MemberValidationError({"consent": "Consent is required"})


def _post_event(path: str, origin: str) -> dict:
    return {
        "httpMethod": "POST",
        "path": path,
        "headers": {"Origin": origin, "Content-Type": "application/json"},
        "queryStringParameters": None,
        "body": json.dumps(
            {
                "fields": {"email": "a@b.nl"},
                "locale": "nl",
                "consent": {},
                "website": "",
            }
        ),
        "isBase64Encoded": False,
    }


@settings(
    max_examples=6,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(resolved_slug=st.sampled_from(["hdcn-aanmelden", "form-aanmelden"]))
def test_cors_422_echoes_origin_for_the_resolved_slug_host(resolved_slug, monkeypatch):
    """CORS_ERROR facet: a 422 from the form's own slug host must carry ACAO == that origin.

    CURRENT: the `MemberValidationError` branch passes no tenant/slug to `_apply_cors_origin`, so
    the header is dropped and the browser hides the 422 -> FAILS.

    Validates (bugfix): Requirement 8.2
    """
    tenant_id = f"{resolved_slug}-tenant"
    origin = f"https://{resolved_slug}.{_APEX}"

    monkeypatch.setenv(public_app.ALLOWED_ORIGINS_ENV, _CANONICAL_HOST)
    monkeypatch.delenv(public_app.APEX_ENV, raising=False)
    monkeypatch.setattr(
        public_app,
        "S3SlugMarkerStore",
        lambda *a, **k: _FakeSlugReader(
            {resolved_slug: tenant_id},
            {
                resolved_slug: SlugMarker(
                    owner_plane="sam",
                    kind="application_form",
                    tenant_id=tenant_id,
                    resource_ref="config#fields",
                )
            },
        ),
    )
    monkeypatch.setattr(
        public_app, "MembersProjectionReader", lambda *a, **k: _FakeEmbedOriginReader()
    )
    monkeypatch.setattr(
        public_app, "_application_service", lambda: _RaisingApplicationService()
    )

    resp = public_app.handler(
        _post_event(f"/public/members/{resolved_slug}/applications", origin)
    )

    assert resp["statusCode"] == 422, (
        f"precondition: expected a 422, got {resp['statusCode']}"
    )
    acao = resp.get("headers", {}).get("Access-Control-Allow-Origin")
    assert acao == origin, (
        "BUG (CORS_ERROR facet): the 422 response drops Access-Control-Allow-Origin for the "
        f"form's own slug host. Origin {origin!r} got ACAO={acao!r} (baseline {_CANONICAL_HOST!r}, "
        "no embed origins). Counterexample: the browser blocks reading the 422, so the applicant "
        "sees only the generic failure message."
    )
    assert acao != "*"


# ══════════════════════════════════════════════════════════════════════════════════════
# FACET: FALLBACK — Defect 3 / isBugConditionR3(facet=FALLBACK)
# ══════════════════════════════════════════════════════════════════════════════════════


def _render_without_notice() -> str:
    from sam.members.domain.application_form_render import render_application_form_page

    config = {
        "tenant_id": _TENANT,
        "fields": [
            {
                "key": "email",
                "type": "email",
                "label": {"nl": "E-mail", "en": "Email"},
                "required": True,
            }
        ],
        "functional_groups": [],
        "locales": ["nl", "en"],
        "notice": {"version": None},  # no notice -> no consent control rendered
    }
    return render_application_form_page(
        config,
        head_meta={"title": "Aanmelden", "canonical": f"https://{_SLUG}.{_APEX}/"},
        slug=_SLUG,
        public_api_base="https://api.test.example",
    )


def _no_wrapper_branch(artifact: str) -> str | None:
    """Return the body of the `if (!wrap) { ... }` block inside `showFieldError`, or None."""
    fn = re.search(
        r"function showFieldError\(name, message\) \{(.*?)\n  \}\n", artifact, re.S
    )
    if not fn:
        return None
    branch = re.search(r"if \(!wrap\) \{(.*?)\}", fn.group(1), re.S)
    return branch.group(1) if branch else None


class _StartTagCollector(HTMLParser):
    """Record the attribute dict of every start tag (script bodies are never parsed as tags)."""

    def __init__(self) -> None:
        super().__init__()
        self.tags: list[dict[str, str | None]] = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(dict(attrs))


def test_fallback_unmatched_422_entry_goes_to_the_form_level_message():
    """FALLBACK facet: with no `[data-field="consent"]` target, the script must fall back to the
    form-level message area (marker: the `!wrap` branch references `status` or `neutral(`).

    CURRENT: the branch is a bare `return;` -> the message is dropped silently -> FAILS.

    Validates (bugfix): Requirement 8.3
    """
    artifact = _render_without_notice()

    # Precondition: this really is the no-target case — no rendered consent CONTROL element. The
    # embedded <script> COMMENTS mention `data-field="consent"`; HTMLParser treats script bodies as
    # CDATA, so only real elements' attributes are recorded.
    collector = _StartTagCollector()
    collector.feed(artifact)
    collector.close()
    assert not any(attrs.get("data-field") == "consent" for attrs in collector.tags), (
        "precondition: notice-less render has no consent control"
    )
    assert any(
        "form-status" in (attrs.get("class") or "").split() for attrs in collector.tags
    ), "precondition: the form-level message area exists"

    branch = _no_wrapper_branch(artifact)
    assert branch is not None, "precondition: showFieldError has an `if (!wrap)` branch"

    routes_to_form_level = ("status" in branch) or ("neutral(" in branch)
    assert routes_to_form_level, (
        "BUG (FALLBACK facet): showFieldError's no-target branch drops the message. "
        f"`if (!wrap) {{{branch.strip()}}}` neither writes to the form-level status element nor "
        "calls neutral(). Counterexample: a 422 keyed `consent` on a page without the consent "
        "element shows the applicant nothing."
    )


# ══════════════════════════════════════════════════════════════════════════════════════
# FACET: PUBLISH_STATE — Defect 4 / isBugConditionR3(facet=PUBLISH_STATE)
# ══════════════════════════════════════════════════════════════════════════════════════


class _FakeFieldsStore:
    """In-memory stand-in for the stored `config#fields` row (the publish-state carrier)."""

    def __init__(self):
        self.row: dict = {"tenant_id": _TENANT, "slug": _SLUG}


class _StoreBackedFieldConfigReader:
    """Public field-config view backed by the stored row: it surfaces `published_version` from the
    row exactly as `_next_published_version` reads it, so a persisted value advances the version."""

    def __init__(self, store: _FakeFieldsStore):
        self._store = store

    def get_public_field_config(self, tenant_id):
        view = {
            "tenant_id": tenant_id,
            "fields": [{"key": "email", "type": "email", "label": {"nl": "E-mail"}}],
            "locales": ["nl", "en"],
            "notice": {"version": None},
        }
        if "published_version" in self._store.row:
            view["published_version"] = self._store.row["published_version"]
        return view


class _FakeSlugForwardReader:
    def get_form_slug(self, tenant_id):
        return _SLUG


class _FakeArtifactWriter:
    def __init__(self):
        self.writes = []

    def publish_artifacts(self, slug, *, index_html, form_json):
        self.writes.append(slug)


class _StoreBackedPublishStateWriter:
    """`PublishStateWriter` stand-in that persists onto the fake `_FakeFieldsStore.row`."""

    def __init__(self, store: _FakeFieldsStore):
        self._store = store

    def record_publish(self, tenant_id, *, published_version, published_at):
        self._store.row["published_version"] = published_version
        self._store.row["published_at"] = published_at


def _build_publish_service(store: _FakeFieldsStore):
    """The single wiring point of the publish service to the fake `config#fields` store.

    Task 11.4 adds the persistence collaborator and adapts ONLY this helper.
    """
    from sam.members.domain.application_publish import ApplicationPublishService
    from sam.members.domain.application_readiness import StaticMailReadinessProvider

    return ApplicationPublishService(
        slug_reader=_FakeSlugForwardReader(),
        readiness_provider=StaticMailReadinessProvider({_TENANT: (True, "h-dcn.nl")}),
        field_config_reader=_StoreBackedFieldConfigReader(store),
        artifact_writer=_FakeArtifactWriter(),
        publish_state_writer=_StoreBackedPublishStateWriter(store),
    )


def test_publish_state_is_persisted_on_config_fields_and_second_publish_is_v2(
    monkeypatch,
):
    """PUBLISH_STATE facet: after publish the stored row carries `published_version` /
    `published_at`, and a second publish yields version 2.

    CURRENT: publish returns the values but never persists them -> the row stays bare and the
    second publish is version 1 again -> FAILS.

    Validates (bugfix): Requirement 8.4
    """
    from sam.members.domain.application_publish import PUBLIC_API_BASE_ENV_VAR

    monkeypatch.setenv(PUBLIC_API_BASE_ENV_VAR, "https://api.test.example")
    store = _FakeFieldsStore()
    svc = _build_publish_service(store)

    first = svc.publish(_TENANT)
    assert first["success"] is True and first["published_version"] == 1, (
        "precondition: first publish"
    )

    assert store.row.get("published_version") == first["published_version"], (
        "BUG (PUBLISH_STATE facet): the stored config#fields row lacks published_version after a "
        f"successful publish. Stored row keys={sorted(store.row)!r}, publish returned "
        f"{first['published_version']!r}. Counterexample: the builder keeps saying 'unpublished "
        "changes' because nothing was persisted."
    )
    assert store.row.get("published_at") == first["published_at"], (
        "BUG (PUBLISH_STATE facet): the stored config#fields row lacks published_at after publish."
    )

    second = svc.publish(_TENANT)
    assert second["published_version"] == 2, (
        "BUG (PUBLISH_STATE facet): a second publish does not advance the version "
        f"(got {second['published_version']!r}, expected 2) because the first was never persisted."
    )
