"""About and gallery section renderers for the landing page publish pipeline."""

import html

import markdown


class ContentMixin:
    """Renders the about and gallery sections and their layout variants."""

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

        # Render markdown content to HTML (supports headings, bold, lists, etc.)
        if content.strip():
            text_html = markdown.markdown(content, extensions=["nl2br", "smarty"])
        else:
            text_html = ""
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
