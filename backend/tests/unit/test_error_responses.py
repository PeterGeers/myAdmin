"""
Unit tests for routes.error_responses helper.

Covers the two-tier error contract introduced by security-assessment-2026-10-19 (Task 4).
Asserts: generic client_message returned, non-empty error_id, str(exc) never in body,
status passthrough, include_success=False shape, and full-exception server-side
logging (caplog + exc_info).
"""

import logging
import sys
from pathlib import Path

import pytest
from flask import Flask

# Add src directory to Python path (mirrors backend/tests/conftest.py)
backend_dir = Path(__file__).parent.parent
src_dir = backend_dir / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from routes.error_responses import error_response, error_payload


@pytest.fixture(autouse=True)
def _flask_app_ctx():
    """Provide a minimal Flask app context so jsonify() works in unit tests."""
    app = Flask(__name__)
    with app.app_context():
        yield


class TestErrorResponse:
    """Tests for the error_response helper (returns Flask jsonify tuple)."""

    def test_returns_generic_client_message(self):
        """Response body contains the provided client_message, not str(exc)."""
        exc = ValueError("internal detail that must not leak")
        body, status = error_response(exc, "Failed to save bookings")

        assert body.json["error"] == "Failed to save bookings"
        assert str(exc) not in body.get_json()
        # Default client message when none provided
        body2, _ = error_response(KeyError("missing"))
        assert (
            body2.json["error"] == "An internal error occurred. Please try again later."
        )

    def test_non_empty_error_id(self):
        """Response body contains a non-empty error_id (hex uuid)."""
        exc = RuntimeError("boom")
        body, _ = error_response(exc, "Something went wrong")

        error_id = body.json["error_id"]
        assert error_id is not None
        assert isinstance(error_id, str)
        assert len(error_id) == 32  # uuid4().hex length
        # Verify it's hex
        int(error_id, 16)  # raises ValueError if not hex

    def test_str_exc_never_in_body(self):
        """str(exc) never appears anywhere in the response body."""
        exc = ValueError("sensitive table name: finance.users")
        body, _ = error_response(exc, "Operation failed")

        body_json = body.get_json()
        assert "sensitive table name" not in str(body_json)
        assert "finance.users" not in str(body_json)
        # The error message is the generic one
        assert body_json["error"] == "Operation failed"

    def test_status_passthrough_default_500(self):
        """Default status code is 500 and passes through unchanged."""
        exc = Exception("any")
        _, status = error_response(exc, "msg")
        assert status == 500

    def test_status_passthrough_custom(self):
        """Custom status code is passed through unchanged."""
        exc = Exception("any")
        for custom_status in (400, 401, 403, 404, 422, 502, 503):
            _, status = error_response(exc, "msg", status=custom_status)
            assert status == custom_status

    def test_include_success_true_default_shape(self):
        """Default include_success=True includes 'success': False in body."""
        exc = Exception("any")
        body, _ = error_response(exc, "msg")

        assert body.json.get("success") is False
        assert "error" in body.json
        assert "error_id" in body.json

    def test_include_success_false_shape(self):
        """include_success=False returns bare {'error': ..., 'error_id': ...}."""
        exc = Exception("any")
        body, _ = error_response(exc, "msg", include_success=False)

        body_json = body.get_json()
        assert "success" not in body_json
        assert body_json["error"] == "msg"
        assert "error_id" in body_json
        assert len(body_json) == 2  # exactly error + error_id


class TestErrorPayload:
    """Tests for the error_payload helper (returns plain dict, no jsonify)."""

    def test_returns_dict_not_flask_response(self):
        """error_payload returns a plain dict, not a Flask Response."""
        exc = ValueError("detail")
        payload = error_payload(exc, "Client message")

        assert isinstance(payload, dict)
        assert "json" not in dir(payload)  # not a Flask Response

    def test_shape_matches_error_response(self):
        """error_payload body shape matches error_response (minus jsonify)."""
        exc = KeyError("missing")
        payload = error_payload(exc, "Client message")
        response, _status = error_response(exc, "Client message")
        body_json = response.get_json()

        assert set(payload.keys()) == set(body_json.keys())
        assert payload["error"] == body_json["error"] == "Client message"

    def test_include_success_false_shape(self):
        """include_success=False returns bare dict."""
        payload = error_payload(Exception("x"), "msg", include_success=False)
        assert "success" not in payload
        assert set(payload.keys()) == {"error", "error_id"}


class TestServerSideLogging:
    """Tests for full-exception server-side logging via caplog + exc_info."""

    def test_logs_full_exception_with_exc_info(self, caplog):
        """Logger.error is called with exc_info=exc (full traceback)."""
        exc = ValueError("internal detail")
        caplog.set_level(logging.ERROR)

        error_response(exc, "Client message")

        assert len(caplog.records) == 1
        record = caplog.records[0]
        assert record.levelno == logging.ERROR
        assert record.exc_info is not None
        exc_type, exc_value, exc_tb = record.exc_info
        assert exc_type is ValueError
        assert str(exc_value) == "internal detail"
        assert "error_id=" in record.message
        assert "ValueError" in record.message

    def test_log_context_appears_in_log(self, caplog):
        """Optional log_context is prefixed in the log line."""
        exc = RuntimeError("boom")
        caplog.set_level(logging.ERROR)

        error_response(exc, "msg", log_context="booking_save")

        record = caplog.records[0]
        assert "booking_save:" in record.message

    def test_error_id_in_log_matches_response(self, caplog):
        """The error_id logged server-side matches the one returned to client."""
        exc = KeyError("x")
        caplog.set_level(logging.ERROR)

        body, _ = error_response(exc, "msg")

        record = caplog.records[0]
        response_error_id = body.json["error_id"]
        assert f"error_id={response_error_id}" in record.message

    def test_multiple_calls_produce_unique_error_ids(self, caplog):
        """Each call generates a fresh error_id."""
        caplog.set_level(logging.ERROR)

        body1, _ = error_response(Exception("1"), "msg")
        body2, _ = error_response(Exception("2"), "msg")

        assert body1.json["error_id"] != body2.json["error_id"]
        assert len(caplog.records) == 2
        assert f"error_id={body1.json['error_id']}" in caplog.records[0].message
        assert f"error_id={body2.json['error_id']}" in caplog.records[1].message


class TestDefaultClientMessage:
    """Tests for the fallback _DEFAULT_CLIENT_MESSAGE."""

    def test_default_message_used_when_none_provided(self):
        """When client_message omitted, default generic message is used."""
        body, _ = error_response(ValueError("detail"))

        assert (
            body.json["error"] == "An internal error occurred. Please try again later."
        )

    def test_explicit_empty_string_uses_default(self):
        """Empty string client_message falls back to default."""
        body, _ = error_response(ValueError("detail"), client_message="")
        assert (
            body.json["error"] == "An internal error occurred. Please try again later."
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
