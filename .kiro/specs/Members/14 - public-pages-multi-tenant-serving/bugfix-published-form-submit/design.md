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

---

# Round 2 — CORS, consent notice text, and error clarity

## Round 2 Overview

The Round-1 fix shipped: the published `{slug}/index.html` now renders a `preventDefault`ed submit
script, client-side `format` (IBAN/EMAIL) + `required` checks, a locale selector, and a consent
CHECKBOX bound to `notice.version`. Testing that artifact in TEST showed the applicant STILL cannot
complete a submission. Three root causes were confirmed this session against the current code — all
in the submit flow — and are fixed together as Round 2:

- **Defect 1 — CORS blocks the response.** The published form is served per-tenant at
  `https://{slug}.jabaki.nl` and POSTs cross-origin to the separate public API (`MembersPublicApi`).
  `sam/members/handler/public_app.py::_apply_cors_origin` echoes `Access-Control-Allow-Origin` only
  when the request `Origin` is an EXACT-STRING member of `_allowed_origins()` (the
  `PUBLIC_FORM_ALLOWED_ORIGINS` env — a SINGLE canonical host per env: TEST
  `https://aanmelden-test.jabaki.nl`, PROD `https://aanmelden.jabaki.nl`) unioned with the tenant's
  `application_embed_origins`. The per-slug published host `{slug}.jabaki.nl` is in NEITHER list, so
  the browser drops the CORS header and BLOCKS the read; the submit fetch rejects into the generic
  catch-all and the real 422 is never readable. An exact-string match cannot cover per-slug hosts.
- **Defect 2 — the consent NOTICE TEXT is not shown.** `get_public_field_config`
  (`_membership_writes_fieldconfig.py`) serves `notice = {"version": ...}` ONLY (wired to
  `_consent_notice_provider.get_consent_notice_version`). The applicant therefore has no text to
  read/accept, consent is posted empty, and the backend returns a 422 `CONSENT_REQUIRED`. The FULL
  notice `{version, text}` ALREADY exists in SAM on the `config#mail` row and is read by
  `MembersProjectionReader.get_consent_notice(tenant_id) -> {"version","text"} | None`
  (`repository/_mail_config_reader.py`) — whose docstring states the public field-config read is
  intended to serve "this notice's current text + version to the form". So the text is in SAM
  already; NO Flask projection is needed.
- **Defect 3 — error messages are unclear.** Once CORS is fixed the real 422 is readable, but the
  submit script maps only a generic catch-all; the consent-required 422 (synthetic field key
  `consent`, code `CONSENT_REQUIRED`) and per-field 422s are not surfaced near their controls.

### Already handled — NO-OP (verified this session)

The applicant's consent ACCEPTANCE is already STORED IN SAM: `create_application`
(`_membership_writes_application.py::_stamp_application_consent`) stamps a server-authoritative
`consent = {version, accepted_at, locale}` onto the member record in DynamoDB (version resolved
server-side via `get_consent_notice_version`, timestamp server-UTC, locale normalized). Round 2
does NOT touch this. The round-2 work is only: let the applicant SEE + ACCEPT the notice (serve +
render text), CORS so the submit is readable, and clear errors.

## Round 2 Glossary additions

- **Resolved slug host**: the published form's OWN origin `https://{resolved_slug}.{apex}`, where
  `resolved_slug` is the slug already resolved from the `_slugs/{slug}` marker for THAT request and
  `apex` is a per-env config/env var (e.g. `jabaki.nl` in prod, the test apex in TEST). The tightest
  CORS match — only the form's own slug host, never a broad `*.jabaki.nl` wildcard.
- **Full consent notice**: `{version, text}` where `text = {locale: body}`, read from the
  `config#mail` row via `MembersProjectionReader.get_consent_notice`. Empty-is-valid → `None`.
- **CORS Option B** (user-chosen): allow the request `Origin` when it equals the resolved slug host,
  unioned with the existing static baseline + the tenant's embed origins; fail-closed otherwise,
  never `*`, no wildcard.

## Round 2 Bug Details

The bug manifests on the SHIPPED published form's SUBMIT flow across three facets. Formal condition
(continuing the Round-1 `isBugCondition` with new facets):

```
FUNCTION isBugConditionR2(input)
  INPUT: input of type PublishedSubmitInteraction
         { facet: CORS | NOTICE_TEXT | ERROR_CLARITY,
           slug: str,
           resolved_slug: str,            # from the _slugs/{slug} marker for THIS request
           apex: str,                     # per-env config/env var
           request_origin: str,           # the submitting form's host, https://{slug}.jabaki.nl
           public_field_config: Mapping,  # get_public_field_config output
           rendered_artifact: HtmlString,
           backend_response: HttpResponse }
  OUTPUT: boolean

  RETURN
    // Defect 1 — the form's own slug host is blocked by CORS
    (input.facet = CORS
       AND input.request_origin = "https://" + input.resolved_slug + "." + input.apex
       AND NOT cors_allows(input.request_origin))          # header dropped -> read blocked
    OR
    // Defect 2 — notice text is not served, so the applicant cannot see/accept it
    (input.facet = NOTICE_TEXT
       AND consent_notice_exists_in_sam(input.slug)        # get_consent_notice returns {version,text}
       AND public_field_config.notice HAS "version"
       AND NOT public_field_config.notice HAS "text")      # only version served
    OR
    // Defect 3 — a readable 422 is mapped only to the generic catch-all
    (input.facet = ERROR_CLARITY
       AND input.backend_response.status = 422
       AND NOT artifact_maps_inline(input.rendered_artifact, input.backend_response))
END FUNCTION
```

### Round 2 Examples

- `hdcn-aanmelden` submits from `https://hdcn-aanmelden.jabaki.nl` to the public API → the request
  `Origin` is neither the static baseline (`https://aanmelden-test.jabaki.nl` in TEST) nor in
  `application_embed_origins`, so `_apply_cors_origin` drops the header → the browser blocks the
  read → generic catch-all; the real 422 never seen. (facet=CORS)
- `config#mail` for h-dcn carries `consent_notice = {version:"2", text:{nl:"…", en:"…"}}`, but
  `get_public_field_config` serves `notice = {version:"2"}` only → the form shows no text → consent
  posted empty → 422 `CONSENT_REQUIRED`. (facet=NOTICE_TEXT)
- The backend returns 422 with field key `consent` / code `CONSENT_REQUIRED` → the submit script
  shows "Je aanmelding kon niet worden verwerkt" instead of a clear "please accept the notice"
  message near the checkbox. (facet=ERROR_CLARITY)

## Round 2 Hypothesized Root Cause

1. **CORS allow-list is an exact-string set that cannot cover per-slug hosts (Defect 1).**
   `_allowed_origins()` reads a single canonical host from `PUBLIC_FORM_ALLOWED_ORIGINS`;
   `_apply_cors_origin` admits an `Origin` only on exact membership of that set ∪
   `application_embed_origins`. The published per-slug host `{slug}.jabaki.nl` is structurally
   outside both, so no static value can admit it without either enumerating every slug or opening a
   `*.jabaki.nl` wildcard (too broad). The fix must derive the allowed origin from the request's
   OWN resolved slug + a per-env apex.

2. **The public field-config read serves version-only (Defect 2).** `get_public_field_config`
   builds `notice = {"version": get_consent_notice_version(tenant_id)}`. The full notice already
   lives in SAM (`get_consent_notice`), but this read path does not call it, so `text` never reaches
   the form. The fix wires a provider exposing `get_consent_notice` and surfaces `{version, text}`.

3. **The renderer has a checkbox but no text, and the checkbox only renders when a version exists
   (Defect 2 consequence).** `_render_consent_control` renders a checkbox bound to `notice.version`
   but no notice body; with text now served, the renderer must show the localized, HTML-escaped text
   above the checkbox and render the checkbox whenever a notice is present.

4. **The submit script maps only a generic catch-all (Defect 3).** The response handler does not
   distinguish the consent-required 422 (synthetic field key `consent`, code `CONSENT_REQUIRED`) or
   per-field 422s from opaque/5xx failures, so every failure reads the same. The fix maps the
   consent 422 near the consent control and field 422s near their fields.

## Round 2 Correctness Properties

Property 3: Bug Condition (Round 2) - Submit is readable, consent is shown, errors are clear

_For any_ published-submit interaction where the Round-2 bug condition holds (isBugConditionR2
returns true): for a CORS interaction, the fixed `public_app` SHALL echo
`Access-Control-Allow-Origin` for the request `Origin` when it equals the resolved slug host
`https://{resolved_slug}.{apex}` (resolved_slug from the `_slugs/{slug}` marker, apex from a per-env
config/env var), unioned with the static baseline and the tenant's `application_embed_origins`, and
SHALL remain fail-closed (drop the header, never `*`, no `*.jabaki.nl` wildcard) for any other
origin; for a NOTICE_TEXT interaction, `get_public_field_config` SHALL surface the FULL notice
`{version, text}` (from `get_consent_notice`, empty-is-valid → `None`/absent) and the renderer SHALL
show the localized, HTML-escaped notice text ABOVE a consent checkbox bound to `notice.version`,
rendering the checkbox whenever a notice is present, styled with `LandingPageStyles`; and for an
ERROR_CLARITY interaction, the submit script SHALL map the consent-required 422 (field key
`consent`, code `CONSENT_REQUIRED`) to a clear message near the consent control and field 422s
inline near their fields, keeping a neutral message only for opaque/5xx cases.

**Validates: Requirements 5.1, 5.2, 5.3, 5.4**

Property 4: Preservation (Round 2) - Backend consent gate, consent stamp, and other planes unchanged

_For any_ input where the Round-2 bug condition does NOT hold (isBugConditionR2 returns false), the
fixed system SHALL produce the same result as the original, preserving: the backend public submit
endpoint and its consent gate (`_consent_is_affirmative` requires `accepted === true`, fail-closed);
the server-authoritative consent stamp on the member record (`_stamp_application_consent`); the
in-app SPA form; the Flask landing plane; the `config#mail` write path
(`config_write_service._shape_consent_notice`); and `get_public_field_config` as the single field
authority with no raw-shape leak (surfacing the full notice adds only `text` beside `version`). CORS
for any origin that is NOT the resolved slug host, the static baseline, or a tenant embed origin
SHALL stay fail-closed exactly as today.

**Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.5**

## Round 2 Fix Implementation

### Changes Required (Round 2)

**1. CORS Option B — allow the resolved slug host (Defect 1).**

- **File**: `sam/members/handler/public_app.py`
  - When the route has resolved a slug to a tenant for THAT request, compute the form's own host
    `https://{resolved_slug}.{apex}` where `apex` is read from a per-env config/env var (NO
    hardcode, NO `*.jabaki.nl` wildcard). Union it with the existing `_allowed_origins()` static
    baseline and `_tenant_embed_origins(tenant_id)` inside the `_apply_cors_origin` decision.
  - Keep the existing fail-closed semantics: no `Origin`, a foreign origin, or an empty union → drop
    the header, never `*`. The only widening is the form's OWN slug host, derived from the request's
    resolved slug — so no foreign `*.jabaki.nl` site is admitted.

**2. Surface the full consent notice in the public field config (Defect 2).**

- **File**: `sam/members/domain/_membership_writes_fieldconfig.py` (`get_public_field_config`)
  - Replace the version-only `notice = {"version": ...}` with the FULL notice `{version, text}`
    sourced from `get_consent_notice` (wired via a provider exposing `get_consent_notice`; the
    projection reader `MembersProjectionReader` already satisfies it). Keep empty-is-valid: a tenant
    with no well-formed notice surfaces `None`/absent. No raw record shape crosses the boundary
    (steering 39) — only `{version, text}` is added.

**3. Render the notice TEXT above the consent checkbox (Defect 2).**

- **File**: `sam/members/domain/application_form_render.py` (`_render_consent_control` /
  `build_form_body_html`)
  - When a notice is present, render its localized `text[locale]` (with `nl` fallback),
    HTML-escaped, ABOVE the consent checkbox, with the checkbox still bound to `notice.version`.
    Render the checkbox whenever there is a notice (so consent can be given). Style with the shared
    `LandingPageStyles` classes — no new CSS source.

**4. Map the consent-required and field 422s inline (Defect 3).**

- **File**: `sam/members/domain/application_form_render.py` (the embedded submit script)
  - In the response handler, map a 422 whose synthetic field key is `consent` (code
    `CONSENT_REQUIRED`) to a clear message near the consent control, and each field 422 to an inline
    message near that field. Keep a neutral generic message only for opaque / 5xx responses. No
    internal detail leaked.

NOTE: Round 2 stays within the SAM render/publish step + the public handler's CORS decision + the
public field-config read's notice surfacing. The backend submit/consent gate, the consent stamp, the
in-app SPA form, the Flask landing plane, and the `config#mail` write path are NOT modified.

## Round 2 Testing Strategy

### Round 2 Validation Approach

Same two-phase discipline: first surface counterexamples on the UNFIXED (Round-1-shipped) code
across the three facets, then verify the fix. CORS is asserted against `_apply_cors_origin` /
`handler` over a resolved slug + per-env apex; notice surfacing against `get_public_field_config`
over the REAL `config#mail` (`get_consent_notice`) shape; render + error mapping against the
`build_form_body_html` / `_render_consent_control` output string.

### Round 2 Exploratory Bug Condition Checking

**Goal**: surface counterexamples proving submit still fails on the shipped code.

**Test Cases**:
1. **CORS blocks the form host (CORS)**: with `PUBLIC_FORM_ALLOWED_ORIGINS` set to the single TEST
   canonical host and a tenant with no matching embed origin, a request whose `Origin` is the
   resolved slug host `https://{resolved_slug}.{apex}` gets NO `Access-Control-Allow-Origin` on the
   response (read blocked) — buggy.
2. **Notice text missing (NOTICE_TEXT)**: for a tenant whose `config#mail`
   `get_consent_notice` returns `{version, text}`, `get_public_field_config` returns
   `notice = {"version": ...}` with NO `text` — buggy.
3. **Generic error only (ERROR_CLARITY)**: the rendered submit script contains no mapping of a
   `consent` / `CONSENT_REQUIRED` 422 to a consent-adjacent message nor field-adjacent 422 mapping —
   only the generic catch-all — buggy.

**Expected Counterexamples**:
- The form's own slug host is dropped from CORS → the fetch rejects → generic catch-all.
- `notice` carries only `version`, no `text`.
- All 422s read the same generic message.

### Round 2 Fix Checking

```
FOR ALL input WHERE isBugConditionR2(input) DO
  // CORS          -> _apply_cors_origin echoes Access-Control-Allow-Origin for the resolved slug host
  //                  (https://{resolved_slug}.{apex}) ∪ static baseline ∪ embed origins; fail-closed otherwise
  // NOTICE_TEXT   -> get_public_field_config.notice == {version, text} from get_consent_notice (None when absent),
  //                  renderer shows localized HTML-escaped text above the checkbox (checkbox renders when notice present)
  // ERROR_CLARITY -> submit script maps consent 422 near the consent control and field 422s inline
  ASSERT expectedBehaviorR2(result)
END FOR
```

### Round 2 Preservation Checking

```
FOR ALL input WHERE NOT isBugConditionR2(input) DO
  ASSERT originalSystem(input) = fixedSystem(input)
  // backend submit endpoint + consent gate (_consent_is_affirmative, accepted===true, fail-closed);
  // the consent stamp on the member record (_stamp_application_consent);
  // in-app SPA form; Flask landing plane; config#mail write path (_shape_consent_notice);
  // get_public_field_config single-field-authority (only `text` added beside `version`, no raw shape);
  // CORS fail-closed for any non-slug-host, non-baseline, non-embed origin (never `*`, no wildcard)
END FOR
```

**Testing Approach**: property-based for CORS (generate origins: the resolved slug host, the static
baseline, embed origins, and arbitrary foreign origins incl. other `*.jabaki.nl` hosts — assert
exactly the first three are admitted and every foreign host is fail-closed) and for notice surfacing
(configs with/without a well-formed notice → `{version, text}` vs `None`). Prove the notice round-trip
against the REAL `config#mail` `get_consent_notice` shape (e.g. h-dcn), not a hand-built fixture
(steering 39).

### Round 2 Unit / Property / Integration Tests

- **Unit**: `_apply_cors_origin` admits the resolved slug host and remains fail-closed for a foreign
  `*.jabaki.nl` host; `get_public_field_config` emits `{version, text}` / `None`; the rendered body
  shows the localized escaped notice text above the checkbox; the submit script maps the `consent` /
  `CONSENT_REQUIRED` 422 and field 422s inline.
- **Property-based**: Property 3 (bug condition) over generated origins + notice configs + 422
  shapes; Property 4 (preservation) over non-bug inputs (backend gate, consent stamp, Flask plane,
  write path, single-field-authority, CORS fail-closed for foreign origins).
- **Integration**: paired SAM pytest (`python -m pytest -c sam/pytest.ini <paths> -q`) exercising
  `get_public_field_config` over the real `config#mail`/`get_consent_notice` shape and the
  `public_app` CORS decision with a resolved slug + per-env apex; a TEST end-to-end that the
  published `{slug}.jabaki.nl` submit response is readable, the notice text is shown, consent is
  accepted, and a consent-required 422 surfaces clearly.

---

# Round 3 — production wiring, CORS on error responses, silent errors, publish state

## Round 3 Overview

Round 2 deployed but TEST is unchanged for the applicant. Four root causes, all verified against
code and live TEST:

1. **Wiring (primary).** `app.py::_get_membership_service` builds `MembershipService(...)` with no
   `consent_notice_provider` → empty `StaticConsentNoticeProvider()`. Publish
   (`_dispatch_services.py`), the public field-config GET and submit
   (`public_app._application_service`) all go through it, so none sees the notice. Tests passed
   because they inject a provider directly.
2. **CORS on errors.** In `public_app.py` only the 200 `_PublicResult` and 501 branches pass
   `tenant_id`/`resolved_slug` to `_apply_cors_origin`; the `MemberValidationError` 422 and generic
   500 branches do not.
3. **Silent errors.** The script places a 422 message next to `[data-field="consent"]` / the field
   wrapper only; with no such element the message is dropped.
4. **Publish state.** `application_publish.py` (~line 639) computes `published_version` /
   `published_at` but never persists them to `config#fields`.

## Round 3 Bug Details

```
FUNCTION isBugConditionR3(input)
  INPUT: input of type PublishedFormRound3Interaction
         { facet: WIRING | CORS_ERROR | FALLBACK | PUBLISH_STATE, ... }
  OUTPUT: boolean

  RETURN
    (facet = WIRING AND tenant has config#mail consent_notice
       AND production service (app._get_membership_service()) yields no notice text/version)
    OR (facet = CORS_ERROR AND slug resolved AND response status IN {422, 500}
       AND request_origin = "https://" + resolved_slug + "." + apex
       AND NOT acao_echoed(request_origin))
    OR (facet = FALLBACK AND 422 entry has key with no matching DOM target
       AND NOT message_shown_in_form_level_area)
    OR (facet = PUBLISH_STATE AND publish succeeded
       AND config#fields lacks published_version/published_at)
END FUNCTION
```

Examples: h-dcn published page has no notice/checkbox (WIRING); 422 from
`https://hdcn-aanmelden.jabaki.nl` has no ACAO header (CORS_ERROR); a 422 keyed `consent` on a page
without the consent element shows nothing (FALLBACK); after publishing twice the builder still says
"unpublished changes" and version stays 1 (PUBLISH_STATE).

## Round 3 Hypothesized Root Cause

Confirmed by reading code: (1) missing constructor argument in `_get_membership_service`;
(2) the two except-branches call `_apply_cors_origin(..., request)` without `tenant_id` /
`resolved_slug`, and the resolved slug/tenant are not in scope there; (3) the script has a single
target lookup with no fallback; (4) publish returns the values but has no persistence step.

## Round 3 Correctness Properties

Property 5: Bug Condition (Round 3) - Notice is wired, errors are readable and never silent, publish state persists

_For any_ interaction where isBugConditionR3 holds: the production service built via
`app._get_membership_service()` SHALL expose the tenant's notice `{version, text}` through the
public field config (and the consent stamp SHALL record that version); the 422 and 500 responses
after slug resolution SHALL echo `Access-Control-Allow-Origin` for the form's own slug host exactly
like the 200 branch; a 422 entry with a missing target element SHALL be shown in the form-level
message area; and a successful publish SHALL persist `published_version` / `published_at` on
`config#fields` so a second publish yields version 2.

**Validates: Requirements 8.1, 8.2, 8.3, 8.4**

Property 6: Preservation (Round 3) - Consent gate, stamp shape, CORS fail-closed and other branches unchanged

_For any_ input where isBugConditionR3 does NOT hold, the fixed system SHALL behave as before: the
consent gate (`accepted is True`, fail-closed) and stamp shape, CORS rejection of foreign origins
(incl. foreign `*.jabaki.nl`) on 200/422/500, the 400 abuse-guard and 404 unknown-route branches,
notice-less tenants, and the Round 1–2 behavior.

**Validates: Requirements 9.1, 9.2, 9.3, 9.4**

## Round 3 Fix Implementation

- **`sam/members/handler/app.py`**: add a `_ProjectionConsentNoticeProvider` (same pattern as
  `_ProjectionMailConfigProvider`: fresh `MembersProjectionReader` per call, test-override seam)
  exposing `get_consent_notice` + `get_consent_notice_version`; pass it as
  `consent_notice_provider` in `_get_membership_service`.
- **`sam/members/handler/public_app.py`**: thread the resolved `tenant_id` / `resolved_slug` from
  dispatch to the `MemberValidationError` (422) and generic (500) branches and pass them to
  `_apply_cors_origin`. 400 and 404 stay unchanged. Fail-closed, no `*`, no wildcard.
- **`sam/members/domain/application_form_render.py`**: in the submit script, when a 422 entry's
  target element is missing, append its message to the form-level message area.
- **`sam/members/domain/application_publish.py`** (+ the fields CRUD service): after the artifact
  write succeeds, persist `published_version` / `published_at` with a single-path
  version-conditional Change-Op `update_item` on `config#fields`, mirroring `set_form_slug`
  (steering 39; never a whole-record put). `_next_published_version` then reads the stored value.
- **Frontend**: `ApplicationFormBuilder.tsx` `everPublished` already reads these fields; touch it
  only if a test shows it does not.

## Round 3 Testing Strategy

Exploration (must FAIL on current code), one test module with four facets:

- **WIRING**: build the REAL service via `app._get_membership_service()` with a fake projection
  table holding a real h-dcn `config#mail` row with `consent_notice`; assert
  `get_public_field_config` returns a notice with version + text. Patch only the reader's
  table/override seam, never the service.
- **CORS_422**: drive the real `public_app.handler` POST submit from Origin
  `https://hdcn-aanmelden.jabaki.nl` with a service raising `MemberValidationError`; assert ACAO is
  echoed.
- **FALLBACK**: the rendered script routes an unmatched 422 entry to the form-level message.
- **PUBLISH_STATE**: after publish the stored `config#fields` row has `published_version` /
  `published_at`; a second publish yields version 2.

Preservation (must PASS on current code): consent gate/stamp, foreign-origin rejection on 422/500,
400/404 unchanged, notice-less render unchanged. Fix checking and preservation checking reuse the
same tests after the fix. Checkpoint: `python -m pytest -c sam/pytest.ini sam/tests -q` plus the
frontend builder tests if touched.

---

# Round 4 — slug-marker IAM and per-origin preflight

## Round 4 Overview

Two defects keep the published form unsubmittable on TEST. (1) The public Lambda cannot read slug markers
because of an IAM Condition mis-scoped onto `s3:GetObject`. (2) The preflight is answered by API Gateway's
static SAM `Cors` mock, which can never echo the per-slug host. Fix: split the IAM statement and route
`OPTIONS` to the Lambda, which reuses the existing per-origin decision.

## Round 4 Bug Details

```
FUNCTION isBugConditionR4(input)
  INPUT: input of type {facet, request}
  OUTPUT: boolean

  RETURN (facet = IAM AND policy statement has s3:GetObject AND Condition on s3:prefix)
      OR (facet = PREFLIGHT AND request.method = OPTIONS AND route IN public routes
          AND origin is allowed for the resolved slug AND response.ACAO != origin)
END FUNCTION

FUNCTION expectedBehaviorR4(result)
  RETURN GetObject on _slugs/* granted by an unconditioned statement
     AND ListBucket granted by a separate prefix-conditioned statement
     AND preflight is 204 with ACAO == origin (allowed) or no ACAO (foreign/unresolved), never "*"
END FUNCTION
```

Examples: OPTIONS from `https://hdcn-aanmelden.jabaki.nl` returns ACAO empty (expected: echoed). POST
returns 500 with `AccessDenied s3:GetObject .../_slugs/hdcn-aanmelden` (expected: resolves, 200/422).
OPTIONS from `https://evil.example` must return no ACAO (unchanged).

## Round 4 Hypothesized Root Cause

11. `MembersPublicFunction` Sid `PublicReadSlugMarkers` combines `s3:GetObject` and `s3:ListBucket` under one
    `Condition: StringLike s3:prefix`. IAM applies a Condition to every action in the statement; GetObject
    requests carry no `s3:prefix`, so the condition is false. The template comment claiming "GetObject
    ignores it" is wrong. The authenticated `MembersFunction` uses two statements and works.
12. The preflight is answered by the static `Cors` block on `MembersPublicApi`, so the Lambda's
    `_apply_cors_origin` decision never runs for `OPTIONS`.

## Round 4 Correctness Properties

Property 7: Bug Condition (Round 4) - Slug markers are readable and the preflight is decided per origin

_For any_ input where isBugConditionR4 holds, the fixed template and `public_app.handler` SHALL grant
`s3:GetObject` on `_slugs/*` without a Condition (ListBucket in its own conditioned statement) and SHALL
answer `OPTIONS` on both public routes from the Lambda with 204, the allow-methods/headers/max-age/Vary
headers, and ACAO equal to the request origin when allowed.

**Validates: Requirements 11.1, 11.2, 11.3**

Property 8: Preservation (Round 4) - Authenticated CORS, real-request CORS and other IAM unchanged

_For any_ input where isBugConditionR4 does NOT hold, the fixed code SHALL behave as before: foreign
origins get no ACAO on GET/POST/OPTIONS, the `MembersApi` `Cors` block is unchanged, and the public
function's other IAM statements are the same Sid/Action/Resource set.

**Validates: Requirements 12.1, 12.2, 12.3, 12.4, 12.5**

## Round 4 Fix Implementation

**File**: `sam/members/template.yaml`
1. Split `PublicReadSlugMarkers` into `PublicReadSlugMarkerObjects` (`s3:GetObject` on
   `arn:aws:s3:::${LandingPagesBucket}/_slugs/*`, no Condition) and `PublicListSlugMarkers`
   (`s3:ListBucket` on the bucket ARN, `s3:prefix: _slugs/*`); correct the comment.
2. Add explicit `Method: OPTIONS` events on `MembersPublicFunction` for
   `/public/members/{tenant_slug}/field-config` and `/public/members/{tenant_slug}/applications`; remove the
   `Cors` block from `MembersPublicApi` so SAM stops generating the mock responder.

**File**: `backend`-side `public_app.py` (SAM `handler/public_app.py`)
3. In `handler`, add an OPTIONS branch before the body-based abuse guards: resolve the slug via the same
   marker resolution, call `_apply_cors_origin` with tenant + resolved slug, return 204 with
   `Access-Control-Allow-Methods: GET,POST,OPTIONS`, `Access-Control-Allow-Headers: Content-Type`,
   `Access-Control-Max-Age: 600`, `Vary: Origin`. Unresolved slug or foreign origin: no ACAO. No `*`, no PII
   logged. The stage throttle still applies.

## Round 4 Testing Strategy

Exploration (must FAIL on current code), facets: **IAM** (load the template with the CFN-tag-tolerant loader
already used in `sam/tests/test_public_api_stack_contract.py`; no `MembersPublicFunction` statement combines
`s3:GetObject` with an `s3:prefix` Condition, and `_slugs/*` GetObject is granted unconditioned),
**PREFLIGHT_ROUTE** (OPTIONS events exist for both paths; `MembersPublicApi` has no static `Cors`),
**PREFLIGHT_HANDLER** (real `public_app.handler`, OPTIONS from `https://hdcn-aanmelden.jabaki.nl`, fake slug
store: 204 with ACAO == origin and allow-methods/headers).

Preservation (must PASS now): foreign origin gets no ACAO on GET/POST; `MembersApi` `Cors` unchanged; other
public IAM statements unchanged. Checkpoint: `python -m pytest -c sam/pytest.ini sam/tests -q` and
`sam validate --lint` on the template if available.
