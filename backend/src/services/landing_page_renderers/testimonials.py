"""Testimonials section renderer for the landing page publish pipeline."""

import html


class TestimonialsMixin:
    """Renders the testimonials section and its layout variants."""

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
