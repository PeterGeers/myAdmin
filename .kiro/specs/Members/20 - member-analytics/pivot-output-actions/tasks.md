# Implementation Plan

Phased task breakdown for `requirements.md` (R0–R6) and `design.md`. Chunks are < 1 day,
grouped in phases with dependencies; each phase states its testing. Check off as done.

## Overview

The feature extends what a user can do with a Member Analytics pivot result: send to
external addresses, use stored (optionally AI-authored) templates, store a reusable
delivery instruction on a saved set, run it on a schedule, and print address labels — all
on the Members (SAM/DynamoDB) plane. Phase 0 is a hard infra prerequisite (production SES
in nonprofit-deploy + tenant-managed senders + the mail-enabled gate). Phases then follow
the requirement order so each builds on the last.

### Steering that applies to ALL tasks

Read these before working; they are not restated per task.

- `41-shell-environment.md` — WSL/bash, UNC-vs-POSIX paths, the `.env`-overrides-
  `AWS_PROFILE` strip for any `nonprofit-deploy` command, the `<<<DONE marker>>>`
  convention, long-running processes via `control_bash_process`, scratch under
  `.agent-output/`.
- `43-cicd-deploys.md` — branch→env (`test`→TEST, `main`→PROD), OIDC `NonprofitDeployRole`
  (no stored secrets), per-env `samconfig.toml`, promote-to-prod runbook, CodeQL/
  GitGuardian green before merge.
- `35-sam-module-architecture-sam.md` — handler→service→repository layering; data on the
  Members plane; rule 5a; rule of three.
- `23-aws-accounts.md` — accounts, `tenant_id` + `LeadingKeys`, `sam-` table naming,
  PAY_PER_REQUEST, SES = nonprofit-deploy.
- `22-authentication.md` — verified-JWT-only; tenant/roles from the token.
- `40-spec-workflow.md` — keep `design.md` updated if the approach changes; track opens in
  this spec; end-user docs are part of done.

Per-phase/per-task steering is called out inline as **[steering: …]**.

## Task Dependency Graph

Waves group tasks that can proceed in parallel; each wave completes before the next
starts. Phase 0 (R0 infra/gate) blocks real-tenant sending in Phases 1, 4, 5.

```json
{
  "waves": [
    { "id": 0, "tasks": ["0.1", "1.1", "1.2", "2.1", "2.2", "2.4"] },
    { "id": 1, "tasks": ["0.2", "0.3", "0.4", "0.5", "2.3", "2.5", "6.1", "6.2", "6.3"] },
    { "id": 2, "tasks": ["1.3", "3.1", "3.2"] },
    { "id": 3, "tasks": ["3.3", "3.4"] },
    { "id": 4, "tasks": ["4.1", "4.2", "4.4"] },
    { "id": 5, "tasks": ["4.3"] },
    { "id": 6, "tasks": ["5.1", "5.2", "5.3", "5.4"] },
    { "id": 7, "tasks": ["7.1", "7.2", "7.3"] }
  ]
}
```

Edges in words:
- **Phase 0 → P1, P4, P5** — real-tenant mail is blocked until SES is production and the
  mail-enabled gate exists (so `1.3` waits on the gate `0.4`).
- **P1 ∥ P2** — independent of each other; may run in parallel.
- **P2 → P3** — the delivery block references a template (`3.x` waits on `2.1`/`2.2`).
- **P3 → P4** — the send engine runs a set's delivery block.
- **P4 → P5** — scheduling reuses the execute-and-deliver path; `4.3` worker waits on the
  queue `4.2`.
- **P1 → P6** — labels wire into the same pivot-result/compose context.
- **all → P7** — docs + promotion close out.

## Tasks

### Phase 0 — R0: production SES + tenant senders + mail-enabled gate (PREREQUISITE)

> INFRA + cross-plane; must land before real-tenant mail (R1–R5).
> **[steering: 23 (SES=nonprofit-deploy, accounts), 43 (OIDC deploy), 41 (strip `.env`
> for nonprofit-deploy CLI), 36 (projected config read)]**

- [x] 0.1 Draft + submit the **SES production-access re-request** for nonprofit-deploy
  (`506221081911`/`eu-west-1`). Prior request was DENIED (case `178525018600435`); the
  wording must honestly cover bulk/clubblad volume + opt-out handling. **[steering: 41 —
  verify identity with the strip first; this is a nonprofit-deploy action]**
- [x] 0.2 Verify/activate the tenant sender path: backend endpoint
  `POST /members/sender-identities` driving SES `VerifyEmailIdentity`/domain verification
  + status read (`GET`). **[steering: 35 handler→service→repo; 22 tenant-admin gate]**
- [x] 0.3 Tenant-admin UI to add + see verification status of a tenant's sender address(es).
  **[steering: 32 modal/i18n]**
- [x] 0.4 Mail-enabled gate: tenant-admin module writes the flag to MySQL `parameters`;
  project it as `config#mail` into `governance_projection`; Members edge reads it via the
  projection reader (no live MySQL at request time). **[steering: 36 Flask-writes/SAM-
  reads, validate-at-seam; 20 projection]**
- [x] 0.5 IAM: grant the Members/worker role the SES actions, scoped; add SES config
  (sender, configuration set) per env. **[steering: 23 exact-scope IAM]**

**Testing (Phase 0):** backend unit tests for the sender-verify service + the gate read
(flag resolves from the projection, not MySQL); confirm identity resolves to `506221081911`
before any live check. **[steering: 34 markers/SAM fixtures, 41 identity strip]**

### Phase 1 — R1: send to an external address (quick win, frontend-only)

> Smallest change; the mail route already accepts plain addresses.

- [x] 1.1 Add an "external recipients" field to `MemberMailCompose`; client-side address
  validation; send as `recipients: ["addr", ...]`. **[steering: 32 modal/i18n/action
  pattern]**
- [x] 1.2 Keep CSV + PDF-label attachments working unchanged; gate PDF labels on a
  resolvable `address_mapping` + `members:export` (existing behaviour).
- [x] 1.3 Only offer sending when the R0 mail-enabled flag is set.

**Testing (Phase 1):** vitest for the compose modal (external field, validation, attach
toggles); update the allocated `MemberMailCompose.test.tsx` in the same change.
**[steering: 33, 32 change-with-tests]**

### Phase 2 — R2: stored templates (on-plane) + AI improve

> Depends on nothing in P1; can run in parallel. **[steering: 35 rule 5a + rule of three
> (module-agnostic seam, do NOT build `sam/shared/templates/` now)]**

- [x] 2.1 New record type `template#<template_id>` (metadata) + S3 body/logo layout under
  `myadmin-shared/<tenant>/templates/...`. **[steering: 23 S3/tenant-prefix]**
- [x] 2.2 Template service (CRUD + render-with-merge-at-send) behind a module-agnostic
  seam; repository put/get/list for `template#`. **[steering: 35 layering + seam]**
- [x] 2.3 Template routes `GET/POST/PUT/DELETE /members/templates[/{id}]`; API response &
  error standard. **[steering: 37 API response standard; 22 gates]**
- [x] 2.4 OpenRouter adapter (Members-owned, behind a seam): `improve(template,
  instruction)`. Free-models-only, **fail-closed** on any model outside the allow-list;
  model is config; prompt carries template+branding only, never member PII. Wire
  `OPENROUTER_API_KEY` to the Members Lambda per env (secret, fail-fast). **[steering: 36
  config-selects, 23 no-dangerous-fallback, 43 no secrets in CI]**
- [x] 2.5 Frontend: template picker (LazySelect) seeds subject/body; template management
  surface (CRUD + upload + "improve with AI"); NL/EN. **[steering: 32 + 37 LazySelect]**

**Testing (Phase 2):** SAM pytest for the template service (merge render, no PII in the AI
prompt), the AI adapter fail-closed on a non-allow-list model, repository round-trip of
`template#`; vitest for the picker + management UI. **[steering: 34 SAM fixtures, 33]**

### Phase 3 — R3: delivery block on the saved set

> Depends on P2 (template ref) for the template-bearing modes. **[steering: 35 additive
> field; see `myBacklog` "generic additive-field serialization helper" — build EXPLICIT
> now, do not generalize]**

- [x] 3.1 Add the optional `delivery` field to `AnalyticsSetEntry`: declare it, write its
  `validate()` rules (mode discriminator; `to_fixed` requires recipients; `per_recipient`
  stores none), add its legacy default in `from_item`.
- [x] 3.2 Thread it through the repository item builder (key stamp + `floats_to_decimal`
  covers numeric `label_options`), the frontend `MemberAnalyticsSet` type, and
  `toBackendConfig`/`fromBackendConfig`.
- [x] 3.3 Routes `PUT/DELETE /members/analytics-sets/{set_id}/delivery`. Gate:
  `members:export` + existing scope (a stored delivery can send only what the user could
  already export — no new permission, no audit-on-save). **[steering: 22, 37]**
- [x] 3.4 Frontend: a delivery editor on the saved set (mode, template, attachment,
  recipients for `to_fixed`, shared `label_options`). **[steering: 32]**

**Testing (Phase 3):** SAM pytest for delivery validation (both modes), `to_item`/
`from_item` round-trip of the new field, a legacy set with no delivery still loads;
tenancy invariant unchanged. **[steering: 34]**

### Phase 4 — R4: queued server-side execute-and-deliver

> Depends on P3 (delivery block). The core send engine; R5 reuses it. **[steering: 35
> handler→service→repository; 23 queue/Lambda IAM exact-scope; 42 local DynamoDB for
> tests, dev-only, via `control_bash_process`]**

- [x] 4.1 execute-and-deliver service (storage-agnostic): resolve set, re-fetch member
  rows via the repository (pins `tenant_id`), run the pivot, build output, enqueue job(s)
  — `per_recipient` = one job per member (merge values + template ref); `to_fixed` = one
  job (fixed recipients + attachment).
- [x] 4.2 SQS queue `members-mail-send[-test]` + DLQ; thin `POST
  /members/analytics-sets/{set_id}/deliver` handler that enqueues and returns accepted.
  **[steering: 23 PAY-as-used/exact-ARN IAM; 35 thin handler]**yes ples
- [x] 4.3 Worker Lambda (SQS event source, bounded concurrency): render (mail-merge /
  attach) → SES send → metadata-only audit (`log_analytics_output`, `ses_mail`); idempotent
  on redelivery (stable job id, dedupe); retry → DLQ after N. Respect ALL SES limits (rate,
  daily quota, recipients/msg, size, sandbox); reuse `_is_ses_rate_limited`. **[steering:
  23 SES=nonprofit; reuse existing throttle handling]**
- [x] 4.4 SAM template.yaml: declare the queue, DLQ, worker, event-source mapping, IAM;
  parameterize per env. **[steering: 43 `samconfig.toml` per env; 35 per-env tables/stacks]**

**Testing (Phase 4):** SAM pytest for the service fan-out (N jobs vs 1), worker idempotency
(no double-send), SES-limit/throttle handling, DLQ-after-N; local DynamoDB for integration.
**[steering: 34, 42 (`control_bash_process`, never foreground)]**

### Phase 5 — R5: scheduled execution

> Depends on P4 (reuses the execute-and-deliver path). **[steering: 35 same-plane; 23
> EventBridge in nonprofit-deploy; 22 role gate]**

- [x] 5.1 New record type `schedule#<schedule_id>` (set_id, cron, created_by, enabled);
  repository CRUD. Only schedulable if the set has a delivery block.
- [x] 5.2 Schedule routes `GET/POST/PUT/DELETE /members/schedules[/{id}]`. Gate:
  `members:admin` OR (`members:write` + the `["*"]` all-regions grant) — a region-narrowed
  CRUD user may NOT schedule (R5). Pin the tenant in the schedule. **[steering: 22 verified
  role + scope grant]**
- [x] 5.3 EventBridge Scheduler → the execute-and-deliver path for the set → enqueues to the
  SAME queue; tenant-wide member scope (guaranteed by the create-time gate).
- [x] 5.4 Frontend: attach/manage a schedule on a set that has a delivery block.
  **[steering: 32]**

**Testing (Phase 5):** SAM pytest for the schedule gate (region-narrowed CRUD rejected),
scheduled run reuses the P4 path and audits as unattended; the schedule requires a delivery
block. **[steering: 34]**

### Phase 6 — R6: address labels as a first-class output action

> Mostly wiring an existing generator; independent of P3–P5 (can follow P1).

- [x] 6.1 Mount the existing `AddressLabelGenerator` options UI as a "Generate address
  labels" action in the `pivot-result-actions` slot (next to CSV / Mail), reusing
  `addressLabelService.generateAddressLabelPdf`. Let the user pick the Avery format +
  per-run options. **[steering: 32 action pattern/i18n]**
- [x] 6.2 Availability gate: resolvable `address_mapping` + `members:export` (hide with the
  existing degradation reason otherwise — config/capability gate, not a tenant gate).
- [x] 6.3 Share ONE `label_options` model between R6 (interactive) and R3's `to_fixed` +
  `pdf_labels` delivery — do not fork two models.

**Testing (Phase 6):** vitest for the action's availability gating + option pass-through;
label-generate audit (`pdf_labels`) metadata-only; update allocated tests same change.
**[steering: 33, 32 change-with-tests]**

### Phase 7 — End-user documentation + promote to production

> **[steering: 40 docs are part of done; 43 promote-to-prod runbook]**

- [x] 7.1 End-user manual sections (`Common/end-user-documentation/`): external send,
  templates (incl. AI-improve), delivery setup, scheduling, tenant-admin sender verification.
- [ ] 7.2 Verify on the TEST stack (`test_sam-members`, deployed — not the local emulator):
  full flow per feature. **[steering: 43 TEST on `test` branch; 42 note: emulator is
  dev-only]**
- [ ] 7.3 Promote `test`→`main` via one PR + merge commit; preview prod changesets (no
  unexpected `Replacement: True` on stateful resources); CodeQL + GitGuardian green.
  **[steering: 43 runbook]**

## Notes

- Build-time items from `design.md` §12 (SES re-request wording, final free-model
  allow-list, worker concurrency vs granted SES rate) are resolved within their phases
  (0.1, 2.4, 4.3).
- The generic serialization helper is explicitly NOT built here — see `myBacklog/backlog.md`.
