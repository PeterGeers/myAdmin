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

- [ ] 15. Neutralize `test_mode` selector (Step 1: shim)
  - [ ] 15.1 Update `DatabaseManager.__init__` to ignore `test_mode` for environment selection
  - [ ] 15.2 Add deprecation warning when `test_mode` is passed but ignored
  - [ ] 15.3 Keep `test_mode` parameter signature for backward compatibility
  - [ ] 15.4 Write property test for `test_mode` no longer selecting environment (Property 6)
  - _Requirements: 2.6_

- [ ] 16. Collapse request-driven `test_mode` (Step 2)
  - [ ] 16.1 Update `reporting_routes` to stop reading `testMode` from request args
  - [ ] 16.2 Update `str_channel_routes` to stop defaulting `test_mode=True`
  - [ ] 16.3 Update all other services reading `test_mode` from request or kwargs
  - [ ] 16.4 Remove `mutaties_test`/`testfinance` table/schema switches
  - [ ] 16.5 Update paired tests for each touched route (change-with-tests)
  - _Requirements: 1.6, 2.6_

- [ ] 17. Remove `test_mode` parameter (Step 3)
  - [ ] 17.1 Drop `test_mode` kwarg from `DatabaseManager` and all service constructors
  - [ ] 17.2 Refactor test fixtures `test_environment`/`production_environment` to set `APP_ENV`
  - [ ] 17.3 Update migration scripts to use `APP_ENV` instead of `TEST_MODE`
  - [ ] 17.4 Clean up remaining `test_mode` references across codebase
  - _Requirements: 2.6_

- [ ] 18. Checkpoint - `test_mode` migration complete
  - Ensure all tests pass, ask the user if questions arise.

### Phase 4: SAM test stack (heavy build)

- [ ] 19. Prepare SAM template for environment parameterization
  - [ ] 19.1 Add `Environment` parameter to SAM templates with allowed values `[test, production]`
  - [ ] 19.2 Update template to flow `Environment` into all resources
  - [ ] 19.3 Add `APP_ENV` environment variable to each Lambda deriving from `Environment`
  - [ ] 19.4 Update table name references to use prefix based on `Environment`
  - _Requirements: 11.1-11.3_

- [ ] 20. Create test/prod SAM config environments
  - [ ] 20.1 Add `[test.deploy.parameters]` section to `samconfig.toml` with `Environment=test`
  - [ ] 20.2 Add `[prod.deploy.parameters]` section with `Environment=production`
  - [ ] 20.3 Set distinct stack names: `myAdmin-test` and `myAdmin-prod`
  - [ ] 20.4 Configure parameter overrides for each environment
  - _Requirements: 11.2_

- [ ] 21. Implement environment-scoped execution roles
  - [ ] 21.1 Update IAM role policies to scope DynamoDB by prefix: `test_*` for TEST, unprefixed for PROD
  - [ ] 21.2 Ensure TEST role denies access to unprefixed tables at IAM layer
  - [ ] 21.3 Verify PROD role scoped to unprefixed tables only
  - [ ] 21.4 Write integration test for IAM cross-prefix denial
  - _Requirements: 10.3, 12.1-12.4_

- [ ] 22. Deploy separate TEST API Gateway
  - [ ] 22.1 Configure separate `AWS::Serverless::Api` for TEST stack
  - [ ] 22.2 Ensure TEST and PROD stacks have distinct invoke URLs
  - [ ] 22.3 Update frontend SAM API base URL resolution to use environment-specific URL
  - [ ] 22.4 Update backend health report to include active SAM API URL
  - _Requirements: 13.1-13.4_

- [ ] 23. Implement per-environment Cognito authorizer
  - [ ] 23.1 Update authorizer configuration to reference pool based on `Environment`
  - [ ] 23.2 TEST authorizer references test pool `eu-west-1_xyrlzfqbl`
  - [ ] 23.3 PROD authorizer references production pool `eu-west-1_Hdp40eWmu`
  - [ ] 23.4 Write integration test for authorizer accept/reject behavior
  - _Requirements: 14.1-14.3_

- [ ] 24. Extend guard to SAM plane
  - [ ] 24.1 Add guard check for SAM authorizer pool matching `APP_ENV`
  - [ ] 24.2 Add guard check for SAM API base URL matching `APP_ENV`
  - [ ] 24.3 Add guard check for DynamoDB prefix matching `APP_ENV`
  - _Requirements: 4.4, 14.4-14.5, 19.4_

- [ ] 25. Update Environment_Definition with SAM delta
  - [ ] 25.1 Record current-state delta: no separate TEST stack today
  - [ ] 25.2 Document target state: stack-per-environment with separate API Gateway
  - [ ] 25.3 Update definition with TEST and PROD SAM configuration
  - _Requirements: 15.1-15.3_

- [ ] 26. Checkpoint - SAM plane ready for deployment
  - Ensure all tests pass, ask the user if questions arise.

### Phase 5: Operational tooling + steering

- [ ] 27. Implement Copy_Utility (PROD→TEST only)
  - [ ] 27.1 Create `scripts/copy-prod-to-test.py` utility
  - [ ] 27.2 Implement Cognito account-attribute copying from PROD to TEST
  - [ ] 27.3 Implement DynamoDB table copying from PROD to `test_` tables
  - [ ] 27.4 Ensure utility only writes TEST targets, never writes TEST→PROD
  - [ ] 27.5 Make utility require explicit human invocation (no automation)
  - [ ] 27.6 Write integration test verifying PROD→TEST only behavior
  - _Requirements: 16.1-16.6, 20.4_

- [ ] 28. Create Test_Account provisioning script
  - [ ] 28.1 Create `scripts/provision-test-account.py` targeting Identity_Account
  - [ ] 28.2 Create user in test pool if absent with `admin-set-user-password --permanent`
  - [ ] 28.3 Clear `FORCE_CHANGE_PASSWORD` flag
  - [ ] 28.4 Set `custom:tenants`/`custom:role` to specified realistic shape
  - [ ] 28.5 Support optional mode to mirror production reference account attributes
  - [ ] 28.6 Use placeholders only, no real credentials in committed files
  - _Requirements: 17.1-17.6_

- [ ] 29. Update steering documentation
  - [ ] 29.1 Update `31-backend-database-flask-mysql.md` with `APP_ENV` + resolved target model
  - [ ] 29.2 Update `41-shell-environment.md` with DB connection notes for resolved targets
  - [ ] 29.3 Update `#database` skill with environment distinction by resolved target
  - [ ] 29.4 Update `35-sam-module-architecture-sam.md` with stack-per-environment model
  - [ ] 29.5 Update `42-local-dynamodb-testing.md` marking local emulator as dev-only
  - _Requirements: 18.1-18.4_

- [ ] 30. Implement URL-based environment selection (Req 22)
  - [ ] 30.1 Add `TEST_URL` and `PROD_URL` fields to Environment_Definition
  - [ ] 30.2 Document pool-based access control: TEST URL authenticates against test pool
  - [ ] 30.3 Ensure frontend contains no UI control to switch environments within a unit
  - [ ] 30.4 Add smoke test for URL-based auth boundary
  - _Requirements: 22.1-22.4_

- [ ] 31. Implement branch-based promotion flow (Req 23)
  - [ ] 31.1 Add `test_branch` and `production_branch` fields to Environment_Definition
  - [ ] 31.2 Document CI/CD pipeline mapping: TEST branch → Test_Environment, main → Production
  - [ ] 31.3 Configure pipeline to set `APP_ENV` based on branch
  - [ ] 31.4 Ensure branch mapping is separate from application source
  - _Requirements: 23.1-23.4_

- [ ] 32. Final checkpoint - All planes complete
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
    { "id": 7, "tasks": ["27.6", "28.5", "28.6", "29.1", "29.2", "29.3", "29.4", "29.5", "30.1", "30.2", "30.3", "30.4", "31.1", "31.2", "31.3", "31.4"] }
  ]
}
```