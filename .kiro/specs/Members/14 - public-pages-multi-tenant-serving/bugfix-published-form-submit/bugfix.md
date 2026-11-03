# Bugfix Requirements Document

**Bugfix — the PUBLISHED static application form renders but cannot be submitted by an applicant**

Parent spec: `.kiro/specs/Members/14 - public-pages-multi-tenant-serving` (R5.1, R5.3, R5.5, R7.1, R10).

## Introduction

Spec 14 makes each SAM page producer publish a slug-addressed static artifact — for the
application form, a `{slug}/index.html` page served from the shared public-pages bucket at
`{slug}.jabaki.nl/apply` (e.g. `hdcn-aanmelden.jabaki.nl/apply`). The published page IS rendered
and IS styled (it builds its CSS from the shared `LandingPageStyles` source and lays out the
authored `<fieldset>` sections, labels, and required markers), but an applicant **cannot actually
use it** — submitting the form fails, and the form does not honor the tenant's field-format
definitions.

The two defects were confirmed this session against the current code and TEST; they are fixed
together as ONE bug condition because they are the same broken artifact: the published page is
emitted as a bare, no-JavaScript form that neither posts to the backend nor applies the published
field checks.

- **Submit 404s.** The published body (built by
  `sam/members/domain/application_form_render.py` → `build_form_body_html`) renders a bare
  `<form class="application-form" method="post">` with a `<button type="submit">`, NO JavaScript
  and NO `action`. On submit the browser does a NATIVE form POST (form-urlencoded) to the page's
  own URL (`/apply`) — e.g. `https://hdcn-aanmelden.jabaki.nl/apply` → **404 Not Found** (the
  S3/CloudFront static site has no POST handler). The form never reaches the backend. The backend
  public submit endpoint already exists and is correct — the published artifact just never calls
  it.
- **Field definition not honored on the published page.** The field `format` validator token
  (`{checker, params}` — e.g. `IBAN`, `EMAIL`, from the `field_formats` registry) IS emitted in
  the public field config (`_serialize_public_field` / `get_public_field_config` sets
  `payload["format"]`), but `_render_field` in `application_form_render.py` IGNORES it — so the
  published page has NO client-side IBAN/email format check. (The `required` flag and the
  email/tel/number/date input types ARE already rendered.)

Impact: every published SAM application form is a dead end for applicants — the page looks
complete but any submit is lost to a 404, and format-constrained fields (bank account, email)
get no client-side feedback. The capability spec 14 R5.5 promised (a public applicant submits the
published form to the backend) is absent from the published artifact.

**Scope boundary (inherited from spec 14 Scope decision):** the Flask landing module is NOT
touched. The backend public submit endpoint and its tenant-from-marker resolution, CORS
allow-list, honeypot, and payload cap are already correct and are NOT modified. The fix is the
published FRONTEND artifact (its render) plus the publish-time API-base plumbing ONLY.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN an applicant submits the published static application form at `{slug}.jabaki.nl/apply`
THEN the browser performs a NATIVE form POST (form-urlencoded) to the page's own `/apply` URL,
which the static S3/CloudFront site has no handler for, so the submit returns **404 Not Found**
and the application is lost — the backend submit endpoint is never called.

1.2 WHEN `build_form_body_html` composes the published form body THEN it emits a bare
`<form class="application-form" method="post">` with NO `action`, NO embedded JavaScript, and NO
`preventDefault`, so there is no code path that serializes the fields to the backend JSON shape
or that sends them to `POST /public/members/{slug}/applications`.

1.3 WHEN a field carries a `format` validator token (`{checker, params}`, e.g. `IBAN` or `EMAIL`)
that the public field config emits under `payload["format"]` THEN `_render_field` IGNORES that
token, so the published page performs NO client-side IBAN/email format validation.

1.4 WHEN the backend requires a consent record and a locale on submit THEN the published page
renders NEITHER a consent control bound to the notice version nor a locale selector (the config
exposes `notice.version` and `locales`, but the renderer does not surface them), so even a
correctly-posted body would be hard-rejected by the backend for missing consent.

1.5 WHEN the published static page needs to know the public API base URL to submit THEN there is
no publish-time mechanism to bake that base into the artifact (the static page cannot read
`VITE_*`), so the page has no backend address to call even if it tried.

### Expected Behavior (Correct)

2.1 WHEN an applicant submits the published static application form THEN the page SHALL call
`preventDefault` on the native submit and instead send a JSON request to
`POST /public/members/{slug}/applications`, with the field values under `fields` (an object),
plus `locale` (or `lang`), `consent` (an object), an optional `session_key`, and the honeypot
`website` field left empty — the native form POST SHALL never fire.

2.2 WHEN the backend responds to the submit THEN the page SHALL handle each outcome: on success
show a success state; on a 422 map the per-field errors inline next to their fields; and on the
non-probeable 404 / neutral states show the appropriate neutral message — without exposing
internal detail.

2.3 WHEN a field carries a `format` validator token THEN the published page SHALL run the matching
client-side check (IBAN and EMAIL, mirroring the `field_formats` registry semantics) in addition
to the already-rendered `required` check, with the SERVER 422 as the authoritative backstop
(the client checks are a convenience; the server remains authoritative).

2.4 WHEN the published page is rendered THEN it SHALL render a consent control (a checkbox bound
to the config's notice version) and a locale selector (from the config's `locales`), because the
backend REQUIRES a consent record and a locale on submit.

2.5 WHEN the published page is rendered THEN its new elements (consent, inline errors, success
state, format feedback) SHALL reuse the existing `LandingPageStyles` CSS source and the existing
`<fieldset>`/section/label structure and classes, so they match the application form's look and
feel and are not visually bolted on.

2.6 WHEN the artifact is published THEN the publish step SHALL bake the public API base URL into
the static page, resolved from a publish-time environment variable with NO silent default (the
fail-fast resource-resolution convention), so the baked-in base is correct per environment and a
missing value fails loudly rather than targeting the wrong backend.

2.7 WHEN the published page renders a DATE field or a DROPDOWN (enum/`options`) field THEN it
SHALL constrain and check them for correctness as follows: a dropdown SHALL be a `<select>`
offering ONLY the field's allowed `options` from the public field config (so an invalid value
cannot be chosen in the UI), and a date field SHALL use the native `type="date"` control (date
picker + basic date-validity). The SERVER remains authoritative: `create_application` already
re-validates the field TYPE (incl. date parsing) and ENUM MEMBERSHIP (rejecting a value not in
the allowed `options`, including the `membership_type` catalog reference and role-restricted
options) and returns a 422. Per 2.2 the page SHALL map any such server 422 — a bad date or an
out-of-set dropdown value a forged/stale client slips through — to an inline per-field error, so
date and enum correctness is always enforced (client convenience + authoritative server backstop),
never silently stored. (Business rules beyond type/membership — e.g. "date must be in the past" —
are NOT in scope here unless carried by the field definition's `format`/`validate_member` hook.)

### Unchanged Behavior (Regression Prevention)

3.1 WHEN the in-app SPA application form runs
(`frontend/src/components/public/application/ApplicationFormPage.tsx` with Formik +
`submitApplication`) THEN the system SHALL CONTINUE TO validate, submit, and map 422s exactly as
today — the published static form is a distinct public, no-login path and this fix SHALL NOT alter
the in-app form. (The h-dcn single-tenant in-app form requires login; the published form is the
public, no-login path — they stay distinct.)

3.2 WHEN a submit reaches the backend public endpoint
(`POST /public/members/{slug}/applications`, `sam/members/handler/public_app.py`) THEN the system
SHALL CONTINUE TO resolve the tenant from the `_slugs/{slug}` marker (never from the body), strip
any forged body `tenant_id`, enforce the CORS allow-list, the honeypot, and the payload-size cap,
re-validate required + format server-side, and return 422 / non-probeable 404 as today — the
backend is already correct and is NOT modified by this fix.

3.3 WHEN any Flask landing-plane operation runs THEN the system SHALL CONTINUE TO behave exactly
as before — the landing module is not modified by this fix (spec 14 Scope decision).

3.4 WHEN the renderer builds the published page THEN it SHALL CONTINUE TO consume
`get_public_field_config` (the single filter authority / whitelist) as its only field source and
SHALL NOT re-derive a field list or let any raw record shape cross the boundary (steering 39) —
the already-rendered `required` flag, input types, group/section ordering, labels, and the shared
`LandingPageStyles` CSS SHALL be preserved.
