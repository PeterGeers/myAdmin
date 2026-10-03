"""Unit tests for the app-bootstrap environment wiring (environment/bootstrap.py).

Covers S3 / T3.1 + T3.5 — Requirements 1.3, 2.1, 2.3:

- ``bootstrap_environment`` with ``APP_ENV=test`` resolves and stores the
  ``ResolvedConfig`` (and the active ``AppEnv``) on ``app.config``.
- ``bootstrap_environment`` with ``APP_ENV=production`` resolves the production
  config.
- ``bootstrap_environment`` with ``APP_ENV`` unset or unrecognized fail-fasts with
  ``EnvironmentConfigError`` (no silent default — the running unit refuses to start).

The tests use a minimal fake app exposing only a dict-like ``.config`` (the only
surface ``bootstrap_environment`` touches), and inject ``environ`` so nothing reads
the real process environment or hits AWS/DB.
"""

import pytest

from environment.app_env import AppEnv, EnvironmentConfigError
from environment.bootstrap import (
    APP_ENV_CONFIG_KEY,
    RESOLVED_ENV_CONFIG_KEY,
    bootstrap_environment,
)
from environment.environment_definition import (
    ENVIRONMENT_DEFINITION,
    PROD_POOL_ID,
    TEST_POOL_ID,
)
from environment.resolver import ResolvedConfig, resolve


class _FakeApp:
    """Minimal stand-in for a Flask app — only a dict ``config`` is needed."""

    def __init__(self) -> None:
        self.config: dict = {}


class TestBootstrapResolvesAndStores:
    """APP_ENV=test / production resolves and is stored on app.config."""

    def test_test_env_resolves_and_stores_resolved_config(self) -> None:
        app = _FakeApp()

        # run_guard=False: this test asserts the resolution wiring only; the guard
        # has its own test module and would try to load the pool registry.
        resolved = bootstrap_environment(
            app, environ={"APP_ENV": "test"}, run_guard=False
        )

        assert isinstance(resolved, ResolvedConfig)
        assert resolved.app_env is AppEnv.TEST
        assert resolved.cognito.pool_id == TEST_POOL_ID

        # Stored on app.config for every plane to consume (Req 2.1, 2.3).
        assert app.config[APP_ENV_CONFIG_KEY] is AppEnv.TEST
        assert app.config[RESOLVED_ENV_CONFIG_KEY] is resolved
        # Matches the central resolver output (single decision point, Req 2.1).
        assert app.config[RESOLVED_ENV_CONFIG_KEY] == resolve(
            AppEnv.TEST, ENVIRONMENT_DEFINITION
        )

    def test_production_env_resolves_production_config(self) -> None:
        app = _FakeApp()

        resolved = bootstrap_environment(
            app, environ={"APP_ENV": "production"}, run_guard=False
        )

        assert resolved.app_env is AppEnv.PRODUCTION
        assert resolved.cognito.pool_id == PROD_POOL_ID
        assert app.config[APP_ENV_CONFIG_KEY] is AppEnv.PRODUCTION

    def test_whitespace_padded_value_is_accepted(self) -> None:
        app = _FakeApp()
        resolved = bootstrap_environment(
            app, environ={"APP_ENV": "  test  "}, run_guard=False
        )
        assert resolved.app_env is AppEnv.TEST


class TestBootstrapFailFast:
    """Unset/unrecognized APP_ENV refuses to start (no default — Req 1.3)."""

    def test_unset_app_env_raises(self) -> None:
        app = _FakeApp()
        with pytest.raises(EnvironmentConfigError) as exc_info:
            bootstrap_environment(app, environ={}, run_guard=False)
        assert "APP_ENV is unset" in str(exc_info.value)
        # Nothing was stored — the unit refused to start.
        assert RESOLVED_ENV_CONFIG_KEY not in app.config
        assert APP_ENV_CONFIG_KEY not in app.config

    def test_empty_app_env_raises(self) -> None:
        app = _FakeApp()
        with pytest.raises(EnvironmentConfigError):
            bootstrap_environment(app, environ={"APP_ENV": ""}, run_guard=False)

    def test_unrecognized_app_env_raises(self) -> None:
        app = _FakeApp()
        with pytest.raises(EnvironmentConfigError) as exc_info:
            bootstrap_environment(
                app, environ={"APP_ENV": "staging"}, run_guard=False
            )
        assert "APP_ENV='staging' is not recognized" in str(exc_info.value)


class TestBootstrapGuardIsFailFast:
    """Phase 1 (task 9.1): the guard raises on an inconsistent startup env."""

    def test_guard_raises_on_inconsistent_env(self, monkeypatch) -> None:
        # With run_guard=True the consistency guard runs in fail-fast mode. The
        # injected environ carries no identity block and the Pool_Registry cannot be
        # loaded in this unit-test env, so the guard is INCONSISTENT and must raise
        # EnvironmentConfigError — the unit refuses to start (task 9.1).
        # Force the registry loader to report "could not load" so the test does not
        # depend on ambient COGNITO_POOL_KEYS config.
        monkeypatch.setattr(
            "environment.consistency_guard._load_registered_issuers",
            lambda: None,
        )
        app = _FakeApp()
        with pytest.raises(EnvironmentConfigError):
            bootstrap_environment(app, environ={"APP_ENV": "test"}, run_guard=True)

    def test_guard_does_not_block_consistent_env(self, monkeypatch) -> None:
        # A correctly-wired TEST environment (identity block names the resolved
        # pool/client, empty test secret, pool registered) is CONSISTENT, so the
        # fail-fast guard must NOT raise and startup proceeds normally.
        from environment.environment_definition import TEST_CLIENT_ID

        test_issuer = (
            f"https://cognito-idp.eu-west-1.amazonaws.com/{TEST_POOL_ID}"
        )
        monkeypatch.setattr(
            "environment.consistency_guard._load_registered_issuers",
            lambda: [test_issuer],
        )
        app = _FakeApp()
        resolved = bootstrap_environment(
            app,
            environ={
                "APP_ENV": "test",
                "COGNITO_USER_POOL_ID": TEST_POOL_ID,
                "COGNITO_CLIENT_ID": TEST_CLIENT_ID,
                "COGNITO_CLIENT_SECRET": "",
            },
            run_guard=True,
        )
        assert resolved.app_env is AppEnv.TEST
        assert app.config[RESOLVED_ENV_CONFIG_KEY] is resolved
