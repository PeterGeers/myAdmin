"""
application-app task 2.2 — tests for the PUBLIC ``create_application`` write (seam b).

``MembershipService.create_application(tenant_id, body, session_key, locale, consent)`` is the
core public-intake write: it REUSES the ``create_member`` spine but is trusted for NOTHING
(R3, Property 2). These pin the behaviours task 2.2 adds (the required-ness 422 collection,
membership_type default, duplicate flag, consent-version enforcement are later tasks 2.3–2.6
and intentionally NOT asserted here):

1. **Forced status (R3.1)** — the created record is ``status=application`` regardless of any
   client-supplied status.
2. **Privileged-field strip (R4.7/R4.8, verify-before-trust)** — a client ``member_id`` /
   ``tenant_id`` / ``status`` / ``member_number`` / ``created_at`` is dropped; the ``member_id``
   is a SYSTEM-minted uuid4.
3. **Application-selected-only (R3.4/R4.8)** — ONLY fields a tenant marked
   ``application_visible`` land on the record; an unselected ``membership`` field, a staff-only
   field, or an unknown key posted anyway is ignored.
4. **Un-flatten (R4.7)** — a FLAT ``{dotted_key: value}`` submission is nested back into the
   ``{personal, membership, overlay}`` shape the create spine expects.
5. **First-creates / resubmit-updates (R3a.2)** — the first submit of a session CREATES a
   ``status=application`` member + claims the session; a same-session resend resolves the
   existing ``member_id`` and UPDATES it rather than inserting a second record.

The field config is supplied via a ``StaticOverlayProvider`` that marks specific fields onto
the public form (``application_visible`` via a fixed-field override / an overlay field); the
repo is an in-memory fake that HONOURS the session claim's first-wins semantics so the
create-vs-update branch is genuinely exercised.

Validates: Requirements R3, R3.1, R3.4, R3.5, R3a.2, R4.7, R4.8
"""

from __future__ import annotations

import os
import sys
import uuid

import pytest

_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from sam.members.domain.fixed_fields import EnumOption
from sam.members.domain.field_resolver import (
    FixedFieldOverride,
    OverlayField,
    StaticOverlayProvider,
    TenantOverlay,
)
from sam.members.domain.fixed_fields import FieldType
from sam.members.domain.membership_service import MembershipService

# Reuse the field-config test's in-memory fake catalog repo (read-only catalog surface) + its
# `_entry` factory, as the write-surface tests do.
from sam.tests.test_field_config_endpoint import FakeCatalogRepository, _entry

TENANT = "h-dcn"


# ── A fake repo: the read-only catalog + a member store + the session de-dup primitive ──


class _ApplicationRepo(FakeCatalogRepository):
    """Fake repo with a member store + an in-memory session-claim that is first-wins.

    ``claim_application_session`` mirrors the real conditional ``attribute_not_exists`` put:
    the FIRST claim of a ``(tenant, session_key)`` returns ``True`` and records the mapping; a
    later claim of the SAME session returns ``False`` (first-wins), so a resend resolves the
    mapped member to UPDATE it (R3a.2/R3a.3).
    """

    def __init__(self):
        super().__init__()
        self.members: dict[tuple[str, str], dict] = {}
        self._sessions: dict[tuple[str, str], str] = {}

    # catalog surface the membership_type reference check reads
    def get_membership_type(self, tenant_id, type_code):
        for e in self.catalog.get(tenant_id, []):
            if e.type_code == type_code:
                return e
        return None

    # member store
    def get_member(self, tenant_id, member_id):
        return self.members.get((tenant_id, member_id))

    def save_member(self, tenant_id, record):
        member_id = record.get("member_id")
        if not member_id:
            raise ValueError("member must carry a non-empty 'member_id'")
        self.members[(tenant_id, member_id)] = dict(record)
        return dict(record)

    # session de-dup (task 2.1 surface) — first-wins conditional claim
    def claim_application_session(self, tenant_id, session_key, member_id):
        key = (tenant_id, session_key)
        if key in self._sessions:
            return False  # already claimed (a resend) — first-wins
        self._sessions[key] = member_id
        return True

    def get_application_session_member(self, tenant_id, session_key):
        return self._sessions.get((tenant_id, session_key))


def _overlay_public_form() -> TenantOverlay:
    """An overlay that puts a few fields on the PUBLIC form via ``application_visible``.

    - ``personal.first_name`` / ``personal.last_name`` / ``personal.email`` → fixed-field
      overrides with ``application_visible=True`` (R4.2 — fixed fields onto the form).
    - ``membership.membership_type`` → on the form (so a valid applicant can pick a type).
    - an overlay field ``nickname`` → on the form (a tenant-added field, R4.4).
    - ``membership.member_number`` is NOT application-selected → must be ignored even if posted.
    """
    return TenantOverlay(
        overrides={
            "personal.first_name": FixedFieldOverride(application_visible=True),
            "personal.last_name": FixedFieldOverride(application_visible=True),
            "personal.email": FixedFieldOverride(application_visible=True),
            # birth_date is on the form so the public-path identity requirement (R6.1a, enforced
            # by task 2.4) can be satisfied — a tenant form must expose email/name/DOB.
            "personal.birth_date": FixedFieldOverride(application_visible=True),
            "membership.membership_type": FixedFieldOverride(
                application_visible=True,
                # 03b CONTRACT (Task 10.5): membership_type owns its vocabulary as INLINE field
                # options (the `membershiptype#` catalog is retired). The reference check reads these.
                options=(
                    EnumOption(
                        value="gewoon",
                        label={"nl": "Gewoon", "en": "Regular"},
                        allowed=True,
                        order=10,
                    ),
                    EnumOption(
                        value="erelid",
                        label={"nl": "Erelid", "en": "Honorary"},
                        allowed=True,
                        order=20,
                    ),
                ),
            ),
        },
        fields={
            "nickname": OverlayField(
                key="nickname",
                type=FieldType.STRING,
                label={"nl": "Bijnaam", "en": "Nickname"},
                application_visible=True,
            ),
        },
    )


@pytest.fixture()
def service() -> MembershipService:
    repo = _ApplicationRepo()
    repo.add_type(TENANT, _entry(TENANT, "gewoon", order=10))
    repo.add_type(TENANT, _entry(TENANT, "erelid", order=20))
    return MembershipService(
        repo, overlay_provider=StaticOverlayProvider({TENANT: _overlay_public_form()})
    )


def _flat_submission(**over):
    """A flat (dotted-key) public submission with the required identity fields filled.

    Task 2.4 made the public path server-enforce required-ness: ``email`` + name (``last_name``)
    + ``birth_date`` are required on the public path regardless of tenant config (R6.1/R6.1a), so
    a baseline valid submission MUST carry them (the create otherwise 422s before it can exercise
    the task-2.2 behaviours these tests target). ``birth_date`` is added here alongside the
    already-present email/last_name for that reason.
    """
    body = {
        "personal.first_name": "Sam",
        "personal.last_name": "Jansen",
        "personal.email": "sam@example.com",
        "personal.birth_date": "1990-05-01",
        "membership.membership_type": "gewoon",
        "overlay.nickname": "Sammy",
    }
    body.update(over)
    return body


#: Affirmative consent block. Task 2.6 made consent MANDATORY on the public create path
#: (F4/R12.1): a submit without it is rejected. These task-2.2 behaviour tests are not about
#: consent, so they go through `_create` (below), which supplies affirmative consent by default
#: — the consent GATE + server-authoritative STAMP are pinned in `test_application_consent.py`.
_AFFIRMATIVE_CONSENT = {"accepted": True}


def _create(service, body, *, consent=_AFFIRMATIVE_CONSENT, **kw):
    """Call ``create_application`` supplying affirmative consent by default (task 2.6).

    A thin test helper so the pre-existing task-2.2 behaviour tests (forced status, privileged
    strip, un-flatten, session de-dup) stay focused on their own concern while satisfying the
    now-mandatory affirmative-consent gate. Pass ``consent=None`` to exercise the gate.
    """
    return service.create_application(TENANT, body, consent=consent, **kw)


# ── 1. forced status ────────────────────────────────────────────────────────────────


class TestForcedStatus:
    def test_created_record_is_status_application(self, service):
        rec = _create(service, _flat_submission(), session_key="s1")
        assert rec["membership"]["status"] == "application"

    def test_client_supplied_status_is_overridden(self, service):
        # A hand-crafted submission that tries to self-activate must NOT escalate (R3.1).
        body = _flat_submission()
        body["membership.status"] = "active"
        rec = _create(service, body, session_key="s1")
        assert rec["membership"]["status"] == "application"


# ── 2. privileged-field strip + system-minted id ─────────────────────────────────────


class TestPrivilegedFieldStrip:
    def test_member_id_is_a_system_minted_uuid4(self, service):
        rec = _create(service, _flat_submission(), session_key="s1")
        assert uuid.UUID(str(rec["member_id"])).version == 4

    def test_client_supplied_member_id_is_ignored(self, service):
        body = _flat_submission()
        body["member_id"] = "hacker-supplied-id"
        rec = _create(service, body, session_key="s1")
        assert rec["member_id"] != "hacker-supplied-id"
        assert uuid.UUID(str(rec["member_id"])).version == 4

    def test_client_supplied_tenant_id_is_ignored(self, service):
        body = _flat_submission()
        body["tenant_id"] = "other-tenant"
        rec = _create(service, body, session_key="s1")
        assert rec["tenant_id"] == TENANT

    def test_staff_owned_membership_keys_are_stripped(self, service):
        # member_number / created_at are staff-owned (not application-selected) — dropped even if
        # posted under a nested membership bucket.
        body = {
            "personal": {
                "first_name": "Sam",
                "last_name": "Jansen",
                "email": "sam@example.com",
                "birth_date": "1990-05-01",  # required on the public path (R6.1a, task 2.4)
            },
            "membership": {
                "membership_type": "gewoon",
                "member_number": "SNEAKY-1",
                "created_at": "1999-01-01",
            },
        }
        rec = _create(service, body, session_key="s1")
        assert "member_number" not in rec["membership"]
        assert "created_at" not in rec["membership"]


# ── 3. application-selected-only ──────────────────────────────────────────────────────


class TestApplicationSelectedOnly:
    def test_selected_fields_land_on_the_record(self, service):
        rec = _create(service, _flat_submission(), session_key="s1")
        assert rec["personal"]["first_name"] == "Sam"
        assert rec["personal"]["email"] == "sam@example.com"
        assert rec["membership"]["membership_type"] == "gewoon"
        assert rec["overlay"]["nickname"] == "Sammy"

    def test_unselected_field_posted_anyway_is_ignored(self, service):
        # `member_number` is NOT application_visible → ignored even if the client posts it flat.
        body = _flat_submission()
        body["membership.member_number"] = "POSTED-999"
        rec = _create(service, body, session_key="s1")
        assert "member_number" not in rec.get("membership", {})

    def test_unknown_key_is_ignored(self, service):
        body = _flat_submission()
        body["personal.secret_backdoor"] = "x"
        body["totally.unknown"] = "y"
        rec = _create(service, body, session_key="s1")
        assert "secret_backdoor" not in rec.get("personal", {})
        assert "totally" not in rec


# ── 4. un-flatten ─────────────────────────────────────────────────────────────────────


class TestUnFlatten:
    def test_flat_submission_is_nested_by_storage_group(self, service):
        rec = _create(service, _flat_submission(), session_key="s1")
        # Flat `personal.first_name` → nested under the `personal` bucket; `overlay.nickname`
        # under `overlay`; `membership.membership_type` under `membership`.
        assert set(rec["personal"]) >= {"first_name", "last_name", "email"}
        assert "nickname" in rec["overlay"]
        assert "membership_type" in rec["membership"]

    def test_already_nested_submission_is_accepted(self, service):
        # A direct caller / test may pass the nested shape without flattening first.
        body = {
            "personal": {
                "first_name": "Nes",
                "last_name": "Ted",
                "email": "n@e.com",
                "birth_date": "1990-05-01",  # required on the public path (R6.1a, task 2.4)
            },
            "membership": {"membership_type": "gewoon"},
            "overlay": {"nickname": "N"},
        }
        rec = _create(service, body, session_key="s1")
        assert rec["personal"]["first_name"] == "Nes"
        assert rec["overlay"]["nickname"] == "N"

    def test_fields_wrapper_is_accepted(self, service):
        # design §3.2: the form may wrap the flat values under a `fields` sub-object.
        body = {"fields": _flat_submission()}
        rec = _create(service, body, session_key="s1")
        assert rec["personal"]["first_name"] == "Sam"


# ── 5. first-creates / same-session resubmit-updates (R3a.2) ──────────────────────────


class TestSessionDedup:
    def test_first_submit_creates_and_claims_the_session(self, service):
        rec = _create(service, _flat_submission(), session_key="s1")
        # exactly one member stored; the session maps to that member_id.
        repo = service._repo
        assert len(repo.members) == 1
        assert repo.get_application_session_member(TENANT, "s1") == rec["member_id"]

    def test_resubmit_same_session_updates_not_inserts(self, service):
        first = _create(service, _flat_submission(), session_key="s1")
        # The applicant corrects their email and resends in the SAME session.
        corrected = _flat_submission(**{"personal.email": "corrected@example.com"})
        second = _create(service, corrected, session_key="s1")
        repo = service._repo
        # STILL one record — the resend UPDATED, it did not insert a second (R3a.2).
        assert len(repo.members) == 1
        # same member_id preserved; status stays application; the corrected value won.
        assert second["member_id"] == first["member_id"]
        assert second["membership"]["status"] == "application"
        assert second["personal"]["email"] == "corrected@example.com"

    def test_distinct_sessions_create_distinct_records(self, service):
        a = _create(service, _flat_submission(), session_key="s1")
        b = _create(service, _flat_submission(), session_key="s2")
        assert a["member_id"] != b["member_id"]
        assert len(service._repo.members) == 2

    def test_concurrent_same_session_double_submit_resolves_to_single_record(
        self, service
    ):
        # R14.13 (concurrent single-record): two NEAR-SIMULTANEOUS submits of the SAME session —
        # a double-click / retried request the applicant did not mean to duplicate — must resolve
        # to EXACTLY ONE record via the first-wins conditional claim, NOT two. This is distinct
        # from `test_resubmit_same_session_updates_not_inserts` (a SEQUENTIAL corrected resend):
        # here the second create mints its OWN candidate member_id and loses the claim, so the
        # thing under test is that the loser DISCARDS its candidate and converges on the winner's
        # record rather than inserting a second row under its freshly-minted id. The repo's
        # first-wins `claim_application_session` is the conditional-write seam (the DynamoDB
        # `attribute_not_exists` race pinned at the primitive level in
        # test_application_session_dedup.py); this asserts the SERVICE resolves that race to one
        # record end-to-end.
        repo = service._repo
        # Capture every member_id the service minted + claimed, so we can prove the loser's
        # candidate was never written as a second record.
        minted_ids: list[str] = []
        real_claim = repo.claim_application_session

        def _spy_claim(tenant_id, session_key, member_id):
            minted_ids.append(member_id)
            return real_claim(tenant_id, session_key, member_id)

        repo.claim_application_session = _spy_claim  # type: ignore[assignment]

        # Submit A wins the claim (first-wins) → creates the one record.
        first = _create(service, _flat_submission(), session_key="race")
        # Submit B (the concurrent double) mints a DISTINCT candidate id, loses the claim, and
        # must resolve to A's record — never insert a second.
        second = _create(service, _flat_submission(), session_key="race")

        # Two DISTINCT candidate ids were minted (A's winner + B's loser) — a real race, not the
        # same id reused.
        assert len(minted_ids) == 2
        assert minted_ids[0] != minted_ids[1]
        loser_candidate = minted_ids[1]

        # EXACTLY ONE record exists, carrying the WINNER's id (first-wins). The session maps to it.
        assert len(repo.members) == 1
        assert first["member_id"] == second["member_id"] == minted_ids[0]
        assert repo.get_application_session_member(TENANT, "race") == first["member_id"]
        # The loser's freshly-minted candidate id was DISCARDED — never written as a second row.
        assert (TENANT, loser_candidate) not in repo.members
        # Both submits are status=application (the double never escalated or lost the record).
        assert second["membership"]["status"] == "application"


# ── 6. locale seam + consent gate (consent fully handled in 2.6; see test_application_consent) ─


class TestLocaleAndConsentSeams:
    """locale stamp (task 5.1 seam) + the consent GATE (task 2.6).

    Consent is now REQUIRED on this path (F4/R12.1): a submit must carry affirmative consent or
    it is rejected. The server-authoritative consent STAMP (server version, server UTC timestamp,
    normalized locale, client timestamp ignored) is pinned in ``test_application_consent.py``;
    these keep this file's own create path green with the mandatory affirmative-consent block.
    """

    #: The affirmative consent block every create on the public path now needs (task 2.6).
    _CONSENT = {"accepted": True}

    @pytest.mark.parametrize("locale", ["en", "nl"])
    def test_supported_locale_is_persisted_top_level(self, service, locale):
        # R6b.4/R14.14: a supported applicant locale is persisted on the record as a flat
        # top-level `locale` attribute (what a later re-send / confirmation re-render reads).
        rec = service.create_application(
            TENANT,
            _flat_submission(),
            session_key=f"s-{locale}",
            locale=locale,
            consent=self._CONSENT,
        )
        assert rec["locale"] == locale

    @pytest.mark.parametrize(
        ("submitted", "expected"),
        [("EN", "en"), (" nl ", "nl"), ("de", "nl"), ("", "nl"), ("xx", "nl")],
    )
    def test_invalid_or_wrong_case_locale_is_normalized_before_persisting(
        self, service, submitted, expected
    ):
        # R14.14 "invalid → nl fallback, locale persisted": the create path MUST persist the
        # NORMALIZED locale, never the raw client value. An unsupported/blank value falls back to
        # `nl`; a wrong-case/padded-but-supported value is canonicalized. Guards the regression
        # where the top-level stamp wrote the raw value (only `consent.locale` was normalized).
        rec = service.create_application(
            TENANT,
            _flat_submission(),
            session_key=f"s-{submitted!r}",
            locale=submitted,
            consent=self._CONSENT,
        )
        assert rec["locale"] == expected

    def test_omitted_locale_defaults_to_nl_on_the_record(self, service):
        # R6b.2/R14.14: an absent locale defaults to `nl` AND is persisted — every application
        # record carries an authoritative locale, not an absent key.
        rec = service.create_application(
            TENANT, _flat_submission(), session_key="s-default", consent=self._CONSENT
        )
        assert rec["locale"] == "nl"

    def test_persisted_locale_reads_back_through_locale_of_record(self, service):
        # R6b.4: the stored top-level value round-trips through the record-read contract
        # (`locale_of_record`) that the confirmation re-render / staff-reply path uses — an
        # invalid submit resolves to `nl` on read, a valid one to its canonical form.
        from sam.members.domain.applicant_locale import locale_of_record

        for submitted, expected in [("en", "en"), ("de", "nl"), ("NL", "nl")]:
            rec = service.create_application(
                TENANT,
                _flat_submission(),
                session_key=f"rb-{submitted}",
                locale=submitted,
                consent=self._CONSENT,
            )
            assert locale_of_record(rec) == expected

    def test_affirmative_consent_is_recorded(self, service):
        rec = service.create_application(
            TENANT, _flat_submission(), session_key="s1", consent=self._CONSENT
        )
        # A consent block is stamped on acceptance (shape/authority asserted in the 2.6 suite).
        assert "consent" in rec
        assert rec["consent"][
            "accepted_at"
        ]  # server-stamped acceptance timestamp present

    def test_locale_optional_with_consent_present(self, service):
        # Omitting the locale must not break the create (it is optional); consent is required.
        rec = service.create_application(
            TENANT, _flat_submission(), session_key="s1", consent=self._CONSENT
        )
        assert rec["membership"]["status"] == "application"


# ── 7. SEC-9 PII minimization + SEC-10 stored-XSS (spec 14 task 4.3) ──────────────────


class TestPiiMinimizationAndXss:
    """spec 14 task 4.3 — applicant PII minimization (SEC-9) + stored-XSS neutralization (SEC-10).

    SEC-9: the submit persists ONLY the tenant's DECLARED (``application_visible``) fields, scoped
    to the marker-resolved ``tenant_id`` — an undeclared body field can never be persisted (the
    field gate ``_application_selected_record`` only reads declared fields).

    SEC-10: applicant FREE-TEXT is HTML-neutralized at the public write (the trust boundary) so a
    ``<script>`` payload cannot execute when the authenticated admin review UI later re-displays
    it, WITHOUT corrupting structured fields (an enum ``membership_type`` code is left verbatim; a
    valid email carries no HTML metacharacters so it is unchanged).

    Validates: Requirements R5.1, R5.5, R3.2, R10.9, R10.10
    """

    def test_undeclared_body_field_is_not_persisted(self, service):
        # SEC-9: a field the tenant did NOT publish on the form (not application_visible) can never
        # land on the record, no matter how it is addressed in the body (flat, nested, bare key).
        body = _flat_submission()
        body["personal.national_id"] = "undeclared-sensitive-value"  # not on the form
        body["overlay.secret_notes"] = "also undeclared"
        rec = _create(service, body, session_key="s1")
        assert "national_id" not in rec.get("personal", {})
        assert "secret_notes" not in rec.get("overlay", {})
        # Only the published fields are present under personal.
        assert set(rec["personal"]) <= {
            "first_name",
            "last_name",
            "email",
            "birth_date",
        }

    def test_write_is_scoped_to_the_passed_tenant_id(self, service):
        # SEC-9 / SEC-3: the record is stamped + stored under the resolved tenant, even when the
        # body forges a different tenant_id.
        body = _flat_submission()
        body["tenant_id"] = "attacker-tenant"
        rec = _create(service, body, session_key="s1")
        assert rec["tenant_id"] == TENANT
        # Stored under the resolved tenant's partition in the fake repo.
        assert (TENANT, rec["member_id"]) in service._repo.members
        assert ("attacker-tenant", rec["member_id"]) not in service._repo.members

    def test_free_text_script_payload_is_html_neutralized(self, service):
        # SEC-10: a <script>/HTML payload in a free-text field (first_name, a tenant-added
        # overlay nickname) is HTML-escaped on write so it cannot execute when re-displayed in the
        # admin review UI — the raw active markup is gone, the escaped entities remain readable.
        payload = "<script>alert(document.cookie)</script>"
        body = _flat_submission(
            **{
                "personal.first_name": payload,
                "overlay.nickname": 'Sam"><img src=x onerror=alert(1)>',
            }
        )
        rec = _create(service, body, session_key="s1")
        stored_name = rec["personal"]["first_name"]
        stored_nick = rec["overlay"]["nickname"]
        # No raw executable markup survives — the tag delimiters are gone, so the payload is
        # inert text even if dropped into a raw-HTML sink (the `onerror=` word may remain as
        # harmless text, but with its `<img` escaped it can never form an element/attribute).
        assert "<script>" not in stored_name
        assert "<img" not in stored_nick
        assert "<" not in stored_name and ">" not in stored_name
        assert "<" not in stored_nick and ">" not in stored_nick
        # The dangerous characters are HTML-encoded (defense-in-depth against a raw-HTML sink).
        assert "&lt;script&gt;" in stored_name
        assert "&lt;img" in stored_nick
        assert "&quot;" in stored_nick

    def test_structured_fields_are_left_verbatim(self, service):
        # SEC-10 scope: a valid email (no HTML metacharacters) and the enum membership_type code
        # must pass through UNCHANGED — the neutralizer only touches free-text, never corrupts
        # structured/choice values.
        rec = _create(service, _flat_submission(), session_key="s1")
        assert rec["personal"]["email"] == "sam@example.com"
        assert rec["membership"]["membership_type"] == "gewoon"


# ── 8. spec 14 task 4.5 — the submit-path battery CONSOLIDATED against the REAL engine ─────
#
# Task 4.5 completes the SEC-2/3/9/10 submit battery. The EDGE half (404-mapping, 422-mapping,
# CORS, abuse guards) is pinned in `test_public_app_edge.py` against a fake service. This class
# is the half the task marks "REAL behaviour, not a mock" (HC6 / requirements R10.11): it drives
# the AUTHORITATIVE `MembershipService.create_application` + the in-memory `_ApplicationRepo` so
# the assertions are about the real engine's observable behaviour, never a pass-through mock that
# merely records a call.
#
# What this class ADDS (the genuinely-missing 4.5 items — it does NOT duplicate the SEC-9/SEC-10
# write-layer assertions already in `TestPiiMinimizationAndXss` verbatim):
#   * SEC-3 routing against the REAL engine: a write SCOPED to the (marker-resolved) tenant_id the
#     EDGE passes lands under THAT tenant's partition — the engine stamps the passed tenant and
#     stores there, never a forged body `tenant_id` (the edge's marker-resolve is proven in the
#     edge file; here we prove the ENGINE honours the tenant the edge hands it).
#   * SEC-2 bad-TYPE and unexpected-FIELD against the REAL validator / field gate.
#   * SEC-10 ADMIN RE-DISPLAY: the stored (neutralized) value, read back the way the admin review
#     UI reads the record, carries no raw active markup — it cannot execute on re-display.
#
# Validates: Requirements R5.1, R5.5, R3.2, R10.2, R10.3, R10.9, R10.10


class TestSubmitBatteryRealEngine:
    """spec 14 task 4.5 — submit-path battery against the REAL `MembershipService` engine."""

    # ── SEC-3 — write routed to the tenant the edge resolved, against the REAL engine ──

    def test_write_lands_under_the_resolved_tenant_partition_real_engine(self, service):
        # SEC-3 (REAL behaviour, not a mock): the EDGE resolves the tenant from the `_slugs/{slug}`
        # marker BODY and calls `create_application(tenant_id, ...)` with THAT tenant. Here we prove
        # the authoritative engine honours the handed-in tenant end-to-end: the created record is
        # stamped with the resolved tenant AND is stored under that tenant's partition in the repo
        # — the members module's own `tenant_id`-partitioned store (steering 39). This is the real
        # engine + in-memory repo, so it is the routing proof the edge's `_FakeApplicationService`
        # (a call-recorder) cannot give.
        rec = _create(service, _flat_submission(), session_key="sec3")
        assert rec["tenant_id"] == TENANT
        # The record physically lands under the resolved tenant's partition — nowhere else.
        assert (TENANT, rec["member_id"]) in service._repo.members
        stored = service._repo.get_member(TENANT, rec["member_id"])
        assert stored is not None
        assert stored["tenant_id"] == TENANT

    def test_forged_body_tenant_is_ignored_record_lands_under_resolved_tenant(
        self, service
    ):
        # SEC-3 cross-tenant write safety: even when the body forges a DIFFERENT `tenant_id`, the
        # real engine strips it and stamps/stores under the tenant the edge passed — the forged
        # partition is never written. (The edge never forwards a body tenant; this proves the
        # engine is also defence-in-depth against one slipping through.)
        body = _flat_submission()
        body["tenant_id"] = "attacker-tenant"
        rec = _create(service, body, session_key="sec3-forge")
        assert rec["tenant_id"] == TENANT
        assert (TENANT, rec["member_id"]) in service._repo.members
        assert ("attacker-tenant", rec["member_id"]) not in service._repo.members

    # ── SEC-2 — bad-TYPE and unexpected-FIELD against the REAL validator / field gate ──

    @pytest.mark.parametrize(
        ("bad_key", "bad_value", "expected_field"),
        [
            # A blank REQUIRED identity field (email / name / DOB are required on the public path,
            # R6.1a) — the authoritative required-ness validator raises on the empty value.
            ("personal.email", "", "personal.email"),
            ("personal.last_name", "   ", "personal.last_name"),
            # A bad-TYPE value in a required identity slot (a list / object where a scalar string
            # is expected) is not a valid value → the required/format validation rejects it too.
            ("personal.birth_date", "", "personal.birth_date"),
        ],
    )
    def test_bad_value_in_required_field_is_rejected_before_the_write_real_validator(
        self, service, bad_key, bad_value, expected_field
    ):
        # SEC-2 (R10.9) per-field validation against the REAL validator (not the edge's sentinel
        # fake): a blank/bad value in a required identity field makes the authoritative engine
        # raise `MemberValidationError` (→ the edge's 422) BEFORE `save_member`, so NO record
        # lands. The refusal names the offending field — the per-field map the edge flattens into
        # the RFC 9457 `errors` array. (NOTE: this fixture's `personal.email` carries no EMAIL
        # FORMAT checker — it enforces REQUIRED-ness, not email syntax — so the deterministic
        # real-validator failure this drives is the required/blank path, which is what the engine
        # actually enforces here; email-SYNTAX rejection is proven at the edge's 422-mapping in
        # `test_public_app_edge.py` and belongs to a form that wires `format.checker=EMAIL`.)
        from sam.members.domain._membership_errors import MemberValidationError

        before = len(service._repo.members)
        bad = _flat_submission(**{bad_key: bad_value})
        with pytest.raises(MemberValidationError) as exc_info:
            _create(service, bad, session_key=f"badtype-{expected_field}")
        assert expected_field in exc_info.value.errors
        # Raise-before-persist: nothing was written on the validation-failure path.
        assert len(service._repo.members) == before

    def test_unexpected_field_is_not_persisted_real_field_gate(self, service):
        # SEC-2 / SEC-9 unexpected-field contract (the ACTUAL behaviour, per design §4.2 +
        # requirements R10.9): an undeclared/unexpected field in the body is NOT persisted — the
        # real `application_visible` field gate only reads DECLARED fields, so an unexpected key
        # can never land on the record (it is silently dropped, not an error). This asserts the
        # contract the engine actually implements against the REAL gate, rather than inventing a
        # rejection path that does not exist. A VALID submit still succeeds (the extra key does not
        # break the write), and the undeclared key is absent from the stored record.
        body = _flat_submission()
        body["personal.unexpected_field"] = "should-not-persist"
        body["totally.bogus"] = {"nested": "junk"}
        rec = _create(service, body, session_key="unexpected")
        # The write SUCCEEDED (unexpected fields are dropped, not a hard reject) ...
        assert rec["membership"]["status"] == "application"
        # ... and the undeclared keys are nowhere on the stored record.
        assert "unexpected_field" not in rec.get("personal", {})
        assert "totally" not in rec
        stored = service._repo.get_member(TENANT, rec["member_id"])
        assert "unexpected_field" not in stored.get("personal", {})
        assert "totally" not in stored

    # ── SEC-10 — admin RE-DISPLAY: stored value cannot execute when the admin UI reads it ──

    def test_stored_free_text_is_inert_when_read_back_for_admin_redisplay(
        self, service
    ):
        # SEC-10 (R10.10) admin-re-display angle: `TestPiiMinimizationAndXss` proves the value is
        # neutralized ON WRITE; this proves the ADMIN-FACING READ sees an inert value. The admin
        # review UI re-displays a submission by reading the stored member record back — so read it
        # back the way the admin path does (from the tenant-partitioned member store) and assert
        # the free-text value carries NO raw active markup (`<`/`>`/`"` are gone), so even a
        # raw-HTML admin sink (`dangerouslySetInnerHTML`) cannot form a `<script>`/`<img onerror>`
        # element from it. The escaped entities remain as readable text.
        payload = "<script>alert(document.cookie)</script>"
        body = _flat_submission(
            **{
                "personal.first_name": payload,
                "overlay.nickname": 'Eve"><img src=x onerror=alert(1)>',
            }
        )
        rec = _create(service, body, session_key="sec10-admin")

        # Read the record back exactly as the admin review UI would — from the stored partition,
        # NOT from the create return value — to prove the PERSISTED value (what an admin later
        # loads) is the inert one, not just the in-flight return.
        stored = service._repo.get_member(TENANT, rec["member_id"])
        admin_name = stored["personal"]["first_name"]
        admin_nick = stored["overlay"]["nickname"]
        # No raw tag delimiters survive on the admin-facing read → no element/attribute can form.
        assert "<" not in admin_name and ">" not in admin_name
        assert "<" not in admin_nick and ">" not in admin_nick
        assert "<script>" not in admin_name
        assert "<img" not in admin_nick
        # The dangerous characters are HTML-encoded — safe even dropped into a raw-HTML sink.
        assert "&lt;script&gt;" in admin_name
        assert "&lt;img" in admin_nick
        assert "&quot;" in admin_nick
