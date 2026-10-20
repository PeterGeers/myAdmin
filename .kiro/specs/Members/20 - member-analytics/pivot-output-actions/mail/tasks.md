# Implementation Plan: Members mail sending (SAM plane)

## Overview

> **Scope note (read first):** this `mail/` spec is a **SUBTASK of the parent spec**
> `.kiro/specs/Members/pivot-output-actions` getting fully TEST-verified and PRODUCTION-ready. It is
> NOT independently shippable: its promotion to prod rides the PARENT spec's `test → main` promotion
> (steering 43 runbook), together with the parent's other fixes. These tasks get the mail capability
> correct + TEST-verified; final prod promotion is a parent-spec step (Phase 7 there).
>
> **Grounding:** `analysis.md` (findings + decisions), `requirements.md` (R1–R9), `design.md`
> (there/add/change/remove + resolved choices). Members is a SAM module that CONSUMES SAM-plane
> capabilities (steering 35/40); mail stays on the SAM plane (rule 5a).
>
> **Execution discipline (steering 41):** one command at a time; judge success by the in-band
> `<<<DONE marker=$?>>>`, not the tool exit code; AWS CLI against `nonprofit-deploy` uses the
> `.env`-strip + STS account guard; long-running processes go to the background; infra/IaC + AWS CLI
> are operator-run (not local deploys). Deploys happen on GitHub via OIDC (steering 43), never local.

---

## Tasks

> **⚠️ STATUS RE-AUDIT (2026-10-09) — marker meaning corrected.** Several tasks below were
> marked `[x]` on "tests pass / code written", NOT on "a user can send mail and it works". Driving
> the feature by hand in TEST exposed gaps that unit/integration green had hidden. Marker meaning
> from here on:
>
> - `[x]` = VERIFIED working end-to-end in TEST (a real send/behaviour was observed).
> - `[ ] **[CODE-ONLY, UNVERIFIED]**` = code landed + unit tests green, NOT verified end-to-end.
> - `[ ] **[BROKEN]**` = found BROKEN in TEST (inline note says what fails + fix status).
>
> (The checkbox stays `[ ]`/`[x]` for format validity; the honest status is the bold tag after the task number.)
>
> **Corrections found during TEST verification (do NOT fix as new sub-specs — fix here):**
> 1. **[FIXED]** Deploy-role lacked SNS perms → first `test` deploy FAILED creating the feedback
>    topic (5.1/5.2). Fixed out-of-band: inline policy `SNSMembersAccess` on `NonprofitDeployRole`.
> 2. **[FIXED]** SES send IAM scoped only to the domain identity, not the config-set resource →
>    every real send got `AccessDenied` on `ses:SendRawEmail`/`configuration-set`. Fixed in
>    `sam/members/template.yaml` (commit 13411054), deployed to `test-sam-members`.
> 3. **[OPEN]** `per_recipient` send with no template is ACCEPTED (route returns 202 "sent") then
>    silently dead-letters in the worker ("carries no template_id") → mail never arrives, user
>    misled. Needs: a clear "a template is required for a per-recipient send" error (fail-fast),
>    NOT a false "sent". (User decision: per_recipient REQUIRES a template.)
> 4. **[OPEN]** `S3_SHARED_BUCKET` is UNSET (null) on the deployed worker (and likely handler) →
>    stored-template body rendering would fail fast. The template-send path cannot work until this
>    env var is wired in `template.yaml` + samconfig.
> 5. **[OPEN — DESIGN]** One "Mail" button conflates two intents (to_fixed+attachment vs
>    per_recipient merge) via hidden heuristics — confusing. Proposed redesign (user): move
>    "send CSV by email" under the Export-CSV action; make "Mail" mean per_recipient only
>    (requires an email column + a selected template; show a merged first-row PREVIEW, send only
>    after approval). This is a PARENT-spec change, decided deliberately — not another sub-spec.

### Phase 0 — Per-tenant mail config (projection rails)

- [x] 0.1 Add `members.mail_domain`, `members.mail_local_part` (default `noreply`), and
  `members.mail_certified` (bool) to `parameter_schema.py` (members namespace) with validation.
  **[R4, §5f; steering 36]**
- [x] 0.2 Extend `build_config_mail_row` to project `{ mail_enabled, mail_domain, mail_local_part,
  mail_certified }` into the SINGLE `config#mail` row. **[R4; design Data Models]**
- [x] 0.3 Extend the SAM projection reader to expose the new fields (domain / local_part / certified)
  alongside `is_mail_enabled`. **[R4/R5]**
- **Testing (P0):** backend pytest for schema + `build_config_mail_row` shape; SAM pytest for the
  reader; projection round-trip. **[steering 34]**

### Phase 1 — Per-tenant sender resolution + pre-send certification check

- [x] 1.1 Pre-send certification resolver (SAM domain): resolve From =
  `<mail_local_part|noreply>@<mail_domain>`; read `mail_certified` (Option B) + `mail_enabled`; return
  usable-From or a typed not-certified/not-enabled reason. **Docstring MUST note Option A (live
  `GetEmailIdentity`) as the future alternative.** Pure/injectable. **[R4, R5; design]**
- [x] 1.2 Change `SesBotoSender` to accept a per-send `From` + `Reply-To` (drop the single global
  `SES_SENDER_EMAIL` as the source of truth). **[R4; design CHANGE]**
- [x] 1.3 Worker passes the resolved tenant From + user Reply-To into the sender for every send.
  - ⚠️ **[~] send was AccessDenied until the config-set IAM fix (correction #2); to_fixed+attachment now verified (7.7).**
  **[R4]**
- **Testing (P1):** SAM pytest — From resolution (domain/local-part/default); not-certified →
  typed refusal (no enqueue); Reply-To = user; fail-closed on absent flags. **[R5 Properties 2/4]**

### Phase 2 — Interactive send route (ad-hoc per_recipient) + deliver-now wiring

- [x] 2.1 New stateless SAM route `POST /members/mail/send` (ad-hoc): thin handler → authz
  - ⚠️ **[!] per_recipient with no template is accepted + reported 'sent' then dead-lettered — correction #3.**
  (`members:export` + active tenant) → pre-send check → shared send service → enqueue → 202. **[R1,
  R2, R3; design two-routes-one-service]**
- [x] 2.2 Shared send service: build `MailJob`s for the ad-hoc body (recipients/template/attachment)
  - ⚠️ **[!] same template-less per_recipient hole as 2.1 (correction #3); stored-template render also blocked by unset S3_SHARED_BUCKET (correction #4).**
  AND reuse it from the existing `/deliver` path — ONE service, both routes. **[design]**
- [x] 2.3 Frontend: repoint `MemberMailCompose` from the Flask `/api/members/mail-set` to
  `POST /members/mail/send`. **[R1; change-with-tests steering 30/33]**
- [x] 2.4 Frontend: add the interactive "deliver now" action on a saved set with a `to_fixed`
  delivery → calls the EXISTING `POST /members/analytics-sets/{id}/deliver`. **[R3; the missing trigger]**
- **Testing (P2):** vitest — compose POSTs to the SAM route (not Flask); deliver-now calls `/deliver`;
  SAM pytest — both routes delegate to the one service; both fan-out modes enqueue. **[R2/R3]**

### Phase 3 — Send-run status (records + read route + screen)

- [x] 3.1 `MembersRepository`: write/update `mailrun#<run_id>` (tally) at enqueue + from the worker;
  write FAILURE-ONLY `mailrecipient#…` sub-records; set `ttl` (default 90 days). Tenant-pinned. **[R9; design]**
- [x] 3.2 Read route `GET /members/mail-runs[/{id}]` (capability-gated: own sends for a user; all
  tenant sends for Tenant_Admin). **[R9.3]**
- [x] 3.3 Frontend: a mail status/history screen (list of runs + per-run drill-down to failures) + a
  manual-delete action. **[R9; steering 32]**
- **Testing (P3):** SAM pytest — mailrun tally transitions, failure-only sub-records, TTL set,
  tenancy scope (user vs admin); vitest — status screen renders runs + failures. **[R9]**

### Phase 4 — Remove the plane violation

- [x] 4.1 Retire Members' use of the Flask `POST /api/members/mail-set`
  (`backend/src/routes/members_mail.py`): confirm NO other consumer (grep), then remove the Members
  path. **[R1; design REMOVE]**
- [x] 4.2 Remove the `jabaki.nl` substitute-sender fallback for Members (certified → send; not
  certified → clear error, no send, no substitute). **[R4.2]**
- **Testing (P4):** regression — no Members send path reaches Flask; not-certified yields the error,
  never a foreign sender (the `jabaki.nl` regression guard). **[Property 1/6]**

### Phase 5 — SES feedback (layered: delivered/bounced/complaint)

> Higher effort; delivers true per-recipient delivered/bounced status. Can follow P1–P4.

- [ ] 5.1 **[CODE-ONLY, UNVERIFIED]** SES **configuration set** publishing bounce/complaint/delivery events to SNS (infra —
  - ⚠️ **[~] first deploy FAILED on missing SNS deploy-role perm (correction #1); now deploys, event receipt NOT yet verified (7.4).**
  operator via AWS CLI / IaC per steering 41/43). **[R8.4; infra]**
- [ ] 5.2 **[CODE-ONLY, UNVERIFIED]** Ingestion handler (SAM): consume SNS events, route each to the Members store by
  `run_id`/message tag, write/create the FAILURE `mailrecipient#…` sub-record (late bounce creates
  one) + adjust the run tally. **[R8.4/R9.5; design]**
- **Testing (P5):** SAM pytest — a simulated bounce event records against the right run/recipient;
  late bounce for a previously-sent address creates a failure record. **[R8.4]**

### Phase 6 — Documentation

- [x] 6.1 User-manual section (per `Common/end-user-documentation/`): sending to a fixed address vs
  the member list; the mail status screen; and the **mail-domain certification ONBOARDING runbook**
  (what to enter; the SES DKIM/SPF DNS records to add; how to confirm verified; recording the
  `mail_certified` flag) — linked to Tenant Info. **[analysis onboarding decision; steering 40]**

### Phase 7 — Prepare TEST for h-dcn, then verify end-to-end (the point of this subtask)

> Build (P0–P6) must be done first. CI/CD deploys run on GitHub via **OIDC** (steering 43) — NEVER
> local. AWS CLI steps use the `.env`-strip + STS account guard, one command at a time, judged by the
> in-band `<<<DONE marker=$?>>>` (steering 41). Account: `nonprofit-deploy` 506221081911, eu-west-1.
> Verify on the DEPLOYED TEST stack, not the local emulator.

**7A — Prepare TEST**
- [x] 7.1 **Land code on `test` + deploy.** Merge the implemented P0–P4 (+P5 if done) to the `test`
  branch → triggers `Deploy SAM Members` (members Lambda + worker) via OIDC; do NOT deploy locally.
  Confirm green: `gh run list --workflow=deploy-sam-members.yml --branch test` → `success`; stack
  `test-sam-members` settles `UPDATE_COMPLETE`. **[steering 43]**
- [x] 7.2 **SES preconditions (read-only).** `aws sesv2 get-account` → out of sandbox + sending
  enabled; `aws sesv2 get-email-identity --email-identity h-dcn.nl` → `VerifiedForSendingStatus:true`
  (already true — re-confirm). **[R5 §5c]**
- [x] 7.3 **Author + project h-dcn mail config to TEST** (operator; explicit — the version-bump trap
  bit us before). Requires Phase 0 BUILT (schema + `build_config_mail_row` carry the new fields;
  `noreply@<domain>` is composed from `mail_domain`+`mail_local_part`, never projected as a literal).
  - [x] 7.3a Author `members.*` params in TEST MySQL (Docker, APP_ENV=test; idempotent upsert,
    scope=tenant scope_id=h-dcn): `mail_domain=h-dcn.nl`, `mail_certified=true`, `mail_enabled=true`,
    `mail_local_part` only if non-default.
  - [x] 7.3b `UPDATE tenants SET updated_at=CURRENT_TIMESTAMP WHERE administration='h-dcn'` (version
    SUPERSEDES — else the sync skips, `written=0`).
  - [x] 7.3c Run `ProjectionSync` for h-dcn → `test_governance_projection` (`.env`-strip + STS guard;
    re-strip AFTER importing database; confirm account 506221081911). Expect `written>0`.
  - [x] 7.3d Verify: `aws dynamodb get-item` `{tenant_id:h-dcn, sk:config#mail}` →
    `{ mail_enabled:true, mail_domain:"h-dcn.nl", mail_local_part:"noreply", mail_certified:true }`.
  **[R4/R5]**
- [ ] 7.4 **(If P5) Wire the SES configuration set + SNS** for bounce/complaint/delivery in TEST
  (operator via AWS CLI/IaC); confirm the ingestion handler receives events. **[5.1/5.2]**
- [x] 7.5 **Frontend on TEST.** Per steering 43 there is NO hosted TEST frontend — run the local dev
  server (`VITE_APP_ENV=test`, `localhost:3000`) with the P2/P3 changes against the deployed TEST SAM
  backend. No frontend deploy. **[steering 43]**

**7B — Verify end-to-end (as webmaster@h-dcn.nl)**
- [x] 7.6 `per_recipient`: send to the member list → worker invoked, mail delivered,
  **From = `noreply@h-dcn.nl` (NOT jabaki.nl)**, Reply-To = the user, audit + mailrun status written.
  **[R2, R7; regression guard]**
  - ⚠️ **[!] BROKEN for inline/no-template send: accepted then dead-lettered (correction #3). Not yet verified with a selected template.**
- [x] 7.7 `to_fixed` deliver-now: CSV attachment to a fixed address; same checks. **[R3, R7]**
- [ ] 7.8 Not-certified path: an un-certified tenant/user gets the clear error, NO send, no substitute
  sender. **[R4.2/R5]**
- [ ] 7.9 Status screen: user sees own sends; Tenant_Admin sees all tenant sends; failures shown;
  (if P5) a bounce appears. **[R9]**

### Phase 9 — Corrections remediation (found during TEST verification)

> These are the OPEN corrections from the re-audit block, as actionable tasks. They are the
> real fix sites; the original tasks they unblock STAY `[BROKEN]`/unverified until the
> correction lands AND a real end-to-end send is observed in TEST — only then flip the
> original to `[x]`. Order: C5 (design) frames the flow → C4 (plumbing) makes template
> bodies loadable → C3 (rule) is enforced inside the redesigned flow.

- [x] 9.1 **(C5 — DESIGN)** Split the two send intents by button (user decision):
  - "Send CSV by email" moves UNDER the Export-CSV action (two options: Save locally /
    Send CSV by email to fixed address(es)) — the existing `to_fixed`+attachment path.
  - "Mail" means `per_recipient` ONLY: requires an email column in the pivot result AND a
    selected template; renders a MERGED FIRST-ROW PREVIEW; sends to all only after approval.
  Write this up in the PARENT `pivot-output-actions` design (not a new sub-spec).
  **Unblocks/reshapes: 2.1, 2.2, 2.3, 2.4, 7.6, 7.7.**
- [x] 9.2 **(C4 — shared bucket + key namespacing)** Members owns a per-env shared bucket in
  nonprofit-deploy named `myadmin-shared-<env>` (`myadmin-shared-test` / `myadmin-shared`),
  created + owned by the Members SAM stack in `template.yaml`. Wire `S3_SHARED_BUCKET` on the
  worker AND handler (per-env via samconfig); add least-privilege S3 IAM. Change the template
  body key to **tenant-first + free-form logical service path**:
  `<tenant>/<service-path>/.../<id>/<lang>.html` → Members mail =
  `h-dcn/members/mail/templates/<template_id>/<lang>.html` (update
  `table_design.template_body_s3_key`). Tenant prefix is the isolation boundary; IAM scopes
  the module's namespace. Do NOT reuse the h-dcn APP buckets (`h-dcn-*-email-templates` are
  owned by the standalone `h-dcn`/`h-dcn-test` CFN stacks). **Unblocks: 2.2 render; template
  create/get routes.**
- [x] 9.3 **(C3 — per_recipient requires a template)** In the redesigned Mail flow, a
  `per_recipient` send with NO `template_id` FAILS FAST with a clear bilingual error
  ("a template is required for a per-recipient send") → HTTP 422, ZERO jobs enqueued, NO
  mailrun, NO false "sent". Guard in `send_ad_hoc` (domain), surfaced in `MemberMailCompose`
  via `applyApiError`. `to_fixed` unchanged. **Unblocks: 2.1, 2.2, 7.6 silent-send hole.**
- **Verification gate (P9): PASSED 2026-10-09.** Verified live as webmaster@h-dcn.nl: a
  per_recipient send WITH the `TEST - leden merge (4 velden)` template DELIVERED from
  `noreply@h-dcn.nl` with all 4 merge fields; a template-less per_recipient send shows the clear
  "a template is required" error and does NOT send; Export CSV → Email CSV delivers the CSV
  attachment. 2.1/2.2/7.6/9.1/9.2/9.3 flipped to `[x]` accordingly.

### Phase 8 — Production promotion (PARENT-spec step — not done here)

> This subtask does NOT promote to prod on its own. Its prod readiness FEEDS the parent
> `pivot-output-actions` promotion.

- [ ] 8.1 Fold this mail capability into the PARENT spec's `test → main` promotion (steering 43
  runbook: one PR `test → main`; preview the prod changeset; CodeQL + GitGuardian green; merge-commit;
  watch the deploys settle). Prod tenant mail-domain certification is an onboarding step per tenant.
  **[parent spec Phase 7.3; steering 43]**

---

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["0.1", "0.2", "0.3"] },
    { "id": 1, "tasks": ["1.1", "1.2", "1.3"] },
    { "id": 2, "tasks": ["2.1", "2.2", "2.3", "2.4"] },
    { "id": 3, "tasks": ["3.1", "3.2", "3.3"] },
    { "id": 4, "tasks": ["4.1", "4.2"] },
    { "id": 5, "tasks": ["5.1", "5.2"] },
    { "id": 6, "tasks": ["6.1"] },
    { "id": 7, "tasks": ["7.1", "7.2", "7.3", "7.4", "7.5", "7.6", "7.7", "7.8", "7.9"] },
    { "id": 9, "tasks": ["9.1", "9.2", "9.3"] },
    { "id": 8, "tasks": ["8.1"] }
  ]
}
```

**Ordering notes:**
- P0 → P1 (resolver needs the projected fields).
- P1 → P2 (send routes need From resolution + pre-send check).
- P2 → P3 (status records are written by the send/worker path).
- P1–P4 independent of P5 (SES feedback layered on top).
- P7 (TEST verify) depends on P0–P4 (and P5 for the bounce check).
- P8 depends on P7 green AND the parent spec's promotion.

## Notes
- Parent spec: `.kiro/specs/Members/pivot-output-actions` (this is a subtask of its prod readiness).
- `bugs-to-solve.md` #9/#10/#13 are subsumed by this spec.
- SAM-plane capabilities consumed (not redefined): `35-sam-module-architecture-sam.md`.
- CI/CD + branch→env + promotion runbook: `43-cicd-deploys.md`.
