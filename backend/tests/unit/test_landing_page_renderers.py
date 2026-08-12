"""
Unit Tests for Landing Page Renderers

Tests HTML rendering for all section types in the landing page publish pipeline.
"""

import os
import sys
from unittest.mock import patch

import pytest

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from services.landing_page_renderers import LandingPageRenderers


@pytest.fixture
def renderer():
    """Create a LandingPageRenderers instance with test defaults."""
    return LandingPageRenderers(
        img_base="https://cdn.example.com/images",
        color_accent="#F4A261",
        color_primary="#2D5F8A",
    )


class TestImgUrl:
    """Tests for _img_url helper."""

    def test_empty_key_returns_empty(self, renderer):
        """Empty image key returns empty string."""
        assert renderer._img_url("") == ""

    def test_relative_key_prepends_base(self, renderer):
        """Relative key gets img_base prepended."""
        result = renderer._img_url("uploads/hero.jpg")
        assert result == "https://cdn.example.com/images/uploads/hero.jpg"

    def test_absolute_url_returned_as_is(self, renderer):
        """HTTP(S) URLs are returned unchanged."""
        url = "https://other-cdn.com/photo.png"
        assert renderer._img_url(url) == url

    def test_http_url_returned_as_is(self, renderer):
        """http:// URLs are also returned unchanged."""
        url = "http://legacy.com/img.jpg"
        assert renderer._img_url(url) == url

    def test_relative_key_without_base(self):
        """Relative key with empty img_base returns key only."""
        r = LandingPageRenderers(img_base="", color_accent="#fff", color_primary="#000")
        assert r._img_url("some/image.png") == "some/image.png"


class TestRenderHero:
    """Tests for render_hero section."""

    def test_basic_hero_structure(self, renderer):
        """Hero contains h1, subtitle, and CTA button."""
        props = {
            "title": "Welcome",
            "subtitle": "Start here",
            "cta_text": "Sign Up",
            "cta_url": "/register",
            "image_key": "hero.jpg",
        }
        html = renderer.render_hero(props, "default")

        assert '<h1>Welcome</h1>' in html
        assert '<p>Start here</p>' in html
        assert 'href="/register"' in html
        assert 'Sign Up' in html
        assert 'hero.jpg' in html
        assert 'class="section"' in html

    def test_hero_image_left_layout(self, renderer):
        """image-left layout adds flex-direction: row-reverse."""
        props = {"title": "Test", "image_key": "img.jpg"}
        html = renderer.render_hero(props, "image-left")
        assert "row-reverse" in html

    def test_hero_default_layout_no_reverse(self, renderer):
        """Default layout does not add row-reverse."""
        props = {"title": "Test", "image_key": "img.jpg"}
        html = renderer.render_hero(props, "default")
        assert "row-reverse" not in html

    def test_hero_no_image(self, renderer):
        """Hero without image_key omits img div."""
        props = {"title": "No Image"}
        html = renderer.render_hero(props, "default")
        assert "hero-img" not in html

    def test_hero_no_cta(self, renderer):
        """Hero without cta_text omits button."""
        props = {"title": "Title Only"}
        html = renderer.render_hero(props, "default")
        assert 'class="btn"' not in html

    def test_hero_escapes_html(self, renderer):
        """Hero HTML-escapes user content."""
        props = {"title": "<script>alert('xss')</script>"}
        html = renderer.render_hero(props, "default")
        assert "<script>" not in html
        assert "&lt;script&gt;" in html

    def test_hero_image_bg_layout(self, renderer):
        """image-bg layout renders full-bleed background image with overlay."""
        props = {
            "title": "Welcome",
            "subtitle": "Start here",
            "cta_text": "Sign Up",
            "cta_url": "/register",
            "image_key": "hero-bg.jpg",
        }
        result = renderer.render_hero(props, "image-bg")

        assert 'hero-image-bg' in result
        assert "background-image:url('https://cdn.example.com/images/hero-bg.jpg')" in result
        assert 'background-size:cover' in result
        assert 'background-position:center' in result
        assert 'min-height:500px' in result
        assert 'hero-overlay' in result
        assert 'color:#fff;' in result
        assert '<h1' in result and 'Welcome' in result
        assert 'color:#eee;' in result
        assert 'Sign Up' in result

    def test_hero_split_diagonal_layout(self, renderer):
        """split-diagonal layout renders clip-path split between text and image."""
        props = {
            "title": "Diagonal",
            "subtitle": "Stylish",
            "cta_text": "Learn More",
            "cta_url": "/about",
            "image_key": "split.jpg",
        }
        result = renderer.render_hero(props, "split-diagonal")

        assert 'hero-split' in result
        assert 'clip-path:polygon(15% 0, 100% 0, 100% 100%, 0% 100%)' in result
        assert "background-image:url('https://cdn.example.com/images/split.jpg')" in result
        assert 'min-height:500px' in result
        assert '<h1>Diagonal</h1>' in result
        assert '<p>Stylish</p>' in result
        assert 'Learn More' in result

    def test_hero_video_bg_layout(self, renderer):
        """video-bg layout renders YouTube embed with autoplay, muted, looped."""
        props = {
            "title": "Video Hero",
            "subtitle": "Watch now",
            "cta_text": "Subscribe",
            "cta_url": "/subscribe",
            "video_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        }
        result = renderer.render_hero(props, "video-bg")

        assert 'hero-video-bg' in result
        assert 'youtube.com/embed/dQw4w9WgXcQ' in result
        assert 'autoplay=1' in result
        assert 'mute=1' in result
        assert 'loop=1' in result
        assert 'playlist=dQw4w9WgXcQ' in result
        assert 'controls=0' in result
        assert 'hero-overlay' in result
        assert 'color:#fff;' in result
        assert '<h1' in result and 'Video Hero' in result

    def test_hero_video_bg_short_url(self, renderer):
        """video-bg layout handles youtu.be short URLs."""
        props = {
            "title": "Short URL",
            "video_url": "https://youtu.be/abc123_XY",
        }
        result = renderer.render_hero(props, "video-bg")

        assert 'youtube.com/embed/abc123_XY' in result
        assert 'playlist=abc123_XY' in result

    def test_hero_video_bg_no_url(self, renderer):
        """video-bg layout without video_url renders section but no iframe."""
        props = {"title": "No Video"}
        result = renderer.render_hero(props, "video-bg")

        assert 'hero-video-bg' in result
        assert '<h1' in result and 'No Video' in result
        assert 'iframe' not in result

    def test_hero_video_bg_invalid_url(self, renderer):
        """video-bg layout with non-YouTube URL renders section but no iframe."""
        props = {
            "title": "Invalid",
            "video_url": "https://vimeo.com/12345",
        }
        result = renderer.render_hero(props, "video-bg")

        assert 'hero-video-bg' in result
        assert 'iframe' not in result


class TestExtractYoutubeId:
    """Tests for _extract_youtube_id helper."""

    def test_standard_youtube_url(self, renderer):
        """Extracts ID from standard youtube.com/watch?v= URL."""
        assert renderer._extract_youtube_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_short_youtu_be_url(self, renderer):
        """Extracts ID from short youtu.be URL."""
        assert renderer._extract_youtube_id("https://youtu.be/abc123_XY") == "abc123_XY"

    def test_youtube_without_www(self, renderer):
        """Extracts ID from youtube.com without www."""
        assert renderer._extract_youtube_id("https://youtube.com/watch?v=test-ID_1") == "test-ID_1"

    def test_empty_url_returns_empty(self, renderer):
        """Empty URL returns empty string."""
        assert renderer._extract_youtube_id("") == ""

    def test_non_youtube_url_returns_empty(self, renderer):
        """Non-YouTube URL returns empty string."""
        assert renderer._extract_youtube_id("https://vimeo.com/12345") == ""

    def test_none_url_returns_empty(self, renderer):
        """None-like empty value returns empty string."""
        assert renderer._extract_youtube_id("") == ""


class TestRenderAbout:
    """Tests for render_about section."""

    def test_about_with_image(self, renderer):
        """About section includes image when image_key provided."""
        props = {
            "title": "About Us",
            "content_md": "Line one\nLine two",
            "image_key": "about.jpg",
        }
        html = renderer.render_about(props, "default")

        assert '<h2>About Us</h2>' in html
        assert '<p>Line one</p>' in html
        assert '<p>Line two</p>' in html
        assert 'about-img' in html
        assert 'about.jpg' in html

    def test_about_without_image(self, renderer):
        """About section omits image div when no image_key."""
        props = {"title": "About", "content_md": "Some text"}
        html = renderer.render_about(props, "default")

        assert 'about-img' not in html
        assert '<p>Some text</p>' in html

    def test_about_empty_lines_skipped(self, renderer):
        """Empty lines in content_md are not rendered as paragraphs."""
        props = {"title": "", "content_md": "First\n\nSecond"}
        html = renderer.render_about(props, "default")

        assert '<p>First</p>' in html
        assert '<p>Second</p>' in html
        # Should not have empty <p></p>
        assert '<p></p>' not in html

    def test_about_no_title(self, renderer):
        """About without title omits h2."""
        props = {"title": "", "content_md": "Text"}
        html = renderer.render_about(props, "default")
        assert '<h2>' not in html

    def test_about_image_left_layout(self, renderer):
        """image-left layout puts image before text in HTML output."""
        props = {
            "title": "About Us",
            "content_md": "Hello world",
            "image_key": "about.jpg",
        }
        html = renderer.render_about(props, "image-left")

        # Image should appear before text in the output
        img_pos = html.index('about-img')
        text_pos = html.index('about-text')
        assert img_pos < text_pos, "image-left layout should render image before text"

    def test_about_default_layout_text_before_image(self, renderer):
        """Default layout puts text before image in HTML output."""
        props = {
            "title": "About Us",
            "content_md": "Hello world",
            "image_key": "about.jpg",
        }
        html = renderer.render_about(props, "default")

        # Text should appear before image in the output
        img_pos = html.index('about-img')
        text_pos = html.index('about-text')
        assert text_pos < img_pos, "default layout should render text before image"

    def test_about_image_left_without_image_no_crash(self, renderer):
        """image-left layout without image falls back to default order."""
        props = {"title": "About", "content_md": "Text"}
        html = renderer.render_about(props, "image-left")

        assert 'about-text' in html
        assert 'about-img' not in html

    def test_about_card_layout_structure(self, renderer):
        """card layout renders elevated card with shadow and centred content."""
        props = {
            "title": "Our Story",
            "content_md": "We started in 2020.",
            "image_key": "team.jpg",
        }
        html = renderer.render_about(props, "card")

        assert 'class="section about"' in html
        assert 'class="container"' in html
        assert "max-width:700px" in html
        assert "margin:0 auto" in html
        assert "background:#fff" in html
        assert "border-radius:12px" in html
        assert "box-shadow:0 4px 16px rgba(0,0,0,0.1)" in html
        assert "padding:3rem" in html
        assert "text-align:center" in html
        assert "<h2>Our Story</h2>" in html
        assert "<p>We started in 2020.</p>" in html
        assert "team.jpg" in html

    def test_about_card_layout_no_image(self, renderer):
        """card layout without image still renders correctly."""
        props = {"title": "About", "content_md": "Text here"}
        html = renderer.render_about(props, "card")

        assert "max-width:700px" in html
        assert "<h2>About</h2>" in html
        assert "<p>Text here</p>" in html
        assert "about-img" not in html

    def test_about_timeline_layout_structure(self, renderer):
        """timeline layout renders vertical timeline with milestones."""
        props = {
            "title": "Our Journey",
            "content_md": "",
            "timeline_items": [
                {"title": "Founded", "description": "Company established in 2018"},
                {"title": "Growth", "description": "Reached 100 customers"},
            ],
        }
        html = renderer.render_about(props, "timeline")

        assert 'class="section about"' in html
        assert 'class="container"' in html
        assert "<h2>Our Journey</h2>" in html
        assert "position:relative" in html
        assert "padding-left:2rem" in html
        assert "border-left:3px solid #F4A261" in html
        assert "Founded" in html
        assert "Company established in 2018" in html
        assert "Growth" in html
        assert "Reached 100 customers" in html

    def test_about_timeline_dot_styling(self, renderer):
        """timeline layout renders accent-colored dots for each milestone."""
        props = {
            "title": "Timeline",
            "content_md": "",
            "timeline_items": [
                {"title": "Step 1", "description": "First step"},
            ],
        }
        html = renderer.render_about(props, "timeline")

        assert "width:12px" in html
        assert "height:12px" in html
        assert "border-radius:50%" in html
        assert f"background:{renderer.color_accent}" in html
        assert "left:-1.6rem" in html

    def test_about_timeline_empty_items(self, renderer):
        """timeline layout with no timeline_items renders section without items."""
        props = {"title": "History", "content_md": "", "timeline_items": []}
        html = renderer.render_about(props, "timeline")

        assert "<h2>History</h2>" in html
        assert "border-left:3px solid" in html
        # No item divs
        assert "margin-bottom:2rem" not in html

    def test_about_timeline_escapes_html(self, renderer):
        """timeline layout HTML-escapes item titles and descriptions."""
        props = {
            "title": "Timeline",
            "content_md": "",
            "timeline_items": [
                {"title": "<script>xss</script>", "description": "<b>bold</b>"},
            ],
        }
        html = renderer.render_about(props, "timeline")

        assert "<script>" not in html
        assert "&lt;script&gt;" in html
        assert "<b>" not in html
        assert "&lt;b&gt;" in html

    """Tests for render_faq section."""

    def test_faq_with_items(self, renderer):
        """FAQ renders details/summary elements for each item."""
        props = {
            "title": "FAQ",
            "items": [
                {"question": "What is this?", "answer": "A product."},
                {"question": "How much?", "answer": "Free."},
            ],
        }
        html = renderer.render_faq(props)

        assert '<h2>FAQ</h2>' in html
        assert '<summary>What is this?</summary>' in html
        assert '<p>A product.</p>' in html
        assert '<summary>How much?</summary>' in html
        assert '<p>Free.</p>' in html
        assert html.count('faq-item') == 2

    def test_faq_empty_items_returns_empty(self, renderer):
        """FAQ with no items returns empty string."""
        props = {"title": "FAQ", "items": []}
        assert renderer.render_faq(props) == ""

    def test_faq_escapes_content(self, renderer):
        """FAQ escapes HTML in questions and answers."""
        props = {
            "title": "FAQ",
            "items": [{"question": "<b>Bold?</b>", "answer": "No <i>italic</i>"}],
        }
        html = renderer.render_faq(props)
        assert "<b>" not in html
        assert "&lt;b&gt;" in html


class TestRenderSection:
    """Tests for render_section dispatch."""

    def test_dispatches_to_hero(self, renderer):
        """render_section dispatches 'hero' to render_hero."""
        props = {"title": "Hero Title"}
        html = renderer.render_section("hero", props, "default", "test-slug")
        assert '<h1>Hero Title</h1>' in html

    def test_dispatches_to_about(self, renderer):
        """render_section dispatches 'about' to render_about."""
        props = {"title": "About Title", "content_md": "Content"}
        html = renderer.render_section("about", props, "default", "test-slug")
        assert '<h2>About Title</h2>' in html

    def test_dispatches_to_faq(self, renderer):
        """render_section dispatches 'faq' to render_faq."""
        props = {"title": "FAQ", "items": [{"question": "Q?", "answer": "A."}]}
        html = renderer.render_section("faq", props, "", "test-slug")
        assert 'faq-item' in html

    def test_dispatches_to_cta(self, renderer):
        """render_section dispatches 'cta' to render_cta."""
        props = {"title": "Act Now", "button_text": "Click"}
        html = renderer.render_section("cta", props, "", "test-slug")
        assert 'class="cta"' in html

    def test_dispatches_to_testimonials(self, renderer):
        """render_section dispatches 'testimonials' to render_testimonials."""
        props = {"title": "Reviews", "items": [{"quote": "Great!", "author": "Jan"}]}
        html = renderer.render_section("testimonials", props, "", "test-slug")
        assert 'testimonial-card' in html

    def test_dispatches_to_embed(self, renderer):
        """render_section dispatches 'embed' to render_embed."""
        props = {"url": "https://youtube.com/embed/abc", "title": "Video"}
        html = renderer.render_section("embed", props, "", "test-slug")
        assert 'iframe' in html

    def test_dispatches_to_pricing(self, renderer):
        """render_section dispatches 'pricing' to render_pricing."""
        props = {"title": "Plans", "items": [{"name": "Basic", "price": "€10"}]}
        html = renderer.render_section("pricing", props, "", "test-slug")
        assert 'pricing-card' in html

    def test_unknown_type_returns_empty(self, renderer):
        """Unknown section type returns empty string."""
        result = renderer.render_section("unknown_type", {}, "", "slug")
        assert result == ""


class TestRenderCta:
    """Tests for render_cta section."""

    def test_cta_structure(self, renderer):
        """CTA renders title, subtitle, and button."""
        props = {
            "title": "Ready?",
            "subtitle": "Join now",
            "button_text": "Start",
            "button_url": "/start",
        }
        html = renderer.render_cta(props)
        assert '<h2>Ready?</h2>' in html
        assert '<p>Join now</p>' in html
        assert 'href="/start"' in html
        assert 'Start' in html

    def test_cta_no_button(self, renderer):
        """CTA without button_text omits button."""
        props = {"title": "Title"}
        html = renderer.render_cta(props)
        assert 'class="btn"' not in html


class TestRenderEmbed:
    """Tests for render_embed section."""

    def test_embed_valid_https(self, renderer):
        """Embed renders iframe for HTTPS URLs."""
        props = {"url": "https://example.com/widget", "height": "400px", "title": "Widget"}
        html = renderer.render_embed(props)
        assert 'iframe' in html
        assert 'src="https://example.com/widget"' in html
        assert 'height="400px"' in html

    def test_embed_rejects_http(self, renderer):
        """Embed rejects non-HTTPS URLs."""
        props = {"url": "http://example.com/widget", "title": "Widget"}
        assert renderer.render_embed(props) == ""

    def test_embed_rejects_empty(self, renderer):
        """Embed rejects empty URL."""
        props = {"url": ""}
        assert renderer.render_embed(props) == ""


class TestRenderSectionsHtml:
    """Tests for render_sections_html orchestrator."""

    def test_renders_multiple_sections(self, renderer):
        """render_sections_html combines multiple sections."""
        sections = [
            {"type": "hero", "properties": {"title": "Hero"}, "layout": "default"},
            {"type": "faq", "properties": {"title": "FAQ", "items": [{"question": "Q", "answer": "A"}]}, "layout": ""},
        ]
        html = renderer.render_sections_html(sections, "test-slug")
        assert '<h1>Hero</h1>' in html
        assert 'faq-item' in html

    def test_skips_unknown_sections(self, renderer):
        """render_sections_html skips unknown types gracefully."""
        sections = [
            {"type": "unknown", "properties": {}, "layout": ""},
            {"type": "hero", "properties": {"title": "Valid"}, "layout": "default"},
        ]
        html = renderer.render_sections_html(sections, "slug")
        assert '<h1>Valid</h1>' in html

    def test_section_without_settings_renders_as_before(self, renderer):
        """Sections without settings render identically to legacy behaviour (no style attr)."""
        sections = [
            {"type": "hero", "properties": {"title": "Legacy"}, "layout": "default"},
        ]
        html = renderer.render_sections_html(sections, "slug")
        # Should NOT have a wrapper style attribute injected
        assert 'style="' not in html or 'flex-direction' in html  # hero may have internal style
        # The hero's own section markup is preserved
        assert '<section class="section">' in html
        assert '<h1>Legacy</h1>' in html

    def test_section_with_empty_settings_renders_as_before(self, renderer):
        """Sections with empty settings dict render identically to legacy (backwards compat)."""
        sections = [
            {"type": "hero", "properties": {"title": "NoStyle"}, "layout": "default", "settings": {}},
        ]
        html = renderer.render_sections_html(sections, "slug")
        # Empty settings → build_section_style returns "" → no wrapping
        assert '<section class="section">' in html
        assert '<h1>NoStyle</h1>' in html

    def test_section_with_settings_gets_inline_style(self, renderer):
        """Sections with settings get wrapped with inline style attribute."""
        sections = [
            {
                "type": "faq",
                "properties": {"title": "FAQ", "items": [{"question": "Q", "answer": "A"}]},
                "layout": "",
                "settings": {
                    "background_type": "color",
                    "background_color": "#ff0000",
                    "padding": "spacious",
                },
            },
        ]
        html = renderer.render_sections_html(sections, "slug")
        assert 'style="' in html
        assert "background-color: #ff0000" in html
        assert "padding: 4rem 1.5rem" in html
        # Section wrapper has class="section"
        assert '<section class="section"' in html

    def test_section_with_settings_contained_max_width(self, renderer):
        """Settings with max_width=contained wraps content in container div."""
        sections = [
            {
                "type": "faq",
                "properties": {"title": "FAQ", "items": [{"question": "Q", "answer": "A"}]},
                "layout": "",
                "settings": {
                    "background_type": "color",
                    "background_color": "#eee",
                    "max_width": "contained",
                },
            },
        ]
        html = renderer.render_sections_html(sections, "slug")
        assert '<div class="container">' in html

    def test_section_with_settings_full_width(self, renderer):
        """Settings with max_width=full-width uses empty container class."""
        sections = [
            {
                "type": "faq",
                "properties": {"title": "FAQ", "items": [{"question": "Q", "answer": "A"}]},
                "layout": "",
                "settings": {
                    "background_type": "color",
                    "background_color": "#eee",
                    "max_width": "full-width",
                },
            },
        ]
        html = renderer.render_sections_html(sections, "slug")
        assert '<div class="">' in html

    def test_section_with_gradient_settings_sanitizes(self, renderer):
        """Gradient in settings is sanitized (url/expression/javascript stripped)."""
        sections = [
            {
                "type": "hero",
                "properties": {"title": "Styled"},
                "layout": "default",
                "settings": {
                    "background_type": "gradient",
                    "background_gradient": "linear-gradient(135deg, red, url(https://evil.com))",
                },
            },
        ]
        html = renderer.render_sections_html(sections, "slug")
        assert "url(" not in html.lower()
        assert "background:" in html


class TestPublishRoundTrip:
    """Task 27: Test publish round-trip — settings saved → published HTML has correct inline styles."""

    def test_full_settings_produce_correct_inline_style(self, renderer):
        """All settings fields produce matching CSS properties in published HTML."""
        sections = [
            {
                "type": "faq",
                "properties": {"title": "FAQ", "items": [{"question": "Q?", "answer": "A."}]},
                "layout": "",
                "settings": {
                    "background_type": "color",
                    "background_color": "#1a2b3c",
                    "padding": "spacious",
                    "text_color": "light",
                    "border_radius": "lg",
                    "max_width": "contained",
                },
            },
        ]
        html = renderer.render_sections_html(sections, "test-slug")

        # Verify all expected CSS properties in the style attribute
        assert "background-color: #1a2b3c" in html
        assert "padding: 4rem 1.5rem" in html
        assert "color: #fff" in html
        assert "border-radius: 24px" in html
        # Contained max_width uses the container class
        assert '<div class="container">' in html

    def test_gradient_background_round_trip(self, renderer):
        """Gradient background setting produces correct CSS background property."""
        gradient = "linear-gradient(135deg, #667eea 0%, #764ba2 100%)"
        sections = [
            {
                "type": "about",
                "properties": {"title": "About", "content_md": "Content"},
                "layout": "default",
                "settings": {
                    "background_type": "gradient",
                    "background_gradient": gradient,
                    "padding": "compact",
                    "text_color": "light",
                    "border_radius": "md",
                    "max_width": "full-width",
                },
            },
        ]
        html = renderer.render_sections_html(sections, "slug")

        assert f"background: {gradient}" in html
        assert "padding: 1rem 1.5rem" in html
        assert "color: #fff" in html
        assert "border-radius: 16px" in html
        # Full-width uses empty class
        assert '<div class="">' in html

    def test_image_background_round_trip(self, renderer):
        """Image background produces url, cover, and center properties."""
        sections = [
            {
                "type": "cta",
                "properties": {"title": "CTA", "button_text": "Click"},
                "layout": "",
                "settings": {
                    "background_type": "image",
                    "background_image_key": "uploads/bg-hero.jpg",
                    "padding": "normal",
                    "text_color": "light",
                    "border_radius": "sm",
                    "max_width": "contained",
                },
            },
        ]
        html = renderer.render_sections_html(sections, "slug")

        assert "background-image: url('https://cdn.example.com/images/uploads/bg-hero.jpg')" in html
        assert "background-size: cover" in html
        assert "background-position: center" in html
        assert "padding: 2rem 1.5rem" in html
        assert "border-radius: 8px" in html

    def test_multiple_sections_each_get_own_style(self, renderer):
        """Multiple sections each receive their own independent inline style."""
        sections = [
            {
                "type": "hero",
                "properties": {"title": "Section 1"},
                "layout": "default",
                "settings": {
                    "background_type": "color",
                    "background_color": "#ff0000",
                    "padding": "compact",
                },
            },
            {
                "type": "about",
                "properties": {"title": "Section 2", "content_md": "Text"},
                "layout": "default",
                "settings": {
                    "background_type": "color",
                    "background_color": "#00ff00",
                    "padding": "spacious",
                },
            },
        ]
        html = renderer.render_sections_html(sections, "slug")

        assert "background-color: #ff0000" in html
        assert "padding: 1rem 1.5rem" in html
        assert "background-color: #00ff00" in html
        assert "padding: 4rem 1.5rem" in html

    def test_section_without_settings_no_inline_style(self, renderer):
        """A section without settings produces no inline style attribute on wrapper."""
        sections = [
            {
                "type": "hero",
                "properties": {"title": "Plain Hero"},
                "layout": "default",
                # No 'settings' key
            },
        ]
        html = renderer.render_sections_html(sections, "slug")

        # The hero renders its own internal HTML without a styled wrapper
        assert '<h1>Plain Hero</h1>' in html
        # No build_section_style wrapper was applied (the hero has its own section tag)
        lines = [l for l in html.split("\n") if 'style="background' in l]
        assert len(lines) == 0


class TestResponsiveVerification:
    """Task 26: Verify responsive behaviour of all settings on mobile viewports.

    Block settings use inline styles which work at all viewport sizes by default.
    This verifies that generated CSS is inherently responsive:
    - Padding uses rem-based values (scale with root font size)
    - Background images use cover + center (adapt to any viewport)
    - Max-width "contained" uses the .container class (already responsive)
    - Border-radius uses absolute px values (fine for all viewports)
    """

    def test_padding_values_are_rem_based(self, renderer):
        """All padding presets use rem units — they scale with viewport/font size."""
        from services.landing_page_styles import LandingPageStyles

        for preset, value in LandingPageStyles.PADDING_MAP.items():
            # All padding values must use rem
            assert "rem" in value, f"Padding '{preset}' ({value}) should use rem units"
            # No px in padding values
            assert "px" not in value, f"Padding '{preset}' should not use fixed px"

    def test_background_image_uses_cover_and_center(self, renderer):
        """Background image settings include cover and center for responsive behaviour."""
        sections = [
            {
                "type": "faq",
                "properties": {"title": "FAQ", "items": [{"question": "Q", "answer": "A"}]},
                "layout": "",
                "settings": {
                    "background_type": "image",
                    "background_image_key": "uploads/bg.jpg",
                },
            },
        ]
        html = renderer.render_sections_html(sections, "slug")

        # Cover and center ensure the image fills any viewport size
        assert "background-size: cover" in html
        assert "background-position: center" in html

    def test_contained_max_width_uses_responsive_container_class(self, renderer):
        """Contained max_width applies the .container class which is responsive via CSS."""
        sections = [
            {
                "type": "faq",
                "properties": {"title": "FAQ", "items": [{"question": "Q", "answer": "A"}]},
                "layout": "",
                "settings": {
                    "background_type": "color",
                    "background_color": "#eee",
                    "max_width": "contained",
                },
            },
        ]
        html = renderer.render_sections_html(sections, "slug")

        # Uses the .container class which has max-width + auto margins
        assert '<div class="container">' in html

    def test_border_radius_values_are_absolute_px(self, renderer):
        """Border-radius uses absolute px values — consistent on all viewports."""
        from services.landing_page_styles import LandingPageStyles

        for preset, value in LandingPageStyles.BORDER_RADIUS_MAP.items():
            if preset != "none":
                assert "px" in value, f"Radius '{preset}' ({value}) should use px"
            else:
                assert value == "0", "Radius 'none' should be '0'"

    def test_full_width_has_no_container_constraint(self, renderer):
        """Full-width max_width removes container constraint (edge-to-edge on mobile)."""
        sections = [
            {
                "type": "faq",
                "properties": {"title": "FAQ", "items": [{"question": "Q", "answer": "A"}]},
                "layout": "",
                "settings": {
                    "background_type": "color",
                    "background_color": "#eee",
                    "max_width": "full-width",
                },
            },
        ]
        html = renderer.render_sections_html(sections, "slug")

        # Full-width uses empty class — no container max-width restriction
        assert '<div class="">' in html

    def test_generated_css_has_no_fixed_width_in_inline_styles(self, renderer):
        """Inline styles never include fixed widths that break responsive layout."""
        from services.landing_page_styles import LandingPageStyles

        settings = {
            "background_type": "color",
            "background_color": "#f0f0f0",
            "padding": "normal",
            "text_color": "dark",
            "border_radius": "lg",
            "max_width": "contained",
        }
        style = LandingPageStyles.build_section_style(settings, "https://cdn.test.com")

        # Should not contain fixed width/height (responsive by omission)
        assert "width:" not in style
        assert "height:" not in style
        assert "max-width:" not in style  # max-width handled by container class, not inline


class TestRenderTestimonialsCarousel:
    """Tests for testimonials carousel layout (Task 75)."""

    def test_carousel_structure(self, renderer):
        """Carousel layout renders carousel container with track, buttons, and dots."""
        props = {
            "title": "What People Say",
            "items": [
                {"quote": "Amazing!", "author": "Alice", "role": "CEO"},
                {"quote": "Great service.", "author": "Bob"},
            ],
        }
        html = renderer.render_testimonials(props, "carousel")

        assert 'class="section testimonials"' in html
        assert '<h2>What People Say</h2>' in html
        assert 'data-carousel' in html
        assert 'data-carousel-track' in html
        assert 'data-carousel-prev' in html
        assert 'data-carousel-next' in html
        assert 'carousel-dots' in html
        assert '&#10094;' in html
        assert '&#10095;' in html

    def test_carousel_slides(self, renderer):
        """Carousel renders one slide per testimonial."""
        props = {
            "title": "",
            "items": [
                {"quote": "First quote", "author": "A1", "role": "Dev"},
                {"quote": "Second quote", "author": "A2"},
                {"quote": "Third quote", "author": "A3", "role": "PM"},
            ],
        }
        html = renderer.render_testimonials(props, "carousel")

        assert html.count('class="carousel-slide"') == 3
        assert '"First quote"' in html
        assert '"Second quote"' in html
        assert '"Third quote"' in html
        assert '— A1, Dev' in html
        assert '— A2' in html
        assert '— A3, PM' in html

    def test_carousel_dots_match_items(self, renderer):
        """Carousel renders one dot per slide, first active."""
        props = {
            "title": "",
            "items": [
                {"quote": "Q1", "author": "A"},
                {"quote": "Q2", "author": "B"},
            ],
        }
        html = renderer.render_testimonials(props, "carousel")

        assert html.count('data-carousel-dot') == 2  # one per slide
        assert 'carousel-dot active' in html
        assert 'data-index="0"' in html
        assert 'data-index="1"' in html

    def test_carousel_slide_styling(self, renderer):
        """Carousel slides have centred text and italic blockquote."""
        props = {
            "title": "",
            "items": [{"quote": "Nice!", "author": "Z"}],
        }
        html = renderer.render_testimonials(props, "carousel")

        assert 'min-width:100%' in html
        assert 'text-align:center' in html
        assert 'font-size:1.3rem' in html
        assert 'font-style:italic' in html

    def test_carousel_escapes_html(self, renderer):
        """Carousel HTML-escapes user content."""
        props = {
            "title": "",
            "items": [{"quote": "<script>xss</script>", "author": "<b>Hacker</b>"}],
        }
        html = renderer.render_testimonials(props, "carousel")

        assert '<script>' not in html
        assert '&lt;script&gt;' in html
        assert '<b>' not in html
        assert '&lt;b&gt;' in html

    def test_carousel_empty_items_returns_empty(self, renderer):
        """Carousel with no items returns empty string."""
        props = {"title": "Reviews", "items": []}
        assert renderer.render_testimonials(props, "carousel") == ""


class TestRenderTestimonialsQuoteLarge:
    """Tests for testimonials quote-large layout (Task 76)."""

    def test_quote_large_structure(self, renderer):
        """Quote-large renders centred large quote from first item."""
        props = {
            "title": "Testimonial",
            "items": [
                {"quote": "This changed everything.", "author": "Jane", "role": "Founder"},
                {"quote": "Ignored second", "author": "John"},
            ],
        }
        html = renderer.render_testimonials(props, "quote-large")

        assert 'class="section testimonials"' in html
        assert '<h2>Testimonial</h2>' in html
        assert 'text-align:center' in html
        assert 'max-width:800px' in html
        assert 'margin:0 auto' in html
        assert '"This changed everything."' in html
        assert '— Jane, Founder' in html
        # Second item should NOT be rendered
        assert 'Ignored second' not in html

    def test_quote_large_styling(self, renderer):
        """Quote-large uses large font and bold cite."""
        props = {
            "title": "",
            "items": [{"quote": "Brilliant", "author": "Sam"}],
        }
        html = renderer.render_testimonials(props, "quote-large")

        assert 'font-size:2rem' in html
        assert 'font-style:italic' in html
        assert 'color:#333' in html
        assert 'line-height:1.4' in html
        assert 'font-weight:600' in html
        assert 'font-size:1.1rem' in html

    def test_quote_large_no_role(self, renderer):
        """Quote-large without role renders author only."""
        props = {
            "title": "",
            "items": [{"quote": "Good", "author": "Kim"}],
        }
        html = renderer.render_testimonials(props, "quote-large")

        assert '— Kim' in html
        # Should not have trailing comma
        assert '— Kim,' not in html

    def test_quote_large_escapes_html(self, renderer):
        """Quote-large HTML-escapes user content."""
        props = {
            "title": "",
            "items": [{"quote": "<img src=x>", "author": "<em>Evil</em>", "role": "<b>Boss</b>"}],
        }
        html = renderer.render_testimonials(props, "quote-large")

        assert '<img' not in html
        assert '&lt;img' in html
        assert '<em>' not in html
        assert '&lt;em&gt;' in html

    def test_quote_large_empty_items_returns_empty(self, renderer):
        """Quote-large with no items returns empty string."""
        props = {"title": "Reviews", "items": []}
        assert renderer.render_testimonials(props, "quote-large") == ""


class TestRenderTestimonialsGrid:
    """Tests for testimonials grid layout (Task 77)."""

    def test_grid_structure(self, renderer):
        """Grid layout renders items in a CSS grid without card styling."""
        props = {
            "title": "Reviews",
            "items": [
                {"quote": "Love it", "author": "Alice", "role": "Manager"},
                {"quote": "Top notch", "author": "Bob"},
            ],
        }
        html = renderer.render_testimonials(props, "grid")

        assert 'class="section testimonials"' in html
        assert '<h2>Reviews</h2>' in html
        assert 'display:grid' in html
        assert 'grid-template-columns:repeat(auto-fill,minmax(280px,1fr))' in html
        assert 'gap:1.5rem' in html

    def test_grid_items_no_card_styling(self, renderer):
        """Grid items have border-bottom but no card background/shadow."""
        props = {
            "title": "",
            "items": [{"quote": "Nice", "author": "Eve"}],
        }
        html = renderer.render_testimonials(props, "grid")

        assert 'border-bottom:1px solid #eee' in html
        assert 'testimonial-card' not in html
        assert 'box-shadow' not in html

    def test_grid_item_content(self, renderer):
        """Grid items render quote and cite correctly."""
        props = {
            "title": "",
            "items": [
                {"quote": "Wonderful", "author": "Dave", "role": "CTO"},
                {"quote": "So good", "author": "Ella"},
            ],
        }
        html = renderer.render_testimonials(props, "grid")

        assert '"Wonderful"' in html
        assert '— Dave, CTO' in html
        assert '"So good"' in html
        assert '— Ella' in html
        # No trailing comma when no role
        assert '— Ella,' not in html

    def test_grid_escapes_html(self, renderer):
        """Grid HTML-escapes user content."""
        props = {
            "title": "",
            "items": [{"quote": "<div>hack</div>", "author": "<a>link</a>"}],
        }
        html = renderer.render_testimonials(props, "grid")

        assert '<div>hack</div>' not in html
        assert '&lt;div&gt;' in html
        assert '<a>link</a>' not in html
        assert '&lt;a&gt;' in html

    def test_grid_empty_items_returns_empty(self, renderer):
        """Grid with no items returns empty string."""
        props = {"title": "Reviews", "items": []}
        assert renderer.render_testimonials(props, "grid") == ""


class TestRenderFaqTwoColumn:
    """Tests for FAQ two-column layout (Task 78)."""

    def test_two_column_structure(self, renderer):
        """Two-column layout forces 2-column grid via inline style."""
        props = {
            "title": "FAQ",
            "items": [
                {"question": "Q1?", "answer": "A1."},
                {"question": "Q2?", "answer": "A2."},
            ],
        }
        html = renderer.render_faq(props, "two-column")

        assert 'class="section faq"' in html
        assert '<h2>FAQ</h2>' in html
        assert 'display:grid' in html
        assert 'grid-template-columns:repeat(2,1fr)' in html
        assert 'gap:0 2rem' in html

    def test_two_column_still_has_faq_grid_class(self, renderer):
        """Two-column layout keeps faq-grid class for base styling."""
        props = {
            "title": "",
            "items": [{"question": "Q?", "answer": "A."}],
        }
        html = renderer.render_faq(props, "two-column")

        assert 'class="faq-grid"' in html

    def test_two_column_items_rendered(self, renderer):
        """Two-column layout renders all FAQ items as details/summary."""
        props = {
            "title": "",
            "items": [
                {"question": "What?", "answer": "This."},
                {"question": "Why?", "answer": "Because."},
                {"question": "How?", "answer": "Like so."},
            ],
        }
        html = renderer.render_faq(props, "two-column")

        assert html.count('faq-item') == 3
        assert '<summary>What?</summary>' in html
        assert '<summary>Why?</summary>' in html
        assert '<summary>How?</summary>' in html

    def test_two_column_empty_items_returns_empty(self, renderer):
        """Two-column with no items returns empty string."""
        props = {"title": "FAQ", "items": []}
        assert renderer.render_faq(props, "two-column") == ""

    def test_default_faq_no_inline_grid_style(self, renderer):
        """Default FAQ layout uses faq-grid class without inline grid style."""
        props = {
            "title": "FAQ",
            "items": [{"question": "Q?", "answer": "A."}],
        }
        html = renderer.render_faq(props, "")

        assert 'class="faq-grid"' in html
        assert 'grid-template-columns' not in html

    def test_faq_backward_compat_no_layout_arg(self, renderer):
        """render_faq without layout argument still works (backward compat)."""
        props = {
            "title": "FAQ",
            "items": [{"question": "Q?", "answer": "A."}],
        }
        html = renderer.render_faq(props)

        assert 'class="faq-grid"' in html
        assert 'grid-template-columns' not in html


class TestRenderFaqSideBySide:
    """Tests for FAQ side-by-side layout (Task 79)."""

    def test_side_by_side_grid_structure(self, renderer):
        """Side-by-side layout uses 1fr 2fr grid columns."""
        props = {
            "title": "FAQ",
            "items": [
                {"question": "Q1?", "answer": "A1."},
                {"question": "Q2?", "answer": "A2."},
            ],
        }
        result = renderer.render_faq(props, "side-by-side")

        assert "display:grid" in result
        assert "grid-template-columns:1fr 2fr" in result
        assert "gap:1rem 2rem" in result
        assert "align-items:start" in result

    def test_side_by_side_question_answer_pairs(self, renderer):
        """Each item renders as question div + answer div."""
        props = {
            "title": "",
            "items": [
                {"question": "What is it?", "answer": "A tool."},
                {"question": "How much?", "answer": "Free."},
            ],
        }
        result = renderer.render_faq(props, "side-by-side")

        assert 'font-weight:600' in result
        assert "What is it?" in result
        assert "A tool." in result
        assert "How much?" in result
        assert "Free." in result
        assert 'color:#555' in result

    def test_side_by_side_empty_items_returns_empty(self, renderer):
        """Side-by-side with no items returns empty string."""
        props = {"title": "FAQ", "items": []}
        assert renderer.render_faq(props, "side-by-side") == ""

    def test_side_by_side_escapes_html(self, renderer):
        """Side-by-side escapes HTML in questions and answers."""
        props = {
            "title": "",
            "items": [{"question": "<b>Q</b>", "answer": "<script>x</script>"}],
        }
        result = renderer.render_faq(props, "side-by-side")

        assert "<b>Q</b>" not in result
        assert "&lt;b&gt;" in result
        assert "<script>" not in result

    def test_side_by_side_has_title(self, renderer):
        """Side-by-side renders title when provided."""
        props = {
            "title": "Questions",
            "items": [{"question": "Q?", "answer": "A."}],
        }
        result = renderer.render_faq(props, "side-by-side")

        assert "<h2>Questions</h2>" in result


class TestRenderPricingHorizontal:
    """Tests for Pricing horizontal layout (Task 80)."""

    def test_horizontal_table_structure(self, renderer):
        """Horizontal layout renders a table with correct styling."""
        props = {
            "title": "Plans",
            "items": [
                {"name": "Basic", "price": "$9", "features": ["Email"]},
                {"name": "Pro", "price": "$29", "features": ["Email", "Chat"]},
            ],
        }
        result = renderer.render_pricing(props, "horizontal")

        assert "<table" in result
        assert "border-collapse:collapse" in result
        assert "text-align:center" in result
        assert "<thead>" in result
        assert "<tbody>" in result

    def test_horizontal_header_shows_names_and_prices(self, renderer):
        """Header cells show plan name and price."""
        props = {
            "title": "",
            "items": [
                {"name": "Starter", "price": "$5", "features": []},
                {"name": "Growth", "price": "$15", "features": []},
            ],
        }
        result = renderer.render_pricing(props, "horizontal")

        assert "Starter" in result
        assert "$5" in result
        assert "Growth" in result
        assert "$15" in result
        assert self.renderer_accent(renderer) in result

    def test_horizontal_feature_rows(self, renderer):
        """Feature rows show ✓ for included and — for missing."""
        props = {
            "title": "",
            "items": [
                {"name": "A", "price": "$1", "features": ["X", "Y"]},
                {"name": "B", "price": "$2", "features": ["Y", "Z"]},
            ],
        }
        result = renderer.render_pricing(props, "horizontal")

        assert "X" in result
        assert "Y" in result
        assert "Z" in result
        assert "✓" in result
        assert "—" in result

    def test_horizontal_empty_items_returns_empty(self, renderer):
        """Horizontal with no items returns empty string."""
        props = {"title": "Plans", "items": []}
        assert renderer.render_pricing(props, "horizontal") == ""

    @staticmethod
    def renderer_accent(renderer):
        return renderer.color_accent


class TestRenderPricingFeaturedCenter:
    """Tests for Pricing featured-center layout (Task 81)."""

    def test_featured_center_middle_highlighted(self, renderer):
        """Middle card gets scale transform and accent border."""
        props = {
            "title": "Pricing",
            "items": [
                {"name": "A", "price": "$1", "description": "", "features": []},
                {"name": "B", "price": "$2", "description": "", "features": []},
                {"name": "C", "price": "$3", "description": "", "features": []},
            ],
        }
        result = renderer.render_pricing(props, "featured-center")

        assert "transform:scale(1.05)" in result
        assert f"border:2px solid {renderer.color_accent}" in result
        assert "box-shadow:0 4px 20px rgba(0,0,0,0.15)" in result

    def test_featured_center_non_middle_no_highlight(self, renderer):
        """Non-middle cards have no inline style."""
        props = {
            "title": "",
            "items": [
                {"name": "A", "price": "$1", "description": "", "features": []},
                {"name": "B", "price": "$2", "description": "", "features": []},
                {"name": "C", "price": "$3", "description": "", "features": []},
            ],
        }
        result = renderer.render_pricing(props, "featured-center")

        # Count occurrences of transform:scale — only the middle card
        assert result.count("transform:scale(1.05)") == 1

    def test_featured_center_uses_pricing_grid(self, renderer):
        """Featured-center still uses pricing-grid container."""
        props = {
            "title": "",
            "items": [
                {"name": "A", "price": "$1", "description": "", "features": []},
            ],
        }
        result = renderer.render_pricing(props, "featured-center")

        assert 'class="pricing-grid"' in result

    def test_featured_center_empty_items_returns_empty(self, renderer):
        """Featured-center with no items returns empty string."""
        props = {"title": "Plans", "items": []}
        assert renderer.render_pricing(props, "featured-center") == ""


class TestRenderPricingComparisonTable:
    """Tests for Pricing comparison-table layout (Task 82)."""

    def test_comparison_table_structure(self, renderer):
        """Comparison table has Feature header and plan columns."""
        props = {
            "title": "Compare",
            "items": [
                {"name": "Free", "price": "$0", "features": ["Email"]},
                {"name": "Pro", "price": "$20", "features": ["Email", "Phone"]},
            ],
        }
        result = renderer.render_pricing(props, "comparison-table")

        assert "<table" in result
        assert "border-collapse:collapse" in result
        assert "Feature" in result
        assert "Free - $0" in result
        assert "Pro - $20" in result

    def test_comparison_table_feature_marks(self, renderer):
        """Features show ✓ when included and — when not."""
        props = {
            "title": "",
            "items": [
                {"name": "A", "price": "$1", "features": ["X"]},
                {"name": "B", "price": "$2", "features": ["X", "Y"]},
            ],
        }
        result = renderer.render_pricing(props, "comparison-table")

        assert "✓" in result
        assert "—" in result
        # Feature X is in both plans
        assert "X" in result
        # Feature Y is only in B
        assert "Y" in result

    def test_comparison_table_unique_features(self, renderer):
        """All unique features across items appear as rows."""
        props = {
            "title": "",
            "items": [
                {"name": "A", "price": "$1", "features": ["F1", "F2"]},
                {"name": "B", "price": "$2", "features": ["F2", "F3"]},
            ],
        }
        result = renderer.render_pricing(props, "comparison-table")

        assert "F1" in result
        assert "F2" in result
        assert "F3" in result

    def test_comparison_table_empty_items_returns_empty(self, renderer):
        """Comparison-table with no items returns empty string."""
        props = {"title": "Plans", "items": []}
        assert renderer.render_pricing(props, "comparison-table") == ""


class TestRenderCtaSplit:
    """Tests for CTA split layout (Task 83)."""

    def test_split_flex_structure(self, renderer):
        """Split layout uses flex with space-between."""
        props = {
            "title": "Ready?",
            "subtitle": "Join now",
            "button_text": "Sign Up",
            "button_url": "/register",
        }
        result = renderer.render_cta(props, "split")

        assert "display:flex" in result
        assert "align-items:center" in result
        assert "justify-content:space-between" in result
        assert "flex-wrap:wrap" in result

    def test_split_text_left(self, renderer):
        """Split layout has title and subtitle on the left."""
        props = {
            "title": "Get Started",
            "subtitle": "No credit card needed",
            "button_text": "Go",
            "button_url": "#",
        }
        result = renderer.render_cta(props, "split")

        assert "<h2>Get Started</h2>" in result
        assert "<p>No credit card needed</p>" in result
        assert 'flex:1;min-width:280px' in result

    def test_split_button_right(self, renderer):
        """Split layout has button in a flex-shrink:0 container."""
        props = {
            "title": "Act Now",
            "subtitle": "",
            "button_text": "Buy",
            "button_url": "/buy",
        }
        result = renderer.render_cta(props, "split")

        assert "flex-shrink:0" in result
        assert 'href="/buy"' in result
        assert "Buy" in result

    def test_split_no_subtitle(self, renderer):
        """Split layout without subtitle omits the p tag."""
        props = {
            "title": "Go",
            "subtitle": "",
            "button_text": "Click",
            "button_url": "#",
        }
        result = renderer.render_cta(props, "split")

        # Empty subtitle should not produce a <p></p>
        assert "<p></p>" not in result

    def test_split_empty_button(self, renderer):
        """Split layout without button_text omits button."""
        props = {
            "title": "Info",
            "subtitle": "Details",
            "button_text": "",
            "button_url": "#",
        }
        result = renderer.render_cta(props, "split")

        assert 'class="btn"' not in result

    def test_default_cta_backward_compat(self, renderer):
        """Default CTA still works when no layout is passed."""
        props = {
            "title": "Hello",
            "subtitle": "World",
            "button_text": "Go",
            "button_url": "/go",
        }
        result = renderer.render_cta(props)

        assert '<h2>Hello</h2>' in result
        assert 'class="container"' in result
        assert "display:flex" not in result

    def test_render_section_passes_layout_to_cta(self, renderer):
        """render_section dispatches layout to render_cta."""
        props = {
            "title": "CTA",
            "subtitle": "",
            "button_text": "Go",
            "button_url": "#",
        }
        result = renderer.render_section("cta", props, "split", "test-slug")

        assert "display:flex" in result
        assert "justify-content:space-between" in result

    def test_render_section_passes_layout_to_pricing(self, renderer):
        """render_section dispatches layout to render_pricing."""
        props = {
            "title": "Plans",
            "items": [
                {"name": "A", "price": "$1", "features": ["X"]},
            ],
        }
        result = renderer.render_section("pricing", props, "horizontal", "test-slug")

        assert "<table" in result
        assert "text-align:center" in result


class TestRenderCtaBanner:
    """Tests for CTA banner layout (Task 84)."""

    def test_banner_thin_strip(self, renderer):
        """Banner layout uses smaller padding for a thin strip."""
        props = {
            "title": "Limited Offer",
            "subtitle": "Ends today",
            "button_text": "Shop Now",
            "button_url": "/shop",
        }
        result = renderer.render_cta(props, "banner")

        assert 'style="padding:1rem 1.5rem;"' in result

    def test_banner_flex_center(self, renderer):
        """Banner layout centres items with flex and gap."""
        props = {
            "title": "Sale",
            "subtitle": "",
            "button_text": "Go",
            "button_url": "#",
        }
        result = renderer.render_cta(props, "banner")

        assert "display:flex" in result
        assert "align-items:center" in result
        assert "justify-content:center" in result
        assert "gap:1.5rem" in result
        assert "flex-wrap:wrap" in result

    def test_banner_title_as_span(self, renderer):
        """Banner layout renders title as a bold span, not h2."""
        props = {
            "title": "Act Now",
            "subtitle": "",
            "button_text": "Click",
            "button_url": "#",
        }
        result = renderer.render_cta(props, "banner")

        assert '<span style="font-weight:600;">Act Now</span>' in result
        assert "<h2>" not in result

    def test_banner_subtitle_span(self, renderer):
        """Banner layout renders subtitle as a span with opacity."""
        props = {
            "title": "Promo",
            "subtitle": "While stocks last",
            "button_text": "Buy",
            "button_url": "/buy",
        }
        result = renderer.render_cta(props, "banner")

        assert '<span style="opacity:0.9;">While stocks last</span>' in result

    def test_banner_no_subtitle(self, renderer):
        """Banner layout without subtitle omits the subtitle span."""
        props = {
            "title": "Go",
            "subtitle": "",
            "button_text": "Click",
            "button_url": "#",
        }
        result = renderer.render_cta(props, "banner")

        assert "opacity:0.9" not in result

    def test_banner_button(self, renderer):
        """Banner layout renders the CTA button."""
        props = {
            "title": "Ready",
            "subtitle": "",
            "button_text": "Start",
            "button_url": "/start",
        }
        result = renderer.render_cta(props, "banner")

        assert 'href="/start"' in result
        assert 'class="btn"' in result
        assert "Start" in result

    def test_banner_no_button(self, renderer):
        """Banner layout without button_text omits button."""
        props = {
            "title": "Info",
            "subtitle": "Details",
            "button_text": "",
            "button_url": "#",
        }
        result = renderer.render_cta(props, "banner")

        assert 'class="btn"' not in result

    def test_banner_section_class(self, renderer):
        """Banner layout uses section with cta class."""
        props = {
            "title": "Hello",
            "subtitle": "",
            "button_text": "Go",
            "button_url": "#",
        }
        result = renderer.render_cta(props, "banner")

        assert '<section class="cta"' in result

    def test_banner_container_class(self, renderer):
        """Banner layout uses container class on inner div."""
        props = {
            "title": "Hello",
            "subtitle": "",
            "button_text": "Go",
            "button_url": "#",
        }
        result = renderer.render_cta(props, "banner")

        assert 'class="container"' in result


class TestRenderCtaFloating:
    """Tests for CTA floating layout (Task 85)."""

    def test_floating_fixed_position(self, renderer):
        """Floating layout uses position:fixed at bottom."""
        props = {
            "title": "Subscribe",
            "subtitle": "",
            "button_text": "Join",
            "button_url": "/join",
        }
        result = renderer.render_cta(props, "floating")

        assert "position:fixed" in result
        assert "bottom:0" in result
        assert "left:0" in result
        assert "right:0" in result

    def test_floating_z_index(self, renderer):
        """Floating layout uses z-index:999."""
        props = {
            "title": "Sub",
            "subtitle": "",
            "button_text": "Go",
            "button_url": "#",
        }
        result = renderer.render_cta(props, "floating")

        assert "z-index:999" in result

    def test_floating_background_uses_primary_color(self, renderer):
        """Floating layout uses primary colour as background."""
        props = {
            "title": "CTA",
            "subtitle": "",
            "button_text": "Go",
            "button_url": "#",
        }
        result = renderer.render_cta(props, "floating")

        # Renderer is initialized with color_primary="#2D5F8A"
        assert "background:#2D5F8A" in result

    def test_floating_box_shadow(self, renderer):
        """Floating layout has upward box-shadow."""
        props = {
            "title": "CTA",
            "subtitle": "",
            "button_text": "Go",
            "button_url": "#",
        }
        result = renderer.render_cta(props, "floating")

        assert "box-shadow:0 -2px 8px rgba(0,0,0,0.15)" in result

    def test_floating_padding(self, renderer):
        """Floating layout uses 1rem 1.5rem padding."""
        props = {
            "title": "CTA",
            "subtitle": "",
            "button_text": "Go",
            "button_url": "#",
        }
        result = renderer.render_cta(props, "floating")

        assert "padding:1rem 1.5rem" in result

    def test_floating_title_white_bold(self, renderer):
        """Floating layout renders title as white bold span."""
        props = {
            "title": "Limited Time",
            "subtitle": "",
            "button_text": "Act",
            "button_url": "#",
        }
        result = renderer.render_cta(props, "floating")

        assert '<span style="color:#fff;font-weight:600;">Limited Time</span>' in result

    def test_floating_button(self, renderer):
        """Floating layout renders button."""
        props = {
            "title": "CTA",
            "subtitle": "",
            "button_text": "Buy Now",
            "button_url": "/buy",
        }
        result = renderer.render_cta(props, "floating")

        assert 'href="/buy"' in result
        assert 'class="btn"' in result
        assert "Buy Now" in result

    def test_floating_no_button(self, renderer):
        """Floating layout without button_text omits button."""
        props = {
            "title": "Info",
            "subtitle": "",
            "button_text": "",
            "button_url": "#",
        }
        result = renderer.render_cta(props, "floating")

        assert 'class="btn"' not in result

    def test_floating_uses_div_not_section(self, renderer):
        """Floating layout uses div wrapper with cta-floating class, not section."""
        props = {
            "title": "CTA",
            "subtitle": "",
            "button_text": "Go",
            "button_url": "#",
        }
        result = renderer.render_cta(props, "floating")

        assert '<div class="cta-floating"' in result
        assert "<section" not in result

    def test_floating_flex_space_between(self, renderer):
        """Floating layout uses flex with space-between."""
        props = {
            "title": "CTA",
            "subtitle": "",
            "button_text": "Go",
            "button_url": "#",
        }
        result = renderer.render_cta(props, "floating")

        assert "display:flex" in result
        assert "align-items:center" in result
        assert "justify-content:space-between" in result
        assert "flex-wrap:wrap" in result
        assert "gap:1rem" in result

    def test_floating_container_class(self, renderer):
        """Floating layout uses container class on inner div."""
        props = {
            "title": "CTA",
            "subtitle": "",
            "button_text": "Go",
            "button_url": "#",
        }
        result = renderer.render_cta(props, "floating")

        assert 'class="container"' in result


class TestRenderVideo:
    """Tests for render_video section (Tasks 89-92)."""

    def test_video_centered_layout_structure(self, renderer):
        """Centered layout renders with max-width:800px and margin:0 auto."""
        props = {
            "title": "Watch Our Tour",
            "description": "A virtual tour of our place",
            "video_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        }
        result = renderer.render_video(props, "centered")

        assert 'class="section video-block"' in result
        assert "max-width:800px;margin:0 auto;" in result
        assert "<h2>Watch Our Tour</h2>" in result
        assert "<p>A virtual tour of our place</p>" in result

    def test_video_full_width_layout(self, renderer):
        """Full-width layout renders without max-width constraint."""
        props = {
            "title": "Full Width Video",
            "description": "No constraint",
            "video_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        }
        result = renderer.render_video(props, "full-width")

        assert 'class="section video-block"' in result
        assert "max-width:800px" not in result
        assert "<h2>Full Width Video</h2>" in result

    def test_video_uses_youtube_nocookie(self, renderer):
        """Video embed uses youtube-nocookie.com for privacy-enhanced embedding."""
        props = {
            "title": "Privacy Video",
            "video_url": "https://www.youtube.com/watch?v=abc123_XY",
        }
        result = renderer.render_video(props, "centered")

        assert "youtube-nocookie.com/embed/abc123_XY" in result
        # Must NOT use regular youtube.com for the embed
        assert "www.youtube.com/embed/" not in result

    def test_video_thumbnail_lazy_load(self, renderer):
        """Video shows YouTube thumbnail with play button, replaces on click."""
        props = {
            "title": "Lazy Video",
            "video_url": "https://www.youtube.com/watch?v=testID123",
        }
        result = renderer.render_video(props, "centered")

        # Thumbnail image from img.youtube.com
        assert "https://img.youtube.com/vi/testID123/maxresdefault.jpg" in result
        # Play button SVG
        assert '<svg width="24" height="24"' in result
        assert '<path d="M8 5v14l11-7z"/>' in result
        # Onclick replaces with iframe
        assert "onclick=" in result
        assert "youtube-nocookie.com/embed/testID123?autoplay=1" in result

    def test_video_responsive_16_9_wrapper(self, renderer):
        """Video wrapper uses padding-bottom:56.25% for 16:9 aspect ratio."""
        props = {
            "title": "Responsive",
            "video_url": "https://www.youtube.com/watch?v=resp1234",
        }
        result = renderer.render_video(props, "centered")

        assert "padding-bottom:56.25%" in result
        assert "height:0" in result
        assert "overflow:hidden" in result
        assert "position:relative" in result

    def test_video_extracts_id_from_short_url(self, renderer):
        """Video handles youtu.be short URLs correctly."""
        props = {
            "title": "Short URL",
            "video_url": "https://youtu.be/shortID_1",
        }
        result = renderer.render_video(props, "centered")

        assert "youtube-nocookie.com/embed/shortID_1" in result
        assert "img.youtube.com/vi/shortID_1/maxresdefault.jpg" in result

    def test_video_no_url_returns_empty(self, renderer):
        """Video without video_url returns empty string."""
        props = {"title": "No Video", "video_url": ""}
        result = renderer.render_video(props, "centered")
        assert result == ""

    def test_video_invalid_url_returns_empty(self, renderer):
        """Video with non-YouTube URL returns empty string."""
        props = {"title": "Invalid", "video_url": "https://vimeo.com/12345"}
        result = renderer.render_video(props, "centered")
        assert result == ""

    def test_video_no_title_omits_h2(self, renderer):
        """Video without title omits h2 element."""
        props = {
            "title": "",
            "video_url": "https://www.youtube.com/watch?v=noTitle1",
        }
        result = renderer.render_video(props, "centered")

        assert "<h2>" not in result
        assert "youtube-nocookie.com/embed/noTitle1" in result

    def test_video_no_description_omits_p(self, renderer):
        """Video without description omits p element."""
        props = {
            "title": "Title Only",
            "description": "",
            "video_url": "https://www.youtube.com/watch?v=descTest",
        }
        result = renderer.render_video(props, "centered")

        assert "<h2>Title Only</h2>" in result
        assert "<p>" not in result

    def test_video_escapes_html_in_title(self, renderer):
        """Video escapes HTML in title to prevent XSS."""
        props = {
            "title": "<script>alert('xss')</script>",
            "video_url": "https://www.youtube.com/watch?v=xssTest1",
        }
        result = renderer.render_video(props, "centered")

        assert "<script>" not in result
        assert "&lt;script&gt;" in result

    def test_video_default_layout_is_centered(self, renderer):
        """Default (empty) layout behaves as centered."""
        props = {
            "title": "Default Layout",
            "video_url": "https://www.youtube.com/watch?v=default1",
        }
        result = renderer.render_video(props, "")

        assert "max-width:800px;margin:0 auto;" in result

    def test_video_dispatch_from_render_section(self, renderer):
        """render_section dispatches 'video' to render_video."""
        props = {
            "title": "Dispatched",
            "video_url": "https://www.youtube.com/watch?v=dispatch1",
        }
        result = renderer.render_section("video", props, "centered", "test-slug")

        assert 'class="section video-block"' in result
        assert "youtube-nocookie.com/embed/dispatch1" in result

    def test_video_data_video_id_attribute(self, renderer):
        """Video div has data-video-id attribute for the video ID."""
        props = {
            "title": "Data Attr",
            "video_url": "https://www.youtube.com/watch?v=dataAttr1",
        }
        result = renderer.render_video(props, "centered")

        assert 'data-video-id="dataAttr1"' in result


class TestRenderGalleryVariants:
    """Tests for gallery section with all layout variants (Task 100).

    Verifies grid-3, grid-4, masonry, and carousel layouts render correctly.
    """

    def test_gallery_grid_3_layout(self, renderer):
        """Grid-3 layout uses gallery-grid-3 class with 3-column grid."""
        props = {
            "title": "Our Work",
            "images": [
                {"image_key": "img1.jpg", "alt": "Photo 1"},
                {"image_key": "img2.jpg", "alt": "Photo 2"},
                {"image_key": "img3.jpg", "alt": "Photo 3"},
            ],
        }
        html = renderer.render_gallery(props, "grid-3")

        assert 'class="section gallery"' in html
        assert 'class="gallery-grid-3"' in html
        assert '<h2>Our Work</h2>' in html
        assert "img1.jpg" in html
        assert "img2.jpg" in html
        assert "img3.jpg" in html

    def test_gallery_grid_4_layout(self, renderer):
        """Grid-4 layout uses gallery-grid-4 class with 4-column grid."""
        props = {
            "title": "Portfolio",
            "images": [
                {"image_key": "a.jpg", "alt": "A"},
                {"image_key": "b.jpg", "alt": "B"},
                {"image_key": "c.jpg", "alt": "C"},
                {"image_key": "d.jpg", "alt": "D"},
            ],
        }
        html = renderer.render_gallery(props, "grid-4")

        assert 'class="gallery-grid-4"' in html
        assert "a.jpg" in html
        assert "d.jpg" in html

    def test_gallery_masonry_layout(self, renderer):
        """Masonry layout uses gallery-masonry class with CSS columns."""
        props = {
            "title": "Masonry",
            "images": [
                {"image_key": "m1.jpg", "alt": "M1"},
                {"image_key": "m2.jpg", "alt": "M2"},
            ],
        }
        html = renderer.render_gallery(props, "masonry")

        assert 'class="gallery-masonry"' in html
        assert "m1.jpg" in html
        assert "m2.jpg" in html

    def test_gallery_carousel_layout_structure(self, renderer):
        """Carousel layout renders data-carousel container with track, buttons, dots."""
        props = {
            "title": "Slideshow",
            "images": [
                {"image_key": "s1.jpg", "alt": "Slide 1"},
                {"image_key": "s2.jpg", "alt": "Slide 2"},
                {"image_key": "s3.jpg", "alt": "Slide 3"},
            ],
        }
        html = renderer.render_gallery(props, "carousel")

        assert 'data-carousel' in html
        assert 'data-carousel-track' in html
        assert 'data-carousel-prev' in html
        assert 'data-carousel-next' in html
        assert 'carousel-dots' in html
        assert 'carousel-slide' in html

    def test_gallery_carousel_dots_match_slides(self, renderer):
        """Carousel renders one dot per slide, first dot active."""
        props = {
            "title": "",
            "images": [
                {"image_key": "a.jpg", "alt": "A"},
                {"image_key": "b.jpg", "alt": "B"},
                {"image_key": "c.jpg", "alt": "C"},
            ],
        }
        html = renderer.render_gallery(props, "carousel")

        assert html.count('data-carousel-dot') == 3
        assert 'data-index="0"' in html
        assert 'data-index="1"' in html
        assert 'data-index="2"' in html
        # First dot is active
        assert 'carousel-dot active' in html

    def test_gallery_carousel_auto_advance_timing(self, renderer):
        """Carousel JS uses 10-second (10000ms) auto-advance interval."""
        from services.landing_page_styles import LandingPageStyles

        js = LandingPageStyles.build_carousel_js()

        assert "10000" in js
        assert "setInterval" in js

    def test_gallery_default_layout_is_grid_3(self, renderer):
        """Default/unrecognized layout falls back to grid-3."""
        props = {
            "title": "",
            "images": [{"image_key": "x.jpg", "alt": "X"}],
        }
        html = renderer.render_gallery(props, "default")

        assert 'class="gallery-grid-3"' in html

    def test_gallery_empty_images_returns_empty(self, renderer):
        """Gallery with no images returns empty string."""
        props = {"title": "Empty", "images": []}
        assert renderer.render_gallery(props, "grid-3") == ""

    def test_gallery_skips_images_without_key(self, renderer):
        """Gallery skips images that have no image_key."""
        props = {
            "title": "",
            "images": [
                {"image_key": "valid.jpg", "alt": "Valid"},
                {"image_key": "", "alt": "Empty"},
                {"alt": "No key"},
            ],
        }
        html = renderer.render_gallery(props, "grid-3")

        assert "valid.jpg" in html
        # Empty key and missing key should be skipped
        assert html.count("<img") == 1

    def test_gallery_escapes_alt_text(self, renderer):
        """Gallery escapes HTML in alt attributes."""
        props = {
            "title": "",
            "images": [{"image_key": "x.jpg", "alt": '<img onerror="alert(1)">'}],
        }
        html = renderer.render_gallery(props, "grid-3")

        assert 'onerror="alert(1)"' not in html
        assert "&lt;img" in html


class TestCarouselJsBehaviour:
    """Tests for carousel JS pause/resume behaviour (Task 104).

    Verifies the inline carousel JavaScript contains the correct patterns
    for auto-advance, pause on hover, resume on leave, and interaction handling.
    """

    def test_carousel_js_mouseenter_pauses(self):
        """Carousel JS adds mouseenter listener to pause auto-advance."""
        from services.landing_page_styles import LandingPageStyles

        js = LandingPageStyles.build_carousel_js()

        assert "mouseenter" in js
        assert "stopAuto" in js

    def test_carousel_js_mouseleave_resumes(self):
        """Carousel JS adds mouseleave listener to resume auto-advance."""
        from services.landing_page_styles import LandingPageStyles

        js = LandingPageStyles.build_carousel_js()

        assert "mouseleave" in js
        assert "startAuto" in js

    def test_carousel_js_click_pauses_and_schedules_resume(self):
        """Prev/next/dot clicks stop auto-advance and schedule resume after delay."""
        from services.landing_page_styles import LandingPageStyles

        js = LandingPageStyles.build_carousel_js()

        # Click handlers exist for prev, next, dot
        assert "prev" in js
        assert "next" in js
        assert "dot" in js
        # On click: stop auto and schedule resume
        assert "scheduleResume" in js
        # scheduleResume uses setTimeout with DELAY
        assert "setTimeout" in js

    def test_carousel_js_10s_delay_constant(self):
        """Carousel uses DELAY = 10000 (10 seconds) for auto-advance and resume."""
        from services.landing_page_styles import LandingPageStyles

        js = LandingPageStyles.build_carousel_js()

        assert "DELAY = 10000" in js

    def test_carousel_js_touch_swipe_support(self):
        """Carousel JS supports touch swipe via pointer events."""
        from services.landing_page_styles import LandingPageStyles

        js = LandingPageStyles.build_carousel_js()

        assert "pointerdown" in js
        assert "pointerup" in js
        # 50px threshold
        assert "50" in js

    def test_carousel_js_wrapped_in_script_tag(self):
        """Carousel JS is wrapped in a <script> tag."""
        from services.landing_page_styles import LandingPageStyles

        js = LandingPageStyles.build_carousel_js()

        assert js.startswith("<script>")
        assert js.strip().endswith("</script>")

    def test_carousel_js_uses_data_attributes(self):
        """Carousel JS targets elements via data-carousel attributes."""
        from services.landing_page_styles import LandingPageStyles

        js = LandingPageStyles.build_carousel_js()

        assert "[data-carousel]" in js
        assert "[data-carousel-track]" in js
        assert "[data-carousel-prev]" in js
        assert "[data-carousel-next]" in js
        assert "[data-carousel-dot]" in js

    def test_carousel_html_has_data_attributes_for_js(self, renderer):
        """Gallery carousel HTML output contains all data attributes that JS needs."""
        props = {
            "title": "Gallery",
            "images": [
                {"image_key": "a.jpg", "alt": "A"},
                {"image_key": "b.jpg", "alt": "B"},
            ],
        }
        html = renderer.render_gallery(props, "carousel")

        # All data attributes that the JS uses to find elements
        assert 'data-carousel' in html
        assert 'data-carousel-track' in html
        assert 'data-carousel-prev' in html
        assert 'data-carousel-next' in html
        assert 'data-carousel-dot' in html
