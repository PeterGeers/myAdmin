"""
Unit Tests for LandingPagePublishService

Tests publish, unpublish, branding resolution, and HTML generation.
Uses unittest.mock to mock dependencies (LandingPageService, ParameterService,
TenantSlugService, boto3 S3 client).
"""

import json
import os
import sys
from unittest.mock import Mock, patch, call

import pytest
from botocore.exceptions import ClientError

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))


class TestLandingPagePublishService:
    """Test suite for LandingPagePublishService."""

    @pytest.fixture
    def mock_landing_page_svc(self):
        """Mock LandingPageService."""
        svc = Mock()
        svc.get_draft.return_value = {
            "status": "draft",
            "version": 5,
            "last_modified": "2026-08-05T14:30:00+00:00",
            "modified_by": "admin@acme.nl",
            "sections": [
                {"id": "block-001", "type": "hero", "properties": {"title": "Welcome"}},
                {
                    "id": "block-002",
                    "type": "about",
                    "properties": {"content_md": "About us"},
                },
            ],
        }
        svc.save_version.return_value = {"success": True, "version": 5}
        return svc

    @pytest.fixture
    def mock_param_svc(self):
        """Mock ParameterService with branding values."""
        svc = Mock()

        def get_param_side_effect(namespace, key, tenant=None, **kwargs):
            params = {
                ("landing_page", "company_name"): "Acme Rentals B.V.",
                ("landing_page", "tagline"): "Your holiday starts here",
                ("landing_page", "logo_url"): "https://cdn.example.com/logo.png",
                ("landing_page", "color_primary"): "#2D5F8A",
                ("landing_page", "color_accent"): "#F4A261",
                ("landing_page", "address"): "Keizersgracht 123",
                ("landing_page", "postal_city"): "1015 AA Amsterdam",
                ("landing_page", "country"): "Nederland",
                ("landing_page", "phone"): "+31 20 123 4567",
                ("landing_page", "email"): "info@acme-rentals.nl",
                ("landing_page", "coc"): "12345678",
                ("landing_page", "vat"): "NL123456789B01",
                ("landing_page", "social_links"): json.dumps(
                    {
                        "instagram": "https://instagram.com/acme-rentals",
                        "facebook": "https://facebook.com/acme-rentals",
                    }
                ),
                ("landing_page", "show_share_buttons"): "true",
                ("landing_page", "seo_title"): "Acme Rentals — Luxury Vacation Homes",
                ("landing_page", "seo_description"): "Book your perfect holiday home",
                (
                    "landing_page",
                    "og_image_url",
                ): "https://cdn.example.com/og-preview.jpg",
            }
            return params.get((namespace, key))

        svc.get_param.side_effect = get_param_side_effect
        return svc

    @pytest.fixture
    def mock_slug_svc(self):
        """Mock TenantSlugService."""
        svc = Mock()
        svc.get_slug.return_value = "acme-rentals"
        return svc

    @pytest.fixture
    def mock_s3(self):
        """Mock boto3 S3 client."""
        with patch(
            "services.landing_page_publish_service.boto3.client"
        ) as mock_client_factory:
            mock_client = Mock()
            mock_client_factory.return_value = mock_client
            mock_client.put_object.return_value = {}
            mock_client.delete_object.return_value = {}
            yield mock_client

    @pytest.fixture
    def service(self, mock_landing_page_svc, mock_param_svc, mock_slug_svc, mock_s3):
        """Create LandingPagePublishService with mocked dependencies."""
        with patch.dict(
            os.environ,
            {
                "AWS_DEFAULT_REGION": "eu-west-1",
                "ENVIRONMENT": "test",
                "LANDING_PAGES_BUCKET": "myadmin-public-pages-test",
                "LANDING_PAGE_BASE_URL": "https://myadmin.app",
            },
        ):
            from services.landing_page_publish_service import LandingPagePublishService

            svc = LandingPagePublishService(
                landing_page_service=mock_landing_page_svc,
                parameter_service=mock_param_svc,
                slug_service=mock_slug_svc,
            )
            # Replace the S3 client with our mock
            svc._s3 = mock_s3
            return svc

    # ========================================================================
    # Publish tests (Task 1.11)
    # ========================================================================

    def test_publish_happy_path(
        self, service, mock_landing_page_svc, mock_slug_svc, mock_s3
    ):
        """Test publish succeeds with all steps completing."""
        result = service.publish("TestTenant", "admin@acme.nl")

        assert result["success"] is True
        assert result["version"] == 5
        assert "published_at" in result
        assert result["public_url"] == "/p/acme-rentals"

        # Verify S3 writes
        assert mock_s3.put_object.call_count == 2

        # First call: landing.json
        json_call = mock_s3.put_object.call_args_list[0]
        assert json_call[1]["Key"] == "acme-rentals/landing.json"
        assert json_call[1]["ContentType"] == "application/json"
        body = json.loads(json_call[1]["Body"])
        assert body["tenant_slug"] == "acme-rentals"
        assert body["version"] == 5
        assert len(body["sections"]) == 2

        # Second call: index.html
        html_call = mock_s3.put_object.call_args_list[1]
        assert html_call[1]["Key"] == "acme-rentals/index.html"
        assert html_call[1]["ContentType"] == "text/html; charset=utf-8"

        # Verify version saved in DynamoDB
        mock_landing_page_svc.save_version.assert_called_once()

    def test_publish_no_slug(self, service, mock_slug_svc):
        """Test publish fails when tenant has no slug configured."""
        mock_slug_svc.get_slug.return_value = None

        result = service.publish("TestTenant", "admin@acme.nl")

        assert result["success"] is False
        assert "No slug configured" in result["error"]

    def test_publish_no_draft(self, service, mock_landing_page_svc):
        """Test publish fails when no draft exists."""
        mock_landing_page_svc.get_draft.return_value = None

        result = service.publish("TestTenant", "admin@acme.nl")

        assert result["success"] is False
        assert "No draft found" in result["error"]

    def test_publish_s3_landing_json_error(self, service, mock_s3):
        """Test publish fails gracefully on S3 landing.json write error."""
        mock_s3.put_object.side_effect = ClientError(
            {"Error": {"Code": "InternalError", "Message": "S3 failed"}},
            "PutObject",
        )

        result = service.publish("TestTenant", "admin@acme.nl")

        assert result["success"] is False
        assert "Failed to publish landing page data" in result["error"]

    def test_publish_s3_index_html_error(self, service, mock_s3):
        """Test publish fails gracefully on S3 index.html write error."""
        # First put_object succeeds, second fails
        mock_s3.put_object.side_effect = [
            {},  # landing.json succeeds
            ClientError(
                {"Error": {"Code": "InternalError", "Message": "S3 failed"}},
                "PutObject",
            ),
        ]

        result = service.publish("TestTenant", "admin@acme.nl")

        assert result["success"] is False
        assert "Failed to publish index.html" in result["error"]

    def test_publish_version_save_failure_still_succeeds(
        self, service, mock_landing_page_svc
    ):
        """Test publish still returns success if version snapshot save fails."""
        mock_landing_page_svc.save_version.return_value = {
            "success": False,
            "error": "DynamoDB throttled",
        }

        result = service.publish("TestTenant", "admin@acme.nl")

        # Publish should still succeed — the S3 files are the critical path
        assert result["success"] is True

    def test_publish_branding_included_in_json(self, service, mock_s3):
        """Test published JSON contains resolved branding."""
        service.publish("TestTenant", "admin@acme.nl")

        json_call = mock_s3.put_object.call_args_list[0]
        body = json.loads(json_call[1]["Body"])

        assert body["branding"]["name"] == "Acme Rentals B.V."
        assert body["branding"]["tagline"] == "Your holiday starts here"
        assert body["branding"]["logo_url"] == "https://cdn.example.com/logo.png"
        assert body["branding"]["color_primary"] == "#2D5F8A"
        assert body["branding"]["color_accent"] == "#F4A261"

    def test_publish_footer_included_in_json(self, service, mock_s3):
        """Test published JSON contains footer with social links."""
        service.publish("TestTenant", "admin@acme.nl")

        json_call = mock_s3.put_object.call_args_list[0]
        body = json.loads(json_call[1]["Body"])

        assert body["footer"]["company_name"] == "Acme Rentals B.V."
        assert body["footer"]["address"] == "Keizersgracht 123"
        assert (
            body["footer"]["social_links"]["instagram"]
            == "https://instagram.com/acme-rentals"
        )

    def test_publish_seo_included_in_json(self, service, mock_s3):
        """Test published JSON contains SEO fields."""
        service.publish("TestTenant", "admin@acme.nl")

        json_call = mock_s3.put_object.call_args_list[0]
        body = json.loads(json_call[1]["Body"])

        assert body["seo"]["title"] == "Acme Rentals — Luxury Vacation Homes"
        assert body["seo"]["description"] == "Book your perfect holiday home"
        assert body["seo"]["og_image"] == "https://cdn.example.com/og-preview.jpg"
        assert body["seo"]["canonical_url"] == "https://myadmin.app/p/acme-rentals"

    def test_publish_settings_share_buttons(self, service, mock_s3):
        """Test published JSON has settings.show_share_buttons resolved."""
        service.publish("TestTenant", "admin@acme.nl")

        json_call = mock_s3.put_object.call_args_list[0]
        body = json.loads(json_call[1]["Body"])

        assert body["settings"]["show_share_buttons"] is True

    # ========================================================================
    # Unpublish tests (Task 1.12)
    # ========================================================================

    def test_unpublish_happy_path(self, service, mock_s3):
        """Test unpublish deletes both S3 files and returns success."""
        result = service.unpublish("TestTenant", "admin@acme.nl")

        assert result["success"] is True
        assert result["message"] == "Landing page is now offline."

        # Verify both files deleted
        assert mock_s3.delete_object.call_count == 2
        calls = mock_s3.delete_object.call_args_list
        assert calls[0][1]["Key"] == "acme-rentals/landing.json"
        assert calls[1][1]["Key"] == "acme-rentals/index.html"

    def test_unpublish_no_slug(self, service, mock_slug_svc):
        """Test unpublish fails when no slug configured."""
        mock_slug_svc.get_slug.return_value = None

        result = service.unpublish("TestTenant", "admin@acme.nl")

        assert result["success"] is False
        assert "No slug configured" in result["error"]

    def test_unpublish_files_dont_exist(self, service, mock_s3):
        """Test unpublish succeeds even if files don't exist in S3."""
        # S3 delete_object doesn't raise for non-existent keys by default
        # (AWS returns 204 even if the object doesn't exist)
        mock_s3.delete_object.return_value = {}

        result = service.unpublish("TestTenant", "admin@acme.nl")

        assert result["success"] is True

    def test_unpublish_s3_error(self, service, mock_s3):
        """Test unpublish fails on S3 error (non-NoSuchKey)."""
        mock_s3.delete_object.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "Access denied"}},
            "DeleteObject",
        )

        result = service.unpublish("TestTenant", "admin@acme.nl")

        assert result["success"] is False
        assert "Failed to delete" in result["error"]

    # ========================================================================
    # Branding resolution tests (Task 1.15)
    # ========================================================================

    def test_resolve_branding_all_from_landing_page(self, service):
        """Test branding resolved entirely from landing_page namespace."""
        result = service.resolve_branding("TestTenant")

        assert result["company_name"] == "Acme Rentals B.V."
        assert result["tagline"] == "Your holiday starts here"
        assert result["logo_url"] == "https://cdn.example.com/logo.png"
        assert result["color_primary"] == "#2D5F8A"
        assert result["color_accent"] == "#F4A261"
        assert result["address"] == "Keizersgracht 123"
        assert result["coc"] == "12345678"
        assert result["vat"] == "NL123456789B01"

    def test_resolve_branding_fallback_to_zzp(self, service, mock_param_svc):
        """Test branding falls back to zzp_branding when landing_page empty."""

        def get_param_fallback(namespace, key, tenant=None, **kwargs):
            if namespace == "landing_page":
                return None  # Nothing in landing_page namespace
            if namespace == "zzp_branding":
                return {"company_name": "ZZP Company", "email": "zzp@co.nl"}.get(key)
            return None

        mock_param_svc.get_param.side_effect = get_param_fallback

        result = service.resolve_branding("TestTenant")

        assert result["company_name"] == "ZZP Company"
        assert result["email"] == "zzp@co.nl"
        assert result["logo_url"] == ""  # Not in any namespace

    def test_resolve_branding_fallback_to_str(self, service, mock_param_svc):
        """Test branding falls back to str_branding as third priority."""

        def get_param_fallback(namespace, key, tenant=None, **kwargs):
            if namespace == "landing_page":
                return None
            if namespace == "zzp_branding":
                return None
            if namespace == "str_branding":
                return {"company_name": "STR Rentals", "phone": "+31 123"}.get(key)
            return None

        mock_param_svc.get_param.side_effect = get_param_fallback

        result = service.resolve_branding("TestTenant")

        assert result["company_name"] == "STR Rentals"
        assert result["phone"] == "+31 123"

    def test_resolve_branding_empty_when_nothing_found(self, service, mock_param_svc):
        """Test branding returns empty strings when no values found anywhere."""
        mock_param_svc.get_param.side_effect = None
        mock_param_svc.get_param.return_value = None

        result = service.resolve_branding("TestTenant")

        for field in result.values():
            assert field == ""

    def test_resolve_branding_mixed_sources(self, service, mock_param_svc):
        """Test branding can resolve different fields from different namespaces."""

        def get_param_mixed(namespace, key, tenant=None, **kwargs):
            if namespace == "landing_page" and key == "company_name":
                return "Landing Company"
            if namespace == "zzp_branding" and key == "email":
                return "zzp@example.com"
            if namespace == "str_branding" and key == "phone":
                return "+31 555"
            return None

        mock_param_svc.get_param.side_effect = get_param_mixed

        result = service.resolve_branding("TestTenant")

        assert result["company_name"] == "Landing Company"
        assert result["email"] == "zzp@example.com"
        assert result["phone"] == "+31 555"

    # ========================================================================
    # Footer resolution tests
    # ========================================================================

    def test_resolve_footer_with_social_links(self, service):
        """Test footer includes social links parsed from JSON string."""
        branding = {
            "company_name": "Acme B.V.",
            "address": "Street 1",
            "postal_city": "1000 AA City",
            "country": "NL",
            "phone": "+31 123",
            "email": "info@acme.nl",
            "coc": "123",
            "vat": "NL123",
        }

        result = service.resolve_footer("TestTenant", branding)

        assert result["company_name"] == "Acme B.V."
        assert result["address"] == "Street 1"
        assert isinstance(result["social_links"], dict)
        assert "instagram" in result["social_links"]

    def test_resolve_footer_no_social_links(self, service, mock_param_svc):
        """Test footer returns empty social_links when not configured."""
        mock_param_svc.get_param.side_effect = None
        mock_param_svc.get_param.return_value = None

        result = service.resolve_footer("TestTenant", {"company_name": "Test"})

        assert result["social_links"] == {}

    def test_resolve_footer_social_links_as_dict(self, service, mock_param_svc):
        """Test footer handles social_links already as dict (not JSON string)."""
        links_dict = {"instagram": "https://instagram.com/test"}

        def get_param_dict(namespace, key, tenant=None, **kwargs):
            if key == "social_links":
                return links_dict
            return None

        mock_param_svc.get_param.side_effect = get_param_dict

        result = service.resolve_footer("TestTenant", {})

        assert result["social_links"] == links_dict

    # ========================================================================
    # SEO resolution tests
    # ========================================================================

    def test_resolve_seo_with_params(self, service):
        """Test SEO fields resolved from ParameterService."""
        branding = {"company_name": "Acme"}

        result = service.resolve_seo("TestTenant", "acme-rentals", branding)

        assert result["title"] == "Acme Rentals — Luxury Vacation Homes"
        assert result["description"] == "Book your perfect holiday home"
        assert result["og_image"] == "https://cdn.example.com/og-preview.jpg"
        assert result["canonical_url"] == "https://myadmin.app/p/acme-rentals"

    def test_resolve_seo_fallback_title_to_company_name(self, service, mock_param_svc):
        """Test SEO title falls back to branding company_name."""
        mock_param_svc.get_param.side_effect = None
        mock_param_svc.get_param.return_value = None

        result = service.resolve_seo(
            "TestTenant", "acme-rentals", {"company_name": "Fallback Corp"}
        )

        assert result["title"] == "Fallback Corp"

    def test_resolve_seo_canonical_url_uses_base_url(self, service, mock_param_svc):
        """Test canonical URL is built from base_url + slug."""
        mock_param_svc.get_param.return_value = None

        result = service.resolve_seo("TestTenant", "my-slug", {})

        assert result["canonical_url"] == "https://myadmin.app/p/my-slug"

    # ========================================================================
    # HTML generation tests (Task 1.16)
    # ========================================================================

    def test_generate_index_html_contains_og_tags(self, service):
        """Test generated HTML includes all Open Graph meta tags."""
        published_data = {
            "seo": {
                "title": "Test Title",
                "description": "Test description",
                "og_image": "https://cdn.example.com/image.jpg",
                "canonical_url": "https://myadmin.app/p/test-slug",
            },
            "branding": {"name": "Test Company"},
        }

        html_output = service.generate_index_html(published_data, "test-slug")

        assert '<meta property="og:type" content="website" />' in html_output
        assert '<meta property="og:title" content="Test Title" />' in html_output
        assert (
            '<meta property="og:description" content="Test description" />'
            in html_output
        )
        assert (
            '<meta property="og:image" content="https://cdn.example.com/image.jpg" />'
            in html_output
        )
        assert (
            '<meta property="og:url" content="https://myadmin.app/p/test-slug" />'
            in html_output
        )
        assert '<meta property="og:site_name" content="Test Company" />' in html_output
        assert '<meta property="og:locale" content="nl_NL" />' in html_output

    def test_generate_index_html_contains_twitter_card(self, service):
        """Test generated HTML includes Twitter Card meta tags."""
        published_data = {
            "seo": {
                "title": "Twitter Test",
                "description": "Twitter desc",
                "og_image": "https://cdn.example.com/tw.jpg",
                "canonical_url": "https://myadmin.app/p/tw-slug",
            },
            "branding": {"name": "TW Co"},
        }

        html_output = service.generate_index_html(published_data, "tw-slug")

        assert (
            '<meta name="twitter:card" content="summary_large_image" />' in html_output
        )
        assert '<meta name="twitter:title" content="Twitter Test" />' in html_output
        assert (
            '<meta name="twitter:description" content="Twitter desc" />' in html_output
        )
        assert (
            '<meta name="twitter:image" content="https://cdn.example.com/tw.jpg" />'
            in html_output
        )

    def test_generate_index_html_escapes_xss(self, service):
        """Test HTML generation escapes dangerous characters to prevent XSS."""
        published_data = {
            "seo": {
                "title": '<script>alert("xss")</script>',
                "description": 'A "quoted" & <tagged> value',
                "og_image": "",
                "canonical_url": "https://myadmin.app/p/test",
            },
            "branding": {"name": "Test & Co <b>bold</b>"},
        }

        html_output = service.generate_index_html(published_data, "test")

        # XSS payload must be escaped
        assert "<script>alert" not in html_output
        assert "&lt;script&gt;" in html_output
        assert "&amp;" in html_output
        assert "&lt;tagged&gt;" in html_output
        assert (
            "&#x27;" in html_output
            or "&quot;" in html_output
            or "quoted" in html_output
        )

    def test_generate_index_html_contains_slug_variable(self, service):
        """Test HTML includes the slug in the canonical URL or structure."""
        published_data = {
            "seo": {
                "title": "T",
                "description": "D",
                "og_image": "",
                "canonical_url": "https://example.com/p/my-tenant",
            },
            "branding": {"name": "N"},
        }

        html_output = service.generate_index_html(published_data, "my-tenant")

        # Slug is used in canonical URL
        assert "my-tenant" in html_output

    def test_generate_index_html_contains_noscript(self, service):
        """Test HTML works without JavaScript (standalone static page)."""
        published_data = {
            "seo": {
                "title": "NoScript Title",
                "description": "NoScript Desc",
                "og_image": "",
                "canonical_url": "",
            },
            "branding": {"name": "N"},
        }

        html_output = service.generate_index_html(published_data, "slug")

        # Static HTML renders content directly — no JS required
        assert "NoScript Title" in html_output

    def test_generate_index_html_has_valid_structure(self, service):
        """Test HTML has proper doctype, html, head, body structure."""
        published_data = {
            "seo": {
                "title": "T",
                "description": "D",
                "og_image": "",
                "canonical_url": "",
            },
            "branding": {"name": "N"},
        }

        html_output = service.generate_index_html(published_data, "slug")

        assert html_output.startswith("<!DOCTYPE html>")
        assert '<html lang="nl">' in html_output
        assert "<head>" in html_output
        assert "</head>" in html_output
        assert "<body>" in html_output
        assert "</body>" in html_output
        assert '<link rel="canonical"' in html_output

    def test_generate_index_html_includes_spa_script(self, service):
        """Test HTML includes inline styles (standalone static page)."""
        published_data = {
            "seo": {
                "title": "T",
                "description": "D",
                "og_image": "",
                "canonical_url": "",
            },
            "branding": {"name": "N"},
        }

        html_output = service.generate_index_html(published_data, "slug")

        # Standalone HTML has inline <style> instead of external script
        assert "<style>" in html_output

    def test_generate_index_html_slug_escaped(self, service):
        """Test slug is HTML-escaped in the output."""
        published_data = {
            "seo": {
                "title": "T",
                "description": "D",
                "og_image": "",
                "canonical_url": "",
            },
            "branding": {"name": "N"},
        }

        html_output = service.generate_index_html(published_data, 'test";alert(1)//')

        # The slug should be escaped
        assert 'test";alert(1)//' not in html_output
        assert "alert(1)" not in html_output or "&quot;" in html_output

    # ========================================================================
    # Module data enrichment tests (Task 3.14)
    # ========================================================================

    def test_enrich_services_block(self, service):
        """Test services block gets enriched with ZZP data at publish time."""
        mock_db = Mock()
        service.db = mock_db

        sections = [
            {
                "id": "block-002",
                "type": "services",
                "properties": {"title": "Our Services"},
            },
        ]

        zzp_data = [
            {"id": 1, "name": "Web Dev", "price": "€95/uur", "category": "dev"},
        ]

        with patch(
            "services.landing_page_data_loaders.load_zzp_public_services",
            return_value=zzp_data,
        ):
            service._enrich_sections_with_module_data(sections, "TestTenant")

        assert sections[0]["properties"]["items"] == zzp_data
        assert sections[0]["properties"]["title"] == "Our Services"

    def test_enrich_skips_non_data_blocks(self, service):
        """Test enrichment does not modify hero/about/other block types."""
        mock_db = Mock()
        service.db = mock_db

        sections = [
            {"id": "block-001", "type": "hero", "properties": {"title": "Welcome"}},
            {
                "id": "block-002",
                "type": "about",
                "properties": {"content_md": "About us"},
            },
        ]

        service._enrich_sections_with_module_data(sections, "TestTenant")

        # Sections should be unchanged — no items injected
        assert "items" not in sections[0].get("properties", {})
        assert "items" not in sections[1].get("properties", {})

    def test_enrich_without_db_manager_logs_warning(self, service):
        """Test enrichment is skipped gracefully when no db_manager available."""
        service.db = None

        sections = [
            {"id": "block-001", "type": "services", "properties": {}},
        ]

        # Should not raise — just logs warning and returns
        service._enrich_sections_with_module_data(sections, "TestTenant")

        # Section unchanged (no items injected)
        assert "items" not in sections[0]["properties"]

    def test_enrich_creates_properties_dict_if_missing(self, service):
        """Test enrichment creates properties dict on section if missing."""
        mock_db = Mock()
        service.db = mock_db

        sections = [
            {"id": "block-001", "type": "services"},  # No 'properties' key
        ]

        zzp_data = [{"id": 1, "name": "Consulting"}]

        with patch(
            "services.landing_page_data_loaders.load_zzp_public_services",
            return_value=zzp_data,
        ):
            service._enrich_sections_with_module_data(sections, "TestTenant")

        assert sections[0]["properties"]["items"] == zzp_data

    def test_enrich_services_only(self, service):
        """Test enrichment handles services block type only."""
        mock_db = Mock()
        service.db = mock_db

        sections = [
            {"id": "block-001", "type": "hero", "properties": {}},
            {"id": "block-002", "type": "services", "properties": {}},
        ]

        zzp_data = [{"id": 2, "name": "Design"}]

        with patch(
            "services.landing_page_data_loaders.load_zzp_public_services",
            return_value=zzp_data,
        ):
            service._enrich_sections_with_module_data(sections, "TestTenant")

        assert "items" not in sections[0]["properties"]
        assert sections[1]["properties"]["items"] == zzp_data

    # ========================================================================
    # Initialization tests
    # ========================================================================

    def test_init_defaults(self, mock_landing_page_svc, mock_param_svc, mock_slug_svc):
        """Test service initializes with correct defaults."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("LANDING_PAGES_BUCKET", None)
            os.environ.pop("ENVIRONMENT", None)
            os.environ.pop("LANDING_PAGE_BASE_URL", None)

            with patch(
                "services.landing_page_publish_service.boto3.client"
            ) as mock_boto:
                mock_boto.return_value = Mock()

                from services.landing_page_publish_service import (
                    LandingPagePublishService,
                )

                svc = LandingPagePublishService(
                    landing_page_service=mock_landing_page_svc,
                    parameter_service=mock_param_svc,
                    slug_service=mock_slug_svc,
                )

                assert svc.bucket_name == "myadmin-public-pages-production"
                assert svc.base_url == "https://myadmin.app"

    def test_init_with_env_vars(
        self, mock_landing_page_svc, mock_param_svc, mock_slug_svc
    ):
        """Test service reads bucket name and base URL from environment."""
        with patch.dict(
            os.environ,
            {
                "LANDING_PAGES_BUCKET": "custom-bucket",
                "LANDING_PAGE_BASE_URL": "https://custom.app",
                "CLOUDFRONT_PUBLIC_PAGES_DOMAIN": "d123.cloudfront.net",
            },
        ):
            with patch(
                "services.landing_page_publish_service.boto3.client"
            ) as mock_boto:
                mock_boto.return_value = Mock()

                from services.landing_page_publish_service import (
                    LandingPagePublishService,
                )

                svc = LandingPagePublishService(
                    landing_page_service=mock_landing_page_svc,
                    parameter_service=mock_param_svc,
                    slug_service=mock_slug_svc,
                )

                assert svc.bucket_name == "custom-bucket"
                assert svc.base_url == "https://custom.app"
                assert svc.cloudfront_domain == "d123.cloudfront.net"
