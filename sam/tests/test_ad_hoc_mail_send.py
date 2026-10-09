"""
SAM pytest for the AD-HOC shared send entry :meth:`ExecuteAndDeliverService.send_ad_hoc`
(mail-spec Phase 2, task 2.2) — the SIBLING of the saved-set
:meth:`ExecuteAndDeliverService.execute_and_deliver`.

The ad-hoc interactive send (``POST /members/mail/send``, task 2.1) carries the COMPOSE body
itself — the current result rows + the typed recipients / template / attachment — rather than a
saved ``analyticsset#<id>`` + a stored ``delivery`` block. The design decides TWO thin routes,
ONE shared send service: both the saved-set ``/deliver`` and the stateless ``/mail/send`` route
converge on the SAME pre-send certification gate, the SAME fan-out, the SAME ``MailJob`` shape,
and the SAME ``MailQueue`` — only the INPUT differs (a set to re-fetch vs an ad-hoc body carrying
its own rows).

These exercise ``send_ad_hoc`` through the service's injected ports — a fake ``MailQueue`` that
CAPTURES the enqueued jobs and a (certified-by-default) ``MailSenderResolver`` over a static
config reader — with NO AWS/boto3 and NO repository re-fetch (the ad-hoc rows arrive on the body).
What is pinned:

- ``per_recipient`` ad-hoc body builds N jobs (one per result row) with the resolved tenant From
  + the user Reply-To STAMPED on every job (R2, R4).
- ``to_fixed`` ad-hoc body builds exactly ONE job carrying the fixed recipients + attachment +
  rows, stamped likewise (R3, R4).
- NOT-CERTIFIED refuses BEFORE enqueue (no job, the typed reason) — the SAME gate as the saved
  path, with no substitute sender (R4.2/R5.2).
- Tenancy: the stamped From is the AUTHORITATIVE tenant's; a different tenant's config drives a
  different From / a refusal (Property 3).
- Idempotency: a stable ``job_id`` means an at-least-once redelivery of the same run never
  double-sends (Property 5).
- Shape validation: a malformed ad-hoc body raises ``AdHocMailInvalid`` before any enqueue.

Validates: Requirements R2, R3, R4
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
from sam.members.domain.execute_and_deliver import (
    AdHocMailBody,
    AdHocMailInvalid,
    DeliveryOutcome,
    ExecuteAndDeliverService,
    MailJob,
    MailNotCertified,
)
from sam.members.domain.mail_sender_resolver import (
    MailSenderResolver,
    NotCertifiedReason,
)

TENANT = "h-dcn"
RUN_ID = "run-adhoc-0001"
REPLY_TO = "webmaster@h-dcn.nl"


# ── fakes (the injected ports the ad-hoc path actually uses) ────────────────────────────


class FakeQueue:
    """An in-memory :class:`MailQueue` that CAPTURES every enqueued job (no SQS, no boto3)."""

    def __init__(self):
        self.jobs: list[MailJob] = []

    def enqueue(self, job):
        self.jobs.append(job)


class ExplodingRepo:
    """A repo that FAILS if touched — proves the ad-hoc path does NO repository re-fetch.

    The ad-hoc body carries its own already-computed result rows (design "What to ADD" #1), so
    ``send_ad_hoc`` must never call ``get_analytics_set`` / ``list_members``. Injecting a repo
    whose every method raises turns an accidental re-fetch into a loud test failure.
    """

    def get_analytics_set(self, *a, **k):  # pragma: no cover - must never be called
        raise AssertionError("ad-hoc send must not resolve a saved set")

    def list_members(self, *a, **k):  # pragma: no cover - must never be called
        raise AssertionError("ad-hoc send must not re-fetch members")


class FakeMailConfigReader:
    """A static :class:`MailConfigReader` for the pre-send resolver (no projection/DynamoDB).

    Defaults model a CERTIFIED tenant (enabled + certified + a domain) so the happy-path fan-out
    gets a usable From; flip the flags / drop the domain to drive the fail-closed refusals. Pins
    by ``tenant_id`` — an unseeded/blank tenant is fail-closed (Property 3/4).
    """

    def __init__(
        self,
        *,
        enabled=True,
        certified=True,
        domain="h-dcn.nl",
        local_part="noreply",
    ):
        self._enabled = enabled
        self._certified = certified
        self._domain = domain
        self._local_part = local_part

    def is_mail_enabled(self, tenant_id):
        return bool(tenant_id) and self._enabled

    def is_mail_certified(self, tenant_id):
        return bool(tenant_id) and self._certified

    def get_mail_domain(self, tenant_id):
        return self._domain if tenant_id else None

    def get_mail_local_part(self, tenant_id):
        return self._local_part


def _certified_resolver(**overrides):
    return MailSenderResolver(FakeMailConfigReader(**overrides))


def _service(queue, resolver=None):
    """Build the service with an ExplodingRepo (ad-hoc path never re-fetches) + a certified gate.

    The PivotRunner is unused on the ad-hoc path (the rows ride on the body), so a ``None`` runner
    is passed to prove it is never invoked — any accidental ``.run`` would raise ``AttributeError``.
    """
    return ExecuteAndDeliverService(
        ExplodingRepo(), None, queue, resolver or _certified_resolver()
    )


def _member(first_name, email):
    return {
        "member_id": first_name.lower(),
        "first_name": first_name,
        "personal": {"email": email, "first_name": first_name},
        "membership_type": "lid",
    }


@pytest.fixture()
def queue():
    return FakeQueue()


# ── per_recipient ad-hoc: ONE job per result row, From/Reply-To stamped ─────────────────


class TestAdHocPerRecipient:
    def test_fans_out_to_n_jobs_one_per_result_row(self, queue):
        body = AdHocMailBody(
            mode=DELIVERY_MODE_PER_RECIPIENT,
            result_rows=(
                _member("Ava", "ava@example.com"),
                _member("Ben", "ben@example.com"),
                _member("Cas", "cas@example.com"),
            ),
            template_id="tpl-1",
        )
        service = _service(queue)

        outcome = service.send_ad_hoc(TENANT, body, RUN_ID, reply_to=REPLY_TO)

        assert isinstance(outcome, DeliveryOutcome)
        assert outcome.mode == DELIVERY_MODE_PER_RECIPIENT
        assert outcome.enqueued == 3
        assert len(queue.jobs) == 3
        assert sorted(r for job in queue.jobs for r in job.recipients) == [
            "ava@example.com",
            "ben@example.com",
            "cas@example.com",
        ]

    def test_stamps_resolved_from_and_reply_to_on_every_job(self, queue):
        body = AdHocMailBody(
            mode=DELIVERY_MODE_PER_RECIPIENT,
            result_rows=(
                _member("Ava", "ava@example.com"),
                _member("Ben", "ben@example.com"),
            ),
            template_id="tpl-1",
        )
        service = _service(queue)

        service.send_ad_hoc(TENANT, body, RUN_ID, reply_to=REPLY_TO)

        assert len(queue.jobs) == 2
        for job in queue.jobs:
            assert job.from_address == "noreply@h-dcn.nl"
            assert job.reply_to == REPLY_TO
            assert job.template_id == "tpl-1"

    def test_each_job_carries_that_rows_merge_values(self, queue):
        body = AdHocMailBody(
            mode=DELIVERY_MODE_PER_RECIPIENT,
            result_rows=(
                _member("Ava", "ava@example.com"),
                _member("Ben", "ben@example.com"),
            ),
            template_id="tpl-9",
        )
        service = _service(queue)

        service.send_ad_hoc(TENANT, body, RUN_ID, reply_to=REPLY_TO)

        by_addr = {job.recipients[0]: job for job in queue.jobs}
        assert by_addr["ava@example.com"].merge_values["first_name"] == "Ava"
        assert by_addr["ava@example.com"].merge_values["personal.email"] == "ava@example.com"
        assert by_addr["ben@example.com"].merge_values["first_name"] == "Ben"

    def test_skips_rows_with_no_resolvable_address(self, queue):
        body = AdHocMailBody(
            mode=DELIVERY_MODE_PER_RECIPIENT,
            result_rows=(
                _member("Ava", "ava@example.com"),
                {"member_id": "noaddr", "first_name": "Noa", "personal": {}},
            ),
            template_id="tpl-1",
        )
        service = _service(queue)

        outcome = service.send_ad_hoc(TENANT, body, RUN_ID)

        assert outcome.enqueued == 1
        assert outcome.skipped_no_address == 1
        assert queue.jobs[0].recipients == ("ava@example.com",)

    def test_honours_a_custom_recipient_field(self, queue):
        rows = ({"member_id": "a", "contact": {"work_email": "a@work.example"}},)
        body = AdHocMailBody(
            mode=DELIVERY_MODE_PER_RECIPIENT,
            result_rows=rows,
            template_id="tpl-1",
            recipient_field="contact.work_email",
        )
        service = _service(queue)

        service.send_ad_hoc(TENANT, body, RUN_ID)

        assert queue.jobs[0].recipients == ("a@work.example",)


# ── to_fixed ad-hoc: exactly ONE job, From/Reply-To stamped ─────────────────────────────


class TestAdHocToFixed:
    def test_makes_exactly_one_job_with_recipients_attachment_and_rows(self, queue):
        rows = (_member("Ava", "ava@example.com"), _member("Ben", "ben@example.com"))
        body = AdHocMailBody(
            mode=DELIVERY_MODE_TO_FIXED,
            result_rows=rows,
            recipients=("agent@example.com", "ops@example.com"),
            attachment="csv",
        )
        service = _service(queue)

        outcome = service.send_ad_hoc(TENANT, body, RUN_ID, reply_to=REPLY_TO)

        assert outcome.mode == DELIVERY_MODE_TO_FIXED
        assert outcome.enqueued == 1
        [job] = queue.jobs
        assert job.recipients == ("agent@example.com", "ops@example.com")
        assert job.attachment == {"kind": "csv", "label_options": None}
        assert len(job.rows) == 2
        assert job.from_address == "noreply@h-dcn.nl"
        assert job.reply_to == REPLY_TO

    def test_pdf_labels_attachment_carries_its_label_options(self, queue):
        body = AdHocMailBody(
            mode=DELIVERY_MODE_TO_FIXED,
            result_rows=(_member("Ava", "ava@example.com"),),
            recipients=("agent@example.com",),
            attachment="pdf_labels",
            label_options={"format": "avery_l7160", "sort": "name"},
        )
        service = _service(queue)

        service.send_ad_hoc(TENANT, body, RUN_ID)

        [job] = queue.jobs
        assert job.attachment == {
            "kind": "pdf_labels",
            "label_options": {"format": "avery_l7160", "sort": "name"},
        }


# ── pre-send certification gate: refuse BEFORE enqueue (the SAME gate as the saved path) ─


class TestAdHocPreSendGate:
    def _body(self):
        return AdHocMailBody(
            mode=DELIVERY_MODE_PER_RECIPIENT,
            result_rows=(_member("Ava", "ava@example.com"),),
            template_id="tpl-1",
        )

    def test_not_certified_refuses_before_enqueue(self, queue):
        service = _service(queue, _certified_resolver(certified=False))

        with pytest.raises(MailNotCertified) as excinfo:
            service.send_ad_hoc(TENANT, self._body(), RUN_ID, reply_to=REPLY_TO)

        assert excinfo.value.reason is NotCertifiedReason.NOT_CERTIFIED
        assert queue.jobs == []

    def test_mail_disabled_refuses_before_enqueue(self, queue):
        service = _service(queue, _certified_resolver(enabled=False))

        with pytest.raises(MailNotCertified) as excinfo:
            service.send_ad_hoc(TENANT, self._body(), RUN_ID)

        assert excinfo.value.reason is NotCertifiedReason.MAIL_DISABLED
        assert queue.jobs == []

    def test_no_domain_refuses_before_enqueue(self, queue):
        service = _service(queue, _certified_resolver(domain=None))

        with pytest.raises(MailNotCertified) as excinfo:
            service.send_ad_hoc(TENANT, self._body(), RUN_ID)

        assert excinfo.value.reason is NotCertifiedReason.NO_DOMAIN
        assert queue.jobs == []

    def test_to_fixed_also_refuses_before_enqueue_when_not_certified(self, queue):
        body = AdHocMailBody(
            mode=DELIVERY_MODE_TO_FIXED,
            result_rows=(_member("Ava", "ava@example.com"),),
            recipients=("agent@example.com",),
            attachment="csv",
        )
        service = _service(queue, _certified_resolver(certified=False))

        with pytest.raises(MailNotCertified):
            service.send_ad_hoc(TENANT, body, RUN_ID)
        assert queue.jobs == []


# ── tenancy: the stamped From is the AUTHORITATIVE tenant's (Property 3) ─────────────────


class TestAdHocTenancy:
    def test_from_is_the_tenants_projected_identity(self, queue):
        service = _service(
            queue, _certified_resolver(local_part="info", domain="club.example")
        )
        body = AdHocMailBody(
            mode=DELIVERY_MODE_PER_RECIPIENT,
            result_rows=(_member("Ava", "ava@example.com"),),
            template_id="tpl-1",
        )

        service.send_ad_hoc(TENANT, body, RUN_ID)

        assert queue.jobs[0].from_address == "info@club.example"
        # every enqueued job is tenant-pinned to the authoritative tenant
        assert queue.jobs[0].tenant_id == TENANT

    def test_blank_tenant_is_fail_closed_no_enqueue(self, queue):
        # A blank tenant can carry no projected config → the resolver refuses (fail-closed),
        # so nothing is ever enqueued without an authoritative tenant (Property 3/4).
        service = _service(queue)
        body = AdHocMailBody(
            mode=DELIVERY_MODE_PER_RECIPIENT,
            result_rows=(_member("Ava", "ava@example.com"),),
            template_id="tpl-1",
        )

        with pytest.raises(MailNotCertified):
            service.send_ad_hoc("", body, RUN_ID)
        assert queue.jobs == []


# ── idempotency: stable job id (Property 5) ──────────────────────────────────────────────


class TestAdHocStableJobId:
    def _run(self, queue, run_id):
        body = AdHocMailBody(
            mode=DELIVERY_MODE_PER_RECIPIENT,
            result_rows=(_member("Ava", "ava@example.com"),),
            template_id="tpl-1",
        )
        _service(queue).send_ad_hoc(TENANT, body, run_id)

    def test_same_run_produces_the_same_job_id(self):
        q1, q2 = FakeQueue(), FakeQueue()
        self._run(q1, RUN_ID)
        self._run(q2, RUN_ID)
        assert q1.jobs[0].job_id == q2.jobs[0].job_id

    def test_different_run_ids_produce_different_job_ids(self):
        q1, q2 = FakeQueue(), FakeQueue()
        self._run(q1, "run-A")
        self._run(q2, "run-B")
        assert q1.jobs[0].job_id != q2.jobs[0].job_id

    def test_distinct_recipients_in_one_run_have_distinct_job_ids(self, queue):
        body = AdHocMailBody(
            mode=DELIVERY_MODE_PER_RECIPIENT,
            result_rows=(
                _member("Ava", "ava@example.com"),
                _member("Ben", "ben@example.com"),
            ),
            template_id="tpl-1",
        )
        _service(queue).send_ad_hoc(TENANT, body, RUN_ID)
        assert len({job.job_id for job in queue.jobs}) == 2


# ── shape validation: a malformed ad-hoc body raises before any enqueue ─────────────────


class TestAdHocBodyValidation:
    def test_unknown_mode_raises_before_enqueue(self, queue):
        service = _service(queue)
        body = AdHocMailBody(mode="broadcast", result_rows=(_member("Ava", "a@x.io"),))

        with pytest.raises(AdHocMailInvalid):
            service.send_ad_hoc(TENANT, body, RUN_ID)
        assert queue.jobs == []

    def test_per_recipient_with_no_rows_raises(self, queue):
        service = _service(queue)
        body = AdHocMailBody(mode=DELIVERY_MODE_PER_RECIPIENT, result_rows=())

        with pytest.raises(AdHocMailInvalid):
            service.send_ad_hoc(TENANT, body, RUN_ID)
        assert queue.jobs == []

    # ── bug: template-less per_recipient send (per-recipient-template-guard) ─────────────
    #
    # Property 1 (Bug Condition): a per_recipient send carrying result rows but NO template_id
    # must FAIL FAST with AdHocMailInvalid before any enqueue — a per-recipient fan-out has no
    # body source but a stored template, so a template-less job is doomed. On UNFIXED code the
    # service wrongly ACCEPTS it (enqueues one job per row, returns a 202 "sent"), and the worker
    # then dead-letters every job ("carries no template_id") — a false "sent": mail never arrives.

    def test_per_recipient_with_no_template_id_raises(self, queue):
        # The user's real flow: per_recipient + rows + template_id=None (the bug condition).
        service = _service(queue)
        body = AdHocMailBody(
            mode=DELIVERY_MODE_PER_RECIPIENT,
            result_rows=(_member("Ava", "ava@example.com"),),
            template_id=None,
        )

        with pytest.raises(AdHocMailInvalid) as excinfo:
            service.send_ad_hoc(TENANT, body, RUN_ID)
        assert "a template is required for a per-recipient send" in str(
            excinfo.value.detail
        )
        # ZERO jobs enqueued (no false "sent", no dead-letter-bound fan-out).
        assert queue.jobs == []

    def test_per_recipient_with_blank_template_id_raises(self, queue):
        # A blank template id is normalized to None at the edge, but assert the service itself is
        # robust to a blank slipping through (both None and "" are the bug condition).
        service = _service(queue)
        body = AdHocMailBody(
            mode=DELIVERY_MODE_PER_RECIPIENT,
            result_rows=(_member("Ava", "ava@example.com"),),
            template_id="",
        )

        with pytest.raises(AdHocMailInvalid):
            service.send_ad_hoc(TENANT, body, RUN_ID)
        assert queue.jobs == []

    def test_to_fixed_with_no_template_id_is_still_allowed(self, queue):
        # Preservation: the template guard applies ONLY to per_recipient. A to_fixed send needs
        # no template and must CONTINUE TO enqueue exactly one job with no template_id.
        service = _service(queue)
        body = AdHocMailBody(
            mode=DELIVERY_MODE_TO_FIXED,
            result_rows=(_member("Ava", "ava@example.com"),),
            recipients=("agent@example.com",),
            attachment="csv",
            template_id=None,
        )

        outcome = service.send_ad_hoc(TENANT, body, RUN_ID)

        assert outcome.enqueued == 1
        assert len(queue.jobs) == 1
        assert queue.jobs[0].template_id is None

    def test_to_fixed_with_no_recipients_raises(self, queue):
        service = _service(queue)
        body = AdHocMailBody(
            mode=DELIVERY_MODE_TO_FIXED,
            result_rows=(_member("Ava", "a@x.io"),),
            recipients=(),
            attachment="csv",
        )

        with pytest.raises(AdHocMailInvalid):
            service.send_ad_hoc(TENANT, body, RUN_ID)
        assert queue.jobs == []

    def test_to_fixed_with_only_blank_recipients_raises(self, queue):
        service = _service(queue)
        body = AdHocMailBody(
            mode=DELIVERY_MODE_TO_FIXED,
            result_rows=(_member("Ava", "a@x.io"),),
            recipients=("", "   "),
            attachment="csv",
        )

        with pytest.raises(AdHocMailInvalid):
            service.send_ad_hoc(TENANT, body, RUN_ID)
        assert queue.jobs == []

    def test_validation_runs_before_the_certification_gate(self, queue):
        # A malformed body is rejected as AdHocMailInvalid even for an un-certified tenant —
        # the shape check is first, so the edge returns the right 422 (not a certification 4xx).
        service = _service(queue, _certified_resolver(certified=False))
        body = AdHocMailBody(mode="nope", result_rows=())

        with pytest.raises(AdHocMailInvalid):
            service.send_ad_hoc(TENANT, body, RUN_ID)
        assert queue.jobs == []
