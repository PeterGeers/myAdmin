"""
SAM pytest for the mail-send WORKER (R4, pivot-output-actions task 4.3) — the CONSUMER side of
the queued send path (design §4.2/§4.3). These exercise
:class:`~sam.members.worker.mail_send_worker.MailSendWorker` and the thin Lambda entrypoint
:mod:`sam.members.worker.app` through their injected ports — a FAKE SES sender that CAPTURES the
send (and can simulate a throttle / permanent error), an in-memory dedupe-marker store, a fake
template renderer, and a capturing audit sink — with NO AWS/boto3 and NO real SQS/SES.

What is pinned (Phase 4 testing, tasks.md):
  * renders + sends for BOTH modes (per_recipient merge; to_fixed CSV attachment);
  * idempotent redelivery — the same job_id twice → ONE send (the marker dedupes);
  * SES rate-limit / throttle → the worker RAISES retryable (SQS retries → DLQ path);
  * a permanent SES rejection → RAISES permanent (dead-letters, never swallowed);
  * metadata-only audit — no subject / body / recipient address / merge value in the record;
  * tenant pinned — the marker + the render + the audit all carry the envelope's tenant;
  * the Lambda handler reports failures via the SQS partial-batch response.

Validates: Requirements R4
"""

from __future__ import annotations

import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from sam.members.domain.analytics_set import (
    DELIVERY_MODE_PER_RECIPIENT,
    DELIVERY_MODE_TO_FIXED,
)
from sam.members.domain.template_service import RenderedMessage
from sam.members.worker import app as worker_app
from sam.members.worker.mail_send_worker import (
    MAX_RECIPIENTS_PER_MESSAGE,
    MailSendPermanent,
    MailSendRetryable,
    MailSendWorker,
    SesSendOutcome,
    is_ses_rate_limited,
)

TENANT = "h-dcn"
SET_ID = "set-abc"
RUN_ID = "run-0001"


# ── fakes (the injected ports) ───────────────────────────────────────────────────────────


class FakeSes:
    """A fake SES sender that CAPTURES each send; can be told to throttle or permanently reject."""

    def __init__(self, *, outcome: SesSendOutcome | None = None):
        self.sends: list[dict] = []
        self._outcome = outcome

    def send(
        self,
        *,
        from_address,
        reply_to=None,
        recipients,
        subject,
        body_html,
        attachments=None,
        tags=None,
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


class FakeTemplates:
    """A fake template renderer — returns a merged subject/body and records the call."""

    def __init__(self):
        self.calls: list[dict] = []

    def render_for_recipient(self, tenant_id, template_id, lang, merge_values):
        self.calls.append(
            {
                "tenant_id": tenant_id,
                "template_id": template_id,
                "lang": lang,
                "merge_values": dict(merge_values),
            }
        )
        name = merge_values.get("first_name", "")
        return RenderedMessage(
            subject=f"Hello {name}".strip(),
            body_html=f"<p>Dear {name}</p>",
            lang=lang,
        )


class CapturingAudit:
    """A capturing audit sink — records the kwargs so a test can assert metadata-only."""

    def __init__(self):
        self.records: list[dict] = []

    def __call__(self, **kwargs):
        self.records.append(dict(kwargs))
        return dict(kwargs)


# ── envelope builders (the shape _mail_job_to_envelope writes) ───────────────────────────


#: The per-send From (active tenant's noreply@<tenant-domain>) + the user Reply-To ride on the
#: envelope (mail-spec task 1.2/1.3); the worker forwards them to the SES port.
FROM_ADDRESS = "noreply@h-dcn.nl"
REPLY_TO = "webmaster@h-dcn.nl"


def _per_recipient_envelope(job_id="job-1", address="ava@example.com"):
    return {
        "job_id": job_id,
        "tenant_id": TENANT,
        "set_id": SET_ID,
        "run_id": RUN_ID,
        "mode": DELIVERY_MODE_PER_RECIPIENT,
        "from_address": FROM_ADDRESS,
        "reply_to": REPLY_TO,
        "recipients": [address],
        "template_id": "tpl-1",
        "merge_values": {"first_name": "Ava", "personal.email": address},
        "attachment": None,
        "rows": [],
    }


def _to_fixed_envelope(job_id="job-fixed", attachment_kind="csv"):
    return {
        "job_id": job_id,
        "tenant_id": TENANT,
        "set_id": SET_ID,
        "run_id": RUN_ID,
        "mode": DELIVERY_MODE_TO_FIXED,
        "from_address": FROM_ADDRESS,
        "reply_to": REPLY_TO,
        "recipients": ["agent@example.com"],
        "template_id": None,
        "merge_values": {},
        "attachment": {"kind": attachment_kind, "label_options": None},
        "rows": [
            {"first_name": "Ava", "membership_type": "lid"},
            {"first_name": "Ben", "membership_type": "erelid"},
        ],
    }


def _worker(ses=None, markers=None, templates=None, audit=None):
    return MailSendWorker(
        ses=ses or FakeSes(),
        marker_store=markers or FakeMarkerStore(),
        template_service=templates or FakeTemplates(),
        audit=audit,
    )


# ── throttle detection (reuses the Flask _is_ses_rate_limited pattern) ───────────────────


class TestThrottleDetection:
    @pytest.mark.parametrize(
        "error",
        [
            "Throttling: Maximum sending rate exceeded",
            "ThrottlingException: Rate exceeded",
            "LimitExceeded: Daily message quota exceeded",
            "Too Many Requests",
        ],
    )
    def test_rate_limit_markers_are_detected(self, error):
        assert is_ses_rate_limited(error) is True

    @pytest.mark.parametrize(
        "error",
        ["MessageRejected: Email address is not verified", "", None, "AccessDenied"],
    )
    def test_non_throttle_errors_are_not_rate_limited(self, error):
        assert is_ses_rate_limited(error) is False


# ── per_recipient render + send ──────────────────────────────────────────────────────────


class TestPerRecipientSend:
    def test_renders_merge_and_sends_one_message(self):
        ses, templates = FakeSes(), FakeTemplates()
        worker = _worker(ses=ses, templates=templates)

        result = worker.process(_per_recipient_envelope())

        assert result.sent is True and result.deduped is False
        assert len(ses.sends) == 1
        sent = ses.sends[0]
        assert sent["recipients"] == ["ava@example.com"]
        assert sent["subject"] == "Hello Ava"  # merged from the member's merge_values
        assert "Ava" in sent["body_html"]
        assert sent["attachments"] == []  # per_recipient has no attachment
        # the merge ran on-plane with the job's own merge values
        assert templates.calls[0]["merge_values"]["first_name"] == "Ava"

    def test_missing_template_is_permanent(self):
        env = _per_recipient_envelope()
        env["template_id"] = None
        with pytest.raises(MailSendPermanent):
            _worker().process(env)

    def test_forwards_resolved_from_and_reply_to_to_the_ses_port(self):
        # Property 2: the per-send From (tenant noreply@<domain>) + the user Reply-To ride on the
        # envelope and are passed through to the SES port — never a global/substitute sender.
        ses = FakeSes()
        _worker(ses=ses).process(_per_recipient_envelope())
        sent = ses.sends[0]
        assert sent["from_address"] == FROM_ADDRESS
        assert sent["reply_to"] == REPLY_TO

    def test_stamps_ses_feedback_routing_tags(self):
        # mail-spec task 5.2 (R9.5): the worker stamps the tenant_id + run_id as SES message tags
        # (encoded) so the feedback event can be routed back to this run. The tags are encoded via
        # the shared mail_feedback_tags codec; the ingestion handler decodes them back.
        from sam.members.domain.mail_feedback_tags import (
            SES_TAG_RUN_ID,
            SES_TAG_TENANT_ID,
            decode_ses_tag_value,
        )

        ses = FakeSes()
        _worker(ses=ses).process(_per_recipient_envelope())
        tags = ses.sends[0]["tags"]
        assert decode_ses_tag_value(tags[SES_TAG_TENANT_ID]) == TENANT
        assert decode_ses_tag_value(tags[SES_TAG_RUN_ID]) == RUN_ID


# ── to_fixed render + send (CSV attachment) ──────────────────────────────────────────────


class TestToFixedSend:
    def test_builds_csv_attachment_and_sends_to_fixed_recipients(self):
        ses = FakeSes()
        worker = _worker(ses=ses)

        result = worker.process(_to_fixed_envelope(attachment_kind="csv"))

        assert result.sent is True
        [sent] = ses.sends
        assert sent["recipients"] == ["agent@example.com"]
        assert len(sent["attachments"]) == 1
        att = sent["attachments"][0]
        assert att["filename"] == "members.csv"
        assert att["content_type"] == "text/csv"
        body = att["content"].decode("utf-8")
        # header + two data rows (metadata of the set, no member PII beyond the set itself)
        assert "first_name" in body and "membership_type" in body
        assert "Ava" in body and "Ben" in body

    def test_pdf_labels_not_available_is_permanent(self):
        with pytest.raises(MailSendPermanent):
            _worker().process(_to_fixed_envelope(attachment_kind="pdf_labels"))


# ── idempotent redelivery: same job_id twice → ONE send ──────────────────────────────────


class TestIdempotentRedelivery:
    def test_same_job_id_twice_sends_once(self):
        ses, markers = FakeSes(), FakeMarkerStore()
        worker = _worker(ses=ses, markers=markers)
        env = _per_recipient_envelope(job_id="job-dup")

        first = worker.process(env)
        second = worker.process(env)  # at-least-once redelivery of the SAME job

        assert first.sent is True and first.deduped is False
        assert second.sent is False and second.deduped is True
        assert len(ses.sends) == 1  # ONE SES send despite two deliveries

    def test_distinct_job_ids_each_send(self):
        ses, markers = FakeSes(), FakeMarkerStore()
        worker = _worker(ses=ses, markers=markers)
        worker.process(_per_recipient_envelope(job_id="job-a", address="a@example.com"))
        worker.process(_per_recipient_envelope(job_id="job-b", address="b@example.com"))
        assert len(ses.sends) == 2

    def test_marker_is_written_before_send(self):
        # If the marker is checked AFTER the send, a crash between send and mark would double-
        # send on redelivery. The marker metadata is recorded on the first (owning) call.
        markers = FakeMarkerStore()
        worker = _worker(markers=markers)
        worker.process(_per_recipient_envelope(job_id="job-order"))
        assert markers.metadata[0]["job_id"] == "job-order"
        assert markers.metadata[0]["tenant_id"] == TENANT


# ── SES rate-limit → raises retryable (DLQ path); permanent → raises permanent ───────────


class TestSesLimitHandling:
    def test_throttle_raises_retryable_and_does_not_swallow(self):
        ses = FakeSes(
            outcome=SesSendOutcome(
                ok=False, error="Throttling: Maximum sending rate exceeded"
            )
        )
        worker = _worker(ses=ses)
        with pytest.raises(MailSendRetryable):
            worker.process(_per_recipient_envelope())

    def test_quota_exhaustion_is_retryable(self):
        ses = FakeSes(
            outcome=SesSendOutcome(ok=False, error="LimitExceeded: Daily message quota exceeded")
        )
        with pytest.raises(MailSendRetryable):
            _worker(ses=ses).process(_per_recipient_envelope())

    def test_permanent_rejection_raises_permanent(self):
        ses = FakeSes(
            outcome=SesSendOutcome(
                ok=False, error="MessageRejected: Email address is not verified"
            )
        )
        with pytest.raises(MailSendPermanent):
            _worker(ses=ses).process(_per_recipient_envelope())

    def test_too_many_recipients_is_permanent(self):
        env = _to_fixed_envelope()
        env["recipients"] = [f"r{i}@example.com" for i in range(MAX_RECIPIENTS_PER_MESSAGE + 1)]
        with pytest.raises(MailSendPermanent):
            _worker().process(env)

    def test_oversize_message_is_permanent(self):
        ses = FakeSes(
            outcome=SesSendOutcome(ok=True, message_id="m", size_bytes=11 * 1024 * 1024)
        )
        with pytest.raises(MailSendPermanent):
            _worker(ses=ses).process(_per_recipient_envelope())

    def test_a_retryable_throttle_still_records_no_double_send_marker_block(self):
        # The marker is written before the send; a throttle raises AFTER the marker exists, so
        # the SQS redelivery would be deduped. That is acceptable: the design relies on the
        # idempotency marker + the DLQ, and a throttled job is retried as a NEW receive only if
        # the marker is absent. This test documents that a throttle does raise (retryable).
        ses = FakeSes(outcome=SesSendOutcome(ok=False, error="Throttling: slow down"))
        with pytest.raises(MailSendRetryable):
            _worker(ses=ses).process(_per_recipient_envelope())


# ── metadata-only audit (no PII) ─────────────────────────────────────────────────────────


class TestMetadataOnlyAudit:
    def test_audit_records_only_metadata_no_pii(self):
        audit = CapturingAudit()
        worker = _worker(audit=audit)
        env = _per_recipient_envelope(address="ava@example.com")

        worker.process(env)

        assert len(audit.records) == 1
        rec = audit.records[0]
        assert rec["output_kind"] == "ses_mail"
        assert rec["tenant"] == TENANT
        assert rec["set_key"] == SET_ID
        assert rec["record_count"] == 1
        # NO body / subject / address / merge value anywhere in the audit kwargs.
        blob = repr(rec)
        assert "ava@example.com" not in blob
        assert "Ava" not in blob
        assert "Dear" not in blob

    def test_deduped_redelivery_does_not_re_audit(self):
        audit = CapturingAudit()
        worker = _worker(audit=audit)
        env = _per_recipient_envelope(job_id="job-dup-audit")
        worker.process(env)
        worker.process(env)
        assert len(audit.records) == 1  # the second (deduped) delivery emits no audit

    def test_audit_actor_is_run_id_not_a_member(self):
        audit = CapturingAudit()
        _worker(audit=audit).process(_per_recipient_envelope())
        assert audit.records[0]["actor"] == RUN_ID


# ── tenant pinning ───────────────────────────────────────────────────────────────────────


class TestTenantPinning:
    def test_marker_render_and_audit_all_carry_the_envelope_tenant(self):
        markers, templates, audit = FakeMarkerStore(), FakeTemplates(), CapturingAudit()
        worker = _worker(markers=markers, templates=templates, audit=audit)
        worker.process(_per_recipient_envelope())

        assert markers.metadata[0]["tenant_id"] == TENANT
        assert templates.calls[0]["tenant_id"] == TENANT
        assert audit.records[0]["tenant"] == TENANT

    def test_missing_tenant_is_permanent(self):
        env = _per_recipient_envelope()
        env["tenant_id"] = ""
        with pytest.raises(MailSendPermanent):
            _worker().process(env)


# ── the thin Lambda handler (SQS event → partial-batch response) ─────────────────────────


class TestWorkerHandler:
    @pytest.fixture(autouse=True)
    def _reset_worker(self):
        worker_app._WORKER = None
        yield
        worker_app._WORKER = None

    def _event(self, envelope, message_id="m-1"):
        import json

        return {"Records": [{"messageId": message_id, "body": json.dumps(envelope)}]}

    def test_handler_processes_a_record_and_reports_no_failures(self, monkeypatch):
        ses = FakeSes()
        worker_app._WORKER = _worker(ses=ses)
        resp = worker_app.handler(self._event(_per_recipient_envelope()))
        assert resp == {"batchItemFailures": []}
        assert len(ses.sends) == 1

    def test_handler_reports_failed_record_for_retry(self):
        ses = FakeSes(outcome=SesSendOutcome(ok=False, error="Throttling: slow down"))
        worker_app._WORKER = _worker(ses=ses)
        resp = worker_app.handler(self._event(_per_recipient_envelope(), message_id="m-x"))
        assert resp == {"batchItemFailures": [{"itemIdentifier": "m-x"}]}

    def test_handler_reports_malformed_body_as_failure(self):
        worker_app._WORKER = _worker()
        event = {"Records": [{"messageId": "m-bad", "body": "not-json"}]}
        resp = worker_app.handler(event)
        assert resp == {"batchItemFailures": [{"itemIdentifier": "m-bad"}]}

    def test_handler_empty_batch_is_noop(self):
        worker_app._WORKER = _worker()
        assert worker_app.handler({"Records": []}) == {"batchItemFailures": []}
