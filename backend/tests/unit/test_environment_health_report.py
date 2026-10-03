"""
Unit + property tests for the backend environment/health report (Req 6).

Feature: test-environment
Reference: .kiro/specs/Common/test-environment/first-draft/design.md (§11 Health report)

Covers Task 8.5 — Property 9 ("The health report cannot drift and never leaks
secrets") plus example-based unit tests for the pure report builder
:func:`environment.health_report.build_environment_report`.

Property 9 (design.md): *For any* ``APP_ENV`` and ``EnvironmentDefinition``, every
value in the backend health report equals the corresponding field of the same
``ResolvedConfig`` the planes use (the report is derived, not independently read), and
no secret-shaped value (client secret, DB password) appears in the report payload —
only non-secret labels/identifiers.
    Validates: Requirements 5.3, 6.1, 6.2, 6.3, 6.4, 6.5, 6.6

The property test injects a unique sentinel string into every secret field of the
generated definition (the Cognito ``client_secret_ref`` and all MySQL ``*_ref``
connection references) and asserts the sentinel never appears anywhere in the
serialized report — proving secrets cannot leak (Req 6.6).
"""

import json
import string

import pytest
from hypothesis import given, settings, strategies as st

from environment.app_env import AppEnv
from environment.environment_definition import (
    CognitoDef,
    EnvironmentDefinition,
    MysqlDef,
    PlaneDef,
    SamDef,
    ENVIRONMENT_DEFINITION,
)
from environment.health_report import build_environment_report
from environment.resolver import ResolvedConfig, resolve


# ---------------------------------------------------------------------------
# Example-based unit tests (pure report builder)
# ---------------------------------------------------------------------------

class TestBuildEnvironmentReportExamples:
    """Example-based checks of the derived, non-secret report payload."""

    def _resolved(self, app_env: AppEnv) -> ResolvedConfig:
        return resolve(app_env, ENVIRONMENT_DEFINITION)

    def test_report_test_env_names_test_boundary(self) -> None:
        """For APP_ENV=test the report names the TEST boundary values (Req 6.1-6.4)."""
        report = build_environment_report(self._resolved(AppEnv.TEST))
        assert report["app_env"] == "test"
        assert report["cognito_pool_label"] == "myAdmin-test"
        assert report["identity_block_pool_label"] == "myAdmin-test"
        assert report["cognito_pool_id"] == "eu-west-1_xyrlzfqbl"
        assert report["mysql_target_label"] == "TEST"
        assert report["mysql_schema"] == "finance"
        assert report["dynamodb_prefix"] == "test_"
        assert report["sam_stack_label"] == "test-sam-members"

    def test_report_production_env_names_production_boundary(self) -> None:
        """For APP_ENV=production the report names PRODUCTION boundary values."""
        report = build_environment_report(self._resolved(AppEnv.PRODUCTION))
        assert report["app_env"] == "production"
        assert report["cognito_pool_label"] == "myAdmin"
        assert report["mysql_target_label"] == "PRODUCTION"
        assert report["mysql_schema"] == "finance"
        assert report["dynamodb_prefix"] == ""
        assert report["sam_stack_label"] == "sam-members"

    def test_report_omits_secret_fields(self) -> None:
        """The report never carries secret values or secret-shaped references (Req 6.6).

        Specifically: no Cognito client secret and no MySQL connection *_ref keys.
        """
        report = build_environment_report(self._resolved(AppEnv.PRODUCTION))
        forbidden_keys = {
            "client_secret",
            "client_secret_ref",
            "password",
            "password_ref",
            "host_ref",
            "port_ref",
            "user_ref",
        }
        assert forbidden_keys.isdisjoint(report.keys())

    def test_report_is_json_serializable(self) -> None:
        """The report must serialize cleanly to JSON (it is returned via jsonify)."""
        report = build_environment_report(self._resolved(AppEnv.TEST))
        # Round-trips without raising.
        assert json.loads(json.dumps(report)) == report


# ---------------------------------------------------------------------------
# Generators for Property 9 — reuse the shape from test_environment_properties,
# but inject a unique sentinel into EVERY secret field.
# ---------------------------------------------------------------------------

SENTINEL = "S3CR3T-SENTINEL-9f3c2a-DO-NOT-LEAK"

_text = st.text(
    alphabet=string.ascii_letters + string.digits + "-_.:/",
    min_size=0,
    max_size=40,
)
_nonempty_text = st.text(
    alphabet=string.ascii_letters + string.digits + "-_.:/",
    min_size=1,
    max_size=40,
)
_optional_text = st.one_of(st.none(), _nonempty_text)
app_env_st = st.sampled_from(list(AppEnv))


def _cognito_with_secret_sentinel() -> st.SearchStrategy[CognitoDef]:
    # client_secret_ref carries the sentinel secret — it must never surface.
    return st.builds(
        CognitoDef,
        pool_id=_nonempty_text,
        client_id=_nonempty_text,
        client_secret_ref=st.just(SENTINEL),
        pool_label=_nonempty_text,
    )


def _mysql_with_secret_sentinel(target_label: str) -> st.SearchStrategy[MysqlDef]:
    # Every connection reference carries the sentinel — none may surface.
    return st.builds(
        MysqlDef,
        target_label=st.just(target_label),
        schema=st.just("finance"),
        host_ref=st.just(SENTINEL),
        port_ref=st.just(SENTINEL),
        user_ref=st.just(SENTINEL),
        password_ref=st.just(SENTINEL),
    )


def _sam_st(table_prefix: str) -> st.SearchStrategy[SamDef]:
    return st.builds(
        SamDef,
        stack_name=_nonempty_text,
        api_base_url=_nonempty_text,
        table_prefix=st.just(table_prefix),
        exec_role_scope=_nonempty_text,
        authorizer_pool_id=_nonempty_text,
    )


def _plane_st(target_label: str, table_prefix: str) -> st.SearchStrategy[PlaneDef]:
    return st.builds(
        PlaneDef,
        cognito=_cognito_with_secret_sentinel(),
        mysql=_mysql_with_secret_sentinel(target_label),
        backend_host_ref=_nonempty_text,
        flask_api_base_url=_nonempty_text,
        sam=_sam_st(table_prefix),
    )


definition_with_secrets_st = st.builds(
    EnvironmentDefinition,
    test=_plane_st("TEST", "test_"),
    production=_plane_st("PRODUCTION", ""),
    test_url=_nonempty_text,
    production_url=_nonempty_text,
    test_branch=_optional_text,
    production_branch=_optional_text,
)


def _selected_plane(app_env: AppEnv, definition: EnvironmentDefinition) -> PlaneDef:
    return definition.test if app_env == AppEnv.TEST else definition.production


# ---------------------------------------------------------------------------
# Property 9: The health report cannot drift and never leaks secrets
# Feature: test-environment, Property 9
# Validates: Requirements 5.3, 6.1, 6.2, 6.3, 6.4, 6.5, 6.6
# ---------------------------------------------------------------------------

class TestProperty9HealthReportNonDriftAndSecretOmission:
    """The report is derived from the resolver and never leaks a secret."""

    @given(app_env=app_env_st, definition=definition_with_secrets_st)
    @settings(max_examples=200)
    def test_report_values_equal_resolver_values(
        self, app_env: AppEnv, definition: EnvironmentDefinition
    ) -> None:
        """Non-drift: every report value equals the resolver's field (Req 6.5).

        The oracle reads the SAME ResolvedConfig the planes consume, so the report is
        proven derived, not independently read.
        """
        resolved = resolve(app_env, definition)
        plane = _selected_plane(app_env, definition)
        report = build_environment_report(resolved)

        # Req 6.1 — active APP_ENV
        assert report["app_env"] == app_env.value == resolved.app_env.value
        # Req 6.2 — pool labels + public ids (registry label == identity-block label)
        assert report["cognito_pool_label"] == plane.cognito.pool_label
        assert report["identity_block_pool_label"] == plane.cognito.pool_label
        assert report["cognito_pool_id"] == plane.cognito.pool_id
        assert report["cognito_client_id"] == plane.cognito.client_id
        # Req 6.3 — MySQL target named by resolved identity
        assert report["mysql_target_label"] == plane.mysql.target_label
        assert report["mysql_schema"] == plane.mysql.schema
        # Req 6.4 — DynamoDB prefix + observable SAM surface
        assert report["dynamodb_prefix"] == plane.sam.table_prefix
        assert report["sam_api_base_url"] == plane.sam.api_base_url
        assert report["sam_stack_label"] == plane.sam.stack_name
        assert report["sam_authorizer_pool_id"] == plane.sam.authorizer_pool_id

    @given(app_env=app_env_st, definition=definition_with_secrets_st)
    @settings(max_examples=200)
    def test_report_never_leaks_the_secret_sentinel(
        self, app_env: AppEnv, definition: EnvironmentDefinition
    ) -> None:
        """Secret-omission: the injected sentinel never appears in the report (Req 6.6).

        The sentinel is injected into every secret field of the definition (Cognito
        client_secret_ref and all MySQL connection *_ref values). Serializing the
        report to JSON and scanning the whole payload — keys and values — proves no
        secret-shaped value can leak.
        """
        resolved = resolve(app_env, definition)
        report = build_environment_report(resolved)

        serialized = json.dumps(report)
        assert SENTINEL not in serialized
        # Also confirm no value in the dict equals the sentinel directly.
        for value in report.values():
            assert value != SENTINEL

    @given(app_env=app_env_st, definition=definition_with_secrets_st)
    @settings(max_examples=100)
    def test_report_keys_are_stable_and_non_secret(
        self, app_env: AppEnv, definition: EnvironmentDefinition
    ) -> None:
        """The report exposes exactly the known non-secret key set, nothing more."""
        resolved = resolve(app_env, definition)
        report = build_environment_report(resolved)
        assert set(report.keys()) == {
            "app_env",
            "cognito_pool_label",
            "cognito_pool_id",
            "cognito_client_id",
            "identity_block_pool_label",
            "mysql_target_label",
            "mysql_schema",
            "dynamodb_prefix",
            "sam_api_base_url",
            "sam_stack_label",
            "sam_authorizer_pool_id",
        }
