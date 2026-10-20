# Design — Pivot Output Actions & Scheduled Delivery

Technical design for the requirements in `requirements.md` (R0–R6). Analysis and
option trade-offs are in `design-options.md`. This document specifies architecture,
data model, API contracts, the send pipeline, security, error handling, testing, and
deployment.

## Steering this design follows

Rules are NOT restated here — this design conforms to them and cites the rule where it
applies.

- `35-sam-module-architecture-sam.md` — layering (handler→service→repository), data
  stays on the Members plane, rule 5a (no cross-plane storage), rule of three.
- `23-aws-accounts.md` — two-account model, `tenant_id` + `LeadingKeys` tenancy, `sam-`
  table naming, PAY_PER_REQUEST, SES is a nonprofit-deploy service.
- `22-authentication.md` — verified-JWT-only; tenant/roles from the verified token.
- `36-config-and-parameters.md` — MySQL `parameters` is the one writer; SAM reads a
  one-directional projection; config-selects-strategy via a resolver.
- `37-shared-building-blocks.md` — reach for a registered block; API response & error
  standard v1.0.
- `32-frontend-ui.md` — action/modal/i18n patterns; LazySelect; Table Filter Framework.
- `20-platform-architecture.md` — two planes + module contract.
- `34-backend-testing.md` / `33-frontend-testing.md` / `42-local-dynamodb-testing.md` —
  test markers, SAM fixtures, local DynamoDB discipline.
- `43-cicd-deploys.md` — branch→env, OIDC deploy, `samconfig.toml` per env.

---

## 1. Architecture overview

The feature spans the two planes defined in `20-platform-architecture.md`, but all
member data and all new feature data stay on the **Members (SAM/DynamoDB) plane** — no
cross-plane storage (rule 5a).

```
React (presentation only)
  │  DTO over HTTPS (X-Tenant selector; verified JWT)
  ▼
API Gateway  ──►  Members Lambda (handler = thin adapter, steering 35)
                    │  parse · verify JWT · active-tenant · authorize · delegate
                    ▼
                  Application / domain SERVICES  (business logic, storage-agnostic)
                    │   - delivery service (R3)
                    │   - execute-and-deliver service (R4)
                    │   - template service (R2)  → OpenRouter adapter (R2, behind a seam)
                    ▼
                  Repository  (ONLY DynamoDB touch-point; pins tenant_id)
                    ▼
                  DynamoDB  sam-members   +   S3 myadmin-shared (template body/logos)

Queue path (R4):  enqueue job ──► SQS ──► worker Lambda ──► SES  (drains at the SES rate)
Schedule path (R5): EventBridge Scheduler ──► enqueue the SAME job ──► same queue/worker
Cross-plane READ (R0 gate): Members edge reads the tenant "mail-enabled" flag via the
  projection (config#mail), NOT a live Flask call (steering 36).
```

Key architectural decisions (from requirements, settled):

- **One execute-and-deliver service**, invoked by both an interactive request and a
  scheduled run — so there is a single send path (R4/R5).
- **Queued, not synchronous** (R4): the request/schedule enqueues; a worker drains at
  the SES rate. New infra owned by this spec.
- **Templates owned by the Members module**, built behind a clean seam for later
  extraction to `sam/shared/templates/` on a second consumer (R2, steering 35 rule of
  three).
- **AI client is a Members-owned OpenRouter adapter behind a seam**, free-models-only,
  fail-closed on model choice (R2).

---

## 2. Data model (DynamoDB, `sam-members`)

Single-table design per `35`/`23`: PK `tenant_id`, SK `record_type#id`. New record
types are additive, following the `analyticsset#` precedent (`from_item` defaults absent
fields so legacy items load unchanged).

### 2.1 Delivery block on `AnalyticsSetEntry` (R3)

The delivery block is an OPTIONAL additive field on the existing `analyticsset#<set_id>`
item — NOT a new record type and NOT inside `PivotConfig.definition`.

```
# analyticsset#<set_id> item (additive `delivery` field; absent on legacy sets)
delivery: {
  mode: "per_recipient" | "to_fixed",
  template_id: "<template id>" | null,      # ref into template#<id> (R2)
  attachment:  "csv" | "pdf_labels" | null,
  recipients:  ["agent@example.com", ...],  # to_fixed ONLY; empty/absent for per_recipient
  label_options: { format, sort, font_size, alignment, border, country, start } | null
                                            # pdf_labels only; shared shape with R6
}
```

- `per_recipient` stores NO recipient addresses (resolved from the dataset at run
  time); stores the template + its merge fields.
- `to_fixed` stores the explicit `recipients` list.
- `label_options` is the SAME shape R6 uses interactively (one label-options model, not
  two).
- Serialization: the `delivery` field is added the **explicit** way — declare it on the
  SAM entity + its `validate()` rules + its legacy default in `from_item`, mirror it in
  the frontend `MemberAnalyticsSet` type and `toBackendConfig`/`fromBackendConfig`. This
  is the proven `origin`/`created_by` path; `floats_to_decimal` in the item builder
  already handles the numeric `label_options` generically. It does NOT round-trip for
  free — but the explicit path is DELIBERATE here: a generic additive-field
  serialization helper is a known idea DEFERRED to the backlog per steering 35 (rule of
  three — do not build the shared serializer for one entity). See `myBacklog/backlog.md`
  ("Generic additive-field serialization helper for SAM entities").

### 2.2 Template (R2) — new record type `template#<template_id>`

Metadata on-plane in `sam-members`; body + logo binaries in S3 `myadmin-shared` (400 KB
item limit + binary → never inline).

```
# template#<template_id>
{
  tenant_id, sk: "template#<template_id>", template_id,
  name,
  languages: { nl: { subject, s3_body_key }, en: { subject, s3_body_key } },
  merge_fields: ["first_name", "membership_type", ...],   # which fields the body uses
  logo_asset_ref: "<asset id>" | null,                    # reuses the asset/branding system
  origin: "user" | "preset",
  created_by, created_at, updated_at
}
```

- Body HTML lives at `s3://myadmin-shared/<tenant>/templates/<template_id>/<lang>.html`
  (tenant-prefixed, per `s3.tf`).
- Written behind a module-agnostic seam (no member-specific logic) so the whole template
  store/adapter/CRUD can extract to `sam/shared/templates/` on a second consumer.

### 2.3 Schedule (R5) — new record type `schedule#<schedule_id>`

```
# schedule#<schedule_id>
{
  tenant_id, sk: "schedule#<schedule_id>", schedule_id,
  set_id,                        # the analytics-set to run (must have a delivery block)
  cron: "<EventBridge schedule expression>",
  created_by,                    # must have been CRUD+region-all or admin at create (R5)
  enabled: true,
  created_at, updated_at
}
```

Tenant is pinned here (the scheduled run has no interactive user — R5). The run resolves
tenant-wide member scope because only a tenant-wide-capable role could create it.

### 2.4 Tenancy

Every read/write pins `tenant_id` as the partition key in the repository (the only
DynamoDB touch-point). IAM `LeadingKeys` remains the documented plan, not deployed —
isolation is structural (`35` rule 5 / the repository-invariant test). No `.scan()`.

---

## 3. API contracts

All responses use the API response & error standard v1.0 (`37`): success
`{success:true, data}`, error `{success:false, error, code?, params?, errors?[]}` with
the real HTTP status; every handler ends in a bodied 5xx catch-all. The SPA localizes by
the machine `code`.

New/changed routes on the Members Lambda (declared before `/members/{member_id}` so
literal paths win, as the analytics-set routes already are):

| Method & path | Purpose | Gate (capabilities) |
| --- | --- | --- |
| `PUT /members/analytics-sets/{set_id}/delivery` | set/replace a set's delivery block (R3) | `members:export` + scope |
| `DELETE /members/analytics-sets/{set_id}/delivery` | clear it | `members:export` + scope |
| `POST /members/analytics-sets/{set_id}/deliver` | run execute-and-deliver NOW (enqueues) (R4) | `members:export` + scope |
| `GET/POST/PUT/DELETE /members/templates[/{id}]` | template CRUD (R2) | `members:export` or `members:write` |
| `POST /members/templates/{id}/ai-improve` | AI adapt a template (R2) | `members:write` or `members:admin` |
| `GET/POST/PUT/DELETE /members/schedules[/{id}]` | schedule CRUD (R5) | `members:admin` OR (`members:write` + region-all) |
| `POST /members/sender-identities` + `GET` | tenant admin verifies/activates a sender (R0) | `members:admin` (tenant admin) |

- Recipients/attachments on the existing `POST /api/members/mail-set` are unchanged for
  R1 (the route already accepts plain external addresses); R1 is a frontend-only field.
- `deliver` and the schedule target return quickly with an accepted/enqueued result —
  the actual send happens in the worker (section 4).

Request bodies carry only domain fields; `tenant_id`, `created_by` (Cognito `sub`), and
roles come from the verified token (`22`), never the body.

---

## 4. The send pipeline (R4 queued, R5 scheduled)

### 4.1 Layering (steering 35 golden rule)

- **Handler** (thin): parse → verify JWT → resolve active tenant (`X-Tenant` validated
  against the token's tenants, ADR 0007) → authorize → delegate → respond. No logic, no
  DynamoDB.
- **execute-and-deliver service** (storage-agnostic): resolve the set, re-fetch member
  rows via the repository, run the pivot, build the output, and ENQUEUE send jobs. One
  service, called by both the interactive `deliver` route and the scheduled invocation.
- **Repository**: the only DynamoDB access; pins `tenant_id`.

### 4.2 Enqueue → worker → SES

```
deliver route / schedule fire
   └─ execute-and-deliver service
        ├─ per_recipient: resolve rows → one job per member (merge-field values + template ref)
        └─ to_fixed:      build attachment once → one job (fixed recipients)
   └─ enqueue job(s) to SQS  (members-mail-send[-test])
        └─ worker Lambda (SQS event source, bounded concurrency)
             ├─ render (mail-merge per recipient / attach for to_fixed)
             ├─ send via SES  (respect ALL SES limits — section 6)
             ├─ audit each send (metadata-only, log_analytics_output, ses_mail)
             └─ on failure: SQS retry; dead-letter (DLQ) after N attempts
```

- **Why queued (R4):** per-recipient mail-merge is N sends; a synchronous request would
  block / time out, and SES is rate-limited. The queue decouples trigger from send and
  drains at the SES rate.
- **One queue for both paths:** interactive `deliver` and the EventBridge-scheduled run
  enqueue the SAME job shape, so there is a single worker/send path (R4/R5).
- **Idempotency:** each job carries a stable id (set_id + run timestamp + recipient) so a
  retry/at-least-once SQS redelivery does not double-send (dedupe in the worker).

### 4.3 Scheduling (R5)

EventBridge Scheduler (nonprofit-deploy) fires per `schedule#<id>.cron` → invokes the
execute-and-deliver path for that set → enqueues as above. Tenant is read from the stored
schedule; member scope is tenant-wide (R5 gate guarantees the creator had tenant-wide
access). New infra; nothing like it exists today.

---

## 5. Templates & AI (R2)

- **Template service** (Members-owned, behind a module-agnostic seam): CRUD over
  `template#<id>` metadata + S3 body/logo; renders a template with merge values at send
  time (merge happens on-plane, never in the AI prompt).
- **OpenRouter adapter** (Members-owned, behind a seam — Option B, NOT the Flask code):
  `improve(template, instruction) -> improved_template`.
  - **Free-models-only, fail-closed.** The model id is config (`members.ai.model` or an
    allow-list), defaulting to OpenRouter's zero-price tier (`:free` ids or the
    `openrouter/free` router). The adapter REFUSES any model not on the allow-list — a
    costly model can never be selected by accident.
  - The prompt carries TEMPLATE + branding only; member PII is never sent (R2).
  - `OPENROUTER_API_KEY` is wired to the Members Lambda (today it lives Flask-side); the
    key is a secret, read fail-fast from env (`23` no-dangerous-fallback).
- **Extraction (rule of three):** everything template-related is written module-agnostic
  so a second module triggers extraction to `sam/shared/templates/`. Do NOT build the
  shared library now.

---

## 6. SES & R0 (production access, tenant senders, the mail-enabled gate)

### 6.1 Account & production access

- SES is a **nonprofit-deploy** service (`23`). Personal-account prod SES stays as-is
  (temporary; phase-out is in `myBacklog`).
- Nonprofit-deploy SES must reach **production** (today sandbox; prior request DENIED,
  case `178525018600435`). The re-request must honestly describe bulk/clubblad volume +
  opt-out. **This is a prerequisite (R0), owned by this spec** — not code, but in scope
  (steering 40: infra is in scope).

### 6.2 Tenant-managed senders (R0)

- A tenant admin verifies/activates their tenant's sender address(es) via
  `POST /members/sender-identities` → the backend drives SES identity verification
  (`VerifyEmailIdentity` / domain verification) in nonprofit-deploy and tracks status.
- The verified sender is what the worker sends `From` for that tenant.

### 6.3 The mail-enabled gate (R0, cross-plane READ)

- A per-tenant "mail-enabled / SES-certified" flag is OWNED by the tenant-admin module
  (Flask/MySQL `parameters`). The Members plane must READ it without a cross-plane data
  reach.
- **Mechanism (steering 36):** the flag is a projected `config#mail` row in
  `governance_projection`; the Members edge reads it via its projection reader (a Lambda
  never queries MySQL at request time, ADR 0005/0006). Flask writes, SAM reads
  one-directionally — same rails as `config#fields`/`config#scope`.
- The mail output actions (R1–R5) are offered only when the flag is set.

### 6.4 Respect ALL SES limits

The worker respects send rate, daily quota, recipients-per-message, message size, and
sandbox state. Reuse the existing throttle handling (`members_mail.py`
`_is_ses_rate_limited` → distinct 429); the queue naturally paces to the rate; chunk
per-member sends; surface quota exhaustion as a retryable condition (DLQ after N).

---

## 7. Frontend (R1, R2, R6)

Follows `32-frontend-ui.md`: row-click/action patterns, Chakra modal, Formik+Yup,
bilingual i18n (no hardcoded strings), responsive. Reach for registered building blocks
(`37`): LazySelect for the template picker; the API response & error standard for
surfacing structured errors by `code`.

- **R1** — add an "external recipients" field to `MemberMailCompose`; validate addresses
  client-side; send as `recipients: ["addr", ...]`. No backend change.
- **R2** — template picker (LazySelect) in the compose modal seeds subject/body; template
  management surface for CRUD + upload + "improve with AI"; language NL/EN.
- **R6** — a "Generate address labels" action in the `pivot-result-actions` slot (next to
  CSV / Mail), reusing `addressLabelService.generateAddressLabelPdf` and the existing
  (currently-unmounted) `AddressLabelGenerator` options UI; available only when
  `address_mapping` resolves + `members:export`; shares the `label_options` shape with
  R3's `to_fixed` labels delivery.
- Change-with-tests contract (`32`): update allocated `*.test.tsx` in the same change.

---

## 8. Security & data protection

- **AuthN/Z:** verified-JWT-only (`22`); tenant + roles from the token; `X-Tenant` is a
  selector among granted tenants, never a grant.
- **Authorization gates:** per the API table (section 3). `to_fixed` delivery needs only
  `members:export` + the existing scope (a stored delivery can send only what the user
  could already export — decided). Scheduling needs `members:admin` OR `members:write`
  with the `["*"]` all-regions grant (R5).
- **Tenancy:** repository pins `tenant_id`; no `.scan()`; `LeadingKeys` plan documented.
- **PII:** audit is metadata-only (`log_analytics_output`); the AI prompt never carries
  member data; per-recipient sends mean each recipient sees only their own email;
  in-memory attachment buffers released after send (existing R8.5 pattern).
- **Secrets:** `OPENROUTER_API_KEY` fail-fast from env; no secrets in CI (`43`, OIDC
  only).
- **External recipients / standing instructions:** a `to_fixed` delivery stores an
  external address — bounded by `members:export` + scope at create and at every (incl.
  scheduled) run; audited on send.

---

## 9. Error handling

- API response & error standard v1.0 (`37`): bodied errors with a machine `code`;
  never an empty 502.
- SES throttle → distinct retryable condition (not a hard failure); queue retries; DLQ
  after N attempts; a DLQ item is an operational alarm, not a silent drop.
- AI adapter: a disallowed model → fail-closed 4xx with a clear code; an OpenRouter
  error/timeout → the template is simply not improved (the user keeps the prefab), never
  a crash.
- Mail-not-enabled tenant (R0 flag unset) → the action is not offered; a direct call is
  rejected with a clear code.
- Config/validation rejected at the seam before store/projection (`36` rule 4).

---

## 10. Testing

Per `34-backend-testing.md` (markers, naming, SAM fixtures under `sam/tests`) and
`33-frontend-testing.md`; local DynamoDB per `42` (dev-only, via `control_bash_process`,
never foreground). TEST environment is the deployed `test_`-stack, not the emulator.

- **Domain/service (SAM pytest):** delivery-block validation (both modes), execute-and-
  deliver fan-out (per_recipient N jobs vs to_fixed one), tenancy invariant (every
  read/write pins `tenant_id`, no `.scan()`), schedule gate (CRUD-region-all/admin only),
  AI adapter fail-closed on a non-allow-list model, template merge renders without PII in
  the prompt.
- **Repository:** `to_item`/`from_item` round-trip for the new `delivery` field +
  `template#`/`schedule#` records; legacy set without a delivery block still loads.
- **Worker:** idempotent re-delivery (no double-send), SES-limit/throttle handling, DLQ
  after N.
- **Frontend (vitest):** compose external-recipient field, template picker (LazySelect),
  R6 label action availability gating; update allocated tests in the same change (`32`).
- **Cross-plane gate:** the mail-enabled flag read resolves from the projection
  (`config#mail`), not a live MySQL call.
- Coverage target 80% new code; focus on service logic + tenant isolation.

---

## 11. Deployment (steering 23 / 43)

- All resources in **nonprofit-deploy** (`506221081911`, `eu-west-1`): Members Lambda,
  the new worker Lambda, SQS queue + DLQ, EventBridge Scheduler, SES, S3 `myadmin-shared`.
- New SAM resources go in `sam/members/template.yaml`, parameterized per env; IAM scoped
  to the exact table/queue ARNs (no wildcard) — the existing exact-ARN pattern.
- Per-env via `samconfig.toml` (`sam-members` prod / `test_sam-members` test; CFN stack
  `test-sam-members` hyphenated). Branch→env: `test`→TEST, `main`→PROD (`43`); deploy via
  OIDC `NonprofitDeployRole`, no stored secrets.
- `OPENROUTER_API_KEY` added to the Members Lambda env per environment (secret).
- DynamoDB stays PAY_PER_REQUEST, managed outside CFN / Retain (`23`).
- Tables/queues are new infra owned by this spec (R0 principle: infra is in scope).

---

## 12. Open build-time items (not design blockers)

- The SES production re-request wording for nonprofit-deploy (R0) — must cover
  bulk/clubblad volume + opt-out so it is not denied again.
- Final `members.ai.model` allow-list values (free-tier ids churn — pin the tier/router +
  an allow-list, not a single model name).
- Worker concurrency / batch size tuning against the granted SES rate (known once
  production access lands).

---

## 13. End-user documentation

Every feature owes a manual section (`Common/end-user-documentation/`): the output
actions, templates (incl. AI-improve), delivery setup, scheduling, and the tenant-admin
sender-verification flow. Tracked in `tasks.md`.
