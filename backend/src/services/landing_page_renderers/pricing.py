"""Pricing and footer renderers for the landing page publish pipeline."""

import html


class PricingMixin:
    """Renders the pricing section, its layout variants, and the footer."""

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
