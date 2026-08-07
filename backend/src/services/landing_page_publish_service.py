"""
Landing Page Publish Service

Handles the publish/unpublish workflow for tenant landing pages.
Orchestrates reading from DynamoDB, resolving branding from ParameterService,
building the published JSON, writing to S3, and generating the index.html
with Open Graph meta tags for social crawlers.

Tasks: 1.11, 1.12, 1.15, 1.16, 3.14
"""

import html
import json
import logging
import os
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class LandingPagePublishService:
    """
    Service for publishing and unpublishing tenant landing pages.

    Coordinates between DynamoDB (content), ParameterService (branding),
    TenantSlugService (slug resolution), and S3 (public delivery).
    """

    def __init__(self, landing_page_service, parameter_service, slug_service, db_manager=None):
        """
        Initialize the publish service.

        Args:
            landing_page_service: LandingPageService instance for DynamoDB CRUD
            parameter_service: ParameterService instance for branding resolution
            slug_service: TenantSlugService instance for slug lookups
            db_manager: Optional DatabaseManager for audit logging
        """
        self.landing_page_svc = landing_page_service
        self.param_svc = parameter_service
        self.slug_svc = slug_service
        self.db = db_manager

        region = os.environ.get("AWS_DEFAULT_REGION", "eu-west-1")
        env = os.environ.get("ENVIRONMENT", "production")
        self.bucket_name = os.environ.get(
            "LANDING_PAGES_BUCKET", f"myadmin-public-pages-{env}"
        )
        self.cloudfront_domain = os.environ.get("CLOUDFRONT_PUBLIC_PAGES_DOMAIN", "")
        self.cloudfront_distribution_id = os.environ.get("CLOUDFRONT_PUBLIC_PAGES_DISTRIBUTION_ID", "")
        self.base_url = os.environ.get("LANDING_PAGE_BASE_URL", "https://myadmin.app")
        self._s3 = boto3.client("s3", region_name=region)
        self._cloudfront = boto3.client("cloudfront", region_name=region)

    # ========================================================================
    # Publish (Task 1.11)
    # ========================================================================

    def publish(self, tenant: str, published_by: str) -> dict:
        """
        Publish the current draft landing page to S3.

        Steps:
        1. Get slug for tenant
        2. Read draft from DynamoDB
        3. Resolve branding via fallback chain
        4. Resolve footer and SEO fields
        5. Build published JSON
        6. Write landing.json to S3
        7. Generate and write index.html to S3
        8. Save version snapshot in DynamoDB
        9. Return success with version info

        Args:
            tenant: Administration identifier
            published_by: Email of the user publishing

        Returns:
            Dict with success, version, published_at, public_url or error.
        """
        # Step 1: Resolve slug
        slug = self.slug_svc.get_slug(tenant)
        if not slug:
            return {"success": False, "error": "No slug configured for this tenant. Set a slug first."}

        # Step 2: Read draft from DynamoDB
        draft = self.landing_page_svc.get_draft(slug)
        if not draft:
            return {"success": False, "error": "No draft found. Create a landing page draft first."}

        # Step 3: Resolve branding
        branding = self.resolve_branding(tenant)

        # Step 4: Resolve footer and SEO
        footer = self.resolve_footer(tenant, branding)
        seo = self.resolve_seo(tenant, slug, branding)

        # Step 5: Build published JSON
        now = datetime.now(timezone.utc).isoformat()
        version = draft.get("version", 1)
        sections = draft.get("sections", [])

        # Resolve settings
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
            "settings": {
                "show_share_buttons": show_share_buttons in ("true", "True", True),
            },
            "sections": sections,
        }

        # Step 5b: Enrich sections with live module data (Task 3.14)
        self._enrich_sections_with_module_data(published_data["sections"], tenant)

        # Step 6: Write landing.json to S3
        try:
            self._s3.put_object(
                Bucket=self.bucket_name,
                Key=f"{slug}/landing.json",
                Body=json.dumps(published_data, ensure_ascii=False),
                ContentType="application/json",
                CacheControl="max-age=300",
            )
        except ClientError as e:
            logger.error("S3 put_object landing.json failed for slug=%s: %s", slug, e)
            return {"success": False, "error": "Failed to publish landing page data to S3."}

        # Step 7: Generate and write index.html to S3
        try:
            index_html = self.generate_index_html(published_data, slug)
            self._s3.put_object(
                Bucket=self.bucket_name,
                Key=f"{slug}/index.html",
                Body=index_html,
                ContentType="text/html; charset=utf-8",
                CacheControl="max-age=300",
            )
        except ClientError as e:
            logger.error("S3 put_object index.html failed for slug=%s: %s", slug, e)
            return {"success": False, "error": "Failed to publish index.html to S3."}

        # Step 8: Save version snapshot in DynamoDB
        version_result = self.landing_page_svc.save_version(
            slug=slug,
            version=version,
            sections=sections,
            published_by=published_by,
        )
        if not version_result.get("success"):
            logger.warning("Failed to save version snapshot for slug=%s version=%d", slug, version)

        # Step 9: Invalidate CloudFront cache for immediate visibility
        self._invalidate_cache(slug)

        # Step 10: Return success
        return {
            "success": True,
            "version": version,
            "published_at": now,
            "public_url": f"/p/{slug}",
        }

    # ========================================================================
    # Unpublish (Task 1.12)
    # ========================================================================

    def unpublish(self, tenant: str, unpublished_by: str) -> dict:
        """
        Take a landing page offline by deleting S3 files.

        Steps:
        1. Get slug for tenant
        2. Delete landing.json from S3
        3. Delete index.html from S3
        4. Return success

        Args:
            tenant: Administration identifier
            unpublished_by: Email of the user unpublishing

        Returns:
            Dict with success and message or error.
        """
        # Step 1: Resolve slug
        slug = self.slug_svc.get_slug(tenant)
        if not slug:
            return {"success": False, "error": "No slug configured for this tenant."}

        # Step 2 & 3: Delete S3 files (graceful — not an error if files don't exist)
        for key in (f"{slug}/landing.json", f"{slug}/index.html"):
            try:
                self._s3.delete_object(Bucket=self.bucket_name, Key=key)
            except ClientError as e:
                error_code = e.response.get("Error", {}).get("Code", "")
                if error_code == "NoSuchKey":
                    # File doesn't exist — that's fine
                    continue
                logger.error("S3 delete_object failed for key=%s: %s", key, e)
                return {"success": False, "error": f"Failed to delete {key} from S3."}

        logger.info(
            "Unpublished landing page for tenant=%s slug=%s by=%s",
            tenant, slug, unpublished_by,
        )

        # Invalidate CloudFront cache so page goes offline immediately
        self._invalidate_cache(slug)

        return {"success": True, "message": "Landing page is now offline."}

    # ========================================================================
    # CloudFront Cache Invalidation
    # ========================================================================

    def _invalidate_cache(self, slug: str) -> None:
        """
        Invalidate CloudFront cache for a tenant's landing page files.

        This ensures publish/unpublish changes are visible immediately
        instead of waiting for the default TTL (5 minutes) to expire.

        Args:
            slug: Tenant slug (used as S3 key prefix)
        """
        if not self.cloudfront_distribution_id:
            logger.warning("CLOUDFRONT_PUBLIC_PAGES_DISTRIBUTION_ID not set — skipping cache invalidation")
            return

        try:
            self._cloudfront.create_invalidation(
                DistributionId=self.cloudfront_distribution_id,
                InvalidationBatch={
                    "Paths": {
                        "Quantity": 2,
                        "Items": [f"/{slug}/*", f"/{slug}"],
                    },
                    "CallerReference": f"{slug}-{datetime.now(timezone.utc).isoformat()}",
                },
            )
            logger.info("CloudFront invalidation created for slug=%s", slug)
        except ClientError as e:
            # Non-fatal — page will update after TTL expires
            logger.warning("CloudFront invalidation failed for slug=%s: %s", slug, e)

    # ========================================================================
    # Branding Resolution (Task 1.15)
    # ========================================================================

    def resolve_branding(self, tenant: str) -> dict:
        """
        Resolve branding fields with fallback chain.

        Priority order:
        1. landing_page namespace (tenant-specific landing page overrides)
        2. zzp_branding namespace (ZZP module branding)
        3. str_branding namespace (STR module branding)

        Args:
            tenant: Administration identifier

        Returns:
            Dict with all branding fields resolved (empty string if not found).
        """
        fields = [
            "company_name",
            "logo_url",
            "address",
            "postal_city",
            "country",
            "phone",
            "email",
            "coc",
            "vat",
            "tagline",
            "color_primary",
            "color_accent",
        ]

        result = {}
        for field in fields:
            # Priority 1: landing_page namespace
            value = self.param_svc.get_param("landing_page", field, tenant=tenant)
            if not value:
                # Priority 2: zzp_branding namespace
                value = self.param_svc.get_param("zzp_branding", field, tenant=tenant)
            if not value:
                # Priority 3: str_branding namespace
                value = self.param_svc.get_param("str_branding", field, tenant=tenant)
            result[field] = value or ""

        return result

    # ========================================================================
    # Footer Resolution
    # ========================================================================

    def resolve_footer(self, tenant: str, branding: dict) -> dict:
        """
        Build footer object from branding fields and social links.

        Args:
            tenant: Administration identifier
            branding: Resolved branding dict

        Returns:
            Dict with footer fields including social_links.
        """
        # Get social links from ParameterService
        social_links_raw = self.param_svc.get_param(
            "landing_page", "social_links", tenant=tenant
        )
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

    # ========================================================================
    # SEO Resolution
    # ========================================================================

    def resolve_seo(self, tenant: str, slug: str, branding: dict) -> dict:
        """
        Build SEO object from ParameterService with branding fallbacks.

        Args:
            tenant: Administration identifier
            slug: Tenant slug for canonical URL
            branding: Resolved branding dict

        Returns:
            Dict with title, description, og_image, canonical_url.
        """
        title = self.param_svc.get_param("landing_page", "seo_title", tenant=tenant)
        if not title:
            title = branding.get("company_name", "")

        description = self.param_svc.get_param(
            "landing_page", "seo_description", tenant=tenant
        ) or ""

        og_image = self.param_svc.get_param(
            "landing_page", "og_image_url", tenant=tenant
        ) or ""

        canonical_url = f"{self.base_url}/p/{slug}"

        return {
            "title": title,
            "description": description,
            "og_image": og_image,
            "canonical_url": canonical_url,
        }

    # ========================================================================
    # Module Data Enrichment (Task 3.14)
    # ========================================================================

    def _enrich_sections_with_module_data(self, sections: list, tenant: str) -> None:
        """
        Enrich sections with live module data snapshots at publish time.

        Scans sections for 'services' block types.
        If found, loads live data from MySQL and injects it into the
        section's properties.items field.

        Args:
            sections: List of section dicts (mutated in place)
            tenant: Administration identifier
        """
        from services.landing_page_data_loaders import (
            load_zzp_public_services,
        )

        has_services = any(s.get("type") == "services" for s in sections)

        if not has_services:
            return

        # Use the db_manager passed to this service
        db = self.db
        if not db:
            logger.warning("No DatabaseManager available for module data enrichment")
            return

        # Load data once (shared across multiple blocks of same type)
        zzp_items = load_zzp_public_services(db, tenant)

        # Inject into sections
        for section in sections:
            section_type = section.get("type")
            if section_type == "services" and zzp_items is not None:
                if "properties" not in section:
                    section["properties"] = {}
                section["properties"]["items"] = zzp_items

    # ========================================================================
    # HTML Generation (Task 1.16)
    # ========================================================================

    def generate_index_html(self, published_data: dict, slug: str) -> str:
        """
        Generate a fully standalone static HTML page.

        This page renders the entire landing page content inline — no React,
        no external JS bundles. It is served directly from S3 via CloudFront.

        Features:
        - OG + Twitter Card meta tags for social sharing
        - All sections rendered as HTML
        - Inline CSS for styling (brand colors applied)
        - Responsive layout
        - Contact form posts to backend API

        Args:
            published_data: The full published JSON data dict
            slug: Tenant slug

        Returns:
            Complete HTML string ready to be written to S3.
        """
        seo = published_data.get("seo", {})
        branding = published_data.get("branding", {})
        footer = published_data.get("footer", {})
        sections = published_data.get("sections", [])
        settings = published_data.get("settings", {})

        title = html.escape(seo.get("title", branding.get("name", "")))
        description = html.escape(seo.get("description", ""))
        og_image = html.escape(seo.get("og_image", ""))
        canonical = html.escape(seo.get("canonical_url", f"{self.base_url}/p/{slug}"))
        site_name = html.escape(branding.get("name", ""))
        color_primary = html.escape(branding.get("color_primary", "#2D5F8A"))
        color_accent = html.escape(branding.get("color_accent", "#F4A261"))

        # Build the CloudFront base URL for images
        cf_domain = os.environ.get("CLOUDFRONT_PUBLIC_PAGES_DOMAIN", "")
        img_base = f"https://{cf_domain}" if cf_domain else ""

        # Render sections to HTML
        sections_html = self._render_sections_html(sections, img_base, color_accent, slug)

        # Render header with logo
        logo_url = branding.get("logo_url", "")
        # If logo_url is an image_key (not a full URL), build the CloudFront URL
        if logo_url and not logo_url.startswith("http"):
            logo_url = f"{img_base}/{logo_url}" if img_base else logo_url
        logo_url = html.escape(logo_url)
        tagline = html.escape(branding.get("tagline", ""))
        header_html = ""
        if logo_url or site_name:
            logo_img = f'<img src="{logo_url}" alt="{site_name}" style="max-height:60px;width:auto;margin:0 auto;">' if logo_url else ""
            tagline_html = f'<p style="color:#666;margin-top:0.5rem;font-size:1.1rem;">{tagline}</p>' if tagline else ""
            header_html = f"""<header style="padding:1.5rem;text-align:center;border-bottom:1px solid #eee;display:flex;flex-direction:column;align-items:center;">
  {logo_img}
  {tagline_html}
</header>"""

        # Render footer
        footer_html = self._render_footer_html(footer, branding)

        return f"""<!DOCTYPE html>
<html lang="nl">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{title}</title>
  <meta name="description" content="{description}" />

  <!-- Open Graph -->
  <meta property="og:type" content="website" />
  <meta property="og:title" content="{title}" />
  <meta property="og:description" content="{description}" />
  <meta property="og:image" content="{og_image}" />
  <meta property="og:url" content="{canonical}" />
  <meta property="og:site_name" content="{site_name}" />
  <meta property="og:locale" content="nl_NL" />

  <!-- Twitter/X Card -->
  <meta name="twitter:card" content="summary_large_image" />
  <meta name="twitter:title" content="{title}" />
  <meta name="twitter:description" content="{description}" />
  <meta name="twitter:image" content="{og_image}" />

  <link rel="canonical" href="{canonical}" />
  <style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #333; line-height: 1.6; }}
    img {{ max-width: 100%; height: auto; display: block; }}
    .section {{ padding: 2rem 1.5rem; }}
    .container {{ max-width: 1100px; margin: 0 auto; }}
    .hero {{ display: flex; flex-wrap: wrap; align-items: center; gap: 2rem; }}
    .hero-text {{ flex: 1; min-width: 280px; }}
    .hero-img {{ flex: 1; min-width: 280px; }}
    .hero h1 {{ font-size: 2.5rem; font-weight: 700; margin-bottom: 0.5rem; color: {color_primary}; }}
    .hero p {{ font-size: 1.2rem; color: #555; margin-bottom: 1rem; }}
    .btn {{ display: inline-block; padding: 0.75rem 1.5rem; background: {color_accent}; color: #fff; text-decoration: none; border-radius: 6px; font-weight: 600; }}
    .btn:hover {{ opacity: 0.9; }}
    .about {{ background: #f9f9f9; }}
    .about-content {{ display: flex; flex-wrap: wrap; align-items: center; gap: 2rem; }}
    .about-text {{ flex: 1; min-width: 280px; }}
    .about-text h2 {{ font-size: 1.8rem; font-weight: 700; margin-bottom: 1rem; color: {color_primary}; }}
    .about-text p {{ margin-bottom: 0.75rem; color: #555; }}
    .about-img {{ flex: 1; min-width: 280px; }}
    .about-img img {{ border-radius: 8px; }}
    .gallery {{ text-align: center; }}
    .gallery h2 {{ font-size: 1.8rem; font-weight: 700; margin-bottom: 1.5rem; color: {color_primary}; }}
    .gallery-grid-3 {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 1rem; }}
    .gallery-grid-4 {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 1rem; }}
    .gallery-masonry {{ columns: 3; column-gap: 1rem; }}
    .gallery-masonry img {{ break-inside: avoid; margin-bottom: 1rem; }}
    .gallery-grid-3 img, .gallery-grid-4 img {{ border-radius: 8px; width: 100%; height: auto; object-fit: contain; }}
    .gallery-masonry img {{ border-radius: 8px; width: 100%; height: auto; }}
    .carousel {{ position: relative; overflow: hidden; border-radius: 8px; max-width: 800px; margin: 0 auto; }}
    .carousel-track {{ display: flex; transition: transform 0.4s ease; }}
    .carousel-slide {{ min-width: 100%; }}
    .carousel-slide img {{ width: 100%; height: auto; max-height: 500px; object-fit: contain; display: block; margin: 0 auto; }}
    .carousel-btn {{ position: absolute; top: 50%; transform: translateY(-50%); background: rgba(0,0,0,0.5); color: #fff; border: none; padding: 0.8rem 1rem; font-size: 1.2rem; cursor: pointer; border-radius: 4px; z-index: 2; }}
    .carousel-btn:hover {{ background: rgba(0,0,0,0.8); }}
    .carousel-prev {{ left: 0.5rem; }}
    .carousel-next {{ right: 0.5rem; }}
    .carousel-dots {{ text-align: center; padding: 0.8rem 0; }}
    .carousel-dot {{ display: inline-block; width: 10px; height: 10px; border-radius: 50%; background: #ccc; margin: 0 4px; cursor: pointer; transition: background 0.3s; }}
    .carousel-dot.active {{ background: {color_primary}; }}
    @media (max-width: 768px) {{
      .gallery-grid-3, .gallery-grid-4 {{ grid-template-columns: repeat(2, 1fr); }}
      .gallery-masonry {{ columns: 2; }}
    }}
    @media (max-width: 480px) {{
      .gallery-grid-3, .gallery-grid-4 {{ grid-template-columns: 1fr; }}
      .gallery-masonry {{ columns: 1; }}
    }}
    .cta {{ background: {color_primary}; color: #fff; text-align: center; padding: 4rem 1.5rem; }}
    .cta h2 {{ font-size: 2rem; margin-bottom: 0.5rem; }}
    .cta p {{ font-size: 1.1rem; margin-bottom: 1.5rem; opacity: 0.9; }}
    .cta .btn {{ background: {color_accent}; }}
    .faq {{ background: #f9f9f9; }}
    .faq h2 {{ font-size: 1.8rem; font-weight: 700; margin-bottom: 1.5rem; color: {color_primary}; text-align: center; }}
    .faq-grid {{ display: grid; grid-template-columns: 1fr; gap: 0 2rem; }}
    @media (min-width: 769px) {{ .faq-grid {{ grid-template-columns: repeat(2, 1fr); }} }}
    .faq-item {{ border-bottom: 1px solid #ddd; padding: 0.4rem 0; margin: 0; display: block; }}
    .faq-item:last-child {{ border-bottom: none; padding-bottom: 0; }}
    .faq-item summary {{ font-weight: 600; cursor: pointer; font-size: 1.05rem; margin: 0; padding: 0; }}
    .faq-item p {{ margin: 0.2rem 0 0.2rem 0; padding: 0; color: #555; line-height: 1.4; }}
    .faq-item[open] summary {{ margin-bottom: 0; }}
    .testimonials {{ text-align: center; }}
    .testimonials h2 {{ font-size: 1.8rem; font-weight: 700; margin-bottom: 1.5rem; color: {color_primary}; }}
    .testimonial-cards {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 1.5rem; }}
    .testimonial-card {{ background: #f9f9f9; padding: 1.5rem; border-radius: 8px; text-align: left; }}
    .testimonial-card blockquote {{ font-style: italic; color: #555; margin-bottom: 0.75rem; }}
    .testimonial-card cite {{ font-weight: 600; color: {color_primary}; }}
    .contact {{ background: #f9f9f9; }}
    .contact h2 {{ font-size: 1.8rem; font-weight: 700; margin-bottom: 1rem; color: {color_primary}; text-align: center; }}
    .contact form {{ max-width: 500px; margin: 0 auto; }}
    .contact input, .contact textarea {{ width: 100%; padding: 0.75rem; margin-bottom: 1rem; border: 1px solid #ddd; border-radius: 6px; font-size: 1rem; }}
    .contact textarea {{ min-height: 120px; resize: vertical; }}
    .contact button {{ width: 100%; padding: 0.75rem; background: {color_accent}; color: #fff; border: none; border-radius: 6px; font-size: 1rem; font-weight: 600; cursor: pointer; }}
    .embed-block iframe {{ width: 100%; border: none; border-radius: 8px; }}
    .pricing h2 {{ font-size: 1.8rem; font-weight: 700; margin-bottom: 1.5rem; color: {color_primary}; text-align: center; }}
    .pricing-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 1.5rem; }}
    .pricing-card {{ background: #f9f9f9; padding: 1.5rem; border-radius: 8px; text-align: center; border: 1px solid #eee; }}
    .pricing-card h3 {{ color: {color_primary}; margin-bottom: 0.5rem; }}
    .pricing-card .price {{ font-size: 1.5rem; font-weight: 700; color: {color_accent}; margin-bottom: 0.5rem; }}
    footer {{ background: #222; color: #ccc; padding: 2rem 1.5rem; text-align: center; font-size: 0.9rem; }}
    footer a {{ color: {color_accent}; text-decoration: none; }}
    @media (max-width: 768px) {{
      .hero h1 {{ font-size: 1.8rem; }}
      .section {{ padding: 1.5rem 1rem; }}
    }}
  </style>
</head>
<body>
{header_html}
{sections_html}
{footer_html}
</body>
</html>"""

    def _render_sections_html(self, sections: list, img_base: str, color_accent: str, slug: str) -> str:
        """Render all sections to static HTML."""
        parts = []
        for section in sections:
            section_type = section.get("type", "")
            props = section.get("properties", {})
            layout = section.get("layout", "")
            rendered = self._render_section(section_type, props, layout, img_base, color_accent, slug)
            if rendered:
                parts.append(rendered)
        return "\n".join(parts)

    def _render_section(self, section_type: str, props: dict, layout: str, img_base: str, color_accent: str, slug: str) -> str:
        """Render a single section to HTML."""
        if section_type == "hero":
            return self._render_hero(props, layout, img_base, color_accent)
        elif section_type == "about":
            return self._render_about(props, layout, img_base)
        elif section_type == "gallery":
            return self._render_gallery(props, layout, img_base)
        elif section_type == "cta":
            return self._render_cta(props)
        elif section_type == "faq":
            return self._render_faq(props)
        elif section_type == "testimonials":
            return self._render_testimonials(props)
        elif section_type == "contact":
            return self._render_contact(props, slug)
        elif section_type == "embed":
            return self._render_embed(props)
        elif section_type == "pricing":
            return self._render_pricing(props)
        return ""

    def _img_url(self, image_key: str, img_base: str) -> str:
        """Build full image URL from key."""
        if not image_key:
            return ""
        if image_key.startswith("http"):
            return image_key
        return f"{img_base}/{image_key}" if img_base else image_key

    def _render_hero(self, props: dict, layout: str, img_base: str, color_accent: str) -> str:
        title = html.escape(props.get("title", ""))
        subtitle = html.escape(props.get("subtitle", ""))
        cta_text = html.escape(props.get("cta_text", ""))
        cta_url = html.escape(props.get("cta_url", "#"))
        image_key = props.get("image_key", "")
        img_url = self._img_url(image_key, img_base)

        img_html = f'<div class="hero-img"><img src="{img_url}" alt="{title}"></div>' if img_url else ""
        btn_html = f'<a href="{cta_url}" class="btn">{cta_text}</a>' if cta_text else ""
        sub_html = f"<p>{subtitle}</p>" if subtitle else ""

        direction = "" if layout != "image-left" else ' style="flex-direction: row-reverse;"'

        return f"""<section class="section">
  <div class="container hero"{direction}>
    <div class="hero-text">
      <h1>{title}</h1>
      {sub_html}
      {btn_html}
    </div>
    {img_html}
  </div>
</section>"""

    def _render_about(self, props: dict, layout: str, img_base: str) -> str:
        title = html.escape(props.get("title", ""))
        content = props.get("content_md", "")
        image_key = props.get("image_key", "")
        img_url = self._img_url(image_key, img_base)

        paragraphs = [html.escape(p) for p in content.split("\n") if p.strip()]
        text_html = "".join(f"<p>{p}</p>" for p in paragraphs)
        title_html = f"<h2>{title}</h2>" if title else ""
        img_html = f'<div class="about-img"><img src="{img_url}" alt="{title}"></div>' if img_url else ""

        return f"""<section class="section about">
  <div class="container about-content">
    <div class="about-text">
      {title_html}
      {text_html}
    </div>
    {img_html}
  </div>
</section>"""

    def _render_gallery(self, props: dict, layout: str, img_base: str) -> str:
        title = html.escape(props.get("title", ""))
        images = props.get("images", [])
        if not images:
            return ""

        title_html = f"<h2>{title}</h2>" if title else ""

        if layout == "carousel":
            return self._render_gallery_carousel(images, title_html, img_base)

        imgs_html = "".join(
            f'<img src="{self._img_url(img.get("image_key", ""), img_base)}" alt="{html.escape(img.get("alt", ""))}">'
            for img in images if img.get("image_key")
        )

        # Map layout to CSS class
        layout_class = "gallery-grid-3"
        if layout == "grid-4":
            layout_class = "gallery-grid-4"
        elif layout == "masonry":
            layout_class = "gallery-masonry"
        else:
            layout_class = "gallery-grid-3"

        return f"""<section class="section gallery">
  <div class="container">
    {title_html}
    <div class="{layout_class}">{imgs_html}</div>
  </div>
</section>"""

    def _render_gallery_carousel(self, images: list, title_html: str, img_base: str) -> str:
        """Render gallery as a carousel/slider with prev/next buttons."""
        imgs_html = "".join(
            f'<div class="carousel-slide"><img src="{self._img_url(img.get("image_key", ""), img_base)}" alt="{html.escape(img.get("alt", ""))}"></div>'
            for img in images if img.get("image_key")
        )
        carousel_id = f"carousel-{id(images)}"

        return f"""<section class="section gallery">
  <div class="container">
    {title_html}
    <div class="carousel" id="{carousel_id}">
      <div class="carousel-track">{imgs_html}</div>
      <button class="carousel-btn carousel-prev" onclick="carouselNav('{carousel_id}', -1)">&#10094;</button>
      <button class="carousel-btn carousel-next" onclick="carouselNav('{carousel_id}', 1)">&#10095;</button>
      <div class="carousel-dots" id="{carousel_id}-dots"></div>
    </div>
  </div>
</section>
<script>
(function() {{
  var c = document.getElementById('{carousel_id}');
  var track = c.querySelector('.carousel-track');
  var slides = track.querySelectorAll('.carousel-slide');
  var dots = c.querySelector('.carousel-dots');
  for (var i = 0; i < slides.length; i++) {{
    var dot = document.createElement('span');
    dot.className = 'carousel-dot' + (i === 0 ? ' active' : '');
    dot.setAttribute('data-index', i);
    dot.onclick = function() {{ goToSlide('{carousel_id}', parseInt(this.getAttribute('data-index'))); }};
    dots.appendChild(dot);
  }}
}})();
function carouselNav(id, dir) {{
  var c = document.getElementById(id);
  var track = c.querySelector('.carousel-track');
  var slides = track.querySelectorAll('.carousel-slide');
  var current = parseInt(track.getAttribute('data-index') || '0');
  var next = (current + dir + slides.length) % slides.length;
  goToSlide(id, next);
}}
function goToSlide(id, index) {{
  var c = document.getElementById(id);
  var track = c.querySelector('.carousel-track');
  var slides = track.querySelectorAll('.carousel-slide');
  track.setAttribute('data-index', index);
  track.style.transform = 'translateX(-' + (index * 100) + '%)';
  var dots = c.querySelectorAll('.carousel-dot');
  for (var i = 0; i < dots.length; i++) {{
    dots[i].className = 'carousel-dot' + (i === index ? ' active' : '');
  }}
}}
</script>"""

    def _render_cta(self, props: dict) -> str:
        title = html.escape(props.get("title", ""))
        subtitle = html.escape(props.get("subtitle", ""))
        btn_text = html.escape(props.get("button_text", ""))
        btn_url = html.escape(props.get("button_url", "#"))

        sub_html = f"<p>{subtitle}</p>" if subtitle else ""
        btn_html = f'<a href="{btn_url}" class="btn">{btn_text}</a>' if btn_text else ""

        return f"""<section class="cta">
  <div class="container">
    <h2>{title}</h2>
    {sub_html}
    {btn_html}
  </div>
</section>"""

    def _render_faq(self, props: dict) -> str:
        title = html.escape(props.get("title", ""))
        items = props.get("items", [])
        if not items:
            return ""

        items_html = "".join(
            f'<details class="faq-item"><summary>{html.escape(item.get("question", "").strip())}</summary><p>{html.escape(item.get("answer", "").strip())}</p></details>'
            for item in items
        )
        title_html = f"<h2>{title}</h2>" if title else ""

        return f"""<section class="section faq">
  <div class="container">
    {title_html}
    <div class="faq-grid">{items_html}</div>
  </div>
</section>"""

    def _render_testimonials(self, props: dict) -> str:
        title = html.escape(props.get("title", ""))
        items = props.get("items", [])
        if not items:
            return ""

        cards_html = "".join(
            f'<div class="testimonial-card"><blockquote>"{html.escape(item.get("quote", ""))}"</blockquote><cite>— {html.escape(item.get("author", ""))}{", " + html.escape(item.get("role", "")) if item.get("role") else ""}</cite></div>'
            for item in items
        )
        title_html = f"<h2>{title}</h2>" if title else ""

        return f"""<section class="section testimonials">
  <div class="container">
    {title_html}
    <div class="testimonial-cards">{cards_html}</div>
  </div>
</section>"""

    def _render_contact(self, props: dict, slug: str) -> str:
        title = html.escape(props.get("title", ""))
        subtitle = html.escape(props.get("subtitle", ""))
        title_html = f"<h2>{title}</h2>" if title else "<h2>Contact</h2>"
        sub_html = f"<p style=\"text-align:center;color:#555;margin-bottom:1.5rem;\">{subtitle}</p>" if subtitle else ""
        api_base = html.escape(self.base_url)

        safe_slug = html.escape(slug)
        # Contact form needs the backend API URL (not the CloudFront URL)
        backend_url = html.escape(os.environ.get("CONTACT_FORM_API_URL", self.base_url).rstrip("/"))
        api_url = f"{backend_url}/api/public/landing/{safe_slug}/contact"

        return f"""<section class="section contact">
  <div class="container">
    {title_html}
    {sub_html}
    <form id="contact-form" onsubmit="return submitContact(event)">
      <input type="text" name="name" placeholder="Naam" required>
      <input type="email" name="email" placeholder="E-mail" required>
      <textarea name="message" placeholder="Bericht" required></textarea>
      <input type="text" name="website" style="display:none" tabindex="-1">
      <button type="submit">Verstuur</button>
      <p id="form-status" style="margin-top:1rem;text-align:center;"></p>
    </form>
  </div>
</section>
<script>
function submitContact(e) {{
  e.preventDefault();
  var f = e.target;
  var data = {{name: f.name.value, email: f.email.value, message: f.message.value, honeypot: f.website.value}};
  document.getElementById('form-status').textContent = 'Verzenden...';
  fetch('{api_url}', {{
    method: 'POST', headers: {{'Content-Type': 'application/json'}}, body: JSON.stringify(data)
  }}).then(function(r){{ return r.json(); }}).then(function(d){{
    document.getElementById('form-status').textContent = d.success ? 'Bedankt! Bericht verzonden.' : (d.error || 'Er ging iets mis.');
    if(d.success) f.reset();
  }}).catch(function(){{ document.getElementById('form-status').textContent = 'Er ging iets mis.'; }});
  return false;
}}
</script>"""

    def _render_embed(self, props: dict) -> str:
        url = props.get("url", "")
        height = props.get("height", "500px")
        title = html.escape(props.get("title", ""))
        if not url or not url.startswith("https://"):
            return ""

        return f"""<section class="section embed-block">
  <div class="container">
    <iframe src="{html.escape(url)}" height="{html.escape(height)}" title="{title}" sandbox="allow-scripts allow-same-origin" loading="lazy"></iframe>
  </div>
</section>"""

    def _render_pricing(self, props: dict) -> str:
        title = html.escape(props.get("title", ""))
        items = props.get("items", [])
        if not items:
            return ""

        cards_html = ""
        for item in items:
            name = html.escape(item.get("name", ""))
            price = html.escape(item.get("price", ""))
            desc = html.escape(item.get("description", ""))
            features = item.get("features", [])
            features_html = ""
            if features:
                features_li = "".join(f"<li>{html.escape(f)}</li>" for f in features if f)
                features_html = f"<ul class=\"pricing-features\">{features_li}</ul>"
            cards_html += f'<div class="pricing-card"><h3>{name}</h3><div class="price">{price}</div><p>{desc}</p>{features_html}</div>'
        title_html = f"<h2>{title}</h2>" if title else ""

        return f"""<section class="section pricing">
  <div class="container">
    {title_html}
    <div class="pricing-grid">{cards_html}</div>
  </div>
</section>"""

    def _render_footer_html(self, footer: dict, branding: dict) -> str:
        """Render the page footer with company info and social links."""
        company = html.escape(footer.get("company_name", branding.get("name", "")))
        address = html.escape(footer.get("address", ""))
        postal_city = html.escape(footer.get("postal_city", ""))
        phone = html.escape(footer.get("phone", ""))
        email = html.escape(footer.get("email", ""))

        info_parts = [p for p in [company, address, postal_city] if p]
        info_line = " · ".join(info_parts)
        contact_line = " · ".join([p for p in [phone, email] if p])

        social_links = footer.get("social_links", {})
        social_html = ""
        if social_links:
            links = []
            for platform, url in social_links.items():
                if url:
                    links.append(f'<a href="{html.escape(url)}" target="_blank" rel="noopener noreferrer">{html.escape(platform.replace("_", " ").title())}</a>')
            if links:
                social_html = f'<p style="margin-top:0.5rem;">{"  ·  ".join(links)}</p>'

        return f"""<footer>
  <p>{info_line}</p>
  {"<p>" + contact_line + "</p>" if contact_line else ""}
  {social_html}
</footer>"""
