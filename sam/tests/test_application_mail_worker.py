"""
Member Application Form (application-app) — task 6.3 tests: the WORKER branch.

Pins the worker-side processing of the TWO offloaded application jobs the enqueue side (task 6.2)
puts on the EXISTING members mail-send queue — the ``member_application_staff`` and
``member_application_ack`` kinds — in :class:`~sam.members.worker.mail_send_worker.MailSendWorker`
(design §6 / seam e). These exercise the branch through its injected ports — a FAKE SES sender
that CAPTURES the send (and can simulate a throttle / permanent error), an in-memory dedupe-marker
store, a fake recipient resolver (task 6.1's ``RecipientResolution`` shape), and a fake sender
resolver (``MailSenderResolver`` shape) — with NO AWS/boto3.

What this task owns (tasks.md 6.3 / 6.5):
  * recipient resolution is WIRED — the staff job sends to task 6.1's resolved recipients;
  * ``From`` is composed via the sender resolver (D4 — per-tenant ``noreply@<mail_domain>``);
  * the Reply-To chain ORDER is the resolver's ``RecipientResolution.reply_to`` (D8/D24/R9a) —
    multi-address, mirrors the all-scope set, falls back to TenantAdmin, else none;
  * the STAFF body carries the deep-link + the neutral DUP marker and NO applicant PII (R8.6/R8.6a);
  * the APPLICANT body embeds the applicant's own data in the applicant's locale (R8a/R6b);
  * SES send is BEST-EFFORT + DLQ (R8.8): a send failure never rolls back the committed record
    (throttle → retryable, permanent → permanent; a no-recipients / no-sender case skips, not DLQ).

What task 6.4 adds (tasks.md 6.4, R8.5/R9/D22):
  * NO_NOTIFY: when the staff notification has NO recipients, the worker appends the stable
    ``NO_NOTIFY`` keyword to the COMMITTED record's ``overlay.additional_info`` (keyword-filterable
    on the applications inbox, R8b.5) AND raises a platform-operator alert — never a DLQ;
  * send-log (D22/0.4): the two application sends are jobs of ONE run — the worker creates the
    shared ``mailrun#<run_id>`` tally idempotently (application mode, public-intake triggered_by)
    and advances it (sending + sent counts; a permanent send fault records a failure sub-record).

Validates: Requirements R8, R8a, R8.5, R8.6, R8.6a, R8.8, R9, R9a
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
from sam.members.worker.mail_send_worker import (
    APPLICATION_TRIGGERED_BY,
    MODE_MEMBER_APPLICATION,
    MailSendPermanent,
    MailSendRetryable,
    MailSendWorker,
    SesSendOutcome,
)

TENANT = "h-dcn"
RUN_ID = "run-app-0001"
MEMBER_ID = "mem-123"
FROM_ADDRESS = "noreply@h-dcn.nl"


# ── fakes (the injected ports) ───────────────────────────────────────────────────────────


class FakeSes:
    """A fake SES sender that CAPTURES each send; can be told to throttle or permanently reject."""

    def __init__(self, *, outcome: SesSendOutcome | None = None):
        self.sends: list[dict] = []
        self._outcome = outcome

    def send(
        self, *, from_address, reply_to=None, recipients, subject, body_html,
        attachments=None, tags=None,
    ):
        self.sends.append(
            {
                "from_address": from_address,
                "reply_to": reply_to,
                "recipients": list(recipients),
                "subject": subject,
                "body_html": body_html,
                "attachments": list(attachments or []),
                "tags": dict(tags or {}),
            }
        )
        if self._outcome is not None:
            return self._outcome
        return SesSendOutcome(ok=True, message_id="msg-1", size_bytes=len(body_html))


class FakeMarkerStore:
    """An in-memory conditional-marker store — first mark_if_absent per (tenant, job) wins."""

    def __init__(self):
        self._seen: set[tuple[str, str]] = set()
        self.metadata: list[dict] = []

    def mark_if_absent(self, tenant_id, job_id, metadata):
        key = (tenant_id, job_id)
        if key in self._seen:
            return False
        self._seen.add(key)
        self.metadata.append({"tenant_id": tenant_id, "job_id": job_id, **dict(metadata)})
        return True


class _Resolution:
    """Mimics task 6.1's RecipientResolution — the worker reads .recipients and .reply_to."""

    def __init__(self, recipients, reply_to):
        self.recipients = tuple(recipients)
        self.reply_to = tuple(reply_to)


class FakeRecipientResolver:
    """A fake ApplicationRecipientResolver capturing the call + returning a canned resolution."""

    def __init__(self, recipients=("crud-a@h-dcn.nl", "crud-b@h-dcn.nl"), reply_to=None):
        self._recipients = recipients
        self._reply_to = reply_to if reply_to is not None else recipients
        self.calls: list[dict] = []

    def resolve_recipients(self, tenant_id, applicant_scope_value=None):
        self.calls.append(
            {"tenant_id": tenant_id, "applicant_scope_value": applicant_scope_value}
        )
        return _Resolution(self._recipients, self._reply_to)


class FakeRunStore:
    """An in-memory send-run tally (D22) — records create_mail_run + the status/count advances.

    Mimics the DynamoDbMembersRepository run-store surface the worker uses: ``create_mail_run``
    (idempotent on run_id), ``update_mail_run_status``, ``increment_mail_run_counts``, and
    ``record_mail_failure``. Captures enough for the 6.4 send-log assertions (the run exists with
    the application mode + public-intake triggered_by; status advanced to sending; sent counted;
    a failure recorded on a permanent fault)."""

    def __init__(self):
        self.runs: dict[tuple[str, str], dict] = {}
        self.statuses: list[tuple[str, str, str]] = []  # (tenant, run, status)
        self.counts: list[dict] = []  # {tenant, run, sent, failed}
        self.failures: list[dict] = []  # {tenant, run, address, reason}

    def create_mail_run(self, tenant_id, run_id, *, mode, triggered_by, recipient_count):
        key = (tenant_id, run_id)
        if key in self.runs:
            return self.runs[key]  # idempotent — the second job of the run must not reset it
        item = {
            "mode": mode,
            "triggered_by": triggered_by,
            "recipient_count": recipient_count,
            "status": "queued",
            "sent": 0,
            "failed": 0,
        }
        self.runs[key] = item
        return item

    def update_mail_run_status(self, tenant_id, run_id, status):
        self.statuses.append((tenant_id, run_id, status))
        run = self.runs.get((tenant_id, run_id))
        if run is not None:
            run["status"] = status
        return run

    def increment_mail_run_counts(self, tenant_id, run_id, *, sent=0, failed=0):
        self.counts.append({"tenant": tenant_id, "run": run_id, "sent": sent, "failed": failed})
        run = self.runs.get((tenant_id, run_id))
        if run is not None:
            run["sent"] = run.get("sent", 0) + sent
            run["failed"] = run.get("failed", 0) + failed
        return run

    def record_mail_failure(self, tenant_id, run_id, *, address, status="failed", reason=None,
                            message_id=None, adjust_run_tally=False):
        self.failures.append({"tenant": tenant_id, "run": run_id, "address": address,
                              "reason": reason})
        return {"address": address}

    @property
    def sent_total(self):
        return sum(c["sent"] for c in self.counts)


class FakeMembersStore:
    """An in-memory members store (get_member / save_member) for the NO_NOTIFY seam (R8.5).

    Seeded with a committed application record; the worker reads it, appends the NO_NOTIFY keyword
    to overlay.additional_info, and saves it back. Can be told the member is missing or that a
    save raises, to exercise the best-effort guards."""

    def __init__(self, record=None, *, missing=False, raise_on_save=False):
        self._record = record
        self._missing = missing
        self._raise_on_save = raise_on_save
        self.saved: list[dict] = []

    def get_member(self, tenant_id, member_id):
        if self._missing:
            return None
        return self._record

    def save_member(self, tenant_id, member):
        if self._raise_on_save:
            raise RuntimeError("boom")
        self._record = member
        self.saved.append(member)
        return member


class _SenderResolution:
    """Mimics MailSenderResolver's SenderResolution — the worker reads .from_address."""

    def __init__(self, from_address):
        self.from_address = from_address


class FakeSenderResolver:
    """A fake ApplicationSenderResolver returning a composed From (or None = not certified)."""

    def __init__(self, from_address=FROM_ADDRESS):
        self._from = from_address
        self.calls: list[str] = []

    def resolve(self, tenant_id):
        self.calls.append(tenant_id)
        return _SenderResolution(self._from)


def _worker(*, ses=None, markers=None, recipients=None, sender=None, run_store=None,
            members_store=None):
    return MailSendWorker(
        ses=ses or FakeSes(),
        marker_store=markers or FakeMarkerStore(),
        recipient_resolver=recipients if recipients is not None else FakeRecipientResolver(),
        sender_resolver=sender if sender is not None else FakeSenderResolver(),
        run_store=run_store,
        members_store=members_store,
    )


def _staff_job(*, duplicate_suspected=False, applicant_scope_value=None, name="Sam van Doe"):
    job = {
        JOB_KIND_KEY: JOB_KIND_STAFF,
        "tenant_id": TENANT,
        "run_id": RUN_ID,
        "member_id": MEMBER_ID,
        "applicant_display_name": name,
        "duplicate_suspected": duplicate_suspected,
    }
    if applicant_scope_value is not None:
        job["applicant_scope_value"] = applicant_scope_value
    return job


def _applicant_job(*, locale="en", recipient="sam@example.org"):
    return {
        JOB_KIND_KEY: JOB_KIND_APPLICANT,
        "tenant_id": TENANT,
        "run_id": RUN_ID,
        "member_id": MEMBER_ID,
        "recipient": recipient,
        "locale": locale,
        "submitted": {
            "personal": {
                "first_name": "Sam",
                "last_name": "Doe",
                "email": recipient,
            },
            "membership": {"status": "application"},
        },
    }


# ── recipient resolution wired (staff) ───────────────────────────────────────────────────


class TestStaffRecipientResolution:
    def test_staff_job_sends_to_the_resolved_recipients(self):
        ses = FakeSes()
        resolver = FakeRecipientResolver(recipients=("crud-a@h-dcn.nl", "crud-b@h-dcn.nl"))
        result = _worker(ses=ses, recipients=resolver).process(_staff_job())

        assert result.sent is True and result.deduped is False
        [sent] = ses.sends
        assert sent["recipients"] == ["crud-a@h-dcn.nl", "crud-b@h-dcn.nl"]
        # resolution ran tenant-pinned (Property 1) — never a client value.
        assert resolver.calls[0]["tenant_id"] == TENANT

    def test_staff_job_passes_applicant_scope_value_to_the_resolver(self):
        # D9a: when the envelope carries the applicant's scope value (toggle gated upstream),
        # the worker forwards it so the resolver can add the scope-matched copy.
        resolver = FakeRecipientResolver()
        _worker(recipients=resolver).process(_staff_job(applicant_scope_value="noord"))
        assert resolver.calls[0]["applicant_scope_value"] == "noord"

    def test_staff_job_no_scope_value_passes_none(self):
        resolver = FakeRecipientResolver()
        _worker(recipients=resolver).process(_staff_job())
        assert resolver.calls[0]["applicant_scope_value"] is None


# ── From composed via the sender resolver (D4) ───────────────────────────────────────────


class TestSenderComposition:
    def test_from_is_composed_via_the_sender_resolver(self):
        ses = FakeSes()
        sender = FakeSenderResolver(from_address="noreply@h-dcn.nl")
        _worker(ses=ses, sender=sender).process(_staff_job())
        assert ses.sends[0]["from_address"] == "noreply@h-dcn.nl"
        assert sender.calls == [TENANT]  # tenant-pinned (D4)

    def test_applicant_from_is_composed_via_the_sender_resolver(self):
        ses = FakeSes()
        sender = FakeSenderResolver(from_address="noreply@h-dcn.nl")
        _worker(ses=ses, sender=sender).process(_applicant_job())
        assert ses.sends[0]["from_address"] == "noreply@h-dcn.nl"


# ── Reply-To chain order (D8/D24/R9a) ────────────────────────────────────────────────────


class TestReplyToChain:
    def test_staff_reply_to_is_the_all_scope_set_multi_address(self):
        # R9a.2: Reply-To mirrors the all-scope Members_CRUD recipient SET (multi-address).
        ses = FakeSes()
        resolver = FakeRecipientResolver(
            recipients=("crud-a@h-dcn.nl", "crud-b@h-dcn.nl"),
            reply_to=("crud-a@h-dcn.nl", "crud-b@h-dcn.nl"),
        )
        _worker(ses=ses, recipients=resolver).process(_staff_job())
        # the SES port takes a single reply_to; the set is comma-joined (the adapter splits it).
        assert ses.sends[0]["reply_to"] == "crud-a@h-dcn.nl, crud-b@h-dcn.nl"

    def test_staff_reply_to_falls_back_to_tenant_admin_when_no_all_scope(self):
        # R9a.3: when there is no all-scope Members_CRUD the resolution's recipients AND reply_to
        # are the TenantAdmin set — the worker just forwards whatever the resolver returns.
        ses = FakeSes()
        resolver = FakeRecipientResolver(
            recipients=("admin@h-dcn.nl",), reply_to=("admin@h-dcn.nl",)
        )
        _worker(ses=ses, recipients=resolver).process(_staff_job())
        assert ses.sends[0]["recipients"] == ["admin@h-dcn.nl"]
        assert ses.sends[0]["reply_to"] == "admin@h-dcn.nl"

    def test_applicant_ack_sets_no_reply_to_chain(self):
        # The applicant confirmation is one-way — no Members_CRUD Reply-To (R9a is staff-only).
        ses = FakeSes()
        _worker(ses=ses).process(_applicant_job())
        assert ses.sends[0]["reply_to"] is None


# ── staff body: deep-link + DUP marker, NO applicant PII (R8.6/R8.6a) ────────────────────


class TestStaffBodyNoPii:
    def test_staff_body_carries_deep_link_and_no_applicant_pii(self):
        ses = FakeSes()
        _worker(ses=ses).process(_staff_job())
        body = ses.sends[0]["body_html"]
        # deep-link to the authenticated member detail (R8b.1).
        assert "/members/mem-123" in body
        # display name is allowed (the one identifying string, R8.6); the email is NOT.
        assert "Sam van Doe" in body
        assert "sam@example.org" not in body
        assert "status" not in body  # no submitted field values leak into the staff body

    def test_staff_body_shows_neutral_dup_marker_when_flagged(self):
        ses = FakeSes()
        _worker(ses=ses).process(_staff_job(duplicate_suspected=True))
        body = ses.sends[0]["body_html"]
        # neutral one-line triage marker (R8.6a) — never names a matched member.
        assert "possible existing member" in body.lower() or "bestaand lid" in body.lower()
        assert "mem-" not in body.replace("/members/mem-123", "")  # no OTHER member id leaks

    def test_staff_body_omits_dup_marker_when_not_flagged(self):
        ses = FakeSes()
        _worker(ses=ses).process(_staff_job(duplicate_suspected=False))
        body = ses.sends[0]["body_html"].lower()
        assert "possible existing member" not in body and "bestaand lid" not in body

    def test_staff_subject_uses_tenant_locale_default_nl_not_applicant_choice(self):
        # R6b.5: the staff email is NOT in the applicant's locale — it defaults to nl.
        ses = FakeSes()
        _worker(ses=ses).process(_staff_job())
        assert "aanmelding" in ses.sends[0]["subject"].lower()  # nl copy


# ── applicant body: own data + applicant locale (R8a/R6b) ────────────────────────────────


class TestApplicantBody:
    def test_applicant_body_embeds_own_submitted_data(self):
        ses = FakeSes()
        _worker(ses=ses).process(_applicant_job(recipient="sam@example.org"))
        [sent] = ses.sends
        assert sent["recipients"] == ["sam@example.org"]  # their OWN validated address (R8a.4)
        body = sent["body_html"]
        assert "Sam" in body and "sam@example.org" in body  # own data is not a leak (R8a.4)

    def test_applicant_body_renders_in_applicant_locale_en(self):
        ses = FakeSes()
        _worker(ses=ses).process(_applicant_job(locale="en"))
        assert "application" in ses.sends[0]["subject"].lower()  # en copy

    def test_applicant_body_renders_in_applicant_locale_nl(self):
        ses = FakeSes()
        _worker(ses=ses).process(_applicant_job(locale="nl"))
        assert "aanmelding" in ses.sends[0]["subject"].lower()  # nl copy

    def test_applicant_invalid_locale_falls_back_to_nl(self):
        ses = FakeSes()
        _worker(ses=ses).process(_applicant_job(locale="zz"))
        assert "aanmelding" in ses.sends[0]["subject"].lower()


# ── SES best-effort + DLQ (R8.8): a send failure never rolls back the record ─────────────


class TestBestEffortAndDlq:
    def test_throttle_raises_retryable_for_sqs_redelivery(self):
        ses = FakeSes(outcome=SesSendOutcome(ok=False, error="Throttling: slow down"))
        with pytest.raises(MailSendRetryable):
            _worker(ses=ses).process(_staff_job())

    def test_permanent_rejection_raises_permanent_to_dead_letter(self):
        ses = FakeSes(
            outcome=SesSendOutcome(ok=False, error="MessageRejected: identity not verified")
        )
        with pytest.raises(MailSendPermanent):
            _worker(ses=ses).process(_applicant_job())

    def test_no_recipients_is_no_notify_seam_not_a_dead_letter(self):
        # R8.5 NO_NOTIFY: an empty staff recipient set is NOT a failure — the record is already
        # in the inbox (R8b.4). The branch skips the send and returns not-sent; it does NOT raise
        # (no DLQ churn) and does NOT mark the run failed.
        ses = FakeSes()
        resolver = FakeRecipientResolver(recipients=(), reply_to=())
        runs = FakeRunStore()
        result = _worker(ses=ses, recipients=resolver, run_store=runs).process(_staff_job())
        assert result.sent is False and result.recipient_count == 0
        assert ses.sends == []  # nothing sent
        assert runs.failures == []  # NO_NOTIFY is not a failure — the run is not marked failed

    def test_no_usable_sender_skips_best_effort_without_dead_letter(self):
        # R8.8: a sender lapsing between the readiness precheck and send never crashes the worker
        # — the record is already committed. The branch skips the send rather than dead-lettering.
        ses = FakeSes()
        sender = FakeSenderResolver(from_address=None)  # not certified
        result = _worker(ses=ses, sender=sender).process(_staff_job())
        assert result.sent is False
        assert ses.sends == []


# ── R14.4: the committed application RECORD survives a worker SES failure (no rollback) ──
#
# The best-effort invariant R14.4 and task 6.5 name explicitly: "a simulated SES failure in the
# worker does NOT fail or roll back the application record." The TestBestEffortAndDlq cases above
# pin that an SES fault RAISES (throttle→retryable for SQS redelivery, permanent→DLQ) — but they
# wire no members store, so they do not assert the already-committed record is left UNTOUCHED
# when the send blows up. These close that gap: the worker never reads or mutates the member
# record on the send path (it touches it ONLY for the NO_NOTIFY note, which is the no-recipients
# branch, not a send failure), so a throttle / permanent rejection dead-letters while the record
# stands byte-for-byte unchanged — the record, written synchronously by create_application and
# discoverable in the status=application inbox (R8b.4), is independent of the offloaded send.


class TestRecordSurvivesSesFailure:
    def test_permanent_ses_rejection_leaves_the_committed_record_untouched(self):
        # A permanent SES rejection on the STAFF job dead-letters (MailSendPermanent) — but the
        # committed application record is NEVER read or mutated on the send path, so it stands.
        store = FakeMembersStore(_committed_record())
        before = dict(store.get_member(TENANT, MEMBER_ID))  # snapshot the committed record
        ses = FakeSes(
            outcome=SesSendOutcome(ok=False, error="MessageRejected: identity not verified")
        )
        with pytest.raises(MailSendPermanent):
            _worker(ses=ses, members_store=store).process(_staff_job())
        # No rollback, no save, no mutation: the record is exactly as create_application left it.
        assert store.saved == []
        assert store.get_member(TENANT, MEMBER_ID) == before

    def test_throttle_retryable_leaves_the_committed_record_untouched(self):
        # A retryable throttle on the APPLICANT job surfaces for SQS redelivery — the committed
        # record is still untouched (the send is fully decoupled from the write, R14.4).
        store = FakeMembersStore(_committed_record())
        before = dict(store.get_member(TENANT, MEMBER_ID))
        ses = FakeSes(outcome=SesSendOutcome(ok=False, error="Throttling: slow down"))
        with pytest.raises(MailSendRetryable):
            _worker(ses=ses, members_store=store).process(_applicant_job())
        assert store.saved == []
        assert store.get_member(TENANT, MEMBER_ID) == before

    def test_send_failure_does_not_stamp_no_notify_on_the_record(self):
        # A send FAILURE is distinct from the no-recipients NO_NOTIFY case: a failed send must NOT
        # annotate the record with NO_NOTIFY (that keyword means "nobody to notify", not "send
        # failed"). The record carries no DUP/NO_NOTIFY keyword it did not already have.
        store = FakeMembersStore(_committed_record())
        ses = FakeSes(
            outcome=SesSendOutcome(ok=False, error="MessageRejected: identity not verified")
        )
        with pytest.raises(MailSendPermanent):
            _worker(ses=ses, members_store=store).process(_staff_job())
        record = store.get_member(TENANT, MEMBER_ID)
        assert NO_NOTIFY_KEYWORD not in record.get("overlay", {}).get("additional_info", "")


# ── idempotent redelivery (stable run_id#kind marker) ────────────────────────────────────


class TestIdempotentRedelivery:
    def test_same_application_job_twice_sends_once(self):
        ses, markers = FakeSes(), FakeMarkerStore()
        worker = _worker(ses=ses, markers=markers)
        first = worker.process(_staff_job())
        second = worker.process(_staff_job())  # at-least-once redelivery
        assert first.sent is True and second.deduped is True
        assert len(ses.sends) == 1

    def test_staff_and_applicant_of_same_run_do_not_collide(self):
        # The two jobs share a run_id but differ by kind → distinct markers → both send.
        ses, markers = FakeSes(), FakeMarkerStore()
        worker = _worker(ses=ses, markers=markers)
        worker.process(_staff_job())
        worker.process(_applicant_job())
        assert len(ses.sends) == 2

    def test_application_job_without_resolver_is_permanent(self):
        # An application job that reaches a worker with no recipient resolver wired is a deploy
        # fault — permanent (dead-letters) rather than a silent no-send.
        worker = MailSendWorker(
            ses=FakeSes(),
            marker_store=FakeMarkerStore(),
            recipient_resolver=None,
            sender_resolver=FakeSenderResolver(),
        )
        with pytest.raises(MailSendPermanent):
            worker.process(_staff_job())


# ── feedback routing tags (reused from the pivot path) ───────────────────────────────────


class TestFeedbackTags:
    def test_application_send_stamps_tenant_and_run_tags(self):
        from sam.members.domain.mail_feedback_tags import (
            SES_TAG_RUN_ID,
            SES_TAG_TENANT_ID,
            decode_ses_tag_value,
        )

        ses = FakeSes()
        _worker(ses=ses).process(_staff_job())
        tags = ses.sends[0]["tags"]
        assert decode_ses_tag_value(tags[SES_TAG_TENANT_ID]) == TENANT
        assert decode_ses_tag_value(tags[SES_TAG_RUN_ID]) == RUN_ID


def _committed_record(*, additional_info=None):
    """A committed application record the NO_NOTIFY seam updates (shape: nested groups)."""
    overlay: dict = {}
    if additional_info is not None:
        overlay["additional_info"] = additional_info
    return {
        "member_id": MEMBER_ID,
        "personal": {"first_name": "Sam", "last_name": "Doe", "email": "sam@example.org"},
        "membership": {"status": "application"},
        "overlay": overlay,
    }


# ── NO_NOTIFY note on overlay.additional_info when no recipients (R8.5, task 6.4) ────────


class TestNoNotifyNote:
    def test_no_recipients_appends_no_notify_keyword_to_committed_record(self):
        # R8.5: no all-scope Members_CRUD AND no TenantAdmin → the committed record is annotated
        # with the stable NO_NOTIFY keyword on overlay.additional_info (keyword-filterable, R8b.5).
        resolver = FakeRecipientResolver(recipients=(), reply_to=())
        store = FakeMembersStore(_committed_record())
        _worker(recipients=resolver, members_store=store).process(_staff_job())

        assert len(store.saved) == 1
        info = store.saved[0]["overlay"]["additional_info"]
        assert NO_NOTIFY_KEYWORD in info.split()

    def test_no_notify_preserves_an_existing_dup_keyword(self):
        # Appending (not replacing) preserves a DUP note already written by the create path (2.5).
        resolver = FakeRecipientResolver(recipients=(), reply_to=())
        store = FakeMembersStore(_committed_record(additional_info="DUP"))
        _worker(recipients=resolver, members_store=store).process(_staff_job())

        info = store.saved[0]["overlay"]["additional_info"].split()
        assert "DUP" in info and NO_NOTIFY_KEYWORD in info

    def test_no_notify_is_idempotent_on_redelivery(self):
        # An at-least-once redelivery of the staff job must not double-append the keyword.
        resolver = FakeRecipientResolver(recipients=(), reply_to=())
        store = FakeMembersStore(_committed_record())
        worker = _worker(recipients=resolver, members_store=store)
        worker.process(_staff_job())
        worker.process(_staff_job())  # redelivery

        info = store.saved[-1]["overlay"]["additional_info"].split()
        assert info.count(NO_NOTIFY_KEYWORD) == 1
        # second pass is a no-op append (keyword already present) → no extra save
        assert len(store.saved) == 1

    def test_recipients_present_does_not_write_no_notify(self):
        # The note is ONLY for the no-recipients case — a normal send never annotates the record.
        store = FakeMembersStore(_committed_record())
        _worker(members_store=store).process(_staff_job())
        assert store.saved == []

    def test_no_notify_without_store_is_best_effort(self):
        # No members store wired → the note is simply not written; the worker never raises and
        # still returns not-sent (the application is in the inbox regardless, R8.7).
        resolver = FakeRecipientResolver(recipients=(), reply_to=())
        result = _worker(recipients=resolver, members_store=None).process(_staff_job())
        assert result.sent is False

    def test_no_notify_tolerates_a_missing_record(self):
        resolver = FakeRecipientResolver(recipients=(), reply_to=())
        store = FakeMembersStore(None, missing=True)
        result = _worker(recipients=resolver, members_store=store).process(_staff_job())
        assert result.sent is False and store.saved == []

    def test_no_notify_tolerates_a_save_error(self):
        # A save failure must never fail the worker (best-effort, R8.7) — no raise.
        resolver = FakeRecipientResolver(recipients=(), reply_to=())
        store = FakeMembersStore(_committed_record(), raise_on_save=True)
        result = _worker(recipients=resolver, members_store=store).process(_staff_job())
        assert result.sent is False


# ── platform-operator alert when no recipients (R8.5, task 6.4) ──────────────────────────


class TestOperatorAlert:
    def test_no_recipients_emits_operator_alert(self, caplog):
        import logging

        resolver = FakeRecipientResolver(recipients=(), reply_to=())
        with caplog.at_level(logging.ERROR, logger="sam.members.worker.mail_send_worker"):
            _worker(recipients=resolver, members_store=FakeMembersStore(_committed_record())).process(
                _staff_job()
            )
        # A stable, greppable operator-alert marker at ERROR (a metric filter / alarm subscribes).
        assert any(
            "OPERATOR_ALERT NO_RECIPIENTS" in r.getMessage() and r.levelno == logging.ERROR
            for r in caplog.records
        )

    def test_operator_alert_carries_no_applicant_pii(self, caplog):
        import logging

        resolver = FakeRecipientResolver(recipients=(), reply_to=())
        with caplog.at_level(logging.ERROR, logger="sam.members.worker.mail_send_worker"):
            _worker(recipients=resolver, members_store=FakeMembersStore(_committed_record())).process(
                _staff_job(name="Sam van Doe")
            )
        alert = next(r.getMessage() for r in caplog.records if "OPERATOR_ALERT" in r.getMessage())
        # Metadata only — tenant/run/member id, never the applicant's email or submitted data.
        assert "sam@example.org" not in alert
        assert TENANT in alert and RUN_ID in alert

    def test_no_operator_alert_on_a_normal_send(self, caplog):
        import logging

        with caplog.at_level(logging.ERROR, logger="sam.members.worker.mail_send_worker"):
            _worker(members_store=FakeMembersStore(_committed_record())).process(_staff_job())
        assert not any("OPERATOR_ALERT" in r.getMessage() for r in caplog.records)


# ── send-log: the application run tally (D22/0.4, R9) ────────────────────────────────────


class TestApplicationSendLog:
    def test_application_run_created_with_application_mode_and_public_triggered_by(self):
        runs = FakeRunStore()
        _worker(run_store=runs).process(_staff_job())
        run = runs.runs[(TENANT, RUN_ID)]
        assert run["mode"] == MODE_MEMBER_APPLICATION
        assert run["triggered_by"] == APPLICATION_TRIGGERED_BY

    def test_successful_staff_send_advances_run_to_sending_and_counts_sent(self):
        runs = FakeRunStore()
        resolver = FakeRecipientResolver(recipients=("crud-a@h-dcn.nl", "crud-b@h-dcn.nl"))
        _worker(recipients=resolver, run_store=runs).process(_staff_job())
        assert (TENANT, RUN_ID, "sending") in runs.statuses
        assert runs.sent_total == 2  # both resolved recipients counted sent

    def test_both_jobs_of_one_run_share_a_single_tally(self):
        # The two application jobs (staff + applicant) are jobs of ONE run — create is idempotent,
        # and both advance the SAME tally (no second run row, counts accumulate).
        runs = FakeRunStore()
        worker = _worker(run_store=runs)
        worker.process(_staff_job())       # 2 recipients (default resolver)
        worker.process(_applicant_job())   # 1 recipient (the applicant)
        assert list(runs.runs.keys()) == [(TENANT, RUN_ID)]
        assert runs.sent_total == 3

    def test_permanent_failure_records_a_run_failure(self):
        # R9.5: a permanent SES rejection records a FAILURE-only sub-record against the run before
        # dead-lettering (so the send-log reflects the undeliverable recipient).
        runs = FakeRunStore()
        ses = FakeSes(
            outcome=SesSendOutcome(ok=False, error="MessageRejected: identity not verified")
        )
        with pytest.raises(MailSendPermanent):
            _worker(ses=ses, run_store=runs).process(_applicant_job())
        assert len(runs.failures) == 1
        assert runs.failures[0]["address"] == "sam@example.org"

    def test_throttle_does_not_record_a_run_failure(self):
        # A retryable throttle is NOT a failure — the job will retry, so nothing is counted failed.
        runs = FakeRunStore()
        ses = FakeSes(outcome=SesSendOutcome(ok=False, error="Throttling: slow down"))
        with pytest.raises(MailSendRetryable):
            _worker(ses=ses, run_store=runs).process(_staff_job())
        assert runs.failures == []

    def test_no_recipients_creates_run_but_records_no_send_or_failure(self):
        # NO_NOTIFY: the run exists (both jobs created it) but the staff job neither sent nor failed.
        runs = FakeRunStore()
        resolver = FakeRecipientResolver(recipients=(), reply_to=())
        _worker(recipients=resolver, run_store=runs).process(_staff_job())
        assert (TENANT, RUN_ID) in runs.runs
        assert runs.sent_total == 0 and runs.failures == []

    def test_no_run_store_is_a_noop(self):
        # The send path must work with no run_store wired (the tally is additive, R9.1).
        result = _worker(run_store=None).process(_staff_job())
        assert result.sent is True


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
