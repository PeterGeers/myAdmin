"""Contact, embed, and video section renderers for the landing page pipeline."""

import html
import os


class MediaMixin:
    """Renders the contact form, embed/iframe, and video sections."""

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
