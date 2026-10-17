# Design Document

## Member Application Form (public applicant intake) — Design

- Status: **Draft** (design phase — follows `requirements.md` D1–D18)
- Plane: **SAM** (`sam/members/`, data account `nonprofit-deploy`) for the whole runtime flow;
  **Flask** (`backend/src/`) for authoring + projecting the per-field application config (R4c/D18).
- Governing steering: `35-sam-module-architecture-sam` (handler→service→repository layering;
  CODE-shared / DATA-per-module; rule of three; ADR 0007 active-tenant — the public edge is a
  governed exception to it), `38-sam-module-field-config` (catalog-first field model, versioned
  projection, i18n labels in config), `36-config-and-parameters` (Flask writes config → SAM reads
  projection), `37-shared-building-blocks` (API response & error standard v1.0; Table Filter
  Framework v2), `34-backend-testing`, `40-spec-workflow`, `30-backend-api-flask-mysql` (Flask
  authoring/projection + change-with-tests).

This design turns the 18 settled requirement decisions into concrete components, contracts, and
insertion points. It deliberately **reuses** existing SAM members machinery (the create spine, the
field resolver, the `config#mail` sender resolver, the mail-send queue/worker, the projection
readers) rather than inventing parallel mechanisms — per the layering and rule-of-three steering.

---

## 1. Architecture overview

The feature adds the SAM plane's **first public (unauthenticated) route**, a deliberate, fenced
exception to ADR 0007's "deny without a verified token" edge invariant. Everything downstream of the
edge reuses the authenticated module's layers unchanged.

**How the skip-auth is actually wired (confirmed against the code).** The members API is a single
`AWS::Serverless::Api` with `Auth.DefaultAuthorizer: CognitoAuthorizer`; auth runs in `handler()`
via `_authenticate_and_authorize` **before** dispatch, and `RouteSpec` has **no** per-route
auth-skip field. So the public path is NOT a `RouteSpec` flag. **Decided (D27): a separate public
`AWS::Serverless::Api`** — its own stage, NO `DefaultAuthorizer`, own throttle/usage plan and
invoke URL — routed to a **dedicated public Lambda entrypoint `handler/public_app.py`** that never
calls `_authenticate_and_authorize`. The authenticated members API and its `handler()` are
untouched — cleanest blast-radius isolation for the plane's first unauthenticated surface. (The
rejected alternative was an `Auth: {Authorizer: NONE}` route on the existing API.) The precedent
that an unauthenticated carve-out is possible already exists in the template:
`AddDefaultAuthorizerToCorsPreflight: false` exempts CORS preflight today.

```
Public SPA (config-driven form)            presentation only; Yup mirrors server rules
   │  GET  /public/members/{slug}/field-config   (readiness gate + schema)
   │  POST /public/members/{slug}/applications    (submit)
   ▼
API Gateway  (public stage — NOT behind the Cognito DefaultAuthorizer)
   ▼
Lambda HANDLER (thin)   parse · resolve tenant from slug (allow-list, verify-before-trust) ·
   │                    abuse guards (honeypot, payload cap, CORS) · shape HTTP response
   ▼
Application / domain SERVICE
   │   ApplicationService.get_public_field_config(tenant)     → readiness gate + filtered schema
   │   ApplicationService.create_application(tenant, body, …) → reuses create_member spine
   ▼
Repository (ONLY DynamoDB touch-point)   save_member (PutItem) · session-key conditional write ·
   │                                     role-recipients + scopegrant reads · config#mail read
   ▼
DynamoDB  sam-members (tenant_id PK + record_type#id SK) · governance_projection (read)
   │
   └── offloaded notification: enqueue SQS job → mail worker → SES (staff + applicant)
```

Layer ownership (steering 35):
- **Handler** stays an adapter: parse, resolve-tenant-from-slug, abuse guards, HTTP envelope. No
  domain logic, no DynamoDB.
- **Domain** (`ApplicationService`) owns the authoritative rules; storage-agnostic; reuses
  `MembershipService.create_member` rather than a second write path (R3.5).
- **Repository** is the only DynamoDB code; tenancy is the `tenant_id` PK.
- **Notification** is offloaded to the existing mail-send queue + worker (D5); recipient resolution
  and SES send run in the worker, never in the applicant's request path.

### Plane split (boundary rule, D18)
- **SAM** builds + runs the form, the edge, the service, the repository reads/writes, and the
  notification.
- **Flask** authors the per-field application config and projects it into `config#fields` (R4c) —
  SAM only reads it. No SAM→Flask call, no Flask write to the SAM table.

---

## 2. Data flow

### 2.1 Form load (GET field-config) — the readiness gate
1. SPA calls `GET /public/members/{tenant_slug}/field-config`.
2. Handler resolves `tenant_slug` → `tenant_id` via the **existing landing-page slug mechanism** (D19): the slug is the tenant's landing slug (`<slug>.jabaki.nl` host-based; custom domains via the CloudFront KVS `myadmin-domain-slug-mapping`, `infrastructure/landing-pages.tf`) — no new `tenant-directory` store. The API edge reads slug→`tenant_id` from a thin SAM-plane projection of that mapping (keeps the boundary clean). Unknown slug → **404** (non-probeable, R1a.4).
3. `ApplicationService.get_public_field_config(tenant_id)`:
   a. **Readiness gate (D15/R5.4):** read `config#mail`; if not `mail_certified` or no `mail_domain` → return the "not available" error (**409/422** + stable `code`). Form does not open.
   b. Resolve the field set: `FieldResolver` over fixed base ⊕ `config#fields` overlay, filtered to **application-selected** fields (R4.2), each carrying `application-required` (R4b), enum **application subset** (R4a), `FieldFormat` (R7), `show_when`, `label{nl,en}`, `functional_group`, `order`.
4. Handler returns **200** + the schema (R1a). SPA builds the Yup schema from it (R10a.2) and renders via Chakra `FormControl` (R10a.4), labels in the applicant locale (R6b, default `nl`).

### 2.2 Submit (POST applications)
1. SPA POSTs the flattened form values + `locale` + session key + honeypot + consent.
2. Handler: honeypot / payload-cap / CORS guards (R10); resolve `tenant_slug` → `tenant_id` (R2); re-check readiness (R9.4 defense-in-depth — no sender → refuse, no record).
3. `ApplicationService.create_application(tenant_id, body, session_key, locale, consent)`:
   a. **Session de-dup (R3a):** derive the session item key; conditional `PutItem` (`attribute_not_exists`) — first submit creates, a repeat **updates** the same member record (preserve `member_id`, `status=application`).
   b. **Field gate:** accept only application-selected fields (R3.4/R4.8); un-flatten to `{personal, membership, overlay, …}` (R4.7).
   c. **Reuse `create_member` spine** (R3.5): sanitize → stamp `tenant_id` → mint `member_id` → default `status=application` → `validate_fixed_fields` + overlay gates → `FieldFormat` registry step (R7.5) → `_validate_membership_type_reference` (R11) → `_reject_invalid_overlay_enum_values` → `save_member`.
   d. **Required enforcement (R6.6):** every required (platform or application-required) field present; email required+valid; IBAN mod-97 when incasso shown; errors collected → R1a **422** `errors[]`.
   e. **Consent stamp (F4/R12.1a):** persist notice version + server UTC timestamp + locale.
   f. **Duplicate flag (R3a.5/D25):** name+DOB match via the `(tenant_id, name+dob)` GSI → `DUP` note in `overlay.additional_info`; never blocks; response unchanged.
4. On success → enqueue **two** notification jobs (staff + applicant, D10) via the existing `MailSendQueuePort.enqueue(job)` / `enqueue_many(jobs)` (JSON `SendMessage`, `tenant_id` on the job envelope); return **202** (R1a.2), no `member_id` in body.
5. **Worker** (async): resolve recipients (all-scope `Members_CRUD` + optional scope copy + `TenantAdmin` fallback, D9/D9a); compose `From` via `MailSenderResolver` (D4); set Reply-To (D8); render bilingual template; SES send; best-effort with DLQ (R8.8). If no recipients → `NO_NOTIFY` note (R8.5) + platform-operator alert.

---

## 3. API contracts

All responses use the **API response & error standard v1.0** envelope (steering 37) via the existing
`_http._response` / `_http._error` / `_field_errors_array` (R1a).

### 3.1 `GET /public/members/{tenant_slug}/field-config`
- **200** — `{ success: true, data: { fields: [ ResolvedPublicField … ], locales: ["nl","en"], notice: { version, text{nl,en} } } }`
  where `ResolvedPublicField = { key(dotted), type, label{nl,en}, functional_group, order, required(application-required), show_when?, options?/choices?(application-subset-applied), format?({checker,params}) }`.
- **409** `code=errors.application.notAvailable` — tenant not send-ready (D15) or not accepting applications.
- **404** `code=errors.api.notFound` — unknown/forged slug (non-probeable).

### 3.2 `POST /public/members/{tenant_slug}/applications`
Request body: `{ session_key, locale, consent:{ accepted:true, notice_version }, honeypot?, fields:{ <dotted_key>: value, … } }`.
- **202** `{ success: true, data: { received: true } }` — accepted (record written; notifications offloaded). No `member_id`.
- **422** `code=errors.validation.failed`, `errors:[{field,code,detail}]` — field validation (R6.5/R10a.3).
- **400** `code=errors.api.badRequest` — honeypot tripped / oversized / malformed.
- **404** — unknown slug. **409** — not send-ready (defense-in-depth).

The two endpoints are the ONLY unauthenticated routes; both carry CORS headers on every response
including errors (R10.3).

---

## 4. Data model (DynamoDB — `sam-members`, `tenant_id` PK + `record_type#id` SK)

Reuses `table_design.py` conventions. New/changed items:

| Item | PK | SK | Purpose |
| --- | --- | --- | --- |
| Member (applicant) | `tenant_id` | `member#<uuid4>` | The application lands here, `status=application` (Option 1, D1). Unchanged shape; new attrs: `consent{version,accepted_at,locale}`, `locale`. |
| Application session marker | `tenant_id` | `appsession#<session_key>` | Conditional `attribute_not_exists` write → session de-dup (R3a); maps session_key → the member_id it created, so a resend updates that record. TTL to expire stale sessions. |

- **No new flag columns** (per user): the `DUP` and `NO_NOTIFY` signals are keyworded notes appended to the existing `overlay.additional_info` free-text field (R3a.5/R8.5), keyword-filterable via Table Filter Framework v2 (R8b.5).
- **New GSI for the duplicate flag (D25):** a GSI keyed on the normalized `(tenant_id, name+dob)` composite backs the name+DOB possible-duplicate lookup (R3a.5–R3a.8) — a cheap indexed read on the public path, not a partition scan. It makes *checking* cheap; it does NOT enforce uniqueness (DynamoDB GSIs aren't unique constraints), which is correct — the flag never blocks.
- **No hard uniqueness item** in v1 (deferred members-core dependency — Open Question #8); only the name+DOB *flag* read via the GSI.
- Governance projection (`governance_projection`, read-only): `config#fields`, `config#mail`, `role#<email>#<role>`, `scopegrant#<email>#<dimension>` — all already projected; this feature adds the new per-field application attributes onto `config#fields` (Flask side, §7).

---

## 5. Field model + `FieldFormat` (D6, D16; steering 38)

Per steering 38 the field model stays in `sam/members/domain/`, catalog-first, module-neutral shape.

- **New per-field attributes** on `FixedField` / `OverlayField` / `ResolvedField` (`_field_models.py`), mirroring the existing `member_number_format` precedent:
  - `application_visible: bool` (default `False`) — R4.2/R4.3.
  - `application_required: bool` (default `False`) — R4b.
  - `application_choices: tuple[str,...] | None` — the enum subset (R4a); `None` = full set.
  - `format: FieldFormat | None` — `{checker, params}` (R7).
- **`FieldFormat` registry** — a module-level `dict[str, Callable[[Any, Mapping], FieldError|None]]` with `EMAIL` (regex, reusing the existing email pattern) and `IBAN` (ISO 13616 mod-97 — not a regex) as the first two entries (R7.6). One generic validation step over resolved fields with a `format`, gated by `show_when` (R7.4/R7.5). Built in `members/` with a module-agnostic seam; extraction to `sam/shared` deferred to the second consumer (D16 exception justified: committed events/webshop roadmap).
- **Reader:** `projection_config_reader.py` gains `_build_format(spec)` + reads the three new attributes onto the resolved fields (degrade gracefully on unknown token/malformed — R7.3).

---

## 6. Notification (offloaded — D5; reuses the mail worker)

- **Enqueue** (service): on success, enqueue two jobs to the existing members mail-send SQS queue (`mail_send_queue.py`) — a `member_application_staff` job and a `member_application_ack` job. `tenant_id` is authoritative on the job envelope.
- **Recipient resolution** (worker, new thin `role-recipients` reader over the shared projection schema, R8.2): query the tenant partition; keep `RECORD_TYPE_ROLE` rows with role `Members_CRUD`; filter to **all-scope** grants via the `scopegrant#<email>#<dimension>` rows = `["*"]` (D9, scope-generic — region is h-dcn's instance). Optional scope-matched copy for the applicant's selected scope value (D9a). Fallback to `TenantAdmin` rows; else `NO_NOTIFY` note + operator alert (R8.4/R8.5).
- **Sender** (D4): `MailSenderResolver` composes `From=<mail_local_part|noreply>@<mail_domain>` from `config#mail`, gated by `mail_certified` (fail-closed `MailNotCertified` — but the readiness gate R5.4/R9.4 means a non-ready tenant never reaches submit).
- **Reply-To** (D8/D24): the all-scope `Members_CRUD` recipient SET (multi-address, mirrors the recipients); fallback to the `TenantAdmin` set when none. No configured Reply-To param, no single-pick tiebreak.
- **Staff email** carries a deep-link to `/members/{member_id}` (R8.6, no PII) + a neutral `DUP` marker when flagged (R8.6a). **Applicant email** embeds their own submitted data, applicant locale (R8a, R6b).
- Best-effort: throttle→retry→DLQ, permanent→DLQ (R8.8), never affects the committed record.

---

## 7. Flask authoring + projection (R4c/D18; steering 36 + 38)

- Tenant Admin authors the per-field application attributes in the existing `members.*` / `field_overlay` tenant-scope parameters (one authoring surface, steering 38 rule 5).
- `_projection_config_builders.build_config_fields_row` + its per-field maps are extended to carry `application_visible`, `application_required`, `application_choices`, and `format` 1:1 onto the `config#fields` row (no new row type) — `projection_sync` writes it.
- `projection_validator` / `members_config_validation` validate at Save (fail loud, R4c.3): subset ⊆ field choices; `format.checker` is a platform-known token; application-required cannot relax a platform-required field.
- The **optional scope-copy toggle** (D9a) is a new `members.*` param projected onto `config#mail`. (The per-tenant application Reply-To param is DROPPED — D24: Reply-To is the all-scope `Members_CRUD` set, not configured.)

---

## 8. Correctness properties

1. **Tenant isolation (Property 1):** every repository call keyed by `tenant_id`; the public path is covered by the SAME tenant-invariant test as the authenticated path (R2.5). A forged slug never resolves (R2.3).
2. **Server authoritative (R3):** status forced `application`; `tenant_id`/`member_id`/`status` stripped; only application-selected fields accepted; reuses the create spine's invariants.
3. **Verify-before-trust:** tenant from the allow-list, recipients only from the projection, consent timestamp + member_id server-minted.
4. **No boundary mix:** write + recipient resolution + send all SAM-plane; Flask only authors/projects config (D18).
5. **Best-effort notification never blocks the write** (D5); readiness gate means no accepted submission is silently un-notifiable (D15).
6. **Scope-generic:** no hardcoded `region`; all notification scoping via `<dimension>` grants (D9).

---

## 9. Error handling

- All errors via `_http._error` with a stable `code` the SPA localizes (api-response-standard v1.0, steering 37); English `detail` is fallback only.
- 422 validation → `_field_errors_array` `{field,code,detail}` keyed by dotted field id, mapped into Formik by key (R10a.3); error-summary ARIA live region (R10a.5).
- 404 for unknown slug is deliberately indistinguishable from no-endpoint (no enumeration oracle); the duplicate flag likewise never changes the applicant response (R3a.7).
- Catch-all returns a bodied 5xx (never empty 502), per the standard.

---

## 10. Testing strategy (steering 34 — SAM via `sam/pytest.ini`; Flask via `backend/tests`)

SAM-plane (`sam/tests/`): the public edge (skip-auth, slug→tenant, 404 non-probeable); the create
spine reuse + forced status + sanitize; required-ness (all required fields, not just email/IBAN);
the `FieldFormat` registry (EMAIL regex, IBAN mod-97, unknown-token degrade, `show_when` gating);
enum subset; session de-dup (update, not insert; concurrent single record); duplicate flag
(DUP note, neutral 202); recipient resolution (all-scope, scope-copy, TenantAdmin fallback,
NO_NOTIFY); offloaded best-effort send; sender resolution; Reply-To chain; locale; consent recording;
readiness gate; inbox-as-authoritative-channel; the R1a contract. Maps to requirements R14.1–R14.18.

Flask-plane (`backend/tests/`): `build_config_fields_row` carries the new attributes; the projection
validator rejects invalid subset / unknown checker; defaults project back-compatibly (R14.20). Paired
tests land in the same change (change-with-tests, steering 30/34).

Frontend: config-generated Yup parity with the server; server-422→Formik mapping by dotted key; axe
gate over the public form (R14.16). Per `33-frontend-testing`.

---

## 11. Governance / definition-of-done (steering 40 + 00-index)

- Extend `35-sam-module-architecture-sam.md` with the **public/unauthenticated intake** edge pattern + controls (R13.1); add a new **ADR** (companion to 0007) for the fenced exception (R13.2).
- **Per-tenant verified-sender dependency (R13.3).** The intake notification (D4/D15) depends on the tenant having a **verified SES sender** — `noreply@<mail_domain>`, gated by the `mail_certified` + `mail_domain` readiness check (§2.1). That per-tenant sender verification / certification process is **owned by** the existing spec [`Common/Serverless-applications/SNS-SES/SES Email Service`](../../Common/Serverless-applications/SNS-SES/SES%20Email%20Service/requirements.md) (companion: `../../Common/Serverless-applications/SNS-SES/ses-email-verification/`). This spec **consumes and references** that process — it does **not** re-document or re-scope SES verification here; a tenant without a verified sender is simply "not accepting applications yet" (readiness gate, D15). The staff-facing authoring UI is documented at `docs/docs/tenant-admin/sender-verification.md`.
- End-user docs: applicant form + staff review (R13.4).
- Building-block registry (37): the `FieldFormat` validator registry is members-local now; register it only on the second consumer (rule of three) — no row added in v1.

---

## 11a. Insertion points (verified against the code — the exact seams `tasks.md` builds on)

| New piece | File(s) | Add / modify | Mirror / precedent |
| --- | --- | --- | --- |
| (a) Public route + skip-auth (D27) | `sam/members/template.yaml`; new `sam/members/handler/public_app.py` | NEW separate public `AWS::Serverless::Api` (no `DefaultAuthorizer`, own stage/throttle) → a NEW `public_handler(event, context)` that resolves slug→tenant and does NOT call `_authenticate_and_authorize` | `handler()` flow in `app.py`; the `AddDefaultAuthorizerToCorsPreflight: false` carve-out precedent |
| Slug→tenant resolver (D19 — reuse landing-page slug) | new `sam/members/repository/tenant_slug_reader.py` (+ a thin slug→tenant_id projection seeded from the landing mapping) | New read over the EXISTING landing slug namespace (`<slug>.jabaki.nl` + KVS `myadmin-domain-slug-mapping`), NOT a new directory store | mirrors the fail-safe read discipline of `projection_config_reader`; unknown → 404 |
| (b) `create_application()` | `sam/members/domain/_membership_writes.py` (or a thin `ApplicationService` wrapper over it) | New method beside `create_member`; REUSES its spine (`_sanitize_write_payload` → stamp `tenant_id` → mint `member_id` → initial status → `_validate_member_record` → `_validate_membership_type_reference` → `save_member`), forcing `status=application` and adding the public-path rules | `create_member(tenant_id, body, allowed_scopes, *, requester_sub, caller_roles)` |
| (c) `FieldFormat` attribute + registry | `sam/members/domain/_field_models.py` (attr on `FixedField`/`OverlayField`/`ResolvedField`), new `sam/members/domain/field_formats.py` (registry); reader `projection_config_reader.py` `_build_format` | New frozen `FieldFormat{checker,params}` + `application_visible`/`application_required`/`application_choices`; `_build_format(spec)` + 3 attr reads in `_build_overlay_field`/`_build_override` | `MemberNumberFormat` + `_build_member_number_format`; `_build_options` |
| Generic validator step | `sam/members/domain/_membership_writes.py::_validate_member_record` | One loop over resolved fields with a `format`, gated by `show_when`, merge `FieldError` | sits beside `_validate_member_number` / `_drop_hidden_required_errors` |
| (d) `role-recipients` reader | new `sam/members/repository/role_recipients_reader.py` | Query tenant partition; keep `RECORD_TYPE_ROLE` role=`Members_CRUD`; filter all-scope via `scopegrant#<email>#<dimension>==["*"]`; `TenantAdmin` fallback | `projection_config_reader._query_partition`/`_classify` + `split_sort_key`; `pretokengen/projection_governance_reader` role filter |
| Duplicate-flag GSI + reader (D25) | `sam/members/repository/table_design.py` (GSI def + normalized `name+dob` key attr); `members_repository.py` (write the key attr on member create/update + a `query_by_name_dob`) ; `template.yaml` (GSI) | New GSI on `(tenant_id, name+dob)`; member items carry the normalized composite attr; a cheap indexed read for the flag | the existing key-attr/query patterns in `members_repository`; GSI wiring in `template.yaml` |
| appsession# de-dup item | `sam/members/repository/table_design.py` (`RECORD_TYPE_APP_SESSION` + `app_session_sk`); `members_repository.py` conditional put | New record type + conditional `attribute_not_exists` put | `RECORD_TYPE_MAIL_SENT` + `mail_sent_marker_sk` + the `mailsent#` conditional-put idempotency pattern |
| (e) Offloaded notification | new `sam/members/domain/application_notification.py`; worker extension `sam/members/worker/mail_send_worker.py`; `template.yaml` (2nd queue consumer or new job kind + IAM) | Enqueue two jobs via `MailSendQueuePort.enqueue`; worker branch renders the two templates, resolves recipients + `From` (`MailSenderResolver`) + Reply-To | `execute_and_deliver` enqueue; `MailSenderResolver`/`MailNotCertified`; `SesSender` port |
| (f) Flask projection extension | `backend/src/services/_projection_config_builders.py` (`_OVERLAY_FIELD_DEFAULTS`, `_FIXED_OVERRIDE_FIELDS`, `_map_*`); `members_config_validation.py`; `projection_validator.py` | Add `application_visible`/`application_required`/`application_choices`/`format` to the per-field maps carried onto `config#fields`; validate at Save | the existing `options`/`choices`/`scope`/`functional_group` carries; `_map_fixed_override` coherence rule |

## 12. Open items carried from requirements (design must still pin)

Tracked as `tasks.md` Phase 0 spikes; none blocks the architecture above.

- **RESOLVED — D19 (OQ2): tenant carrier reuses the landing-page slug** (`<slug>.jabaki.nl` +
  CloudFront KVS `myadmin-domain-slug-mapping`, `infrastructure/landing-pages.tf`); the API edge
  reads slug→`tenant_id` from a thin SAM-plane projection of that mapping. No new `tenant-directory`.
- **RESOLVED — D20 (OQ3): four sibling keys per field spec on `config#fields`**
  (`application_visible`/`application_required`/`application_choices`/`format`), mirroring the
  existing carries; no new row type.
- **RESOLVED — D21 (OQ4): membership_type required on the form, first subset option default;
  tenant-default stamp when not exposed.**
- **RESOLVED — D22 (OQ5): send-log reuses the `mailrun#`/`mailrecipient#` analytics mail model** —
  no new log store.
- **RESOLVED — D23 (OQ6): retention = manual delete by all-scope `Members_CRUD`, no auto-TTL in
  v1** (avoids auto-deleting a since-approved applicant; TTL + approval-clears-TTL is a future add).
- **RESOLVED — D24 (OQ7 Reply-To half): Reply-To = the all-scope `Members_CRUD` set, `TenantAdmin`
  fallback only** — no configured param, no tiebreak.
- **RESOLVED — D25 (OQ8): duplicate flag matches name+DOB via a `(tenant_id, name+dob)` GSI**
  (flag-only, neutral). Remaining: key normalization + GSI projection detail.
- **RESOLVED — D26 (OQ10): consent notice is tenant-authored + versioned**, projected via Flask
  config. Remaining: which projected row + the stored `consent{}` shape.
- **RESOLVED — D27 (OQ9): a separate public `AWS::Serverless::Api`** (no `DefaultAuthorizer`, own
  stage/throttle) + a dedicated `public_app.py` entrypoint; the authenticated API is untouched.
- **RESOLVED — OQ7 remainder: `TenantAdmin`** is the projected role segment for the member-module
  tenant-admin fallback.

**All Phase 0 spikes are now resolved (D19–D27).** Only normalization/projection-shape *details*
remain (noted per decision above); none blocks implementation.
