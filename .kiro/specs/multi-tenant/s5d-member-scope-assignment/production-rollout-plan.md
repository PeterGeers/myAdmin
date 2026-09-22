# s5d — Production rollout action plan (h-dcn pilot)

Goal: bring the s5d member-user scope feature live in the **pilot/production**
environment, in three phases:

1. **Deploy the code** — UI (SPA), Flask/MySQL (Railway), and the SAM Members
   module (AWS `nonprofit-deploy`).
2. **Import the member data** into prod.
3. **Create the config** — the `members.scope_dimensions` (the 10 official
   regions) and per-user `user_tenant_scope` grants.

Environments (steering 23-aws-accounts):
- **Flask + MySQL** → Railway (system of record for tenant/governance data).
- **DynamoDB (sam-members, governance projection) + Lambda + API GW** → AWS
  account `nonprofit-deploy` (506221081911), region `eu-west-1`.
- **Cognito** → the h-dcn pool `eu-west-1_fcUkvwjH5` (nonprofit H-DCN), identity
  account. (Prod SPA users log in here; the SAM API uses a Cognito authorizer.)

Guardrails (steering 23): DynamoDB tables + Cognito pools are managed OUTSIDE
CloudFormation / retained; never `--delete`/`rm -r` a data bucket; back up before
any data move; PAY_PER_REQUEST; `sam-` table prefix stays at the front; critical
env vars fail-fast.

Legend: `[ ]` todo · `[H]` human/credentials required · `[!]` destructive-or-
irreversible — confirm first · `[BACKUP]` take a backup before this step.

===================================================================
## PHASE 0 — Pre-flight (do BEFORE touching prod)
===================================================================
- [ ] **0.1 Merge/PR `feature/sam-members` → the deployed branch.** All s5d code
  (incl. the two-modal UI fix) is on `feature/sam-members`. Open a PR, review, and
  merge to whatever branch Railway + the SAM deploy build from (confirm which).
- [ ] **0.2 [BACKUP] Back up prod MySQL** (Railway) — at least the `parameters`,
  `user_tenant_roles`, `tenants`, `tenant_modules` tables (a full dump is better).
  s5d adds `user_tenant_scope` and reads `members.scope_dimensions`; a backup lets
  us roll back config/schema.
- [ ] **0.3 [BACKUP] Back up the prod DynamoDB tables** (`sam-members`,
  `governance_projection`) — on-demand PITR or an export to S3. Required before the
  data import (Phase 2).
- [ ] **0.4 Confirm the 10 official regions (authoritative list).** Gather the
  exact canonical spellings + nl/en labels for h-dcn's regions (the set that was in
  `members.scope_dimensions` before — e.g. Noord-Holland, Zuid-Holland, Friesland,
  Utrecht, Oost, Limburg, Groningen/Drenthe, Brabant/Zeeland, Duitsland, Overig).
  This is the vocabulary BOTH the member `region` field AND the scope grants must
  use (R9 — exact canonical match). Do NOT let the pilot 4-value placeholder
  (Noord/Zuid/Oost/West) reach prod.
- [ ] **0.5 Fix the config-clobber hazard.** `scripts/local/onboard-hdcn-local.py`
  OVERWRITES `members.scope_dimensions` unconditionally (it wiped the 10 regions in
  dev). Do NOT run any onboarding/seed fixture against prod. If a seed is needed,
  make it seed-only-if-absent first.
- [ ] **0.6 Verify prod env vars exist (fail-fast):** on Railway (Flask) and in the
  SAM deploy params — `MEMBERS_TABLE=sam-members`, `GOVERNANCE_PROJECTION_TABLE=<prod>`,
  `AWS_REGION=eu-west-1`, Cognito pool config for `eu-west-1_fcUkvwjH5`. Prod leaves
  `AWS_ENDPOINT_URL_DYNAMODB` UNSET (→ real AWS).

===================================================================
## PHASE 1 — Deploy the code (UI + Flask + AWS)
===================================================================
Order matters: **backend contracts first (Flask + SAM), UI last**, so the SPA never
calls an endpoint that isn't deployed.

### 1A. Flask/MySQL (Railway)
- [ ] **1A.1 [H] Apply the `user_tenant_scope` migration to prod MySQL.** Migrations
  are NOT auto-applied (steering 31):
  `cd backend && PYTHONPATH=src python -c "from database_migrations import DatabaseMigration; DatabaseMigration(test_mode=False).run_all_migrations()"`
  KNOWN HAZARD (seen in dev): the batch runner ABORTS on a pre-existing failed
  migration. Check prod's `database_migrations` for `status='failed'` rows FIRST
  (e.g. `add_jabaki_enabled_to_tenant_slugs`, `add_performance_indexes`). If the
  batch won't reach `create_user_tenant_scope_table`, apply that ONE migration's
  `up` DDL directly (a single `CREATE TABLE`) and record a `success` tracking row —
  do NOT edit unrelated failed migrations. Verify the table exists (keyed
  `(email, administration, module)`, FK to `tenants`, `idx_administration`).
- [ ] **1A.2 [H] Deploy the Flask backend** (the Railway deploy of the merged
  branch). This ships: `user_tenant_scope_service.py`, the scope routes
  (`tenant_admin_scope.py`: GET/PUT scope, GET scope-dimensions, POST resync),
  the rewritten `projection_sync.py` (sources scopegrant from `user_tenant_scope`;
  role-decode removed; version-bump + diff-delete freshness fixes),
  `scope_canon.py`, and the app.py blueprint registration.
- [ ] **1A.3 Smoke-check the Flask deploy:** health endpoint 200; the new routes
  respond (401 unauthenticated is correct). No startup errors in logs.

### 1B. SAM Members module (AWS nonprofit-deploy)
- [ ] **1B.1 [H] `sam build`** from `sam/members`: `cd sam/members && sam build`
  (needs sam, rsync, python on PATH; vendors sam/shared + sam/members into the layer).
- [ ] **1B.2 [H] `sam deploy` to prod** (`--profile nonprofit-deploy --region eu-west-1`),
  Stage=prod, supplying the fail-fast params (NO defaults):
  `MembersTableName=sam-members`, `GovernanceProjectionTableName=<prod projection>`,
  `Region=eu-west-1`, `CognitoUserPoolArn=<arn of eu-west-1_fcUkvwjH5>`. Leave the
  local-only params (DynamoDbEndpointUrl, CognitoPoolKeys, etc.) empty in prod.
  This ships the s5d domain changes: `_record_scope_values` reads the member field,
  `_in_scope` per-dimension AND, `scope_dimensions` model (field, no multi_valued),
  the reader, `scope_canon`.
- [ ] **1B.3 Confirm** the `sam-members` + governance projection tables are the
  managed-outside-CFN prod tables (template does NOT create them — RetentionPolicy).
  A deploy must never recreate/replace them.
- [ ] **1B.4 Note the MembersApi base URL** output — the SPA needs it.

### 1C. Frontend SPA
- [ ] **1C.1 [H] Build + deploy the SPA** with the correct prod API bases (the
  Members API base from 1B.4, the Flask API base). Ships: the scope API client +
  types (`tenantAdminApi.ts`, `members.ts`), the two-modal user surface
  (`UserInviteModal.tsx` "Rollen bewerken" / "Scope bewerken"), `UserScopeEditor.tsx`,
  `scopeFuzzyFilter.ts`, the nl/en locale keys.
- [ ] **1C.2 Smoke-check:** log in as a Tenant-Admin (Cognito `eu-west-1_fcUkvwjH5`),
  open a user → the two modals render and conform (scroll, single Save).

===================================================================
## PHASE 2 — Import the member data into prod
===================================================================
- [ ] **2.1 [H] Confirm the member source** (the h-dcn Ledenbestand export — CSV/JSON
  from the Google Sheet) and the `--tenant h-dcn` target.
- [ ] **2.2 DRY-RUN the backfill (writes nothing):**
  `MEMBERS_TABLE=sam-members AWS_REGION=eu-west-1 AWS_PROFILE=nonprofit-deploy \
     backend/.venv/bin/python scripts/aws/backfill-hdcn-members.py --source <export> --tenant h-dcn`
  Review the fidelity report: field mapping, rows-missing-region, duplicate member
  numbers, and that `region` lands on the NORMAL field (`overlay.region`) as a
  CANONICAL value (s5d — NOT the retired `scope_values` bucket).
  CRITICAL: the importer normalizes `region` via `scope_canon` against the dimension's
  canonical value set. If Phase 3 config (the 10 regions) isn't in place yet, the
  canonical set won't match — so SEQUENCE: do 3.1 (author the 10 regions) BEFORE the
  real apply, so the importer canonicalizes to the right vocabulary.
- [ ] **2.3 [!][H] APPLY the backfill** (`--apply`) only after a clean dry-run AND a
  DynamoDB backup (0.3). Per-tenant member-number uniqueness is enforced (conflicts
  reported, never overwritten). This writes to `sam-members` (prod) only.
- [ ] **2.4 Data-shape check:** confirm imported members carry `overlay.region`
  (scalar, canonical) and NOT a `scope_values` bucket. (In dev, legacy members still
  had `scope_values` — a fresh s5d import must not.)

===================================================================
## PHASE 3 — Create the config / scope items
===================================================================
- [ ] **3.1 [H] Author `members.scope_dimensions` with the 10 official regions.**
  Via the Tenant-Admin members-config UI (preferred — authoritative, audited) or a
  targeted `ParameterService.set_param("tenant","h-dcn","members","scope_dimensions", [...])`.
  Shape: `[{"key":"region","field":"region","label":{"nl":"Regio","en":"Region"},
  "enabled":true,"values":[<the 10 canonical regions>],"required_for":["Members_CRUD"]}]`.
  NO `multi_valued`, NO `all_wildcard`/`Regio_*` (s5d clean break). This fires
  `enqueue_sync` → projects `config#scope`.
- [ ] **3.2 Run the R9.5 normalization verification (read-only)** against prod:
  `MEMBERS_TABLE=sam-members GOVERNANCE_PROJECTION_TABLE=<prod> AWS_REGION=eu-west-1 \
     AWS_PROFILE=nonprofit-deploy backend/.venv/bin/python \
     scripts/aws/verify-member-scope-normalization.py --tenant h-dcn --dimension region`
  Expect PASS (every distinct member region ∈ the 10 canonical values). Any offender
  = a member whose region won't match a grant → fix before granting scope.
- [ ] **3.3 [H] Author per-user scope grants** via the SPA "Scope bewerken" modal (or
  `PUT /api/tenant-admin/users/<user>/scope/members`). Each write fires enqueue_sync →
  `scopegrant#<email>#region`. Use `["*"]` for all-access (national) users.
- [ ] **3.4 Remove legacy `Regio_*` role rows (optional cleanup).** s5d no longer
  decodes them, but they linger in `user_tenant_roles` (e.g. `Regio_All`). Removing
  them is cosmetic; do it as a separate, reviewed data cleanup (not required for
  function).
- [ ] **3.5 If projection looks stale, use "Re-sync now"** (`POST /api/tenant-admin/projection/resync`)
  or `ProjectionSync.sync_administration("h-dcn")` — a full diff-and-replace.

===================================================================
## PHASE 4 — Verify end-to-end in prod
===================================================================
- [ ] **4.1** As a Tenant-Admin: set a test member-user to `region:["Oost"]` → the
  member list shows only Oost members; `["*"]` shows all; clearing shows none.
- [ ] **4.2** Confirm the projected `scopegrant#…#region` row matches the grant.
- [ ] **4.3** Confirm an all-access user (`["*"]`) sees the full member list (the dev
  symptom "webmaster sees nothing" was a FRONTEND/edge issue, NOT backend — verify
  the deployed SPA→SAM API path returns members for a wildcard user).
- [ ] **4.4** Sanity: capability (roles) and scope are independent — changing scope
  never changes roles.

===================================================================
## SEQUENCING NOTES / GOTCHAS
===================================================================
- **Config before data apply:** author the 10 regions (3.1) BEFORE the real backfill
  apply (2.3), so the importer canonicalizes member `region` to the correct vocabulary
  (R9). Otherwise re-normalize afterwards.
- **Never run `onboard-hdcn-local.py` (or any overwriting seed) against prod** — it
  clobbers `members.scope_dimensions` (it wiped the dev regions).
- **Migration runner may be blocked** by pre-existing failed migrations (dev proof) —
  have the direct-apply fallback ready for `create_user_tenant_scope_table`.
- **Backups first (0.2/0.3)** before the migration and the data apply — both are the
  hard-to-reverse steps.
- **UI base URLs:** the SPA must point at the deployed Members API (1B.4) and Flask
  API; a wrong/empty base is exactly what makes the member list look empty regardless
  of scope.
- **The "webmaster sees no members" dev symptom is a frontend/edge wiring issue, not
  data or scope** — verified: the backend returns 1163 members for a `["*"]` grant.
  Chase it in the deployed SPA→API path if it recurs, not in the scope logic.

## CONFIRMED INPUTS (resolved 2026-09-22)

- **Deploy branch:** `main` (merge `feature/sam-members` → `main`; Railway + SAM build from `main`).
- **Projection table (prod):** `config-projection` (confirm exact name at deploy;
  `GOVERNANCE_PROJECTION_TABLE`).
- **Member import source:** `.agent-output/Ledenbestand.json` (1242 rows; column `Regio`).
- **Scope-dimension `values` (the region list):** the DISTINCT `Regio` values in the
  import file **+ `Overig`** = **11 values**, using the exact data spellings so existing
  member data matches without re-normalization (R9). VERIFIED: all 1215 members with a
  regio map to one of these (27 blank → unscoped, visible only to `["*"]`). Canonical
  forms via `scope_canon` fold spacing/slashes (e.g. `Brabant/Zeeland`→`brabant zeeland`,
  `Groningen/Drente`→`groningen drente`), so the fuzzy picker tolerates spelling variants.

  The exact `members.scope_dimensions` to author in PHASE 3.1:

  ```json
  [{
    "key": "region",
    "field": "region",
    "label": { "nl": "Regio", "en": "Region" },
    "enabled": true,
    "values": [
      "Friesland", "Oost", "Noord Holland", "Brabant/Zeeland", "Zuid Holland",
      "Utrecht", "Groningen/Drente", "Limburg", "Duitsland", "Geen", "Overig"
    ],
    "required_for": ["Members_CRUD"]
  }]
  ```

  NOTE: `Geen` ("no region") and `Overig` ("other") are kept as selectable values.
  This is the value set derived from the REAL data — NOT the pilot placeholder
  Noord/Zuid/Oost/West, and NOT the illustrative doc list (which used different
  spellings like `Noord-Holland`/`Groningen/Drenthe`). Author these EXACT strings.
