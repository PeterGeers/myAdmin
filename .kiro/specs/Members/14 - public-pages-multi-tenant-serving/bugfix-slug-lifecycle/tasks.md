# Implementation Plan

## Overview

Exploratory bugfix flow for the broken SAM slug lifecycle (author -> display -> publish). The
exploration test (task 1) and preservation tests (task 2) are written and run on the UNFIXED code
BEFORE the fix; the fix (task 3) adds the SAM slug-author Change-Op + route, fixes the frontend
display/readiness to read SAM state, and re-runs both test sets; task 4 is the all-tests
checkpoint.

## Task Dependency Graph

```json
{
  "waves": [
    {
      "wave": 1,
      "tasks": ["1", "2"],
      "description": "Exploration test (fails on unfixed code) and preservation tests (pass on unfixed code), both independent and written first."
    },
    {
      "wave": 2,
      "tasks": ["3.1"],
      "description": "Backend SAM slug-author Change-Op + route + dispatch. Depends on 1 and 2."
    },
    {
      "wave": 3,
      "tasks": ["3.2", "3.3"],
      "description": "Rename/change support and frontend display/readiness + author control. Both depend on 3.1."
    },
    {
      "wave": 4,
      "tasks": ["3.4", "3.5"],
      "description": "Verify exploration test passes (depends on 3.1, 3.3) and preservation tests still pass (depends on 3.1, 3.2, 3.3)."
    },
    {
      "wave": 5,
      "tasks": ["4"],
      "description": "Checkpoint: all backend + frontend tests pass. Depends on all of task 3."
    }
  ]
}
```

## Tasks

- [x] 1. Write bug condition exploration test
  - **Property 1: Bug Condition** - SAM slug lifecycle authors + displays + gates from SAM state
  - **CRITICAL**: This test MUST FAIL on unfixed code - failure confirms the bug exists
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: This test encodes the expected behavior - it will validate the fix when it passes after implementation
  - **GOAL**: Surface counterexamples that demonstrate the slug lifecycle is broken end to end
  - **Scoped PBT Approach**: scope the property to the concrete verified failing cases for `h-dcn`
    (SAM `config#fields.slug = NULL`) across the three facets (AUTHOR / DISPLAY / PUBLISH_REACHABILITY)
  - Backend (`python -m pytest -c sam/pytest.ini <paths> -q`):
    - AUTHOR facet: assert there is NO client-reachable SAM write that persists `config#fields.slug`
      AND claims `_slugs/{slug}` — the generic `PUT /members/config/{configId}` rejects
      `configId=fields`, and `ConfigFieldsCrudService` exposes no slug op (from Bug Condition in design)
    - PUBLISH_REACHABILITY facet: for a tenant with `config#fields.slug=None`, `ApplicationPublishService.publish`
      raises `PublishNotReady(NO_SLUG)` and no SAM path clears it
  - Frontend (vitest `--run`):
    - DISPLAY facet: render `ApplicationFormBuilder` with SAM `cfg.slug=null` + a non-null Flask
      `getSlug()` and assert the UNFIXED code shows the Flask slug / `slugPresent=true`
  - Run on UNFIXED code
  - **EXPECTED OUTCOME**: Test FAILS / asserts the buggy behavior (this is correct - it proves the bug exists)
  - Document counterexamples found (e.g. "h-dcn: no author op; publish stuck no_slug; builder shows hdcn-application-form.jabaki.nl while SAM slug is NULL")
  - Mark task complete when test is written, run, and failure is documented
  - _Requirements: 1.1, 1.2, 1.3, 1.4_

- [x] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** - already-slugged publish, Flask plane, non-slug writes unchanged
  - **IMPORTANT**: Follow observation-first methodology
  - Observe on UNFIXED code, then assert the SAME behavior is preserved:
    - A tenant with a valid stored `config#fields.slug` publishes/claims identically
      (`ApplicationPublishService` + `S3SlugMarkerStore.claim` + `get_form_slug`)
    - A non-slug `config#fields` Change-Op (`set_field_application`) and a `config#mail` write
      round-trip unchanged
    - A `config#fields` row's existing `published_at` / `published_version` is carried through a
      (hypothetical) slug change — observe the current carry-through contract
    - Any Flask landing-plane call (`/api/landing/slug`) is observed and must stay identical (the
      landing module is NOT modified)
  - Prove the backend round-trip against the REAL `config#fields` row (`h-dcn`), not a hand-built
    fixture (steering 39)
  - Write property-based tests capturing the observed behavior
  - Run tests on UNFIXED code
  - **EXPECTED OUTCOME**: Tests PASS (this confirms the baseline behavior to preserve)
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 3.1, 3.2, 3.3, 3.4_

- [x] 3. Fix for broken SAM slug lifecycle (author -> display -> publish)

  - [x] 3.1 Add the SAM slug-author Change-Op (backend domain + route + dispatch)
    - In `sam/members/domain/config_fields_crud_service.py`: add a `members:admin` slug-author op
      that REUSES `form_slug.validate_slug_format` (format/reserved) then
      `form_slug.validate_slug_prefix_ownership` (SEC-4 prefix, with `get_public_prefix`), claims
      `_slugs/{slug}` via injected `S3SlugMarkerStore.claim` (idempotent same-owner, clobber
      backstop), and emits a SINGLE identity Change-Op `SET slug` on `config#fields` via `apply_ops`
      (explicit `null` CLEARS it); carry `published_*` through, never author them
    - Inject the marker store + prefix reader (no boto3 in the domain; steering 35/39)
    - In `sam/members/handler/routes.py`: add the `members:admin`-gated author/change route;
      `tenant_id` from the verified token, never the body
    - In `sam/members/handler/_dispatch_services.py`: wire the route to the op (lazy, warm-reused,
      fakes in tests); map validation to 422/400 and foreign-owner `SlugTaken` to a caller-safe 409
      (steering 30/37; never `str(e)`)
    - Confirm at review whether `config_write_service._author_form_slug` is retired or kept as the
      internal persistence primitive the new op calls
    - _Bug_Condition: isBugCondition(input) with facet=AUTHOR / PUBLISH_REACHABILITY from design_
    - _Expected_Behavior: Property 1 (validate -> claim -> persist via Change-Op; publish reachable) from design_
    - _Preservation: Preservation Requirements from design (non-slug writes + published_* unchanged)_
    - _Requirements: 2.3, 2.4, 3.3, 3.4_

  - [x] 3.2 Add rename/change support if low-cost via the marker-store rename
    - If `S3SlugMarkerStore.rename` (claim-new-before-release-old, R4.6) makes a change low-cost,
      the slug-author op handles a change by rename (claim new, persist new `config#fields.slug`,
      release old) in that safe order; otherwise keep the first increment to author+persist and
      record rename as a follow-up
    - _Bug_Condition: isBugCondition(input) with facet=AUTHOR (change) from design_
    - _Expected_Behavior: Property 1 from design_
    - _Requirements: 2.3, 2.4_

  - [x] 3.3 Fix the SAM admin display + readiness and add the author control (frontend)
    - In `frontend/src/components/TenantAdmin/MembersConfig/ApplicationFormBuilder.tsx`: remove the
      `getSlug`/`landingPageApi` import+call; source the slug from the SAM field-config response
      (`cfg.slug`/overlay) so `shell.slug` + `computeReadiness` reflect SAM state; show "no public
      address yet" when absent
    - Add a `members:admin` control to set/change the public address, calling the new SAM
      slug-author endpoint via a SAM API client (NOT `landingPageApi`), then re-load so the
      display/readiness reflect the persisted SAM slug
    - Add `setApplicationFormSlug(slug)` to the SAM members config API client
    - _Bug_Condition: isBugCondition(input) with facet=DISPLAY from design_
    - _Expected_Behavior: Property 1 (address + readiness from config#fields.slug; "not set" when absent) from design_
    - _Preservation: Preservation Requirements from design (Flask landing plane untouched)_
    - _Requirements: 2.1, 2.2, 3.2_

  - [x] 3.4 Verify bug condition exploration test now passes
    - **Property 1: Expected Behavior** - SAM slug lifecycle authors + displays + gates from SAM state
    - **IMPORTANT**: Re-run the SAME test from task 1 - do NOT write a new test
    - The test from task 1 encodes the expected behavior
    - When this test passes, it confirms the expected behavior is satisfied
    - Run bug condition exploration test from step 1 (backend `pytest -c sam/pytest.ini`, frontend vitest `--run`)
    - **EXPECTED OUTCOME**: Test PASSES (confirms the slug can be authored, display reads SAM state, publish reachable)
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

  - [x] 3.5 Verify preservation tests still pass
    - **Property 2: Preservation** - already-slugged publish, Flask plane, non-slug writes unchanged
    - **IMPORTANT**: Re-run the SAME tests from task 2 - do NOT write new tests
    - Run preservation property tests from step 2 (incl. the real `h-dcn` `config#fields` round-trip)
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions)
    - Confirm all tests still pass after fix (no regressions)

- [x] 4. Checkpoint - Ensure all tests pass
  - Run the paired SAM pytest suites for changed backend files and the frontend builder/readiness
    tests; ensure all pass. Ask the user if questions arise.

## Notes

- Write the exploration test (task 1) BEFORE implementing the fix, and run it on the UNFIXED code
  to confirm it fails (proving the bug exists). Do not fix the test or code when it fails at task 1.
- Prove the backend round-trip against the REAL `config#fields` row (`h-dcn`), not a hand-built
  fixture (steering 39). "Tests pass" alone is not sufficient evidence.
- The Flask landing module (`/api/landing/slug`, `landing_page_service.py`, `tenant_slugs`) MUST
  NOT be modified (spec 14 Scope decision). Any observable change there is a regression.
- No boto3 outside the repository layer; the slug op's marker store + prefix reader are injected
  (steering 35/39). The slug write is an identity Change-Op, never a whole-record replace.
- Backend tests: `python -m pytest -c sam/pytest.ini <paths> -q`. Frontend tests: vitest `--run`
  (single execution, not watch mode).
