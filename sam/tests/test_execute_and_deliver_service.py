"""
SAM pytest for the :class:`ExecuteAndDeliverService` (R4, task 4.1) — the storage-agnostic
execute-and-deliver service that resolves a set + its delivery block, re-fetches member rows
through the repository (tenant pinned — Property 1), runs the pivot, and FANS the result out
into enqueue jobs on the queue PORT.

Phase 4 testing (tasks.md): "SAM pytest for the service fan-out (N jobs vs 1) ...". These
exercise the service through its three injected ports — a tenant-scoped FAKE repository, a
fake :class:`PivotRunner`, and a fake :class:`MailQueue` that CAPTURES the enqueued jobs — with
NO AWS/boto3 and NO real SQS (task 4.2 wires the real queue; task 4.3 the worker). The fan-out
is the heart of R4: ``per_recipient`` → one job per member (each with that member's merge
values + the template ref); ``to_fixed`` → one job (fixed recipients + attachment). The
tenant-pinned re-fetch (never a scan) and the stable idempotency job id are pinned too.

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

from sam.members.domain._membership_errors import AnalyticsSetNotFound
from sam.members.domain.analytics_set import (
    DELIVERY_MODE_PER_RECIPIENT,
    DELIVERY_MODE_TO_FIXED,
    AnalyticsSetEntry,
)
from sam.members.domain.execute_and_deliver import (
    DeliveryNotConfigured,
    DeliveryOutcome,
    ExecuteAndDeliverService,
    MailJob,
    MailNotCertified,
    MailQueue,
    PivotRunner,
)
from sam.members.domain.mail_sender_resolver import (
    MailSenderResolver,
    NotCertifiedReason,
)

TENANT = "h-dcn"
SET_ID = "set-abc"
RUN_ID = "run-0001"


# ── fakes (the three injected ports) ────────────────────────────────────────────────────


class FakeRepo:
    """A tenant-scoped fake Members repository that pins ``tenant_id`` like the real one.

    Holds analytics-sets keyed by ``(tenant_id, set_id)`` and member rows keyed by
    ``tenant_id`` — so a cross-tenant read is structurally impossible, the same isolation the
    real repository's partition key enforces (Property 1). It RECORDS every tenant it was asked
    for so a test can assert the re-fetch was keyed by the authoritative tenant and NEVER did a
    tenant-less scan.
    """

    def __init__(self):
        self._sets: dict[tuple, AnalyticsSetEntry] = {}
        self._members: dict[str, list[dict]] = {}
        self.list_members_calls: list[str] = []
        self.get_set_calls: list[tuple] = []
        # Records the send-run tallies the service creates at enqueue (R9.1) so a test can assert
        # a `mailrun#` was created with the right mode + recipient_count. Keyed by (tenant, run).
        self.mail_runs: dict[tuple, dict] = {}

    # seed helpers
    def put_set(self, entry: AnalyticsSetEntry) -> None:
        self._sets[(entry.tenant_id, entry.set_id)] = entry

    def put_members(self, tenant_id: str, rows: list[dict]) -> None:
        self._members[tenant_id] = rows

    # repository surface used by the service
    def get_analytics_set(self, tenant_id, set_id):
        self.get_set_calls.append((tenant_id, set_id))
        return self._sets.get((tenant_id, set_id))

    def list_members(self, tenant_id, *, filters=None, scope_filter=None):
        # Pin to the tenant partition — a tenant we were never seeded for yields [] (NEVER a
        # scan across other tenants' rows).
        self.list_members_calls.append(tenant_id)
        return list(self._members.get(tenant_id, []))

    def create_mail_run(self, tenant_id, run_id, *, mode, triggered_by, recipient_count):
        # Idempotent on run_id, like the real repo: a second create for the same run is a no-op.
        key = (tenant_id, run_id)
        existing = self.mail_runs.get(key)
        if existing is not None:
            return existing
        run = {
            "tenant_id": tenant_id,
            "run_id": run_id,
            "mode": mode,
            "triggered_by": triggered_by,
            "recipient_count": recipient_count,
            "status": "queued",
            "sent": 0,
            "failed": 0,
        }
        self.mail_runs[key] = run
        return run


class PassThroughPivot:
    """A fake :class:`PivotRunner` that returns the re-fetched rows unchanged (identity).

    A ``list`` set's result rows ARE the member rows; this keeps the test's assertions about
    fan-out focused on the delivery logic, not on pivot math. It also RECORDS the rows it was
    handed so a test can prove the service re-fetched FRESH rows and passed them through.
    """

    def __init__(self):
        self.seen_rows = None
        self.seen_definition = None

    def run(self, tenant_id, definition, rows):
        self.seen_definition = definition
        self.seen_rows = list(rows)
        return list(rows)


class CannedPivot:
    """A fake :class:`PivotRunner` that returns a fixed set of result rows (a count/list output)."""

    def __init__(self, result_rows):
        self._result = list(result_rows)

    def run(self, tenant_id, definition, rows):
        return list(self._result)


class FakeQueue:
    """An in-memory :class:`MailQueue` that CAPTURES every enqueued job (no SQS, no boto3)."""

    def __init__(self):
        self.jobs: list[MailJob] = []

    def enqueue(self, job):
        self.jobs.append(job)


class FakeMailConfigReader:
    """A static :class:`MailConfigReader` for the pre-send resolver (no projection/DynamoDB).

    Models a tenant's projected ``config#mail`` flags in memory so the resolver can be driven
    without AWS. Defaults model a CERTIFIED tenant (``mail_enabled`` + ``mail_certified`` + a
    domain) so the happy-path fan-out tests get a usable From; flip the flags / drop the domain
    to drive the fail-closed refusal branches (mail-spec task 1.3). Pins by ``tenant_id`` — an
    unseeded tenant is fail-closed (disabled, uncertified, no domain), Property 3/4.
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
    """Build a :class:`MailSenderResolver` over a static reader (certified by default)."""
    return MailSenderResolver(FakeMailConfigReader(**overrides))


def _build_service(repo, pivot, queue, resolver=None):
    """Build the service with a CERTIFIED sender resolver by default (mail-spec task 1.3).

    One shared builder so the whole suite constructs the service the same way; a test that
    exercises the pre-send refusal passes an explicitly un-certified ``resolver``.
    """
    return ExecuteAndDeliverService(
        repo, pivot, queue, resolver or _certified_resolver()
    )


# ── builders ──────────────────────────────────────────────────────────────────────────


def _definition():
    return {
        "data_source": "members",
        "group_columns": [],
        "aggregate_measures": [],
        "filters": {},
        "display_mode": "flat",
    }


def _set(delivery):
    return AnalyticsSetEntry(
        tenant_id=TENANT,
        set_id=SET_ID,
        name="Clubblad",
        kind="list",
        definition=_definition(),
        delivery=delivery,
        created_at="2024-01-01T00:00:00+00:00",
        updated_at="2024-01-01T00:00:00+00:00",
    )


def _member(first_name, email):
    return {
        "member_id": first_name.lower(),
        "first_name": first_name,
        "personal": {"email": email, "first_name": first_name},
        "membership_type": "lid",
    }


@pytest.fixture()
def repo():
    return FakeRepo()


@pytest.fixture()
def queue():
    return FakeQueue()


# ── port conformance ────────────────────────────────────────────────────────────────────


class TestPortConformance:
    def test_fake_queue_satisfies_mail_queue_port(self, queue):
        assert isinstance(queue, MailQueue)

    def test_fake_pivot_satisfies_pivot_runner_port(self):
        assert isinstance(PassThroughPivot(), PivotRunner)


# ── per_recipient fan-out: ONE job PER member ───────────────────────────────────────────


class TestPerRecipientFanOut:
    def _service(self, repo, queue, result_rows=None):
        pivot = CannedPivot(result_rows) if result_rows is not None else PassThroughPivot()
        return _build_service(repo, pivot, queue), pivot

    def test_per_recipient_fans_out_to_n_jobs_one_per_member(self, repo, queue):
        repo.put_set(_set({"mode": DELIVERY_MODE_PER_RECIPIENT, "template_id": "tpl-1"}))
        members = [
            _member("Ava", "ava@example.com"),
            _member("Ben", "ben@example.com"),
            _member("Cas", "cas@example.com"),
        ]
        repo.put_members(TENANT, members)
        service, _ = self._service(repo, queue)

        outcome = service.execute_and_deliver(TENANT, SET_ID, RUN_ID)

        assert isinstance(outcome, DeliveryOutcome)
        assert outcome.mode == DELIVERY_MODE_PER_RECIPIENT
        assert outcome.enqueued == 3  # N members → N jobs
        assert len(queue.jobs) == 3
        # one job per distinct member address
        assert sorted(r for job in queue.jobs for r in job.recipients) == [
            "ava@example.com",
            "ben@example.com",
            "cas@example.com",
        ]

    def test_per_recipient_job_carries_that_members_merge_values_and_template(
        self, repo, queue
    ):
        repo.put_set(_set({"mode": DELIVERY_MODE_PER_RECIPIENT, "template_id": "tpl-9"}))
        repo.put_members(TENANT, [_member("Ava", "ava@example.com")])
        service, _ = self._service(repo, queue)

        service.execute_and_deliver(TENANT, SET_ID, RUN_ID)

        [job] = queue.jobs
        assert job.recipients == ("ava@example.com",)
        assert job.template_id == "tpl-9"
        # merge values are THIS member's own fields (flattened leaf + dotted), for the merge.
        assert job.merge_values["first_name"] == "Ava"
        assert job.merge_values["personal.email"] == "ava@example.com"
        assert job.merge_values["membership_type"] == "lid"
        # per_recipient carries no fixed attachment / no bulk rows (it merges per-member).
        assert job.attachment is None
        assert job.rows == ()

    def test_per_recipient_each_job_has_its_own_merge_values(self, repo, queue):
        repo.put_set(_set({"mode": DELIVERY_MODE_PER_RECIPIENT, "template_id": "tpl-1"}))
        repo.put_members(
            TENANT, [_member("Ava", "ava@example.com"), _member("Ben", "ben@example.com")]
        )
        service, _ = self._service(repo, queue)

        service.execute_and_deliver(TENANT, SET_ID, RUN_ID)

        by_addr = {job.recipients[0]: job for job in queue.jobs}
        assert by_addr["ava@example.com"].merge_values["first_name"] == "Ava"
        assert by_addr["ben@example.com"].merge_values["first_name"] == "Ben"

    def test_per_recipient_skips_rows_with_no_resolvable_address(self, repo, queue):
        repo.put_set(_set({"mode": DELIVERY_MODE_PER_RECIPIENT, "template_id": "tpl-1"}))
        repo.put_members(
            TENANT,
            [
                _member("Ava", "ava@example.com"),
                {"member_id": "noaddr", "first_name": "Noa", "personal": {}},
            ],
        )
        service, _ = self._service(repo, queue)

        outcome = service.execute_and_deliver(TENANT, SET_ID, RUN_ID)

        assert outcome.enqueued == 1  # only the mailable member
        assert outcome.skipped_no_address == 1
        assert len(queue.jobs) == 1
        assert queue.jobs[0].recipients == ("ava@example.com",)

    def test_per_recipient_zero_members_enqueues_nothing(self, repo, queue):
        repo.put_set(_set({"mode": DELIVERY_MODE_PER_RECIPIENT, "template_id": "tpl-1"}))
        repo.put_members(TENANT, [])
        service, _ = self._service(repo, queue)

        outcome = service.execute_and_deliver(TENANT, SET_ID, RUN_ID)

        assert outcome.enqueued == 0
        assert queue.jobs == []


# ── to_fixed fan-out: exactly ONE job ───────────────────────────────────────────────────


class TestToFixedFanOut:
    def _service(self, repo, queue, result_rows):
        return _build_service(repo, CannedPivot(result_rows), queue)

    def test_to_fixed_makes_exactly_one_job(self, repo, queue):
        repo.put_set(
            _set(
                {
                    "mode": DELIVERY_MODE_TO_FIXED,
                    "recipients": ["agent@example.com", "ops@example.com"],
                    "attachment": "csv",
                }
            )
        )
        repo.put_members(TENANT, [])  # rows come from the pivot result below
        rows = [_member("Ava", "ava@example.com"), _member("Ben", "ben@example.com")]
        service = self._service(repo, queue, rows)

        outcome = service.execute_and_deliver(TENANT, SET_ID, RUN_ID)

        assert outcome.mode == DELIVERY_MODE_TO_FIXED
        assert outcome.enqueued == 1  # ONE job regardless of result-row count
        assert len(queue.jobs) == 1

    def test_to_fixed_job_carries_fixed_recipients_and_attachment_and_rows(
        self, repo, queue
    ):
        repo.put_set(
            _set(
                {
                    "mode": DELIVERY_MODE_TO_FIXED,
                    "recipients": ["agent@example.com"],
                    "attachment": "pdf_labels",
                    "label_options": {"format": "avery_l7160", "sort": "name"},
                }
            )
        )
        repo.put_members(TENANT, [])
        rows = [_member("Ava", "ava@example.com"), _member("Ben", "ben@example.com")]
        service = self._service(repo, queue, rows)

        service.execute_and_deliver(TENANT, SET_ID, RUN_ID)

        [job] = queue.jobs
        assert job.recipients == ("agent@example.com",)
        assert job.attachment == {
            "kind": "pdf_labels",
            "label_options": {"format": "avery_l7160", "sort": "name"},
        }
        # the whole result ships once on the single job (the worker builds the attachment).
        assert len(job.rows) == 2
        assert job.merge_values == {}

    def test_to_fixed_no_attachment_is_none(self, repo, queue):
        repo.put_set(
            _set(
                {
                    "mode": DELIVERY_MODE_TO_FIXED,
                    "recipients": ["agent@example.com"],
                    "attachment": None,
                    "template_id": "tpl-cover",
                }
            )
        )
        repo.put_members(TENANT, [])
        service = self._service(repo, queue, [_member("Ava", "ava@example.com")])

        service.execute_and_deliver(TENANT, SET_ID, RUN_ID)

        [job] = queue.jobs
        assert job.attachment is None
        assert job.template_id == "tpl-cover"


# ── tenant pinning on the re-fetch (Property 1, never a scan) ────────────────────────────


class TestTenantPinning:
    def test_refetch_is_keyed_by_the_authoritative_tenant(self, repo, queue):
        repo.put_set(_set({"mode": DELIVERY_MODE_PER_RECIPIENT, "template_id": "t"}))
        repo.put_members(TENANT, [_member("Ava", "ava@example.com")])
        pivot = PassThroughPivot()
        service = _build_service(repo, pivot, queue)

        service.execute_and_deliver(TENANT, SET_ID, RUN_ID)

        # The set lookup AND the member re-fetch were both keyed by the caller's tenant.
        assert repo.get_set_calls == [(TENANT, SET_ID)]
        assert repo.list_members_calls == [TENANT]
        # The pivot ran over the FRESH re-fetched rows (not a stale/stored snapshot).
        assert [r["member_id"] for r in pivot.seen_rows] == ["ava"]

    def test_another_tenants_set_is_not_found(self, repo, queue):
        # Seed the set under h-dcn; a different tenant must not resolve it (isolation).
        repo.put_set(_set({"mode": DELIVERY_MODE_PER_RECIPIENT, "template_id": "t"}))
        service = _build_service(repo, PassThroughPivot(), queue)

        with pytest.raises(AnalyticsSetNotFound):
            service.execute_and_deliver("other-tenant", SET_ID, RUN_ID)
        assert queue.jobs == []

    def test_refetch_never_bleeds_another_tenants_members(self, repo, queue):
        repo.put_set(_set({"mode": DELIVERY_MODE_PER_RECIPIENT, "template_id": "t"}))
        # h-dcn has no members seeded; another tenant does — the run must see NONE of them.
        repo.put_members("other-tenant", [_member("Zoe", "zoe@other.example.com")])
        service = _build_service(repo, PassThroughPivot(), queue)

        outcome = service.execute_and_deliver(TENANT, SET_ID, RUN_ID)

        assert outcome.enqueued == 0
        assert queue.jobs == []


# ── stable job id (idempotency, design §4.2) ─────────────────────────────────────────────


class TestStableJobId:
    def _run(self, repo, queue, run_id):
        repo.put_set(_set({"mode": DELIVERY_MODE_PER_RECIPIENT, "template_id": "t"}))
        repo.put_members(TENANT, [_member("Ava", "ava@example.com")])
        service = _build_service(repo, PassThroughPivot(), queue)
        return service.execute_and_deliver(TENANT, SET_ID, run_id)

    def test_same_run_produces_the_same_job_id(self):
        q1, q2 = FakeQueue(), FakeQueue()
        self._run(FakeRepo(), q1, RUN_ID)
        self._run(FakeRepo(), q2, RUN_ID)
        assert q1.jobs[0].job_id == q2.jobs[0].job_id  # deterministic → dedupe-able

    def test_different_run_ids_produce_different_job_ids(self):
        q1, q2 = FakeQueue(), FakeQueue()
        self._run(FakeRepo(), q1, "run-A")
        self._run(FakeRepo(), q2, "run-B")
        assert q1.jobs[0].job_id != q2.jobs[0].job_id  # distinct runs never collide

    def test_distinct_recipients_in_one_run_have_distinct_job_ids(self):
        repo, queue = FakeRepo(), FakeQueue()
        repo.put_set(_set({"mode": DELIVERY_MODE_PER_RECIPIENT, "template_id": "t"}))
        repo.put_members(
            TENANT, [_member("Ava", "ava@example.com"), _member("Ben", "ben@example.com")]
        )
        service = _build_service(repo, PassThroughPivot(), queue)
        service.execute_and_deliver(TENANT, SET_ID, RUN_ID)
        ids = {job.job_id for job in queue.jobs}
        assert len(ids) == 2  # one id per recipient, no aliasing

    def test_to_fixed_job_id_is_stable_across_runs(self):
        def run(queue):
            repo = FakeRepo()
            repo.put_set(
                _set(
                    {
                        "mode": DELIVERY_MODE_TO_FIXED,
                        "recipients": ["agent@example.com"],
                        "attachment": "csv",
                    }
                )
            )
            repo.put_members(TENANT, [])
            service = _build_service(repo, CannedPivot([]), queue)
            service.execute_and_deliver(TENANT, SET_ID, RUN_ID)

        q1, q2 = FakeQueue(), FakeQueue()
        run(q1)
        run(q2)
        assert q1.jobs[0].job_id == q2.jobs[0].job_id


# ── delivery-not-configured + not-found guards ──────────────────────────────────────────


class TestGuards:
    def test_set_without_delivery_block_raises(self, repo, queue):
        repo.put_set(_set(None))  # legacy set, no delivery
        repo.put_members(TENANT, [_member("Ava", "ava@example.com")])
        service = _build_service(repo, PassThroughPivot(), queue)

        with pytest.raises(DeliveryNotConfigured):
            service.execute_and_deliver(TENANT, SET_ID, RUN_ID)
        assert queue.jobs == []

    def test_absent_set_raises_not_found(self, repo, queue):
        service = _build_service(repo, PassThroughPivot(), queue)
        with pytest.raises(AnalyticsSetNotFound):
            service.execute_and_deliver(TENANT, "nope", RUN_ID)


# ── mail-spec task 1.3: resolve + STAMP the tenant From + user Reply-To onto every job ───
#
# The pre-send resolver resolves the active tenant's From (noreply@<tenant-domain>) ONCE at
# enqueue time, and the service stamps that From + the triggering user's Reply-To onto EVERY
# job for BOTH modes, so the worker FORWARDS them to SES without re-resolving (design "What to
# CHANGE" #1/#4; MailJob EXTENDED carries from_address + reply_to). A not-certified tenant is
# refused BEFORE enqueue with the TYPED reason — no job, no substitute sender (Property 2/4/6).


class TestSenderStamping:
    REPLY_TO = "webmaster@h-dcn.nl"

    def test_per_recipient_stamps_resolved_from_and_reply_to_on_every_job(
        self, repo, queue
    ):
        repo.put_set(_set({"mode": DELIVERY_MODE_PER_RECIPIENT, "template_id": "tpl-1"}))
        repo.put_members(
            TENANT,
            [
                _member("Ava", "ava@example.com"),
                _member("Ben", "ben@example.com"),
                _member("Cas", "cas@example.com"),
            ],
        )
        service = _build_service(repo, PassThroughPivot(), queue)

        service.execute_and_deliver(TENANT, SET_ID, RUN_ID, reply_to=self.REPLY_TO)

        assert len(queue.jobs) == 3
        # EVERY per-recipient job carries the SAME resolved tenant From + the user Reply-To.
        for job in queue.jobs:
            assert job.from_address == "noreply@h-dcn.nl"
            assert job.reply_to == self.REPLY_TO

    def test_to_fixed_stamps_resolved_from_and_reply_to_on_the_job(self, repo, queue):
        repo.put_set(
            _set(
                {
                    "mode": DELIVERY_MODE_TO_FIXED,
                    "recipients": ["agent@example.com"],
                    "attachment": "csv",
                }
            )
        )
        repo.put_members(TENANT, [])
        service = _build_service(
            repo, CannedPivot([_member("Ava", "ava@example.com")]), queue
        )

        service.execute_and_deliver(TENANT, SET_ID, RUN_ID, reply_to=self.REPLY_TO)

        [job] = queue.jobs
        assert job.from_address == "noreply@h-dcn.nl"
        assert job.reply_to == self.REPLY_TO

    def test_from_honours_the_tenants_projected_local_part(self, repo, queue):
        # A tenant that authored a non-default local-part gets From = <local_part>@<domain>.
        resolver = _certified_resolver(local_part="info", domain="club.example")
        repo.put_set(_set({"mode": DELIVERY_MODE_PER_RECIPIENT, "template_id": "t"}))
        repo.put_members(TENANT, [_member("Ava", "ava@example.com")])
        service = _build_service(repo, PassThroughPivot(), queue, resolver)

        service.execute_and_deliver(TENANT, SET_ID, RUN_ID, reply_to=self.REPLY_TO)

        [job] = queue.jobs
        assert job.from_address == "info@club.example"

    def test_unattended_run_stamps_from_with_no_reply_to(self, repo, queue):
        # A scheduled/unattended run has no triggering user → reply_to defaults to None, but the
        # From still carries the tenant identity (R4.3 — Reply-To optional, From required).
        repo.put_set(_set({"mode": DELIVERY_MODE_PER_RECIPIENT, "template_id": "t"}))
        repo.put_members(TENANT, [_member("Ava", "ava@example.com")])
        service = _build_service(repo, PassThroughPivot(), queue)

        service.execute_and_deliver(TENANT, SET_ID, RUN_ID)  # no reply_to

        [job] = queue.jobs
        assert job.from_address == "noreply@h-dcn.nl"
        assert job.reply_to is None


# ── mail-spec task 1.3: NOT-CERTIFIED refuses BEFORE enqueue (no job, typed reason) ──────


class TestPreSendCertificationGate:
    def test_not_certified_tenant_refuses_before_enqueue(self, repo, queue):
        repo.put_set(_set({"mode": DELIVERY_MODE_PER_RECIPIENT, "template_id": "t"}))
        repo.put_members(TENANT, [_member("Ava", "ava@example.com")])
        service = _build_service(
            repo, PassThroughPivot(), queue, _certified_resolver(certified=False)
        )

        with pytest.raises(MailNotCertified) as excinfo:
            service.execute_and_deliver(TENANT, SET_ID, RUN_ID, reply_to="u@h-dcn.nl")

        # The TYPED machine reason rides on the exception; NOTHING was enqueued (no substitute).
        assert excinfo.value.reason is NotCertifiedReason.NOT_CERTIFIED
        assert queue.jobs == []

    def test_mail_disabled_tenant_refuses_with_the_disabled_reason(self, repo, queue):
        repo.put_set(_set({"mode": DELIVERY_MODE_PER_RECIPIENT, "template_id": "t"}))
        repo.put_members(TENANT, [_member("Ava", "ava@example.com")])
        service = _build_service(
            repo, PassThroughPivot(), queue, _certified_resolver(enabled=False)
        )

        with pytest.raises(MailNotCertified) as excinfo:
            service.execute_and_deliver(TENANT, SET_ID, RUN_ID)

        assert excinfo.value.reason is NotCertifiedReason.MAIL_DISABLED
        assert queue.jobs == []

    def test_no_domain_tenant_refuses_with_the_no_domain_reason(self, repo, queue):
        # Certified + enabled but no projected domain → no From composable, never a guessed host
        # (R4.2 — the jabaki.nl foreign-sender regression stays dead).
        repo.put_set(_set({"mode": DELIVERY_MODE_PER_RECIPIENT, "template_id": "t"}))
        repo.put_members(TENANT, [_member("Ava", "ava@example.com")])
        service = _build_service(
            repo, PassThroughPivot(), queue, _certified_resolver(domain=None)
        )

        with pytest.raises(MailNotCertified) as excinfo:
            service.execute_and_deliver(TENANT, SET_ID, RUN_ID)

        assert excinfo.value.reason is NotCertifiedReason.NO_DOMAIN
        assert queue.jobs == []

    def test_to_fixed_also_refuses_before_enqueue_when_not_certified(self, repo, queue):
        # The gate applies to BOTH modes (a to_fixed run is refused up front too).
        repo.put_set(
            _set(
                {
                    "mode": DELIVERY_MODE_TO_FIXED,
                    "recipients": ["agent@example.com"],
                    "attachment": "csv",
                }
            )
        )
        repo.put_members(TENANT, [])
        service = _build_service(
            repo,
            CannedPivot([_member("Ava", "ava@example.com")]),
            queue,
            _certified_resolver(certified=False),
        )

        with pytest.raises(MailNotCertified):
            service.execute_and_deliver(TENANT, SET_ID, RUN_ID)
        assert queue.jobs == []
