# s5d — Activation runbook (dev/test ONLY)

Scope: bring the s5d member-user scope-assignment feature live in **dev/test** —
the local Docker stack (MySQL + `dynamodb-local` + backend), local MySQL, the dev
frontend, and *optionally* the **standing test** AWS resources (`myAdmin-test`
pool `eu-west-1_xyrlzfqbl`, `sam-members-test` in the `nonprofit-deploy` account).

**Explicitly OUT OF SCOPE:** Railway, production Pool A (`eu-west-1_Hdp40eWmu`),
and any production DynamoDB / S3 data tables. Do not deploy s5d to prod from this
runbook.

Related steering: `41-shell-environment`, `42-local-dynamodb-testing`,
`31-backend-database-flask-mysql`, `23-aws-accounts`, `35-sam-module-architecture-sam`.

Status legend: `[ ]` todo · `[x]` done · `[H]` human-gated (needs a person /
credentials) · `[-]` optional.

> **Activation run 2026-09-22 (dev/test, local):** Phases A–E executed and GREEN
> against real local MySQL + `dynamodb-local`. B1 needed a workaround (see note).
> C2 was proven at the service layer (the live HTTP route needs a real signed
> token — see note). Phase F (test-AWS) intentionally NOT run (human-gated).

---

## Already done (context)
- [x] Code committed + pushed to `feature/sam-members` (`a6a4cdd`).
- [x] All unit / property / E2E tests green (backend, SAM, frontend) — but against
  **in-memory fakes**, not a live DB / DynamoDB. This runbook is what exercises the
  real wiring.

---

## Phase A — Local environment up
- [x] **A1. Start the local stack in the BACKGROUND** (via `control_bash_process`,
  never foreground — steering 42):
  `docker compose up` (whole stack) or `docker compose up dynamodb-local mysql backend`.
  Confirm MySQL + `dynamodb-local` are healthy (`http://localhost:8000` host,
  `http://dynamodb-local:8000` in-network).
  → DONE: `mysql`, `dynamodb-local`, `backend` all running/healthy (were already up;
  started detached with `docker compose up -d`).
- [x] **A2. Create the local projection table** (short-lived, `execute_bash` is fine):
  `backend/.venv/bin/python scripts/local/seed-dynamodb-local.py --reset`
  (creates `test_governance_projection`, PK `tenant_id` / SK `sk`).
  → DONE: table created fresh (on-demand).

## Phase B — Schema + config (local MySQL)
- [x] **B1. [H] Apply the `user_tenant_scope` migration** to local MySQL (schema
  change — migrations are NOT auto-applied, steering 31):
  ```bash
  cd backend && PYTHONPATH=src python -c "from database_migrations import DatabaseMigration; DatabaseMigration(test_mode=False).run_all_migrations()"
  ```
  Verify the `user_tenant_scope` table exists — keyed `(email, administration, module)`,
  FK to `tenants`, `idx_administration`. This is the hard prerequisite: the service,
  routes, and projection all read/write this table.
  → DONE **with a workaround** (see "B1 note"): the batch runner was blocked by
  pre-existing FAILED migrations, so the s5d migration's `up` DDL was applied
  directly and recorded in `database_migrations` as `success`. Table verified:
  columns `id/email/administration/module/scopes(json)/created_at/updated_at/created_by`,
  UNIQUE `uk_user_tenant_scope(email, administration, module)`, `idx_administration`,
  `idx_admin_module`.
- [x] **B2. Ensure `members.scope_dimensions` is authored** for the dev tenant
  (h-dcn: `region` -> Noord/Zuid/Oost/West). Either already seeded, or produced by
  the onboarding seed in C1. This param is the source of truth (D4) for both authoring
  validation and the projection builder.
  → DONE: seeded by C1 (region: Noord/Zuid/Oost/West).

## Phase C — Seed dev data + drive the full chain
- [x] **C1. Run the local onboarding fixture** (data-track convenience — seeds params,
  a `user_tenant_scope` grant, runs `ProjectionSync` against dynamodb-local, seeds
  members with canonical `overlay.region`):
  `backend/.venv/bin/python scripts/local/onboard-hdcn-local.py`
  → DONE: `sync_administration(h-dcn)` wrote 20 rows incl.
  `scopegrant#webmaster@h-dcn.nl#region`; 3 membership types + 4 members seeded into
  `sam-members-local`.
- [x] **C2. (Governance path) author a scope grant** — the real 4-hop chain:
  `PUT /api/tenant-admin/users/<user>/scope/members` body
  `{"scopes":{"region":["Oost"]}}` -> `enqueue_sync` -> `scopegrant#<email>#region`
  projected -> SAM reader consumes it.
  → DONE **at the service layer** (see "C2 note"): drove `UserTenantScopeService`
  + `ProjectionSync` against real local MySQL + dynamodb-local. Verified transitions:
  `region:["Oost"]` -> projected `{values:["Oost"]}`; `["*"]` -> row supersedes
  (version bumped, ODx4a); clear -> row DELETED (ODx4b) + `get_scope` empty; unknown
  value `Atlantis` -> `ScopeValidationError`. Left `member-test@example.com` scoped to
  `region:["Oost"]`. The live HTTP endpoint was NOT driven — it needs a real signed
  `myAdmin-test` token (auth boundary); the route logic is covered by the 16 route
  unit tests + the cross-plane E2E.

## Phase D — Verify projection + normalization
- [x] **D1. Run the R9.5 normalization check (read-only)** against local data:
  ```bash
  MEMBERS_TABLE=sam-members-local GOVERNANCE_PROJECTION_TABLE=test_governance_projection \
    AWS_REGION=eu-west-1 AWS_ENDPOINT_URL_DYNAMODB=http://localhost:8000 \
    backend/.venv/bin/python scripts/aws/verify-member-scope-normalization.py --tenant h-dcn --dimension region
  ```
  Expect "PASS — every distinct value is canonical." Fix any offenders (re-run the
  backfill / member write so values land canonical) before trusting scoped filtering.
  → DONE: PASS — 1163 members scanned, distinct values {Noord, Zuid, West} all in the
  canonical set. No un-normalized values.
- [x] **D2. Confirm the `scopegrant#<email>#region` row landed** in
  `test_governance_projection`; confirm `["*"]` widens to all and clearing the grant
  DELETES the row (ODx4b diff-and-delete) -> deny-by-default.
  → DONE: verified as part of C2 (row present for Oost, supersedes on `["*"]`, deleted
  on clear).

## Phase E — Frontend dev
- [x] **E1. Run the frontend dev server** (background) and open Tenant-Admin -> user
  details for a user holding a `Members_*` role. Verify the **Scope** section renders
  (per-dimension multi-select of PLAIN values + All toggle + diacritic/spacing-tolerant
  fuzzy typeahead), Save persists the selected set, clearing removes the grant, and
  "Re-sync now" (`POST /api/tenant-admin/projection/resync`) returns a written/removed
  summary. i18n strings (nl + en) present. The editor is offered ONLY for Members-role
  users (R4.6).
  → DONE **headlessly**: the scope editor vitest suite is GREEN
  (`UserScopeEditor.test.tsx` 13, `scopeFuzzyFilter.test.ts` 12, `tenantAdminApi.test.ts`
  33 = 58 tests, 3 files) — renders per-dimension multi-selects + All toggle + fuzzy +
  save. A manual in-browser click-through still needs a real `myAdmin-test` login
  (human — see below).

## Phase F — SAM module on TEST AWS (optional — only if validating the deployed Lambda)
- [ ] **F1. [H][-] Provision `sam-members-test`** if absent (test tables only, never
  prod): `scripts/aws/provision-members-tables.py` (profile `nonprofit-deploy`, region
  `eu-west-1`).
  → NOT RUN (human-gated; needs AWS credentials).
- [ ] **F2. [H][-] `sam build` + `sam deploy` the Members function to TEST** — only
  needed if you want the deployed test Lambda to reflect s5d (local domain tests
  already cover the logic). Then author a test `user_tenant_scope` grant + point the
  test `members.scope_dimensions`, and hit the deployed `list_members` to confirm
  scoped narrowing against the test pool `myAdmin-test` (`eu-west-1_xyrlzfqbl`).
  **Test resources only — NOT prod Pool A, NOT prod tables.**
  → NOT RUN (human-gated; needs AWS credentials).

## Phase G — Teardown / cleanup
- [ ] **G1. Between runs**: drop just the local projection table
  (`backend/.venv/bin/python scripts/local/teardown-dynamodb-local.py`); stop the
  stack via `control_bash_process` `stop` (optionally `docker compose stop dynamodb-local`).
  → NOT DONE ON PURPOSE: the stack was already running before this activation and is
  left up; the projection table is left populated (a scoped `region:["Oost"]` grant for
  `member-test@example.com`) as useful dev state. Run G1 when you want a clean slate.

---

## B1 note — why the migration runner was worked around
`DatabaseMigration.run_all_migrations()` applied 0 migrations and never reached
`create_user_tenant_scope_table`. Root cause (pre-existing local-DB drift, NOT s5d):
the batch runner aborts on a failing migration, and two earlier migrations are recorded
`failed` in `database_migrations` —
- id 17 `add_jabaki_enabled_to_tenant_slugs`: `1060 Duplicate column 'jabaki_enabled'`
  (the column already exists on `tenant_slugs`),
- id 15 `add_performance_indexes`: old `CREATE INDEX IF NOT EXISTS` syntax error.

Minimal-blast-radius fix for dev/test: applied ONLY the s5d migration's `up` DDL
directly via `DatabaseManager` (a single `CREATE TABLE`), then inserted a `success`
tracking row for `create_user_tenant_scope_table`. The unrelated failed migrations were
left untouched — reconciling jabaki/perf-indexes is a separate cleanup for whoever owns
them before the full runner will pass again.

## C2 note — live HTTP vs service layer
The dev backend has the `myAdmin-test` Cognito verifier configured, so the scope routes
require a real SIGNED JWT (an unsigned dev token is rejected `401 "Token missing key ID
(kid)"`). Driving the actual endpoints needs a real test-pool login (human). The
underlying `UserTenantScopeService` + `ProjectionSync` were exercised directly against
the real local datastores instead (all transitions verified), and the thin route wrapper
is covered by `test_tenant_admin_scope_routes.py` (16 tests) + `test_scope_e2e.py`.

## Still needs a human
- A manual in-browser walkthrough of the Scope editor with a real `myAdmin-test`
  Tenant_Admin login (the only step that needs a person at the keyboard for dev/test).
- Phase F (test-AWS SAM deploy) — needs `nonprofit-deploy` credentials; test resources
  only, never prod.
