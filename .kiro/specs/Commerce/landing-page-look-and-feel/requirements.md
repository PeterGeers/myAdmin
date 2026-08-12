# Landing Page Look & Feel — Requirements

## User Stories

### US-1: Block-Level Visual Settings (Phase A)

**As a** tenant administrator,
**I want to** customize the background, spacing, and text colour of each block individually,
**so that** my landing page looks unique and professional without needing CSS knowledge.

**Acceptance Criteria:**

- [ ] AC-1.1: Each block in the editor has a "Settings" tab alongside existing property fields
- [ ] AC-1.2: I can set a block's background to a solid colour (colour picker)
- [ ] AC-1.3: I can set a block's background to a gradient (curated presets + free-form CSS input)
- [ ] AC-1.4: I can set a block's background to an image (reuses existing ImageUploader)
- [ ] AC-1.5: I can choose padding: compact (1rem), normal (2rem), or spacious (4rem)
- [ ] AC-1.6: I can choose text colour: dark, light, or auto (WCAG AA contrast)
- [ ] AC-1.7: I can toggle between contained (max-width) and full-width layout
- [ ] AC-1.8: I can choose border-radius: none, sm, md, lg
- [ ] AC-1.9: Blocks without settings render with current defaults (backwards compatible)
- [ ] AC-1.10: Published HTML reflects all block settings as inline styles
- [ ] AC-1.11: All settings work correctly on mobile viewports

### US-2: Global Theme Presets (Phase B)

**As a** tenant administrator,
**I want to** select from curated professional themes,
**so that** I can quickly achieve a polished look without manually configuring every setting.

**Acceptance Criteria:**

- [ ] AC-2.1: A "Theme" selector appears in Branding Settings with visual preview cards
- [ ] AC-2.2: At least 6 theme presets available (Professional, Warm, Modern, Nature, Minimal, Luxury)
- [ ] AC-2.3: Selecting a theme fills in colour fields but allows per-field overrides
- [ ] AC-2.4: A "Custom" option preserves current manual behaviour
- [ ] AC-2.5: Theme selection applies Google Fonts (heading + body) to published HTML
- [ ] AC-2.6: "Reset to theme defaults" button restores all overrides to the preset values
- [ ] AC-2.7: Theme changes preview in real-time in the editor preview panel

### US-3: Block Layout Variants (Phase C)

**As a** tenant administrator,
**I want to** choose from multiple layout arrangements per block type,
**so that** my page has visual variety and matches my content structure.

**Acceptance Criteria:**

- [ ] AC-3.1: Hero block supports: image-right, image-left, image-bg, split-diagonal, video-bg (YouTube)
- [ ] AC-3.2: About block supports: centered, image-left, image-right, card, timeline
- [ ] AC-3.3: Gallery block supports: grid-3, grid-4, masonry, carousel (auto-advances 10s + user controls)
- [ ] AC-3.4: Testimonials block supports: cards, carousel (auto-advances 10s), quote-large, grid
- [ ] AC-3.5: FAQ block supports: accordion (existing), two-column, side-by-side
- [ ] AC-3.6: Pricing block supports: default grid, horizontal, featured-center, comparison-table
- [ ] AC-3.7: CTA block supports: centered, split, banner, floating
- [ ] AC-3.8: New "Video" block type with YouTube embed (title, description, responsive 16:9 player)
- [ ] AC-3.9: Video block layouts: centered, full-width
- [ ] AC-3.10: Video block uses thumbnail preview (lazy-loads iframe on play click)
- [ ] AC-3.11: Layout selector shows visual thumbnails (SVG icons) for each option
- [ ] AC-3.12: Carousel auto-advances every 10 seconds, pauses on hover/interaction
- [ ] AC-3.13: Carousel has prev/next buttons and dot indicators
- [ ] AC-3.14: All new layouts are responsive (mobile/tablet/desktop)

### US-4: Typography & Global Spacing (Phase D)

**As a** tenant administrator,
**I want to** control fonts, spacing, and visual polish globally,
**so that** my page feels cohesive and matches my brand aesthetic.

**Acceptance Criteria:**

- [ ] AC-4.1: Font selector for headings (Inter, Lora, Poppins, Nunito, Playfair Display, System)
- [ ] AC-4.2: Font selector for body text (Inter, Lora, Poppins, Nunito, Lato, System)
- [ ] AC-4.3: Global spacing control: compact, normal, relaxed
- [ ] AC-4.4: Global border-radius: sharp, rounded, pill
- [ ] AC-4.5: Global shadow style: none, subtle, medium, dramatic
- [ ] AC-4.6: Font preview text shown alongside selectors
- [ ] AC-4.7: Google Fonts loaded via `<link>` tag in published HTML (only selected fonts)
- [ ] AC-4.8: All settings stored in ParameterService (`landing_page` namespace)

---

## Success Metrics

- Tenant admins can style a landing page without CSS in < 10 minutes
- Published HTML stays under 100KB (excluding images)
- All theme/setting combinations pass WCAG AA contrast when `text_color: auto` is used
- No JavaScript frameworks added to published HTML (vanilla JS only for carousels)
- Backwards compatible: existing published pages unaffected until re-published

## Out of Scope

- Custom CSS injection (security risk, out of scope)
- Animation/transition configuration per block
- Multi-page landing sites (single page only)
- Custom font uploads (Google Fonts library only)
- Self-hosted video (YouTube embed only for video-bg)
- A/B testing of visual variants (Phase 5 in parent spec)

## Constraints

- Published HTML must remain standalone (no React, no build step)
- All styling via inline `<style>` block — no external CSS files
- Responsive: all new options must work on mobile
- Accessibility: `text_color: auto` must ensure WCAG AA contrast ratio
- File size: published HTML < 100KB without images
- Backend file size: target 500 lines per file. Extract renderers to keep all files within the 500-line guideline.
