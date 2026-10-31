"""Unit tests for the public branding-logo read endpoint.

Covers ``GET /api/public/landing/<slug>/logo`` (spec 13, R5.1-R5.4):
- configured tenant -> the PUBLIC ``landing_page.logo_url`` CloudFront URL
- unconfigured tenant -> graceful ``logo: null`` (no error, no broken image, R5.3)
- unknown slug -> 404

The endpoint returns the tenant's stored ``landing_page.logo_url`` parameter (the
public-pages CloudFront URL set when a logo is uploaded) — NOT an inline data URI
from the protected ``branding`` bucket (that round-1 behaviour is retired because
the source was not public). The ParameterService is mocked here so the test
exercises the route's public/no-auth, slug-resolution, and response-shape
conventions without a real parameter dependency.
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
    """Mock the TenantSlugService to resolve slugs to a tenant."""
    with patch("routes.landing_page_routes._get_slug_service") as mock_factory:
        mock_svc = Mock()
        mock_svc.resolve_slug.return_value = "TestTenant"
        mock_factory.return_value = mock_svc
        yield mock_svc


@pytest.fixture
def mock_parameter_service():
    """Mock the ParameterService factory (handler reads config through it)."""
    with patch("routes.landing_page_routes._get_parameter_service") as mock_factory:
        mock_svc = Mock()
        mock_factory.return_value = mock_svc
        yield mock_svc


class TestBrandingLogoRead:
    """GET /api/public/landing/<slug>/logo — public, tenant-addressed logo read."""

    def test_configured_logo_relative_key_resolves_to_cdn_url(
        self, client, mock_slug_service, mock_parameter_service, monkeypatch
    ):
        """A relative `landing_page.logo_url` S3 KEY resolves to a full CloudFront URL.

        By convention `logo_url` stores the RELATIVE public-pages key (the same value the
        landing page stores); the endpoint prepends `CLOUDFRONT_PUBLIC_PAGES_DOMAIN` so the
        form receives a browser-loadable URL (R5.2).
        """
        monkeypatch.setenv(
            "CLOUDFRONT_PUBLIC_PAGES_DOMAIN", "d3afn46os9e9nc.cloudfront.net"
        )
        mock_parameter_service.get_param.return_value = (
            "TestTenant/landing-pages/ast_01ABC_logo.jpg"
        )

        response = client.get("/api/public/landing/test-slug/logo")

        assert response.status_code == 200
        body = response.get_json()
        assert body == {
            "success": True,
            "data": {
                "logo": "https://d3afn46os9e9nc.cloudfront.net/"
                "TestTenant/landing-pages/ast_01ABC_logo.jpg"
            },
        }
        # Read from the PUBLIC `landing_page.logo_url` param for the resolved tenant (R5.2).
        mock_parameter_service.get_param.assert_called_once_with(
            "landing_page", "logo_url", tenant="TestTenant"
        )

    def test_configured_logo_absolute_url_passed_through(
        self, client, mock_slug_service, mock_parameter_service, monkeypatch
    ):
        """An already-absolute http(s) `logo_url` is returned unchanged (no double-prefix)."""
        monkeypatch.setenv(
            "CLOUDFRONT_PUBLIC_PAGES_DOMAIN", "d3afn46os9e9nc.cloudfront.net"
        )
        abs_url = "https://cdn.example.com/x/logo.png"
        mock_parameter_service.get_param.return_value = abs_url

        response = client.get("/api/public/landing/test-slug/logo")

        assert response.status_code == 200
        assert response.get_json() == {"success": True, "data": {"logo": abs_url}}

    def test_relative_key_without_cdn_domain_degrades_to_none(
        self, client, mock_slug_service, mock_parameter_service, monkeypatch
    ):
        """A relative key with no CDN domain configured is not browser-loadable → no logo (R5.3)."""
        monkeypatch.delenv("CLOUDFRONT_PUBLIC_PAGES_DOMAIN", raising=False)
        mock_parameter_service.get_param.return_value = "TestTenant/landing-pages/x.jpg"

        response = client.get("/api/public/landing/test-slug/logo")

        assert response.status_code == 200
        assert response.get_json() == {"success": True, "data": {"logo": None}}

    def test_unconfigured_logo_returns_none_gracefully(
        self, client, mock_slug_service, mock_parameter_service
    ):
        """A tenant with no configured logo returns logo=null, not an error (R5.3)."""
        mock_parameter_service.get_param.return_value = None

        response = client.get("/api/public/landing/test-slug/logo")

        assert response.status_code == 200
        body = response.get_json()
        assert body == {"success": True, "data": {"logo": None}}

    def test_unknown_slug_returns_404(self, client, mock_parameter_service):
        """An unresolvable slug returns 404 and never calls the resolver."""
        with patch("routes.landing_page_routes._get_slug_service") as mock_factory:
            mock_svc = Mock()
            mock_svc.resolve_slug.return_value = None
            mock_factory.return_value = mock_svc

            response = client.get("/api/public/landing/unknown-slug/logo")

        assert response.status_code == 404
        body = response.get_json()
        assert body["success"] is False
        # No tenant resolved -> the logo param is never read.
        mock_parameter_service.get_param.assert_not_called()

    def test_resolver_failure_returns_generic_error(
        self, client, mock_slug_service, mock_parameter_service
    ):
        """An unexpected resolver exception yields the generic error_response shape.

        Never leaks ``str(e)`` to the client (steering 30); returns the generic
        message + an error_id and a 500 status.
        """
        mock_parameter_service.get_param.side_effect = RuntimeError(
            "boto3 blew up: s3://secret/path"
        )

        response = client.get("/api/public/landing/test-slug/logo")

        assert response.status_code == 500
        body = response.get_json()
        assert body["success"] is False
        assert body["error"] == "Failed to resolve logo"
        assert "error_id" in body
        # The internal exception text must not leak to the client.
        assert "boto3" not in body["error"]
        assert "secret" not in body["error"]
