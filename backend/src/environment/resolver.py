"""
Environment_Resolver — the single decision point mapping APP_ENV to per-plane configuration.

S3 / T1.4 — Implement the central Environment_Resolver that maps APP_ENV to concrete
per-plane configuration. This module realizes the "one decision, many consumers"
principle from the design.

The Environment_Resolver is the single decision contract (Requirements 2.1-2.5):
- It is the single location in which APP_ENV is mapped to per-plane values (Req 2.4)
- It never consults hostname or incidental signals (Req 1.4)
- It reads values from the Environment_Definition (Req 3.1-3.6)
- It produces one resolved per-plane configuration derived from APP_ENV (Req 2.1)

Design contract (see `.kiro/specs/Common/test-environment/first-draft/design.md`):

- The resolver is the single decision contract: `resolve(app_env, definition) -> ResolvedConfig`
- `ResolvedConfig` includes all resolved per-plane values: app_env, cognito, mysql,
  backend_host, flask_api_base_url, sam_api_base_url, dynamodb_prefix,
  sam_authorizer_pool_id, sam_stack_label (Requirements 2.2, 8, 9, 10, 21)
- Nested dataclasses for each plane: ResolvedCognito, ResolvedDbTarget, etc.
- The resolver reads values from EnvironmentDefinition, selecting TEST or PRODUCTION
  based on AppEnv.
- All dataclasses are frozen (immutable) for safety.
- The resolver should work with placeholders for secrets (the definition contains
  references to env vars, not real values) (Req 3.6).

Implementation note: The resolver does NOT read environment variables itself — it
returns references (env var names) for secrets. Actual credential resolution happens
at the consumption point (e.g., DatabaseManager reads the referenced env vars).
"""

from dataclasses import dataclass

from .app_env import AppEnv
from .environment_definition import EnvironmentDefinition


@dataclass(frozen=True)
class ResolvedCognito:
    """Resolved Cognito identity configuration for the active environment.

    Attributes:
        pool_id: Cognito User Pool ID (public identifier).
        client_id: Cognito App Client ID (public identifier).
        client_secret_ref: Reference to the client secret (env var name or empty).
        pool_label: Human-readable pool label (e.g., "myAdmin-test", "myAdmin").
        registry_keys_env_var: Environment variable name containing the pool registry
            keys (`COGNITO_POOL_KEYS`). The registry should include this pool.
    """

    pool_id: str
    client_id: str
    client_secret_ref: str
    pool_label: str
    registry_keys_env_var: str = "COGNITO_POOL_KEYS"


@dataclass(frozen=True)
class ResolvedDbTarget:
    """Resolved MySQL database target for the active environment.

    Attributes:
        target_label: "TEST" or "PRODUCTION".
        schema: Always "finance".
        host_ref: Environment variable name for database host.
        port_ref: Environment variable name for database port.
        user_ref: Environment variable name for database user.
        password_ref: Environment variable name for database password.
    """

    target_label: str
    schema: str
    host_ref: str
    port_ref: str
    user_ref: str
    password_ref: str


@dataclass(frozen=True)
class ResolvedSam:
    """Resolved SAM plane configuration for the active environment.

    Attributes:
        stack_name: Deployed SAM/CloudFormation stack name.
        api_base_url: API Gateway invoke URL.
        table_prefix: DynamoDB table prefix ("test_" for TEST, "" for PRODUCTION).
        exec_role_scope: IAM resource ARN pattern for DynamoDB access.
        authorizer_pool_id: Cognito pool ID that the SAM authorizer validates against.
    """

    stack_name: str
    api_base_url: str
    table_prefix: str
    exec_role_scope: str
    authorizer_pool_id: str


@dataclass(frozen=True)
class ResolvedConfig:
    """Complete resolved configuration for the active environment.

    This is the output of the Environment_Resolver — the single coherent per-plane
    configuration derived from APP_ENV. Every plane consumes values from this
    dataclass rather than reading raw environment variables or hostname.

    Attributes:
        app_env: The active AppEnv (TEST or PRODUCTION).
        cognito: Resolved Cognito identity configuration.
        mysql: Resolved MySQL database target.
        backend_host_ref: Environment variable reference for the Flask backend
            runtime host (where the Flask process runs).
        flask_api_base_url: The Flask API base URL that the frontend calls.
        sam: Resolved SAM compute plane configuration.
        test_url: Distinct URL for the Test_Environment (from definition).
        production_url: Distinct URL for the Production_Environment (from definition).
        test_branch: Git branch designated for TEST deployments (optional).
        production_branch: Git branch designated for PRODUCTION deployments (optional).
    """

    app_env: AppEnv
    cognito: ResolvedCognito
    mysql: ResolvedDbTarget
    backend_host_ref: str
    flask_api_base_url: str
    sam: ResolvedSam
    test_url: str
    production_url: str
    test_branch: str | None = None
    production_branch: str | None = None

    @property
    def dynamodb_prefix(self) -> str:
        """Convenience property: DynamoDB table prefix."""
        return self.sam.table_prefix

    @property
    def sam_api_base_url(self) -> str:
        """Convenience property: SAM API Gateway invoke URL."""
        return self.sam.api_base_url

    @property
    def sam_authorizer_pool_id(self) -> str:
        """Convenience property: SAM authorizer Cognito pool ID."""
        return self.sam.authorizer_pool_id

    @property
    def sam_stack_label(self) -> str:
        """Convenience property: SAM stack name/label."""
        return self.sam.stack_name


def resolve(app_env: AppEnv, definition: EnvironmentDefinition) -> ResolvedConfig:
    """Resolve APP_ENV to a complete per-plane configuration.

    This is the central Environment_Resolver — the single decision point mapping
    APP_ENV to concrete per-plane values (Requirements 2.1-2.5). It is the single
    location in which APP_ENV is mapped to per-plane configuration (Req 2.4).

    The resolver:
    1. Selects either the TEST or PRODUCTION configuration from the
       EnvironmentDefinition based on APP_ENV
    2. Converts definition dataclasses to resolved dataclasses
    3. Returns a complete ResolvedConfig with all per-plane values

    The resolver is deterministic: same input → same output. It never consults
    hostname or incidental signals (Req 1.4); all values come from the definition.

    Args:
        app_env: The active AppEnv (TEST or PRODUCTION).
        definition: The EnvironmentDefinition containing TEST and PRODUCTION
            configuration for all planes.

    Returns:
        ResolvedConfig with all per-plane values resolved for the given app_env.

    Raises:
        ValueError: If the definition is malformed or missing required configuration.
    """
    # Select the appropriate plane definition based on APP_ENV
    if app_env == AppEnv.TEST:
        plane_def = definition.test
    else:  # AppEnv.PRODUCTION
        plane_def = definition.production

    # Convert CognitoDef to ResolvedCognito
    cognito_def = plane_def.cognito
    resolved_cognito = ResolvedCognito(
        pool_id=cognito_def.pool_id,
        client_id=cognito_def.client_id,
        client_secret_ref=cognito_def.client_secret_ref,
        pool_label=cognito_def.pool_label,
        registry_keys_env_var="COGNITO_POOL_KEYS",
    )

    # Convert MysqlDef to ResolvedDbTarget
    mysql_def = plane_def.mysql
    resolved_mysql = ResolvedDbTarget(
        target_label=mysql_def.target_label,
        schema=mysql_def.schema,
        host_ref=mysql_def.host_ref,
        port_ref=mysql_def.port_ref,
        user_ref=mysql_def.user_ref,
        password_ref=mysql_def.password_ref,
    )

    # Convert SamDef to ResolvedSam
    sam_def = plane_def.sam
    resolved_sam = ResolvedSam(
        stack_name=sam_def.stack_name,
        api_base_url=sam_def.api_base_url,
        table_prefix=sam_def.table_prefix,
        exec_role_scope=sam_def.exec_role_scope,
        authorizer_pool_id=sam_def.authorizer_pool_id,
    )

    # Build the complete ResolvedConfig
    return ResolvedConfig(
        app_env=app_env,
        cognito=resolved_cognito,
        mysql=resolved_mysql,
        backend_host_ref=plane_def.backend_host_ref,
        flask_api_base_url=plane_def.flask_api_base_url,
        sam=resolved_sam,
        test_url=definition.test_url,
        production_url=definition.production_url,
        test_branch=definition.test_branch,
        production_branch=definition.production_branch,
    )
