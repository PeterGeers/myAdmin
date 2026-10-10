# Design Document — Members mail sending (SAM plane)

## Overview

This design implements the mail requirements by CONSOLIDATING Members mail onto the SAM plane and
closing the gaps found in `analysis.md`. Much of the SAM pipeline already exists; the work is mostly
**wiring + plane-correction + per-tenant sender resolution**, not greenfield.

It is framed around four buckets — **already there (reuse)**, **add**, **change**, **remove** — so
scope and risk are explicit. Guiding rule (steering 35): React → API Gateway → Lambda (thin handler
→ domain service → repository) → DynamoDB → SES; a SAM module's data stays on the SAM plane (rule
5a); the React frontend only triggers + displays, never sends mail.

## Architecture

### Current (as-is) vs target
- **As-is (the bug):** the interactive pivot "Mail" send goes through the **Flask** route
  `POST /api/members/mail-set` (`backend/src/routes/members_mail.py`) → Flask `SESEmailService` →
  SES, from the Flask fallback sender `jabaki.nl`. The purpose-built SAM pipeline exists but is
  UNEXERCISED. This violates rule 5a and is the wrong-sender cause.
- **Target:** ALL Members mail flows on the SAM plane:
  `React → API Gateway → Members Lambda (edge → service → repository) → SQS → worker Lambda → SES`,
  with per-tenant From resolution and status recorded in the Members DynamoDB table.

### What is ALREADY THERE (reuse as-is)
- `sam/members/domain/execute_and_deliver.py` (`ExecuteAndDeliverService`): resolves a saved set +
  its stored `delivery`, re-fetches rows (tenant-pinned), runs the pivot, fans out to the
  `MailQueue` port — `per_recipient` → one `MailJob`/member; `to_fixed` → one job. Stable `job_id`.
- SQS `members-mail-send[-test]` + DLQ, the `MailQueue` SQS impl, and the deliver route
  `POST /members/analytics-sets/{set_id}/deliver` (202).
- Worker: `sam/members/worker/app.py` + `mail_send_worker.py` — drain → render → SES send →
  retryable/permanent classification (`is_ses_rate_limited`) → dedupe marker → audit
  (`mail_audit.py`, `ses_mail`). The ONE worker for both modes.
- `SesBotoSender` (`mail_send_adapters.py`) — `send_email`/`send_raw_email` + config set.
- `config#mail` projection + `is_mail_enabled` reader; templates (R2); schedules (R5).
- Frontend `MemberMailCompose.tsx` (per_recipient compose) + `MemberDeliveryEditor.tsx` (saves the
  `to_fixed` delivery block).

### What to ADD
1. **SAM interactive send route for ad-hoc `per_recipient`** (e.g. `POST /members/analytics-sets/{id}/send`
   or stateless `POST /members/mail/send`) + a thin service entry that builds the same `MailJob`s and
   enqueues on the SAME `MailQueue`/worker. (`ExecuteAndDeliver` is saved-set-only; the compose is
   ad-hoc: current result + typed recipients + template/attachment, no stored delivery.)
2. **Synchronous PRE-SEND certification check at the edge** (shared by both send routes): resolve the
   tenant From, run the §5c address-OR-domain SES check (+ account sending-enabled), refuse with a
   clear reason BEFORE enqueue if not certified.
3. **Per-tenant sender resolution**: From = `<mail_local_part|noreply>@<tenant-domain>` (from
   `config#mail`); Reply-To = the verified user email.
4. **`mail_domain` projection**: add to the `members.*` params + `build_config_mail_row` so
   `config#mail = { mail_enabled, mail_domain }` (ONE row).
5. **Send-run status**: `mailrun#<run_id>` records (+ per-recipient outcomes) in the Members table,
   written at enqueue, updated by the worker; `GET /members/mail-runs[/{id}]` read route; a React
   status/history view (user = own; Tenant_Admin = all tenant sends).
6. **Frontend "deliver now" trigger** for `to_fixed` → calls the EXISTING `/deliver` route.
7. **(Layered) SES feedback ingestion**: SES configuration set → SNS → handler records
   bounce/complaint/delivery against the Members `mailrun` records (routed by `run_id`/tag).

### What to CHANGE
1. `SesBotoSender` sender resolution: single global `SES_SENDER_EMAIL` → per-tenant
   `noreply@<tenant-domain>` + Reply-To = user (worker passes resolved values in).
2. `build_config_mail_row`: project `mail_domain` alongside `mail_enabled`.
3. `MemberMailCompose.tsx`: POST to the NEW SAM send route, not Flask `/api/members/mail-set`.
4. `MailJob`/audit plumbing: carry `run_id` + resolved From through to the worker + `mailrun` record.

### What to REMOVE
1. Members' use of the Flask `/api/members/mail-set` route (plane violation, R1) — retire for Members
   once the frontend uses the SAM route; confirm no other consumer before deleting the file.
2. The `jabaki.nl` substitute-sender fallback for Members (R4.2) — certified → send; not certified →
   clear error, no send, NO substitute.
3. `_build_pdf_labels` stays as a loud guard (interactive-only labels, bugs-to-solve #4) — not reachable
   via a valid saved delivery; not removed.

## Components and Interfaces

- **Edge handlers (thin):** the new interactive-send route; the existing `/deliver` route; the new
  `GET /members/mail-runs` read route. Each: authz (`members:export` + active tenant) → pre-send
  certification check → delegate → shape response. No business logic in the handler (rule 3).
- **Pre-send certification resolver (new, domain):** input = active `tenant_id`; resolves the tenant
  From from the projection and answers "is it a usable SES identity" via the §5c address-OR-domain
  check. Returns usable-From or a typed not-certified reason. Pure/injectable (SES port behind a seam).
- **`ExecuteAndDeliverService` (existing):** unchanged for `to_fixed`/saved-set; a sibling ad-hoc
  entry builds `MailJob`s for the interactive `per_recipient` compose and enqueues on `MailQueue`.
- **`MailQueue` port + SQS impl (existing):** unchanged.
- **Worker `MailSendWorker` (existing, extended):** now receives the resolved From + Reply-To and the
  `run_id`; updates the `mailrun` record per job; audit unchanged in shape.
- **`SesBotoSender` (changed):** accepts a per-send From + Reply-To rather than a single env sender.
- **`MembersRepository` (existing, extended):** add `mailrun` read/write methods (tenant-pinned).
- **Projection reader/builder (changed):** `config#mail` now carries `mail_domain`.
- **React:** `MemberMailCompose` (repointed), a "deliver now" action, a mail-status/history view.

## Data Models

- **`config#mail` (projection row, EXTENDED):**
  `{ tenant_id, sk:"config#mail", version, mail_enabled: bool, mail_domain: str, mail_local_part: str }`.
  `mail_local_part` is per-tenant configurable (e.g. `info`, `onderhoud`), DEFAULT `noreply` when unset.
  `mail_certified: bool` — the onboarding-recorded SES-verified flag (Option B); the pre-send check
  reads this (fail-closed when absent/false).
- **`members.mail_domain` (tenant parameter, NEW):** the tenant's mail domain (e.g. `h-dcn.nl`),
  authored at onboarding, projected into `config#mail`.
- **`members.mail_local_part` (tenant parameter, NEW, optional):** the From local-part (e.g. `info`),
  DEFAULT `noreply`; projected into `config#mail`.
- **`mailrun#<run_id>` (Members table, NEW):**
  `{ tenant_id, sk:"mailrun#<run_id>", mode, triggered_by, recipient_count, status:
  queued|sending|completed, sent:int, failed:int, created_at, updated_at }`.
- **`mailrecipient#<run_id>#<n>` (NEW, FAILURE-ONLY):**
  `{ tenant_id, sk, run_id, address, status: failed|bounced|complaint, reason?, message_id?,
  updated_at }` — written only for failures (incl. late async bounces/complaints). Successes are
  counted in the run tally, not stored per-recipient.
- Both `mailrun#` and `mailrecipient#` records carry a **`ttl`** epoch attribute (DynamoDB TTL,
  default 90 days) + support manual delete.
- **`MailJob` (existing, EXTENDED):** carries `run_id`, resolved `from_address`, `reply_to`.
- All rows pinned by `tenant_id` (LeadingKeys).

## Error Handling

- **Not certified (pre-send):** refuse synchronously → clear bilingual reason + action ("tenant mail
  not certified — contact your administrator"); no enqueue, no substitute sender.
- **SES rejection at send (worker):** captured in `SesSendOutcome.error`; classified
  retryable (throttle/quota → retry → DLQ after N) vs permanent (→ DLQ); reason recorded on the
  `mailrun`/recipient record.
- **Per-recipient (per_recipient):** a row with no resolvable address is skipped + reported; a single
  recipient failure never fails the whole run.
- **Async failures:** surfaced via the status view (R9) / notification, not a live wait.
- **No silent fallback** to a foreign sender anywhere.

## Correctness Properties

### Property 1: Plane isolation
No Members mail send touches the Flask backend; the whole flow is SAM-plane (rule 5a).

**Validates: Requirements 1.1, 1.2, 1.3**

### Property 2: Correct sender
Every sent mail's From = the active tenant's `noreply@<tenant-domain>` (or the send is refused);
Reply-To = the triggering user; never a foreign/substitute From.

**Validates: Requirements 4.1, 4.2, 4.3**

### Property 3: Tenancy
Every send and every status read is bounded to the active tenant (`tenant_id`); no cross-tenant
read/write.

**Validates: Requirements 1.4, 9.3**

### Property 4: Fail-closed
Not-certified / not-mail-enabled → no send; the gate opens only on explicit verified truth.

**Validates: Requirements 4.2, 5.1, 5.2**

### Property 5: Idempotency
A stable `job_id` means an at-least-once SQS redelivery never double-sends.

**Validates: Requirements 6.3**

### Property 6: No silent failure
Every refusal/failure yields a recorded, surfaceable reason (never a silent drop or a foreign-sender
fallback).

**Validates: Requirements 8.1, 8.3, 9.1**

## Testing Strategy

- **SAM pytest:** pre-send certification refusal (no enqueue, clear reason); per-tenant From
  resolution; both fan-out modes enqueue; worker sets From/Reply-To; `mailrun` status transitions;
  tenancy invariant (no `.scan()`, every op pins `tenant_id`); idempotent redelivery.
- **Frontend vitest:** compose POSTs to the SAM route (not Flask); deliver-now calls `/deliver`;
  status screen renders run outcomes; not-certified degradation message; change-with-tests on the
  repointed compose.
- **TEST stack end-to-end (R7):** both modes; From = tenant domain; Reply-To = user; audit + status
  written; no `jabaki.nl` regression.

## Resolved implementation choices (decided during design)
- §5c certification truth: **DECIDED = Option B** — an onboarding-recorded + PROJECTED verified flag
  (a `members.*` param in the `config#mail` row, same mechanism as `mail_enabled`/`mail_domain`). The
  pre-send check reads this flag; no SES call on the send path.
  - **Option A (live `GetEmailIdentity` at pre-send) is NOT built now but SHALL be noted as a future
    alternative in the pre-send resolver's DOCSTRING** — switch to it if the projected flag's
    staleness (certification lapses after projection) becomes a problem. Behaviour (the not-certified
    error) is identical either way; only the truth-source differs.
  - Implication: the onboarding process (documented, § onboarding) must record the verified flag, and
    a re-check/re-projection is needed if certification changes — same staleness caveat as any
    projected config.
- Interactive route: **DECIDED = two thin routes, ONE shared send service** (NOT an id-optional
  merged route — an empty/sentinel `{id}` in a path is a REST anti-pattern):
  - `POST /members/analytics-sets/{id}/deliver` (EXISTING) — saved-set + stored delivery.
  - `POST /members/mail/send` (NEW, stateless) — ad-hoc interactive send; body carries the current
    result / recipients / template / attachment.
  - BOTH delegate to the SAME underlying send logic (resolve/build `MailJob`s → enqueue). The
    id-vs-no-id branch is handled by WHICH route, not by a sentinel inside one route — DRY logic,
    honest URLs.
- `mailrun` records: **DECIDED = summary tally + FAILURE-ONLY sub-records.**
  - `mailrun#<run_id>` carries the aggregated tally (`recipient_count`, `sent`, `failed`, status).
    Successful recipients are only COUNTED (no per-recipient row).
  - A `mailrecipient#<run_id>#<addr-or-seq>` sub-record is written ONLY for a FAILURE (send-time
    reject / no-address / bounce / complaint), carrying `address`, `status`, `reason`.
  - LATE async bounce/complaint (R8.4) for a previously-"sent" recipient CREATES a failure
    sub-record at event time (there is none yet, since it succeeded at send) and increments the
    run's failed/adjusts counts.
  - **Retention:** manual delete action + a DynamoDB **TTL** auto-delete, DEFAULT **90 days**
    (configurable). 90d covers ~3 monthly newsletter cycles for look-back; records are tiny
    metadata. (NB: dedupe marker's 14d is a different, short-lived purpose; longer-term audit
    archiving, if ever needed, is a separate concern — not this status view.)
