# Implementation Plan

## Overview

Exploration-test-first bugfix for `ApplicationFormBuilder.load()` seeding its working overlay from
the retired `cfg.field_overlay` (undefined on the current SAM read) instead of reconstructing it
from the resolved `fields[]` via `flatViewToOverlay(cfg)`. One fix, mirroring `MembersConfigEditor`,
with a checkpoint running the builder + overlay frontend suites.

## Task Dependency Graph

```json
{
  "waves": [
    {
      "wave": 1,
      "tasks": ["1", "2"],
      "description": "Write and run the exploration test (FAILS on unfixed code) and the preservation tests (PASS on unfixed code), before any fix."
    },
    {
      "wave": 2,
      "tasks": ["3.1"],
      "description": "Apply the fix: seed working overlay + baseline via flatViewToOverlay(cfg) and correct the stale comment."
    },
    {
      "wave": 3,
      "tasks": ["3.2", "3.3"],
      "description": "Re-run the SAME tests from waves 1: exploration now PASSES, preservation still PASSES."
    },
    {
      "wave": 4,
      "tasks": ["4"],
      "description": "Checkpoint: run the builder + overlay frontend suites."
    }
  ]
}
```

## Tasks

- [x] 1. Write bug condition exploration test
  - **Property 1: Bug Condition** - Resolved application attributes seed the builder panels
  - **CRITICAL**: This test MUST FAIL on unfixed code - failure confirms the bug exists
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: This test encodes the expected behavior - it will validate the fix when it passes after implementation
  - **GOAL**: Surface a counterexample that demonstrates the builder shows per-field application attributes at defaults even though they are stored/served
  - **Scoped PBT Approach**: Scope the property to the concrete failing case - a resolved config with NO `field_overlay` key and a tenant-added `iban` field in `fields[]` (`origin:'variable'`, `application_visible:true`, `application_required:true`, `format:{checker:'IBAN'}`, `functional_group:'financial'`) plus a `payment_method` field with `application_required:true`
  - Reuse the existing builder harness/mocks (grep `ApplicationFormBuilder.test.tsx`, `renderWithLiveOverlay`, the Phase-3 matrix fixtures); mock `getMembersFieldConfig` to return the REALISTIC resolved config described above (resolved-config shape the real GET returns, NOT a hand-built `field_overlay`)
  - Render `ApplicationFormBuilder`, select the IBAN field, and assert the required toggle is CHECKED and the format select value is `IBAN`; assert `payment_method` required is CHECKED (assertions match Property 1 / Expected Behavior in design)
  - Run test on UNFIXED code under vitest (steering `33-frontend-testing`)
  - **EXPECTED OUTCOME**: Test FAILS - toggles unchecked / format empty (this is correct; it proves the bug exists)
  - Document the counterexample found (seeded overlay is `{}` because `cfg.field_overlay` is undefined, so panels fall back to defaults)
  - Mark task complete when test is written, run, and failure is documented
  - _Requirements: 1.1, 1.2_

- [x] 2. Write preservation tests (BEFORE implementing fix)
  - **Property 2: Preservation** - Unauthored configs, one-save contract, and form-shell seeding
  - **IMPORTANT**: Follow observation-first methodology
  - Observe behavior on UNFIXED code for non-bug configs: a config with no authored application attrs seeds panels at platform defaults; a fresh unedited load is NOT dirty (Save disabled / empty diff); editing one field yields exactly one `set_field_application` op; form-shell (slug/embed/consent) seeds from `config#mail` + `cfg.slug`
  - Write tests (matrix/property-based preferred) capturing those observed patterns from the Preservation Requirements in design
  - Run tests on UNFIXED code under vitest
  - **EXPECTED OUTCOME**: Tests PASS (this confirms baseline behavior to preserve)
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 3.1, 3.2, 3.3_

- [x] 3. Fix for Application Form Builder overlay seeding

  - [x] 3.1 Seed the working overlay + baseline via flatViewToOverlay and fix the stale comment
    - In `ApplicationFormBuilder.tsx` `load()`, replace `const overlayValue = (cfg?.field_overlay as MembersConfigValue) ?? {}` with `const overlayValue = flatViewToOverlay(cfg)` (keep `setOverlay(overlayValue)` and `setBaseline(JSON.stringify(overlayValue))` so working + baseline come from the SAME reconstruction)
    - Add `import { flatViewToOverlay } from './flatViewToOverlay';` (reuse the existing module; do NOT duplicate it) - mirror `MembersConfigEditor`
    - Rewrite the stale comment block that claims the reader serves `field_overlay` in authoring wire shape: the SAM read resolves the overlay into `fields[]`/`functional_groups` and no longer surfaces raw `field_overlay` (steering 39), so the builder reconstructs the authoring overlay via `flatViewToOverlay`
    - _Bug_Condition: isBugCondition(cfg) where cfg.field_overlay is undefined and fields[] carry authored application attrs (design)_
    - _Expected_Behavior: Property 1 - seed via flatViewToOverlay(cfg) so panels reflect stored attrs (design)_
    - _Preservation: Preservation Requirements - unauthored defaults, one-save contract, form-shell seeding (design)_
    - _Requirements: 2.1, 2.2, 3.1, 3.2, 3.3_

  - [x] 3.2 Verify bug condition exploration test now passes
    - **Property 1: Expected Behavior** - Resolved application attributes seed the builder panels
    - **IMPORTANT**: Re-run the SAME test from task 1 - do NOT write a new test
    - Run the bug condition exploration test from task 1
    - **EXPECTED OUTCOME**: Test PASSES (IBAN required CHECKED, format = `IBAN`, payment_method required CHECKED - confirms bug is fixed)
    - _Requirements: 2.1, 2.2_

  - [x] 3.3 Verify preservation tests still pass
    - **Property 2: Preservation** - Unauthored configs, one-save contract, and form-shell seeding
    - **IMPORTANT**: Re-run the SAME tests from task 2 - do NOT write new tests
    - Run the preservation tests from task 2
    - **EXPECTED OUTCOME**: Tests PASS (no regressions - unauthored defaults, fresh load not dirty, one edit → one op, form-shell seeding unchanged)
    - _Requirements: 3.1, 3.2, 3.3_

- [x] 4. Checkpoint - Ensure all tests pass
  - Run the builder + overlay frontend suites: `cd frontend && npx vitest run src/components/TenantAdmin/MembersConfig`
  - Ensure all tests pass, ask the user if questions arise
  - Reminder: this is FRONTEND-only and ships via the frontend deploy (main → GitHub Pages); the user's TEST admin SPA is the local dev server, so after the fix the user must reload the dev server (no SAM deploy involved)

## Notes

- FRONTEND-only: no SAM/backend/Lambda change. The module read already serves the attributes; only
  the builder's load-seeding is fixed.
- Write the exploration test (task 1) BEFORE the fix and run it on UNFIXED code - it MUST FAIL to
  confirm the bug. Run the preservation tests (task 2) on UNFIXED code - they MUST PASS.
- Reuse the existing `ApplicationFormBuilder.test.tsx` harness/mocks and the `flatViewToOverlay`
  module; do not duplicate the reconstruction.
- Deploy/reload: after the fix lands, reload the local Vite dev server (`VITE_APP_ENV=test`,
  `localhost:3000`) to pick up the new bundle. No `sam deploy`.
