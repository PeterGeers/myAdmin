# Requirements Document

## Introduction

This feature adds missing user documentation for two recently implemented features in myAdmin: **Media Asset Management** (completing/verifying existing docs) and **Landing Page Look & Feel** (new sections covering theming, gradients, typography, and block-level visual settings). Documentation is authored in MkDocs Material with Dutch as primary language and English as secondary language.

## Glossary

- **Documentation_System**: The MkDocs-based documentation site that serves user-facing manuals at `docs/docs/`
- **Media_Assets_Manual**: The existing user documentation at `docs/docs/tenant-admin/media-assets.md` (Dutch) and `media-assets.en.md` (English) covering the Media Asset Management feature
- **Landing_Page_Manual**: The existing user documentation at `docs/docs/landing-page/index.md` (Dutch) and `index.en.md` (English) covering the Landing Page feature
- **Storage_Summary_Tab**: The "Opslag" tab in Media Assets showing storage usage per category and orphaned asset counts
- **Scan_Tab**: The "Scan" tab in Media Assets that runs reconciliation scans between S3 and the asset registry
- **Unregistered_Tab**: The "Niet-geregistreerd" tab in Media Assets listing S3 objects not in the registry
- **Duplicates_Tab**: The "Duplicaten" tab in Media Assets showing groups of files with identical hashes for merging
- **Retention_Tab**: The "Bewaartermijn" tab in Media Assets for configuring retention periods per asset category
- **Deletion_Tab**: The "Verwijdering" tab in Media Assets where orphaned, retention-expired assets are approved for deletion
- **Theme_Selector**: The component allowing users to choose from predefined theme presets (Professional, Warm, Modern, Nature, Minimal, Luxury) or a Custom theme
- **Gradient_Picker**: The component providing preset gradient buttons (Sunset, Ocean, Forest, Peach, Night, Warm, Sky, Gold) and a free-form CSS gradient input
- **Typography_Settings**: The component managing font selection (heading/body), spacing, border-radius, and shadow style for the published landing page
- **Block_Settings**: Per-block visual settings including background type (color, image, gradient), padding, text colour, max-width, and border-radius
- **Tenant_Admin**: A user with the `Tenant_Admin` role who manages tenant-level configuration

## Requirements

### Requirement 1: Verify and Complete Media Assets Manual — Storage Summary Tab

**User Story:** As a Tenant_Admin, I want the Storage_Summary_Tab documented in the Media_Assets_Manual, so that I can understand how to interpret storage metrics and category breakdowns.

#### Acceptance Criteria

1. THE Media_Assets_Manual SHALL contain a dedicated section for the Storage_Summary_Tab explaining storage-per-category metrics and orphaned asset counts
2. WHEN a user navigates to the Storage Summary documentation section, THE Media_Assets_Manual SHALL describe how to read the dashboard including total storage used, storage per category, and number of orphaned assets
3. THE Documentation_System SHALL render the Storage Summary section in both Dutch and English versions of the Media_Assets_Manual

### Requirement 2: Verify and Complete Media Assets Manual — Scan and Unregistered Tabs

**User Story:** As a Tenant_Admin, I want the Scan_Tab and Unregistered_Tab procedures fully documented, so that I can follow step-by-step instructions for running scans and handling unregistered objects.

#### Acceptance Criteria

1. THE Media_Assets_Manual SHALL contain step-by-step instructions for running a reconciliation scan, including all scan phases (S3 bucket scanning, registry comparison, reference verification, eligible asset transition)
2. THE Media_Assets_Manual SHALL document all scan result categories (Consistent, Unregistered, Missing, Stale References, Newly Eligible) with clear descriptions
3. THE Media_Assets_Manual SHALL contain step-by-step instructions for importing unregistered S3 objects into the asset registry
4. THE Media_Assets_Manual SHALL contain step-by-step instructions for deleting unregistered S3 objects with a warning about permanence
5. THE Documentation_System SHALL render the Scan and Unregistered sections in both Dutch and English versions

### Requirement 3: Verify and Complete Media Assets Manual — Duplicates Detection

**User Story:** As a Tenant_Admin, I want the Duplicates_Tab documented in the Media_Assets_Manual, so that I can understand how to detect and merge duplicate files.

#### Acceptance Criteria

1. THE Media_Assets_Manual SHALL contain a section explaining how duplicates are detected (identical content hash)
2. THE Media_Assets_Manual SHALL contain step-by-step instructions for selecting which file to keep in each duplicate group and merging
3. THE Media_Assets_Manual SHALL document that references are transferred from deleted duplicates to the retained file
4. THE Documentation_System SHALL render the Duplicates section in both Dutch and English versions

### Requirement 4: Verify and Complete Media Assets Manual — Retention Policies

**User Story:** As a Tenant_Admin, I want the Retention_Tab documented in the Media_Assets_Manual, so that I can understand how to configure and interpret retention periods per asset category.

#### Acceptance Criteria

1. THE Media_Assets_Manual SHALL contain a section explaining retention policy configuration including the distinction between system defaults and tenant overrides
2. THE Media_Assets_Manual SHALL list all default retention periods (Invoices: 2555 days/7 years, Branding: 30 days, Templates: 90 days, Landing Pages: 7 days) with explanatory notes
3. THE Media_Assets_Manual SHALL contain step-by-step instructions for adjusting retention values and saving changes
4. THE Documentation_System SHALL render the Retention section in both Dutch and English versions

### Requirement 5: Verify and Complete Media Assets Manual — Deletion Management

**User Story:** As a Tenant_Admin, I want the Deletion_Tab documented in the Media_Assets_Manual, so that I can understand how to approve deletion of orphaned, retention-expired assets safely.

#### Acceptance Criteria

1. THE Media_Assets_Manual SHALL contain a section explaining the deletion approval workflow (orphaned assets past retention period require explicit admin approval)
2. THE Media_Assets_Manual SHALL document the compliance warning for invoice-related assets and the 7-year legal retention requirement
3. THE Media_Assets_Manual SHALL contain step-by-step instructions for selecting and approving assets for permanent deletion
4. THE Documentation_System SHALL render the Deletion section in both Dutch and English versions

### Requirement 6: Add Landing Page Manual — Theme Presets and Selection

**User Story:** As a Tenant_Admin, I want the Theme_Selector documented in the Landing_Page_Manual, so that I can understand how to choose a theme preset or use a custom theme for my landing page.

#### Acceptance Criteria

1. THE Landing_Page_Manual SHALL contain a new section documenting theme selection, listing all available presets (Professional, Warm, Modern, Nature, Minimal, Luxury) with their colour and font characteristics
2. THE Landing_Page_Manual SHALL document the Custom theme option that allows full manual control over colours and fonts
3. THE Landing_Page_Manual SHALL document the "Reset to theme defaults" functionality that restores preset values when a named theme is selected
4. THE Documentation_System SHALL render the Theme section in both Dutch and English versions

### Requirement 7: Add Landing Page Manual — Gradient Backgrounds

**User Story:** As a Tenant_Admin, I want gradient background options documented in the Landing_Page_Manual, so that I can understand how to apply gradient backgrounds to blocks.

#### Acceptance Criteria

1. THE Landing_Page_Manual SHALL contain a section documenting gradient backgrounds, listing available presets (Sunset, Ocean, Forest, Peach, Night, Warm, Sky, Gold)
2. THE Landing_Page_Manual SHALL document the free-form CSS gradient input for custom gradients
3. THE Landing_Page_Manual SHALL document the live preview strip that shows the selected gradient
4. THE Documentation_System SHALL render the Gradient section in both Dutch and English versions

### Requirement 8: Add Landing Page Manual — Typography Settings

**User Story:** As a Tenant_Admin, I want the Typography_Settings documented in the Landing_Page_Manual, so that I can understand how to configure fonts, spacing, border-radius, and shadow styles for my landing page.

#### Acceptance Criteria

1. THE Landing_Page_Manual SHALL contain a section documenting font selection for headings and body text, listing available fonts (System Default, Inter, Lora, Poppins, Nunito, Playfair Display, Lato) with live preview
2. THE Landing_Page_Manual SHALL document base spacing options (compact, normal, relaxed)
3. THE Landing_Page_Manual SHALL document global border-radius options (sharp, rounded, pill) with visual descriptions
4. THE Landing_Page_Manual SHALL document shadow style options (none, subtle, medium, dramatic) with visual descriptions
5. THE Documentation_System SHALL render the Typography section in both Dutch and English versions

### Requirement 9: Add Landing Page Manual — Block Settings

**User Story:** As a Tenant_Admin, I want per-block visual settings documented in the Landing_Page_Manual, so that I can understand how to customise individual block appearance (background, padding, text colour, width, borders).

#### Acceptance Criteria

1. THE Landing_Page_Manual SHALL contain a section documenting per-block background types: solid colour (with colour picker), background image (with upload), and gradient (with Gradient_Picker)
2. THE Landing_Page_Manual SHALL document padding options (compact, normal, spacious) for individual blocks
3. THE Landing_Page_Manual SHALL document text colour options (dark, light, auto) for individual blocks
4. THE Landing_Page_Manual SHALL document max-width options (contained, full-width) for individual blocks
5. THE Landing_Page_Manual SHALL document border-radius options (none, sm, md, lg) for individual blocks
6. THE Documentation_System SHALL render the Block Settings section in both Dutch and English versions

### Requirement 10: Documentation Structure and Navigation

**User Story:** As a Tenant_Admin, I want the new documentation sections properly integrated into the MkDocs navigation, so that I can find them through the site's table of contents and search.

#### Acceptance Criteria

1. WHEN new documentation pages are added, THE Documentation_System SHALL include the pages in the `mkdocs.yml` navigation structure under the appropriate section
2. THE Documentation_System SHALL ensure all new sections are searchable via the built-in search plugin in both Dutch and English
3. IF a documentation section references another section, THEN THE Documentation_System SHALL use relative MkDocs links that resolve correctly in the published site

### Requirement 11: Documentation Content Quality

**User Story:** As a Tenant_Admin, I want documentation written clearly with consistent formatting, so that I can quickly find and follow instructions.

#### Acceptance Criteria

1. THE Documentation_System SHALL use consistent MkDocs Material admonitions (tip, warning, note) for callouts in all new and updated sections
2. THE Documentation_System SHALL use tables for structured data (settings lists, option comparisons, troubleshooting) in all new and updated sections
3. THE Documentation_System SHALL use numbered lists for step-by-step procedures and bullet lists for feature enumerations
4. THE Documentation_System SHALL maintain terminology consistency between the UI labels and the documentation text (using exact button names and tab names as shown in the application)
