---
inclusion: auto
---

# AWS Accounts & Infrastructure — Platform Model

> Active-rules summary. Full reasoning:
> `.kiro/specs/multi-tenant/Analysis/second_thoughts.md`, `migration_plan.md`,
> `environments_and_testing.md`. Decision of record: ADR 0003. Current phase/status:
> `00-index.md`.

The platform (myAdmin, evolved in place) spans two AWS accounts plus Railway.

## Account model

- **Identity account (personal, 344561557829):** home of the Cognito pools — the
  tenant-neutral access function for the whole platform. Profile: `personal` —
  Cognito/identity administration only.
  - **Pool A (admins):** the existing Cognito pool **named `myAdmin`** — pool id
    `eu-west-1_Hdp40eWmu`, app client `myAdmin-client` (id
    `66tp0087h9tfbstggonnu5aghp`) — kept in place (not migrated), Plus tier.
    PRODUCTION. ("Pool A" is the audience-role label; `myAdmin` is the pool's name.)
  - **Pool B (end-users):** a NEW Essentials pool — deferred (see `00-index.md`);
    addable config-only via the S2 issuer registry.
  - **Standing test pool `myAdmin-test`** — pool id `eu-west-1_xyrlzfqbl`, app client
    `myAdmin-test-client` (`43s15cm8qcgg8an85udt0e087u`): a permanent Essentials-tier
    pool mirroring Pool A's app-client config, claim shapes, groups, and (like Pool A)
    **no Pre-Token-Generation trigger** — Pool A's `LambdaConfig` is empty, so there is
    nothing to mirror. Seeded with throwaway test users (one per role/claim shape plus
    an empty-groups edge case). All identity work is validated here first; production
    Pool A changes only after gated validation. Permanent (Essentials = 10k MAU free).
    See `environments_and_testing.md`.
    - `iss`: `https://cognito-idp.eu-west-1.amazonaws.com/eu-west-1_xyrlzfqbl`
    - `jwks_uri`: `https://cognito-idp.eu-west-1.amazonaws.com/eu-west-1_xyrlzfqbl/.well-known/jwks.json`
- **Infrastructure & data account (nonprofit, 506221081911):** all generic AWS
  services — DynamoDB, S3, SES, SNS, Secrets Manager, SSM Parameters, CloudFront, API
  Gateway, Lambda. No Cognito pool of record (triggers attach cross-account). Profile:
  `nonprofit-deploy` — all infrastructure operations.
- **Railway (external):** myAdmin Flask backend + MySQL. Stays as-is; the system of
  record for tenant management. Only its AWS resources move to nonprofit (roadmap S6,
  see `migration_plan.md`).

## Cognito pool inventory (current)

- **Active — keep:**
  - `eu-west-1_Hdp40eWmu` (`myAdmin`) — production Pool A.
  - `eu-west-1_xyrlzfqbl` (`myAdmin-test`) — standing test pool.
  - `eu-west-1_fcUkvwjH5` (nonprofit H-DCN) — **MUST be kept while the h-dcn project
    runs.** Do not delete; it is decommissioned only when h-dcn itself is retired.
- **Decommissioned — already deleted:** `eu-west-1_OAT3oPCIm`, `eu-west-1_VtKQHhXGN`
  (removed during S3, with backups then removed per user; Pool A + test pool untouched).

## Guardrails

- Region: `eu-west-1` throughout.
- DynamoDB tables, Cognito pools, and S3 data buckets are managed **outside**
  CloudFormation (or with `DeletionPolicy: Retain`) — a prior deploy deleted prod data
  by not doing this.
- Never `--delete` or `rm --recursive` against a data bucket. Back up before any data
  move. Keep distinct data buckets separate; never cross them.
- Critical env vars must fail fast (throw on missing) — no dangerous fallbacks.
- DynamoDB tables use PAY_PER_REQUEST (on-demand) billing.
- **SAM-module-plane DynamoDB table naming:** module-plane tables carry a `sam-` name
  (e.g. `sam-members`) chosen to NOT collide with the pre-existing single-tenant per-app
  tables/stacks in the same account (notably `Members` / the h-dcn app). **PRODUCTION
  tables are unprefixed (`sam-members`, `governance_projection`); the non-prod environment
  uses a `test_` PREFIX (`test_sam-members`, `test_governance_projection`).** This matches
  `35-sam-module-architecture-sam.md` rule 6 and the deployed `sam/members/samconfig.toml`.
  Names are resolved from a per-module env var (fail-fast), never hardcoded. Legacy per-app
  tables (`Members`, `Events`, `Carts`, `Counters`, `Payments`, `Memberships`, `Orders`,
  `Producten`, `StockMovements`, …) keep their existing names untouched.
  - **Isolation boundary = per-stack exact-ARN IAM + distinct stack names, NOT a name
    wildcard.** Each stack's execution role is scoped to the EXACT table ARN(s) its
    parameters resolve to (`table/${MembersTableName}` → `table/sam-members` for prod,
    `table/test_sam-members` for test — see `sam/members/template.yaml`), so a TEST stack
    can only reach `test_*` tables and a PROD stack only the unprefixed ones. Distinct
    CloudFormation stack names (`sam-members` vs. the h-dcn `h-dcn` stack; the TEST CFN
    stack is `test-sam-members` with a hyphen since CFN forbids underscores, while the
    TABLE stays `test_sam-members`) keep the stacks independent. This exact-ARN scoping is
    STRONGER than a wildcard and is the defense-in-depth layer over `tenant_id`
    `LeadingKeys`.
  - **⚠️ Historical note (do not restore):** an earlier version of this guardrail required
    the environment as a `-test` **suffix** so IAM could match `arn:…:table/sam-*`. That
    `sam-*` WILDCARD policy was **never deployed** — the live IAM pins the exact resolved
    table ARN per stack (above), and both the deployed tables and steering 35 use the
    `test_` prefix. The suffix/wildcard rationale was stale and is retired here; do not
    reintroduce it or rename the live `test_`-prefixed tables to chase it.
- Pool deletion is high-risk and irreversible — run manually, never from automation,
  and only after confirming no dependency.
- **`cognito-idp update-user-pool` REPLACES the WHOLE pool config — never call it with a
  partial config.** The API overwrites every block, including `LambdaConfig`. Calling it with
  only (say) `--policies` and no `--lambda-config` BLANKS the Pre-Token-Generation trigger
  (`pretokengen-prod`), stripping `custom:entitlements` from every token — platform-wide auth
  breakage. The PreTokenGen trigger lives OUTSIDE Terraform/CFN (owned by `sam/pretokengen`
  + a manual identity-account attach — see `sam/pretokengen/DEPLOY.md`), so nothing silently
  re-adds it. Before any `update-user-pool`, READ the current config and PASS BACK UNCHANGED
  every block you are not intentionally editing (`LambdaConfig` especially), then verify the
  trigger survived. Prefer the NARROW APIs when they exist (`set-user-pool-mfa-config` touches
  only MFA/WebAuthn and is safe). This bit once (2026-10-07) — see
  `.kiro/specs/Common/Cognito/PassKey/findings.md` F-003; the fix is codified in
  `null_resource.cognito_passkey_post_apply` + the pool `lifecycle.ignore_changes`
  in `infrastructure/cognito.tf`.

## Tenant keys (per plane)

- **Flask/MySQL plane (myAdmin):** the `administration` column is the tenant key;
  scope every query by it (see `31-backend-database-flask-mysql.md`).
- **SAM-backed module plane (DynamoDB):** `tenant_id` is the partition key; scope
  every query by it, with IAM `dynamodb:LeadingKeys` as defense in depth.
