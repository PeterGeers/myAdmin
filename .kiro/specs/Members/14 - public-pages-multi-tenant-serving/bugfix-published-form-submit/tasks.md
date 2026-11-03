# Implementation Plan

## Overview

Exploratory bugfix flow for the PUBLISHED static application form that renders but cannot be
submitted. The exploration test (task 1) and preservation tests (task 2) are written and run on
the UNFIXED render BEFORE the fix; the fix (task 3) enriches the render step with a `preventDefault`ed
JSON submit to the backend, client-side `format` (IBAN/EMAIL) + `required` checks, consent + locale
controls, and a publish-time API base, then re-runs both test sets; task 4 is the all-tests
checkpoint.

## Task Dependency Graph

```json
{
  "waves": [
    {
      "wave": 1,
      "tasks": ["1", "2"],
      "description": "Exploration test (asserts the buggy no-JS artifact on unfixed render) and preservation tests (pass on unfixed render), both independent and written first."
    },
    {
      "wave": 2,
      "tasks": ["3.1"],
      "description": "Publish-time API base plumbing (fail-fast env, baked into the artifact). Depends on 1 and 2."
    },
    {
      "wave": 3,
      "tasks": ["3.2", "3.3"],
      "description": "Embedded submit script + format/required client checks, and consent + locale controls. Both depend on 3.1."
    },
    {
      "wave": 4,
      "tasks": ["3.4", "3.5"],
      "description": "Verify exploration test passes (depends on 3.1, 3.2, 3.3) and preservation tests still pass (depends on 3.1, 3.2, 3.3)."
    },
    {
      "wave": 5,
      "tasks": ["4"],
      "description": "Checkpoint: all render/publish + preservation tests pass. Depends on all of task 3."
    }
  ]
}
```

## Tasks

- [x] 1. Write bug condition exploration test
  - **Property 1: Bug Condition** - Published form submits to the backend and honors the field definition
  - **CRITICAL**: This test MUST FAIL on unfixed code - failure confirms the bug exists
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: This test encodes the expected behavior - it will validate the fix when it passes after implementation
  - **GOAL**: Surface counterexamples that demonstrate the published artifact is a dead end for applicants
  - **Scoped PBT Approach**: scope the property to a representative public field config — a
    `format`-constrained field (`format = {checker:"IBAN"}`), non-empty `locales`, and a
    `notice.version` — across the three facets (SUBMIT / FORMAT / CONSENT_LOCALE)
  - Backend (`python -m pytest -c sam/pytest.ini <paths> -q`), render the artifact via
    `render_application_form_page` / `build_form_body_html` over the config and assert the UNFIXED
    output:
    - SUBMIT facet: the artifact contains a bare `<form method="post">` with NO embedded submit
      `<script>`, NO `preventDefault`, and NO reference to `POST /public/members/{slug}/applications`
      (a submit would do a native POST and 404) — from Bug Condition in design
    - FORMAT facet: for the `IBAN` field, the artifact wires NO client-side IBAN check
    - CONSENT_LOCALE facet: the artifact renders NEITHER a consent control bound to `notice.version`
      NOR a locale selector from `locales`
  - Run on UNFIXED code
  - **EXPECTED OUTCOME**: Test FAILS / asserts the buggy behavior (this is correct - it proves the bug exists)
  - Document counterexamples found (e.g. "hdcn-aanmelden: static no-JS form, native POST to /apply 404s; IBAN field has no client check; no consent/locale controls")
  - Mark task complete when test is written, run, and failure is documented
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

- [x] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** - In-app form, backend, Flask plane, and existing render output unchanged
  - **IMPORTANT**: Follow observation-first methodology
  - Observe on UNFIXED code, then assert the SAME behavior is preserved:
    - For a config with `required` fields, email/number/date input types, grouped sections, labels,
      and branding, the rendered `required` attributes, input types, `<fieldset>` section ordering,
      labels (locale with `nl` fallback), HTML-escaping of config-origin values, and the
      `LandingPageStyles` CSS are observed and must stay identical after the fix
    - The backend public submit handler (`public_app.py` → `POST /public/members/{slug}/applications`)
      — slug-marker resolution, forged-`tenant_id` strip, CORS allow-list, honeypot, payload cap,
      422 / non-probeable 404 — round-trips unchanged (NOT modified by this fix)
    - The in-app SPA form (`ApplicationFormPage.tsx` + `submitApplication`) is not referenced or
      altered by the render change
    - Any Flask landing-plane call is observed and must stay identical (the landing module is NOT
      modified)
  - Prove the render round-trip against the REAL `get_public_field_config` shape (e.g. `h-dcn`),
    not a hand-built fixture (steering 39)
  - Write property-based tests capturing the observed behavior
  - Run tests on UNFIXED code
  - **EXPECTED OUTCOME**: Tests PASS (this confirms the baseline behavior to preserve)
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 3.1, 3.2, 3.3, 3.4_

- [x] 3. Fix for the published application form that cannot be submitted

  - [x] 3.1 Bake the public API base into the artifact at publish time (fail-fast, no silent default)
    - In `sam/members/domain/application_publish.py` (and the render entry point
      `render_application_form_page`): resolve the public API base URL from a publish-time
      environment variable with NO default (mirror the `GOVERNANCE_PROJECTION_TABLE` fail-fast
      model — a missing value raises at the first real call, never silently targets the wrong
      backend); pass the resolved base + the `slug` into `render_application_form_page` so the
      submit script's `fetch` target is correct per environment
    - No boto3 / no plane-crossing; the base is DATA resolved from env at publish time
    - _Bug_Condition: isBugCondition(input) with facet=SUBMIT from design_
    - _Expected_Behavior: Property 1 (baked-in API base; fetch target correct per env) from design_
    - _Preservation: Preservation Requirements from design (backend + Flask plane untouched)_
    - _Requirements: 2.6, 3.2, 3.3_

  - [x] 3.2 Render a working submit script + honor the `format` token (client checks)
    - In `sam/members/domain/application_form_render.py` `build_form_body_html`: stop emitting a
      bare `<form method="post">`; emit a form whose submit is handled by an embedded `<script>`
      that `preventDefault`s the native submit, serializes fields into the backend JSON shape
      (values under `fields`, plus `locale`/`lang`, `consent`, optional `session_key`, empty
      `website` honeypot), `fetch`es `POST {API_BASE}/public/members/{slug}/applications` with
      `Content-Type: application/json`, and handles the response (success state, inline per-field
      422 mapping, neutral message on 404 / neutral states; no internal detail leaked)
    - In `_render_field`: read the `field["format"]` token the config already emits
      (`{checker, params}`) and wire the matching client-side check — EMAIL (platform pattern) and
      IBAN (ISO 13616 mod-97), mirroring the `field_formats` registry semantics; keep the existing
      `required` rendering; the server 422 remains authoritative
    - Keep all config-origin values HTML-escaped; keep `get_public_field_config` as the only field
      source (steering 39)
    - _Bug_Condition: isBugCondition(input) with facet=SUBMIT / FORMAT from design_
    - _Expected_Behavior: Property 1 (preventDefault + JSON POST; client IBAN/EMAIL check) from design_
    - _Preservation: Preservation Requirements from design (required/input types/escaping unchanged)_
    - _Requirements: 2.1, 2.2, 2.3, 3.4_

  - [x] 3.3 Render the consent control + locale selector, styled with LandingPageStyles
    - In `build_form_body_html`: render a consent control (a checkbox bound to the config's
      `notice.version`) and a locale selector (options from the config's `locales`); the submit
      script reads them into `consent` and `locale`
    - Style the new elements (consent, inline errors, success state, format feedback) with the
      existing `form-field` / `form-group` classes and the shared `LandingPageStyles` CSS so they
      match the application form's look and feel — no new CSS source
    - _Bug_Condition: isBugCondition(input) with facet=CONSENT_LOCALE from design_
    - _Expected_Behavior: Property 1 (consent bound to notice.version + locale selector; shared styling) from design_
    - _Preservation: Preservation Requirements from design (single CSS source; single field authority)_
    - _Requirements: 2.4, 2.5, 3.4_

  - [x] 3.4 Verify bug condition exploration test now passes
    - **Property 1: Expected Behavior** - Published form submits to the backend and honors the field definition
    - **IMPORTANT**: Re-run the SAME test from task 1 - do NOT write a new test
    - The test from task 1 encodes the expected behavior
    - When this test passes, it confirms the expected behavior is satisfied
    - Run bug condition exploration test from step 1 (`python -m pytest -c sam/pytest.ini <paths> -q`)
    - **EXPECTED OUTCOME**: Test PASSES (confirms the artifact submits JSON to the backend, wires the IBAN/EMAIL check, and renders consent + locale)
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

  - [x] 3.5 Verify preservation tests still pass
    - **Property 2: Preservation** - In-app form, backend, Flask plane, and existing render output unchanged
    - **IMPORTANT**: Re-run the SAME tests from task 2 - do NOT write new tests
    - Run preservation property tests from step 2 (incl. the real `get_public_field_config` /
      `h-dcn` render round-trip)
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions)
    - Confirm all tests still pass after fix (no regressions)

- [x] 4. Checkpoint - Ensure all tests pass
  - Run the paired SAM pytest suites for the changed render/publish files; ensure all pass. Ask the
    user if questions arise.

## Notes

- Write the exploration test (task 1) BEFORE implementing the fix, and run it on the UNFIXED render
  to confirm it asserts the buggy behavior (proving the bug exists). Do not fix the test or code
  when it fails at task 1.
- Prove the render round-trip against the REAL `get_public_field_config` shape (`h-dcn`), not a
  hand-built fixture (steering 39). "Tests pass" alone is not sufficient evidence.
- The backend public submit endpoint (`public_app.py`), the public field config whitelist, the
  in-app SPA form, and the Flask landing module MUST NOT be modified. Any observable change there is
  a regression.
- The render step consumes `get_public_field_config` as its only field source and never re-derives
  a field list; no raw record shape crosses the boundary (steering 39). The public API base resolves
  from a publish-time env var with NO silent default (fail-fast).
- Backend tests: `python -m pytest -c sam/pytest.ini <paths> -q`.
