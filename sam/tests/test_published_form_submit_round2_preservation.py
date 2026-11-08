"""
Bugfix spec `bugfix-published-form-submit` — Round 2, Task 6: the PRESERVATION property tests.

Parent spec: `.kiro/specs/Members/14 - public-pages-multi-tenant-serving`.
Bugfix spec: `.kiro/specs/Members/14 .../bugfix-published-form-submit` (design.md "Round 2").

WHAT THIS TEST IS
-----------------
This is the PRESERVATION half of the Round-2 exploration (companion to the task-5 bug-condition
exploration `test_published_form_submit_round2_bug_condition.py`). It encodes Property 4
(Preservation, Round 2): for any input where the Round-2 bug condition does NOT hold
(`isBugConditionR2` false), the Round-2 fix (tasks 7.x — CORS Option B, notice-text surfacing,
inline error mapping) must produce the SAME result as the shipped (Round-1) system for the
behaviours the design's "Round 2 Preservation Requirements" name.

OBSERVATION-FIRST (bugfix workflow / steering 39): every assertion here was OBSERVED on the
SHIPPED (Round-1) code and MUST PASS NOW — it is the baseline the Round-2 fix must not disturb.
The Round-2 fix widens CORS to the form's OWN resolved slug host, surfaces the notice `text`
beside `version`, renders that text, and maps the consent/field 422s inline; it must NOT change:

  * R6.1 — the backend consent GATE `_consent_is_affirmative` (requires `accepted is True`,
           fail-closed), and the public submit endpoint it guards — NOT modified by Round 2;
  * R6.2 — `create_application`'s server-authoritative consent STAMP
           (`_stamp_application_consent` → `{version, accepted_at, locale}`) — unchanged;
  * R6.3 — the in-app SPA form, the Flask landing plane, and the `config#mail` WRITE path
           (`config_write_service._shape_consent_notice`) are not referenced/altered by the
           SAM render/handler/field-config read change (STRUCTURAL import-boundary assertion);
  * R6.4 — `get_public_field_config` stays the single field authority; no raw record shape
           crosses the boundary (steering 39). The Round-2 fix adds only `text` beside `version`;
           for PRESERVATION we pin the STABLE aspects (single authority shape, no raw-shape leak);
  * R6.5 — CORS stays fail-closed: for any origin that is NOT the resolved slug host, the static
           baseline, or a tenant embed origin the header is DROPPED (never `*`, no `*.jabaki.nl`
           wildcard). Explicitly asserts a FOREIGN `*.jabaki.nl` host (`https://evil.jabaki.nl`)
           is REJECTED.

PROVE AGAINST THE REAL SHAPE (steering 39): the notice round-trip (`TestRealConfigMailNotice...`)
does NOT hand-build the notice dict — it drives the REAL
`MembersProjectionReader.get_consent_notice` over a REAL `config#mail` row shape (seeded into the
reader's partition cache, the established sibling pattern from `test_application_consent.py`'s
`_NoticeReader`), so the `{version, text}` round-trip is proven against the genuine `config#mail`
projection shape (e.g. h-dcn), NOT a hand-built fixture. A hand-built dict has hidden this class
of bug before (steering 39 — "trust runs, not inference").

NO live AWS: the consent gate/stamp run over the in-memory fake application repo + static
providers (the established `test_application_consent` / `test_create_application` pattern); the
reader runs over a pre-seeded partition cache (its `table` is never queried); the CORS decision
and render are PURE. Property-based where the invariant is universal (any foreign origin is
fail-closed; any well-formed `config#mail` row round-trips to `{version, text}`) — design
"Round 2 Preservation Checking".

Validates (bugfix): Requirements 6.1, 6.2, 6.3, 6.4, 6.5
"""

from __future__ import annotations

import importlib
import os
import sys
from datetime import datetime, timezone

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
# LandingPageStyles (the single CSS source) lives in backend/src/services — resolved from
# backend/src on the path in dev/test (vendored into the Members layer at build time); mirrors
# the sibling render tests and projection_schema reuse.
_BACKEND_SRC = os.path.join(_REPO_ROOT, "backend", "src")
if _BACKEND_SRC not in sys.path:
    sys.path.insert(0, _BACKEND_SRC)

from sam.members.domain._membership_errors import MemberValidationError  # noqa: E402
from sam.members.domain.consent_notice import StaticConsentNoticeProvider  # noqa: E402
from sam.members.domain.error_codes import CONSENT_REQUIRED  # noqa: E402
from sam.members.domain.field_resolver import (  # noqa: E402
    FixedFieldOverride,
    StaticOverlayProvider,
    TenantOverlay,
)
from sam.members.domain.fixed_fields import EnumOption  # noqa: E402
from sam.members.domain.membership_service import MembershipService  # noqa: E402

# Reuse the task-2.2 fake repo (member store + first-wins session claim + catalog surface) and
# the shared catalog-entry factory — the SAME fakes the Round-1 consent tests used, so the
# preservation baseline is observed on the identical shipped path.
from sam.tests.test_create_application import _ApplicationRepo  # noqa: E402
from sam.tests.test_field_config_endpoint import _entry  # noqa: E402

_TENANT = "h-dcn"
_APEX = "jabaki.nl"


# ──────────────────────────────────────────────────────────────────────────────────────
# Shared builders for the backend consent gate/stamp baseline (mirror test_application_consent).
# ──────────────────────────────────────────────────────────────────────────────────────


def _overlay_public_form() -> TenantOverlay:
    """Put the identity + membership_type fields on the PUBLIC form (application_visible)."""
    return TenantOverlay(
        overrides={
            "personal.first_name": FixedFieldOverride(application_visible=True),
            "personal.last_name": FixedFieldOverride(application_visible=True),
            "personal.email": FixedFieldOverride(application_visible=True),
            "personal.birth_date": FixedFieldOverride(application_visible=True),
            "membership.membership_type": FixedFieldOverride(
                application_visible=True,
                options=(
                    EnumOption(
                        value="gewoon",
                        label={"nl": "Gewoon", "en": "Regular"},
                        allowed=True,
                        order=10,
                    ),
                ),
            ),
        },
    )


def _service(consent_version: str | None = "v1") -> MembershipService:
    repo = _ApplicationRepo()
    repo.add_type(_TENANT, _entry(_TENANT, "gewoon", order=10))
    provider = StaticConsentNoticeProvider(
        {_TENANT: consent_version} if consent_version is not None else {}
    )
    return MembershipService(
        repo,
        overlay_provider=StaticOverlayProvider({_TENANT: _overlay_public_form()}),
        consent_notice_provider=provider,
    )


def _submission(**over):
    body = {
        "personal.first_name": "Sam",
        "personal.last_name": "Jansen",
        "personal.email": "sam@example.com",
        "personal.birth_date": "1990-05-01",
        "membership.membership_type": "gewoon",
    }
    body.update(over)
    return body


# ══════════════════════════════════════════════════════════════════════════════════════
# R6.1 — the backend consent GATE `_consent_is_affirmative` round-trips unchanged.
#
# Round 2 touches CORS / notice surfacing / error mapping — NOT the gate. These pin the exact
# fail-closed affirmative semantics (only `accepted is True` passes) observed on the shipped code,
# so the Round-2 change can never loosen the gate.
# ══════════════════════════════════════════════════════════════════════════════════════


class TestConsentGatePreserved:
    @pytest.mark.parametrize(
        "consent",
        [
            None,  # no consent block
            {},  # block but no `accepted`
            {"accepted": False},  # explicitly not accepted
            {"accepted": "true"},  # truthy STRING is not affirmative (fail-closed)
            {"accepted": 1},  # truthy int is not affirmative
            {"notice_version": "v1"},  # version but no acceptance
            "not-a-mapping",  # non-mapping consent value
        ],
    )
    def test_submit_without_affirmative_consent_still_hard_rejects(self, consent):
        # R6.1: the fail-closed gate rejects every non-`accepted-is-True` consent on the SHIPPED
        # code — the Round-2 baseline the fix must preserve.
        service = _service()
        with pytest.raises(MemberValidationError) as exc:
            service.create_application(
                _TENANT, _submission(), session_key="s1", consent=consent
            )
        assert "consent" in exc.value.errors
        assert exc.value.errors["consent"].code == CONSENT_REQUIRED

    def test_rejected_submit_still_writes_no_record(self):
        # R6.1: a non-affirmative submit leaves NO record (the reject precedes save_member).
        service = _service()
        with pytest.raises(MemberValidationError):
            service.create_application(
                _TENANT, _submission(), session_key="s1", consent=None
            )
        assert len(service._repo.members) == 0

    def test_affirmative_consent_still_accepted(self):
        # R6.1: the ONE affirmative shape (`accepted is True`) still passes the gate.
        service = _service()
        rec = service.create_application(
            _TENANT, _submission(), session_key="s1", consent={"accepted": True}
        )
        assert rec["membership"]["status"] == "application"
        assert "consent" in rec


@settings(max_examples=60)
@given(
    accepted=st.one_of(
        st.booleans(),
        st.sampled_from(["true", "false", "1", "yes", ""]),
        st.integers(min_value=0, max_value=3),
        st.none(),
    )
)
def test_preserve_gate_is_true_only_for_boolean_true(accepted):
    """R6.1: the affirmative gate is TRUE for exactly one value — the boolean ``True`` — and
    fail-closed for every other (a truthy string / int / None). Universal over the client value.

    Validates (bugfix): Requirement 6.1
    """
    is_affirmative = MembershipService._consent_is_affirmative({"accepted": accepted})
    assert is_affirmative is (accepted is True)


# ══════════════════════════════════════════════════════════════════════════════════════
# R6.2 — the server-authoritative consent STAMP is unchanged.
#
# `create_application` stamps `consent{version, accepted_at, locale}` server-side: version from
# the server-resolved notice (never the client value), a server-UTC timestamp, the normalized
# locale. Round 2 does NOT touch this. Pin the stamp shape + authority on the shipped code.
# ══════════════════════════════════════════════════════════════════════════════════════


class TestConsentStampPreserved:
    def test_stamp_shape_and_server_resolved_version(self):
        # R6.2: the stamp is exactly {version, accepted_at, locale}; version is the SERVER-resolved
        # notice version, not any client value.
        service = _service(consent_version="2026-01-notice")
        rec = service.create_application(
            _TENANT,
            _submission(),
            session_key="s1",
            consent={"accepted": True, "notice_version": "client-spoofed"},
        )
        assert set(rec["consent"].keys()) == {"version", "accepted_at", "locale"}
        assert rec["consent"]["version"] == "2026-01-notice"
        assert rec["consent"]["version"] != "client-spoofed"

    def test_stamp_timestamp_is_server_utc(self):
        # R6.2: accepted_at is a server-minted tz-aware UTC timestamp ~now (client value ignored).
        before = datetime.now(timezone.utc)
        service = _service()
        rec = service.create_application(
            _TENANT,
            _submission(),
            session_key="s1",
            consent={"accepted": True, "accepted_at": "1999-01-01T00:00:00+00:00"},
        )
        after = datetime.now(timezone.utc)
        stamped = datetime.fromisoformat(rec["consent"]["accepted_at"])
        assert stamped.tzinfo is not None
        assert before <= stamped <= after

    @pytest.mark.parametrize(
        "submitted, expected",
        [("en", "en"), ("nl", "nl"), ("EN", "en"), (" nl ", "nl"), ("de", "nl"), (None, "nl")],
    )
    def test_stamp_locale_is_normalized(self, submitted, expected):
        # R6.2: the stamped locale is the normalized applicant locale (nl fallback).
        service = _service()
        rec = service.create_application(
            _TENANT,
            _submission(),
            session_key="s1",
            locale=submitted,
            consent={"accepted": True},
        )
        assert rec["consent"]["locale"] == expected

    def test_stamp_records_even_when_tenant_has_no_notice(self):
        # R6.2: a tenant with no authored notice stamps version None but still records consent.
        service = _service(consent_version=None)
        rec = service.create_application(
            _TENANT, _submission(), session_key="s1", consent={"accepted": True}
        )
        assert rec["consent"]["version"] is None
        assert rec["consent"]["accepted_at"]
        assert rec["consent"]["locale"] == "nl"


# ══════════════════════════════════════════════════════════════════════════════════════
# R6.4 — PROVE THE NOTICE ROUND-TRIP AGAINST THE REAL config#mail / get_consent_notice SHAPE.
#
# Drives the REAL `MembersProjectionReader.get_consent_notice` over a REAL `config#mail` row
# (seeded into the reader's partition cache — the established `test_application_consent._NoticeReader`
# pattern, NO boto3). This is the single read authority the Round-2 fix will source the surfaced
# `text` from; the PRESERVATION assertion pins its STABLE round-trip ({version, text} in / out,
# empty-is-valid → None) so the fix surfaces the genuine shape, not a hand-built one (steering 39).
# ══════════════════════════════════════════════════════════════════════════════════════


def _reader_over_config_mail(consent_notice):
    """A `MembersProjectionReader` over a single pre-seeded REAL `config#mail` partition row.

    Mirrors `test_application_consent._NoticeReader`: builds the row with the REAL projection
    schema keys and seeds the reader's per-invocation partition cache, so `get_consent_notice`
    reads it exactly as it would a genuine projected row — no boto3, the `table` is never queried.
    """
    from sam.members.repository.projection_config_reader import MembersProjectionReader
    from services import projection_schema as schema

    row = {
        schema.PARTITION_KEY_ATTR: _TENANT,
        schema.SORT_KEY_ATTR: f"{schema.RECORD_TYPE_CONFIG}#{schema.CONFIG_ID_MAIL}",
    }
    if consent_notice is not None:
        row["consent_notice"] = consent_notice
    reader = MembersProjectionReader(table=object())  # table never queried (cache pre-seeded)
    reader._partition_cache[_TENANT] = [row]
    return reader


class TestRealConfigMailNoticeRoundTrip:
    """R6.4: the REAL `get_consent_notice` round-trip over a real `config#mail` row shape."""

    def test_well_formed_hdcn_notice_round_trips_to_version_and_text(self):
        # The realistic h-dcn-shaped notice (versioned, bilingual) stored on config#mail reads
        # back as {version, text} unchanged — the shape the Round-2 fix will surface.
        reader = _reader_over_config_mail(
            {
                "version": "2",
                "text": {
                    "nl": "Door dit formulier te versturen ga je akkoord met onze privacyverklaring.",
                    "en": "By submitting this form you agree to our privacy notice.",
                },
            }
        )
        notice = reader.get_consent_notice(_TENANT)
        assert notice == {
            "version": "2",
            "text": {
                "nl": "Door dit formulier te versturen ga je akkoord met onze privacyverklaring.",
                "en": "By submitting this form you agree to our privacy notice.",
            },
        }
        # The version-only accessor the Round-1 stamp uses still agrees with the full notice.
        assert reader.get_consent_notice_version(_TENANT) == "2"

    def test_absent_notice_is_empty_is_valid_none(self):
        # Empty-is-valid: a config#mail row with no consent_notice attr reads back None (both
        # accessors) — the baseline the fix must keep (a notice-less tenant is not an error).
        reader = _reader_over_config_mail(None)
        assert reader.get_consent_notice(_TENANT) is None
        assert reader.get_consent_notice_version(_TENANT) is None

    @pytest.mark.parametrize(
        "notice",
        [
            "not-a-mapping",
            {"text": {"nl": "x"}},  # no version
            {"version": "   ", "text": {"nl": "x"}},  # blank version
            {"version": "v1"},  # no text
            {"version": "v1", "text": {}},  # empty text
            {"version": "v1", "text": {"nl": "   "}},  # only blank bodies
        ],
    )
    def test_malformed_notice_still_degrades_to_none(self, notice):
        # A malformed stored notice degrades to None (never a broken partial) on the shipped
        # reader — preserved regardless of the Round-2 surfacing.
        reader = _reader_over_config_mail(notice)
        assert reader.get_consent_notice(_TENANT) is None
        assert reader.get_consent_notice_version(_TENANT) is None


@settings(max_examples=60)
@given(
    version=st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789-.", min_size=1, max_size=12),
    nl_body=st.text(min_size=1, max_size=40).filter(lambda s: s.strip()),
    en_body=st.text(min_size=1, max_size=40).filter(lambda s: s.strip()),
)
def test_preserve_wellformed_notice_round_trips_version_and_nonblank_bodies(version, nl_body, en_body):
    """R6.4: for any well-formed `config#mail` consent notice (a non-blank version + at least one
    non-blank locale body), the REAL reader round-trips it to `{version, text}` with the version
    trimmed and only non-blank bodies surviving — the stable shape the fix surfaces.

    Validates (bugfix): Requirement 6.4
    """
    reader = _reader_over_config_mail(
        {"version": version, "text": {"nl": nl_body, "en": en_body}}
    )
    notice = reader.get_consent_notice(_TENANT)
    assert notice is not None
    assert notice["version"] == version.strip()
    assert notice["text"]["nl"] == nl_body
    assert notice["text"]["en"] == en_body
    assert reader.get_consent_notice_version(_TENANT) == version.strip()


# ══════════════════════════════════════════════════════════════════════════════════════
# R6.4 — `get_public_field_config` stays the single field authority (no raw-shape leak).
#
# On the SHIPPED code the public field config serves `notice = {"version": ...}` (version-only —
# that is exactly the Round-2 bug, asserted by the task-5 exploration). PRESERVATION pins the
# STABLE aspects the fix must NOT disturb: the single-authority shape (a flat `fields` list, a
# `functional_groups` catalog, `locales`, a `notice`) and that NO raw record shape (`field_overlay`
# / `overrides` / `fixed_overrides`) crosses the boundary (steering 39). The fix adds only `text`
# beside `version`; it must not change the shape or leak raw storage keys.
# ══════════════════════════════════════════════════════════════════════════════════════


def _public_config_service():
    """A real `MembershipService` whose `get_public_field_config` serves a realistic h-dcn shape."""
    repo = _ApplicationRepo()
    repo.add_type(_TENANT, _entry(_TENANT, "gewoon", order=10))
    return MembershipService(
        repo,
        overlay_provider=StaticOverlayProvider({_TENANT: _overlay_public_form()}),
        consent_notice_provider=StaticConsentNoticeProvider({_TENANT: "notice-v3"}),
    )


class TestPublicFieldConfigSingleAuthorityPreserved:
    @pytest.fixture(scope="class")
    def config(self):
        return _public_config_service().get_public_field_config(_TENANT)

    def test_single_authority_shape_is_stable(self, config):
        # R6.4: the resolved single-authority shape (fields list + functional_groups + locales +
        # notice) is what the renderer consumes — unchanged by the Round-2 surfacing.
        assert set(config.keys()) >= {"tenant_id", "fields", "functional_groups", "locales", "notice"}
        assert isinstance(config["fields"], list)
        assert all("key" in f for f in config["fields"])
        assert "version" in config["notice"]  # the stable version is present (text is the fix)

    def test_no_raw_record_shape_crosses_the_boundary(self, config):
        # R6.4 / steering 39: no raw storage-shape key leaks into the public config — the stable
        # invariant the fix (adding only `text`) must keep.
        import json

        blob = json.dumps(config)
        for raw in ("field_overlay", "overrides", "fixed_overrides"):
            assert raw not in blob


# ══════════════════════════════════════════════════════════════════════════════════════
# R6.5 — CORS stays FAIL-CLOSED for every origin that is not the resolved slug host, the static
# baseline, or a tenant embed origin (never `*`, no `*.jabaki.nl` wildcard).
#
# Asserted against the REAL `public_app._apply_cors_origin` on the SHIPPED code. Explicitly pins
# that a FOREIGN `*.jabaki.nl` host (`https://evil.jabaki.nl`) is REJECTED — the Round-2 CORS
# Option B widening (task 7.1) only admits the form's OWN resolved slug host, so this fail-closed
# baseline for foreign hosts must survive. On the shipped code the resolved slug host itself is
# ALSO dropped (that is the Round-2 bug the task-5 exploration asserts); here we only pin the
# fail-closed behaviour for foreign origins + no-origin + wildcard-never.
# ══════════════════════════════════════════════════════════════════════════════════════


def _parsed_request_with_origin(origin):
    """A `ParsedRequest` carrying (or omitting, when `origin is None`) an `Origin` header."""
    from sam.members.handler._http import ParsedRequest

    headers = {"Origin": origin} if origin is not None else {}
    return ParsedRequest(
        method="POST",
        path=f"/public/members/{_TENANT}/applications",
        headers=headers,
        query={},
        body={},
    )


def _apply_cors(origin, *, allowed_env, tenant_id=None, embed_origins=()):
    """Run the REAL `_apply_cors_origin` with a controlled static baseline + tenant embed list.

    `allowed_env` sets `PUBLIC_FORM_ALLOWED_ORIGINS` (the static baseline). `embed_origins` stubs
    the tenant's projected `application_embed_origins` so the decision is deterministic without
    boto3 (the reader resolve is monkeypatched on the module). Returns the response headers dict.
    """
    import sam.members.handler.public_app as public_app

    prior_env = os.environ.get(public_app.ALLOWED_ORIGINS_ENV)
    prior_embed = public_app._tenant_embed_origins
    try:
        if allowed_env is None:
            os.environ.pop(public_app.ALLOWED_ORIGINS_ENV, None)
        else:
            os.environ[public_app.ALLOWED_ORIGINS_ENV] = allowed_env
        public_app._tenant_embed_origins = lambda tid: list(embed_origins) if tid else []
        response = {"headers": {"Access-Control-Allow-Origin": "*"}}  # the shared `*` envelope
        out = public_app._apply_cors_origin(
            response, _parsed_request_with_origin(origin), tenant_id=tenant_id
        )
        return out["headers"]
    finally:
        public_app._tenant_embed_origins = prior_embed
        if prior_env is None:
            os.environ.pop(public_app.ALLOWED_ORIGINS_ENV, None)
        else:
            os.environ[public_app.ALLOWED_ORIGINS_ENV] = prior_env


_STATIC_BASELINE = "https://aanmelden-test.jabaki.nl"


class TestCorsFailClosedPreserved:
    def test_foreign_jabaki_subdomain_is_rejected(self):
        # R6.5: a FOREIGN `*.jabaki.nl` host (not the resolved slug host, not the baseline, not an
        # embed origin) gets NO Access-Control-Allow-Origin — the fail-closed baseline the Round-2
        # slug-host widening must NOT relax into a `*.jabaki.nl` wildcard.
        headers = _apply_cors(
            "https://evil.jabaki.nl",
            allowed_env=_STATIC_BASELINE,
            tenant_id=_TENANT,
            embed_origins=(),
        )
        assert "Access-Control-Allow-Origin" not in headers

    def test_resolved_slug_host_is_not_admitted_on_shipped_code(self):
        # The SHIPPED baseline: the form's OWN resolved slug host is NOT in the static baseline nor
        # an embed origin, so it is dropped (this IS the Round-2 bug the fix addresses). Pinned here
        # only to document the observed shipped behaviour — the fix will FLIP this (task 7.1 / 7.5),
        # and it is the task-5 exploration, not this preservation file, that asserts the flip.
        headers = _apply_cors(
            f"https://{_TENANT}.{_APEX}",
            allowed_env=_STATIC_BASELINE,
            tenant_id=_TENANT,
            embed_origins=(),
        )
        assert "Access-Control-Allow-Origin" not in headers

    def test_static_baseline_origin_is_echoed_exactly_never_wildcard(self):
        # R6.5: a request from the static baseline host echoes EXACTLY that origin (never `*`) and
        # sets Vary: Origin — the admitted case that must stay unchanged.
        headers = _apply_cors(
            _STATIC_BASELINE, allowed_env=_STATIC_BASELINE, tenant_id=_TENANT
        )
        assert headers["Access-Control-Allow-Origin"] == _STATIC_BASELINE
        assert "Origin" in headers.get("Vary", "")

    def test_tenant_embed_origin_is_echoed_exactly(self):
        # R6.5: a tenant-authored embed origin is admitted (echoed exactly) — the second member of
        # the allow-list union, unchanged by Round 2.
        embed = "https://club.example.org"
        headers = _apply_cors(
            embed,
            allowed_env=_STATIC_BASELINE,
            tenant_id=_TENANT,
            embed_origins=(embed,),
        )
        assert headers["Access-Control-Allow-Origin"] == embed

    def test_no_origin_header_is_dropped_not_wildcard(self):
        # R6.5: a request with no Origin (non-browser / same-origin) drops the header rather than
        # leaving the shared `*` — fail-closed, preserved.
        headers = _apply_cors(None, allowed_env=_STATIC_BASELINE, tenant_id=_TENANT)
        assert "Access-Control-Allow-Origin" not in headers

    def test_empty_allow_list_drops_the_header(self):
        # R6.5: an unset baseline AND no embed origins → empty union → header dropped (never `*`).
        headers = _apply_cors(
            "https://anything.example.com", allowed_env=None, tenant_id=None, embed_origins=()
        )
        assert "Access-Control-Allow-Origin" not in headers


# A strategy for arbitrary FOREIGN origins — including other `*.jabaki.nl` hosts that are NOT the
# resolved slug host — none of which may ever be admitted (fail-closed, no wildcard).
_FOREIGN_HOST = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789-", min_size=1, max_size=12
).filter(lambda s: s not in {_TENANT, "aanmelden-test", "aanmelden"})


@settings(max_examples=120)
@given(sub=_FOREIGN_HOST, apex=st.sampled_from(["jabaki.nl", "example.com", "evil.net"]))
def test_preserve_foreign_origin_never_admitted_and_never_wildcard(sub, apex):
    """R6.5: for ANY foreign origin (a random `*.jabaki.nl` host included) that is not the resolved
    slug host, the static baseline, or an embed origin, the CORS header is DROPPED — never echoed,
    never `*`. The universal fail-closed invariant the Round-2 slug-host widening must preserve.

    Validates (bugfix): Requirement 6.5
    """
    origin = f"https://{sub}.{apex}"
    headers = _apply_cors(
        origin, allowed_env=_STATIC_BASELINE, tenant_id=_TENANT, embed_origins=()
    )
    acao = headers.get("Access-Control-Allow-Origin")
    assert acao != "*"
    # The only admissible origin in this configuration is the static baseline itself; a random
    # foreign host (even under jabaki.nl) must never be echoed.
    assert acao is None or acao == _STATIC_BASELINE


# ══════════════════════════════════════════════════════════════════════════════════════
# R6.3 — STRUCTURAL boundary: the SAM render / handler / field-config read paths do NOT reach into
# the Flask landing plane NOR the `config#mail` WRITE path (`config_write_service`). Mirrors the
# sibling Round-1 `test_published_form_submit_preservation.py` import-boundary test: import the
# module and scan the NEWLY-imported `sys.modules` for a forbidden fragment. The in-app SPA form is
# a frontend artifact a Python import cannot pull in (listed for completeness).
# ══════════════════════════════════════════════════════════════════════════════════════

#: The SAM modules Round 2 touches — the render step, the public handler (CORS), and the
#: field-config read surface. None may NEWLY import the landing plane or the config#mail writer.
_ROUND2_MODULES = (
    "sam.members.domain.application_form_render",
    "sam.members.handler.public_app",
    "sam.members.domain._membership_writes_fieldconfig",
)

#: Flask landing-plane module fragments the SAM paths must never import (R6.3 — landing untouched).
_LANDING_PLANE_FRAGMENTS = (
    "landing_page_service",
    "landing_page_routes",
    "tenant_slug_service",
    "tenant_slugs",
)

#: The `config#mail` WRITE path + the in-app SPA path — NOT referenced/altered by Round 2. The
#: SAM paths READ the notice (`get_consent_notice`), they never reach the write-shaper.
_WRITE_PATH_FRAGMENTS = (
    "config_write_service",
    "ApplicationFormPage",
)


@pytest.mark.parametrize("module_name", _ROUND2_MODULES)
def test_preserve_round2_module_never_imports_flask_landing_plane(module_name):
    """R6.3: no Round-2-touched SAM module transitively imports the Flask landing plane — the
    landing module is untouched by this fix (spec 14 Scope decision).

    Order-independent: inspect only the NEWLY-imported modules (`sys.modules - before`), never the
    union with `before` (which would fold in everything earlier tests already imported and surface
    a false leak in a full-suite run).

    Validates (bugfix): Requirement 6.3
    """
    before = set(sys.modules)
    importlib.import_module(module_name)
    newly = set(sys.modules) - before
    leaked = [n for n in newly if any(frag in n for frag in _LANDING_PLANE_FRAGMENTS)]
    assert leaked == [], (
        f"{module_name} must not import the Flask landing plane (R6.3 — landing untouched); "
        f"leaked: {leaked}"
    )


@pytest.mark.parametrize("module_name", _ROUND2_MODULES)
def test_preserve_round2_module_does_not_reach_config_mail_write_path_or_spa(module_name):
    """R6.3: no Round-2-touched SAM module reaches the `config#mail` WRITE path
    (`config_write_service._shape_consent_notice`) — Round 2 only READS the notice
    (`get_consent_notice`), it never touches the write-shaper. (The in-app SPA form is a frontend
    artifact and cannot be imported by a Python module; its fragment is listed for completeness.)

    Order-independent: inspect only the NEWLY-imported modules (`sys.modules - before`).

    Validates (bugfix): Requirement 6.3
    """
    before = set(sys.modules)
    importlib.import_module(module_name)
    newly = set(sys.modules) - before
    leaked = [n for n in newly if any(frag in n for frag in _WRITE_PATH_FRAGMENTS)]
    assert leaked == [], (
        f"{module_name} must not reach the config#mail write path / in-app SPA (R6.3 — not "
        f"referenced/altered by Round 2); leaked: {leaked}"
    )
