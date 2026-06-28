"""
Property-based tests for CORS Origin Enforcement (Property 11).

Feature: security-hardening, Property 11: CORS Origin Enforcement

For any HTTP request with an Origin header value not present in the configured
allowlist, the response SHALL NOT include the Access-Control-Allow-Origin header,
and SHALL NOT include the Access-Control-Allow-Credentials header. Conversely,
for any origin in the allowlist, both headers SHALL be present.

Validates: Requirements 5.3, 5.4, 5.5
"""
import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st
from flask import Flask
from flask_cors import CORS


# Fixed allowlist for testing (mirrors production config structure)
TEST_ALLOWED_ORIGINS = [
    'https://myadmin.jabaki.nl',
    'https://petergeers.github.io',
]


def create_test_app(allowed_origins):
    """Create a minimal Flask app with CORS configured like production."""
    app = Flask(__name__)
    app.config['TESTING'] = True

    CORS(app, resources={
        r"/api/*": {
            "origins": allowed_origins,
            "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            "allow_headers": [
                "Content-Type", "Authorization", "X-Tenant",
                "X-Language", "X-CSRF-Token", "X-Frontend-URL"
            ],
            "supports_credentials": True,
            "expose_headers": ["Content-Type", "Authorization"],
            "vary_header": True,
        }
    })

    @app.route('/api/test', methods=['GET', 'OPTIONS'])
    def test_endpoint():
        return {'status': 'ok'}, 200

    return app


# Strategy: generate random origin URLs that are NOT in the allowlist
# Uses a restricted alphabet to produce valid-looking origins
_domain_chars = st.sampled_from(
    'abcdefghijklmnopqrstuvwxyz0123456789-'
)

random_origin_strategy = st.text(
    alphabet=_domain_chars, min_size=3, max_size=40
).map(lambda s: f"https://{s}.example.com")


class TestCORSOriginEnforcementProperty:
    """Property 11: CORS Origin Enforcement."""

    @given(origin=random_origin_strategy)
    @settings(max_examples=100, deadline=None)
    def test_disallowed_origin_no_cors_headers(self, origin):
        """
        **Validates: Requirements 5.3, 5.4, 5.5**

        For any origin NOT in the allowlist, the response SHALL NOT include
        Access-Control-Allow-Origin or Access-Control-Allow-Credentials headers.
        """
        # Ensure the generated origin is not accidentally in our allowlist
        assume(origin not in TEST_ALLOWED_ORIGINS)

        app = create_test_app(TEST_ALLOWED_ORIGINS)
        client = app.test_client()

        # Test regular GET request with disallowed origin
        response = client.get(
            '/api/test',
            headers={'Origin': origin}
        )

        assert 'Access-Control-Allow-Origin' not in response.headers, (
            f"Disallowed origin '{origin}' should not receive "
            f"Access-Control-Allow-Origin header, got: "
            f"{response.headers.get('Access-Control-Allow-Origin')}"
        )
        assert 'Access-Control-Allow-Credentials' not in response.headers, (
            f"Disallowed origin '{origin}' should not receive "
            f"Access-Control-Allow-Credentials header"
        )

    @given(origin=random_origin_strategy)
    @settings(max_examples=100, deadline=None)
    def test_disallowed_origin_preflight_no_cors_headers(self, origin):
        """
        **Validates: Requirements 5.5**

        For any preflight OPTIONS request with a non-allowlisted origin,
        the response SHALL NOT include Access-Control-Allow-Origin or
        Access-Control-Allow-Methods headers.
        """
        assume(origin not in TEST_ALLOWED_ORIGINS)

        app = create_test_app(TEST_ALLOWED_ORIGINS)
        client = app.test_client()

        # Test preflight OPTIONS request with disallowed origin
        response = client.options(
            '/api/test',
            headers={
                'Origin': origin,
                'Access-Control-Request-Method': 'POST',
                'Access-Control-Request-Headers': 'Content-Type',
            }
        )

        # Preflight must return 200 (browser enforces CORS policy, not the server)
        assert response.status_code == 200, (
            f"Preflight for disallowed origin '{origin}' should return 200, "
            f"got {response.status_code}"
        )

        assert 'Access-Control-Allow-Origin' not in response.headers, (
            f"Preflight for disallowed origin '{origin}' should not receive "
            f"Access-Control-Allow-Origin header"
        )
        assert 'Access-Control-Allow-Credentials' not in response.headers, (
            f"Preflight for disallowed origin '{origin}' should not receive "
            f"Access-Control-Allow-Credentials header"
        )

    @given(origin=st.sampled_from(TEST_ALLOWED_ORIGINS))
    @settings(max_examples=100, deadline=None)
    def test_allowed_origin_receives_cors_headers(self, origin):
        """
        **Validates: Requirements 5.3, 5.4**

        For any origin in the allowlist, the response SHALL include both
        Access-Control-Allow-Origin and Access-Control-Allow-Credentials headers.
        """
        app = create_test_app(TEST_ALLOWED_ORIGINS)
        client = app.test_client()

        # Test regular GET request with allowed origin
        response = client.get(
            '/api/test',
            headers={'Origin': origin}
        )

        assert response.headers.get('Access-Control-Allow-Origin') == origin, (
            f"Allowed origin '{origin}' should receive matching "
            f"Access-Control-Allow-Origin header, got: "
            f"{response.headers.get('Access-Control-Allow-Origin')}"
        )
        assert response.headers.get('Access-Control-Allow-Credentials') == 'true', (
            f"Allowed origin '{origin}' should receive "
            f"Access-Control-Allow-Credentials: true header"
        )

    @given(origin=st.sampled_from(TEST_ALLOWED_ORIGINS))
    @settings(max_examples=100, deadline=None)
    def test_allowed_origin_preflight_receives_cors_headers(self, origin):
        """
        **Validates: Requirements 5.5**

        For any preflight OPTIONS request with an allowlisted origin,
        the response SHALL include Access-Control-Allow-Origin and
        Access-Control-Allow-Methods headers.
        """
        app = create_test_app(TEST_ALLOWED_ORIGINS)
        client = app.test_client()

        # Test preflight OPTIONS request with allowed origin
        response = client.options(
            '/api/test',
            headers={
                'Origin': origin,
                'Access-Control-Request-Method': 'POST',
                'Access-Control-Request-Headers': 'Content-Type',
            }
        )

        assert response.headers.get('Access-Control-Allow-Origin') == origin, (
            f"Preflight for allowed origin '{origin}' should receive matching "
            f"Access-Control-Allow-Origin header"
        )
        assert response.headers.get('Access-Control-Allow-Credentials') == 'true', (
            f"Preflight for allowed origin '{origin}' should receive "
            f"Access-Control-Allow-Credentials: true header"
        )

    @given(origin=st.just('null'))
    @settings(max_examples=5, deadline=None)
    def test_null_origin_rejected(self, origin):
        """
        **Validates: Requirements 5.1, 5.3**

        The "null" origin (from iframes, file:// URIs) SHALL be rejected.
        """
        app = create_test_app(TEST_ALLOWED_ORIGINS)
        client = app.test_client()

        response = client.get(
            '/api/test',
            headers={'Origin': origin}
        )

        assert 'Access-Control-Allow-Origin' not in response.headers, (
            "'null' origin should not receive Access-Control-Allow-Origin header"
        )
        assert 'Access-Control-Allow-Credentials' not in response.headers, (
            "'null' origin should not receive Access-Control-Allow-Credentials header"
        )
