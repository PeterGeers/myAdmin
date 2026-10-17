"""
application-app task 2.5 — tests for the FLAG-ONLY name+DOB duplicate flag in
``create_application`` (R3a.5–R3a.8, D25).

The automatic duplicate flag matches on NORMALIZED name + date of birth (NOT email, both
required — R6.1a) via the tenant-scoped ``name_dob_index`` GSI. When the applicant's name+DOB
matches an EXISTING member, a stable ``DUP`` keyword is appended to the new record's
``overlay.additional_info`` for staff review. These pin the four behaviours of the flag:

1. **Dup detected → DUP note** — a name+DOB match appends ``DUP`` to ``overlay.additional_info``.
2. **No dup → no note** — a non-matching submission carries no ``DUP`` keyword.
3. **Dup NEVER blocks + response unchanged** — the matched application is STILL created
   (``status=application``), exactly like an unmatched one (R3a.5/R3a.7 — no enumeration oracle).
4. **Self is excluded** — a same-session resubmit does not flag itself against its own GSI row.

The fake repo extends the create-path fake with a GSI-backed ``query_by_name_dob`` that indexes
every saved member by its normalized name+DOB key, so the flag is exercised end-to-end against a
real indexed read, not mocked away.

Validates: Requirements R3a.5, R3a.6, R3a.7, R3a.8, R6.1a
"""

from __future__ import annotations

import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from sam.members.domain.field_resolver import (
    FixedFieldOverride,
    StaticOverlayProvider,
    TenantOverlay,
)
from sam.members.domain.membership_service import MembershipService
from sam.members.repository import table_design as td
from sam.tests.test_create_application import _ApplicationRepo
from sam.tests.test_field_config_endpoint import _entry

TENANT = "h-dcn"


class _DupFlagRepo(_ApplicationRepo):
    """``_ApplicationRepo`` + a GSI-backed ``query_by_name_dob`` over the member store.

    Mirrors the real repository: ``save_member`` indexes a member by its normalized name+DOB
    (computed from the record's own ``personal`` fields, exactly as ``build_member_item`` does),
    and ``query_by_name_dob`` returns every member of the tenant with that composite key — a
    cheap INDEXED read, not a scan (R3a.8).
    """

    def query_by_name_dob(self, tenant_id, name_dob_key):
        if not name_dob_key:
            return []
        hits = []
        for (t, _mid), rec in self.members.items():
            if t != tenant_id:
                continue  # tenant-scoped (Property 1)
            personal = rec.get("personal") or {}
            key = td.normalize_name_dob_key(
                personal.get("first_name"),
                personal.get("name_infix"),
                personal.get("last_name"),
                personal.get("birth_date"),
            )
            if key == name_dob_key:
                hits.append(dict(rec))
        return hits


def _overlay_public_form() -> TenantOverlay:
    """Put the name + DOB fields (and email) on the PUBLIC form via ``application_visible``."""
    return TenantOverlay(
        overrides={
            "personal.first_name": FixedFieldOverride(application_visible=True),
            "personal.last_name": FixedFieldOverride(application_visible=True),
            "personal.name_infix": FixedFieldOverride(application_visible=True),
            "personal.birth_date": FixedFieldOverride(application_visible=True),
            "personal.email": FixedFieldOverride(application_visible=True),
            "membership.membership_type": FixedFieldOverride(application_visible=True),
        },
    )


@pytest.fixture()
def service() -> MembershipService:
    repo = _DupFlagRepo()
    repo.add_type(TENANT, _entry(TENANT, "gewoon", order=10))
    return MembershipService(
        repo, overlay_provider=StaticOverlayProvider({TENANT: _overlay_public_form()})
    )


def _submission(**over):
    body = {
        "personal.first_name": "Sam",
        "personal.last_name": "Berg",
        "personal.birth_date": "1990-05-01",
        "personal.email": "sam@example.com",
        "membership.membership_type": "gewoon",
    }
    body.update(over)
    return body


#: Affirmative consent. Task 2.6 made consent MANDATORY on the public create path (F4/R12.1);
#: these dup-flag tests are not about consent, so `_create` supplies it by default (the consent
#: gate + server-authoritative stamp are pinned in `test_application_consent.py`).
_AFFIRMATIVE_CONSENT = {"accepted": True}


def _create(service, body, **kw):
    """Call ``create_application`` with affirmative consent supplied (task 2.6)."""
    kw.setdefault("consent", _AFFIRMATIVE_CONSENT)
    return service.create_application(TENANT, body, **kw)


def _seed_existing_member(repo, *, first="Sam", last="Berg", dob="1990-05-01", email="old@e.com"):
    """Put an EXISTING member in the store so a later application can match it on name+DOB."""
    record = {
        "member_id": "existing-1",
        "tenant_id": TENANT,
        "personal": {"first_name": first, "last_name": last, "birth_date": dob, "email": email},
        "membership": {"status": "active", "membership_type": "gewoon"},
    }
    repo.save_member(TENANT, record)


def _additional_info(record) -> str:
    return str((record.get("overlay") or {}).get("additional_info", ""))


# ── 1. dup detected → DUP note ────────────────────────────────────────────────────────


class TestDupDetected:
    def test_name_dob_match_appends_dup_keyword(self, service):
        _seed_existing_member(service._repo)
        rec = _create(service, _submission(), session_key="s1")
        assert "DUP" in _additional_info(rec).split()

    def test_match_is_case_insensitive(self, service):
        _seed_existing_member(service._repo, first="SAM", last="BERG")
        rec = _create(
            service,
            _submission(**{"personal.first_name": "sam", "personal.last_name": "berg"}),
            session_key="s1",
        )
        assert "DUP" in _additional_info(rec).split()

    def test_dup_keyword_is_idempotent_across_a_resubmit(self, service):
        # A NEW-session match flags once; a same-session resend re-runs the flag but must not
        # accumulate a second `DUP` token (the keyword is appended only when absent).
        _seed_existing_member(service._repo)
        first = _create(service, _submission(), session_key="s1")
        assert _additional_info(first).split().count("DUP") == 1
        second = _create(
            service, _submission(**{"personal.email": "again@e.com"}), session_key="s1"
        )
        assert _additional_info(second).split().count("DUP") == 1


# ── 2. no dup → no note ───────────────────────────────────────────────────────────────


class TestNoDup:
    def test_no_match_leaves_no_dup_note(self, service):
        # Store has no member with this name+DOB → no flag.
        rec = _create(service, _submission(), session_key="s1")
        assert "DUP" not in _additional_info(rec).split()

    def test_same_name_different_dob_is_not_a_match(self, service):
        _seed_existing_member(service._repo, dob="1985-01-01")
        rec = _create(service, _submission(), session_key="s1")  # 1990-05-01
        assert "DUP" not in _additional_info(rec).split()

    def test_missing_dob_is_rejected_so_can_never_be_flagged(self, service):
        # DOB is half the dup signal (R6.1a) AND is now server-REQUIRED on the public path (task
        # 2.4, R6.1a): a submission without a DOB is rejected with a 422 before it can reach the
        # dup-flag check, so an un-indexable (DOB-less) record can never land to be flagged. (The
        # dup logic's own `name_dob_key is None` guard stays unit-covered via the GSI/normalize
        # tests; through create_application the DOB requirement makes that path unreachable.)
        from sam.members.domain._membership_errors import MemberValidationError

        _seed_existing_member(service._repo)
        body = _submission()
        body.pop("personal.birth_date")
        with pytest.raises(MemberValidationError) as exc:
            _create(service, body, session_key="s1")
        assert "personal.birth_date" in exc.value.errors
        # Nothing persisted → no record exists to carry a DUP note.
        assert len(service._repo.members) == 1  # only the seeded existing member


# ── 3. dup NEVER blocks + the response is unchanged ───────────────────────────────────


class TestDupNeverBlocks:
    def test_matched_application_is_still_created(self, service):
        _seed_existing_member(service._repo)
        rec = _create(service, _submission(), session_key="s1")
        # The record STILL lands as status=application (R3a.5 — detection never rejects).
        assert rec["membership"]["status"] == "application"
        assert rec["member_id"]  # a real, saved record

    def test_matched_and_unmatched_produce_the_same_status(self, service):
        # No enumeration oracle (R3a.7): the outward result does not vary by match.
        unmatched = _create(service, _submission(), session_key="s1")
        _seed_existing_member(service._repo, email="existing@e.com")
        matched = _create(
            service, _submission(**{"personal.email": "new@e.com"}), session_key="s2"
        )
        assert unmatched["membership"]["status"] == matched["membership"]["status"] == "application"

    def test_a_lookup_error_never_fails_the_submission(self, service, monkeypatch):
        # Flag-only: if the GSI read raises, the applicant's submission must STILL succeed
        # unchanged (R3a.7) — the flag is best-effort, the record is the source of truth.
        def _boom(tenant_id, name_dob_key):
            raise RuntimeError("index unavailable")

        monkeypatch.setattr(service._repo, "query_by_name_dob", _boom)
        rec = _create(service, _submission(), session_key="s1")
        assert rec["membership"]["status"] == "application"
        assert "DUP" not in _additional_info(rec).split()


# ── 4. self is excluded (a resubmit must not flag itself) ─────────────────────────────


class TestSelfExcluded:
    def test_first_submit_does_not_flag_itself(self, service):
        # No prior member; the first create must not match its own (not-yet-saved) row.
        rec = _create(service, _submission(), session_key="s1")
        assert "DUP" not in _additional_info(rec).split()

    def test_same_session_resubmit_does_not_flag_itself(self, service):
        first = _create(service, _submission(), session_key="s1")
        # The applicant resends in the SAME session — the record is now in the store, but the
        # resubmit resolves to the SAME member_id, so it must NOT flag itself as a duplicate.
        second = _create(
            service, _submission(**{"personal.email": "corrected@e.com"}), session_key="s1"
        )
        assert second["member_id"] == first["member_id"]
        assert "DUP" not in _additional_info(second).split()

    def test_distinct_session_same_person_IS_flagged(self, service):
        # A genuine re-application (NEW session, same person already a member) IS flagged.
        _seed_existing_member(service._repo)
        rec = _create(service, _submission(), session_key="new-session")
        assert "DUP" in _additional_info(rec).split()
