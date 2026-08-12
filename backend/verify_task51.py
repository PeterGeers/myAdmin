"""Verify Task 51: CSS variables in build_page_css and generate_index_html."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
os.environ.setdefault("AWS_DEFAULT_REGION", "eu-west-1")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("LANDING_PAGES_BUCKET", "test-bucket")
os.environ.setdefault("LANDING_PAGE_BASE_URL", "https://test.app")

from unittest.mock import Mock
from services.landing_page_styles import LandingPageStyles
from services.landing_page_publish_service import LandingPagePublishService

# 1. Verify build_page_css uses var() references
css = LandingPageStyles.build_page_css("#2D5F8A", "#F4A261")
assert "var(--font-body)" in css, "Missing var(--font-body)"
assert "var(--font-heading)" in css, "Missing var(--font-heading)"
assert "var(--spacing-section)" in css, "Missing var(--spacing-section)"
assert "var(--radius-md)" in css, "Missing var(--radius-md)"
assert "var(--shadow-card)" in css, "Missing var(--shadow-card)"
assert "-apple-system" not in css, "Still has hardcoded font-family"
assert "border-radius: 8px" not in css, "Still has hardcoded 8px radius"
print("OK: build_page_css uses CSS variables correctly")

# 2. Verify generate_index_html injects CSS variables
svc = LandingPagePublishService(Mock(), Mock(), Mock())
published_data = {
    "seo": {"title": "Test", "description": "", "og_image": "", "canonical_url": "https://test.app/p/s"},
    "branding": {
        "name": "Test", "tagline": "", "logo_url": "",
        "color_primary": "#2D5F8A", "color_accent": "#F4A261",
        "font_heading": "Inter", "font_body": "Nunito",
        "base_spacing": "normal", "border_radius_global": "rounded",
        "shadow_style": "subtle",
    },
    "footer": {},
    "sections": [],
}
html = svc.generate_index_html(published_data, "test-slug")
assert ":root {" in html, "Missing :root block in HTML"
assert "--font-heading:" in html, "Missing --font-heading variable"
assert "--font-body:" in html, "Missing --font-body variable"
assert "--spacing-section:" in html, "Missing --spacing-section variable"
assert "--radius-md:" in html, "Missing --radius-md variable"
assert "--shadow-card:" in html, "Missing --shadow-card variable"
assert "var(--font-body)" in html, "Missing var(--font-body) usage in HTML"
assert "var(--radius-md)" in html, "Missing var(--radius-md) usage in HTML"
print("OK: generate_index_html injects CSS variables + uses var() references")

print("\nAll Task 51 verifications passed!")
