"""Hero section renderer for the landing page publish pipeline."""

import html
import re


class HeroMixin:
    """Renders the hero section and its layout variants."""

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
