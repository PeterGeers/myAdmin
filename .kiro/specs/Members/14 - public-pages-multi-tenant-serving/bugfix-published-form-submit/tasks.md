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

---

## Round 2 — CORS, consent notice text, and error clarity

Second round for defects found testing the shipped Round-1 fix in TEST: the published form's submit
still fails because (1) CORS blocks the response from the per-slug host, (2) the consent notice TEXT
is not served/rendered so consent is posted empty (422 `CONSENT_REQUIRED`), and (3) error messages
are only the generic catch-all. Same exploration-test-first / preservation discipline, continuing
the task numbering. The exploration test (task 5) and preservation tests (task 6) are written and
run on the UNFIXED (Round-1-shipped) code BEFORE the Round-2 fix (task 7); task 8 is the checkpoint.

### Round 2 Task Dependency Graph

```json
{
  "waves": [
    {
      "wave": 1,
      "tasks": ["5", "6"],
      "description": "Round-2 exploration test (asserts the three buggy facets on the shipped code) and preservation tests (pass on the shipped code), both written first."
    },
    {
      "wave": 2,
      "tasks": ["7.1", "7.2"],
      "description": "CORS Option B (resolved slug host) and full-notice surfacing in get_public_field_config. Independent of each other; both depend on 5 and 6."
    },
    {
      "wave": 3,
      "tasks": ["7.3", "7.4"],
      "description": "Render notice text above the checkbox (depends on 7.2) and inline 422 error mapping (depends on 7.1 so the real 422 is readable)."
    },
    {
      "wave": 4,
      "tasks": ["7.5", "7.6"],
      "description": "Verify Round-2 exploration test passes (depends on 7.1-7.4) and preservation tests still pass (depends on 7.1-7.4)."
    },
    {
      "wave": 5,
      "tasks": ["8"],
      "description": "Round-2 checkpoint: all CORS/notice/render/error + preservation tests pass. Depends on all of task 7."
    }
  ]
}
```

### Round 2 Tasks

- [x] 5. Write Round-2 bug condition exploration test
  - **Property 3: Bug Condition** - Submit is readable, consent is shown, errors are clear
  - **CRITICAL**: This test MUST FAIL on the shipped (Round-1) code - failure confirms the Round-2 bug exists
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: This test encodes the expected Round-2 behavior - it will validate the fix when it passes after implementation
  - **GOAL**: Surface counterexamples proving the submit still fails for the applicant across the three facets (CORS / NOTICE_TEXT / ERROR_CLARITY)
  - **Scoped PBT Approach**: scope to a representative slug + per-env apex, a tenant whose
    `config#mail` `get_consent_notice` returns `{version, text}`, and a consent-required 422
    (`consent` / `CONSENT_REQUIRED`)
  - Backend (`python -m pytest -c sam/pytest.ini <paths> -q`), assert the UNFIXED behavior:
    - CORS facet: with `PUBLIC_FORM_ALLOWED_ORIGINS` = the single canonical host and no matching
      embed origin, `_apply_cors_origin` / `handler` returns NO `Access-Control-Allow-Origin` for a
      request `Origin` equal to the resolved slug host `https://{resolved_slug}.{apex}` (read blocked)
    - NOTICE_TEXT facet: `get_public_field_config` returns `notice = {"version": ...}` with NO
      `text`, even though `get_consent_notice` returns `{version, text}` for that tenant
    - ERROR_CLARITY facet: the rendered submit script maps a `consent` / `CONSENT_REQUIRED` 422 only
      to the generic catch-all (no consent-adjacent message, no field-adjacent 422 mapping)
  - Run on the shipped code
  - **EXPECTED OUTCOME**: Test FAILS / asserts the buggy behavior (this is correct - it proves the bug exists)
  - Document counterexamples found (e.g. "hdcn-aanmelden: Origin https://hdcn-aanmelden.jabaki.nl dropped by CORS; notice has version but no text; consent 422 shows generic message")
  - Mark task complete when test is written, run, and failure is documented
  - _Requirements: 4.1, 4.2, 4.3, 4.4_

- [x] 6. Write Round-2 preservation property tests (BEFORE implementing fix)
  - **Property 4: Preservation** - Backend consent gate, consent stamp, and other planes unchanged
  - **IMPORTANT**: Follow observation-first methodology — observe on the shipped code, then assert the SAME behavior is preserved
  - Observe and assert preserved:
    - The backend public submit endpoint + its consent gate (`_consent_is_affirmative` requires
      `accepted === true`, fail-closed) round-trips unchanged (NOT modified by Round 2)
    - `create_application`'s server-authoritative consent stamp on the member record
      (`_stamp_application_consent` → `{version, accepted_at, locale}`) is unchanged
    - The in-app SPA form, the Flask landing plane, and the `config#mail` write path
      (`config_write_service._shape_consent_notice`) are not referenced or altered
    - `get_public_field_config` stays the single field authority: surfacing the full notice adds
      only `text` beside `version`; no raw record shape crosses the boundary (steering 39)
    - CORS stays fail-closed (drop the header, never `*`, no `*.jabaki.nl` wildcard) for any origin
      that is NOT the resolved slug host, the static baseline, or a tenant embed origin — assert a
      foreign `*.jabaki.nl` host is rejected
  - Prove the notice round-trip against the REAL `config#mail` / `get_consent_notice` shape
    (e.g. `h-dcn`), not a hand-built fixture (steering 39)
  - Write property-based tests capturing the observed behavior
  - Run tests on the shipped code
  - **EXPECTED OUTCOME**: Tests PASS (this confirms the baseline behavior to preserve)
  - Mark task complete when tests are written, run, and passing on the shipped code
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

- [x] 7. Fix for the published form submit failing in TEST (CORS, notice text, error clarity)

  - [x] 7.1 CORS Option B — allow the resolved slug host (fail-closed otherwise, no wildcard)
    - In `sam/members/handler/public_app.py`: when the route has resolved a slug to a tenant for
      THAT request, compute the form's own host `https://{resolved_slug}.{apex}` where `apex` is read
      from a per-env config/env var (NO hardcode, NO `*.jabaki.nl` wildcard), and union it with the
      existing `_allowed_origins()` static baseline and `_tenant_embed_origins(tenant_id)` in the
      `_apply_cors_origin` decision
    - Keep fail-closed: no `Origin` / foreign origin / empty union → drop the header, never `*`; the
      only widening is the form's OWN resolved slug host, so no foreign `*.jabaki.nl` site is admitted
    - _Bug_Condition: isBugConditionR2(input) with facet=CORS from design_
    - _Expected_Behavior: Property 3 (echo for resolved slug host ∪ baseline ∪ embed origins; fail-closed) from design_
    - _Preservation: Round 2 Preservation Requirements (backend gate/stamp, CORS fail-closed for foreign origins)_
    - _Requirements: 5.1, 6.1, 6.5_

  - [x] 7.2 Surface the full consent notice {version, text} in get_public_field_config
    - In `sam/members/domain/_membership_writes_fieldconfig.py` (`get_public_field_config`): replace
      the version-only `notice = {"version": ...}` with the FULL notice `{version, text}` sourced
      from `get_consent_notice` (wired via a provider exposing `get_consent_notice`; the projection
      reader `MembersProjectionReader` already satisfies it); keep empty-is-valid (`None`/absent)
    - No raw record shape crosses the boundary (steering 39) — only `text` is added beside `version`;
      `get_public_field_config` stays the single field authority
    - _Bug_Condition: isBugConditionR2(input) with facet=NOTICE_TEXT from design_
    - _Expected_Behavior: Property 3 (notice == {version, text} from get_consent_notice, empty-is-valid) from design_
    - _Preservation: Round 2 Preservation Requirements (single field authority, no raw-shape leak)_
    - _Requirements: 5.2, 6.4_

  - [x] 7.3 Render the notice TEXT above the consent checkbox, styled with LandingPageStyles
    - In `sam/members/domain/application_form_render.py` (`_render_consent_control` /
      `build_form_body_html`): when a notice is present, render its localized `text[locale]`
      (with `nl` fallback), HTML-escaped, ABOVE the consent checkbox (checkbox still bound to
      `notice.version`); render the checkbox whenever there is a notice so consent can be given;
      style with the shared `LandingPageStyles` classes — no new CSS source
    - _Bug_Condition: isBugConditionR2(input) with facet=NOTICE_TEXT from design_
    - _Expected_Behavior: Property 3 (localized escaped text above the checkbox; checkbox renders when notice present) from design_
    - _Preservation: Round 2 Preservation Requirements (single CSS source; notice-less render unchanged)_
    - _Requirements: 5.3, 6.4_

  - [x] 7.4 Map the consent-required and field 422s inline in the submit script
    - In `sam/members/domain/application_form_render.py` (the embedded submit script): map a 422
      whose synthetic field key is `consent` (code `CONSENT_REQUIRED`) to a clear message near the
      consent control, and each field 422 to an inline message near that field; keep a neutral
      generic message only for opaque / 5xx responses; leak no internal detail
    - Depends on 7.1 so the real 422 is readable cross-origin
    - _Bug_Condition: isBugConditionR2(input) with facet=ERROR_CLARITY from design_
    - _Expected_Behavior: Property 3 (consent 422 near the consent control; field 422s inline; neutral only for opaque/5xx) from design_
    - _Preservation: Round 2 Preservation Requirements (backend endpoint unchanged)_
    - _Requirements: 5.4_

  - [x] 7.5 Verify Round-2 bug condition exploration test now passes
    - **Property 3: Expected Behavior** - Submit is readable, consent is shown, errors are clear
    - **IMPORTANT**: Re-run the SAME test from task 5 - do NOT write a new test
    - Run the Round-2 exploration test from step 5 (`python -m pytest -c sam/pytest.ini <paths> -q`)
    - **EXPECTED OUTCOME**: Test PASSES (confirms the resolved slug host is CORS-allowed, the notice text is served + rendered, and the consent/field 422s map inline)
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

  - [x] 7.6 Verify Round-2 preservation tests still pass
    - **Property 4: Preservation** - Backend consent gate, consent stamp, and other planes unchanged
    - **IMPORTANT**: Re-run the SAME tests from task 6 - do NOT write new tests
    - Run the preservation property tests from step 6 (incl. the real `get_consent_notice` /
      `config#mail` round-trip and the CORS fail-closed-for-foreign-origin assertion)
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions)
    - Confirm all tests still pass after fix (no regressions)

- [x] 8. Round 2 Checkpoint - Ensure all tests pass
  - Run the paired SAM pytest suites for the changed handler/field-config/render files; ensure all
    pass. Ask the user if questions arise.

## Round 2 Notes

- Write the Round-2 exploration test (task 5) BEFORE implementing the fix, and run it on the shipped
  (Round-1) code to confirm it asserts the buggy behavior across CORS / NOTICE_TEXT / ERROR_CLARITY.
  Do not fix the test or code when it fails at task 5.
- CORS Option B is the TIGHTEST match: only the form's OWN resolved slug host
  `https://{resolved_slug}.{apex}` (resolved from the `_slugs/{slug}` marker, apex from a per-env
  config/env var), unioned with the existing static baseline + the tenant's `application_embed_origins`.
  NO hardcoded apex, NO broad `*.jabaki.nl` wildcard, fail-closed otherwise, never `*`.
- The consent notice TEXT already exists in SAM (`get_consent_notice` on the `config#mail` row) — NO
  Flask projection is needed; Round 2 only SURFACES it in `get_public_field_config` and RENDERS it.
- Already DONE / NO-OP (do not change): the server-authoritative consent stamp on the member record
  (`create_application` → `_stamp_application_consent`); the backend consent gate
  (`_consent_is_affirmative`, `accepted === true`, fail-closed); the in-app SPA form; the Flask
  landing plane; the `config#mail` write path (`config_write_service._shape_consent_notice`).
- Prove the notice round-trip against the REAL `config#mail` / `get_consent_notice` shape (`h-dcn`),
  not a hand-built fixture (steering 39). "Tests pass" alone is not sufficient evidence.
- Backend tests: `python -m pytest -c sam/pytest.ini <paths> -q`.
