"""
Unit tests for route_validator.py

Tests route conflict detection logic with overlapping and non-overlapping
route patterns.

Requirements: 4.7, 8.1, 8.5
Reference: .kiro/specs/missing-py-tests/design.md
"""
import pytest
from unittest.mock import MagicMock
from werkzeug.routing import Rule, Map


def _make_app_with_rules(rules):
    """
    Create a mock Flask app with a url_map containing the given rules.

    Each rule is a tuple: (route_string, endpoint, methods)
    """
    app = MagicMock()
    url_map = Map()

    for route_string, endpoint, methods in rules:
        url_map.add(Rule(route_string, endpoint=endpoint, methods=methods))

    app.url_map = url_map
    return app


class TestCheckRouteConflicts:
    """Tests for check_route_conflicts function."""

    def test_no_conflicts_distinct_routes_returns_true(self):
        """Non-overlapping routes should return True (no conflicts)."""
        from route_validator import check_route_conflicts

        app = _make_app_with_rules([
            ('/api/users', 'users.list', ['GET']),
            ('/api/orders', 'orders.list', ['GET']),
            ('/api/products', 'products.list', ['GET']),
        ])

        result = check_route_conflicts(app)
        assert result is True

    def test_no_conflicts_same_route_different_methods_returns_true(self):
        """Same route with different HTTP methods should not conflict."""
        from route_validator import check_route_conflicts

        app = _make_app_with_rules([
            ('/api/users', 'users.list', ['GET']),
            ('/api/users', 'users.create', ['POST']),
        ])

        result = check_route_conflicts(app)
        assert result is True

    def test_conflict_same_route_same_method_returns_false(self):
        """Same route and method registered to different endpoints is a conflict."""
        from route_validator import check_route_conflicts

        app = _make_app_with_rules([
            ('/api/users', 'users.list_v1', ['GET']),
            ('/api/users', 'users.list_v2', ['GET']),
        ])

        result = check_route_conflicts(app)
        assert result is False

    def test_conflict_multiple_methods_overlap_returns_false(self):
        """Routes with overlapping method sets should be detected as conflicts."""
        from route_validator import check_route_conflicts

        app = _make_app_with_rules([
            ('/api/data', 'data.endpoint_a', ['GET', 'POST']),
            ('/api/data', 'data.endpoint_b', ['GET', 'POST']),
        ])

        result = check_route_conflicts(app)
        assert result is False

    def test_empty_app_no_routes_returns_true(self):
        """An app with no routes should return True (no conflicts)."""
        from route_validator import check_route_conflicts

        app = _make_app_with_rules([])

        result = check_route_conflicts(app)
        assert result is True

    def test_head_options_excluded_from_conflict_detection(self):
        """HEAD and OPTIONS methods should be excluded from conflict checks."""
        from route_validator import check_route_conflicts

        # Werkzeug auto-adds HEAD/OPTIONS, so two routes with only
        # HEAD/OPTIONS overlap but different real methods should not conflict
        app = _make_app_with_rules([
            ('/api/resource', 'resource.get', ['GET']),
            ('/api/resource', 'resource.put', ['PUT']),
        ])

        result = check_route_conflicts(app)
        assert result is True

    def test_single_route_returns_true(self):
        """A single route should never conflict with itself."""
        from route_validator import check_route_conflicts

        app = _make_app_with_rules([
            ('/api/health', 'health.check', ['GET']),
        ])

        result = check_route_conflicts(app)
        assert result is True
