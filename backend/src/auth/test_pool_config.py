"""
Test-pool issuer->pool registry configuration (fail-fast, no defaults).

S2 / T2 — Wire the test environment for local runs.

This module reads the standing **test Cognito pool** (`myAdmin-test`,
`eu-west-1_xyrlzfqbl`) coordinates from the environment and exposes them as a
single issuer->pool registry entry. It is the *validation environment* the S2
verifier (T3's registry, T5's verifier extension) is developed against, before
production Pool A is ever touched.

Design contract (see `.kiro/specs/multi-tenant/s2-jwt-verification/design.md`,
R3.1/R3.2): a registry entry is `iss -> { jwks_uri, audience/client_id,
pool_label }`. Pools are **configuration, not code** — adding a pool is a set of
env vars, never a code change.

Fail-fast guardrail (R1.3, `aws-accounts.md` "critical env vars must fail fast"):
every required variable throws `TestPoolConfigError` when missing or blank. There
are **no defaults** — a misconfigured environment can never silently fall back to
a wrong (or production) pool. This is the no-dangerous-fallbacks guardrail applied
to identity config.

Environment variables (all required; missing -> throw):
    TEST_COGNITO_ISSUER      Full issuer URL (the `iss` claim value)
    TEST_COGNITO_JWKS_URI    JWKS endpoint for the test pool
    TEST_COGNITO_CLIENT_ID   App-client id used as audience/client_id
    TEST_COGNITO_POOL_LABEL  Human-readable pool label (e.g. "myAdmin-test")

These are public, non-secret identifiers (no client secret — the test app-client
uses USER_PASSWORD_AUTH), so they are safe to commit to `.env` / `.env.example`.
"""

import os
from dataclasses import dataclass

# The environment variables that make up the test-pool registry entry.
# Order is intentional: it drives the error message when several are missing.
_REQUIRED_TEST_POOL_ENV_VARS = (
    "TEST_COGNITO_ISSUER",
    "TEST_COGNITO_JWKS_URI",
    "TEST_COGNITO_CLIENT_ID",
    "TEST_COGNITO_POOL_LABEL",
)


class TestPoolConfigError(RuntimeError):
    """Raised when the test-pool registry env vars are missing or blank.

    This is a hard configuration error, not a runtime auth failure: the process
    is not wired to the standing test pool, so identity work cannot be validated
    safely. Fail loudly rather than fall back to a default pool.
    """

    # Not a pytest test class (the name begins with "Test" only by domain naming).
    __test__ = False


@dataclass(frozen=True)
class PoolConfig:
    """A single issuer->pool registry entry.

    Attributes:
        iss: The token issuer (the `iss` claim value) — the registry key.
        jwks_uri: JWKS endpoint used to fetch signing keys for this pool.
        audience: App-client id, matched against `aud` / `client_id`.
        pool_label: Human-readable label for logs/diagnostics.
    """

    iss: str
    jwks_uri: str
    audience: str
    pool_label: str


def _require_env(name: str) -> str:
    """Return a required env var's value, or raise if missing/blank.

    No default is ever substituted (no-dangerous-fallbacks guardrail).

    Args:
        name: Environment variable name.

    Returns:
        The stripped, non-empty value.

    Raises:
        TestPoolConfigError: The variable is unset or blank.
    """
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        raise TestPoolConfigError(
            f"Required test-pool env var '{name}' is missing or blank. "
            f"The test environment must be wired to the standing test Cognito "
            f"pool (myAdmin-test); there is no default fallback. "
            f"Set all of: {', '.join(_REQUIRED_TEST_POOL_ENV_VARS)}."
        )
    return value.strip()


def load_test_pool_config() -> PoolConfig:
    """Load the standing test pool's registry entry from the environment.

    Fail-fast: if any required variable is missing or blank, raises
    ``TestPoolConfigError`` — never returns a partial or defaulted config.

    Returns:
        A fully-populated :class:`PoolConfig` for the test pool.

    Raises:
        TestPoolConfigError: One or more required env vars are missing/blank.
    """
    return PoolConfig(
        iss=_require_env("TEST_COGNITO_ISSUER"),
        jwks_uri=_require_env("TEST_COGNITO_JWKS_URI"),
        audience=_require_env("TEST_COGNITO_CLIENT_ID"),
        pool_label=_require_env("TEST_COGNITO_POOL_LABEL"),
    )
