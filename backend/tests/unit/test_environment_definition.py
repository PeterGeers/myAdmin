"""Unit tests for the Environment_Definition dataclass.

Tests the single documented source of truth for environment configuration across
every plane, with placeholders for all secrets as required.
"""

import pytest

from environment.environment_definition import (
    CognitoDef,
    MysqlDef,
    SamDef,
    PlaneDef,
    EnvironmentDefinition,
    ENVIRONMENT_DEFINITION,
    TEST_POOL_ID,
    TEST_CLIENT_ID,
    PROD_POOL_ID,
    PROD_CLIENT_ID,
)


class TestCognitoDef:
    """Test the CognitoDef dataclass structure and invariants."""

    def test_cognito_def_is_frozen(self) -> None:
        """CognitoDef instances should be immutable (frozen dataclass)."""
        cognito = CognitoDef(
            pool_id="test-pool",
            client_id="test-client",
            client_secret_ref="",
            pool_label="Test Pool",
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            cognito.pool_id = "modified"

    def test_cognito_def_fields(self) -> None:
        """CognitoDef should have all required fields with correct types."""
        cognito = CognitoDef(
            pool_id="eu-west-1_abc123",
            client_id="client123",
            client_secret_ref="PLACEHOLDER_SECRET",
            pool_label="myAdmin-test",
        )
        assert cognito.pool_id == "eu-west-1_abc123"
        assert cognito.client_id == "client123"
        assert cognito.client_secret_ref == "PLACEHOLDER_SECRET"
        assert cognito.pool_label == "myAdmin-test"


class TestMysqlDef:
    """Test the MysqlDef dataclass structure and invariants."""

    def test_mysql_def_is_frozen(self) -> None:
        """MysqlDef instances should be immutable (frozen dataclass)."""
        mysql = MysqlDef(
            target_label="TEST",
            schema="finance",
            host_ref="DB_HOST_TEST",
            port_ref="DB_PORT_TEST",
            user_ref="DB_USER_TEST",
            password_ref="DB_PASSWORD_TEST",
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            mysql.schema = "modified"

    def test_mysql_def_fields(self) -> None:
        """MysqlDef should have all required fields with correct types."""
        mysql = MysqlDef(
            target_label="PRODUCTION",
            schema="finance",
            host_ref="DB_HOST",
            port_ref="DB_PORT",
            user_ref="DB_USER",
            password_ref="DB_PASSWORD",
        )
        assert mysql.target_label == "PRODUCTION"
        assert mysql.schema == "finance"
        assert mysql.host_ref == "DB_HOST"
        assert mysql.port_ref == "DB_PORT"
        assert mysql.user_ref == "DB_USER"
        assert mysql.password_ref == "DB_PASSWORD"

    def test_schema_always_finance(self) -> None:
        """Schema should always be 'finance' for both TEST and PRODUCTION."""
        test_mysql = MysqlDef(
            target_label="TEST",
            schema="finance",
            host_ref="DB_HOST_TEST",
            port_ref="DB_PORT_TEST",
            user_ref="DB_USER_TEST",
            password_ref="DB_PASSWORD_TEST",
        )
        prod_mysql = MysqlDef(
            target_label="PRODUCTION",
            schema="finance",
            host_ref="DB_HOST",
            port_ref="DB_PORT",
            user_ref="DB_USER",
            password_ref="DB_PASSWORD",
        )
        assert test_mysql.schema == "finance"
        assert prod_mysql.schema == "finance"


class TestSamDef:
    """Test the SamDef dataclass structure and invariants."""

    def test_sam_def_is_frozen(self) -> None:
        """SamDef instances should be immutable (frozen dataclass)."""
        sam = SamDef(
            stack_name="myAdmin-test",
            api_base_url="https://test-api.execute-api.eu-west-1.amazonaws.com/Prod",
            table_prefix="test_",
            exec_role_scope="arn:aws:dynamodb:*:*:table/test_*",
            authorizer_pool_id="eu-west-1_testpool",
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            sam.stack_name = "modified"

    def test_sam_def_fields(self) -> None:
        """SamDef should have all required fields with correct types."""
        sam = SamDef(
            stack_name="myAdmin-prod",
            api_base_url="https://prod-api.execute-api.eu-west-1.amazonaws.com/Prod",
            table_prefix="",
            exec_role_scope="arn:aws:dynamodb:*:*:table/*",
            authorizer_pool_id="eu-west-1_prodpool",
        )
        assert sam.stack_name == "myAdmin-prod"
        assert sam.api_base_url == "https://prod-api.execute-api.eu-west-1.amazonaws.com/Prod"
        assert sam.table_prefix == ""
        assert sam.exec_role_scope == "arn:aws:dynamodb:*:*:table/*"
        assert sam.authorizer_pool_id == "eu-west-1_prodpool"

    def test_test_prefix_is_test_underscore(self) -> None:
        """TEST environment should have 'test_' prefix."""
        test_sam = SamDef(
            stack_name="myAdmin-test",
            api_base_url="https://test-api.execute-api.eu-west-1.amazonaws.com/Prod",
            table_prefix="test_",
            exec_role_scope="arn:aws:dynamodb:*:*:table/test_*",
            authorizer_pool_id="eu-west-1_testpool",
        )
        assert test_sam.table_prefix == "test_"

    def test_prod_prefix_is_empty(self) -> None:
        """PRODUCTION environment should have empty prefix."""
        prod_sam = SamDef(
            stack_name="myAdmin-prod",
            api_base_url="https://prod-api.execute-api.eu-west-1.amazonaws.com/Prod",
            table_prefix="",
            exec_role_scope="arn:aws:dynamodb:*:*:table/*",
            authorizer_pool_id="eu-west-1_prodpool",
        )
        assert prod_sam.table_prefix == ""


class TestPlaneDef:
    """Test the PlaneDef dataclass structure and invariants."""

    def test_plane_def_is_frozen(self) -> None:
        """PlaneDef instances should be immutable (frozen dataclass)."""
        plane = PlaneDef(
            cognito=CognitoDef(
                pool_id="test-pool",
                client_id="test-client",
                client_secret_ref="",
                pool_label="Test Pool",
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
                authorizer_pool_id="eu-west-1_testpool",
            ),
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            plane.backend_host_ref = "modified"

    def test_plane_def_fields(self) -> None:
        """PlaneDef should have all required fields with correct types."""
        plane = PlaneDef(
            cognito=CognitoDef(
                pool_id="prod-pool",
                client_id="prod-client",
                client_secret_ref="PLACEHOLDER_SECRET",
                pool_label="Production Pool",
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
            flask_api_base_url="https://production.example.com",
            sam=SamDef(
                stack_name="myAdmin-prod",
                api_base_url="https://prod-api.execute-api.eu-west-1.amazonaws.com/Prod",
                table_prefix="",
                exec_role_scope="arn:aws:dynamodb:*:*:table/*",
                authorizer_pool_id="eu-west-1_prodpool",
            ),
        )
        assert isinstance(plane.cognito, CognitoDef)
        assert isinstance(plane.mysql, MysqlDef)
        assert plane.backend_host_ref == "BACKEND_HOST_PROD"
        assert plane.flask_api_base_url == "https://production.example.com"
        assert isinstance(plane.sam, SamDef)


class TestEnvironmentDefinition:
    """Test the EnvironmentDefinition dataclass structure and invariants."""

    def test_environment_definition_is_frozen(self) -> None:
        """EnvironmentDefinition instances should be immutable (frozen dataclass)."""
        env_def = EnvironmentDefinition(
            test=PlaneDef(
                cognito=CognitoDef(
                    pool_id="test-pool",
                    client_id="test-client",
                    client_secret_ref="",
                    pool_label="Test Pool",
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
                    authorizer_pool_id="eu-west-1_testpool",
                ),
            ),
            production=PlaneDef(
                cognito=CognitoDef(
                    pool_id="prod-pool",
                    client_id="prod-client",
                    client_secret_ref="PLACEHOLDER_SECRET",
                    pool_label="Production Pool",
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
                flask_api_base_url="https://production.example.com",
                sam=SamDef(
                    stack_name="myAdmin-prod",
                    api_base_url="https://prod-api.execute-api.eu-west-1.amazonaws.com/Prod",
                    table_prefix="",
                    exec_role_scope="arn:aws:dynamodb:*:*:table/*",
                    authorizer_pool_id="eu-west-1_prodpool",
                ),
            ),
            test_url="localhost:3000",
            production_url="app.example.com",
            test_branch="test",
            production_branch="main",
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            env_def.test_url = "modified"

    def test_environment_definition_fields(self) -> None:
        """EnvironmentDefinition should have all required fields with correct types."""
        env_def = EnvironmentDefinition(
            test=PlaneDef(
                cognito=CognitoDef(
                    pool_id="test-pool",
                    client_id="test-client",
                    client_secret_ref="",
                    pool_label="Test Pool",
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
                    authorizer_pool_id="eu-west-1_testpool",
                ),
            ),
            production=PlaneDef(
                cognito=CognitoDef(
                    pool_id="prod-pool",
                    client_id="prod-client",
                    client_secret_ref="PLACEHOLDER_SECRET",
                    pool_label="Production Pool",
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
                flask_api_base_url="https://production.example.com",
                sam=SamDef(
                    stack_name="myAdmin-prod",
                    api_base_url="https://prod-api.execute-api.eu-west-1.amazonaws.com/Prod",
                    table_prefix="",
                    exec_role_scope="arn:aws:dynamodb:*:*:table/*",
                    authorizer_pool_id="eu-west-1_prodpool",
                ),
            ),
            test_url="localhost:3000",
            production_url="app.example.com",
            test_branch="test",
            production_branch="main",
        )
        assert isinstance(env_def.test, PlaneDef)
        assert isinstance(env_def.production, PlaneDef)
        assert env_def.test_url == "localhost:3000"
        assert env_def.production_url == "app.example.com"
        assert env_def.test_branch == "test"
        assert env_def.production_branch == "main"

    def test_optional_branch_fields(self) -> None:
        """Branch fields should be Optional[str]."""
        env_def = EnvironmentDefinition(
            test=PlaneDef(
                cognito=CognitoDef(
                    pool_id="test-pool",
                    client_id="test-client",
                    client_secret_ref="",
                    pool_label="Test Pool",
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
                    authorizer_pool_id="eu-west-1_testpool",
                ),
            ),
            production=PlaneDef(
                cognito=CognitoDef(
                    pool_id="prod-pool",
                    client_id="prod-client",
                    client_secret_ref="PLACEHOLDER_SECRET",
                    pool_label="Production Pool",
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
                flask_api_base_url="https://production.example.com",
                sam=SamDef(
                    stack_name="myAdmin-prod",
                    api_base_url="https://prod-api.execute-api.eu-west-1.amazonaws.com/Prod",
                    table_prefix="",
                    exec_role_scope="arn:aws:dynamodb:*:*:table/*",
                    authorizer_pool_id="eu-west-1_prodpool",
                ),
            ),
            test_url="localhost:3000",
            production_url="app.example.com",
            test_branch=None,
            production_branch=None,
        )
        assert env_def.test_branch is None
        assert env_def.production_branch is None


class TestEnvironmentDefinitionInstance:
    """Test the concrete ENVIRONMENT_DEFINITION instance."""

    def test_instance_exists(self) -> None:
        """ENVIRONMENT_DEFINITION should be defined and be an EnvironmentDefinition."""
        assert ENVIRONMENT_DEFINITION is not None
        assert isinstance(ENVIRONMENT_DEFINITION, EnvironmentDefinition)

    def test_test_configuration(self) -> None:
        """TEST configuration should have correct values and placeholders."""
        test_config = ENVIRONMENT_DEFINITION.test
        
        # Cognito
        assert test_config.cognito.pool_id == TEST_POOL_ID
        assert test_config.cognito.client_id == TEST_CLIENT_ID
        assert test_config.cognito.client_secret_ref == ""  # test pool has no secret
        assert test_config.cognito.pool_label == "myAdmin-test"
        
        # MySQL
        assert test_config.mysql.target_label == "TEST"
        assert test_config.mysql.schema == "finance"
        assert test_config.mysql.host_ref == "DB_HOST_TEST"
        assert test_config.mysql.port_ref == "DB_PORT_TEST"
        assert test_config.mysql.user_ref == "DB_USER_TEST"
        assert test_config.mysql.password_ref == "DB_PASSWORD_TEST"
        
        # Backend Runtime
        assert test_config.backend_host_ref == "BACKEND_HOST_TEST"
        assert test_config.flask_api_base_url == "http://localhost:5000"
        
        # SAM — members module TEST stack (per-module stacks, test_ boundary)
        assert test_config.sam.stack_name == "test-sam-members"
        assert test_config.sam.api_base_url == "https://28jun82vl3.execute-api.eu-west-1.amazonaws.com/test"
        assert test_config.sam.table_prefix == "test_"
        assert test_config.sam.exec_role_scope == "arn:aws:dynamodb:*:*:table/test_*"
        assert test_config.sam.authorizer_pool_id == TEST_POOL_ID

    def test_production_configuration(self) -> None:
        """PRODUCTION configuration should have correct values and placeholders."""
        prod_config = ENVIRONMENT_DEFINITION.production
        
        # Cognito
        assert prod_config.cognito.pool_id == PROD_POOL_ID
        assert prod_config.cognito.client_id == PROD_CLIENT_ID
        assert prod_config.cognito.client_secret_ref == "PLACEHOLDER_CLIENT_SECRET"
        assert prod_config.cognito.pool_label == "myAdmin"
        
        # MySQL
        assert prod_config.mysql.target_label == "PRODUCTION"
        assert prod_config.mysql.schema == "finance"
        assert prod_config.mysql.host_ref == "DB_HOST"
        assert prod_config.mysql.port_ref == "DB_PORT"
        assert prod_config.mysql.user_ref == "DB_USER"
        assert prod_config.mysql.password_ref == "DB_PASSWORD"
        
        # Backend Runtime
        assert prod_config.backend_host_ref == "BACKEND_HOST_PROD"
        assert "PLACEHOLDER_PRODUCTION_FLASK_API" in prod_config.flask_api_base_url
        
        # SAM — members module PROD stack (per-module stacks, unprefixed)
        assert prod_config.sam.stack_name == "sam-members"
        assert prod_config.sam.api_base_url == (
            "https://22x6z55301.execute-api.eu-west-1.amazonaws.com/prod"
        )
        assert prod_config.sam.table_prefix == ""
        assert prod_config.sam.exec_role_scope == "arn:aws:dynamodb:*:*:table/*"
        assert prod_config.sam.authorizer_pool_id == PROD_POOL_ID

    def test_url_fields(self) -> None:
        """URL fields should be defined as per Req 22."""
        assert ENVIRONMENT_DEFINITION.test_url == "localhost:3000"
        assert ENVIRONMENT_DEFINITION.production_url == "app.myadmin.jabaki.nl"

    def test_branch_fields(self) -> None:
        """Branch fields should be defined as per Req 23."""
        assert ENVIRONMENT_DEFINITION.test_branch == "test"
        assert ENVIRONMENT_DEFINITION.production_branch == "main"

    def test_test_has_empty_client_secret(self) -> None:
        """Test pool should have empty client secret (no secret)."""
        assert ENVIRONMENT_DEFINITION.test.cognito.client_secret_ref == ""

    def test_production_has_secret_placeholder(self) -> None:
        """Production should have a placeholder for client secret."""
        secret_ref = ENVIRONMENT_DEFINITION.production.cognito.client_secret_ref
        assert secret_ref == "PLACEHOLDER_CLIENT_SECRET"
        assert secret_ref != ""  # Should not be empty

    def test_test_table_prefix(self) -> None:
        """TEST should have 'test_' table prefix."""
        assert ENVIRONMENT_DEFINITION.test.sam.table_prefix == "test_"

    def test_production_table_prefix(self) -> None:
        """PRODUCTION should have empty table prefix."""
        assert ENVIRONMENT_DEFINITION.production.sam.table_prefix == ""

    def test_test_exec_role_scope_has_test_pattern(self) -> None:
        """TEST execution role scope should include 'test_*' pattern."""
        scope = ENVIRONMENT_DEFINITION.test.sam.exec_role_scope
        assert "test_*" in scope

    def test_production_exec_role_scope_no_prefix(self) -> None:
        """PRODUCTION execution role scope should not include test prefix."""
        scope = ENVIRONMENT_DEFINITION.production.sam.exec_role_scope
        assert "test_" not in scope

    def test_secrets_are_placeholders(self) -> None:
        """All secret references should be placeholders, not real values."""
        # Check TEST (should be empty for client secret)
        test_secret = ENVIRONMENT_DEFINITION.test.cognito.client_secret_ref
        assert test_secret == ""  # No secret for test pool
        
        # Check PRODUCTION (should be placeholder)
        prod_secret = ENVIRONMENT_DEFINITION.production.cognito.client_secret_ref
        assert "PLACEHOLDER" in prod_secret or prod_secret == ""
        
        # Check MySQL password references
        test_db_pass = ENVIRONMENT_DEFINITION.test.mysql.password_ref
        prod_db_pass = ENVIRONMENT_DEFINITION.production.mysql.password_ref
        assert "PLACEHOLDER" not in test_db_pass  # Should be env var ref
        assert "PLACEHOLDER" not in prod_db_pass  # Should be env var ref
        assert "_TEST" in test_db_pass  # Should reference TEST env var
        assert "_TEST" not in prod_db_pass  # Should reference PROD env var

    def test_constants_match_definition(self) -> None:
        """Public constant values should match the definition."""
        assert ENVIRONMENT_DEFINITION.test.cognito.pool_id == TEST_POOL_ID
        assert ENVIRONMENT_DEFINITION.test.cognito.client_id == TEST_CLIENT_ID
        assert ENVIRONMENT_DEFINITION.production.cognito.pool_id == PROD_POOL_ID
        assert ENVIRONMENT_DEFINITION.production.cognito.client_id == PROD_CLIENT_ID


# Need to import dataclasses for FrozenInstanceError
import dataclasses