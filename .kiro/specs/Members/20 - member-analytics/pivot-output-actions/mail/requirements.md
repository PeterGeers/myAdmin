# Requirements Document

## Introduction

> Scope: make email sending for the Members module work END TO END, correctly, on the SAM
> plane — for BOTH `to_fixed` (a fixed address list) and `per_recipient` (inline/dataset
> addresses) — with the sender model and plane rules agreed in `analysis.md`. Grounded in
> that analysis (every decision there is the basis here). Tenant-generic (no tenant literals);
> h-dcn is only the first tenant used to verify.

## Context (from analysis.md — the agreed facts)
- Members is a SAM module → mail logic/data stays on the **SAM plane** (steering 35 rule 5a).
  The current interactive send going via the **Flask** `/api/members/mail-set` route is a plane
  violation and is the cause of the wrong (`jabaki.nl`) sender.
- SES verification is **account+region scoped**, address-OR-domain (§5c). "SES-verified" ≠
  "allowed to send" — the allowed-to-send authz is OUR app logic.
- **Sender model (decided, §5e/B):** From = the tenant's own-domain generic address when its
  domain is SES-verified (e.g. `noreply@<tenant-domain>`), else a platform-branded fallback;
  **Reply-To = the logged-in user**. Generic by `tenant_id`.

## Glossary
- **per_recipient** — mail each member in the result individually (mail-merge), to the address
  resolved from each member's row.
- **to_fixed** — send the result as ONE message (optionally with a CSV attachment) to an explicit,
  user-entered fixed recipient list (e.g. a handling agent).
- **From / Reply-To** — envelope sender (a verified identity) / where replies go (the user).
- **active tenant** — the per-request tenant resolved at the SAM edge from the verified JWT + X-Tenant.

---

## Requirements

### Requirement 1: Members mail sends on the SAM plane (not Flask)
**User Story:** As the platform, I want all Members mail to send through the SAM plane, so the
module honors the plane boundary (steering 35 rule 5a) and uses correct per-tenant sending.

#### Acceptance criteria
1. WHEN a user triggers any Members mail send, THEN the request SHALL be handled by the SAM
   Members plane (API Gateway → Lambda → SQS → worker → SES), NOT the Flask backend.
2. The Members use of the Flask `POST /api/members/mail-set` route SHALL be retired (no Members
   feature sends via the Flask backend).
3. WHEN a send is accepted, THEN the SAM worker Lambda (`members-mail-worker-test` / prod
   equivalent) SHALL be the component that calls SES (verifiable via its invocation/logs).
4. Tenancy SHALL be enforced at the SAM edge/repository (`tenant_id` + LeadingKeys); a send SHALL
   only ever use the active tenant's data and sender.

### Requirement 2: `per_recipient` send (inline/dataset addresses) works end to end
**User Story:** As a member officer, I want to mail each member in a pivot result individually,
so every member receives their own (optionally templated/merged) message.

#### Acceptance criteria
1. WHEN I send a pivot result in `per_recipient` mode, THEN one message SHALL be sent per member
   to the email resolved from that member's row (the configured email field, R4.12 — never
   hardcoded).
2. A member row with no resolvable email SHALL be skipped and reported in the outcome (not fail
   the whole batch).
3. WHEN a stored template is selected, THEN each message SHALL be mail-merged per recipient on the
   SAM plane (no member PII leaves to any AI prompt).
4. The send SHALL respect SES limits (rate, daily quota, recipients/msg, size) and dedupe on
   redelivery (stable job id).
5. WHEN the send is accepted, THEN the UI SHALL reflect an accepted/queued outcome; a per-recipient
   failure SHALL surface via the send outcome / audit, not be silently dropped.
6. WHO SENDS (decided): each per-recipient mail of an interactive list SHALL be sent by a SAM
   BACKGROUND BATCH (the SQS → worker Lambda pipeline), rate-paced — NOT by the frontend and NOT
   with the user waiting. The frontend/edge only (a) runs the synchronous pre-send check, (b)
   enqueues, and (c) returns an immediate "queued, N recipients" acknowledgment. Rationale: the
   frontend has no SES access; a list of 10s–1000s cannot complete within a request/user wait given
   the SES rate limit (~14/sec) and API Gateway/Lambda timeouts (~29s). Per-recipient outcomes
   (sent/bounced/failed) are recorded and surfaced as a retrievable status/notification (R8.6c),
   never as a live wait.

### Requirement 3: `to_fixed` send (fixed address list) works end to end, incl. interactive run
**User Story:** As a member officer, I want to send a pivot result (optionally as a CSV
attachment) to a fixed list of addresses I enter (e.g. a handling agent), and I want to run that
send on demand — not only via a schedule.

#### Acceptance criteria
1. WHEN a saved set has a `to_fixed` delivery (recipients + optional CSV attachment), THEN there
   SHALL be an interactive action in the UI to RUN/deliver it now.
2. WHEN I run it, THEN the React frontend SHALL call the SAM deliver route
   (`POST /members/analytics-sets/{set_id}/deliver`) — the gap today (no frontend caller) is closed.
3. WHEN delivered, THEN ONE message SHALL be sent to the fixed recipient list with the CSV
   attachment built from the result rows.
4. WHEN the delivery is invalid (e.g. empty recipients), THEN the user SHALL get a clear error, not
   a silent no-op.
5. The run SHALL return a clear accepted/queued result to the UI, and the actual send + any failure
   SHALL be observable (worker logs / audit / DLQ).

### Requirement 4: Per-tenant verified sender (From) + user Reply-To (decided model B)
**User Story:** As a recipient/member, I want club mail to come from the club's own address with
replies going to the real sender, so it is trustworthy and not spoofed.

#### Acceptance criteria
1. WHEN the active tenant's email domain is SES-verified, THEN the envelope **From** SHALL be
   `noreply@<tenant-domain>` (DECIDED: fixed generic local-part `noreply@`, NOT tenant-configurable).
2. WHEN the active tenant's domain is NOT SES-certified, THEN the system SHALL NOT send and SHALL
   show the clear "your tenant's mail is not certified — contact your administrator" error
   (R5/R8). There is NO alternate-sender fallback: the ONLY sender is `noreply@<tenant-domain>`.
   NEVER send from a foreign/unrelated domain (no `jabaki.nl`-style leak), and NO platform-branded
   substitute sender.
3. The **Reply-To** SHALL be the logged-in user's email (from the verified JWT).
4. The From SHALL be resolved GENERICALLY by `tenant_id` (no tenant-name literals / per-tenant code).
5. From resolution SHALL happen on the SAM send path (edge/worker), not Flask.

### Requirement 5: "Allowed to send" verification + graceful degradation
**User Story:** As a user, I want to know up front whether a send will work, so I'm not surprised
by a silent failure.

#### Acceptance criteria
1. The system SHALL determine whether the resolved From is a usable SES identity using the
   address-OR-domain check (§5c): the address itself verified, OR its domain verified+sending-enabled.
2. WHEN the tenant's `noreply@<tenant-domain>` is not an SES-certified identity, THEN the mail
   action SHALL be unavailable/blocked with a clear bilingual reason (no send) — NOT a failed/opaque
   send, and NOT a substitute sender.
3. "SES-verified" SHALL be treated as a PHYSICAL-send gate only; the app SHALL still enforce its own
   authorization (capability + the active tenant) for who may send — SES does not do that.
4. The account-level prerequisites (`SendingEnabled`, production access) SHALL be assumed/verified
   as an operational precondition (not a per-send check).
5. The certification check SHALL happen at send time (pre-send) per §5c. HOW the "is it certified"
   truth is obtained — a live SES check (`GetEmailIdentity`) vs an onboarding-recorded + projected
   verified flag — is a design/implementation detail (design.md); it does NOT change this
   requirement or the decided not-certified error behaviour.

### Requirement 6: Observability, audit, and failure handling
**User Story:** As an operator, I want every send to be auditable and failures to be visible, so
member mail is trustworthy and debuggable.

#### Acceptance criteria
1. Each send SHALL write a metadata-only audit record (no member PII beyond what's required), on the
   SAM plane.
2. A permanent send failure SHALL dead-letter (DLQ) and be observable; a retryable (throttle) failure
   SHALL retry per the SES-limit policy.
3. The worker SHALL be idempotent on SQS redelivery (stable job id / dedupe marker).

### Requirement 7: End-to-end verification on the TEST stack
**User Story:** As the team, I want both modes verified live on TEST before prod, so we trust it.

#### Acceptance criteria
1. A `per_recipient` send SHALL be verified live on the TEST SAM stack: worker invoked, mail
   delivered, From = `noreply@<tenant-domain>` (the certified tenant domain), Reply-To = the user,
   audit written.
2. A `to_fixed` interactive send (with CSV) SHALL be verified live likewise.
3. The mail SHALL NOT arrive from a foreign sender (regression guard for the `jabaki.nl` bug).

### Requirement 8: Detect and surface WHY a send did not happen

**User Story:** As a sender, I want a clear reason when an email is not sent (e.g. sender not
verified, rate limited, rejected), so I am never left with a silent failure.

#### Acceptance criteria
1. PRE-SEND: WHEN the resolved From / its domain is not an SES-verified identity (or account
   sending is disabled), THEN the system SHALL block the send and surface a clear bilingual reason
   (e.g. "sender not verified") BEFORE enqueuing — not a silent attempt. (§5c check.)
2. AT SEND: WHEN SES rejects the send, THEN the worker SHALL capture the SES error code+message
   (e.g. `MessageRejected` / `MailFromDomainNotVerified` for an unverified identity, throttle, size,
   quota) as the failure REASON. (Already captured in `SesSendOutcome.error`; classified by
   `_enforce_outcome` → retryable vs permanent.)
3. The captured reason SHALL be SURFACED, not only logged/dead-lettered: a user-triggered send that
   fails SHALL report the reason back to the user (or make it retrievable), and the audit record
   SHALL include the failure reason. (The gap today: the worker knows the reason but it only lands
   in the DLQ/logs.)
4. POST-SEND (bounces/complaints): WHEN SES accepts a message but it later bounces or is marked as
   a complaint, THEN that outcome SHALL be detectable via an SES configuration set + notification
   sink (bounce/complaint/delivery events) and recorded against the send. (Covers the "sent OK but
   never arrived" case.)
5. A failure reason SHALL NEVER be masked by a silent fallback to a foreign sender (ties to R4.2 —
   no `jabaki.nl`-style leak).
6. ACTIONABLE + SYNCHRONOUS-ENOUGH: the failure reason SHALL reach the user while they can still
   ACT on it, and SHALL carry a suggested action — not just "it failed". Specifically:
   a. The PRE-SEND verification failures (unverified sender/domain, sending disabled) SHALL be
      returned SYNCHRONOUSLY to the triggering user (before/at enqueue), with an action
      (e.g. "verify/certify the tenant mail domain" / "contact your administrator").
   b. For an INTERACTIVE send, a SEND-TIME SES rejection SHALL be returned to the user with the
      reason + an action (implies the interactive path is synchronous, or the UI can retrieve the
      per-send result — a fire-and-forget 202 that hides the reason is NOT sufficient for the
      interactive case).
   c. For ASYNC (bulk/scheduled) sends where the user is not present, the failure reason SHALL be
      recorded and surfaced as a retrievable notification/status the user can act on later (retry,
      fix recipient, verify sender).
7. DESIGN IMPLICATION (for design.md, not decided here): the fire-and-forget async model cannot give
   immediate actionable feedback. The design SHALL resolve this — e.g. a synchronous pre-send check
   for verification/auth reasons (catches the common case up front), and either a synchronous
   interactive send or a per-send result the UI can poll; the queue is retained for large
   `per_recipient` fan-outs / scheduled runs (rate-pacing), whose failures surface as notifications.

### Requirement 9: User & tenant-admin visibility of async send status

**User Story:** As the sending user (and as a tenant admin), I want to see what happened to a
background send — queued, sent, failed — so the async model is trustworthy, not a black box.

#### Acceptance criteria
1. CORE (in scope): each triggered send SHALL create a SEND-RUN record (run_id, tenant_id, who
   triggered, mode, recipient count, created_at) that the worker UPDATES as it processes, built on
   the metadata-only audit the worker already writes (R6.1). Statuses: `queued` → `sent` / `failed`
   per recipient, aggregated per run.
2. The system SHALL provide a SEND-STATUS / HISTORY view showing each run and its outcome (e.g.
   "Newsletter — 198 sent, 2 failed", with per-recipient detail on drill-down).
3. SCOPING: the SENDING USER SHALL see the status of their OWN sends; a TENANT ADMIN SHALL see ALL
   the tenant's sends (oversight). Same data, role-scoped; tenant-scoped by `tenant_id`.
4. HONESTY OF STATUS: "sent" SHALL mean "SES accepted" (MessageId), which is NOT the same as
   "delivered to the inbox". The core view SHALL NOT claim "delivered" based on SES acceptance alone.
5. LAYERED (ties to R8.4, higher effort): true per-recipient `delivered` / `bounced` / `complaint`
   status SHALL require the SES configuration-set → notification (SNS) pipeline recording events
   against each recipient. This is a SEPARATE layer from the core sent/failed view; the core view is
   deliverable without it.
   - PLANE (decided, rule 5a): SES feedback for MEMBERS mail SHALL be loaded into **SAM** — recorded
     against the Members send-run records in the **Members' own DynamoDB table**, NOT into Flask/MySQL.
     (Members is a SAM module; its data stays on the SAM plane. ZZP/Flask invoice mail keeping its
     feedback in Flask is correct FOR ZZP but is NOT the model Members reuses — same PATTERN, own
     PLANE.) NOTE: SES publishes bounce/complaint/delivery events to ONE account-level SNS sink per
     configuration set (SES has no module concept), so the ingestion handler SHALL route each event
     to the Members store by matching it back (e.g. via `run_id` / message tag).
6. MECHANISM (clarified): status is **DynamoDB RECORDS shown on a SCREEN (pull)**, NOT emails:
   - The send-run + per-recipient outcome records live in the **Members module's own DynamoDB
     table** (`tenant_id` tenancy, SAM plane rule 5a) — written at enqueue, updated by the worker
     (reusing the audit it already writes).
   - The React frontend READS them via a SAM read route (e.g. `GET /members/mail-runs[/{id}]`) and
     renders the status/history SCREEN. Pull model: the user/admin opens it when they want to check.
   - Email-to-admin notifications are NOT the core mechanism — an OPTIONAL future push layer
     ("your send failed") on top of these records, out of core scope.

---

## Out of scope (tracked, NOT in this spec)
- **PDF-labels attachment on a scheduled/no-browser send** — deferred (bugs-to-solve #4; interactive
  labels already work frontend-side).
- **Full sender-identity management UI / onboarding domain-verification workflow** — the "Sender
  Addresses" feature (bugs-to-solve #10) and the tenant domain-verification onboarding flow (Flask)
  are a SEPARATE effort. THIS spec consumes the result (is the From a verified identity?) via the
  §5c check + the platform fallback; it does not build the management/onboarding UI.
- **The members-config data-model redesign** (bugs-to-solve #6/#7/#8/#11/#12, Track 3) — separate.
- **AI-improve / template authoring** changes — unchanged; reused as-is.

## Decided (closed)
- **Mail-domain source:** an explicit TENANT PARAMETER (`members.*`, in the SAME `config#mail` row
  as `mail_enabled`), ENTERED AT ONBOARDING, projected to SAM on the existing `config#*` rails. NOT
  derived from other tenant info. (§5f + onboarding decision.)
- **Not-certified behaviour:** clear actionable error to the sending user ("your tenant's mail is
  not certified — contact your administrator"); never silent, never a foreign-sender fallback.
- **Certification:** a DOCUMENTED onboarding process (user manual, linked to Tenant Info); no
  self-service certification UI in scope (deferred nice-to-have).
- **Sender:** `noreply@<tenant-domain>` when certified, platform-branded fallback otherwise;
  Reply-To = the logged-in user.

## Open design questions (for design.md — genuinely undecided; IMPLEMENTATION-level only)
- **(RECOMMENDED DIRECTION — for design.md confirmation)** route shape + sync/async:
  - **`to_fixed` run-now REUSES `/deliver`** (it is literally "run this saved set's stored
    delivery"). **`per_recipient` interactive uses a DEDICATED send route** (ad-hoc: it sends the
    current result / typed recipients / template, not necessarily a stored delivery block) —
    overloading `/deliver` with an ad-hoc body would muddy a clean route.
  - **Pre-send certification/verification check = ALWAYS SYNCHRONOUS** at the edge, both modes,
    before any enqueue — this catches the main actionable failure (not certified) immediately,
    satisfying most of R8's actionable-feedback need regardless of mode.
  - **`per_recipient` bulk = ASYNC** (SQS → worker, rate-paced); per-recipient failures surface via
    audit/notification (R8.6c) — acceptable since the common failure was caught synchronously up front.
  - **ONE WORKER (DECIDED): both `per_recipient` AND `to_fixed` go through the SINGLE existing
    SQS → worker pipeline (async).** NOT a second synchronous worker/path for `to_fixed`.
    Rationale: one worker already handles both modes (job envelope carries the mode); one code path
    keeps SES send / retry / DLQ / audit / dedupe / sender-resolution in ONE place (avoids the
    Flask-vs-SAM-style duplication that caused the original mess). `to_fixed` is one message, so the
    queue handles it fine. The user still gets actionable feedback from the SYNCHRONOUS pre-send
    certification check (both modes); the only thing given up is a LIVE SES result for `to_fixed`,
    which is minor (the actionable failure — not certified — was already caught up front) and NOT a
    stated requirement. (Supersedes the earlier "lean synchronous for `to_fixed`" — two paths' cost
    outweighs the minor live-feedback gain.) Revisit ONLY if a hard "live delivery confirmation for
    `to_fixed`" requirement emerges.
