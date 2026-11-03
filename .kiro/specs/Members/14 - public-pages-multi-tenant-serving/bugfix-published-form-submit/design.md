# Published Application Form Submit Bugfix Design

## Overview

The PUBLISHED SAM application form — the static `{slug}/index.html` artifact served at
`{slug}.jabaki.nl/apply` — is rendered and styled but is a dead end for applicants. Two defects
combine into one unusable artifact and are fixed together:

- **A (submit):** the published body (`application_form_render.build_form_body_html`) emits a bare
  `<form method="post">` with a `<button type="submit">`, NO `action` and NO JavaScript. On submit
  the browser does a NATIVE form POST to the page's own `/apply` URL — a static S3/CloudFront site
  with no POST handler — so every submit 404s and the application is lost. The page never calls the
  (already-correct) backend endpoint.
- **B (field definition):** the field `format` validator token (`{checker, params}`, e.g. `IBAN`
  / `EMAIL`) is emitted in the public field config (`_serialize_public_field` sets
  `payload["format"]`), but `_render_field` IGNORES it, so the published page runs no client-side
  IBAN/email check. (The `required` flag and email/tel/number/date input types ARE already
  rendered.)

Both defects live in the render step, and both share the same root: the renderer emits a STATIC,
no-behavior form that neither wires a submit to the backend JSON contract nor reads the `format`
token (and, consequently, renders neither the consent control nor the locale selector the backend
requires on submit).

The fix enriches the PUBLISHED ARTIFACT only: the render step gains an embedded submit script that
`preventDefault`s the native POST and sends the backend JSON shape, client-side `required` + IBAN
+ EMAIL checks mirroring `field_formats`, a consent control + locale selector, and a publish-time
public-API-base baked into the page. The strategy is REUSE, not re-implementation: the backend
submit endpoint, the public field config whitelist, and the shared `LandingPageStyles` CSS all
already exist and are correct — the missing piece is the behavior and the two required controls in
the rendered artifact, plus the publish-time API base.

### What EXISTS vs what is MISSING (verified this session)

Backend — EXISTS and correct (NOT modified):

- `POST /public/members/{slug}/applications` on the separate public API (`MembersPublicApi` in
  `template.yaml`), NO authorizer (public, no login — by design), CORS restricted to the form
  origin(s) incl. the tenant's `application_embed_origins`. It resolves the tenant from the
  `_slugs/{slug}` marker BODY (scan-free, never from the body), strips any forged body
  `tenant_id`, re-validates required + format, and writes via `ApplicationService.create_application`.
  Handler: `sam/members/handler/public_app.py`.
- The expected request body shape (from `public_app.py`): JSON with field values under `fields`
  (object), `locale` (or `lang`), `consent` (object — REQUIRED; a submit without it is
  hard-rejected and the server stamps the authoritative consent record), optional `session_key`
  (idempotency; server mints a uuid4 if absent), and a honeypot `website` field (must be left
  empty). The server returns 422 with per-field errors; an unknown/unpublished slug returns a
  non-probeable 404.
- `get_public_field_config` / `_serialize_public_field` — the single filter authority. It ALREADY
  emits `payload["format"] = {checker, params}`, `locales` (the locale selector options), and
  `notice.version` (the consent-notice version the submit stamps). The renderer already consumes
  this config as its only field source.
- `field_formats.REGISTRY` — the platform `EMAIL` (regex) and `IBAN` (ISO 13616 mod-97 checksum)
  checkers. The client-side checks mirror these semantics; the server remains the authoritative
  enforcer.
- `services.landing_page_styles.LandingPageStyles` — the single shared CSS source (with the
  tenant's `color_primary` / `color_accent`). The published page already builds its CSS from it.

Published artifact (render step) — WRONG / MISSING:

- `build_form_body_html` emits a bare no-JS `<form method="post">` with a submit button and no
  `action` (defect A) — no submit script, no backend call.
- `_render_field` ignores the emitted `format` token (defect B) — no client-side IBAN/EMAIL check.
- No consent control and no locale selector are rendered, though the backend REQUIRES consent and
  a locale on submit and the config exposes `notice.version` + `locales`.
- No publish-time mechanism bakes the public API base URL into the static page (the static page
  cannot read `VITE_*`).

In-app SPA form — EXISTS and correct (NOT modified):

- `frontend/src/components/public/application/ApplicationFormPage.tsx` (Formik + `submitApplication`)
  already validates, submits, and maps 422s. It is the distinct public, no-login in-app path and
  stays unchanged.

### Where the published artifact is rendered TODAY

`sam/members/domain/application_publish.py` (the publish gate), once a tenant is READY, calls
`render_application_form_page(config, head_meta={...})` in `application_form_render.py`, which:
builds the body via `build_form_body_html` (the bare form), produces CSS from `LandingPageStyles`,
and hands head + body + css to the shared `sam.shared.page_shell.render_page`. The LIVE S3 put +
CloudFront invalidation stay gated (spec 14 Tasks 8/9); this fix changes the rendered STRING the
publish step produces, not the gating.

## Glossary

- **Bug_Condition (C)**: the condition that triggers the bug — a render/interaction on the
  PUBLISHED static application form where the artifact fails to wire a working backend submit or
  fails to honor the field `format` definition (and the consent/locale controls the backend
  requires), because the renderer emits a static, no-behavior form.
- **Property (P)**: the desired behavior — the published page submits the backend JSON shape to
  `POST /public/members/{slug}/applications` via a `preventDefault`ed script, runs client-side
  `required` + IBAN + EMAIL checks, and renders the consent + locale controls, all styled with the
  shared `LandingPageStyles`.
- **Preservation**: the in-app SPA form, the backend submit endpoint + slug-marker resolution +
  CORS + honeypot + payload cap, the Flask landing plane, and the already-correct render output
  (`required`, input types, section ordering, labels, CSS) stay unchanged.
- **Published artifact**: the static `{slug}/index.html` served at `{slug}.jabaki.nl/apply` from
  the shared public-pages bucket — rendered by `render_application_form_page`.
- **Public field config**: `get_public_field_config` output (`fields`, `functional_groups`,
  `locales`, `notice`, per-field `format`) — the single filter authority the renderer consumes.
- **`field_formats` registry**: the platform `EMAIL` / `IBAN` checker set; the client-side checks
  mirror its semantics, the server 422 is authoritative.

## Bug Details

### Bug Condition

The bug manifests on the PUBLISHED static application form: either an applicant submits it (and the
native POST 404s because no script redirects it to the backend JSON endpoint), or a
`format`-constrained field is rendered without its client-side check, or the page is rendered
without the consent/locale controls the backend requires. The shared root is that the render step
(`build_form_body_html` / `_render_field` → `render_application_form_page`) emits a STATIC,
no-behavior form that ignores the backend submit contract and the `format` token.

**Formal Specification:**

```
FUNCTION isBugCondition(input)
  INPUT: input of type PublishedFormInteraction
         { facet: SUBMIT | FORMAT | CONSENT_LOCALE,
           slug: str,
           public_field_config: Mapping,   # get_public_field_config output
           rendered_artifact: HtmlString }  # render_application_form_page output
  OUTPUT: boolean

  RETURN
    // A — submit does a native POST to the static page instead of the backend JSON endpoint
    (input.facet = SUBMIT
       AND NOT artifact_submits_json_to(input.rendered_artifact,
                                        "POST /public/members/{slug}/applications")
       AND native_form_post_not_prevented(input.rendered_artifact))
    OR
    // B — a field carries a format token that the artifact does not client-side check
    (input.facet = FORMAT
       AND exists field IN input.public_field_config.fields WHERE field.format IS NOT None
       AND NOT artifact_client_checks(input.rendered_artifact, field.format.checker))
    OR
    // B consequence — the backend requires consent + locale but the artifact renders neither
    (input.facet = CONSENT_LOCALE
       AND (NOT artifact_renders_consent(input.rendered_artifact, input.public_field_config.notice)
            OR NOT artifact_renders_locale_selector(input.rendered_artifact,
                                                    input.public_field_config.locales)))
END FUNCTION
```

### Examples

- `hdcn-aanmelden` (published): an applicant fills the form and clicks "Verstuur" → the browser
  POSTs form-urlencoded fields to `https://hdcn-aanmelden.jabaki.nl/apply` → **404 Not Found**; the
  backend `POST /public/members/hdcn-aanmelden/applications` is never called. (facet=SUBMIT)
- A field with `format = {checker: "IBAN"}`: an applicant types an IBAN with a bad checksum → the
  published page accepts it with no feedback (no client check); only a later server 422 would catch
  it, but the submit never reaches the server (defect A). (facet=FORMAT)
- The config exposes `notice.version` and `locales` but the published page shows no consent
  checkbox and no locale selector → even a correctly-posted body would be hard-rejected by the
  backend for missing consent. (facet=CONSENT_LOCALE)
- A field with `required: true`: the published `<input required>` IS rendered — NOT a bug (this is
  the preserved render output).

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**

- The in-app SPA application form (`ApplicationFormPage.tsx` + Formik + `submitApplication`) —
  validation, submit, 422 mapping — behaves exactly as today.
- The backend public submit endpoint (`public_app.py` →
  `POST /public/members/{slug}/applications`): slug-marker tenant resolution, forged-`tenant_id`
  strip, CORS allow-list, honeypot, payload-size cap, server-side required + format re-validation,
  422 / non-probeable 404 — all unchanged.
- All Flask landing-plane behavior (spec 14 Scope decision) — untouched.
- `get_public_field_config` (the single filter authority / whitelist) — unchanged; the renderer
  consumes it, never re-derives a field list; no raw record shape crosses the boundary
  (steering 39).
- The already-correct render output: the `required` flag, email/tel/number/date input types, the
  `<fieldset>` section ordering by the authored `functional_groups`, labels (locale with `nl`
  fallback), the HTML-escaping of config-origin values, and the `LandingPageStyles` CSS.

**Scope:**

All interactions that do NOT involve the published artifact's submit behavior, its `format`-based
client checks, or its consent/locale controls are completely unaffected by this fix. This includes
the entire in-app SPA path, the entire backend, and the entire Flask landing plane.

The actual expected correct behavior for buggy inputs is defined in Correctness Properties
(Property 1).

## Hypothesized Root Cause

Based on the verified code, the most likely causes are:

1. **The render step emits a static, no-behavior form (primary, defect A).** In
   `application_form_render.build_form_body_html`, the form body is a literal
   `<form class="application-form" method="post">…<button type="submit">Verstuur</button></form>`
   with NO `action` and NO embedded `<script>`. Nothing calls `preventDefault`, serializes the
   fields to the backend JSON shape, or sends them to
   `POST /public/members/{slug}/applications`. `render_application_form_page` (and the shared
   `page_shell`) wrap this body verbatim, so the full document inherits the no-JS form. A native
   submit therefore POSTs to the page's own URL and 404s.

2. **`_render_field` ignores the `format` token (primary, defect B).** The public field config
   emits `payload["format"] = {checker, params}` (`_serialize_public_field`), but `_render_field`
   only reads `key` / `type` / `label` / `required` / `options`. There is no code path that reads
   `field["format"]` to attach a client-side IBAN/EMAIL check, so a `format`-constrained field is
   rendered as a plain input.

3. **Consent + locale controls were never rendered.** The config already surfaces `locales` and
   `notice.version`, and the backend REQUIRES a consent object + a locale on submit, but
   `build_form_body_html` renders neither a consent checkbox (bound to the notice version) nor a
   locale selector — a direct consequence of emitting a static form that was never wired to the
   submit contract.

4. **No publish-time API base plumbing.** The static page cannot read `VITE_*`, and no publish-time
   env var is resolved to bake the public API base URL into the artifact — so even a submit script
   would have no backend address. Other SAM resources resolve from an env var with no silent
   default (fail-fast); the render/publish step has no equivalent for the API base.

## Correctness Properties

Property 1: Bug Condition - Published form submits to the backend and honors the field definition

_For any_ published-form interaction where the bug condition holds (isBugCondition returns true),
the fixed render SHALL produce an artifact that: for a SUBMIT interaction, calls `preventDefault`
on the native submit and instead sends a JSON request to
`POST /public/members/{slug}/applications` with the field values under `fields`, plus `locale`
(or `lang`), `consent`, an optional `session_key`, and an empty `website` honeypot — showing a
success state on success, mapping per-field errors inline on a 422, and showing a neutral message
on the non-probeable 404 / neutral states; for a FORMAT interaction, runs the client-side check
matching each field's `format.checker` (IBAN / EMAIL, mirroring the `field_formats` registry
semantics) alongside the existing `required` check, with the server 422 as the authoritative
backstop; and for a CONSENT_LOCALE interaction, renders a consent control bound to the config's
notice version and a locale selector from the config's `locales` — all styled with the shared
`LandingPageStyles` and the existing `<fieldset>`/label structure.

**Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 2.6**

Property 2: Preservation - In-app form, backend, Flask plane, and existing render output unchanged

_For any_ input where the bug condition does NOT hold (isBugCondition returns false) — the in-app
SPA application form, the backend public submit endpoint and its slug-marker resolution / CORS /
honeypot / payload cap, any Flask landing-plane operation, or the already-correct render output
(`required`, input types, section ordering, labels, escaping, `LandingPageStyles` CSS) — the fixed
system SHALL produce the same result as the original system, preserving the in-app path, the
untouched backend, the untouched Flask landing module, and the unchanged render output.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4**

## Fix Implementation

### Changes Required

Assuming the root-cause analysis is correct, the minimal fix — contained to the render/publish step
and honoring the single-filter-authority + fail-fast conventions (steering 39) — is:

**1. Render a working submit script into the published body.**

- **File**: `sam/members/domain/application_form_render.py`
  - In `build_form_body_html`, stop emitting a bare `<form method="post">`. Emit a form whose
    submit is handled by an embedded `<script>` that: (a) `preventDefault`s the native submit so no
    form POST to `/apply` fires; (b) serializes the fields into the backend JSON shape — values
    under `fields` (keyed by the field `key`), plus `locale` (or `lang`) from the locale selector,
    `consent` (the object bound to the notice version), an optional `session_key`, and the empty
    `website` honeypot; (c) `fetch`es `POST {API_BASE}/public/members/{slug}/applications` with
    `Content-Type: application/json`; and (d) handles the response — success state, inline per-field
    422 mapping, neutral message on 404 / neutral states. No internal detail is surfaced to the
    applicant.
  - The `slug` and the baked-in API base must be available to `build_form_body_html` /
    `render_application_form_page` (passed through from the publish service — see change 4).

**2. Honor the `format` token in the field render + run client-side checks.**

- **File**: `sam/members/domain/application_form_render.py`
  - In `_render_field`, read `field["format"]` (the `{checker, params}` the config already emits)
    and emit the field so the submit script can run the matching client-side check. The checks
    mirror the `field_formats` semantics: EMAIL (the platform email pattern) and IBAN (ISO 13616
    mod-97 checksum). Keep the existing `required` rendering. The client checks are convenience;
    the server 422 remains authoritative (the submit script still maps server errors).

**3. Render the consent control + locale selector.**

- **File**: `sam/members/domain/application_form_render.py`
  - In `build_form_body_html`, render a consent control (a checkbox bound to the config's
    `notice.version`) and a locale selector (options from the config's `locales`). These are
    required by the backend submit contract; the submit script reads them into `consent` and
    `locale`. Style them with the existing `form-field` / `form-group` classes so they match the
    rest of the form.

**4. Bake the public API base in at publish time (fail-fast, no silent default).**

- **File**: `sam/members/domain/application_publish.py` (and the render entry point
  `render_application_form_page`)
  - Resolve the public API base URL from a publish-time environment variable with NO default
    (mirroring the `GOVERNANCE_PROJECTION_TABLE` fail-fast model — a missing value raises at the
    first real call, never silently targets the wrong backend). Pass the resolved base + the slug
    into `render_application_form_page` so the submit script's `fetch` target is correct per
    environment.

**5. Reuse, do not fork, the CSS + structure.**

- The new elements (consent, inline errors, success state, format feedback) reuse the shared
  `LandingPageStyles` classes and the existing `<fieldset>`/section/label structure — no new CSS
  source, no second field list. `get_public_field_config` stays the only field source (steering 39).

NOTE: the fix is confined to the SAM render/publish step + the publish-time env plumbing. The
backend submit endpoint, the public field config whitelist, the in-app SPA form, and the Flask
landing plane are NOT modified.

## Testing Strategy

### Validation Approach

Two phases: first surface counterexamples that demonstrate the bug on the UNFIXED render, then
verify the fix produces a submitting, definition-honoring artifact and preserves everything else.
The rendered artifact is asserted as a STRING (the render step is pure — it returns the HTML), so
the exploration and fix checks run offline against `render_application_form_page` /
`build_form_body_html` output over the real `get_public_field_config` shape.

### Exploratory Bug Condition Checking

**Goal**: surface counterexamples that demonstrate the bug BEFORE implementing the fix; confirm or
refute the root-cause analysis.

**Test Plan**: render the published artifact on the UNFIXED code from a representative public field
config (including a `format`-constrained field and non-empty `locales` + `notice`) and assert the
artifact's shape per facet.

**Test Cases**:
1. **Native-POST submit (SUBMIT)**: render the artifact and assert it contains a bare
   `<form method="post">` with NO embedded submit `<script>`, NO `preventDefault`, and NO reference
   to `POST /public/members/{slug}/applications` — i.e. a submit would do a native POST (buggy).
2. **Ignored `format` (FORMAT)**: render a config with a field carrying `format = {checker:"IBAN"}`
   and assert the artifact contains NO client-side IBAN check wiring for that field (buggy).
3. **Missing consent/locale (CONSENT_LOCALE)**: render a config with non-empty `locales` and a
   `notice.version` and assert the artifact renders NEITHER a consent control bound to that version
   NOR a locale selector (buggy — the backend would reject the submit).

**Expected Counterexamples**:
- The artifact is a static no-JS form; a submit would POST to the page URL and 404.
- A `format` field is rendered as a plain input with no client check.
- Neither the consent control nor the locale selector is present.

### Fix Checking

**Goal**: verify that for all inputs where the bug condition holds, the fixed render produces the
expected artifact.

**Pseudocode:**

```
FOR ALL input WHERE isBugCondition(input) DO
  artifact := render_application_form_page_fixed(input.public_field_config, slug, api_base)
  ASSERT expectedBehavior(artifact)
  // SUBMIT        -> preventDefault + JSON POST to /public/members/{slug}/applications (fields, locale, consent, session_key, empty website)
  // FORMAT        -> client-side IBAN/EMAIL check wired for each format-constrained field
  // CONSENT_LOCALE-> consent control bound to notice.version + locale selector from locales, styled with LandingPageStyles
END FOR
```

### Preservation Checking

**Goal**: verify that for all inputs where the bug condition does NOT hold, the fixed system
produces the same result as the original.

**Pseudocode:**

```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT originalSystem(input) = fixedSystem(input)
  // in-app SPA form; backend submit endpoint + slug-marker/CORS/honeypot/cap; Flask landing ops;
  // existing render output: required flag, input types, section ordering, labels, escaping, CSS
END FOR
```

**Testing Approach**: observe behavior on the UNFIXED code for non-bug inputs, then write
property-based tests capturing it. Property-based testing is recommended because preservation is a
universal property across many non-buggy inputs (any config without a `format` field still renders
its `required` flags, input types, sections, labels, and CSS identically).

**Test Plan**: observe the UNFIXED render output for the preserved facets, then assert unchanged
after the fix; leave the backend and in-app paths untouched and assert they are not referenced by
the render change.

**Test Cases**:
1. **Existing render output preserved**: for a config with `required` fields, email/number/date
   types, grouped sections, and branding, the `required` attributes, input types, `<fieldset>`
   ordering, labels, escaping, and `LandingPageStyles` CSS are identical before and after.
2. **Backend endpoint unchanged**: the public submit handler (`public_app.py`) — slug-marker
   resolution, forged-`tenant_id` strip, CORS, honeypot, payload cap, 422 / non-probeable 404 —
   round-trips identically (no change in this fix).
3. **In-app SPA form unchanged**: `ApplicationFormPage.tsx` + `submitApplication` behavior is not
   referenced or altered by the render change.

### Unit Tests

- `build_form_body_html` / `render_application_form_page`: the artifact contains a `preventDefault`ed
  submit script posting the correct JSON shape to `POST /public/members/{slug}/applications`; a
  `format` field wires the matching client check; consent + locale controls are rendered and styled
  with the existing classes; config-origin values stay HTML-escaped.
- Publish-time API base: a missing env var fails loudly (fail-fast, no silent default); a present
  value is baked into the artifact's `fetch` target.
- Preserved output: `required`, input types, section ordering, labels, escaping, CSS unchanged for
  a config with no `format` field.

### Property-Based Tests

- Property 1 (bug condition): for generated public field configs (varying fields, `format` tokens,
  `locales`, `notice`), the rendered artifact always submits the backend JSON shape, wires a client
  check for every `format`-constrained field, and renders the consent + locale controls.
- Property 2 (preservation): for generated configs with NO `format` field, the rendered `required`
  flags, input types, section ordering, labels, escaping, and CSS equal the original render output.

### Integration Tests

- Backend paired SAM pytest run (`python -m pytest -c sam/pytest.ini <paths> -q`) exercising
  `render_application_form_page` over the real `get_public_field_config` shape (e.g. `h-dcn`),
  asserting the artifact's submit script targets `POST /public/members/{slug}/applications` with
  the baked-in API base and the correct JSON body shape.
- An end-to-end check (manual / TEST) that a published `{slug}/index.html` submit reaches the
  backend endpoint (no native-POST 404), maps a server 422 inline, and shows a success state —
  with the page's look and feel matching the application form.

## Out of scope — deliberate follow-up (next bugfix): tenant logo + branding on the published form

The published form's COLOURS already flow through `LandingPageStyles` (the renderer accepts a
`branding` dict with `color_primary`/`color_accent`), so richer colour branding is a small data
wire-up and is not a structural problem.

The TENANT LOGO is a deliberate FOLLOW-UP (not this bugfix). The known fact to carry forward:

- The logo is stored as `branding.company_logo_s3_key` (e.g.
  `h-dcn/branding/ast_...company_logo.jpg`) — a tenant-override parameter maintained in the
  **Flask Parameter zone** (MySQL plane), NOT on the SAM plane.
- The published form is a SAM-plane static artifact served from the public-pages bucket on
  `*.jabaki.nl`. So the logo bugfix must (a) SOURCE the value cross-plane (project it to SAM like
  other tenant attributes, or resolve it at publish time from a SAM-readable source), and (b)
  RESOLVE the S3 KEY into a PUBLICLY reachable URL a browser on `*.jabaki.nl` can load, then (c)
  BAKE that URL into the artifact at publish time (the static page cannot resolve an
  authenticated/relative asset) — the same publish-time plumbing this bugfix adds for the API base.

This note exists so the follow-up starts with the cross-plane sourcing + public-URL resolution
already identified. It is explicitly NOT implemented here.
