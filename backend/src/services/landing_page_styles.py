"""
Landing page style/CSS utilities.

Extracted from landing_page_publish_service.py to keep files under 500 lines.
Contains gradient/theme presets, CSS generation, and WCAG contrast utilities.
"""

import re
from typing import ClassVar


class LandingPageStyles:
    """CSS generation utilities for landing page publishing."""

    # ─── Gradient Presets ───────────────────────────────────────────────────

    GRADIENT_PRESETS: ClassVar[list[dict[str, str]]] = [
        {
            "name": "Sunset",
            "value": "linear-gradient(135deg, #667eea 0%, #764ba2 100%)",
        },
        {"name": "Ocean", "value": "linear-gradient(135deg, #2193b0 0%, #6dd5ed 100%)"},
        {
            "name": "Forest",
            "value": "linear-gradient(135deg, #134e5e 0%, #71b280 100%)",
        },
        {"name": "Peach", "value": "linear-gradient(135deg, #ffecd2 0%, #fcb69f 100%)"},
        {
            "name": "Night",
            "value": "linear-gradient(135deg, #0f0c29 0%, #302b63 50%, #24243e 100%)",
        },
        {"name": "Warm", "value": "linear-gradient(135deg, #f093fb 0%, #f5576c 100%)"},
        {"name": "Sky", "value": "linear-gradient(135deg, #a1c4fd 0%, #c2e9fb 100%)"},
        {"name": "Gold", "value": "linear-gradient(135deg, #f7971e 0%, #ffd200 100%)"},
    ]

    # ─── Theme Presets ──────────────────────────────────────────────────────

    THEME_PRESETS: ClassVar[dict[str, dict[str, str]]] = {
        "professional": {
            "color_primary": "#2D5F8A",
            "color_accent": "#F4A261",
            "section_bg": "#ffffff",
            "font_heading": "Inter",
            "font_body": "Inter",
        },
        "warm": {
            "color_primary": "#8B4513",
            "color_accent": "#DAA520",
            "section_bg": "#FFF8F0",
            "font_heading": "Lora",
            "font_body": "Nunito",
        },
        "modern": {
            "color_primary": "#1a1a2e",
            "color_accent": "#e94560",
            "section_bg": "#16213e",
            "font_heading": "Poppins",
            "font_body": "Poppins",
        },
        "nature": {
            "color_primary": "#2d6a4f",
            "color_accent": "#95d5b2",
            "section_bg": "#f0f7f4",
            "font_heading": "Nunito",
            "font_body": "Nunito",
        },
        "minimal": {
            "color_primary": "#333333",
            "color_accent": "#666666",
            "section_bg": "#ffffff",
            "font_heading": "system",
            "font_body": "system",
        },
        "luxury": {
            "color_primary": "#1c1c1c",
            "color_accent": "#c9a96e",
            "section_bg": "#0d0d0d",
            "font_heading": "Playfair Display",
            "font_body": "Lato",
        },
    }

    # ─── Padding / Radius / Text Colour Maps ───────────────────────────────

    PADDING_MAP: ClassVar[dict[str, str]] = {
        "compact": "1rem 1.5rem",
        "normal": "2rem 1.5rem",
        "spacious": "4rem 1.5rem",
    }

    TEXT_COLOR_MAP: ClassVar[dict[str, str]] = {
        "dark": "#333",
        "light": "#fff",
        "auto": "inherit",
    }

    BORDER_RADIUS_MAP: ClassVar[dict[str, str]] = {
        "none": "0",
        "sm": "8px",
        "md": "16px",
        "lg": "24px",
    }

    # ─── Spacing / Radius / Shadow mappings for CSS variables ───────────────

    SPACING_MAP: ClassVar[dict[str, dict[str, str]]] = {
        "compact": {"section": "1.5rem", "element": "0.75rem"},
        "normal": {"section": "2rem", "element": "1rem"},
        "relaxed": {"section": "3rem", "element": "1.5rem"},
    }

    GLOBAL_RADIUS_MAP: ClassVar[dict[str, dict[str, str]]] = {
        "sharp": {"sm": "0", "md": "0", "lg": "0"},
        "rounded": {"sm": "4px", "md": "8px", "lg": "16px"},
        "pill": {"sm": "12px", "md": "24px", "lg": "9999px"},
    }

    SHADOW_MAP: ClassVar[dict[str, dict[str, str]]] = {
        "none": {"card": "none", "hover": "none"},
        "subtle": {
            "card": "0 2px 8px rgba(0,0,0,0.08)",
            "hover": "0 4px 16px rgba(0,0,0,0.12)",
        },
        "medium": {
            "card": "0 4px 12px rgba(0,0,0,0.12)",
            "hover": "0 8px 24px rgba(0,0,0,0.18)",
        },
        "dramatic": {
            "card": "0 8px 24px rgba(0,0,0,0.2)",
            "hover": "0 16px 48px rgba(0,0,0,0.28)",
        },
    }

    # ─── Dangerous CSS patterns (security) ──────────────────────────────────

    _UNSAFE_PATTERN = re.compile(
        r"(url\s*\(|expression\s*\(|javascript\s*:)", re.IGNORECASE
    )

    # ─── Public Methods ─────────────────────────────────────────────────────

    @staticmethod
    def build_section_style(settings: dict, img_base: str) -> str:
        """
        Generate inline CSS string from block settings.

        Args:
            settings: Block-level visual settings dict.
            img_base: CloudFront base URL for images.

        Returns:
            Semicolon-separated CSS properties string.
        """
        if not settings:
            return ""

        styles: list[str] = []

        # Background
        bg_type = settings.get("background_type", "color")
        if bg_type == "color":
            color = settings.get("background_color", "")
            if color and color != "transparent":
                styles.append(f"background-color: {color}")
        elif bg_type == "gradient":
            gradient = settings.get("background_gradient", "")
            if gradient:
                safe_gradient = LandingPageStyles.sanitize_gradient(gradient)
                styles.append(f"background: {safe_gradient}")
        elif bg_type == "image":
            image_key = settings.get("background_image_key", "")
            if image_key:
                if image_key.startswith("http"):
                    url = image_key
                else:
                    url = f"{img_base}/{image_key}" if img_base else image_key
                styles.append(f"background-image: url('{url}')")
                styles.append("background-size: cover")
                styles.append("background-position: center")

        # Padding
        padding = settings.get("padding", "normal")
        padding_value = LandingPageStyles.PADDING_MAP.get(padding, "2rem 1.5rem")
        styles.append(f"padding: {padding_value}")

        # Text colour
        text_color = settings.get("text_color", "dark")
        if text_color == "auto":
            # For auto: compute from background colour if available
            if bg_type == "color":
                bg_color = settings.get("background_color", "")
                if bg_color and len(bg_color) == 7 and bg_color.startswith("#"):
                    resolved = LandingPageStyles.auto_text_color(bg_color)
                    css_color = LandingPageStyles.TEXT_COLOR_MAP.get(resolved, "#333")
                    styles.append(f"color: {css_color}")
            # For gradient/image with auto: default to dark (safe fallback)
            else:
                styles.append("color: #333")
        elif text_color != "dark" or settings.get("background_type") != "color":
            # Only set explicit colour if non-default or non-standard background
            css_color = LandingPageStyles.TEXT_COLOR_MAP.get(text_color, "#333")
            styles.append(f"color: {css_color}")

        # Border radius
        radius = settings.get("border_radius", "none")
        if radius != "none":
            radius_value = LandingPageStyles.BORDER_RADIUS_MAP.get(radius, "0")
            styles.append(f"border-radius: {radius_value}")

        return "; ".join(styles)

    @staticmethod
    def auto_text_color(bg_hex: str) -> str:
        """
        Return 'dark' or 'light' based on WCAG relative luminance of background.

        Uses the W3C relative luminance formula to determine whether light or
        dark text provides better contrast against the given background colour.
        The threshold (0.18) is chosen to maximize WCAG AA (4.5:1) compliance:
        white text is only used on very dark backgrounds where it guarantees AA.

        Args:
            bg_hex: Hex colour string (e.g. '#ffffff').

        Returns:
            'light' if background is dark (needs white text),
            'dark' if background is light (needs dark text).
        """
        if not bg_hex or len(bg_hex) != 7 or not bg_hex.startswith("#"):
            return "dark"  # safe fallback

        try:
            r = int(bg_hex[1:3], 16)
            g = int(bg_hex[3:5], 16)
            b = int(bg_hex[5:7], 16)
        except ValueError:
            return "dark"

        def linearize(c: int) -> float:
            """Convert sRGB channel (0-255) to linear RGB."""
            s = c / 255.0
            return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4

        luminance = (
            0.2126 * linearize(r) + 0.7152 * linearize(g) + 0.0722 * linearize(b)
        )
        # Use WCAG-optimal threshold: white text (#fff) meets AA (4.5:1) only
        # when background luminance ≤ ~0.1791.  Dark text (#333, lum≈0.0304)
        # meets AA when background luminance ≥ ~0.312.  In the gap (0.18-0.31)
        # neither is guaranteed AA, so pick the one with better contrast.
        # Crossover point where dark text becomes better: luminance ≈ 0.1791.
        # We use 0.18 as a practical threshold that maximizes WCAG compliance.
        return "light" if luminance < 0.18 else "dark"

    @staticmethod
    def build_font_links(branding: dict) -> str:
        """
        Generate Google Font <link> tags based on branding fonts.

        Only loads fonts that are actually selected (not 'system').

        Args:
            branding: Resolved branding dict with font_heading / font_body.

        Returns:
            HTML string with preconnect + stylesheet links, or empty string.
        """
        fonts: set[str] = set()
        for key in ("font_heading", "font_body"):
            font = branding.get(key, "")
            if font and font.lower() != "system":
                fonts.add(font)

        if not fonts:
            return ""

        families = "&family=".join(
            f.replace(" ", "+") + ":wght@400;600;700" for f in sorted(fonts)
        )
        return (
            '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
            '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
            f'<link href="https://fonts.googleapis.com/css2?family={families}&display=swap" rel="stylesheet">'
        )

    @staticmethod
    def build_css_variables(branding: dict) -> str:
        """
        Generate CSS :root variables block from branding settings.

        Produces font-family, spacing, border-radius, and shadow variables.

        Args:
            branding: Resolved branding dict with typography/spacing fields.

        Returns:
            CSS string (without <style> tags) defining :root variables.
        """
        lines: list[str] = [":root {"]

        # Font families
        font_heading = branding.get("font_heading", "system")
        font_body = branding.get("font_body", "system")
        heading_family = (
            f'"{font_heading}", sans-serif'
            if font_heading.lower() != "system"
            else "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
        )
        body_family = (
            f'"{font_body}", sans-serif'
            if font_body.lower() != "system"
            else "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
        )
        lines.append(f"  --font-heading: {heading_family};")
        lines.append(f"  --font-body: {body_family};")

        # Spacing
        base_spacing = branding.get("base_spacing", "normal")
        spacing = LandingPageStyles.SPACING_MAP.get(
            base_spacing, LandingPageStyles.SPACING_MAP["normal"]
        )
        lines.append(f"  --spacing-section: {spacing['section']};")
        lines.append(f"  --spacing-element: {spacing['element']};")

        # Border radius
        radius_global = branding.get("border_radius_global", "rounded")
        radii = LandingPageStyles.GLOBAL_RADIUS_MAP.get(
            radius_global, LandingPageStyles.GLOBAL_RADIUS_MAP["rounded"]
        )
        lines.append(f"  --radius-sm: {radii['sm']};")
        lines.append(f"  --radius-md: {radii['md']};")
        lines.append(f"  --radius-lg: {radii['lg']};")

        # Shadows
        shadow_style = branding.get("shadow_style", "subtle")
        shadows = LandingPageStyles.SHADOW_MAP.get(
            shadow_style, LandingPageStyles.SHADOW_MAP["subtle"]
        )
        lines.append(f"  --shadow-card: {shadows['card']};")
        lines.append(f"  --shadow-hover: {shadows['hover']};")

        lines.append("}")
        return "\n".join(lines)

    @staticmethod
    def sanitize_gradient(gradient: str) -> str:
        """
        Strip dangerous CSS patterns from a gradient string for security.

        Removes url(), expression(), and javascript: to prevent CSS injection.

        Args:
            gradient: Raw CSS gradient string from user input.

        Returns:
            Sanitized gradient string safe for inline style use.
        """
        if not gradient:
            return ""
        return LandingPageStyles._UNSAFE_PATTERN.sub("", gradient)

    @staticmethod
    def build_carousel_js() -> str:
        """
        Generate inline carousel JavaScript for published landing pages.

        Features (Tasks 95 & 96):
        - Auto-advances every 10 seconds
        - Pauses on hover (mouseenter) and resumes on mouseleave
        - Pauses on interaction (prev/next/dot click), resumes after 10s idle
        - Touch swipe support via pointer events (swipe > 50px threshold)

        Works with any element having [data-carousel] attribute and matching
        child elements: [data-carousel-track], [data-carousel-prev],
        [data-carousel-next], [data-carousel-dot].

        Returns:
            Complete <script> tag string for embedding before </body>.
        """
        return """<script>
(function() {
  document.querySelectorAll('[data-carousel]').forEach(function(carousel) {
    var track = carousel.querySelector('[data-carousel-track]');
    var slides = track.children;
    var dots = carousel.querySelectorAll('[data-carousel-dot]');
    var current = 0;
    var interval = null;
    var resumeTimeout = null;
    var DELAY = 10000;

    function goTo(idx) {
      current = ((idx % slides.length) + slides.length) % slides.length;
      track.style.transform = 'translateX(-' + (current * 100) + '%)';
      dots.forEach(function(d, i) { d.classList.toggle('active', i === current); });
    }

    function startAuto() { stopAuto(); interval = setInterval(function() { goTo(current + 1); }, DELAY); }
    function stopAuto() { if (interval) { clearInterval(interval); interval = null; } }
    function scheduleResume() { if (resumeTimeout) { clearTimeout(resumeTimeout); } resumeTimeout = setTimeout(startAuto, DELAY); }

    var prev = carousel.querySelector('[data-carousel-prev]');
    var next = carousel.querySelector('[data-carousel-next]');
    if (prev) prev.onclick = function() { goTo(current - 1); stopAuto(); scheduleResume(); };
    if (next) next.onclick = function() { goTo(current + 1); stopAuto(); scheduleResume(); };
    dots.forEach(function(dot, i) { dot.onclick = function() { goTo(i); stopAuto(); scheduleResume(); }; });
    carousel.addEventListener('mouseenter', stopAuto);
    carousel.addEventListener('mouseleave', startAuto);

    // Touch swipe support (pointer events)
    var startX = 0;
    carousel.addEventListener('pointerdown', function(e) { startX = e.clientX; });
    carousel.addEventListener('pointerup', function(e) {
      var diff = e.clientX - startX;
      if (Math.abs(diff) > 50) { goTo(current + (diff > 0 ? -1 : 1)); stopAuto(); scheduleResume(); }
    });

    startAuto();
  });
})();
</script>"""

    @staticmethod
    def build_page_css(color_primary: str, color_accent: str) -> str:
        """
        Generate the full inline CSS for the published landing page.

        Uses CSS variables (--font-body, --font-heading, --spacing-section,
        --radius-md, --shadow-card) defined in :root by build_css_variables().
        Colour theming via color_primary/color_accent params remains inline.

        Args:
            color_primary: Primary brand colour (hex).
            color_accent: Accent brand colour (hex).

        Returns:
            CSS string (without <style> tags) for embedding in the HTML.
        """
        return f"""    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{ font-family: var(--font-body); color: #333; line-height: 1.6; }}
    img {{ max-width: 100%; height: auto; display: block; }}
    .section {{ padding: var(--spacing-section) 1.5rem; }}
    .container {{ max-width: 1100px; margin: 0 auto; }}
    .hero {{ display: flex; flex-wrap: wrap; align-items: center; gap: var(--spacing-element); }}
    .hero-text {{ flex: 1; min-width: 280px; }}
    .hero-img {{ flex: 1; min-width: 280px; }}
    .hero h1 {{ font-family: var(--font-heading); font-size: 2.5rem; font-weight: 700; margin-bottom: 0.5rem; color: {color_primary}; }}
    .hero p {{ font-size: 1.2rem; color: #555; margin-bottom: 1rem; }}
    .btn {{ display: inline-block; padding: 0.75rem 1.5rem; background: {color_accent}; color: #fff; text-decoration: none; border-radius: var(--radius-sm); font-weight: 600; }}
    .btn:hover {{ opacity: 0.9; }}
    .about {{ background: #f9f9f9; }}
    .about-content {{ display: flex; flex-wrap: wrap; align-items: center; gap: var(--spacing-element); }}
    .about-text {{ flex: 1; min-width: 280px; }}
    .about-text h2 {{ font-family: var(--font-heading); font-size: 1.8rem; font-weight: 700; margin-bottom: 1rem; color: {color_primary}; }}
    .about-text p {{ margin-bottom: 0.75rem; color: #555; }}
    .about-img {{ flex: 1; min-width: 280px; }}
    .about-img img {{ border-radius: var(--radius-md); }}
    .gallery {{ text-align: center; }}
    .gallery h2 {{ font-family: var(--font-heading); font-size: 1.8rem; font-weight: 700; margin-bottom: 1.5rem; color: {color_primary}; }}
    .gallery-grid-3 {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 1rem; }}
    .gallery-grid-4 {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 1rem; }}
    .gallery-masonry {{ columns: 3; column-gap: 1rem; }}
    .gallery-masonry img {{ break-inside: avoid; margin-bottom: 1rem; }}
    .gallery-grid-3 img, .gallery-grid-4 img {{ border-radius: var(--radius-md); width: 100%; height: auto; object-fit: contain; }}
    .gallery-masonry img {{ border-radius: var(--radius-md); width: 100%; height: auto; }}
    .carousel {{ position: relative; overflow: hidden; border-radius: var(--radius-md); max-width: 800px; margin: 0 auto; }}
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
    .cta h2 {{ font-family: var(--font-heading); font-size: 2rem; margin-bottom: 0.5rem; }}
    .cta p {{ font-size: 1.1rem; margin-bottom: 1.5rem; opacity: 0.9; }}
    .cta .btn {{ background: {color_accent}; }}
    .faq {{ background: #f9f9f9; }}
    .faq h2 {{ font-family: var(--font-heading); font-size: 1.8rem; font-weight: 700; margin-bottom: 1.5rem; color: {color_primary}; text-align: center; }}
    .faq-grid {{ display: grid; grid-template-columns: 1fr; gap: 0 2rem; }}
    @media (min-width: 769px) {{ .faq-grid {{ grid-template-columns: repeat(2, 1fr); }} }}
    .faq-item {{ border-bottom: 1px solid #ddd; padding: 0.4rem 0; margin: 0; display: block; }}
    .faq-item:last-child {{ border-bottom: none; padding-bottom: 0; }}
    .faq-item summary {{ font-weight: 600; cursor: pointer; font-size: 1.05rem; margin: 0; padding: 0; }}
    .faq-item p {{ margin: 0.2rem 0 0.2rem 0; padding: 0; color: #555; line-height: 1.4; }}
    .faq-item[open] summary {{ margin-bottom: 0; }}
    .testimonials {{ text-align: center; }}
    .testimonials h2 {{ font-family: var(--font-heading); font-size: 1.8rem; font-weight: 700; margin-bottom: 1.5rem; color: {color_primary}; }}
    .testimonial-cards {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 1.5rem; }}
    .testimonial-card {{ background: #f9f9f9; padding: 1.5rem; border-radius: var(--radius-md); text-align: left; box-shadow: var(--shadow-card); }}
    .testimonial-card blockquote {{ font-style: italic; color: #555; margin-bottom: 0.75rem; }}
    .testimonial-card cite {{ font-weight: 600; color: {color_primary}; }}
    .contact {{ background: #f9f9f9; }}
    .contact h2 {{ font-family: var(--font-heading); font-size: 1.8rem; font-weight: 700; margin-bottom: 1rem; color: {color_primary}; text-align: center; }}
    .contact form {{ max-width: 500px; margin: 0 auto; }}
    .contact input, .contact textarea {{ width: 100%; padding: 0.75rem; margin-bottom: 1rem; border: 1px solid #ddd; border-radius: var(--radius-sm); font-size: 1rem; }}
    .contact textarea {{ min-height: 120px; resize: vertical; }}
    .contact button {{ width: 100%; padding: 0.75rem; background: {color_accent}; color: #fff; border: none; border-radius: var(--radius-md); font-size: 1rem; font-weight: 600; cursor: pointer; }}
    .embed-block iframe {{ width: 100%; border: none; border-radius: var(--radius-md); }}
    .pricing h2 {{ font-family: var(--font-heading); font-size: 1.8rem; font-weight: 700; margin-bottom: 1.5rem; color: {color_primary}; text-align: center; }}
    .pricing-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 1.5rem; }}
    .pricing-card {{ background: #f9f9f9; padding: 1.5rem; border-radius: var(--radius-md); text-align: center; border: 1px solid #eee; box-shadow: var(--shadow-card); }}
    .pricing-card h3 {{ color: {color_primary}; margin-bottom: 0.5rem; }}
    .pricing-card .price {{ font-size: 1.5rem; font-weight: 700; color: {color_accent}; margin-bottom: 0.5rem; }}
    footer {{ background: #222; color: #ccc; padding: 2rem 1.5rem; text-align: center; font-size: 0.9rem; }}
    footer a {{ color: {color_accent}; text-decoration: none; }}
    @media (max-width: 768px) {{
      .hero h1 {{ font-size: 1.8rem; }}
      .section {{ padding: 1.5rem 1rem; }}
    }}"""
