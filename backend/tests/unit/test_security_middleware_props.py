"""
Property-based tests for security middleware environment independence.

Uses Hypothesis to verify correctness properties from the design document.
Feature: security-hardening, Property 12: Security Middleware Environment Independence

Requirements: 6.1, 6.2, 6.4
Reference: .kiro/specs/security-hardening/design.md
"""

import os
import sys
import pytest
from unittest.mock import patch, MagicMock
from hypothesis import given, strategies as st, settings

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from flask import Flask
from security_audit import SecurityAudit


# --- Strategies ---

# FLASK_DEBUG values that could be set in environment
flask_debug_values = st.sampled_from(['true', 'false', '', '1', '0', 'True', 'FALSE', 'yes'])

# TEST_MODE values that could be set in environment
test_mode_values = st.sampled_from(['true', 'false', '', '1', '0', 'True', 'FALSE', 'yes'])

# Host header values (various hosts that should NOT bypass security)
host_values = st.sampled_from([
    'localhost', 'localhost:5000', '127.0.0.1', '127.0.0.1:5000',
    '10.0.0.1', '10.0.0.1:5000', '192.168.1.1', '172.16.0.1',
    'example.com', 'myadmin.jabaki.nl', '0.0.0.0:5000',
])

# Remote address values (various IPs that should NOT bypass security)
remote_addr_values = st.sampled_from([
    '127.0.0.1', '10.0.0.1', '192.168.1.100', '172.16.0.50',
    '8.8.8.8', '203.0.113.42', '::1', '0.0.0.0',
])

# Non-health-check API paths for testing security headers
api_paths = st.sampled_from([
    '/api/invoices', '/api/banking/scan-files', '/api/admin/users',
    '/api/str/bookings', '/api/tax/calculate', '/api/sysadmin/config',
])

# Suspicious paths containing SQL injection patterns
suspicious_paths = st.sampled_from([
    '/api/test?q=1=1',
    '/api/users?id=1 OR 1=1',
    '/api/data?name=<script>alert(1)</script>',
    '/api/files/../../../etc/passwd',
    '/api/query?x=union select',
])


# --- Helpers ---

def create_test_app(flask_debug, test_mode, railway_env='production'):
    """Create a Flask app with security middleware installed."""
    env_vars = {
        'FLASK_DEBUG': flask_debug,
        'TEST_MODE': test_mode,
        'RAILWAY_ENVIRONMENT': railway_env,
    }
    with patch.dict(os.environ, env_vars, clear=False):
        app = Flask(__name__)
        app.config['TESTING'] = True

        # Register a simple test route
        @app.route('/api/test')
        def test_route():
            return {'message': 'ok'}

        @app.route('/api/health')
        def health_route():
            return {'status': 'healthy'}

        @app.route('/api/status')
        def status_route():
            return {'status': 'running'}

        # Install the security middleware
        with patch('security_audit.DatabaseManager', return_value=MagicMock()):
            audit = SecurityAudit()
            audit.create_security_middleware(app)

    return app


# ---------------------------------------------------------------------------
# Property 12: Security Middleware Environment Independence
# Feature: security-hardening, Property 12: Security Middleware Environment Independence
# Validates: Requirements 6.1, 6.2, 6.4
# ---------------------------------------------------------------------------

class TestSecurityMiddlewareEnvironmentIndependence:
    """
    Property 12: Security Middleware Environment Independence

    For any combination of FLASK_DEBUG and TEST_MODE environment variable values
    (including "true"), and for any host or remote_addr value when
    RAILWAY_ENVIRONMENT=production, the Security_Middleware SHALL execute
    suspicious pattern detection and apply security response headers on all
    non-health-check requests.

    Feature: security-hardening, Property 12: Security Middleware Environment Independence
    **Validates: Requirements 6.1, 6.2, 6.4**
    """

    @settings(max_examples=100)
    @given(
        flask_debug=flask_debug_values,
        test_mode=test_mode_values,
        host=host_values,
        remote_addr=remote_addr_values,
    )
    def test_security_headers_always_applied(self, flask_debug, test_mode, host, remote_addr):
        """
        Feature: security-hardening, Property 12: Security Middleware Environment Independence

        For any combination of env vars and network addresses, security response
        headers SHALL be present on all non-health-check responses.

        **Validates: Requirements 6.1, 6.2, 6.4**
        """
        app = create_test_app(flask_debug, test_mode)

        with app.test_client() as client:
            response = client.get(
                '/api/test',
                headers={'Host': host},
                environ_base={'REMOTE_ADDR': remote_addr},
            )

            # Security headers must always be present
            assert response.headers.get('X-Content-Type-Options') == 'nosniff', (
                f"X-Content-Type-Options missing with FLASK_DEBUG={flask_debug}, "
                f"TEST_MODE={test_mode}, host={host}, remote_addr={remote_addr}"
            )
            assert response.headers.get('X-Frame-Options') == 'SAMEORIGIN', (
                f"X-Frame-Options missing with FLASK_DEBUG={flask_debug}, "
                f"TEST_MODE={test_mode}, host={host}, remote_addr={remote_addr}"
            )
            assert response.headers.get('X-XSS-Protection') == '1; mode=block', (
                f"X-XSS-Protection missing with FLASK_DEBUG={flask_debug}, "
                f"TEST_MODE={test_mode}, host={host}, remote_addr={remote_addr}"
            )
            assert response.headers.get('Referrer-Policy') == 'strict-origin-when-cross-origin', (
                f"Referrer-Policy missing with FLASK_DEBUG={flask_debug}, "
                f"TEST_MODE={test_mode}, host={host}, remote_addr={remote_addr}"
            )

    @settings(max_examples=100)
    @given(
        flask_debug=flask_debug_values,
        test_mode=test_mode_values,
        host=host_values,
        remote_addr=remote_addr_values,
    )
    def test_suspicious_patterns_always_detected(self, flask_debug, test_mode, host, remote_addr):
        """
        Feature: security-hardening, Property 12: Security Middleware Environment Independence

        For any combination of env vars and network addresses, suspicious pattern
        detection SHALL block requests containing SQL injection patterns.

        **Validates: Requirements 6.1, 6.2, 6.4**
        """
        app = create_test_app(flask_debug, test_mode)

        with app.test_client() as client:
            # Test with a SQL injection pattern in query string
            response = client.get(
                '/api/test?q=1=1',
                headers={'Host': host},
                environ_base={'REMOTE_ADDR': remote_addr},
            )

            # Request should be blocked (403) due to suspicious pattern
            assert response.status_code == 403, (
                f"SQL injection pattern not detected with FLASK_DEBUG={flask_debug}, "
                f"TEST_MODE={test_mode}, host={host}, remote_addr={remote_addr}. "
                f"Got status {response.status_code}"
            )

    @settings(max_examples=100)
    @given(
        flask_debug=flask_debug_values,
        test_mode=test_mode_values,
        host=host_values,
        remote_addr=remote_addr_values,
    )
    def test_health_checks_whitelisted(self, flask_debug, test_mode, host, remote_addr):
        """
        Feature: security-hardening, Property 12: Security Middleware Environment Independence

        Health check endpoints (/api/health, /api/status) SHALL be whitelisted
        from security checks regardless of environment variable values.

        **Validates: Requirements 6.1, 6.2, 6.4**
        """
        app = create_test_app(flask_debug, test_mode)

        with app.test_client() as client:
            # Health check should pass without security blocks
            for path in ['/api/health', '/api/status']:
                response = client.get(
                    path,
                    headers={'Host': host},
                    environ_base={'REMOTE_ADDR': remote_addr},
                )
                assert response.status_code == 200, (
                    f"Health check {path} blocked with FLASK_DEBUG={flask_debug}, "
                    f"TEST_MODE={test_mode}, host={host}, remote_addr={remote_addr}. "
                    f"Got status {response.status_code}"
                )
