"""
API tests for static_routes.py

Tests that static file serving routes are registered and respond correctly,
including the 404 handler for non-API routes.

Requirements: 6.1, 6.2, 6.6, 6.7, 6.8, 8.3
Reference: .kiro/specs/missing-py-tests/design.md
"""
import pytest
import json
from unittest.mock import patch, MagicMock


class TestStaticRoutes:
    """Verify static route registration and basic responses."""

    def test_root_returns_200_or_404(self, client):
        """GET / returns 200 (if build exists) or 404 (if not)."""
        response = client.get('/')
        # In test environment, frontend build folder likely doesn't exist
        assert response.status_code in (200, 404)

    def test_api_nonexistent_returns_json_error(self, client):
        """404 on /api/nonexistent returns JSON error, not HTML."""
        response = client.get('/api/nonexistent-route-xyz')
        assert response.status_code == 404
        data = json.loads(response.data)
        assert 'error' in data

    def test_static_route_is_registered(self, client):
        """The static blueprint's serve_static endpoint should be registered."""
        # Access the app from the client
        app = client.application
        # Check that the static.serve_static endpoint exists in the url_map
        rules = [rule.endpoint for rule in app.url_map.iter_rules()]
        assert 'static.serve_static' in rules
