"""
Unit tests for the Consistency_Guard.

Covers the plane checks (Cognito identity, Pool_Registry membership, frontend-selected
pool vs backend registry, identity block, test-pool client secret) and the derived
half-cutover / is_consistent logic, plus the Phase-1 fail-fast startup hook (task 9.1).
All env access goes through an injected mapping — no real AWS, DB, or os.environ
mutation. The Pool_Registry issuers are injected directly so no auth config is needed.

Validates: Requirements 4.1, 4.2, 4.3, 4.7, 7.2, 7.3, 7.5, 8.4
"""

import logging

import pytest
from dataclasses import FrozenInstanceError

from environment.app_env import AppEnv, EnvironmentConfigError
from environment.environment_definition import (
    ENVIRONMENT_DEFINITION,
    TEST_POOL_ID,
    TEST_CLIENT_ID,
    PROD_POOL_ID,
    PROD_CLIENT_ID,
)
from environment.consistency_guard import (
    PlaneCheck,
    ConsistencyReport,
    build_consistency_report,
    run_consistency_guard,
    consistency_guard_startup_hook,
)
from environment.resolver import resolve


# Issuer strings embedding the pool ids, mirroring Cognito's issuer URL shape.
TEST_ISSUER = f"https://cognito-idp.eu-west-1.amazonaws.com/{TEST_POOL_ID}"
PROD_ISSUER = f"https://cognito-idp.eu-west-1.amazonaws.com/{PROD_POOL_ID}"


def _test_env_block() -> dict:
    """A consistent identity block for the TEST environment."""
    return {
        "COGNITO_USER_POOL_ID": TEST_POOL_ID,
        "COGNITO_CLIENT_ID": TEST_CLIENT_ID,
        "COGNITO_CLIENT_SECRET": "",
    }


def _prod_env_block() -> dict:
    """A consistent identity block for the PRODUCTION environment."""
    return {
        "COGNITO_USER_POOL_ID": PROD_POOL_ID,
        "COGNITO_CLIENT_ID": PROD_CLIENT_ID,
        "COGNITO_CLIENT_SECRET": "a-prod-secret",
    }


# ---------------------------------------------------------------------------
# Dataclass shape / immutability
# ---------------------------------------------------------------------------

class TestDataclasses:
    def test_plane_check_is_frozen(self) -> None:
        check = PlaneCheck(plane="x", resolved_env=AppEnv.TEST, ok=True, message="m")
        with pytest.raises(FrozenInstanceError):
            check.ok = False

    def test_consistency_report_is_frozen(self) -> None:
        report = ConsistencyReport(active_app_env=AppEnv.TEST, checks=[])
        with pytest.raises(FrozenInstanceError):
            report.active_app_env = AppEnv.PRODUCTION


# ---------------------------------------------------------------------------
# is_consistent derived logic
# ---------------------------------------------------------------------------

class TestIsConsistent:
    def test_is_consistent_all_ok_same_env_returns_true(self) -> None:
        report = ConsistencyReport(
            active_app_env=AppEnv.TEST,
            checks=[
                PlaneCheck("a", AppEnv.TEST, True, "ok"),
                PlaneCheck("b", AppEnv.TEST, True, "ok"),
            ],
        )
        assert report.is_consistent is True

    def test_is_consistent_a_failing_check_returns_false(self) -> None:
        report = ConsistencyReport(
            active_app_env=AppEnv.TEST,
            checks=[
                PlaneCheck("a", AppEnv.TEST, True, "ok"),
                PlaneCheck("b", None, False, "boom"),
            ],
        )
        assert report.is_consistent is False

    def test_is_consistent_half_cutover_returns_false(self) -> None:
        # All checks "ok" individually, but planes resolve to different envs.
        report = ConsistencyReport(
            active_app_env=AppEnv.TEST,
            checks=[
                PlaneCheck("a", AppEnv.TEST, True, "ok"),
                PlaneCheck("b", AppEnv.PRODUCTION, True, "ok"),
            ],
        )
        assert report.is_consistent is False

    def test_is_consistent_ignores_none_resolved_env_for_cutover(self) -> None:
        # A None resolved_env does not count toward the "all planes agree" set.
        report = ConsistencyReport(
            active_app_env=AppEnv.TEST,
            checks=[
                PlaneCheck("a", AppEnv.TEST, True, "ok"),
                PlaneCheck("b", None, True, "env-agnostic ok"),
            ],
        )
        assert report.is_consistent is True


# ---------------------------------------------------------------------------
# build_consistency_report — consistent cases
# ---------------------------------------------------------------------------

class TestConsistentCases:
    def test_build_report_test_env_all_agree_is_consistent(self) -> None:
        report = build_consistency_report(
            AppEnv.TEST,
            definition=ENVIRONMENT_DEFINITION,
            environ=_test_env_block(),
            registered_issuers=[TEST_ISSUER],
        )
        assert report.is_consistent is True
        assert all(c.ok for c in report.checks)

    def test_build_report_prod_env_all_agree_is_consistent(self) -> None:
        report = build_consistency_report(
            AppEnv.PRODUCTION,
            definition=ENVIRONMENT_DEFINITION,
            environ=_prod_env_block(),
            registered_issuers=[PROD_ISSUER],
        )
        assert report.is_consistent is True
        assert all(c.ok for c in report.checks)

    def test_build_report_registry_accepts_raw_pool_id(self) -> None:
        # Registry exposing a raw pool id (not a full issuer URL) is still matched.
        report = build_consistency_report(
            AppEnv.TEST,
            environ=_test_env_block(),
            registered_issuers=[TEST_POOL_ID],
        )
        pool_check = _find(report, "pool_registry")
        assert pool_check.ok is True

    def test_correctly_wired_env_will_not_block_fail_fast_startup(self) -> None:
        # Task 9.2 verification: a correctly-wired TEST and PRODUCTION environment
        # (identity block names the resolved pool/client, test secret empty, pool
        # registered on both the backend-registry and frontend-selected seams) is
        # fully consistent, so the strict fail-fast guard would NOT block startup.
        for app_env, env_block, issuer in (
            (AppEnv.TEST, _test_env_block(), TEST_ISSUER),
            (AppEnv.PRODUCTION, _prod_env_block(), PROD_ISSUER),
        ):
            report = build_consistency_report(
                app_env,
                definition=ENVIRONMENT_DEFINITION,
                environ=env_block,
                registered_issuers=[issuer],
            )
            assert report.is_consistent is True, report.format_report()
            # strict mode returns the report (does not raise) for a consistent env.
            strict_report = run_consistency_guard(
                app_env,
                strict=True,
                environ=env_block,
                registered_issuers=[issuer],
            )
            assert strict_report.is_consistent is True


# ---------------------------------------------------------------------------
# Frontend-selected pool vs backend registry (task 9.4, Req 4.2)
# ---------------------------------------------------------------------------

class TestFrontendPoolVsRegistry:
    """The frontend-selected pool must be present in the backend Pool_Registry."""

    def test_frontend_pool_registered_passes_and_names_frontend_side(self) -> None:
        report = build_consistency_report(
            AppEnv.TEST,
            environ=_test_env_block(),
            registered_issuers=[TEST_ISSUER],
        )
        check = _find(report, "frontend_pool_vs_registry")
        assert check.ok is True
        # Framed from the frontend-selected side (Req 4.2).
        assert "frontend-selected" in check.message
        assert TEST_POOL_ID in check.message

    def test_frontend_pool_not_registered_fails_and_names_both_sides(self) -> None:
        # APP_ENV=test selects the TEST pool, but only PROD is registered: the
        # frontend-selected pool is absent from the backend registry.
        report = build_consistency_report(
            AppEnv.TEST,
            environ=_test_env_block(),
            registered_issuers=[PROD_ISSUER],
        )
        check = _find(report, "frontend_pool_vs_registry")
        assert check.ok is False
        assert report.is_consistent is False
        # Names BOTH the frontend-selected pool and the registered pools (Req 4.2).
        assert TEST_POOL_ID in check.message
        assert PROD_POOL_ID in check.message

    def test_frontend_pool_matched_by_raw_pool_id(self) -> None:
        report = build_consistency_report(
            AppEnv.PRODUCTION,
            environ=_prod_env_block(),
            registered_issuers=[PROD_POOL_ID],  # raw id, not full issuer URL
        )
        check = _find(report, "frontend_pool_vs_registry")
        assert check.ok is True


# ---------------------------------------------------------------------------
# Each inconsistency type produces a failing PlaneCheck naming both sides
# ---------------------------------------------------------------------------

class TestInconsistencyTypes:
    def test_pool_not_registered_fails_and_names_both_sides(self) -> None:
        report = build_consistency_report(
            AppEnv.TEST,
            environ=_test_env_block(),
            registered_issuers=[PROD_ISSUER],  # only prod registered
        )
        check = _find(report, "pool_registry")
        assert check.ok is False
        assert report.is_consistent is False
        # Names the resolved pool AND the registered pools.
        assert TEST_POOL_ID in check.message
        assert PROD_POOL_ID in check.message

    def test_identity_block_pool_mismatch_fails_and_names_both_sides(self) -> None:
        env = _test_env_block()
        env["COGNITO_USER_POOL_ID"] = PROD_POOL_ID  # names the wrong pool
        report = build_consistency_report(
            AppEnv.TEST,
            environ=env,
            registered_issuers=[TEST_ISSUER],
        )
        check = _find(report, "identity_block")
        assert check.ok is False
        assert report.is_consistent is False
        assert PROD_POOL_ID in check.message  # actual
        assert TEST_POOL_ID in check.message  # expected

    def test_identity_block_client_mismatch_fails(self) -> None:
        env = _test_env_block()
        env["COGNITO_CLIENT_ID"] = "some-other-client"
        report = build_consistency_report(
            AppEnv.TEST,
            environ=env,
            registered_issuers=[TEST_ISSUER],
        )
        check = _find(report, "identity_block")
        assert check.ok is False
        assert "some-other-client" in check.message
        assert TEST_CLIENT_ID in check.message

    def test_test_pool_nonempty_secret_fails_without_echoing_secret(self) -> None:
        env = _test_env_block()
        secret_value = "super-secret-value-should-not-leak"
        env["COGNITO_CLIENT_SECRET"] = secret_value
        report = build_consistency_report(
            AppEnv.TEST,
            environ=env,
            registered_issuers=[TEST_ISSUER],
        )
        check = _find(report, "client_secret")
        assert check.ok is False
        assert report.is_consistent is False
        # Security (Req 6.6): the secret value must never appear in the message.
        assert secret_value not in check.message
        assert secret_value not in report.format_report()

    def test_prod_env_skips_client_secret_assertion(self) -> None:
        # The empty-secret rule applies to the test pool only.
        report = build_consistency_report(
            AppEnv.PRODUCTION,
            environ=_prod_env_block(),
            registered_issuers=[PROD_ISSUER],
        )
        check = _find(report, "client_secret")
        assert check.ok is True


# ---------------------------------------------------------------------------
# MySQL target isolation (task 12.4, Req 9.3, 9.5, 9.6)
# ---------------------------------------------------------------------------

import dataclasses

from environment.environment_definition import MysqlDef


def _definition_with_mysql(test_mysql: MysqlDef, prod_mysql: MysqlDef):
    """Clone the committed definition, swapping in the given MySQL targets."""
    base = ENVIRONMENT_DEFINITION
    return dataclasses.replace(
        base,
        test=dataclasses.replace(base.test, mysql=test_mysql),
        production=dataclasses.replace(base.production, mysql=prod_mysql),
    )


class TestMysqlTargetIsolation:
    """The resolved TEST MySQL target must be isolated from the PRODUCTION target."""

    def test_committed_definition_mysql_targets_are_isolated(self) -> None:
        # The committed definition declares distinct TEST/PROD targets, so the
        # mysql_target check passes under both APP_ENVs.
        for app_env, env_block, issuer in (
            (AppEnv.TEST, _test_env_block(), TEST_ISSUER),
            (AppEnv.PRODUCTION, _prod_env_block(), PROD_ISSUER),
        ):
            report = build_consistency_report(
                app_env,
                definition=ENVIRONMENT_DEFINITION,
                environ=env_block,
                registered_issuers=[issuer],
            )
            check = _find(report, "mysql_target")
            assert check.ok is True, check.message
            assert check.resolved_env == app_env

    def test_identical_test_and_prod_target_fails_isolation(self) -> None:
        # TEST and PRODUCTION resolve to the SAME connection identity/credentials
        # (as would happen if both pointed at the same env vars — e.g. co-hosted).
        shared_refs = dict(
            schema="finance",
            host_ref="DB_HOST",
            port_ref="DB_PORT",
            user_ref="DB_USER",
            password_ref="DB_PASSWORD",
        )
        definition = _definition_with_mysql(
            MysqlDef(target_label="TEST", **shared_refs),
            MysqlDef(target_label="PRODUCTION", **shared_refs),
        )
        report = build_consistency_report(
            AppEnv.TEST,
            definition=definition,
            environ=_test_env_block(),
            registered_issuers=[TEST_ISSUER],
        )
        check = _find(report, "mysql_target")
        assert check.ok is False
        assert report.is_consistent is False
        # Names the shared credential reference (non-secret) on both sides.
        assert "password_ref='DB_PASSWORD'" in check.message
        assert "not isolated" in check.message.lower()

    def test_non_finance_schema_fails(self) -> None:
        # A TEST target whose schema is not `finance` is rejected (Req 9.2).
        definition = _definition_with_mysql(
            MysqlDef(
                target_label="TEST",
                schema="testfinance",  # the removed-switch schema must not appear
                host_ref="DB_HOST_TEST",
                port_ref="DB_PORT_TEST",
                user_ref="DB_USER_TEST",
                password_ref="DB_PASSWORD_TEST",
            ),
            ENVIRONMENT_DEFINITION.production.mysql,
        )
        report = build_consistency_report(
            AppEnv.TEST,
            definition=definition,
            environ=_test_env_block(),
            registered_issuers=[TEST_ISSUER],
        )
        check = _find(report, "mysql_target")
        assert check.ok is False
        assert "finance" in check.message
        assert "testfinance" in check.message

    def test_mysql_target_check_never_echoes_secret_value(self) -> None:
        # The check compares env-var NAMES (refs), never secret VALUES (Req 6.6).
        secret_value = "super-secret-db-password-should-not-leak"
        definition = _definition_with_mysql(
            ENVIRONMENT_DEFINITION.test.mysql,
            ENVIRONMENT_DEFINITION.production.mysql,
        )
        import os
        from unittest.mock import patch

        with patch.dict(os.environ, {"DB_PASSWORD": secret_value}, clear=False):
            report = build_consistency_report(
                AppEnv.TEST,
                definition=definition,
                environ=_test_env_block(),
                registered_issuers=[TEST_ISSUER],
            )
        check = _find(report, "mysql_target")
        assert secret_value not in check.message
        assert secret_value not in report.format_report()


class TestMysqlActiveTargetMatchesAppEnv:
    """The ACTIVE resolved MySQL target must be the one the active APP_ENV declares."""

    def test_active_target_matches_app_env_passes(self) -> None:
        # The committed definition resolves APP_ENV=test to the TEST target and
        # APP_ENV=production to the PROD target — the active-target assertion passes.
        for app_env, env_block, issuer in (
            (AppEnv.TEST, _test_env_block(), TEST_ISSUER),
            (AppEnv.PRODUCTION, _prod_env_block(), PROD_ISSUER),
        ):
            report = build_consistency_report(
                app_env,
                definition=ENVIRONMENT_DEFINITION,
                environ=env_block,
                registered_issuers=[issuer],
            )
            check = _find(report, "mysql_target")
            assert check.ok is True, check.message
            assert "matches the active env" in check.message

    def test_active_target_naming_other_env_fails_and_names_both_sides(self) -> None:
        # Drive the active-vs-expected failure path directly: hand _check_mysql_target
        # a ResolvedConfig whose app_env is TEST but whose .mysql carries PRODUCTION's
        # connection identity (as a resolver bug would produce). TEST and PROD remain
        # distinct in the definition, so the isolation check passes and the
        # active-target assertion is what fails — naming both the active (PROD) refs
        # and the expected (TEST) refs.
        from environment.consistency_guard import _check_mysql_target

        resolved_test = resolve(AppEnv.TEST, ENVIRONMENT_DEFINITION)
        prod_mysql = resolve(AppEnv.PRODUCTION, ENVIRONMENT_DEFINITION).mysql
        # TEST env but carrying PROD's resolved mysql target.
        bugged = dataclasses.replace(resolved_test, mysql=prod_mysql)

        check = _check_mysql_target(bugged, ENVIRONMENT_DEFINITION)
        assert check.ok is False
        assert check.resolved_env is None  # does not pollute the cutover set
        # Names BOTH sides: the active (PROD) host_ref and the expected (TEST) one.
        assert ENVIRONMENT_DEFINITION.production.mysql.host_ref in check.message
        assert ENVIRONMENT_DEFINITION.test.mysql.host_ref in check.message
        assert "does not match" in check.message


# ---------------------------------------------------------------------------
# Flask API base URL check (task 13.1, Req 21.5, 21.6)
# ---------------------------------------------------------------------------

def _definition_with_flask_urls(test_url: str, prod_url: str):
    """Clone the committed definition, swapping in the given Flask API base URLs."""
    base = ENVIRONMENT_DEFINITION
    return dataclasses.replace(
        base,
        test=dataclasses.replace(base.test, flask_api_base_url=test_url),
        production=dataclasses.replace(base.production, flask_api_base_url=prod_url),
    )


class TestFlaskApiBaseUrl:
    """The resolved Flask API base URL must match the active APP_ENV (Req 21.5/21.6)."""

    def test_committed_definition_flask_urls_pass_for_both_envs(self) -> None:
        # The committed definition declares distinct TEST/PROD Flask URLs, so the
        # flask_api_base_url check passes under both APP_ENVs and resolves to the
        # active env (participating in half-cutover detection).
        for app_env, env_block, issuer in (
            (AppEnv.TEST, _test_env_block(), TEST_ISSUER),
            (AppEnv.PRODUCTION, _prod_env_block(), PROD_ISSUER),
        ):
            report = build_consistency_report(
                app_env,
                definition=ENVIRONMENT_DEFINITION,
                environ=env_block,
                registered_issuers=[issuer],
            )
            check = _find(report, "flask_api_base_url")
            assert check.ok is True, check.message
            assert check.resolved_env == app_env

    def test_identical_test_and_prod_flask_url_fails(self) -> None:
        # If both envs resolve to the SAME Flask URL the frontend cannot be isolated.
        # Use a non-URL-shaped sentinel for both envs: it still exercises the
        # identical-URL detection branch, and the asserted token is not URL-shaped
        # (avoids CodeQL's URL-substring-sanitization false positive on a test message).
        sentinel = "flask-url-sentinel-SAME"
        definition = _definition_with_flask_urls(sentinel, sentinel)
        report = build_consistency_report(
            AppEnv.TEST,
            definition=definition,
            environ=_test_env_block(),
            registered_issuers=[TEST_ISSUER],
        )
        check = _find(report, "flask_api_base_url")
        assert check.ok is False
        assert report.is_consistent is False
        assert "identical" in check.message
        assert sentinel in check.message

    def test_pass_case_names_both_sides(self) -> None:
        # The passing message names the active URL and the other-env URL (both sides).
        report = build_consistency_report(
            AppEnv.TEST,
            definition=ENVIRONMENT_DEFINITION,
            environ=_test_env_block(),
            registered_issuers=[TEST_ISSUER],
        )
        check = _find(report, "flask_api_base_url")
        test_url = ENVIRONMENT_DEFINITION.test.flask_api_base_url
        prod_url = ENVIRONMENT_DEFINITION.production.flask_api_base_url
        assert test_url in check.message
        assert prod_url in check.message

    def test_active_url_naming_other_env_fails_and_names_both_sides(self) -> None:
        # The "frontend built for the wrong env" seam: a ResolvedConfig whose
        # app_env is TEST but whose flask_api_base_url carries PRODUCTION's URL (as a
        # frontend pinned to the wrong env would call). Drive the check directly,
        # since the committed resolver reads one definition for both active and
        # expected and so cannot itself produce this cross-runtime divergence.
        from environment.consistency_guard import _check_flask_api_base_url

        resolved_test = resolve(AppEnv.TEST, ENVIRONMENT_DEFINITION)
        prod_url = ENVIRONMENT_DEFINITION.production.flask_api_base_url
        test_url = ENVIRONMENT_DEFINITION.test.flask_api_base_url
        bugged = dataclasses.replace(resolved_test, flask_api_base_url=prod_url)

        check = _check_flask_api_base_url(bugged, ENVIRONMENT_DEFINITION)
        assert check.ok is False
        assert check.resolved_env is None  # does not pollute the cutover set
        # Names BOTH sides: the active (PROD) URL and the expected (TEST) URL.
        assert prod_url in check.message
        assert test_url in check.message
        assert "the PRODUCTION URL" in check.message

    def test_flask_url_participates_in_half_cutover(self) -> None:
        # A passing flask check contributes its resolved_env; combined with another
        # plane resolving elsewhere it drives the aggregate half-cutover verdict.
        report = build_consistency_report(
            AppEnv.TEST,
            definition=ENVIRONMENT_DEFINITION,
            environ=_test_env_block(),
            registered_issuers=[TEST_ISSUER],
        )
        flask_check = _find(report, "flask_api_base_url")
        assert flask_check.resolved_env == AppEnv.TEST


# ---------------------------------------------------------------------------
# SAM plane checks (task 24, Req 4.4, 10.2, 14.4, 14.5, 19.4)
# ---------------------------------------------------------------------------

def _definition_with_sam(test_sam, prod_sam):
    """Clone the committed definition, swapping in the given SAM plane configs."""
    base = ENVIRONMENT_DEFINITION
    return dataclasses.replace(
        base,
        test=dataclasses.replace(base.test, sam=test_sam),
        production=dataclasses.replace(base.production, sam=prod_sam),
    )


class TestSamAuthorizerPool:
    """The resolved SAM authorizer pool must match the active APP_ENV (Req 14.4/14.5)."""

    def test_committed_definition_passes_for_both_envs(self) -> None:
        for app_env, env_block, issuer in (
            (AppEnv.TEST, _test_env_block(), TEST_ISSUER),
            (AppEnv.PRODUCTION, _prod_env_block(), PROD_ISSUER),
        ):
            report = build_consistency_report(
                app_env,
                definition=ENVIRONMENT_DEFINITION,
                environ=env_block,
                registered_issuers=[issuer],
            )
            check = _find(report, "sam_authorizer_pool")
            assert check.ok is True, check.message
            assert check.resolved_env == app_env

    def test_identical_pools_fail(self) -> None:
        same = dataclasses.replace(
            ENVIRONMENT_DEFINITION.test.sam, authorizer_pool_id="same-pool"
        )
        prod_same = dataclasses.replace(
            ENVIRONMENT_DEFINITION.production.sam, authorizer_pool_id="same-pool"
        )
        definition = _definition_with_sam(same, prod_same)
        report = build_consistency_report(
            AppEnv.TEST,
            definition=definition,
            environ=_test_env_block(),
            registered_issuers=[TEST_ISSUER],
        )
        check = _find(report, "sam_authorizer_pool")
        assert check.ok is False
        assert report.is_consistent is False
        assert "identical" in check.message

    def test_active_pool_naming_other_env_fails_and_names_both_sides(self) -> None:
        from environment.consistency_guard import _check_sam_authorizer_pool

        resolved_test = resolve(AppEnv.TEST, ENVIRONMENT_DEFINITION)
        prod_pool = ENVIRONMENT_DEFINITION.production.sam.authorizer_pool_id
        test_pool = ENVIRONMENT_DEFINITION.test.sam.authorizer_pool_id
        bugged_sam = dataclasses.replace(resolved_test.sam, authorizer_pool_id=prod_pool)
        bugged = dataclasses.replace(resolved_test, sam=bugged_sam)

        check = _check_sam_authorizer_pool(bugged, ENVIRONMENT_DEFINITION)
        assert check.ok is False
        assert check.resolved_env is None  # does not pollute the cutover set
        assert prod_pool in check.message
        assert test_pool in check.message
        assert "the PRODUCTION pool" in check.message


class TestSamApiBaseUrl:
    """The resolved SAM API base URL must match APP_ENV, placeholder-tolerant (Req 4.4)."""

    def test_committed_definition_passes_for_both_envs(self) -> None:
        # TEST api_base_url is a placeholder (stack not yet deployed) -> tolerated;
        # PROD is the real invoke URL -> concrete match. Both pass.
        for app_env, env_block, issuer in (
            (AppEnv.TEST, _test_env_block(), TEST_ISSUER),
            (AppEnv.PRODUCTION, _prod_env_block(), PROD_ISSUER),
        ):
            report = build_consistency_report(
                app_env,
                definition=ENVIRONMENT_DEFINITION,
                environ=env_block,
                registered_issuers=[issuer],
            )
            check = _find(report, "sam_api_base_url")
            assert check.ok is True, check.message
            assert check.resolved_env == app_env

    def test_test_placeholder_is_tolerated(self) -> None:
        # A not-yet-deployed TEST stack records a PLACEHOLDER SAM URL; the guard must
        # tolerate it (wired-but-not-observable) and pass on distinctness only. The
        # committed definition now carries the REAL deployed TEST URL (Phase 5a), so
        # inject a placeholder definition to exercise the tolerance branch directly.
        placeholder_sam = dataclasses.replace(
            ENVIRONMENT_DEFINITION.test.sam,
            api_base_url="https://PLACEHOLDER_TEST_API.execute-api.eu-west-1.amazonaws.com/test",
        )
        definition = _definition_with_sam(placeholder_sam, ENVIRONMENT_DEFINITION.production.sam)
        report = build_consistency_report(
            AppEnv.TEST,
            definition=definition,
            environ=_test_env_block(),
            registered_issuers=[TEST_ISSUER],
        )
        check = _find(report, "sam_api_base_url")
        assert check.ok is True
        assert "placeholder" in check.message.lower()

    def test_committed_test_url_is_concrete_not_placeholder(self) -> None:
        # Phase 5a Task 39: once the TEST stack is deployed, the committed TEST SAM
        # URL is a real endpoint (no PLACEHOLDER) and the guard does a concrete match.
        report = build_consistency_report(
            AppEnv.TEST,
            definition=ENVIRONMENT_DEFINITION,
            environ=_test_env_block(),
            registered_issuers=[TEST_ISSUER],
        )
        check = _find(report, "sam_api_base_url")
        assert check.ok is True
        assert "PLACEHOLDER" not in ENVIRONMENT_DEFINITION.test.sam.api_base_url
        assert "placeholder" not in check.message.lower()

    def test_identical_urls_fail(self) -> None:
        sentinel = "sam-url-sentinel-SAME"
        same = dataclasses.replace(ENVIRONMENT_DEFINITION.test.sam, api_base_url=sentinel)
        prod_same = dataclasses.replace(
            ENVIRONMENT_DEFINITION.production.sam, api_base_url=sentinel
        )
        definition = _definition_with_sam(same, prod_same)
        report = build_consistency_report(
            AppEnv.PRODUCTION,
            definition=definition,
            environ=_prod_env_block(),
            registered_issuers=[PROD_ISSUER],
        )
        check = _find(report, "sam_api_base_url")
        assert check.ok is False
        assert "identical" in check.message

    def test_concrete_active_url_naming_other_env_fails(self) -> None:
        from environment.consistency_guard import _check_sam_api_base_url

        # Give TEST a concrete (non-placeholder) URL that is actually PROD's URL.
        prod_url = ENVIRONMENT_DEFINITION.production.sam.api_base_url
        resolved_test = resolve(AppEnv.TEST, ENVIRONMENT_DEFINITION)
        bugged_sam = dataclasses.replace(resolved_test.sam, api_base_url=prod_url)
        bugged = dataclasses.replace(resolved_test, sam=bugged_sam)

        check = _check_sam_api_base_url(bugged, ENVIRONMENT_DEFINITION)
        assert check.ok is False
        assert check.resolved_env is None
        assert prod_url in check.message


class TestDynamoDbPrefix:
    """The resolved DynamoDB table prefix must match APP_ENV (Req 10.2/19.4)."""

    def test_committed_definition_passes_for_both_envs(self) -> None:
        for app_env, env_block, issuer, expected_prefix in (
            (AppEnv.TEST, _test_env_block(), TEST_ISSUER, "test_"),
            (AppEnv.PRODUCTION, _prod_env_block(), PROD_ISSUER, ""),
        ):
            report = build_consistency_report(
                app_env,
                definition=ENVIRONMENT_DEFINITION,
                environ=env_block,
                registered_issuers=[issuer],
            )
            check = _find(report, "dynamodb_prefix")
            assert check.ok is True, check.message
            assert check.resolved_env == app_env

    def test_identical_prefixes_fail(self) -> None:
        same = dataclasses.replace(ENVIRONMENT_DEFINITION.test.sam, table_prefix="x_")
        prod_same = dataclasses.replace(
            ENVIRONMENT_DEFINITION.production.sam, table_prefix="x_"
        )
        definition = _definition_with_sam(same, prod_same)
        report = build_consistency_report(
            AppEnv.TEST,
            definition=definition,
            environ=_test_env_block(),
            registered_issuers=[TEST_ISSUER],
        )
        check = _find(report, "dynamodb_prefix")
        assert check.ok is False
        assert "identical" in check.message

    def test_active_prefix_naming_other_env_fails(self) -> None:
        from environment.consistency_guard import _check_dynamodb_prefix

        # TEST runtime carrying PROD's empty prefix.
        resolved_test = resolve(AppEnv.TEST, ENVIRONMENT_DEFINITION)
        bugged_sam = dataclasses.replace(resolved_test.sam, table_prefix="")
        bugged = dataclasses.replace(resolved_test, sam=bugged_sam)

        check = _check_dynamodb_prefix(bugged, ENVIRONMENT_DEFINITION)
        assert check.ok is False
        assert check.resolved_env is None
        assert "test_" in check.message


# ---------------------------------------------------------------------------
# Half-cutover detection
# ---------------------------------------------------------------------------

class TestHalfCutover:
    def test_half_cutover_prod_identity_under_test_env_is_inconsistent(self) -> None:
        # APP_ENV=test resolves the TEST pool, but the identity block names PROD.
        report = build_consistency_report(
            AppEnv.TEST,
            environ=_prod_env_block(),
            registered_issuers=[TEST_ISSUER, PROD_ISSUER],
        )
        assert report.is_consistent is False


# ---------------------------------------------------------------------------
# run_consistency_guard — report-only vs strict
# ---------------------------------------------------------------------------

class TestRunConsistencyGuard:
    def test_run_guard_report_only_does_not_raise_on_inconsistency(
        self, caplog
    ) -> None:
        with caplog.at_level(logging.WARNING):
            report = run_consistency_guard(
                AppEnv.TEST,
                strict=False,
                environ=_test_env_block(),
                registered_issuers=[PROD_ISSUER],  # pool not registered -> fail
            )
        assert report.is_consistent is False
        # Logged, not raised.
        assert any("inconsistenc" in r.message.lower() for r in caplog.records)

    def test_run_guard_report_only_consistent_returns_report(self) -> None:
        report = run_consistency_guard(
            AppEnv.TEST,
            strict=False,
            environ=_test_env_block(),
            registered_issuers=[TEST_ISSUER],
        )
        assert report.is_consistent is True

    def test_run_guard_strict_raises_on_inconsistency(self) -> None:
        with pytest.raises(EnvironmentConfigError) as exc:
            run_consistency_guard(
                AppEnv.TEST,
                strict=True,
                environ=_test_env_block(),
                registered_issuers=[PROD_ISSUER],
            )
        # The raised message names the failing surface.
        assert "pool_registry" in str(exc.value)

    def test_run_guard_strict_consistent_does_not_raise(self) -> None:
        report = run_consistency_guard(
            AppEnv.TEST,
            strict=True,
            environ=_test_env_block(),
            registered_issuers=[TEST_ISSUER],
        )
        assert report.is_consistent is True

    def test_startup_hook_fails_fast_on_inconsistency(self, monkeypatch) -> None:
        # Phase 1 (task 9.1): the startup hook now RAISES on an inconsistency so the
        # unit refuses to start. The injected environ names the PROD pool under
        # APP_ENV=test (half-cutover) and the registry cannot be loaded here.
        monkeypatch.setattr(
            "environment.consistency_guard._load_registered_issuers",
            lambda: None,
        )
        with pytest.raises(EnvironmentConfigError):
            consistency_guard_startup_hook(
                AppEnv.TEST,
                environ={"COGNITO_USER_POOL_ID": PROD_POOL_ID},
            )

    def test_startup_hook_does_not_raise_on_consistent_env(
        self, monkeypatch
    ) -> None:
        # A correctly-wired TEST env is consistent, so the fail-fast hook returns the
        # report normally without raising.
        monkeypatch.setattr(
            "environment.consistency_guard._load_registered_issuers",
            lambda: [TEST_ISSUER],
        )
        report = consistency_guard_startup_hook(
            AppEnv.TEST,
            environ=_test_env_block(),
        )
        assert isinstance(report, ConsistencyReport)
        assert report.is_consistent is True


# ---------------------------------------------------------------------------
# Registry load failure degrades gracefully (report-only)
# ---------------------------------------------------------------------------

class TestRegistryLoadFailure:
    def test_registry_unloadable_becomes_failing_check(self, monkeypatch) -> None:
        # Force the internal loader to report "could not load".
        monkeypatch.setattr(
            "environment.consistency_guard._load_registered_issuers",
            lambda: None,
        )
        report = build_consistency_report(
            AppEnv.TEST,
            environ=_test_env_block(),
            registered_issuers=None,
        )
        check = _find(report, "pool_registry")
        assert check.ok is False
        assert "could not load" in check.message.lower()


# ---------------------------------------------------------------------------
# `check` CLI exit codes (task 9.3, Req 4.5, 4.6)
# ---------------------------------------------------------------------------

class TestCheckCliExitCodes:
    """``python -m environment.check`` exits non-zero on inconsistency, 0 otherwise."""

    def _consistent_report(self) -> ConsistencyReport:
        return ConsistencyReport(
            active_app_env=AppEnv.TEST,
            checks=[PlaneCheck("a", AppEnv.TEST, True, "ok")],
        )

    def _inconsistent_report(self) -> ConsistencyReport:
        return ConsistencyReport(
            active_app_env=AppEnv.TEST,
            checks=[PlaneCheck("a", None, False, "boom")],
        )

    def test_cli_returns_zero_when_consistent(self, monkeypatch, capsys) -> None:
        from environment import check as check_module

        monkeypatch.setenv("APP_ENV", "test")
        monkeypatch.setattr(
            check_module,
            "build_consistency_report",
            lambda app_env: self._consistent_report(),
        )
        rc = check_module.main([])
        assert rc == 0
        assert "CONSISTENT" in capsys.readouterr().out

    def test_cli_returns_one_when_inconsistent(self, monkeypatch, capsys) -> None:
        from environment import check as check_module

        monkeypatch.setenv("APP_ENV", "test")
        monkeypatch.setattr(
            check_module,
            "build_consistency_report",
            lambda app_env: self._inconsistent_report(),
        )
        rc = check_module.main([])
        assert rc == 1
        # The report is still printed so the failing surface is visible.
        assert "INCONSISTENT" in capsys.readouterr().out

    def test_cli_returns_two_when_app_env_unset(self, monkeypatch) -> None:
        from environment import check as check_module

        monkeypatch.delenv("APP_ENV", raising=False)
        rc = check_module.main([])
        assert rc == 2

    def test_cli_returns_two_when_app_env_unrecognized(self, monkeypatch) -> None:
        from environment import check as check_module

        monkeypatch.setenv("APP_ENV", "staging")
        rc = check_module.main([])
        assert rc == 2


def _find(report: ConsistencyReport, plane: str) -> PlaneCheck:
    """Return the single PlaneCheck for a plane name (fails if absent)."""
    matches = [c for c in report.checks if c.plane == plane]
    assert matches, f"no check named {plane!r} in {[c.plane for c in report.checks]}"
    return matches[0]
