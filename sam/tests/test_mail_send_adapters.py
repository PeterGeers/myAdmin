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
        sender = SesBotoSender(client=client, configuration_set="")
        out = sender.send(
            from_address="noreply@tenant.example",
            reply_to="webmaster@tenant.example",
            recipients=["a@example.com"],
            subject="Hi",
            body_html="<p>Hi</p>",
        )
        assert out.ok is True and out.message_id == "simple-1"
        assert len(client.send_email_calls) == 1
        call = client.send_email_calls[0]
        # From = the per-send resolved tenant sender (not any global env sender)
        assert call["Source"] == "noreply@tenant.example"
        # Reply-To = the per-send user address
        assert call["ReplyToAddresses"] == ["webmaster@tenant.example"]
        # no config set attached when blank
        assert "ConfigurationSetName" not in call

    def test_simple_send_omits_reply_to_when_none(self):
        client = FakeSesClient()
        sender = SesBotoSender(client=client, configuration_set="")
        sender.send(
            from_address="noreply@tenant.example",
            recipients=["a@example.com"],
            subject="Hi",
            body_html="<p>Hi</p>",
        )
        assert "ReplyToAddresses" not in client.send_email_calls[0]

    def test_attachment_send_uses_send_raw_email_with_from_and_reply_to_headers(self):
        client = FakeSesClient()
        sender = SesBotoSender(client=client, configuration_set="cfg")
        out = sender.send(
            from_address="noreply@tenant.example",
            reply_to="webmaster@tenant.example",
            recipients=["a@example.com"],
            subject="Hi",
            body_html="<p>Hi</p>",
            attachments=[
                {"filename": "members.csv", "content": b"a,b\n1,2\n", "content_type": "text/csv"}
            ],
        )
        assert out.ok is True and out.message_id == "raw-1"
        assert len(client.send_raw_email_calls) == 1
        call = client.send_raw_email_calls[0]
        # the envelope Source is the per-send From
        assert call["Source"] == "noreply@tenant.example"
        # the MIME body carries the From + Reply-To headers for the raw send
        raw = call["RawMessage"]["Data"]
        assert "From: noreply@tenant.example" in raw
        assert "Reply-To: webmaster@tenant.example" in raw
        # config set attached when non-blank
        assert call["ConfigurationSetName"] == "cfg"

    def test_ses_client_error_is_reported_not_raised(self):
        client = FakeSesClient(
            raise_error=FakeClientError("Throttling", "Maximum sending rate exceeded")
        )
        sender = SesBotoSender(client=client, configuration_set="")
        out = sender.send(
            from_address="noreply@tenant.example",
            recipients=["a@example.com"],
            subject="Hi",
            body_html="<p>Hi</p>",
        )
        assert out.ok is False
        assert "Throttling" in out.error  # the service classifies this as retryable

    def test_simple_send_stamps_message_tags_for_feedback_routing(self):
        # mail-spec task 5.2 (R9.5): the simple path stamps SES message Tags (the feedback
        # routing key the config set echoes back as mail.tags) via the SendEmail `Tags` param.
        client = FakeSesClient()
        sender = SesBotoSender(client=client, configuration_set="cfg")
        sender.send(
            from_address="noreply@tenant.example",
            recipients=["a@example.com"],
            subject="Hi",
            body_html="<p>Hi</p>",
            tags={"ms_tenant": "682d64636e", "ms_run": "72756e2d31"},
        )
        tags = client.send_email_calls[0]["Tags"]
        assert {"Name": "ms_tenant", "Value": "682d64636e"} in tags
        assert {"Name": "ms_run", "Value": "72756e2d31"} in tags

    def test_simple_send_omits_tags_when_none(self):
        # No tags supplied → the SendEmail `Tags` key is absent (SES rejects an empty tag list).
        client = FakeSesClient()
        sender = SesBotoSender(client=client, configuration_set="")
        sender.send(
            from_address="noreply@tenant.example",
            recipients=["a@example.com"],
            subject="Hi",
            body_html="<p>Hi</p>",
        )
        assert "Tags" not in client.send_email_calls[0]

    def test_simple_send_drops_a_blank_tag_value(self):
        # A blank-valued tag is OMITTED (SES rejects an empty value); a non-blank one still rides.
        client = FakeSesClient()
        sender = SesBotoSender(client=client, configuration_set="")
        sender.send(
            from_address="noreply@tenant.example",
            recipients=["a@example.com"],
            subject="Hi",
            body_html="<p>Hi</p>",
            tags={"ms_tenant": "682d64636e", "ms_run": ""},
        )
        tags = client.send_email_calls[0]["Tags"]
        assert tags == [{"Name": "ms_tenant", "Value": "682d64636e"}]

    def test_attachment_send_stamps_tags_via_x_ses_message_tags_header(self):
        # mail-spec task 5.2 (R9.5): the RAW (attachment) path cannot use the simple `Tags` param,
        # so it stamps the X-SES-MESSAGE-TAGS header (same key=value pairs) SES reads instead —
        # one routing mechanism, both send paths.
        client = FakeSesClient()
        sender = SesBotoSender(client=client, configuration_set="cfg")
        sender.send(
            from_address="noreply@tenant.example",
            recipients=["a@example.com"],
            subject="Hi",
            body_html="<p>Hi</p>",
            attachments=[
                {"filename": "members.csv", "content": b"a,b\n1,2\n", "content_type": "text/csv"}
            ],
            tags={"ms_tenant": "682d64636e", "ms_run": "72756e2d31"},
        )
        raw = client.send_raw_email_calls[0]["RawMessage"]["Data"]
        assert "X-SES-MESSAGE-TAGS:" in raw
        assert "ms_tenant=682d64636e" in raw
        assert "ms_run=72756e2d31" in raw

    def test_blank_from_is_refused_without_substitute_sender(self):
        # Property 2 / R4.2: no resolved From → refuse (no send, no substitute like jabaki.nl).
        client = FakeSesClient()
        sender = SesBotoSender(client=client, configuration_set="")
        out = sender.send(
            from_address="",
            reply_to="webmaster@tenant.example",
            recipients=["a@example.com"],
            subject="Hi",
            body_html="<p>Hi</p>",
        )
        assert out.ok is False
        assert "no resolved sender" in out.error
        # the SES client was NEVER called — nothing was sent
        assert client.send_email_calls == []
        assert client.send_raw_email_calls == []

    def test_no_global_env_sender_fallback(self, monkeypatch):
        # The adapter no longer reads a global SES_SENDER_EMAIL — the symbol/resolver are gone,
        # and a send with no per-send From does NOT silently fall back to an env value even if
        # one is set (killing the jabaki.nl substitute-sender leak).
        import sam.members.repository.mail_send_adapters as adapters

        assert not hasattr(adapters, "resolve_ses_sender_email")
        assert not hasattr(adapters, "SES_SENDER_EMAIL_ENV_VAR")

        monkeypatch.setenv("SES_SENDER_EMAIL", "support@jabaki.nl")
        client = FakeSesClient()
        out = SesBotoSender(client=client, configuration_set="").send(
            from_address="",
            recipients=["a@example.com"],
            subject="Hi",
            body_html="<p>Hi</p>",
        )
        # refused — the env value is NOT used as a sender
        assert out.ok is False
        assert client.send_email_calls == [] and client.send_raw_email_calls == []


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
