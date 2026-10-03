"""Unit tests for the Environment_Resolver (single decision point mapping APP_ENV to per-plane configuration)."""

import pytest
from dataclasses import FrozenInstanceError

from environment.app_env import AppEnv
from environment.environment_definition import (
    EnvironmentDefinition,
    CognitoDef,
    MysqlDef,
    SamDef,
    PlaneDef,
)
from environment.resolver import (
    ResolvedConfig,
    ResolvedCognito,
    ResolvedDbTarget,
    ResolvedSam,
    resolve,
)


class TestResolvedDataclasses:
    """Test the resolved dataclasses (immutability, convenience properties)."""

    def test_resolved_cognito_is_frozen(self) -> None:
        """ResolvedCognito dataclass should be frozen (immutable)."""
        cognito = ResolvedCognito(
            pool_id="test-pool",
            client_id="test-client",
            client_secret_ref="",
            pool_label="test",
            registry_keys_env_var="COGNITO_POOL_KEYS",
        )
        # Should not be able to modify attributes
        with pytest.raises(FrozenInstanceError):
            cognito.pool_id = "new-pool"

    def test_resolved_db_target_is_frozen(self) -> None:
        """ResolvedDbTarget dataclass should be frozen (immutable)."""
        db_target = ResolvedDbTarget(
            target_label="TEST",
            schema="finance",
            host_ref="DB_HOST_TEST",
            port_ref="DB_PORT_TEST",
            user_ref="DB_USER_TEST",
            password_ref="DB_PASSWORD_TEST",
        )
        with pytest.raises(FrozenInstanceError):
            db_target.target_label = "PRODUCTION"

    def test_resolved_sam_is_frozen(self) -> None:
        """ResolvedSam dataclass should be frozen (immutable)."""
        sam = ResolvedSam(
            stack_name="myAdmin-test",
            api_base_url="https://test-api.execute-api.eu-west-1.amazonaws.com/Prod",
            table_prefix="test_",
            exec_role_scope="arn:aws:dynamodb:*:*:table/test_*",
            authorizer_pool_id="test-pool",
        )
        with pytest.raises(FrozenInstanceError):
            sam.table_prefix = "prod_"

    def test_resolved_config_is_frozen(self) -> None:
        """ResolvedConfig dataclass should be frozen (immutable)."""
        config = ResolvedConfig(
            app_env=AppEnv.TEST,
            cognito=ResolvedCognito(
                pool_id="test-pool",
                client_id="test-client",
                client_secret_ref="",
                pool_label="test",
            ),
            mysql=ResolvedDbTarget(
                target_label="TEST",
                schema="finance",
                host_ref="DB_HOST_TEST",
                port_ref="DB_PORT_TEST",
                user_ref="DB_USER_TEST",
                password_ref="DB_PASSWORD_TEST",
            ),
            backend_host_ref="BACKEND_HOST_TEST",
            flask_api_base_url="http://localhost:5000",
            sam=ResolvedSam(
                stack_name="myAdmin-test",
                api_base_url="https://test-api.execute-api.eu-west-1.amazonaws.com/Prod",
                table_prefix="test_",
                exec_role_scope="arn:aws:dynamodb:*:*:table/test_*",
                authorizer_pool_id="test-pool",
            ),
            test_url="localhost:3000",
            production_url="app.myadmin.jabaki.nl",
        )
        with pytest.raises(FrozenInstanceError):
            config.flask_api_base_url = "http://new-url"

    def test_resolved_config_convenience_properties(self) -> None:
        """ResolvedConfig convenience properties should return correct values."""
        sam = ResolvedSam(
            stack_name="myAdmin-test",
            api_base_url="https://test-api.execute-api.eu-west-1.amazonaws.com/Prod",
            table_prefix="test_",
            exec_role_scope="arn:aws:dynamodb:*:*:table/test_*",
            authorizer_pool_id="test-pool-id",
        )
        config = ResolvedConfig(
            app_env=AppEnv.TEST,
            cognito=ResolvedCognito(
                pool_id="test-pool",
                client_id="test-client",
                client_secret_ref="",
                pool_label="test",
            ),
            mysql=ResolvedDbTarget(
                target_label="TEST",
                schema="finance",
                host_ref="DB_HOST_TEST",
                port_ref="DB_PORT_TEST",
                user_ref="DB_USER_TEST",
                password_ref="DB_PASSWORD_TEST",
            ),
            backend_host_ref="BACKEND_HOST_TEST",
            flask_api_base_url="http://localhost:5000",
            sam=sam,
            test_url="localhost:3000",
            production_url="app.myadmin.jabaki.nl",
        )

        assert config.dynamodb_prefix == "test_"
        assert config.sam_api_base_url == "https://test-api.execute-api.eu-west-1.amazonaws.com/Prod"
        assert config.sam_authorizer_pool_id == "test-pool-id"
        assert config.sam_stack_label == "myAdmin-test"


class TestResolveFunction:
    """Test the resolve() function (single decision point)."""

    def create_test_definition(self) -> EnvironmentDefinition:
        """Create a minimal test EnvironmentDefinition."""
        return EnvironmentDefinition(
            test=PlaneDef(
                cognito=CognitoDef(
                    pool_id="test-pool",
                    client_id="test-client",
                    client_secret_ref="",
                    pool_label="myAdmin-test",
                ),
                mysql=MysqlDef(
                    target_label="TEST",
                    schema="finance",
                    host_ref="DB_HOST_TEST",
                    port_ref="DB_PORT_TEST",
                    user_ref="DB_USER_TEST",
                    password_ref="DB_PASSWORD_TEST",
                ),
                backend_host_ref="BACKEND_HOST_TEST",
                flask_api_base_url="http://localhost:5000",
                sam=SamDef(
                    stack_name="myAdmin-test",
                    api_base_url="https://test-api.execute-api.eu-west-1.amazonaws.com/Prod",
                    table_prefix="test_",
                    exec_role_scope="arn:aws:dynamodb:*:*:table/test_*",
                    authorizer_pool_id="test-pool",
                ),
            ),
            production=PlaneDef(
                cognito=CognitoDef(
                    pool_id="prod-pool",
                    client_id="prod-client",
                    client_secret_ref="PLACEHOLDER_CLIENT_SECRET",
                    pool_label="myAdmin",
                ),
                mysql=MysqlDef(
                    target_label="PRODUCTION",
                    schema="finance",
                    host_ref="DB_HOST",
                    port_ref="DB_PORT",
                    user_ref="DB_USER",
                    password_ref="DB_PASSWORD",
                ),
                backend_host_ref="BACKEND_HOST_PROD",
                flask_api_base_url="https://prod-api.example.com",
                sam=SamDef(
                    stack_name="myAdmin-prod",
                    api_base_url="https://prod-api.execute-api.eu-west-1.amazonaws.com/Prod",
                    table_prefix="",
                    exec_role_scope="arn:aws:dynamodb:*:*:table/*",
                    authorizer_pool_id="prod-pool",
                ),
            ),
            test_url="localhost:3000",
            production_url="app.example.com",
            test_branch="test",
            production_branch="main",
        )

    def test_resolve_test_environment(self) -> None:
        """resolve() with AppEnv.TEST should return TEST configuration."""
        definition = self.create_test_definition()
        config = resolve(AppEnv.TEST, definition)

        assert config.app_env == AppEnv.TEST
        assert config.cognito.pool_id == "test-pool"
        assert config.cognito.client_id == "test-client"
        assert config.cognito.client_secret_ref == ""  # test pool has no secret
        assert config.cognito.pool_label == "myAdmin-test"
        assert config.cognito.registry_keys_env_var == "COGNITO_POOL_KEYS"

        assert config.mysql.target_label == "TEST"
        assert config.mysql.schema == "finance"
        assert config.mysql.host_ref == "DB_HOST_TEST"
        assert config.mysql.user_ref == "DB_USER_TEST"

        assert config.backend_host_ref == "BACKEND_HOST_TEST"
        assert config.flask_api_base_url == "http://localhost:5000"

        assert config.sam.stack_name == "myAdmin-test"
        assert config.sam.table_prefix == "test_"
        assert config.sam.exec_role_scope == "arn:aws:dynamodb:*:*:table/test_*"
        assert config.sam.authorizer_pool_id == "test-pool"

        assert config.test_url == "localhost:3000"
        assert config.production_url == "app.example.com"
        assert config.test_branch == "test"
        assert config.production_branch == "main"

    def test_resolve_production_environment(self) -> None:
        """resolve() with AppEnv.PRODUCTION should return PRODUCTION configuration."""
        definition = self.create_test_definition()
        config = resolve(AppEnv.PRODUCTION, definition)

        assert config.app_env == AppEnv.PRODUCTION
        assert config.cognito.pool_id == "prod-pool"
        assert config.cognito.client_id == "prod-client"
        assert config.cognito.client_secret_ref == "PLACEHOLDER_CLIENT_SECRET"
        assert config.cognito.pool_label == "myAdmin"

        assert config.mysql.target_label == "PRODUCTION"
        assert config.mysql.schema == "finance"
        assert config.mysql.host_ref == "DB_HOST"
        assert config.mysql.user_ref == "DB_USER"

        assert config.backend_host_ref == "BACKEND_HOST_PROD"
        assert config.flask_api_base_url == "https://prod-api.example.com"

        assert config.sam.stack_name == "myAdmin-prod"
        assert config.sam.table_prefix == ""  # empty prefix for production
        assert config.sam.exec_role_scope == "arn:aws:dynamodb:*:*:table/*"
        assert config.sam.authorizer_pool_id == "prod-pool"

        assert config.test_url == "localhost:3000"
        assert config.production_url == "app.example.com"
        assert config.test_branch == "test"
        assert config.production_branch == "main"

    def test_resolve_deterministic(self) -> None:
        """resolve() should be deterministic: same input → same output."""
        definition = self.create_test_definition()
        
        config1 = resolve(AppEnv.TEST, definition)
        config2 = resolve(AppEnv.TEST, definition)
        
        # Compare key attributes
        assert config1.app_env == config2.app_env
        assert config1.cognito.pool_id == config2.cognito.pool_id
        assert config1.sam.table_prefix == config2.sam.table_prefix
        assert config1.flask_api_base_url == config2.flask_api_base_url

    def test_resolve_test_vs_production_different(self) -> None:
        """TEST and PRODUCTION configurations should be distinct."""
        definition = self.create_test_definition()
        
        test_config = resolve(AppEnv.TEST, definition)
        prod_config = resolve(AppEnv.PRODUCTION, definition)
        
        # Key differences
        assert test_config.cognito.pool_id != prod_config.cognito.pool_id
        assert test_config.sam.table_prefix == "test_"
        assert prod_config.sam.table_prefix == ""
        assert test_config.mysql.host_ref == "DB_HOST_TEST"
        assert prod_config.mysql.host_ref == "DB_HOST"
        assert test_config.flask_api_base_url != prod_config.flask_api_base_url

    def test_resolve_test_pool_empty_secret(self) -> None:
        """TEST pool should have empty client secret."""
        definition = self.create_test_definition()
        config = resolve(AppEnv.TEST, definition)
        assert config.cognito.client_secret_ref == ""

    def test_resolve_production_pool_has_secret_ref(self) -> None:
        """PRODUCTION pool should have a secret reference (placeholder)."""
        definition = self.create_test_definition()
        config = resolve(AppEnv.PRODUCTION, definition)
        assert config.cognito.client_secret_ref == "PLACEHOLDER_CLIENT_SECRET"

    def test_resolve_urls_present_in_both(self) -> None:
        """Both TEST and PRODUCTION configs should have test_url and production_url."""
        definition = self.create_test_definition()
        
        test_config = resolve(AppEnv.TEST, definition)
        prod_config = resolve(AppEnv.PRODUCTION, definition)
        
        assert test_config.test_url == "localhost:3000"
        assert test_config.production_url == "app.example.com"
        assert prod_config.test_url == "localhost:3000"
        assert prod_config.production_url == "app.example.com"

    def test_resolve_branches_present(self) -> None:
        """Both TEST and PRODUCTION configs should have branch info."""
        definition = self.create_test_definition()
        
        test_config = resolve(AppEnv.TEST, definition)
        prod_config = resolve(AppEnv.PRODUCTION, definition)
        
        assert test_config.test_branch == "test"
        assert test_config.production_branch == "main"
        assert prod_config.test_branch == "test"
        assert prod_config.production_branch == "main"

    def test_resolve_with_minimal_definition(self) -> None:
        """Should work with minimal definition (no optional branches)."""
        definition = EnvironmentDefinition(
            test=PlaneDef(
                cognito=CognitoDef(
                    pool_id="test-pool",
                    client_id="test-client",
                    client_secret_ref="",
                    pool_label="test",
                ),
                mysql=MysqlDef(
                    target_label="TEST",
                    schema="finance",
                    host_ref="DB_HOST_TEST",
                    port_ref="DB_PORT_TEST",
                    user_ref="DB_USER_TEST",
                    password_ref="DB_PASSWORD_TEST",
                ),
                backend_host_ref="BACKEND_HOST_TEST",
                flask_api_base_url="http://localhost:5000",
                sam=SamDef(
                    stack_name="myAdmin-test",
                    api_base_url="https://test-api.execute-api.eu-west-1.amazonaws.com/Prod",
                    table_prefix="test_",
                    exec_role_scope="arn:aws:dynamodb:*:*:table/test_*",
                    authorizer_pool_id="test-pool",
                ),
            ),
            production=PlaneDef(
                cognito=CognitoDef(
                    pool_id="prod-pool",
                    client_id="prod-client",
                    client_secret_ref="PLACEHOLDER",
                    pool_label="prod",
                ),
                mysql=MysqlDef(
                    target_label="PRODUCTION",
                    schema="finance",
                    host_ref="DB_HOST",
                    port_ref="DB_PORT",
                    user_ref="DB_USER",
                    password_ref="DB_PASSWORD",
                ),
                backend_host_ref="BACKEND_HOST_PROD",
                flask_api_base_url="https://prod.example.com",
                sam=SamDef(
                    stack_name="myAdmin-prod",
                    api_base_url="https://prod-api.execute-api.eu-west-1.amazonaws.com/Prod",
                    table_prefix="",
                    exec_role_scope="arn:aws:dynamodb:*:*:table/*",
                    authorizer_pool_id="prod-pool",
                ),
            ),
            test_url="localhost:3000",
            production_url="app.example.com",
            test_branch=None,  # Optional
            production_branch=None,  # Optional
        )
        
        test_config = resolve(AppEnv.TEST, definition)
        prod_config = resolve(AppEnv.PRODUCTION, definition)
        
        assert test_config.app_env == AppEnv.TEST
        assert prod_config.app_env == AppEnv.PRODUCTION
        assert test_config.test_branch is None
        assert test_config.production_branch is None
        assert prod_config.test_branch is None
        assert prod_config.production_branch is None