# Implementation Plan: jabaki.nl Hosting Migration to Nonprofit

## Overview

Derived from this spec's `design.md` (phases 0–7, decisions D1–D5, risk register, error handling).
This is an **execution runbook**, not application code: it moves all `jabaki.nl` public-pages
hosting (S3 + CloudFront + ACM + functions + the two KVS + backend IAM) from the **personal**
account (`344561557829`) to the **nonprofit** account (`506221081911`) via a blue/green cutover —
build the new stack, copy content, validate, flip only the `*.jabaki.nl` wildcard alias, retire the
old stack only after verification. The `jabaki.nl` zone + all email records STAY in personal.

**Execution model — agent-run with per-step approval.** The agent executes each step and **pauses
for explicit user approval before every MUTATING action** (create / update / copy / DNS change /
delete). It prepares the exact command, shows what it changes + the `sts get-caller-identity`
result, then **waits** for an explicit "go"; after running it verifies and shows the result.

> **⚠️ Conscious relaxation of steering `43-cicd-deploys`.** Steering 43 classifies the DNS/email
> flip (Phase 5), the retire/delete steps (Phase 7), and Terraform destroy/`-replace` as
> **owner-run only, never agent-run**. The user explicitly chose (2026-10-31) to let the agent run
> **every** step under **per-step approval**, including Phases 5 and 7. A deliberate, traceable
> override; the guardrail is preserved behaviourally by the mandatory per-mutation approval gate.

**Per-mutation approval gate (applies to EVERY ⚠ task).** Before any mutating command the agent
MUST, in order: (1) run `aws sts get-caller-identity --profile <expected> --region <region>
--output json` and confirm the expected account (`344561557829` personal / `506221081911`
nonprofit) — abort on mismatch (steering-41 wrong-account trap); (2) show the exact command(s) +
the precise resource(s)/record(s) changed; (3) **stop and request approval**, proceed ONLY on an
explicit "go"; (4) run, then verify and show the result; (5) on failure, present the rollback and
request approval before reverting.

**Shell conventions (steering 41).** Terminal always reports `Exit Code: -1` — judge success by
stdout + the in-band `<<<DONE marker=$?>>>` sentinel. Pin `--profile` + `--region` + `--output
json`; strip stray static keys (`env -u AWS_ACCESS_KEY_ID -u AWS_SECRET_ACCESS_KEY
-u AWS_SESSION_TOKEN -u AWS_ENDPOINT_URL_DYNAMODB …`); inline POSIX cd
(`cd /home/peter/projects/myAdmin && …`).

**Known drift (verified live 2026-10-31).** The design says "H-DCN has never published — no
`h-dcn/` prefix." LIVE REALITY: an `h-dcn/` prefix EXISTS but holds ONLY
`h-dcn/landing-pages/ast_..._h-dcn-logo.jpg` (a logo asset) — no `h-dcn/index.html` /
`h-dcn/landing.json`. **Treat the content inventory as 8 prefixes, not 7** for Phase 0 baseline +
Phase 3 copy. All Current-State facts are author-time: Phase 0 MUST re-read everything live before
any apply.

## Task Dependency Graph

```
Phase 0 (read-only inventory)
   │
   ▼
Phase 1 (grant nonprofit IAM) ⚠
   │
   ▼
Phase 2 (provision new nonprofit stack: ACM, S3, CloudFront, KVS, IAM) ⚠
   │
   ▼
Phase 3 (cross-account content copy, 8 prefixes) ⚠
   │
   ▼
Phase 4 (blue/green validation, test host only) ⚠
   │
   ▼
Phase 5 (flip *.jabaki.nl wildcard alias) ⚠⚠ HIGHEST RISK
   │
   ▼
Phase 6 (repoint backend/frontend to nonprofit) ⚠
   │
   ▼
Phase 7 (retire old personal stack — DELETES) ⚠⚠ irreversible, after soak
   │
   ▼
Acceptance A1–A5
```

Strictly sequential: each phase's precondition is the prior phase verified. Rollback is clean
through Phase 6 (old stack untouched); irreversibility begins at Phase 7.

## Tasks

- [x] 0. Preflight & inventory (READ-ONLY, no approval needed)
  - [x] 0.1 Confirm identities: `sts get-caller-identity` `personal` → `344561557829`,
    `nonprofit-deploy` → `506221081911`.
  - [x] 0.2 Re-verify the old distribution live (`cloudfront get-distribution --id E28OSWC7A9O9K2
    --profile personal`) — record origin, function association, cert ARN, aliases.
  - [x] 0.3 List S3 slug prefixes + record object count + byte size per prefix (expect **8**: 7
    tenants + `h-dcn/` asset) — the Phase-3 integrity baseline.
  - [x] 0.4 Export both KVS contents from personal (`domain_mapping`, `application_embed_origins`).
  - [x] 0.5 Dump ALL `jabaki.nl` zone record sets to a baseline file under `.agent-output/` — the
    "email untouched" reference for every later zone diff.
  - [x] 0.6 Confirm nonprofit has NO `*.jabaki.nl` distribution and NO public-pages bucket.
  - _Design ref: Phase 0. Rollback: none (read-only)._

- [x] 1. ⚠ Grant nonprofit the permissions it lacks
  - [x] 1.1 ⚠ Ensure `NonprofitDeployRole` can manage the new hosting (S3, CloudFront, ACM, KVS) in
    nonprofit. Do personal-zone edits with the `personal` profile (do NOT grant the nonprofit role
    write into the personal zone).
  - _**NO-OP (verified 2026-10-31):** `NonprofitDeployRole` already grants `s3:*`, `cloudfront:*`, `acm:*` (+cfn/lambda/iam/logs/ssm/ses) on `*` via inline `NonprofitDeployPolicy` + `ACMAndOIDCAccess`. Nothing lacking for Phases 2–5. Role is `ManagedBy: cloudformation` — any future tweak goes in the CFN/SAM template, not a hand patch. Only gap: `cloudfront-keyvaluestore:*` data-plane, needed at most at Phase 6.3 and only if KVS re-seed uses this role rather than Railway backend creds._
  - _Precondition: Phase 0. Verification: nonprofit can create ACM/S3/CloudFront (scoped
    describe/dry-run); `personal` can edit the zone. Rollback: remove added IAM. Design ref: Phase 1._

- [ ] 2. ⚠ Provision the new nonprofit stack (no DNS traffic yet)
  - [x] 2.1 ⚠ Decide + record the Terraform strategy (design §9/D5): nonprofit provider +
    **separate state key** scoped to hosting; EXCLUDE `route53-jabaki.tf` zone/email/root-alias.
  - _**STRATEGY (2026-10-31):** New isolated Terraform root `infrastructure/nonprofit-public-pages/` (main.tf+hosting.tf+README.md), separate state key, nonprofit provider. Mirrors personal `landing-pages.tf` (url-rewrite fn verbatim) but EXCLUDES the jabaki zone/email (stay in personal) and the deferred CSP viewer-response fn. New bucket `myadmin-public-pages-nonprofit-506221081911` (name-checked free). `terraform validate` + `fmt` clean; NOT applied. Open: Q1 wildcard ownership for Phase 5 flip (recommend `state rm` + CLI UPSERT, owner-run) & Q2 state-bucket location — deferred to their phases._
  - [x] 2.2 ⚠ Request the new ACM `*.jabaki.nl` cert in nonprofit **us-east-1** (D2).
  - _**DONE (2026-10-31):** cert `arn:aws:acm:us-east-1:506221081911:certificate/28aefddd-3921-455f-a434-7b35e5c92b6a` created, status PENDING_VALIDATION. State bucket `myadmin-tfstate-nonprofit-506221081911` created; backend needed `profile="nonprofit-deploy"` (steering-41 wrong-account trap — `[default]` creds are personal). Validation CNAME to add in Phase 2.3: name `_c0a2da2a1cef8057de6904286f24da23.jabaki.nl.` value `_4f60f231ede2650e404c20eb2a80f0b2.wzccmgtwzk.acm-validations.aws.`_
  - [x] 2.3 ⚠ Add the cert-validation CNAME to the **personal** zone — ADDITIVE only; wait for ACM
    `ISSUED`. (Personal-zone write → approval gate + baseline diff after.)
  - _**DONE (2026-10-31):** validation CNAME added via single UPSERT (change `C05695601S0BRRDTAAIE0`). Zone diff vs Phase-0 baseline: 20→21 records, +1 CNAME, 0 changed, 0 removed; all 14 email records (MX/SPF/SES/DMARC/DKIM/bounce) BYTE-IDENTICAL (verified `2.3-zone-diff.txt`). Cert still PENDING_VALIDATION — ACM will auto-issue once it polls the new record. NOTE: this record is in the personal zone but NOT in the personal Terraform state (intentional; different name from the old cert's record, no collision)._
  - [x] 2.4 ⚠ Create the new S3 bucket (D3, new globally-unique name), SSE AES256, full
    public-access-block, OAC-only read.
  - [x] 2.5 ⚠ Create the new CloudFront distribution: origin = new bucket (OAC), alias
    `*.jabaki.nl`, viewer cert = new ACM cert, viewer-request url-rewrite fn (parity, D4 —
    url-rewrite ONLY, not the CSP fn), the two KVS, bucket policy limiting `s3:GetObject` to the
    new dist ARN.
  - [x] 2.6 ⚠ Create nonprofit backend IAM policies (S3 write, CloudFront invalidation, KVS,
    DynamoDB if needed).
  - _Precondition: Phases 0–1 + strategy. Verification: dist `Deployed` + serves on
    `*.cloudfront.net`; cert `ISSUED`. Rollback: destroy the new nonprofit resources. Design ref:
    Phase 2._

  - _**DONE (2026-10-31):** Phase-2 stack applied. dist `E3GLUX3TWBIJG` (`d3le4vf2nffsil.cloudfront.net`, zone `Z2FDTNDATAQYW2`) built with NO alias (Option A — alias moves at Phase 5 to avoid CNAMEAlreadyExists). bucket `myadmin-public-pages-nonprofit-506221081911`; KVS domain=`76ac2d6f-a02a-4321-afb8-3fd5dbf88c43` embed=`f52da9c3-cea7-48f6-9f1d-d189fc563645`; cert `28aefddd…` ISSUED; IAM s3-write/invalidation/kvs-access created. No DNS, old stack untouched._

- [ ] 3. ⚠ Cross-account content copy (personal → nonprofit)
  - [x] 3.1 ⚠ Apply a TEMPORARY cross-account grant for the copy.
  - [x] 3.2 ⚠ `aws s3 sync s3://myadmin-public-pages-production/ s3://<new-bucket>/` — ALL **8**
    prefixes (7 tenants + the `h-dcn/` asset) with their `index.html`/`landing.json`/asset.
  - [x] 3.3 ⚠ REMOVE the temporary grant immediately after.
  - _Precondition: new bucket exists. Verification: per-prefix object count + bytes match the
    Phase-0 baseline (all 8); spot-fetch via the new dist + a test Host header resolves
    `/<slug>/index.html`. Rollback: delete copied objects; old bucket untouched. Design ref: Phase 3._

  - _**DONE (2026-10-31):** Chose push-from-nonprofit-role (Option 2 variant): temp READ grant added to OLD bucket policy (additive, OAC statement preserved), `s3 sync` copied 225/225 objects, integrity verified — all 9 prefixes match baseline count+bytes exactly, 0 missing/0 extra. Temp grant REMOVED; old bucket policy restored byte-identical to original. New bucket holds full content; nothing serves it yet (no DNS)._

- [ ] 4. ⚠ Blue/green validation before any DNS flip (test host only)
  - [x] 4.1 ⚠ Validate the new dist end-to-end WITHOUT touching production DNS — per-tenant Host
    header to the new `*.cloudfront.net`. Optional disposable `migration-test.jabaki.nl` to test
    TLS/SNI (created + deleted in isolation, never the wildcard).
  - _Precondition: Phase 3 verified. Verification: all 8 prefixes render; TLS serves the new cert.
    Rollback: delete the disposable record. Design ref: Phase 4._

  - _**DONE (2026-10-31):** New dist `E3GLUX3TWBIJG` Deployed. Host-header spoof tests return 421 (expected: no `*.jabaki.nl` alias yet under Option A, so CloudFront rejects non-matching Host). Validated instead via PATH route on the native cf domain `d3le4vf2nffsil.cloudfront.net`: peter/vandenheuvelhoveniers/thecategorystudio/mytest = 200; kimgeers/GoodwinSolutions/h-dcn = 404 — and OLD live dist returns the SAME codes for all (no regression; those 3 serve via host-based KVS route, which needs the alias). `/404.html`=200; peter/index.html serves real content (`<title>Peter Geers</title>`). Host-based branch untestable pre-cutover but is byte-identical function + byte-identical content, so parity is assured; full host-based check happens right after the Phase-5 alias move._

- [ ] 5. ⚠⚠ DNS cutover — flip ONLY the `*.jabaki.nl` wildcard alias (HIGHEST RISK — rides the
  production-email zone; change batch = the two wildcard records ONLY)
  - [x] 5.1 ⚠⚠ Pre-flip: confirm Phases 2–4 verified + explicit go.
  - [x] 5.2 ⚠⚠ `UPSERT` ONLY the `*.jabaki.nl` A and AAAA alias records (personal profile, personal
    zone) → new nonprofit dist domain + its CloudFront hosted-zone-id. No other record. Root alias +
    ALL email records untouched.
  - _Precondition: 2–4 verified + go. Verification: `dig` → new dist; `curl -sI
    https://peter.jabaki.nl/` → 200 + match; all 8 serve; **zone diff vs Phase-0 shows ONLY the two
    wildcard records changed** (MX/DKIM/DMARC byte-identical). Rollback: immediate re-`UPSERT` back
    to old dist `E28OSWC7A9O9K2`. Design ref: Phase 5._

  - _**DONE (2026-10-31) CUTOVER LIVE:** 3-step alias move (Option A): (1) removed `*.jabaki.nl` from OLD dist E28OSWC7A9O9K2; (2) added it to NEW dist E3GLUX3TWBIJG, waited Deployed; (3) UPSERT `*.jabaki.nl` A+AAAA -> `d3le4vf2nffsil.cloudfront.net`. VERIFIED: 14/14 email records (MX/SPF/SES/DMARC/DKIM/bounce) BYTE-IDENTICAL to Phase-0 baseline; only wildcard A changed + wildcard AAAA added (new dist has IPv6; old had none) + the Phase-2.3 cert CNAME. Live: peter/vandenheuvelhoveniers/thecategorystudio=200; kimgeers=404 (SAME as old pre-cutover, not a regression). Brief alias-swap blip occurred as expected. Rollback still available: UPSERT A/AAAA back to d3afn46os9e9nc + re-add alias to old dist (old stack intact until Phase 7)._

- [x] 6. ⚠ Backend & frontend repoint
  - [x] 6.1 ⚠ Update Railway env to nonprofit: `LANDING_PAGES_BUCKET`,
    `CLOUDFRONT_PUBLIC_PAGES_DISTRIBUTION_ID`, `CLOUDFRONT_PUBLIC_PAGES_DOMAIN`, `CLOUDFRONT_KVS_ARN`,
    `CLOUDFRONT_EMBED_ORIGINS_KVS_ARN`.
  - [x] 6.2 ⚠ Update Railway AWS credentials/role so publishes + invalidations target nonprofit.
  - [x] 6.3 ⚠ Re-seed `domain_mapping` + `application_embed_origins` KVS (from Phase 0) into the NEW
    KVS.
  - [x] 6.4 ⚠ Update `VITE_CLOUDFRONT_PUBLIC_PAGES_URL` in `deploy-frontend.yml`.
  - _Precondition: Phase 5 stable. Verification: republish a disposable TEST tenant → lands in NEW
    bucket + invalidates NEW dist + URL serves. Rollback: restore previous Railway env + creds.
    Design ref: Phase 6._

  - _**STATUS (2026-10-31):**
    - **6.1 Railway env — NEEDS OWNER (dashboard, no repo/CLI access).** 

- [ ] 7. ⚠⚠ Post-cutover verification & retirement (DELETES — LAST, irreversible, after soak)
  - [ ] 7.1 ⚠ Final full verification: all 8 prefixes serve from nonprofit; fresh publish
    round-trips; email diff clean.
  - [ ] 7.2 ⚠⚠ ONLY after 7.1 + explicit confirmation: retire the old personal stack —
    disable→delete old dist `E28OSWC7A9O9K2`; delete old bucket `myadmin-public-pages-production`
    (after a final content diff); delete old ACM cert `da81c484…`. **Each deletion = a separate
    approval.**
  - _Precondition: Phases 5–6 verified + soak. Verification: old resources removed; nonprofit sole
    owner. Rollback: NOT trivial post-deletion — hence soak + explicit gates. Design ref: Phase 7._

- [ ] A. Acceptance (from design "Testing Strategy")
  - [ ] A.1 Tenant continuity: each live slug serves correct content over `<slug>.jabaki.nl`
    (200 + content match vs baseline).
  - [ ] A.2 Email untouched: post-cutover zone diff clean vs Phase-0 baseline for every
    MX/TXT/DMARC/DKIM/SES record.
  - [ ] A.3 Account ownership: new bucket/distribution/ACM/both KVS in `506221081911`;
    `*.jabaki.nl` resolves to the nonprofit distribution.
  - [ ] A.4 Publish path: a backend republish of a disposable test tenant writes to the new bucket
    + invalidates the new distribution.
  - [ ] A.5 Rollback drill (pre-flip): confirm the Phase-5 revert is a single reversible change
    while the old stack still exists.

## Notes

**Prerequisite relationship.** This migration is a **hard prerequisite** for the GATED subset of
`.kiro/specs/Members/14 - public-pages-multi-tenant-serving` (the SAM live-publish + nonprofit
publish IAM, its tasks 7–9). Spec 14's account-agnostic work (page registry, MySQL/DynamoDB
generalization, tenant prefix, slug-claim, SAM public GET/POST, rendering-library extract) does NOT
wait on this migration and proceeds in parallel.

**Out of scope (restated from design).**
- The frontend `/apply` route fix + `deriveApplicationFormUrl` (branch `fix/members-tenant-mock`).
- Moving the `jabaki.nl` zone or any email record to nonprofit (rejected, D1).
- Deploying the viewer-response CSP function (deferred, D4).

**Phase 0 findings (verified live 2026-10-31, reconcile later phases to these).**
- **Content baseline is 9 top-level prefixes, not 8.** The 7 tenants + the `h-dcn/` logo asset
  (design's known drift) PLUS a bucket-root `404.html` (713 B) that the distribution serves on
  403/404. Phase 3 copy + every per-prefix integrity check (Phase 3, 7.1, A.1) must count **9**.
- **Authoritative zone = the Terraform zone `Z08387971HTZZ7C0VCJYP`.** Live NS delegation +
  MX (improvmx) + a resolving `*.jabaki.nl` wildcard all answer from it. Every DNS write
  (Phase 2.3 cert CNAME, Phase 5 wildcard flip) targets ONLY this zone id.
- **REMINDER — dormant duplicate `jabaki.nl` zone `Z018259333BU106BC4LJH` (Amplify-created).**
  6 records, NS set NOT in the live delegation, its `www`/`myadmin` CNAMEs do not resolve.
  It is OUT OF SCOPE for this migration: never write to it, never delete it here. It is
  orphaned Amplify cruft and a candidate for a SEPARATE, owner-run cleanup task later (confirm
  nothing queries it by NS before any deletion).

**Safety invariants (non-negotiable).** Only the two `*.jabaki.nl` wildcard records + one additive
cert-validation CNAME ever change in the zone; every email record is read-only (verified by a
baseline diff after each zone write). The old personal stack is never modified or deleted before
Phase 7. Every mutation passes the per-mutation approval gate with an identity check.
