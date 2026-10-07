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
   `sam-members-test`) as items with sort key `analyticsset#<set_id>` inside the
   tenant partition. Shape = `AnalyticsSetEntry`
   (`sam/members/domain/analytics_set.py`):
   `{ tenant_id, set_id, name, kind, definition, origin, created_by, timestamps }`,
   where `definition` is the snake_case `PivotConfig`. Reached via
   `GET/POST/PUT/DELETE /members/analytics-sets` — **not** the old Flask
   `/api/pivot/models` MySQL store (the F-012 migration: the Members module owns
   its own data on its own plane).

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
  higher-trust). Folding delivery into `PivotConfig` would also leak
  member-analytics delivery config into the shared SQL pivot framework that
  ignores that config.
- The entity already demonstrates the **additive pattern** (`origin`,
  `created_by` were added later; `from_item` defaults them for legacy items). So a
  sibling optional `delivery` block on `AnalyticsSetEntry` follows precedent.
- **Real plumbing cost (do not under-estimate):** because `to_item()`/`from_item()`
  serialize a fixed field list, a new block must be threaded through the SAM
  entity, the repository item builder, the frontend `MemberAnalyticsSet` type, and
  the `toBackendConfig`/`fromBackendConfig` boundary. It will NOT round-trip
  automatically.
- A delivery block would hold a list of named actions (e.g. `csv_to_email`,
  `template_mail`, `pdf_labels_to_email`), their fixed external recipients, the
  chosen template, and whether an attachment is included.

### ⚠️ Data-protection caution

Storing delivery config — **especially fixed external recipient addresses** —
changes the data-protection profile of a saved set. Today a set is just a query;
with stored recipients it becomes a **standing instruction to send member data to
a named address**. That deserves:

- an explicit permission **beyond `members:export`** (creating a standing export
  instruction is more than running an ad-hoc export), and
- **audit on save**, not only on send.

This should be decided deliberately before building.

---

## Scheduled execution ("6th of the month → send the paper-clubblad list")

**The biggest item here, and entirely net-new** — there is zero scheduling
precedent in the app. Two hard points to decide up front, not as wiring details:

- **No interactive user ⇒ whose scope?** Every send today is scope-correct because
  a logged-in user triggers it (rows come from that user's scope-authorized
  `GET /members`). A scheduled job has no interactive user, so it needs a trusted
  **service principal** and an explicit decision about **whose scope** the
  scheduled set runs under. This is a security design question, not plumbing.
- **Home = EventBridge Scheduler → the Members Lambda** (the SAM/DynamoDB plane
  where the analytics sets and member data already live), rather than Flask /
  Railway cron. It would re-execute the set server-side and run its stored
  delivery actions.
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
- Do we want per-recipient mail-merge, or is a single bulk body enough for the
  template feature?
- Is email the only delivery channel we care about now, or do S3 / webhook belong
  in scope early (they change the delivery abstraction)?
