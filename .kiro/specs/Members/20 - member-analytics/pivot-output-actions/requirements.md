# Requirements — Pivot Output Actions & Scheduled Delivery

Members module feature: do more with a pivot result (send externally, use templates,
store a delivery, run on a schedule, print labels).

Rules we follow (do not restate them here — read the steering):
- `35-sam-module-architecture-sam.md` — layering + data stays on the Members plane.
- `23-aws-accounts.md` — accounts, tenancy, table names.
- `22-authentication.md` — auth / tenant context.
- `32-frontend-ui.md` — UI, modals, i18n.

Analysis and options live in `design-options.md`.

---

## R0 — Production SES in nonprofit-deploy, with tenant-managed senders

This spec OWNS the infra to make mail actually run (steering 40: scope includes the
infra, not only code). Built first, so R1–R5 build on a platform in a known state.

As a tenant administrator, I want to verify and activate my tenant's own sender email
address, so my tenant's mail goes out from an address we control.

- The **personal** account SES (`344561557829`) stays as-is — not touched.
- The **nonprofit-deploy** account SES (`506221081911`) must reach **production**
  (today it is sandbox; a prior request was denied, so the re-request must honestly
  cover bulk/clubblad volume + opt-out). This is where the Members Lambda sends from.
- A **tenant administrator can verify and activate their own tenant's sender email
  address(es)** in nonprofit-deploy, so a tenant mails from its own verified sender
  (sender verification UI + the backend to drive SES identity verification).
- A per-tenant **"mail-enabled / SES-certified" flag** (owned by the tenant-admin
  module) records whether a tenant is cleared to send; the mail output actions (R1–R5)
  read it to decide whether to offer sending. This onboarding gate is part of the
  prerequisite state — the scope does not work without it.
- Account roles stay per `23-aws-accounts.md`; this makes nonprofit-deploy SES prod
  (not a change to the account model).

> The onboarding gate lives in the tenant-admin module, but it is a PREREQUISITE for
> this scope (R0), not out of scope — the mail actions read its flag.

## R1 — Send to an external address

As a member-admin, I want to mail a pivot result to an address that is not in the
dataset (e.g. a handling agent), so I can hand the result to someone outside the list.

- Add an "external recipients" field to the mail compose modal.
- CSV and PDF-label attachments keep working as they do today.
- No backend change — the mail route already accepts plain addresses.

## R2 — Use a stored template

As a member-admin, I want to pick a stored, named template (NL/EN) for a member mail,
so I don't retype the message each time.

- Pick a template in the compose modal; it fills subject + body (still editable).
- Templates may use merge fields (e.g. first name), filled at send time.
- Templates are owned by the Members module (stored on its own plane, per steering 35).
- Later options: upload a template, or improve one with AI; a template may include a
  logo. The AI prompt never contains member data.
- AI client: a **Members-owned OpenRouter adapter behind a clean seam** (not the Flask
  code shared now) — extract to `sam/shared/` only when a second module needs it
  (steering 35, rule of three).
- **Cost guard — free / near-zero-cost models only, no expensive models.** Use
  OpenRouter's zero-price tier (the `:free` model IDs, or the `openrouter/free` router
  that picks a free model) or an explicit allow-list of near-zero-cost models. The
  model is config, not hardcoded, and the adapter must REFUSE a model outside the
  allow-list (fail closed) so a costly model can never be selected by accident.
- Build it so a second module can reuse it later (per steering 35) — but do not build
  the shared library now.

## R3 — Store a delivery on a saved set

As a member-admin, I want a saved set to remember what to do with its result, so
running or scheduling it repeats the send without re-entering everything.

- Add an optional `delivery` block to the saved set, separate from the pivot config.
- Two modes:
  - `per_recipient` — mail each member in the result individually with **real
    mail-merge** (the template's merge fields are filled from each member's row, so
    every recipient gets a personalized email). Addresses come from the data; not
    stored. Individual per-member sends depend on the server-side send (R4).
  - `to_fixed` — send the result as an attachment to a fixed address list (often one).
- Old sets without a delivery block keep working.
- Protection: the existing `members:export` capability + the existing scope (e.g. the
  `region` scope dimension) are sufficient. A stored delivery can only send what the
  user could already export within their scope — no new permission, no audit-on-save
  gate. (Normal send-time auditing per R4 still applies.)

## R4 — Send it server-side

As the system, I want one server-side component that runs a set and its delivery, so
an interactive send and a scheduled send use the same path.

- Logic lives in a Members service (not the handler); member rows are read through the
  repository. Layering per steering 35.
- `per_recipient` mail-merges and sends one personalized email per member; `to_fixed`
  builds one attachment for the fixed recipient list.
- Sends are **queued, not synchronous**: a request (or a schedule) enqueues the job and
  a worker drains it at the SES rate — the triggering request never blocks on the
  send, and a long run cannot time out. This queue + worker is NEW infra (none exists
  today) and is owned by this spec (per R0). The same queue serves interactive and
  scheduled sends.
- Respects all SES limits (send rate, daily quota, recipients-per-message, message
  size, sandbox); reuses existing rate handling and chunks per-member sends as needed.
  Failed sends retry via the queue (dead-letter after N attempts).
- Every send is audited (metadata only), including unattended runs.

## R5 — Run on a schedule

As a member-admin, I want a saved set + delivery to run on a schedule (e.g. monthly),
so a recurring send happens on its own.

- Attach a schedule to a set that has a delivery block.
- Scheduler: EventBridge → the Members Lambda (same plane). This is new; nothing like
  it exists yet.
- Scheduling is gated to callers with **tenant-wide member access**: either
  **`members:admin`**, or **`members:write` (CRUD) WITH an all-regions scope grant**
  (the `["*"]` wildcard). A CRUD user whose region is NARROWED (e.g. `["Oost"]`) may
  NOT schedule — an unattended run must never replay a partial regional slice. So a
  scheduled run always operates tenant-wide; there is no partial scope to resolve. The
  tenant is pinned in the schedule.
- Reuses the R4 send path; every scheduled send is audited.

## R6 — Print address labels from a result

As a member-admin, I want to generate/print Avery labels straight from a pivot result,
not only as a mail attachment.

- Add a "Generate address labels" action to the result actions (next to CSV / Mail).
- Reuse the existing label generator; let the user pick the Avery format.
- Available only when the tenant has an address mapping and the user may export.
- Share one label-options model with R3's `to_fixed` + labels delivery.

---

## Out of scope

- Sending via an external provider (Mailchimp etc.) — parked, not now.
- The shared template library — only when a second module needs it (steering 35).
- (SES tenant certification / the per-tenant mail-enabled gate is NOT out of scope —
  it is a prerequisite in R0. The tenant-admin module owns the flag; this spec depends
  on and reads it.)
- Other channels (S3 drop, webhook) — later.

## Notes for the design / build

- All earlier open questions are now decided (delivery permission = `members:export` +
  scope; scheduling = CRUD-with-region-all or admin; `per_recipient` = real mail-merge;
  send = queued; AI client = Members-owned seam, free-models-only).
- The one thing still to get right at build time (not a requirements choice): the SES
  production re-request wording for nonprofit-deploy. Status is KNOWN — personal =
  production (stays as-is), nonprofit-deploy = sandbox with a prior prod request DENIED
  (case 178525018600435). R0 covers taking nonprofit to production; the re-request must
  honestly cover bulk/clubblad volume + opt-out so it is not denied again.

## Reuses what already works

Already operational (so these requirements mostly add orchestration, not plumbing):
saved sets, pivot execute, CSV export, SES mail incl. external addresses and CSV/PDF
attachments, the Avery label generator, output auditing, and the infra (DynamoDB, S3,
SES, SNS, OpenRouter, assets). New work: the delivery block, the server-side send,
scheduling, per-recipient merge, the template store, and labels as a standalone action.

Every feature needs an end-user manual section (`Common/end-user-documentation/`).
