"""
Bugfix spec `bugfix-published-form-submit` — Round 2, Task 5: the bug-condition EXPLORATION test.

Parent spec: `.kiro/specs/Members/14 - public-pages-multi-tenant-serving` (R5.1-R5.3, R10).
Bugfix spec: `.kiro/specs/Members/14 .../bugfix-published-form-submit` (design.md "Round 2").

WHAT THIS TEST IS
-----------------
The EXPLORATION test for Property 3 (Round-2 Bug Condition). The ROUND-1 fix SHIPPED — the
published `{slug}/index.html` now renders a `preventDefault`ed submit script, client `format`
checks, a locale selector, and a consent CHECKBOX bound to `notice.version`. Testing THAT shipped
artifact in TEST showed the applicant STILL cannot complete a submission. This test ENCODES THE
EXPECTED (Round-2-fixed) behaviour across the three confirmed facets, so on the SHIPPED (Round-1)
code it MUST FAIL — each failure is the counterexample proving the Round-2 bug exists (bugfix
workflow). After the Round-2 fix (tasks 7.x) the SAME assertions PASS unchanged.

It is a SCOPED property-based test (scoped-PBT): the generated input space is constrained to a
REPRESENTATIVE slug + per-env apex, a tenant whose `config#mail` `get_consent_notice` returns
`{version, text}`, and a consent-required 422 (`consent` / `CONSENT_REQUIRED`) — so every case
exercises the three facets of `isBugConditionR2` (design "Round 2 Bug Details"):

  * CORS         — with `PUBLIC_FORM_ALLOWED_ORIGINS` = the single canonical host and NO matching
                   embed origin, does `public_app.handler` echo `Access-Control-Allow-Origin` for
                   a request `Origin` equal to the resolved slug host `https://{slug}.{apex}`?
                   (Defect 1 — shipped: NO, the header is dropped, the read is blocked.)
  * NOTICE_TEXT  — does `get_public_field_config` surface the FULL notice `{version, text}` for a
                   tenant whose REAL `config#mail` `get_consent_notice` returns `{version, text}`?
                   (Defect 2 — shipped: NO, `notice = {"version": ...}` only, no `text`.)
  * ERROR_CLARITY — does the rendered submit script map a `consent` / `CONSENT_REQUIRED` 422 to a
                   consent-adjacent message (not the generic catch-all)?
                   (Defect 3 — shipped: NO, only the generic catch-all.)

PROVE AGAINST THE REAL SHAPE (steering 39): the NOTICE_TEXT facet does NOT hand-build the notice.
It seeds a REAL `config#mail` row (the shape `build_config_mail_row` produces) into an in-memory
`FakeTable`, drives the REAL `MembersProjectionReader.get_consent_notice` (proving `{version,
text}` genuinely lives in SAM) AND wires that SAME real reader as the `get_public_field_config`
consent-notice provider — so the version-only surfacing is proven against the genuine reader, not
a fixture. The CORS facet runs the REAL `public_app.handler` end-to-end (fake slug-marker store +
fake embed-origin reader, the established edge-test pattern) — no live AWS. The render step is
PURE, so ERROR_CLARITY asserts the rendered HTML string.

Validates (bugfix): Requirements 4.1, 4.2, 4.3, 4.4
"""

from __future__ import annotations

import os
import sys

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
# LandingPageStyles (the single CSS source) lives in backend/src/services — resolved from
# backend/src on the path in dev/test (vendored into the Members layer at build); mirrors the
# sibling Round-1 render tests.
_BACKEND_SRC = os.path.join(_REPO_ROOT, "backend", "src")
if _BACKEND_SRC not in sys.path:
    sys.path.insert(0, _BACKEND_SRC)

from services import projection_schema as schema  # noqa: E402

from sam.members.handler import public_app  # noqa: E402
from sam.members.repository.projection_config_reader import (  # noqa: E402
    MembersProjectionReader,
)
from sam.members.repository.slug_marker_store import SlugMarker  # noqa: E402

#: The verified real-data tenant whose published form is the dead end (design Round 2 Examples).
_SLUG = "hdcn-aanmelden"
#: The per-env apex the resolved slug host is formed against (design Round 2 Glossary — a per-env
#: config/env var in production; `jabaki.nl` is the canonical apex the published form is served on).
_APEX = "jabaki.nl"
#: The single canonical static baseline host for TEST (design Round 2 Overview, Defect 1) — the
#: ONLY value in `PUBLIC_FORM_ALLOWED_ORIGINS`; the per-slug host is NOT in it.
_CANONICAL_HOST = "https://aanmelden-test.jabaki.nl"
#: The resolved tenant the slug marker maps to (distinct from the slug — the resolved tenant_id is
#: what the service/CORS key on, verify-before-trust).
_TENANT = "h-dcn"


# ══════════════════════════════════════════════════════════════════════════════════════
# FACET: NOTICE_TEXT — Defect 2 / design Round 2 isBugConditionR2(facet=NOTICE_TEXT).
#
# EXPECTED (fixed) behaviour: `get_public_field_config` surfaces the FULL notice {version, text}
# from `get_consent_notice`. On the SHIPPED code it surfaces `notice = {"version": ...}` ONLY
# (wired to `get_consent_notice_version`), even though the REAL reader's `get_consent_notice`
# returns {version, text} for that tenant — so the applicant has no text to read/accept, consent
# is posted empty, and the backend returns 422 CONSENT_REQUIRED. This assertion FAILS now; the
# failure IS the counterexample.
#
# Proven against the REAL shape (steering 39): a real `config#mail` row is seeded into a FakeTable
# and read through the REAL `MembersProjectionReader` — the SAME reader is wired as the service's
# consent-notice provider, so the version-only surfacing is the genuine read path, not a fixture.
# ══════════════════════════════════════════════════════════════════════════════════════


class _FakeTable:
    """In-memory stand-in for a boto3 DynamoDB Table (query side) — mirrors the sibling
    projection-reader tests so no AWS / boto3 is touched (steering 39/34)."""

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


class _FakeCatalogRepo:
    """The catalog surface `MembershipService` reads — empty is all a public read needs here."""

    def list_membership_types(self, tenant_id, active_only=True):
        return []


def _config_mail_row(tenant_id: str, *, version: str, text: dict) -> dict:
    """A real `config#mail` row carrying a well-formed consent notice (the shape
    `build_config_mail_row` / `_resolve_application_consent_notice` produce on the Flask plane)."""
    return {
        schema.PARTITION_KEY_ATTR: tenant_id,
        schema.SORT_KEY_ATTR: schema.build_sort_key(schema.RECORD_TYPE_CONFIG, "mail"),
        "mail_enabled": True,
        "consent_notice": {"version": version, "text": dict(text)},
        schema.VERSION_ATTR: 1,
    }


# A well-formed consent-notice body: a non-blank version + at least one non-blank locale body.
_NOTICE_VERSION = st.sampled_from(["2026-01", "2", "notice-7", "v3"])
_NOTICE_TEXT = st.fixed_dictionaries(
    {
        "nl": st.text(min_size=1, max_size=40).filter(lambda s: s.strip()),
        "en": st.text(min_size=1, max_size=40).filter(lambda s: s.strip()),
    }
)


@settings(max_examples=25)
@given(version=_NOTICE_VERSION, text=_NOTICE_TEXT)
def test_notice_text_public_field_config_surfaces_full_notice_version_and_text(version, text):
    """NOTICE_TEXT facet: `get_public_field_config` must surface the FULL notice {version, text}.

    SHIPPED: it serves `{version}` only — so this FAILS (the counterexample).

    Validates (bugfix): Requirement 4.2
    """
    from sam.members.domain.field_resolver import StaticOverlayProvider
    from sam.members.domain.membership_service import MembershipService

    table = _FakeTable()
    table.put(_config_mail_row(_TENANT, version=version, text=text))
    reader = MembersProjectionReader(table=table)

    # REAL reader round-trip (steering 39): the full notice genuinely lives in SAM on config#mail.
    real_notice = reader.get_consent_notice(_TENANT)
    assert real_notice is not None, "precondition: the tenant has a well-formed notice in SAM"
    assert real_notice["version"] == version and real_notice["text"] == text

    # The SAME real reader is the service's consent-notice provider (it satisfies the Protocol by
    # duck-typing via `get_consent_notice_version`). So the surfaced `notice` is the genuine read.
    svc = MembershipService(
        _FakeCatalogRepo(),
        overlay_provider=StaticOverlayProvider(),
        consent_notice_provider=reader,
    )
    served = svc.get_public_field_config(_TENANT)
    notice = served.get("notice") or {}

    assert notice.get("version") == version, (
        "precondition: the served notice pins the tenant's current version"
    )
    # EXPECTED (fixed): the served notice carries the localized text the form shows. SHIPPED: no
    # `text` key at all — only `version` — so the applicant sees nothing to accept and consent is
    # posted empty (422 CONSENT_REQUIRED).
    assert notice.get("text") == text, (
        "BUG (NOTICE_TEXT facet): get_public_field_config surfaces notice.version ONLY, with NO "
        f"text, even though the REAL config#mail get_consent_notice returns {{version, text}} for "
        f"tenant {_TENANT!r}. Served notice={notice!r}. Counterexample: the published form shows "
        "no consent text to read/accept -> consent is posted empty -> backend 422 CONSENT_REQUIRED."
    )


# ══════════════════════════════════════════════════════════════════════════════════════
# FACET: CORS — Defect 1 / design Round 2 isBugConditionR2(facet=CORS).
#
# EXPECTED (fixed) behaviour: with the static baseline = the single canonical host and the tenant
# carrying NO matching embed origin, `public_app.handler` echoes `Access-Control-Allow-Origin` for
# a request `Origin` equal to the resolved slug host `https://{slug}.{apex}` (CORS Option B — the
# form's OWN slug host). On the SHIPPED code `_apply_cors_origin` does exact-match only against the
# baseline ∪ embed origins, and the per-slug host is in NEITHER — so the header is DROPPED, the
# browser blocks the read, and the submit fetch rejects into the generic catch-all. This assertion
# FAILS now; the failure IS the counterexample.
#
# Runs the REAL `public_app.handler` end-to-end (fake slug-marker store + fake embed-origin reader,
# the established edge-test pattern) — no live AWS.
# ══════════════════════════════════════════════════════════════════════════════════════


class _FakeSlugReader:
    """A fake `S3SlugMarkerStore` for the edge (no env, no S3) — mirrors the sibling edge tests.
    Exposes both `resolve_slug` (the POST TenantDirectory leg) and `resolve` (the GET marker-body
    leg) so a published SAM application-form slug resolves to its tenant."""

    def __init__(self, by_slug: dict[str, str], markers: dict[str, SlugMarker]):
        self._by_slug = dict(by_slug)
        self._markers = dict(markers)

    def resolve_slug(self, slug):
        if not isinstance(slug, str) or not slug:
            return None
        return self._by_slug.get(slug)

    def resolve(self, slug):
        if not isinstance(slug, str) or not slug:
            return None
        return self._markers.get(slug.strip().lower())


class _FakeEmbedOriginReader:
    """A `MembersProjectionReader` stand-in returning a canned per-tenant embed-origin list (keyed
    on the RESOLVED tenant_id) — the established CORS edge-test fake."""

    def __init__(self, by_tenant: dict[str, list[str]] | None = None):
        self._by_tenant = dict(by_tenant or {})

    def get_application_embed_origins(self, tenant_id):
        return list(self._by_tenant.get(tenant_id, []))


class _FakeApplicationService:
    """A stand-in for `ApplicationService` the GET field-config read calls (no DynamoDB engine) —
    returns a whitelisted schema for the send-ready tenant so the 200 carries the CORS header."""

    def __init__(self, ready: dict[str, dict]):
        self._ready = dict(ready)

    def get_public_field_config(self, tenant_id):
        from sam.members.domain.application_readiness import ApplicationNotAvailable

        if tenant_id not in self._ready:
            raise ApplicationNotAvailable()
        return self._ready[tenant_id]


def _proxy_event(method, path, *, headers=None):
    """An API Gateway proxy event for the public edge — NO authorizer context (token-less)."""
    return {
        "httpMethod": method,
        "path": path,
        "headers": headers or {},
        "queryStringParameters": None,
        "body": None,
        "isBase64Encoded": False,
    }


def _whitelisted_schema(tenant_id):
    return {
        "tenant_id": tenant_id,
        "fields": [
            {"key": "email", "type": "email", "label": {"nl": "E-mail"}, "required": True}
        ],
        "functional_groups": [],
        "locales": ["nl", "en"],
        "notice": {"version": "2026-01"},
    }


#: The slug segments the published form uses, resolving to a tenant with NO matching embed origin.
_RESOLVED_SLUGS = st.sampled_from(["hdcn-aanmelden", "form-aanmelden", "club-inschrijven"])


# `monkeypatch` is function-scoped (not reset per generated input), but every generated case
# re-applies the SAME deterministic patch set keyed on the drawn slug before asserting, so the
# fixture carryover is safe here — suppress the Hypothesis health check for it (the alternative, a
# manual `MonkeyPatch` context per input, buys nothing over the re-applied setattr/setenv).
@settings(
    max_examples=15,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(resolved_slug=_RESOLVED_SLUGS)
def test_cors_resolved_slug_host_is_allowed_for_the_published_form(resolved_slug, monkeypatch):
    """CORS facet: the resolved slug host `https://{slug}.{apex}` must be CORS-allowed.

    SHIPPED: `_apply_cors_origin` exact-matches the baseline ∪ embed origins only; the per-slug
    host is in NEITHER, so the header is dropped (read blocked) — this FAILS (the counterexample).

    Validates (bugfix): Requirement 4.1
    """
    tenant_id = f"{resolved_slug}-tenant"
    origin = f"https://{resolved_slug}.{_APEX}"  # the form's OWN resolved slug host

    # Static baseline = the single canonical TEST host ONLY — the per-slug host is NOT in it.
    monkeypatch.setenv(public_app.ALLOWED_ORIGINS_ENV, _CANONICAL_HOST)
    # The slug marker store resolves the published SAM application-form slug to its tenant.
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
    # The resolved tenant has NO embed origin that matches its own slug host (the Defect-1 case).
    monkeypatch.setattr(
        public_app,
        "MembersProjectionReader",
        lambda *a, **k: _FakeEmbedOriginReader({}),
    )
    monkeypatch.setattr(
        public_app,
        "_application_service",
        lambda: _FakeApplicationService({tenant_id: _whitelisted_schema(tenant_id)}),
    )

    resp = public_app.handler(
        _proxy_event(
            "GET",
            f"/public/members/{resolved_slug}/field-config",
            headers={"Origin": origin},
        )
    )

    acao = resp.get("headers", {}).get("Access-Control-Allow-Origin")
    assert acao == origin, (
        "BUG (CORS facet): the published form's OWN resolved slug host is DROPPED by CORS. "
        f"Origin {origin!r} (the resolved slug host for tenant {tenant_id!r}) got "
        f"Access-Control-Allow-Origin={acao!r} with the static baseline {_CANONICAL_HOST!r} and "
        "no matching embed origin. Counterexample: the browser blocks the cross-origin read, the "
        "submit fetch rejects into the generic catch-all, and the real 422 is never seen."
    )
    assert acao != "*", "CORS must never echo `*` on the public edge (fail-closed)."


# ══════════════════════════════════════════════════════════════════════════════════════
# FACET: ERROR_CLARITY — Defect 3 / design Round 2 isBugConditionR2(facet=ERROR_CLARITY).
#
# EXPECTED (fixed) behaviour: the embedded submit script maps a `consent` / `CONSENT_REQUIRED` 422
# to a CLEAR message near the consent control (and field 422s inline), keeping the neutral generic
# message only for opaque / 5xx responses. On the SHIPPED code the 422 handler maps only the
# generic catch-all — no `CONSENT_REQUIRED` recognition, no consent-adjacent message — so the
# applicant sees "Je aanmelding kon niet worden verwerkt" with no idea the notice was not accepted.
# This assertion FAILS now; the failure IS the counterexample.
#
# The render step is PURE — assert the rendered artifact STRING.
# ══════════════════════════════════════════════════════════════════════════════════════


def _render_with_consent(notice_version: str, text: dict):
    """Render the published artifact for a config carrying a notice (version + text) so the submit
    script + consent control are present — the shape the Round-2 fix must enrich."""
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
        # On the shipped code only `version` is served; the Round-2 fix adds `text`. The render
        # exploration asserts the SCRIPT's error mapping, which is independent of whether text is
        # present, so carry the full notice to mirror the fixed input space.
        "notice": {"version": notice_version, "text": dict(text)},
    }
    return render_application_form_page(
        config,
        head_meta={"title": "Aanmelden", "canonical": f"https://{_SLUG}.{_APEX}/apply"},
        slug=_SLUG,
        public_api_base="https://api.test.example",
    )


@settings(max_examples=25)
@given(version=_NOTICE_VERSION, text=_NOTICE_TEXT)
def test_error_clarity_submit_script_maps_consent_required_422_near_the_consent_control(
    version, text
):
    """ERROR_CLARITY facet: the submit script must map a `consent` / `CONSENT_REQUIRED` 422 to a
    consent-adjacent message, not the generic catch-all.

    SHIPPED: the 422 handler recognises no `CONSENT_REQUIRED` code and shows no consent-adjacent
    message — only the generic catch-all — so this FAILS (the counterexample).

    Validates (bugfix): Requirements 4.3, 4.4
    """
    artifact = _render_with_consent(version, text)

    # EXPECTED (fixed): the submit script recognises the consent-required 422 by its code and
    # surfaces a message near the consent control. SHIPPED: neither the code nor any
    # consent-adjacent mapping appears — the 422 falls to the generic catch-all.
    recognises_consent_code = "CONSENT_REQUIRED" in artifact
    maps_consent_control = ("consent" in artifact.lower()) and (
        "data-field=\"consent\"" in artifact
    )
    # The fix wires the consent 422 to the consent control specifically — the generic catch-all
    # alone (the shipped behaviour) is NOT a consent-adjacent mapping.
    wires_consent_422_inline = recognises_consent_code and maps_consent_control

    assert wires_consent_422_inline, (
        "BUG (ERROR_CLARITY facet): the submit script maps a consent-required 422 only to the "
        "generic catch-all. Observed on the shipped render: CONSENT_REQUIRED code recognised="
        f"{recognises_consent_code}, consent-control present={maps_consent_control}. "
        "Counterexample: the backend returns 422 with field key `consent` / code "
        "CONSENT_REQUIRED, but the applicant sees 'Je aanmelding kon niet worden verwerkt' with "
        "no hint that the notice was not accepted."
    )
