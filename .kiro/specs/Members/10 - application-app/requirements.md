# Requirements Document

## Member Application Form (public applicant intake) — Requirements

- Status: **Draft** (requirements phase — review before design)
- Analysis inputs: `design-options.md` (this folder). This document is the formal
  **Requirements** phase that follows that analysis.
- Spec home: `Members/application-app/` is a **module feature spec**. The SAM-plane
  capabilities it relies on (public-intake edge, tenancy, SNS/SES, projection reads)
  live under `Common/Serverless-applications/` and are governed by steering 35 — this
  spec **consumes and references** them, it does not redefine them.
- Governing steering: `20-platform-architecture`, `21-identity`, `22-authentication`,
  `35-sam-module-architecture-sam`, `34-backend-testing`, `40-spec-workflow`,
  `30-backend-api-flask-mysql` (Flask-plane: the verified-sender onboarding dependency, AND
  authoring + projection of the per-field application field config — R4c/D18).

## Introduction

Today a member record is only ever created by an authenticated staff member through the
gated SAM members edge (`POST /members`, capability `members:write`, tenant derived from
the verified token + `X-Tenant`). A prospective member has no way to apply themselves.

This feature adds a **public, unauthenticated application form** a would-be member can
fill in without signing in and without any Pool A account. On submit it lands a
member-side record for the **correct tenant** with status **applicant** (`application`),
and notifies that tenant's `Members_CRUD` users by email so they can review and approve.

Two hard constraints shape everything below and are drawn directly from the analysis:

1. **No Flask⇄SAM boundary mix.** The member record is a DynamoDB item owned by the SAM
   plane (`sam/members/`, data account `nonprofit-deploy`). The whole flow — write,
   recipient resolution, and email send — stays in the SAM plane. Flask must not write
   the record, and SAM must not call Flask to do its work. Recipients come from the
   governance projection SAM already reads; email goes out via SES called directly from
   SAM.
2. **The form is a projection of the tenant's resolved field config, never a
   hand-coded field list.** Fields are derived from the `config#fields` projection row
   through `FieldResolver`, and **which fields appear on the public form is an explicit
   per-field selection** marked on the field config — NOT a blanket "exclude the whole
   membership group". The default is that `membership`-admin back-office fields are
   off the form, but a tenant may select specific membership fields (e.g. a
   membership-type choice) to include. The applicant form, the stored submission, and
   the member record all follow the tenant's config with zero per-tenant code — the same
   field model the member overview already uses, filtered by an application-visibility
   selection.

## Terminology / Glossary

- **Applicant** — a non-member who submits the public form. Represented by a member record
  in `status = application` ("Aanmelding"), the default create-time status value (Option 1, D1).
  (`retire-members-status-lifecycle-engine`: `status` is an OPEN tenant-driven enum, not a
  closed `MembershipStatus` set; `application` is a plain default literal stamped on create,
  not a lifecycle "initial state".)
- **Public intake** — an unauthenticated write path on the SAM edge. The plane's **first**
  route not behind the Cognito authorizer; a deliberate, fenced exception to the
  "deny without a verified token" invariant.
- **Tenant carrier** — what conveys the target tenant on a public (token-less) request.
  Decided: a **path slug** (D3), resolved against an **allow-list** (`tenant-directory`),
  never trusted raw.
- **Resolved field config** — the per-tenant field set produced by merging the tenant
  overlay (`config#fields` projection row, via `projection_config_reader.py`) over the
  platform fixed base with `FieldResolver`. Each `ResolvedField` carries
  `functional_group`, `type`, `required`, `label{nl,en}`, `choices`/`options`,
  `show_when`, `visible`, `order`, `read_only`, `group`, and (new) `format`.
- **`FieldFormat`** — a declarative, named validator attached to a field
  (`{checker, params}`), generalizing the existing `MemberNumberFormat` precedent.
- **`role-recipients`** — a SAM read that returns the emails for `(tenant_id, role)` from
  the projection's `role#<email>#<role>` rows. New thin reader over the shared projection
  schema.
- **`Members_CRUD`** — the global Cognito group whose members review applications; its
  per-tenant membership is projected as `role#<email>#Members_CRUD` rows.
- **Verify-before-trust** — authority (and here, tenant) derives only from a verified
  source. A public carrier may *select* among allow-listed tenants, never *grant* one.

## Guiding principles (settled — requirements enforce them)

- **Server is authoritative; the public form is trusted for nothing.** The endpoint
  forces `status = application` and strips any client-supplied `tenant_id` / `member_id`
  / `status` (mirroring `_sanitize_write_payload` + the authoritative-tenant stamp in
  `create_member`).
- **Tenant resolves from an allow-list, never a free client value** (verify-before-trust;
  Property 2 — never land in an arbitrary partition).
- **Fields are derived from the resolved field config** and shown on the form by an
  **explicit per-field application-visibility selection**, grouped by `functional_group`.
  Back-office `membership`-admin fields default off; specific membership fields can be
  selected in. No hand-maintained field list — the selection is config, not code.
- **Reuse the existing create invariants and validation chain**; the public path adds
  only the two critical checks (required+valid email, IBAN mod-97 conditional on incasso)
  on top, via a declarative field-validator seam, not bespoke special-cases.
- **The unauthenticated write is abuse-hardened SAM-side** (API Gateway throttle + honeypot +
  payload cap + CORS; WAF deferred, D17). Non-negotiable for a public POST.
- **The notification never blocks the write.** A slow/failed SES send must not fail the
  applicant's submission; the record is the source of truth, the email is best-effort.
- **Build members-local with clean, module-agnostic seams; defer the shared extraction**
  (rule of three, steering 35). No `sam/shared/<capability>/` is created now; the second
  consumer (event pre-application) triggers extraction. Each module keeps its own
  repository + table (share CODE, never the STORE).

## Settled decisions (resolving the analysis open questions)

These were open in `design-options.md` and are now decided; the requirements below are
written to them (design still fixes the exact mechanisms noted):

- **D1 — Intake shape: Option 1 (immediate `application` row).** The public write lands a
  member-side record directly in the member table with `status = application`. Options 2/3
  are not built; this spec is written for Option 1 throughout. (Resolves analysis OQ1.)
- **D2 — `membership_type` on application: an application-selectable field with a choice
  SUBSET.** `membership_type` is handled through the normal field-definition mechanism: a
  tenant may mark it application-selectable (R4.4) and, when it is, present the applicant a
  **subset of the field's enum choices** (the public-safe membership types), not the full
  staff-facing set (R11, R4a). This replaces the earlier "relax required / stamp a default"
  framing as the primary mechanism. (Resolves analysis OQ3.)
- **D3 — Public tenant carrier: PATH SLUG.** The tenant is carried as a path slug (e.g.
  `POST /public/members/{tenant_slug}/applications`), resolved against the
  `tenant-directory` allow-list. (Resolves analysis OQ4.)
- **D4 — Sender-config source: reuse the members mail `config#mail` projection + resolver.**
  The notification reads the tenant's verified sender from the SAME `config#mail` row and
  `MailSenderResolver` the members mail worker already uses (`mail_domain` /
  `mail_local_part` → `From = <local|noreply>@<domain>`, gated by `mail_certified`) — the
  "similar to email verification in members/pivot" pattern. No new sender-config store.
  (Resolves analysis OQ5 SAM-consumption part.)
- **D5 — Notification delivery: OFFLOADED.** The send is offloaded (SQS / DynamoDB-stream
  notifier), reusing the members mail-send queue/worker pattern, so a slow SES call never
  sits in the applicant's request path. (Resolves analysis OQ6.)
- **D6 — Per-field application-visibility selection + enum-subset** is an extension of the
  field-definition model (R4, R4a), not a separate hand-maintained list.
- **D7 — Shared-services placement is DEFERRED (not forced now).** Built members-local with
  module-agnostic seams (rule of three). The cross-plane question — "shared between SAM
  modules in `sam/shared`; between frontend apps in the frontend; in Flask in Flask; and
  anything shared *across* planes?" — is explicitly left open for a proper solution when a
  genuine cross-plane sharer appears; v1 introduces no cross-plane shared home. (Resolves
  analysis OQ7 by deferring it deliberately — see Open Questions #1.)
- **D8 — Reply-To with NO logged-in user: the all-scope `Members_CRUD` SET; `TenantAdmin` only
  as fallback (simplified per user, D24).** In the normal members-mail flow the From is the
  tenant sender (`noreply@<domain>`) and the Reply-To is the triggering user's email. A public
  applicant has NO logged-in user. Decision: the From is unchanged (the tenant's verified sender,
  D4); the **Reply-To is the SAME all-scope `Members_CRUD` recipient set** the staff notification
  goes to (D9) — i.e. every members admin with an all-scope grant, as a multi-address Reply-To, so
  a reply reaches the same admins who were notified. There is **NO configured Reply-To param** and
  **NO single-pick deterministic tiebreak** (both dropped — the earlier three-layer model is
  replaced by "Reply-To = recipient set"). **Fallback:** WHEN there is NO all-scope `Members_CRUD`,
  Reply-To is the `TenantAdmin` set (the same fallback as recipients, D9). Resolvable in-plane from
  the projection the notification already reads. (Revised per user — resolves OQ7 Reply-To half.)
- **D9 — Staff recipients = `Members_CRUD` ∩ ALL-SCOPE, fallback the member module's
  `TenantAdmin`.** Stated in **tenant-agnostic scope terms** — `region` is merely h-dcn's
  specific scope dimension; the platform concept is a tenant's configured **scope dimension**.
  A new applicant is a tenant-wide event, so the staff notification SHALL go to the
  `Members_CRUD` users with an **all-scope grant** — those whose
  `scopegrant#<email>#<dimension>` row is `["*"]` for the tenant's governing scope dimension
  (h-dcn's instance: `region = ["*"]`, the `Regio_All` label) — NOT scope-limited
  `Members_CRUD` users (who administer only their own scope value). WHEN no all-scope user
  exists the fallback is the **member module's tenant administrator** — the `TenantAdmin`
  role holders from `role#<email>#TenantAdmin` (the `members:admin` capability holder). A
  tenant with NO scope dimension configured has all its `Members_CRUD` as effectively
  all-scope, so they are all notified. (New.)
- **D9a — Optional scope-matched copy (config-gated), confirmed against h-dcn (F2).** The D9
  all-scope default is h-dcn's current, confirmed-working workflow — NOT a guess. As an
  OPTIONAL, tenant-config-gated addition, a copy MAY ALSO go to the `Members_CRUD` users
  **scoped to the scope value the applicant selected** — matched on the same
  `scopegrant#<email>#<dimension>` rows by the applicant's value instead of `["*"]`, where
  `<dimension>` is the tenant's governing scope dimension (h-dcn: `region`) — ADDING to,
  never replacing, the all-scope recipients. This loops in the scope-local reviewer who would
  action the applicant without overloading one inbox, for scope-structured tenants that want
  it. Tenant-agnostic: a tenant whose scope dimension is "chapter" or "department" gets the
  same behaviour on its own dimension. (New — resolves review finding F2.)
- **D10 — The applicant receives a confirmation COPY.** On a successful submission the
  applicant SHALL receive a confirmation email at their own submitted address, containing a
  copy of what they submitted. This is a SECOND notification (different recipient + template
  from the staff one), sent from the same tenant verified sender, best-effort and offloaded
  like the staff send. (New — requested by the user.)
- **D11 — De-duplication: in-session de-dup + a FLAG-ONLY email duplicate signal; hard
  uniqueness enforcement stays a dependency.** A public form is double-submitted (impatient
  click, retry), so the fresh-`uuid4` default (R3.3) must not create duplicates. This spec
  builds: (a) a **client-carried session/idempotency key** (R3a.1–R3a.4) so a re-send within
  the same fill-in session UPDATES that session's record (analogue of the mail worker's
  `mailsent#<job_id>` conditional marker), a double-click resolving to one record via a
  conditional write; and (b) a **flag-only possible-duplicate signal** (R3a.5–R3a.8, D25) — on
  create, if the submitted **name + date of birth** matches an existing member the new
  `application` is **flagged for staff review** (shown on R8b), but is STILL created: detection
  never blocks, the applicant-facing 202 is unchanged (no enumeration oracle), and the match
  signal is **name + DOB** (both required, R6.1a — a stronger "same person" key than a reused
  email; NOT email), looked up via a **GSI** on `(tenant_id, name+dob)` (D25). **Hard, write-time
  uniqueness is NOT enforced here** (user decision): a true members-table uniqueness constraint
  must bind the AUTHENTICATED staff paths too and reintroduce the guard that spec s5k removed
  (with backfilled duplicates to reconcile) — a members-core dependency, recorded as Open
  Question #8, not built in v1 of this form. Required applicant identity = **email + name + date
  of birth** (R6.1/R6.1a). (Revised per user: flag-only on name+DOB via GSI, no hard block.)
- **D12 — Locale is an applicant form selection, default `nl`.** The applicant's locale
  comes from a **selection field on the form** (`nl`/`en`), defaulting to `nl` and falling
  back to `nl` when absent/invalid (R6b). It drives applicant-facing copy (form + the
  applicant's confirmation email) and is persisted on the record. The STAFF email's language
  is NOT the applicant's choice — it uses the recipient/tenant locale. This makes every
  "locale honoured" clause testable. (New — requested by the user.)
- **D13 — Required-ness is a per-field application-required boolean; ALL required fields are
  server-enforced.** "All asked fields must be provided" is NOT blanket — some shown fields
  are legitimately empty (`tussenvoegsel`, address line 2). So required-ness is a **per-field
  application-required flag** on the same application field config as visibility/subset
  (R4b), and the server enforces presence for EVERY required field (platform-`required` or
  application-required), not just email/IBAN (R6.6) — closing the C4 ambiguity. The flag can
  tighten an optional field to required for the form but can NEVER relax a platform-required
  field; email/name/DOB are always required. (New — requested by the user.)
- **D14 — Accessibility (WCAG 2.2 AA) via Yup + Chakra + the server error framework.** The
  public form is accessibility-critical (public, widest audience). Rather than new machinery,
  it REUSES what the frontend already has: **Yup + Formik** for client validation (schema
  generated from the public field-config, not hand-written), **Chakra `FormControl`** for the
  accessible field wiring (aria-invalid / describedby / label), and the **server `errors`
  array** mapped back into Formik by dotted `field` key so the server stays authoritative and
  both error sources render identically (R10a). Net-new is only: config-generated Yup, the
  client/server merge, an ARIA live-region error summary, the keyboard/contrast/zoom/`lang`
  basics, and an axe-in-CI gate (automated ≠ full conformance; manual AT testing still
  required). (New — resolves review finding C6.)
- **D15 — A certified sender is a PRECONDITION: no sender → the form refuses to start.**
  Because notifications go out as the tenant's own certified sender (D4) and a public
  applicant can't be left un-notified silently, a tenant with no usable certified sender
  (`mail_certified` + `mail_domain`) is simply **not accepting applications yet**. The public
  field-config read gates form load (R5.4) and the submit endpoint re-checks (R9.4), both
  refusing with a proper neutral "applications not available for this tenant yet" message —
  the record is NOT created. This REPLACES the earlier accept-then-skip-and-log stance and
  resolves review finding F1: an applicant never sees a form whose notifications would go
  nowhere. (New — requested by the user; F1.)
- **D16 — Build the `FieldFormat` validator registry NOW (R7), as a recorded exception to the
  rule of three (resolves V1).** The v1 need is only EMAIL (a standard regex — reuse the
  existing `emailValidationUtils` / `_validate_email`) and IBAN (a ~10-line mod-97 checksum,
  which a regex CANNOT do). The full config-driven registry is built up front NOT for these
  two alone but because the **events/webshop roadmap is firm** and carries the identical
  "attach a checker to a field" need — so the registry is built anyway and the members
  application is its first caller. This deliberately differs from D7's rule-of-three default:
  D7 defers an abstraction while the second consumer is only *possible*; D16 invests early
  because the second/third consumers are *committed*. If that roadmap were speculative, the
  correct call would be two targeted validators with the registry deferred (rejected Option
  A). (User decision — V1 Option B.)
- **D17 — No WAF in v1; API Gateway throttling + honeypot + payload cap + CORS only (resolves
  V3).** At a member-application form's low, human-paced volume, those controls are
  proportionate, and a WAF (rate-based rule / CAPTCHA) is the one material recurring cost.
  It is deliberately NOT provisioned now (R10.4) and recorded as an easy add-on at the
  public-intake edge IF real abuse appears. (User decision — V3.)
- **D18 — The Flask plane authors the per-field application settings and projects them to
  `config#fields`; SAM only reads.** The new per-field application attributes
  (application-visibility, enum subset, application-required, `FieldFormat` validator) are
  authored in the EXISTING Flask tenant-admin field config (`members.*` / `field_overlay`)
  and carried into the `config#fields` projection row by extending the existing Flask builder
  (`build_config_fields_row`) + `projection_sync`, validated fail-loud at Save
  (`projection_validator` / `members_config_validation`) — NO new projection row, NO SAM-side
  authoring (R4c). This is the authoring/projection counterpart to the SAM read side
  (R4/R4a/R4b/R5) and keeps the boundary rule intact: Flask authors + projects, SAM consumes.
  (New — requested by the user; closes the authoring/projection gap.)

## Requirements

### R1 — Public, unauthenticated application submission

**User story:** As a prospective member, I want to fill in and submit an application form
without signing in, so that I can apply to join a tenant without needing an account.

#### Acceptance criteria
1. The system SHALL expose a **public** submission endpoint that is NOT behind the SAM
   Cognito authorizer and requires NO bearer token and NO Pool A account.
2. WHEN a well-formed application is submitted for an allow-listed tenant THEN the system
   SHALL accept it and create a member record with `status = application` for that tenant
   (Option 1, D1), and respond with a success result.
3. The public endpoint SHALL be the ONLY unauthenticated write on the SAM edge, declared
   as an explicit, documented exception to the "deny without a verified token" invariant.
4. The response SHALL NOT leak internal identifiers beyond what the applicant needs
   (e.g. a confirmation acknowledgement), and SHALL NOT echo back staff-only fields.

### R1a — HTTP response & error contract (reuse the existing SAM edge envelope)

**User story:** As the public form app, I want a documented, consistent response and error
contract, so that I can render success, field errors, and failures without guessing the
shape.

#### Acceptance criteria
1. Both public endpoints (the submission POST and the public field-config GET) SHALL use
   the **existing SAM members response envelope** — `_http._response` for success and
   `_http._error` for failures — NOT a new shape. Every response (including errors) SHALL
   carry the standard CORS headers and a well-formed JSON body, and SHALL serialize
   `Decimal` via `_json_default`.
2. A successful submission SHALL return **202 Accepted** (the member record is written
   synchronously; the two notifications are offloaded, D5), with a minimal body: a success
   flag and a non-sensitive acknowledgement — NO `member_id`, no tenant internals, no
   staff-only fields (R1.4).
3. A validation failure SHALL return **422** with the body carrying the per-field errors as
   the RFC 9457 `errors` array (`_field_errors_array` over the `MemberValidationError` map,
   R6.5) and `code = errors.validation.failed` — the same shape the authenticated create
   path returns, so the form reuses one error renderer.
4. A missing / unknown / forged **tenant slug** (R2.3) SHALL return **404**
   (`code = errors.api.notFound`), deliberately indistinguishable from "no such endpoint"
   so the allow-list cannot be probed for valid tenant slugs. A malformed / oversized /
   honeypot-tripped body (R10.3) SHALL return **400**.
5. The public field-config read (R5) SHALL return **200** with the filtered field set on
   success and the same **404** tenant-not-found behaviour as R1a.4; it SHALL NOT return
   staff-only fields or other tenants' config even on error.
6. The applicant-facing response SHALL NOT vary by whether the tenant has a certified
   sender (R9.4) or recipients (R8.5): those are best-effort side effects AFTER the 202 and
   SHALL NEVER change the applicant-facing status code.

### R2 — Tenant resolves from an allow-list (verify-before-trust)

**User story:** As the platform, I want the target tenant to come from a verified
allow-list and never from a raw client value, so that a forged carrier can never land a
record in another tenant's partition.

#### Acceptance criteria
1. The request SHALL carry the tenant as a **path slug** (D3) — e.g.
   `POST /public/members/{tenant_slug}/applications`.
2. WHEN the slug matches an entry in the `tenant-directory` allow-list THEN the system
   SHALL resolve it to the canonical `tenant_id` and proceed scoped to that tenant.
3. WHEN the carrier value does NOT match an allow-listed tenant THEN the system SHALL
   reject the submission and SHALL NOT write to any tenant partition.
4. The resolved `tenant_id` SHALL be the ONLY source of the record's tenant; any
   `tenant_id` present in the request body SHALL be stripped and ignored.
5. The repository tenant-PK invariant (Property 1 structural isolation) SHALL apply to the
   public path exactly as to the authenticated path, covered by the same tenant-invariant
   test.

### R3 — Server is authoritative; forced status and sanitized payload

**User story:** As the platform, I want the server to force the applicant status and strip
privileged fields, so that a public caller cannot escalate a record's state or identity.

#### Acceptance criteria
1. The system SHALL force `status = application` on the created record regardless of any
   client-supplied status.
2. The system SHALL strip client-supplied `tenant_id`, `member_id` / primary key, and
   `status` from the body before processing (mirroring `_sanitize_write_payload`).
3. The system SHALL mint the record identifier server-side (e.g. `member_id = uuid4()`),
   never from the client.
4. The system SHALL accept ONLY fields the tenant has **application-selected** (R4.2–R4.4);
   any other submitted key — including an unselected `membership` field — SHALL be ignored.
5. The create path SHALL REUSE the proven create spine (sanitize → stamp tenant → mint id
   → default initial status → validate → catalog/enum checks → single write) rather than
   opening a second write path, adding only the public-path rules in this document.

### R3a — One record per form session + flag a possible existing-member duplicate (D11/D25)

**User story:** As an applicant, I want a resend of my application to update rather than
duplicate what I sent; and as a reviewing staff member, I want to be warned when an
applicant's **name + date of birth** matches an existing member, so that I can catch a
re-application without the public form ever blocking a genuine applicant.

#### Acceptance criteria
1. The submission SHALL accept a **client-carried session / idempotency key** (e.g. a
   stable id minted by the form on first render, sent on every submit of that session).
2. WHEN a submit carries a session key that has already created a record **in this session**
   THEN the system SHALL **UPDATE that same record** with the new field values (the applicant
   corrected/changed fields and resent) rather than create a second record. The record's
   server-minted `member_id` and `status = application` SHALL be preserved across the update.
3. WHEN two submits carry the same session key near-simultaneously (double-click / retry)
   THEN the system SHALL NOT create two records — the first creates, the rest update — using
   a **conditional write** (the `attribute_not_exists` pattern the mail worker's
   `mailsent#<job_id>` marker already uses), so the race resolves to a single record.
4. The session de-duplication SHALL use the server-validated `email` (R6.1) and the resolved
   `tenant_id` (R2), never a raw client value.
5. **Possible-duplicate detection is FLAG-ONLY, on NAME + DATE OF BIRTH, never a block (D25).**
   On a successful submission the system SHALL check whether the submitted (normalized)
   **name + date of birth** already matches an existing member of the tenant and, IF it
   matches, record a **possible-duplicate note on the record's `overlay.additional_info`
   field** using the stable **`DUP` keyword** (the existing leftover-info field, appended as a
   keyworded entry — NO new flag attribute/column; keyword-filterable per R8b.5) for staff
   review. The application SHALL STILL be created — detection never rejects, and NO uniqueness
   constraint is enforced on the write.
6. The match signal SHALL be **name + date of birth** (both required, R6.1a) — a stronger
   "same person" key than a reused email; email is NOT the automatic match. Normalization
   (trim/case-fold name, canonical date) is fixed in design.
7. The duplicate note SHALL NOT change the applicant-facing response (R1a): a matched and an
   unmatched submission SHALL return the same neutral 202, so the public endpoint is not an
   **enumeration oracle** for "is this person already a member?". The note is visible ONLY on
   the authenticated staff side (`overlay.additional_info`).
8. The detection lookup SHALL use a **GSI** keyed on the normalized `(tenant_id, name+dob)`
   composite (D25) — a cheap indexed read, NOT a public-endpoint partition scan — staying
   tenant-scoped (Property 1) and using only the server-validated fields, never a raw client
   value.

### R4 — Form is a projection of the tenant's resolved field config, filtered by an explicit per-field selection

**User story:** As a tenant administrator, I want to select exactly which of my configured
fields appear on the public application form — including specific membership fields when I
want applicants to supply them — so that the form stays in lockstep with the member
overview and needs no per-tenant code.

#### Acceptance criteria
1. The applicant form SHALL render fields derived from the tenant's **resolved field
   config** (`config#fields` → `FieldResolver`), grouped by `functional_group`.
2. Which fields appear on the public form SHALL be governed by an **explicit per-field
   application-visibility selection** marked on the field config (distinct from the
   overview's `visible`), NOT by filtering a whole storage group. The exact marker
   name/shape is decided in design (D6; Open Question #3).
3. The default selection SHALL leave back-office `membership`-admin fields
   (`member_number`, `status`, created/updated, etc.) OFF the form, so an applicant is not
   asked for fields staff own.
4. A tenant SHALL be able to **select specific `membership`-group fields onto the form**
   (e.g. a membership-type choice) via the same per-field selection — membership inclusion
   is opt-in per field, not all-or-nothing. A selected enum field MAY present a **subset**
   of its choices on the public form (R4a).
5. All configured functional groups a tenant selects fields from (personal / address /
   financial / **motor**, and any tenant overlay groups) SHALL appear automatically, with
   NO per-group code.
6. Each rendered input SHALL be driven by its `ResolvedField` attributes (`type`, `label`
   {nl,en}, `choices`/`options`, `required`, `show_when`, `order`).
7. The submission SHALL be **un-flattened** back into the nested member shape
   (`{personal:{…}, membership:{…}, overlay:{…}, …}`) the create path expects, keyed by
   each field's `dotted_key()` — the same field model as the overview, used in reverse.
8. The server SHALL accept ONLY fields that are application-selected (per 2–4); any other
   submitted key SHALL be ignored (R3.4), so a selected membership field is accepted while
   an unselected one is rejected even if posted.
9. WHEN a tenant changes the per-field selection, or adds/removes/renames a field, or
   attaches a validator THEN the form, the stored submission, and the member record SHALL
   all follow with zero per-tenant code.

### R4a — Per-field application choice SUBSET for enum fields

**User story:** As a tenant administrator, I want an enum field on the application form to
offer only the choices that make sense for an applicant, so that applicants pick from the
public-safe options (e.g. only the membership types open to new applicants) without seeing
staff-only entries.

#### Acceptance criteria
1. An enum / choice field that is application-selected (R4.2–R4.4) SHALL be able to declare
   an **application choice subset** — a subset of the field's full `options`/`choices` that
   is offered on the public form — via the field-definition config (an extension of the
   existing `options`/`choices` model, NOT a separate list).
2. WHEN a subset is declared THEN the public field-config read (R5) and the rendered form
   SHALL present ONLY the subset; WHEN no subset is declared THEN the full choice set is
   offered (back-compatible default).
3. The server SHALL validate a submitted value against the **application subset** (not the
   full set) for a field that declares one — a value outside the subset SHALL be rejected
   with a field-level error, even if it is a valid staff-facing choice.
4. The subset SHALL be a strict subset of the field's resolved choices; a subset entry that
   is not a valid choice of the field SHALL be a config error surfaced fail-fast (same
   discipline as an enum with no choices), never silently accepted.
5. `membership_type` is the first consumer of this subset (D2): the public-safe membership
   types are the field's application subset, re-validated server-side against the live
   catalog per R11.

### R4b — Per-field application-required flag (D13)

**User story:** As a tenant administrator, I want to mark which application fields an
applicant MUST fill in, so that genuinely-optional fields (e.g. a Dutch surname infix
`tussenvoegsel`, a second address line) can be shown but left blank, while the fields I need
are enforced.

#### Acceptance criteria
1. An application-selected field (R4.2) SHALL carry an **application-required boolean** in
   the field-definition config — the same per-field application config as visibility (R4.2)
   and the enum subset (R4a), NOT a separate list.
2. WHEN a field is application-required THEN a missing/blank value on submit SHALL be
   rejected with a field-level error (merged into the R1a 422 `errors` array); WHEN it is
   NOT application-required THEN a blank value SHALL be accepted (e.g. `tussenvoegsel` left
   empty is valid).
3. The application-required flag SHALL be an **overlay on the form only**: it MAY make an
   otherwise-optional field required for the application, and a field that is already
   **platform-required** (from the resolved config, R4.6) STAYS required — the application
   form SHALL NOT be able to make a platform-required field optional (that would violate the
   create invariants).
4. `email`, `name`, and `date of birth` SHALL be application-required regardless of config
   (R6.1/R6.1a) — tenant config may not relax these on the public path.
5. A field hidden by its `show_when` (R6.3) SHALL be neither required nor validated even if
   application-required — reusing `_drop_hidden_required_errors`, so a conditional field is
   only required when actually shown.
6. The application-required flag SHALL be exposed on the public field-config read (R5) so
   the form can mark/enforce it client-side too (the server remains authoritative, R6.6).

### R4c — Flask authors the application field attributes and projects them (D18)

**User story:** As a tenant administrator, I want to author the application-form settings for
each field in the same tenant-admin field-config UI I already use, so that the public form's
fields, requiredness, choice subsets and validators are configured per tenant without code.

> **Flask-plane owner.** Authoring + projection of field config lives in the **Flask plane**
> (`backend/src/` — the `/api/tenant-admin/parameters` `members.*` surface and the
> `projection_sync` / `build_config_fields_row` pipeline), per steering
> `30-backend-api-flask-mysql`. This spec's SAM side only READS the resulting `config#fields`
> projection row (R4/R4a/R4b/R5). R4c is the authoring/projection counterpart.

#### Acceptance criteria
1. The **per-field application attributes** this spec introduces — application-visibility
   (R4.2), enum **application-subset** (R4a), **application-required** (R4b), and the
   **`FieldFormat` validator** (R7) — SHALL be **authored in the Flask tenant-admin field
   config** (the existing `members.*` / `field_overlay` tenant-scope parameters), alongside
   the attributes already authored there (`label`, `visible`, `required`, `order`,
   `functional_group`, `options`/`choices`, `show_when`).
2. These attributes SHALL be **projected into the `config#fields` row** by extending the
   existing Flask builder (`_projection_config_builders.build_config_fields_row` and its
   per-field maps) and `projection_sync`, carried 1:1 the same way existing field attributes
   are — NO new projection row type, NO SAM-plane authoring. (This is the Flask side of D6 /
   R7's "rides the existing `config#fields` row" claim.)
3. The Flask **write-time projection validator** (`projection_validator` /
   `members_config_validation`) SHALL validate the new attributes at Save (fail loud, no
   partial write): e.g. an application-subset entry that is not a valid choice of the field,
   or a `FieldFormat.checker` that is not a platform-known token, SHALL be rejected at author
   time rather than projecting a broken row.
4. The projected attributes SHALL be the SINGLE SOURCE the SAM plane reads (R4/R4a/R4b/R5) —
   Flask authors and projects, SAM consumes; the boundary rule holds (no SAM authoring, no
   Flask reading SAM data).
5. A tenant that authors none of these SHALL get well-formed defaults (no application-
   visibility → field off the public form; no subset → full choices; no application-required
   → optional unless platform-required; no `FieldFormat` → no extra checker), so the row
   stays back-compatible for tenants not using the application form.

### R5 — Public field-config read for the renderer

**User story:** As the public form app, I want to fetch the tenant's public field schema
before submit, so that I can render a config-driven form without baking in a field list.

#### Acceptance criteria
1. The system SHALL expose an **unauthenticated public field-config read** (a public
   variant of `GET /members/field-config`) returning the resolved field set for an
   allow-listed tenant, filtered to the tenant's **application-selected** fields (R4.2–R4.4).
   Its responses SHALL follow the R1a contract (200 on success, 404 for an unknown slug).
2. The public field-config read SHALL resolve its tenant via the same allow-list as R2 and
   SHALL NOT expose any field the tenant has not application-selected (including
   unselected staff-only / `membership` fields), internal attributes, or other tenants'
   config.
3. The returned schema SHALL carry everything the renderer needs per field (`type`,
   `label{nl,en}`, `choices`/`options`, the **application-required flag** (R4b), the enum
   **application subset** (R4a) where declared, `show_when`, `order`, `functional_group`,
   and any `format` token). The renderer selects the label language from the applicant's
   chosen locale (R6b), defaulting to `nl`.
4. **The public field-config read SHALL also be the tenant-readiness GATE (D15).** It SHALL
   verify the tenant has a **usable certified sender** (`mail_certified` + `mail_domain`,
   D4/R9) BEFORE returning a form schema. WHEN the tenant is NOT send-ready THEN it SHALL
   refuse with a proper error (R1a envelope, e.g. 409/422 + a stable `code` the form renders
   as a bilingual "applications are not available for this tenant yet" message — R6b locale),
   and the form SHALL NOT open. The error SHALL be **neutral** — it SHALL NOT expose tenant
   mail-config internals. This resolves F1: an applicant is never shown a form whose
   notifications would silently go nowhere.

### R6 — Critical validations: required identity fields, email, and conditional IBAN

**User story:** As a reviewing staff member, I want applications to carry a valid reply
email plus enough identity (name + date of birth) to recognise the person, and a valid IBAN
when direct debit is chosen, so that I can contact, identify, and bill the applicant without
fixing bad data by hand.

#### Acceptance criteria
1. The system SHALL require `email` to be present and well-formed on the public path, even
   though the platform keeps `email` optional on a member record generally. A missing or
   malformed email SHALL be rejected with a field-level error — a public-path rule, not a
   change to the fixed-field registry.
1a. The system SHALL also require, on the public path, the applicant's **name** and **date
   of birth** — a missing/blank name or a missing/invalid DOB SHALL be rejected with a
   field-level error. These are required so staff can identify a flagged possible-duplicate
   (R3a) and recognise the applicant; like email, this is a public-path tightening, not a
   change to the fixed-field registry's general optionality. (The exact field keys for
   "name" and "date of birth" are confirmed in design against the tenant's fixed-field set.)
2. WHEN the chosen payment method is direct debit / incasso THEN the system SHALL validate
   the `iban` field with an **ISO 13616 mod-97** check (normalize → country-length check →
   rotate first four chars → letters→digits → `int % 97 == 1`), rejecting an invalid IBAN
   with a field-level error.
3. WHEN incasso is NOT the chosen payment method (the `iban` field's `show_when` does not
   hold) THEN IBAN SHALL be neither required nor format-checked (reuse
   `_drop_hidden_required_errors`; no incasso-specific code).
4. The two critical checks SHALL run on top of the existing validation chain
   (`validate_fixed_fields` + overlay required/enum gates + `member_number` format + the
   tenant `validate_member` hook), not replace it.
5. All field errors SHALL be collected and returned together (one `MemberValidationError`
   map) so the applicant sees every problem at once, not one-at-a-time — returned as the
   R1a 422 `errors` array (`_field_errors_array`).
6. **ALL required application-selected fields SHALL be server-enforced on submit, not only
   email/IBAN.** Every field that is required — whether platform-`required` (R4.6) or
   application-required (R4b) — SHALL be validated for presence server-side via the existing
   validation chain (R6.4); the two critical checks (email, conditional IBAN) are additions
   ON TOP, not the whole of enforcement. A field that is shown-but-optional (R4b.2) or hidden
   by `show_when` (R6.3) is exempt. The public form is trusted for nothing — client-side
   required marks are a convenience, the server is authoritative.

### R6b — Applicant locale selection (D12)

**User story:** As an applicant, I want to choose the language of the form and my
confirmation email, so that I apply and am confirmed in a language I understand.

#### Acceptance criteria
1. The application form SHALL offer an **applicant locale selection** (`nl` / `en`),
   **defaulting to `nl`**. The chosen locale SHALL be submitted with the application.
2. The submitted locale SHALL be validated against the supported set (`nl`, `en`); an
   absent, blank, or unsupported value SHALL fall back to **`nl`** (never an error).
3. The chosen locale SHALL drive all **applicant-facing** copy: the form labels/choices
   (via the public field-config, R5.3) and the applicant's **confirmation email** (R8a.2).
4. The chosen locale SHALL be **persisted on the member record** so a later staff reply,
   re-send, or confirmation re-render uses the same language.
5. The **staff** notification locale (R8.6) SHALL NOT be driven by the applicant's choice —
   it SHALL use the recipient/tenant locale (a Dutch applicant SHALL NOT force an
   English-preferring reviewer's email into Dutch). Where no per-recipient locale is known,
   it defaults to `nl`.

### R7 — Declarative field-validator seam (EMAIL and IBAN as first entries)

**User story:** As the platform, I want field validators attached declaratively via field
config, so that email and IBAN are config-driven entries in a shared registry rather than
application-specific special cases, and new checkers are config, not code.

> **Why build the registry now (V1 justification, D16).** The v1 *need* is small — EMAIL is a
> standard regex (reuse the existing `emailValidationUtils` / Flask `_validate_email` pattern)
> and IBAN is a ~10-line mod-97 checksum (NOT a regex — a regex checks shape but cannot verify
> the checksum). Building the full config-driven registry for just these two is justified
> **only because the events/webshop roadmap is firm**: those modules will carry the same
> "attach a checker to a field" need, so the registry gets built anyway and the members
> application is simply its FIRST caller. This is a deliberate, recorded EXCEPTION to the
> rule-of-three (D7 / steering 35) — we invest in the abstraction up front because a committed
> second/third consumer is known, not speculative. If that roadmap were not firm, the correct
> call would be two targeted validators and defer the registry (the rejected Option A).

#### Acceptance criteria
1. A field SHALL carry an optional **`FieldFormat {checker, params}`** attribute on
   `FixedField`, `OverlayField`, and `ResolvedField`, defaulting to `None` (no extra
   checker beyond `type`/`required`), mirroring how `member_number_format` is carried.
2. The attribute SHALL ride the `config#fields` projection row as a `format` sub-object
   (sibling to `type`/`required`/`choices`/`show_when`) with no projection schema change.
3. A reader helper `_build_format(spec)` SHALL rebuild it onto the field, returning `None`
   for a missing, malformed, or unknown-token spec (degrade gracefully — a stray token
   never crashes the field-config read).
4. Conditionality SHALL reuse the field's existing `show_when` (NOT a condition on
   `FieldFormat`): a hidden field is neither required nor format-checked.
5. The validation chain SHALL gain ONE generic step: for each resolved field with a
   `format`, if the field is present and its `show_when` holds, run
   `REGISTRY[checker](value, params)` and merge any `FieldError` into the shared error map.
6. The registry SHALL be a module-level `dict[str, Callable[[Any, Mapping], FieldError|None]]`
   with **`EMAIL`** (a regex check, reusing the existing `emailValidationUtils` /
   `_validate_email` pattern) and **`IBAN`** (ISO 13616 **mod-97 checksum** — NOT a regex,
   per R6.2) as its first two entries, built now; `DATE`, `PHONE`, etc. remain open for
   extension.
7. The checker SET SHALL be platform-defined (a tenant picks a known token, cannot author
   code); **attaching** a checker to a field SHALL be tenant config on `config#fields`.
8. No field-validator authoring UI is required in v1 — only the attribute, the reader
   helper, the registry, and the one enforcement step.

### R8 — Notify all-scope `Members_CRUD` (+ optional scope-matched copy) from the governance projection (SAM-side, best-effort)

> **Tenant-agnostic scope (D9).** `region` is only h-dcn's specific scope dimension; this
> requirement is written in platform **scope** terms — a tenant's configured scope dimension
> and its `scopegrant#<email>#<dimension>` grants. Where a concrete example helps, h-dcn's
> `region` / `Regio_All` is cited as *an instance*, not the contract.

**User story:** As a tenant-wide membership administrator, I want an email when a new
application arrives, so that I can review and approve it promptly; and (optionally) as a
scope-local administrator, I want a copy of applications for my own scope value so I can
action them without every application landing in one central inbox.

#### Acceptance criteria
1. On a successful submission the system SHALL notify the tenant's **all-scope
   `Members_CRUD`** users by email, resolving recipients ENTIRELY within the SAM plane — NO
   Cognito query, NO Flask call, NO cross-account grant.
2. Recipients SHALL be resolved by a new thin `role-recipients` reader over the shared
   projection schema: `Query` the tenant partition on `GOVERNANCE_PROJECTION_TABLE`, keep
   `RECORD_TYPE_ROLE` items whose role segment is `Members_CRUD`, and collect the email
   id-segment of each `role#<email>#Members_CRUD` sort key.
3. The recipient set SHALL be **filtered to all-scope grants** (D9): keep only those
   `Members_CRUD` emails whose `scopegrant#<email>#<dimension>` row is `["*"]` for the
   tenant's governing scope dimension (h-dcn instance: `region = ["*"]` = `Regio_All`). A
   scope-limited `Members_CRUD` user SHALL NOT be notified by this base rule. A tenant with
   NO scope dimension configured SHALL treat all its `Members_CRUD` as all-scope. (h-dcn's
   current, confirmed-working workflow — D9/F2.)
3a. **OPTIONAL scope-matched copy (config-gated, D9a).** WHEN a tenant enables the option AND
   the applicant selected a **scope value** on the form (h-dcn: a region) THEN the system
   SHALL ALSO send a copy to the `Members_CRUD` users **scoped to that value** — those whose
   `scopegrant#<email>#<dimension>` row contains the applicant's selected value (read from the
   SAME projection rows as R8.3, matched to the value instead of `["*"]`). This ADDS to the
   all-scope recipients (R8.3), never replaces them, so a scope-local reviewer is looped in
   without overloading one inbox. A tenant that does not enable it, or an application with no
   scope value selected, keeps the base R8.3 behaviour. Tenant-agnostic — works on whatever
   dimension the tenant configured (region / chapter / department / …).
4. WHEN a tenant has zero all-scope `Members_CRUD` users THEN the system SHALL fall back
   to the **member module's tenant administrator** (D9): the `TenantAdmin`-role holders,
   read from the `role#<email>#TenantAdmin` rows of the same projection partition. (The
   exact role-name/`members:admin` mapping is confirmed in design.)
5. WHEN neither any all-scope `Members_CRUD` user NOR any `TenantAdmin` exists THEN the
   record SHALL still be created and a **"notification undelivered" note SHALL be recorded on
   the record's `overlay.additional_info` field** using the stable **`NO_NOTIFY` keyword** (no
   new attribute), so the un-notified application is **keyword-filterable** on the
   applications-inbox view (R8b.5), NOT merely written to a Lambda log. The platform operator
   SHALL additionally be alerted (the onboarding/`support@jabaki.nl` channel) so the
   misconfigured tenant gets fixed. It SHALL NOT fail the applicant's submission.
6. The email SHALL be sent via a SAM-side SES client (`ses:SendEmail`), rendered from a
   **bilingual (nl/en)** "new application" template, in the **recipient/tenant locale**
   (NOT the applicant's choice — R6b.5; default `nl`). Rather than
   embedding the applicant's data, the staff email SHALL carry a **deep-link to the
   applicant's member record** (review behind normal auth, R8b) — the body SHALL NOT
   contain applicant PII beyond what is needed to recognise the notification (e.g. a
   display name), keeping personal data behind authentication.
6a. WHEN the application carries the possible-duplicate note (R3a.5, in
   `overlay.additional_info`) THEN the staff email SHALL include a **neutral one-line marker**
   (e.g. "possible existing member — review") as a triage hint. It SHALL NOT name, id, or
   otherwise reveal the MATCHED existing member (no cross-member PII in the email,
   R8.6/R12.4) — the actual comparison happens behind the deep-link (R8b.5).
7. The notification SHALL be **OFFLOADED** (D5): the submission enqueues a notification job
   (SQS / DynamoDB-stream notifier, reusing the members mail-send queue/worker pattern) and
   returns to the applicant; the actual recipient resolution + SES send happen in the
   worker, so a slow or failing SES call NEVER sits in the applicant's request path and can
   NEVER fail or roll back the applicant's submission.
8. The offloaded send SHALL be **best-effort**: a transient SES throttle is retried (queue
   redelivery → DLQ after N) and a permanent failure dead-letters as an operational signal,
   mirroring the members mail worker's retryable-vs-permanent classification — neither
   affects the already-committed application record.
9. Staff recipients SHALL come ONLY from the projection rows, never from any client value;
   the public caller SHALL be unable to choose them.

### R8a — Confirmation copy to the applicant (D10)

**User story:** As an applicant, I want an email copy of the application I submitted, so
that I have a record of what I sent and confirmation it was received.

#### Acceptance criteria
1. On a successful submission the system SHALL send a **confirmation email to the
   applicant's own submitted `email` address**, containing a copy of the data they
   submitted.
2. The confirmation SHALL be a **separate** notification from the staff one (R8): a distinct
   **bilingual (nl/en)** "application received" template, rendered in the **applicant's
   chosen locale** (R6b, default `nl`), sent `From:` the same tenant verified sender (D4/R9).
3. The confirmation SHALL be **offloaded + best-effort** on the same terms as R8.7/R8.8 — it
   SHALL NOT sit in the applicant's request path and SHALL NEVER fail or roll back the
   application record.
4. The applicant address used SHALL be the server-validated `email` (R6.1); the confirmation
   SHALL NOT be sent to any other client-supplied address. Emailing the applicant a copy of
   their OWN submission is not a PII leak (it is their own data) — so this email MAY embed
   the submitted data, unlike the staff email (R8.6).
5. A usable verified sender is guaranteed by the precondition (R5.4/R9.4) — a submission
   only reaches this point for a send-ready tenant — so the confirmation always has a valid
   `From`. (If a sender becomes unusable between precheck and send, the confirmation
   degrades best-effort per R8a.3 and never fails the record.)
6. The applicant SHALL NOT receive an authenticated deep-link (they have no account by
   design, R1) — the confirmation email IS their channel. A web-based application-status
   viewer for applicants is explicitly out of scope for v1 (see Out of Scope / Future
   direction).

### R8b — The staff review screen is the existing member overview + detail (no new screen)

**User story:** As a `Members_CRUD`/`TenantAdmin` reviewer, I want to review applications in
the member overview table and detail I already use — filtered to applications — so that
reviewing and approving an applicant is the normal member workflow, not a new tool.

> Reuses the standard member overview, the generic table-filter framework
> (`Common/Frameworks/table-filter-framework-v2`), and the existing member detail +
> edit flow — this spec adds NO new grid or review UI, only a default
> `status = application` filter and keyword-filtering on the existing `overlay.additional_info`.
>
> **Superseded note (`retire-members-status-lifecycle-engine`):** the membership lifecycle
> engine was retired. `status` is now a plain tenant-driven OPEN enum (authored like `gender`),
> and a status change is an ordinary member **field edit** — there is no transition graph,
> guard, or transition modal. Wherever this requirement said "status transition", read "status
> field edit via the member edit modal".

#### Acceptance criteria
1. The staff email deep-link (R8.6) SHALL target the **existing authenticated member
   detail** for the new record (e.g. `/members/{member_id}`) — Option 1 (D1) means the
   applicant is already a real member record in `status = application`, so no new review
   screen is built.
2. Opening the link SHALL require normal Cognito sign-in and the usual tenant + capability
   check (`Members_CRUD` / `members:admin`); an unauthenticated or unauthorised click SHALL
   NOT reveal any applicant data. The `member_id` in the URL is a destination, not a grant.
3. The reviewer SHALL approve/reject by **editing the member's `status` field** to the
   target value (e.g. `application → active`/`pending`, or a reject/withdraw value) via the
   existing member edit modal — a plain field edit, no bespoke approval workflow in v1.
   (`retire-members-status-lifecycle-engine`: status is an OPEN enum and a status change is
   an ordinary field edit; there is no transition graph or transition endpoint.)
4. The "applications inbox" — the **standard member overview table** driven by the
   **generic table-filter framework** (`.kiro/specs/Common/Frameworks/table-filter-framework-v2`,
   per steering 32/40), the SAME overview staff already use, **filtered to
   `status = application`** — SHALL be the **authoritative, REQUIRED staff channel** for
   finding applications (F3), NOT optional. It is a default/saved filter over the existing
   records — NO new table or store. The email notification (R8) is a best-effort **nudge**
   on top; because Option 1 (D1) lands every applicant as a `status = application` member
   record regardless of whether the email arrives, an application is ALWAYS discoverable in
   the inbox even if the notification is delayed, dead-lettered, or never sent. The feature
   SHALL NOT depend on the email as the sole means of surfacing an application.
5. The **possible-duplicate note** (R3a.5) and the **"notification undelivered" note** (R8.5)
   are both carried in the existing **`overlay.additional_info`** free-text field (no new
   columns), each written with a **stable, documented keyword token** (e.g. `DUP` for a
   possible duplicate, `NO_NOTIFY` for an undelivered notification — exact spelling fixed in
   design). Because the keywords are stable, a reviewer SHALL be able to **filter the overview
   on `overlay.additional_info` by keyword** (via the generic table-filter framework) to list
   possible duplicates or un-notified applications — reliable detection with no dedicated
   column. The notes are advisory; they SHALL NOT auto-block the status edit, and an
   un-notified application is never silently lost.

**User story:** As the platform, I want a tenant's application emails to go out as that
tenant's own verified sender, so that the mail is deliverable and the platform is not
spoofed, while keeping sender provisioning in the onboarding plane.

#### Acceptance criteria
1. The notification SHALL send `From:` the **tenant's own verified SES sender**, NOT the
   platform onboarding sender `support@jabaki.nl`.
2. Provisioning that per-tenant verified sender (SES domain/address verification + DKIM/SPF
   DNS) is a **dependency owned by Flask tenant onboarding / the tenant administration
   module** and is explicitly OUT OF SCOPE for this spec.
3. This spec SHALL CONSUME the sender by **reusing the existing members mail mechanism**
   (D4): the notification worker SHALL read the tenant's verified sender from the SAME
   `config#mail` projection row and `MailSenderResolver` the members mail worker uses —
   composing `From = <mail_local_part|noreply>@<mail_domain>`, gated by the projected
   `mail_certified` flag (the onboarding-recorded SES-verified gate; no live SES call on
   the send path). No new sender-config store is introduced.
4. **A usable certified sender is a PRECONDITION for the whole feature (D15, resolves F1).**
   The public field-config read gates form load on it (R5.4), AND the submission endpoint
   SHALL re-check it (defense in depth — a client could POST without loading the form):
   WHEN the tenant has no usable verified sender (`mail_certified` false / no `mail_domain`)
   THEN the submission SHALL be **refused with a proper neutral error** (R1a envelope +
   stable `code`), the member record SHALL NOT be created, and nothing enqueued. The tenant
   is simply "not accepting applications yet" until onboarding certifies its sender — so a
   submission never commits a record whose notifications would silently fail. (This replaces
   the earlier skip-and-log-at-send stance: the public path refuses UP FRONT, it does not
   accept-then-fail-to-notify.)

### R9a — Reply-To when there is no logged-in user (D8/D24)

**User story:** As a members administrator, I want a reply to an application notification to
reach the members admins who handle applications, so that the applicant's reply lands with
the right people even though there was no logged-in sender.

#### Acceptance criteria
1. The notification's **From** SHALL remain the tenant's verified sender
   (`noreply@<domain>`, D4/R9) — the From is NOT changed by this requirement.
2. The **Reply-To SHALL be the all-scope `Members_CRUD` recipient set** — the SAME set the
   staff notification targets (R8.3/D9), as a multi-address Reply-To — so a reply reaches the
   admins who were notified. There is NO configured Reply-To parameter and NO single-pick
   tiebreak (D24).
3. WHEN there is NO all-scope `Members_CRUD` THEN the Reply-To SHALL be the **`TenantAdmin`**
   set (the same fallback as recipients, R8.4).
4. WHEN neither an all-scope `Members_CRUD` nor a `TenantAdmin` exists THEN no Reply-To SHALL
   be set (the "no recipients" handling of R8.5 applies).
5. The Reply-To SHALL come ONLY from the projection, never from any client value, and SHALL
   mirror (not change) the authoritative recipient list (R8.9) — it only sets the envelope
   Reply-To.

### R10 — Abuse hardening for the public write (SAM-native)

**User story:** As the platform, I want the public endpoint hardened against spam and
resource abuse, so that a scripted flood cannot overwhelm a tenant's records or email.

#### Acceptance criteria
1. The public endpoint SHALL be protected by API Gateway **throttling + a usage plan**
   (per-endpoint rate + burst limits).
2. The handler SHALL implement a **honeypot** field and a **payload-size cap**, rejecting
   oversized or honeypot-tripped submissions before any write (R1a 400).
3. **CORS** SHALL be restricted to the known public form origin(s).
4. **No WAF in v1 (V3 decision, D17).** The abuse controls are API Gateway throttling + the
   honeypot + payload cap + CORS above — proportionate to a low, human-paced application-form
   volume. A WAF (rate-based rule / CAPTCHA) is the one material recurring cost and is
   deliberately NOT provisioned now; it is recorded as an **easy add-on** if real abuse
   appears (the public-intake edge is the place it would attach). Revisit if volume or attack
   traffic warrants it.
5. IAM for the public function SHALL be least-privilege and scoped to exact ARNs in the
   data account: the members-table write grant (Option 1, D1), the projection read for the
   notification job, and the enqueue grant for the offload queue (D5) — NO wildcards, NO
   cross-account.

### R10a — Accessibility & client/server validation parity (WCAG 2.2 AA) (D14)

**User story:** As an applicant, including one using a screen reader or keyboard, I want
clear, consistent, accessible validation on the application form, so that I can correct
mistakes and submit independently.

#### Acceptance criteria
1. The public form SHALL be built to **WCAG 2.2 Level AA** (global steering accessibility
   requirement) — a public, widest-audience surface with corresponding legal exposure.
2. Client-side validation SHALL use the existing **Yup + Formik** pattern, with the Yup
   schema **generated from the public field-config** (R5): application-required (R4b) →
   `.required()`, enum application-subset (R4a) → `.oneOf()`, `format` tokens EMAIL/IBAN
   (R7) → the matching check, `show_when` (R6.3) → conditional (`.when()`). It SHALL NOT be
   a hand-maintained per-tenant schema.
3. The server remains **authoritative** (R6.6): the server `errors` array
   (`_field_errors_array`, `{field, code, detail}`) SHALL be mapped into Formik error state
   **by the dotted `field` key**, so a server-rejected field displays through the SAME
   mechanism as a client error. Client and server SHALL validate the same rules keyed by the
   same field id; on disagreement the server wins.
4. Each field SHALL render via Chakra **`FormControl` + `FormLabel` + `FormErrorMessage`**
   so the accessible wiring is present (`aria-invalid`, `aria-describedby`, label
   association, and error-as-TEXT not colour-only); the label SHALL be the config
   `label{nl,en}` in the applicant locale (R6b), never a placeholder-only label.
5. On a failed submit the form SHALL surface an **accessible error summary in an ARIA live
   region** (announcing the error count and linking to the offending fields), in addition to
   the per-field messages — the one accessibility element Chakra's per-field wiring does not
   provide automatically.
6. The form SHALL be fully **keyboard-operable** with a visible focus indicator and logical
   focus/tab order, meet AA **colour-contrast** minimums, remain usable at **200% zoom**,
   and declare the page **`lang`** matching the applicant locale (R6b) so screen readers
   pronounce content correctly.
7. An **automated accessibility check** (axe / Lighthouse) SHALL gate CI over the public
   form. The spec records that automated checks are **necessary but not sufficient** — full
   WCAG 2.2 AA conformance requires manual assistive-technology testing and expert review,
   which is a verification activity, not something the build auto-satisfies.

### R11 — `membership_type` as an application-selectable field with a choice subset (D2)

**User story:** As a tenant administrator, I want to decide whether applicants pick a
membership type and, if so, from which subset of types, so that the applicant record is
classified sensibly without exposing staff-only tiers or leaving a dangling type.

#### Acceptance criteria
1. `membership_type` SHALL be handled through the normal field-definition mechanism (R4,
   R4a) — it is not a special-cased application field. By default it is NOT
   application-selected and the applicant does not supply it.
2. WHEN a tenant marks `membership_type` application-selectable (R4.4) THEN it SHALL be
   **application-required** (R4b, D21): the applicant chooses from its **application choice
   subset** (R4a) — the public-safe membership types — with the **first subset option
   pre-selected as the default** so a valid value is always present. The server SHALL
   re-validate the submitted value BOTH against the subset (R4a.3) AND against the **live
   catalog** (`_validate_membership_type_reference`), never trusting the submitted value nor
   the default (verify-before-trust).
3. WHEN a tenant does NOT expose `membership_type` on the form THEN the record SHALL be kept
   catalog-valid while `status = application` by a server-stamped **tenant-default**
   `membership_type` (D21) — NOT by deferring the reference check. (This replaces the earlier
   "defer to approval" working direction.)
4. In all cases a `membership_type` that does not reference a **live** catalog entry SHALL
   NOT be persisted — the public path never weakens `_validate_membership_type_reference`.

### R12 — PII / GDPR controls

**User story:** As a data subject applying to join, I want my personal data handled
lawfully, so that my submission is consented, retained no longer than needed, and never
leaked in logs.

#### Acceptance criteria
1. The form SHALL present a **consent / privacy notice** before submission, and submission
   SHALL require the applicant's **explicit, affirmative consent** (e.g. a non-pre-ticked
   checkbox) — a submit without consent SHALL be rejected (field-level error, R1a 422).
1a. **Consent SHALL be recorded defensibly (F4):** on a successful submission the system
   SHALL persist, on the member record, the **version/identifier of the notice the applicant
   accepted**, the **UTC timestamp** of acceptance, and the **locale** (R6b) of the notice
   shown. The notice text SHALL be **versioned** (a stable version id per notice revision) so
   a stored consent references exactly which wording was agreed; a later revision SHALL NOT
   retroactively change what an existing record recorded.
1c. **The notice is TENANT-SPECIFIC (D26):** each tenant authors its OWN bilingual (nl/en)
   consent/privacy notice text in the Flask tenant config, **projected** like the other
   per-tenant config and **versioned** per revision (R4c/Phase 8). The public field-config read
   (R5) serves the tenant's current notice text + version to the form. The platform MAY ship a
   seed/default notice for a tenant that has authored none (steering 38 i18n seed rule); it is
   NOT a platform-only global notice.
1b. The consent record SHALL be an **authoritative server-stamped value** (acceptance
   timestamp minted server-side, like `created_at`), never trusted from a client-supplied
   timestamp. (Storage shape — a structured consent field vs `overlay.additional_info` — is
   fixed in design; it is member data, not a log, so R12.3 does not forbid storing it.)
2. Un-approved applications (records left in `status = application`) SHALL be purgeable by a
   **manual delete** action — and in v1 ONLY an **all-scope `Members_CRUD`** user may delete an
   applicant record (D23; the same all-region set notified per D9; scope-limited `Members_CRUD`
   may not). NO automatic TTL purge in v1 — this avoids auto-deleting an applicant that was since
   approved. The GDPR retention *period* is operational guidance (docs); an automatic TTL purge
   (with an approval-clears-TTL invariant) is a possible future enhancement, not v1.
3. The system SHALL NOT write PII (IBAN, email, name, DOB) values into logs — references
   SHALL be by presence/field name, never by value.
4. The **staff** notification email SHALL NOT embed applicant PII (R8.6) — it deep-links to
   the authenticated member record instead, keeping personal data behind sign-in. (The
   applicant's OWN confirmation copy MAY contain their data — R8a.4 — as it is sent only to
   the data subject themselves.)

### R13 — Governance, documentation, and ADR (definition-of-done)

**User story:** As a reviewer, I want the governance artifacts this feature forces to be
updated, so that the step is not considered done until steering and ADRs match.

#### Acceptance criteria
1. `35-sam-module-architecture-sam.md` SHALL be extended with the **public/unauthenticated
   intake** edge pattern (skip-auth + allow-list tenant resolver + abuse hardening) and its
   security controls — currently it covers only the authenticated edge (ADR 0007).
2. A new **ADR** SHALL record "public unauthenticated intake on the SAM edge" (companion to
   ADR 0007), capturing the fenced exception and its controls.
3. The per-tenant verified-sender gap SHALL be recorded as an **extension of the existing**
   `Common/Serverless-applications/SNS-SES/SES Email Service` spec (owned by onboarding),
   referenced here — not re-scoped into this spec.
4. The feature SHALL include an **end-user documentation** section per
   `.kiro/specs/Common/end-user-documentation/`: the applicant form, and the staff
   "new application" review.
5. Any behavior change to a route/service SHALL update its allocated test(s) in the same
   change (change-with-tests contract).

### R14 — Tests pin the public-intake contract

**User story:** As a maintainer, I want the public-intake invariants covered by tests, so
that the fenced exception can never silently widen.

#### Acceptance criteria
1. Tests SHALL cover: (a) a valid submission for an allow-listed tenant creates an
   `application`-status record for the correct tenant; (b) a non-allow-listed / forged
   tenant carrier is rejected with no write; (c) client-supplied `status` / `tenant_id` /
   `member_id` are stripped and the status is forced to `application`.
2. Tests SHALL cover the validators: email required+valid; **name + date of birth required**
   (R6.1a) — a missing name or missing/invalid DOB is rejected; IBAN mod-97 valid/invalid;
   IBAN skipped when incasso is not chosen; errors returned together.
3. Tests SHALL cover staff recipient resolution (D9/R8), in **scope-generic** terms (region
   is just h-dcn's instance): `Members_CRUD` filtered to all-scope grants (a scope-limited
   `Members_CRUD` user is excluded by the base rule); the **optional scope-matched copy**
   (D9a/R8.3a) — when enabled and the applicant selected a scope value, that scope's
   `Members_CRUD` are ALSO notified, additive to all-scope; the **`TenantAdmin` fallback**
   when no all-scope `Members_CRUD` exists; a tenant with NO scope dimension notifies all
   `Members_CRUD`; and the "no recipients" case (no all-scope `Members_CRUD`, no
   `TenantAdmin`) stamping the `NO_NOTIFY` note. Tests
   SHALL also assert the staff email carries a **deep-link** to the member record and does
   NOT embed applicant PII (R8.6/R8b/R12.4).
4. Tests SHALL assert the notification is **offloaded and best-effort** (D5): the submission
   enqueues a job and returns without an inline SES call; a simulated SES failure in the
   worker does NOT fail or roll back the application record.
5. Tests SHALL assert the public path is covered by the SAME repository tenant-invariant
   test as the authenticated path (Property 1).
6. The declarative validator seam SHALL be unit-tested: `_build_format` degrades on
   unknown/malformed tokens; the generic enforcement step runs a field's checker only when
   present and `show_when` holds.
7. Tests SHALL cover the **enum choice subset** (R4a): a selected enum field with a subset
   exposes/accepts only subset values; a non-subset value is rejected even if it is a valid
   staff-facing choice; a subset entry not in the field's choices is a fail-fast config
   error.
8. Tests SHALL cover the **path-slug tenant carrier** (D3): a known slug resolves to its
   `tenant_id`; an unknown/forged slug is rejected with no write.
9. Tests SHALL cover **sender resolution** (D4/R9): a certified `config#mail` tenant yields
   a composed `From`. (The un-certified case is the R5.4/R9.4 precondition — form refuses,
   submit refused, NO record — covered by R14.17, superseding the old accept-then-skip.)
10. Tests SHALL cover **Reply-To** (D8/D24/R9a): Reply-To is the all-scope `Members_CRUD`
    recipient SET (multi-address, mirrors R8.3); falls back to the `TenantAdmin` set when no
    all-scope `Members_CRUD`; no Reply-To when neither exists — while From stays the tenant's
    verified sender in every case.
11. Tests SHALL cover the **applicant confirmation copy** (D10/R8a): a successful submission
    sends a separate confirmation to the applicant's validated `email` with their submitted
    data; it is offloaded + best-effort; and it is skipped-and-logged (record still created)
    when the tenant has no usable verified sender.
12. Tests SHALL cover the **response/error contract** (R1a): a successful submission returns
    202 with no `member_id` in the body; a validation failure returns 422 with the RFC 9457
    `errors` array; an unknown tenant slug returns 404 (indistinguishable from no-endpoint);
    a malformed/oversized/honeypot body returns 400; and the applicant status code does NOT
    change when the tenant has no certified sender or no recipients.
13. Tests SHALL cover **in-session de-duplication + the duplicate flag** (D11/R3a): a resend
    with the same session key updates the one record (no second row), preserving `member_id`
    + `application` status; a concurrent same-key double-submit resolves to a single record
    via the conditional write; a submission whose **name + DOB** matches an existing member
    (via the GSI, D25) is STILL
    created but carries a `DUP`-keyworded note in `overlay.additional_info` (keyword-filterable
    on the overview per R8b.5, AND surfaced as the neutral staff email marker R8.6a — with NO
    matched-member PII), while a non-matching submission does not; and the applicant-facing
    202 is identical in both cases
    (no enumeration leak). (Hard write-time email uniqueness is out of scope here — not
    tested.)
14. Tests SHALL cover **locale** (D12/R6b): a chosen `en` renders the applicant confirmation
    in English and `nl` in Dutch; an absent/invalid locale falls back to `nl`; the chosen
    locale is persisted on the record; and the STAFF email locale follows the recipient/
    tenant, NOT the applicant's choice.
15. Tests SHALL cover **required-ness** (D13/R4b/R6.6): a missing value for an
    application-required field is rejected (in the 422 `errors` array); a blank
    shown-but-optional field (e.g. `tussenvoegsel`) is accepted; a platform-required field
    cannot be relaxed by config; a field hidden by `show_when` is not required; and email /
    name / DOB are always required. ALL required fields — not just email/IBAN — are enforced
    server-side.
16. Tests SHALL cover **accessibility + validation parity** (D14/R10a): the Yup schema is
    generated from the field-config (required / enum-subset / format / `show_when` all
    reflected); a server 422 maps into per-field Formik errors by dotted `field` key; and an
    automated axe check over the public form passes (label association, `aria-invalid`
    binding, and the live-region error summary present).
17. Tests SHALL cover the **certified-sender precondition** (D15/R5.4/R9.4): for a tenant
    with no usable certified sender, the field-config read REFUSES with the neutral "not
    available" error (form does not open) AND a direct submit is refused with NO record
    created; a send-ready tenant passes both. The refusal error exposes no mail-config
    internals.
18. Tests SHALL cover the **inbox-as-authoritative-channel** invariant (F3/R8b.4): an
    application created when the email notification FAILS (simulated SES failure / dead-letter)
    is STILL present and findable in the `status = application` overview filter — the feature
    does not depend on the email to surface it.
19. Tests SHALL cover **consent recording** (F4/R12.1–R12.1b): a submit WITHOUT affirmative
    consent is rejected; a successful submit persists the notice version, a server-stamped
    UTC acceptance timestamp, and the notice locale on the record; and a client-supplied
    consent timestamp is ignored in favour of the server value.
20. Tests SHALL cover **Flask authoring + projection** (D18/R4c): `build_config_fields_row`
    carries the new per-field application attributes (application-visibility, enum subset,
    application-required, `FieldFormat`) into the `config#fields` row 1:1; the write-time
    projection validator rejects an invalid subset entry or an unknown `FieldFormat.checker`
    (fail loud, no partial write); and a tenant authoring none of them projects
    back-compatible defaults. (Flask-plane tests, per the change-with-tests contract.)

## Success Metrics

- A prospective member can submit a valid application for an allow-listed tenant (via its
  path slug) with no account and no sign-in, and it appears to staff as an
  `application`-status member record for the correct tenant (Option 1, D1).
- A tenant's **all-scope** `Members_CRUD` users (or the member module's `TenantAdmin` when
  none) receive a bilingual "new application" email with a **deep-link** to review the
  applicant's member record behind auth (no PII in the email), sent as the tenant's own
  verified sender with a configured (or derived) Reply-To, for every successful submission
  that has recipients.
- The **applicant** receives a bilingual confirmation copy of their own submission at their
  own email address (no account needed).
- A double-click, retry, or in-session edit-and-resend yields **one** record; and an
  applicant whose **name + date of birth** matches an existing member is still accepted but
  **flagged for staff** as a possible duplicate (never auto-blocked, no enumeration leak) — D11/R3a/D25.
- The public form is built to **WCAG 2.2 AA**: config-generated Yup validation, server
  errors rendered through the same accessible Chakra fields by dotted key, a live-region
  error summary, and an axe-in-CI gate — with manual AT testing noted as the remaining
  verification step (D14/R10a).
- Every application is discoverable by staff in the **applications-inbox** (overview filtered
  to `status = application`) even if the email notification is delayed or never arrives — the
  inbox is the authoritative channel, email is a nudge (F3/R8b.4).
- Email-required and IBAN-mod-97-when-incasso are enforced server-side via the declarative
  `FieldFormat` registry, with `EMAIL` and `IBAN` as its first entries.
- Zero cross-tenant landings and zero privilege/field escalations are possible from the
  public path (verified by the tenant-invariant and sanitize tests).
- The whole flow (write + recipient lookup + send) executes in the SAM plane with no Flask
  call and no cross-account grant.

## Out of Scope

- **Provisioning** per-tenant verified SES sender identities (SES verification + DKIM/SPF
  DNS) — owned by Flask tenant onboarding / the tenant administration module (R9). This
  spec only consumes the configured sender.
- Extracting the reusable capabilities into `sam/shared/<capability>/` — deferred to the
  second consumer (event pre-application) per the rule of three (steering 35). Built
  members-local with module-agnostic seams now.
- A field-validator authoring UI (R7.8) — only the attribute, reader helper, registry, and
  enforcement step are in v1.
- Any Flask endpoint that writes the SAM member record, any SAM→Flask call for recipients
  or email, and any write to the Flask `email_log` MySQL table (boundary rule).
- Option 1 is chosen (D1), so there is no separate quarantine/import path and no distinct
  "application" concept — an applicant is a member record in `status = application`. A
  dedicated staff review/approve UI beyond the normal member list + a plain `status` field
  edit is not in v1. (`retire-members-status-lifecycle-engine`: status is edited as an
  ordinary field, not via a transition flow.)
- The alternative intake shapes (Option 2 DynamoDB quarantine, Option 3 S3-JSON import)
  from the analysis — not built (D1).
- A **tokenized public application-status viewer** for applicants (a signed, expiring link
  that renders their application without an account) — a possible future follow-up, NOT in
  v1. In v1 the applicant's channel is their confirmation email (R8a); staff review behind
  auth (R8b).
- A **member self-service portal** (see Future direction) — members signing in to view/edit
  their own record — is a separate future feature, not built here.

## Future direction (context — NOT v1 requirements)

These are recorded so the v1 design does not foreclose them; they are not committed scope.

- **Member self-service portal (Pool B).** The intended long-term answer to member/applicant
  web access: a member signs in with a **Pool B** account keyed to their **current email in
  the member table**, and self-serves a **subset of their own fields** — personal, address,
  financial, and selected member fields. This reuses THIS spec's field model directly: the
  per-field visibility selection (R4) and the flattening/un-flattening round-trip become a
  third renderer (self-service edit) over the same resolved field config, alongside the
  public application form and the staff overview. A likely **self-service visibility** marker
  (which fields a member may edit about themselves) is the sibling of the public-form
  application-visibility marker (R4.2). Building the application form's field model with that
  generality in mind keeps the portal a thin later addition rather than a rebuild.
- **Tokenized applicant status link.** If applicants later need to track status on the web
  before they have a Pool B account, the tokenized viewer above is the bridge; the
  self-service portal supersedes it once an approved applicant becomes a Pool B member.

## Open Questions (carried to `design.md`)

The analysis questions are now **decided** (see "Settled decisions" D1–D18). What remains
for design is mechanism detail plus one genuinely-open strategic question:

1. **Cross-plane sharing strategy (D7, open on purpose).** Within a plane the home is
   clear — shared between SAM modules lives in `sam/shared/`, shared between frontend apps
   in the frontend shared layer, shared in Flask in Flask. The unresolved question is what
   happens if something must be shared **across** planes (SAM ⇄ frontend ⇄ Flask), as the
   `projection_schema` vendored-into-layer trick hints at. v1 introduces NO cross-plane
   shared home and defers this; WHEN a real cross-plane sharer appears, a proper solution
   is designed then. (Until then: members-local seams, extract on the second same-plane
   consumer per rule of three.)

Mechanism detail for the settled decisions (design fixes the exact shape, not whether):

2. **`tenant-directory` allow-list backing store** for the path-slug → `tenant_id` resolver
   (D3) — where the slug allow-list lives and how a slug is registered at onboarding.
3. **Per-field application-visibility marker + enum-subset shape** (D6/R4/R4a) — the exact
   config attribute(s) that (a) select a field onto the public form and (b) carry an enum
   choice subset, as an extension of the existing field-definition / `options` model.
4. **`membership_type` not-selected path** (R11.3) — tenant-default stamp vs deferred
   reference check for keeping an application-status record catalog-valid.
5. **Send-log decision** (R8/R9) — a DynamoDB send-log item vs no persistent log (no MySQL
   `email_log` on the SAM plane); likely reuse of the members mail audit sink.
6. **Retention/purge** period + mechanism for never-actioned `application` records (R12.2).
7. **`TenantAdmin` role-segment confirmation** (D9/D24, R8.4/R9a.3) — confirm the exact
   projected role segment for the member module's tenant administrator (`TenantAdmin` vs the
   `members:admin` capability holder) used for the recipient + Reply-To fallback. (The Reply-To
   single-pick tiebreak is GONE — D24 uses the whole all-scope set, no ordering needed.)
8. **Duplicate-flag normalization detail** (D25/R3a.5–R3a.8) — RESOLVED mechanism: match on
   **name + date of birth** via a **GSI** on `(tenant_id, name+dob)`, flag-only, neutral
   response. Remaining detail: the exact normalization of the composite key (name trim/case-fold,
   date canonicalization) and the GSI projection. Behaviour is settled.
9. **Hard email-uniqueness is a deferred members-core DEPENDENCY, not this spec** (D11) —
   IF the platform later wants a true write-time constraint (not just a flag): reintroduce
   the guard s5k removed (`email#<normalized>` conditional item vs GSI), enforce it on the
   AUTHENTICATED create/update paths too, and reconcile pre-existing backfilled duplicates
   first. Tracked here as the related future work; an s5k-owner sign-off / ADR note applies.
10. **Consent-notice storage shape** (D26/F4/R12.1a/R12.1c) — RESOLVED ownership: the notice is
    **tenant-authored + versioned**, projected via Flask tenant config (R4c). Remaining detail:
    exactly which projected row carries the notice text+version (`config#mail` sibling vs a new
    `config#notice` row) and the stored-consent shape on the record (a structured `consent{}`
    object — recommended — vs a keyworded `additional_info` entry). Behaviour is settled.
