"""Unit tests for the fail-fast test-pool registry config loader (S2 / T2).

Validates: the issuer->pool registry env wiring is fail-fast with NO defaults —
missing or blank required vars raise TestPoolConfigError, and a fully-populated
environment loads into a PoolConfig with the expected registry shape
(iss -> { jwks_uri, audience/client_id, pool_label }).
"""

import os
from unittest.mock import patch

import pytest

from auth.test_pool_config import (
    PoolConfig,
    TestPoolConfigError,
    load_test_pool_config,
)

# A complete, valid test-pool environment (public, non-secret identifiers).
_VALID_TEST_POOL_ENV = {
    "TEST_COGNITO_ISSUER": "https://cognito-idp.eu-west-1.amazonaws.com/eu-west-1_xyrlzfqbl",
    "TEST_COGNITO_JWKS_URI": "https://cognito-idp.eu-west-1.amazonaws.com/eu-west-1_xyrlzfqbl/.well-known/jwks.json",
    "TEST_COGNITO_CLIENT_ID": "43s15cm8qcgg8an85udt0e087u",
    "TEST_COGNITO_POOL_LABEL": "myAdmin-test",
}


def test_load_test_pool_config_all_vars_present_returns_pool_config():
    """A fully-populated environment loads into the expected registry entry."""
    with patch.dict(os.environ, _VALID_TEST_POOL_ENV, clear=True):
        cfg = load_test_pool_config()

    assert isinstance(cfg, PoolConfig)
    assert cfg.iss == _VALID_TEST_POOL_ENV["TEST_COGNITO_ISSUER"]
    assert cfg.jwks_uri == _VALID_TEST_POOL_ENV["TEST_COGNITO_JWKS_URI"]
    assert cfg.audience == _VALID_TEST_POOL_ENV["TEST_COGNITO_CLIENT_ID"]
    assert cfg.pool_label == _VALID_TEST_POOL_ENV["TEST_COGNITO_POOL_LABEL"]


def test_load_test_pool_config_strips_surrounding_whitespace():
    """Values are stripped so trailing newlines/spaces in .env do not leak in."""
    padded = {k: f"  {v}  " for k, v in _VALID_TEST_POOL_ENV.items()}
    with patch.dict(os.environ, padded, clear=True):
        cfg = load_test_pool_config()

    assert cfg.iss == _VALID_TEST_POOL_ENV["TEST_COGNITO_ISSUER"]
    assert cfg.jwks_uri == _VALID_TEST_POOL_ENV["TEST_COGNITO_JWKS_URI"]


@pytest.mark.parametrize("missing_var", sorted(_VALID_TEST_POOL_ENV.keys()))
def test_load_test_pool_config_missing_var_raises(missing_var):
    """Removing any single required var fails fast — no default fallback."""
    env = {k: v for k, v in _VALID_TEST_POOL_ENV.items() if k != missing_var}
    with patch.dict(os.environ, env, clear=True):
        with pytest.raises(TestPoolConfigError) as exc_info:
            load_test_pool_config()

    assert missing_var in str(exc_info.value)


@pytest.mark.parametrize("blank_var", sorted(_VALID_TEST_POOL_ENV.keys()))
def test_load_test_pool_config_blank_var_raises(blank_var):
    """A blank (whitespace-only) value is treated as missing and fails fast."""
    env = dict(_VALID_TEST_POOL_ENV)
    env[blank_var] = "   "
    with patch.dict(os.environ, env, clear=True):
        with pytest.raises(TestPoolConfigError) as exc_info:
            load_test_pool_config()

    assert blank_var in str(exc_info.value)


def test_load_test_pool_config_empty_environment_raises():
    """With none of the vars set, the loader throws rather than defaulting."""
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(TestPoolConfigError):
            load_test_pool_config()
