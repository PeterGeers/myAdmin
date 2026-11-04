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

---

# Round 2 — defects found testing the shipped fix in TEST

The Round-1 fix shipped and the published form now renders a working `preventDefault`ed submit
script with client-side `format` checks and a consent checkbox. Exercising that artifact in TEST
surfaced that **submit still fails for the applicant**. Three defects were confirmed this session
against the current code; they are the SAME broken submit flow (the applicant cannot complete a
submission), so they are fixed together as a second round under the same bug condition. The
Round-1 sections (1/2/3) are unchanged; Round 2 CONTINUES the numbering with Current Behavior
(section 4), Expected Behavior (section 5), and Unchanged Behavior (section 6).

The three facets:

- **CORS** — the published per-tenant host `{slug}.jabaki.nl` is NOT in the submit endpoint's CORS
  allow-list, so the browser drops `Access-Control-Allow-Origin` and BLOCKS the read; the fetch
  rejects and the applicant only ever sees the generic "could not be processed" catch-all — the
  real 422 is never readable.
- **NOTICE_TEXT** — the published form serves only the consent notice `version` (no TEXT), so the
  applicant cannot SEE or meaningfully ACCEPT the notice; and because the full notice is not
  served, consent is posted empty and the backend returns a 422 `CONSENT_REQUIRED`.
- **ERROR_CLARITY** — once CORS is fixed the real 422 is readable, but the submit script maps only
  a generic catch-all; the consent-required 422 and per-field 422s are not surfaced clearly near
  their controls.

## Already handled (NO-OP — do not change)

The applicant's consent ACCEPTANCE is ALREADY STORED IN SAM. `create_application`
(`_membership_writes_application.py::_stamp_application_consent`) stamps a server-authoritative
`consent = {version, accepted_at, locale}` onto the member record in DynamoDB — version resolved
server-side via `get_consent_notice_version`, timestamp server-UTC, locale normalized. So "store
consent in SAM" is DONE. Round 2 is ONLY: (1) let the applicant SEE + ACCEPT the notice (serve +
render its TEXT), (2) CORS so the submit response is readable, (3) clear error messages.

## Bug Analysis — Round 2

### Current Behavior (Defect) — Round 2

4.1 WHEN an applicant submits the published form served per-tenant at `https://{slug}.jabaki.nl`
(e.g. `hdcn-aanmelden.jabaki.nl`) which POSTs cross-origin to the separate public API
(`MembersPublicApi`) THEN `public_app.py::_apply_cors_origin` echoes `Access-Control-Allow-Origin`
ONLY when the request `Origin` is an EXACT-STRING member of `_allowed_origins()`
(the `PUBLIC_FORM_ALLOWED_ORIGINS` env — a SINGLE canonical host per env) unioned with the tenant's
`application_embed_origins`; the per-slug published host `{slug}.jabaki.nl` is in NEITHER, so the
browser drops the CORS header and BLOCKS the read, the submit fetch rejects, and the applicant sees
only the generic "Je aanmelding kon niet worden verwerkt" catch-all — the real 422 is never
readable.

4.2 WHEN the published form is served THEN `get_public_field_config`
(`_membership_writes_fieldconfig.py`) returns `notice = {"version": ...}` ONLY (wired to
`_consent_notice_provider.get_consent_notice_version`), so the applicant is shown NO notice TEXT to
read and accept — even though the FULL notice `{version, text}` already exists in SAM on the
`config#mail` row and is readable via `MembersProjectionReader.get_consent_notice(tenant_id)`.

4.3 WHEN the published renderer builds the consent control and only a notice VERSION (no text) is
served THEN the applicant cannot meaningfully give consent, so the posted body carries empty/absent
consent and the backend returns a 422 `CONSENT_REQUIRED` (synthetic field key `consent`) — the
submit is rejected.

4.4 WHEN the backend returns a 422 (consent-required, synthetic field key `consent` / code
`CONSENT_REQUIRED`, or a per-field validation error) THEN the submit script maps it only to the
generic catch-all message, so the applicant is not told clearly that consent is required or which
field is invalid.

### Expected Behavior (Correct) — Round 2

5.1 WHEN an applicant submits the published form from its own per-tenant host
`https://{slug}.jabaki.nl` THEN `public_app.py` SHALL allow the request `Origin` when it equals the
RESOLVED form's OWN host `https://{resolved_slug}.{apex}`, where `resolved_slug` is the slug already
resolved from the `_slugs/{slug}` marker for THAT request and `apex` comes from a per-env
config/env var (NOT hardcoded, NO broad `*.jabaki.nl` wildcard), unioned with the existing static
baseline (`_allowed_origins()`) and the tenant's `application_embed_origins` — so the browser
receives `Access-Control-Allow-Origin` and the submit response is readable; any other origin SHALL
remain fail-closed (the header is dropped, never `*`).

5.2 WHEN the published form is served THEN `get_public_field_config` SHALL surface the FULL consent
notice `{version, text}` (sourced from `get_consent_notice`, wired via a provider exposing
`get_consent_notice`; the projection reader already satisfies it) instead of version-only, keeping
empty-is-valid (`None`/absent notice stays valid).

5.3 WHEN the published renderer builds the consent control and a notice is present THEN it SHALL
render the notice TEXT (localized, HTML-escaped) ABOVE the consent checkbox, with the checkbox bound
to `notice.version`, styled with the shared `LandingPageStyles` classes (no new CSS source); the
checkbox SHALL render whenever there is a notice, so consent can be given.

5.4 WHEN the backend returns a 422 THEN the submit script SHALL map the consent-required 422
(synthetic field key `consent`, code `CONSENT_REQUIRED`) to a clear inline message near the consent
control, and field 422s to inline messages near their respective fields, reserving a neutral generic
message only for genuinely opaque / 5xx cases.

### Unchanged Behavior (Regression Prevention) — Round 2

6.1 WHEN a submit reaches the backend public endpoint THEN the system SHALL CONTINUE TO run its
consent gate unchanged — `_consent_is_affirmative` requires `accepted === true`, fail-closed — and
SHALL NOT be weakened by the CORS or render changes.

6.2 WHEN `create_application` stamps consent THEN the system SHALL CONTINUE TO write the
server-authoritative `consent = {version, accepted_at, locale}` onto the member record exactly as
today (`_stamp_application_consent`) — this is already DONE and is NOT modified.

6.3 WHEN the in-app SPA form, the Flask landing plane, or the `config#mail` write path
(`config_write_service._shape_consent_notice`) runs THEN the system SHALL CONTINUE TO behave exactly
as today — none are modified by Round 2.

6.4 WHEN the published renderer consumes field config THEN `get_public_field_config` SHALL CONTINUE
TO be the single field authority (no raw-shape leak, steering 39); surfacing the full notice SHALL
add only `text` alongside the existing `version` and SHALL NOT expose any raw record shape.

6.5 WHEN the request `Origin` is not the resolved form's own host, not in the static baseline, and
not in the tenant's `application_embed_origins` THEN CORS SHALL CONTINUE TO be fail-closed (drop the
header, never `*`) exactly as today — no foreign `*.jabaki.nl` site is permitted.

---

# Round 3 — production wiring, CORS on error responses, silent errors, publish state

Verified against live TEST: the published `hdcn-aanmelden/index.html` (re-published after the
Round-2 deploy) has NO consent notice text, NO consent checkbox and NO `data-notice-version`, and a
submit still shows the generic "Je aanmelding kon niet worden verwerkt". Round-2 tests passed
because they always injected a consent provider directly. Round 3 continues the numbering:
Current Behavior (7), Expected Behavior (8), Unchanged Behavior (9).

## Bug Analysis — Round 3

### Current Behavior (Defect) — Round 3

7.1 WHEN the production service is built by `sam/members/handler/app.py::_get_membership_service`
THEN `MembershipService(...)` is constructed WITHOUT a `consent_notice_provider`, so it defaults to
an empty `StaticConsentNoticeProvider()`; publish, the public field-config GET and submit all see no
notice, so the page renders no notice text and no checkbox, posts `consent:{}` and gets 422
`CONSENT_REQUIRED`, and the server consent stamp records version `None` (the builder still shows
the version because it reads `mail_config` via the separately wired `_ProjectionMailConfigProvider`).

7.2 WHEN the public submit raises a `MemberValidationError` (422) or an unexpected error (500) after
the slug resolved THEN `public_app.py` applies CORS WITHOUT the resolved slug/tenant (only the 200
and 501 branches pass them), so from `https://{slug}.jabaki.nl` the browser blocks the error body,
the fetch rejects, and the reason never reaches the applicant.

7.3 WHEN the submit script receives a 422 entry whose target element (`[data-field="consent"]` or
the field wrapper) is absent THEN the message has nowhere to go and the applicant sees nothing
specific (a silent error).

7.4 WHEN a form is published THEN `application_publish.py` returns `published_version` /
`published_at` but never persists them onto `config#fields`, so after reload the builder sees
"never published", "Draft has unpublished changes" never clears, and `_next_published_version`
always returns 1.

### Expected Behavior (Correct) — Round 3

8.1 WHEN the production `MembershipService` is built THEN the system SHALL wire a consent-notice
provider backed by the projection reader (`MembersProjectionReader`: `get_consent_notice` +
`get_consent_notice_version`) through a stable per-call indirection like
`_ProjectionMailConfigProvider` (fresh reader per call, test-override seam), so publish renders the
notice text + checkbox and the consent stamp records the real version.

8.2 WHEN the public submit returns 422 or 500 after the slug resolved THEN the system SHALL apply
CORS with the resolved slug and tenant exactly like the 200 branch (the form's OWN slug host ∪
tenant embed origins ∪ static baseline), staying fail-closed, never `*`, no wildcard; the
abuse-guard 400 and unknown-route 404 (no slug resolved) SHALL stay as they are.

8.3 WHEN a 422 entry's target element is missing THEN the submit script SHALL show the message in
the form-level message area, so an error is never silent.

8.4 WHEN a publish succeeds (artifact written) THEN the system SHALL persist `published_version`
and `published_at` onto `config#fields` via a single-path, version-conditional Change-Op
`update_item` (steering 39; mirroring `set_form_slug` in `config_fields_crud_service.py`, NOT a
whole-record put), so the builder clears "unpublished changes" and a second publish yields
version 2.

### Unchanged Behavior (Regression Prevention) — Round 3

9.1 WHEN a submit reaches the consent gate THEN the system SHALL CONTINUE TO require
`accepted is True` (fail-closed) and stamp `consent = {version, accepted_at, locale}` in the same
shape as today.

9.2 WHEN the request `Origin` is not the resolved slug host, the baseline, or a tenant embed
origin (incl. a foreign `*.jabaki.nl` host) THEN CORS SHALL CONTINUE TO be fail-closed on 200, 422
and 500 alike.

9.3 WHEN a tenant has no consent notice THEN the render, field config and submit SHALL CONTINUE TO
behave as today (empty-is-valid).

9.4 WHEN Round 1–2 behavior runs (submit script, format checks, notice text render, inline 422
mapping, slug-host CORS on 200) THEN it SHALL CONTINUE TO pass its existing tests unchanged.
