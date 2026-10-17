# Implementation Plan — Member Application Form (public applicant intake)

- Status: **Ready for Implementation** (Phase 0 design spikes complete, D19–D27; build gated on
  user approval per the S5 roadmap).

## Overview

- Follows `requirements.md` (R1–R14, D1–D27) and `design.md` (§11a insertion points).
- Plane split: Phases 1–7 are **SAM** (`sam/members/`, tests `sam/tests/` via `sam/pytest.ini`);
  Phase 8 is **Flask** (`backend/src/`, tests `backend/tests/`); Phase 9 is **frontend**;
  Phase 10 is governance + **CI/CD** + deploy. Tests are paired INTO each phase (change-with-tests,
  steering 34/30) — not deferred to the end.
- **CI/CD is explicit (steering 43):** Phase 10 names the quality gates, the branch→env deploy
  path, the new workflow/`samconfig.toml`/IAM-OIDC wiring, and the `test`→`main` promotion — CI/CD
  is part of the work, not an afterthought.
- Each task cites the requirement(s)/decision(s) it satisfies and the design seam it builds on.
- Tasks are chunked < 1 day; each phase carries a rough estimate (steering 40 / specs-reference).
- Checkbox vocabulary (specs-reference): `[ ]` = not started · `[x]` = done · `❌` = blocked/failed.
- All Phase 0 design spikes are resolved (D19–D27); the remaining phases are the build.
- **Governance definition-of-done (steering 40 / 00-index):** a phase that changes steering or an
  ADR is NOT done until that steering/ADR is updated in the SAME change — this applies to Phase 10
  (steering 35 + the new public-intake ADR) and is a hard gate, not a doc chore.

---

## Tasks

### Phase 0 — Design spikes (resolve the remaining Open Questions before building) — ~1 day · DONE

These are the requirements' Open Questions #1–#10; none blocks the architecture, each unblocks a
later task. Output is a short decision note appended to `design.md`.

- [x] 0.1 **RESOLVED — reuse the existing landing-page slug mechanism (D19).** The public tenant
  carrier is the SAME slug the landing pages already use: `<slug>.jabaki.nl` (host-based, slug ==
  tenant slug) + the custom-domain→slug CloudFront KeyValueStore `myadmin-domain-slug-mapping`
  (`infrastructure/landing-pages.tf`). No new `tenant-directory` store. Remaining sub-question for
  1.2: how the API-edge Lambda reads slug→`tenant_id` — reuse the landing mapping vs re-project onto
  the SAM plane (recommend: a thin SAM-plane projection of slug→tenant_id to keep the boundary clean,
  seeded from the same source). → unblocks 1.2.
- [x] 0.2 **RESOLVED — four sibling keys per field spec (D20).** The application attributes ride as
  four sibling keys on each field entry in `config#fields` — `application_visible` (bool, default
  false), `application_required` (bool, default false), `application_choices` (list|null, null=full
  set), `format` ({checker,params}|null) — on BOTH overlay fields and fixed-field overrides,
  mirroring the existing `options`/`choices`/`scope`/`functional_group` carries. No new row type.
  SAM read (3.3) and Flask author (8.1) agree on this shape. → unblocks 3.x + 8.x.
- [x] 0.3 **RESOLVED — membership_type is REQUIRED on the form; first enum option is the default
  (D21).** When a tenant exposes `membership_type` (application-visible, R4.4): it is
  **application-required** (R4b), the applicant picks from the **application subset** (R4a) of
  public-safe types, and the form **pre-selects the first option** as the default so a valid value
  is always present. Server re-validates the submitted value against BOTH the subset (R4a.3) AND the
  live catalog (`_validate_membership_type_reference`, R11) — the default is UI convenience, never
  trusted. When a tenant does NOT expose it: a configured **tenant-default** type is stamped
  server-side so the `status=application` record stays catalog-valid (the fallback half of R11.3).
  This supersedes the earlier "defer to approval" working direction. → unblocks 2.3.
- [x] 0.4 **RESOLVED — reuse the member-analytics/pivot mail-log model (D22).** The
  application-notification send-log uses the SAME `mailrun#<run_id>` status tally (queued→sending→
  completed, `sent`/`failed` counts, `triggered_by`, `recipient_count`, timestamps, 90-day TTL) +
  `mailrecipient#<run_id>#<seq>` **failure-only** sub-records already built for the pivot/analytics
  mail path (`table_design.py`, `RECORD_TYPE_MAIL_RUN` / `RECORD_TYPE_MAIL_RECIPIENT`). The two
  application sends (staff + applicant) are jobs of a run like any other; `triggered_by` is the
  public intake (no interactive user). No new log store. → unblocks 6.4.
- [x] 0.5 **RESOLVED — manual delete by all-scope `Members_CRUD`, NO auto-TTL in v1 (D23).**
  Retention of un-approved `status = application` records is a **manual staff action**: only an
  **all-scope `Members_CRUD`** user (the same all-region set notified per D9) may delete an
  applicant record, reusing the existing authenticated `delete_member` path, scoped. NO DynamoDB
  TTL on applicant records in v1 — this avoids the "auto-delete an approved member" hazard (a TTL
  would require an approval-clears-ttl invariant we are not building now). The GDPR retention
  *period* is operational guidance (docs), not an automated purge. A future enhancement MAY add TTL
  with the approval-clears-ttl invariant. Design sub-item: confirm all-scope `Members_CRUD` is
  authorized to delete an `application`-status record (today member delete is `members:admin`-gated,
  `CAP_MEMBERS_ADMIN`). → unblocks 2.x / 10.
- [x] 0.6 **RESOLVED — Reply-To = the all-scope `Members_CRUD` SET; `TenantAdmin` fallback only
  (D24).** The application email Reply-To is the SAME all-scope `Members_CRUD` recipient set the
  staff notification targets (D9), as a multi-address Reply-To — NO configured Reply-To param, NO
  single-pick tiebreak (both dropped). Fallback to the `TenantAdmin` set only when no all-scope
  `Members_CRUD` exists. Only remaining sub-item: confirm the exact `TenantAdmin` projected role
  segment (OQ7). → unblocks 6.3 (and 8.2 loses the Reply-To param).
- [x] 0.7 **RESOLVED — match on NAME + DOB via a GSI (D25).** The automatic duplicate flag matches
  on normalized **name + date of birth** (NOT email — a stronger "same person" key; both are
  required, R6.1a), looked up via a **GSI** on `(tenant_id, name+dob)` — a cheap indexed read, not
  a public-endpoint partition scan. Still flag-only (`DUP` note in `additional_info`), never blocks,
  neutral 202. Remaining detail: exact key normalization + GSI projection. → unblocks 2.5.
- [x] 0.8 **RESOLVED — tenant-specific, versioned consent notice (D26).** Each tenant authors its
  OWN privacy/consent notice text (bilingual nl/en), NOT a platform-only default. Authored in the
  Flask tenant config (the `members.*` surface) and **projected** like the other per-tenant config
  (e.g. onto `config#mail` or a sibling `config#` row — fixed in design), **versioned** (stable
  version id per revision) so a stored consent references the exact wording accepted. The public
  field-config read serves the current notice text+version to the form; the record stores
  `consent{version, accepted_at(server UTC), locale}` (R12.1a). A later revision never
  retroactively changes an existing record's recorded version. Platform MAY ship a seed/default
  notice for a tenant that has authored none (steering 38 i18n seed rule). → unblocks 2.6 + 8.x.
- [x] 0.9 **RESOLVED — separate public API (D27).** The public endpoints live on their OWN
  `AWS::Serverless::Api` with NO `DefaultAuthorizer` (own stage, own throttle/usage plan, own
  invoke URL), routed to a distinct `handler/public_app.py` entrypoint that never calls
  `_authenticate_and_authorize`. The authenticated members API is untouched — cleanest blast-radius
  isolation for the plane's first unauthenticated surface. OQ7 remainder: `TenantAdmin` confirmed as
  the projected role segment for the member-module tenant admin fallback. → unblocks 1.1 + 7.1.

---

### Phase 1 — Public edge + tenant resolver (R1, R1a, R2; design §1/§2/§3, seam a) — ~2–3 days

- [x] 1.1 New public Lambda entrypoint `handler/public_app.py` on a SEPARATE public API (D27) — parse, abuse guards (honeypot, payload cap, CORS — R10.2/R10.3), delegate; does NOT call `_authenticate_and_authorize`. Reuses `_http._response`/`_error`/`_field_errors_array` (R1a).
- [x] 1.2 `domain/tenant_directory.py` — allow-list slug→`tenant_id` resolver; unknown/forged slug → non-probeable 404 (R2.1–R2.3, R1a.4). (Depends 0.1.)
- [x] 1.3 Wire the two public routes (`GET …/field-config`, `POST …/applications`) onto the separate public API (D27, no `DefaultAuthorizer`) → `public_app`; CORS restricted to the form origin(s) (R10.4). (template.yaml IAM/throttle in 7.1.)
- [x] 1.4 Tests (`sam/tests/`): public route reachable with no token; unknown slug → 404 indistinguishable from no-endpoint; honeypot/oversized/malformed → 400; CORS headers on success + error. (R14.1b, R14.8, R14.12 partial.)

### Phase 2 — `create_application()` + session de-dup + consent + duplicate flag (R3, R3a, R6, R11, R12; seam b) — ~3–4 days

- [x] 2.1 `RECORD_TYPE_APP_SESSION` + `app_session_sk(session_key)` in `table_design.py`; conditional `attribute_not_exists` put + session→member_id mapping read in `members_repository.py` (mirrors `mailsent#`). (R3a.1–R3a.3.)
- [x] 2.2 `create_application(tenant_id, body, session_key, locale, consent)` beside `create_member` — reuses the spine, forces `status=application`, strips privileged fields, accepts only application-selected fields, un-flattens to nested shape (R3, R4.7/R4.8, R3.5). First submit creates, same-session resubmit UPDATES (R3a.2).
- [x] 2.3 `membership_type` on application: implement the 0.3 decision (tenant-default stamp or deferred reference check), keeping `_validate_membership_type_reference` authoritative (R11). (Depends 0.3.)
- [x] 2.4 Required-ness enforcement: all required (platform + application-required) fields server-enforced; email required+valid; IBAN mod-97 when incasso shown; errors collected → 422 `errors[]` (R6, R6.6). (Validator wiring lands in Phase 3.)
- [x] 2.5 Duplicate flag: **name+DOB** match via the GSI on `(tenant_id, name+dob)` (D25) → `DUP` keyword note appended to `overlay.additional_info`; never blocks; response unchanged (R3a.5–R3a.8). Add the GSI to `table_design.py` + `template.yaml`. (Depends 0.7.)
- [x] 2.6 Consent stamp: persist `consent{version, accepted_at(server UTC), locale}` of the TENANT's versioned notice (D26); reject submit without affirmative consent (F4/R12.1–R12.1c). (Depends 0.8.)
- [x] 2.7 Tests: session update-not-insert + concurrent single-record; forced status + sanitize; required-ness (incl. `tussenvoegsel` optional); duplicate flag neutral 202; consent recorded + client timestamp ignored. (R14.1c, R14.13, R14.15, R14.19.)

### Phase 3 — `FieldFormat` attribute + registry + enum subset + application flags (R4a, R4b, R7, D16; seam c) — ~2–3 days

- [x] 3.1 Add `application_visible` / `application_required` / `application_choices` / `format` (`FieldFormat{checker,params}`) to `FixedField`/`OverlayField`/`ResolvedField` in `_field_models.py` (mirror `member_number_format`). (R4.2, R4a, R4b, R7.1.)
- [x] 3.2 `domain/field_formats.py` — the registry `dict[token→checker]` with `EMAIL` (regex, reuse existing pattern) + `IBAN` (mod-97) as first entries; platform-defined token set (R7.6/R7.7).
- [x] 3.3 `projection_config_reader.py` — `_build_format(spec)` (degrade on unknown/malformed, R7.3) + read the three new attrs in `_build_overlay_field`/`_build_override`.
- [x] 3.4 Generic validation step in `_validate_member_record`: for each resolved field with a `format`, if present and `show_when` holds, run `REGISTRY[checker]` and merge `FieldError` (R7.4/R7.5). Wire into 2.4.
- [x] 3.5 Enum application-subset: filter choices to `application_choices` on the public schema + validate submitted value against the subset (R4a.2/R4a.3); fail-loud on a subset entry not in field choices (R4a.4).
- [x] 3.6 Tests: registry EMAIL/IBAN valid+invalid, unknown-token degrade, `show_when` gating; subset exposes/accepts only subset, non-subset rejected; application-required vs optional vs platform-required-cannot-relax. (R14.6, R14.7, R14.15.)

### Phase 4 — Public field-config read + readiness gate (R5, R5.4, D15; seam a/c) — ~1–2 days

- [x] 4.1 `ApplicationService.get_public_field_config(tenant_id)` — resolve field set via `FieldResolver`, filter to application-selected, attach required/subset/format/show_when/label/group/order; **200** schema (R5.1–R5.3).
- [x] 4.2 Readiness gate: read `config#mail`; not `mail_certified` / no `mail_domain` → neutral 409 `code=errors.application.notAvailable` (D15/R5.4). Submit endpoint re-checks (R9.4 defense-in-depth → refuse, no record).
- [x] 4.3 Tests: schema carries application attrs + subset + format; readiness refuses on uncertified tenant (form) AND on direct submit (no record); neutral error (no mail-config leak); passes for send-ready. (R14.16 partial, R14.17.)

### Phase 5 — Applicant locale (R6b, D12) — ~0.5 day

- [x] 5.1 Accept + validate `locale` (`nl`/`en`, default+fallback `nl`); persist on the record; drive applicant-facing copy (R6b.1–R6b.4).
- [x] 5.2 Tests: en/nl render, invalid→nl fallback, locale persisted. (R14.14 partial.)

### Phase 6 — Offloaded notification: recipients, sender, Reply-To, two templates (R8, R8a, R8b, R9, R9a, D5/D8/D9/D9a/D10; seam d/e) — ~3–4 days

- [x] 6.1 `repository/role_recipients_reader.py` — all-scope `Members_CRUD` via `role#…` + `scopegrant#…#<dimension>==["*"]`; scope-matched copy for the applicant's selected scope value (D9a); `TenantAdmin` fallback; empty → signal for `NO_NOTIFY` (R8.2–R8.5, scope-generic). (Depends 0.6.)
- [x] 6.2 `domain/application_notification.py` — enqueue TWO jobs (staff + applicant) via `MailSendQueuePort.enqueue`; `tenant_id` authoritative on the envelope (D5/D10).
- [x] 6.3 Worker branch (`mail_send_worker.py`) — resolve recipients (6.1); compose `From` via `MailSenderResolver` (D4); Reply-To = configured app-Reply-To else first all-scope `Members_CRUD` else `TenantAdmin` (D8/R9a, order from 0.6); render bilingual templates (staff=deep-link + neutral `DUP` marker, no PII, R8.6/R8.6a; applicant=own data, applicant locale, R8a); SES send best-effort + DLQ (R8.8).
- [x] 6.4 `NO_NOTIFY` keyword note on `overlay.additional_info` + platform-operator alert when no recipients (R8.5); send-log per 0.4.
- [x] 6.5 Tests: all-scope filter (scope-limited excluded), scope copy, `TenantAdmin` fallback, no-scope-dim tenant → all; offloaded best-effort (SES fail doesn't roll back record); sender resolution; Reply-To chain; staff deep-link no-PII + DUP marker; applicant copy; `NO_NOTIFY` note. (R14.3, R14.4, R14.9, R14.10, R14.11, R14.14.)

### Phase 7 — Abuse hardening + IAM + inbox channel (R8b, R10, F3; seam a/e) — ~1–2 days

- [x] 7.1 `template.yaml`: public API (no WAF — D17/R10.4), API Gateway throttle + usage plan (R10.1); least-privilege IAM for the public fn (members-table write, projection read, queue enqueue — exact ARNs, no wildcard/cross-account, R10.5); 2nd queue consumer / job kind + its SES + `config#mail` read grants.
- [x] 7.2 Applications-inbox = existing member overview filtered to `status=application` (NO new grid); `DUP`/`NO_NOTIFY` keyword-filterable on `overlay.additional_info` via Table Filter Framework v2 (R8b.4/R8b.5, F3).
- [x] 7.3 Tests: tenant-invariant test covers the public write path (R2.5, Property 1); inbox-as-authoritative-channel — a record whose email send failed is still in the `status=application` filter (R14.5, R14.18).

### Phase 8 — Flask authoring + projection of the application attributes (R4c, D18; seam f) — ~2–3 days · PARALLEL

- [x] 8.1 Extend `_projection_config_builders.py` (`_OVERLAY_FIELD_DEFAULTS`, `_FIXED_OVERRIDE_FIELDS`, `_map_overlay_field`/`_map_fixed_override`) to carry `application_visible`/`application_required`/`application_choices`/`format` onto `config#fields` 1:1 (R4c.1/R4c.2). (Depends 0.2.)
- [x] 8.2 Project the **scope-copy toggle** (D9a) AND the **tenant consent notice** (bilingual text + stable version id, D26) onto `config#mail` / a sibling `config#` row (R4c). (The application-Reply-To param is DROPPED — D24.)
- [x] 8.3 `members_config_validation.py` / `projection_validator.py`: fail-loud at Save — subset ⊆ field choices; `format.checker` platform-known; application-required cannot relax platform-required (R4c.3).
- [x] 8.4 Tests (`backend/tests/`): builder carries the four attrs; validator rejects invalid subset + unknown checker; un-authored tenant projects back-compatible defaults (R14.20). Paired in the same change (steering 30/34).

### Phase 9 — Frontend public form (R4, R5, R6, R6b, R10a; D14) — ~3–4 days

- [x] 9.1 Config-driven renderer: fetch public field-config, render per field via Chakra `FormControl`/`FormLabel`/`FormErrorMessage`, grouped by `functional_group`, labels in applicant locale; flatten↔un-flatten (R4, R10a.4).
- [x] 9.2 Generate the Yup schema FROM the field-config (required/subset/format/show_when); NOT hand-maintained (R10a.2).
- [x] 9.3 Map server 422 `errors[]` into Formik by dotted `field` key (server authoritative); ARIA live-region error summary; locale selector (default nl); consent checkbox (R10a.3/R10a.5, R6b, R12.1).
- [x] 9.4 Handle the readiness-gate 409 ("not available") + 404 as bilingual messages (R5.4/R1a).
- [x] 9.5 Tests (`frontend/`, per `33-frontend-testing`): Yup generated-from-config parity; 422→Formik by dotted key; axe gate over the public form (label assoc, aria-invalid, live-region). (R14.16.)

### Phase 10 — Governance, docs, CI/CD + deploy (R13; steering 35/40/43/00-index) — ~1–2 days

- [x] 10.1 Extend `35-sam-module-architecture-sam.md` with the public/unauthenticated intake edge pattern + controls (R13.1).
- [x] 10.2 New ADR (companion to 0007) for the fenced public-intake exception (R13.2).
- [x] 10.3 Reference the per-tenant verified-sender dependency to the SNS-SES spec (R13.3); end-user docs: applicant form + staff review (R13.4).
- [x] 10.4 **CI/CD wiring (steering 43).** Add the new **public `AWS::Serverless::Api`** (D27) +
  the duplicate-flag GSI + 2nd queue consumer + public-fn IAM to `sam/members/template.yaml` AND
  to `sam/members/samconfig.toml` `[test]`/`[prod]` (new params: public-API stage, throttle/usage
  plan, slug→tenant projection source). Extend `deploy-sam-members.yml` paths if needed so the new
  resources deploy through the EXISTING OIDC pipeline (`NonprofitDeployRole`, no stored secrets).
  Flask (Phase 8) rides the Flask/Railway path, not the SAM deploy.
- [x] 10.5 **Quality gates (steering 43).** Ensure the change passes the per-PR gates (CodeQL +
  GitGuardian) and the nightly **Full Test Suite** (SAM `sam/tests` + Flask `backend/tests` +
  frontend); run the paired tests for changed files per the change-with-tests contract rather than
  a full suite for scoped steps.
- [~] 10.6 **Branch→env deploy (steering 43).** Land on `test` → TEST stack (`test-sam-members`,
  `--config-env test`); verify in live TEST (NOT just units): public form opens for a send-ready
  tenant, refuses for an uncertified one, an application lands as `status=application`, and
  staff/applicant emails fire. Deploy is codified (`sam deploy --config-env <env>` /
  `deploy-sam-members.yml`) — never hand-typed (steering 35/43).
- [~] 10.7 **Promote `test` → `main` (production release, steering 43 runbook).** One PR `test→main`;
  preview the prod changeset (`--no-execute-changeset`, no unexpected `Replacement: True`); CodeQL +
  GitGuardian green; merge with a MERGE COMMIT; watch each triggered deploy settle
  `UPDATE_COMPLETE`. A merge to `main` IS the production deploy.

---

## Task Dependency Graph

Waves are executable in order; tasks within a wave may run in parallel. Phase 0 (0.1–0.9) is
DONE and omitted. Flask (Phase 8) and frontend (Phase 9) run alongside the SAM critical path as
their inputs land; tests are the last task of each phase and follow that phase's implementation.

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "3.1", "3.2", "8.1"] },
    { "id": 1, "tasks": ["1.3", "3.3", "3.5", "8.3"] },
    { "id": 2, "tasks": ["1.4", "2.1", "3.4", "3.6", "8.2", "8.4"] },
    { "id": 3, "tasks": ["2.2", "2.3", "2.5", "2.6", "5.1"] },
    { "id": 4, "tasks": ["2.4", "2.7", "4.1", "5.2", "6.1", "6.2"] },
    { "id": 5, "tasks": ["4.2", "6.3", "6.4"] },
    { "id": 6, "tasks": ["4.3", "6.5", "7.1", "9.1", "9.2"] },
    { "id": 7, "tasks": ["7.2", "7.3", "9.3", "9.4"] },
    { "id": 8, "tasks": ["9.5", "10.1", "10.2", "10.3"] },
    { "id": 9, "tasks": ["10.4", "10.5"] },
    { "id": 10, "tasks": ["10.6"] },
    { "id": 11, "tasks": ["10.7"] }
  ]
}
```

Phase-level sequencing (tasks within a phase run top-to-bottom; `->` = "must precede"):

```
Phase 0 (spikes - DONE)
   0.1 -> 1.2      0.3 -> 2.3      0.6 -> 6.3
   0.2 -> 3.x,8.1  0.4 -> 6.4      0.7 -> 2.5
   0.5 -> 2.x,10   0.8 -> 2.6,8.2  0.9 -> 1.1,7.1

Phase 1 (public edge + slug resolver)
   -> Phase 2 (create_application + session de-dup + consent + dup flag)
        Phase 3 (FieldFormat + flags) -> feeds 2.4 and 4.1
        -> Phase 4 (public field-config read + readiness gate)
             -> Phase 9 (frontend - needs the field-config contract stable)
   Phase 5 (locale) - small, parallel to 2-4
   Phase 6 (offloaded notification) - after 2 (a record exists to notify about)
   Phase 7 (abuse hardening + IAM + inbox) - template/IAM, after 1/6 wiring

Phase 8 (Flask authoring + projection) - PARALLEL once 0.2 lands; integrates with
   the SAM read side (3.3) only through the projected config#fields row shape.

Phase 10 (governance, docs, deploy) - LAST; closes the governance definition-of-done.
```

Critical path to "an application lands + staff/applicant notified": **1 -> 2 -> 4 -> 6**
(with 3 feeding 2.4/4.1). Phases 5, 8 run in parallel; 9 waits on 4; 7 and 10 close out.

## Notes

- **Definition of done:** all of R1-R14 covered by passing tests on both planes (`sam/tests` +
  `backend/tests` + frontend); steering `35` extended + a new ADR added (R13); end-user docs
  written (R13.4); deployed via the codified pipeline (`sam deploy --config-env <env>`, steering
  35/43); the 10 Phase-0 spikes resolved (D19-D27, folded into `design.md`).
- **Change-with-tests:** every task that touches a route/service/builder updates its paired
  test(s) in the SAME change (steering 30/34) - tests are listed as the last task of each phase,
  not a separate test phase.
- **Build gate:** S5 implementation is gated on user approval (roadmap); Phase 0 is complete, the
  build phases are ready to start on go.
- **Remaining design details (non-blocking):** per-decision normalization/shape items in
  `design.md` §12 - the `name+dob` GSI key normalization (D25), the consent-notice projected row +
  stored `consent{}` shape (D26), and the slug->tenant_id read source (D19). None blocks its phase.
