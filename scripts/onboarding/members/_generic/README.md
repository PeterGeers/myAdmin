# `onboarding/members/_generic/` — tenant-agnostic members-onboarding runners

Reusable runners for onboarding **any** tenant to the `members` module. Each is parameterized
by `--tenant` (no hardcoded tenant) and reads only generic `sam.members.*` code — no tenant
vocabulary or data is baked in. Tenant-specific tools (the h-dcn Ledenbestand importer, the
h-dcn catalog/config seeds) live in the tenant folder (`../h-dcn/`), not here.

All runners are **dry-run-first** (default writes nothing; `--apply` to write) and idempotent.
They bootstrap the repo root via a marker walk and use `scripts/onboarding/_lib` for path +
secrets resolution (see `../../README.md`).

## Runners

| Runner | Purpose | Writes to | When used |
| --- | --- | --- | --- |
| `provision-members-tables.py` | Create the single-table `sam-members` DynamoDB table (PK `tenant_id`, SK `sk`, PAY_PER_REQUEST). Tenant-global (no `--tenant`). | DynamoDB (DDL) | **One-time** per environment (already run for prod). |
| `project-config-to-prod.py` | Seed a tenant's `members.*` config params into MySQL, then project them to DynamoDB via `ProjectionSync` (config → Railway MySQL → DynamoDB). Reuses the tenant's `../<tenant>/seed-hdcn-members-config.py` seed step. | MySQL + DynamoDB | **LIVE h-dcn flow** — the config→projection path. Re-run whenever the tenant's members config changes. |
| `load-cognito-users.py` | Bulk-load Cognito users into a pool from an editable file; assign Members roles via the governance ENDPOINT (never a direct DB write). `--pool-id`/`--source` required. | Cognito + governance API | **Occasional** — when provisioning a tenant's users. Sample input: `../h-dcn/cognito-users.sample.json`. |
| `verify-member-scope-normalization.py` | READ-ONLY check that every stored member `region` (or other scope dimension) is canonical against the projection's config. Exit code signals offenders. | nothing (read-only) | **Occasional** — post-backfill / post-config verification. |
| `cleanup-membernum-guard-rows.py` | Delete the per-tenant `membernum#` uniqueness-guard rows (idempotent, re-checks the prefix before delete). | DynamoDB (deletes) | **One-off remediation** — a specific guard-row cleanup; not part of routine onboarding. |

## Live h-dcn onboarding flows (what we actually run)

Only two flows are part of the recurring h-dcn onboarding:

1. **gsheet → sam-members sync** — `../h-dcn/backfill-hdcn-members.py` (lives in the tenant
   folder; the transform engine is h-dcn-specific). Not in this folder.
2. **config → Railway MySQL → DynamoDB projection** — `project-config-to-prod.py` (here),
   which drives `../h-dcn/seed-hdcn-members-config.py`.

The other runners here are one-time setup (`provision-members-tables`) or
occasional/remediation tools (`load-cognito-users`, `verify-member-scope-normalization`,
`cleanup-membernum-guard-rows`) — kept because they are valid reusable tooling, not deleted.

## Why some h-dcn tools are NOT here

Runners whose payload is h-dcn-specific (the Ledenbestand importer, the hardcoded h-dcn
membership-type catalog seed, the h-dcn members-config seed, the h-dcn Cognito sample) live in
`../h-dcn/`, co-located with the config/loaders they depend on. See `../h-dcn/README.md`.
