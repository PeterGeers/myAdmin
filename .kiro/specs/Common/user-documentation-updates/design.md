# Design Document: User Documentation Updates

## Overview

This design covers the documentation updates for two features: **Media Asset Management** (verifying/completing existing docs) and **Landing Page Look & Feel** (new sections covering theming, gradients, typography, and block-level visual settings).

The documentation system uses **MkDocs Material** with the `i18n` plugin for bilingual support (Dutch primary, English secondary). All documentation lives under `docs/docs/` and is built from `docs/mkdocs.yml`.

### Design Decisions

| Decision               | Choice                                                                      | Rationale                                                                                                                                                                                                      |
| ---------------------- | --------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| File organization      | Extend existing files vs. new pages                                         | Both `media-assets.md` and `landing-page/index.md` already exist and cover these features. New sections are added in-place rather than creating separate pages, keeping navigation simple.                     |
| Landing Page sub-pages | Create dedicated sub-pages for Theme, Gradients, Typography, Block Settings | The existing `index.md` already covers basics (blocks, branding, SEO, publishing). Adding 4 new major sections would make it too long (>500 lines). Sub-pages under `landing-page/` keep content discoverable. |
| Media Assets structure | Keep single-page format                                                     | The existing page is well-structured with clear sections. Verify completeness and add the "Opslag" (Storage Summary) section which is currently thin.                                                          |
| Language workflow      | Write Dutch first, then create English translation                          | Dutch is primary language; English follows the same structure with translated content.                                                                                                                         |
| Admonition style       | Follow existing conventions                                                 | Use `!!! tip`, `!!! warning`, `!!! note` consistently as in existing docs.                                                                                                                                     |

## Architecture

### Documentation Site Structure

```
docs/
├── mkdocs.yml                          # Navigation & plugin config
└── docs/
    ├── tenant-admin/
    │   ├── media-assets.md             # Dutch (UPDATE - verify/complete)
    │   └── media-assets.en.md          # English (UPDATE - verify/complete)
    └── landing-page/
        ├── index.md                    # Dutch - existing basics
        ├── index.en.md                 # English - existing basics
        ├── theme-presets.md            # Dutch - NEW
        ├── theme-presets.en.md         # English - NEW
        ├── gradients.md               # Dutch - NEW
        ├── gradients.en.md            # English - NEW
        ├── typography.md              # Dutch - NEW
        ├── typography.en.md           # English - NEW
        ├── block-settings.md          # Dutch - NEW
        └── block-settings.en.md       # English - NEW
```

### MkDocs Navigation Update

The `nav` section in `mkdocs.yml` will be updated to add the new Landing Page sub-pages:

```yaml
- Tenant Beheer:
    # ... existing items ...
    - Media Assets: tenant-admin/media-assets.md
    - Landing Page:
        - Overzicht: landing-page/index.md
        - Thema presets: landing-page/theme-presets.md
        - Verlopen achtergronden: landing-page/gradients.md
        - Typografie: landing-page/typography.md
        - Blokinstellingen: landing-page/block-settings.md
```

## Components and Interfaces

### Component 1: Media Assets Manual Updates

The existing `media-assets.md` / `media-assets.en.md` files are already comprehensive. The update verifies completeness against the acceptance criteria and ensures all tab sections are fully documented.

**Current state analysis:**

| Section             | Status      | Action Required                                        |
| ------------------- | ----------- | ------------------------------------------------------ |
| Overzicht           | ✅ Complete | None                                                   |
| Tabs overview table | ✅ Complete | Verify "Opslag" tab description                        |
| Scan procedures     | ✅ Complete | Verify all scan phases documented                      |
| Niet-geregistreerd  | ✅ Complete | Verify import/delete procedures                        |
| Verwijdering        | ✅ Complete | Verify compliance warning present                      |
| Bewaartermijn       | ✅ Complete | Verify all default values listed                       |
| Duplicaten          | ✅ Complete | Verify merge workflow documented                       |
| Opslag (Dashboard)  | ⚠️ Thin     | Add dedicated section with storage metrics explanation |
| FAQ                 | ✅ Complete | None                                                   |
| Problemen oplossen  | ✅ Complete | None                                                   |

**Required updates for Media Assets:**

1. **Storage Summary section** — Add a dedicated "Opslag overzicht" section explaining:
   - Total storage usage display
   - Storage breakdown per category (bar chart / table)
   - Orphaned asset count and what it means
   - How to interpret the dashboard metrics

2. **Verification pass** — Confirm all acceptance criteria are addressed:
   - All scan phases listed (S3 scanning, registry comparison, reference verification, eligible transition)
   - All scan result categories (Consistent, Unregistered, Missing, Stale References, Newly Eligible)
   - Step-by-step for import and delete of unregistered objects
   - Warning about permanence of S3 deletion
   - Duplicate detection explanation (content hash)
   - Merge workflow with reference transfer
   - Retention defaults table with correct values
   - System defaults vs tenant overrides distinction
   - Deletion approval workflow
   - Invoice compliance warning (7-year)

### Component 2: Landing Page — Theme Presets

**File:** `landing-page/theme-presets.md` (Dutch) + `theme-presets.en.md` (English)

**Content structure:**

```markdown
# Thema Presets

## Overzicht

Brief intro to theme selection in Look & Feel tab.

## Beschikbare presets

Table listing all 6 presets with their characteristics:
| Preset | Kleuren | Lettertype | Stijl |
| Professional | ... | ... | ... |
| Warm | ... | ... | ... |
| Modern | ... | ... | ... |
| Nature | ... | ... | ... |
| Minimal | ... | ... | ... |
| Luxury | ... | ... | ... |

## Een preset kiezen

Step-by-step instructions for selecting a theme preset.

## Aangepast thema (Custom)

Explanation of Custom option for full manual control.

## Reset naar thema-standaarden

How the "Reset to theme defaults" button works when a named theme is selected.
```

### Component 3: Landing Page — Gradients

**File:** `landing-page/gradients.md` (Dutch) + `gradients.en.md` (English)

**Content structure:**

```markdown
# Verloop achtergronden (Gradients)

## Overzicht

Brief intro to gradient backgrounds for blocks.

## Beschikbare preset verlopen

Table with all 8 gradient presets:
| Naam | Beschrijving/kleuren |
| Sunset | ... |
| Ocean | ... |
| Forest | ... |
| Peach | ... |
| Night | ... |
| Warm | ... |
| Sky | ... |
| Gold | ... |

## Een preset toepassen

Step-by-step instructions.

## Eigen CSS verloop invoeren

How to use the free-form CSS gradient input field.

## Live preview

Explanation of the preview strip showing the selected gradient.
```

### Component 4: Landing Page — Typography

**File:** `landing-page/typography.md` (Dutch) + `typography.en.md` (English)

**Content structure:**

```markdown
# Typografie instellingen

## Overzicht

Brief intro to typography settings in Look & Feel tab.

## Lettertypen

### Beschikbare lettertypen

Table listing fonts with preview info:
| Lettertype | Type | Stijl |
| System Default | Sans-serif | Standaard systeemlettertype |
| Inter | Sans-serif | Modern, clean |
| Lora | Serif | Elegant |
| Poppins | Sans-serif | Rounded, friendly |
| Nunito | Sans-serif | Soft, warm |
| Playfair Display | Serif | Classic, editorial |
| Lato | Sans-serif | Neutral, readable |

### Lettertype voor koppen vs tekst

Separate font selection for headings and body text.

## Basisafstand (Spacing)

Table: compact | normal | relaxed

## Rand-radius (Border radius)

Table: sharp | rounded | pill — with visual descriptions

## Schaduwstijl (Shadow)

Table: none | subtle | medium | dramatic — with visual descriptions
```

### Component 5: Landing Page — Block Settings

**File:** `landing-page/block-settings.md` (Dutch) + `block-settings.en.md` (English)

**Content structure:**

```markdown
# Blokinstellingen

## Overzicht

Brief intro to per-block visual customization.

## Achtergrond

### Effen kleur

Colour picker usage.

### Achtergrondafbeelding

Image upload for block background.

### Verloop (Gradient)

Using the Gradient Picker for block backgrounds (link to gradients page).

## Padding

Table: compact | normal | spacious

## Tekstkleur

Table: dark | light | auto — explanation of auto-detection.

## Maximale breedte

Table: contained | full-width

## Rand-radius

Table: none | sm | md | lg
```

## Data Models

This feature does not introduce any data models. All work involves static Markdown documentation files rendered by MkDocs Material.

**File naming convention:**

- Dutch (primary): `{page-name}.md`
- English (secondary): `{page-name}.en.md`

The `i18n` plugin in MkDocs automatically associates `.en.md` files as English translations of the corresponding `.md` file.

## Error Handling

Not applicable for this documentation-only feature. However, the following build-time checks apply:

| Check                  | Tool                    | Action                                              |
| ---------------------- | ----------------------- | --------------------------------------------------- |
| Broken internal links  | `mkdocs build --strict` | Fails build if relative links don't resolve         |
| Missing nav entries    | `mkdocs build`          | Warns if files in nav don't exist                   |
| Markdown syntax errors | MkDocs build log        | Review warnings for malformed admonitions or tables |
| i18n coverage          | Manual review           | Ensure every `.md` has a corresponding `.en.md`     |

## Correctness Properties

### Property 1: No testable properties

_For any_ documentation-only feature with no backend or frontend code changes, property-based testing does not apply. This feature involves only static Markdown files rendered by MkDocs Material — there are no pure functions, data transformations, or algorithms to verify. Content correctness is validated through build checks (`mkdocs build --strict`) and human review.

**Validates: Requirements 1.1, 2.1, 3.1, 4.1, 5.1, 6.1, 7.1, 8.1, 9.1, 10.1, 11.1**

## Testing Strategy

**PBT is not applicable** for this feature. This is a documentation-only change with no backend or frontend code. There are no pure functions, data transformations, or algorithms to test with property-based testing. Content correctness is verified through build checks and human review.

### Verification Approach

| Method                         | What it verifies                                                   |
| ------------------------------ | ------------------------------------------------------------------ |
| `mkdocs build --strict`        | All navigation entries resolve, no broken links, valid markdown    |
| `mkdocs serve` (local preview) | Visual rendering check for formatting, tables, admonitions         |
| Manual review — Dutch          | Content accuracy, terminology matches UI labels, complete coverage |
| Manual review — English        | Translation accuracy, consistent structure with Dutch version      |
| Search verification            | New sections appear in MkDocs search results for both languages    |
| Cross-link check               | Internal links between Landing Page sub-pages resolve correctly    |

### Acceptance Criteria Verification Checklist

**Media Assets (Requirements 1–5):**

- [ ] Storage Summary section explains metrics, category breakdown, orphaned counts
- [ ] All scan phases documented (S3 scan, registry compare, reference verify, transition)
- [ ] All result categories documented (Consistent, Unregistered, Missing, Stale References, Newly Eligible)
- [ ] Import procedure with step-by-step
- [ ] Delete procedure with permanence warning
- [ ] Duplicates detection explanation (content hash)
- [ ] Merge workflow with reference transfer
- [ ] Retention defaults table (Invoices 2555d, Branding 30d, Templates 90d, Landing Pages 7d)
- [ ] System defaults vs tenant overrides explained
- [ ] Deletion approval workflow documented
- [ ] Invoice compliance warning (7-year legal requirement)
- [ ] Both Dutch and English versions complete

**Landing Page (Requirements 6–9):**

- [ ] Theme presets page lists all 6 presets with characteristics
- [ ] Custom theme option documented
- [ ] Reset to defaults functionality documented
- [ ] Gradient presets listed (all 8)
- [ ] Free-form CSS gradient input documented
- [ ] Live preview strip documented
- [ ] Typography fonts listed (all 7) with heading/body distinction
- [ ] Spacing options documented (compact/normal/relaxed)
- [ ] Border-radius options documented (sharp/rounded/pill)
- [ ] Shadow options documented (none/subtle/medium/dramatic)
- [ ] Block background types documented (colour/image/gradient)
- [ ] Block padding options documented
- [ ] Block text colour options documented (dark/light/auto)
- [ ] Block max-width options documented (contained/full-width)
- [ ] Block border-radius options documented (none/sm/md/lg)
- [ ] Both Dutch and English versions for all new pages

**Structure & Quality (Requirements 10–11):**

- [ ] `mkdocs.yml` nav updated with Landing Page sub-pages
- [ ] All pages searchable in both languages
- [ ] Relative MkDocs links used for cross-references
- [ ] Consistent admonitions (tip/warning/note)
- [ ] Tables for structured data
- [ ] Numbered lists for procedures, bullets for enumerations
- [ ] UI label terminology matches application exactly

### Build Verification Command

```bash
cd docs && mkdocs build --strict
```

This single command validates:

- All nav entries point to existing files
- No broken relative links
- Valid Markdown rendering
- i18n plugin processes all language variants
