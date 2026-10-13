# Implementation Plan: Landing Page Look & Feel

## Overview

Extend the existing landing page feature with visual customization capabilities: per-block styling (backgrounds, spacing, text colour), global theme presets, expanded layout variants per block type, typography/spacing controls, and a new Video block. Prerequisite refactoring splits the 1171-line publish service into three files (≤ 500 lines each).

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1", "2"] },
    { "id": 1, "tasks": ["3", "4"] },
    { "id": 2, "tasks": ["5"] },
    { "id": 3, "tasks": ["6", "7"] },
    { "id": 4, "tasks": ["8", "9", "10"] },
    { "id": 5, "tasks": ["11", "12", "13", "14", "15", "16", "17", "18"] },
    { "id": 6, "tasks": ["19", "20", "21"] },
    { "id": 7, "tasks": ["22", "23", "24"] },
    { "id": 8, "tasks": ["25", "26", "27", "28"] },
    { "id": 9, "tasks": ["29", "30"] },
    { "id": 10, "tasks": ["31", "32", "33", "34"] },
    { "id": 11, "tasks": ["35", "36", "37", "38", "39"] },
    { "id": 12, "tasks": ["40", "41", "42", "43"] },
    { "id": 13, "tasks": ["44", "45", "46", "47"] },
    { "id": 14, "tasks": ["48", "49"] },
    { "id": 15, "tasks": ["50", "51", "52"] },
    { "id": 16, "tasks": ["53", "54", "55", "56", "57", "58"] },
    { "id": 17, "tasks": ["59", "60", "61", "62"] },
    { "id": 18, "tasks": ["63", "64", "65", "66", "67"] },
    { "id": 19, "tasks": ["68", "69", "70", "71"] },
    { "id": 20, "tasks": ["72", "73", "74"] },
    { "id": 21, "tasks": ["75", "76", "77", "78"] },
    { "id": 22, "tasks": ["79", "80", "81", "82", "83"] },
    { "id": 23, "tasks": ["84", "85", "86"] },
    { "id": 24, "tasks": ["87", "88", "89", "90", "91", "92", "93", "94"] },
    { "id": 25, "tasks": ["95", "96", "97", "98", "99"] },
    { "id": 26, "tasks": ["100", "101", "102", "103", "104", "105"] }
  ]
}
```

## Tasks

### Phase 0: Backend Refactoring (prerequisite for all phases — 0.5 day)

- [x] 1. Create `backend/src/services/landing_page_renderers.py` — extract all `_render_*` methods into `LandingPageRenderers` class (~400 lines)
- [x] 2. Create `backend/src/services/landing_page_styles.py` — extract style/CSS utilities (`_build_section_style`, `_auto_text_color`, `_build_font_links`, gradient/theme presets, CSS variables) (~200 lines)
- [x] 3. Trim `landing_page_publish_service.py` to orchestration only (publish, unpublish, resolve\_\*, generate_index_html shell) — target ≤ 500 lines
- [x] 4. Update `LandingPagePublishService` to instantiate and delegate to `LandingPageRenderers` + `LandingPageStyles`
- [x] 5. Verify existing publish pipeline still works after extraction (run existing tests)

**Exit criteria:** Three files, each ≤ 500 lines. All existing tests pass. No behaviour changes.

---

### Phase A: Block-Level Settings (1–2 days)

**A.1 Data Model & Types**

- [x] 6. Add `BlockSettings` interface to `landingPageApi.ts` and extend `Section` type with optional `settings` field
- [x] 7. Define default settings constants in a shared file (`blockSettingsDefaults.ts`)
- [x] 8. Ensure `saveDraft` and `getDraft` correctly serialize/deserialize `settings`

**A.2 Frontend: Settings Tab UI**

- [x] 9. Create `BlockSettingsTab.tsx` component with all settings controls
- [x] 10. Add tab switcher (Content / Settings) to `BlockConfigurator.tsx`
- [x] 11. Background type selector (radio: Colour / Image / Gradient)
- [x] 12. Colour picker for `background_color` (Chakra `Input type="color"` or custom)
- [x] 13. Image uploader for `background_image_key` (reuse existing `ImageUploader`)
- [x] 14. Create `GradientPicker.tsx` — preset buttons + free-form input
- [x] 15. Padding selector (3 segmented buttons: compact / normal / spacious)
- [x] 16. Text colour selector (3 segmented buttons: dark / light / auto)
- [x] 17. Max-width toggle (contained / full-width)
- [x] 18. Border-radius selector (4 buttons: none / sm / md / lg)
- [x] 19. Wire settings changes to `onUpdate` → auto-save pipeline

**A.3 Backend: HTML Generation**

- [x] 20. Add `build_section_style(settings, img_base)` method to `landing_page_styles.py`
- [x] 21. Add `auto_text_color(bg_hex)` utility for WCAG contrast calculation
- [x] 22. Update `_render_sections_html` to read `settings` and wrap sections with inline styles
- [x] 23. Sanitize gradient strings (strip `url()`, `expression()`, `javascript:`)
- [x] 24. Ensure sections without `settings` render with existing defaults (backwards compat)

**A.4 Preview & Testing**

- [x] 25. Update `PreviewPanel.tsx` to apply block settings visually in editor preview
- [x] 26. Verify responsive behaviour of all settings on mobile viewports
- [x] 27. Test publish round-trip: settings saved → published HTML has correct inline styles
- [x] 28. Test auto-contrast: verify WCAG AA compliance when `text_color: auto`

**Exit criteria:** Any block can be individually styled with background, padding, text colour, width, and radius. Published HTML renders correctly. Existing pages unaffected.

---

### Phase B: Global Theme Presets (1–2 days)

**B.1 Theme Definitions**

- [x] 29. Create theme presets constant (Python: `THEME_PRESETS` dict in `landing_page_styles.py`)
- [x] 30. Create matching frontend constant with theme metadata (colours, font names, preview data)

**B.2 Backend: Theme Resolution**

- [x] 31. Extend `resolve_branding()` to read `landing_page.theme` param and apply preset + overrides
- [x] 32. Add `build_font_links(branding)` method — generates Google Font `<link>` tags
- [x] 33. Inject font links into `<head>` of `generate_index_html`
- [x] 34. Inject CSS font-family variables into `<style>` block based on theme fonts

**B.3 Frontend: Theme Selector UI**

- [x] 35. Create `ThemeSelector.tsx` — visual cards with colour swatches and font preview
- [x] 36. Integrate into `BrandingSettings.tsx` (above colour pickers)
- [x] 37. Selecting a theme fills colour/font fields; allow per-field overrides
- [x] 38. "Custom" card for fully manual control (current behaviour)
- [x] 39. "Reset to theme defaults" button — clears overrides, restores preset values

**B.4 API & Storage**

- [x] 40. Save theme selection to ParameterService: `landing_page.theme` → `{"preset": "...", "overrides": {...}}`
- [x] 41. Load theme on `getBrandingSettings` response
- [x] 42. Update `LandingPageSettings` TypeScript interface with `theme` field

**B.5 Testing**

- [x] 43. Verify each theme produces correct colours + fonts in published HTML
- [x] 44. Verify override merging (preset defaults + manual overrides)
- [x] 45. Verify reset button restores to clean preset state
- [x] 46. Verify "Custom" theme preserves existing manual behaviour

**Exit criteria:** Admin can select a theme, see immediate preview, override individual fields, reset to defaults. Published HTML includes correct Google Fonts and colour scheme.

---

### Phase D: Typography & Global Spacing (1–2 days)

**D.1 Backend**

- [x] 47. Add ParameterService keys: `font_heading`, `font_body`, `base_spacing`, `border_radius_global`, `shadow_style`
- [x] 48. Extend `resolve_branding()` to include typography/spacing fields
- [x] 49. Generate CSS variables block in `<style>` (`:root { --font-heading: ...; }`)
- [x] 50. Map spacing/radius/shadow settings to CSS variable values
- [x] 51. Update existing CSS rules to use CSS variables where applicable

**D.2 Frontend**

- [x] 52. Create `TypographySettings.tsx` — font dropdowns with live preview text
- [x] 53. Spacing selector (compact / normal / relaxed) — visual buttons
- [x] 54. Border-radius selector (sharp / rounded / pill) — visual preview rectangles
- [x] 55. Shadow selector (none / subtle / medium / dramatic) — card previews
- [x] 56. Integrate into `BrandingSettings.tsx` (below theme selector)
- [x] 57. Save all typography settings to ParameterService

**D.3 Testing**

- [x] 58. Verify Google Fonts loaded correctly for each font option
- [x] 59. Verify CSS variables applied to all section types
- [x] 60. Verify spacing/radius/shadow visible on published page
- [x] 61. Verify "system" font option produces no Google Font request

**Exit criteria:** Admin controls fonts, spacing, border-radius, and shadows globally. Published HTML uses CSS variables and loads only required Google Fonts.

---

### Phase C: Block Layout Variants (3–5 days)

**C.1 Hero Layout Variants**

- [x] 62. `image-left` — mirror of existing `image-right`
- [x] 63. `image-bg` — full-bleed background image with text overlay
- [x] 64. `split-diagonal` — diagonal clip-path split between image and text
- [x] 65. `video-bg` — YouTube embed (autoplay, muted, looped) with text overlay
- [x] 66. Add `video_url` property to hero block in `renderFieldsForType`

**C.2 About Layout Variants**

- [x] 67. `image-left` — image on left, text on right
- [x] 68. `image-right` — image on right, text on left
- [x] 69. `card` — elevated card with shadow, centred content
- [x] 70. `timeline` — vertical timeline with milestones (requires `timeline_items` property)

**C.3 Gallery Layout Variants**

- [x] 71. `grid-4` — 4-column grid
- [x] 72. `masonry` — CSS columns masonry layout
- [x] 73. `carousel` — auto-advancing (10s) with prev/next + dots + pause on hover

**C.4 Testimonials Layout Variants**

- [x] 74. `cards` — card grid (current default, formalize)
- [x] 75. `carousel` — auto-advancing (10s) single testimonial with prev/next + dots
- [x] 76. `quote-large` — single large quote, rotating
- [x] 77. `grid` — compact grid without cards

**C.5 FAQ Layout Variants**

- [x] 78. `two-column` — questions split across 2 columns
- [x] 79. `side-by-side` — question on left, answer on right (table-like)

**C.6 Pricing Layout Variants**

- [x] 80. `horizontal` — features comparison table
- [x] 81. `featured-center` — middle card enlarged/highlighted
- [x] 82. `comparison-table` — full table with feature rows

**C.7 CTA Layout Variants**

- [x] 83. `split` — text left, button/form right
- [x] 84. `banner` — thin full-width strip
- [x] 85. `floating` — fixed bottom bar with CTA

**C.8 Video Block (new block type)**

- [x] 86. Add `video` to block type definitions (`blockTypeDefinitions.ts`)
- [x] 87. Create `VideoBlock` field renderer in `BlockConfigurator` (video_url, title, description)
- [x] 88. YouTube URL validation (accept `youtube.com/watch?v=`, `youtu.be/`, reject others)
- [x] 89. Backend: `_render_video()` — extract video ID, generate responsive 16:9 iframe
- [x] 90. Use `youtube-nocookie.com` for privacy-enhanced embedding
- [x] 91. Thumbnail lazy-load: show YouTube thumbnail image, replace with iframe on click (inline JS)
- [x] 92. Layout `centered` (max-width 800px) and `full-width`
- [x] 93. Preview in editor: render video thumbnail + title in `PreviewPanel`

**C.9 Carousel JS & Frontend**

- [x] 94. Add inline carousel JS to published HTML (vanilla, data-attribute based)
- [x] 95. Carousel auto-advances every 10s, pauses on hover/interaction, resumes after 10s idle
- [x] 96. Touch swipe support for mobile
- [x] 97. Update `blockTypeDefinitions.ts` with all new layout options (including `video`)
- [x] 98. Add visual SVG thumbnails for layout selector in BlockConfigurator

**C.10 Testing**

- [x] 99. Test all hero variants (responsive)
- [x] 100. Test all gallery variants including carousel auto-advance timing
- [x] 101. Test video-bg with YouTube URL parsing
- [x] 102. Test Video block (centred + full-width, thumbnail lazy-load)
- [x] 103. Test all layout variants on mobile/tablet/desktop
- [x] 104. Verify carousel pause/resume behaviour

**Exit criteria:** All block types have expanded layout options. New Video block works end-to-end. Carousels auto-advance, respond to user interaction, and work on mobile.

---

## Notes

### Implementation Priority

```
Phase 0 (Refactor) → Phase A (Block settings) → Phase B (Themes) → Phase D (Typography) → Phase C (Layouts)
    0.5 day               1–2 days                 1–2 days             1–2 days              3–5 days
```

Phase 0 is a prerequisite for all work (refactor before adding features). Phase A provides highest impact with least effort. Phase B builds on A. Phase D is small refinement. Phase C is largest effort — implement incrementally (1–2 layouts per block type per sprint).

### Dependencies

| Dependency                         | Required for       | Status                     |
| ---------------------------------- | ------------------ | -------------------------- |
| Existing landing page (Phases 1–4) | All                | ✅ Complete                |
| `BlockConfigurator.tsx`            | Phase A            | ✅ Exists                  |
| `BrandingSettings.tsx`             | Phase B, D         | ✅ Exists                  |
| `ImageUploader.tsx`                | Phase A (bg image) | ✅ Exists                  |
| `blockTypeDefinitions.ts`          | Phase C (layouts)  | ✅ Exists                  |
| ParameterService                   | Phase B, D         | ✅ Exists                  |
| Google Fonts (external)            | Phase B, D         | No dependency to provision |
| No new npm packages                | All                | ✅                         |
| No database migrations             | All                | ✅                         |
| No new AWS services                | All                | ✅                         |

### Estimated Total: 6.5–12 days

| Phase | Estimate | Notes                                          |
| ----- | -------- | ---------------------------------------------- |
| 0     | 0.5 day  | Prerequisite refactoring — no behaviour change |
| A     | 1–2 days | Highest ROI                                    |
| B     | 1–2 days | Builds on A                                    |
| D     | 1–2 days | Small, high polish                             |
| C     | 3–5 days | Largest — can be done incrementally            |
