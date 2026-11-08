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

---

# Round 4 — slug-marker IAM and per-origin preflight

## Bug Analysis — Round 4

Verified on live TEST after the Round 3 deploy and re-publish: the consent text and checkbox render and
the browser posts `consent: {accepted: true, version: "2026-03"}`, yet the applicant still sees "Je
aanmelding kon niet worden verwerkt" and the browser reports a CORS error. Two independent defects remain.

### Current Behavior (Defect) — Round 4

10.1 WHEN the public Lambda resolves a slug marker (`s3:GetObject` on `_slugs/{slug}`) THEN the system
fails with `AccessDenied` and the POST returns HTTP 500 `errors.api.serverError`, because the single
`PublicReadSlugMarkers` IAM statement attaches an `s3:prefix` Condition to `s3:GetObject`, which carries
no such key, so GetObject is never allowed.

10.2 WHEN a browser sends a CORS preflight `OPTIONS` for a public route from the slug host (e.g.
`https://hdcn-aanmelden.jabaki.nl`) THEN the system answers HTTP 200 with an EMPTY
`access-control-allow-origin`, because API Gateway's static `Cors` responder on `MembersPublicApi` answers
instead of the Lambda and can only advertise the first static origin, so the browser rejects the preflight
and never sends the POST.

### Expected Behavior (Correct) — Round 4

11.1 WHEN the public Lambda resolves a slug marker THEN the system SHALL be allowed `s3:GetObject` on
`_slugs/*` by an unconditioned statement, with `s3:ListBucket` in a separate statement on the bucket ARN
conditioned on `s3:prefix` `_slugs/*` (same least privilege).

11.2 WHEN a preflight `OPTIONS` reaches either public route THEN the system SHALL answer it from
`MembersPublicFunction` with 204, `Access-Control-Allow-Methods: GET,POST,OPTIONS`,
`Access-Control-Allow-Headers: Content-Type`, a short `Access-Control-Max-Age` and `Vary: Origin`, and
SHALL set `Access-Control-Allow-Origin` to the request origin only when the per-origin decision
(resolved slug host, static baseline, tenant embed origins) allows it.

11.3 WHEN the slug is unresolved or the origin is foreign THEN the system SHALL omit
`Access-Control-Allow-Origin` on the preflight (fail-closed), never `*` and never a wildcard.

### Unchanged Behavior (Regression Prevention) — Round 4

12.1 WHEN the authenticated `MembersApi` handles requests THEN its CORS configuration SHALL CONTINUE TO be
unchanged.

12.2 WHEN a real GET or POST arrives THEN the per-origin CORS decision (incl. foreign-origin rejection on
200, 422 and 500) SHALL CONTINUE TO be unchanged.

12.3 WHEN the public function's other IAM statements are evaluated THEN they SHALL CONTINUE TO be the same
Sid/Action/Resource set, except for the slug-marker split.

12.4 WHEN a preflight arrives THEN the stage throttle SHALL CONTINUE TO apply, the body-based abuse guards
(honeypot, payload cap) SHALL NOT run on it, and no PII SHALL be logged.

12.5 WHEN Round 1–3 behavior runs THEN it SHALL CONTINUE TO pass its existing tests unchanged.

---

# Round 5 — field-keyed errors, required parity, readable error UX

## Bug Analysis — Round 5

Verified on live TEST after Round 4: a complete, valid submit from `https://hdcn-aanmelden.jabaki.nl`
succeeds. Submitting with EMPTY fields shows only "Controleer de gemarkeerde velden." — no field is marked
and no reason is shown. The 422 carries five errors (`personal.last_name`, `membership.membership_type`,
`overlay.region`, `personal.email`, `personal.birth_date`), while the form marks only `magazine_pref` as
`required`, which the server does not require.

### Current Behavior (Defect) — Round 5

13.1 WHEN the public submit returns 422 THEN `errors[].field` carries physical dotted keys
(`personal.last_name`, `overlay.region`) while the published form names its controls by bare key
(`last_name`, `region`), so no field wrapper is found and each message falls back to the status line.

13.2 WHEN the submit script has mapped the 422 entries THEN it replaces the status text with the generic
"Controleer de gemarkeerde velden.", wiping the fallback messages shown for unmatched entries.

13.3 WHEN the published form is rendered THEN its `required` flags (only `magazine_pref`) differ from the set
the validation engine enforces for the public application (last_name, email, birth_date, membership_type,
region), so the browser lets empty required fields through and blocks on a field the server does not require.

13.4 WHEN an error is shown THEN there is no error styling (no CSS for `.field-error`, `.form-status`,
`.form-status-error`), no `aria-invalid`, no focus on the first error, and the text is the server's English
`detail`.

### Expected Behavior (Correct) — Round 5

14.1 WHEN the public submit returns 422 THEN every `errors[].field` SHALL be the bare field key the published
form uses (resolved from the resolved field view; `consent` stays `consent`), and no dotted key SHALL cross
the public boundary.

14.2 WHEN the script has mapped the 422 entries THEN the status summary SHALL NOT overwrite inline or fallback
messages; fallback entries SHALL be listed in the status area together with the summary.

14.3 WHEN the published form is rendered THEN its `required` flags SHALL equal the set the validation engine
enforces for the public application, from ONE authority (no duplicated rule) — for every field.

14.4 WHEN an error is shown THEN the script SHALL map known codes to Dutch messages (required / mustNotBeBlank
→ "Dit veld is verplicht."; invalid email → "Vul een geldig e-mailadres in."; invalid IBAN → "Vul een geldig
IBAN in."; enum / other → "Ongeldige waarde."), never render the server `detail`, show the message inline,
add an error class (`has-error`) on the field wrapper and `aria-invalid="true"` on the control, scroll/focus
the first error, and skip the client-side check for controls not visible to the user.

14.5 WHEN the page is styled THEN the shared `LandingPageStyles` SHALL define `.field-error`,
`.form-field.has-error` controls, `.form-status`, `.form-status-error` and `.form-status-success` (honouring
the theme's light/dark handling if present), as the single CSS source.

### Unchanged Behavior (Regression Prevention) — Round 5

15.1 WHEN a valid submit succeeds THEN the record written and the success flow SHALL CONTINUE TO be unchanged.

15.2 WHEN consent is missing or given THEN the consent gate and stamp SHALL CONTINUE TO be unchanged.

15.3 WHEN a preflight or real request arrives THEN the Round-4 CORS behavior SHALL CONTINUE TO be unchanged.

15.4 WHEN Flask landing pages render with `LandingPageStyles` THEN they SHALL CONTINUE TO render unchanged
apart from the added rules (additive CSS only).

15.5 WHEN the authenticated `MembersApi` returns a 422 THEN its shape SHALL CONTINUE TO be unchanged (unless
the same mapper is shared safely and its tests stay green).

15.6 WHEN Round 1–4 behavior runs THEN it SHALL CONTINUE TO pass its existing tests unchanged.

---

# Round 6 — the application form is the boss: form-required is the SOLE requiredness rule on the public form

## Bug Analysis — Round 6

Verified against the real `h-dcn` TEST `config#fields` row + the SAM engine + the builder code
this session (root cause re-investigated, not inferred), and RECONCILED with the direction of
`retire-members-status-lifecycle-engine` (`.kiro/specs/Members/01 - members-config-projection-and-
cleanup/Parameter redesign/`): **config is the boss, keep the human responsible, minimise engine
gatekeeping.**

Decision (user, this session): **the application form is the boss.** On the PUBLIC application form,
a field is required **iff the tenant marked it `application_required`** — the single, config-owned
requiredness axis the human controls in the builder. The platform-registry "required floor" is NOT
unioned into the public-form rule. The server keeps ONLY the few non-negotiables it already enforces
on their OWN dedicated paths, independent of requiredness:

- the public-path IDENTITY keys (`personal.email`, `personal.last_name`, `personal.birth_date`,
  `APPLICATION_REQUIRED_IDENTITY_KEYS`) — the server needs them to recognise/dedupe an applicant;
- `membership_type` — its own D21/R11 rule (application-required WHEN exposed; tenant-default
  STAMPED when not exposed) — unchanged;
- server-stamped defaults: `status = "application"` (preserved by the retirement spec) and the other
  `APPLICATION_SERVER_SET_MEMBERSHIP_KEYS` (`member_number`, timestamps) — stripped from a forged
  body and set server-side; an applicant never supplies them.

### Where the floor union actually bites (corrected, proven against the real row + engine)

`effective_application_required` → `_platform_required_by_engine` combines the two axes DIFFERENTLY
by field origin, so the bug reproduces for OVERLAY (VARIABLE) fields, NOT fixed fields:

- **OVERLAY / VARIABLE field** — `_platform_required_by_engine` returns `field.required and
  field.visible` (the RESOLVED flag). So an overlay field with the platform `required:true` but NO
  `application_required` IS demanded of the applicant via the floor union. The real reproduction is
  **`region`** (overlay, resolved `required:true`, no `application_required`): omitting it on a
  public submit yields a `VALIDATION_REQUIRED` 422 for `overlay.region`, though the tenant never
  marked it required on the form. THIS is the Round-6 bug.
- **FIXED field** — `_platform_required_by_engine` reads the PLATFORM REGISTRY (`field_by_key`),
  which does NOT see a tenant OVERRIDE's `required`. So a fixed-field override `required:true` (the
  stored `personal.gender` row) never reaches the public floor — gender is ALREADY optional and
  accepted blank on the public form today. (Earlier drafts named `gender` as the reproduction; that
  was inaccurate — corrected here. Gender stays the illustrative "already correct" case.)

Ground truth from the stored `h-dcn` row (read-only `get-item`, this session) + engine probe:

- `overrides.personal.gender` (FIXED): override `required:true`, NO `application_required` →
  resolved `required=True`, floor=**False** (registry read), effective=False → omitting gender
  SUCCEEDS today. Already sole-rule-correct.
- `region` (OVERLAY): resolved `required:true`, NO `application_required` → floor=**True**,
  effective=True → omitting region → 422 `overlay.region`. The floor union demanding a field the
  tenant did not mark required on the form — the bug.
- `fields.magazine_pref` (overlay): `application_required:true` → required on the form. Correct.
- `overrides.membership.status` (FIXED, server-stamped): never applicant-supplied → not required,
  not offerable.

### Builder already writes the right axis (corrected)

`frontend/src/components/TenantAdmin/MembersConfig/ApplicationFieldModal.tsx` ALREADY persists the
"Verplicht op formulier" toggle as `application_required` (origin-aware `upsertField`), and for a
platform-required field the toggle is FORCED ON + disabled (no-relax). So the earlier claim that the
builder writes the OVERRIDE `required` for fixed fields is INACCURATE and is dropped. Round 6 is
therefore an ENGINE-side fix (drop the floor union from the public rule); the one builder nuance
worth addressing is cosmetic: with the floor union gone, the forced-on+disabled coupling of the
toggle to the platform floor is no longer semantically load-bearing for the PUBLIC form (the public
rule reads only `application_required`), and server-stamped fields should not offer the toggle.

### Current Behavior (Defect) — Round 6

16.1 WHEN the public submit engine computes requiredness for an OVERLAY field that is resolved
platform-`required:true` but NOT `application_required` (e.g. `region`) THEN
`_platform_required_by_engine` unions that platform floor into the public rule and the engine
DEMANDS the field of the applicant (a blank value yields a `VALIDATION_REQUIRED` 422), even though
the tenant never marked it required on the form — automated gatekeeping the human did not author.

16.2 WHEN `get_public_field_config` renders the public schema THEN it derives `required` from the
SAME `effective_application_required`, so a floor-only overlay field (`region`) is RENDERED required
too — the rendered-required set includes fields the tenant did not mark `application_required`,
matching the over-strict engine (render⇄engine agree, but on the wrong rule).

16.3 WHEN the Application Form Builder renders the per-field "Verplicht op formulier" control for a
server-stamped field (`status`, `member_number`, timestamps) THEN it offers a required toggle for a
field the applicant can never supply, so "required on form" for such a field is meaningless yet
shown.

### Expected Behavior (Correct) — Round 6

17.1 WHEN the public submit engine computes requiredness for a field on the application form THEN a
field SHALL be required IFF the tenant marked it `application_required` (the SOLE, config-owned
rule) — the platform-registry/resolved floor SHALL NOT be unioned into the public-form requiredness
for ANY origin (fixed OR overlay). So a blank `region` (floor-only, not `application_required`) SHALL
be ACCEPTED on the public form.

17.2 WHEN a tenant marks ANY offerable field "Verplicht op formulier" THEN the builder SHALL persist
that intent as `application_required` (the single public-form requiredness axis) — which it already
does uniformly for fixed and overlay fields; Round 6 SHALL keep that write behaviour, only removing
the now-unnecessary forced-on+disabled coupling to the platform floor on the PUBLIC-form axis.

17.3 WHEN requiredness is computed for the public form THEN there SHALL be ONE authority shared by
`get_public_field_config` (`_serialize_public_field`) and the submit validator
(`_validate_application_required`) — `effective_application_required` — now defined as
`application_required` plus the fixed identity-key set (17.4), honouring `show_when` as today; so the
rendered `required`, the client check and the server enforcement are the SAME set for every field
(Round-5 parity preserved over the simplified rule).

17.4 WHEN the public-path identity keys (`personal.email`, `personal.last_name`,
`personal.birth_date`) are validated THEN they SHALL CONTINUE TO be required on the public path
regardless of tenant config — the ONLY requiredness the server adds beyond the tenant's
`application_required`, because the server needs them to recognise/deduplicate an applicant.

17.5 WHEN a field is server-stamped (`status`, `member_number`, `created_at`, `updated_at` — the
`APPLICATION_SERVER_SET_MEMBERSHIP_KEYS`) THEN `effective_application_required` SHALL return false
for it, the published form SHALL NOT render it required, and the Application Form Builder SHALL NOT
offer a "Verplicht op formulier" toggle for it — while the server SHALL CONTINUE to stamp it
authoritatively (`status = "application"` default preserved).

17.6 WHEN `membership_type` requiredness is evaluated THEN it SHALL CONTINUE TO be governed by its
OWN D21/R11 rule (application-required WHEN exposed on the form; tenant-default STAMPED when not
exposed) — Round 6 SHALL NOT fold `membership_type` into the generic floor union it removes.

### Unchanged Behavior (Regression Prevention) — Round 6

18.1 WHEN the authenticated staff write path (`MembersApi` create/edit, `_validate_member_record`
over the fixed-field registry + overlay `required`) runs THEN the members-table platform `required`
floor SHALL CONTINUE TO be enforced EXACTLY as today — Round 6 changes ONLY the PUBLIC application
form's requiredness rule, never the staff/members-table enforcement. A platform-required field a
staff user leaves blank SHALL still be rejected.

18.2 WHEN a field is not `application_required` and is not an identity key THEN a blank value on the
PUBLIC form SHALL be accepted — including a floor-only OVERLAY field (`region`) and a floor-only
FIXED field (`gender`, already accepted today).

18.3 WHEN `membership_type` is exposed/not-exposed on the form THEN its application-required-when-
exposed check and its tenant-default stamp when not exposed SHALL CONTINUE TO behave exactly as today
(`_apply_application_membership_type`).

18.4 WHEN the server stamps a server-set field THEN `status` / `member_number` / timestamps SHALL
CONTINUE TO be stripped from a forged body and set server-side exactly as today — Round 6 only stops
them being OFFERED/rendered as applicant-required.

18.5 WHEN the resolver resolves a field THEN `required` (members-table/staff floor) and
`application_required` (public-form flag) SHALL CONTINUE TO be two independent axes on the resolved
field (`TestPlatformRequiredAndApplicationRequiredAreIndependentAxes`) — Round 6 simply stops the
PUBLIC engine from consulting the floor axis; the data model keeping them distinct is unchanged.

18.6 WHEN Round 1–5 behavior runs (submit script, format checks, notice text, inline 422 mapping,
bare field keys, slug-host CORS/preflight, error CSS, render⇄engine parity) THEN it SHALL CONTINUE
TO pass its existing tests, with the Round-5 parity tests updated IN THE SAME CHANGE to the
simplified requiredness rule where they asserted the platform-floor union (change-with-tests).

18.7 WHEN this change lands THEN it SHALL be reconciled with the `retire-members-status-lifecycle-
engine` direction (config is the boss, minimal engine gatekeeping) — no docstring/spec left
asserting a platform-floor union on the public form (incl. Round-5 design note #15 and the
`_platform_required_by_engine` docstring).
