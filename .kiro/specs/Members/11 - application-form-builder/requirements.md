# Requirements Document

## Application Form Builder (tenant-admin authoring UI) — Requirements

- Status: **Draft** (requirements phase — review before design)
- Spec home: `Members/11 - application-form-builder/` is a **module feature spec**. It is the
  **authoring counterpart** to `Members/10 - application-app/` (the public applicant intake). That
  spec shipped the whole *read/consume* path — the public form renderer, the SAM resolver that
  filters by the per-field application attributes, `create_application`, de-dup, duplicate flag,
  and the two notifications — but shipped **no authoring surface**. This spec builds that surface.
- Governing steering: `20-platform-architecture`, `35-sam-module-architecture-sam`,
  `38-sam-module-field-config` (the SAM-owned `config#*` model + one-authoring-surface rule),
  `37-shared-building-blocks` (API response/error standard, Table Filter Framework), `34-backend-testing`,
  `33-frontend-testing`, `40-spec-workflow`.

## Introduction

Today the public member application form (spec 10) is driven by four per-field attributes on the
tenant's `config#fields` row — `application_visible`, `application_required`, `application_choices`
(enum subset), `format` (a declarative validator token) — plus three form-level settings on
`config#mail` (`application_scope_copy`, the Reply-To default, and the versioned `consent_notice`).
Every one of these is **read and enforced** by the SAM plane and **projected/validated** on save,
but **no UI authors any of them**. A tenant admin who wants to stand up an application form must
hand-edit raw JSON. There is also no place to see or confirm the public URL the form answers on,
nor to choose standalone-vs-iframe embedding.

This feature adds an **"Application form" sub-tab** inside the tenant-admin **Members** area that
lets a Tenant Admin:

1. pick, from the tenant's own resolved field list, **which fields appear on the public form**,
   mark each **required-on-the-form**, choose an **enum subset** for choice fields, and attach a
   **format validator** — authoring the four per-field attributes through the existing SAM write
   path;
2. author the **form-shell settings** — the **public slug/URL** the form is served at, the
   **standalone-vs-iframe embedding** choice (with a copy-ready embed snippet and the allowed
   embedding origin), and the tenant's **versioned bilingual consent notice**;
3. see a **live preview** of the resulting public form so authoring and the public render never drift.

### Critical context — authoring now lives on the SAM plane, NOT Flask

Spec 10's design assumed Flask authored the field config (`members.field_overlay` parameter) and
**projected** it to `config#fields` for SAM to read (its D18). **That is no longer true.** After
spec 10 started, member config authoring was migrated into SAM (the "Parameter redesign" spec 02):

- `config#fields`, `config#scope`, and `config#mail` are now **SAM's system-of-record**, authored
  directly via the SAM Members API route **`PUT /members/config/{configId}`** (`configId ∈ {fields,
  scope, mail}`, gated `members:admin` / Tenant_Admin), resolving the tenant from the verified JWT.
- `ProjectionSync` (Flask) **no longer emits any `config#*` row** — the Flask `field_overlay`
  parameter + `_projection_config_builders` + `members_config_validation` path is **legacy** for
  authoring (the builders survive only for a one-off migration script + unit tests).
- The frontend field editor already saves through SAM: the field modal mutates one `field_overlay`
  working object, and `saveMembersParameter('field_overlay', …)` calls `writeFieldConfig` →
  `PUT {VITE_MEMBERS_API_BASE_URL}/members/config/fields`.

**Therefore this spec authors against the SAM write path, not Flask.** No Flask projection work is
needed. The four per-field attributes already pass through `ConfigWriteService._validate_fields_body`
**verbatim**, and `config#mail` authoring already accepts `application_scope_copy`,
`mail_reply_to_default`, and `consent_notice` via `_validate_mail_body`. The work is overwhelmingly
**frontend authoring UI**, plus a small amount of **SAM-side shape validation** so the write path
rejects an incoherent body fail-loud instead of storing it.

## Terminology / Glossary

- **The four per-field application attributes** — `application_visible` (bool, on the public form?),
  `application_required` (bool, required *on the form* — may tighten, never relax a platform-required
  field), `application_choices` (an enum **subset**; `null` = full set), `format`
  (`{checker, params}` naming a platform-known validator token). Carried per field on both overlay
  (variable) fields and fixed-field overrides of the `config#fields` row.
- **`config#fields`** — the SAM-owned projected field-config row: `{ functional_groups, fields,
  overrides }` (the frontend `field_overlay` object aliases `overrides` as `fixed_overrides`).
- **`config#mail`** — the SAM-owned mail-config row carrying the three form-shell mail settings:
  `application_scope_copy`, `mail_reply_to_default`, `consent_notice {version, text{nl,en}}`.
- **Form-shell settings** — the form-level (not per-field) configuration: the public **slug/URL**,
  the **embed mode** (standalone vs iframe) + allowed origin, and the **consent notice**.
- **Resolved field list** — the tenant's `GET /members/field-config` response: the single ordered
  field set (fixed base ⊕ overlay), each field carrying `type`, `label{nl,en}`, `choices`/`options`,
  `required`, `functional_group`, `order`, `show_when`, and the four application attributes.
- **Public field-config** — the filtered schema `GET /public/members/{slug}/field-config` returns
  (spec 10): only `application_visible` fields, carrying the application-required flag, the subset,
  the `format` token, and the consent notice `{version, text{nl,en}}` — what the live preview shows.
- **Format token** — a platform-defined validator name in the SAM `field_formats` registry
  (`EMAIL`, `IBAN` today; the set is the authority — a tenant picks a known token, never authors code).
- **Slug** — the tenant's public landing slug (spec 10 D19: `<slug>.jabaki.nl` host-based + the
  CloudFront KeyValueStore `myadmin-domain-slug-mapping` for custom domains). The application form is
  served under that slug; the SAM edge resolves slug → `tenant_id` from a thin projection.

## Guiding principles (settled)

- **One authoring surface, one object, one save** (steering 38 rule 5). The per-field attributes are
  authored INTO the same single `field_overlay` object the existing Field-configuration editor
  commits, through the SAME `PUT /members/config/fields` call — not a parallel write path. The
  form-shell mail settings are authored INTO the same `config#mail` body the Mail editor commits.
- **Author toward the SAM contract, never a hand-coded shape.** The field picker is driven by the
  tenant's own `GET /members/field-config`; the format dropdown is driven by the platform's known
  tokens; the preview consumes the real public field-config read. Zero per-tenant code.
- **The server stays authoritative.** The UI never enforces a rule the server does not also enforce.
  `application_required` can tighten but never relax a platform-required field; an `application_choices`
  subset must be ⊆ the field's own choices; a `format.checker` must be a platform-known token. The
  SAM write path re-validates all of this fail-loud (hardening R8) so a crafted request cannot store
  an incoherent `config#fields`/`config#mail`.
- **Gated as administrative.** Every authoring action requires `members:admin` (Tenant_Admin), the
  same gate the existing `PUT /members/config/{configId}` route enforces, tenant resolved from the
  verified token (never the body).
- **Accessibility and bilingual (nl/en) throughout**, consistent with the existing tenant-admin UI
  (Chakra `FormControl` wiring, keyboard operreadiness, nl/en labels).
- **No new store, no Flask projection.** Reuse `config#fields` and `config#mail`. The slug reuses
  the landing-page slug mechanism (spec 10 D19) — this spec authors/surfaces it, it does not invent
  a new slug store.

## Settled decisions

- **E1 — Option B: a dedicated "Application form" builder sub-tab.** Chosen over extending the
  per-field modal, because the form-shell settings (slug, embed, consent) have no home on a per-field
  modal and the builder benefits from a field-list-first layout + live preview. It is a new sibling
  sub-tab under tenant-admin **Members**, beside Field configuration / Membership types / Mail.
- **E2 — The builder authors the SAME `config#fields` object as the Field-configuration editor.**
  Selecting a field onto the form writes `application_visible` (+ the other three attrs) onto that
  field's entry in the `field_overlay` object and commits via `PUT /members/config/fields`. The two
  sub-tabs edit the same row; the builder is a focused *view* over the application attributes.
- **E3 — Form-shell mail settings are authored through the existing `config#mail` write.** The embed
  scope-copy toggle (`application_scope_copy`), the Reply-To default (`mail_reply_to_default`), and
  the versioned `consent_notice` are added to the Mail editor's `config#mail` body (which already
  accepts them server-side) — not a new row.
- **E4 — Slug is surfaced read-mostly; embed is authored.** The public slug is derived from the
  tenant's landing-page slug (spec 10 D19). v1 **displays** the resolved public URL and lets the
  admin **choose the embed mode** (standalone vs iframe) with a generated snippet + allowed origin.
  Changing the underlying landing slug itself stays with the Landing Page editor (not duplicated
  here); if no slug exists the builder tells the admin the form has no public address yet and links
  to where to set it.
- **E5 — Readiness is shown, not silently blocked.** Because the public form refuses to open for a
  tenant without a certified sender (spec 10 D15), the builder SHOWS the readiness state (certified
  sender present? slug present?) so the admin understands why a preview/publish is unavailable,
  rather than authoring into a form that can never open.
- **E6 — SAM write-path validation is hardened in this spec.** Today `ConfigWriteService`
  passes the four per-field attributes through `config#fields` verbatim (no shape check). This spec
  adds fail-loud validation on the SAM write (subset ⊆ choices; known `format.checker`;
  application-required cannot relax a platform-required field; well-formed consent notice) so the
  authoritative author rejects an incoherent body — closing the gap left when authoring moved off
  the Flask validator (`members_config_validation._validate_application_attrs`).

## Requirements

### R1 — "Application form" builder sub-tab in the tenant-admin Members area

**User story:** As a Tenant Admin, I want an "Application form" section in the Members admin area, so
that I can configure my public application form in one place without editing raw JSON.

#### Acceptance criteria
1. The system SHALL add an **"Application form" sub-tab** inside the tenant-admin **Members** TabPanel,
   as a sibling to the existing Field configuration / Membership types / Mail sub-tabs, gated by the
   same `hasMembers` condition.
2. The sub-tab SHALL be reachable ONLY by a Tenant_Admin of the current tenant (the dashboard's
   existing admin guard); every write it performs SHALL go through a `members:admin`-gated SAM route.
3. The sub-tab SHALL present, in one view: a **field list** (R2), the **form-shell settings** (R5),
   a **readiness panel** (R6), and a **live preview** (R7).
4. All labels and messages SHALL be bilingual (nl/en), following the existing Members admin language
   convention.

### R2 — Field list: select which fields appear on the public form

**User story:** As a Tenant Admin, I want to see my configured member fields and toggle which appear
on the application form, so that applicants are asked for exactly the right fields.

#### Acceptance criteria
1. The builder SHALL render the tenant's **resolved field list** from `GET /members/field-config`,
   grouped by `functional_group` and ordered by the catalog rule `(group.order, field.order, key)`.
2. Each field row SHALL show the field's label (applicant-facing locale), key/provenance, type, and
   its current **on-the-form** state (`application_visible`).
3. Toggling a field **on** SHALL set `application_visible = true` for that field in the working
   `field_overlay` object; toggling it **off** SHALL set it `false` (or clear it to the default).
4. The builder SHALL respect the storage-group convention: back-office `membership`-admin fields
   (e.g. `member_number`, `status`) default **off**, but the admin MAY still toggle a specific
   membership field (e.g. a membership-type choice) **on** — inclusion is per field, never
   all-or-nothing (spec 10 R4.3/R4.4).
5. A field the platform marks hidden / non-authorable (e.g. calculated/derived fields) SHALL NOT be
   offerable on the form; the builder SHALL make this clear rather than silently accept a toggle.

### R3 — Per-field application attributes: required, enum subset, format

**User story:** As a Tenant Admin, for each field I put on the form I want to mark it required,
restrict choices for enum fields, and attach a format check, so the form collects valid data.

#### Acceptance criteria
1. For a field that is on the form, the builder SHALL offer an **application-required** toggle writing
   `application_required`. It SHALL be able to TIGHTEN an optional field to required, but SHALL NOT be
   able to RELAX a platform-required field (the control is disabled/forced for such fields, and the
   SAM write rejects a relax regardless — R8).
2. For an **enum** field on the form, the builder SHALL offer a **subset picker** over that field's
   own choices writing `application_choices` (a list; empty/cleared = `null` = full set). The picker
   SHALL only offer values that are valid choices of the field; it SHALL NOT allow a value that is not
   a field choice.
3. The builder SHALL offer a **format** control writing `format = {checker, params?}`, whose checker
   options are the **platform-known tokens** fetched from the SAM registry (`EMAIL`, `IBAN`, … — never
   a free-typed token). Clearing it writes `format = null`.
4. Each of these controls SHALL be available ONLY when the field is on the form (`application_visible`),
   and SHALL default to the field's current authored value (or the back-compatible default when none).
5. All four attributes SHALL be written onto the SAME field entry in the ONE `field_overlay` object and
   committed in ONE `PUT /members/config/fields` (one object, one save).

### R4 — Membership-type on the form (coherent with spec 10 D21)

**User story:** As a Tenant Admin, when I expose a membership-type choice on the form, I want the
applicant to pick from a public-safe subset, so I don't show staff-only types.

#### Acceptance criteria
1. WHEN the admin puts `membership_type` (or the tenant's membership-type field) on the form THEN the
   builder SHALL let them author the **public-safe subset** via the R3.2 subset picker over the live
   membership-type catalog values.
2. The builder SHALL surface that an exposed membership-type field is **application-required** with a
   default first option (spec 10 D21) so the authored form is coherent with how the public form
   renders it; it SHALL NOT allow authoring a subset that is empty when the field is exposed-required.
3. The subset values SHALL be validated against the live catalog the same way the server does
   (`_validate_membership_type_reference`); the builder SHALL not let the admin save a subset value
   not in the catalog (and the SAM write rejects it regardless — R8).

### R5 — Form-shell settings: slug/URL, embed mode, consent notice

**User story:** As a Tenant Admin, I want to set the form's public address, choose standalone-vs-iframe
embedding, and author the consent notice, so the form is usable and legally complete.

#### Acceptance criteria
1. **Public slug/URL (E4).** The builder SHALL DISPLAY the tenant's resolved public application URL,
   derived from the landing-page slug (spec 10 D19). WHEN no slug exists THEN it SHALL state that the
   form has no public address yet and point the admin to where the slug is set (Landing Page editor),
   rather than inventing one here.
2. **Embed mode (E4).** The builder SHALL let the admin choose **standalone** (its own page at the
   public URL) or **iframe-embedded**. For iframe it SHALL generate a copy-ready `<iframe>` snippet
   for the public URL and let the admin declare the **allowed embedding origin(s)**; it SHALL explain
   that the origin governs the CORS / `frame-ancestors` the public edge enforces.
3. **Consent notice (E3; spec 10 D26).** The builder SHALL let the admin author a **bilingual (nl/en)
   consent notice text** with a **stable version id** per revision, writing `consent_notice =
   {version, text{nl,en}}` onto `config#mail`. Saving a changed notice SHALL produce a new version id;
   an existing applicant record's recorded version SHALL NEVER be retroactively changed (the record
   stores the version it accepted).
4. **Scope-copy / Reply-To (E3; spec 10 D9a/D24).** The builder SHALL let the admin toggle the
   optional **scope-matched copy** (`application_scope_copy`) and, where applicable, the mail
   **Reply-To default** (`mail_reply_to_default`) — authored onto `config#mail`. (These MAY be
   presented on the existing Mail sub-tab and merely referenced from the builder, as long as they are
   authorable; design decides placement.)
5. The form-shell mail settings (5.3/5.4) SHALL be committed through the existing
   `PUT /members/config/mail` write (one `config#mail` object), never a new row.

### R6 — Readiness panel (show, don't silently block)

**User story:** As a Tenant Admin, I want to see whether my form can actually go live, so I understand
why preview/publish may be unavailable.

#### Acceptance criteria
1. The builder SHALL show a **readiness summary**: whether the tenant has a **certified sender**
   (`mail_certified` + a `mail_domain`), whether a **public slug** exists, and whether at least one
   field is **on the form**.
2. WHEN the tenant is NOT send-ready THEN the readiness panel SHALL explain it (neutral, no mail-config
   internals leaked) and link to the sender-verification surface; the live preview (R7) SHALL reflect
   the same 409 "not available yet" the public read returns.
3. The readiness check SHALL use the SAME signal the public edge uses (spec 10 D15) so the panel and
   the live form never disagree.

### R7 — Live preview of the public form

**User story:** As a Tenant Admin, I want to preview the public form as an applicant would see it, so
I can confirm my selections before publishing.

#### Acceptance criteria
1. The builder SHALL render a **live preview** by consuming the real public field-config contract
   (`GET /public/members/{slug}/field-config` or an equivalent authenticated preview of the same
   filtered schema), so the preview shows EXACTLY the fields, subsets, required flags, and consent
   notice an applicant would see.
2. The preview SHALL reuse the public form **renderer component** (spec 10's
   `ApplicationFormRenderer`) so there is a single rendering code path — authoring never drifts from
   the live form.
3. WHEN the tenant is not send-ready THEN the preview SHALL show the same neutral "not available"
   state the public form shows (R6.2), not a half-rendered form.
4. The preview SHALL be read-only (no submission) and SHALL reflect UNSAVED edits where feasible, or
   clearly indicate it reflects the last saved state — design decides, but the behavior SHALL be
   explicit to the admin.

### R8 — SAM write-path validation hardening (close the validator gap)

**User story:** As the platform, I want the authoritative SAM author to reject an incoherent
application config fail-loud, so a crafted or buggy write can never store a broken form config now
that the Flask validator is off the authoring path.

#### Acceptance criteria
1. `ConfigWriteService` (the `PUT /members/config/fields` author) SHALL validate each field's
   application attributes at write time and REJECT the write (no store) when:
   a. `application_choices` is set but is not a list ⊆ the field's own resolved choices (R3.2);
   b. `format` is set but `format.checker` is not a **platform-known** token (the SAM
      `field_formats` registry) or `format` is not a well-formed `{checker, params?}` object;
   c. `application_required = false` would relax a **platform-required** field (R3.1).
2. `ConfigWriteService` (the `PUT /members/config/mail` author) SHALL validate the `consent_notice`
   shape (non-blank `version` + at least one non-blank locale text) and reject a malformed notice
   rather than silently omitting it where the admin intended to author one — surfacing a clear error.
3. A rejected write SHALL return the standard SAM error envelope (steering 37) with a stable `code`
   and a caller-safe message keyed to the offending field, consistent with the existing config-write
   error contract; it SHALL NOT leak internals.
4. The hardening SHALL be equivalent to the retired Flask `members_config_validation
   ._validate_application_attrs` rules (subset ⊆ choices, known checker, no-relax) so moving the
   authority to SAM loses no guard.

### R9 — Testing (change-with-tests, both planes)

**User story:** As a maintainer, I want the builder and the hardened write covered by paired tests so
a behavior change can't silently break the nightly suite.

#### Acceptance criteria
1. **Frontend** (`frontend/`, per `33-frontend-testing`): the builder writes the four per-field
   attributes correctly into the `field_overlay` object (subset only on enum fields; required cannot
   be relaxed for a platform-required field; format only offers known tokens); one-object/one-save is
   preserved; the live preview consumes the real public-config contract; axe over the builder.
2. **SAM** (`sam/tests/`, per `34-backend-testing`): the R8 write-path validation rejects a subset ⊄
   choices, an unknown `format.checker`, a platform-required relax, and a malformed consent notice,
   with the standard error envelope; a coherent body still writes; back-compatible defaults still
   write for a tenant that authors none.
3. Paired tests land in the SAME change as the behavior they cover (steering 30/34).

## Non-functional requirements

- **Security:** every write `members:admin`-gated, tenant from the verified JWT, body never trusted
  for tenant. The builder never exposes another tenant's config. Reads of mail config never leak
  domain/sender internals in a public-facing error.
- **Accessibility:** WCAG 2.2 AA for the builder UI (Chakra `FormControl` wiring, keyboard operreadiness,
  focus management, nl/en `lang`), consistent with spec 10 D14's bar for the public form.
- **Performance:** authoring is low-volume, human-paced; the builder makes at most one config read per
  row type on load and one write per save (one object, one save).
- **Boundary:** SAM authors + reads `config#*`; no Flask projection introduced; no new DynamoDB store.

## Out of scope (v1)

- Changing the underlying landing **slug** value itself (stays with the Landing Page editor; the
  builder surfaces/derives the public URL and authors embed mode only — E4).
- A WAF / CAPTCHA on the public edge (spec 10 D17 deferred; unchanged here).
- Hard write-time uniqueness for applicants (spec 10 D11 Open Question #8; unchanged here).
- Any change to the public submission flow, de-dup, duplicate flag, or notifications (all shipped in
  spec 10) — this spec only authors the config those mechanisms already read.
- Re-introducing Flask authoring/projection of `config#*` (explicitly retired; do not revive).

## Open questions — ALL RESOLVED (2026-10-21, user-answered; detail in design §9)

1. **Preview surface (R7.1) — RESOLVED.** The form is CloudFront-hosted at a predictable name (e.g.
   `tenant-member-application.jabaki.nl`, overridable with a tenant private URL). The live preview is
   an `<iframe>` to that hosted form — no new preview route; the preview IS the real form.
2. **Preview freshness (R7.4) — RESOLVED.** Save-then-preview: last-saved state, the iframe reloads
   after a save. No client-side filter mirror. TEST applications are trivially deletable; PROD editing
   by a Tenant_Admin is expected.
3. **Embed origin (R5.2) — RESOLVED.** Enforced by CSP `frame-ancestors` on the CloudFront-hosted FORM
   (distinct from CORS on the SAM API). One tenant list `application_embed_origins` on `config#mail`
   feeds both (CloudFront `frame-ancestors` via a `viewer-response` function + KVS; SAM API CORS). No
   admin-SPA hosting migration required (that is a separate ADR — design §9.1).
4. **Reply-To / scope-copy (R5.4) — RESOLVED.** ONE Reply-To for all in v1 (`mail_reply_to_default` on
   `config#mail`); `application_scope_copy` is an optional CC toggle that does not change Reply-To. All
   three stay on the existing Mail sub-tab (one authoring home); the builder references them. Per-scope
   Reply-To is a future additive enhancement — simplifies spec 10's D8/D24.
