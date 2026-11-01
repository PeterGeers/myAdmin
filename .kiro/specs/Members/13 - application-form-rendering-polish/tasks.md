# Tasks — 13. Public application-form rendering polish

Presentation-only. R1–R4 are pure frontend (no contract change); R5 adds one optional
backward-compatible field to the public field-config. Each task updates its paired test in the same
change (steering: change-with-tests). Verify with `vitest --run` on the affected files and keep the
axe gate green.

- [x] 1. Group ORDER from field sequence (R2)
  - [x] 1.1 In `applicationForm.model.ts::groupFieldsByFunctionalGroup`, order groups by
    `min(field.order)` per group (tiebreak: group key), keeping the `__default__` bucket pinned
    LAST. Keep the function pure; keep field ordering `(order, key)` unchanged.
  - [x] 1.2 Add/extend the unit test: groups appear in min-field-order order; stable tiebreak;
    `__default__` last; field order within a group unchanged. Confirm the authenticated Members
    form's existing tests (shared helpers) still pass.
  - _Requirements: R2.1, R2.2, R2.3_

- [x] 2. Readable group headings (R1)
  - [x] 2.1 In `ApplicationFormRenderer.tsx::groupHeading`, render a presentable heading from the
    `functional_group` key; for the `__default__` bucket render NO empty `<legend>` artifact (omit
    the legend, or use a neutral localized "Overig/Other" heading per design). Apply heading
    styling so sections read as sections.
  - [x] 2.2 Render test: every non-default group shows its heading; the default bucket shows no
    empty-legend; groups appear in the R2 order.
  - _Requirements: R1.1, R1.2, R1.3_

- [x] 3. De-emphasize dropdown styling (R3)
  - [x] 3.1 Style `<Select>` to match the text `<Input>` weight on the public form (shared style /
    scoped variant — applied uniformly, not per-field). Keep the chevron affordance and a visible
    focus ring; reserve the accent for focus. Scope to the public application form only.
  - [x] 3.2 Render test / visual check: select and input read at equal weight; focus ring visible;
    the rest of the app theme is untouched.
  - _Requirements: R3.1, R3.2, R3.3_

- [x] 4. Responsive one-line + multi-column layout (R4)
  - [x] 4.1 Label-beside-control on `md`+, stacked on `base`, via Chakra responsive props; preserve
    `htmlFor`/`id` association.
  - [x] 4.2 Replace the group `VStack` with a responsive `SimpleGrid columns={{ base: 1, md: 2 }}`
    (≥2 columns on desktop, 1 on mobile); allow a full-width span for an intrinsically-wide field.
  - [x] 4.3 Render test: single column at `base`, ≥2 columns at `md`; DOM/tab order matches the
    resolved sequence; error-summary anchors still focus the right control.
  - [x] 4.4 Re-run the axe accessibility gate against the new layout — must stay green.
  - _Requirements: R4.1, R4.2, R4.3, R4.4, HC2_

- [x] 5. Tenant logo at the top (R5) — ONE branding source, not landing-page-gated
  - [x] 5.1 Add a small PUBLIC, tenant-addressed branding-logo read that returns the tenant's logo
    from `branding.company_logo_s3_key`, reusing `services/logo_resolver.py` (point it at the
    `branding` namespace; return the inline data URI it already produces — no public-bucket/CDN
    dependency). Pair with a test: configured → logo, unconfigured → none.
  - [x] 5.2 In `ApplicationFormPage.tsx`, render `<Image src={logo} alt={tenantName ?? 'logo'}>`
    constrained + centered ABOVE the heading when a logo is returned; render nothing when absent
    (no broken image, R5.3). Works whether or not the tenant has a landing page.
  - [x] 5.3 Render test: logo shown when configured (with alt); graceful absence when not.
  - _Requirements: R5.1, R5.2, R5.3, R5.4_

- [x] 5b. (BACKLOG, out of this spec) Converge the fragmented logo configs
  (`branding.*`, `str_/zzp_branding.*`, `landing_page.logo_url`) to ONE tenant branding logo every
  feature resolves from. Captured as its own backlog item; R5 above already consumes the single
  `branding` source so it aligns when this lands.

- [ ] 6. Verify end-to-end against a real tenant
  - [x] 6.1 Run the affected frontend suites (`vitest --run`) green, including the axe gate.
  - [~] 6.2 Load the public form for a real tenant (h-dcn) in the running app; confirm all five:
    grouped + ordered sections, softened dropdowns, one-line/multi-column on desktop + stacked on
    mobile, logo at top. Capture before/after screenshots.
  - _Requirements: all; HC1–HC4_

## Sequencing note
All of tasks 1–5 are pure-frontend and independent — any order, or together. (R5 reuses the already-
published public `landing.json` branding, so there is NO backend/SAM change.) Task 6 is the final
verification once 1–5 are in.
