"""
Member Application Form (application-app) — task 6.2 tests.

Pins the offloaded notification **ENQUEUE orchestration** (``domain/application_notification``,
R8/R8a/R9, D5/D10; design §6 / seam e). On a successful public application the service enqueues
the TWO notification jobs — a STAFF notification and an APPLICANT confirmation (D10) — onto the
EXISTING members mail-send queue via the ``MailSendQueuePort`` (reused, not rebuilt), with
``tenant_id`` AUTHORITATIVE on EACH envelope (the point of this task, D5/D10, R2/R8.9).

These exercise the service through an in-memory fake ``MailSendQueuePort`` that CAPTURES the
enqueued job envelopes (no boto3, no SQS, no SES — the worker-side recipient resolution, From/
Reply-To composition, and template rendering are task 6.3; the NO_NOTIFY note + send-log are
6.4). The assertions this task owns:

  * TWO jobs are enqueued (staff + applicant, D10).
  * ``tenant_id`` is AUTHORITATIVE on EACH envelope — the resolved tenant, never the applicant's
    body value (D5/D10, R8.9).
  * the staff vs applicant job KIND discrimination (``member_application_staff`` /
    ``member_application_ack``) + each branch's start inputs (staff: deep-link member_id + neutral
    DUP marker, no PII; applicant: own email + locale + own submitted data).
  * best-effort: an enqueue failure never raises (the record is already committed, R8.7/R8.8).

Validates: Requirements R8, R8a, R9
"""

from __future__ import annotations

import os
import sys

import pytest

# repo root on sys.path (mirrors the other sam/tests modules) so `sam.members...` imports.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from sam.members.domain.application_notification import (
    JOB_KIND_APPLICANT,
    JOB_KIND_KEY,
    JOB_KIND_STAFF,
    NO_NOTIFY_KEYWORD,
    ApplicationNotificationService,
    append_additional_info_keyword,
    build_application_notification_jobs,
)

TENANT = "h-dcn"
RUN_ID = "run-app-0001"


# ── append_additional_info_keyword: the shared keyword-note mechanism (task 6.4) ─────────


class TestAppendAdditionalInfoKeyword:
    """The pure helper the create-path DUP flag (2.5) and the worker NO_NOTIFY note (6.4) share."""

    def test_appends_to_an_empty_record_and_returns_true(self):
        record: dict = {}
        assert append_additional_info_keyword(record, NO_NOTIFY_KEYWORD) is True
        assert record["overlay"]["additional_info"] == NO_NOTIFY_KEYWORD

    def test_preserves_an_existing_keyword(self):
        record = {"overlay": {"additional_info": "DUP"}}
        assert append_additional_info_keyword(record, NO_NOTIFY_KEYWORD) is True
        assert record["overlay"]["additional_info"].split() == ["DUP", NO_NOTIFY_KEYWORD]

    def test_idempotent_when_already_present_returns_false(self):
        record = {"overlay": {"additional_info": NO_NOTIFY_KEYWORD}}
        assert append_additional_info_keyword(record, NO_NOTIFY_KEYWORD) is False
        assert record["overlay"]["additional_info"] == NO_NOTIFY_KEYWORD

    def test_creates_overlay_bucket_when_absent(self):
        record = {"personal": {"email": "x@y.nl"}}
        append_additional_info_keyword(record, NO_NOTIFY_KEYWORD)
        assert record["overlay"]["additional_info"] == NO_NOTIFY_KEYWORD
        assert record["personal"] == {"email": "x@y.nl"}  # untouched


# ── fakes (the one injected port) ────────────────────────────────────────────────────


class FakeQueue:
    """An in-memory ``MailSendQueuePort`` that CAPTURES enqueued jobs (no SQS/boto3).

    Structurally satisfies the port (``enqueue`` / ``enqueue_many``) so the service depends on the
    shape, not SQS. Records every enqueued envelope so a test can assert the two jobs, their
    authoritative ``tenant_id``, and the staff-vs-applicant discrimination.
    """

    def __init__(self):
        self.jobs: list[dict] = []
        self._next = 0

    def enqueue(self, job):
        self.jobs.append(dict(job))
        self._next += 1
        return f"msg-{self._next}"

    def enqueue_many(self, jobs):
        return [self.enqueue(job) for job in jobs]


class ExplodingQueue:
    """A ``MailSendQueuePort`` whose ``enqueue`` always raises — to pin best-effort (R8.7/R8.8)."""

    def enqueue(self, job):
        raise RuntimeError("SQS unavailable")

    def enqueue_many(self, jobs):
        return [self.enqueue(job) for job in jobs]


def _record(**overrides):
    """A committed application member record (``create_application``'s return shape)."""
    record = {
        "tenant_id": TENANT,
        "member_id": "mem-123",
        "personal": {
            "first_name": "Sam",
            "name_infix": "van",
            "last_name": "Doe",
            "email": "sam@example.org",
        },
        "membership": {"status": "application"},
        "overlay": {},
        "locale": "en",
        "consent": {"version": "v1", "accepted_at": "2026-01-01T00:00:00+00:00", "locale": "en"},
    }
    record.update(overrides)
    return record


# ── build_application_notification_jobs (pure envelope shape) ──────────────────────────


def test_build_jobs_returns_exactly_two_jobs_staff_and_applicant():
    jobs = build_application_notification_jobs(TENANT, _record(), RUN_ID)

    assert len(jobs) == 2
    kinds = [job[JOB_KIND_KEY] for job in jobs]
    assert kinds == [JOB_KIND_STAFF, JOB_KIND_APPLICANT]


def test_build_jobs_stamps_authoritative_tenant_id_on_each_envelope():
    # The record's own tenant is the SAME source, but the authority is the passed argument — a
    # record carrying a FORGED tenant_id must never leak onto the envelope (D5/D10, R8.9).
    record = _record(tenant_id="attacker-tenant")

    jobs = build_application_notification_jobs(TENANT, record, RUN_ID)

    for job in jobs:
        assert job["tenant_id"] == TENANT
    assert all(job["tenant_id"] != "attacker-tenant" for job in jobs)


def test_build_jobs_share_one_run_id():
    jobs = build_application_notification_jobs(TENANT, _record(), RUN_ID)
    assert {job["run_id"] for job in jobs} == {RUN_ID}


def test_staff_job_carries_deep_link_member_id_and_no_applicant_pii_body():
    staff, _applicant = build_application_notification_jobs(TENANT, _record(), RUN_ID)

    assert staff[JOB_KIND_KEY] == JOB_KIND_STAFF
    assert staff["member_id"] == "mem-123"  # the deep-link target /members/{member_id} (R8.6)
    # A display name is the ONLY applicant-identifying text; no email / no submitted data body.
    assert staff["applicant_display_name"] == "Sam van Doe"
    assert "recipient" not in staff
    assert "submitted" not in staff


def test_staff_job_duplicate_marker_is_false_when_no_dup_note():
    staff, _applicant = build_application_notification_jobs(TENANT, _record(), RUN_ID)
    assert staff["duplicate_suspected"] is False


def test_staff_job_duplicate_marker_true_when_dup_keyword_present_but_names_no_member():
    record = _record(overlay={"additional_info": "some note DUP"})

    staff, _applicant = build_application_notification_jobs(TENANT, record, RUN_ID)

    assert staff["duplicate_suspected"] is True
    # Neutral marker only — the matched member is NEVER named on the envelope (R8.6a/R12.4).
    assert "matched_member_id" not in staff
    assert "matched" not in staff


def test_applicant_job_carries_own_email_locale_and_submitted_copy():
    applicant = build_application_notification_jobs(TENANT, _record(), RUN_ID)[1]

    assert applicant[JOB_KIND_KEY] == JOB_KIND_APPLICANT
    assert applicant["recipient"] == "sam@example.org"  # the server-validated own address (R8a.4)
    assert applicant["locale"] == "en"  # the applicant's chosen locale (R6b/R8a.2)
    # A copy of their OWN submitted data (their own data is not a leak, R8a.4).
    assert applicant["submitted"]["personal"]["email"] == "sam@example.org"


def test_applicant_submitted_copy_omits_server_owned_control_keys():
    applicant = build_application_notification_jobs(TENANT, _record(), RUN_ID)[1]

    submitted = applicant["submitted"]
    # Identity/control keys the applicant did not submit and does not need echoed are stripped;
    # consent + locale ride the envelope / record explicitly, not the submitted body.
    for owned in ("tenant_id", "member_id", "consent", "locale"):
        assert owned not in submitted


def test_applicant_locale_falls_back_to_nl_for_legacy_record_without_locale():
    record = _record()
    record.pop("locale")

    applicant = build_application_notification_jobs(TENANT, record, RUN_ID)[1]

    assert applicant["locale"] == "nl"  # locale_of_record default/fallback (R6b.2)


# ── ApplicationNotificationService.enqueue_application_notifications ────────────────────


def test_enqueue_places_both_jobs_on_the_queue():
    queue = FakeQueue()
    service = ApplicationNotificationService(queue)

    message_ids = service.enqueue_application_notifications(TENANT, _record(), RUN_ID)

    assert len(queue.jobs) == 2
    assert len(message_ids) == 2
    assert [job[JOB_KIND_KEY] for job in queue.jobs] == [JOB_KIND_STAFF, JOB_KIND_APPLICANT]


def test_enqueue_stamps_authoritative_tenant_on_each_enqueued_job():
    queue = FakeQueue()
    service = ApplicationNotificationService(queue)

    service.enqueue_application_notifications(TENANT, _record(tenant_id="forged"), RUN_ID)

    assert [job["tenant_id"] for job in queue.jobs] == [TENANT, TENANT]


def test_enqueue_mints_a_shared_run_id_when_none_supplied():
    queue = FakeQueue()
    service = ApplicationNotificationService(queue)

    service.enqueue_application_notifications(TENANT, _record())

    run_ids = {job["run_id"] for job in queue.jobs}
    assert len(run_ids) == 1  # one minted id, shared by both jobs
    assert next(iter(run_ids))  # non-empty


def test_enqueue_is_best_effort_and_never_raises_on_queue_failure():
    # The record is ALREADY committed, so an enqueue failure must never fail the submission
    # (R8.7/R8.8) — the service swallows it and reports zero successful enqueues.
    service = ApplicationNotificationService(ExplodingQueue())

    message_ids = service.enqueue_application_notifications(TENANT, _record(), RUN_ID)

    assert message_ids == []


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
