# Implementation Plan: Common Test Environment

## Overview

This implementation plan converts the feature design for a proper TEST environment across every plane into actionable coding tasks. The plan follows the design's rollout sequence: start with the core resolver/guard, then frontend `APP_ENV` injection, then MySQL/backend-runtime plane, then SAM data plane, then SAM compute plane heavy build, then `test_mode` migration, then copy utility + account provisioning, then steering updates. Each phase keeps the app deployable and follows the "one PR per logical change" + "change-with-tests" contract.

The implementation involves:
- **Backend (Python)**: Environment resolver, consistency guard, `test_mode` migration, health report
- **Frontend (TypeScript)**: `APP_ENV` injection, environment indicator, API URL resolution  
- **SAM Infrastructure**: Stack-per-environment build with separate TEST stack, API Gateway, IAM roles
- **Operational Tooling**: Copy utility, test account provisioning

## Tasks

### Phase 0: Core resolver + definition + guard (no behavior change)

- [x] 1. Set up environment module structure and core types
  - [x] 1.1 Create `backend/src/environment/` directory with `__init__.py`
  - [x] 1.2 Implement `AppEnv` enum and `parse_app_env` function in `app_env.py`
  - [x] 1.3 Create `EnvironmentDefinition` dataclass in `environment_definition.py` with placeholders for all planes
  - [x] 1.4 Implement `ResolvedConfig` dataclass and `resolve()` function in `resolver.py`
  - [x] 1.5 Create frontend `src/config/appEnv.ts` and `environmentDefinition.ts` with TypeScript equivalents
  - [x] 1.6 Write property tests for APP_ENV parsing and resolution (Properties 1-4)
  - _Requirements: 1.1-1.3, 2.1-2.4, 3.1-3.6_

- [x] 2. Implement consistency guard (report-only mode)
  - [x] 2.1 Create `consistency_guard.py` with `ConsistencyReport` and `PlaneCheck` dataclasses
  - [x] 2.2 Implement guard logic to check Cognito identity, pool registry, identity block
  - [x] 2.3 Add guard startup hook that logs inconsistencies but doesn't block (report-only)
  - [x] 2.4 Create `check` CLI command in `backend/src/environment/check.py`
  - [x] 2.5 Write property tests for guard consistency logic (Properties 7-8)
  - _Requirements: 4.1-4.7, 7.5_

- [x] 3. Wire `APP_ENV`/`VITE_APP_ENV` with fail-fast
  - [x] 3.1 Update backend app bootstrap to read `APP_ENV` and call resolver
  - [x] 3.2 Add `VITE_APP_ENV` to frontend `.env.example` and TypeScript declarations
  - [x] 3.3 Configure Vite to inject `VITE_APP_ENV` at build time
  - [x] 3.4 Add fail-fast validation in frontend `appEnv.ts` module load
  - [x] 3.5 Update any existing startup checks to include environment validation
  - _Requirements: 1.3-1.5, 1.6, 2.1, 2.3_

- [x] 4. Checkpoint - Core infrastructure deployed
  - Ensure all tests pass, ask the user if questions arise.

### Phase 1: Identity + indicator + health report

- [x] 5. Update frontend Cognito pool selection
  - [x] 5.1 Modify `frontend/src/aws-exports.ts` to select pool from resolved `APP_ENV` instead of hostname
  - [x] 5.2 Remove `isLocal = window.location.hostname === 'localhost'` switch logic
  - [x] 5.3 Update frontend tests to mock resolved environment config
  - [x] 5.4 Write property test for resolution ignoring incidental signals (Property 3)
  - _Requirements: 1.4, 1.5, 2.3, 8.1-8.5_

- [x] 6. Update backend identity resolution
  - [x] 6.1 Modify `backend/src/auth/pool_registry.py` to accept resolved identity from resolver
  - [x] 6.2 Update `COGNITO_POOL_KEYS` loading to work with resolved config
  - [x] 6.3 Ensure identity block (`COGNITO_USER_POOL_ID`, `CLIENT_ID`) resolves from `APP_ENV`
  - [x] 6.4 Handle empty client secret for test pool (Req 7.3, 8.4)
  - [x] 6.5 Write property test for test environment consequences (Property 5)
  - _Requirements: 2.3, 7.2-7.3, 8.1-8.5_

- [x] 7. Implement environment indicator
  - [x] 7.1 Create frontend component showing "TEST"/"PROD" badge based on resolved `APP_ENV`
  - [x] 7.2 Add indicator to login screen and authenticated layout
  - [x] 7.3 Show active pool/identity label and SAM API endpoint where observable
  - [x] 7.4 Make TEST label visually distinct (different color/style)
  - _Requirements: 5.1-5.5_

- [x] 8. Implement backend health report endpoint
  - [x] 8.1 Create `GET /api/environment` endpoint returning active environment config
  - [x] 8.2 Include `APP_ENV`, pool labels, MySQL target label, DynamoDB prefix, SAM API URL
  - [x] 8.3 Omit secret values, return only non-secret labels/identifiers
  - [x] 8.4 Ensure health report derives values from resolver (cannot drift)
  - [x] 8.5 Write property test for health report non-drift and secret omission (Property 9)
  - _Requirements: 6.1-6.6_

- [x] 9. Flip guard to fail-fast mode
  - [x] 9.1 Update guard startup hook to raise `EnvironmentConfigError` on inconsistencies
  - [x] 9.2 Verify all existing inconsistencies are resolved (using report-only mode)
  - [x] 9.3 Update `check` command to exit non-zero on inconsistencies
  - [x] 9.4 Add guard checks for frontend-selected pool vs backend registry
  - _Requirements: 4.1-4.7_

- [x] 10. Checkpoint - Identity plane complete
  - Ensure all tests pass, ask the user if questions arise.

### Phase 2: Flask API base URL + MySQL target

- [x] 11. Replace hardcoded Flask API URLs
  - [x] 11.1 Audit all `localhost:5000` literals in `frontend/src/services/*.ts`
  - [x] 11.2 Create `RESOLVED.flaskApiBaseUrl` in frontend config
  - [x] 11.3 Update `authService`, `verificationApi`, `chartOfAccountsService`, `tenantAdminApi`
  - [x] 11.4 Update components like `ProfitLoss.tsx`, `PDFValidation.tsx`
  - [x] 11.5 Update `frontend/src/config.ts` to use resolved URL
  - _Requirements: 21.1-21.4_

- [x] 12. Update MySQL plane with resolved targets
  - [x] 12.1 Modify `DatabaseManager` to accept `ResolvedConfig.mysql` instead of `TEST_MODE`
  - [x] 12.2 Remove `TEST_DB_NAME`/`testfinance` switching logic
  - [x] 12.3 Ensure both environments use schema `finance` on their resolved target
  - [x] 12.4 Add guard check for MySQL target consistency
  - [x] 12.5 Write property test for TEST/PROD database target isolation (Property 11)
  - _Requirements: 9.1-9.6_

- [x] 13. Extend guard to Flask URL and MySQL target
  - [x] 13.1 Add guard check for Flask API base URL matching `APP_ENV`
  - [x] 13.2 Add guard check for MySQL resolved target consistency
  - [x] 13.3 Verify TEST target ≠ PRODUCTION target in identity and credentials
  - _Requirements: 4.4, 9.5, 21.5-21.6_

- [x] 14. Checkpoint - Backend runtime plane complete
  - Ensure all tests pass, ask the user if questions arise.

### Phase 3: `test_mode` removal (staged refactor)

- [x] 15. Neutralize `test_mode` selector (Step 1: shim)
  - [x] 15.1 Update `DatabaseManager.__init__` to ignore `test_mode` for environment selection
  - [x] 15.2 Add deprecation warning when `test_mode` is passed but ignored
  - [x] 15.3 Keep `test_mode` parameter signature for backward compatibility
  - [x] 15.4 Write property test for `test_mode` no longer selecting environment (Property 6)
  - _Requirements: 2.6_

- [x] 16. Collapse request-driven `test_mode` (Step 2)
  - [x] 16.1 Update `reporting_routes` to stop reading `testMode` from request args
  - [x] 16.2 Update `str_channel_routes` to stop defaulting `test_mode=True`
  - [x] 16.3 Update all other services reading `test_mode` from request or kwargs
  - [x] 16.4 Remove `mutaties_test`/`testfinance` table/schema switches
  - [x] 16.5 Update paired tests for each touched route (change-with-tests)
  - _Requirements: 1.6, 2.6_

- [x] 17. Remove `test_mode` parameter (Step 3)
  - [x] 17.1 Drop `test_mode` kwarg from `DatabaseManager` and all service constructors
  - [x] 17.2 Refactor test fixtures `test_environment`/`production_environment` to set `APP_ENV`
  - [x] 17.3 Update migration scripts to use `APP_ENV` instead of `TEST_MODE`
  - [x] 17.4 Clean up remaining `test_mode` references across codebase
  - _Requirements: 2.6_

- [x] 18. Checkpoint - `test_mode` migration complete
  - Ensure all tests pass, ask the user if questions arise.

### Phase 4: SAM test stack (heavy build)

> **Phase 4 reconciliation (agreed with user).** The SAM plane uses the existing
> per-module `Stage` parameter as the SINGLE environment knob (reused, not a parallel
> `Environment` param) and DERIVES `APP_ENV` from it via a `StageToAppEnv` mapping
> (`local`/`test` → `test`, `prod` → `production`). Stacks are PER-MODULE, not one
> monolith: members = `test_sam-members`/`sam-members`, pretokengen =
> `test_pretokengen`/`pretokengen-prod` (the design's `myAdmin-test`/`myAdmin-prod` were
> illustrative). TEST tables carry the `test_` prefix; NO DynamoDB table is shared across
> environments (TEST owns `test_governance_projection`). Live cross-prefix-DENY and
> authorizer accept/reject exercises require a real deploy (gated), so they are covered
> deploy-free by static template-contract tests; the live assertion happens at deploy time.

- [x] 19. Prepare SAM template for environment parameterization
  - [x] 19.1 `Stage` (the single env knob) AllowedValues extended to `[local, test, prod]`
  - [x] 19.2 `Stage` already flows into all resources (names, API stage, output URL)
  - [x] 19.3 Added `APP_ENV` env var to each Lambda via `!FindInMap [StageToAppEnv, Stage]`
  - [x] 19.4 Table names are per-env params; members pattern widened to accept `test_` prefix
  - _Requirements: 11.1-11.3_
  - _Done: sam/members/template.yaml + sam/pretokengen/template.yaml; sam validate --lint passes._

- [x] 20. Create test/prod SAM config environments
  - [x] 20.1 Added `[test.deploy.parameters]` with `Stage=test` (members; pretokengen already had it)
  - [x] 20.2 `[prod.deploy.parameters]` with `Stage=prod` (both modules)
  - [x] 20.3 Distinct per-module stack names: `test_sam-members`/`sam-members`, `test_pretokengen`/`pretokengen-prod`
  - [x] 20.4 Per-env parameter overrides (tables, pool ARN, projection) configured
  - _Requirements: 11.2_

- [x] 21. Implement environment-scoped execution roles
  - [x] 21.1 Inline IAM scopes DynamoDB to the EXACT table-name params (resolve to `test_*` for TEST, unprefixed for PROD)
  - [x] 21.2 TEST role cannot reach unprefixed tables — no `table/*` wildcard, same-account only
  - [x] 21.3 PROD role scoped to unprefixed table ARNs only
  - [x] 21.4 Static contract test asserts the no-wildcard / exact-ARN scoping (live cross-prefix DENY exercised at deploy)
  - _Requirements: 10.3, 12.1-12.4_
  - _Done: sam/tests/test_members_env_stack_contract.py, test_pretokengen_env_stack_contract.py._

- [x] 22. Deploy separate TEST API Gateway
  - [x] 22.1 Each stack declares its own `AWS::Serverless::Api` (members); a distinct stack ⇒ distinct API
  - [x] 22.2 TEST/PROD are distinct stacks ⇒ distinct invoke URLs (URL output is `Stage`-scoped)
  - [x] 22.3 Frontend SAM API base URL resolves per-env from the Environment_Definition (TEST placeholder until first deploy)
  - [x] 22.4 Backend health report already surfaces the active resolved SAM API URL
  - _Requirements: 13.1-13.4_

- [x] 23. Implement per-environment Cognito authorizer
  - [x] 23.1 Authorizer `UserPoolArn` is the per-env `CognitoUserPoolArn` parameter
  - [x] 23.2 TEST `[test]` config sets the test pool `eu-west-1_xyrlzfqbl`
  - [x] 23.3 PROD `[prod]` config sets the production pool `eu-west-1_Hdp40eWmu`
  - [x] 23.4 Contract test asserts the per-env authorizer/invoke pool wiring (live accept/reject exercised at deploy)
  - _Requirements: 14.1-14.3_

- [x] 24. Extend guard to SAM plane
  - [x] 24.1 `_check_sam_authorizer_pool` — SAM authorizer pool matches `APP_ENV`
  - [x] 24.2 `_check_sam_api_base_url` — SAM API base URL matches `APP_ENV` (placeholder-tolerant pre-deploy)
  - [x] 24.3 `_check_dynamodb_prefix` — DynamoDB prefix matches `APP_ENV`
  - _Requirements: 4.4, 14.4-14.5, 19.4_
  - _Done: backend/src/environment/consistency_guard.py + paired tests; verified live `environment.check` → CONSISTENT._

- [x] 25. Update Environment_Definition with SAM delta
  - [x] 25.1 Current-state delta recorded (comments: only the `test_` prefix isolates SAM today)
  - [x] 25.2 Target state documented in design.md §9/§10 (per-module stack-per-environment)
  - [x] 25.3 Definition updated with TEST (`test_sam-members`) and PROD (`sam-members`) SAM config; frontend mirrored
  - _Requirements: 15.1-15.3_

- [x] 26. Checkpoint - SAM plane ready for deployment
  - All tests pass: SAM suite 1207, backend env/guard suite 96, frontend 21. `sam validate --lint` passes both templates.
  - REMAINING (needs user — LIVE AWS): deploy `test_sam-members` + `test_pretokengen` to the data account via `sam deploy --config-env test`, re-attach the Cognito pre-token-generation trigger on the `myAdmin-test` pool to the new `test_pretokengen` function, retire the old `pretokengen-data` stack, and seed `test_governance_projection` (local seed or Phase-5 Copy_Utility). Record the real TEST API invoke URL in the Environment_Definition after first deploy.

### Phase 5: Operational tooling + steering

> **Phase 5 note (scripts folder standard).** The example paths `scripts/copy-prod-to-test.py`
> / `scripts/provision-test-account.py` are illustrative; the repo convention (see
> `scripts/onboarding/README.md`) is a purpose-named subfolder with a README and the shared
> `_lib` marker-walk bootstrap. Both runners therefore live under
> `scripts/test-environment/`. Paired tests for the hyphen-named runners live in `sam/tests/`.

- [x] 27. Implement Copy_Utility (PROD→TEST only)
  - [x] 27.1 Create `scripts/test-environment/copy-prod-to-test.py` utility (+ folder README)
  - [x] 27.2 Cognito account-attribute copying from PROD Pool A → test pool (non-secret allow-list)
  - [x] 27.3 DynamoDB table copying from a PROD table → its `test_`-prefixed table
  - [x] 27.4 One-directional: source clients read PROD, dest clients write TEST only; asserts dest is `test_`/test pool and source≠dest before any write
  - [x] 27.5 Explicit human invocation: dry-run default; a real write needs BOTH `--apply` and `--i-understand-this-writes-test` (no automation/schedule/startup hook)
  - [x] 27.6 Integration test (`sam/tests/test_copy_prod_to_test.py`, 15) with fakes that FAIL on any PROD write
  - _Requirements: 16.1-16.6, 20.4_

- [x] 28. Create Test_Account provisioning script
  - [x] 28.1 Create `scripts/test-environment/provision-test-account.py` (TEST pool, identity account)
  - [x] 28.2 Create user if absent; set a PERMANENT password (`admin_set_user_password Permanent=True`)
  - [x] 28.3 Permanent password clears `FORCE_CHANGE_PASSWORD` (no forced-change trap)
  - [x] 28.4 Seed `custom:tenants`/`custom:role` to a specified realistic shape (any valid config)
  - [x] 28.5 Prod-mirror is a SEPARATE explicit Copy_Utility step (`--mirror-prod` prints the command; never reads prod here)
  - [x] 28.6 Placeholders only; defense-in-depth guard refuses any non-test pool
  - _Requirements: 17.1-17.6_
  - _Paired test: `sam/tests/test_provision_test_account.py` (17)._

- [x] 29. Update steering documentation
  - [x] 29.1 `31-backend-database-flask-mysql.md` — Environments bullet → `APP_ENV` + resolved target
  - [x] 29.2 `41-shell-environment.md` — `#database` xref + wrapper note to resolved-target model
  - [x] 29.3 `#database` skill (`.kiro/skills/database.md`) — Environments section rewritten (schema `finance` both; `DB_*_TEST` vs `DB_*`)
  - [x] 29.4 `35-sam-module-architecture-sam.md` — rule 6 → per-env `test_` prefix + IAM boundary; new Stack-per-environment section
  - [x] 29.5 `42-local-dynamodb-testing.md` — DEV-ONLY banner (local emulator/`sam local` out of scope for `APP_ENV=test`)
  - _Requirements: 18.1-18.4_

- [x] 30. Implement URL-based environment selection (Req 22)
  - [x] 30.1 `TEST_URL`/`PROD_URL` fields in the Environment_Definition (added in Phase 1)
  - [x] 30.2 Pool-based access boundary pinned: TEST URL → test pool, PROD URL → Pool A
  - [x] 30.3 No in-app env-switch UI (resolver reads `APP_ENV` only; `aws-exports` hostname switch removed)
  - [x] 30.4 Smoke test (`frontend/src/config/urlPoolBoundary.test.ts`, 4) for the URL→pool boundary; indicator-from-`APP_ENV` already covered by `EnvironmentIndicator.test.tsx` / `aws-exports.test.ts`
  - _Requirements: 22.1-22.4_

- [x] 31. Implement branch-based promotion flow (Req 23)
  - [x] 31.1 `test_branch`/`production_branch` fields in the definition (added in Phase 1: `test`/`main`)
  - [x] 31.2 CI mapping documented: `test` branch → Test_Environment, `main` → Production (in all three deploy workflows)
  - [x] 31.3 Pipeline sets the env per branch: `deploy-sam-{members,pretokengen}.yml` trigger on `[main, test]` + `workflow_dispatch` `config_env`; a Resolve step → `sam deploy --config-env <test|prod>`
  - [x] 31.4 Mapping is CI config separate from source (the test/prod split lives in `samconfig.toml`)
  - _Requirements: 23.1-23.4_
  - _LIVE-IAM prerequisite (out of band): widen `NonprofitDeployRole`'s OIDC trust to allow `refs/heads/test` before the first `test`-branch deploy._

- [x] 32. Final checkpoint - All planes complete
  - All Phase 5 tests pass: SAM suite (incl. Copy_Utility 15 + provisioning 17), backend env/guard suite, frontend Req-22 suite. `sam validate --lint` unaffected.
  - REMAINING (needs user — LIVE AWS, carried from Phase 4): deploy the TEST stacks, re-attach the Cognito pretoken trigger, retire `pretokengen-data`, seed `test_governance_projection`, record the real TEST API URL; widen the OIDC trust to the `test` ref (Task 31 prerequisite).

### Phase 6: Production config wiring + environment-variable consolidation

- [ ] 33. Fill real non-secret config values in Environment_Definition
  - [ ] 33.1 Replace remaining PLACEHOLDER values with real non-secret identifiers where the plane is live (done for PROD_CLIENT_ID=66tp0087h9tfbstggonnu5aghp; audit the rest)
  - [ ] 33.2 Set the real production Flask API base URL (replace `https://PLACEHOLDER_PRODUCTION_FLASK_API`) once known
  - [ ] 33.3 Keep every SECRET as an env-var reference only — never commit a secret value (client secret, DB password, AWS keys stay env-sourced)
  - [ ] 33.4 Mirror each committed public identifier change in the frontend `environmentDefinition.ts` so backend/frontend cannot drift
  - [ ] 33.5 Add a test asserting NO `PLACEHOLDER_` value remains for any plane marked live in the definition
  - _Requirements: 3.1-3.6, 8.5_

- [ ] 34. Retire duplicated identity env vars once resolver supplies identity
  - [ ] 34.1 Make the backend derive the active identity block (COGNITO_USER_POOL_ID / COGNITO_CLIENT_ID) from the resolver's ResolvedConfig, not from raw env vars
  - [ ] 34.2 Confirm the Pool_Registry (COGNITO_POOL_KEYS + {KEY}_COGNITO_* ) remains the SOLE source for token verification (multi-pool), independent of the identity block
  - [ ] 34.3 Remove the now-redundant raw identity-block env vars from the deploy config (Railway) once 34.1 lands, keeping only the registry vars + secrets + APP_ENV
  - [ ] 34.4 Keep COGNITO_CLIENT_SECRET as an env var (the resolver supplies the public identity; the secret stays operational)
  - [ ] 34.5 Update the Consistency_Guard identity-block check to tolerate an unset identity block when the resolver is authoritative (no false fail-fast)
  - [ ] 34.6 Change-with-tests: update guard + resolver tests for the resolver-authoritative identity
  - _Requirements: 2.3, 2.4, 4.3, 8.3_

- [ ] 35. Audit and consolidate deploy environment variables (Railway)
  - [ ] 35.1 Produce a mapping of every deploy env var -> the code that consumes it (name-only; never record secret values)
  - [ ] 35.2 Flag overlaps/duplicates (e.g. identity-block vs PROD_A_* registry; multiple frontend-URL/CloudFront vars) and record which are intentional vs redundant
  - [ ] 35.3 Document the target per-plane variable set per environment in the Environment_Definition doc (which vars are required where)
  - [ ] 35.4 Recommend rotation for any secret that has leaked into a non-gitignored/plaintext file, and verify no secret is committed
  - _Requirements: 3.5, 18.1-18.4_

- [ ] 36. Checkpoint - Production config wiring complete
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from design
- Unit tests validate specific examples and edge cases
- Integration tests verify AWS/IaC behavior
- Follow "one PR per logical change" + "change-with-tests" contract
- Keep app deployable at every step
- Use placeholders only, no real secrets in committed files

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3", "1.4", "1.5", "2.1", "2.2", "2.3", "2.4", "3.1", "3.2", "3.3", "3.4", "3.5"] },
    { "id": 1, "tasks": ["1.6", "2.5", "5.1", "5.2", "5.3", "6.1", "6.2", "6.3", "6.4", "7.1", "7.2", "7.3", "7.4", "8.1", "8.2", "8.3", "8.4"] },
    { "id": 2, "tasks": ["5.4", "6.5", "8.5", "9.1", "9.2", "9.3", "9.4", "11.1", "11.2", "11.3", "11.4", "11.5", "12.1", "12.2", "12.3"] },
    { "id": 3, "tasks": ["12.4", "12.5", "13.1", "13.2", "13.3", "15.1", "15.2", "15.3", "16.1", "16.2", "16.3", "16.4", "16.5"] },
    { "id": 4, "tasks": ["15.4", "17.1", "17.2", "17.3", "17.4", "19.1", "19.2", "19.3", "19.4", "20.1", "20.2", "20.3", "20.4"] },
    { "id": 5, "tasks": ["21.1", "21.2", "21.3", "22.1", "22.2", "22.3", "22.4", "23.1", "23.2", "23.3", "24.1", "24.2", "24.3"] },
    { "id": 6, "tasks": ["21.4", "23.4", "25.1", "25.2", "25.3", "27.1", "27.2", "27.3", "27.4", "27.5", "28.1", "28.2", "28.3", "28.4"] },
    { "id": 7, "tasks": ["27.6", "28.5", "28.6", "29.1", "29.2", "29.3", "29.4", "29.5", "30.1", "30.2", "30.3", "30.4", "31.1", "31.2", "31.3", "31.4"] },
    { "id": 8, "tasks": ["33.1", "33.2", "33.3", "33.4", "33.5", "34.1", "34.2", "34.3", "34.4", "34.5", "34.6", "35.1", "35.2", "35.3", "35.4"] }
  ]
}
```