# Pivot Output Actions & Scheduled Delivery — Design Options

## Context

Each Member Analytics pivot result has two output actions today:

- **Export to CSV** — downloads the result (the table's filtered/sorted rows).
- **Mail** — mails the members **in the result**, i.e. the recipient addresses
  are read off each result row via the field key resolved from the tenant's
  field config (`resolveEmailField`), BCC-by-default, optional CSV / PDF-label
  attachment, with a two-step confirm.

Both are **manual, interactive, single-actor, one-click** actions that operate on
the transient result. The saved set (`AnalyticsSetEntry`) stores only the
**definition** (what to compute) — there is no stored notion of **what to do with
the result**, and there is **no scheduler anywhere in the application**.

The questions this note answers:

1. Can we send the CSV to a specific address that is NOT in the dataset?
2. Can we mail a predefined template to the addresses in the dataset, with or
   without an attachment?
3. What other output options are relevant (best practice)?
4. Should the handling of execute results be stored in the pivot definition?
5. What about planned (scheduled) execution — e.g. "every 6th of the month, send
   the paper-clubblad distribution list to the agent who handles it"?

---

## Where the data lives (SAM / DynamoDB) — and the computation wrinkle

Two different "data" things are in play, in different places:

1. **The saved pivot / analytics-set *definitions*** → **SAM → DynamoDB.** Stored
   by the Members SAM Lambda in its DynamoDB table (`sam-members` prod /
   `test_sam-members` test) as items with sort key `analyticsset#<set_id>` inside the
   tenant partition. Shape = `AnalyticsSetEntry`
   (`sam/members/domain/analytics_set.py`):
   `{ tenant_id, set_id, name, kind, definition, origin, created_by, timestamps }`,
   where `definition` is the snake_case `PivotConfig`. Reached via
   `GET/POST/PUT/DELETE /members/analytics-sets`. The Members module is
   **autonomous** — it owns its own data on its own DynamoDB plane, with **no
   cross-plane traffic** (F-012). Everything in this spec stays on that plane.

2. **The member *rows* the pivot computes over** → also from the Members SAM
   module (DynamoDB), served by `GET /members`. **But the pivot does NOT run
   server-side against the table.** Execute calls
   `executeMemberPivot(processedData, config, fieldConfig)` — a **client-side**
   adapter. `processedData` is the already-loaded, scope-authorized member rows
   the Members overview fetched for the current user. So the records originate in
   DynamoDB, but the aggregation / listing happens **in the browser**, over the
   rows already loaded for that user's scope — it is not a DynamoDB-side query.

**Why this matters for scheduling (below):** today the pivot is scope-correct
*because* it runs in the browser over rows a logged-in user already pulled. A
scheduled, user-less run cannot rely on that — it would have to **re-fetch member
rows server-side** (from DynamoDB, in the Members Lambda) under a service
principal, which forces the explicit "whose scope?" decision called out in the
Scheduled-execution section.

**Account boundary (steering 23).** Every infra resource this feature touches —
DynamoDB (`sam-members`), S3 (`myadmin-shared`), SES, SNS, EventBridge, and the
`OPENROUTER_API_KEY` secret (Secrets Manager / SSM) — lives in the **nonprofit-deploy
account (`506221081911`, `eu-west-1`)**. The Cognito `sub` used as the owner key for
per-user items (preflist / column prefs / future templates) comes from the **personal
identity account (`344561557829`)**. The two-account split is a design constraint, not
a detail: anything stored or sent runs in nonprofit-deploy, under its execution role
scoped to the exact `sam-*` table ARNs (defense in depth over `tenant_id`
LeadingKeys).

---

## What exists today (so the gaps are concrete)

- **Mail route** (`POST /api/members/mail-set`, `backend/src/routes/members_mail.py`):
  gated by `members:export`, tenant always from the verified auth context, BCC
  every recipient, optional base64 CSV/PDF attachments, SES rate-limit mapped to
  a distinct 429, self-audits on success. It already accepts **plain email
  strings** in `recipients`, not only member rows.
- **Compose modal** (`MemberMailCompose.tsx`): subject/body seeded from bilingual
  i18n strings and edited inline — there is **no stored/named template**.
- **Saved set** (`sam/members/domain/analytics_set.py` `AnalyticsSetEntry`):
  `{ tenant_id, set_id, name, kind, definition, origin, created_by, timestamps }`.
  `definition` is the snake_case `PivotConfig`. `to_item()`/`from_item()`
  serialize a **fixed field list** — a new top-level block does not round-trip
  for free, but `origin`/`created_by` prove the additive-field pattern works.
- **Audit** (`backend/src/services/analytics_audit.py`): every output
  (`csv_export` / `pdf_labels` / `ses_mail`) is logged **metadata-only** (actor,
  tenant, set_key, record/recipient count, PII-free filter summary) to the
  CloudWatch access log. There is **no persisted results store** beyond this log.
- **Scheduling:** none. No EventBridge/scheduled Lambda, no Flask cron, no Railway
  cron. (The only crons in the repo are a GitHub Actions nightly test run and a
  docs backup example — neither is an app-job hook.)

---

## The two concrete asks

### Ask 1 — CSV to a specific external address (not in the dataset)

**Smallest gap of everything here.** The mail route already accepts plain email
strings in `recipients`, and the compose modal already builds the CSV attachment.
The only missing piece is a **UI affordance**: an "external recipients" free-text
field in the compose modal, sent as `recipients: ["agent@example.com"]` with
`email_field` ignored. **Frontend-only, no backend change, no stored state.** Best
quick win.

### Ask 2 — Template-based mail to the dataset addresses (± attachment)

**Medium gap.** The send path and attachments already exist; what is missing is a
**stored, named template** (bilingual subject + body, optionally with merge
placeholders like member first name). Today subject/body are only i18n seed
strings edited inline. Needs a template store + a template picker in the compose
modal.

---

## Other relevant output options (best practice)

- **CSV to a cloud destination** — write the file to S3 / a shared Drive folder
  instead of (or alongside) email. Right when the distribution list feeds another
  system or is too large to email. (S3 + a gdrive template already exist in-repo.)
- **PDF address labels as the delivery itself** — Avery-label generation already
  exists; "send the labels to the handling agent" is a first-class output, not
  just an attachment toggle.
- **Webhook / API push** — POST the result rows to an external endpoint (print
  shop / fulfilment partner). Directly relevant to a paper-clubblad list a third
  party processes.
- **Per-recipient personalization (mail-merge)** — today a bulk mail BCCs everyone
  the same body; a template with merge fields sent individually is the natural
  companion to Ask 2.
- **Download-again / resend-last-run** — persist the last result (or a signed S3
  link) so an agent can re-fetch without re-running. Ties into scheduling.
- **Delivery confirmation surfaced back** — SES bounce/complaint is already tracked
  via SNS → `email_log`; surfacing "3 bounced" on the set would close the loop.

---

## Design question — store delivery handling in the pivot definition?

**Recommendation: yes, but as a separate additive `delivery` block, NOT folded
into `PivotConfig`.**

- `PivotConfig.definition` answers *"what rows do I compute?"*; delivery answers
  *"what do I do with them?"* — different concerns, different lifecycles, different
  trust levels (computing is read; emailing external parties / scheduling is
  higher-trust). `PivotConfig` is a shared type; keeping delivery OUT of it keeps
  the Members plane self-contained and avoids leaking member-specific delivery
  config into a type other consumers ignore.
- The entity already demonstrates the **additive pattern** (`origin`,
  `created_by` were added later; `from_item` defaults them for legacy items). So a
  sibling optional `delivery` block on `AnalyticsSetEntry` follows precedent.
- **Real plumbing cost (do not under-estimate):** because `to_item()`/`from_item()`
  serialize a fixed field list, a new block must be threaded through the SAM
  entity, the repository item builder, the frontend `MemberAnalyticsSet` type, and
  the `toBackendConfig`/`fromBackendConfig` boundary. It will NOT round-trip
  automatically.

### The two delivery modes are fundamentally different — model as a discriminated kind

There are **two distinct mail semantics**, not two settings of one. They differ in
*who* the recipients are, *where that list comes from*, whether the body is
personalized, and their data-protection profile. The `delivery` block should carry
an explicit **`mode` discriminator** rather than a flat blob (illustrative shape —
NOT the final contract; the typed schema is a design.md deliverable):

```
delivery: {
  mode: "per_recipient" | "to_fixed",
  template: <template ref>,          # both modes
  attachment: "csv" | "pdf_labels" | null,
  recipients: [ ... ],               # to_fixed ONLY (often length 1)
}
```

- **`per_recipient` — recipients come FROM the dataset.** The pivot result *is* the
  mailing list; each resolved member row is one recipient, mailed at their own
  address (resolved at run time via the existing `resolveEmailField`). This is the
  natural home for **mail-merge personalization** — the body changes per recipient
  from that member's fields (`Dear {first_name}, your membership {type}…`). The
  recipient list is **dynamic** (whoever the pivot resolved this run — 5 or 500) and
  is therefore **NOT stored**. What IS stored is the template + which merge fields
  it uses. This is a refinement of today's bulk Mail action (which BCCs the rows)
  toward per-recipient individual sends. **Lower data-protection risk:** no standing
  external address is persisted.

- **`to_fixed` — recipients are FIXED in the delivery config.** The pivot result is
  an **attachment/payload** (CSV / PDF labels) sent to a small, predefined address
  list — often exactly one (the agent handling the paper clubblad, a print shop, an
  ops mailbox). The recipients are **not** in the dataset and do **not** change when
  the data changes; there is **no** per-recipient personalization (one email, one
  body, result attached). This is the mode that stores explicit recipients.

The discriminator maps cleanly onto the risk tiers below: `per_recipient` stores
little and leans on the existing scope-correct recipient resolution; `to_fixed` is
the one that turns a saved set into a standing export instruction.

### ⚠️ Data-protection caution (applies mainly to `to_fixed`)

Storing delivery config — **especially the fixed external recipient addresses in
`to_fixed`** — changes the data-protection profile of a saved set. Today a set is
just a query; with stored recipients it becomes a **standing instruction to send
member data to a named address**. That deserves:

- an explicit permission **beyond `members:export`** (creating a standing export
  instruction is more than running an ad-hoc export), and
- **audit on save**, not only on send.

`per_recipient` is lower-risk on this axis (no stored external address — recipients
are re-resolved from the scoped dataset each run), but it carries its own scope
concern once scheduled (see below). This should be decided deliberately before
building.

### Server-side send component (a Members Lambda action), especially for `per_recipient`

A per-recipient personalized send is **not** a good fit for the browser: a bulk
mail-merge means N individual SES sends with per-row bodies, subject to the SES
per-second rate (today the client Mail action does a single BCC send, which does
not personalize). The cleaner home is a **server-side send on the Members
Lambda plane**:

- A user (or a schedule) issues one request — *"execute this set and run its
  delivery"* — and the **Members Lambda** does the fan-out: re-resolve the rows
  server-side, render the template per recipient (`per_recipient`) or build the
  attachment once (`to_fixed`), and drive the SES sends (honoring the rate limit /
  the existing throttle handling, chunking as needed).
- **Layering (steering 35, golden rule).** This is NOT a monolithic handler. The
  Lambda **handler** stays a thin adapter (parse → authenticate + active-tenant
  context → authorize → delegate → respond); the execute-and-deliver logic lives in
  an **application/domain service** (storage-agnostic, testable, reusable by both the
  interactive route and the scheduled invocation); the server-side **re-fetch of
  member rows** goes through the **repository** — the only DynamoDB touch-point —
  which pins the `tenant_id` partition key. No business logic or direct DynamoDB
  access in the handler.
- This keeps member PII and the recipient fan-out **server-side** (not assembled in
  the browser), reuses the existing SES delivery-tracking + audit path, and gives
  **one** execution component that both an interactive request AND a scheduled run
  (EventBridge → same Lambda) call — so scheduling does not need a second send path.
- It also forces the **scope decision** into one place: an interactive call runs
  under the caller's scope; a scheduled call runs under a service principal whose
  scope must be stated explicitly (the open decision below). `per_recipient` is
  where this bites hardest — "which members get mailed" must be re-resolved
  server-side with no interactive user; `to_fixed` is easier (recipients are fixed,
  only the attachment contents are recomputed).
- **Trade-off / alternative:** for `to_fixed` with a single small attachment, a
  synchronous send in the request path may be enough and the Lambda fan-out is
  overkill. The Lambda-executor pattern earns its keep for `per_recipient` fan-out
  and for anything scheduled. For very large sends, an async/queued variant (enqueue
  the job, a worker drains it) avoids a long-running request — worth considering if
  list sizes grow, but not needed for the first cut.

### Volume reality

**Current/anticipated volume does NOT force heavy infrastructure.** The largest
list today is a few hundred; a future tenant might reach ~1000. At SES production
rates (order ~14 msg/sec, raisable), 1000 individual `per_recipient` sends is a
minute or two of sending — comfortable inside a single **async Lambda** invocation.
So on throughput alone, the Members-Lambda executor (sync `to_fixed` / async
`per_recipient`) is sufficient; SQS/fan-out machinery is NOT needed at these sizes.

> **Remark (no consequences now):** delegating `per_recipient` newsletter sends to
> an ESP (Mailchimp / SendGrid / Brevo) could later add managed deliverability +
> built-in unsubscribe, at the cost of member PII leaving the plane (DPA). Parked
> as a possibility only — not part of the current design.

---

## Template management (Members-owned now; genericity DEFERRED per steering 35)

The stored template behind Ask 2 should NOT be a one-off member-mail feature. The
need is a reusable template-management capability: store a prefab template, let a
user **upload** an externally-authored (incl. AI-generated) version, OR
**adapt/improve** a stored prefab via an OpenRouter-supported model, and support
**logos / images** as part of the template. Member Analytics is the **first
consumer** of this capability — but, per steering 35, "first consumer" means Members
**owns its own template data on its own plane** and builds the capability behind a
clean seam; the *shared* library is extracted only when a second module needs it. It
is NOT a shared service built up-front, and NOT data stored off-plane.

### A lot of this already exists in fragments (so it is NOT greenfield)

- **OpenRouter is already integrated.** `OPENROUTER_API_KEY` is a known env var
  (`backend/validate_env.py`, `drift_detector.py`), and there are e2e tests for
  **AI template help / apply-AI-fixes** against the real OpenRouter API
  (`frontend/tests/e2e/template-real-data.spec.ts`) — almost certainly the
  landing-pages feature. The "AI adapts a template" pattern is partly built already,
  just not for mail templates.
- **S3 already stores templates + branding.** `infrastructure/s3.tf` provisions
  `myadmin-shared-<env>` explicitly for "tenant-prefixed invoice, **branding, and
  template** storage" — encrypted, versioned, private, with CORS for browser
  uploads. The right home for template HTML + logo binaries (NOT inline in a
  DynamoDB item — 400 KB limit + binary).
- **Logos already have an asset/branding pattern** — an asset system
  (`original_filename`, `mime_type`, `presigned_url`, dedup/merge in Asset Admin)
  plus tenant branding config (`company_logo_file_id`). "Templates include logos"
  reuses this, rather than inventing logo storage.
- **Email templates already exist Flask-side** (`list_email_templates` in
  `tenant_admin_email.py`).

So the ingredients (AI adapter, S3 template/branding store, asset/logo system) are
already spread across the app — the gap is that they are **per-feature, not a single
reusable template service.**

### The ruling — steering 35 settles "generic" (CODE shared, DATA per-module, extract on the SECOND consumer)

My earlier instinct toward a generic shared template *service/adapter* built now is
**wrong per steering `35-sam-module-architecture-sam.md`**. Two rules there govern
this directly:

- **Rule 5a — a SAM module's data (INCLUDING feature/config data like templates) is
  persisted by its OWN repository, in its OWN DynamoDB table, via its OWN Lambda.**
  "Reuse the client/engine **CODE** across planes if useful; **never reuse the other
  plane's STORAGE.**" So prefab member templates live in **`sam-members`** (as a new
  record type), NOT in a shared/Flask store, and NOT in a single cross-module table.
  This also means the existing Flask-side AI-template machinery is **prior-art CODE
  to learn from / potentially share**, never a store to persist member templates in.

- **Shared SAM application-capability pattern — CODE may be shared via
  `sam/shared/<capability>/`, but build per-module FIRST and extract on the SECOND
  consumer (rule of three).** The steering explicitly says: do NOT build the shared
  abstraction while there is one consumer; write the first module's implementation in
  **module-agnostic files with a clean seam**, so the second module that needs it
  triggers the extraction. **Member Analytics is named as the first such consumer;
  the shared library is NOT built until the second.**

So "generic" here does **not** mean "build a shared template service now." It means:
**build template management inside the Members module, on the Members plane, in
module-agnostic files with a clean seam, so it can be extracted into
`sam/shared/templates/` when a SECOND module needs it.** That satisfies both the
autonomy rule and the (deferred) genericity ambition.

### What this resolves to (per the ruling)

- **Storage — Members-owned, on-plane.** Template **metadata** (name, language,
  merge-fields used, S3 key, logo asset ref, timestamps) → a new `sam-members`
  record type (e.g. `template#<template_id>`), following the same additive pattern as
  `analyticsset#`, written by the Members repository via the Members Lambda. Template
  **body** (HTML + merge placeholders) + **logo/image binaries** → the existing S3
  `myadmin-shared` bucket (NOT inline in a DynamoDB item — 400 KB + binary),
  referenced by key. S3 is a shared *primitive*, not another plane's record store, so
  this does not violate 5a.
- **AI adapt/improve + upload — CODE reuse is fine, data stays on-plane.** The
  OpenRouter integration already exists Flask-side; its **client/engine code** is a
  candidate to share (or re-implement behind a clean seam), but the Members module
  calls it from its own Lambda and stores the result in `sam-members`. `upload` =
  user supplies the body directly (no model call); `adapt/improve` = OpenRouter call
  (in = stored prefab + instruction, out = revised template). Both land in the
  Members store.
- **Clean seam now, extraction later.** Write the set CRUD / template store / AI
  adapter / result-export in module-agnostic files (no member-specific logic baked
  in), so Events/Webshop becoming the second consumer triggers the
  `sam/shared/templates/` extraction — exactly the rule-of-three path the steering
  prescribes. Do **not** build `sam/shared/templates/` while Members is the only user.
- **Data-protection.** The adapt/improve prompt carries the TEMPLATE + branding only
  — **never member PII**. Merge happens at SEND time on-plane, not in the AI prompt.
- **Secrets.** `OPENROUTER_API_KEY` already exists Flask-side; a Members-Lambda caller
  needs it wired to that Lambda. (A shared key owner is a *later* extraction concern,
  not a reason to centralize storage now.)

### Scope note

This is a **substantially larger** effort than the inline "stored template" picker in
Ask 2 — it is a module capability with its own on-plane storage, S3 body/logo
handling, and an AI integration. Ask 2's picker is the **thin first slice** (pick a
stored template); upload + AI-adapt + logos layer on as the Members-owned template
capability matures — all built behind a clean seam so a future second consumer can
extract it to `sam/shared/templates/` without a rewrite.

---

## Scheduled execution ("6th of the month → send the paper-clubblad list")

**The biggest item here, and entirely net-new** — there is zero scheduling
precedent in the app. Two hard points to decide up front, not as wiring details:

- **No interactive user ⇒ whose scope?** Every send today is scope-correct because
  a logged-in user triggers it (rows come from that user's scope-authorized
  `GET /members`). A scheduled job has no interactive user, so it needs a trusted
  **service principal** and an explicit decision about **whose scope** the
  scheduled set runs under. This is a security design question, not plumbing.
  - **Mechanism (steering 23 + 35).** The active tenant normally comes from the
    `X-Tenant` header validated against the caller's entitlements (ADR 0007); a
    scheduled run has no header, so the **tenant must be pinned in the stored
    schedule config** and the service principal still scopes every read/write by the
    `tenant_id` partition key with IAM `LeadingKeys` as defense in depth — the
    established module-plane tenancy, not a new path. The remaining decision is
    whose *member-scope* (which rows within the tenant) the run resolves under, since
    there is no interactive user whose scope to inherit.
- **Home = EventBridge Scheduler → the Members Lambda** (the SAM/DynamoDB plane
  where the analytics sets and member data already live). Keeping the scheduler on
  the same plane preserves the module's autonomy — it re-executes the set
  server-side and runs its stored delivery actions without reaching across planes.
- **Depends on stored delivery config** — you cannot schedule an action that only
  exists as transient UI state, so scheduling sits on top of the `delivery`-block
  decision above.

---

## Suggested sequencing (value-to-effort)

1. **External-recipient field in the mail modal** (Ask 1) — small, frontend-only,
   no stored state. Immediate win.
2. **Stored mail templates** (Ask 2) — a template store + a picker in the compose
   modal.
3. **Delivery block on the saved set** — additive `delivery` metadata + its own
   permission + audit-on-save.
4. **Scheduled execution** — EventBridge Scheduler → Members Lambda, built on top
   of (3), with the service-principal / scope decision made explicitly.

Each stage is independently useful; each later stage depends on the earlier one.

---

## Open decisions to confirm before building

- Is a standing stored export instruction acceptable, and under what new
  permission? (delivery-block gate)
- Whose data scope does a scheduled, user-less run execute under? (service
  principal + scope)
- For `per_recipient`, do we want true per-recipient mail-merge (individual sends
  with merged bodies), or is today's single bulk BCC body enough for the first cut?
- Does the server-side send run synchronously in the request, or async/queued? (A
  Lambda executor is justified for `per_recipient` fan-out and all scheduled runs;
  a small single-attachment `to_fixed` send may not need it.)
- Template management storage/location is NOT open — steering 35 (rule 5a + the
  shared-capability pattern) settles it: Members-owned templates in `sam-members` +
  S3 for body/logos, built behind a clean seam, extracted to `sam/shared/templates/`
  only on the SECOND consumer. The open parts are narrower: (a) whether to share the
  Flask OpenRouter client CODE now or re-implement behind the seam, and (b) the
  template record shape + merge-field model.
- Is email the only delivery channel we care about now, or do S3 / webhook belong
  in scope early (they change the delivery abstraction)?

---

## Future task (cross-cutting prerequisite) — SES tenant certification at onboarding

**Noted here so it is not forgotten; it is NOT built on the Members plane and is
NOT part of this spec's implementation.**

Every tenant that will send mail (Ask 1 external-recipient CSV, Ask 2 bulk member
mail, and especially scheduled sends) depends on the tenant being **SES-certified**
— i.e. a verified sender identity *and* an SES account/tenant that can actually
deliver to real recipients (out of the sandbox, with adequate sending quota). This
is an **operational onboarding prerequisite**, not a feature of the pivot output
actions themselves.

- **Where it belongs:** the **Flask tenant-administrator module** (tenant
  onboarding/provisioning), NOT the Members SAM/DynamoDB plane. It is a
  cross-cutting, per-tenant setup step, so it lives with the rest of tenant
  provisioning — this keeps the Members module autonomous (no new cross-plane
  dependency introduced by this spec).
- **What "certification" covers:**
  - a **verified sender identity** for the tenant (domain or address verification
    — today the platform sends from the shared verified `support@jabaki.nl`;
    per-tenant sender identity is a separate decision to make here),
  - **SES production access** (out of the sandbox) so mail reaches non-verified
    real recipients — **[TO VERIFY]** the current sandbox/production status is
    per-account/per-region in nonprofit-deploy (`506221081911` / `eu-west-1`) and
    has NOT been confirmed; a read-only `aws sesv2 get-account` settles it,
  - **sending-quota headroom** appropriate to the tenant's list sizes (bulk /
    scheduled sends can hit the per-second rate or daily cap).
- **Why it is a prerequisite, not a nice-to-have:** in the sandbox, Ask 1 (CSV to
  an external agent) is blocked unless that address is verified, and Ask 2 / any
  scheduled bulk send cannot reach real members at all. So onboarding must record
  and gate on a tenant's SES-certified status before these output actions are
  offered to that tenant.
- **Suggested shape:** a tenant-onboarding checklist item + a stored per-tenant
  "mail-enabled / SES-certified" flag the tenant-admin module owns; the Members
  mail/scheduling UI can later read that flag (via the normal API boundary, not a
  cross-plane data reach) to decide whether to surface the mail output actions.

**Action:** add this as a backlog item in the **Flask tenant-administrator
onboarding** module. Tracked here only as a dependency reminder for the mail /
scheduled-delivery stages above.
---

## Spec workflow / next steps (steering 40)

This document is the **analysis / design-options artifact** (step 1 of the spec
workflow). It is NOT the spec trio. Per steering 40 a spec folder carries
**`requirements.md` → `design.md` → `tasks.md`**; those do not yet exist here. The
"Suggested sequencing" above is pre-tasks shaping, not a `tasks.md`.

Next steps to make this a conformant Members *feature* spec:

1. **`requirements.md`** — user stories + acceptance criteria for Ask 1, Ask 2, the
   `delivery` block, and scheduling; explicit out-of-scope (ESP delegation, the
   shared `sam/shared/templates/` extraction, SES tenant certification).
2. **`design.md`** — the typed `delivery` / `template#` schemas, the API contracts,
   the handler → service → repository layering (steering 35), tenancy
   (`tenant_id` + `LeadingKeys`), and the correctness/security properties.
3. **`tasks.md`** — phased, <1-day chunks with testing per phase.

Per steering 40, the SAM-plane capabilities this feature **consumes** (the handler
edge/auth, SES/SNS, the EventBridge scheduler) are governed under
`Common/Serverless-applications/` + steering 35 — reference them, do not redefine
them here.

## References (reusable patterns — steering 40)

- **SAM module architecture / layering + shared-capability rule:**
  `35-sam-module-architecture-sam.md` (handler = thin adapter; data per-module;
  rule-of-three extraction).
- **AWS accounts / tenancy / table naming:** `23-aws-accounts.md` (nonprofit-deploy
  vs. personal; `sam-*` + `test_` prefix; `tenant_id` + `LeadingKeys`).
- **Authentication / verified-JWT at the edge:** `22-authentication.md`; active-tenant
  resolution ADR 0007.
- **Frontend UI — action buttons + table/modal + i18n:** `32-frontend-ui.md`. The
  Ask 1 "external-recipient field" and Ask 2 "template picker" follow the
  BankingProcessor action pattern (row-click opens a modal, no inline buttons) and
  must be bilingual (i18n), consistent with the existing compose modal.
- **End-user documentation:** every feature needs a manual section per
  `.kiro/specs/Common/end-user-documentation/` — the output actions, templates, and
  scheduling each owe one (add as a task in `tasks.md`).
- **Generic filter framework:** `.kiro/specs/Common/Filters a generic approach/` —
  relevant if the saved-set filter summary / delivery filters reuse it.
