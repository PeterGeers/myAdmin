"""
Cross-tenant access tests for pattern_storage_routes (S2 T6 / R1.1).

These routes accept the tenant key (`<administration>`) from the URL PATH. Per the
tenant-isolation rule (database-patterns.md), tenant scope must flow from the
authenticated session and must never be trusted from a client-supplied path/param.

This module proves that a caller authenticated for tenant "TenantA" cannot reach
another tenant's ("TenantB") pattern data by putting "TenantB" in the path — the
route must return 403 and must never invoke the PatternAnalyzer (no data touched).

Isolation: authentication is stubbed at the source (`extract_user_credentials` +
`get_tenant_roles`) so no real Cognito/JWKS/network/DB is used. The tenant list is
carried by a well-formed (unsigned) JWT so the real tenant-extraction path runs.
"""

import base64
import json

import pytest
from flask import Flask
from unittest.mock import patch

from pattern_storage_routes import pattern_storage_bp


def _make_jwt(tenants):
    """Build a well-formed (unsigned) JWT carrying custom:tenants."""
    header = {"alg": "RS256", "typ": "JWT", "kid": "test-key-id"}
    payload = {
        "email": "user@example.com",
        "custom:tenants": json.dumps(tenants),
    }
    h = base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip("=")
    p = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    return f"{h}.{p}.sig"


@pytest.fixture
def app():
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(pattern_storage_bp)
    return app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture(autouse=True)
def stub_auth():
    """
    Stub the verified-JWT credential extraction and per-tenant role lookup so the
    caller is authenticated with Finance_CRUD (grants banking_read + banking_process)
    without touching Cognito/JWKS or the database. Tenant extraction still runs
    against the real JWT/X-Tenant, which is what these tests exercise.
    """
    # Finance_CRUD is a per-tenant role, so it is only retained by the decorator's
    # role merge when returned from the (patched) role cache. Patch it at its source
    # module (auth.role_cache) since cognito_required imports it locally.
    with patch(
        "auth.cognito_utils.extract_user_credentials",
        return_value=("user@example.com", ["Finance_CRUD"], None),
    ), patch(
        "auth.role_cache.get_tenant_roles",
        return_value=["Finance_CRUD"],
    ), patch(
        "database.DatabaseManager",
    ):
        yield


# Every pattern_storage route, keyed by (method, url-template).
ALL_ROUTES = [
    ("GET", "/api/patterns/storage/stats/{admin}"),
    ("POST", "/api/patterns/analyze/{admin}"),
    ("GET", "/api/patterns/summary/{admin}"),
    ("POST", "/api/patterns/apply/{admin}"),
    ("GET", "/api/patterns/performance-comparison/{admin}"),
    ("GET", "/api/patterns/incremental-stats/{admin}"),
]


class TestPatternStorageCrossTenantPathAccess:
    """A caller must not reach another tenant's administration via the path."""

    @pytest.mark.parametrize("method,url_tpl", ALL_ROUTES)
    @patch("pattern_storage_routes.PatternAnalyzer")
    def test_path_administration_other_tenant_returns_403_and_no_analysis(
        self, mock_analyzer, client, method, url_tpl
    ):
        # Caller is authenticated & session-scoped to TenantA...
        token = _make_jwt(["TenantA"])
        # ...but tries to operate on TenantB by putting it in the URL path.
        url = url_tpl.format(admin="TenantB")
        headers = {
            "Authorization": f"Bearer {token}",
            "X-Tenant": "TenantA",
            "Content-Type": "application/json",
        }

        resp = client.open(url, method=method, headers=headers, json={})

        assert resp.status_code == 403, resp.get_data(as_text=True)
        body = resp.get_json()
        assert body is not None and body.get("success") is False
        # The cross-tenant request must be rejected BEFORE any data is touched.
        mock_analyzer.assert_not_called()

    @pytest.mark.parametrize("method,url_tpl", ALL_ROUTES)
    @patch("pattern_storage_routes.PatternAnalyzer")
    def test_path_administration_own_tenant_is_authorized(
        self, mock_analyzer, client, method, url_tpl
    ):
        # Caller scoped to TenantA operating on TenantA passes tenant-scope enforcement
        # (i.e. does NOT get a 403). We don't assert business output here — the
        # analyzer is mocked — only that authorization allows the handler to run.
        token = _make_jwt(["TenantA"])
        url = url_tpl.format(admin="TenantA")
        headers = {
            "Authorization": f"Bearer {token}",
            "X-Tenant": "TenantA",
            "Content-Type": "application/json",
        }

        resp = client.open(url, method=method, headers=headers, json={"transactions": []})

        assert resp.status_code != 403, resp.get_data(as_text=True)
        mock_analyzer.assert_called()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


class TestPatternStorageDecoratorCoverage:
    """
    R1.1 invariant: every pattern_storage view is verified-JWT protected AND
    tenant-scoped. Both decorators expose introspectable sentinels
    (_cognito_required / _tenant_required) set after functools.wraps.
    """

    def test_every_pattern_storage_route_has_both_decorators(self, app):
        checked = 0
        for rule in app.url_map.iter_rules():
            if not str(rule).startswith("/api/patterns/"):
                continue
            view = app.view_functions[rule.endpoint]
            assert getattr(view, "_cognito_required", False), (
                f"{rule.endpoint} missing @cognito_required"
            )
            assert getattr(view, "_tenant_required", False), (
                f"{rule.endpoint} missing @tenant_required"
            )
            checked += 1
        assert checked == 6, f"expected 6 pattern_storage routes, found {checked}"
