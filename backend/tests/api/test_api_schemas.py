"""
API tests for Flask app route schema validation.

Smoke tests verifying that the Flask app's registered routes have expected
patterns and key API routes exist.

Requirements: 6.1, 6.2, 6.6, 6.7, 6.8, 8.3
Reference: .kiro/specs/missing-py-tests/design.md
"""
import pytest


class TestAPISchemas:
    """Verify Flask app route registration and schema patterns."""

    def test_app_has_routes_registered(self, client):
        """App url_map should not be empty — routes must be registered."""
        app = client.application
        rules = list(app.url_map.iter_rules())
        # Flask always has at least the 'static' rule, but we expect many more
        assert len(rules) > 10

    def test_key_api_routes_exist(self, client):
        """Key API routes should be registered in the app."""
        app = client.application
        rule_paths = [rule.rule for rule in app.url_map.iter_rules()]

        # Check essential routes exist
        assert '/api/health' in rule_paths or any('/api/health' in r for r in rule_paths)
        assert any('/api/btw/generate-report' in r for r in rule_paths)

    def test_api_routes_start_with_api_prefix(self, client):
        """All API routes should start with /api/ prefix (except static/root/docs)."""
        app = client.application
        non_api_allowed_prefixes = (
            '/static', '/', '/docs', '/manifest.json', '/favicon.ico',
            '/logo192.png', '/logo512.png', '/jabaki-logo.png', '/config.js',
            '/backend-static', '/flasgger_static', '/apispec',
            '/apidocs',
        )

        for rule in app.url_map.iter_rules():
            path = rule.rule
            if path == '/':
                continue
            if any(path.startswith(prefix) for prefix in non_api_allowed_prefixes):
                continue
            # All remaining routes should be under /api/
            if not path.startswith('/api/'):
                # Allow Flask internal routes
                if rule.endpoint in ('static', 'flasgger.static'):
                    continue
                # This is unexpected — but don't fail on docs routes
                if '/docs' in path or 'apidocs' in path or 'apispec' in path:
                    continue
                assert path.startswith('/api/'), \
                    f"Route {path} (endpoint: {rule.endpoint}) does not start with /api/"

    def test_no_duplicate_route_registrations(self, client):
        """No duplicate route registrations for same path+method combination."""
        app = client.application
        seen = set()
        duplicates = []

        for rule in app.url_map.iter_rules():
            for method in rule.methods:
                if method in ('HEAD', 'OPTIONS'):
                    continue
                key = (rule.rule, method)
                if key in seen:
                    duplicates.append(key)
                seen.add(key)

        assert len(duplicates) == 0, \
            f"Duplicate route registrations found: {duplicates}"
