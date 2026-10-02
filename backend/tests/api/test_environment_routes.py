"""
API tests for environment_routes.py (GET /api/environment).

Feature: test-environment
Reference: .kiro/specs/Common/test-environment/first-draft/design.md (§11 Health report)

Thin route tests (Task 8.1-8.4): verify the endpoint is public, derives from the
resolver (either the bootstrapped app.config["RESOLVED_ENV"] or a resolve-from-APP_ENV
fallback), returns the non-secret report shape, and omits secrets (Req 6.1-6.6). The
pure report-builder logic and Property 9 are covered in
backend/tests/unit/test_environment_health_report.py.
"""
import json
from unittest.mock import patch

import pytest

from environment.app_env import AppEnv
from environment.bootstrap import RESOLVED_ENV_CONFIG_KEY
from environment.environment_definition import ENVIRONMENT_DEFINITION
from environment.resolver import resolve


class TestEnvironmentReportRoute:
    """GET /api/environment is public and reports resolver-derived, non-secret data."""

    def test_report_uses_bootstrapped_resolved_config(self, client, app):
        """When app.config has a RESOLVED_ENV, the report derives from it (Req 6.5)."""
        resolved = resolve(AppEnv.TEST, ENVIRONMENT_DEFINITION)
        app.config[RESOLVED_ENV_CONFIG_KEY] = resolved
        try:
            response = client.get("/api/environment")
        finally:
            app.config.pop(RESOLVED_ENV_CONFIG_KEY, None)

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["app_env"] == "test"
        assert data["cognito_pool_label"] == "myAdmin-test"
        assert data["mysql_target_label"] == "TEST"
        assert data["dynamodb_prefix"] == "test_"

    def test_report_falls_back_to_app_env_when_not_bootstrapped(self, client, app):
        """Without a stored config, the route resolves from APP_ENV (cannot drift)."""
        app.config.pop(RESOLVED_ENV_CONFIG_KEY, None)
        with patch.dict("os.environ", {"APP_ENV": "production"}, clear=False):
            response = client.get("/api/environment")

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["app_env"] == "production"
        assert data["mysql_target_label"] == "PRODUCTION"

    def test_report_omits_secret_fields(self, client, app):
        """The response never contains secret-shaped keys (Req 6.6)."""
        resolved = resolve(AppEnv.PRODUCTION, ENVIRONMENT_DEFINITION)
        app.config[RESOLVED_ENV_CONFIG_KEY] = resolved
        try:
            response = client.get("/api/environment")
        finally:
            app.config.pop(RESOLVED_ENV_CONFIG_KEY, None)

        assert response.status_code == 200
        data = json.loads(response.data)
        for forbidden in (
            "client_secret",
            "client_secret_ref",
            "password",
            "password_ref",
            "host_ref",
            "user_ref",
        ):
            assert forbidden not in data

    def test_report_returns_503_when_app_env_unresolved(self, client, app):
        """Unset APP_ENV with no stored config → 503 (no dangerous default, Req 1.3)."""
        app.config.pop(RESOLVED_ENV_CONFIG_KEY, None)
        with patch.dict("os.environ", {}, clear=False):
            import os
            os.environ.pop("APP_ENV", None)
            response = client.get("/api/environment")

        assert response.status_code == 503
        data = json.loads(response.data)
        assert data["error"] == "environment_unresolved"
        # The raw exception text must NOT be exposed to the (unauthenticated) client
        # (CodeQL: information exposure through an exception).
        assert "detail" not in data
