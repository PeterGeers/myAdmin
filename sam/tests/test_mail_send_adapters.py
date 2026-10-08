"""
SAM pytest for the mail-send WORKER adapters (R4, pivot-output-actions task 4.3) — the
repository/adapter-layer implementations of the two worker ports
(:mod:`sam.members.repository.mail_send_adapters`):

  * :class:`SesBotoSender` — reports an SES ``ClientError`` on the outcome (never raises), picks
    ``send_email`` (simple) vs ``send_raw_email`` (attachment), attaches the config set only when
    non-blank;
  * :class:`DynamoDbMailSentMarkerStore` — a CONDITIONAL ``attribute_not_exists`` put so the
    first delivery of a ``job_id`` creates the marker (returns True) and a redelivery is a no-op
    (returns False), writing metadata only.

Driven with fake boto clients / tables (no AWS). Validates: Requirements R4
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

from sam.members.repository import table_design as td
from sam.members.repository.mail_send_adapters import (
    DynamoDbMailSentMarkerStore,
    SesBotoSender,
)

TENANT = "h-dcn"


# ── a minimal boto ClientError lookalike + fakes ─────────────────────────────────────────


class FakeClientError(Exception):
    """Stand-in for ``botocore.exceptions.ClientError`` with the ``.response`` shape."""

    def __init__(self, code, message="boom"):
        self.response = {"Error": {"Code": code, "Message": message}}
        super().__init__(f"{code}: {message}")


@pytest.fixture(autouse=True)
def _patch_client_error(monkeypatch):
    """Rebind the adapter's module-level ``ClientError`` to our fake so ``except`` catches it.

    The adapter does ``from botocore.exceptions import ClientError`` at module top, so the fake
    SES/table clients raise a stand-in that the adapter's ``except ClientError`` must catch —
    done by rebinding the name in the adapter's namespace (the fakes raise :class:`FakeClientError`).
    """
    import sam.members.repository.mail_send_adapters as adapters

    monkeypatch.setattr(adapters, "ClientError", FakeClientError, raising=True)


class FakeSesClient:
    def __init__(self, *, raise_error=None):
        self.send_email_calls: list[dict] = []
        self.send_raw_email_calls: list[dict] = []
        self._raise = raise_error

    def send_email(self, **kwargs):
        self.send_email_calls.append(kwargs)
        if self._raise:
            raise self._raise
        return {"MessageId": "simple-1"}

    def send_raw_email(self, **kwargs):
        self.send_raw_email_calls.append(kwargs)
        if self._raise:
            raise self._raise
        return {"MessageId": "raw-1"}


class FakeTable:
    """A fake DynamoDB Table honouring the ``attribute_not_exists`` conditional put."""

    def __init__(self):
        self.items: dict[tuple, dict] = {}

    def put_item(self, *, Item, ConditionExpression=None):
        key = (Item[td.PARTITION_KEY_ATTR], Item[td.SORT_KEY_ATTR])
        if (
            ConditionExpression
            and "attribute_not_exists" in ConditionExpression
            and key in self.items
        ):
            raise FakeClientError("ConditionalCheckFailedException", "exists")
        self.items[key] = dict(Item)
        return {}


# ── SesBotoSender ────────────────────────────────────────────────────────────────────────


class TestSesBotoSender:
    def test_simple_send_uses_send_email_and_reports_ok(self):
        client = FakeSesClient()
        sender = SesBotoSender(
            client=client, sender_email="noreply@tenant.example", configuration_set=""
        )
        out = sender.send(
            recipients=["a@example.com"], subject="Hi", body_html="<p>Hi</p>"
        )
        assert out.ok is True and out.message_id == "simple-1"
        assert len(client.send_email_calls) == 1
        assert client.send_email_calls[0]["Source"] == "noreply@tenant.example"
        # no config set attached when blank
        assert "ConfigurationSetName" not in client.send_email_calls[0]

    def test_attachment_send_uses_send_raw_email(self):
        client = FakeSesClient()
        sender = SesBotoSender(
            client=client, sender_email="noreply@tenant.example", configuration_set="cfg"
        )
        out = sender.send(
            recipients=["a@example.com"],
            subject="Hi",
            body_html="<p>Hi</p>",
            attachments=[
                {"filename": "members.csv", "content": b"a,b\n1,2\n", "content_type": "text/csv"}
            ],
        )
        assert out.ok is True and out.message_id == "raw-1"
        assert len(client.send_raw_email_calls) == 1
        # config set attached when non-blank
        assert client.send_raw_email_calls[0]["ConfigurationSetName"] == "cfg"

    def test_ses_client_error_is_reported_not_raised(self):
        client = FakeSesClient(
            raise_error=FakeClientError("Throttling", "Maximum sending rate exceeded")
        )
        sender = SesBotoSender(
            client=client, sender_email="noreply@tenant.example", configuration_set=""
        )
        out = sender.send(recipients=["a@example.com"], subject="Hi", body_html="<p>Hi</p>")
        assert out.ok is False
        assert "Throttling" in out.error  # the service classifies this as retryable


# ── DynamoDbMailSentMarkerStore ──────────────────────────────────────────────────────────


class TestMailSentMarkerStore:
    def test_first_mark_creates_returns_true_second_returns_false(self):
        table = FakeTable()
        store = DynamoDbMailSentMarkerStore(table=table)

        created = store.mark_if_absent(TENANT, "job-1", {"run_id": "r", "recipient_count": 1})
        redelivered = store.mark_if_absent(TENANT, "job-1", {"run_id": "r"})

        assert created is True
        assert redelivered is False
        # exactly one marker stored, under the mailsent#<job_id> sort key
        [(_pk, sk)] = list(table.items.keys())
        assert sk == td.mail_sent_marker_sk("job-1")

    def test_marker_is_tenant_scoped(self):
        table = FakeTable()
        store = DynamoDbMailSentMarkerStore(table=table)
        # the same job_id under two tenants are distinct markers (partition key differs)
        assert store.mark_if_absent(TENANT, "job-x", {}) is True
        assert store.mark_if_absent("other-tenant", "job-x", {}) is True
        assert len(table.items) == 2

    def test_marker_stores_metadata_only_and_a_ttl(self):
        table = FakeTable()
        store = DynamoDbMailSentMarkerStore(table=table)
        store.mark_if_absent(
            TENANT, "job-m", {"run_id": "run-9", "set_id": "set-7", "recipient_count": 3}
        )
        item = next(iter(table.items.values()))
        assert item["run_id"] == "run-9"
        assert item["set_id"] == "set-7"
        assert item["recipient_count"] == 3
        assert "ttl" in item and isinstance(item["ttl"], int)
        # no body / address keys
        assert "body_html" not in item and "recipients" not in item

    def test_blank_tenant_or_job_is_rejected(self):
        store = DynamoDbMailSentMarkerStore(table=FakeTable())
        with pytest.raises(ValueError):
            store.mark_if_absent("", "job", {})
        with pytest.raises(ValueError):
            store.mark_if_absent(TENANT, "", {})
