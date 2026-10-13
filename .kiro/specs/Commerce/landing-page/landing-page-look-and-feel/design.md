# Landing Page Look & Feel — Technical Design

## Architecture Impact

This feature extends three existing layers:

```
┌──────────────────────────────────────────────────────────┐
│  DynamoDB (CMS)                                          │
│  sections[].settings → NEW per-block visual settings     │
├──────────────────────────────────────────────────────────┤
│  ParameterService (MySQL)                                │
│  landing_page namespace → NEW theme/typography params    │
├──────────────────────────────────────────────────────────┤
│  S3 Published HTML                                       │
│  generate_index_html → EXTENDED with settings + themes   │
└──────────────────────────────────────────────────────────┘
```

No new AWS services. No database migrations. No new dependencies.

---

## Phase A: Block-Level Settings

### Data Model Extension

Add optional `settings` object to each section in DynamoDB:

```json
{
  "id": "block-003",
  "type": "faq",
  "layout": "centered",
  "properties": { "items": [...], "title": "FAQ" },
  "settings": {
    "background_type": "color",
    "background_color": "#f9f9f9",
    "background_image_key": "",
    "background_gradient": "",
    "padding": "normal",
    "text_color": "dark",
    "max_width": "contained",
    "border_radius": "none"
  }
}
```

| Setting                | Type   | Options                         | Default       |
| ---------------------- | ------ | ------------------------------- | ------------- |
| `background_type`      | enum   | `color`, `image`, `gradient`    | `color`       |
| `background_color`     | string | Any hex colour                  | `transparent` |
| `background_image_key` | string | S3 image key                    | `""`          |
| `background_gradient`  | string | CSS gradient string             | `""`          |
| `padding`              | enum   | `compact`, `normal`, `spacious` | `normal`      |
| `text_color`           | enum   | `dark`, `light`, `auto`         | `dark`        |
| `max_width`            | enum   | `contained`, `full-width`       | `contained`   |
| `border_radius`        | enum   | `none`, `sm`, `md`, `lg`        | `none`        |

### Frontend: TypeScript Interface

```typescript
// In landingPageApi.ts
export interface BlockSettings {
  background_type: "color" | "image" | "gradient";
  background_color: string;
  background_image_key: string;
  background_gradient: string;
  padding: "compact" | "normal" | "spacious";
  text_color: "dark" | "light" | "auto";
  max_width: "contained" | "full-width";
  border_radius: "none" | "sm" | "md" | "lg";
}

export interface Section {
  id: string;
  type: string;
  layout: string;
  properties: Record<string, unknown>;
  settings?: BlockSettings; // NEW — optional for backwards compatibility
}
```

### Frontend: BlockConfigurator Settings Tab

Add a second tab to `BlockConfigurator.tsx`:

```
┌─────────────────────────────────────────────┐
│  [Content]  [Settings]                       │  ← Tab switcher
├─────────────────────────────────────────────┤
│  Background                                  │
│  ○ Colour  ○ Image  ○ Gradient              │
│  [#f9f9f9 ■ ]  ← colour picker             │
│                                              │
│  Padding                                     │
│  [ Compact ] [ Normal ] [ Spacious ]         │
│                                              │
│  Text Colour                                 │
│  [ Dark ] [ Light ] [ Auto ]                 │
│                                              │
│  Width:  [x] Contained  [ ] Full-width       │
│  Radius: [ none ] [ sm ] [ md ] [ lg ]       │
└─────────────────────────────────────────────┘
```

New component: `BlockSettingsTab.tsx` (renders the settings controls).

### Backend: HTML Generation

In `_render_sections_html`, extract `settings` and generate wrapper styles:

```python
def _render_sections_html(self, sections, img_base, color_accent, slug):
    parts = []
    for section in sections:
        section_type = section.get("type", "")
        props = section.get("properties", {})
        layout = section.get("layout", "")
        settings = section.get("settings", {})

        # Generate section wrapper with settings-based inline style
        wrapper_style = self._build_section_style(settings, img_base)
        content_html = self._render_section(
            section_type, props, layout, img_base, color_accent, slug
        )
        if content_html:
            max_width = settings.get("max_width", "contained")
            container_class = "container" if max_width == "contained" else ""
            parts.append(
                f'<section class="section" style="{wrapper_style}">'
                f'<div class="{container_class}">{content_html}</div>'
                f'</section>'
            )
    return "\n".join(parts)
```

Style mapping:

```python
def _build_section_style(self, settings: dict, img_base: str) -> str:
    if not settings:
        return ""
    styles = []

    # Background
    bg_type = settings.get("background_type", "color")
    if bg_type == "color":
        color = settings.get("background_color", "")
        if color and color != "transparent":
            styles.append(f"background-color: {color}")
    elif bg_type == "gradient":
        gradient = settings.get("background_gradient", "")
        if gradient:
            styles.append(f"background: {gradient}")
    elif bg_type == "image":
        image_key = settings.get("background_image_key", "")
        if image_key:
            url = self._img_url(image_key, img_base)
            styles.append(f"background-image: url('{url}')")
            styles.append("background-size: cover")
            styles.append("background-position: center")

    # Padding
    padding_map = {"compact": "1rem 1.5rem", "normal": "2rem 1.5rem", "spacious": "4rem 1.5rem"}
    padding = settings.get("padding", "normal")
    styles.append(f"padding: {padding_map.get(padding, '2rem 1.5rem')}")

    # Text colour
    text_map = {"dark": "#333", "light": "#fff", "auto": "inherit"}
    text_color = settings.get("text_color", "dark")
    if text_color != "auto":
        styles.append(f"color: {text_map.get(text_color, '#333')}")

    # Border radius
    radius_map = {"none": "0", "sm": "8px", "md": "16px", "lg": "24px"}
    radius = settings.get("border_radius", "none")
    if radius != "none":
        styles.append(f"border-radius: {radius_map.get(radius, '0')}")

    return "; ".join(styles)
```

### WCAG Auto-Contrast (text_color: auto)

When `text_color` is `auto`, calculate contrast ratio against the background:

- If `background_type == "color"`: compute relative luminance → choose dark or light text
- If gradient or image: default to dark (safe fallback; admin can override)

Utility function:

```python
def _auto_text_color(bg_hex: str) -> str:
    """Return 'dark' or 'light' based on WCAG relative luminance of bg colour."""
    r, g, b = int(bg_hex[1:3], 16), int(bg_hex[3:5], 16), int(bg_hex[5:7], 16)
    # sRGB to linear
    def linearize(c):
        c = c / 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    luminance = 0.2126 * linearize(r) + 0.7152 * linearize(g) + 0.0722 * linearize(b)
    return "light" if luminance < 0.5 else "dark"
```

---

## Phase B: Global Theme Presets

### Theme Definitions (system-level, in code)

```python
THEME_PRESETS = {
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
```

### Storage (ParameterService)

```
namespace: landing_page
key: theme
value: {"preset": "professional", "overrides": {"color_accent": "#custom"}}
```

### Branding Resolution Change

Extend `resolve_branding()`:

```python
def resolve_branding(self, tenant: str) -> dict:
    # ... existing resolution ...

    # Theme layer: apply preset defaults, then overrides
    theme_param = self.param_svc.get_param("landing_page", "theme", tenant=tenant)
    if theme_param:
        theme_data = json.loads(theme_param) if isinstance(theme_param, str) else theme_param
        preset_name = theme_data.get("preset", "")
        if preset_name in THEME_PRESETS:
            preset = THEME_PRESETS[preset_name]
            # Fill unset fields from preset
            for key, value in preset.items():
                if key in result and not result[key]:
                    result[key] = value
            # Apply explicit overrides on top
            overrides = theme_data.get("overrides", {})
            for key, value in overrides.items():
                if value:
                    result[key] = value

    return result
```

### Frontend: Theme Selector

New component: `ThemeSelector.tsx` in BrandingSettings area.

```
┌───────────────────────────────────────────────┐
│  Choose a Theme                                │
│                                                │
│  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐         │
│  │ Prof │ │ Warm │ │ Mod. │ │ Nat. │         │
│  │ ■■■  │ │ ■■■  │ │ ■■■  │ │ ■■■  │         │
│  └──────┘ └──────┘ └──────┘ └──────┘         │
│  ┌──────┐ ┌──────┐ ┌──────┐                  │
│  │ Min. │ │ Lux. │ │Custom│                  │
│  │ ■■■  │ │ ■■■  │ │  ✎  │                  │
│  └──────┘ └──────┘ └──────┘                  │
│                                                │
│  [ Reset to theme defaults ]                   │
└───────────────────────────────────────────────┘
```

### Google Fonts Integration

In `generate_index_html`, inject font links based on resolved branding:

```python
def _build_font_links(self, branding: dict) -> str:
    fonts = set()
    for key in ("font_heading", "font_body"):
        font = branding.get(key, "")
        if font and font.lower() != "system":
            fonts.add(font)
    if not fonts:
        return ""
    families = "|".join(f.replace(" ", "+") + ":wght@400;600;700" for f in fonts)
    return (
        f'<link rel="preconnect" href="https://fonts.googleapis.com">\n'
        f'<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
        f'<link href="https://fonts.googleapis.com/css2?family={families}&display=swap" rel="stylesheet">'
    )
```

---

## Phase C: Block Layout Variants

### New Layouts Per Type

| Block        | New Layouts                                            |
| ------------ | ------------------------------------------------------ |
| Hero         | `image-left`, `image-bg`, `split-diagonal`, `video-bg` |
| About        | `image-left`, `image-right`, `card`, `timeline`        |
| Gallery      | `grid-4`, `masonry`, `carousel`                        |
| Testimonials | `cards`, `carousel`, `quote-large`, `grid`             |
| FAQ          | `two-column`, `side-by-side`                           |
| Pricing      | `horizontal`, `featured-center`, `comparison-table`    |
| CTA          | `split`, `banner`, `floating`                          |
| Video        | **NEW block type** — `centered`, `full-width`          |

### Video Block (new block type)

A dedicated YouTube video section — simpler and more user-friendly than the generic `embed` block for video content.

**Properties:**

```json
{
  "video_url": "https://www.youtube.com/watch?v=xxxxx",
  "title": "Watch Our Property Tour",
  "description": "Take a virtual tour of our Amsterdam apartment"
}
```

**Layouts:**

- `centered` — contained max-width (800px), centred
- `full-width` — edge-to-edge, larger player

**Behaviour:**

- Accepts YouTube URLs (full URL or short `youtu.be` format)
- Backend extracts video ID, generates embed with `youtube-nocookie.com` (privacy-enhanced)
- Thumbnail preview shown initially (faster page load, no iframe until user clicks play)
- Responsive 16:9 aspect ratio via `padding-bottom: 56.25%` wrapper
- Title rendered as `<h2>`, description as `<p>` below the player

**HTML output:**

```html
<section class="section video-block">
  <div class="container">
    <h2>Watch Our Property Tour</h2>
    <div
      class="video-wrapper"
      style="position:relative;padding-bottom:56.25%;height:0;overflow:hidden;"
    >
      <iframe
        src="https://www.youtube-nocookie.com/embed/{VIDEO_ID}"
        style="position:absolute;top:0;left:0;width:100%;height:100%;"
        frameborder="0"
        allowfullscreen
        allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
        loading="lazy"
      ></iframe>
    </div>
    <p>Take a virtual tour of our Amsterdam apartment</p>
  </div>
</section>
```

**Thumbnail lazy-load pattern:**

```html
<div class="video-wrapper" data-video-id="{VIDEO_ID}">
  <img
    src="https://img.youtube.com/vi/{VIDEO_ID}/maxresdefault.jpg"
    alt="Video thumbnail"
  />
  <button class="video-play-btn" aria-label="Play video">▶</button>
</div>
```

Clicking the thumbnail replaces it with the iframe (small inline JS).

### Carousel Behaviour (Gallery + Testimonials)

- Auto-advances every **10 seconds**
- Pauses on hover and on user interaction (click/touch)
- Resumes auto-advance 10s after last interaction
- Previous/Next buttons (absolute positioned)
- Dot indicators (clickable)
- Touch swipe support (pointer events)
- Vanilla JS inline in `<script>` at end of `<body>`

```javascript
// Carousel pattern (inline in published HTML)
(function () {
  document.querySelectorAll("[data-carousel]").forEach(function (carousel) {
    var track = carousel.querySelector("[data-carousel-track]");
    var slides = track.children;
    var dots = carousel.querySelectorAll("[data-carousel-dot]");
    var current = 0;
    var interval = null;
    var DELAY = 10000;

    function goTo(idx) {
      current = ((idx % slides.length) + slides.length) % slides.length;
      track.style.transform = "translateX(-" + current * 100 + "%)";
      dots.forEach(function (d, i) {
        d.classList.toggle("active", i === current);
      });
    }

    function startAuto() {
      stopAuto();
      interval = setInterval(function () {
        goTo(current + 1);
      }, DELAY);
    }

    function stopAuto() {
      if (interval) {
        clearInterval(interval);
        interval = null;
      }
    }

    carousel.querySelector("[data-carousel-prev]").onclick = function () {
      goTo(current - 1);
      stopAuto();
      setTimeout(startAuto, DELAY);
    };
    carousel.querySelector("[data-carousel-next]").onclick = function () {
      goTo(current + 1);
      stopAuto();
      setTimeout(startAuto, DELAY);
    };
    dots.forEach(function (dot, i) {
      dot.onclick = function () {
        goTo(i);
        stopAuto();
        setTimeout(startAuto, DELAY);
      };
    });
    carousel.addEventListener("mouseenter", stopAuto);
    carousel.addEventListener("mouseleave", startAuto);

    startAuto();
  });
})();
```

### Backend Refactoring: Extract Renderers

Current `landing_page_publish_service.py` is 1171 lines — far exceeds the 500-line target. Must be refactored before adding layout variants.

**Split into multiple files (each ≤ 500 lines):**

| File                              | Responsibility                                                                                             | ~Lines |
| --------------------------------- | ---------------------------------------------------------------------------------------------------------- | ------ |
| `landing_page_publish_service.py` | Orchestration: publish/unpublish, resolve_branding, resolve_footer, resolve_seo, generate_index_html shell | ~400   |
| `landing_page_renderers.py`       | Section HTML renderers (`_render_hero`, `_render_about`, etc.)                                             | ~400   |
| `landing_page_styles.py`          | Style utilities: `_build_section_style`, `_auto_text_color`, `_build_font_links`, CSS generation           | ~200   |

Extract all `_render_*` methods into a standalone class:

```python
class LandingPageRenderers:
    """Section HTML renderers for the landing page publish pipeline."""

    def __init__(self, img_base: str, color_accent: str, color_primary: str):
        self.img_base = img_base
        self.color_accent = color_accent
        self.color_primary = color_primary

    def render_section(self, section_type, props, layout, slug):
        ...

    def render_hero(self, props, layout):
        ...
    # etc.
```

`LandingPagePublishService` instantiates `LandingPageRenderers` during publish and delegates.

**New file:** `backend/src/services/landing_page_styles.py`

Extract style/CSS utilities:

```python
class LandingPageStyles:
    """CSS generation utilities for landing page publishing."""

    GRADIENT_PRESETS = [...]  # moved here
    THEME_PRESETS = {...}     # moved here

    @staticmethod
    def build_section_style(settings: dict, img_base: str) -> str: ...

    @staticmethod
    def auto_text_color(bg_hex: str) -> str: ...

    @staticmethod
    def build_font_links(branding: dict) -> str: ...

    @staticmethod
    def build_css_variables(branding: dict) -> str: ...

    @staticmethod
    def sanitize_gradient(gradient: str) -> str: ...
```

All three files stay within the 500-line target, even after Phase C layout variants are added.

### Video-BG Hero (YouTube)

```html
<section class="section hero-video-bg">
  <div class="hero-video-wrapper">
    <iframe
      src="https://www.youtube.com/embed/{VIDEO_ID}?autoplay=1&mute=1&loop=1&playlist={VIDEO_ID}&controls=0"
      frameborder="0"
      allow="autoplay"
      allowfullscreen
    ></iframe>
  </div>
  <div class="hero-overlay">
    <div class="container">
      <h1>...</h1>
      <p>...</p>
      <a class="btn">...</a>
    </div>
  </div>
</section>
```

Properties extension for hero:

```json
{
  "video_url": "https://www.youtube.com/watch?v=xxxxx"
}
```

Backend extracts video ID from URL and embeds accordingly.

---

## Phase D: Typography & Global Spacing

### New ParameterService Keys

All in `landing_page` namespace:

| Key                    | Options                                                | Default |
| ---------------------- | ------------------------------------------------------ | ------- |
| `font_heading`         | Inter, Lora, Poppins, Nunito, Playfair Display, system | system  |
| `font_body`            | Inter, Lora, Poppins, Nunito, Lato, system             | system  |
| `base_spacing`         | compact, normal, relaxed                               | normal  |
| `border_radius_global` | sharp, rounded, pill                                   | rounded |
| `shadow_style`         | none, subtle, medium, dramatic                         | subtle  |

### CSS Variables in Published HTML

```css
:root {
  --font-heading: "Inter", sans-serif;
  --font-body: "Inter", sans-serif;
  --spacing-section: 2rem;
  --spacing-element: 1rem;
  --radius-sm: 4px;
  --radius-md: 8px;
  --radius-lg: 16px;
  --shadow-card: 0 2px 8px rgba(0, 0, 0, 0.08);
  --shadow-hover: 0 4px 16px rgba(0, 0, 0, 0.12);
}
```

Mapping:

| `base_spacing` | `--spacing-section` | `--spacing-element` |
| -------------- | ------------------- | ------------------- |
| compact        | 1.5rem              | 0.75rem             |
| normal         | 2rem                | 1rem                |
| relaxed        | 3rem                | 1.5rem              |

| `border_radius_global` | `--radius-sm` | `--radius-md` | `--radius-lg` |
| ---------------------- | ------------- | ------------- | ------------- |
| sharp                  | 0             | 0             | 0             |
| rounded                | 4px           | 8px           | 16px          |
| pill                   | 12px          | 24px          | 9999px        |

| `shadow_style` | `--shadow-card`             | `--shadow-hover`             |
| -------------- | --------------------------- | ---------------------------- |
| none           | none                        | none                         |
| subtle         | 0 2px 8px rgba(0,0,0,0.08)  | 0 4px 16px rgba(0,0,0,0.12)  |
| medium         | 0 4px 12px rgba(0,0,0,0.12) | 0 8px 24px rgba(0,0,0,0.18)  |
| dramatic       | 0 8px 24px rgba(0,0,0,0.2)  | 0 16px 48px rgba(0,0,0,0.28) |

### Frontend: Typography Settings UI

Extend `BrandingSettings.tsx` with:

- Font heading dropdown + preview text
- Font body dropdown + preview text
- Spacing selector (3 visual buttons)
- Border-radius selector (3 visual rectangles)
- Shadow selector (4 card previews)

---

## Gradient Presets

Curated presets available in the gradient picker:

```python
GRADIENT_PRESETS = [
    {"name": "Sunset", "value": "linear-gradient(135deg, #667eea 0%, #764ba2 100%)"},
    {"name": "Ocean", "value": "linear-gradient(135deg, #2193b0 0%, #6dd5ed 100%)"},
    {"name": "Forest", "value": "linear-gradient(135deg, #134e5e 0%, #71b280 100%)"},
    {"name": "Peach", "value": "linear-gradient(135deg, #ffecd2 0%, #fcb69f 100%)"},
    {"name": "Night", "value": "linear-gradient(135deg, #0f0c29 0%, #302b63 50%, #24243e 100%)"},
    {"name": "Warm", "value": "linear-gradient(135deg, #f093fb 0%, #f5576c 100%)"},
    {"name": "Sky", "value": "linear-gradient(135deg, #a1c4fd 0%, #c2e9fb 100%)"},
    {"name": "Gold", "value": "linear-gradient(135deg, #f7971e 0%, #ffd200 100%)"},
]
```

Plus a free-form text input for custom CSS gradient strings.

---

## File Changes Summary

### New Files

| File                                                                     | Purpose                                                  |
| ------------------------------------------------------------------------ | -------------------------------------------------------- |
| `backend/src/services/landing_page_renderers.py`                         | Extracted section renderers (~400 lines)                 |
| `backend/src/services/landing_page_styles.py`                            | Style/CSS utilities, theme/gradient presets (~200 lines) |
| `frontend/src/components/TenantAdmin/LandingPage/BlockSettingsTab.tsx`   | Per-block settings UI (Phase A)                          |
| `frontend/src/components/TenantAdmin/LandingPage/ThemeSelector.tsx`      | Theme preset cards (Phase B)                             |
| `frontend/src/components/TenantAdmin/LandingPage/GradientPicker.tsx`     | Gradient presets + free-form (Phase A)                   |
| `frontend/src/components/TenantAdmin/LandingPage/TypographySettings.tsx` | Font/spacing controls (Phase D)                          |

### Modified Files

| File                                                                      | Change                                                                  |
| ------------------------------------------------------------------------- | ----------------------------------------------------------------------- |
| `frontend/src/services/landingPageApi.ts`                                 | Add `BlockSettings` interface, extend `Section`                         |
| `frontend/src/components/TenantAdmin/LandingPage/BlockConfigurator.tsx`   | Add Settings tab                                                        |
| `frontend/src/components/TenantAdmin/LandingPage/BrandingSettings.tsx`    | Add theme selector + typography                                         |
| `frontend/src/components/TenantAdmin/LandingPage/blockTypeDefinitions.ts` | Expand layout options                                                   |
| `backend/src/services/landing_page_publish_service.py`                    | Trim to orchestration only (≤500 lines), delegate to renderers + styles |

---

## Backwards Compatibility

- Sections without `settings` field render with current defaults (no visual change)
- Existing branding without `theme` continues to use manually set colours
- No database migration required (settings stored in DynamoDB section structure)
- Existing published pages unaffected until re-published

## Security Considerations

- Gradient string is rendered into CSS — sanitize to prevent CSS injection (strip `url()`, `expression()`, `javascript:`)
- Image keys validated to be within tenant S3 prefix
- YouTube video IDs validated (alphanumeric + dashes only)
- No user-provided CSS classes or custom HTML injection

## Performance

- Google Fonts: only load fonts actually selected (not all 6)
- `<link rel="preconnect">` for font performance
- Carousel JS: minimal vanilla JS (< 2KB inline)
- No additional HTTP requests beyond font files
- Existing `loading="lazy"` for images preserved
