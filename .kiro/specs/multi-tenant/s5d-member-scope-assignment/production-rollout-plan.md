# s5d — Production rollout action plan (h-dcn pilot)

Goal: bring the s5d member-user scope feature live in **production**. The correct
flow separates the **generic platform** (tenant-agnostic — ship once) from the
**h-dcn tenant onboarding** (done AFTER the platform is live). Starting state
(VERIFIED 2026-09-22):
- **SAM Members module does NOT exist** in prod yet (no `sam-members` table, no
  deployed stack/API).
- **MySQL:** exactly ONE new table to create (`user_tenant_scope`); NO existing
  MySQL record references the members module for any tenant yet (h-dcn has no
  MEMBERS `tenant_modules` row, no `members.*` params, no scope grants).
- So this is a **cold start**: build the code, stand up the generic platform, THEN
  onboard tenant h-dcn (enable module → seed config → import data → grant scope).

Phases (revised for the cold-start flow):
- **PHASE A — Code** (on `feature/sam-members`, BEFORE merge): the open code changes
  the rest of the flow depends on.
- **PHASE B — Platform deploy** (generic, tenant-agnostic): merge → Flask + SAM +
  SPA live; the `user_tenant_scope` table; the SAM stack + `sam-members` table.
- **PHASE C — Onboard tenant h-dcn**: enable the MEMBERS module → seed catalog +
  `field_overlay` + `scope_dimensions` → import members → roles → scope grants.
- **PHASE D — Verify end-to-end.**

> **Companion doc (authoritative for the field/enum/overlay model + the ordered
> onboarding protocol):** `scripts/aws/h-dcn/ONBOARDING.md`. This plan is the phased
> runbook; ONBOARDING.md owns the member field model (fixed vs overlay, functional
> groups), the four enum/dropdown buckets, the exact `members.field_overlay` payload,
> the `member_id` (UUID) + `member_number` (`M00001`) decisions, the dropdown-validation
> layering (§4.1), and the "open code changes" list (§8). Where the two overlap, the
> detail lives in ONBOARDING.md and this plan REFERENCES it (see PHASE C, esp. C.2/C.3)
> — keep them in sync when either changes.

Environments (steering 23-aws-accounts):
- **Flask + MySQL** → Railway (system of record for tenant/governance data).
- **DynamoDB (sam-members, governance projection) + Lambda + API GW** → AWS
  account `nonprofit-deploy` (506221081911), region `eu-west-1`.
- **Cognito** → the **myAdmin** pool `eu-west-1_Hdp40eWmu` (aka "Pool A", app client
  `myAdmin-client` / `66tp0087h9tfbstggonnu5aghp`), AWS account `personal`
  (344561557829), region `eu-west-1` — the identity account. VERIFIED 2026-09-22:
  this is the pool this workspace uses (`frontend/.env`, steering 21/22/23); the SAM
  Members API authenticates against it and its verified-auth edge validates ITS tokens.
  Prod SPA users log in here. NOTE: `eu-west-1_fcUkvwjH5` is a DIFFERENT pool — that is
  the h-dcn app's pool in the NONPROFIT account (506221081911), NOT used by myAdmin.

Guardrails (steering 23): DynamoDB tables + Cognito pools are managed OUTSIDE
CloudFormation / retained; never `--delete`/`rm -r` a data bucket; back up before
any data move; PAY_PER_REQUEST; `sam-` table prefix stays at the front; critical
env vars fail-fast.

Isolation from the existing h-dcn app (VERIFIED 2026-09-22 — the two share the AWS
account `506221081911` but do NOT interfere):
- **DynamoDB — disjoint.** The Members module uses ONLY `sam-members` (its own new
  `sam-`prefixed table, created in B.3 — NOT the legacy `Members` table) and reads
  `governance_projection` READ-ONLY. The h-dcn app's tables (`Members`, `Producten`,
  `Payments`, `Events`, `Memberships`, `Carts`, `Orders`, `Counters`, `Parameters`,
  `StockMovements`) are untouched — no name overlap, no writes to them.
- **Stack — separate; the deploy stack name MUST NOT be `h-dcn`.** The Members module is
  its own SAM/CloudFormation stack (function `members-prod`, layer `members-layer-prod`,
  its own `MembersApi`). Pin a distinct stack name in the samconfig/workflow (A.7/A.13),
  e.g. `sam-members` — sharing `h-dcn` would collide.
- **Cognito — SEPARATE pools in SEPARATE accounts (no sharing).** myAdmin (incl. the SAM
  Members API) uses pool `eu-west-1_Hdp40eWmu` ("myAdmin") in the PERSONAL account
  (344561557829). The h-dcn app uses `eu-west-1_fcUkvwjH5` (H-DCN pool) in the NONPROFIT
  account (506221081911). Different pool, different account → zero auth overlap. The SAM
  module only uses its pool as an API Gateway authorizer + verifies bearer tokens; it
  attaches NO trigger and never modifies the pool/users/groups.
- **Tables are managed-outside-CFN / `Retain`** (B.4) — a deploy can never
  recreate/replace `governance_projection` or the legacy tables.

Legend: `[ ]` todo · `[H]` human/credentials required · `[!]` destructive-or-
irreversible — confirm first · `[BACKUP]` take a backup before this step.

===================================================================
## PHASE A — Code changes (on `feature/sam-members`, BEFORE the merge)
===================================================================
These are the generic-platform + h-dcn code deltas the rest of the flow depends on
(the ONBOARDING.md §8 list). Implement + test on the branch; they ship together at
the B.1 merge. NONE touches prod.

STATUS: A.1–A.11 DONE on `feature/sam-members`; full `sam/tests` suite green
(A.8). A.12 (this doc update) in progress. During implementation A.1 was
CORRECTED — the real regions are tenant data and must NOT live in the generic
core; see A.9/A.10 and Decisions D16/D17/D18 in `scripts/aws/h-dcn/ONBOARDING.md`.
- [x] **A.1 ~~`HDCN_SCOPE_CONFIG` → the real 10 regions~~ — SUPERSEDED by A.9.**
  The generic core (`sam/members/domain/scope_dimensions.py`) must NOT carry a real
  tenant's vocabulary. It was instead renamed to `SAMPLE_SCOPE_CONFIG` and ships only
  synthetic `North/South/East/West` dimensions. The real 10 h-dcn regions live ONLY in
  `scripts/aws/h-dcn/members_config.json` → MySQL → projection (see A.9/A.10, D17).
- [x] **A.2 Backfill identity + number shaping** (`sam/members/migration/hdcn_backfill.py`):
  mints `member_id = uuid4()` (stable internal id), and maps source `Lidnummer` →
  `membership.member_number` as `M{n:05d}` (`M00001`, width-5 sortable string) — NOT as
  `member_id`. Also derives `joined_date` (`Datum ondertekening` date-part →
  `Aanmeldingsjaar-01-01` → sysdate), `status="active"`, and omits `birth_date`
  (privacy). (ONBOARDING §2/§3/§6.1; D4–D9.)
- [x] **A.3 Backfill region alias** `Groningen/Drente` → `Groningen/Drenthe` — handled by
  the `RegionCanonicalizer` (alias map), since `scope_canon` can't fold the `h`; the
  105 affected rows normalize onto the canonical value. (D3; the canonicalizer is now
  sourced from `members_config.json` — see A.10.)
- [x] **A.4 `Overig` membership-type** — added `overig` to the catalog seed
  (`hdcn_catalog_seed.py`) + `MembershipTypeMapper.DEFAULT_ALIASES["overig"]="overig"`;
  numbered `Clubblad` members alias to `overig`, Clubblad orgs w/o Lidnummer skipped.
  (D12/D13.)
- [x] **A.5 Generic overlay-enum choice-membership validation** (partial-update-
  friendly) — `MembershipService._reject_invalid_overlay_enum_values(...)` enforces an
  overlay enum (`motor_brand`) against its `choices` ONLY when the field is present in
  the write (`create_member`, and `update_member(previous=existing)`), so new/edited
  values are enforced and untouched legacy values pass. (ONBOARDING §4.1; D11.)
- [x] **A.6 Cognito pool-key rename** in `sam/members/template.yaml` +
  `env-vars.local.json`: `Hdcn*` params / `HDCN_*` env → `MyAdmin*` / `MYADMIN_*`
  (`COGNITO_POOL_KEYS=MYADMIN`) — the values are the **myAdmin** pool (personal acct
  `eu-west-1_Hdp40eWmu`); the `HDCN` label was misleading. (ONBOARDING §8.7; D19.)
  NOTE: `sam/members/.aws-sam/build/template.yaml` is a regenerated build artifact and
  still shows the old names — ignore; it is rebuilt on `sam build`.
- [x] **A.7 Add `sam/members/samconfig.toml`** with a `prod` environment (stack name
  `sam-members` — NOT `h-dcn`; `region = eu-west-1`; the fail-fast parameter_overrides)
  so prod deploys are reproducible and the workflow (A.13) can omit inline flags. (D20.)
- [x] **A.8 Run the test suite** (`sam/tests`, backend unit) — region-config, backfill,
  catalog-seed, overlay-enum, parity-harness, and fixed-field tests all PASS on the
  branch (full `sam/tests` green).

Added during implementation (tenant-data-out-of-core refactor; D16–D18):
- [x] **A.9 Keep tenant data OUT of the generic core** (`scope_dimensions.py`):
  `HDCN_SCOPE_CONFIG` → `SAMPLE_SCOPE_CONFIG` with only synthetic `North/South/East/West`
  dimensions. Downstream tests derive their expected vocab from `SAMPLE_SCOPE_CONFIG`
  rather than hard-coding regions. This replaces the original A.1 intent. (D17.)
- [x] **A.10 Backfill sources the region vocab from tenant config, not from code**
  (`sam/members/migration/hdcn_backfill.py` + `scripts/aws/backfill-hdcn-members.py`):
  a `RegionCanonicalizer` (built from `scripts/aws/h-dcn/members_config.json` via
  `members_config_loader.py`, wired through the new `--members-config` CLI arg) supplies
  the 10 real regions + the `Groningen/Drenthe` alias. The core no longer knows any real
  region. Final dry-run: **1152 ok, 90 skipped, 0 errors** (non-members skipped per D14,
  duplicate member numbers skipped per D15). (D17/D18.)
- [x] **A.11 No projection fallback + authored member config**:
  (a) `scripts/aws/verify-member-scope-normalization.py` raises `ProjectionUnavailableError`
  and exits `4` (SYSTEM ERROR) instead of falling back to a hardcoded tenant model; a
  tenant with no scope config is "not onboarded" (exit `2`). (D16.)
  (b) member CONFIG is AUTHORED, not backfilled: new `scripts/aws/seed-hdcn-members-config.py`
  upserts the `members.*` params (field_overlay + scope_dimensions) via `set_param`,
  single-sourced from `scripts/aws/h-dcn/members_config.json`. (D18.)
- [x] **A.12 Update rollout plan + ONBOARDING.md to match the code** (this task):
  reflected the A.1 supersession, A.9–A.11, and Decisions D16–D20; reconciled PHASE C
  (C.3+C.4 scripted config seed via `seed-hdcn-members-config.py`; C.6/C.7 `--members-config`;
  C.8 exit-4 no-fallback). ONBOARDING Decisions log D1–D20 already updated.
- [x] **A.13 Add the SAM auto-deploy workflow** `.github/workflows/deploy-sam-members.yml`
  (so SAM ships on merge like Flask/frontend). This is a CODE change on the branch that
  MUST ship in the same PR as the rest of PHASE A — otherwise the B.1 merge will deploy
  frontend + Flask but NOT SAM. (Moved here from PHASE B: it is a prerequisite of the
  merge, not a post-merge step.) DONE: created the workflow (OIDC, no secrets;
  `push` on `main` for `sam/members/**`+`sam/shared/**` + `workflow_dispatch`;
  `sam build` then `sam deploy --config-env prod`, so all deploy params come from the
  A.7 `samconfig.toml`). Verified `sam validate --config-env prod` resolves + template is
  valid. STILL PENDING (one-time [H], not code): the `NonprofitDeployRole` OIDC-trust
  entry for `repo:PeterGeers/myAdmin:ref:refs/heads/main` — until added, the deploy job
  fails at assume-role (frontend + Flask still deploy); manual fallback documented below.
  REUSE the h-dcn repo pattern
  (`/home/peter/projects/h-dcn/.github/workflows/deploy-backend.yml`): GitHub **OIDC**,
  NO stored secrets (`permissions: id-token: write` + `aws-actions/configure-aws-credentials@v4`
  with `role-to-assume: arn:aws:iam::506221081911:role/NonprofitDeployRole`,
  `aws-region: eu-west-1`), then `aws-actions/setup-sam@v2` → `sam build` → `sam deploy`.
  - `on: push: branches:[main] paths:['sam/members/**','sam/shared/**','.github/workflows/deploy-sam-members.yml']` + `workflow_dispatch`.
  - `working-directory: sam/members`; deploy with the A.7 `samconfig.toml` `prod`
    env (stack name NOT `h-dcn`; params `Stage=prod`, `MembersTableName=sam-members`,
    `GovernanceProjectionTableName=governance_projection`, `Region=eu-west-1`,
    `CognitoUserPoolArn=arn:aws:cognito-idp:eu-west-1:344561557829:userpool/eu-west-1_Hdp40eWmu`
    — the myAdmin pool, PERSONAL account, cross-account from this nonprofit deploy; an
    API GW authorizer references the pool by ARN, no cross-account role needed).
  - PREREQUISITE (one-time [H]): confirm `NonprofitDeployRole`'s OIDC trust allows
    `repo:PeterGeers/myAdmin:ref:refs/heads/main` (h-dcn's trust is scoped to the h-dcn
    repo). Until added, the assume-role fails. Manual fallback: `cd sam/members &&
    sam build && sam deploy` via `workflow_dispatch` or local CLI (`--profile nonprofit-deploy`).

===================================================================
## PHASE B — Platform deploy (GENERIC / tenant-agnostic; no h-dcn data yet)
===================================================================
Stands up the platform for ALL tenants. Order: backend contracts first, UI last.
- [x] **B.0 [BACKUP] Back up prod MySQL** (Railway) — `parameters`, `user_tenant_roles`,
  `tenants`, `tenant_modules` (a full dump is better). Lets us roll back config/schema.
- [x] **B.1 Merge/PR `feature/sam-members` → `main`.** DONE — PR #15 merged (merge commit
  `a1f14c0`, 2026-09-22). On merge, THREE deploys fire automatically: FRONTEND (GitHub
  Pages, `.github/workflows/deploy-frontend.yml`), FLASK (Railway GitHub integration on
  push to `main`), and SAM (`.github/workflows/deploy-sam-members.yml`, added in A.13).
  The A.13 OIDC-trust prerequisite was completed first (NonprofitDeployRole trust widened
  to `repo:PeterGeers/myAdmin:*`, stack `h-dcn-iam-roles` UPDATE_COMPLETE + committed to
  h-dcn IaC `37fc5d3`), so the SAM CI deploy ran green (run 35782647793, conclusion
  success). PRE-MERGE VALIDATION (Path A): the `sam-members` stack was first deployed
  manually via `sam deploy --config-env prod --profile nonprofit-deploy` →
  CREATE_COMPLETE; smoke `GET /prod/members` → 401 (authorizer live). That manual deploy
  caught + fixed an empty-`DynamoDbEndpointUrl` override bug in `samconfig.toml` (commit
  `b4caad6`) that would otherwise have failed the CI deploy identically.
  NOTE: `MembersApiBaseUrl` is NOT stored here — re-fetch from the stack output:
  `aws cloudformation describe-stacks --stack-name sam-members --query "Stacks[0].Outputs[?OutputKey=='MembersApiBaseUrl'].OutputValue" --output text --profile nonprofit-deploy --region eu-west-1`.
- [x] **B.2 [H] Apply the `user_tenant_scope` migration to prod MySQL** — DONE (verified
  on Railway/prod MySQL, which is physically separate from the local dev DB). Prod's
  `database_migrations` shows `create_user_tenant_scope_table` = `status='success'` and
  the `user_tenant_scope` table exists (keyed `(email, administration, module)`, FK to
  `tenants(administration)`, `idx_administration` + `idx_admin_module`). No failed
  migrations blocked the batch. Applied out of band from this WSL shell because the
  Railway CLI (Windows npm shim) doesn't run reliably under WSL — the SQL was run
  directly on prod. COSMETIC follow-up (optional, non-blocking): the tracker has a
  DUPLICATE `create_user_tenant_scope_table` `success` row; harmless (the runner only
  checks name presence) — can be de-duped keeping the earliest `id` if desired.
  (Original runner command, for reference:
  `cd backend && PYTHONPATH=src python -c "from database_migrations import DatabaseMigration; DatabaseMigration(test_mode=False).run_all_migrations()"`.)
  Verified the table (keyed `(email, administration, module)`, FK to
  `tenants`, `idx_administration`).
- [x] **B.3 [H] Create the prod `sam-members` table** — DONE. Ran
  `provision-members-tables.py` (dry-run first, then `--apply`) with
  `MEMBERS_TABLE=sam-members AWS_REGION=eu-west-1 AWS_PROFILE=nonprofit-deploy`. Verified
  live: table `sam-members` is **ACTIVE**, key shape `tenant_id` (S, HASH) + `sk` (S,
  RANGE), PAY_PER_REQUEST, 0 items, no GSIs (from `sam/members/repository/table_design.py`).
  Additive/idempotent; `governance_projection` and the legacy tables were left untouched.
  IAM reminder: bind the principal to `sam-*` / the tenant partition separately
  (`table_design.LEADING_KEYS_IAM_POLICY_PLAN`) — the Lambda's own role from the SAM
  stack already covers its access.
- [x] **B.4 Confirm the SAM deploy** — DONE. Stack `sam-members` is up (B.1); `sam-members`
  (just created) + `governance_projection` (pre-existing) are the managed-outside-CFN prod
  tables. `MembersApiBaseUrl` is re-fetchable from the stack output (not stored here — see
  the B.1 note for the command).
- [x] **B.5 Smoke-check the platform (no tenant data yet):** SAM `MembersApi` returns 401
  without a token (authorizer live, no regression to 5xx after the table create) — correct.
  Frontend (GitHub Pages) + Flask (Railway) deploys reported successful. A member list is
  expected EMPTY at this point — no tenant is onboarded yet (PHASE C).

===================================================================
## PHASE C — Onboard tenant h-dcn (config → data → scope)
===================================================================
Nothing here touches other tenants. Cold start: h-dcn has no MEMBERS module row, no
`members.*` params, no members, no grants yet.
- [x] **C.1 [H] Enable the MEMBERS module for h-dcn** (`tenant_modules`) — DONE (verified
  2026-09-22 on prod Railway MySQL: tenant `h-dcn` created, row `h-dcn/MEMBERS/is_active=1`).
  UI renders the Members section after a refresh (5-min role/module cache TTL — a refresh
  or re-login surfaces it; not a bug). PREREQUISITE
  for everything below: the `members.*` parameter namespace is GATED to an active
  MEMBERS module (`parameter_schema.py`: `members` → `module: MEMBERS`). Until h-dcn has
  the active MEMBERS module row, `ParameterService.set_param("tenant","h-dcn","members",…)`
  (C.3/C.4) is rejected. Add the `tenant_modules` row for `administration='h-dcn'`,
  module `MEMBERS`, active.
- [x] **C.2 [H] Seed the Lidmaatschap Beheer membership-type catalog** — DONE + VERIFIED
  2026-09-22 (prod `sam-members`, tenant `h-dcn`, `--apply`: created 7 / updated 0). Read-back
  query confirms 7 items `membershiptype#{gewoon_lid,gezins_lid,erelid,donateur,gezins_donateur,
  sponsor,overig}` in the `h-dcn` partition. Dry-run-first, idempotent upsert:
  `scripts/aws/seed-hdcn-catalog.py --tenant h-dcn` (then `--apply`). All `active=True`.
  ⚠️ **CREDENTIALS GOTCHA (applies to ALL AWS-side C-steps below).** The repo-root `.env`
  exports static `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` for the **personal** account
  (344561557829) AND `AWS_ENDPOINT_URL_DYNAMODB=http://localhost:8000`. boto3 ranks static
  env keys ABOVE `AWS_PROFILE`, so a plain `AWS_PROFILE=nonprofit-deploy` invocation silently
  hits the WRONG account (personal) → `ResourceNotFoundException` on `sam-members` (which only
  exists in nonprofit 506221081911). The endpoint var also silently redirects to the local
  emulator. STRIP BOTH. Verified-safe invocation for every AWS Phase-C script:
  ```bash
  env -u AWS_ENDPOINT_URL_DYNAMODB -u AWS_ACCESS_KEY_ID -u AWS_SECRET_ACCESS_KEY -u AWS_SESSION_TOKEN \
    MEMBERS_TABLE=sam-members AWS_REGION=eu-west-1 AWS_PROFILE=nonprofit-deploy \
    backend/.venv/bin/python scripts/aws/<script>.py ...
  ```
  Sanity-check identity first: with the strip, `sts get-caller-identity` must show account
  `506221081911` (NonprofitDeployRole), NOT `344561557829`.
- [x] **C.3+C.4 [H] Author the member CONFIG (`field_overlay` + `scope_dimensions`)** —
  DONE + VERIFIED 2026-09-23 (`--apply`). Both params upserted to prod Railway MySQL
  `parameters` (scope `tenant`/`h-dcn`, namespace `members`): `scope_dimensions` (json) +
  `field_overlay` (json, ~4.7KB). Read-back confirms the 10 regions exactly:
  `["Brabant/Zeeland","Duitsland","Friesland","Geen","Groningen/Drenthe","Limburg",
  "Noord Holland","Oost","Utrecht","Zuid Holland"]` (correct spelling, no `Overig`).
  ⚠️ **This is a MySQL/Railway step — NOT AWS.** The script builds
  `DatabaseManager(test_mode=False)` reading `DB_*`, which defaults to LOCAL Docker — so it
  MUST run through the Railway wrapper or it authors config into the wrong DB. Verified
  invocation used: `PYTHONPATH=backend/src backend/scripts/railway-db.sh
  backend/.venv/bin/python scripts/aws/seed-hdcn-members-config.py --tenant h-dcn --apply`.
  No AWS credential strip needed here (that's only for the DynamoDB steps).
  ---
  now a SINGLE scripted, single-sourced step (config is AUTHORED, not backfilled — D18).
  Run `scripts/aws/seed-hdcn-members-config.py`, which upserts BOTH `members.*` params
  via `ParameterService.set_param(...)` from the one authoritative source
  `scripts/aws/h-dcn/members_config.json` (mirrors ONBOARDING.md §5). Dry-run first, then
  `--apply`. This writes:
  - `members.field_overlay` — fields, `{nl,en}` labels, dropdown/enum choices (incl. the
    `motor_brand` enum enforced by A.5), functional groups, `gender` M/V/X/N, `status`
    relabels, `M00001` member_number format. Fires `enqueue_sync` → `config#fields`.
  - `members.scope_dimensions` — the 10 regions:
    `[{"key":"region","field":"region","label":{"nl":"Regio","en":"Region"},"enabled":true,
    "values":[<the 10>],"required_for":["Members_CRUD"]}]`. NO `multi_valued`, NO
    `all_wildcard`/`Regio_*`. Fires `enqueue_sync` → `config#scope`.
  Author BEFORE the backfill (R9) so overlay/dropdown values resolve and `region`
  canonicalizes to the right vocabulary. Alternatively author via the Tenant-Admin
  members-config UI (audited), but the script keeps it reproducible + single-sourced.
- [x] **C.5 [BACKUP] Back up the DynamoDB projection + members** — DONE 2026-09-23 via
  on-demand DynamoDB backups (both `AVAILABLE`, verified):
  - `governance_projection-preC7-20260923-081530` (1817 B) — baseline 16 items
  - `sam-members-preC7-20260923-081530` (731 B) — baseline 7 items (catalog only, pre-members)
  Restore path if C.7 goes wrong: `aws dynamodb restore-table-from-backup` (with the
  credential strip). Baseline captured before ANY member write.
- [x] **C.6 [H] DRY-RUN the member backfill (writes nothing)** — DONE 2026-09-23. Result
  matched the target EXACTLY: **1152 ok, 90 skipped (1242 source), 0 errors, 0 missing
  region.** Verified in samples: `member_id`=UUID, `member_number`=`M#####`, `region` on
  `overlay.region` as canonical (Utrecht/Oost/Zuid Holland), `status=active`, `tenant_id=h-dcn`.
  All `membership_type` values validated against the 7 seeded catalog codes (ran with
  `--known-code` ×7 → 0 errors). 3 within-batch duplicate member numbers flagged
  (`M06247`, `M06560`, `M06564`) — on apply the repo writes the 1st, rejects the 2nd (D15).
  Invocation used the AWS credential strip (see C.2 warning) + `--members-config`.
  `MEMBERS_TABLE=sam-members AWS_REGION=eu-west-1 AWS_PROFILE=nonprofit-deploy \`
  `  backend/.venv/bin/python scripts/aws/backfill-hdcn-members.py --source .agent-output/Ledenbestand.json --tenant h-dcn \`
  `    --members-config scripts/aws/h-dcn/members_config.json`
  The `--members-config` arg (A.10) supplies the region vocabulary + `Groningen/Drenthe`
  alias (the core no longer knows any real region — D17). Review the fidelity report:
  field mapping; `region` lands on `overlay.region` as a CANONICAL value (NOT
  `scope_values`); `member_id` is a UUID; `member_number` is `M00001`-shaped. SKIPPED
  (reported, NOT errors): empty export rows, non-members with no `Lidnummer` (D14 —
  future contact table), and ALL occurrences of duplicate member numbers (D15). Expected
  on the current export: **1152 ok, 90 skipped, 0 errors.**
- [x] **C.7 [!][H] APPLY the backfill** — DONE + VERIFIED 2026-09-23. `--apply` summary:
  **written 1152, conflicts 0, errors 0**; independent DynamoDB count of `member#` items in
  the `h-dcn` partition = **1152** (matches). Writes to `sam-members` (prod) only.
  ⚠️ **Two write-only bugs were found on the FIRST apply attempt and fixed before this clean
  run** (dry-run never caught them — it doesn't serialize to DynamoDB):
  1. **float→Decimal** — `overlay.Bedrag` (a JSON float, the fee) hit boto3
     "Float types are not supported." FIX: recursive `floats_to_decimal()` in
     `sam/members/repository/table_design.py`, applied in the item builders (+ inline
     `save_membership`/`save_delegates`). Failed on record 1 → no partial write.
  2. **empty attribute name** — the source's blank-header column folded into `overlay[""]`,
     which DynamoDB rejects ("Empty attribute name"). FIX: skip empty-named overlay keys in
     `sam/members/migration/hdcn_backfill.py` `map_hdcn_row`. This one had partially written
     ~176 members → RECOVERED via `.agent-output/cleanup_partial_members.py` (deleted 352
     member#/membernum# items back to the 7-catalog baseline) before the clean re-run.
  Both fixes covered by new tests (`sam/tests/test_members_repository.py`,
  `test_hdcn_backfill.py`); full `sam/tests` green. NOTE: each backfill run mints fresh
  `member_id` UUIDs, so it is NOT idempotent across runs — a clean baseline before `--apply`
  is mandatory (verified at 7 before this run). C.5 backup was the safety net (unused —
  cleanup was surgical).
- [x] **C.8 Run the R9.5 normalization verification (read-only)** — PASS 2026-09-23 (exit 0).
  Every distinct member region ∈ the 10 canonical values. NOTE: **C.11 (resync) had to run
  FIRST** — see below. The check reads the canonical set SOLELY from the projection
  `config#scope` (D16: no fallback), so a stale projection makes it read the wrong set.
  - FIRST attempt FAILED (exit 3): the projection `config#scope` still held a STALE
    Sept-18 row with the synthetic pilot values `[Noord,Zuid,Oost,West]` (+ retired
    `all_wildcard: Regio_All`, `multi_valued`) — leftover dev/local data (`onboard-hdcn-local.py`
    warning in SEQUENCING NOTES). C.3/C.4 authored the REAL 10 regions in MySQL but the
    projection was never re-synced, so the check compared members against the wrong vocab.
    This was NOT an illegitimate fallback — the reader faithfully returned a real (stale) row.
  - FIX = run C.11 resync (below) → re-run C.8 → PASS.
  Exit codes (A.11 / D16 — NO fallback to a hardcoded tenant model): `0` PASS, `2` tenant
  not onboarded (no scope config), `3` un-normalized member value(s), `4` SYSTEM ERROR
  (`ProjectionUnavailableError` — projection read failed; investigate, do NOT proceed).
  ⚠️ **Cross-plane AWS credential gotcha (worse than the C.2 one).** The projection sync +
  this verify read MySQL (Railway) AND write/read DynamoDB (nonprofit-deploy) in ONE process.
  `env -u ... AWS_PROFILE=nonprofit-deploy` was NOT enough — botocore still logged "Found
  credentials in environment variables" and hit the WRONG account (`ResourceNotFoundException`
  on `governance_projection`), because the `.env`/session leaked personal-account keys into
  the boto3 default session at import. RELIABLE FIX: export the ROLE's real temp creds into
  the env (overwrites any leak), no `AWS_PROFILE`:
  ```bash
  unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN AWS_ENDPOINT_URL_DYNAMODB
  eval "$(aws configure export-credentials --profile nonprofit-deploy --format env)"; unset AWS_PROFILE
  ```
- [x] **C.9 [H] Seed / confirm user ROLES** in `user_tenant_roles` — DONE EARLY (verified
  2026-09-22 prod): `webmaster@h-dcn.nl` on `h-dcn` has `Tenant_Admin` (id 95),
  `Members_CRUD` (id 96, the `required_for` gate), `Finance_CRUD` (id 97). Roles are
  INDEPENDENT of scope; a grant without the capability is inert. (Roles can be done any
  time before C.10; sequenced early here without issue.)
  NOTE: a role assigned OUT-OF-BAND (direct SQL, not via the tenant-admin route that calls
  `role_cache.invalidate_cache`) could read as "not assigned" for up to the 5-min TTL —
  fixed durably by not caching empty role lookups (`backend/src/auth/role_cache.py`,
  next Flask deploy). A refresh/re-login clears it meanwhile.
- [x] **C.10 [H] Author per-user scope grants** — DONE 2026-09-23 (authored via SPA), +
  projected. Two `user_tenant_scope` rows (MySQL, verified): `webmaster@h-dcn.nl` →
  `{"region":["*"]}` (all-access), `peter@pgeers.nl` → `{"region":["Utrecht"]}`.
  ⚠️ **Same projection-lag gotcha as C.11:** authoring in the SPA wrote MySQL + fired
  `enqueue_sync`, but the `scopegrant#` projection rows did NOT appear (queue not processed
  outside a running app that drains it). SYMPTOM: both users saw ZERO members — including the
  `["*"]` user, which ruled out scope-filtering and pointed at the missing projection (NOT a
  cache: the SAM edge builds a FRESH projection reader per request — `handler/app.py`
  `_new_projection_reader`, R5 — so there is no stale backend cache). FIX: re-ran the
  projection sync (export-role-creds technique) → written 3 → both
  `scopegrant#{webmaster@h-dcn.nl,peter@pgeers.nl}#region` rows now present + verified
  (`["*"]` / `["Utrecht"]`). Members visible on next fresh request. `["*"]` = all-access.
- [x] **C.11 Re-sync the projection** — DONE 2026-09-23, run BEFORE C.8 (the projection was
  stale — see C.8). Ran the production path `get_default_trigger()._resolve_sync().
  sync_administration("h-dcn")` (same as `POST /api/tenant-admin/projection/resync`). Result:
  **written 9, deleted 1** — the diff-and-replace overwrote the stale Sept-18 `config#scope`
  (Noord/Zuid/Oost/West) with the real 10 regions from MySQL `members.scope_dimensions`, and
  removed the 1 obsolete row. Read MySQL (Railway) + wrote DynamoDB (nonprofit-deploy) in one
  process — needed the export-role-creds technique (see C.8 gotcha). Re-run C.8 → PASS.
  NOTE: this ordering (C.11 before C.8) will recur for any tenant onboarded via the offline
  `seed-hdcn-members-config.py` script rather than the live app — the script authors MySQL +
  fires `enqueue_sync`, but nothing processes that queue outside the running Flask app, so a
  manual resync is REQUIRED before the projection reflects the config.
- [x] **C.12 Remove legacy `Regio_*` role rows (cleanup)** — DONE 2026-09-23. Scope turned
  out BROADER than just `Regio_*`: found 3 STALE `role#` rows in the prod projection with NO
  MySQL `user_tenant_roles` source — `webmaster@h-dcn.nl#Regio_All` (the named legacy row),
  `webmaster@h-scn.nl#Tenant_Admin` (typo `h-scn`), and `member-test@example.com#Members_CRUD`.
  Deleted via a diff-computed cleanup (projection `role#` rows MINUS the MySQL source set),
  so the 4 legit rows were untouched — incl. `peter@pgeers.nl#Members_CRUD` (id 98). Verified:
  projection now has exactly 4 `role#` rows, all MySQL-backed.
  ROOT CAUSE of the staleness (→ backlog): `ProjectionSync` only reconciles/deletes obsolete
  `scopegrant#` rows, NEVER `role#`/`module#`/`config#` — so role removals in MySQL never
  propagate as projection deletions and orphaned `role#` rows accumulate. Logged in
  `.kiro/specs/myBacklog/backlog.md`. ⚠️ Relevant to PHASE CE: a stale `role#` could inflate
  the resolved entitlement once the PreTokenGen trigger is live — worth fixing before/with CE.2.

===================================================================
## PHASE CE — CAPABILITY CHANNEL (blocks PHASE D) — the s5c Phase 7 tasks never run
===================================================================
> **WHY THIS EXISTS (RCA 2026-09-23).** After C.1–C.11 the member DATA + SCOPE are correct
> in prod, but BOTH users (`webmaster@h-dcn.nl` `["*"]`, `peter@pgeers.nl` `["Utrecht"]`)
> get **403 / "Geen leden gevonden"**. Direct `GET /prod/members` with a real Pool A token
> returns `{"error":"Forbidden"}`. ROOT CAUSE: the SAM edge authorizes in two independent
> steps — (1) CAPABILITY via `has_capability()` reading the token's `custom:entitlements`
> claim, then (2) SCOPE via the projected `scopegrant#`. Capability runs FIRST and FAILS:
> the Pool A token carries NO members entitlement, because the **Pre-Token-Generation (PTG)
> trigger is NOT attached to prod Pool A** (`eu-west-1_Hdp40eWmu`). The entitlement machinery
> (resolver/codec/Lambda/readers) is BUILT + tested (S4), and the trigger is LIVE on the
> **test** pool (`eu-west-1_xyrlzfqbl`, s5c Phase 5 done) — but the prod attach was deferred:
> S4 **T18** → S5 **Step 7** → **s5c task 7.5**, and s5c **Phase 7 was never executed**.
> The old fake path (`Members_CRUD` Cognito group + local-dev fallback) was deliberately
> REMOVED (s5c R6.4, 2026-09-19), so the honest result today is a 403. These are the s5c
> Phase-7 must-do tasks, re-homed here because s5d's rollout depends on them.
> Guardrails (steering 23): identity-account = `personal` 344561557829 (Pool A lives here);
> data-account = `nonprofit-deploy` 506221081911 (PTG Lambda + projection live here); the
> invoke crosses accounts, the data read does not. Test-pool-first, gated, detach-to-rollback.

- [x] **CE.1 [PREREQ] Verify the projection lets PTG resolve a NON-EMPTY entitlement** —
  DONE + VERIFIED 2026-09-23: **NO-OP, projection already sufficient (no widening needed).**
  Ran the EXACT PTG chain (`sam/pretokengen/handler.py`) against real prod data for
  `webmaster@h-dcn.nl` with `custom:tenants=["mytest3","h-dcn"]`:
  `ProjectionGovernanceReader.get_user_roles_by_tenant` → h-dcn `[Finance_CRUD, Members_CRUD,
  Tenant_Admin]`; `get_active_modules_by_tenant` → h-dcn `[FIN, MEMBERS, TENADMIN]`;
  `resolve_entitlement(...)` → h-dcn entitlement INCLUDES `members:admin/export/read/write`;
  `encode_entitlements(...)` → a valid `custom:entitlements` claim carrying them. So the
  roadmap's "widen the projection for ordinary Pool A tenants" caveat is ALREADY satisfied for
  h-dcn — the `module#MEMBERS` + `role#…#Members_CRUD` rows resolve a full members entitlement.
  ⇒ The ONLY things between now and members-visible are CE.2 (attach trigger) + CE.3 (SPA URL).
  Read-only; no prod change.
> **BLAST-RADIUS ASSESSMENT (RCA 2026-09-23, corroborated by code + tests).** Attaching the
> PTG trigger to Pool A is SAFE-BY-DESIGN for existing **FIN/ZZP/STR** (Flask-plane) users,
> with ONE genuine risk to gate on. Evidence:
> - **Additive** — `_stamp_claim_v2` writes ONLY `custom:entitlements`, never touches
>   `cognito:groups`/`custom:tenants` (test `test_existing_claims_are_untouched`).
> - **Flask ignores the claim** — `cognito_utils` authorizes from `cognito:groups` + MySQL
>   `role_cache`; nothing on the FIN/ZZP/STR path reads `custom:entitlements` (the optional
>   `entitlement_reader` is adopted by NO route and is itself fail-safe). So the new claim is
>   invisible/harmless to them.
> - **Size-bounded** — codec caps at 3 KiB, emits an overflow SIGNAL (never truncates); a
>   FIN/ZZP/STR token is a few hundred bytes → no oversized-token login break.
> - **Runtime fail-safe** — a projection/resolver/codec failure at issuance OMITS the claim
>   and returns a valid event → login still succeeds (fail-safe tests).
> - **Detach-reversible** — removing the trigger restores the exact prior token shape (s5c 5.6).
> - **THE ONE RISK:** the fail-FAST path — if the Lambda is MISCONFIGURED (missing/blank
>   `GOVERNANCE_PROJECTION_TABLE`/`AWS_REGION`, or wrong cross-account wiring so the projection
>   table can't resolve), it raises `DynamoDBConfigError`, which PROPAGATES → Cognito fails
>   token issuance for **EVERY Pool A login (FIN/ZZP/STR included)**. This is a deploy-time
>   misconfig, fully preventable by the CE.3 pre-attach smoke test below.

- [x] **CE.2 Deploy the frontend Members-API-URL fix** — DONE 2026-09-23. PR #16 merged to
  `main` (merge `6e03681`); frontend Pages + Flask/Railway + SAM deploys all SUCCEEDED.
  VERIFIED on the live Pages bundle: `MembersPage-CcNJ61oy.js` now contains ONLY
  `https://22x6z55301.execute-api.eu-west-1.amazonaws.com/prod` (the `127.0.0.1:3000` fallback
  is gone). SPA now targets the real Members API. (Members still 0 until CE.5 — capability —
  but now for the RIGHT reason: a 403 at the edge, not a localhost miss.) Original note:
  Deploy the frontend Members-API-URL fix (independent, do EARLY, low risk). The
  GitHub Pages build had NO `VITE_MEMBERS_API_BASE_URL`, so the deployed SPA fell back to the
  committed dev default `http://127.0.0.1:3000` (confirmed baked into
  `frontend/build/assets/MembersPage-*.js`) → member requests hit localhost → "Geen leden
  gevonden" regardless of auth. FIX (in working tree): added
  `VITE_MEMBERS_API_BASE_URL=https://22x6z55301.execute-api.eu-west-1.amazonaws.com/prod`
  (the `sam-members` stack `MembersApiBaseUrl` output) to `.github/workflows/deploy-frontend.yml`.
  DO: commit + merge to `main` → Pages redeploys → confirm the new bundle contains the
  execute-api URL (not 127.0.0.1). Independent of the trigger work; safe to land first. (After
  this, the SPA will still show 0 members until CE.4 — capability — but for the RIGHT reason.)
- [x] **CE.3 [PRE-ATTACH SMOKE] Invoke the deployed PTG Lambda; confirm valid event, no raise**
  — DONE + PASSED 2026-09-23. Invoked the deployed `pretokengen-test` Lambda (data account
  506221081911; its `GOVERNANCE_PROJECTION_TABLE=governance_projection` = the SAME prod table,
  identical handler code to the future prod-stage fn) with a representative Cognito V2 event for
  `webmaster@h-dcn.nl` (`custom:tenants=["mytest3","h-dcn"]`). Result: **StatusCode 200, NO
  FunctionError** (Lambda did NOT raise → the fail-fast config path is NOT a risk), and the
  returned event stamps `custom:entitlements` on BOTH id+access generations with h-dcn
  `members:admin/export/read/write` (+ FIN/TENADMIN caps), `v:1`, additive. This proves code +
  prod projection data + account config are healthy end-to-end.
  ⚠️ **CE.3 SURFACED A GAP → new CE.4a below.** Only `pretokengen-test` (stage `test`, from s5c
  Phase 5) is deployed; there is **NO `pretokengen-prod`** function (stack `pretokengen-data`
  deployed only the test stage). CE.5 has nothing to attach until a prod-stage Lambda exists.
- [x] **CE.4a [H] Deploy the PROD-stage PreTokenGen Lambda** — DONE + VERIFIED 2026-09-23.
  `sam build` + `sam deploy` to a NEW stack **`pretokengen-prod`** (NOT re-parameterizing
  `pretokengen-data` — that would have replaced the test fn). Changeset reviewed BEFORE apply
  (`--no-execute-changeset`): **3 additive resources only** (PreTokenGenFunctionRole IAM::Role,
  PreTokenGenFunction Lambda, PreTokenGenLayer LayerVersion) — 0 Modify/Remove/Replacement,
  `pretokengen-test` untouched. Stack `CREATE_COMPLETE`. Outputs:
  - fn ARN `arn:aws:lambda:eu-west-1:506221081911:function:pretokengen-prod` (← CE.5 attach target)
  - layer `pretokengen-layer-prod:1`
  Params: Stage=prod, Region=eu-west-1, GovernanceProjectionTableName=governance_projection.
  SMOKE (CE.3 re-run on `pretokengen-prod`): StatusCode 200, NO FunctionError, stamps
  `custom:entitlements` with h-dcn `members:admin/export/read/write` on both generations. Prod fn
  healthy + ready. Deploy was MANUAL/inline (no samconfig) — see backlog "SAM deploys are ad-hoc".
  → RESOLVED by **s5e** (`.kiro/specs/multi-tenant/s5e-codify-sam-deploys/`): `sam/pretokengen`
  now has a committed `samconfig.toml` + OIDC CI workflow (`deploy-sam-pretokengen.yml`); the
  invoke permission is template-owned. Codified deploy runbook: **`sam/pretokengen/DEPLOY.md`**.
  Do NOT hand-type inline `sam deploy` params any more — use `--config-env prod`.
- [x] **CE.4 [H] Capture Pool A baseline + stage the one-command rollback** — DONE 2026-09-23.
  Verified identity = `personal` account 344561557829 (where Pool A `eu-west-1_Hdp40eWmu` lives;
  use the `personal` profile, NOT nonprofit-deploy). Captured baseline:
  **`UserPool.LambdaConfig = {}`** (Pool A has NO Lambda triggers currently — confirms the RCA;
  nothing to preserve). So rollback is trivial and exact — restore `LambdaConfig` to `{}`.
  STAGED ROLLBACK (one command, run under the `personal` profile — this is the CE.5 undo):
  ```bash
  env -u AWS_ACCESS_KEY_ID -u AWS_SECRET_ACCESS_KEY -u AWS_SESSION_TOKEN \
    aws cognito-idp update-user-pool --user-pool-id eu-west-1_Hdp40eWmu \
    --lambda-config '{}' --profile personal --region eu-west-1
  ```
  NOTE: Cognito's `update-user-pool` REPLACES the whole `LambdaConfig`, so the ATTACH (CE.5)
  must set the FULL desired config in one call, and the DETACH sets it back to `{}`. Baseline
  saved; s5c 5.6 already proved detach restores prior behaviour on the test pool.
- [x] **CE.5 [H][!] Attach the PTG trigger to PROD Pool A** — DONE + VERIFIED 2026-09-23.
  (1) Cross-account invoke permission added on `pretokengen-prod` (`lambda add-permission`,
  principal `cognito-idp.amazonaws.com`, source-arn Pool A `eu-west-1_Hdp40eWmu`) — mirrors the
  test-pool statement. (2) `update-user-pool --lambda-config` set
  `PreTokenGenerationConfig{LambdaVersion=V2_0, LambdaArn=…pretokengen-prod}` on Pool A
  (`personal` profile). Verified via describe: `LambdaConfig` now carries the V2 config.
  Trigger is LIVE — confirmed by a real login (see CE.6): `peter@pgeers.nl`'s fresh token
  carries `custom:entitlements` with h-dcn `members:admin/export/read/write`.
- [x] **CE.6 [H] Existing users NOT frustrated — PASS 2026-09-23.** `peter@pgeers.nl` (SysAdmin +
  FIN/STR groups) logged in successfully AFTER the attach; login works, app works. A separate
  FIN/STR-type user (`pjageers@gmail.com`) also **logs in successfully** — the "you need members
  roles / access refused" message it briefly showed is a FRONTEND page-authorization message
  (it landed on a Members view while `selectedTenant=h-dcn`), NOT a Cognito login failure:
  reopening the app URL opens a normal successful session. So the trigger did NOT break any
  login (additive claim + Flask ignores it, as designed). No rollback needed. (Follow-up, minor:
  the SPA phrases a per-page authz miss as "login refused" — confusing UX; backlog-worthy.)
- [~] **CE.7 [H] Verify members capability end-to-end** — ✅ **EDGE FIX SHIPPED 2026-09-23
  (s5f)** — was BLOCKED on a ROOT-CAUSED edge bug
  (2026-09-23). Token side ✅: post-attach tokens carry h-dcn `members:*` (decoded from both
  `peter@pgeers.nl` and `webmaster@h-dcn.nl`). BUT `GET /prod/members` still returns **403**.
  ROOT CAUSE (found, not guessed): the SAM edge `_establish_tenant_context`
  (`sam/members/handler/app.py`) derives the tenant SOLELY from the entitlement's `tenant_keys`
  and **requires exactly ONE** — `len(tenant_keys)==1` else `TenantResolutionError` (403). It
  deliberately IGNORES `X-Tenant`. Both real Pool A users are MULTI-tenant (peter has 7:
  GoodwinSolutions/PeterPrive/h-dcn/kimgeers/myAdmin/vandenheuvelhoveniers/…; webmaster has
  mytest3+h-dcn) → multi-key token → denied at the tenant step (a ~3.5ms early deny, before
  capability/scope; members-prod logs show START/END, no app error). The X-Tenant header the SPA
  sends is not trusted, so a multi-tenant user has NO way to select h-dcn.
  ⇒ This is a SAM-edge REGRESSION from the PROVEN Flask multi-tenant pattern (NOT an unsolved
  design). Flask (`backend/src/auth/tenant_context.py`, in prod for FIN/ZZP/STR) already does it
  right: `get_current_tenant` reads `X-Tenant`, then `validate_tenant_access` denies unless
  `requested_tenant IN user_tenants` (the verified `custom:tenants`). FIX = mirror that in the
  SAM edge: accept `X-Tenant` as a selector IFF it ∈ the verified entitlement `tenant_keys`
  (fall back to the single-tenant case; deny if selector absent or multi-tenant w/o selector).
  Verify-before-trust preserved. Own scoped task/PR + `sam/tests` — logged in backlog. The PTG
  trigger stays attached (harmless; existing logins fine per CE.6) until the edge fix ships.
  Members list stays empty until then.
  → **RESOLVED by spec `s5f-sam-edge-active-tenant` + ADR 0007 (PR #18 merged `75126c1`,
  Deploy SAM Members run 35931888652 success, `sam-members` UPDATE_COMPLETE 2026-09-23).** The
  edge now resolves the active tenant from `X-Tenant` validated ∈ verified `tenant_keys` (header
  selects, never grants; single-tenant back-compat; all denies 403; no fallback). Full
  `sam/tests` suite green incl. the multi-tenant 200/403 matrix; live API 401 on unauth
  (healthy). REMAINING (manual, needs a browser SPA login): confirm `peter@pgeers.nl` +
  `X-Tenant: h-dcn` shows h-dcn members — PHASE D can now proceed.
- [ ] **CE.8 Confirm the reconciliation backstop** is scheduled/runnable in prod (s5c 7.7).
- [ ] **CE.9 (recommended before/with CE.5) Fix the `role#`/`module#` projection reconcile gap**
  so stale governance rows can't inflate a resolved entitlement once the trigger is live — see
  `.kiro/specs/myBacklog/backlog.md` ("Projection sync does not reconcile obsolete role#…").
  C.12 cleaned the current stale rows manually; this closes the recurring hole.

===================================================================
## PHASE D — Verify end-to-end in prod (h-dcn)  [UNBLOCKED 2026-09-23 — s5f shipped]
===================================================================
> **UNBLOCKED 2026-09-23:** all PHASE CE prerequisites are now met — SPA API-URL fix (CE.2 ✅),
> Pool A PTG trigger attached (CE.5 ✅), and the multi-tenant edge bug that failed CE.7 is FIXED
> and deployed (**s5f** / ADR 0007 / PR #18, `sam-members` UPDATE_COMPLETE). D.1/D.3 (users see
> members) can now be exercised via the SPA. D.2/D.4 are already confirmable at the data layer
> (scopegrant rows present; roles/scope are separate tables).
- [ ] **D.1** As a Tenant-Admin: set a test member-user to `region:["Oost"]` → the
  member list shows only Oost members; `["*"]` shows all; clearing shows none.
- [ ] **D.2** Confirm the projected `scopegrant#…#region` row matches the grant.
- [ ] **D.3** Confirm an all-access user (`["*"]`) sees the full member list (verify the
  deployed SPA→SAM API path returns members for a wildcard user).
- [ ] **D.4** Sanity: capability (roles) and scope are independent — changing scope
  never changes roles.
- [ ] **D.5** Overlay dropdown enforcement (A.5): creating/editing a member rejects an
  off-list `motor_brand`; an address-only edit of a legacy member with a junk brand
  still saves.

===================================================================
## SEQUENCING NOTES / GOTCHAS
===================================================================
- **Cold-start order is CODE → PLATFORM → TENANT:** finish PHASE A (code) before the
  B.1 merge; stand up the generic platform (B) before ANY h-dcn onboarding (C). The
  merge auto-deploys frontend + Flask + SAM (the A.13 workflow) — so A must be done first.
- **Enable the MEMBERS module (C.1) FIRST in the tenant phase** — the `members.*`
  parameter namespace is gated to an active MEMBERS module, so C.3/C.4 are rejected
  until the `tenant_modules` row exists.
- **Config before data apply:** author the 10 regions (C.4) + `field_overlay` (C.3) +
  catalog (C.2) BEFORE the real backfill apply (C.7), so the importer canonicalizes
  member `region` to the correct vocabulary and `membership_type` refs resolve.
- **Never run `onboard-hdcn-local.py` (or any overwriting seed) against prod** — it
  clobbers `members.scope_dimensions` (it wiped the dev regions).
- **Migration runner may be blocked** by pre-existing failed migrations (dev proof) —
  have the direct-apply fallback ready for the `user_tenant_scope` migration (B.2).
- **Backups first (B.0 MySQL, C.5 DynamoDB)** before the migration and the data apply —
  both are the hard-to-reverse steps.
- **UI base URLs:** the SPA must point at the deployed Members API (B.4) and Flask API;
  a wrong/empty base is exactly what makes the member list look empty regardless of scope.
  See PHASE CE.3 — the deployed SPA was baked with the localhost fallback.
- **"Members sees no members" has THREE independent causes — check all three (RCA
  2026-09-23):** (1) CAPABILITY — the Pool A token carries no `custom:entitlements` because
  the PTG trigger isn't attached to prod Pool A (PHASE CE.1/CE.2); this 403s at the SAM edge
  BEFORE scope is evaluated. (2) SPA API URL — deployed SPA baked with `127.0.0.1:3000`
  (PHASE CE.3). (3) SCOPE projection — `scopegrant#` rows missing until a resync (fixed in
  C.10/C.11). A `["*"]` user seeing nothing rules OUT scope-filtering and points at (1) or
  (2). The earlier "just a frontend issue" note was INCOMPLETE — capability (1) is the
  primary blocker. NOTE: the SAM edge does NOT cache (fresh projection reader per request,
  `handler/app.py` R5) — so it is never a backend cache; suspect token/SPA-URL/projection.
- **Projection lag after offline authoring:** any MySQL governance/scope/config write made
  by an OFFLINE script (or SPA action whose `enqueue_sync` queue isn't drained by a running
  app) needs a MANUAL projection resync before the projection reflects it (the C.11
  technique: `get_default_trigger()._resolve_sync().sync_administration("h-dcn")` with the
  export-role-creds env). Bit us on C.8 (config) AND C.10 (scope grants).
- **AWS credential resolution for cross-plane scripts:** `.env` static keys beat
  `AWS_PROFILE` in boto3, so `AWS_PROFILE=nonprofit-deploy` alone silently hits the WRONG
  account. Use `eval "$(aws configure export-credentials --profile nonprofit-deploy --format
  env)"` + `unset AWS_PROFILE` (+ strip `AWS_ENDPOINT_URL_DYNAMODB`). See steering
  `41-shell-environment.md`.

## CONFIRMED INPUTS (resolved 2026-09-22)

- **Companion documents:** `scripts/aws/h-dcn/ONBOARDING.md` (authoritative field/enum/
  overlay model + ordered onboarding protocol; referenced by PHASE C, esp. C.2/C.3/C.4);
  `.kiro/specs/multi-tenant/s5c-members-runnable-in-spa/design.md` (the R4.10 field
  classification table ONBOARDING.md is built from).
- **Deploy branch:** `main` (merge `feature/sam-members` → `main`; Railway + SAM build from `main`).
- **Projection table (prod):** `governance_projection` (VERIFIED 2026-09-22 to exist in
  the `nonprofit-deploy` account, eu-west-1; env var `GOVERNANCE_PROJECTION_TABLE`).
- **Member import source:** `.agent-output/Ledenbestand.json` (1242 rows; column `Regio`).
- **Scope-dimension `values` (the region list):** the **10** DISTINCT `Regio` values in
  the import file (census 2026-09-22), with ONE spelling fix: `Groningen/Drente` →
  `Groningen/Drenthe` (the correct Dutch spelling). `scope_canon` does NOT fold
  `drente`↔`drenthe` (the `h` is a real letter), so the importer needs a `Drente`→
  `Drenthe` region alias for the 105 affected rows to normalize onto the canonical
  `Groningen/Drenthe` (see A.3/C.4). `Geen` ("no region / Other") is a real value in the
  data (58 members) and is the canonical value — there is NO `Overig` in the import and
  NO `Overig` alias. VERIFIED: 1215 of 1242 members carry a regio; 27 are blank
  (→ unscoped, visible only to `["*"]`). Separator/case spelling is COSMETIC —
  `scope_canon` folds space/`-`/`/`, so `Noord Holland`/`Noord-Holland` compare equal.

  Census (value → count): Friesland 211, Oost 167, Noord Holland 153,
  Brabant/Zeeland 121, Zuid Holland 111, Groningen/Drente 105 (→ Drenthe), Utrecht 105,
  Limburg 93, Duitsland 91, Geen 58, blank 27.

  The exact `members.scope_dimensions` to author in C.4:

  ```json
  [{
    "key": "region",
    "field": "region",
    "label": { "nl": "Regio", "en": "Region" },
    "enabled": true,
    "values": [
      "Friesland", "Oost", "Noord Holland", "Brabant/Zeeland", "Zuid Holland",
      "Utrecht", "Groningen/Drenthe", "Limburg", "Duitsland", "Geen"
    ],
    "required_for": ["Members_CRUD"]
  }]
  ```

  NOTE: exactly **10** values; `Geen` is the canonical "no region / Other" value (no
  `Overig`). This is the set derived from the REAL data — NOT the pilot placeholder
  Noord/Zuid/Oost/West. Author these EXACT strings, AND ensure the importer carries the
  `Drente`→`Drenthe` region alias (A.3 — a code change to `sam/members/migration/hdcn_backfill.py`,
  mirroring `MembershipTypeMapper.DEFAULT_ALIASES`) so the 105 `Groningen/Drente` rows
  land on `Groningen/Drenthe` — otherwise C.8 (R9.5) will flag them as offenders.
