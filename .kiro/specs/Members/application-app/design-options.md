# Member Application Form (public applicant intake) — Design Options

## Problem

A prospective member has no way to apply themselves. Today a member record is
only ever created by an authenticated staff member through the gated SAM members
edge (`POST /members`, capability `members:write`, tenant from the verified
token + `X-Tenant`). We want a **public, unauthenticated** application form a
would-be member can fill in without signing in and without any Pool A account,
which lands a member record in the correct tenant with status **applicant**
(`application`) and notifies that tenant's `Members_CRUD` users by email so they
can review and approve it.

Concretely the ask is:

- A form that renders **all functional field groups except the membership-admin
  group**, in the **same functional grouping** the staff member UI uses
  (personal / address / financial), so an applicant supplies who they are — not
  the back-office fields (member_number, status, created/updated).
- **Public access** — no Pool A, ideally no sign-in at all.
- The record is written to the member store with `status = application` under the
  **correct tenant**.
- The tenant's `Members_CRUD` users get an email that a new application arrived.
- **Critical fields validated:** email (present + well-formed), and IBAN
  (ISO 13616 mod-97) **when incasso / direct-debit is the chosen payment method**.

## Operational surface — what it takes to RUN this, not just the code

**A design option is everything needed to get a working application, not the code
alone.** Each option below carries a non-code surface — DNS, SES identity, IAM,
API Gateway / WAF, deployment wiring, and an onboarding-protocol step — and every one
of those is a first-class deliverable with an **owner** (which plane/module provides
it), not a footnote. If any is missing the feature does not run even with perfect
code. The table is the checklist `design.md` must close for the recommended option;
it also makes explicit that several items are **owned outside this spec** (notably by
Flask tenant onboarding), which this spec DEPENDS ON rather than builds.

| Deliverable | What it is | Owner / plane | Status |
| --- | --- | --- | --- |
| **Per-tenant verified SES sender** | Verify the tenant's domain/address in SES + **DKIM/SPF DNS**; a tenant sends **as itself** (NOT `support@jabaki.nl`, which is the platform *onboarding* sender) | **Flask tenant onboarding / tenant administration module** (SES is generic → a reusable onboarding capability) | **Dependency — not built here**; blocks real sends until provisioned |
| **Tenant sender config readable in-plane** | Where SAM reads a tenant's configured sender (e.g. a tenant-config projection row) so the notifier sets `From:` without a Flask call | Flask writes it (onboarding) → projection; SAM reads it | Open: storage location (see Q5) |
| **SES send IAM grant** | `ses:SendEmail` on the SAM notifier (data account), scoped to the tenant's verified identity | This spec — SAM `template.yaml` | New |
| **S3 quarantine bucket (Option 3) — locked down** | Private bucket, **Block Public Access ON**, ACLs disabled, SSE, TLS-only + deny-all-except-roles bucket policy, versioning, lifecycle expiry; **Lambda-mediated write only** (`s3:PutObject` on the public Lambda role scoped to `applications/<tenant_id>/*`; `s3:GetObject`/`Delete` on the import role) — the browser never touches S3 | This spec — SAM `template.yaml` | New (Option 3 only) |
| **Projection read IAM grant** | `dynamodb:Query` on `GOVERNANCE_PROJECTION_TABLE` for the `role-recipients` read (members function already has this grant) | This spec — reuse existing grant | Exists |
| **Public route + skip-auth** | API Gateway route NOT behind the Cognito `DefaultAuthorizer`; edge special-case to skip `_authenticate_and_authorize` | This spec — SAM `template.yaml` + `handler/app.py` | New |
| **Abuse hardening** | API Gateway throttle/usage plan + **WAF** (rate-based, optional CAPTCHA) + honeypot field + payload cap + CORS | This spec — SAM `template.yaml` + handler | New (greenfield in SAM) |
| **Tenant allow-list (public tenant carrier)** | The `tenant-directory` backing store that maps a public slug/subdomain → `tenant_id`, verify-before-trust | This spec — shared SAM service + its data source | Open (see Q4) |
| **Email template(s)** | Bilingual (nl/en) "new application" template the `notification` service renders | This spec — SAM | New |
| **Send-log decision** | DynamoDB send-log item vs no persistent log (SAM has no MySQL `email_log`) | This spec — SAM | Open (see Q5) |
| **Deployment wiring** | New params (public-route stage, WAF, sender-config source) threaded through `template.yaml` + the layer build | This spec — SAM | New |
| **Frontend form app** | The public SPA/page that fetches the public field-config and submits (where it is hosted, its domain, its CORS origin) | This spec — frontend | New |

The point of the table: the **SES/sender-identity item is not a loose open question —
it is one row of the operational surface, and it is OWNED by Flask tenant onboarding.**
This spec consumes it. The rows marked "This spec — SAM" are what Option 1/2 must
actually deliver to run; the rows marked "Dependency" must exist (via onboarding)
before a real send works, and `design.md` records that dependency explicitly rather
than discovering it at deploy time.

## Platform lens: generic SAM services, not a members feature

This form is **consumer #1 of a pattern the whole SAM platform will repeat**, not a
one-off members feature. The SAM stack is already declared as a multi-module, single
deployment — the `sam/README.md` names `members / events / webshop` modules sharing
`sam/shared/`, and every module is **multi-tenant**. Coming work (a pivot framework,
user-selectable table columns, a webshop frontend on a SAM backend, event
administration with a calendar and **event pre-application**) will hit the exact same
needs this form hits. A webshop checkout and an event pre-application are both
"public/unauthenticated intake → land a tenant-scoped record → notify a role," which
is precisely this feature. So the design goal is: **build the reusable services once,
make the members application their first caller**, and avoid a members-specific
solution that every later module has to copy.

### What is shared today vs. what must be lifted out

Only **auth** is shared today. `sam/shared/` holds JWT/JWKS verification and the pool
registry (`auth_utils.py`, `_verifier.py`, `_jwks.py`, `_pool_registry.py`,
`entitlement_claim.py`) — nothing else. Everything this feature needs beyond auth
currently lives **inside a module** (`sam/members/` or `sam/pretokengen/`) and would
be copy-pasted by the next module unless promoted:

- **Tenant resolution at the edge** — `members/handler/app.py::_establish_tenant_context`
  is members-specific (token `tenant_keys` + `X-Tenant`). The **public** variant
  (allow-list slug → tenant) this feature needs does not exist anywhere and should be
  built as a shared edge concern, not a members function.
- **Routing / HTTP edge** — `members/handler/{app,router,routes,_dispatch,_http}.py`
  is per-module. A second module repeats this skeleton; the reusable parts (method/path
  match, error→HTTP mapping, the public-vs-gated route distinction) belong in a shared
  edge toolkit.
- **The governance projection — shared SCHEMA, per-module READERS.** Correction: the
  reusable asset is **`services.projection_schema`** (key shape + `split_sort_key` +
  table resolver), whose source lives in `backend/src/services/projection_schema.py`
  and is **vendored into each SAM function's Lambda layer at build time** (layer
  Makefile `cp projection_schema.py`). The **readers are NOT shared**: `pretokengen`
  is a standalone function with its own private reader
  (`projection_governance_reader.py`, reads `role#*`/`module#*`), and `members` has
  its own (`projection_config_reader.py`, reads `config#*`/`scopegrant#*`). So "who
  holds role R for tenant T, with their email" (`role#<email>#<role>`) has **no shared
  reader today** — this feature builds the first one. That is the generic
  `role-recipients` service: a NEW thin reader over the shared schema, placed in a
  shared SAM home so events/webshop reuse it rather than re-implementing per module.
- **Repository / table-design conventions** — `members/repository/table_design.py`
  encodes the tenant-PK + `record_type#id`-SK pattern (Property 1 structural
  isolation). Events/webshop records will want the identical convention; the key-shape
  helpers and the float→Decimal / build-item plumbing are candidates for a shared
  repository base.
- **SES notification** — greenfield everywhere (no `send_email` under `sam/`). Build it
  **once** as a shared `notification` service (resolve recipients via the new
  `role-recipients` reader + send via SES **as the tenant's own verified sender** +
  optional DynamoDB send-log), parameterized by tenant, role, template, and locale — so
  members-application, event-pre-application, and webshop-order-received all call the
  same service with different templates. **Note:** the per-tenant verified SES *sender
  identity* is NOT provisioned here — it is a tenant-onboarding capability owned by the
  Flask tenant administration module; this service only *consumes* the configured
  sender (see "Sender identity" under Option 1).
- **Public-write abuse hardening** — greenfield in SAM. The throttle/WAF/honeypot/CORS
  package is identical for every public intake endpoint; it belongs in the shared edge
  + the deployment template, applied by any module that declares a public route.
- **Field model (fixed ⊕ overlay) + validation chain** — members-specific in content,
  but the *shape* (fixed registry + per-tenant overlay resolved from the projection
  `config#fields` row, with required/enum/`show_when` gates) is a pattern events/webshop
  forms will mirror. The **validators themselves** (email, IBAN mod-97) are fully
  generic and should live in a shared validation module from day one.

### The reusable services this feature should establish

Framed as services with the members application as first consumer:

1. **`tenant-directory` / public tenant resolver (shared)** — allow-list a public
   caller's tenant slug/subdomain → canonical `tenant_id`, verify-before-trust. Used by
   every public intake (members application, event pre-application, webshop).
2. **`role-recipients` service (shared)** — given `(tenant_id, role)`, return the
   emails from the governance projection's `role#<email>#<role>` rows. Generic directory
   lookup; members passes `Members_CRUD`, events passes `Events_CRUD`, etc.
3. **`notification` service (shared)** — `(tenant_id, role, template, locale, context)`
   → resolve recipients (service #2) → render → SES send → best-effort, non-blocking,
   optional DynamoDB send-log. One SES integration for all modules.
4. **`public-intake` edge toolkit (shared)** — the public-route declaration + the
   abuse-hardening package (throttle/WAF/honeypot/CORS) + the "skip auth, resolve tenant
   from slug" edge path. Any module adds a public endpoint by using this, not by
   re-coding the edge.
5. **`validation` module (shared) — a validator REGISTRY keyed by a declarative field
   attribute.** A field in the config carries an optional `format` token (`EMAIL`,
   `IBAN`, `DATE`, `PHONE`, …); the registry maps each token to a pure
   `(value) -> FieldError | None` checker; the domain runs it generically for any field
   that declares one, gated by the field's `show_when`. `EMAIL` + `IBAN` are the first two
   entries, built now; the seam makes "attach a checker to a field" config, not code — for
   any field, tenant, or module. (Generalizes the existing per-field `MemberNumberFormat`
   precedent.)
6. **`repository-base` conventions (shared)** — the tenant-PK + `record_type#id`-SK key
   helpers and item-build plumbing, so events/webshop get Property-1 isolation for free.
7. **`config-driven form` renderer (shared, frontend + a public field-config read)** —
   a form that is a pure projection of a module's resolved field config: group by
   `functional_group`, render one input per `ResolvedField` (`type`/`label`/`choices`/
   `show_when`/`required`), flatten for the UI, un-flatten to the nested record shape on
   submit. Members derives it from `config#fields`; events/webshop point the same renderer
   at their own field config. This is the SAME field model + flattening concept the member
   overview already uses — the intake form and the overview table are two renderers over one
   config, so they never drift.

Items 2, 3, 4, 5 are the ones the application form directly needs; building them as
shared services (rather than members internals) is the whole point of this lens. The
two options below are therefore described **both** as a members feature **and** in
terms of which shared services they stand up.

### Sequencing — RULE OF THREE, per steering 35 (CORRECTION)

An earlier draft recommended "build the shared services up front." **Steering
`35-sam-module-architecture-sam.md` governs this and says the opposite**, so the doc
is corrected to follow it:

> *"Build per-module first; extract on the SECOND consumer (rule of three). Do not
> build the `sam/shared/<capability>/` abstraction while there is one consumer. Write
> the first module's implementation in module-agnostic files with a clean seam … the
> second module that needs it … triggers the extraction."*

So the correct stance is **members-first with clean seams, extraction deferred to the
second consumer** (event pre-application), NOT shared-first:

- Build each capability (public-intake edge, `role-recipients`, `notification`,
  `validation`, config-driven form) **inside `members/` (or its own module file) with a
  module-agnostic signature and NO members-specific logic in the seam** —
  parameterized by tenant, role, template, field-config source.
- Do **not** create `sam/shared/<capability>/` now. When event pre-application (the
  roadmap's next intake) arrives, that second consumer triggers the extraction into the
  shared library, with both modules then consuming it.
- This also respects rule 5a / the "CODE shared, DATA per-module" rule: each module
  persists via its **own** repository + table; only mechanism is ever shared, never a
  store.
- Genuinely members-specific pieces (fixed-field *content*, the `membership_type`
  catalog) stay in `members/` permanently.

The platform-lens inventory above therefore lists these as **future-shared, built
members-local-with-a-seam today** — the services the extraction will later lift, not
services to build shared on day one. (This resolves open question #2 **against** the
earlier shared-first recommendation.)

## The hard constraint: NO Flask⇄SAM boundary mix

**The feature must be built entirely within the SAM plane.** The member record is
a DynamoDB item owned by the SAM/Lambda module (`sam/members/`, data account
`nonprofit-deploy`). The Flask/MySQL plane (`backend/src/`, identity account
`personal`) must not participate in creating that record, and the SAM plane must
not reach into Flask to do its work. That rule is the single biggest driver of
this design, so its impact is spelled out here before the options.

### What the rule rules OUT

- **A public Flask endpoint that writes the member record is forbidden.** Flask
  writing SAM-owned DynamoDB data (even via the SAM repository/table-design
  builders) is a boundary mix by definition. This removes the "mirror
  `signup_routes.py` and write DynamoDB from Flask" shape entirely — it is not an
  option, so it is not listed below.
- **The notification cannot call Flask.** The convenient
  "SAM emits an event → a small internal Flask endpoint does the Cognito lookup +
  SES send" is out: it couples SAM to Flask. SAM must resolve recipients and send
  mail using only its own plane and direct AWS-service calls.
- **SAM cannot log the send to the Flask `email_log` table.** `SESEmailService`
  logs every send to a **MySQL** table in the Flask plane. SAM has no MySQL
  connection (S1 contract: a module Lambda never opens a MySQL connection), so the
  SAM path cannot write that table. The unified-email-audit story breaks along the
  boundary — SAM either forgoes send-logging or keeps its own DynamoDB log.

### What the rule FORCES the SAM plane to own

Everything the feature needs becomes SAM-native. The good news (verified below) is
that the two pieces that *looked* Flask-only — recipient lookup and email — can
both be satisfied without crossing the boundary:

1. **Recipient resolution from the governance projection SAM already reads
   (NO Cognito, NO Flask, NO cross-account grant).** The S3 governance projection
   (`sam/pretokengen/.../projection_schema.py`,
   `projection_governance_reader.py`) stores per-tenant role rows keyed
   `role#<email>#<role>` — the schema's own example is literally
   `role#a@b#Members_CRUD`. So for a tenant, SAM issues one DynamoDB `Query` on the
   tenant partition, keeps the `RECORD_TYPE_ROLE` items whose role segment is
   `Members_CRUD`, and **the recipient email is the first id segment of the sort
   key**. This is the same projection, same data account, same read pattern the
   pre-token-gen reader already uses — recipient resolution stays 100% in-plane.
   (The MySQL `user_tenant_roles` → projection sync that populates these rows is
   Flask-plane, but that already exists and runs independently; the application
   feature only *reads* the projection, never triggers or depends on the Flask
   sync at request time.)
2. **SES called directly from the SAM plane (SAM→AWS, not SAM→Flask).** Sending
   mail via SES is an AWS-service call, not a Flask dependency — SAM gets its own
   `ses:SendEmail` IAM grant in the data account and its own verified sender
   identity. SES is **greenfield in SAM today** (no `send_email` anywhere under
   `sam/`), so this is new code, not reuse of `SESEmailService`. That means the
   SAM plane must own: the sender/verified-domain config, the (small, bilingual)
   application-notification template, and a decision on send-logging that does not
   reach MySQL (log to a DynamoDB email-log item, or accept no persistent send log
   in v1).
3. **Abuse hardening native to SAM.** Flask's `@limiter` / honeypot / CSRF and the
   `before_request` skip cannot be borrowed. SAM must harden the public write with
   API Gateway throttling + usage plan, a WAF (rate-based rule / optional CAPTCHA),
   a honeypot field + payload-size cap in the handler, and tight CORS.
4. **The public route, edge exception, validators, and `create_application`
   service** — all SAM-side regardless (see Option 1); the rule simply confirms
   there is no Flask half to lean on.

### Net impact

The boundary rule **collapses the solution space to SAM-only shapes** and
**moves the notification machinery (recipient lookup + SES) into the SAM plane**,
sourced from the governance projection rather than Cognito/Flask. It does **not**
make the feature impossible or require a cross-account Cognito read — the
projection already carries `Members_CRUD` emails per tenant. The real costs it
imposes are: (a) building SES + a template + an email-log decision inside SAM where
none exist, (b) building abuse controls in SAM where none exist, and (c) losing the
single Flask `email_log` audit for these sends. The remaining open question it
sharpens is **sender identity / deliverability** — which verified SES identity and
domain the SAM plane sends as, independent of Flask's `support@jabaki.nl`.

## Other architectural facts that shape every option

- **The applicant's fields are DERIVED from the field-config projection, not
  hand-picked.** This is the same model the member overview uses, and it is already
  built SAM-side. The tenant's field config lives in the governance projection's
  **`config#fields`** row; the SAM plane already reads it via
  `members/repository/projection_config_reader.py` (a `TenantOverlayProvider`),
  which `FieldResolver` merges over the platform fixed base to produce the
  **resolved field set** — the exact shape `GET /members/field-config` serves. Each
  `ResolvedField` (`field_resolver.py`) already carries everything a form generator
  needs: `functional_group` (the display grouping), `type`, `required`, `label`
  {nl,en}, `choices`/`options`, `show_when` (conditional visibility), `visible`,
  `order`, `read_only`, and `group` (the storage bucket `personal`/`membership`/
  `overlay`). So the applicant form is a **pure projection of the resolved field
  config**, grouped by `functional_group`, with the `membership`-admin storage group
  filtered out. IBAN / payment_method / incasso are overlay fields and appear
  automatically wherever the tenant configured them (e.g. a `financial` functional
  group) — no separate hand-maintained list. **Likewise the `motor` functional group**
  (h-dcn's motor-type overlay fields) **must appear on the application form** (review):
  because the form renders every functional group except the `membership`-admin group,
  `motor` is in scope automatically — it is the proof that "all functional groups except
  membership" already includes the tenant's overlay groups (personal / address /
  financial / **motor**), with no per-group code. This sharpens one sub-question: what
  marks a field/group as **shown on the public application form** vs. staff-only (a
  `public`/`application`-visibility flag on the field config, distinct from the
  overview's `visible`).
- **"Flattening" is how nested fields become normal form fields.** On the overview,
  nested storage buckets (`personal.*`, `overlay.*`) are flattened to flat top-level
  keys so the generic table engine treats them as ordinary columns (the overview's
  `flattenMember` / `valueFor` concept — see
  `member-field-search/design-options.md`). The application form uses the same
  concept in reverse: it renders one input per resolved field keyed by its
  `dotted_key()` (`personal.first_name`, `overlay.iban`, …), and the submission is
  un-flattened back into the nested `{personal:{}, membership:{}, overlay:{}}` member
  shape the create path expects. One field model, flattened for the UI, nested for
  storage — identical to the overview, so the form and the table stay in lockstep
  with the tenant's config with zero duplication.
- **"Applicant" is the `application` status.** `MembershipStatus` is a closed
  enum (`application, pending, active, suspended, lapsed, left`); the applicant
  state is `application` ("Aanmelding") and is already the lifecycle **initial
  state**. `MembershipService.create_member` already defaults `status` to the
  tenant's initial state when the body omits it.
- **Tenant is never client-trusted today.** The SAM edge
  (`handler/app.py::_establish_tenant_context`) derives the active tenant from the
  verified token's capability-scoped `tenant_keys`, with `X-Tenant` only
  *selecting* among already-verified tenants. A public applicant has **no token
  and no `tenant_keys`**, so a public path must carry the tenant another way — and
  that way must be **verify-before-trust** (an allow-list of known tenant slugs),
  never a raw client value that could land a record in an arbitrary partition.
- **No IBAN validation exists.** The `iban` references in the Flask plane only
  read a *tenant's own* bank account for invoicing/banking — there is no reusable
  applicant-IBAN format/checksum validator. A mod-97 check is new SAM-side code.
- **The public-endpoint precedent is Flask-only.** `signup_routes.py` (trial
  signup) is "No JWT auth required. Protected by rate limiting, honeypot, and
  CSRF." It is a useful *pattern* to copy conceptually, but under the boundary rule
  its code can't be reused — the SAM plane reimplements the equivalent hardening.

## Shared constraints (apply to every option)

- **Server is authoritative; the public form is trusted for nothing** (R2.3). The
  endpoint **forces** `status = application` and strips any client-supplied
  `tenant_id` / `member_id` / `status` — mirroring `_sanitize_write_payload` and
  the authoritative-tenant stamp already in `create_member`.
- **Tenant resolves from an allow-list**, never a free client value. Whatever
  carries the tenant (path slug, subdomain, signed form token) is checked against
  a known-tenants set before any write — the public analogue of
  "select among verified tenants, never grant one" (Property 2).
- **Fields are derived from the tenant's resolved field config** (the `config#fields`
  projection row → `FieldResolver`), rendered grouped by `functional_group` with the
  `membership`-admin storage group filtered out. The form never carries a
  hand-maintained field list — it reflects whatever the tenant configured, exactly
  like the overview.
- **Reuse the existing SAM validation chain.** `validate_fixed_fields` + the
  overlay gates (`_validate_required_overlay_fields`,
  `_reject_invalid_overlay_enum_values`, `member_number` format) already run inside
  the create path; the public path adds only the two **critical** validations on
  top — required+format email, and IBAN mod-97 **conditional on incasso** — rather
  than re-implementing field validation.
- **An unauthenticated write must be abuse-hardened**, SAM-side (see the boundary
  section): throttle + WAF + honeypot + payload cap + CORS. Non-negotiable for a
  public POST.
- **Email is required for an applicant** even though the platform keeps `email`
  optional on a member record. An application submitted by a human needs a reply
  address, so the public path tightens `email` to required+valid — a public-path
  rule, not a change to the fixed-field registry.
- **The notification never blocks the write.** A failed/slow SES send must not
  fail the applicant's submission — the member record is the source of truth; the
  email is a best-effort side effect (ideally offloaded, see Option 1's async
  note).

---

## Option 1 — Public intake via shared SAM services; members is the first consumer

Add a deliberately public route — e.g.
`POST /public/members/{tenant_slug}/applications` — that stands up the shared
`public-intake` edge toolkit (skip-auth + allow-list slug→tenant + abuse
hardening) and calls a thin members `create_application()` which forces
`status = application`, accepts the **config-derived field set** (the tenant's
resolved field config grouped by `functional_group`, minus the `membership`-admin
group — see "fields are derived from the field-config projection" above), and runs
the existing validation chain plus the shared email + IBAN validators. On success it calls the shared `notification`
service `(tenant, "Members_CRUD", template, locale)`, which resolves recipients via
the shared `role-recipients` projection read and sends via a shared SES client —
all **within the SAM plane**, never Flask.

The members-specific parts (the field subset, the `membership_type` handling, the
`create_application` method) stay in `members/`; the tenant resolver, abuse
hardening, recipient lookup, SES send, and the email/IBAN validators are built in
`sam/shared/` with module-agnostic signatures so event-pre-application and webshop
are later thin callers.

- **Mechanism:** one new `RouteSpec` + an edge special-case for the public path +
  a new service method beside `create_member`. The member record is written by
  the module that owns it (single `PutItem` via `save_member`). The notification
  reads the tenant's `role#<email>#Members_CRUD` rows from the projection and
  calls SES directly — no cross-plane hop at all.
- **Pros:** fully satisfies the boundary rule — the whole flow (write + resolve
  recipients + send) lives in one plane and one account. The member record stays
  in its **canonical** store with the proven create invariants (tenant-stamp,
  uuid4 mint, initial-status default, catalog check, full validation). No
  duplicated member model, no cross-account Cognito grant (recipients come from
  the projection SAM already reads).
- **Cons:** introduces the **first** unauthenticated route in the SAM module — the
  "deny without a verified token" edge invariant now has a documented, carefully
  fenced exception. SES, an email template, and an email-log decision are
  **greenfield in SAM**. Abuse controls (throttle/WAF/honeypot) are new in SAM.
  The send has no Flask `email_log` audit (own DynamoDB log or none).
- **Shared services it stands up:** `public-intake` edge toolkit, `tenant-directory`
  resolver, `role-recipients`, `notification` (SES), and the `validation` module —
  every one reused as-is by event pre-application and webshop intake. Members adds
  only `create_application` + its field subset on top.
- **Operational surface it must deliver (not code):** the SAM-owned rows of the
  Operational-surface table — public route + skip-auth, abuse hardening (throttle/WAF/
  honeypot/CORS), `ses:SendEmail` IAM grant, email template(s), deployment wiring, and
  the public frontend form — PLUS the standing **dependency** on Flask onboarding
  having provisioned the tenant's verified SES sender. The code is ready to run only
  when these are in place.
- **Assessment:** the natural and now effectively **mandatory** shape under the
  boundary rule, and the one that leaves behind reusable platform services rather
  than members internals. The projection-sourced recipient lookup is what makes it
  clean rather than forcing a cross-account Cognito read. Recommended primary.

### Reality check — where the create invariants live (why we reuse, not re-insert)

`create_member` (`_membership_writes.py`) is not a thin insert — it is a sequence
of **authoritative** steps `create_application` must preserve:

1. `_sanitize_write_payload(body)` — strip client `tenant_id` / PK / `member_id`
   (verify-before-trust, Property 2).
2. stamp authoritative `tenant_id`; mint `member_id = uuid4()` server-side.
3. default `membership.status` to the tenant lifecycle **initial state**
   (`application`) when the body omits it — exactly the applicant state we want.
4. `_validate_member_record` → `validate_fixed_fields` + overlay required/enum
   gates + `member_number` format + the tenant `validate_member` hook.
5. `_validate_membership_type_reference` — the member's `membership_type` must
   reference a **live** catalog entry (C8); the dropdown is convenience only.
6. `_reject_invalid_overlay_enum_values` — overlay dropdowns enforced on create.
7. `save_member` — a single `PutItem`.

`create_application` should REUSE this spine (force `status=application`, add the
email + IBAN checks, restrict to the config-derived field set) rather than open a
second write path — the same "don't duplicate the authoritative layer" rule that
keeps every member write funneled through the domain service.

### The `membership_type` tension (membership field — needs careful definition)

**Review flag:** `membership_type` is a **membership-admin field** and its handling
must be defined deliberately, not waved through. Two facts frame it:

- It is a **required**, catalog-referenced fixed field in the `membership` group.
  The create path enforces referential integrity via
  `_validate_membership_type_reference` — a staff-set `membership_type` must point at
  a **live** entry in the tenant's Lidmaatschap Beheer catalog (design C8); the
  dropdown the staff UI shows is convenience only, never trusted (the server
  re-checks the value against the live catalog). *(This is the sentence flagged as
  unclear in review: the rule exists so a client cannot persist a membership_type
  that does not actually exist / is retired in the tenant's catalog.)*
- The application form **excludes the entire `membership` group**, so by default the
  applicant never supplies `membership_type` at all — which is consistent with it
  being a back-office classification.

Because the form omits it, the real question is what the **applicant record** carries
for `membership_type` while it is in `status = application`, and when/who sets it:

- **(a) Applicant chooses** from the tenant's live, *public-safe* catalog entries —
  needs an unauthenticated public catalog read + filtering of staff-only options, AND
  it contradicts "exclude the membership group" (we'd have to re-admit one membership
  field to the form). Only if a tenant genuinely wants applicants to pick a tier.
- **(b) Omit on application, set on approval** — relax the required-on-create rule
  **for `status = application` only**; a staff member assigns the (catalog-validated)
  type at the `application → pending/active` transition. Keeps the form to
  identity/contact/financial/motor.
- **(c) Tenant default** — onboarding configures a default application
  membership_type that is stamped server-side so the record is always
  catalog-valid even while an applicant.

Recommendation **(b)**, with **(c)** as the mechanism that keeps the record
catalog-valid in the meantime (a configured default stamped on create, overwritten by
staff on approval). This needs its own treatment in `design.md`: the exact
required-ness relaxation (scoped to the application status), whether the
`_validate_membership_type_reference` check is deferred or satisfied by the default,
and the approval-time assignment. **Flagged as an open design item — not settled
here.**

### Recipient resolution — a NEW thin reader over the shared projection schema

**Correction (what is actually shared):** `pretokengen` is **not** a shared library —
it is its own standalone SAM function with its **own private** reader
(`projection_governance_reader.py`) that reads `role#*` / `module#*` rows for *its*
job (token issuance). The members module likewise has its **own** reader
(`projection_config_reader.py`) for `config#*` / `scopegrant#*`. **What is shared is
the projection *schema*** — `services.projection_schema` (key shape + `split_sort_key`
+ table resolver), whose source lives in `backend/src/services/projection_schema.py`
and is **vendored into each SAM function's Lambda layer at build time** (see the layer
Makefile's `cp projection_schema.py`). So there is **no existing shared reader to call**
for `Members_CRUD` recipients — this feature adds one.

For tenant `T`, the notification step (a new reader built with the shared schema):

1. `Query` the projection partition `tenant_id = T` on the fail-fast
   `GOVERNANCE_PROJECTION_TABLE` (same table + key helpers; a new, thin read).
2. Keep items where `split_sort_key(sk)` is `("role", (email, role))` and
   `role == "Members_CRUD"` (`RECORD_TYPE_ROLE`).
3. Collect the `email` id-segment of each — that is the recipient list.
4. Hand the list to the shared `notification` service, which sends **as the tenant's
   own verified sender** (see "Sender identity" above), `email_type="member_application"`.

No Cognito call, no Flask call, no cross-account grant. A tenant with zero
`Members_CRUD` rows yields an empty list → the record is still created, and the
"no recipients" case is logged for staff follow-up (never fails the applicant).

This is exactly the generic **`role-recipients` shared service** from the platform
lens: `(tenant_id, role) → emails`, built once here (members is first to need the
`role#*` read for notifications), reused by events (`Events_CRUD`) and webshop. It
belongs in a shared SAM home, not inside `members` — see the open question on where
new shared SAM services live.

### Sender identity — a TENANT's own sender, provisioned by onboarding (NOT this spec)

**Correction (review):** `support@jabaki.nl` is the **platform→tenant onboarding**
sender; it is **not** used to send a tenant's own mail. A notification to a tenant's
`Members_CRUD` about a new application is the **tenant emailing itself**, so it must
go out **as that tenant's own verified sender**, not as the platform.

That makes sender identity **out of scope for the application form** and **in scope
for tenant onboarding / the tenant administration module**:

- **Provisioning the identity** (verify a tenant's domain or address with SES, set up
  DKIM/SPF DNS) is a **tenant onboarding** step and lives in the **Flask** plane with
  the rest of onboarding — exactly where tenant setup already happens. SES is a
  generic AWS service, so a per-tenant "verified sender" is a reusable onboarding
  capability the **tenant administration module** should own, used by any module that
  emails on a tenant's behalf (members application, event pre-application, webshop
  order confirmations).
- **Consuming the identity** is all the SAM application feature does: the shared
  `notification` service looks up the tenant's configured sender (its verified
  SES identity, from tenant config the SAM plane can read — e.g. a tenant-config
  projection row) and sends `From:` that address. If a tenant has no verified sender
  configured yet, the send degrades gracefully (logged "no sender for tenant T",
  never blocks the applicant write) — the record is still created.

This keeps the boundary rule intact: **Flask onboarding provisions** the per-tenant
SES identity (config + DNS); the **SAM notification service consumes** it at send
time. The application spec depends on that onboarding capability existing, but does
not build it. Open items this leaves: (a) where the per-tenant verified-sender config
is stored so SAM can read it in-plane (tenant-config projection row vs a SAM tenant
table), and (b) the fallback when a tenant has not yet verified a sender.

## Option 2 — Decoupled intake: capture now, create member on staff approval

The public form does **not** create a member record. It writes a lightweight
**application** item (its own `RECORD_TYPE_APPLICATION` in the tenant partition),
notifies `Members_CRUD` (same projection-sourced SAM-side send as Option 1), and a
staff member **reviews then promotes** it into a real member via the existing
authenticated `create_member`. The applicant becomes a real member only at
promotion. Everything still lives in the SAM plane — the decoupling is *within*
SAM, so it respects the boundary rule just as Option 1 does.

- **Mechanism:** a public write to a *separate* application record (easy to
  rate-limit, quarantine, and purge), plus a staff-side review queue that, on
  approve, calls the normal gated `create_member`. No public writer ever touches
  the member record itself.
- **Pros:** the member record is **only ever written by the authenticated gated
  path** — the SAM edge invariant stays fully intact, no public crack in the
  member-write path. Natural anti-abuse boundary (spam lands in quarantine, not
  among real members). Clean home for review metadata, GDPR/consent capture, and
  an audit trail. Staff get an explicit approve/reject workflow instead of raw
  `application`-status rows mixed into the member list.
- **Cons:** more to build — a new record type, a review/approve UI, and the
  promotion wiring — the largest option. Introduces a second concept
  ("application" ≠ "member"); the user's stated intent is specifically that the
  application **lands in the member table with status applicant**, which this
  option defers until approval. Carries the same SAM-side SES/abuse greenfield
  cost as Option 1.
- **Shared services it stands up:** the SAME five as Option 1 (`public-intake`,
  `tenant-directory`, `role-recipients`, `notification`, `validation`) PLUS a shared
  **intake/review record pattern** — a generic `record_type#id` "pending submission +
  promote-to-canonical" shape that is arguably even MORE reusable for events (event
  pre-application is literally this) and webshop (order → fulfil). The review/approve
  surface would want to be generic too.
- **Assessment:** the most defensible long-term (keeps the member write path
  closed; best for GDPR/audit/anti-spam), fully boundary-compliant, and it produces
  the most reusable platform asset (the intake-then-promote pattern that event
  pre-application reuses directly) — but it diverges from the literal ask and is the
  biggest lift. Right answer if review/consent/audit become first-class; heavier than
  needed if the goal is simply "applicants appear as `application` rows for staff to
  action."

## Option 3 — S3-JSON intake: public write lands as a file, staff IMPORT into members (the safest)

The public form does **not** write to DynamoDB at all. It serializes the submission
to a **plain JSON object in an S3 quarantine bucket** (one key per application, e.g.
`applications/<tenant_id>/<uuid>.json`). An **S3 event** then notifies the tenant's
`Members_CRUD` ("a new application is waiting — review & import"); a staff member
reviews the JSON and **imports** it into `members` through the existing
authenticated import path, which stamps `status = application`. The public endpoint's
*only* capability is "put a JSON file in a bucket." This is the user-proposed
"store the response in an S3 unit as JSON and trigger an action for the member to
import the JSON record."

- **Mechanism:** public Lambda validates (email/IBAN + field-config shape) and
  `PutObject`s the JSON to the quarantine bucket — **no DynamoDB grant on the public
  function at all**. An S3 `ObjectCreated` event (or a stream/queue) fires the
  projection-sourced `Members_CRUD` notification. Promotion is the authenticated
  import reading the JSON and writing the member record (status forced to
  `application`).

- **The S3 write is LAMBDA-MEDIATED and least-privilege — NOT an open bucket (best
  practice, review).** "Store in S3" must never mean a world-writable bucket. The
  bucket is fully private and the **only** writer is the public intake Lambda's
  execution role:
  - **Browser never touches S3.** The applicant POSTs the form to API Gateway → the
    Lambda; the **Lambda** does the `PutObject`. The applicant gets no S3 credentials
    and no bucket path. (We deliberately do NOT hand the browser a pre-signed PUT URL:
    that pattern suits large direct uploads, but for a tiny JSON form it hands a
    time-boxed credential to an untrusted client for no benefit — the payload fits in
    the request body, and a single Lambda choke point is where validation + honeypot +
    size cap + WAF/throttle all apply BEFORE anything lands in the bucket.)
  - **IAM:** only the public Lambda role has `s3:PutObject`, scoped to the one bucket +
    key prefix (`applications/<tenant_id>/*`); only the import/promotion role has
    `s3:GetObject`/`s3:DeleteObject`. No other principal can read or write.
  - **Bucket hardening baseline:** S3 **Block Public Access = ON** (all four),
    bucket-owner-enforced / **ACLs disabled**, default **SSE encryption**, a bucket
    policy that **denies all except the two roles** and denies non-TLS requests
    (`aws:SecureTransport=false`), versioning on, and **lifecycle expiry** auto-purging
    un-promoted applications (the GDPR retention control). No cross-account, no public
    read/list.
  - This is what makes Option 3 "safe": the public surface is a validated Lambda that
    may only append a file to one private prefix — not direct, unauthenticated S3
    access.
- **Pros (why it is the safest):** the public attack surface collapses to "write a
  file to a bucket" — a compromised/abused public path **structurally cannot** reach
  the member table, cannot escalate a field, and cannot land cross-tenant into a live
  partition, because it holds **no DynamoDB write permission**. Spam is just junk
  objects, trivially contained by bucket rate-limits, **S3 lifecycle expiry** (auto-
  purge un-imported applications — a clean GDPR retention story), and object-level
  review. The member record is still only ever written by the **authenticated import**.
  JSON is a natural, inspectable intake artifact and an easy audit trail. Fully
  boundary-compliant (S3 is an AWS service → SAM→AWS, not SAM→Flask).
- **Cons / reality checks:**
  - **Diverges furthest from the literal ask** — the applicant is NOT in the member
    table until a human imports them; "applicant rows" don't exist until promotion
    (even more so than Option 2).
  - **Import is NOT an exposed SAM capability today.** The route map
    (`handler/routes.py`) has create/update/delete/export and bulk-*transition*, but
    **no import/bulk-create route** — member import exists only as the **offline
    `migration/hdcn_backfill.py` script**, not a live API. So "the member imports the
    JSON" is **new** work: either a new authenticated import route that accepts the
    applicant-JSON shape, or a staff review-UI that calls `create_application` per
    record. It is not reuse of a live feature.
  - **S3 is a new store for the SAM plane** — new bucket + event wiring + lifecycle
    policy + `s3:PutObject`(public fn)/`s3:GetObject`(import) IAM, all SAM-side (new
    operational-surface rows).
  - Two hops to a member record (write file → import) means an application is not
    actionable as a member until staff act — fine for a review workflow, not for
    "instant applicant row."
- **Shared services it stands up:** `public-intake` edge + `tenant-directory` +
  `validation` + `role-recipients` + `notification` (same as Options 1/2), PLUS a
  generic **S3 intake-bucket + import pattern** (public `PutObject` quarantine →
  event → authenticated import) that is **highly reusable** — event pre-application
  and webshop order intake are the same "capture a public JSON submission, promote on
  staff action" shape. The validators run on the public write (reject junk before it
  files) and/or at import (authoritative) — recommended: both (fast reject public,
  authoritative at import).
- **Assessment:** the **safest** option by isolation (public path has zero DynamoDB
  reach) and the best GDPR/anti-spam story (lifecycle-expiring quarantine). Its cost
  is that it needs a **new import capability** (not live today) and diverges most from
  "applicant row in the member table." Strong choice if security/abuse containment is
  the priority and a staff import step is acceptable; it essentially IS Option 2 with
  an S3-file quarantine instead of a DynamoDB `RECORD_TYPE_APPLICATION`, trading a
  DynamoDB record for a file and gaining the "public function holds no table grant"
  isolation.

### How the three options relate (safety vs. literal-ask spectrum)

- **Option 1** — public write goes straight into the member table as `status=application`.
  Closest to the literal ask; largest public blast radius (the public fn can write the
  member table, fenced only by forced-status + sanitize + allow-list tenant).
- **Option 2** — public write goes into a *separate DynamoDB record* in the same table;
  staff promote. Safer (quarantined), but the public fn still writes the member table.
- **Option 3** — public write goes into *S3 JSON*; staff import. Safest (public fn has
  **no** DynamoDB grant), furthest from the literal ask, needs a new import capability.

The axis is **isolation of the public write vs. immediacy of the applicant row**.
Option 3 maximises isolation; Option 1 maximises immediacy; Option 2 sits between. All
three keep the member record authoritative + server-validated and respect the no-
boundary-mix rule.

**AWS run cost is not a differentiator.** At a member-application form's low, human-paced
volume all three options cost effectively nothing per application (well inside free
tiers); the only material recurring cost is the shared public-endpoint abuse protection
(WAF + API Gateway), which every option needs equally. Decide on isolation vs. immediacy,
not cost.

**Invariant across ALL three options — the multi-tenant, field-config-driven model is
preserved.** None of the options changes the field model: the form is always a
projection of the **tenant's resolved field config** (`config#fields` → `FieldResolver`,
grouped by `functional_group`, `membership`-admin group filtered out), validators come
from the per-field `FieldFormat` registry, and the submission is the same nested
`{personal, overlay, …}` field-model shape. This is explicit because Option 3 could be
mis-built as a fixed hand-coded form or a free-form JSON blob — it must NOT be. The S3
JSON is simply that field-model payload **in transit**; the quarantine format is a
transport/staging detail, not a different model. On import/promotion the JSON is
validated against the **same** resolved field config (authoritative), so a tenant that
adds/removes/renames a field, or attaches a checker, sees the application form, the
stored JSON, and the member record all follow — with zero per-tenant code, exactly like
the overview. Any option that would hardcode fields or bypass `FieldResolver` is rejected
on this ground.

---

## Cross-cutting: field-level validators as a DECLARATIVE field attribute (not special cases)

The email and IBAN checks should **not** be hard-coded as application-path
special-cases. The right model — and the one that scales to every module — is a
**declarative `format` / `validator` attribute attached to a field in the config**,
backed by a small **shared validator registry**. A field says *which* checker it
needs (`EMAIL`, `IBAN`, `DATE`, `PHONE`, …); the server looks the checker up in the
registry and runs it generically. Email-required-and-valid and IBAN-mod-97 then
become the **first two entries in that registry**, not bespoke code.

### Why this fits what already exists

- **The precedent is already in the registry.** `member_number` carries a
  `MemberNumberFormat` attribute and `validate_member_number_format` enforces it —
  a field-level, declarative format check already exists for exactly one field.
  Generalizing that to a named validator any field can reference is the same idea,
  not a new mechanism.
- **It rides the projection with no new plumbing.** `config#fields` already projects
  per-field attributes (`type`, `required`, `choices`, `show_when`); an optional
  `format` / `validator` key is one more attribute on the same row,
  reconstructed by `projection_config_reader.py` onto `ResolvedField` and `FixedField`.
- **`type` already does the base coercion.** `FieldType.DATE` already validates
  ISO-8601 in `_validate_date`; so `DATE` is partly native. The registry is for the
  checks `type` can't express — `IBAN`, `EMAIL`, `PHONE`, postal-code-by-country, etc.

### Shape

- A field carries an optional **`format`** (a named checker token, e.g. `"IBAN"`)
  and/or a **conditional** (reuse `show_when`) that gates whether the checker
  applies. Example: the `iban` field has `format: "IBAN"` and
  `show_when: {payment_method: "incasso"}` — so IBAN is validated *only* when incasso
  is chosen, using the SAME conditional mechanism that already drops hidden-required
  errors (`_drop_hidden_required_errors`), no incasso-specific code.
- A **shared `validators` module** maps each token to a pure
  `(value) -> FieldError | None` function:
  - `EMAIL` — format check, `validation.invalidFormat` on failure. (The Flask
    `_validate_email` regex is a reference only; code is reimplemented SAM-side — no
    cross-boundary import.)
  - `IBAN` — ISO 13616 mod-97: normalize (strip spaces, upper-case),
    country-length check, move first four chars to the end, map letters → digits,
    assert `int(rearranged) % 97 == 1`.
  - `DATE`, `PHONE`, … — added as needed; the registry is open for extension.
- The domain validation chain gains one generic step: for each resolved field with
  a `format`, if the field is present (and its `show_when` holds), run the
  registry's checker and merge any `FieldError` into the same
  `MemberValidationError` map — so the applicant still sees every problem at once.

### Pinned-down attribute shape

Decided, aligned 1:1 with the existing `MemberNumberFormat` precedent and the
projection reader's conventions (sub-spec is a dict, unknown tokens degrade
gracefully, missing → `None`).

**Domain shape — a frozen `FieldFormat` dataclass**, carried as an optional
attribute on `FixedField`, `OverlayField`, and `ResolvedField` (exactly as
`member_number_format: MemberNumberFormat | None` is carried today):

```python
@dataclass(frozen=True)
class FieldFormat:
    """A declarative, named validator attached to a field (generalizes MemberNumberFormat)."""
    checker: str                                   # registry token: "EMAIL" | "IBAN" | "DATE" | "PHONE" | ...
    params: Mapping[str, Any] = field(default_factory=dict)   # optional checker args, e.g. {"countries": ["NL","BE"]}
    # NB: conditionality is NOT here — it reuses the field's existing `show_when`.
```

On the field:

```python
# FixedField / OverlayField / ResolvedField gain:
format: FieldFormat | None = None     # None → no extra checker beyond `type`/`required`
```

**Projection shape — a `format` sub-object on the field's spec in the
`config#fields` row** (sibling to `type`/`required`/`choices`/`show_when`), so it
rides the existing row with no schema change:

```jsonc
"fields": {
  "iban": {
    "type": "string",
    "functional_group": "financial",
    "show_when": { "payment_method": "incasso" },   // existing conditional mechanism
    "format": { "checker": "IBAN", "params": { "countries": ["NL", "BE"] } }
  },
  "email": {
    "type": "string",
    "required": true,
    "format": { "checker": "EMAIL" }
  }
}
```

**Reader — a `_build_format(spec)` helper** mirroring `_build_options` /
`_build_jubilee_rule`: accepts a dict with a non-empty string `checker`, copies
`params` if a dict, and **returns `None` for a missing/malformed spec or an unknown
checker token** (degrade gracefully — a stray token never crashes the field-config
read; the generic step simply finds no checker and skips). `_build_overlay_field`
and `_build_override` set `format=_build_format(spec.get("format"))`.

**Why `{checker, params}` and not a bare `"IBAN"` string:** params are needed for
real checkers (IBAN country allow-list, phone region, date min/max) and a bare
string cannot carry them; the object is forward-compatible, and an absent `params`
defaults to `{}` so the common case stays terse.

**Why conditionality is NOT on `FieldFormat`:** reuse the field's existing
`show_when`. "Validate IBAN only when incasso" is `show_when:
{payment_method:"incasso"}` on the `iban` field — the SAME condition that already
hides it and drops its required-error (`_drop_hidden_required_errors`). So a hidden
field is neither required nor format-checked, with one condition and zero new
conditional code.

**Enforcement — one generic step in the validation chain.** For each resolved field
with a `format`, if the field is present AND its `show_when` holds, call
`REGISTRY[fmt.checker](value, fmt.params)` and merge any returned `FieldError` into
the same `MemberValidationError` map. The registry is a module-level
`dict[str, Callable[[Any, Mapping], FieldError | None]]`; `EMAIL` and `IBAN` are its
first entries.

### Scope now vs. later

Per the user: build the two concrete checkers (`EMAIL`, `IBAN`) now, but behind the
`FieldFormat` attribute + registry seam above, so attaching a checker to any field
later is config, not code. We do **not** need a field-validator authoring UI in v1 —
just the `FieldFormat` attribute, the `_build_format` reader helper, the registry,
and the one generic enforcement step. This keeps the application form's two critical
validations working today while making "define a field checker on a field" a
first-class, tenant-/module-agnostic capability from the start (another shared asset
events/webshop inherit). Authority model (recommended): the **checker SET is
platform-defined** (a tenant picks a known token, cannot author code); **attaching a
checker to a field is tenant config** on `config#fields`.

## Cross-cutting: notifying `Members_CRUD` (SAM-side)

`Members_CRUD` is a **global** Cognito group (tenant-agnostic by design — s5c);
per the boundary rule we do **not** query Cognito for recipients. Instead SAM
reads the governance projection's `role#<email>#Members_CRUD` rows for the tenant
via the new `role-recipients` reader (see Option 1's "Recipient resolution") and
sends via a **new SAM-side SES client** (`ses:SendEmail` grant in the data account)
**as the tenant's own verified sender** — provisioned by Flask tenant onboarding /
the tenant administration module, merely *consumed* here (see "Sender identity").
The send is best-effort and never blocks the applicant write; v1 should decide
whether to offload it (e.g. the write enqueues to SQS / a DynamoDB-stream-triggered
notifier) so a slow SES call never sits in the applicant's request path.

---

## Recommendation

- **Primary: Option 1** — a thin, well-fenced public SAM route + a
  `create_application()` that reuses the proven create invariants, with the two
  critical checks and a SAM-native, projection-sourced `Members_CRUD`
  notification. Under the no-boundary-mix rule this is effectively the only shape
  that both meets the literal ask ("land in the member table with status
  applicant, correct tenant") and stays in one plane.
- Treat **`membership_type`** as an open design item (membership field — review
  flag). Working direction: **(b) omit-on-application, set-on-approval**, kept
  catalog-valid in the meantime by a **(c) tenant-default** stamp — but the exact
  required-ness relaxation and the `_validate_membership_type_reference` handling must
  be defined in `design.md`, not assumed.
- **Sender identity is NOT this spec's to solve** (review). A tenant emails its
  `Members_CRUD` **as itself**, so the per-tenant verified SES sender is provisioned by
  **Flask tenant onboarding / the tenant administration module** (SES is generic) and
  only *consumed* by the SAM `notification` service. `support@jabaki.nl` is the
  onboarding sender, not a tenant's outbound identity. Settle only the SAM-side
  *consumption* (where SAM reads the tenant's configured sender) and the **email-log
  decision** (DynamoDB log vs none) in `design.md`.
- Keep **Option 2** on the table as the evolution if review workflow, GDPR consent
  capture, and anti-spam quarantine become first-class — the most defensible long-term
  shape, at the cost of diverging from the "applicant row in the member table" intent.
- **Consider Option 3 (S3-JSON intake) if SAFETY is the deciding factor** (user's
  framing: "if safer"). It gives the public endpoint **zero DynamoDB reach** — the
  strongest isolation of the three — and a clean lifecycle-expiring GDPR quarantine,
  by storing the submission as S3 JSON and promoting via an authenticated **import**.
  Its cost is that member **import is not a live SAM capability today** (only the
  offline backfill script exists), so it needs a new import route/flow, and it is
  furthest from "applicant in the member table now." The pattern (public JSON
  quarantine → staff import) is highly reusable for event pre-application and webshop
  order intake. If the priority is "the public form must not be able to touch member
  data," this is the recommended shape.

- **Build members-local with clean seams; defer the shared extraction** (rule of
  three, steering 35 — CORRECTED). The five capabilities (`public-intake` edge,
  `role-recipients`, `notification`, `validation`, config-driven form) are built
  **inside `members/` with module-agnostic signatures and no members logic in the
  seam** — NOT in `sam/shared/` yet. The **second** consumer (event pre-application)
  triggers the extraction. Each module keeps its own repository + table (rule 5a:
  share CODE, never the STORE).

Whichever option: everything stays in the SAM plane (write + recipient lookup +
send), the server is authoritative with a forced `application` status, the tenant
resolves from an allow-list, the validation chain is reused plus the two critical
checks, the public write is SAM-side abuse-hardened, and the `Members_CRUD`
notification is best-effort and never blocks the write.

## Security & risk (a public write is a real attack surface)

This feature **weakens the SAM edge's strongest invariant** — "deny without a verified
token" — by introducing the plane's first unauthenticated write. That is a deliberate,
fenced exception, and the risks must be designed for, not discovered. Known risks and
the controls that must be in `design.md` / `requirements.md`:

- **Unauthenticated write / spam & resource abuse.** A public POST can be scripted to
  flood a tenant's member table and fire mass emails. Controls: API Gateway throttle +
  usage plan, **WAF** rate-based rule (+ optional CAPTCHA), honeypot field, payload-size
  cap, and tight CORS. Option 2 (intake-then-promote) further contains this — spam lands
  in a quarantine record, never among real members.
- **Cross-tenant landing (the worst case).** A forged/guessed tenant carrier must never
  write into another tenant's partition. Control: tenant resolves ONLY from the
  allow-list `tenant-directory` (verify-before-trust), and the repository keeps the
  `tenant_id` PK invariant (Property 1). The public path must be covered by the same
  repository tenant-invariant test the authenticated path has.
- **Privilege/field escalation via the body.** A client could try to set
  `status=active`, a `member_number`, `tenant_id`, or a staff-only field. Control: the
  create path **forces** `status=application`, strips `tenant_id`/`member_id`/`status`
  (`_sanitize_write_payload`), and accepts only the public-visible, non-`membership`
  field set — authoritative server-side, never trusting the form.
- **PII / GDPR.** The form collects personal data (name, address, DOB, IBAN) from a
  non-member. Needs: a consent/privacy notice on the form, a retention/purge policy for
  un-approved applications (Option 2 makes this cleaner), and no PII in logs
  (reference IBAN/email by presence, never echo values).
- **Email as an exfil/abuse vector.** The notification sends on a tenant's behalf;
  recipients come ONLY from the projection `Members_CRUD` rows (never a client value),
  and the sender is the tenant's verified SES identity (SPF/DKIM) — so the public caller
  can neither choose recipients nor spoof the sender.
- **IAM blast radius.** The public function needs `ses:SendEmail` + projection read; both
  scoped to exact ARNs in the data account, no cross-account, no wildcard.
- **Reference the platform security posture.** Fold this into the existing SAM security
  assessment line (`security-assessment-2026-09-26`, risk S1 on structural-only tenant
  isolation) — a public write raises the stakes on that still-structural isolation, which
  `design.md` must note.

## Spec placement & governance (definition-of-done)

Per `40-spec-workflow.md` and `35-sam-module-architecture-sam.md`:

- **This spec's home is correct.** `Members` is a module/domain tree like
  `FIN`/`STR`/`ZZP`; `Members/application-app/` is the module's feature spec. The
  SAM-plane capabilities it needs live under `Common/Serverless-applications/` and are
  governed by steering 35 — this spec **consumes and references** them, not redefines.
- **`design-options.md` + `findings.md` are the Analysis phase.** Next the formal trio
  `requirements.md` / `design.md` / `tasks.md` (lowercase) follows, once the open
  questions settle.
- **Steering / ADR updates this feature forces** (a step is not done until these land):
  - `40-spec-workflow.md` — add `Members` (and `ZZP`) to the domain list. *(done in this
    pass.)*
  - `35-sam-module-architecture-sam.md` — currently covers only the **authenticated**
    edge (ADR 0007 active-tenant resolution). A **public/unauthenticated intake** edge
    pattern (skip-auth + allow-list tenant resolver + abuse hardening) is **new** and must
    be added as a governed SAM-plane pattern, with its security controls.
  - **The SES tenant-sender gap is an existing deferred item**, not new scope: the
    `Common/Serverless-applications/SNS-SES/SES Email Service` spec lists **"Custom
    per-tenant sender addresses"** as explicitly out-of-scope and fixes `Source` to
    `support@jabaki.nl` (Flask-plane). Per-tenant verified senders + a **SAM-plane** SES
    capability extend that spec (owned by tenant onboarding), referenced here.
  - A likely **new ADR** for "public unauthenticated intake on the SAM edge" (companion to
    ADR 0007), capturing the fenced exception + controls.
  - **End-user documentation** is required per feature (40-steering) — the applicant form
    + the staff "new application" review need a manual section.

## Open questions carried to `design.md`

1. **Option 1 vs 2 vs 3 — the isolation-vs-immediacy choice.** (1) public write
   straight into the member table as `status=application` (most immediate, largest
   public blast radius); (2) public write into a separate DynamoDB application record,
   staff promote (quarantined, public fn still writes the table); (3) public write to
   **S3 JSON**, staff **import** (safest — public fn has NO DynamoDB grant — furthest
   from the literal ask, needs a new import capability). Governs how much of the
   intake/review (or S3-intake-and-import) pattern is built. If security/abuse
   containment is the priority, (3); if "applicant appears instantly for staff", (1).
2. **Shared-first vs members-first sequencing — RESOLVED by steering 35 (rule of
   three):** build **members-local with clean, module-agnostic seams**; extract to
   `sam/shared/<capability>/` only when the **second** consumer (event pre-application)
   arrives. (This overturns the earlier shared-first recommendation.)
3. **`membership_type` on application (membership field — review-flagged, NOT
   settled)** — (a) applicant chooses / (b) omit, set on approval / (c) tenant
   default. Working direction: (b) with a (c) default keeping the record
   catalog-valid; `design.md` must define the required-ness relaxation (scoped to
   `status=application`) and how `_validate_membership_type_reference` is satisfied
   or deferred.
4. **Public tenant carrier** — path slug vs subdomain vs signed form token, and the
   source of the allow-list (`tenant-directory` backing store).
5. **Per-tenant SES sender identity — a row of the Operational-surface table, OWNED by
   Flask tenant onboarding / the tenant administration module, NOT this spec (review).**
   It is a full operational deliverable (SES domain/address verification + DKIM/SPF
   DNS), not a code gap: a tenant emails **as itself**; `support@jabaki.nl` is only the
   platform onboarding sender. This spec **depends on** that provisioning and only
   resolves the SAM-side *consumption*: (a) where SAM reads a tenant's configured
   verified sender in-plane (tenant-config projection row vs a SAM tenant table), (b)
   the fallback when a tenant has no verified sender yet (log + skip, never block), and
   (c) the **send-log decision** (DynamoDB log vs none). See the Operational-surface
   table for the full non-code run-list.
5b. **Public-form field/group visibility** — what marks a field or functional group
   (e.g. `motor`) as **shown on the public application form** vs staff-only: a
   `public`/`application` visibility flag on the field config, distinct from the
   overview's `visible`. Confirms the `motor` group is in scope.
5c. **Where new shared SAM services live** — `sam/shared/` vs the
   `backend/src/services` vendored-into-layer pattern (how `projection_schema` is
   shared today). Governs placement of `role-recipients`, `notification`,
   `public-intake`, `tenant-directory`, `validation`.
6. **Notification delivery** — synchronous in-request vs offloaded (SQS /
   DynamoDB-stream notifier) so a slow SES call never sits in the applicant's path.
7. **Field model source for the public form** — RESOLVED: derived from the tenant's
   resolved field config (`config#fields` projection → `FieldResolver`), grouped by
   `functional_group`, `membership`-admin group filtered out, same model as the
   overview. Remaining sub-question: expose it via an **unauthenticated public
   field-config read** (a public variant of `GET /members/field-config`, filtered to
   the public-safe fields) so the form can fetch the schema before submit — vs
   baking the resolved set server-side only. (Recommended: a public field-config
   read, so the form is a thin, config-driven renderer.)
8. **Field-level validators** — SHAPE PINNED (see "Pinned-down attribute shape"): a
   frozen `FieldFormat {checker, params}` attribute on `FixedField`/`OverlayField`/
   `ResolvedField`, projected as a `format` sub-object on the `config#fields` field spec,
   rebuilt by a `_build_format` reader helper (unknown token → `None`, degrade
   gracefully), conditionality via the field's existing `show_when`, enforced by one
   generic step over a `dict[token→checker]` registry (`EMAIL`, `IBAN` built now). Only
   confirm-later item: the **authority model** (recommended: platform-defined checker
   SET, tenant-attachable per field).
