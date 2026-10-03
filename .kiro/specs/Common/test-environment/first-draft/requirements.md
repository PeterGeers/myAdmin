# Requirements Document

## Introduction

This spec defines the proper TEST environment for the myAdmin system across every plane, at target state. It describes the environment the project is building toward: a single, authoritative, deploy-level environment selector, `APP_ENV`, whose only recognized values are `production` and `test`, from which a central Environment_Resolver derives one coherent per-plane configuration that every plane consumes. The guiding principle is "one decision, many consumers": the environment is decided once, and no plane re-decides TEST versus PRODUCTION on its own from raw signals such as the browser hostname.

The TEST environment follows the best-practice "one running unit = one environment" model (Model A). A single running unit serves exactly one environment for its entire lifetime; there is no per-request or per-call environment switching. For a long-running process (the Flask backend, the frontend SPA build) the running unit is the process. For the serverless SAM plane the running unit is a deployed stack: the TEST environment on that plane is a separately deployed stack, parameterized by its own `APP_ENV`, distinct from the production stack. If `APP_ENV` is unset or not a recognized value, the unit refuses to start rather than silently defaulting to production or test, consistent with the fail-fast, no-dangerous-default philosophy already present in `backend/src/auth/pool_registry.py`.

The purpose of the TEST environment is to validate changed application logic BEFORE it reaches production — in particular code that is not yet on `main` — without any risk to production data. "TEST" is a durable, pre-production validation environment, and it is distinct from "dev". Local or ephemeral setups (for example a local DynamoDB emulator that loses all data when its process stops, or `sam local` running a function on a developer machine) are "dev" and are explicitly out of scope for this spec. The spec keeps TEST and PRODUCTION as the only environment terms and never uses "dev/test" as a single label.

The TEST environment is a FIXED BOUNDARY with FLEXIBLE CONTENTS. What this spec guarantees is the environment boundary: when `APP_ENV=test`, the structural wiring is always TEST — the test Cognito pool, the resolved TEST database target, the resolved TEST backend host and Flask API base URL, the `test_`-prefixed DynamoDB tables, and the deployed TEST SAM compute stack (its Lambdas, API Gateway endpoint, and environment-scoped execution roles) — and the Consistency_Guard enforces that this boundary never varies per test. What this spec does NOT fix is the contents inside that boundary: the Cognito accounts and their `custom:tenants`/`custom:role` attributes, the MySQL data, and the DynamoDB data MAY be identical to production, partially matching, or deliberately different (for example edge-case data, or a tenant/role configuration that does not yet exist in production), depending on what is being tested. Making TEST contents identical to production is therefore a CAPABILITY — one supported way to populate TEST when a test needs prod-identical data, provided by the explicit Copy_Utility — and NOT a mandate or the default. The spec guarantees the Environment_Boundary, not content parity.

The real isolation boundary is IAM, not application code. Across both the data plane and the compute plane, access control (IAM policies scoping DynamoDB access by table-name pattern, environment-scoped Lambda execution roles) is what prevents a TEST unit from reaching production resources even if application code resolves a prefix incorrectly. Code resolution is the convenience; IAM is the enforcement.

Every Plane's environment target is a RESOLVED, NAMED value derived from `APP_ENV`, never a hardcoded physical location. Physical hosting location — where a database or the backend process actually runs — is an OPERATIONAL mapping with minimal architectural impact: it maps to a resolved target via configuration, and relocating a target (for example moving the TEST database or the backend host from a local machine to a hosted provider) is a resolver-mapping and configuration change, NOT a requirements or architecture change. Concrete current locations appear in this spec only as non-normative "current mapping" examples that record the present operational reality; they are never the definition of a target. This complements the "IAM is the real boundary" and "fixed boundary / flexible contents" principles: the boundary that `APP_ENV` selects is enforced regardless of where the resolved targets physically live.

### Motivation / background

The move toward this target state was prompted by recurring, silent environment mismatches in which independent per-plane switches disagreed by construction. The Cognito pool mismatch addressed earlier this week (a test-pool frontend login validated against a production pool) is one already-resolved instance of that class, not the subject of this spec. The spec is forward-looking: it defines the proper TEST environment for all planes and drives the implementation needed to reach it, rather than being shaped around individual past incidents.

## Glossary

- **APP_ENV**: The single, authoritative, deploy-level environment selector. A named enum with a closed set of recognized values — `production` and `test` — not a boolean. It is set explicitly per running unit (a backend environment variable; an injected Vite build/runtime variable on the frontend; a deploy-time SAM parameter and per-Lambda environment variable on the SAM plane) and is never inferred from incidental signals such as the browser hostname. An unset or unrecognized value causes the running unit to refuse to start.
- **Environment_Resolver**: The single environment decision contract that reads `APP_ENV` and produces one resolved per-plane configuration (the resolved Cognito identity, MySQL target, DynamoDB prefix, and SAM compute wiring) that every Plane consumes. On the Flask and Frontend planes it is the central resolver module reading `APP_ENV`. On the SAM plane the same contract is realized by each Lambda reading its deploy-time `APP_ENV` environment variable to resolve its table prefix, identity, and authorizer pool. It is the one place that maps `APP_ENV` to concrete per-plane configuration; no Plane re-derives the environment on its own.
- **Test_Environment**: The coherent set of per-plane configuration selected when `APP_ENV=test`: the test Cognito pool, the resolved TEST database target (schema `finance`), the resolved TEST backend host, the resolved TEST Flask API base URL, the `test_`-prefixed DynamoDB tables, and the deployed TEST SAM compute stack. Its counterpart, selected when `APP_ENV=production`, is the **Production_Environment**, whose database target, backend host, and Flask API base URL are the resolved PRODUCTION values. The two are distinguished by their resolved targets and credentials, not by physical hosting location or provider.
- **Resolved_Target**: Any concrete per-plane value the Environment_Resolver produces from `APP_ENV` — the Cognito pool, the database target, the Flask backend host, the Flask API base URL, the DynamoDB table prefix, and the SAM API base URL. Every Resolved_Target is derived from `APP_ENV` and read from configuration; none is hardcoded to a physical location or inferred from the browser hostname. A Resolved_Target's physical hosting location is an operational mapping that MAY change (for example a database or backend host moving between a local machine and a hosted provider) without changing the requirement, by changing only the resolver mapping and configuration.
- **Plane**: One of the subsystems that consume the resolved configuration: the **Frontend_Plane** (Vite SPA Cognito, SAM API base-URL, and Flask API base-URL selection), the **Backend_Identity_Plane** (Flask backend Cognito registry and identity block), the **MySQL_Plane** (Flask database connection target), the **Backend_Runtime_Plane** (the Flask backend runtime host — where the Flask backend process runs — resolved from `APP_ENV`), and the **SAM_Plane** (SAM/CloudFormation compute stack, its Lambdas, API Gateway, execution roles, and DynamoDB tables).
- **SAM_Test_Stack**: The separately deployed SAM/CloudFormation stack that constitutes the SAM_Plane's TEST environment (for example `myAdmin-test`), distinct from the production stack (for example `myAdmin-prod`). It is parameterized by an `Environment`/`APP_ENV` SAM parameter that flows into every resource, deployed via its own named `samconfig` environment (`sam deploy --config-env <name>`), and it is the serverless realization of Model A ("one deployed stack = one environment"). It is NOT `sam local`, which is a dev-only, out-of-scope target.
- **Pool_Registry**: The backend issuer→pool registry (`backend/src/auth/pool_registry.py`) that maps a token issuer (`iss`) to a `PoolConfig`, driven by the `COGNITO_POOL_KEYS` environment variable with fail-fast, no-default semantics. A token whose issuer is not registered is rejected (`UnknownIssuerError` → 401).
- **Environment_Definition**: The single documented source of truth that declares, per Plane, the TEST and PRODUCTION configuration, derived from `APP_ENV` via the Environment_Resolver, in one documented location rather than scattered across frontend `.env`, backend `.env`, SAM templates, and source code.
- **Consistency_Guard**: A verification mechanism that checks every Plane's resolved wiring matches the single active `APP_ENV` and fails loudly — refusing to start and/or exiting non-zero as a `check` command — when any Plane disagrees, rather than allowing a silent runtime failure. Its coverage spans the Cognito identity, the resolved database target, the Flask API base URL the frontend calls, DynamoDB tables, and the SAM compute surface (the API Gateway base URL that clients call and the Cognito pool the SAM authorizer validates against).
- **Environment_Boundary**: The fixed, always-TEST (or always-PRODUCTION) structural wiring selected by `APP_ENV` — for the Test_Environment, the test Cognito pool, the resolved TEST database target, the resolved TEST backend host and Flask API base URL, the `test_`-prefixed DynamoDB tables, and the deployed TEST SAM compute stack (Lambdas, API Gateway, and environment-scoped execution roles). The Environment_Boundary is enforced by the Consistency_Guard and does not vary per test; it is what this spec guarantees.
- **Environment_Contents**: The flexible accounts and data inside the Environment_Boundary — the Cognito accounts and their `custom:tenants`/`custom:role` attributes, the MySQL data, and the DynamoDB data. The Environment_Contents MAY be identical to production, partially matching, or deliberately different, chosen per the test under consideration; the spec does not fix the Environment_Contents.
- **Environment_Indicator**: A derived on-screen label that names the active environment (TEST vs PROD), the active pool/identity, and, where observable, the active SAM API endpoint, computed from the same `APP_ENV`/Environment_Resolver so it cannot drift from the configuration actually in use.
- **Cutover**: The act of switching one running unit from one environment to the other by changing the single `APP_ENV` value (for the SAM plane, deploying/selecting the stack for the target environment), which the Environment_Resolver then applies across all Planes at once.
- **Copy_Utility**: A deliberate, separately-invoked administrative utility that copies data or attributes from PRODUCTION into TEST (Cognito account-attribute parity; a DynamoDB production→`test_` table copy) only on an explicit human request. It is the only sanctioned mechanism that touches both environments; it never runs automatically or on a schedule, and it never writes from TEST toward PRODUCTION.
- **Test_Account**: ANY Cognito user in the test pool, carrying the standard `custom:tenants` and `custom:role` attributes that drive the application's user→tenant→role authorization. The attribute shape of a Test_Account is arbitrary and chosen per test: it MAY mirror a production reference account or be deliberately different (for example a tenant/role combination that does not yet exist in production). A Test_Account is not defined as a single, production-mirrored account.
- **Identity_Account**: The AWS account that holds the Cognito pools — the `personal` profile, account `344561557829`, region `eu-west-1`. The test pool is `eu-west-1_xyrlzfqbl` (`myAdmin-test`, app client `43s15cm8qcgg8an85udt0e087u`, no client secret); production Pool A is `eu-west-1_Hdp40eWmu` (`myAdmin`).
- **Infra_Account**: The AWS account that holds infra/data/compute resources (DynamoDB, API Gateway, Lambda) — the `nonprofit-deploy` profile, account `506221081911`. Both the TEST SAM stack and the production SAM stack, and both the `test_`-prefixed TEST tables and the unprefixed PRODUCTION tables, live in this one account.
- **TEST_URL**: The distinct URL (for example `localhost:3000` or a hosted URL) where the Test_Environment deployment is served. This URL authenticates users against the test Cognito pool (`eu-west-1_xyrlzfqbl`) and determines access solely by account membership in that pool.
- **PROD_URL**: The distinct URL where the Production_Environment deployment is served. This URL authenticates users against production Pool A (`eu-west-1_Hdp40eWmu`).
- **Branch_Environment_Mapping**: The CI/CD pipeline configuration that maps Git branches to environments — for example, the `test` branch deploys to the Test_Environment, and the `main` branch deploys to the Production_Environment. This mapping is separate from the application source and can evolve without changing the spec.

## Requirements

### Requirement 1: Single authoritative environment selector (`APP_ENV`)

**User Story:** As a developer deploying a running unit, I want one explicit, deploy-level setting that names the environment, so that every plane agrees on TEST versus PRODUCTION without inferring it from incidental signals.

#### Acceptance Criteria

1. THE Environment_Resolver SHALL read the active environment solely from `APP_ENV`.
2. THE Environment_Resolver SHALL recognize exactly the values `production` and `test` for `APP_ENV`.
3. IF `APP_ENV` is unset or is not a recognized value, THEN THE Environment_Resolver SHALL refuse to start the running unit and SHALL report an error naming the unrecognized value and the recognized values.
4. THE Environment_Resolver SHALL NOT infer the active environment from the browser hostname, request origin, or any other incidental signal.
5. THE Frontend_Plane SHALL obtain `APP_ENV` from an explicitly injected build or runtime variable rather than from `window.location.hostname`.
6. WHILE a single running unit is active, THE Environment_Resolver SHALL resolve to exactly one environment for the lifetime of that running unit.

### Requirement 2: Central resolver as the single environment decision point

**User Story:** As a developer, I want one decision contract to translate `APP_ENV` into per-plane configuration that every plane consumes, so that no plane independently re-decides the environment.

#### Acceptance Criteria

1. WHEN a running unit starts, THE Environment_Resolver SHALL produce one resolved per-plane configuration derived from `APP_ENV`.
2. THE resolved configuration SHALL name, per Plane, the Cognito identity, the resolved database target, the resolved Flask backend host, the resolved Flask API base URL, the DynamoDB table prefix, and the SAM compute wiring (API base URL and authorizer pool) for the active environment.
3. THE Frontend_Plane, Backend_Identity_Plane, MySQL_Plane, and SAM_Plane SHALL each consume the resolved configuration from the Environment_Resolver rather than reading raw environment variables or the browser hostname to decide the environment.
4. THE Environment_Resolver SHALL be the single location in which `APP_ENV` is mapped to concrete per-plane configuration.
5. WHERE the Plane is the SAM_Plane, THE Environment_Resolver contract SHALL be realized by each Lambda reading its deploy-time `APP_ENV` environment variable to resolve its table prefix, identity, and authorizer pool.
6. THE legacy `test_mode` flag SHALL NOT be used as an environment selector.

### Requirement 3: Single documented source of truth for the environment definition

**User Story:** As a developer validating unmerged code, I want one documented definition of what the TEST environment is across every plane, so that I do not have to reconstruct it from scattered frontend `.env`, backend `.env`, SAM templates, and code.

#### Acceptance Criteria

1. THE Environment_Definition SHALL declare, for each Plane, which configuration values constitute the Test_Environment and which constitute the Production_Environment, as derived from `APP_ENV` by the Environment_Resolver.
2. THE Environment_Definition SHALL record, for the Backend_Identity_Plane and Frontend_Plane, the Cognito pool identifier, app-client identifier, and pool label for each environment.
3. THE Environment_Definition SHALL record, for the MySQL_Plane, the resolved TEST database target for the Test_Environment and the resolved PRODUCTION database target for the Production_Environment, both using schema name `finance`, distinguished by resolved target and credentials rather than by physical hosting location. (Non-normative current mapping: the TEST database target currently resolves to a local Docker MySQL instance and the PRODUCTION database target currently resolves to Railway; this is the present operational mapping only, not the definition, and a future move — for example a hosted TEST database instance — is accommodated by changing the resolver mapping and configuration, not this requirement.)
4. THE Environment_Definition SHALL record, for the SAM_Plane, the deployed stack name, the API Gateway invoke URL, the Lambda execution-role scope, and the DynamoDB table-name prefix for each environment, with the `test_` prefix for the Test_Environment and the unprefixed names for the Production_Environment.
5. THE Environment_Definition SHALL reside in a single documented location rather than being distributed across multiple `.env` files, SAM templates, and source files.
6. WHERE a configuration value is a secret or a real production credential, THE Environment_Definition SHALL use a placeholder rather than the real value.

### Requirement 4: Cross-plane consistency guard with fail-fast behavior

**User Story:** As a developer, I want the system to detect when any plane's resolved wiring disagrees with the active `APP_ENV` and fail loudly, so that I get a clear diagnostic instead of a silent 401 or a cross-environment call.

#### Acceptance Criteria

1. WHEN the Backend_Identity_Plane starts, THE Consistency_Guard SHALL verify that the pool required by the active environment is present in the Pool_Registry.
2. IF the pool selected by the Frontend_Plane is not registered in the Backend_Identity_Plane Pool_Registry, THEN THE Consistency_Guard SHALL report the inconsistency with an explicit message naming both the frontend-selected pool and the registered pools.
3. IF the Backend_Identity_Plane identity block (`COGNITO_USER_POOL_ID`, `COGNITO_CLIENT_ID`) names a pool that is not consistent with the active `APP_ENV`, THEN THE Consistency_Guard SHALL report the inconsistency.
4. IF the SAM_Plane authorizer pool or the API Gateway base URL that clients call does not match the active `APP_ENV`, THEN THE Consistency_Guard SHALL report the inconsistency with an explicit message naming the mismatched surface.
5. WHERE the Consistency_Guard is invoked as a `check` command, THE Consistency_Guard SHALL exit with a non-zero status when any Plane's resolved wiring is inconsistent with the active `APP_ENV`.
6. WHEN every Plane's resolved wiring agrees with the active `APP_ENV`, THE Consistency_Guard SHALL report a successful, consistent state.
7. IF one subset of Planes resolves to the Test_Environment while another subset resolves to the Production_Environment, THEN THE Consistency_Guard SHALL report the half-cutover as an inconsistency.

### Requirement 5: On-screen visibility of the active environment

**User Story:** As a user on the login screen and while authenticated, I want to see plainly which environment is active (TEST vs PROD), so that I never mistake one for the other.

#### Acceptance Criteria

1. WHEN the login screen is displayed, THE Environment_Indicator SHALL show a label distinguishing the Production_Environment ("PROD") from the Test_Environment ("TEST").
2. WHILE a user is authenticated, THE Environment_Indicator SHALL show the active environment label and the active pool/identity label.
3. THE Environment_Indicator SHALL derive the displayed environment from the same `APP_ENV` and Environment_Resolver that select the active Cognito pool, so that the indicator cannot drift from the configuration actually in use.
4. WHERE the active SAM API endpoint is observable to the client, THE Environment_Indicator SHALL present the active SAM API endpoint or stack-environment label alongside the environment label.
5. WHERE the active environment is the Test_Environment, THE Environment_Indicator SHALL present a visually distinct label from the Production_Environment label.

### Requirement 6: Backend environment/health report

**User Story:** As a developer, I want a backend endpoint or command that names the active environment, pool, MySQL target, DynamoDB prefix, and SAM compute surface, so that I can confirm the environment without reading source, `.env`, or SAM templates.

#### Acceptance Criteria

1. WHEN the backend environment report is requested, THE Backend_Identity_Plane SHALL return the active `APP_ENV` value.
2. WHEN the backend environment report is requested, THE Backend_Identity_Plane SHALL return the active Pool_Registry pool label and the active identity-block pool label.
3. WHEN the backend environment report is requested, THE MySQL_Plane SHALL return the active resolved database target as either the resolved TEST database target or the resolved PRODUCTION database target, named by its resolved identity rather than by a hardcoded physical location.
4. WHEN the backend environment report is requested, THE SAM_Plane SHALL return the active DynamoDB table prefix and, where observable, the active SAM API Gateway base URL and stack-environment label.
5. THE backend environment report SHALL derive its values from the Environment_Resolver, so that the report cannot drift from the active configuration.
6. IF a reported value is a secret, THEN THE backend environment report SHALL omit the secret value and report only a non-secret label or identifier.

### Requirement 7: Cutover driven by a single selector

**User Story:** As a developer performing a cutover, I want the environment switched by changing one value that the resolver applies everywhere, so that a cutover cannot be half-finished.

#### Acceptance Criteria

1. WHEN `APP_ENV` is changed for a running unit, THE Environment_Resolver SHALL apply the corresponding configuration to every Plane together as a single resolved environment.
2. WHEN the Backend_Identity_Plane is wired for the Test_Environment, THE identity block (`COGNITO_USER_POOL_ID`, `COGNITO_CLIENT_ID`) SHALL name the same pool and client that `COGNITO_POOL_KEYS` registers for the Test_Environment.
3. WHERE the active Backend_Identity_Plane pool is the test pool, THE `COGNITO_CLIENT_SECRET` SHALL be empty, because the test app-client has no secret.
4. WHERE the Plane is the SAM_Plane, THE Cutover SHALL be realized by deploying the stack with the named `samconfig` environment (`sam deploy --config-env <name>`) that supplies the target environment's parameter value, rather than by mutating a running stack's environment in place.
5. IF the resolved wiring of any Plane names a different environment than the active `APP_ENV`, THEN THE Consistency_Guard SHALL report the Cutover as incomplete.

### Requirement 8: Cognito identity plane

**User Story:** As a developer, I want the Cognito identity resolved from `APP_ENV` and internally coherent, so that frontend login and backend validation always target the same pool.

#### Acceptance Criteria

1. WHERE `APP_ENV` is `test`, THE Environment_Resolver SHALL resolve the Cognito identity to the test pool `eu-west-1_xyrlzfqbl` (`myAdmin-test`) with app client `43s15cm8qcgg8an85udt0e087u`.
2. WHERE `APP_ENV` is `production`, THE Environment_Resolver SHALL resolve the Cognito identity to production Pool A `eu-west-1_Hdp40eWmu` (`myAdmin`).
3. THE Backend_Identity_Plane Pool_Registry (`COGNITO_POOL_KEYS`) and identity block (`COGNITO_USER_POOL_ID`, `COGNITO_CLIENT_ID`, `COGNITO_CLIENT_SECRET`) SHALL resolve from the active `APP_ENV`.
4. WHERE the resolved Cognito identity is the test pool, THE resolved `COGNITO_CLIENT_SECRET` SHALL be empty.
5. THE Cognito pool identifiers and app-client identifiers SHALL be read from configuration and SHALL NOT be hardcoded in source other than as non-secret public identifiers in the Environment_Definition.

### Requirement 9: MySQL plane test target

**User Story:** As a developer, I want the TEST database target to be the resolved TEST database target derived from `APP_ENV`, so that TEST never operates against the resolved PRODUCTION database target regardless of where either target is physically hosted.

#### Acceptance Criteria

1. THE Environment_Definition SHALL declare the resolved TEST database target as the MySQL_Plane connection target for the Test_Environment and the resolved PRODUCTION database target as the connection target for the Production_Environment, each defined by its resolved target and credentials rather than by a hardcoded physical location.
2. THE MySQL_Plane SHALL use schema name `finance` for both the Test_Environment and the Production_Environment, distinguishing the two by resolved target and credentials rather than by schema name or physical location.
3. WHEN the MySQL_Plane is resolved for the Test_Environment, THE MySQL_Plane SHALL connect to the resolved TEST database target and SHALL NOT connect to the resolved PRODUCTION database target.
4. THE MySQL_Plane database connection values SHALL be read from environment variables and SHALL NOT be hardcoded in source.
5. IF the MySQL_Plane connection resolved for the Test_Environment targets the resolved PRODUCTION database target, THEN THE Consistency_Guard SHALL report the inconsistency.
6. THE isolation between the resolved TEST database target and the resolved PRODUCTION database target SHALL be enforced by their being separate resolved targets with separate credentials, so that the isolation holds even where both targets are later hosted on the same provider ("boundary is enforced, not assumed", as applied to the DynamoDB and Lambda planes).
7. THE Test_Environment MySQL_Plane SHALL be loadable with a known test dataset.

> **Non-normative current mapping:** the resolved TEST database target currently resolves to a local Docker MySQL instance and the resolved PRODUCTION database target currently resolves to Railway. This records the present operational mapping only and is not the definition of either target. A future relocation — for example a hosted TEST database instance — is accommodated by changing the resolver mapping and configuration, not by changing this requirement.

### Requirement 10: SAM/DynamoDB data plane test target

**User Story:** As a developer, I want the TEST DynamoDB tables to be real, persistent, `test_`-prefixed tables scoped by IAM, so that TEST data survives across runs and a prefix typo cannot reach production tables.

#### Acceptance Criteria

1. THE Environment_Definition SHALL declare the `test_`-prefixed DynamoDB tables in the Infra_Account as the SAM_Plane data target for the Test_Environment and the unprefixed tables in the same account as the target for the Production_Environment.
2. WHEN the SAM_Plane is resolved for the Test_Environment, THE SAM_Plane SHALL target the `test_`-prefixed DynamoDB tables and SHALL NOT target the unprefixed production tables.
3. THE Test_Environment SAM_Plane identity SHALL be constrained by an IAM policy that scopes DynamoDB access to the resource ARN pattern `arn:aws:dynamodb:*:*:table/test_*`, and the Production_Environment identity SHALL be scoped to the unprefixed tables.
4. THE SAM_Plane configuration SHALL operate within the account boundary defined for the Infra_Account (`nonprofit-deploy`, `506221081911`).
5. THE Environment_Definition SHALL record the local DynamoDB emulator as a dev-only, out-of-scope target that loses data when its process stops and is not used as the Test_Environment.
6. THE Environment_Definition SHALL record AWS Organizations multi-account isolation (account-per-environment, a separate test account under a management account) as a documented further escalation beyond stack-per-environment that is not built in this spec.

### Requirement 11: SAM compute plane as a stack-per-environment

**User Story:** As a developer, I want the TEST SAM compute to be its own separately deployed stack parameterized by `APP_ENV`, so that the serverless surface follows the "one deployed stack = one environment" model instead of sharing one stack between TEST and PRODUCTION.

#### Acceptance Criteria

1. THE SAM_Plane Test_Environment SHALL be a separately deployed SAM/CloudFormation stack (for example `myAdmin-test`) distinct from the Production_Environment stack (for example `myAdmin-prod`).
2. THE SAM_Test_Stack SHALL be parameterized by a SAM template parameter (for example `Environment`) whose value is supplied per environment by a named `samconfig` environment section selected via `sam deploy --config-env <name>` (for example a `test` config-env supplying `Environment=test` and a `prod` config-env supplying `Environment=production`), and that parameter SHALL flow into every resource in the stack.
3. WHEN a Lambda in the SAM_Test_Stack is deployed, THE SAM_Plane SHALL provide `APP_ENV` to that Lambda as a deploy-time environment variable, and the Lambda SHALL resolve its table prefix and identity from that `APP_ENV` value.
4. THE SAM_Plane SHALL classify `sam local` as a dev-only, out-of-scope target, parallel to the local DynamoDB emulator, and SHALL define the Test_Environment on the SAM plane as the deployed SAM_Test_Stack rather than `sam local`.
5. THE SAM_Test_Stack and the Production_Environment stack SHALL both reside in the Infra_Account (`nonprofit-deploy`, `506221081911`).

### Requirement 12: Environment-scoped Lambda execution roles

**User Story:** As a developer, I want each environment's Lambda execution role scoped by IAM so that the TEST stack's functions can reach only `test_`-prefixed tables, so that IAM — not application code — is the hard isolation boundary on the compute plane.

#### Acceptance Criteria

1. THE SAM_Test_Stack Lambda execution role SHALL be scoped by an IAM policy that restricts DynamoDB access to the resource ARN pattern `arn:aws:dynamodb:*:*:table/test_*`.
2. THE Production_Environment stack Lambda execution role SHALL be scoped by an IAM policy that restricts DynamoDB access to the unprefixed production tables.
3. IF a Lambda in the SAM_Test_Stack attempts to access an unprefixed production table, THEN THE environment-scoped execution role SHALL deny the access at the IAM layer independently of the Lambda's resolved prefix.
4. THE environment-scoped execution roles SHALL be defined within their respective SAM stacks so that each stack provisions the role matching its `APP_ENV`.

### Requirement 13: Separate TEST API Gateway endpoint

**User Story:** As a developer, I want the TEST SAM stack to expose its own API Gateway endpoint distinct from production, so that TEST clients call a TEST URL and can never reach the production compute surface by sharing an endpoint.

#### Acceptance Criteria

1. THE SAM_Test_Stack SHALL expose its own API Gateway surface — a separate REST API or at minimum a dedicated stage — with its own invoke URL distinct from the Production_Environment invoke URL.
2. THE Frontend_Plane and the Backend_Identity_Plane SHALL select the SAM API base URL from the Environment_Resolver using `APP_ENV`.
3. THE SAM API base URL SHALL NOT be hardcoded in source nor inferred from the browser hostname or any other incidental signal.
4. WHEN `APP_ENV` is `test`, THE resolved SAM API base URL SHALL be the SAM_Test_Stack invoke URL, and WHEN `APP_ENV` is `production`, THE resolved SAM API base URL SHALL be the Production_Environment invoke URL.

### Requirement 14: Authorizer pool consistency on the SAM surface

**User Story:** As a developer, I want the SAM API Gateway/Lambda authorizer to validate tokens against the Cognito pool for its own environment, so that a TEST frontend token is accepted by the TEST SAM API and rejected by PRODUCTION, closing the pool-mismatch class on the compute surface.

#### Acceptance Criteria

1. THE SAM_Plane API Gateway or Lambda authorizer SHALL validate tokens against the Cognito pool resolved from its stack's `APP_ENV`.
2. WHERE the SAM_Test_Stack is active, THE authorizer SHALL accept a token issued by the test pool `eu-west-1_xyrlzfqbl` and SHALL reject a token issued by production Pool A `eu-west-1_Hdp40eWmu`.
3. WHERE the Production_Environment stack is active, THE authorizer SHALL accept a token issued by production Pool A and SHALL reject a token issued by the test pool.
4. THE Consistency_Guard SHALL verify that the authorizer pool on the active SAM surface and the SAM API base URL the clients call both match the active `APP_ENV`.
5. IF the SAM authorizer pool or the client-called SAM API base URL does not match the active `APP_ENV`, THEN THE Consistency_Guard SHALL report the inconsistency and SHALL NOT report a consistent state.

### Requirement 15: SAM compute current-state delta

**User Story:** As a developer, I want the spec to record honestly what the SAM plane isolation looks like today versus target state, so that the implementation delta is explicit and treated as work this spec drives rather than a permanent limitation.

#### Acceptance Criteria

1. THE Environment_Definition SHALL record that the SAM_Plane's only TEST isolation today is the `test_` table prefix, with no separate TEST stack, no separate TEST API Gateway, and no per-environment execution role yet in place.
2. THE Environment_Definition SHALL record that reaching the target state requires building the SAM_Test_Stack, its API Gateway, and the per-environment Lambda execution roles.
3. THE Environment_Definition SHALL frame the SAM compute delta as the implementation this spec drives and SHALL NOT frame it as a permanent limitation or a deferral.

### Requirement 16: Explicit-request-only copy utilities

**User Story:** As an operator, I want the supported tool for making TEST contents look like production to be a deliberate, human-initiated action, so that I can populate TEST with prod-identical data when a test needs it while production is never touched by a background process and TEST never writes back to production.

#### Acceptance Criteria

1. WHERE a test requires the Environment_Contents of the Test_Environment to match the Production_Environment, THE Copy_Utility SHALL be the supported capability for populating the Test_Environment with Production_Environment data or attributes.
2. WHEN a Copy_Utility runs, THE Copy_Utility SHALL run only in response to an explicit human-initiated request.
3. THE Copy_Utility SHALL NOT run automatically, on a schedule, or as a side effect of normal running-unit startup or operation.
4. WHEN a Copy_Utility copies data, THE Copy_Utility SHALL copy only from the Production_Environment into the Test_Environment.
5. THE Copy_Utility SHALL NOT write any data from the Test_Environment toward the Production_Environment.
6. THE Copy_Utility SHALL be invoked separately from the single-environment running unit.

### Requirement 17: Repeatable test-account provisioning

**User Story:** As a developer, I want a documented, repeatable mechanism to create and seed a test user, set its password without the forced-change trap, and give it an arbitrary realistic `custom:tenants`/`custom:role` shape chosen for the test at hand, so that I stop relying on one-off AWS CLI commands and can provision whatever attribute configuration a test needs.

#### Acceptance Criteria

1. WHEN the provisioning mechanism is run for a named Test_Account, THE provisioning mechanism SHALL create the user in the test pool if the user does not already exist.
2. WHEN the provisioning mechanism sets a Test_Account password, THE provisioning mechanism SHALL leave the account in a usable state that does not require a forced password change on first sign-in.
3. WHEN the provisioning mechanism seeds a Test_Account, THE provisioning mechanism SHALL set `custom:tenants` and `custom:role` to a specified realistic shape chosen for the test, which MAY be any valid tenant/role configuration including one that does not exist in the Production_Environment.
4. WHERE the specified shape is that of a production reference account, THE provisioning mechanism SHALL mirror that account's `custom:tenants` and `custom:role` onto the Test_Account as an optional mode performed through an explicit, human-initiated Copy_Utility invocation rather than as the default behavior.
5. THE provisioning mechanism SHALL operate against the Identity_Account (`personal` profile, `344561557829`, `eu-west-1`).
6. THE provisioning mechanism SHALL NOT embed real production credentials or secrets in the repository or the spec.

### Requirement 18: Steering alignment

**User Story:** As a developer, I want the steering files that describe the environment model to match the `APP_ENV` model, so that steering is not itself a stale source of truth.

#### Acceptance Criteria

1. WHERE a steering file references the obsolete `finance`/`testfinance` schema split or the legacy `test_mode` schema switch, THE steering update SHALL replace that description with the `APP_ENV` plus resolved-database-target model (whose current operational mapping is local Docker for the TEST target and Railway for the PRODUCTION target).
2. THE steering update SHALL align `31-backend-database-flask-mysql.md`, `41-shell-environment.md`, and the `#database` skill (`.kiro/skills/database.md`) with the MySQL_Plane model that distinguishes environments by resolved target and credentials using schema name `finance`.
3. WHERE the SAM steering (`35-sam-module-architecture-sam.md`, `42-local-dynamodb-testing.md`) describes the DynamoDB or compute environment model, THE steering update SHALL align it with the `test_`-prefix plus IAM-scoping data model and the stack-per-environment compute model.
4. THE steering update SHALL NOT introduce real production credentials or secrets, using placeholders in all committed artifacts.

### Requirement 19: Safety guardrails and non-goals

**User Story:** As an operator, I want strict guardrails so that validating unmerged code can never endanger production data or leak secrets, so that the TEST environment is safe to use freely.

#### Acceptance Criteria

1. THE spec and repository SHALL NOT contain real production credentials or secrets, using placeholders in all committed artifacts.
2. THE Test_Environment configuration SHALL NOT cause the Production_Environment to depend on any test resource.
3. WHILE `APP_ENV` is `test`, THE Planes SHALL operate against test resources only — the test pool, the resolved TEST database target (schema `finance`), the resolved TEST backend host and Flask API base URL, the `test_`-prefixed DynamoDB tables, and the SAM_Test_Stack compute surface.
4. IF a Plane resolved under `APP_ENV=test` resolves to a production resource, THEN THE Consistency_Guard SHALL report the violation and SHALL NOT proceed.
5. THE local or ephemeral "dev" setups, including the local DynamoDB emulator and `sam local`, SHALL be out of scope for the Test_Environment defined by this spec.
6. WHERE a test populates the Test_Environment with Production_Environment data or attributes, THE Planes SHALL continue to operate against the test resources of the Environment_Boundary only, because the guardrails constrain the Environment_Boundary and not the Environment_Contents.

### Requirement 20: Fixed boundary, flexible contents

**User Story:** As a developer, I want the TEST environment boundary to be guaranteed fixed while its contents stay freely choosable, so that I can test prod-identical, partially-matching, or deliberately-different data and accounts without ever losing the safety of the always-TEST wiring.

#### Acceptance Criteria

1. WHILE `APP_ENV` is `test`, THE Environment_Boundary — the test Cognito pool, the resolved TEST database target, the resolved TEST backend host and Flask API base URL, the `test_`-prefixed DynamoDB tables, and the deployed SAM_Test_Stack compute surface — SHALL be fixed and SHALL NOT vary per test.
2. WHILE `APP_ENV` is `test`, THE Consistency_Guard SHALL enforce the Environment_Boundary across every Plane.
3. THE Environment_Contents within the Environment_Boundary — the Cognito accounts and their `custom:tenants`/`custom:role` attributes, the MySQL data, and the DynamoDB data — MAY be identical to the Production_Environment, partially matching, or deliberately different, as the test under consideration requires.
4. WHERE a test requires the Environment_Contents to be identical to the Production_Environment, THE Copy_Utility of Requirement 16 SHALL provide that parity as an optional capability rather than as a required or default state of the Test_Environment.
5. THE spec SHALL guarantee the Environment_Boundary and SHALL NOT require content parity between the Test_Environment and the Production_Environment.

### Requirement 21: Backend runtime host and Flask API base URL as resolved targets

**User Story:** As a developer, I want where the Flask backend runs and which Flask API the frontend calls to both be resolved from `APP_ENV` rather than hardcoded to a physical location, so that the backend host and its API base URL can be relocated as an operational change without a requirements or architecture change.

#### Acceptance Criteria

1. THE Flask backend runtime host SHALL be an environment-resolved target: WHERE `APP_ENV` is `test`, THE Backend_Runtime_Plane SHALL resolve to the resolved TEST backend host, and WHERE `APP_ENV` is `production`, THE Backend_Runtime_Plane SHALL resolve to the resolved PRODUCTION backend host, each defined by its resolved target rather than by a hardcoded physical location.
2. THE Flask API base URL that the Frontend_Plane calls SHALL be resolved from `APP_ENV` by the Environment_Resolver, parallel to the SAM API base URL of Requirement 13.
3. THE Flask API base URL SHALL NOT be hardcoded in source and SHALL NOT be inferred from the browser hostname or any other incidental signal.
4. WHEN `APP_ENV` is `test`, THE resolved Flask API base URL SHALL be the resolved TEST Flask API base URL, and WHEN `APP_ENV` is `production`, THE resolved Flask API base URL SHALL be the resolved PRODUCTION Flask API base URL.
5. THE Consistency_Guard SHALL verify that the Flask API base URL the Frontend_Plane calls matches the active `APP_ENV`, parallel to the treatment the Consistency_Guard gives the SAM API base URL and the SAM authorizer pool.
6. IF the Flask API base URL the Frontend_Plane calls does not match the active `APP_ENV`, THEN THE Consistency_Guard SHALL report the inconsistency and SHALL NOT report a consistent state.

> **Non-normative current mapping:** the resolved TEST backend host currently runs locally and the resolved PRODUCTION backend host currently runs on Railway. This records the present operational mapping only and is not the definition of either target. A future relocation — for example a hosted TEST backend host — is accommodated by changing the resolver mapping and configuration, not by changing this requirement; this requirement does not commit to any specific hosting provider.

### Requirement 22: Environment selection and access via URL and Cognito pool

**User Story:** As a developer or user, I want to reach the TEST environment by opening its distinct URL (currently `localhost:3000`) and authenticating against the test Cognito pool, so that environment choice is a deployment/entry-point decision, not an in-app toggle, and access to TEST is controlled by membership in the test pool.

#### Acceptance Criteria

1. THE Environment_Definition SHALL declare the distinct URL for the Test_Environment (for example `localhost:3000` or a hosted URL) and the distinct URL for the Production_Environment, and SHALL NOT infer `APP_ENV` from the hostname or request origin.
2. WHEN a deployment is built for the Test_Environment, THE Frontend_Plane SHALL be built with `VITE_APP_ENV=test`, and the Backend_Plane SHALL be started with `APP_ENV=test`, regardless of the hostname where that deployment is served.
3. THE Test_Environment URL SHALL authenticate users against the test Cognito pool (`eu-west-1_xyrlzfqbl`), and the Production_Environment URL SHALL authenticate against production Pool A (`eu-west-1_Hdp40eWmu`).
4. ACCESS to the Test_Environment SHALL be determined solely by account membership in the test Cognito pool; there SHALL NOT be a separate allow-list or in-app environment switch.
5. THE Environment_Indicator SHALL derive its displayed environment from the deployment's explicit `APP_ENV` (which is fixed by the build/start) and SHALL NOT infer "TEST" from the hostname being `localhost`.
6. THE Frontend_Plane SHALL NOT contain any UI control that switches the active environment within a single running unit; environment selection SHALL occur by navigating to the other environment's URL.

### Requirement 23: Branch-based promotion from TEST to PRODUCTION

**User Story:** As a developer, I want changes to land in TEST first (via a TEST-targeted branch), be validated there, and then be promoted to PRODUCTION (via a PRODUCTION-targeted branch), so that the environment selection maps directly to the Git branch and deployment pipeline.

#### Acceptance Criteria

1. THE Environment_Definition SHALL record that the Test_Environment deployment is sourced from a Git branch designated for TEST (for example `test`, `develop`, or `staging`), and the Production_Environment deployment is sourced from a branch designated for PRODUCTION (for example `main`).
2. THE CI/CD pipeline SHALL set `APP_ENV` to `test` when deploying the TEST branch and to `production` when deploying the PRODUCTION branch.
3. A pull request merging into the TEST branch SHALL cause a deployment to the Test_Environment (where the change can be validated against the TEST Cognito pool, TEST database target, and TEST SAM stack).
4. AFTER validation in the Test_Environment, a pull request merging the validated changes from the TEST branch into the PRODUCTION branch SHALL cause a deployment to the Production_Environment.
5. THE Environment_Definition SHALL record that the branch-to-environment mapping is a CI/CD pipeline configuration separate from the application source, so that the mapping can evolve without changing the spec.