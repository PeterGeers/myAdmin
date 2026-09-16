---
inclusion: auto
---

# AWS Accounts & Infrastructure — Platform Model

> Active-rules summary. Full reasoning:
> `.kiro/specs/multi-tenant/Analysis/second_thoughts.md`, `migration_plan.md`,
> `environments_and_testing.md`. Decision of record: ADR 0003.

The platform (myAdmin, evolved in place) spans two AWS accounts plus Railway.

## Account model

- **Identity account (personal, 344561557829):** home of the Cognito pools — the
  tenant-neutral access function for the whole platform.
  - **Pool A (admins):** the existing Cognito pool **named `myAdmin`** (pool id
    `eu-west-1_Hdp40eWmu`, app client `myAdmin-client`), kept in place (not migrated)
    — Plus tier. PRODUCTION. ("Pool A" is the audience-role label; `myAdmin` is the
    pool's actual name.)
  - **Pool B (end-users):** a NEW Essentials pool (to create).
  - **Standing test pool `myAdmin-test`** (pool id `eu-west-1_xyrlzfqbl`, app client
    `myAdmin-test-client` = `43s15cm8qcgg8an85udt0e087u`): a permanent Essentials-tier
    pool mirroring Pool A's app-client config, claim shapes, groups, and (like Pool A)
    **no Pre-Token-Generation trigger** — Pool A's `LambdaConfig` is empty, so there is
    nothing to mirror. Seeded with throwaway test users (one per role/claim shape plus
    an empty-groups edge case). All identity work (S2/S3/S4) is validated here first;
    production Pool A changes only after gated validation. Permanent (Essentials =
    10k MAU free). See `environments_and_testing.md`.
    - `iss`: `https://cognito-idp.eu-west-1.amazonaws.com/eu-west-1_xyrlzfqbl`
    - `jwks_uri`: `https://cognito-idp.eu-west-1.amazonaws.com/eu-west-1_xyrlzfqbl/.well-known/jwks.json`
  - **Legacy pools to remove** (after confirming no dependency; high-risk,
    irreversible — run manually): `eu-west-1_OAT3oPCIm`, `eu-west-1_VtKQHhXGN`.
  - Profile: `personal` — Cognito/identity administration only.
- **Infrastructure & data account (nonprofit, 506221081911):** all generic AWS
  services — DynamoDB, S3, SES, SNS, Secrets Manager, SSM Parameters, CloudFront, API
  Gateway, Lambda. No Cognito pool of record (triggers attach cross-account). Legacy
  pool `eu-west-1_fcUkvwjH5` (nonprofit H-DCN) is decommissioned with this account's
  cleanup.
  - Profile: `nonprofit-deploy` — all infrastructure operations.
- **Railway (external):** myAdmin Flask backend + MySQL. Stays as-is; the system of
  record for tenant management. Only its AWS resources move to nonprofit (roadmap S6,
  see `migration_plan.md`).

## Guardrails

- Region: `eu-west-1` throughout.
- DynamoDB tables, Cognito pools, and S3 data buckets are managed **outside**
  CloudFormation (or with `DeletionPolicy: Retain`) — a prior deploy deleted prod data
  by not doing this.
- Never `--delete` or `rm --recursive` against a data bucket. Back up before any data
  move. Keep distinct data buckets separate; never cross them.
- Critical env vars must fail fast (throw on missing) — no dangerous fallbacks.
- DynamoDB tables use PAY_PER_REQUEST (on-demand) billing.

## Tenant keys (per plane)

- **Flask/MySQL plane (myAdmin):** the `administration` column is the tenant key;
  scope every query by it (see database-patterns).
- **SAM-backed module plane (DynamoDB):** `tenant_id` is the partition key; scope
  every query by it, with IAM `dynamodb:LeadingKeys` as defense in depth.
