# Implementation Plan: SAM Page Look-and-Feel

## Overview

This plan implements the `Look_And_Feel_Capability` on the SAM plane following the design's
three-layer model and the three confirmed decisions (DD-1, DD-2, DD-3). Work proceeds bottom-up
through the layers so each step builds on the previous and ends with everything wired:

1. **Layer 2 first** — relocate/extract the SAM-owned CSS generator (`sam/shared/page_styles/`,
   `render_page_styles` → `PageStyles`) and remove the Flask-plane build-time vendoring (DD-1).
2. **Layer 1** — the stored `look_and_feel` slice on `config#fields`, its reader/writer seams, and
   the `LookAndFeelSettingsService` (get/set/copy) (DD-2).
3. **Layer 3 wiring** — close the Req 5 defect by resolving stored values → Layer 2 →
   `branding=` into `render_application_form_page` inside `ApplicationPublishService.publish`.
4. **Edge** — `members:admin`-gated authoring routes (get/set/copy) with verified `tenant_id`.
5. **Composition root** — wire real reader/writer; fakes in tests.
6. **Frontend** — Layer-1 authoring UI + the preview Layer-2/3 React mirror pinned by a parity
   fixture (DD-3).
7. **Real-data round-trip, all-planes delivery, CI/CD, and governance definition-of-done.**

Language: implementation is Python (SAM domain/repository/handler, `sam/shared/`) and
TypeScript/React (frontend) — the languages the design and the touched seams already use. No
pseudocode in the design, so no language choice is required.

Property-based tests use **Hypothesis** (≥100 iterations), one per correctness Property 1–11, each
tagged exactly `Feature: sam-page-look-and-feel, Property {number}: {property_text}`. Per the
change-with-tests contract (steering 30/34/39), every product-code task updates its paired tests in
the SAME task.

## Tasks

- [x] 1. Layer 2 — relocate the SAM-owned CSS generator and remove Flask-plane vendoring (DD-1)
  - [x] 1.1 Create `sam/shared/page_styles/` with `render_page_styles(settings) -> PageStyles`
    - Relocate/extract the `LandingPageStyles` CSS logic (`build_css_variables` / `build_page_css`
      / `build_font_links`) into the SAM-owned home as the new source of truth
    - Expose exactly one reusable function (C1); `PageStyles` carries the `:root` variables block,
      the page CSS, and the font `<link>` tags
    - Support exactly the seven attributes (`color_primary`, `color_accent`, `font_heading`,
      `font_body`, `base_spacing`, `border_radius_global`, `shadow_style`); absent attribute →
      SAM-owned default; unsupported attribute → raise an `UnsupportedAttributeError` and produce
      no styling; page-type-agnostic (no Application_Form-specific state)
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 3.1, 3.2, 3.3, 3.4, 3.5, 6.1, 6.2, 6.3_

  - [x] 1.2 Property test — Layer-2 determinism in the settings
    - **Property 1: Layer-2 output is deterministic in the settings**
    - Tag: `Feature: sam-page-look-and-feel, Property 1: For any valid Look_And_Feel_Settings values mapping, invoking render_page_styles twice with that same mapping SHALL produce identical styling output.`
    - Hypothesis ≥100 iterations over generated settings mappings
    - _Requirements: 1.2, 1.5_ _Properties: 1_

  - [x] 1.3 Property test — Layer-2 output depends only on the supplied values (page-type-agnostic)
    - **Property 2: Layer-2 output depends only on the supplied values**
    - Tag: `Feature: sam-page-look-and-feel, Property 2: For any two Pages supplied identical Look_And_Feel_Settings values, render_page_styles SHALL produce identical styling output regardless of Page type or any other Page state.`
    - _Requirements: 1.5, 4.3, 6.1, 6.2, 6.3_ _Properties: 2_

  - [x] 1.4 Property test — different values produce correspondingly different styling
    - **Property 3: Different values produce correspondingly different styling**
    - Tag: `Feature: sam-page-look-and-feel, Property 3: For any two values mappings differing in at least one supported attribute's value, render_page_styles SHALL produce styling that differs in at least the corresponding styling attribute.`
    - _Requirements: 4.2, 5.3_ _Properties: 3_

  - [x] 1.5 Property test — absent attributes fall back to defaults without failing
    - **Property 4: Absent attributes fall back to defaults without failing**
    - Tag: `Feature: sam-page-look-and-feel, Property 4: For any values mapping with any subset of the supported attributes omitted, render_page_styles SHALL produce styling using the SAM-owned default for each omitted attribute and SHALL NOT fail.`
    - _Requirements: 1.3, 3.3, 4.4, 5.4_ _Properties: 4_

  - [x] 1.6 Property test — unsupported attribute is rejected and produces no styling
    - **Property 5: Unsupported attribute is rejected and produces no styling**
    - Tag: `Feature: sam-page-look-and-feel, Property 5: For any values mapping containing a key that is not one of the seven supported attributes, render_page_styles SHALL reject the request, signal the unsupported attribute, and produce no Page styling.`
    - _Requirements: 3.4_ _Properties: 5_

- [x] 2. Layer 2 packaging — remove the Flask-plane vendored copy from the layer build (DD-1)
  - Remove the `cp .../landing_page_styles.py` line from `sam/members/layer/Makefile`
  - Package the SAM-owned `sam/shared/page_styles/` the same least-surface way the layer already
    packages `sam/shared/`
  - Update/add the layer-packaging test or build assertion that the layer no longer contains the
    Flask module and does contain `sam/shared/page_styles/`
  - _Requirements: 3.1_

- [x] 3. Checkpoint — Layer 2 complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Layer 1 — stored `look_and_feel` slice, reader and writer seams (DD-2)
  - [x] 4.1 Add the `look_and_feel` slice to the `config#fields` skeleton and new-tenant seeding
    - Seed the `look_and_feel` parent map in the `config#fields` skeleton so the Change-Op path can
      `SET` into it; `config#fields` is already in the closed `_WRITABLE_CONFIG_IDS` (no guard
      widening); store attribute VALUES only, never CSS; distinct from `fields` / `overrides`
    - _Requirements: 2.3, 8.2, 8.3_

  - [x] 4.2 Add a resolved-view reader on `MembersProjectionReader` for the `look_and_feel` slice
    - Tenant-scoped read of the stored values; absent slice/key → empty mapping (defaults); never
      merges a Flask `landing_page` projection
    - _Requirements: 2.1, 2.4, 8.4_

  - [x] 4.3 Property test — styling is produced entirely from SAM-owned code (no Flask runtime call)
    - **Property 7: Styling is produced entirely from SAM-owned code**
    - Tag: `Feature: sam-page-look-and-feel, Property 7: For any styling production, no attribute value SHALL originate from the Flask plane and no runtime read of or call to the Flask plane SHALL occur.`
    - _Requirements: 2.1, 2.2, 3.1, 3.5, 8.4_ _Properties: 7_

  - [x] 4.4 Property test — tenant isolation on resolve
    - **Property 8: Tenant isolation on resolve**
    - Tag: `Feature: sam-page-look-and-feel, Property 8: For any resolve of Look_And_Feel_Settings for a verified tenant, the resolved values SHALL be scoped to that tenant and SHALL exclude any other tenant's settings.`
    - _Requirements: 2.4_ _Properties: 8_

  - [x] 4.5 Add the Change-Op writer adapter over `MembersConfigWriteRepository.apply_ops`
    - `SET look_and_feel.#attr = :v` / `REMOVE look_and_feel.#attr` / `SET look_and_feel = :snapshot`
      as single path-scoped, version-conditional `update_item` ops (no whole-record `put_item`);
      `StaleVersionError` surfaces unchanged; `TruncationTripwireError` backstop applies
    - _Requirements: 8.1, 8.3_

  - [x] 4.6 Unit test — unrelated slices survive the Change-Op write by construction
    - Assert a `look_and_feel` SET leaves `fields` / `overrides` / slug / publish-state untouched and
      bumps the version; stale version → caller-safe 409 path
    - _Requirements: 4.1, 8.3_

- [x] 5. Layer 1 — `LookAndFeelSettingsService` (get / set / copy) (C3)
  - [x] 5.1 Implement `LookAndFeelSettingsService` with injected reader + writer
    - New `sam/members/domain/look_and_feel_settings_service.py` following the
      `ConfigFieldsCrudService` pattern (no boto3 in the domain)
    - `get_settings(tenant_id, page_id)` resolved-view read, absent → defaults;
      `set_setting(tenant_id, page_id, attribute, value)` validates attribute (Req 3.4) and value
      (Req 4.5), rejects invalid leaving stored values unchanged, issues one scoped Change-Op;
      `page_id` is a forward-looking seam resolving today to the application form's `config#fields`
      slice (no generic Page entity)
    - _Requirements: 2.3, 3.4, 4.1, 4.5, 8.1, 8.3_

  - [x] 5.2 Property test — invalid value is rejected and stored values are preserved
    - **Property 6: Invalid value is rejected and stored values are preserved**
    - Tag: `Feature: sam-page-look-and-feel, Property 6: For any supported attribute supplied a value outside its permitted set, the Layer-1 authoring operation SHALL reject the setting, leave the Page's previously stored Look_And_Feel_Settings values unchanged, and identify the rejected setting.`
    - Uses in-memory fake writer/reader
    - _Requirements: 4.5_ _Properties: 6_

  - [x] 5.3 Implement `copy_settings` (one-time snapshot, same tenant, no link)
    - Read source resolved view → single `SET look_and_feel = :snapshot` on target (overwrite);
      establish no live link; reject a cross-tenant source
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

  - [x] 5.4 Property test — copy is a one-time independent snapshot
    - **Property 9: Copy is a one-time independent snapshot**
    - Tag: `Feature: sam-page-look-and-feel, Property 9: For any source and target Page of the same tenant, after a Layer-1 copy the target's values SHALL equal the source's at copy time, and any subsequent change to either Page's values SHALL NOT alter the other's.`
    - _Requirements: 9.1, 9.2, 9.3, 9.5_ _Properties: 9_

  - [x] 5.5 Unit tests — copy overwrite + no-link; cross-tenant copy rejected
    - Same-tenant snapshot overwrites target and establishes no ongoing link; cross-tenant source
      rejected (caller-safe 403)
    - _Requirements: 9.2, 9.3, 9.4, 9.5_

- [x] 6. Checkpoint — Layer 1 complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Layer 3 wiring — close the Req 5 defect in `ApplicationPublishService.publish` (C4)
  - [x] 7.1 Add the `LookAndFeelSettingsReader` Protocol and optional injection
    - New `@runtime_checkable` Protocol `get_look_and_feel(tenant_id) -> Mapping` in
      `sam/members/domain/application_publish.py`; `ApplicationPublishService.__init__` gains an
      optional `look_and_feel_reader` param matching the existing optional-seam style
    - _Requirements: 5.1_

  - [x] 7.2 Resolve values → Layer 2 → `branding=` into the renderer in `publish()`
    - Resolve stored values for the verified tenant, run `render_page_styles` (Layer 2), pass
      `branding=resolved_styles` into `render_application_form_page` (Layer 3); when the reader is
      absent the renderer uses its existing fallback defaults (backward compatible)
    - If Layer 2 fails, do NOT write the artifact and return a failure indication; the previously
      published artifact is untouched (Req 5.5)
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

  - [x] 7.3 Example/regression test — publish passes branding (the Req 5 defect)
    - Assert `publish()` runs Layer 2 and calls the renderer WITH `branding=`; assert the baked
      `index.html` differs when a stored value changes; reader-absent tenant publishes with defaults
      and does not fail
    - Uses in-memory fakes for the artifact writer and settings reader
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

  - [x] 7.4 Property test — publish failure preserves the previously published artifact
    - **Property 10: Publish failure preserves the previously published artifact**
    - Tag: `Feature: sam-page-look-and-feel, Property 10: For any publish in which Layer 2 fails to produce styling, the Publish_Step SHALL NOT replace the previously published Application_Form and SHALL return a failure indication.`
    - In-memory fakes for the artifact writer and settings reader
    - _Requirements: 5.5_ _Properties: 10_

  - [x] 7.5 Property test — published form carries styling derived from resolved values
    - **Property 11: Published form carries styling derived from resolved values**
    - Tag: `Feature: sam-page-look-and-feel, Property 11: For any tenant with resolved Look_And_Feel_Settings values, a successful publish SHALL carry styling produced by Layer 2 from exactly those values (and from defaults where a tenant has none).`
    - In-memory fakes for the artifact writer and settings reader
    - _Requirements: 5.1, 5.2, 5.4_ _Properties: 11_

- [x] 8. Edge — `members:admin`-gated Layer-1 authoring routes (get / set / copy)
  - Add handler route(s) in the `_dispatch_services.py` accessor pattern for get / set / copy;
    `members:admin`-gated; resolve the verified `tenant_id` (never from the body)
  - Caller-safe error envelope (no `str(e)`): unsupported attribute 422, invalid value 422,
    cross-tenant copy 403, stale version 409, unverifiable tenant 401/403
  - _Requirements: 2.5, 3.4, 4.5, 8.1, 9.4_

  - [x] 8.1 Unit test — route auth, verified-tenant, and caller-safe error envelope
    - Assert `tenant_id` comes from the verified identity not the body; assert each error maps to its
      caller-safe status with no internals leaked
    - _Requirements: 2.5, 3.4, 4.5, 9.4_

- [x] 9. Composition root — wire real reader/writer (C6)
  - In `sam/members/handler/app.py` wire the real reader and writer into
    `LookAndFeelSettingsService` and inject the real `LookAndFeelSettingsReader` into
    `ApplicationPublishService`; tests continue to inject in-memory fakes (the `Static*Provider`
    pattern)
  - _Requirements: 5.1, 8.1_

- [x] 10. Checkpoint — SAM plane end-to-end
  - Ensure all tests pass, ask the user if questions arise.

- [x] 11. Real-data round-trip (steering 39, NON-NEGOTIABLE)
  - Author → resolve → generate → render against a REAL `config#fields` row (e.g. `h-dcn`): set a
    `look_and_feel` value via the Change-Op, resolve it back through the resolved view, confirm the
    published render reflects it, and confirm unrelated slices (`fields` / `overrides` / slug /
    publish-state) survive the write by construction
    - Run against the real row before marking this change done; "tests pass" alone is not sufficient
  - _Requirements: 4.1, 5.1, 5.2, 5.3, 8.3_

- [x] 12. Frontend — Layer-1 authoring UI (preferences editor)
  - Add the React admin UI that sends Change-Ops by domain identity (which page, which attribute,
    new value) — never a whole record, never generated CSS; wire get / set / copy to the authoring
    routes; surface the caller-safe error envelope
  - _Requirements: 2.3, 4.5, 8.1, 9.1, 9.3, 9.4_

  - [x] 12.1 Frontend unit tests — authoring UI sends values-only Change-Ops and handles errors
    - Assert the UI never sends generated CSS or whole records; assert copy and error surfaces
    - _Requirements: 8.1, 9.1, 9.4_

  - [x] 12.2 Build the look-and-feel editor component and wire it into the builder + preview
    - Add the React admin editor control (the seven-attribute preferences editor: color_primary,
      color_accent, font_heading, font_body, base_spacing, border_radius_global, shadow_style)
      inside the Application Form Builder (a panel/slot in `ApplicationFormBuilder.tsx`), consuming
      the existing authoring client (`getLookAndFeelSettings` / `setLookAndFeelSetting` /
      `copyLookAndFeelSettings` in `membersConfigApi.ts`, task 12.1) — values-only Change-Ops, never
      CSS, never a whole record
    - Feed the editor's current values into the `ApplicationFormPreview lookAndFeel` prop so an
      admin's stored + unsaved look-and-feel renders live in the preview (closes the gap where the
      builder rendered the preview with NO lookAndFeel prop); surface the caller-safe error envelope
      (422 identifying the rejected setting, 403 cross-tenant copy, 409 stale version)
    - Paired vitest tests: the editor renders the seven controls, an edit calls the client with the
      right values-only payload, the preview reflects the edit, and an edge error surfaces without
      leaking internals (change-with-tests, steering 33)
    - Closes the steering-40 all-planes gap: the admin-facing UI must reflect the change, not just
      the backend/data/preview (no half-shipped feature)
    - _Requirements: 2.3, 4.2, 4.5, 7.1, 7.2, 8.1, 9.1, 9.4_

- [x] 13. Frontend — admin preview Layer-2/3 React mirror + parity fixture (DD-3, C5)
  - [x] 13.1 Make `ApplicationFormPreview.tsx` mirror the Python Layer-2 output
    - Compute the same CSS-variable values the Python Layer-2 generator emits from the same values
      (plus the admin's unsaved edits) and inject them into the preview container (Layer-3 React
      render); keeps the instant, no-round-trip unsaved-edit preview; absent values → same defaults
      the published page uses
    - _Requirements: 7.1, 7.2, 7.3_

  - [x] 13.2 Shared parity fixture pinning React Layer-2/3 output to the Python output
    - Add a shared fixture (mirroring the existing `buildPreviewConfig` ↔ `get_public_field_config`
      pin) that asserts the React injected CSS-variable values match the Python `render_page_styles`
      output for the same values, so the two implementations cannot drift
    - _Requirements: 7.1, 7.3_

- [x] 14. Checkpoint — all planes delivered
  - Ensure all tests pass, ask the user if questions arise.

- [x] 15. CI/CD — quality gates, deploy paths, and production-release gate (steering 40/43)
  - Confirm the per-PR gates are green on the feature branch: CodeQL Advanced + GitGuardian; address
    root causes rather than suppressing
  - Confirm the changed paths trigger the right deploy workflows on the branch→env contract:
    `sam/members/**` + `sam/shared/**` → `deploy-sam-members` (TEST on `test`, PROD on `main`);
    `frontend/**` → `deploy-frontend` (PROD on `main`); note `config#fields` is already writable so
    the DynamoDB write needs NO new IAM — call out only if an authoring route needs anything else
  - Dispatch the nightly `full-test-suite.yml` (optionally a narrowed `scope:`) for blast-radius
    coverage; land TEST verification before the promote `test`→`main` production-release gate
  - _Requirements: 5.1, 5.2_

- [x] 16. Governance definition-of-done (steering 40 + design Governance section)
  - [x] 16.1 Rewrite steering 36 for SAM config-authoring autonomy
    - Rewrite steering 36 so SAM authoring/ownership of SAM-owned look-and-feel config supersedes the
      "MySQL is single source of truth / Flask authors / SAM reads a one-directional projection"
      model for this config, and record that the previous one-directional projection interface proved
      too weak to depend on
    - _Requirements: 8.1, 8.2, 8.4_

  - [x] 16.2 Review/update steering 35, 39 and ADRs 0005 / 0006 for consistency
    - Review steering 35 (SAM module architecture) and 39 (SAM data access) for any
      Flask-writes/SAM-reads phrasing for this config and update for consistency; review/annotate (or
      supersede) projection ADRs 0005 / 0006 to reflect that look-and-feel config is now SAM-authored
      and SAM-owned (Layer 1)
    - _Requirements: 8.2, 8.4_

## Notes

- Tasks marked with `*` are optional (tests) and can be skipped for a faster MVP; core
  implementation tasks are never optional.
- Property-based tests use Hypothesis (≥100 iterations), one per Property 1–11, each tagged exactly
  `Feature: sam-page-look-and-feel, Property {number}: {property_text}`. Properties 10/11 (and 6)
  use in-memory fakes for the publish/write edge.
- Every product-code task updates its paired tests in the SAME task (change-with-tests contract,
  steering 30/34/39).
- The real-data round-trip (task 11) is non-negotiable per steering 39 — run it against a real
  `config#fields` row, not just the unit suite.
- Governance tasks (16.1, 16.2) are part of done, not afterthoughts (steering 40).
- CI/CD coverage, the deploy-ordering invariant (the task-2 layer-packaging change and the task-7.2
  renderer cutover MUST deploy together — neither alone leaves a working publish path), and the
  production-release gate (promote `test`→`main`, steering 43) are documented in `RELEASE_NOTES.md`
  in this spec directory (task 15). No workflow change was needed — the existing `full-test-suite`
  globs and the `deploy-sam-members` path filters (`sam/members/**`, `sam/shared/**`) already cover
  the feature, and it introduces no new AWS resource/IAM.
- Planes touched: SAM domain (Layer-1 service + Layer-2 `sam/shared/page_styles/`), SAM repository
  (reader/writer slice + skeleton seed), SAM handler/edge (authoring routes + publish wiring), the
  layer Makefile packaging change, the React frontend (authoring UI + preview parity), and the
  stored-data shape (`look_and_feel` slice on `config#fields`).

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "1.3", "1.4", "1.5", "1.6", "2"] },
    { "id": 2, "tasks": ["4.1"] },
    { "id": 3, "tasks": ["4.2", "4.5"] },
    { "id": 4, "tasks": ["4.3", "4.4", "4.6", "5.1"] },
    { "id": 5, "tasks": ["5.2", "5.3"] },
    { "id": 6, "tasks": ["5.4", "5.5", "7.1"] },
    { "id": 7, "tasks": ["7.2"] },
    { "id": 8, "tasks": ["7.3", "7.4", "7.5", "8"] },
    { "id": 9, "tasks": ["8.1", "9"] },
    { "id": 10, "tasks": ["11", "12", "13.1"] },
    { "id": 11, "tasks": ["12.1", "13.2", "15"] },
    { "id": 12, "tasks": ["16.1", "16.2"] },
    { "id": 13, "tasks": ["12.2"] }
  ]
}
```
