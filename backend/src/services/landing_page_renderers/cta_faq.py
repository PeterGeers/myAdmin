"""Call-to-action and FAQ section renderers for the landing page pipeline."""

import html


class CtaFaqMixin:
    """Renders the CTA and FAQ sections and their layout variants."""

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
