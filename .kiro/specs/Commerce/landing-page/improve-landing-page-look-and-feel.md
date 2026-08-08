# Improve Landing Page Look & Feel

## Problem Statement

The current landing page renders with hardcoded styles per block type. Tenant administrators have no control over background colours, spacing, typography, or visual themes beyond the two brand colours (`color_primary`, `color_accent`). This limits the ability to create distinctive, professional-looking pages.

## Goals

- Give tenant admins visual control **without** requiring CSS knowledge
- Provide curated theme presets for quick professional results
- Allow per-block customisation (background, spacing, text colour)
- Expand layout options per block type for visual variety
- Keep the published HTML lightweight (inline CSS, no JS frameworks)

---

## Phase A: Block-Level Settings (High Impact, Low Effort)

### Data Model Extension

Add a `settings` object to each section alongside `properties`:

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

| Setting                | Options                         | Default       | Description                                               |
| ---------------------- | ------------------------------- | ------------- | --------------------------------------------------------- |
| `background_type`      | `color`, `image`, `gradient`    | `color`       | What fills the block background                           |
| `background_color`     | Any hex colour                  | `transparent` | Solid background colour                                   |
| `background_image_key` | S3 image key                    | `""`          | Background image (uses CloudFront)                        |
| `background_gradient`  | CSS gradient string             | `""`          | e.g. `linear-gradient(135deg, #667eea, #764ba2)`          |
| `padding`              | `compact`, `normal`, `spacious` | `normal`      | Vertical padding (1rem / 2rem / 4rem)                     |
| `text_color`           | `dark`, `light`, `auto`         | `dark`        | Text colour scheme for readability                        |
| `max_width`            | `contained`, `full-width`       | `contained`   | Whether content respects max-width or bleeds edge-to-edge |
| `border_radius`        | `none`, `sm`, `md`, `lg`        | `none`        | Border radius on the block container                      |

### Frontend Changes

- Add a **"Settings" tab** in `BlockConfigurator` (alongside the existing properties fields)
- Settings tab renders:
  - Background type selector (radio buttons or segmented control)
  - Colour picker (when type = color)
  - Image uploader (when type = image, reuse existing `ImageUploader`)
  - Gradient input (when type = gradient, with presets dropdown)
  - Padding selector (3 buttons: compact / normal / spacious)
  - Text colour selector (dark / light / auto)
  - Max width toggle
  - Border radius selector

### Backend Changes

- `generate_index_html` in `landing_page_publish_service.py`: read `section.settings` and generate inline `style` attributes on the section wrapper `<div>`
- Map `padding` values: compact → `padding: 1rem 1.5rem`, normal → `padding: 2rem 1.5rem`, spacious → `padding: 4rem 1.5rem`
- Map `text_color`: dark → `color: #333`, light → `color: #fff`
- Map `background_type` → appropriate CSS (`background-color`, `background-image`, `background: linear-gradient(...)`)
- Existing sections without `settings` keep current behaviour (backwards compatible)

### Estimated Effort: 1–2 days

---

## Phase B: Global Theme Presets

### Theme Definitions

Curated colour/font/spacing combinations stored as a `theme` parameter in branding settings:

| Theme        | Primary   | Accent    | Section BG | Font Heading     | Font Body    | Feel            |
| ------------ | --------- | --------- | ---------- | ---------------- | ------------ | --------------- |
| Professional | `#2D5F8A` | `#F4A261` | white      | Inter            | Inter        | Clean corporate |
| Warm         | `#8B4513` | `#DAA520` | `#FFF8F0`  | Lora             | Nunito       | Hospitality/B&B |
| Modern       | `#1a1a2e` | `#e94560` | `#16213e`  | Poppins          | Poppins      | Bold tech       |
| Nature       | `#2d6a4f` | `#95d5b2` | `#f0f7f4`  | Nunito           | Nunito       | Eco/outdoor     |
| Minimal      | `#333333` | `#666666` | white      | System stack     | System stack | Ultra-clean     |
| Luxury       | `#1c1c1c` | `#c9a96e` | `#0d0d0d`  | Playfair Display | Lato         | High-end        |

### Data Model

```json
// ParameterService: namespace="landing_page", key="theme"
{
  "preset": "professional",
  "overrides": {
    "color_primary": "#2D5F8A",
    "color_accent": "#custom-override"
  }
}
```

### Frontend Changes

- Add a **Theme selector** in BrandingSettings (visual cards with preview swatches)
- Selecting a preset fills in the colour fields but allows per-field overrides
- "Custom" option for fully manual colour control (current behaviour)

### Backend Changes

- `resolve_branding()` applies theme defaults first, then merges overrides on top
- `generate_index_html()` includes Google Font `<link>` tags based on theme's fonts
- Theme CSS variables injected into `<style>` block

### Estimated Effort: 1–2 days

---

## Phase C: Block Layout Variants

### Expanded Layout Options per Block Type

| Block type   | Current       | New options                                                                                 |
| ------------ | ------------- | ------------------------------------------------------------------------------------------- |
| Hero         | `image-right` | `image-left`, `image-bg` (full-bleed background image), `split-diagonal`, `video-bg`        |
| About        | `centered`    | `image-left`, `image-right`, `card` (elevated card), `timeline`                             |
| Gallery      | `grid-3`      | `grid-4`, `masonry`, `carousel` (with prev/next), `lightbox`                                |
| Testimonials | default grid  | `cards`, `carousel`, `quote-large` (single rotating), `grid`                                |
| FAQ          | accordion     | `two-column` (questions split across 2 cols), `side-by-side` (Q left, A right)              |
| Pricing      | default grid  | `horizontal` (features table), `featured-center` (middle card enlarged), `comparison-table` |
| CTA          | centered      | `split` (text left, form right), `banner` (thin full-width strip), `floating`               |

### Frontend Changes

- Layout selector in `BlockConfigurator` header (already exists as a concept, expand options)
- Visual thumbnails for each layout option (small SVG icons showing the arrangement)

### Backend Changes

- Each new layout needs a corresponding `_render_{type}_{layout}` method in the HTML generator
- CSS additions per layout variant in the `<style>` block
- Carousel layouts need minimal inline JS (vanilla, no dependencies)

### Estimated Effort: 3–5 days (depends on number of variants)

---

## Phase D: Typography & Global Spacing

### Branding Extensions

Add to the existing branding/settings:

| Setting                | Options                                                | Default   | Description                                     |
| ---------------------- | ------------------------------------------------------ | --------- | ----------------------------------------------- |
| `font_heading`         | Inter, Lora, Poppins, Nunito, Playfair Display, System | System    | Google Font for headings                        |
| `font_body`            | Inter, Lora, Poppins, Nunito, Lato, System             | System    | Google Font for body text                       |
| `base_spacing`         | `compact`, `normal`, `relaxed`                         | `normal`  | Global spacing multiplier                       |
| `border_radius_global` | `sharp`, `rounded`, `pill`                             | `rounded` | Global border-radius for cards, buttons, images |
| `shadow_style`         | `none`, `subtle`, `medium`, `dramatic`                 | `subtle`  | Box-shadow intensity for cards                  |

### Frontend Changes

- Font dropdowns in BrandingSettings with live preview text
- Spacing/radius as visual selectors (small preview rectangles)

### Backend Changes

- Add Google Fonts `<link>` to HTML `<head>` for selected fonts
- Map spacing to CSS variables: `--spacing-section`, `--spacing-element`
- Map border-radius to CSS variables: `--radius-sm`, `--radius-md`, `--radius-lg`
- Map shadow to CSS variables: `--shadow-card`, `--shadow-hover`

### Estimated Effort: 1–2 days

---

## Implementation Priority

```
Phase A ─── Block settings (background, padding, text colour)
   │        Highest impact for least effort. Every existing page
   │        immediately looks more custom.
   │
Phase B ─── Theme presets
   │        Quick professional results for non-designer users.
   │        Builds on Phase A settings.
   │
Phase D ─── Typography & spacing
   │        Refines the overall feel. Small effort, noticeable polish.
   │
Phase C ─── Layout variants
            Biggest effort. Expand incrementally — add 1-2 new layouts
            per block type per sprint rather than all at once.
```

## Dependencies

- No new packages required (inline CSS, Google Fonts via `<link>`)
- No database changes (settings stored in existing DynamoDB sections structure)
- No infrastructure changes (CloudFront already serves images)
- Backwards compatible: sections without `settings` render with current defaults

## Design Constraints

- Published HTML must remain standalone (no React, no build step)
- Keep HTML file size reasonable (< 100KB without images)
- All styling via inline `<style>` block — no external CSS files
- Responsive: all new options must work on mobile
- Accessibility: `text_color: auto` must ensure WCAG AA contrast ratio against the chosen background

## Open Questions

1. Should theme presets be system-level (hardcoded in code) or tenant-configurable (stored as parameters)?
2. Do we need a "reset block settings to theme defaults" button?
3. Should gradient presets be curated (6-8 options) or allow free-form CSS input?
4. For `video-bg` hero layout: support YouTube embed or self-hosted video only?
5. Carousel: vanilla JS inline, or skip carousel and offer grid-only for simplicity?
