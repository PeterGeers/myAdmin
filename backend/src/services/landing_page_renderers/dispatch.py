"""Section dispatch and shared helpers for the landing page renderers."""

import re

from services.landing_page_styles import LandingPageStyles


class DispatchMixin:
    """Section dispatch, wrapper handling, and the image-URL helper."""

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

    def _img_url(self, image_key: str) -> str:
        """Build full image URL from an S3 key."""
        if not image_key:
            return ""
        if image_key.startswith("http"):
            return image_key
        return f"{self.img_base}/{image_key}" if self.img_base else image_key
