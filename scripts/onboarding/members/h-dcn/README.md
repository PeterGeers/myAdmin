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
| ~~`seed-hdcn-catalog.py`~~ | **RETIRED (03b).** Membership types are no longer a separate `membershiptype#` catalog; they are the `membership_type` field's own inline `options`, folded from `HDCN_MEMBERSHIP_TYPES` by the EXPAND migration (`sam/members/migration/membership_type_catalog_to_field_options.py`). The seeder + its `save_membership_type` write path were removed. | — | — |
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

## Faster re-onboarding and safety (added 2026-11-13)

- onboard-hdcn-members.sh: one command = seed config then dry-run then apply --reconcile (dedup guarded).
- backfill-hdcn-members.py --dedup: pre-flight duplicate guard. Refuses --apply (exit 2) if the tenant already has duplicate member_numbers; with --reconcile it also re-verifies after apply.
- verify-hdcn-members.py: read-only table-vs-source verification (counts, duplicates, drift).
- DynamoDB PITR is ENABLED on the sam-members table (35-day restore window).

### Secrets (never commit)
- Real secrets live in scripts/tenants/h-dcn/secrets.local.json plus the Google service-account key beside it.
- Both are git-ignored (scripts/tenants/*/* plus the google-service-account.json patterns). Only secrets.example.json is committed.

#  Commands
## Run full onboarding (single command):
AWS_PROFILE=nonprofit-deploy bash scripts/onboarding/members/h-dcn/onboard-hdcn-members.sh

## Dry-run only:
SKIP_SEED=1 SKIP_DRY=1 bash scripts/onboarding/members/h-dcn/onboard-hdcn-members.sh

## Verify only:
backend/.venv/bin/python scripts/onboarding/members/h-dcn/verify-hdcn-members.py --tenant h-dcn

