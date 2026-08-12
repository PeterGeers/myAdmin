"""
Unit Tests for Landing Page Styles

Tests CSS generation, WCAG contrast utilities, and security sanitization
for the landing page publish pipeline.
"""

import os
import sys

import pytest

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from services.landing_page_styles import LandingPageStyles


class TestBuildSectionStyle:
    """Tests for build_section_style."""

    def test_empty_settings_returns_empty(self):
        """Empty or None settings returns empty string."""
        assert LandingPageStyles.build_section_style({}, "https://cdn.example.com") == ""
        assert LandingPageStyles.build_section_style(None, "https://cdn.example.com") == ""

    def test_background_color(self):
        """Color background type generates background-color."""
        settings = {"background_type": "color", "background_color": "#ff0000"}
        result = LandingPageStyles.build_section_style(settings, "")
        assert "background-color: #ff0000" in result

    def test_background_color_transparent_skipped(self):
        """Transparent color does not generate background-color."""
        settings = {"background_type": "color", "background_color": "transparent"}
        result = LandingPageStyles.build_section_style(settings, "")
        assert "background-color" not in result

    def test_background_gradient(self):
        """Gradient background type generates background property."""
        settings = {
            "background_type": "gradient",
            "background_gradient": "linear-gradient(135deg, #667eea 0%, #764ba2 100%)",
        }
        result = LandingPageStyles.build_section_style(settings, "")
        assert "background: linear-gradient(135deg, #667eea 0%, #764ba2 100%)" in result

    def test_background_image_relative_key(self):
        """Image background with relative key uses img_base."""
        settings = {
            "background_type": "image",
            "background_image_key": "uploads/bg.jpg",
        }
        result = LandingPageStyles.build_section_style(settings, "https://cdn.example.com")
        assert "background-image: url('https://cdn.example.com/uploads/bg.jpg')" in result
        assert "background-size: cover" in result
        assert "background-position: center" in result

    def test_background_image_absolute_url(self):
        """Image background with absolute URL uses it directly."""
        settings = {
            "background_type": "image",
            "background_image_key": "https://other.com/bg.png",
        }
        result = LandingPageStyles.build_section_style(settings, "https://cdn.example.com")
        assert "url('https://other.com/bg.png')" in result

    def test_padding_compact(self):
        """Compact padding produces correct value."""
        settings = {"padding": "compact"}
        result = LandingPageStyles.build_section_style(settings, "")
        assert "padding: 1rem 1.5rem" in result

    def test_padding_spacious(self):
        """Spacious padding produces correct value."""
        settings = {"padding": "spacious"}
        result = LandingPageStyles.build_section_style(settings, "")
        assert "padding: 4rem 1.5rem" in result

    def test_padding_default_normal(self):
        """Default (no padding key) falls back to normal."""
        settings = {"background_type": "color", "background_color": "#fff"}
        result = LandingPageStyles.build_section_style(settings, "")
        assert "padding: 2rem 1.5rem" in result

    def test_text_color_light(self):
        """Light text_color produces color: #fff."""
        settings = {"text_color": "light", "background_type": "gradient"}
        result = LandingPageStyles.build_section_style(settings, "")
        assert "color: #fff" in result

    def test_text_color_auto_dark_bg(self):
        """Auto text_color on dark background resolves to light text."""
        settings = {
            "background_type": "color",
            "background_color": "#000000",
            "text_color": "auto",
        }
        result = LandingPageStyles.build_section_style(settings, "")
        assert "color: #fff" in result

    def test_text_color_auto_light_bg(self):
        """Auto text_color on light background resolves to dark text."""
        settings = {
            "background_type": "color",
            "background_color": "#ffffff",
            "text_color": "auto",
        }
        result = LandingPageStyles.build_section_style(settings, "")
        assert "color: #333" in result

    def test_border_radius_md(self):
        """Border radius md produces 16px."""
        settings = {"border_radius": "md"}
        result = LandingPageStyles.build_section_style(settings, "")
        assert "border-radius: 16px" in result

    def test_border_radius_none_omitted(self):
        """Border radius 'none' does not add border-radius property."""
        settings = {"border_radius": "none"}
        result = LandingPageStyles.build_section_style(settings, "")
        assert "border-radius" not in result


class TestAutoTextColor:
    """Tests for auto_text_color WCAG luminance utility."""

    def test_black_background_needs_light_text(self):
        """Black background (#000000) needs light text."""
        assert LandingPageStyles.auto_text_color("#000000") == "light"

    def test_white_background_needs_dark_text(self):
        """White background (#ffffff) needs dark text."""
        assert LandingPageStyles.auto_text_color("#ffffff") == "dark"

    def test_dark_blue_needs_light_text(self):
        """Dark blue (#1a1a2e) needs light text."""
        assert LandingPageStyles.auto_text_color("#1a1a2e") == "light"

    def test_light_yellow_needs_dark_text(self):
        """Light yellow (#ffecd2) needs dark text."""
        assert LandingPageStyles.auto_text_color("#ffecd2") == "dark"

    def test_medium_gray_boundary(self):
        """Medium gray returns a valid result (dark or light)."""
        result = LandingPageStyles.auto_text_color("#808080")
        assert result in ("dark", "light")

    def test_invalid_hex_returns_dark(self):
        """Invalid hex returns safe fallback 'dark'."""
        assert LandingPageStyles.auto_text_color("not-a-color") == "dark"
        assert LandingPageStyles.auto_text_color("") == "dark"
        assert LandingPageStyles.auto_text_color("#fff") == "dark"  # too short

    def test_none_returns_dark(self):
        """None input returns safe fallback 'dark'."""
        assert LandingPageStyles.auto_text_color(None) == "dark"


class TestAutoContrastWcagAA:
    """Task 28: Test auto-contrast — verify WCAG AA compliance when text_color: auto.

    WCAG AA requires a contrast ratio of at least 4.5:1 for normal text.
    The auto_text_color function chooses 'dark' (#333) or 'light' (#fff) based on
    the background luminance. We verify these choices produce sufficient contrast.
    """

    @staticmethod
    def _relative_luminance(hex_color: str) -> float:
        """Calculate W3C relative luminance from hex colour."""
        r = int(hex_color[1:3], 16)
        g = int(hex_color[3:5], 16)
        b = int(hex_color[5:7], 16)

        def linearize(c: int) -> float:
            s = c / 255.0
            return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4

        return 0.2126 * linearize(r) + 0.7152 * linearize(g) + 0.0722 * linearize(b)

    @staticmethod
    def _contrast_ratio(lum1: float, lum2: float) -> float:
        """Calculate WCAG contrast ratio between two luminance values."""
        lighter = max(lum1, lum2)
        darker = min(lum1, lum2)
        return (lighter + 0.05) / (darker + 0.05)

    def _check_wcag_aa(self, bg_hex: str):
        """Verify auto_text_color choice meets WCAG AA 4.5:1 contrast ratio."""
        choice = LandingPageStyles.auto_text_color(bg_hex)
        text_hex = "#ffffff" if choice == "light" else "#333333"

        bg_lum = self._relative_luminance(bg_hex)
        text_lum = self._relative_luminance(text_hex)
        ratio = self._contrast_ratio(bg_lum, text_lum)

        assert ratio >= 4.5, (
            f"WCAG AA violation: bg={bg_hex}, text={text_hex} (choice={choice}), "
            f"contrast ratio={ratio:.2f} (need ≥4.5:1)"
        )

    def test_pure_white_returns_dark(self):
        """Pure white (#ffffff) → dark text for readability."""
        assert LandingPageStyles.auto_text_color("#ffffff") == "dark"

    def test_pure_black_returns_light(self):
        """Pure black (#000000) → light text for readability."""
        assert LandingPageStyles.auto_text_color("#000000") == "light"

    def test_white_bg_meets_wcag_aa(self):
        """White background with dark text meets WCAG AA 4.5:1."""
        self._check_wcag_aa("#ffffff")

    def test_black_bg_meets_wcag_aa(self):
        """Black background with light text meets WCAG AA 4.5:1."""
        self._check_wcag_aa("#000000")

    def test_dark_navy_meets_wcag_aa(self):
        """Dark navy (#1a1a2e) with light text meets WCAG AA."""
        self._check_wcag_aa("#1a1a2e")

    def test_light_peach_meets_wcag_aa(self):
        """Light peach (#ffecd2) with dark text meets WCAG AA."""
        self._check_wcag_aa("#ffecd2")

    def test_yellow_background_meets_wcag_aa(self):
        """Yellow (#ffff00) background — a notoriously tricky colour — meets WCAG AA."""
        self._check_wcag_aa("#ffff00")

    def test_red_background_meets_wcag_aa(self):
        """Red (#cc0000) background meets WCAG AA."""
        self._check_wcag_aa("#cc0000")

    def test_bright_green_meets_wcag_aa(self):
        """Bright green (#00cc00) background meets WCAG AA."""
        self._check_wcag_aa("#00cc00")

    def test_deep_purple_meets_wcag_aa(self):
        """Deep purple (#4a0080) background meets WCAG AA."""
        self._check_wcag_aa("#4a0080")

    def test_common_brand_colours_meet_wcag_aa(self):
        """Common brand colours used in themes produce WCAG-compliant contrast.

        Note: Some mid-luminance colours (#e94560) fall in the 'impossible zone'
        where neither dark nor light text achieves 4.5:1. These are excluded as
        they are accent colours unlikely to be used as full section backgrounds.
        """
        brand_colours = [
            "#2D5F8A",  # professional primary (dark enough for light text)
            "#8B4513",  # warm primary (dark brown)
            "#2d6a4f",  # nature primary (dark green)
            "#1c1c1c",  # luxury primary (near-black)
            "#ffffff",  # minimal section bg (white)
            "#FFF8F0",  # warm section bg (light cream)
            "#f0f7f4",  # nature section bg (light green)
        ]
        for colour in brand_colours:
            self._check_wcag_aa(colour)

    def test_auto_in_build_section_style_injects_correct_colour(self):
        """When text_color=auto in build_section_style, the resolved colour is injected."""
        # Dark background → should get light text (#fff)
        settings_dark = {
            "background_type": "color",
            "background_color": "#000000",
            "text_color": "auto",
        }
        style_dark = LandingPageStyles.build_section_style(settings_dark, "")
        assert "color: #fff" in style_dark

        # Light background → should get dark text (#333)
        settings_light = {
            "background_type": "color",
            "background_color": "#ffffff",
            "text_color": "auto",
        }
        style_light = LandingPageStyles.build_section_style(settings_light, "")
        assert "color: #333" in style_light

    def test_auto_with_gradient_defaults_to_dark(self):
        """Auto text_color with gradient background defaults to dark (safe fallback)."""
        settings = {
            "background_type": "gradient",
            "background_gradient": "linear-gradient(135deg, #667eea, #764ba2)",
            "text_color": "auto",
        }
        style = LandingPageStyles.build_section_style(settings, "")
        assert "color: #333" in style

    def test_auto_with_image_defaults_to_dark(self):
        """Auto text_color with image background defaults to dark (safe fallback)."""
        settings = {
            "background_type": "image",
            "background_image_key": "uploads/bg.jpg",
            "text_color": "auto",
        }
        style = LandingPageStyles.build_section_style(settings, "https://cdn.test.com")
        assert "color: #333" in style


class TestBuildFontLinks:
    """Tests for build_font_links."""

    def test_system_fonts_return_empty(self):
        """System fonts produce no Google Font links."""
        branding = {"font_heading": "system", "font_body": "system"}
        assert LandingPageStyles.build_font_links(branding) == ""

    def test_custom_font_produces_link(self):
        """Custom font name produces Google Fonts link."""
        branding = {"font_heading": "Inter", "font_body": "system"}
        result = LandingPageStyles.build_font_links(branding)
        assert "fonts.googleapis.com" in result
        assert "Inter" in result
        assert "preconnect" in result

    def test_two_different_fonts(self):
        """Two different custom fonts both appear in link."""
        branding = {"font_heading": "Playfair Display", "font_body": "Lato"}
        result = LandingPageStyles.build_font_links(branding)
        assert "Playfair+Display" in result
        assert "Lato" in result

    def test_same_font_deduped(self):
        """Same font for heading and body appears only once."""
        branding = {"font_heading": "Poppins", "font_body": "Poppins"}
        result = LandingPageStyles.build_font_links(branding)
        assert result.count("Poppins") == 1

    def test_empty_font_treated_as_system(self):
        """Empty string font is treated as system (no link)."""
        branding = {"font_heading": "", "font_body": ""}
        assert LandingPageStyles.build_font_links(branding) == ""


class TestBuildCssVariables:
    """Tests for build_css_variables."""

    def test_produces_root_block(self):
        """Output contains :root { ... } block."""
        branding = {"font_heading": "Inter", "font_body": "Inter"}
        result = LandingPageStyles.build_css_variables(branding)
        assert result.startswith(":root {")
        assert result.endswith("}")

    def test_custom_font_family(self):
        """Custom font produces quoted font-family."""
        branding = {"font_heading": "Playfair Display", "font_body": "Lato"}
        result = LandingPageStyles.build_css_variables(branding)
        assert '"Playfair Display", sans-serif' in result
        assert '"Lato", sans-serif' in result

    def test_system_font_family(self):
        """System font produces system font stack."""
        branding = {"font_heading": "system", "font_body": "system"}
        result = LandingPageStyles.build_css_variables(branding)
        assert "-apple-system" in result
        assert "BlinkMacSystemFont" in result

    def test_spacing_compact(self):
        """Compact spacing produces correct variables."""
        branding = {"font_heading": "system", "font_body": "system", "base_spacing": "compact"}
        result = LandingPageStyles.build_css_variables(branding)
        assert "--spacing-section: 1.5rem" in result
        assert "--spacing-element: 0.75rem" in result

    def test_spacing_relaxed(self):
        """Relaxed spacing produces correct variables."""
        branding = {"font_heading": "system", "font_body": "system", "base_spacing": "relaxed"}
        result = LandingPageStyles.build_css_variables(branding)
        assert "--spacing-section: 3rem" in result
        assert "--spacing-element: 1.5rem" in result

    def test_radius_sharp(self):
        """Sharp border radius produces zero values."""
        branding = {"font_heading": "system", "font_body": "system", "border_radius_global": "sharp"}
        result = LandingPageStyles.build_css_variables(branding)
        assert "--radius-sm: 0" in result
        assert "--radius-md: 0" in result

    def test_radius_pill(self):
        """Pill border radius produces large values."""
        branding = {"font_heading": "system", "font_body": "system", "border_radius_global": "pill"}
        result = LandingPageStyles.build_css_variables(branding)
        assert "--radius-lg: 9999px" in result

    def test_shadow_dramatic(self):
        """Dramatic shadow style produces heavy shadow values."""
        branding = {"font_heading": "system", "font_body": "system", "shadow_style": "dramatic"}
        result = LandingPageStyles.build_css_variables(branding)
        assert "--shadow-card:" in result
        assert "0 8px 24px" in result

    def test_shadow_none(self):
        """None shadow style produces 'none' values."""
        branding = {"font_heading": "system", "font_body": "system", "shadow_style": "none"}
        result = LandingPageStyles.build_css_variables(branding)
        assert "--shadow-card: none" in result
        assert "--shadow-hover: none" in result


class TestSanitizeGradient:
    """Tests for sanitize_gradient security sanitization."""

    def test_valid_gradient_unchanged(self):
        """Valid CSS gradient passes through unchanged."""
        gradient = "linear-gradient(135deg, #667eea 0%, #764ba2 100%)"
        assert LandingPageStyles.sanitize_gradient(gradient) == gradient

    def test_strips_url(self):
        """Removes url() from gradient string."""
        gradient = "linear-gradient(135deg, red, url(https://evil.com/bg.jpg))"
        result = LandingPageStyles.sanitize_gradient(gradient)
        assert "url(" not in result.lower()

    def test_strips_expression(self):
        """Removes expression() from gradient string."""
        gradient = "expression(alert('xss'))"
        result = LandingPageStyles.sanitize_gradient(gradient)
        assert "expression(" not in result.lower()

    def test_strips_javascript(self):
        """Removes javascript: from gradient string."""
        gradient = "linear-gradient(135deg, javascript:alert(1), red)"
        result = LandingPageStyles.sanitize_gradient(gradient)
        assert "javascript:" not in result.lower()

    def test_empty_returns_empty(self):
        """Empty input returns empty string."""
        assert LandingPageStyles.sanitize_gradient("") == ""
        assert LandingPageStyles.sanitize_gradient(None) == ""

    def test_case_insensitive_stripping(self):
        """Stripping is case-insensitive."""
        gradient = "URL(evil.com) Expression(bad) JAVASCRIPT:x"
        result = LandingPageStyles.sanitize_gradient(gradient)
        assert "url(" not in result.lower()
        assert "expression(" not in result.lower()
        assert "javascript:" not in result.lower()
