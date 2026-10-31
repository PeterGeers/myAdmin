"""
Unit tests for SES Email Service

Tests the SESEmailService class with mocked boto3 SES client.
"""

from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from services.ses_email_service import SESEmailService


@pytest.fixture
def mock_ses_client():
    """Create a mocked SES client"""
    with patch("services.ses_email_service.boto3") as mock_boto3:
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        mock_client.send_email.return_value = {"MessageId": "test-message-id-123"}
        yield mock_client


@pytest.fixture
def ses_service(mock_ses_client):
    """Create SESEmailService with mocked client"""
    with patch.dict(
        "os.environ",
        {"SES_SENDER_EMAIL": "support@jabaki.nl", "AWS_REGION": "eu-west-1"},
    ):
        service = SESEmailService()
    return service


# ============================================================================
# is_enabled()
# ============================================================================


class TestIsEnabled:
    def test_enabled_with_sender(self, ses_service):
        assert ses_service.is_enabled() is True

    def test_disabled_without_sender(self, mock_ses_client):
        with patch.dict("os.environ", {"SES_SENDER_EMAIL": ""}, clear=False):
            service = SESEmailService()
            assert service.is_enabled() is False


# ============================================================================
# send_email()
# ============================================================================


class TestSendEmail:
    def test_send_html_and_text(self, ses_service, mock_ses_client):
        result = ses_service.send_email(
            to_email="user@example.com",
            subject="Test Subject",
            html_body="<h1>Hello</h1>",
            text_body="Hello",
        )

        assert result["success"] is True
        assert result["message_id"] == "test-message-id-123"

        call_args = mock_ses_client.send_email.call_args
        assert call_args[1]["Destination"] == {"ToAddresses": ["user@example.com"]}
        assert call_args[1]["Message"]["Subject"]["Data"] == "Test Subject"
        assert "Html" in call_args[1]["Message"]["Body"]
        assert "Text" in call_args[1]["Message"]["Body"]

    def test_send_text_only(self, ses_service, mock_ses_client):
        result = ses_service.send_email(
            to_email="user@example.com", subject="Test", text_body="Plain text only"
        )

        assert result["success"] is True
        body = mock_ses_client.send_email.call_args[1]["Message"]["Body"]
        assert "Text" in body
        assert "Html" not in body

    def test_send_html_only(self, ses_service, mock_ses_client):
        result = ses_service.send_email(
            to_email="user@example.com", subject="Test", html_body="<p>HTML only</p>"
        )

        assert result["success"] is True
        body = mock_ses_client.send_email.call_args[1]["Message"]["Body"]
        assert "Html" in body
        assert "Text" not in body

    def test_correct_sender_and_reply_to(self, ses_service, mock_ses_client):
        ses_service.send_email(
            to_email="user@example.com", subject="Test", text_body="Hello"
        )

        call_args = mock_ses_client.send_email.call_args[1]
        assert call_args["Source"] == "myAdmin <support@jabaki.nl>"
        assert call_args["ReplyToAddresses"] == ["support@jabaki.nl"]

    def test_no_recipient_returns_error(self, ses_service):
        result = ses_service.send_email(to_email="", subject="Test", text_body="Hello")

        assert result["success"] is False
        assert "No recipient" in result["error"]

    def test_no_body_returns_error(self, ses_service):
        result = ses_service.send_email(to_email="user@example.com", subject="Test")

        assert result["success"] is False
        assert "No email body" in result["error"]

    def test_message_rejected_error(self, ses_service, mock_ses_client):
        mock_ses_client.send_email.side_effect = ClientError(
            {
                "Error": {
                    "Code": "MessageRejected",
                    "Message": "Email address not verified",
                }
            },
            "SendEmail",
        )

        result = ses_service.send_email(
            to_email="user@example.com", subject="Test", text_body="Hello"
        )

        assert result["success"] is False
        # Sanitized (Concern C): the raw code/message never reaches the client body —
        # it is retained as the structured error_code for internal fallback (req 3.4).
        assert result["error"] == "Email sending failed. Please try again later."
        assert "MessageRejected" not in result["error"]
        assert result["error_code"] == "MessageRejected"

    def test_domain_not_verified_error(self, ses_service, mock_ses_client):
        mock_ses_client.send_email.side_effect = ClientError(
            {
                "Error": {
                    "Code": "MailFromDomainNotVerifiedException",
                    "Message": "Domain not verified",
                }
            },
            "SendEmail",
        )

        result = ses_service.send_email(
            to_email="user@example.com", subject="Test", text_body="Hello"
        )

        assert result["success"] is False
        # Sanitized: generic client message; structured code retained internally (req 3.4).
        assert result["error"] == "Email sending failed. Please try again later."
        assert "MailFromDomainNotVerifiedException" not in result["error"]
        assert result["error_code"] == "MailFromDomainNotVerifiedException"

    def test_unexpected_exception(self, ses_service, mock_ses_client):
        mock_ses_client.send_email.side_effect = Exception("Network timeout")

        result = ses_service.send_email(
            to_email="user@example.com", subject="Test", text_body="Hello"
        )

        assert result["success"] is False
        # Raw exception text must not leak to the caller (py/stack-trace-exposure).
        assert "Network timeout" not in result["error"]
        assert result["error"] == "Failed to send email. Please try again later."


# ============================================================================
# send_invitation()
# ============================================================================


class TestSendInvitation:
    def test_send_invitation_success(self, ses_service, mock_ses_client):
        result = ses_service.send_invitation(
            to_email="newuser@example.com",
            subject="Welcome to myAdmin - TestTenant Invitation",
            html_body="<h1>Welcome</h1>",
            text_body="Welcome",
        )

        assert result["success"] is True
        assert result["message_id"] == "test-message-id-123"
        mock_ses_client.send_email.assert_called_once()

    def test_send_invitation_failure(self, ses_service, mock_ses_client):
        mock_ses_client.send_email.side_effect = ClientError(
            {"Error": {"Code": "MessageRejected", "Message": "Rejected"}}, "SendEmail"
        )

        result = ses_service.send_invitation(
            to_email="newuser@example.com", subject="Welcome", text_body="Welcome"
        )

        assert result["success"] is False


# ============================================================================
# Custom reply-to
# ============================================================================


class TestCustomReplyTo:
    def test_custom_reply_to(self, mock_ses_client):
        with patch.dict(
            "os.environ",
            {
                "SES_SENDER_EMAIL": "support@jabaki.nl",
                "SES_REPLY_TO_EMAIL": "info@jabaki.nl",
                "AWS_REGION": "eu-west-1",
            },
        ):
            service = SESEmailService()

        service.send_email(
            to_email="user@example.com", subject="Test", text_body="Hello"
        )

        call_args = mock_ses_client.send_email.call_args[1]
        assert call_args["ReplyToAddresses"] == ["info@jabaki.nl"]


# ============================================================================
# CONCERN C — ERROR SANITIZATION, Property 3 EXPECTED-BEHAVIOR TESTS
# (ses-sender-identity-pollution-cleanup, tasks 1 + 5.1/5.2)
#
# These started life as the task-1 bug-condition EXPLORATION tests (which FAILED
# on the unfixed code, confirming the leak). The Concern C fix (task 5.1) now
# sanitizes the `except ClientError` path in BOTH send methods, so they have
# become the PAIRED expected-behavior tests for Property 3: the client body
# carries ONLY a generic message, while the structured `error_code` is retained
# internally and the FULL AWS detail is still logged server-side via log_failed.
#
# Property 3 (Expected Behavior): for any ClientError reaching a client-facing
#   send path -> client `error` is generic (no ARN / identity / raw code:msg),
#   internal `error_code` preserved (req 3.4), full detail persisted server-side.
#
# Validates: Requirements 2.5, 2.6, 3.3, 3.4
# ============================================================================

# A representative AccessDenied ClientError carrying an ARN / identity detail — the exact
# shape the design cites (AccessDenied ... ses:SendRawEmail ... identity/<addr>).
_ACCESS_DENIED_RAW_MSG = (
    "User: arn:aws:iam::344561557829:user/WebMaster is not authorized to perform: "
    "ses:SendRawEmail on resource: arn:aws:ses:eu-west-1:344561557829:identity/"
    "tenant@example.com because no identity-based policy allows the ses:SendRawEmail action"
)

# The exact generic, caller-safe message the sanitized ClientError path returns.
_GENERIC_CLIENT_ERROR = "Email sending failed. Please try again later."


class TestConcernCFlaskErrorSanitized:
    """C-Flask — the sanitized send paths return a GENERIC client ``error`` and keep the
    structured ``error_code`` internally, with the full AWS detail only logged server-side.

    Property 3 (Expected Behavior) for isBugCondition_C(outcome): a ClientError failure
    whose verbatim AWS "<Code>: <Message>" (including the ARN / identity detail) must NOT
    reach the client-facing response body. Instead the client sees a fixed generic message,
    the structured ``error_code`` is retained internally (req 3.4), and the full detail is
    persisted server-side via ``log_failed`` (req 3.3 server-side logging unchanged).
    """

    def test_send_email_client_error_returns_generic_message(
        self, ses_service, mock_ses_client
    ):
        mock_ses_client.send_email.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": _ACCESS_DENIED_RAW_MSG}},
            "SendEmail",
        )

        result = ses_service.send_email(
            to_email="user@example.com", subject="Test", text_body="Hello"
        )

        assert result["success"] is False
        # Client body is a fixed generic message — NO AWS detail (no ARN / identity / code:msg).
        assert result["error"] == _GENERIC_CLIENT_ERROR
        assert "AccessDenied" not in result["error"]
        assert "identity/" not in result["error"]
        assert "arn:aws:" not in result["error"]
        # Structured error_code IS preserved internally for fallback logic (req 3.4).
        assert result["error_code"] == "AccessDenied"

    def test_send_email_client_error_logs_full_detail_server_side(
        self, ses_service, mock_ses_client
    ):
        """The full AWS detail is still passed to log_failed server-side (req 3.3)."""
        mock_ses_client.send_email.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": _ACCESS_DENIED_RAW_MSG}},
            "SendEmail",
        )

        with patch("services.ses_email_service._get_email_log") as mock_get_log:
            mock_log = MagicMock()
            mock_get_log.return_value = mock_log

            result = ses_service.send_email(
                to_email="user@example.com",
                subject="Test",
                text_body="Hello",
                email_type="invitation",
                administration="tenant1",
            )

        assert result["success"] is False
        # Client body stays generic even on the logged path.
        assert result["error"] == _GENERIC_CLIENT_ERROR
        assert result["error_code"] == "AccessDenied"
        # Server-side: log_failed receives the FULL "{code}: {msg}" detail (ARN/identity included).
        mock_log.log_failed.assert_called_once()
        logged_error = mock_log.log_failed.call_args[1]["error_message"]
        assert logged_error == f"AccessDenied: {_ACCESS_DENIED_RAW_MSG}"
        assert "identity/" in logged_error
        assert "arn:aws:" in logged_error

    def test_send_email_with_attachments_client_error_returns_generic_message(
        self, ses_service, mock_ses_client
    ):
        mock_ses_client.send_raw_email.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": _ACCESS_DENIED_RAW_MSG}},
            "SendRawEmail",
        )

        result = ses_service.send_email_with_attachments(
            to_email="user@example.com",
            subject="Invoice",
            html_body="<p>See attached</p>",
            attachments=[
                {
                    "filename": "invoice.pdf",
                    "content": b"%PDF-1.4 fake",
                    "content_type": "application/pdf",
                }
            ],
        )

        assert result["success"] is False
        # Client body is the fixed generic message — no ARN / identity / raw code:msg.
        assert result["error"] == _GENERIC_CLIENT_ERROR
        assert "AccessDenied" not in result["error"]
        assert "identity/" not in result["error"]
        assert "arn:aws:" not in result["error"]
        # Structured error_code IS preserved internally for fallback logic (req 3.4).
        assert result["error_code"] == "AccessDenied"

    def test_send_email_with_attachments_client_error_logs_full_detail_server_side(
        self, ses_service, mock_ses_client
    ):
        """The full AWS detail is still passed to log_failed server-side (req 3.3)."""
        mock_ses_client.send_raw_email.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": _ACCESS_DENIED_RAW_MSG}},
            "SendRawEmail",
        )

        with patch("services.ses_email_service._get_email_log") as mock_get_log:
            mock_log = MagicMock()
            mock_get_log.return_value = mock_log

            result = ses_service.send_email_with_attachments(
                to_email="user@example.com",
                subject="Invoice",
                html_body="<p>See attached</p>",
                attachments=[
                    {
                        "filename": "invoice.pdf",
                        "content": b"%PDF-1.4 fake",
                        "content_type": "application/pdf",
                    }
                ],
                email_type="invoice",
                administration="tenant1",
            )

        assert result["success"] is False
        assert result["error"] == _GENERIC_CLIENT_ERROR
        assert result["error_code"] == "AccessDenied"
        mock_log.log_failed.assert_called_once()
        logged_error = mock_log.log_failed.call_args[1]["error_message"]
        assert logged_error == f"AccessDenied: {_ACCESS_DENIED_RAW_MSG}"
        assert "identity/" in logged_error
        assert "arn:aws:" in logged_error


# ============================================================================
# PRESERVATION TESTS (ses-sender-identity-pollution-cleanup, task 2)
#
# These capture the UNFIXED baseline SUCCESS behavior that the Concern C
# sanitization fix (task 5.x) MUST preserve: the success shape
# {'success': True, 'message_id': ...}, the log_sent call, and the structured
# error_code remaining available INTERNALLY on failure (even though the raw
# detail will stop reaching the client body after the fix).
#
# EXPECTED OUTCOME on UNFIXED code: these tests PASS (baseline to preserve).
# After task 5.x, the success assertions MUST STILL PASS; the "internal
# error_code" observation below documents what the fix retains server-side.
#
# Validates (Preservation): Requirements 3.3 (success shape + logging),
#                           3.4 (internal structured error_code retained)
# ============================================================================


class TestPreservationSendSuccess:
    """Preservation (req 3.3) — successful sends keep the success shape + logging.

    Baseline on UNFIXED code: both send paths return {'success': True, 'message_id': ...}
    and call EmailLogService.log_sent when email_type is supplied. The Concern C fix only
    touches the except ClientError branch, so success must be byte-for-byte unchanged.
    """

    def test_send_email_success_shape(self, ses_service, mock_ses_client):
        result = ses_service.send_email(
            to_email="user@example.com",
            subject="Test",
            text_body="Hello",
        )
        assert result == {"success": True, "message_id": "test-message-id-123"}

    def test_send_email_success_logs_sent(self, ses_service, mock_ses_client):
        """With an email_type, a successful send logs via EmailLogService.log_sent."""
        with patch("services.ses_email_service._get_email_log") as mock_get_log:
            mock_log = MagicMock()
            mock_get_log.return_value = mock_log

            result = ses_service.send_email(
                to_email="user@example.com",
                subject="Test",
                text_body="Hello",
                email_type="invitation",
                administration="tenant1",
                sent_by="admin@example.com",
            )

        assert result["success"] is True
        mock_log.log_sent.assert_called_once()
        kwargs = mock_log.log_sent.call_args[1]
        assert kwargs["recipient"] == "user@example.com"
        assert kwargs["email_type"] == "invitation"
        assert kwargs["ses_message_id"] == "test-message-id-123"

    def test_send_email_with_attachments_success_shape(
        self, ses_service, mock_ses_client
    ):
        mock_ses_client.send_raw_email.return_value = {"MessageId": "raw-id-456"}

        result = ses_service.send_email_with_attachments(
            to_email="user@example.com",
            subject="Invoice",
            html_body="<p>See attached</p>",
            attachments=[
                {
                    "filename": "invoice.pdf",
                    "content": b"%PDF-1.4 fake",
                    "content_type": "application/pdf",
                }
            ],
        )

        assert result == {"success": True, "message_id": "raw-id-456"}

    def test_send_email_with_attachments_success_uses_source_email(
        self, ses_service, mock_ses_client
    ):
        """A tenant source_email is used as the From sender on success (baseline)."""
        mock_ses_client.send_raw_email.return_value = {"MessageId": "raw-id-456"}

        ses_service.send_email_with_attachments(
            to_email="user@example.com",
            subject="Invoice",
            html_body="<p>See attached</p>",
            attachments=[
                {
                    "filename": "f.pdf",
                    "content": b"x",
                    "content_type": "application/pdf",
                }
            ],
            from_name="Acme BV",
            source_email="verified@acme.example",
        )

        call_args = mock_ses_client.send_raw_email.call_args[1]
        assert call_args["Source"] == "Acme BV <verified@acme.example>"


class TestPreservationInternalErrorCode:
    """Preservation (req 3.4) — the structured error_code is still available internally.

    Baseline on UNFIXED code: on a ClientError, both send paths pass the full
    "{code}: {msg}" into EmailLogService.log_failed (server-side) and the client-facing
    'error' carries the code. The Concern C fix (task 5.x) will stop echoing the raw
    detail to the client body, BUT must keep the full detail flowing to log_failed
    server-side — this test fixes the baseline that the server-side path receives the
    structured detail, which the fix must retain.
    """

    def test_send_email_client_error_logs_failed_with_full_detail(
        self, ses_service, mock_ses_client
    ):
        mock_ses_client.send_email.side_effect = ClientError(
            {
                "Error": {
                    "Code": "MessageRejected",
                    "Message": "Email address not verified",
                }
            },
            "SendEmail",
        )

        with patch("services.ses_email_service._get_email_log") as mock_get_log:
            mock_log = MagicMock()
            mock_get_log.return_value = mock_log

            result = ses_service.send_email(
                to_email="user@example.com",
                subject="Test",
                text_body="Hello",
                email_type="invitation",
                administration="tenant1",
            )

        assert result["success"] is False
        # Server-side failure logging receives the full structured detail (code + message).
        mock_log.log_failed.assert_called_once()
        logged_error = mock_log.log_failed.call_args[1]["error_message"]
        assert "MessageRejected" in logged_error

    def test_send_email_with_attachments_client_error_logs_failed_with_full_detail(
        self, ses_service, mock_ses_client
    ):
        mock_ses_client.send_raw_email.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "nope"}},
            "SendRawEmail",
        )

        with patch("services.ses_email_service._get_email_log") as mock_get_log:
            mock_log = MagicMock()
            mock_get_log.return_value = mock_log

            result = ses_service.send_email_with_attachments(
                to_email="user@example.com",
                subject="Invoice",
                html_body="<p>x</p>",
                attachments=[
                    {
                        "filename": "f.pdf",
                        "content": b"x",
                        "content_type": "application/pdf",
                    }
                ],
                email_type="invoice",
                administration="tenant1",
            )

        assert result["success"] is False
        mock_log.log_failed.assert_called_once()
        logged_error = mock_log.log_failed.call_args[1]["error_message"]
        assert "AccessDenied" in logged_error
