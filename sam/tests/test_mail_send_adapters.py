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

    def test_simple_send_splits_multi_address_reply_to_into_the_address_list(self):
        # The member-application Reply-To is the all-scope Members_CRUD SET (application-app
        # R9a/D8/D24): the worker passes it as ONE comma-joined `reply_to` string; the adapter
        # splits it back into the SES `ReplyToAddresses` LIST so every admin is a reply target.
        client = FakeSesClient()
        sender = SesBotoSender(client=client, configuration_set="")
        sender.send(
            from_address="noreply@tenant.example",
            reply_to="a@tenant.example, b@tenant.example",
            recipients=["x@example.com"],
            subject="Hi",
            body_html="<p>Hi</p>",
        )
        assert client.send_email_calls[0]["ReplyToAddresses"] == [
            "a@tenant.example",
            "b@tenant.example",
        ]

    def test_attachment_send_joins_multi_address_reply_to_in_the_header(self):
        client = FakeSesClient()
        sender = SesBotoSender(client=client, configuration_set="")
        sender.send(
            from_address="noreply@tenant.example",
            reply_to="a@tenant.example, b@tenant.example",
            recipients=["x@example.com"],
            subject="Hi",
            body_html="<p>Hi</p>",
            attachments=[
                {"filename": "f.csv", "content": b"a\n1\n", "content_type": "text/csv"}
            ],
        )
        raw = client.send_raw_email_calls[0]["RawMessage"]["Data"]
        assert "Reply-To: a@tenant.example, b@tenant.example" in raw

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
                {
                    "filename": "members.csv",
                    "content": b"a,b\n1,2\n",
                    "content_type": "text/csv",
                }
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
                {
                    "filename": "members.csv",
                    "content": b"a,b\n1,2\n",
                    "content_type": "text/csv",
                }
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

        created = store.mark_if_absent(
            TENANT, "job-1", {"run_id": "r", "recipient_count": 1}
        )
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
            TENANT,
            "job-m",
            {"run_id": "run-9", "set_id": "set-7", "recipient_count": 3},
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


# ── CONCERN C — SANITIZED SES ERROR (ses-sender-identity-pollution-cleanup, task 5.3/5.4) ─
#
# Expected-behavior test for Concern C on the SAM plane, re-worked from the task-1 C-SAM
# bug-condition exploration test now that the fix (task 5.3) has landed in
# `SesBotoSender.send`. On a ClientError the outcome carries ONLY the structured SES error
# CODE + a generic phrase ("<Code>: SES send failed") — NO raw AWS Message, NO ARN, NO
# `identity/`. The full code+message is logged server-side (CloudWatch) via `logger.warning`,
# never outward. The code prefix is what the worker's `is_ses_rate_limited` matches, so the
# retryable-vs-permanent classification is preserved.
#
# Validates (Expected Behavior — Property 3): Requirements 2.7, 3.3, 3.4


class TestConcernC_SamErrorSanitized:
    """C-SAM — ``SesBotoSender.send`` carries a structured+generic error, never raw AWS text.

    Expected Behavior (Property 3): on a ClientError the outcome ``error`` is
    ``"<Code>: SES send failed"`` — the stable SES error CODE prefix + a generic phrase. It
    does NOT carry the raw AWS Message, the IAM ARN, or `identity/<addr>`; that full detail
    is logged server-side only. The retained code prefix preserves the worker's
    retryable-vs-permanent classification.
    """

    def test_send_sanitizes_access_denied_client_error_to_structured_generic(self):
        """A forced AccessDenied ClientError carrying an ARN/identity raw message is sanitized."""
        raw_msg = (
            "User: arn:aws:iam::344561557829:user/WebMaster is not authorized to perform: "
            "ses:SendRawEmail on resource: arn:aws:ses:eu-west-1:344561557829:identity/"
            "noreply@tenant.example"
        )
        client = FakeSesClient(raise_error=FakeClientError("AccessDenied", raw_msg))
        sender = SesBotoSender(client=client, configuration_set="")

        out = sender.send(
            from_address="noreply@tenant.example",
            recipients=["a@example.com"],
            subject="Hi",
            body_html="<p>Hi</p>",
        )

        assert out.ok is False
        # Exact structured+generic value: the SES CODE prefix + the generic phrase, nothing else.
        assert out.error == "AccessDenied: SES send failed"
        # NONE of the raw AWS detail leaks outward — not the raw "<Code>: <Message>",
        # not the ARN, not the `identity/<addr>`, not any substring of the raw message.
        assert out.error != f"AccessDenied: {raw_msg}"
        assert "arn:aws:" not in out.error
        assert "identity/" not in out.error
        assert raw_msg not in out.error
        assert "WebMaster" not in out.error

    def test_sanitized_error_preserves_worker_throttle_classification(self):
        """The retained CODE prefix keeps the worker's retryable-vs-permanent classification.

        A forced `Throttling` ClientError → `is_ses_rate_limited(out.error) is True` (RETRYABLE);
        a forced `AccessDenied` → `is_ses_rate_limited(out.error) is False` (PERMANENT). The
        worker's own classifier (imported from the worker module) must agree with the sanitized
        outward error, proving the fix did not break classification.
        """
        from sam.members.worker.mail_send_worker import is_ses_rate_limited

        throttled = FakeSesClient(
            raise_error=FakeClientError("Throttling", "Maximum sending rate exceeded")
        )
        out_throttled = SesBotoSender(client=throttled, configuration_set="").send(
            from_address="noreply@tenant.example",
            recipients=["a@example.com"],
            subject="Hi",
            body_html="<p>Hi</p>",
        )
        assert out_throttled.ok is False
        assert out_throttled.error == "Throttling: SES send failed"
        # the retained `Throttling` code classifies RETRYABLE even though the raw message is gone
        assert is_ses_rate_limited(out_throttled.error) is True

        denied = FakeSesClient(
            raise_error=FakeClientError(
                "AccessDenied", "arn:aws:...:identity/x@y.z denied"
            )
        )
        out_denied = SesBotoSender(client=denied, configuration_set="").send(
            from_address="noreply@tenant.example",
            recipients=["a@example.com"],
            subject="Hi",
            body_html="<p>Hi</p>",
        )
        assert out_denied.ok is False
        # a non-throttle code classifies PERMANENT (and still carries no raw detail)
        assert is_ses_rate_limited(out_denied.error) is False
        assert (
            "arn:aws:" not in out_denied.error and "identity/" not in out_denied.error
        )


# ── PRESERVATION TESTS (ses-sender-identity-pollution-cleanup, task 2) ───────────────────
#
# Capture the UNFIXED baseline behavior of the SAM send plane that the Concern C
# sanitization fix (task 5.3/5.4) MUST preserve:
#   * SesBotoSender only ever SENDS (send_email / send_raw_email) — it NEVER verifies an
#     identity, and the per-send From is the resolved projected sender (Option B, no live
#     SES verify on send) (req 3.2);
#   * the ok=True success outcome shape (ok / message_id / size_bytes) is unchanged (req 3.3);
#   * the no-resolved-sender MessageRejected refusal is unchanged (req 3.3);
#   * on a ClientError the outcome still carries a structured code the worker classifies
#     retryable-vs-permanent (req 3.4) — the baseline the fix retains server-side.
#
# EXPECTED OUTCOME on UNFIXED code: these tests PASS (baseline to preserve). After task 5.3
# the "worker classification" preservation stays green (a structured code is retained),
# while the raw-string leak (the task-1 bug-condition test above) flips to fixed.
#
# Validates (Preservation): Requirements 3.2, 3.3, 3.4


class TestPreservationSesBotoSender:
    """Preservation — SAM send success / refusal / classification baseline (req 3.2/3.3/3.4)."""

    def test_sender_never_verifies_identity(self):
        """SesBotoSender exposes only send paths — no verify_email_identity touch-point (req 3.2)."""
        client = FakeSesClient()
        sender = SesBotoSender(client=client, configuration_set="")
        # The adapter never calls a verify API — the fake has no such method recorded.
        assert not hasattr(client, "verify_email_identity")
        # The public surface is `send` only; there is no verify method on the port.
        assert not hasattr(sender, "verify_email_identity")

    def test_simple_send_uses_resolved_projected_from_no_verify(self):
        """The per-send From is the resolved projected sender; send_email is used, no verify (req 3.2)."""
        client = FakeSesClient()
        sender = SesBotoSender(client=client, configuration_set="")
        out = sender.send(
            from_address="noreply@tenant.example",
            recipients=["a@example.com"],
            subject="Hi",
            body_html="<p>Hi</p>",
        )
        assert out.ok is True
        # exactly one SEND happened (simple path), and the From is the projected sender
        assert len(client.send_email_calls) == 1
        assert client.send_email_calls[0]["Source"] == "noreply@tenant.example"
        assert client.send_raw_email_calls == []

    def test_simple_send_success_outcome_shape(self):
        """ok=True success shape (ok / message_id / size_bytes) unchanged (req 3.3)."""
        client = FakeSesClient()
        sender = SesBotoSender(client=client, configuration_set="")
        out = sender.send(
            from_address="noreply@tenant.example",
            recipients=["a@example.com"],
            subject="Hi",
            body_html="<p>Hi</p>",
        )
        assert out.ok is True
        assert out.error is None
        assert out.message_id == "simple-1"
        assert out.size_bytes > 0

    def test_attachment_send_success_outcome_shape(self):
        """ok=True success shape unchanged on the raw (attachment) path (req 3.3)."""
        client = FakeSesClient()
        sender = SesBotoSender(client=client, configuration_set="cfg")
        out = sender.send(
            from_address="noreply@tenant.example",
            recipients=["a@example.com"],
            subject="Hi",
            body_html="<p>Hi</p>",
            attachments=[
                {
                    "filename": "m.csv",
                    "content": b"a,b\n1,2\n",
                    "content_type": "text/csv",
                }
            ],
        )
        assert out.ok is True
        assert out.error is None
        assert out.message_id == "raw-1"
        assert out.size_bytes > 0

    def test_no_resolved_sender_refusal_unchanged(self):
        """No From → MessageRejected refusal, no send, no substitute (req 3.3)."""
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
        assert client.send_email_calls == []
        assert client.send_raw_email_calls == []

    def test_client_error_retains_structured_code_for_worker_classification(self):
        """On ClientError the outcome carries a structured code the worker classifies (req 3.4).

        Baseline: a retryable SES error (Throttling) is reported on out.error with its code
        preserved, which the worker service uses for retryable-vs-permanent classification.
        The Concern C fix (task 5.3) must keep a structured code available for this, even as
        it stops carrying the raw ARN/identity detail outward.
        """
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
        # The structured SES code is retained on the sanitized outward error (code + generic
        # phrase), so the worker's classification still sees the `Throttling` marker — while the
        # raw AWS Message ("Maximum sending rate exceeded") is NOT leaked outward (logged only).
        assert out.error == "Throttling: SES send failed"
        assert "Throttling" in out.error
        assert "Maximum sending rate exceeded" not in out.error
