"""
application-app task 7.3 — the **inbox-as-authoritative-channel** invariant (R14.5/R14.18, F3/R8b.4).

This is the KEY cross-cutting guarantee of the public-intake feature: the application RECORD —
committed synchronously by ``create_application`` — is the authoritative channel, and the staff
notification email is only a NUDGE. An application is discoverable by staff in the
**applications inbox** (the member overview filtered to ``status = application``) REGARDLESS of
whether the offloaded notification later succeeded, failed, throttled, or had no recipients
(NO_NOTIFY). The email never gates the record's discoverability.

Two sibling tests already touch pieces of this and are DELIBERATELY NOT duplicated here:

  * ``test_create_application.py`` pins that ``create_application`` FORCES ``status=application``
    on the committed record (the write side).
  * ``test_application_mail_worker.py::TestRecordSurvivesSesFailure`` pins that a worker SES
    failure / throttle leaves the committed record BYTE-FOR-BYTE UNTOUCHED (no rollback), and
    that a send FAILURE never stamps NO_NOTIFY.

What those do NOT assert — and what task 7.3 frames as the inbox-channel guarantee — is the
end-to-end payoff across BOTH halves through ONE shared store: a record created by the public
write path is STILL RETURNED BY THE ``status = application`` INBOX FILTER after the notification
send has failed (or had no recipients). That is the genuine gap these tests close. They wire the
create path and the mail worker to the SAME in-memory store and assert the inbox filter over that
store before and after the send fault.

The inbox is the EXISTING member overview filtered to ``status = application`` (task 7.2 — NO new
grid): list the tenant's members, keep those whose ``membership.status == "application"``. These
tests model that filter directly (``_applications_inbox``) over the shared store the create path
writes to — the authoritative discovery path, independent of the email.

Validates: Requirements R2.5 (Property 1 — public write stays tenant-pinned), R14.5, R14.18, R8b.4
"""

from __future__ import annotations

import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from sam.members.domain.application_notification import (
    JOB_KIND_APPLICANT,
    JOB_KIND_KEY,
    JOB_KIND_STAFF,
    NO_NOTIFY_KEYWORD,
)
from sam.members.domain.field_resolver import StaticOverlayProvider
from sam.members.domain.membership_service import MembershipService
from sam.members.worker.mail_send_worker import (
    MailSendPermanent,
    MailSendRetryable,
    MailSendWorker,
    SesSendOutcome,
)

# Reuse the task-2.2 create-path fixtures: the in-memory repo (catalog + member store + first-wins
# session claim) and the overlay that marks the public-form fields, plus the create-path helpers.
from sam.tests.test_create_application import (
    TENANT,
    _ApplicationRepo,
    _flat_submission,
    _overlay_public_form,
)
# Reuse the worker-side fakes so the SES failure / NO_NOTIFY branches are the REAL worker path.
from sam.tests.test_application_mail_worker import (
    FROM_ADDRESS,
    FakeMarkerStore,
    FakeRecipientResolver,
    FakeSenderResolver,
    FakeSes,
)


# ── the inbox: the member overview filtered to status=application (task 7.2) ─────────────


def _applications_inbox(repo: _ApplicationRepo, tenant_id: str) -> list[dict]:
    """The applications inbox = the tenant's members filtered to ``membership.status==application``.

    Models task 7.2's inbox (the EXISTING overview filtered by status, NO new grid) directly over
    the store the create path writes to: enumerate the tenant's committed member records and keep
    only the ``application``-status ones. This is the authoritative staff-discovery path — it
    reads the RECORD, never the email. Tenant-pinned (only this tenant's partition, Property 1).
    """
    return [
        dict(record)
        for (rec_tenant, _mid), record in repo.members.items()
        if rec_tenant == tenant_id
        and (record.get("membership") or {}).get("status") == "application"
    ]


def _inbox_member_ids(repo: _ApplicationRepo, tenant_id: str) -> set[str]:
    return {r["member_id"] for r in _applications_inbox(repo, tenant_id)}


# ── a MembershipService + a worker wired to the SAME store ───────────────────────────────


@pytest.fixture()
def repo() -> _ApplicationRepo:
    from sam.tests.test_field_config_endpoint import _entry

    r = _ApplicationRepo()
    r.add_type(TENANT, _entry(TENANT, "gewoon", order=10))
    r.add_type(TENANT, _entry(TENANT, "erelid", order=20))
    return r


@pytest.fixture()
def service(repo) -> MembershipService:
    return MembershipService(
        repo, overlay_provider=StaticOverlayProvider({TENANT: _overlay_public_form()})
    )


def _create_application(service, *, session_key, **over) -> dict:
    """Commit one public application (affirmative consent) and return the created record."""
    return service.create_application(
        TENANT, _flat_submission(**over), session_key=session_key, consent={"accepted": True}
    )


def _worker(repo, *, ses=None, recipients=None, sender=None):
    """A worker whose members_store IS the create path's repo — the inbox-channel coupling."""
    return MailSendWorker(
        ses=ses or FakeSes(),
        marker_store=FakeMarkerStore(),
        recipient_resolver=recipients if recipients is not None else FakeRecipientResolver(),
        sender_resolver=sender if sender is not None else FakeSenderResolver(),
        run_store=None,
        members_store=repo,
    )


def _staff_job(member_id, *, run_id="run-app-7-3"):
    return {
        JOB_KIND_KEY: JOB_KIND_STAFF,
        "tenant_id": TENANT,
        "run_id": run_id,
        "member_id": member_id,
        "applicant_display_name": "Sam Jansen",
        "duplicate_suspected": False,
    }


def _applicant_job(member_id, recipient, *, run_id="run-app-7-3"):
    return {
        JOB_KIND_KEY: JOB_KIND_APPLICANT,
        "tenant_id": TENANT,
        "run_id": run_id,
        "member_id": member_id,
        "recipient": recipient,
        "locale": "nl",
        "submitted": {
            "personal": {"first_name": "Sam", "last_name": "Jansen", "email": recipient},
            "membership": {"status": "application"},
        },
    }


# ── baseline: a committed application is in the inbox before any send ─────────────────────


class TestCreatedApplicationIsInTheInbox:
    def test_committed_application_appears_in_the_status_application_filter(self, service, repo):
        rec = _create_application(service, session_key="s1")
        # The authoritative channel: the record is discoverable in the inbox the instant it is
        # committed — before, and independent of, any notification.
        assert rec["member_id"] in _inbox_member_ids(repo, TENANT)
        assert _applications_inbox(repo, TENANT)[0]["membership"]["status"] == "application"


# ── R14.18: a send FAILURE never removes the record from the inbox ───────────────────────


class TestInboxSurvivesSendFailure:
    def test_permanent_staff_send_failure_leaves_record_in_the_inbox(self, service, repo):
        # The record is committed by the public write...
        rec = _create_application(service, session_key="s1")
        before = _inbox_member_ids(repo, TENANT)
        assert rec["member_id"] in before

        # ...then the OFFLOADED staff notification permanently fails (identity unverified → DLQ).
        ses = FakeSes(
            outcome=SesSendOutcome(ok=False, error="MessageRejected: identity not verified")
        )
        with pytest.raises(MailSendPermanent):
            _worker(repo, ses=ses).process(_staff_job(rec["member_id"]))

        # The inbox is UNCHANGED: a failed email never evicts the record (R14.18/R8b.4). The
        # record remains discoverable via the status=application filter, byte-for-byte present.
        after = _inbox_member_ids(repo, TENANT)
        assert rec["member_id"] in after
        assert after == before
        [found] = _applications_inbox(repo, TENANT)
        assert found["membership"]["status"] == "application"

    def test_throttled_applicant_send_leaves_record_in_the_inbox(self, service, repo):
        # A retryable throttle on the APPLICANT confirmation surfaces for SQS redelivery — the
        # committed record is still fully discoverable in the inbox (the send is decoupled).
        rec = _create_application(service, session_key="s1")
        ses = FakeSes(outcome=SesSendOutcome(ok=False, error="Throttling: slow down"))
        with pytest.raises(MailSendRetryable):
            _worker(repo, ses=ses).process(
                _applicant_job(rec["member_id"], rec["personal"]["email"])
            )
        assert rec["member_id"] in _inbox_member_ids(repo, TENANT)

    def test_send_failure_does_not_change_the_recorded_status(self, service, repo):
        # The failure path must not mutate membership.status away from application — the status
        # the inbox filters on is the create path's, never touched by the send outcome.
        rec = _create_application(service, session_key="s1")
        ses = FakeSes(
            outcome=SesSendOutcome(ok=False, error="MessageRejected: identity not verified")
        )
        with pytest.raises(MailSendPermanent):
            _worker(repo, ses=ses).process(_staff_job(rec["member_id"]))
        stored = repo.get_member(TENANT, rec["member_id"])
        assert stored["membership"]["status"] == "application"
        # A send failure is NOT a NO_NOTIFY — no keyword is stamped by a failed send.
        assert NO_NOTIFY_KEYWORD not in (stored.get("overlay") or {}).get("additional_info", "")


# ── R8b.4: a NO_NOTIFY (no recipients) record is STILL in the inbox ──────────────────────


class TestInboxSurvivesNoNotify:
    def test_no_recipients_record_stays_in_the_inbox_with_no_notify_marker(self, service, repo):
        # No all-scope Members_CRUD and no TenantAdmin → NO recipients. The staff notification
        # cannot send, the record is annotated NO_NOTIFY — but it is STILL in the applications
        # inbox (the record, not the email, is authoritative — R8b.4). NO_NOTIFY is itself a
        # keyword-filterable marker ON the inbox record (R8b.5), not an eviction.
        rec = _create_application(service, session_key="s1")
        resolver = FakeRecipientResolver(recipients=(), reply_to=())
        result = _worker(repo, recipients=resolver).process(_staff_job(rec["member_id"]))

        assert result.sent is False  # nothing sent (NO_NOTIFY) — not a DLQ
        assert rec["member_id"] in _inbox_member_ids(repo, TENANT)
        stored = repo.get_member(TENANT, rec["member_id"])
        assert stored["membership"]["status"] == "application"  # still in the filter
        assert NO_NOTIFY_KEYWORD in (stored["overlay"]["additional_info"]).split()


# ── happy path: a successful send does not change inbox discoverability either ───────────


class TestInboxUnaffectedByASuccessfulSend:
    def test_successful_send_leaves_the_record_in_the_inbox(self, service, repo):
        # Completeness: the inbox discoverability is INVARIANT across the send outcome — a
        # successful notification does not add, remove, or alter the record's inbox membership.
        rec = _create_application(service, session_key="s1")
        before = _inbox_member_ids(repo, TENANT)
        result = _worker(repo).process(_staff_job(rec["member_id"]))
        assert result.sent is True
        assert _inbox_member_ids(repo, TENANT) == before
        assert rec["member_id"] in before


# ── R2.5 / Property 1: the public write lands ONLY in the resolved tenant's partition ────
#
# The exhaustive repository tenant-partition invariant (test_members_repository_tenant_invariant.py)
# already proves EVERY repo op — including the public-write-path ops claim_application_session,
# get_application_session_member, query_by_name_dob — pins the tenant PK, with a completeness guard
# that fails the build if a new public method ships unlisted (R14.5). This test adds the
# SERVICE-level payoff for the public create: the slug-resolved tenant_id is the record's ONLY
# tenant, and the record is never visible in another tenant's inbox — a client-supplied tenant_id
# is stripped (verify-before-trust, R2.4/R2.5).


class TestPublicWriteStaysInResolvedTenantPartition:
    def test_created_record_carries_the_resolved_tenant_and_only_that(self, service, repo):
        rec = _create_application(service, session_key="s1")
        assert rec["tenant_id"] == TENANT
        # The record is in THIS tenant's inbox — and in no other tenant's inbox.
        assert rec["member_id"] in _inbox_member_ids(repo, TENANT)
        assert _applications_inbox(repo, "other-tenant") == []

    def test_client_supplied_tenant_id_cannot_redirect_the_write(self, service, repo):
        # A forged body tenant_id is stripped: the record lands in the slug-resolved tenant's
        # partition (its inbox), never the attacker's — the resolved tenant is authoritative.
        rec = _create_application(service, session_key="s1", **{"tenant_id": "other-tenant"})
        assert rec["tenant_id"] == TENANT
        assert rec["member_id"] in _inbox_member_ids(repo, TENANT)
        assert _applications_inbox(repo, "other-tenant") == []
