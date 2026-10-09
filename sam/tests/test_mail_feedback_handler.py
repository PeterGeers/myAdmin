"""
SAM pytest for the SES FEEDBACK INGESTION path (mail-spec task 5.2; R8.4/R9.5) — the CONSUMER
side of the SES -> SNS feedback pipeline. Exercises
:class:`~sam.members.domain.mail_feedback_handler.MailFeedbackService` and the thin SNS Lambda
entrypoint :mod:`sam.members.worker.mail_feedback_app` through an injected FAKE repository (no
AWS), over synthetic SES notifications routed by the stamped ms_tenant/ms_run message tags.

What is pinned (Phase 5 testing, tasks.md):
  * a simulated BOUNCE event records a FAILURE against the right run/recipient (routed by tag) and
    adjusts the tally (adjust_run_tally — the LATE path);
  * a late bounce for a previously-sent address CREATES a sub-record (there was none);
  * a COMPLAINT likewise;
  * a DELIVERY event is handled per the design decision (informational no-op — no record);
  * an UNROUTABLE event (missing tag) is REPORTED, never silently dropped;
  * tenancy — the tag's tenant_id is AUTHORITATIVE (never guessed from the address/domain);
  * the SNS Lambda entrypoint unwraps Sns.Message, delegates, and summarises.

Validates: Requirements R8.4, R9.5
"""

from __future__ import annotations

import json
import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from sam.members.domain.mail_feedback_handler import (
    EVENT_TYPE_BOUNCE,
    EVENT_TYPE_COMPLAINT,
    EVENT_TYPE_DELIVERY,
    MailFeedbackService,
)
from sam.members.domain.mail_feedback_tags import (
    SES_TAG_RUN_ID,
    SES_TAG_TENANT_ID,
    build_feedback_tags,
)
from sam.members.repository.members_repository import (
    MAIL_RECIPIENT_STATUS_BOUNCED,
    MAIL_RECIPIENT_STATUS_COMPLAINT,
)
from sam.members.worker import mail_feedback_app as feedback_app

TENANT = "h-dcn"
RUN_ID = "deliver:set-abc:user-7:20250101T000000000000Z"
OTHER_TENANT = "other-club"


# ── fake repository (the injected MailFailureStore port) ─────────────────────────────────


class FakeRepo:
    """An in-memory ``record_mail_failure`` capture — pins the tenant/run/address/status/flags."""

    def __init__(self):
        self.calls: list[dict] = []

    def record_mail_failure(
        self,
        tenant_id,
        run_id,
        *,
        address,
        status="failed",
        reason=None,
        message_id=None,
        adjust_run_tally=False,
    ):
        call = {
            "tenant_id": tenant_id,
            "run_id": run_id,
            "address": address,
            "status": status,
            "reason": reason,
            "message_id": message_id,
            "adjust_run_tally": adjust_run_tally,
        }
        self.calls.append(call)
        return dict(call)


# ── synthetic SES notifications (the mail.tags shape SES publishes) ──────────────────────


def _tags(tenant_id=TENANT, run_id=RUN_ID):
    """The mail.tags block SES echoes back: {tag_name: [value]}, values the stamped encoding."""
    stamped = build_feedback_tags(tenant_id, run_id)
    return {name: [value] for name, value in stamped.items()}


def _mail(tenant_id=TENANT, run_id=RUN_ID, message_id="msg-abc", include_tags=True):
    mail = {"messageId": message_id, "source": "noreply@h-dcn.nl"}
    if include_tags:
        mail["tags"] = _tags(tenant_id, run_id)
    return mail


def _bounce_event(address="bounced@example.com", **mail_kw):
    return {
        "eventType": "Bounce",
        "bounce": {
            "bounceType": "Permanent",
            "bounceSubType": "General",
            "bouncedRecipients": [
                {
                    "emailAddress": address,
                    "action": "failed",
                    "status": "5.1.1",
                    "diagnosticCode": "smtp; 550 5.1.1 user unknown",
                }
            ],
        },
        "mail": _mail(**mail_kw),
    }


def _complaint_event(address="complainer@example.com", **mail_kw):
    return {
        "eventType": "Complaint",
        "complaint": {
            "complainedRecipients": [{"emailAddress": address}],
            "complaintFeedbackType": "abuse",
        },
        "mail": _mail(**mail_kw),
    }


def _delivery_event(**mail_kw):
    return {
        "eventType": "Delivery",
        "delivery": {"recipients": ["ok@example.com"], "smtpResponse": "250 OK"},
        "mail": _mail(**mail_kw),
    }


# ── the service ──────────────────────────────────────────────────────────────────────────


class TestBounceIngestion:
    def test_bounce_records_failure_against_the_tagged_run_and_adjusts_tally(self):
        repo = FakeRepo()
        result = MailFeedbackService(repo).ingest(_bounce_event())

        assert result.routed is True
        assert result.recorded == 1
        [call] = repo.calls
        # routed to the right tenant/run by the tag; recipient + status + late-path tally move
        assert call["tenant_id"] == TENANT
        assert call["run_id"] == RUN_ID
        assert call["address"] == "bounced@example.com"
        assert call["status"] == MAIL_RECIPIENT_STATUS_BOUNCED
        assert call["adjust_run_tally"] is True  # the LATE async path (R8.4)
        assert call["message_id"] == "msg-abc"
        assert "550" in call["reason"]  # the SES diagnostic as the reason

    def test_late_bounce_for_previously_sent_address_creates_a_subrecord(self):
        # The failure-only model: a previously-"sent" recipient has NO sub-record; a late bounce
        # must CREATE one. record_mail_failure(adjust_run_tally=True) is exactly the create+adjust
        # call — so a single invocation with that flag is the "creates a sub-record" contract.
        repo = FakeRepo()
        MailFeedbackService(repo).ingest(_bounce_event(address="late@example.com"))
        [call] = repo.calls
        assert call["address"] == "late@example.com"
        assert call["adjust_run_tally"] is True

    def test_bounce_with_multiple_recipients_records_each(self):
        repo = FakeRepo()
        event = _bounce_event()
        event["bounce"]["bouncedRecipients"].append(
            {"emailAddress": "second@example.com", "status": "4.4.1"}
        )
        result = MailFeedbackService(repo).ingest(event)
        assert result.recorded == 2
        assert {c["address"] for c in repo.calls} == {
            "bounced@example.com",
            "second@example.com",
        }


class TestComplaintIngestion:
    def test_complaint_records_failure_with_complaint_status(self):
        repo = FakeRepo()
        result = MailFeedbackService(repo).ingest(_complaint_event())
        assert result.recorded == 1
        [call] = repo.calls
        assert call["tenant_id"] == TENANT
        assert call["run_id"] == RUN_ID
        assert call["address"] == "complainer@example.com"
        assert call["status"] == MAIL_RECIPIENT_STATUS_COMPLAINT
        assert call["adjust_run_tally"] is True
        assert call["reason"] == "abuse"


class TestDeliveryIngestion:
    def test_delivery_is_informational_noop_no_record(self):
        # Design decision (R9.4): the core view is sent/failed and must not claim per-recipient
        # "delivered" from SES acceptance — so a delivery event records NOTHING (handled no-op).
        repo = FakeRepo()
        result = MailFeedbackService(repo).ingest(_delivery_event())
        assert result.routed is True
        assert result.ignored is True
        assert result.recorded == 0
        assert repo.calls == []


class TestUnroutable:
    def test_bounce_without_tags_is_reported_not_dropped(self):
        # R9.5 / Property 6: an event we cannot route (missing tag) is REPORTED, never silently
        # dropped — and nothing is written (we never guess a tenant).
        repo = FakeRepo()
        result = MailFeedbackService(repo).ingest(_bounce_event(include_tags=False))
        assert result.routed is False
        assert result.unroutable_reason is not None
        assert "tenant_id" in result.unroutable_reason
        assert repo.calls == []

    def test_bounce_with_corrupt_tag_is_unroutable(self):
        # A corrupt (non-hex) tag decodes to empty → treated as absent → unroutable (fail-closed).
        repo = FakeRepo()
        event = _bounce_event()
        event["mail"]["tags"] = {SES_TAG_TENANT_ID: ["zzz"], SES_TAG_RUN_ID: ["zzz"]}
        result = MailFeedbackService(repo).ingest(event)
        assert result.routed is False
        assert repo.calls == []

    def test_bounce_with_no_recipient_is_unroutable(self):
        repo = FakeRepo()
        event = _bounce_event()
        event["bounce"]["bouncedRecipients"] = []
        result = MailFeedbackService(repo).ingest(event)
        assert result.routed is False
        assert "recipient" in result.unroutable_reason
        assert repo.calls == []

    def test_unknown_event_type_is_ignored_not_recorded(self):
        repo = FakeRepo()
        result = MailFeedbackService(repo).ingest(
            {"eventType": "Reject", "mail": _mail(), "reject": {"reason": "Bad content"}}
        )
        assert result.ignored is True
        assert repo.calls == []


class TestTenancyAuthority:
    def test_tenant_id_comes_from_the_tag_not_the_source_domain(self):
        # Property 3: tenant_id is AUTHORITATIVE from the tag. Even though the mail.source domain is
        # h-dcn.nl, a tag naming OTHER_TENANT routes the failure to OTHER_TENANT (and never guesses
        # from the address/domain). This is the fail-closed tenancy contract.
        repo = FakeRepo()
        event = _bounce_event(tenant_id=OTHER_TENANT)
        MailFeedbackService(repo).ingest(event)
        [call] = repo.calls
        assert call["tenant_id"] == OTHER_TENANT

    def test_store_fault_propagates(self):
        # A real store fault (not a routing problem) must PROPAGATE so the entry-point can fail the
        # record for SNS redelivery — it is not swallowed as "unroutable".
        class BoomRepo(FakeRepo):
            def record_mail_failure(self, *a, **k):
                raise RuntimeError("dynamo down")

        with pytest.raises(RuntimeError):
            MailFeedbackService(BoomRepo()).ingest(_bounce_event())


# ── the thin SNS Lambda entrypoint ───────────────────────────────────────────────────────


class TestFeedbackHandler:
    @pytest.fixture(autouse=True)
    def _reset_service(self):
        feedback_app._SERVICE = None
        yield
        feedback_app._SERVICE = None

    def _sns_event(self, *notifications):
        return {
            "Records": [
                {"Sns": {"Message": json.dumps(n), "MessageId": f"m-{i}"}}
                for i, n in enumerate(notifications)
            ]
        }

    def test_handler_unwraps_sns_message_and_records(self):
        repo = FakeRepo()
        feedback_app._SERVICE = MailFeedbackService(repo)
        summary = feedback_app.handler(self._sns_event(_bounce_event()))
        assert summary["records"] == 1
        assert summary["routed"] == 1
        assert summary["recorded"] == 1
        assert summary["unroutable"] == 0
        assert repo.calls[0]["tenant_id"] == TENANT

    def test_handler_reports_unroutable_without_raising(self):
        # SNS -> Lambda has no partial batch; an unroutable (untagged) event is counted + logged,
        # never silently dropped, and does NOT raise (retrying can't make the tag appear).
        repo = FakeRepo()
        feedback_app._SERVICE = MailFeedbackService(repo)
        summary = feedback_app.handler(self._sns_event(_bounce_event(include_tags=False)))
        assert summary["unroutable"] == 1
        assert summary["recorded"] == 0
        assert repo.calls == []

    def test_handler_delivery_is_counted_ignored(self):
        repo = FakeRepo()
        feedback_app._SERVICE = MailFeedbackService(repo)
        summary = feedback_app.handler(self._sns_event(_delivery_event()))
        assert summary["routed"] == 1
        assert summary["ignored"] == 1
        assert summary["recorded"] == 0

    def test_handler_malformed_message_is_counted_not_raised(self):
        repo = FakeRepo()
        feedback_app._SERVICE = MailFeedbackService(repo)
        event = {"Records": [{"Sns": {"Message": "not-json", "MessageId": "m-bad"}}]}
        summary = feedback_app.handler(event)
        assert summary["unroutable"] == 1
        assert repo.calls == []

    def test_handler_empty_batch_is_noop(self):
        feedback_app._SERVICE = MailFeedbackService(FakeRepo())
        summary = feedback_app.handler({"Records": []})
        assert summary["records"] == 0 and summary["recorded"] == 0

    def test_handler_store_fault_propagates_for_retry(self):
        class BoomRepo(FakeRepo):
            def record_mail_failure(self, *a, **k):
                raise RuntimeError("dynamo down")

        feedback_app._SERVICE = MailFeedbackService(BoomRepo())
        with pytest.raises(RuntimeError):
            feedback_app.handler(self._sns_event(_bounce_event()))
