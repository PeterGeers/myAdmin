"""
Unit Tests for Landing Page Contact Form Endpoint

Tests rate limiting, honeypot detection, email validation,
submission storage, and SES notification.
"""

import os
import sys
from unittest.mock import Mock, patch

import pytest

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))


@pytest.fixture
def app():
    """Create a Flask test app with the landing_page blueprint registered."""
    from flask import Flask

    from routes.landing_page_routes import landing_page_bp

    app = Flask(__name__)
    app.register_blueprint(landing_page_bp)
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(app):
    """Create a Flask test client."""
    return app.test_client()


@pytest.fixture
def mock_slug_service():
    """Mock the TenantSlugService to resolve slugs."""
    with patch("routes.landing_page_routes._get_slug_service") as mock_factory:
        mock_svc = Mock()
        mock_svc.resolve_slug.return_value = "TestTenant"
        mock_factory.return_value = mock_svc
        yield mock_svc


@pytest.fixture
def mock_db():
    """Mock DatabaseManager for query execution."""
    with patch("routes.landing_page_routes.DatabaseManager") as MockDB:
        mock_instance = Mock()
        MockDB.return_value = mock_instance
        # Default: rate limit checks return 0 count
        mock_instance.execute_query.return_value = [{"cnt": 0}]
        yield mock_instance


@pytest.fixture
def mock_notification():
    """Mock the _send_contact_notification helper."""
    with patch("routes.landing_page_routes._send_contact_notification") as mock_fn:
        yield mock_fn


class TestHoneypot:
    """Task 3.5: Honeypot field rejects bots silently."""

    def test_honeypot_filled_returns_200_success(
        self, client, mock_slug_service, mock_db
    ):
        """If honeypot field is filled, return 200 success (fool bots) without storing."""
        response = client.post(
            "/api/public/landing/test-slug/contact",
            json={
                "name": "Bot",
                "email": "bot@spam.com",
                "message": "Buy stuff",
                "honeypot": "I am a bot",
            },
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert data["message"] == "Your message has been sent."
        # Ensure nothing was stored
        mock_db.execute_query.assert_not_called()

    def test_honeypot_empty_proceeds_normally(
        self, client, mock_slug_service, mock_db, mock_notification
    ):
        """Empty honeypot field allows normal processing."""
        # Make the insert call succeed (return None for non-fetch)
        mock_db.execute_query.side_effect = [
            [{"cnt": 0}],  # email rate limit check
            [{"cnt": 0}],  # IP rate limit check
            None,  # INSERT
        ]

        response = client.post(
            "/api/public/landing/test-slug/contact",
            json={
                "name": "Alice",
                "email": "alice@example.com",
                "message": "Hello!",
                "honeypot": "",
            },
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True


class TestEmailValidation:
    """Task 3.6: Email format validation."""

    def test_invalid_email_rejected(self, client):
        """Invalid email format returns 400."""
        response = client.post(
            "/api/public/landing/test-slug/contact",
            json={
                "name": "Alice",
                "email": "not-an-email",
                "message": "Hello!",
            },
        )

        assert response.status_code == 400
        data = response.get_json()
        assert data["success"] is False
        assert "Invalid email" in data["error"]

    def test_valid_email_accepted(
        self, client, mock_slug_service, mock_db, mock_notification
    ):
        """Valid email format passes validation."""
        mock_db.execute_query.side_effect = [
            [{"cnt": 0}],  # email rate limit
            [{"cnt": 0}],  # IP rate limit
            None,  # INSERT
        ]

        response = client.post(
            "/api/public/landing/test-slug/contact",
            json={
                "name": "Alice",
                "email": "alice@example.com",
                "message": "Hello!",
            },
        )

        assert response.status_code == 200

    def test_missing_email_rejected(self, client):
        """Missing email returns 400."""
        response = client.post(
            "/api/public/landing/test-slug/contact",
            json={
                "name": "Alice",
                "email": "",
                "message": "Hello!",
            },
        )

        assert response.status_code == 400
        data = response.get_json()
        assert "Email is required" in data["error"]


class TestRateLimiting:
    """Task 3.4: Rate limiting (5 per email/hour, 10 per IP/hour)."""

    def test_email_rate_limit_exceeded(self, client, mock_slug_service, mock_db):
        """5+ submissions from same email in 1 hour returns 429."""
        # First query (email check) returns count >= 5
        mock_db.execute_query.return_value = [{"cnt": 5}]

        response = client.post(
            "/api/public/landing/test-slug/contact",
            json={
                "name": "Spammer",
                "email": "spammer@example.com",
                "message": "Spam!",
            },
        )

        assert response.status_code == 429
        data = response.get_json()
        assert data["success"] is False
        assert "Too many requests" in data["error"]

    def test_ip_rate_limit_exceeded(self, client, mock_slug_service, mock_db):
        """10+ submissions from same IP in 1 hour returns 429."""
        mock_db.execute_query.side_effect = [
            [{"cnt": 4}],  # email check: under limit
            [{"cnt": 10}],  # IP check: at limit
        ]

        response = client.post(
            "/api/public/landing/test-slug/contact",
            json={
                "name": "User",
                "email": "user@example.com",
                "message": "Hello",
            },
        )

        assert response.status_code == 429
        data = response.get_json()
        assert "Too many requests" in data["error"]

    def test_within_rate_limits_succeeds(
        self, client, mock_slug_service, mock_db, mock_notification
    ):
        """Submissions within rate limits proceed normally."""
        mock_db.execute_query.side_effect = [
            [{"cnt": 3}],  # email check: under limit
            [{"cnt": 7}],  # IP check: under limit
            None,  # INSERT
        ]

        response = client.post(
            "/api/public/landing/test-slug/contact",
            json={
                "name": "Alice",
                "email": "alice@example.com",
                "message": "Hello!",
            },
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True


class TestStoreSubmission:
    """Task 3.7: Store submission + success/error feedback."""

    def test_successful_submission_stored(
        self, client, mock_slug_service, mock_db, mock_notification
    ):
        """Valid submission is stored in landing_page_submissions table."""
        mock_db.execute_query.side_effect = [
            [{"cnt": 0}],  # email rate limit
            [{"cnt": 0}],  # IP rate limit
            None,  # INSERT
        ]

        response = client.post(
            "/api/public/landing/test-slug/contact",
            json={
                "name": "Alice",
                "email": "alice@example.com",
                "message": "Hello!",
            },
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert data["message"] == "Your message has been sent."

        # Verify INSERT was called (3rd call)
        insert_call = mock_db.execute_query.call_args_list[2]
        query = insert_call[0][0]
        params = insert_call[0][1]
        assert "INSERT INTO landing_page_submissions" in query
        assert params[0] == "TestTenant"  # administration
        assert params[1] == "Alice"  # visitor_name
        assert params[2] == "alice@example.com"  # visitor_email
        assert params[3] == "Hello!"  # message

    def test_slug_not_found_returns_404(self, client):
        """Unknown slug returns 404."""
        with patch("routes.landing_page_routes._get_slug_service") as mock_factory:
            mock_svc = Mock()
            mock_svc.resolve_slug.return_value = None
            mock_factory.return_value = mock_svc

            response = client.post(
                "/api/public/landing/unknown-slug/contact",
                json={
                    "name": "Alice",
                    "email": "alice@example.com",
                    "message": "Hello!",
                },
            )

            assert response.status_code == 404
            data = response.get_json()
            assert "Page not found" in data["error"]

    def test_db_error_returns_500(self, client, mock_slug_service, mock_db):
        """Database error returns 500 with generic message."""
        mock_db.execute_query.side_effect = Exception("Connection failed")

        response = client.post(
            "/api/public/landing/test-slug/contact",
            json={
                "name": "Alice",
                "email": "alice@example.com",
                "message": "Hello!",
            },
        )

        assert response.status_code == 500
        data = response.get_json()
        assert data["success"] is False
        assert "Failed to send message" in data["error"]

    def test_missing_name_returns_400(self, client):
        """Missing name field returns 400."""
        response = client.post(
            "/api/public/landing/test-slug/contact",
            json={
                "name": "",
                "email": "alice@example.com",
                "message": "Hello!",
            },
        )

        assert response.status_code == 400
        data = response.get_json()
        assert "Name is required" in data["error"]

    def test_missing_message_returns_400(self, client):
        """Missing message field returns 400."""
        response = client.post(
            "/api/public/landing/test-slug/contact",
            json={
                "name": "Alice",
                "email": "alice@example.com",
                "message": "",
            },
        )

        assert response.status_code == 400
        data = response.get_json()
        assert "Message is required" in data["error"]

    def test_invalid_json_returns_400(self, client):
        """Non-JSON body returns 400."""
        response = client.post(
            "/api/public/landing/test-slug/contact",
            data="not json",
            content_type="text/plain",
        )

        assert response.status_code == 400
        data = response.get_json()
        assert "Invalid request body" in data["error"]


class TestSESNotification:
    """Task 3.6: SES notification to tenant after storing submission."""

    def test_notification_called_after_insert(
        self, client, mock_slug_service, mock_db, mock_notification
    ):
        """_send_contact_notification is called with correct params after store."""
        mock_db.execute_query.side_effect = [
            [{"cnt": 0}],  # email rate limit
            [{"cnt": 0}],  # IP rate limit
            None,  # INSERT
        ]

        response = client.post(
            "/api/public/landing/test-slug/contact",
            json={
                "name": "Alice",
                "email": "alice@example.com",
                "message": "Hello!",
            },
        )

        assert response.status_code == 200
        mock_notification.assert_called_once_with(
            "TestTenant", "Alice", "alice@example.com", "Hello!"
        )

    def test_notification_not_called_for_honeypot(
        self, client, mock_slug_service, mock_db, mock_notification
    ):
        """Honeypot submissions do not trigger notification."""
        response = client.post(
            "/api/public/landing/test-slug/contact",
            json={
                "name": "Bot",
                "email": "bot@spam.com",
                "message": "Spam",
                "honeypot": "filled",
            },
        )

        assert response.status_code == 200
        mock_notification.assert_not_called()

    def test_notification_not_called_on_rate_limit(
        self, client, mock_slug_service, mock_db, mock_notification
    ):
        """Rate-limited submissions do not trigger notification."""
        mock_db.execute_query.return_value = [{"cnt": 5}]

        response = client.post(
            "/api/public/landing/test-slug/contact",
            json={
                "name": "User",
                "email": "user@example.com",
                "message": "Hello",
            },
        )

        assert response.status_code == 429
        mock_notification.assert_not_called()


class TestSendContactNotificationHelper:
    """Unit tests for _send_contact_notification helper function."""

    @patch("routes.landing_page_routes.DatabaseManager")
    def test_no_email_configured_skips_send(self, mock_db_cls):
        """If tenant has no email configured, notification is skipped.

        The helper reads the tenant's contact email via
        ``ParameterService.get_param('landing_page', 'email', ...)`` — there is
        no ``os.getenv`` seam. When the parameter returns ``None`` the function
        must log and return without attempting to send, so SES is never invoked.
        """
        from routes.landing_page_routes import _send_contact_notification

        mock_db_cls.return_value = Mock()

        # ParameterService / SESEmailService are imported inside the function
        # body from their defining modules, so patch them there.
        with (
            patch("services.parameter_service.ParameterService") as MockParam,
            patch("services.ses_email_service.SESEmailService") as MockSES,
        ):
            mock_param = Mock()
            mock_param.get_param.return_value = None
            MockParam.return_value = mock_param

            _send_contact_notification(
                "TestTenant", "Alice", "alice@example.com", "Hello"
            )

            # No email configured -> SES must never be constructed or called.
            MockSES.assert_not_called()

    @patch("routes.landing_page_routes.DatabaseManager")
    def test_ses_error_does_not_raise(self, mock_db_cls):
        """SES errors are caught and logged, not raised."""
        from routes.landing_page_routes import _send_contact_notification

        with patch("services.parameter_service.ParameterService") as MockParam:
            mock_p = Mock()
            mock_p.get_param.return_value = "tenant@example.com"
            MockParam.return_value = mock_p

            with patch("services.ses_email_service.SESEmailService") as MockSES:
                mock_ses = Mock()
                mock_ses.send_email.side_effect = Exception("SES down")
                MockSES.return_value = mock_ses

                # Should NOT raise — errors are swallowed
                _send_contact_notification(
                    "TestTenant", "Alice", "alice@example.com", "Hello"
                )


class TestSanitizeInput:
    """Task 1 (security-assessment-2026-10-19): linear, ReDoS-safe input sanitizer.

    The contact-form sanitizer previously used a backtracking regex
    (``re.sub(r"<[^>]*>", "", value)``) flagged by CodeQL as
    ``py/polynomial-redos`` on this public, unauthenticated endpoint. It is
    now backed by a linear ``html.parser`` stripper. These tests pin the
    stripping contract (same tags removed, text preserved) AND assert the
    sanitizer stays fast on pathological input (no catastrophic backtracking).
    """

    def test_strips_script_tag_keeps_text(self):
        from routes.landing_page_routes.public_endpoints import _sanitize_input

        result = _sanitize_input('<script>alert("xss")</script>Hello')
        assert "<script>" not in result
        assert "</script>" not in result
        assert "Hello" in result

    def test_strips_all_html_tags(self):
        from routes.landing_page_routes.public_endpoints import _sanitize_input

        result = _sanitize_input("<p>Para</p><b>Bold</b><i>Italic</i>")
        assert "<" not in result
        assert ">" not in result
        assert "Para" in result
        assert "Bold" in result
        assert "Italic" in result

    def test_strips_tags_hidden_behind_html_entities(self):
        from routes.landing_page_routes.public_endpoints import _sanitize_input

        # Entity-encoded tag should be decoded then stripped on the 2nd pass.
        result = _sanitize_input("&lt;script&gt;evil()&lt;/script&gt;")
        assert "<script>" not in result
        assert "</script>" not in result

    def test_normalizes_horizontal_whitespace(self):
        from routes.landing_page_routes.public_endpoints import _sanitize_input

        result = _sanitize_input("Hello     \t   World")
        assert result == "Hello World"

    def test_preserves_newlines(self):
        from routes.landing_page_routes.public_endpoints import _sanitize_input

        result = _sanitize_input("Line one\nLine two")
        assert result == "Line one\nLine two"

    def test_plain_text_unchanged(self):
        from routes.landing_page_routes.public_endpoints import _sanitize_input

        assert _sanitize_input("Just a normal message.") == "Just a normal message."

    def test_pathological_input_completes_quickly(self):
        """A crafted pathological input must sanitize in well under 50ms (no ReDoS).

        A backtracking tag-strip regex degrades super-linearly on inputs like
        a long run of '<' with no closing '>'. The linear parser finishes
        near-instantly. 20k chars of this worst-case shape is a severe attack
        payload yet stays far under 50ms with the linear parser; the old
        ``<[^>]*>`` regex exhibited polynomial blow-up on the same shape.
        """
        import time

        from routes.landing_page_routes.public_endpoints import _sanitize_input

        # Worst-case shape for ``<[^>]*>``-style patterns: a long unterminated
        # run of '<'. 20k chars dwarfs any legitimate contact-form field
        # (name <= 200 chars) while remaining a realistic request-sized payload.
        pathological = "<" * 10_000 + "a" * 10_000
        start = time.perf_counter()
        _sanitize_input(pathological)
        elapsed = time.perf_counter() - start

        assert elapsed < 0.05, f"sanitizer took {elapsed * 1000:.1f}ms (ReDoS risk)"

        # A second worst-case shape: many *complete* tags interleaved with text.
        # These ARE real tags, so they must be stripped — and still fast.
        many_tags = "<a>x</a>" * 10_000
        start = time.perf_counter()
        result = _sanitize_input(many_tags)
        elapsed = time.perf_counter() - start

        assert elapsed < 0.05, f"sanitizer took {elapsed * 1000:.1f}ms (ReDoS risk)"
        # Real tags are stripped; only the text content 'x' survives.
        assert "<a>" not in result
        assert "</a>" not in result
        assert set(result) <= {"x"}

    def test_sanitizer_scales_linearly(self):
        """Doubling input size must not more than ~triple the time (no ReDoS).

        This is the core anti-ReDoS guarantee: runtime grows (roughly) linearly
        with input length, not super-linearly. A backtracking regex on the
        worst-case shape would blow up far past a 3x factor.
        """
        import time

        from routes.landing_page_routes.public_endpoints import _sanitize_input

        def _time(n: int) -> float:
            payload = "<" * n + "a" * n
            start = time.perf_counter()
            _sanitize_input(payload)
            return time.perf_counter() - start

        # Warm up (import / parser setup) so the ratio reflects steady state.
        _time(1_000)
        small = _time(10_000)
        large = _time(20_000)

        # Guard against a zero/near-zero small measurement on fast machines.
        if small < 1e-4:
            return
        assert large < small * 3, (
            f"runtime scaled super-linearly: {small * 1000:.1f}ms -> "
            f"{large * 1000:.1f}ms (possible ReDoS)"
        )

    def test_contact_endpoint_strips_html_from_stored_fields(
        self, client, mock_slug_service, mock_db, mock_notification
    ):
        """End-to-end: HTML in name/message is stripped before storage."""
        mock_db.execute_query.side_effect = [
            [{"cnt": 0}],  # email rate limit
            [{"cnt": 0}],  # IP rate limit
            None,  # INSERT
        ]

        response = client.post(
            "/api/public/landing/test-slug/contact",
            json={
                "name": "<b>Alice</b>",
                "email": "alice@example.com",
                "message": "<script>alert(1)</script>Hello",
            },
        )

        assert response.status_code == 200
        insert_call = mock_db.execute_query.call_args_list[2]
        params = insert_call[0][1]
        assert params[1] == "Alice"  # visitor_name, tags stripped
        assert "<script>" not in params[3]  # message
        assert "Hello" in params[3]
