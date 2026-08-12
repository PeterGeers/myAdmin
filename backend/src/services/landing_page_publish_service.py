"""
Landing Page Publish Service

Orchestrates the publish/unpublish workflow for tenant landing pages.
Rendering is delegated to LandingPageRenderers; CSS/style utilities to
LandingPageStyles.

Tasks: 1.11, 1.12, 1.15, 1.16, 3.14
"""

import html
import json
import logging
import os
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

from services.landing_page_renderers import LandingPageRenderers
from services.landing_page_styles import LandingPageStyles
from services.media_asset_service import MediaAssetService

logger = logging.getLogger(__name__)


class LandingPagePublishService:
    """
    Orchestrates publishing/unpublishing tenant landing pages.

    Delegates rendering to LandingPageRenderers, CSS to LandingPageStyles.
    """

    def __init__(self, landing_page_service, parameter_service, slug_service, db_manager=None):
        self.landing_page_svc = landing_page_service
        self.param_svc = parameter_service
        self.slug_svc = slug_service
        self.db = db_manager

        if db_manager:
            self.asset_svc = MediaAssetService(db_manager, parameter_service)
        else:
            self.asset_svc = None

        region = os.environ.get("AWS_DEFAULT_REGION", "eu-west-1")
        env = os.environ.get("ENVIRONMENT", "production")
        self.bucket_name = os.environ.get(
            "LANDING_PAGES_BUCKET", f"myadmin-public-pages-{env}"
        )
        self.cloudfront_domain = os.environ.get("CLOUDFRONT_PUBLIC_PAGES_DOMAIN", "")
        self.cloudfront_distribution_id = os.environ.get(
            "CLOUDFRONT_PUBLIC_PAGES_DISTRIBUTION_ID", ""
        )
        self.base_url = os.environ.get("LANDING_PAGE_BASE_URL", "https://myadmin.app")
        self._cloudfront = boto3.client("cloudfront", region_name=region)

    # ========================================================================
    # Publish
    # ========================================================================

    def publish(self, tenant: str, published_by: str) -> dict:
        """
        Publish the current draft landing page to S3.

        Resolves slug → draft → branding → footer/SEO, writes landing.json
        and index.html to S3, saves version snapshot, invalidates CloudFront.
        """
        slug = self.slug_svc.get_slug(tenant)
        if not slug:
            return {"success": False, "error": "No slug configured for this tenant. Set a slug first."}

        draft = self.landing_page_svc.get_draft(slug)
        if not draft:
            return {"success": False, "error": "No draft found. Create a landing page draft first."}

        branding = self.resolve_branding(tenant)
        footer = self.resolve_footer(tenant, branding)
        seo = self.resolve_seo(tenant, slug, branding)

        now = datetime.now(timezone.utc).isoformat()
        version = draft.get("version", 1)
        sections = draft.get("sections", [])
        show_share_buttons = self.param_svc.get_param(
            "landing_page", "show_share_buttons", tenant=tenant
        )

        published_data = {
            "tenant_slug": slug,
            "published_at": now,
            "version": version,
            "branding": {
                "name": branding.get("company_name", ""),
                "tagline": branding.get("tagline", ""),
                "logo_url": branding.get("logo_url", ""),
                "color_primary": branding.get("color_primary", ""),
                "color_accent": branding.get("color_accent", ""),
            },
            "footer": footer,
            "seo": seo,
            "settings": {"show_share_buttons": show_share_buttons in ("true", "True", True)},
            "sections": sections,
        }

        self._enrich_sections_with_module_data(published_data["sections"], tenant)

        # Write landing.json to S3
        json_body = json.dumps(published_data, ensure_ascii=False)
        try:
            s3_client = boto3.client("s3", region_name=os.environ.get("AWS_DEFAULT_REGION", "eu-west-1"))
            s3_client.put_object(
                Bucket=self.bucket_name,
                Key=f"{slug}/landing.json",
                Body=json_body.encode("utf-8"),
                ContentType="application/json",
                CacheControl="public, max-age=300",
            )
            logger.info("Published landing.json to s3://%s/%s/landing.json", self.bucket_name, slug)
        except (ClientError, ValueError) as e:
            logger.error("S3 put_object landing.json failed for slug=%s: %s", slug, e)
            return {"success": False, "error": "Failed to publish landing page data to S3."}

        # Generate and write index.html to S3
        try:
            index_html = self.generate_index_html(published_data, slug)
            # Write directly to {slug}/index.html — CloudFront expects this key
            s3_client = boto3.client("s3", region_name=os.environ.get("AWS_DEFAULT_REGION", "eu-west-1"))
            s3_client.put_object(
                Bucket=self.bucket_name,
                Key=f"{slug}/index.html",
                Body=index_html.encode("utf-8") if isinstance(index_html, str) else index_html,
                ContentType="text/html; charset=utf-8",
                CacheControl="public, max-age=300",
            )
            logger.info("Published index.html to s3://%s/%s/index.html", self.bucket_name, slug)
        except (ClientError, ValueError) as e:
            logger.error("S3 put_object index.html failed for slug=%s: %s", slug, e)
            return {"success": False, "error": "Failed to publish index.html to S3."}

        # Save version snapshot
        version_result = self.landing_page_svc.save_version(
            slug=slug, version=version, sections=sections, published_by=published_by,
        )
        if not version_result.get("success"):
            logger.warning("Failed to save version snapshot for slug=%s version=%d", slug, version)
        else:
            self.landing_page_svc.prune_old_versions(slug)

        self._invalidate_cache(slug)

        return {"success": True, "version": version, "published_at": now, "public_url": f"/p/{slug}"}

    # ========================================================================
    # Unpublish
    # ========================================================================

    def unpublish(self, tenant: str, unpublished_by: str) -> dict:
        """Take a landing page offline by detaching and deleting assets."""
        slug = self.slug_svc.get_slug(tenant)
        if not slug:
            return {"success": False, "error": "No slug configured for this tenant."}

        if not self.asset_svc:
            return {"success": False, "error": "MediaAssetService not available (db_manager required)."}

        asset_ids = self._find_landing_page_assets(tenant, slug)

        if asset_ids:
            for asset_id in asset_ids:
                try:
                    detach_result = self.asset_svc.detach(tenant, asset_id, "landing_page", str(slug))
                    if (
                        detach_result.get("success")
                        and detach_result.get("asset", {}).get("reference_count", 1) == 0
                    ):
                        self.asset_svc.delete_asset(tenant, asset_id, approved_by=unpublished_by)
                except Exception as e:
                    logger.warning("Asset detach/delete failed for asset_id=%s slug=%s: %s", asset_id, slug, e)
        else:
            # Legacy S3 cleanup (pre-migration data)
            for key in (f"{slug}/landing.json", f"{slug}/index.html"):
                self.asset_svc._delete_raw(self.bucket_name, key)

        logger.info("Unpublished landing page for tenant=%s slug=%s by=%s", tenant, slug, unpublished_by)
        self._invalidate_cache(slug)
        return {"success": True, "message": "Landing page is now offline."}

    # ========================================================================
    # Internal Helpers
    # ========================================================================

    def _find_landing_page_assets(self, tenant: str, slug: str) -> list:
        """Find asset IDs registered for a landing page via the references table."""
        if not self.db:
            return []
        try:
            rows = self.db.execute_query(
                """
                SELECT ar.asset_id
                FROM s3_asset_references ar
                JOIN s3_assets a ON a.id = ar.asset_id
                WHERE ar.entity_type = 'landing_page'
                  AND ar.entity_id = %s
                  AND a.administration = %s
                """,
                (str(slug), tenant),
                fetch=True,
            )
            return [row["asset_id"] for row in rows] if rows else []
        except Exception as e:
            logger.warning("Failed to query landing page assets for slug=%s: %s", slug, e)
            return []

    def _invalidate_cache(self, slug: str) -> None:
        """Invalidate CloudFront cache for a tenant's landing page files."""
        if not self.cloudfront_distribution_id:
            logger.warning("CLOUDFRONT_PUBLIC_PAGES_DISTRIBUTION_ID not set — skipping cache invalidation")
            return
        try:
            self._cloudfront.create_invalidation(
                DistributionId=self.cloudfront_distribution_id,
                InvalidationBatch={
                    "Paths": {"Quantity": 2, "Items": [f"/{slug}/*", f"/{slug}"]},
                    "CallerReference": f"{slug}-{datetime.now(timezone.utc).isoformat()}",
                },
            )
            logger.info("CloudFront invalidation created for slug=%s", slug)
        except ClientError as e:
            logger.warning("CloudFront invalidation failed for slug=%s: %s", slug, e)

    def _get_active_custom_domain(self, tenant: str) -> str | None:
        """Get the active custom domain for a tenant, or None."""
        if not self.db:
            return None
        try:
            result = self.db.execute_query(
                "SELECT domain FROM tenant_custom_domains "
                "WHERE administration = %s AND domain_type = 'custom' "
                "AND is_active = TRUE LIMIT 1",
                (tenant,),
            )
            if result and result[0].get("domain"):
                return result[0]["domain"]
        except Exception:
            pass
        return None

    def _is_jabaki_enabled(self, tenant: str) -> bool:
        """Check if Jabaki subdomain is enabled for a tenant."""
        if not self.db:
            return False
        try:
            result = self.db.execute_query(
                "SELECT jabaki_enabled FROM tenant_slugs WHERE administration = %s",
                (tenant,),
            )
            if result and result[0].get("jabaki_enabled"):
                return True
        except Exception:
            pass
        return False

    # ========================================================================
    # Branding / Footer / SEO Resolution
    # ========================================================================

    def resolve_branding(self, tenant: str) -> dict:
        """
        Resolve branding fields with fallback chain:
        landing_page → zzp_branding → str_branding.

        Then apply theme layer: preset defaults fill unset fields,
        explicit overrides are applied on top.
        """
        fields = [
            "company_name", "logo_url", "address", "postal_city", "country",
            "phone", "email", "coc", "vat", "tagline", "color_primary", "color_accent",
            "font_heading", "font_body", "section_bg",
        ]
        result = {}
        for field in fields:
            value = self.param_svc.get_param("landing_page", field, tenant=tenant)
            if not value:
                value = self.param_svc.get_param("zzp_branding", field, tenant=tenant)
            if not value:
                value = self.param_svc.get_param("str_branding", field, tenant=tenant)
            result[field] = value or ""

        # Theme layer: apply preset defaults, then overrides
        theme_param = self.param_svc.get_param("landing_page", "theme", tenant=tenant)
        if theme_param:
            theme_data = json.loads(theme_param) if isinstance(theme_param, str) else theme_param
            preset_name = theme_data.get("preset", "")
            if preset_name in LandingPageStyles.THEME_PRESETS:
                preset = LandingPageStyles.THEME_PRESETS[preset_name]
                # Fill unset fields from preset
                for key, value in preset.items():
                    if key in result and not result[key]:
                        result[key] = value
            # Apply explicit overrides on top
            overrides = theme_data.get("overrides", {})
            for key, value in overrides.items():
                if value:
                    result[key] = value

        return result

    def resolve_footer(self, tenant: str, branding: dict) -> dict:
        """Build footer object from branding fields and social links."""
        social_links_raw = self.param_svc.get_param("landing_page", "social_links", tenant=tenant)
        social_links = {}
        if social_links_raw:
            if isinstance(social_links_raw, str):
                try:
                    social_links = json.loads(social_links_raw)
                except (json.JSONDecodeError, TypeError):
                    social_links = {}
            elif isinstance(social_links_raw, dict):
                social_links = social_links_raw

        return {
            "company_name": branding.get("company_name", ""),
            "address": branding.get("address", ""),
            "postal_city": branding.get("postal_city", ""),
            "country": branding.get("country", ""),
            "phone": branding.get("phone", ""),
            "email": branding.get("email", ""),
            "coc": branding.get("coc", ""),
            "vat": branding.get("vat", ""),
            "social_links": social_links,
        }

    def resolve_seo(self, tenant: str, slug: str, branding: dict) -> dict:
        """Build SEO object from ParameterService with branding fallbacks."""
        title = self.param_svc.get_param("landing_page", "seo_title", tenant=tenant)
        if not title:
            title = branding.get("company_name", "")

        description = self.param_svc.get_param("landing_page", "seo_description", tenant=tenant) or ""
        og_image = self.param_svc.get_param("landing_page", "og_image_url", tenant=tenant) or ""

        custom_domain = self._get_active_custom_domain(tenant)
        jabaki_enabled = self._is_jabaki_enabled(tenant)

        if custom_domain:
            canonical_url = f"https://{custom_domain}/"
        elif jabaki_enabled:
            canonical_url = f"https://{slug}.jabaki.nl/"
        else:
            canonical_url = f"{self.base_url}/p/{slug}"

        alternate_urls = []
        if custom_domain:
            alternate_urls.append(f"https://{custom_domain}/")
        if jabaki_enabled:
            alternate_urls.append(f"https://{slug}.jabaki.nl/")
        alternate_urls.append(f"{self.base_url}/p/{slug}")
        alternate_urls = [u for u in alternate_urls if u != canonical_url]

        return {
            "title": title, "description": description, "og_image": og_image,
            "canonical_url": canonical_url, "alternate_urls": alternate_urls,
        }

    # ========================================================================
    # Module Data Enrichment
    # ========================================================================

    def _enrich_sections_with_module_data(self, sections: list, tenant: str) -> None:
        """Enrich sections with live module data snapshots at publish time."""
        from services.landing_page_data_loaders import load_zzp_public_services

        if not any(s.get("type") == "services" for s in sections):
            return
        if not self.db:
            logger.warning("No DatabaseManager available for module data enrichment")
            return

        zzp_items = load_zzp_public_services(self.db, tenant)
        for section in sections:
            if section.get("type") == "services" and zzp_items is not None:
                if "properties" not in section:
                    section["properties"] = {}
                section["properties"]["items"] = zzp_items

    # ========================================================================
    # HTML Generation
    # ========================================================================

    def generate_index_html(self, published_data: dict, slug: str) -> str:
        """
        Generate a standalone static HTML page.

        Delegates section rendering to LandingPageRenderers and style/CSS
        generation to LandingPageStyles.
        """
        seo = published_data.get("seo", {})
        branding = published_data.get("branding", {})
        footer = published_data.get("footer", {})
        sections = published_data.get("sections", [])

        title = html.escape(seo.get("title", branding.get("name", "")))
        description = html.escape(seo.get("description", ""))
        og_image = html.escape(seo.get("og_image", ""))
        canonical = html.escape(seo.get("canonical_url", f"{self.base_url}/p/{slug}"))
        site_name = html.escape(branding.get("name", ""))
        color_primary = html.escape(branding.get("color_primary", "#2D5F8A"))
        color_accent = html.escape(branding.get("color_accent", "#F4A261"))

        cf_domain = os.environ.get("CLOUDFRONT_PUBLIC_PAGES_DOMAIN", "")
        img_base = f"https://{cf_domain}" if cf_domain else ""

        # Fix image key prefix: stored keys may use tenant name (e.g., 'myadmin/images/...')
        # but S3 files are under the slug prefix (e.g., 'peter/images/...')
        # Correct the prefix in section image keys before rendering
        for section in sections:
            props = section.get("properties", {})
            # Fix single image_key fields
            img_key = props.get("image_key", "")
            if img_key and "/" in img_key and not img_key.startswith(slug + "/"):
                # Replace wrong prefix with slug prefix
                parts = img_key.split("/", 1)
                if len(parts) == 2:
                    props["image_key"] = f"{slug}/{parts[1]}"
            # Fix gallery images array
            for img in props.get("images", []):
                ik = img.get("image_key", "")
                if ik and "/" in ik and not ik.startswith(slug + "/"):
                    parts = ik.split("/", 1)
                    if len(parts) == 2:
                        img["image_key"] = f"{slug}/{parts[1]}"

        # Delegate rendering
        renderer = LandingPageRenderers(img_base=img_base, color_accent=color_accent, color_primary=color_primary)
        sections_html = renderer.render_sections_html(sections, slug)
        footer_html = renderer.render_footer_html(footer, branding)

        # Header
        logo_url = branding.get("logo_url", "")
        if logo_url and not logo_url.startswith("http"):
            logo_url = f"{img_base}/{logo_url}" if img_base else logo_url
        logo_url = html.escape(logo_url)
        tagline = html.escape(branding.get("tagline", ""))
        header_html = ""
        if logo_url or site_name:
            logo_img = f'<img src="{logo_url}" alt="{site_name}" style="max-height:60px;width:auto;margin:0 auto;">' if logo_url else ""
            tagline_p = f'<p style="color:#666;margin-top:0.5rem;font-size:1.1rem;">{tagline}</p>' if tagline else ""
            header_html = (
                '<header style="padding:1.5rem;text-align:center;border-bottom:1px solid #eee;'
                f'display:flex;flex-direction:column;align-items:center;">\n  {logo_img}\n  {tagline_p}\n</header>'
            )

        # Delegate styles
        font_links = LandingPageStyles.build_font_links(branding)
        font_links_html = f"\n  {font_links}" if font_links else ""
        css_variables = LandingPageStyles.build_css_variables(branding)
        page_css = LandingPageStyles.build_page_css(color_primary, color_accent)

        # Unified carousel JS (auto-advance, pause/resume, touch swipe)
        carousel_js = LandingPageStyles.build_carousel_js()

        return f"""<!DOCTYPE html>
<html lang="nl">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{title}</title>
  <meta name="description" content="{description}" />{font_links_html}
  <meta property="og:type" content="website" />
  <meta property="og:title" content="{title}" />
  <meta property="og:description" content="{description}" />
  <meta property="og:image" content="{og_image}" />
  <meta property="og:url" content="{canonical}" />
  <meta property="og:site_name" content="{site_name}" />
  <meta property="og:locale" content="nl_NL" />
  <meta name="twitter:card" content="summary_large_image" />
  <meta name="twitter:title" content="{title}" />
  <meta name="twitter:description" content="{description}" />
  <meta name="twitter:image" content="{og_image}" />
  <link rel="canonical" href="{canonical}" />
  <style>
{css_variables}
{page_css}
  </style>
</head>
<body>
{header_html}
{sections_html}
{footer_html}
{carousel_js}
</body>
</html>"""
