"""
Landing Page Renderers

Section HTML renderers for the landing page publish pipeline.
Extracted from landing_page_publish_service.py to keep files under 500 lines.

Each render method converts a section's properties and layout into
standalone static HTML served directly from S3/CloudFront.
"""

import html
import os
import re

from services.landing_page_styles import LandingPageStyles


class LandingPageRenderers:
    """Section HTML renderers for the landing page publish pipeline."""

    def __init__(self, img_base: str, color_accent: str, color_primary: str):
        self.img_base = img_base
        self.color_accent = color_accent
        self.color_primary = color_primary

    # ========================================================================
    # Section Dispatch
    # ========================================================================

    def render_sections_html(self, sections: list, slug: str) -> str:
        """Render all sections to static HTML.

        Each section's optional ``settings`` dict is used to generate an inline
        style on the wrapping ``<section>`` element via
        ``LandingPageStyles.build_section_style``.  When settings are absent or
        empty, the section renders exactly as before (no style attribute, default
        container class) preserving backwards compatibility.
        """
        parts = []
        for section in sections:
            section_type = section.get("type", "")
            props = section.get("properties", {})
            layout = section.get("layout", "")
            settings = section.get("settings", {})

            # Generate section wrapper with settings-based inline style
            wrapper_style = LandingPageStyles.build_section_style(
                settings, self.img_base
            )

            content_html = self.render_section(section_type, props, layout, slug)
            if content_html:
                if wrapper_style:
                    # Settings present — apply styled wrapper
                    max_width = settings.get("max_width", "contained")
                    container_class = "container" if max_width == "contained" else ""
                    style_attr = f' style="{wrapper_style}"'

                    # Separate any trailing <script> blocks from section HTML
                    section_part, script_part = self._split_script(content_html)

                    # Extract original CSS classes from the section wrapper
                    orig_classes = self._extract_section_classes(section_part)

                    # Merge classes: always include 'section', preserve originals
                    all_classes = {"section"}
                    all_classes.update(orig_classes)
                    class_str = " ".join(sorted(all_classes))

                    # Extract original id attribute if present
                    orig_id = self._extract_section_id(section_part)
                    id_attr = f' id="{orig_id}"' if orig_id else ""

                    # Strip the existing wrapper to get inner content
                    inner = self._strip_section_wrapper(section_part)

                    parts.append(
                        f'<section{id_attr} class="{class_str}"{style_attr}>'
                        f'<div class="{container_class}">{inner}</div>'
                        f"</section>"
                    )
                    if script_part:
                        parts.append(script_part)
                else:
                    # No settings — render as-is
                    parts.append(content_html)
        return "\n".join(parts)

    @staticmethod
    def _strip_section_wrapper(html_str: str) -> str:
        """Strip outer <section ...>...</section> wrapper if present.

        Returns the inner content (everything between the opening and closing
        section tags). If the content also has a <div class="container"> wrapper
        immediately inside, that is stripped too so the caller can apply its own
        container class.
        """
        stripped = html_str.strip()
        if not stripped.startswith("<section"):
            return html_str

        # Remove opening <section ...> tag
        close_bracket = stripped.index(">")
        inner = stripped[close_bracket + 1 :]

        # Remove closing </section> tag
        if inner.rstrip().endswith("</section>"):
            inner = inner.rstrip()[: -len("</section>")]

        # Strip container div wrapper if present
        inner_stripped = inner.strip()
        container_match = re.match(
            r'^<div class="container">\s*(.*?)\s*</div>$',
            inner_stripped,
            re.DOTALL,
        )
        if container_match:
            inner = container_match.group(1)

        return inner

    @staticmethod
    def _split_script(html_str: str) -> tuple:
        """Split trailing <script>...</script> from section HTML.

        Returns (section_html, script_html). script_html is empty string
        if no script block follows the section.
        """
        # Find </section> followed by <script>
        idx = html_str.find("</section>")
        if idx == -1:
            return html_str, ""
        end_section = idx + len("</section>")
        remainder = html_str[end_section:].strip()
        if remainder.startswith("<script"):
            return html_str[:end_section], remainder
        return html_str, ""

    @staticmethod
    def _extract_section_classes(html_str: str) -> set:
        """Extract CSS classes from the opening <section> tag."""
        stripped = html_str.strip()
        if not stripped.startswith("<section"):
            return set()
        close_bracket = stripped.index(">")
        opening_tag = stripped[: close_bracket + 1]
        match = re.search(r'class="([^"]*)"', opening_tag)
        if match:
            return set(match.group(1).split())
        return set()

    @staticmethod
    def _extract_section_id(html_str: str) -> str:
        """Extract id attribute from the opening <section> tag."""
        stripped = html_str.strip()
        if not stripped.startswith("<section"):
            return ""
        close_bracket = stripped.index(">")
        opening_tag = stripped[: close_bracket + 1]
        match = re.search(r'id="([^"]*)"', opening_tag)
        return match.group(1) if match else ""

    def render_section(
        self, section_type: str, props: dict, layout: str, slug: str
    ) -> str:
        """Render a single section by dispatching to type-specific renderer."""
        if section_type == "hero":
            return self.render_hero(props, layout)
        elif section_type == "about":
            return self.render_about(props, layout)
        elif section_type == "gallery":
            return self.render_gallery(props, layout)
        elif section_type == "cta":
            return self.render_cta(props, layout)
        elif section_type == "faq":
            return self.render_faq(props, layout)
        elif section_type == "testimonials":
            return self.render_testimonials(props, layout)
        elif section_type == "contact":
            return self.render_contact(props, slug)
        elif section_type == "embed":
            return self.render_embed(props)
        elif section_type == "pricing":
            return self.render_pricing(props, layout)
        elif section_type == "video":
            return self.render_video(props, layout)
        return ""

    # ========================================================================
    # Helper
    # ========================================================================

    def _img_url(self, image_key: str) -> str:
        """Build full image URL from an S3 key."""
        if not image_key:
            return ""
        if image_key.startswith("http"):
            return image_key
        return f"{self.img_base}/{image_key}" if self.img_base else image_key

    # ========================================================================
    # Hero
    # ========================================================================

    def render_hero(self, props: dict, layout: str) -> str:
        """Render hero section.

        Supports layouts: default (image-right), image-left, image-bg,
        split-diagonal, video-bg.
        """
        title = html.escape(props.get("title", ""))
        subtitle = html.escape(props.get("subtitle", ""))
        cta_text = html.escape(props.get("cta_text", ""))
        cta_url = html.escape(props.get("cta_url", "#"))
        image_key = props.get("image_key", "")
        img_url = self._img_url(image_key)

        if layout == "image-bg":
            return self._render_hero_image_bg(
                title, subtitle, cta_text, cta_url, img_url
            )
        elif layout == "split-diagonal":
            return self._render_hero_split_diagonal(
                title, subtitle, cta_text, cta_url, img_url
            )
        elif layout == "video-bg":
            return self._render_hero_video_bg(title, subtitle, cta_text, cta_url, props)

        # Default / image-left layout
        img_html = (
            f'<div class="hero-img"><img src="{img_url}" alt="{title}"></div>'
            if img_url
            else ""
        )
        btn_html = f'<a href="{cta_url}" class="btn">{cta_text}</a>' if cta_text else ""
        sub_html = f"<p>{subtitle}</p>" if subtitle else ""

        direction = (
            "" if layout != "image-left" else ' style="flex-direction: row-reverse;"'
        )

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

    def _render_hero_image_bg(
        self, title: str, subtitle: str, cta_text: str, cta_url: str, img_url: str
    ) -> str:
        """Render hero with full-bleed background image and text overlay."""
        sub_html = f'<p style="color:#eee;">{subtitle}</p>' if subtitle else ""
        btn_html = f'<a href="{cta_url}" class="btn">{cta_text}</a>' if cta_text else ""

        return (
            f'<section class="section hero-image-bg" style="background-image:url(\'{img_url}\');'
            f"background-size:cover;background-position:center;min-height:500px;"
            f'display:flex;align-items:center;">\n'
            f'  <div class="container hero-overlay" style="background:rgba(0,0,0,0.5);'
            f'padding:3rem;border-radius:8px;">\n'
            f'    <h1 style="color:#fff;">{title}</h1>\n'
            f"    {sub_html}\n"
            f"    {btn_html}\n"
            f"  </div>\n"
            f"</section>"
        )

    def _render_hero_split_diagonal(
        self, title: str, subtitle: str, cta_text: str, cta_url: str, img_url: str
    ) -> str:
        """Render hero with diagonal clip-path split between image and text."""
        sub_html = f"<p>{subtitle}</p>" if subtitle else ""
        btn_html = f'<a href="{cta_url}" class="btn">{cta_text}</a>' if cta_text else ""

        return (
            f'<section class="section hero-split" style="display:flex;min-height:500px;'
            f'position:relative;overflow:hidden;">\n'
            f'  <div style="flex:1;padding:3rem;display:flex;flex-direction:column;'
            f'justify-content:center;">\n'
            f"    <h1>{title}</h1>\n"
            f"    {sub_html}\n"
            f"    {btn_html}\n"
            f"  </div>\n"
            f'  <div style="flex:1;clip-path:polygon(15% 0, 100% 0, 100% 100%, 0% 100%);'
            f"background-image:url('{img_url}');background-size:cover;"
            f'background-position:center;">\n'
            f"  </div>\n"
            f"</section>"
        )

    def _render_hero_video_bg(
        self, title: str, subtitle: str, cta_text: str, cta_url: str, props: dict
    ) -> str:
        """Render hero with YouTube embed (autoplay, muted, looped) background."""
        video_url = props.get("video_url", "")
        video_id = self._extract_youtube_id(video_url)
        sub_html = f'<p style="color:#eee;">{subtitle}</p>' if subtitle else ""
        btn_html = f'<a href="{cta_url}" class="btn">{cta_text}</a>' if cta_text else ""

        iframe_html = ""
        if video_id:
            iframe_html = (
                f'<iframe src="https://www.youtube.com/embed/{video_id}'
                f"?autoplay=1&mute=1&loop=1&playlist={video_id}&controls=0"
                f'&rel=0&modestbranding=1&showinfo=0&iv_load_policy=3&disablekb=1" '
                f'style="position:absolute;top:50%;left:50%;min-width:100%;'
                f'min-height:100%;transform:translate(-50%,-50%);" '
                f'frameborder="0" allow="autoplay" allowfullscreen></iframe>'
            )

        return (
            f'<section class="section hero-video-bg" style="position:relative;'
            f'min-height:500px;overflow:hidden;">\n'
            f'  <div style="position:absolute;top:0;left:0;width:100%;height:100%;">\n'
            f"    {iframe_html}\n"
            f"  </div>\n"
            f'  <div class="container hero-overlay" style="position:relative;z-index:2;'
            f'background:rgba(0,0,0,0.5);padding:3rem;border-radius:8px;">\n'
            f'    <h1 style="color:#fff;">{title}</h1>\n'
            f"    {sub_html}\n"
            f"    {btn_html}\n"
            f"  </div>\n"
            f"</section>"
        )

    @staticmethod
    def _extract_youtube_id(url: str) -> str:
        """Extract YouTube video ID from a URL.

        Supports:
        - https://www.youtube.com/watch?v=VIDEO_ID
        - https://youtu.be/VIDEO_ID
        - https://youtube.com/watch?v=VIDEO_ID

        Returns empty string if no valid ID found.
        """
        if not url:
            return ""
        # Match youtube.com/watch?v=ID or youtu.be/ID
        match = re.search(r"(?:youtube\.com/watch\?v=|youtu\.be/)([\w-]+)", url)
        return match.group(1) if match else ""

    # ========================================================================
    # About
    # ========================================================================

    def render_about(self, props: dict, layout: str) -> str:
        """Render about section with text and optional image.

        Supports layouts:
        - default/image-right: text on left, image on right
        - image-left: image on left, text on right
        - card: elevated card with shadow, centred content
        - timeline: vertical timeline with milestones
        """
        title = html.escape(props.get("title", ""))
        content = props.get("content_md", "")
        image_key = props.get("image_key", "")
        img_url = self._img_url(image_key)

        paragraphs = [html.escape(p) for p in content.split("\n") if p.strip()]
        text_html = "".join(f"<p>{p}</p>" for p in paragraphs)
        title_html = f"<h2>{title}</h2>" if title else ""
        img_html = (
            f'<div class="about-img"><img src="{img_url}" alt="{title}"></div>'
            if img_url
            else ""
        )

        if layout == "card":
            return self._render_about_card(title_html, text_html, img_html)
        elif layout == "timeline":
            return self._render_about_timeline(title_html, props)

        text_block = f'<div class="about-text">\n      {title_html}\n      {text_html}\n    </div>'

        if layout == "image-left" and img_html:
            # Image first, then text
            inner = f"    {img_html}\n    {text_block}"
        else:
            # Default: text first, then image
            inner = f"    {text_block}\n    {img_html}"

        return f"""<section class="section about">
  <div class="container about-content">
{inner}
  </div>
</section>"""

    def _render_about_card(self, title_html: str, text_html: str, img_html: str) -> str:
        """Render about section as an elevated card with shadow and centred content."""
        return (
            f'<section class="section about">\n'
            f'  <div class="container">\n'
            f'    <div style="max-width:700px;margin:0 auto;background:#fff;'
            f"border-radius:12px;box-shadow:0 4px 16px rgba(0,0,0,0.1);"
            f'padding:3rem;text-align:center;">\n'
            f"      {title_html}\n"
            f"      {text_html}\n"
            f"      {img_html}\n"
            f"    </div>\n"
            f"  </div>\n"
            f"</section>"
        )

    def _render_about_timeline(self, title_html: str, props: dict) -> str:
        """Render about section as a vertical timeline with milestones."""
        timeline_items = props.get("timeline_items", [])

        items_html = ""
        for item in timeline_items:
            item_title = html.escape(item.get("title", ""))
            item_desc = html.escape(item.get("description", ""))
            items_html += (
                f'<div style="margin-bottom:2rem;position:relative;">'
                f'<div style="position:absolute;left:-1.6rem;top:0;width:12px;'
                f'height:12px;border-radius:50%;background:{self.color_accent};"></div>'
                f'<h3 style="margin:0 0 0.25rem 0;">{item_title}</h3>'
                f'<p style="color:#555;margin:0;">{item_desc}</p>'
                f"</div>"
            )

        return (
            f'<section class="section about">\n'
            f'  <div class="container">\n'
            f"    {title_html}\n"
            f'    <div style="position:relative;padding-left:2rem;'
            f'border-left:3px solid {self.color_accent};">\n'
            f"      {items_html}\n"
            f"    </div>\n"
            f"  </div>\n"
            f"</section>"
        )

    # ========================================================================
    # Gallery
    # ========================================================================

    def render_gallery(self, props: dict, layout: str) -> str:
        """Render gallery section. Supports: grid-3, grid-4, masonry, carousel."""
        title = html.escape(props.get("title", ""))
        images = props.get("images", [])
        if not images:
            return ""

        title_html = f"<h2>{title}</h2>" if title else ""

        if layout == "carousel":
            return self._render_gallery_carousel(images, title_html)

        imgs_html = "".join(
            f'<img src="{self._img_url(img.get("image_key", ""))}" alt="{html.escape(img.get("alt", ""))}">'
            for img in images
            if img.get("image_key")
        )

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

    def _render_gallery_carousel(self, images: list, title_html: str) -> str:
        """Render gallery as carousel with data-carousel attributes.

        Uses the unified carousel JS (injected at page level) for:
        - Auto-advance every 10s
        - Pause on hover/interaction, resume after 10s idle
        - Touch swipe support
        """
        imgs_html = "".join(
            f'<div class="carousel-slide"><img src="{self._img_url(img.get("image_key", ""))}" alt="{html.escape(img.get("alt", ""))}"></div>'
            for img in images
            if img.get("image_key")
        )

        num_slides = sum(1 for img in images if img.get("image_key"))
        dots_html = "".join(
            f'<span class="carousel-dot{" active" if i == 0 else ""}" data-carousel-dot data-index="{i}"></span>'
            for i in range(num_slides)
        )

        return f"""<section class="section gallery">
  <div class="container">
    {title_html}
    <div class="carousel" data-carousel>
      <div class="carousel-track" data-carousel-track>{imgs_html}</div>
      <button class="carousel-btn carousel-prev" data-carousel-prev>&#10094;</button>
      <button class="carousel-btn carousel-next" data-carousel-next>&#10095;</button>
      <div class="carousel-dots">{dots_html}</div>
    </div>
  </div>
</section>"""

    # ========================================================================
    # CTA (Call to Action)
    # ========================================================================

    def render_cta(self, props: dict, layout: str = "") -> str:
        """Render call-to-action section.

        Supports layouts:
        - default: centred title, subtitle, and button
        - split: text on left, button on right in a flex row
        - banner: thin full-width strip (smaller padding, single line)
        - floating: fixed bottom bar with CTA (position:fixed at page bottom)
        """
        title = html.escape(props.get("title", ""))
        subtitle = html.escape(props.get("subtitle", ""))
        btn_text = html.escape(props.get("button_text", ""))
        btn_url = html.escape(props.get("button_url", "#"))

        if layout == "split":
            return self._render_cta_split(title, subtitle, btn_text, btn_url)
        elif layout == "banner":
            return self._render_cta_banner(title, subtitle, btn_text, btn_url)
        elif layout == "floating":
            return self._render_cta_floating(title, subtitle, btn_text, btn_url)

        sub_html = f"<p>{subtitle}</p>" if subtitle else ""
        btn_html = f'<a href="{btn_url}" class="btn">{btn_text}</a>' if btn_text else ""

        return f"""<section class="cta">
  <div class="container">
    <h2>{title}</h2>
    {sub_html}
    {btn_html}
  </div>
</section>"""

    def _render_cta_split(
        self, title: str, subtitle: str, btn_text: str, btn_url: str
    ) -> str:
        """Render CTA with text left and button right in a flex row."""
        sub_html = f"<p>{subtitle}</p>" if subtitle else ""
        btn_html = f'<a href="{btn_url}" class="btn">{btn_text}</a>' if btn_text else ""

        return (
            f'<section class="cta" style="display:flex;align-items:center;'
            f'justify-content:space-between;flex-wrap:wrap;">\n'
            f'  <div style="flex:1;min-width:280px;">\n'
            f"    <h2>{title}</h2>\n"
            f"    {sub_html}\n"
            f"  </div>\n"
            f'  <div style="flex-shrink:0;">\n'
            f"    {btn_html}\n"
            f"  </div>\n"
            f"</section>"
        )

    def _render_cta_banner(
        self, title: str, subtitle: str, btn_text: str, btn_url: str
    ) -> str:
        """Render CTA as a thin full-width strip (smaller padding, single line)."""
        subtitle_span = (
            f'<span style="opacity:0.9;">{subtitle}</span>' if subtitle else ""
        )
        btn_html = f'<a href="{btn_url}" class="btn">{btn_text}</a>' if btn_text else ""

        return (
            f'<section class="cta" style="padding:1rem 1.5rem;">\n'
            f'  <div class="container" style="display:flex;align-items:center;'
            f'justify-content:center;gap:1.5rem;flex-wrap:wrap;">\n'
            f'    <span style="font-weight:600;">{title}</span>\n'
            f"    {subtitle_span}\n"
            f"    {btn_html}\n"
            f"  </div>\n"
            f"</section>"
        )

    def _render_cta_floating(
        self, title: str, subtitle: str, btn_text: str, btn_url: str
    ) -> str:
        """Render CTA as a fixed bottom bar (position:fixed at page bottom)."""
        btn_html = f'<a href="{btn_url}" class="btn">{btn_text}</a>' if btn_text else ""

        return (
            f'<div class="cta-floating" style="position:fixed;bottom:0;left:0;right:0;'
            f"z-index:999;padding:1rem 1.5rem;background:{self.color_primary};"
            f'box-shadow:0 -2px 8px rgba(0,0,0,0.15);">\n'
            f'  <div class="container" style="display:flex;align-items:center;'
            f'justify-content:space-between;flex-wrap:wrap;gap:1rem;">\n'
            f'    <span style="color:#fff;font-weight:600;">{title}</span>\n'
            f"    {btn_html}\n"
            f"  </div>\n"
            f"</div>"
        )

    # ========================================================================
    # FAQ
    # ========================================================================

    def render_faq(self, props: dict, layout: str = "") -> str:
        """Render FAQ section with collapsible details/summary elements.

        Supports layouts:
        - default: responsive faq-grid (2 columns on desktop via CSS media query)
        - two-column: forced 2-column grid at all viewports via inline style
        - side-by-side: question on left, answer on right in a 2-column grid
        """
        title = html.escape(props.get("title", ""))
        items = props.get("items", [])
        if not items:
            return ""

        title_html = f"<h2>{title}</h2>" if title else ""

        if layout == "side-by-side":
            return self._render_faq_side_by_side(items, title_html)

        items_html = "".join(
            f'<details class="faq-item"><summary>{html.escape(item.get("question", "").strip())}</summary><p>{html.escape(item.get("answer", "").strip())}</p></details>'
            for item in items
        )

        if layout == "two-column":
            return f"""<section class="section faq">
  <div class="container">
    {title_html}
    <div class="faq-grid" style="display:grid;grid-template-columns:repeat(2,1fr);gap:0 2rem;">{items_html}</div>
  </div>
</section>"""

        return f"""<section class="section faq">
  <div class="container">
    {title_html}
    <div class="faq-grid">{items_html}</div>
  </div>
</section>"""

    def _render_faq_side_by_side(self, items: list, title_html: str) -> str:
        """Render FAQ as side-by-side grid: question left, answer right."""
        rows_html = ""
        for item in items:
            question = html.escape(item.get("question", "").strip())
            answer = html.escape(item.get("answer", "").strip())
            rows_html += (
                f'<div style="font-weight:600;">{question}</div>'
                f'<div style="color:#555;">{answer}</div>'
            )

        return (
            f'<section class="section faq">\n'
            f'  <div class="container">\n'
            f"    {title_html}\n"
            f'    <div style="display:grid;grid-template-columns:1fr 2fr;'
            f'gap:1rem 2rem;align-items:start;">{rows_html}</div>\n'
            f"  </div>\n"
            f"</section>"
        )

    # ========================================================================
    # Testimonials
    # ========================================================================

    def render_testimonials(self, props: dict, layout: str = "") -> str:
        """Render testimonials section.

        Supports layouts:
        - default/cards: card grid (existing default)
        - carousel: auto-advancing single testimonial with prev/next + dots
        - quote-large: single large centred quote (first item)
        - grid: compact grid without card styling
        """
        title = html.escape(props.get("title", ""))
        items = props.get("items", [])
        if not items:
            return ""

        title_html = f"<h2>{title}</h2>" if title else ""

        if layout == "carousel":
            return self._render_testimonials_carousel(items, title_html)
        elif layout == "quote-large":
            return self._render_testimonials_quote_large(items, title_html)
        elif layout == "grid":
            return self._render_testimonials_grid(items, title_html)

        # Default: card grid
        cards_html = "".join(
            f'<div class="testimonial-card"><blockquote>"{html.escape(item.get("quote", ""))}"</blockquote><cite>— {html.escape(item.get("author", ""))}{", " + html.escape(item.get("role", "")) if item.get("role") else ""}</cite></div>'
            for item in items
        )

        return f"""<section class="section testimonials">
  <div class="container">
    {title_html}
    <div class="testimonial-cards">{cards_html}</div>
  </div>
</section>"""

    def _render_testimonials_carousel(self, items: list, title_html: str) -> str:
        """Render testimonials as auto-advancing carousel with prev/next and dots."""
        slides_html = ""
        for item in items:
            quote = html.escape(item.get("quote", ""))
            author = html.escape(item.get("author", ""))
            role = item.get("role", "")
            cite_text = f"— {author}{', ' + html.escape(role) if role else ''}"
            slides_html += (
                f'<div class="carousel-slide" style="min-width:100%;padding:2rem;text-align:center;">'
                f'<blockquote style="font-size:1.3rem;font-style:italic;color:#555;">"{quote}"</blockquote>'
                f'<cite style="display:block;margin-top:1rem;font-weight:600;">{cite_text}</cite>'
                f"</div>"
            )

        carousel_id = f"testimonial-carousel-{id(items)}"
        num_slides = len(items)
        dots_html = "".join(
            f'<span class="carousel-dot{" active" if i == 0 else ""}" data-carousel-dot data-index="{i}"></span>'
            for i in range(num_slides)
        )

        return f"""<section class="section testimonials">
  <div class="container">
    {title_html}
    <div class="carousel" id="{carousel_id}" data-carousel>
      <div class="carousel-track" data-carousel-track>{slides_html}</div>
      <button class="carousel-btn carousel-prev" data-carousel-prev>&#10094;</button>
      <button class="carousel-btn carousel-next" data-carousel-next>&#10095;</button>
      <div class="carousel-dots">{dots_html}</div>
    </div>
  </div>
</section>"""

    def _render_testimonials_quote_large(self, items: list, title_html: str) -> str:
        """Render single large centred quote from first testimonial."""
        first = items[0]
        quote = html.escape(first.get("quote", ""))
        author = html.escape(first.get("author", ""))
        role = first.get("role", "")
        cite_text = f"— {author}{', ' + html.escape(role) if role else ''}"

        return f"""<section class="section testimonials">
  <div class="container" style="text-align:center;max-width:800px;margin:0 auto;">
    {title_html}
    <blockquote style="font-size:2rem;font-style:italic;color:#333;line-height:1.4;">"{quote}"</blockquote>
    <cite style="display:block;margin-top:1.5rem;font-weight:600;font-size:1.1rem;">{cite_text}</cite>
  </div>
</section>"""

    def _render_testimonials_grid(self, items: list, title_html: str) -> str:
        """Render testimonials as compact grid without card styling."""
        grid_items_html = ""
        for item in items:
            quote = html.escape(item.get("quote", ""))
            author = html.escape(item.get("author", ""))
            role = item.get("role", "")
            cite_text = f"— {author}{', ' + html.escape(role) if role else ''}"
            grid_items_html += (
                f'<div style="padding:1rem 0;border-bottom:1px solid #eee;">'
                f'<blockquote style="font-style:italic;color:#555;">"{quote}"</blockquote>'
                f'<cite style="font-weight:600;color:#333;">{cite_text}</cite>'
                f"</div>"
            )

        return f"""<section class="section testimonials">
  <div class="container">
    {title_html}
    <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:1.5rem;">{grid_items_html}</div>
  </div>
</section>"""

    # ========================================================================
    # Contact
    # ========================================================================

    def render_contact(self, props: dict, slug: str) -> str:
        """Render contact form section with inline submission JS."""
        title = html.escape(props.get("title", ""))
        subtitle = html.escape(props.get("subtitle", ""))
        title_html = f"<h2>{title}</h2>" if title else "<h2>Contact</h2>"
        sub_html = (
            f'<p style="text-align:center;color:#555;margin-bottom:1.5rem;">{subtitle}</p>'
            if subtitle
            else ""
        )

        safe_slug = html.escape(slug)
        base_url = os.environ.get("LANDING_PAGE_BASE_URL", "https://myadmin.app")
        backend_url = html.escape(
            os.environ.get("CONTACT_FORM_API_URL", base_url).rstrip("/")
        )
        api_url = f"{backend_url}/api/public/landing/{safe_slug}/contact"

        return f"""<section id="contact" class="section contact">
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

    # ========================================================================
    # Embed
    # ========================================================================

    def render_embed(self, props: dict) -> str:
        """Render embed/iframe section. Only allows HTTPS URLs."""
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

    # ========================================================================
    # Video
    # ========================================================================

    def render_video(self, props: dict, layout: str = "") -> str:
        """Render video section with YouTube embed (privacy-enhanced).

        Uses youtube-nocookie.com for the embed URL.
        Implements thumbnail lazy-load: shows YouTube thumbnail with play button,
        replaces with iframe on click via inline JS.

        Supports layouts:
        - centered: max-width 800px, centred
        - full-width: no width constraint (edge-to-edge)
        """
        title = html.escape(props.get("title", ""))
        description = html.escape(props.get("description", ""))
        video_url = props.get("video_url", "")
        video_id = self._extract_youtube_id(video_url)

        if not video_id:
            return ""

        title_html = f"<h2>{title}</h2>" if title else ""
        desc_html = f"<p>{description}</p>" if description else ""

        # Layout: centered (default) vs full-width
        if layout == "full-width":
            max_width_style = ""
        else:
            # centered layout (default)
            max_width_style = "max-width:800px;margin:0 auto;"

        return (
            f'<section class="section video-block">\n'
            f'  <div class="container" style="{max_width_style}">\n'
            f"    {title_html}\n"
            f'    <div class="video-wrapper" style="position:relative;padding-bottom:56.25%;height:0;overflow:hidden;">\n'
            f'      <div data-video-id="{video_id}" style="position:absolute;top:0;left:0;width:100%;height:100%;cursor:pointer;"'
            f" onclick=\"this.innerHTML='<iframe src=&quot;https://www.youtube-nocookie.com/embed/{video_id}?autoplay=1&quot;"
            f" style=&quot;position:absolute;top:0;left:0;width:100%;height:100%;&quot;"
            f" frameborder=&quot;0&quot; allowfullscreen allow=&quot;autoplay&quot;></iframe>'\">\n"
            f'        <img src="https://img.youtube.com/vi/{video_id}/maxresdefault.jpg"'
            f' style="width:100%;height:100%;object-fit:cover;" alt="{title}">\n'
            f'        <div style="position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);'
            f"width:68px;height:48px;background:rgba(0,0,0,0.7);border-radius:8px;"
            f'display:flex;align-items:center;justify-content:center;">\n'
            f'          <svg width="24" height="24" viewBox="0 0 24 24" fill="white">'
            f'<path d="M8 5v14l11-7z"/></svg>\n'
            f"        </div>\n"
            f"      </div>\n"
            f"    </div>\n"
            f"    {desc_html}\n"
            f"  </div>\n"
            f"</section>"
        )

    # ========================================================================
    # Pricing
    # ========================================================================

    def render_pricing(self, props: dict, layout: str = "") -> str:
        """Render pricing section.

        Supports layouts:
        - default: card grid
        - horizontal: comparison table with features as rows
        - featured-center: middle card enlarged/highlighted
        - comparison-table: full table with feature rows (✓ or —)
        """
        title = html.escape(props.get("title", ""))
        items = props.get("items", [])
        if not items:
            return ""

        title_html = f"<h2>{title}</h2>" if title else ""

        if layout == "horizontal":
            return self._render_pricing_horizontal(items, title_html)
        elif layout == "featured-center":
            return self._render_pricing_featured_center(items, title_html)
        elif layout == "comparison-table":
            return self._render_pricing_comparison_table(items, title_html)

        cards_html = ""
        for item in items:
            name = html.escape(item.get("name", ""))
            price = html.escape(item.get("price", ""))
            desc = html.escape(item.get("description", ""))
            features = item.get("features", [])
            features_html = ""
            if features:
                features_li = "".join(
                    f"<li>{html.escape(f)}</li>" for f in features if f
                )
                features_html = f'<ul class="pricing-features">{features_li}</ul>'
            cards_html += f'<div class="pricing-card"><h3>{name}</h3><div class="price">{price}</div><p>{desc}</p>{features_html}</div>'

        return f"""<section class="section pricing">
  <div class="container">
    {title_html}
    <div class="pricing-grid">{cards_html}</div>
  </div>
</section>"""

    def _render_pricing_horizontal(self, items: list, title_html: str) -> str:
        """Render pricing as horizontal comparison table with features as rows."""
        # Build header row
        header_cells = ""
        for item in items:
            name = html.escape(item.get("name", ""))
            price = html.escape(item.get("price", ""))
            header_cells += (
                f'<th style="padding:1rem;border-bottom:2px solid #eee;">'
                f'{name}<br><span style="font-size:1.5rem;color:{self.color_accent};">'
                f"{price}</span></th>"
            )

        # Collect all unique features across items
        all_features = []
        for item in items:
            for f in item.get("features", []):
                if f and f not in all_features:
                    all_features.append(f)

        # Build body rows
        body_rows = ""
        for feature in all_features:
            cells = ""
            for item in items:
                item_features = item.get("features", [])
                if feature in item_features:
                    cells += '<td style="padding:0.75rem;border-bottom:1px solid #eee;">✓</td>'
                else:
                    cells += '<td style="padding:0.75rem;border-bottom:1px solid #eee;">—</td>'
            body_rows += (
                f'<tr><td style="padding:0.75rem;border-bottom:1px solid #eee;'
                f'text-align:left;font-weight:500;">{html.escape(feature)}</td>'
                f"{cells}</tr>"
            )

        return (
            f'<section class="section pricing">\n'
            f'  <div class="container">\n'
            f"    {title_html}\n"
            f'    <table style="width:100%;border-collapse:collapse;text-align:center;">\n'
            f"      <thead><tr><th></th>{header_cells}</tr></thead>\n"
            f"      <tbody>{body_rows}</tbody>\n"
            f"    </table>\n"
            f"  </div>\n"
            f"</section>"
        )

    def _render_pricing_featured_center(self, items: list, title_html: str) -> str:
        """Render pricing cards with middle item enlarged/highlighted."""
        mid_index = len(items) // 2
        cards_html = ""
        for i, item in enumerate(items):
            name = html.escape(item.get("name", ""))
            price = html.escape(item.get("price", ""))
            desc = html.escape(item.get("description", ""))
            features = item.get("features", [])
            features_html = ""
            if features:
                features_li = "".join(
                    f"<li>{html.escape(f)}</li>" for f in features if f
                )
                features_html = f'<ul class="pricing-features">{features_li}</ul>'

            if i == mid_index:
                card_style = (
                    f' style="transform:scale(1.05);border:2px solid {self.color_accent};'
                    f'box-shadow:0 4px 20px rgba(0,0,0,0.15);"'
                )
            else:
                card_style = ""

            cards_html += (
                f'<div class="pricing-card"{card_style}>'
                f'<h3>{name}</h3><div class="price">{price}</div>'
                f"<p>{desc}</p>{features_html}</div>"
            )

        return f"""<section class="section pricing">
  <div class="container">
    {title_html}
    <div class="pricing-grid">{cards_html}</div>
  </div>
</section>"""

    def _render_pricing_comparison_table(self, items: list, title_html: str) -> str:
        """Render pricing as full comparison table with feature rows."""
        # Build header
        header_cells = ""
        for item in items:
            name = html.escape(item.get("name", ""))
            price = html.escape(item.get("price", ""))
            header_cells += f'<th style="padding:0.75rem;">{name} - {price}</th>'

        # Collect all unique features across all items
        all_features = []
        for item in items:
            for f in item.get("features", []):
                if f and f not in all_features:
                    all_features.append(f)

        # Build body rows
        body_rows = ""
        for feature in all_features:
            cells = ""
            for item in items:
                item_features = item.get("features", [])
                mark = "✓" if feature in item_features else "—"
                cells += f'<td style="padding:0.75rem;text-align:center;">{mark}</td>'
            body_rows += (
                f'<tr><td style="padding:0.75rem;">{html.escape(feature)}</td>'
                f"{cells}</tr>"
            )

        return (
            f'<section class="section pricing">\n'
            f'  <div class="container">\n'
            f"    {title_html}\n"
            f'    <table style="width:100%;border-collapse:collapse;">\n'
            f'      <thead><tr><th style="padding:0.75rem;">Feature</th>'
            f"{header_cells}</tr></thead>\n"
            f"      <tbody>{body_rows}</tbody>\n"
            f"    </table>\n"
            f"  </div>\n"
            f"</section>"
        )

    # ========================================================================
    # Footer
    # ========================================================================

    def render_footer_html(self, footer: dict, branding: dict) -> str:
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
                    links.append(
                        f'<a href="{html.escape(url)}" target="_blank" rel="noopener noreferrer">{html.escape(platform.replace("_", " ").title())}</a>'
                    )
            if links:
                social_html = f'<p style="margin-top:0.5rem;">{"  ·  ".join(links)}</p>'

        return f"""<footer>
  <p>{info_line}</p>
  {"<p>" + contact_line + "</p>" if contact_line else ""}
  {social_html}
</footer>"""
