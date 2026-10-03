"""
Environment_Definition — the single documented source of truth for the environment
configuration across every plane.

S3 / T1.3 — Define the EnvironmentDefinition dataclass with placeholders for all planes.
This is the committed source of truth that declares, per plane, the TEST and PRODUCTION
configuration values derived from APP_ENV via the Environment_Resolver.

Design contract (see `.kiro/specs/Common/test-environment/first-draft/design.md`):

- Declare TEST and PRODUCTION configuration per plane: Frontend, Backend_Identity,
  MySQL, Backend_Runtime, SAM_Data, SAM_Compute.
- Use placeholders for secrets (never real values in committed artifacts — Req 3.6).
- Record Cognito pool identifiers, app-client identifiers (public only).
- Record resolved TEST/PRODUCTION database targets (schema `finance` for both).
- Record SAM plane configuration: stack names, API Gateway URLs, DynamoDB prefixes.
- Record Flask API base URL and SAM API base URL.
- Include `TEST_URL` and `PROD_URL` fields (Req 22).
- Include `test_branch` and `production_branch` fields (Req 23).
- Include current operational mappings as comments (non-normative).
- All dataclasses are frozen (immutable) for safety.

The resolver (T1.4) will read this definition and produce a ResolvedConfig for the
active APP_ENV.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class CognitoDef:
    """Cognito identity plane configuration for a single environment.

    Contains public pool and client identifiers; the client secret is a placeholder
    reference (never the real value in the committed source).

    Attributes:
        pool_id: The Cognito User Pool ID (public identifier).
        client_id: The Cognito App Client ID (public identifier).
        client_secret_ref: Reference to the client secret (placeholder/env var).
            For the test pool this should be empty string (no secret).
        pool_label: Human-readable pool label (e.g., "myAdmin-test", "myAdmin").
    """

    pool_id: str
    client_id: str
    client_secret_ref: str  # placeholder/secret-ref, never the value
    pool_label: str


@dataclass(frozen=True)
class MysqlDef:
    """MySQL plane configuration for a single environment.

    Defines the resolved database target (TEST or PRODUCTION) with schema `finance`.
    All connection values are references to environment variables (never hardcoded
    credentials). The target is defined by its resolved identity and credentials,
    not by physical hosting location.

    Attributes:
        target_label: Label for this target ("TEST" | "PRODUCTION").
        schema: Always "finance" for both environments.
        host_ref: Environment variable name for the database host.
        port_ref: Environment variable name for the database port.
        user_ref: Environment variable name for the database user.
        password_ref: Environment variable name for the database password.
    """

    target_label: str  # "TEST" | "PRODUCTION"
    schema: str  # always "finance"
    host_ref: str
    port_ref: str
    user_ref: str
    password_ref: str


@dataclass(frozen=True)
class SamDef:
    """SAM plane configuration for a single environment.

    Defines the SAM compute stack, its API Gateway, execution role scope,
    DynamoDB prefix, and authorizer pool.

    Attributes:
        stack_name: The deployed SAM/CloudFormation stack name.
        api_base_url: The API Gateway invoke URL for this environment.
        table_prefix: DynamoDB table prefix ("test_" for TEST, "" for PRODUCTION).
        exec_role_scope: IAM resource ARN pattern for DynamoDB access
            (e.g., "arn:aws:dynamodb:*:*:table/test_*" for TEST, unprefixed for PROD).
        authorizer_pool_id: Cognito pool ID that the SAM authorizer validates against.
    """

    stack_name: str
    api_base_url: str
    table_prefix: str  # "test_" | ""
    exec_role_scope: str
    authorizer_pool_id: str


@dataclass(frozen=True)
class PlaneDef:
    """Complete per-plane configuration for a single environment.

    Aggregates all plane-specific configurations that are resolved from APP_ENV.

    Attributes:
        cognito: Cognito identity configuration.
        mysql: MySQL database target configuration.
        backend_host_ref: Environment variable reference for the Flask backend
            runtime host (where the Flask process runs).
        flask_api_base_url: The Flask API base URL that the frontend calls.
        sam: SAM compute plane configuration.
    """

    cognito: CognitoDef
    mysql: MysqlDef
    backend_host_ref: str
    flask_api_base_url: str
    sam: SamDef


@dataclass(frozen=True)
class EnvironmentDefinition:
    """The single documented source of truth for environment configuration.

    Contains both TEST and PRODUCTION PlaneDef configurations, plus operational
    deployment mappings (URLs and branch mapping for CI/CD).

    Attributes:
        test: TEST environment configuration (APP_ENV=test).
        production: PRODUCTION environment configuration (APP_ENV=production).
        test_url: Distinct URL where the Test_Environment deployment is served
            (e.g., "localhost:3000" or a hosted URL). Authenticates against the
            test Cognito pool.
        production_url: Distinct URL where the Production_Environment deployment
            is served (e.g., "app.myadmin.jabaki.nl"). Authenticates against
            production Pool A.
        test_branch: Git branch designated for TEST deployments (e.g., "test",
            "develop", or None if not recorded).
        production_branch: Git branch designated for PRODUCTION deployments
            (e.g., "main", or None if not recorded).
    """

    test: PlaneDef
    production: PlaneDef
    test_url: str
    production_url: str
    test_branch: Optional[str]
    production_branch: Optional[str]


# -----------------------------------------------------------------------------
# Concrete definition — the single source of truth
# -----------------------------------------------------------------------------

# Public identifiers (non-secret)
TEST_POOL_ID = "eu-west-1_xyrlzfqbl"
TEST_CLIENT_ID = "43s15cm8qcgg8an85udt0e087u"
PROD_POOL_ID = "eu-west-1_Hdp40eWmu"
# PROD_CLIENT_ID — the production Cognito app client id. PUBLIC, non-secret
# identifier (like the pool ids above); the app-client SECRET is NOT stored here
# (read from the COGNITO_CLIENT_SECRET env var). The startup Consistency_Guard
# compares the service's COGNITO_CLIENT_ID against this value, so it must be the
# real id (not a placeholder) or production fails fast at startup.
PROD_CLIENT_ID = "66tp0087h9tfbstggonnu5aghp"

ENVIRONMENT_DEFINITION = EnvironmentDefinition(
    test=PlaneDef(
        cognito=CognitoDef(
            pool_id=TEST_POOL_ID,
            client_id=TEST_CLIENT_ID,
            client_secret_ref="",  # test pool has no client secret
            pool_label="myAdmin-test",
        ),
        mysql=MysqlDef(
            target_label="TEST",
            schema="finance",
            host_ref="DB_HOST_TEST",  # env var for TEST database host
            port_ref="DB_PORT_TEST",  # env var for TEST database port
            user_ref="DB_USER_TEST",  # env var for TEST database user
            password_ref="DB_PASSWORD_TEST",  # env var for TEST database password
        ),
        backend_host_ref="BACKEND_HOST_TEST",  # env var for TEST backend host
        flask_api_base_url="http://localhost:5000",  # current TEST Flask API URL
        # SAM plane is per MODULE; this SamDef records the members module (the one
        # with an HTTP API). stack_name is the members TEST stack (CFN stack name
        # `test-sam-members`; the DynamoDB table is `test_sam-members`). The TEST API
        # base URL below is the live MembersApiBaseUrl output of the first
        # `test-sam-members` deploy (Phase 5a Task 35).
        sam=SamDef(
            stack_name="test-sam-members",
            api_base_url="https://28jun82vl3.execute-api.eu-west-1.amazonaws.com/test",
            table_prefix="test_",
            exec_role_scope="arn:aws:dynamodb:*:*:table/test_*",
            authorizer_pool_id=TEST_POOL_ID,
        ),
    ),
    production=PlaneDef(
        cognito=CognitoDef(
            pool_id=PROD_POOL_ID,
            client_id=PROD_CLIENT_ID,
            client_secret_ref="PLACEHOLDER_CLIENT_SECRET",  # SECRET reference only —
            # the real value lives in the COGNITO_CLIENT_SECRET env var; it MUST stay a
            # placeholder in committed source (Req 3.6 / 19.1). Never fill this in.
            pool_label="myAdmin",
        ),
        mysql=MysqlDef(
            target_label="PRODUCTION",
            schema="finance",
            host_ref="DB_HOST",  # env var for PRODUCTION database host
            port_ref="DB_PORT",  # env var for PRODUCTION database port
            user_ref="DB_USER",  # env var for PRODUCTION database user
            password_ref="DB_PASSWORD",  # env var for PRODUCTION database password
        ),
        backend_host_ref="BACKEND_HOST_PROD",  # env var for PRODUCTION backend host
        # PROD Flask API base URL — a Railway-managed RUNTIME value, NOT a committed
        # literal (the frontend calls the backend via the VITE_API_URL GitHub/Railway
        # secret, and nothing reads THIS field as a live endpoint — only the
        # Consistency_Guard uses it, for TEST!=PROD distinctness). So this is an
        # explicit REFERENCE marker, deliberately not a real hostname (Phase 6 Task 42,
        # Option A; keeps runtime config in Railway, per Req 3.6 / 19.1).
        flask_api_base_url="railway-managed://VITE_API_URL",
        # SAM plane is per MODULE; this SamDef records the members module (the one
        # with an HTTP API). stack_name is the members PROD stack; pretokengen's
        # stacks are recorded in the current-mapping notes below.
        sam=SamDef(
            stack_name="sam-members",
            api_base_url="https://22x6z55301.execute-api.eu-west-1.amazonaws.com/prod",
            table_prefix="",
            exec_role_scope="arn:aws:dynamodb:*:*:table/*",  # unprefixed tables
            authorizer_pool_id=PROD_POOL_ID,
        ),
    ),
    test_url="localhost:3000",
    production_url="app.myadmin.jabaki.nl",
    test_branch="test",
    production_branch="main",
)

# -----------------------------------------------------------------------------
# Non-normative current mapping notes
# -----------------------------------------------------------------------------

# Current operational mappings (recorded for context, not part of the definition):
#
# MySQL plane:
# - TEST target: local Docker MySQL instance (schema finance)
# - PRODUCTION target: Railway (schema finance)
#
# Backend_Runtime plane:
# - TEST host: local (where the Flask process runs)
# - PRODUCTION host: Railway
#
# SAM plane current-state delta:
# - Today the SAM plane's only TEST isolation is the `test_` table prefix
# - No separate TEST stack, TEST API Gateway, or per-environment execution roles yet
# - Building the SAM_Test_Stack, its API Gateway, and per-environment roles is
#   implementation work driven by this spec
#
# URL mapping:
# - TEST_URL: localhost:3000 (serves the test deployment)
# - PROD_URL: app.myadmin.jabaki.nl (serves the production deployment)
#
# Branch mapping:
# - test_branch: "test" (deploys to Test_Environment)
# - production_branch: "main" (deploys to Production_Environment)
#
# Secrets guardrail:
# - All secret values (client secrets, DB passwords) are placeholders in this
#   committed source. Real values are supplied via environment variables at
#   deployment/runtime.