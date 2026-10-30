"""
application-app task 2.6 — the CONSENT stamp + affirmative-consent gate on the PUBLIC
``create_application`` write (D26 / F4 / R12.1–R12.1c, seam b).

Each tenant authors its OWN versioned, bilingual consent/privacy notice (D26), projected onto
``config#mail`` (task 8.2) and read on the SAM plane via
``MembersProjectionReader.get_consent_notice`` / ``get_consent_notice_version`` (the accessors
task 2.6 adds, mirroring ``get_mail_domain`` / ``is_mail_enabled``). ``create_application``
consumes the version through the ``ConsentNoticeProvider`` seam. These pin the task-2.6
behaviours:

1. **Affirmative consent REQUIRED (F4/R12.1).** A submit WITHOUT affirmative consent is a HARD
   422 reject (one of the few on the public path, unlike the neutral-202 dup flag) — no record is
   written.
2. **Server-authoritative stamp (R12.1a/R12.1b/R12.1c).** On acceptance the record carries
   ``consent{version, accepted_at, locale}`` where the version is the TENANT's current notice
   version resolved SERVER-SIDE (never the client ``notice_version``), ``accepted_at`` is a
   server-minted UTC timestamp (any client timestamp IGNORED), and ``locale`` is the normalized
   applicant locale.
3. **A later notice revision never changes a stored record (R12.1a).** A record stamped with
   ``v1`` keeps ``v1`` after the tenant revises its notice to ``v2`` — the version is pinned at
   acceptance.
4. **Reader accessors** read the projected ``consent_notice`` row, degrading gracefully.

Validates: Requirements R12.1, R12.1a, R12.1b, R12.1c, F4
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from sam.members.domain._membership_errors import MemberValidationError
from sam.members.domain.consent_notice import StaticConsentNoticeProvider
from sam.members.domain.error_codes import CONSENT_REQUIRED
from sam.members.domain.fixed_fields import EnumOption
from sam.members.domain.field_resolver import (
    FixedFieldOverride,
    StaticOverlayProvider,
    TenantOverlay,
)
from sam.members.domain.membership_service import MembershipService

# Reuse the task-2.2 fake repo (member store + first-wins session claim + catalog surface) and
# the shared catalog-entry factory.
from sam.tests.test_create_application import _ApplicationRepo
from sam.tests.test_field_config_endpoint import _entry

TENANT = "h-dcn"


def _overlay_public_form() -> TenantOverlay:
    """Put the identity + membership_type fields on the PUBLIC form (application_visible)."""
    return TenantOverlay(
        overrides={
            "personal.first_name": FixedFieldOverride(application_visible=True),
            "personal.last_name": FixedFieldOverride(application_visible=True),
            "personal.email": FixedFieldOverride(application_visible=True),
            # birth_date on the form so the task-2.4 public-path identity requirement (R6.1a) is
            # satisfied on the success path (consent stamp runs before validation, but the create
            # still 422s on a missing DOB before returning a record).
            "personal.birth_date": FixedFieldOverride(application_visible=True),
            "membership.membership_type": FixedFieldOverride(
                application_visible=True,
                # 03b CONTRACT (Task 10.5): membership_type owns its vocabulary as INLINE options.
                options=(
                    EnumOption(value="gewoon", label={"nl": "Gewoon", "en": "Regular"}, allowed=True, order=10),
                ),
            ),
        },
    )


def _service(consent_version: str | None = "v1") -> MembershipService:
    """A service wired with a consent-notice provider resolving the tenant to ``consent_version``.

    ``consent_version=None`` models a tenant that authored NO well-formed notice (empty-is-valid):
    the applicant's affirmative consent is still required + recorded, with a ``None`` pinned
    version.
    """
    repo = _ApplicationRepo()
    repo.add_type(TENANT, _entry(TENANT, "gewoon", order=10))
    provider = StaticConsentNoticeProvider(
        {TENANT: consent_version} if consent_version is not None else {}
    )
    return MembershipService(
        repo,
        overlay_provider=StaticOverlayProvider({TENANT: _overlay_public_form()}),
        consent_notice_provider=provider,
    )


def _submission(**over):
    # email + name + birth_date are required on the public path (R6.1/R6.1a, enforced by task
    # 2.4); a baseline submission carries them so the success-path consent assertions can run.
    body = {
        "personal.first_name": "Sam",
        "personal.last_name": "Jansen",
        "personal.email": "sam@example.com",
        "personal.birth_date": "1990-05-01",
        "membership.membership_type": "gewoon",
    }
    body.update(over)
    return body


# ── 1. affirmative consent is REQUIRED (F4/R12.1) ─────────────────────────────────────


class TestConsentRequired:
    @pytest.mark.parametrize(
        "consent",
        [
            None,  # no consent block at all
            {},  # block present but no `accepted`
            {"accepted": False},  # explicitly not accepted
            {"accepted": "true"},  # a truthy STRING is not affirmative (fail-closed)
            {"accepted": 1},  # a truthy int is not affirmative
            {"notice_version": "v1"},  # a version but no acceptance
            "not-a-mapping",  # a non-mapping consent value
        ],
    )
    def test_submit_without_affirmative_consent_is_rejected(self, consent):
        service = _service()
        with pytest.raises(MemberValidationError) as exc:
            service.create_application(
                TENANT, _submission(), session_key="s1", consent=consent
            )
        # The reject surfaces on the synthetic `consent` key with the consent-required code.
        assert "consent" in exc.value.errors
        assert exc.value.errors["consent"].code == CONSENT_REQUIRED

    def test_rejected_submit_writes_no_record(self):
        # F4/R12.1: a submit without consent leaves NO record (the reject precedes save_member).
        service = _service()
        with pytest.raises(MemberValidationError):
            service.create_application(
                TENANT, _submission(), session_key="s1", consent=None
            )
        assert len(service._repo.members) == 0

    def test_affirmative_consent_is_accepted(self):
        service = _service()
        rec = service.create_application(
            TENANT, _submission(), session_key="s1", consent={"accepted": True}
        )
        assert rec["membership"]["status"] == "application"
        assert "consent" in rec


# ── 2. server-authoritative stamp: version + UTC timestamp + locale ───────────────────


class TestServerAuthoritativeStamp:
    def test_version_is_the_tenant_current_notice_version_server_resolved(self):
        # R12.1a: the stamped version is the tenant's CURRENT notice version (server-resolved).
        service = _service(consent_version="2026-01-notice")
        rec = service.create_application(
            TENANT, _submission(), session_key="s1", consent={"accepted": True}
        )
        assert rec["consent"]["version"] == "2026-01-notice"

    def test_client_supplied_notice_version_is_ignored(self):
        # R12.1a: a client-supplied notice_version must NOT win over the server-resolved version.
        service = _service(consent_version="server-v9")
        rec = service.create_application(
            TENANT,
            _submission(),
            session_key="s1",
            consent={"accepted": True, "notice_version": "client-spoofed-v1"},
        )
        assert rec["consent"]["version"] == "server-v9"
        assert rec["consent"]["version"] != "client-spoofed-v1"

    def test_accepted_at_is_a_server_utc_timestamp(self):
        # R12.1b: the acceptance timestamp is server-minted UTC (parseable, tz-aware, ~now).
        before = datetime.now(timezone.utc)
        service = _service()
        rec = service.create_application(
            TENANT, _submission(), session_key="s1", consent={"accepted": True}
        )
        after = datetime.now(timezone.utc)
        stamped = datetime.fromisoformat(rec["consent"]["accepted_at"])
        assert stamped.tzinfo is not None  # tz-aware (UTC)
        assert before <= stamped <= after

    def test_client_supplied_timestamp_is_ignored(self):
        # R12.1b: a client `accepted_at` must be IGNORED in favour of the server value.
        service = _service()
        rec = service.create_application(
            TENANT,
            _submission(),
            session_key="s1",
            consent={"accepted": True, "accepted_at": "1999-01-01T00:00:00+00:00"},
        )
        assert rec["consent"]["accepted_at"] != "1999-01-01T00:00:00+00:00"
        stamped = datetime.fromisoformat(rec["consent"]["accepted_at"])
        assert stamped.year >= 2024  # a real server timestamp, not the client's 1999 value

    @pytest.mark.parametrize(
        "submitted, expected",
        [("en", "en"), ("nl", "nl"), ("EN", "en"), (" nl ", "nl"), ("de", "nl"), (None, "nl")],
    )
    def test_locale_is_the_normalized_applicant_locale(self, submitted, expected):
        # R12.1a: the recorded consent locale is the normalized applicant locale (task 5.1).
        service = _service()
        rec = service.create_application(
            TENANT,
            _submission(),
            session_key="s1",
            locale=submitted,
            consent={"accepted": True},
        )
        assert rec["consent"]["locale"] == expected

    def test_consent_recorded_even_when_tenant_has_no_notice(self):
        # R12.1c: a tenant that authored no notice → version None, but consent is still recorded
        # (the affirmative acceptance + server timestamp + locale), never a reject on the version.
        service = _service(consent_version=None)
        rec = service.create_application(
            TENANT, _submission(), session_key="s1", consent={"accepted": True}
        )
        assert rec["consent"]["version"] is None
        assert rec["consent"]["accepted_at"]
        assert rec["consent"]["locale"] == "nl"


# ── 3. a later notice revision never changes a stored record (R12.1a) ─────────────────


class TestVersionPinnedAtAcceptance:
    def test_later_revision_does_not_change_a_stored_record(self):
        # A record stamped under v1 keeps v1 after the tenant revises its notice to v2. Model the
        # revision by swapping the provider's resolved version between two submits.
        repo = _ApplicationRepo()
        repo.add_type(TENANT, _entry(TENANT, "gewoon", order=10))
        provider = StaticConsentNoticeProvider({TENANT: "v1"})
        service = MembershipService(
            repo,
            overlay_provider=StaticOverlayProvider({TENANT: _overlay_public_form()}),
            consent_notice_provider=provider,
        )

        first = service.create_application(
            TENANT, _submission(), session_key="s1", consent={"accepted": True}
        )
        assert first["consent"]["version"] == "v1"
        stored_member_id = first["member_id"]

        # The tenant revises its notice → the provider now resolves v2 for NEW submits.
        provider._version_by_tenant[TENANT] = "v2"

        # A DISTINCT new applicant now stamps v2 …
        second = service.create_application(
            TENANT,
            _submission(**{"personal.email": "new@e.com"}),
            session_key="s2",
            consent={"accepted": True},
        )
        assert second["consent"]["version"] == "v2"

        # … but the EARLIER record's stored version is untouched by the revision (R12.1a).
        assert repo.members[(TENANT, stored_member_id)]["consent"]["version"] == "v1"


# ── 4. the SAM read-side accessors over the projected config#mail row ─────────────────


class _NoticeReader:
    """A ``MembersProjectionReader`` over a single pre-seeded ``config#mail`` partition.

    Avoids boto3: it pre-seeds the reader's per-invocation partition cache with one tenant
    partition carrying a ``config#mail`` row, so ``get_consent_notice`` /
    ``get_consent_notice_version`` read it exactly as they would a real projected row.
    """

    @staticmethod
    def reader(consent_notice):
        from sam.members.repository.projection_config_reader import MembersProjectionReader
        from services import projection_schema as schema

        row = {
            schema.PARTITION_KEY_ATTR: TENANT,
            schema.SORT_KEY_ATTR: f"{schema.RECORD_TYPE_CONFIG}#{schema.CONFIG_ID_MAIL}",
        }
        if consent_notice is not None:
            row["consent_notice"] = consent_notice
        r = MembersProjectionReader(table=object())  # table never queried (cache pre-seeded)
        r._partition_cache[TENANT] = [row]
        return r


class TestReaderAccessors:
    def test_well_formed_notice_is_returned(self):
        reader = _NoticeReader.reader(
            {"version": "v1", "text": {"nl": "Privacyverklaring", "en": "Privacy notice"}}
        )
        notice = reader.get_consent_notice(TENANT)
        assert notice == {
            "version": "v1",
            "text": {"nl": "Privacyverklaring", "en": "Privacy notice"},
        }
        assert reader.get_consent_notice_version(TENANT) == "v1"

    def test_absent_notice_resolves_to_none(self):
        reader = _NoticeReader.reader(None)  # config#mail row present, no consent_notice attr
        assert reader.get_consent_notice(TENANT) is None
        assert reader.get_consent_notice_version(TENANT) is None

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
    def test_malformed_notice_degrades_to_none(self, notice):
        reader = _NoticeReader.reader(notice)
        assert reader.get_consent_notice(TENANT) is None
        assert reader.get_consent_notice_version(TENANT) is None

    def test_blank_locale_bodies_are_dropped_from_text(self):
        reader = _NoticeReader.reader(
            {"version": "v1", "text": {"nl": "ok", "en": "   ", "de": 5}}
        )
        assert reader.get_consent_notice(TENANT) == {"version": "v1", "text": {"nl": "ok"}}
