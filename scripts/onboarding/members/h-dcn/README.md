# `onboarding/members/h-dcn/` — h-dcn members onboarding (config + tenant tools)

Everything specific to onboarding the **h-dcn** tenant into the `members` module:
version-controlled config, the mapping contract, and the runners whose payload is h-dcn
(the Ledenbestand importer, the catalog/config seeds). Generic, reusable runners live in
`../_generic/`. Cross-plane secrets (the Google key + sheet/folder IDs) live git-ignored in
`scripts/tenants/h-dcn/` — see `scripts/tenants/README.md`.

Full runbook: **`ONBOARDING.md`** (ordered, runnable protocol + decisions log).

## Committed config (version-controlled)

| File | What it is |
| --- | --- |
| `ONBOARDING.md` | The ordered production-onboarding protocol + the agreed-decisions log. |
| `members_config.json` | SINGLE source of truth (D18) for `members.scope_dimensions` (the 10 regions) + `members.field_overlay` (fixed overrides + overlay fields). |
| `members_source_mapping.csv` | The authored mapping contract: one row per source column → target field / rule / disposition. |
| `members_config_loader.py` | Loads `members_config.json`; builds the region canonicalizer. Read by the seeds + the backfill. |
| `members_mapping_loader.py` | Parses + validates `members_source_mapping.csv` (drift + orphan guards against the config). |

## h-dcn tenant runners (payload is h-dcn)

| Runner | Purpose | Writes to | When used |
| --- | --- | --- | --- |
| `backfill-hdcn-members.py` | **gsheet → sam-members sync.** Reads the live Google Sheet (or an export), transforms via the h-dcn mapping, writes members to `sam-members`. `--reconcile` does a match-by-member_number upsert + absence sweep. Dry-run first. | DynamoDB `sam-members` | **LIVE flow #1.** The recurring member sync. |
| `seed-hdcn-members-config.py` | Author h-dcn's `members.scope_dimensions` + `members.field_overlay` params in MySQL from `members_config.json`. Idempotent upsert. | MySQL `parameters` | **LIVE flow #2 (seed step).** Driven by `../_generic/project-config-to-prod.py`; re-run when the config changes. |
| `seed-hdcn-catalog.py` | Seed the h-dcn Lidmaatschap Beheer membership-type catalog (the hardcoded `HDCN_MEMBERSHIP_TYPES`) into `sam-members`. | DynamoDB `sam-members` | **Occasional** — when the catalog changes. |
| `cognito-users.sample.json` | h-dcn-shaped sample input for `../_generic/load-cognito-users.py` (regions, `h-dcn-test`). Editable template, not run directly. | — | Reference / input to the Cognito load. |

## The two live onboarding flows

1. **gsheet → sam-members** — `backfill-hdcn-members.py` (sheet_id / worksheet / credential
   resolve from `scripts/tenants/h-dcn/secrets.local.json`; explicit CLI flags win).
2. **config → Railway MySQL → DynamoDB** — `../_generic/project-config-to-prod.py --tenant h-dcn`,
   which runs `seed-hdcn-members-config.py` then `ProjectionSync`.

See `ONBOARDING.md` for the full ordered sequence (provision table → author scope dims → seed
catalog → backfill → project config → verify).

## Secrets

The Google service-account key, spreadsheet ID, worksheet, and Drive folder IDs live in
`scripts/tenants/h-dcn/secrets.local.json` (git-ignored, co-located credential). The runners
resolve them from there unless overridden on the CLI. Template:
`scripts/tenants/h-dcn/secrets.example.json`.
