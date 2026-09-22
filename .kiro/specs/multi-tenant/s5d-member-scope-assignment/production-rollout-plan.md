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
- [ ] **B.1 Merge/PR `feature/sam-members` → `main`.** After PHASE A is reviewed
  (INCLUDING A.13 — the SAM workflow must be in the PR). On merge, THREE deploys fire
  automatically: FRONTEND (GitHub Pages, `.github/workflows/deploy-frontend.yml`), FLASK
  (Railway GitHub integration builds + deploys on push to `main`), and SAM
  (`.github/workflows/deploy-sam-members.yml`, added in A.13). See CONFIRMED INPUTS
  (deploy branch `main`). NOTE: the SAM deploy needs the A.13 OIDC-trust prerequisite in
  place, else its job fails at assume-role (frontend + Flask still deploy).
- [ ] **B.2 [H] Apply the `user_tenant_scope` migration to prod MySQL** (the ONE new
  table; migrations are NOT auto-applied — steering 31):
  `cd backend && PYTHONPATH=src python -c "from database_migrations import DatabaseMigration; DatabaseMigration(test_mode=False).run_all_migrations()"`
  KNOWN HAZARD (dev): the batch runner ABORTS on a pre-existing failed migration.
  Check prod's `database_migrations` for `status='failed'` rows FIRST. If the batch
  won't reach the `user_tenant_scope` migration, apply that ONE migration's `up` DDL
  directly and record a `success` tracking row — do NOT edit unrelated failed
  migrations. Verify the table (keyed `(email, administration, module)`, FK to
  `tenants`, `idx_administration`).
- [ ] **B.3 [H] Create the prod `sam-members` table** (does NOT exist yet; the SAM
  template does NOT create it — managed-outside-CFN / Retain). Key shape `tenant_id`
  (S, HASH) + `sk` (S, RANGE), PAY_PER_REQUEST, no GSIs (from
  `sam/members/repository/table_design.py`):
  `MEMBERS_TABLE=sam-members AWS_REGION=eu-west-1 AWS_PROFILE=nonprofit-deploy \`
  `  backend/.venv/bin/python scripts/aws/provision-members-tables.py --apply`
  (dry-run is the default — run WITHOUT `--apply` first). Idempotent; refuses `--reset`
  against real AWS. `governance_projection` already exists — do NOT recreate it. NOTE:
  the SAM deploy (B.1, via the A.13 workflow) can happen before or after this, but the
  Lambda cannot serve requests until the table exists.
- [ ] **B.4 Confirm the SAM deploy** — the stack is up, `sam-members` +
  `governance_projection` are the managed-outside-CFN prod tables (a deploy never
  recreates/replaces them), and NOTE the `MembersApi` base URL output (the SPA needs it).
- [ ] **B.5 Smoke-check the platform (no tenant data yet):** Flask health 200 + new
  scope routes respond (401 unauthenticated is correct); the SAM `MembersApi` responds
  (401 without a token); SPA loads with the correct API bases. A member list is
  expected EMPTY at this point — no tenant is onboarded yet.

===================================================================
## PHASE C — Onboard tenant h-dcn (config → data → scope)
===================================================================
Nothing here touches other tenants. Cold start: h-dcn has no MEMBERS module row, no
`members.*` params, no members, no grants yet.
- [ ] **C.1 [H] Enable the MEMBERS module for h-dcn** (`tenant_modules`) — PREREQUISITE
  for everything below: the `members.*` parameter namespace is GATED to an active
  MEMBERS module (`parameter_schema.py`: `members` → `module: MEMBERS`). Until h-dcn has
  the active MEMBERS module row, `ParameterService.set_param("tenant","h-dcn","members",…)`
  (C.3/C.4) is rejected. Add the `tenant_modules` row for `administration='h-dcn'`,
  module `MEMBERS`, active.
- [ ] **C.2 [H] Seed the Lidmaatschap Beheer membership-type catalog** (BEFORE the
  backfill so `membership_type` refs resolve). Dry-run-first, idempotent upsert:
  `MEMBERS_TABLE=sam-members AWS_REGION=eu-west-1 AWS_PROFILE=nonprofit-deploy \`
  `  backend/.venv/bin/python scripts/aws/seed-hdcn-catalog.py --tenant h-dcn`
  (then re-run with `--apply`). Seeds gewoon_lid / gezins_lid / erelid / donateur /
  gezins_donateur / sponsor (+ `overig` once A.4 lands), all `active=True`.
- [ ] **C.3+C.4 [H] Author the member CONFIG (`field_overlay` + `scope_dimensions`)** —
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
- [ ] **C.5 [BACKUP] Back up the DynamoDB projection + members** before the data write:
  `governance_projection` (has data) and `sam-members` (empty until now) — on-demand
  PITR or S3 export.
- [ ] **C.6 [H] DRY-RUN the member backfill (writes nothing):**
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
- [ ] **C.7 [!][H] APPLY the backfill** (`--apply` + the same `--members-config`) only
  after a clean dry-run AND C.5. Per-tenant member-number uniqueness enforced (conflicts
  reported, never overwritten). Writes to `sam-members` (prod) only.
- [ ] **C.8 Run the R9.5 normalization verification (read-only):**
  `MEMBERS_TABLE=sam-members GOVERNANCE_PROJECTION_TABLE=governance_projection AWS_REGION=eu-west-1 \`
  `  AWS_PROFILE=nonprofit-deploy backend/.venv/bin/python \`
  `  scripts/aws/verify-member-scope-normalization.py --tenant h-dcn --dimension region`
  Expect PASS (every distinct member region ∈ the 10). Any offender = fix before granting scope.
  Exit codes (A.11 / D16 — NO fallback to a hardcoded tenant model): `0` PASS, `2` tenant
  not onboarded (no scope config), `4` SYSTEM ERROR (`ProjectionUnavailableError` — the
  projection read failed; investigate, do NOT proceed).
- [ ] **C.9 [H] Seed / confirm user ROLES** in `user_tenant_roles` (a Tenant_Admin to
  author scope; member-users with `Members_CRUD` — the `required_for` gate). Roles are
  INDEPENDENT of scope; a grant without the capability is inert.
- [ ] **C.10 [H] Author per-user scope grants** (`user_tenant_scope`, or the SPA "Scope
  bewerken" modal / `PUT /api/tenant-admin/users/<user>/scope/members`). `["*"]` =
  all-access. Fires `enqueue_sync` → `scopegrant#<email>#region`.
- [ ] **C.11 If projection looks stale, "Re-sync now"** (`POST /api/tenant-admin/projection/resync`
  or `ProjectionSync.sync_administration("h-dcn")`).
- [ ] **C.12 Remove legacy `Regio_*` role rows (optional cleanup)** — cosmetic; s5d no
  longer decodes them. Separate reviewed data cleanup, not required for function.

===================================================================
## PHASE D — Verify end-to-end in prod (h-dcn)
===================================================================
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
- **The "webmaster sees no members" dev symptom is a frontend/edge wiring issue, not
  data or scope** — verified: the backend returns members for a `["*"]` grant. Chase it
  in the deployed SPA→API path if it recurs, not in the scope logic.

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
