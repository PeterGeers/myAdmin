# Mail handling analysis — SAM Members

> Evidence-based analysis of how mail is handled for the SAM Members module today, and
> what is needed to handle ALL mail capabilities fully on the SAM plane. Every claim cites
> the file read. **Facts** are confirmed from code; **inferences** are marked.
>
> Governing rule (steering 35 "SAM module architecture", rule 5a): a SAM module's logic
> and data stay on the **SAM plane** (React frontend → API Gateway → Lambda → DynamoDB →
> SES). It must **NOT** be served via the Flask backend / MySQL. "Reuse CODE across planes
> if useful; never reuse the other plane's STORAGE."

---

## 0. Framing — this is a GENERIC MULTI-TENANT capability (h-dcn is only an example)
Mail for the Members module must be designed as a **tenant-generic** capability, resolved by
`tenant_id` — NOT a per-tenant / h-dcn-specific solution. h-dcn appears below ONLY as the first
tenant used to exercise and verify the feature; it is an INSTANCE, never the design target.
Steering 35/36 forbid tenant literals (`if tenant == "..."`) and tenant-name branches — the
mechanism is one generic path (`tenant_id` + `LeadingKeys` tenancy; config resolved per tenant).

Read every "`@h-dcn.nl`" / "h-dcn" below as **"the ACTIVE tenant's verified sender identity /
the active tenant"**. The requirement is: resolve the sender (and all mail config) GENERICALLY
from the active tenant's configuration + its SES-verified identity — so the SAME code serves
h-dcn, Events, Webshop, and any future tenant with no code change. A solution that only works
for h-dcn (or needs per-tenant code) is explicitly OUT OF SCOPE / an anti-pattern.

---

## 1. The two planes (precise terms)
- **React frontend** — the SPA. Presentation + triggers API calls only. Never sends mail.
- **Flask backend** — Python app in a container (Docker local / Railway prod). Has SES
  access; owns ZZP/invoice/tenant-admin mail (`backend/src/services/ses_email_service.py`,
  `invoice_email_service.py`, `backend/src/routes/members_mail.py`).
- **SAM plane** — API Gateway → Lambda (edge handler → domain service → repository) →
  DynamoDB, with an SQS queue + worker Lambda → SES. This is where Members mail MUST live.

---

## 2. THE HEADLINE FINDING (confirmed) — the interactive Members mail is on the WRONG plane
**The pivot "Mail" button sends via the FLASK backend, not the SAM plane.**
- Frontend calls `POST /api/members/mail-set` (`frontend/.../MemberMailCompose.tsx` →
  `mailMembersSet`).
- That route is DEFINED in the **Flask backend**: `backend/src/routes/members_mail.py`
  (`@members_mail_bp.route("/api/members/mail-set", methods=["POST"])`), delegating to the
  Flask `SESEmailService`.
- **Consequence (confirmed by live test):** the mail that arrived came
  `From: support@jabaki.nl` — the Flask `SESEmailService` / `invoice_email_service`
  fallback sender ("Uses SES default (support@jabaki.nl)"). And the SAM worker Lambda
  (`members-mail-worker-test`) **never ran** (no CloudWatch log group; SQS
  `members-mail-send-test` + DLQ both empty).
- **This is a steering 35 rule-5a plane violation:** a SAM-module feature (Members mail)
  is implemented on the Flask backend. It also explains BOTH observed problems — the wrong
  sender AND why the SAM send pipeline is unexercised.
- *(Inference)* The `per_recipient` interactive send was wired to the pre-existing Flask
  `members_mail.py` route (member-analytics task 9.1) rather than the SAM send path built
  later in pivot-output-actions Phase 4.

---

## 3. What IS implemented on the SAM plane (confirmed, cited)
The SAM send pipeline EXISTS and is well-structured — it is just not reached by the
interactive button.

- **Deliver route (edge):** `sam/members/handler/routes.py` —
  `deliver_analytics_set` (`POST /members/analytics-sets/{set_id}/deliver`, 202 Accepted)
  and `set_analytics_set_delivery` / `clear_analytics_set_delivery`
  (`PUT/DELETE .../delivery`). Dispatched in `sam/members/handler/_dispatch.py`.
- **Execute-and-deliver service:** `sam/members/domain/execute_and_deliver.py` — resolves
  the set, builds send jobs: `per_recipient` → one job per member (merge values + template
  ref); `to_fixed` → one job (fixed recipients + attachment). Enqueues to SQS.
- **Worker Lambda:** `sam/members/worker/app.py` (thin SQS adapter, BatchSize 1,
  partial-batch failures) + `sam/members/worker/mail_send_worker.py` (render → SES send →
  audit; retryable-vs-permanent; dedupe marker). CSV attachment is built; `pdf_labels`
  raises `MailSendPermanent` (not implemented on the worker — deliberate shim).
- **SES sender port:** `sam/members/repository/mail_send_adapters.py` — `SesBotoSender`
  (`send_email` / `send_raw_email`), FROM = `resolve_ses_sender_email()` =
  `require_env("SES_SENDER_EMAIL")`. Fail-fast, **single global sender, NO per-tenant
  resolution.**
- **Templates:** `sam/members/domain/template_service.py` + S3 body store (R2) — on the SAM
  plane, used by the worker for `per_recipient` merge.
- **Schedules (R5):** `schedule#<id>` records + `GET/POST/PUT/DELETE /members/schedules`;
  EventBridge Scheduler → the execute-and-deliver path (tasks 5.1–5.4, marked done).
- **Mail-enabled gate (R0):** `config#mail` projection read by the edge
  (`projection_config_reader.is_mail_enabled`); set true for h-dcn (verified).

---

## 4. What is MISSING / broken for full SAM mail capability (gap list, cited)

| # | Capability | SAM status | Evidence / gap |
|---|------------|-----------|----------------|
| G1 | Interactive `per_recipient` send on the SAM plane | **MISSING (on wrong plane)** | Goes via Flask `/api/members/mail-set` (`backend/src/routes/members_mail.py`). Must move to a SAM edge route → SQS → worker. |
| G2 | Interactive `to_fixed` "deliver now" | **MISSING (no trigger)** | Backend `/deliver` route exists, but NO frontend calls it (grep `/deliver` in `frontend/src` = none). tasks.md Phase 4 has no frontend task. |
| G3 | GENERIC per-tenant sender (From = the ACTIVE tenant's verified identity) | **MISSING** | `SesBotoSender` uses a SINGLE global `SES_SENDER_EMAIL` env var — one sender for ALL tenants, no `tenant_id`-based resolution (`mail_send_adapters.py`). Needs a generic per-tenant sender resolver (NO tenant literals). |
| G4 | SES sender identity verification per tenant | **MISSING / broken** | The "Sender Addresses" UI (tenant-admin) is broken (bugs-to-solve #10: `POST /members/sender-identities` → 404; load → HTML/JSON error). No working SAM-plane sender-identity management. |
| G5 | PDF-labels attachment on the SAM worker | **MISSING (shim)** | `mail_send_worker._build_pdf_labels` raises `MailSendPermanent`. (Scope-decided: interactive-only; see bugs-to-solve #4.) |
| G6 | Scheduled delivery actually exercised | **UNVERIFIED** | Code exists (R5) but never run end-to-end (worker never invoked). |
| G7 | Audit of sends (metadata-only) | Implemented on SAM worker | `mail_audit.py` (`ses_mail` record). Not yet verified live. |

---

## 5. What is NEEDED to handle ALL mail capabilities in SAM Members (requirements, not yet designed)
*(This is the gap-closing scope — to be turned into requirements/design, not implemented yet.)*
1. **Move the interactive mail send onto the SAM plane** (G1): a SAM edge route (e.g.
   `POST /members/analytics-sets/{id}/deliver` for the interactive case, or a dedicated
   send route) that enqueues to the existing SQS → worker → SES path. Retire the Members
   use of the Flask `/api/members/mail-set` route (plane violation). React frontend calls
   the SAM edge, not Flask.
2. **Wire the `to_fixed` "deliver now" trigger** (G2): a React action → the SAM `/deliver`
   route. (Interactive, synchronous-feeling via 202 + status, or a result toast.)
3. **GENERIC per-tenant sender resolution on the SAM plane** (G3): resolve FROM from the
   ACTIVE tenant's configuration + its SES-verified identity, keyed by `tenant_id` — ONE
   generic resolver, no tenant literals, serving every tenant. Replaces the single global
   `SES_SENDER_EMAIL`. Decide the generic source of truth for a tenant's sender (projection /
   per-tenant config), honoring "SES is the identity authority".
4. **Working SAM-plane sender-identity management** (G4): fix/implement the sender-address
   feature so a tenant's From identity is configured + SES-verified (ties to bugs #10).
5. **(Deferred)** PDF-labels on a scheduled/no-browser send (G5) — interactive-only decided.
6. **Verify end-to-end on the SAM plane** (G6/G7): worker runs, SES sends from the correct
   identity, audit records written, DLQ behavior on failure.

---

## 5b. PROPOSED SENDER MODEL (user, 2026-10-09) — sender = the logged-in user's own email
A cleaner, inherently multi-tenant model than a per-tenant domain identity:
- **FROM = the logged-in user's own email address**, taken from their verified credentials
  (the JWT the SAM edge already decodes via `get_verified_claims`). Mail goes out AS the person
  who sends it. No per-tenant sender config, no tenant literals — fully generic by construction.
- **Allowed-to-send check belongs to ONBOARDING** of the user-role-tenant — a **Flask backend**
  function (user/role/tenant management lives on the Flask/MySQL plane). The SAM send path just
  uses the verified user email as FROM; the right to send is established earlier, at onboarding.

### CORRECTION (user, confirmed): SES verification is ACCOUNT+REGION scoped — NOT app/tenant scoped
SES has **no concept of app or tenant.** Verified identities, production/sandbox status, and the
send quota are all scoped to the **AWS account + region** (here `nonprofit-deploy` /
`506221081911`, `eu-west-1`). Consequences for the design:
- The verified-identity list is **shared** across everything in that account — the Flask backend
  AND the SAM worker see the SAME identities (`h-dcn.nl` domain, `pjageers@gmail.com`). "Verify
  per app" is not a thing.
- SES is therefore **NOT a per-tenant isolation boundary.** SES only answers *"is this `From` a
  verified identity in the account?"* — it will let ANY caller with SES permission in the account
  send from ANY verified identity. It does NOT answer *"is this tenant/user allowed to send as
  that?"*.
- So there are **TWO distinct layers**, and only one is SES:
  1. **SES-verified (account-level, AWS-enforced):** can this `From` physically be sent at all.
  2. **Allowed-to-send (APP-level authz, WE enforce):** should this logged-in user / tenant be
     permitted to send as this `From`. This is where the user-role-tenant onboarding rule lives
     (Flask) — SES will not do it for us.
- This CORRECTS earlier loose wording ("per-tenant SES verification"): the *verification* is
  account-wide; any *per-tenant / per-user* restriction is OUR application logic, not SES.

### Hard constraint this must satisfy (confirmed from SES, read-only)
SES only sends `From:` a **verified identity** (address OR domain). In `nonprofit-deploy` SES
today the verified identities are the **domain `h-dcn.nl`** and the address `pjageers@gmail.com`.
So:
- `webmaster@h-dcn.nl` can send BECAUSE the `h-dcn.nl` DOMAIN is verified (domain verification
  covers every address at that domain).
- An address whose domain is NOT verified (e.g. `peter@pgeers.nl`) would be REJECTED by SES.

### Open design questions this model raises (for the spec — not decided here)
1. **Address vs domain verification.** Per-domain is far more practical for a club/tenant: verify
   the tenant's email domain ONCE (e.g. `h-dcn.nl`) → every user at that domain can send as
   themselves, no per-user SES step. Per-address verification means an SES confirmation link per
   user (friction). RECOMMEND domain-level, decided in the spec.
2. **Pre-send check (so the user is not surprised).** At send time SES is the ultimate authority,
   but the UI/edge SHOULD pre-check that the user's From is a verified/allowed identity and
   degrade gracefully (clear message) rather than let the send fail opaquely. Where this check
   reads its truth from (SES `GetIdentityVerificationAttributes`, or an onboarding-recorded flag)
   is a design decision.
3. **Plane split (consistent with steering):** IDENTITY/onboarding management = **Flask backend**
   (user-role-tenant); the actual SEND = **SAM plane** using the verified user email as FROM. The
   two planes keep their responsibilities; no rule-5a violation.
4. **Fallback behaviour:** explicitly NO silent fallback to a foreign sender (`jabaki.nl`) — that
   is the current wrong behaviour. If the user's From is not allowed, REFUSE with a clear reason,
   never send as someone else.

### Impact on the earlier gaps
- Supersedes G3's "per-tenant domain identity" framing with "**per-USER sender = the verified
  logged-in user's email**" (still generic; still `tenant_id`-scoped for authz, but the FROM is
  the user). G4 (sender-identity management) becomes: verify the user's/ tenant-domain's SES
  identity at ONBOARDING (Flask), surfaced to the SAM send as an allowed-to-send signal.

---

## 5c. Options to CHECK "is this email approved to send?" via SES (proven live, read-only)
Live results against `nonprofit-deploy` / eu-west-1 (`aws sesv2 get-email-identity`):
| Query | SES result |
|-------|-----------|
| `webmaster@h-dcn.nl` (address) | **NotFoundException** ("does not exist") |
| `h-dcn.nl` (domain) | **DOMAIN, Verified: true** |
| `peter@pgeers.nl` (address) | **NotFoundException** |
| `pjageers@gmail.com` (address) | **EMAIL_ADDRESS, Verified: true** |

**KEY FINDING:** `webmaster@h-dcn.nl` CAN send, yet querying the ADDRESS returns "does not exist"
— it inherits sending rights from the verified DOMAIN `h-dcn.nl`. A naive address-only check would
WRONGLY reject it. The check MUST consider the domain.

Options, ranked:
1. **❌ Address-only** (`GetEmailIdentity <address>`): INSUFFICIENT — NotFound for any address not
   explicitly registered, even when its domain is verified. Only works for registered addresses.
2. **✅ Address OR domain** (correct): `GetEmailIdentity <address>`; if NotFound, derive the domain
   and `GetEmailIdentity <domain>`. Approved iff either exists AND `VerifiedForSendingStatus:true`.
   Correctly: `webmaster@h-dcn.nl` ✅ (domain), `pjageers@gmail.com` ✅ (address), `peter@pgeers.nl` ❌.
3. **✅ Cache the identity set** (`ListEmailIdentities` once): check locally `address ∈ set` OR
   `domain(address) ∈ set`. One list call instead of per-check; same address-OR-domain logic. Good
   for a frequently-run pre-send check.
4. **Account prerequisite** (`GetAccount`): `SendingEnabled` + `ProductionAccessEnabled` must be
   true before any send (confirmed true today). Account-level, not per-address.

**Caveats:** (a) these confirm the From is a VERIFIED IDENTITY, not that delivery will succeed (SES
is still final authority at send: suppression, bounces). (b) SES verification is ACCOUNT-WIDE
(§5b correction) → "SES-approved" ≠ "this user/tenant is ALLOWED to use it"; the allowed-to-send
authz is OUR app logic, layered on top of this SES check.

---

## 5d. How multi-tenant SaaS normally does this (industry pattern — conceptual, not codebase)
The awkwardness is a signal that "sender = the logged-in user's own email" is the NON-standard
model. What large multi-tenant senders (Mailchimp, HubSpot, Salesforce, Stripe, Zendesk, …) do:

- **The app/tenant is the sender, NOT the individual user.** Envelope `From` is a CONTROLLED,
  verified tenant identity (e.g. `members@h-dcn.nl` or a platform fallback). The individual user
  is surfaced as **Reply-To** (and/or named in the body), never as the spoofed `From`.
- **Why NOT send as the user's personal email:** DMARC/SPF/DKIM. Sending "as" `peter@pgeers.nl`
  via SES spoofs pgeers.nl unless its DNS authorizes SES → spam-foldered/rejected. Reputation is
  also kept on domains the platform controls. (This is exactly why SES demands a verified
  identity — anti-spoofing, not an AWS quirk.)
- **Onboarding = ONE-TIME DNS domain verification per tenant.** A tenant that wants its own-domain
  mail adds SES DKIM/SPF records to its domain once; thereafter the platform sends from any
  `@that-domain` address and passes DMARC. Tenants who don't → fall back to a **platform shared
  domain** (`noreply@mail.<platform>.app`), NOT a foreign address. (h-dcn already has `h-dcn.nl`
  verified → it's in the "own-domain" state.)
- **Nobody builds a mail SERVER.** They use a provider (SES/SendGrid/Postmark/Mailgun) + a THIN
  layer: per-tenant from-identity + reply-to (config), domain-verification-status tracking (the
  "is it approved" check — §5c), suppression/bounce handling. Small; config + a status check +
  a send call — not a mail system.

### What this means for OUR design (reshapes §5b)
- **Preferred model:** `From` = the **tenant's configured, verified sending identity**
  (generic, per-`tenant_id` config); **Reply-To** = the logged-in user. One-time domain verify at
  onboarding (Flask); fall back to a PLATFORM-branded verified address, never a foreign one.
- This supersedes §5b's "sender = user's own email" (which carries DMARC/verification friction and
  is not how the industry does it). The user still appears (Reply-To), but is not the envelope From.
- The `jabaki.nl` fallback was the right INSTINCT (fall back to a platform-verified sender) with
  the wrong, un-branded domain — a platform mail domain (e.g. `mail.<platform>`) is the fix.
- "Allowed to send" check = §5c address-OR-domain SES check against the TENANT's from-identity,
  plus our app authz for which tenant may use which identity (SES won't do that part).

---

## 5e. CHOSEN DIRECTION (user, 2026-10-09) — generic verified From + user as Reply-To
Settled, low-effort, fully multi-tenant, no mail-management system:
- **From** = a **generic VERIFIED sending address** (never the user's personal email).
- **Reply-To** = the **logged-in user's email** (the real sender) — replies reach the person.
- SES sends; NO per-user verification; NO custom mail system. Just: verified From + set Reply-To
  + call SES. No tenant-specific code (generic by `tenant_id` config).

**"Generic" has two valid shapes (design pick in requirements):**
- (A) ONE platform-wide sender for all tenants (e.g. `noreply@mail.<platform>.app`). Minimum
  effort; one verified identity; zero per-tenant setup.
- (B) Per-tenant own-domain sender when the tenant's domain is SES-verified (e.g. `noreply@h-dcn.nl`
  for h-dcn), falling back to the platform sender (A) otherwise. Nicer branding ("from the club").
PROVEN: `noreply@h-dcn.nl` needs NO extra SES step — the `h-dcn.nl` DOMAIN is already verified and
covers all its addresses (§5c). A tenant with no verified domain uses the platform fallback until
it verifies its domain (one-time DNS, at onboarding).

**This is the fix for the wrong-sender bug:** replace the `jabaki.nl` fallback with a proper
generic verified sender (platform address, or the tenant's own-domain address), and always set
Reply-To = the sending user. Supersedes §5b (user-as-From) per §5d (industry pattern).

Effort: a config value for From (global, or per-tenant with platform fallback) + set Reply-To from
the verified JWT email. Small — no identity-management build.

### DECISION (user, 2026-10-09): option (B) — PER-TENANT generic sender
From = the TENANT's own-domain generic address when its domain is SES-verified (e.g.
`noreply@h-dcn.nl`), with the platform-branded address as the FALLBACK for tenants whose domain
is not yet verified. Reply-To = the logged-in user. Fully generic by `tenant_id` (no tenant
literals). Design points this introduces, to settle in requirements/design (NOT now):
1. **What exactly is the per-tenant From** — DECIDED (2026-10-09): `noreply@<tenant-domain>` —
   fixed generic local-part `noreply@` (world standard), NOT tenant-configurable. Replies still
   reach the user via Reply-To, so the local-part need not be personal. Platform fallback =
   `noreply@<platform-domain>`.
2. **Where the per-tenant From config + the tenant's mail-domain live** — generic, keyed by
   `tenant_id` (consistent with how other members config is projected to the SAM plane). This is
   also where the SES address-OR-domain verification check (§5c) reads its truth.
3. **Fallback rule** — when the tenant's domain is NOT SES-verified, use the platform-branded
   verified address; NEVER a foreign domain (no `jabaki.nl`-style leak).
4. **Resolution happens on the SAM send path** (edge/worker), per steering 35 — not Flask.

---

## 5f. WHERE the per-tenant mail-domain / From config lives (investigated + decided direction)
**Confirmed from `_projection_config_builders.py`:** the projection builds per-tenant `config#*`
rows — `config#scope`, `config#fields`, `config#views`, `config#mail` — EACH sourced from a
`members.*` tenant PARAMETER (authored via `/api/tenant-admin/parameters`, projected by
ProjectionSync, read by the SAM edge). So "a tenant parameter → projected `config#*` → read on
the SAM plane" is a PROVEN, reused pattern (it is exactly how `mail_enabled` works today).

**Gap found:** there is NO existing tenant mail-domain / sender field — not a `config#*` builder,
not a `members.*` param, not in tenant info. And **tenant info is NOT wholesale projected to SAM**
— only the specific `members.*` params that have a builder are projected (selective, per-row).

**Decision direction (user):** the per-tenant From/mail-domain SHALL be a **tenant parameter**
(Tenant Info / `members.*` namespace), **projected to SAM** on the SAME rails as `mail_enabled` —
a new `members.mail_domain` (or `members.sender`) param + a projected `config#` row (extend
`config#mail` or a sibling `config#sender`), read by the edge/worker. Generic, keyed by `tenant_id`.
No new infrastructure — "add one more projected param", the pattern used 4× already.

**DECISION (user, 2026-10-09): same mechanism as the flag, ONE row.**
- The mail-domain is a `members.*` tenant PARAMETER (e.g. `members.mail_domain`), authored +
  projected EXACTLY like `members.mail_enabled` (NOT via the separate "Tenant Info" function).
- It goes in the SAME projected row as the flag: `config#mail = { mail_enabled, mail_domain }` —
  extend the existing `build_config_mail_row`; no new `config#` row type. One builder, one row,
  one read.

**DECISIONS (user, 2026-10-09):**
- **Domain source = ONBOARDING.** The tenant's mail domain is ENTERED ONCE at onboarding (new data,
  set up with the tenant) — not re-entered per send, not derived.
- **If the tenant mail is NOT SES-certified → clear, actionable error to the sending user:** e.g.
  "Your tenant's mail is not certified — please contact your administrator." Optionally offer an
  action to request/invoke SES certification. NEVER a silent failure, NEVER a foreign-sender
  fallback.

**DECISION (user, 2026-10-09): certification = a DOCUMENTED ONBOARDING PROCESS, not a built feature.**
- The tenant mail-domain setup + SES certification is a **solid, documented onboarding process**,
  written up in the **user manual and linked to Tenant Info**. (It is inherently operator + DNS +
  wait: operator runs SES `CreateEmailIdentity`, the tenant admin adds the returned DKIM/SPF DNS
  records to their domain, SES verifies asynchronously — minutes to ~72h. No in-app code removes
  the DNS/human step.)
- **In scope for THIS mail spec:** the SAM send path only READS "is the domain certified"; if not,
  it shows the decided clear error ("your tenant's mail is not certified — contact your
  administrator"). No self-service certification UI is built now.
- **Self-service "request certification" button = DEFERRED nice-to-have** (easy to START via one
  `CreateEmailIdentity` call, but cannot FINISH in-app — DNS + wait — so low value for a few
  tenants; an operator does it + hands over the DNS records, like the SES production-access step).
- **Doc deliverable:** a Tenant-Info-linked onboarding runbook section covering mail-domain
  certification (what to enter, the DNS records to add, how to confirm verified).

**Implementation detail still for design.md (does NOT change the above):** HOW "is it certified"
is known at send time — a live SES check (`GetEmailIdentity` on the domain) vs an onboarding-recorded
+ projected verified flag. Either way the user-facing behaviour is the decided error above.

**(superseded open question):** add an EXPLICIT `mail_domain` param, OR DERIVE the domain from
existing tenant info (a tenant `contact_email` / website like `portal.h-dcn.nl` was seen in SES
context). And WHERE the §5c "is it verified" truth is read: live SES check in the worker/edge, or a
verified-flag recorded at onboarding and projected alongside the domain.

---

## 6. Single most important conclusion
**The Members mail feature is currently split across planes incorrectly:** the interactive
send runs on the **Flask backend** (plane violation, wrong `jabaki.nl` sender), while the
purpose-built **SAM send pipeline** (deliver route → SQS → worker → SES) is complete but
**unexercised** — and even it lacks **per-tenant sender resolution**. To make Members mail
trustworthy and compliant with steering 35, the send must be consolidated onto the SAM
plane with a GENERIC, `tenant_id`-based per-tenant sender resolution (NO tenant literals;
h-dcn is only the first tenant to verify it). This analysis is the basis for a tenant-generic
mail requirements/design spec; no code changes made.

---

## Appendix — files read for this analysis
- `backend/src/routes/members_mail.py` (Flask `/api/members/mail-set` route) — FACT: interactive send is Flask.
- `frontend/src/components/members/analytics/MemberMailCompose.tsx` + `membersApiService.ts` — FACT: button → `mailMembersSet` → `/api/members/mail-set`; no `/deliver` caller.
- `sam/members/repository/mail_send_adapters.py` — FACT: `SesBotoSender`, single `SES_SENDER_EMAIL`, no per-tenant sender.
- `sam/members/worker/app.py`, `worker/mail_send_worker.py`, `worker/__init__.py` — SAM worker pipeline + `_build_pdf_labels` shim.
- `sam/members/handler/routes.py`, `handler/_dispatch.py` — deliver/delivery routes + dispatch.
- `sam/members/domain/execute_and_deliver.py` — job building (per_recipient / to_fixed) + enqueue.
- `.kiro/steering/35-sam-module-architecture-sam.md` — rule 5a (plane boundary).
- Live evidence (read-only AWS CLI): worker log group absent; SQS `members-mail-send-test` + DLQ empty; `config#mail` for h-dcn = true.
