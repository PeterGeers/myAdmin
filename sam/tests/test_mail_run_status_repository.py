"""
Mail-spec task 3.1 — tests for the SEND-RUN STATUS repository methods on
:class:`DynamoDbMembersRepository` (R9.1/R9.5/R9.6; design "Resolved implementation choices").

The DECIDED model is a SUMMARY TALLY (``mailrun#<run_id>``) + FAILURE-ONLY sub-records
(``mailrecipient#<run_id>#<n>``). These tests pin that behaviour over a faithful in-memory fake
table (no moto, no live AWS — same ``get_item`` / ``put_item`` / ``delete_item`` / ``query``
surface the repository uses):

- the tally LIFECYCLE: written ``queued`` at enqueue with ``recipient_count``; advanced
  ``queued`` → ``sending`` → ``completed`` by the worker; ``sent`` / ``failed`` increments;
- a FAILURE sub-record is written ONLY on a failure (a success is only COUNTED in the tally);
- a LATE async bounce (R8.4) for a previously-sent recipient CREATES a sub-record AND adjusts the
  run tally (sent→failed);
- the ``ttl`` epoch attribute is present on both record kinds (DEFAULT 90 days);
- a manual delete removes the run tally AND all its failure sub-records;
- TENANCY: every op pins ``tenant_id`` (Property 3) and a second tenant's run is invisible; no
  ``.scan()`` (the fake has none; the structural guard lives in the invariant test).

Validates: Requirements 9.1, 9.5, 9.6; design Property 3.
"""

from __future__ import annotations

import os
import sys

import pytest

# repo root + backend/src on sys.path (mirrors test_members_repository.py) so
# `sam.members...` and its `services.dynamodb_client` dependency both import.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
_BACKEND_SRC = os.path.join(_REPO_ROOT, "backend", "src")
if _BACKEND_SRC not in sys.path:
    sys.path.insert(0, _BACKEND_SRC)

from sam.members.repository import table_design as td
from sam.members.repository.members_repository import (
    MAIL_RECIPIENT_STATUS_BOUNCED,
    MAIL_RECIPIENT_STATUS_COMPLAINT,
    MAIL_RECIPIENT_STATUS_FAILED,
    MAIL_RUN_STATUS_COMPLETED,
    MAIL_RUN_STATUS_QUEUED,
    MAIL_RUN_STATUS_SENDING,
    MAIL_RUN_TTL_SECONDS,
    DynamoDbMembersRepository,
)

TENANT = "tenant-a"
RUN = "run-123"


# ---------------------------------------------------------------------------
# In-memory fake DynamoDB table (the surface the repository uses).
# ---------------------------------------------------------------------------


def _walk_condition(condition):
    expr = condition.get_expression()
    op = expr["operator"]
    values = expr["values"]
    if op == "AND":
        pk = sk_prefix = None
        for sub in values:
            t, p = _walk_condition(sub)
            pk = pk if t is None else t
            sk_prefix = sk_prefix if p is None else p
        return pk, sk_prefix
    if op == "=":
        attr = values[0].name
        if attr == td.PARTITION_KEY_ATTR:
            return values[1], None
        return None, None
    if op == "begins_with":
        return None, values[1]
    return None, None  # pragma: no cover


class FakeDynamoTable:
    """In-memory stand-in for a boto3 DynamoDB Table (the used surface only).

    Stores items keyed by ``(tenant_id, sk)``. ``query`` honours a partition-key ``eq`` + an
    optional sort-key ``begins_with`` and returns ONLY the matching tenant's items, so a second
    tenant's records are structurally unreturnable (the isolation a real table + ``LeadingKeys``
    enforce). Deliberately has NO ``scan`` — a repository slip would ``AttributeError``.
    """

    def __init__(self, name="test_members"):
        self.name = name
        self.store: dict[tuple, dict] = {}

    def get_item(self, Key=None):
        item = self.store.get((Key[td.PARTITION_KEY_ATTR], Key[td.SORT_KEY_ATTR]))
        return {"Item": dict(item)} if item is not None else {}

    def query(self, KeyConditionExpression=None, ExclusiveStartKey=None):
        pk, sk_prefix = _walk_condition(KeyConditionExpression)
        items = [
            dict(v)
            for k, v in self.store.items()
            if k[0] == pk and (sk_prefix is None or k[1].startswith(sk_prefix))
        ]
        return {"Items": items}

    def put_item(self, Item=None):
        self.store[(Item[td.PARTITION_KEY_ATTR], Item[td.SORT_KEY_ATTR])] = dict(Item)
        return {}

    def delete_item(self, Key=None):
        self.store.pop((Key[td.PARTITION_KEY_ATTR], Key[td.SORT_KEY_ATTR]), None)
        return {}


@pytest.fixture()
def table() -> FakeDynamoTable:
    return FakeDynamoTable()


@pytest.fixture()
def repo(table) -> DynamoDbMembersRepository:
    return DynamoDbMembersRepository(table=table)


# ---------------------------------------------------------------------------
# 1. The tally lifecycle: queued → sending → completed, sent/failed increments.
# ---------------------------------------------------------------------------


class TestMailRunTallyLifecycle:
    def test_create_mail_run_writes_a_queued_tally_with_the_recipient_count(self, repo):
        run = repo.create_mail_run(
            TENANT, RUN, mode="per_recipient", triggered_by="sub-1", recipient_count=5
        )
        assert run["status"] == MAIL_RUN_STATUS_QUEUED
        assert run["recipient_count"] == 5
        assert run["mode"] == "per_recipient"
        assert run["triggered_by"] == "sub-1"
        assert run["sent"] == 0
        assert run["failed"] == 0
        assert run["run_id"] == RUN
        # Stored + readable back as the same tally.
        assert repo.get_mail_run(TENANT, RUN)["status"] == MAIL_RUN_STATUS_QUEUED

    def test_create_mail_run_is_idempotent_and_never_resets_an_advanced_run(self, repo):
        repo.create_mail_run(
            TENANT, RUN, mode="per_recipient", triggered_by="sub-1", recipient_count=5
        )
        repo.update_mail_run_status(TENANT, RUN, MAIL_RUN_STATUS_SENDING)
        repo.increment_mail_run_counts(TENANT, RUN, sent=2)
        # A re-enqueue of the same run (an at-least-once enqueue retry) must NOT clobber it.
        again = repo.create_mail_run(
            TENANT, RUN, mode="per_recipient", triggered_by="sub-1", recipient_count=5
        )
        assert again["status"] == MAIL_RUN_STATUS_SENDING
        assert again["sent"] == 2

    def test_status_advances_queued_to_sending_to_completed(self, repo):
        repo.create_mail_run(
            TENANT, RUN, mode="to_fixed", triggered_by="sub-1", recipient_count=1
        )
        assert (
            repo.update_mail_run_status(TENANT, RUN, MAIL_RUN_STATUS_SENDING)["status"]
            == MAIL_RUN_STATUS_SENDING
        )
        assert (
            repo.update_mail_run_status(TENANT, RUN, MAIL_RUN_STATUS_COMPLETED)["status"]
            == MAIL_RUN_STATUS_COMPLETED
        )

    def test_update_status_on_a_missing_run_returns_none(self, repo):
        assert repo.update_mail_run_status(TENANT, "no-such-run", MAIL_RUN_STATUS_SENDING) is None

    def test_unknown_status_is_rejected(self, repo):
        repo.create_mail_run(
            TENANT, RUN, mode="to_fixed", triggered_by="sub-1", recipient_count=1
        )
        with pytest.raises(ValueError):
            repo.update_mail_run_status(TENANT, RUN, "delivered")

    def test_sent_and_failed_increments_accumulate(self, repo):
        repo.create_mail_run(
            TENANT, RUN, mode="per_recipient", triggered_by="sub-1", recipient_count=10
        )
        repo.increment_mail_run_counts(TENANT, RUN, sent=3)
        repo.increment_mail_run_counts(TENANT, RUN, sent=4, failed=1)
        run = repo.get_mail_run(TENANT, RUN)
        assert run["sent"] == 7
        assert run["failed"] == 1

    def test_increment_counts_never_goes_negative(self, repo):
        repo.create_mail_run(
            TENANT, RUN, mode="per_recipient", triggered_by="sub-1", recipient_count=1
        )
        run = repo.increment_mail_run_counts(TENANT, RUN, sent=-5)
        assert run["sent"] == 0  # floored at 0

    def test_increment_on_a_missing_run_returns_none(self, repo):
        assert repo.increment_mail_run_counts(TENANT, "no-such-run", sent=1) is None


# ---------------------------------------------------------------------------
# 2. FAILURE-ONLY sub-records: written only on failure; successes are counted.
# ---------------------------------------------------------------------------


class TestFailureOnlySubRecords:
    def test_a_successful_run_stores_no_failure_sub_records(self, repo):
        repo.create_mail_run(
            TENANT, RUN, mode="per_recipient", triggered_by="sub-1", recipient_count=3
        )
        repo.increment_mail_run_counts(TENANT, RUN, sent=3)
        repo.update_mail_run_status(TENANT, RUN, MAIL_RUN_STATUS_COMPLETED)
        # Successes are only COUNTED in the tally — never stored per-recipient.
        assert list(repo.list_mail_run_failures(TENANT, RUN)) == []
        assert repo.get_mail_run(TENANT, RUN)["sent"] == 3

    def test_a_failure_writes_a_sub_record_and_increments_failed(self, repo):
        repo.create_mail_run(
            TENANT, RUN, mode="per_recipient", triggered_by="sub-1", recipient_count=3
        )
        rec = repo.record_mail_failure(
            TENANT,
            RUN,
            address="bad@example.com",
            reason="MessageRejected: Email address is not verified",
        )
        assert rec["address"] == "bad@example.com"
        assert rec["status"] == MAIL_RECIPIENT_STATUS_FAILED
        assert "MessageRejected" in rec["reason"]
        failures = list(repo.list_mail_run_failures(TENANT, RUN))
        assert len(failures) == 1
        assert repo.get_mail_run(TENANT, RUN)["failed"] == 1

    def test_multiple_failures_do_not_collide(self, repo):
        repo.create_mail_run(
            TENANT, RUN, mode="per_recipient", triggered_by="sub-1", recipient_count=3
        )
        repo.record_mail_failure(TENANT, RUN, address="a@x.com", reason="r1")
        repo.record_mail_failure(TENANT, RUN, address="b@x.com", reason="r2")
        failures = list(repo.list_mail_run_failures(TENANT, RUN))
        assert len(failures) == 2
        sks = {f[td.SORT_KEY_ATTR] for f in failures}
        assert len(sks) == 2  # distinct sort keys — no overwrite
        assert repo.get_mail_run(TENANT, RUN)["failed"] == 2

    def test_unknown_failure_status_is_rejected(self, repo):
        repo.create_mail_run(
            TENANT, RUN, mode="per_recipient", triggered_by="sub-1", recipient_count=1
        )
        with pytest.raises(ValueError):
            repo.record_mail_failure(TENANT, RUN, address="a@x.com", status="deferred")


# ---------------------------------------------------------------------------
# 3. Late async bounce/complaint (R8.4): creates a sub-record + adjusts the tally.
# ---------------------------------------------------------------------------


class TestLateBounceAdjustsTally:
    def test_late_bounce_for_a_sent_recipient_creates_a_record_and_moves_sent_to_failed(self, repo):
        # A run where all 3 were SENT (counted, no sub-records yet).
        repo.create_mail_run(
            TENANT, RUN, mode="per_recipient", triggered_by="sub-1", recipient_count=3
        )
        repo.increment_mail_run_counts(TENANT, RUN, sent=3)
        repo.update_mail_run_status(TENANT, RUN, MAIL_RUN_STATUS_COMPLETED)
        assert list(repo.list_mail_run_failures(TENANT, RUN)) == []

        # A LATE bounce arrives for one previously-sent address.
        rec = repo.record_mail_failure(
            TENANT,
            RUN,
            address="later-bounced@example.com",
            status=MAIL_RECIPIENT_STATUS_BOUNCED,
            reason="Bounce: mailbox full",
            message_id="ses-msg-1",
            adjust_run_tally=True,
        )
        assert rec["status"] == MAIL_RECIPIENT_STATUS_BOUNCED
        assert rec["message_id"] == "ses-msg-1"
        # The sub-record now exists (it did not before — the recipient had succeeded).
        assert len(list(repo.list_mail_run_failures(TENANT, RUN))) == 1
        # And the tally moved sent→failed (3 sent → 2 sent / 1 failed).
        run = repo.get_mail_run(TENANT, RUN)
        assert run["sent"] == 2
        assert run["failed"] == 1

    def test_late_complaint_is_a_valid_failure_status(self, repo):
        repo.create_mail_run(
            TENANT, RUN, mode="per_recipient", triggered_by="sub-1", recipient_count=1
        )
        repo.increment_mail_run_counts(TENANT, RUN, sent=1)
        repo.record_mail_failure(
            TENANT,
            RUN,
            address="complainer@example.com",
            status=MAIL_RECIPIENT_STATUS_COMPLAINT,
            adjust_run_tally=True,
        )
        run = repo.get_mail_run(TENANT, RUN)
        assert run["sent"] == 0
        assert run["failed"] == 1


# ---------------------------------------------------------------------------
# 4. TTL attribute present (90-day default) on both record kinds.
# ---------------------------------------------------------------------------


class TestTtlIsSet:
    def test_mail_run_carries_a_ttl_roughly_90_days_out(self, repo):
        import time

        before = int(time.time())
        run = repo.create_mail_run(
            TENANT, RUN, mode="per_recipient", triggered_by="sub-1", recipient_count=1
        )
        assert "ttl" in run
        # TTL is now + 90 days (within a small slack for test execution time).
        expected = before + MAIL_RUN_TTL_SECONDS
        assert abs(int(run["ttl"]) - expected) <= 5
        assert MAIL_RUN_TTL_SECONDS == 90 * 24 * 60 * 60

    def test_failure_sub_record_carries_a_ttl(self, repo):
        repo.create_mail_run(
            TENANT, RUN, mode="per_recipient", triggered_by="sub-1", recipient_count=1
        )
        rec = repo.record_mail_failure(TENANT, RUN, address="a@x.com", reason="r")
        assert "ttl" in rec
        assert int(rec["ttl"]) > 0


# ---------------------------------------------------------------------------
# 5. Manual delete removes the run tally AND all its failure sub-records.
# ---------------------------------------------------------------------------


class TestManualDelete:
    def test_delete_removes_the_run_and_every_failure_sub_record(self, repo, table):
        repo.create_mail_run(
            TENANT, RUN, mode="per_recipient", triggered_by="sub-1", recipient_count=3
        )
        repo.record_mail_failure(TENANT, RUN, address="a@x.com", reason="r1")
        repo.record_mail_failure(TENANT, RUN, address="b@x.com", reason="r2")
        # Pre-condition: the tally + 2 failures are present.
        assert repo.get_mail_run(TENANT, RUN) is not None
        assert len(list(repo.list_mail_run_failures(TENANT, RUN))) == 2

        repo.delete_mail_run(TENANT, RUN)

        assert repo.get_mail_run(TENANT, RUN) is None
        assert list(repo.list_mail_run_failures(TENANT, RUN)) == []
        # Nothing for this run is left anywhere in the partition.
        assert not any(RUN in k[1] for k in table.store)

    def test_delete_blank_run_id_is_rejected(self, repo):
        with pytest.raises(ValueError):
            repo.delete_mail_run(TENANT, "")


# ---------------------------------------------------------------------------
# 6. list_mail_runs feeds the read route: newest-first, tallies only.
# ---------------------------------------------------------------------------


class TestListMailRuns:
    def test_lists_runs_newest_first_and_excludes_failure_sub_records(self, repo):
        repo.create_mail_run(
            TENANT, "run-old", mode="per_recipient", triggered_by="sub-1", recipient_count=1
        )
        # Force a distinct, later created_at so the ordering is deterministic.
        import time

        time.sleep(0.01)
        repo.create_mail_run(
            TENANT, "run-new", mode="to_fixed", triggered_by="sub-1", recipient_count=1
        )
        repo.record_mail_failure(TENANT, "run-new", address="a@x.com", reason="r")

        runs = list(repo.list_mail_runs(TENANT))
        run_ids = [r["run_id"] for r in runs]
        assert run_ids == ["run-new", "run-old"]  # newest first
        # Only TALLY items — no failure sub-records swept in.
        assert all(
            td.split_sort_key(r[td.SORT_KEY_ATTR])[0] == td.RECORD_TYPE_MAIL_RUN
            for r in runs
        )

    def test_empty_tenant_lists_nothing(self, repo):
        assert list(repo.list_mail_runs(TENANT)) == []


# ---------------------------------------------------------------------------
# 7. Tenancy (Property 3): a second tenant's run is invisible; blanks refused.
# ---------------------------------------------------------------------------


class TestTenancy:
    def test_a_second_tenants_run_is_invisible(self, repo):
        repo.create_mail_run(
            "tenant-a", RUN, mode="per_recipient", triggered_by="sub-1", recipient_count=1
        )
        repo.record_mail_failure("tenant-a", RUN, address="a@x.com", reason="r")
        # Same run id, different tenant — nothing comes back.
        assert repo.get_mail_run("tenant-b", RUN) is None
        assert list(repo.list_mail_run_failures("tenant-b", RUN)) == []
        assert list(repo.list_mail_runs("tenant-b")) == []

    def test_blank_tenant_is_refused_on_every_mail_run_op(self, repo):
        for run in (
            lambda: repo.create_mail_run(
                "", RUN, mode="per_recipient", triggered_by="s", recipient_count=1
            ),
            lambda: repo.update_mail_run_status("", RUN, MAIL_RUN_STATUS_SENDING),
            lambda: repo.increment_mail_run_counts("", RUN, sent=1),
            lambda: repo.record_mail_failure("", RUN, address="a@x.com"),
            lambda: repo.get_mail_run("", RUN),
            lambda: repo.list_mail_run_failures("", RUN),
            lambda: repo.list_mail_runs(""),
            lambda: repo.delete_mail_run("", RUN),
        ):
            with pytest.raises(ValueError):
                run()


# ---------------------------------------------------------------------------
# 8. table_design SK helpers follow the mail_sent_marker_sk pattern.
# ---------------------------------------------------------------------------


class TestSortKeyHelpers:
    def test_mail_run_sk_shape(self):
        assert td.mail_run_sk("r1") == f"{td.RECORD_TYPE_MAIL_RUN}#r1"

    def test_mail_recipient_sk_shape_and_prefix(self):
        assert td.mail_recipient_sk("r1", "0") == f"{td.RECORD_TYPE_MAIL_RECIPIENT}#r1#0"
        assert td.mail_recipient_sk_prefix("r1") == f"{td.RECORD_TYPE_MAIL_RECIPIENT}#r1"

    def test_blank_segments_are_refused(self):
        with pytest.raises(ValueError):
            td.mail_run_sk("")
        with pytest.raises(ValueError):
            td.mail_recipient_sk("r1", "")

    def test_item_builders_stamp_the_authoritative_key(self):
        run_item = td.build_mail_run_item("t", "r1", {"tenant_id": "WRONG", "status": "queued"})
        assert run_item[td.PARTITION_KEY_ATTR] == "t"  # payload tenant_id overwritten
        assert run_item[td.SORT_KEY_ATTR] == td.mail_run_sk("r1")
        rec_item = td.build_mail_recipient_item("t", "r1", "0", {"address": "a@x.com"})
        assert rec_item[td.PARTITION_KEY_ATTR] == "t"
        assert rec_item[td.SORT_KEY_ATTR] == td.mail_recipient_sk("r1", "0")
        assert rec_item["run_id"] == "r1"
