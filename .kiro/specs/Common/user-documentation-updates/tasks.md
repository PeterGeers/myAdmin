# Implementation Plan: User Documentation Updates

## Overview

This plan covers completing the Media Assets documentation (Storage Summary section + verification pass) and creating four new Landing Page sub-pages (theme-presets, gradients, typography, block-settings) in both Dutch and English. All tasks involve creating or modifying Markdown files in the MkDocs documentation site and updating the navigation configuration.

## Tasks

- [x] 1. Media Assets — Storage Summary section and verification
  - [x] 1.1 Add Storage Summary (Opslag) section to media-assets.md (Dutch)
    - Add a dedicated "Opslag overzicht" section to `docs/docs/tenant-admin/media-assets.md`
    - Document total storage usage display, storage per category breakdown, orphaned asset count and its meaning
    - Include explanation of how to interpret the dashboard metrics
    - Use a table for the category breakdown and admonitions for tips
    - _Requirements: 1.1, 1.2_

  - [x] 1.2 Add Storage Summary section to media-assets.en.md (English)
    - Add the English translation of the Storage Summary section to `docs/docs/tenant-admin/media-assets.en.md`
    - Match structure and content of the Dutch version
    - _Requirements: 1.3_

  - [x] 1.3 Run verification pass on media-assets.md against all acceptance criteria
    - Review `docs/docs/tenant-admin/media-assets.md` against Requirements 2–5 acceptance criteria
    - Verify: all scan phases documented (S3 scanning, registry comparison, reference verification, eligible transition)
    - Verify: all scan result categories present (Consistent, Unregistered, Missing, Stale References, Newly Eligible)
    - Verify: import procedure with step-by-step instructions for unregistered objects
    - Verify: delete procedure with permanence warning for S3 deletion
    - Verify: duplicate detection explanation (content hash) and merge workflow with reference transfer
    - Verify: retention defaults table (Invoices 2555d, Branding 30d, Templates 90d, Landing Pages 7d)
    - Verify: system defaults vs tenant overrides distinction
    - Verify: deletion approval workflow and invoice compliance warning (7-year)
    - Fix any gaps found during verification
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 3.1, 3.2, 3.3, 4.1, 4.2, 4.3, 5.1, 5.2, 5.3_

  - [x] 1.4 Run verification pass on media-assets.en.md against all acceptance criteria
    - Verify the English version has the same completeness as Dutch
    - Fix any gaps found during verification
    - _Requirements: 2.5, 3.4, 4.4, 5.4_

- [x] 2. Checkpoint — Media Assets verification complete
  - Ensure Media Assets documentation is complete for both languages, ask the user if questions arise.

- [x] 3. Landing Page — Theme Presets sub-page
  - [x] 3.1 Create theme-presets.md (Dutch)
    - Create `docs/docs/landing-page/theme-presets.md`
    - Include: overview of theme selection in Look & Feel tab
    - Include: table listing all 6 presets (Professional, Warm, Modern, Nature, Minimal, Luxury) with colour and font characteristics
    - Include: step-by-step instructions for selecting a theme preset
    - Include: Custom theme option explanation for full manual control
    - Include: "Reset naar thema-standaarden" functionality description
    - Use consistent admonitions (tip/warning/note) and tables for structured data
    - _Requirements: 6.1, 6.2, 6.3, 11.1, 11.2, 11.3, 11.4_

  - [x] 3.2 Create theme-presets.en.md (English)
    - Create `docs/docs/landing-page/theme-presets.en.md`
    - English translation of theme-presets.md, matching structure exactly
    - _Requirements: 6.4_

- [x] 4. Landing Page — Gradients sub-page
  - [x] 4.1 Create gradients.md (Dutch)
    - Create `docs/docs/landing-page/gradients.md`
    - Include: overview of gradient backgrounds for blocks
    - Include: table with all 8 gradient presets (Sunset, Ocean, Forest, Peach, Night, Warm, Sky, Gold)
    - Include: step-by-step instructions for applying a preset
    - Include: free-form CSS gradient input explanation
    - Include: live preview strip description
    - Use consistent admonitions and tables
    - _Requirements: 7.1, 7.2, 7.3, 11.1, 11.2, 11.3, 11.4_

  - [x] 4.2 Create gradients.en.md (English)
    - Create `docs/docs/landing-page/gradients.en.md`
    - English translation of gradients.md, matching structure exactly
    - _Requirements: 7.4_

- [x] 5. Landing Page — Typography sub-page
  - [x] 5.1 Create typography.md (Dutch)
    - Create `docs/docs/landing-page/typography.md`
    - Include: overview of typography settings in Look & Feel tab
    - Include: table listing all fonts (System Default, Inter, Lora, Poppins, Nunito, Playfair Display, Lato) with heading/body distinction
    - Include: base spacing options (compact, normal, relaxed)
    - Include: border-radius options (sharp, rounded, pill) with visual descriptions
    - Include: shadow style options (none, subtle, medium, dramatic) with visual descriptions
    - Use consistent admonitions and tables
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 11.1, 11.2, 11.3, 11.4_

  - [x] 5.2 Create typography.en.md (English)
    - Create `docs/docs/landing-page/typography.en.md`
    - English translation of typography.md, matching structure exactly
    - _Requirements: 8.5_

- [x] 6. Landing Page — Block Settings sub-page
  - [x] 6.1 Create block-settings.md (Dutch)
    - Create `docs/docs/landing-page/block-settings.md`
    - Include: overview of per-block visual customization
    - Include: background types section — solid colour (colour picker), background image (upload), gradient (link to gradients page)
    - Include: padding options (compact, normal, spacious)
    - Include: text colour options (dark, light, auto) with auto-detection explanation
    - Include: max-width options (contained, full-width)
    - Include: border-radius options (none, sm, md, lg)
    - Use relative MkDocs links when referencing the gradients page
    - Use consistent admonitions and tables
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 10.3, 11.1, 11.2, 11.3, 11.4_

  - [x] 6.2 Create block-settings.en.md (English)
    - Create `docs/docs/landing-page/block-settings.en.md`
    - English translation of block-settings.md, matching structure exactly
    - _Requirements: 9.6_

- [x] 7. Checkpoint — All Landing Page sub-pages created
  - Ensure all 4 sub-pages exist in both Dutch and English, ask the user if questions arise.

- [x] 8. Navigation and build verification
  - [x] 8.1 Update mkdocs.yml navigation structure
    - Update `docs/mkdocs.yml` to expand the Landing Page nav entry into sub-pages
    - Change from single `Landing Page: landing-page/index.md` to a section with:
      - Overzicht: landing-page/index.md
      - Thema presets: landing-page/theme-presets.md
      - Verlopen achtergronden: landing-page/gradients.md
      - Typografie: landing-page/typography.md
      - Blokinstellingen: landing-page/block-settings.md
    - _Requirements: 10.1, 10.2_

  - [x] 8.2 Run mkdocs build --strict to verify all pages resolve
    - Execute `cd docs && mkdocs build --strict` from project root
    - Verify: no broken internal links, no missing nav entries, no markdown warnings
    - Fix any issues that arise from the build
    - _Requirements: 10.1, 10.2, 10.3_

- [x] 9. Final checkpoint — Documentation complete
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- No property-based tests apply — this is a documentation-only feature with no backend/frontend code changes
- Content correctness is validated through `mkdocs build --strict` and human review
- Dutch is always written first, English follows with matching structure
- All files use MkDocs Material conventions: admonitions, tables, numbered lists for procedures
- The i18n plugin automatically associates `.en.md` files as English translations
- Cross-references between Landing Page sub-pages must use relative MkDocs links

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "3.1", "4.1", "5.1", "6.1"] },
    { "id": 1, "tasks": ["1.2", "3.2", "4.2", "5.2", "6.2"] },
    { "id": 2, "tasks": ["1.3"] },
    { "id": 3, "tasks": ["1.4", "8.1"] },
    { "id": 4, "tasks": ["8.2"] }
  ]
}
```
