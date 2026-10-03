"""
Property-based tests for the Environment_Resolver pure-logic core.

Uses Hypothesis to verify correctness properties from the design document.
Feature: test-environment
Reference: .kiro/specs/Common/test-environment/first-draft/design.md

Covers Properties 1-4 (Phase 0 — core resolver + parser):

- Property 1: APP_ENV is a closed two-value set.
    `parse_app_env` succeeds iff the trimmed value is exactly "production"/"test";
    every other value raises EnvironmentConfigError.
    Validates: Requirements 1.1, 1.2, 1.5

- Property 2: Unset/unrecognized APP_ENV fails fast and names the recognized set.
    Validates: Requirements 1.3, 1.5

- Property 3: Resolution ignores incidental signals.
    `resolve(app_env, definition)` is a pure function of (app_env, definition);
    identical inputs always yield an identical ResolvedConfig, independent of any
    ambient signal (hostname, env vars, port, order of evaluation).
    Validates: Requirements 1.1, 1.4, 2.3, 13.3, 21.3

- Property 4: Resolution is atomic and faithful to the definition.
    Every per-plane field of the ResolvedConfig equals the corresponding field of
    the selected PlaneDef in the definition — no half-resolution, no mixing of the
    other environment's values.
    Validates: Requirements 2.1, 2.2, 7.1, 8.1-8.3, 9.1-9.2, 10.1-10.2, 13.4, 21.1-21.4

- Property 5: Test environment consequences — empty client secret and test_ prefix.
    `resolve(test, definition)` yields an empty resolved Cognito client secret and a
    DynamoDB prefix equal to "test_", while `resolve(production, definition)` yields a
    non-test (empty) prefix — the test-pool-has-no-secret and test-tables-are-prefixed
    guarantees hold for ALL definitions, over arbitrary definition/env inputs. The
    active-identity derivation (`resolved_identity`) likewise yields an empty client
    secret for the test pool regardless of ambient env.
    Validates: Requirements 7.3, 8.4, 10.2

Generators build arbitrary-but-well-formed EnvironmentDefinitions so the properties
hold for all definitions, not just the committed one. The test oracle asserts against
the generated definition directly — it does not reimplement the resolver.
"""

import os
import string

import pytest
from hypothesis import given, settings, strategies as st

from environment.app_env import AppEnv, EnvironmentConfigError, parse_app_env
from environment.environment_definition import (
    CognitoDef,
    EnvironmentDefinition,
    MysqlDef,
    PlaneDef,
    SamDef,
)
from environment.resolver import ResolvedConfig, resolve


# ---------------------------------------------------------------------------
# Generators
# ---------------------------------------------------------------------------

# The two recognized APP_ENV literals (canonical form).
RECOGNIZED_VALUES = ("production", "test")

# Reasonable identifier-ish text for pool ids, hosts, urls, labels, etc.
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


def _cognito_st(client_secret_ref: st.SearchStrategy[str]) -> st.SearchStrategy[CognitoDef]:
    return st.builds(
        CognitoDef,
        pool_id=_nonempty_text,
        client_id=_nonempty_text,
        client_secret_ref=client_secret_ref,
        pool_label=_nonempty_text,
    )


def _mysql_st(target_label: str) -> st.SearchStrategy[MysqlDef]:
    return st.builds(
        MysqlDef,
        target_label=st.just(target_label),
        schema=st.just("finance"),
        host_ref=_nonempty_text,
        port_ref=_nonempty_text,
        user_ref=_nonempty_text,
        password_ref=_nonempty_text,
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


# TEST plane: by the test-environment contract the test pool has no client secret
# ("") and the DynamoDB prefix is "test_".
_test_plane_st = st.builds(
    PlaneDef,
    cognito=_cognito_st(client_secret_ref=st.just("")),
    mysql=_mysql_st("TEST"),
    backend_host_ref=_nonempty_text,
    flask_api_base_url=_nonempty_text,
    sam=_sam_st("test_"),
)

# PRODUCTION plane: non-test (empty) prefix; secret ref may be any placeholder text.
_prod_plane_st = st.builds(
    PlaneDef,
    cognito=_cognito_st(client_secret_ref=_text),
    mysql=_mysql_st("PRODUCTION"),
    backend_host_ref=_nonempty_text,
    flask_api_base_url=_nonempty_text,
    sam=_sam_st(""),
)

environment_definition_st = st.builds(
    EnvironmentDefinition,
    test=_test_plane_st,
    production=_prod_plane_st,
    test_url=_nonempty_text,
    production_url=_nonempty_text,
    test_branch=_optional_text,
    production_branch=_optional_text,
)


def _selected_plane(app_env: AppEnv, definition: EnvironmentDefinition) -> PlaneDef:
    """The PlaneDef the resolver should select for the given app_env."""
    return definition.test if app_env == AppEnv.TEST else definition.production


# ---------------------------------------------------------------------------
# Property 1: APP_ENV is a closed two-value set
# Feature: test-environment, Property 1: APP_ENV is a closed two-value set
# Validates: Requirements 1.1, 1.2, 1.5
# ---------------------------------------------------------------------------

class TestProperty1ClosedTwoValueSet:
    """parse_app_env accepts exactly 'production'/'test' (trimmed), nothing else."""

    @given(value=st.sampled_from(RECOGNIZED_VALUES))
    @settings(max_examples=100)
    def test_parse_app_env_recognized_value_returns_matching_member(
        self, value: str
    ) -> None:
        """A recognized value returns the matching AppEnv member."""
        result = parse_app_env(value)
        assert result is AppEnv(value)

    @given(
        value=st.sampled_from(RECOGNIZED_VALUES),
        lead=st.text(alphabet=" \t\n\r", max_size=4),
        trail=st.text(alphabet=" \t\n\r", max_size=4),
    )
    @settings(max_examples=100)
    def test_parse_app_env_recognized_value_with_whitespace_returns_member(
        self, value: str, lead: str, trail: str
    ) -> None:
        """Surrounding whitespace is stripped; the trimmed value still parses."""
        result = parse_app_env(f"{lead}{value}{trail}")
        assert result is AppEnv(value)

    @given(raw=st.text(max_size=60))
    @settings(max_examples=200)
    def test_parse_app_env_arbitrary_string_parses_iff_recognized(
        self, raw: str
    ) -> None:
        """For ANY string: parse succeeds iff trimmed value is a recognized literal.

        This is the biconditional at the heart of Property 1 — the parser is total
        over the whole string space and admits exactly the closed two-value set.
        """
        trimmed = raw.strip()
        if trimmed in RECOGNIZED_VALUES:
            assert parse_app_env(raw) is AppEnv(trimmed)
        else:
            with pytest.raises(EnvironmentConfigError):
                parse_app_env(raw)


# ---------------------------------------------------------------------------
# Property 2: Unset/unrecognized APP_ENV fails fast and names the recognized set
# Feature: test-environment, Property 2: Unset/unrecognized APP_ENV fails fast
# Validates: Requirements 1.3, 1.5
# ---------------------------------------------------------------------------

class TestProperty2FailFastNamesRecognizedSet:
    """None/blank/unrecognized raise EnvironmentConfigError naming the valid set."""

    @given(
        raw=st.one_of(
            st.none(),
            st.text(alphabet=" \t\n\r", max_size=6),  # empty / whitespace-only
            st.text(max_size=60).filter(
                lambda s: s.strip() not in RECOGNIZED_VALUES
            ),
        )
    )
    @settings(max_examples=200)
    def test_parse_app_env_invalid_input_raises_naming_recognized_values(
        self, raw
    ) -> None:
        """Invalid input raises and the message names both recognized values.

        No default is ever substituted — the running unit refuses to start.
        """
        with pytest.raises(EnvironmentConfigError) as exc_info:
            parse_app_env(raw)
        message = str(exc_info.value)
        assert "production" in message
        assert "test" in message


# ---------------------------------------------------------------------------
# Property 3: Resolution ignores incidental signals
# Feature: test-environment, Property 3: Resolution ignores incidental signals
# Validates: Requirements 1.1, 1.4, 2.3, 13.3, 21.3
# ---------------------------------------------------------------------------

class TestProperty3IgnoresIncidentalSignals:
    """resolve() is a pure function of (app_env, definition) only."""

    @given(app_env=app_env_st, definition=environment_definition_st)
    @settings(max_examples=100)
    def test_resolve_same_inputs_are_deterministic(
        self, app_env: AppEnv, definition: EnvironmentDefinition
    ) -> None:
        """Same (app_env, definition) always yields an equal ResolvedConfig."""
        first = resolve(app_env, definition)
        second = resolve(app_env, definition)
        assert first == second

    @given(
        app_env=app_env_st,
        definition=environment_definition_st,
        # os.environ rejects embedded NULs, so exclude \x00 from ambient strings.
        hostname=st.text(max_size=30).filter(lambda s: "\x00" not in s),
        port=st.integers(min_value=0, max_value=65535),
        request_origin=st.text(max_size=30).filter(lambda s: "\x00" not in s),
    )
    @settings(max_examples=100)
    def test_resolve_ignores_ambient_signals(
        self,
        app_env: AppEnv,
        definition: EnvironmentDefinition,
        hostname: str,
        port: int,
        request_origin: str,
    ) -> None:
        """Varying ambient signals (hostname, port, origin, env vars) changes nothing.

        The resolver takes no ambient input, so simulating different incidental
        contexts via monkeypatched env vars must not alter the output. We assert the
        result equals a baseline resolve computed with no ambient context at all.
        """
        import os
        from unittest.mock import patch

        baseline = resolve(app_env, definition)
        incidental_env = {
            "HOSTNAME": hostname,
            "PORT": str(port),
            "HTTP_ORIGIN": request_origin,
            "COMPUTERNAME": hostname,
        }
        with patch.dict(os.environ, incidental_env, clear=False):
            under_signals = resolve(app_env, definition)
        assert under_signals == baseline


# ---------------------------------------------------------------------------
# Property 4: Resolution is atomic and faithful to the definition
# Feature: test-environment, Property 4: Resolution is atomic and faithful
# Validates: Requirements 2.1, 2.2, 7.1, 8.1-8.3, 9.1-9.2, 10.1-10.2, 13.4, 21.1-21.4
# ---------------------------------------------------------------------------

class TestProperty4AtomicAndFaithful:
    """Every resolved per-plane field equals the selected definition's field."""

    @given(app_env=app_env_st, definition=environment_definition_st)
    @settings(max_examples=100)
    def test_resolve_fields_match_selected_plane(
        self, app_env: AppEnv, definition: EnvironmentDefinition
    ) -> None:
        """All per-plane fields are drawn faithfully from the selected PlaneDef."""
        resolved = resolve(app_env, definition)
        plane = _selected_plane(app_env, definition)

        # app_env echoed back
        assert resolved.app_env == app_env

        # Cognito identity plane
        assert resolved.cognito.pool_id == plane.cognito.pool_id
        assert resolved.cognito.client_id == plane.cognito.client_id
        assert resolved.cognito.client_secret_ref == plane.cognito.client_secret_ref
        assert resolved.cognito.pool_label == plane.cognito.pool_label

        # MySQL target
        assert resolved.mysql.target_label == plane.mysql.target_label
        assert resolved.mysql.schema == plane.mysql.schema
        assert resolved.mysql.host_ref == plane.mysql.host_ref
        assert resolved.mysql.port_ref == plane.mysql.port_ref
        assert resolved.mysql.user_ref == plane.mysql.user_ref
        assert resolved.mysql.password_ref == plane.mysql.password_ref

        # Backend runtime + Flask API
        assert resolved.backend_host_ref == plane.backend_host_ref
        assert resolved.flask_api_base_url == plane.flask_api_base_url

        # SAM plane (incl. convenience properties)
        assert resolved.sam.stack_name == plane.sam.stack_name
        assert resolved.sam.api_base_url == plane.sam.api_base_url
        assert resolved.sam.table_prefix == plane.sam.table_prefix
        assert resolved.sam.exec_role_scope == plane.sam.exec_role_scope
        assert resolved.sam.authorizer_pool_id == plane.sam.authorizer_pool_id
        assert resolved.dynamodb_prefix == plane.sam.table_prefix
        assert resolved.sam_api_base_url == plane.sam.api_base_url
        assert resolved.sam_authorizer_pool_id == plane.sam.authorizer_pool_id
        assert resolved.sam_stack_label == plane.sam.stack_name

    @given(app_env=app_env_st, definition=environment_definition_st)
    @settings(max_examples=100)
    def test_resolve_does_not_mix_in_other_environment_values(
        self, app_env: AppEnv, definition: EnvironmentDefinition
    ) -> None:
        """No half-resolution: no field leaks from the non-selected plane.

        The target labels of TEST and PRODUCTION are fixed and distinct, so the
        resolved MySQL target label pins which plane was selected end-to-end.
        """
        resolved = resolve(app_env, definition)
        if app_env == AppEnv.TEST:
            assert resolved.mysql.target_label == "TEST"
            assert resolved.sam.table_prefix == definition.test.sam.table_prefix
        else:
            assert resolved.mysql.target_label == "PRODUCTION"
            assert resolved.sam.table_prefix == definition.production.sam.table_prefix

    @given(app_env=app_env_st, definition=environment_definition_st)
    @settings(max_examples=100)
    def test_resolve_returns_fully_populated_resolved_config(
        self, app_env: AppEnv, definition: EnvironmentDefinition
    ) -> None:
        """resolve() always returns a complete ResolvedConfig instance."""
        resolved = resolve(app_env, definition)
        assert isinstance(resolved, ResolvedConfig)
        assert resolved.cognito is not None
        assert resolved.mysql is not None
        assert resolved.sam is not None


# ---------------------------------------------------------------------------
# Property 5: Test environment consequences — empty client secret and test_ prefix
# Feature: test-environment, Property 5: Test environment consequences —
#   empty client secret and test_ prefix
# Validates: Requirements 7.3, 8.4, 10.2
# ---------------------------------------------------------------------------

class TestProperty5TestEnvironmentConsequences:
    """APP_ENV=test ⇒ empty client secret and 'test_' prefix; prod ⇒ non-test prefix.

    These are the two always-true consequences of selecting the Test_Environment that
    the design pins across ALL definitions: the test app-client has no secret
    (Req 7.3, 8.4) and the test DynamoDB tables are prefixed `test_` (Req 10.2), while
    production carries a non-test (empty) prefix. The property is exercised both at the
    resolver output (`resolve`) and at the active-identity derivation
    (`resolved_identity`), the latter under arbitrary ambient env so no incidental
    variable can conjure a test-pool secret.
    """

    @given(definition=environment_definition_st)
    @settings(max_examples=100)
    def test_resolve_test_env_has_empty_secret_ref_and_test_prefix(
        self, definition: EnvironmentDefinition
    ) -> None:
        """resolve(test, ...) ⇒ empty client_secret_ref and dynamodb_prefix 'test_'."""
        resolved = resolve(AppEnv.TEST, definition)
        assert resolved.cognito.client_secret_ref == ""
        assert resolved.dynamodb_prefix == "test_"
        assert resolved.sam.table_prefix == "test_"

    @given(definition=environment_definition_st)
    @settings(max_examples=100)
    def test_resolve_production_env_has_non_test_prefix(
        self, definition: EnvironmentDefinition
    ) -> None:
        """resolve(production, ...) ⇒ a non-test (empty) DynamoDB prefix."""
        resolved = resolve(AppEnv.PRODUCTION, definition)
        assert resolved.dynamodb_prefix == ""
        assert resolved.dynamodb_prefix != "test_"
        assert resolved.sam.table_prefix == ""

    @given(
        definition=environment_definition_st,
        # Arbitrary ambient env (incl. a would-be secret var) must NOT give the test
        # pool a secret. os.environ rejects NULs, so exclude them.
        ambient_secret=st.text(max_size=30).filter(lambda s: "\x00" not in s),
        region=st.one_of(
            st.none(),
            st.text(alphabet=string.ascii_letters + string.digits + "-",
                    min_size=1, max_size=15),
        ),
    )
    @settings(max_examples=100)
    def test_resolved_identity_test_pool_has_empty_client_secret(
        self,
        definition: EnvironmentDefinition,
        ambient_secret: str,
        region,
    ) -> None:
        """The active identity for APP_ENV=test always has an empty client secret.

        `resolved_identity` dereferences the client-secret ref against the env. For the
        test pool the ref is "" (no secret), so NO ambient variable — even one that
        looks like a secret — can produce a non-empty secret. The issuer still embeds
        the resolved pool id so the registry cross-check can match it.
        """
        from auth.pool_registry import resolved_identity

        resolved = resolve(AppEnv.TEST, definition)
        env = {"SOME_SECRET": ambient_secret, "COGNITO_CLIENT_SECRET": ambient_secret}
        if region is not None:
            env["AWS_REGION"] = region

        identity = resolved_identity(resolved.cognito, environ=env)

        assert identity.client_secret == ""
        assert identity.has_client_secret is False
        assert identity.pool_id == resolved.cognito.pool_id
        assert identity.client_id == resolved.cognito.client_id
        # The issuer embeds the pool id (the registry key for the coherence check).
        assert resolved.cognito.pool_id in identity.iss

    @given(
        definition=environment_definition_st,
        secret_value=st.text(
            alphabet=string.ascii_letters + string.digits, min_size=1, max_size=30
        ),
    )
    @settings(max_examples=100)
    def test_resolved_identity_production_dereferences_secret_ref(
        self, definition: EnvironmentDefinition, secret_value: str
    ) -> None:
        """A non-empty production secret ref is dereferenced from the env var it names.

        Production's client_secret_ref is the NAME of an env var holding the secret;
        `resolved_identity` reads that var. When the var is set, the resolved identity
        carries the value; the committed definition never embeds the real secret.
        """
        from auth.pool_registry import resolved_identity

        resolved = resolve(AppEnv.PRODUCTION, definition)
        ref = resolved.cognito.client_secret_ref
        env = {ref: secret_value} if ref else {}

        identity = resolved_identity(resolved.cognito, environ=env)

        if ref:
            assert identity.client_secret == secret_value
            assert identity.has_client_secret is True
        else:
            # An empty ref (edge-case generated prod definition) ⇒ empty secret.
            assert identity.client_secret == ""


# ---------------------------------------------------------------------------
# Property 11: TEST and PRODUCTION database targets are isolated by distinct
#   targets and credentials
# Feature: test-environment, Property 11: TEST and PRODUCTION database targets
#   are isolated by distinct targets and credentials
# Validates: Requirements 9.3, 9.5, 9.6
# ---------------------------------------------------------------------------

from environment.consistency_guard import build_consistency_report


def _mysql_target_check(definition: EnvironmentDefinition, app_env: AppEnv):
    """Resolve the Consistency_Guard's mysql_target PlaneCheck for a definition.

    Issuers for BOTH resolved pools are injected so the Cognito/registry planes
    never fail for reasons unrelated to Property 11 — this isolates the MySQL
    target-isolation verdict. No real registry, AWS, or DB is touched.
    """
    test_issuer = resolve(AppEnv.TEST, definition).cognito.pool_id
    prod_issuer = resolve(AppEnv.PRODUCTION, definition).cognito.pool_id
    report = build_consistency_report(
        app_env,
        definition=definition,
        environ={},
        registered_issuers=[test_issuer, prod_issuer],
    )
    matches = [c for c in report.checks if c.plane == "mysql_target"]
    assert matches, "mysql_target check missing from report"
    return matches[0]


# A MySQL target strategy that forces schema `finance` (Req 9.2) but lets the
# connection references vary freely so TEST/PROD may independently coincide or
# differ — exactly the input space Property 11 ranges over.
def _mysql_target_st(label: str) -> st.SearchStrategy[MysqlDef]:
    return st.builds(
        MysqlDef,
        target_label=st.just(label),
        schema=st.just("finance"),
        host_ref=_nonempty_text,
        port_ref=_nonempty_text,
        user_ref=_nonempty_text,
        password_ref=_nonempty_text,
    )


def _definition_with_mysql_st() -> st.SearchStrategy[EnvironmentDefinition]:
    """Arbitrary well-formed definition with free-floating MySQL targets."""
    test_plane = st.builds(
        PlaneDef,
        cognito=_cognito_st(client_secret_ref=st.just("")),
        mysql=_mysql_target_st("TEST"),
        backend_host_ref=_nonempty_text,
        flask_api_base_url=_nonempty_text,
        sam=_sam_st("test_"),
    )
    prod_plane = st.builds(
        PlaneDef,
        cognito=_cognito_st(client_secret_ref=_text),
        mysql=_mysql_target_st("PRODUCTION"),
        backend_host_ref=_nonempty_text,
        flask_api_base_url=_nonempty_text,
        sam=_sam_st(""),
    )
    return st.builds(
        EnvironmentDefinition,
        test=test_plane,
        production=prod_plane,
        test_url=_nonempty_text,
        production_url=_nonempty_text,
        test_branch=_optional_text,
        production_branch=_optional_text,
    )


class TestProperty11DatabaseTargetIsolation:
    """The guard reports consistent only when TEST and PROD targets are distinct."""

    @given(definition=_definition_with_mysql_st(), app_env=app_env_st)
    @settings(max_examples=100)
    def test_mysql_target_ok_iff_targets_are_distinct(
        self, definition: EnvironmentDefinition, app_env: AppEnv
    ) -> None:
        """mysql_target check passes iff the resolved TEST and PROD identities differ.

        The connection identity is (host_ref, port_ref, user_ref, password_ref):
        with schema pinned to `finance`, isolation holds exactly when those tuples
        differ between TEST and PRODUCTION. This is the biconditional Property 11
        pins over ALL definitions — including the (rare, generated) case where the
        two targets coincide.
        """
        test_identity = (
            definition.test.mysql.host_ref,
            definition.test.mysql.port_ref,
            definition.test.mysql.user_ref,
            definition.test.mysql.password_ref,
        )
        prod_identity = (
            definition.production.mysql.host_ref,
            definition.production.mysql.port_ref,
            definition.production.mysql.user_ref,
            definition.production.mysql.password_ref,
        )
        check = _mysql_target_check(definition, app_env)
        assert check.ok is (test_identity != prod_identity)

    @given(definition=_definition_with_mysql_st(), app_env=app_env_st)
    @settings(max_examples=100)
    def test_test_resolved_naming_production_target_is_reported_inconsistent(
        self, definition: EnvironmentDefinition, app_env: AppEnv
    ) -> None:
        """If TEST would resolve to the PRODUCTION target, the guard reports it.

        Force the TEST plane's MySQL target to carry the SAME connection
        references as PRODUCTION (co-located / mis-wired). For ANY definition and
        ANY active APP_ENV the mysql_target check must then FAIL — the boundary is
        enforced by distinct targets, not assumed from hosting (Req 9.6).
        """
        import dataclasses

        prod_mysql = definition.production.mysql
        collided_test_mysql = dataclasses.replace(
            prod_mysql, target_label="TEST"
        )
        collided = dataclasses.replace(
            definition,
            test=dataclasses.replace(definition.test, mysql=collided_test_mysql),
        )
        check = _mysql_target_check(collided, app_env)
        assert check.ok is False

    @given(definition=_definition_with_mysql_st(), app_env=app_env_st)
    @settings(max_examples=50)
    def test_mysql_target_check_never_leaks_schema_other_than_finance(
        self, definition: EnvironmentDefinition, app_env: AppEnv
    ) -> None:
        """Schema is pinned to `finance` for both envs, so the check accepts it.

        A sanity companion to the isolation biconditional: with schema forced to
        `finance` the only failure mode is identity collision, never a schema
        complaint — the message never names `testfinance`.
        """
        check = _mysql_target_check(definition, app_env)
        assert "testfinance" not in check.message


# ---------------------------------------------------------------------------
# Property 6: test_mode no longer selects the environment
# Feature: test-environment, Property 6: test_mode no longer selects the
#   environment
# Validates: Requirements 2.6
# ---------------------------------------------------------------------------
#
# Design (§ Testing Strategy, Property 6):
#   "For any AppEnv value and for any legacy test_mode argument value, the
#    resolved MySQL target is a function of APP_ENV alone — the resolved target is
#    unchanged when only test_mode changes."
#
# Task 15 (Step 1 shim): DatabaseManager keeps the `test_mode` parameter for
# backward compatibility but IGNORES it for environment/target selection. The
# schema is always `finance` and the resolved target comes from APP_ENV (or the
# legacy DB_* fallback when APP_ENV is unset) — never from `test_mode`. A truthy
# `test_mode` additionally emits a one-time deprecation warning; the default
# (False) stays silent.
#
# The autouse connection guard in tests/unit/conftest.py forbids a real DB, so
# mysql.connector.connect / pooling are mocked exactly as the other
# DatabaseManager unit tests do.

from unittest.mock import patch as _patch

from database import DatabaseManager


# A DB_* environment that pins a deterministic legacy connection target, so the
# resolved `config` depends only on this env + APP_ENV — never on `test_mode`.
_DB_ENV = {
    "DB_HOST": "db.example.test",
    "DB_PORT": "3307",
    "DB_USER": "finance_user",
    "DB_PASSWORD": "pw-placeholder",
}


class TestProperty6SchemaIsEnvironmentIndependent:
    """Environment/target selection does not depend on any per-instance flag (Req 2.6).

    The removed `test_mode` parameter was never a selector. The resolved MySQL
    target (`db.config`) is a function of APP_ENV (and the referenced env vars)
    ALONE, and the schema is always `finance`.
    """

    @settings(max_examples=50)
    @given(app_env=app_env_st)
    def test_schema_always_finance(self, app_env: AppEnv) -> None:
        """Under ANY APP_ENV, the resolved schema is `finance`, never testfinance."""
        env = dict(_DB_ENV)
        env["APP_ENV"] = app_env.value
        with _patch("database.mysql.connector.connect"), _patch(
            "database.pooling.MySQLConnectionPool"
        ), _patch.dict(os.environ, env, clear=False):
            db = DatabaseManager()
        assert db.config["database"] == "finance"
        assert db.config["database"] != "testfinance"

    @given(app_env=app_env_st)
    @settings(max_examples=50)
    def test_resolved_target_is_deterministic_for_fixed_app_env(
        self, app_env: AppEnv
    ) -> None:
        """Under a FIXED APP_ENV, two managers resolve the IDENTICAL MySQL target.

        The target is a function of APP_ENV (plus the referenced DB_* vars) alone;
        with `test_mode` removed there is no per-instance flag that could perturb
        it, so repeated construction must yield an equal config field-for-field.
        """
        env = dict(_DB_ENV)
        env["APP_ENV"] = app_env.value
        with _patch("database.mysql.connector.connect"), _patch(
            "database.pooling.MySQLConnectionPool"
        ), _patch.dict(os.environ, env, clear=False):
            db_first = DatabaseManager()
            db_second = DatabaseManager()
        assert db_first.config == db_second.config
        assert db_first.config["database"] == "finance"
