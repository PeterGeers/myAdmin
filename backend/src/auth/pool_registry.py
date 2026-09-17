"""
Issuer->pool registry (fail-fast, env-driven, no defaults).

S2 / T3 — Define the issuer->pool registry.

The verifier (T5) must be able to validate tokens from *several* Cognito pools —
the standing **test pool** now (`myAdmin-test`, `eu-west-1_xyrlzfqbl`), production
**Pool A** (`eu-west-1_Hdp40eWmu`) in Phase 6, and Pool B later — without a code
change per pool. This module turns the single-entry T2 loader
(`test_pool_config.py`) into a proper **registry**: a map keyed by the token issuer
(`iss`) to its :class:`PoolConfig` (`{ jwks_uri, audience/client_id, pool_label }`).

Design contract (see `.kiro/specs/multi-tenant/s2-jwt-verification/design.md`,
R3.1/R3.2):

- **Pools are configuration, not code.** The set of pools is declared by an env var
  ``COGNITO_POOL_KEYS`` — a comma-separated list of *pool keys*. Each key ``K`` names
  a group of env vars ``{K}_COGNITO_ISSUER`` / ``{K}_COGNITO_JWKS_URI`` /
  ``{K}_COGNITO_CLIENT_ID`` / ``{K}_COGNITO_POOL_LABEL``. Adding a pool (Pool A in
  Phase 6, Pool B later) is: append its key to ``COGNITO_POOL_KEYS`` and set its four
  vars. **No code change.**
- **The test pool is the first entry now.** Its key is ``TEST`` and it reuses the
  exact ``TEST_COGNITO_*`` vars the T2 loader already reads — so the existing
  ``.env`` wiring works unchanged and the registry is a strict generalization.
- **Fail-fast, no defaults** (R1.3, no-dangerous-fallbacks): a missing/blank required
  var for a *declared* pool raises :class:`PoolRegistryError`. A blank/absent
  ``COGNITO_POOL_KEYS`` raises too — an empty registry is a misconfiguration, never a
  silent "trust nothing / trust anything" fallback.
- **Unknown issuer is explicit.** :meth:`PoolRegistry.get` returns ``None`` for an
  issuer not in the registry and :meth:`PoolRegistry.require` raises
  :class:`UnknownIssuerError`; the verifier (T5) turns either into a 401. The registry
  never guesses a pool for an unrecognized ``iss``.

Environment variables (all public, non-secret Cognito identifiers — safe to commit
to ``.env`` / ``.env.example``; the app-clients have no secret):

    COGNITO_POOL_KEYS            Comma-separated pool keys, e.g. "TEST" or "TEST,PROD_A"
    {KEY}_COGNITO_ISSUER         Full issuer URL (the `iss` claim value)
    {KEY}_COGNITO_JWKS_URI       JWKS endpoint for the pool
    {KEY}_COGNITO_CLIENT_ID      App-client id used as audience/client_id
    {KEY}_COGNITO_POOL_LABEL     Human-readable pool label (e.g. "myAdmin-test")
"""

import os
from collections.abc import Iterable, Mapping

# Reuse the T2 registry-entry type rather than duplicating it.
from auth.test_pool_config import PoolConfig

# The env var that declares which pools exist. Its value is a comma-separated list
# of pool keys; each key prefixes that pool's four required vars.
_POOL_KEYS_ENV_VAR = "COGNITO_POOL_KEYS"

# The per-pool var suffixes, in the order used for PoolConfig construction. The
# suffix order also drives the "missing var" error message when several are unset.
_POOL_VAR_SUFFIXES = (
    "COGNITO_ISSUER",
    "COGNITO_JWKS_URI",
    "COGNITO_CLIENT_ID",
    "COGNITO_POOL_LABEL",
)


class PoolRegistryError(RuntimeError):
    """Raised when the issuer->pool registry is misconfigured.

    This is a hard configuration error, not a runtime auth failure: the process is
    not wired to a valid set of pools, so it cannot verify tokens safely. Fail loudly
    rather than fall back to an empty or partial registry (no-dangerous-fallbacks).
    """


class UnknownIssuerError(PoolRegistryError):
    """Raised by :meth:`PoolRegistry.require` when an `iss` has no registered pool.

    The verifier (T5) maps this to a **401** — an unrecognized issuer is rejected, it
    is never verified against a guessed pool.
    """

    def __init__(self, iss: str):
        self.iss = iss
        super().__init__(
            f"No pool is registered for issuer '{iss}'. The token's issuer is not in "
            f"the configured issuer->pool registry ({_POOL_KEYS_ENV_VAR}); reject it."
        )


def _require_pool_env(pool_key: str, suffix: str, environ: Mapping[str, str]) -> str:
    """Return a required per-pool env var's value, or raise if missing/blank.

    No default is ever substituted (no-dangerous-fallbacks guardrail).

    Args:
        pool_key: The declared pool key (e.g. "TEST"), used as the var prefix.
        suffix: The var suffix (e.g. "COGNITO_ISSUER").
        environ: The environment mapping to read from.

    Returns:
        The stripped, non-empty value.

    Raises:
        PoolRegistryError: The variable is unset or blank.
    """
    name = f"{pool_key}_{suffix}"
    value = environ.get(name)
    if value is None or value.strip() == "":
        expected = ", ".join(f"{pool_key}_{s}" for s in _POOL_VAR_SUFFIXES)
        raise PoolRegistryError(
            f"Required env var '{name}' for pool '{pool_key}' is missing or blank. "
            f"Every pool declared in {_POOL_KEYS_ENV_VAR} must set all of: {expected}. "
            f"There is no default fallback (no-dangerous-fallbacks)."
        )
    return value.strip()


def _load_pool_entry(pool_key: str, environ: Mapping[str, str]) -> PoolConfig:
    """Build one :class:`PoolConfig` from a declared pool key's env vars."""
    return PoolConfig(
        iss=_require_pool_env(pool_key, "COGNITO_ISSUER", environ),
        jwks_uri=_require_pool_env(pool_key, "COGNITO_JWKS_URI", environ),
        audience=_require_pool_env(pool_key, "COGNITO_CLIENT_ID", environ),
        pool_label=_require_pool_env(pool_key, "COGNITO_POOL_LABEL", environ),
    )


def _parse_pool_keys(raw: str | None) -> list:
    """Split the COGNITO_POOL_KEYS value into a clean, ordered, de-duplicated list.

    Args:
        raw: The raw env value (may be None).

    Returns:
        Ordered list of non-empty, stripped pool keys (duplicates removed,
        first occurrence wins).

    Raises:
        PoolRegistryError: The value is missing or contains no usable key.
    """
    if raw is None or raw.strip() == "":
        raise PoolRegistryError(
            f"'{_POOL_KEYS_ENV_VAR}' is missing or blank. Declare at least one pool "
            f"key (the standing test pool is 'TEST'); an empty registry is a "
            f"misconfiguration, not a valid state (no-dangerous-fallbacks)."
        )
    keys = []
    for token in raw.split(","):
        key = token.strip()
        if key and key not in keys:
            keys.append(key)
    if not keys:
        raise PoolRegistryError(
            f"'{_POOL_KEYS_ENV_VAR}' contained no usable pool key (value: {raw!r})."
        )
    return keys


class PoolRegistry:
    """An immutable issuer->pool map with explicit unknown-issuer handling.

    Look up a pool by the token's ``iss`` claim: :meth:`get` returns ``None`` for an
    unknown issuer, :meth:`require` raises :class:`UnknownIssuerError`. The verifier
    (T5) turns either into a 401.
    """

    def __init__(self, entries: Iterable[PoolConfig]):
        by_iss: dict[str, PoolConfig] = {}
        for entry in entries:
            if entry.iss in by_iss:
                raise PoolRegistryError(
                    f"Two pools declare the same issuer '{entry.iss}' "
                    f"({by_iss[entry.iss].pool_label} and {entry.pool_label}); "
                    f"issuers must be unique in the registry."
                )
            by_iss[entry.iss] = entry
        self._by_iss = by_iss

    def get(self, iss: str) -> PoolConfig | None:
        """Return the pool for ``iss``, or ``None`` if the issuer is unknown."""
        return self._by_iss.get(iss)

    def require(self, iss: str) -> PoolConfig:
        """Return the pool for ``iss`` or raise :class:`UnknownIssuerError`.

        Use this on the verify path so an unrecognized issuer is an explicit,
        loggable rejection rather than a silent ``None``.
        """
        pool = self._by_iss.get(iss)
        if pool is None:
            raise UnknownIssuerError(iss)
        return pool

    def issuers(self) -> list:
        """Return the registered issuers (for diagnostics/logging, not decisions)."""
        return list(self._by_iss.keys())

    def __len__(self) -> int:
        return len(self._by_iss)

    def __contains__(self, iss: object) -> bool:
        return iss in self._by_iss


def load_pool_registry(environ: Mapping[str, str] | None = None) -> PoolRegistry:
    """Load the issuer->pool registry from the environment (fail-fast, no defaults).

    Reads ``COGNITO_POOL_KEYS`` for the declared pool keys, then loads each pool's
    four required vars into a :class:`PoolConfig`. Any missing/blank required var —
    or a blank ``COGNITO_POOL_KEYS`` — raises :class:`PoolRegistryError`; the loader
    never returns a partial, empty, or defaulted registry.

    Args:
        environ: Optional environment mapping (defaults to :data:`os.environ`).
            Injectable for tests.

    Returns:
        A populated :class:`PoolRegistry`.

    Raises:
        PoolRegistryError: The registry is unconfigured or a declared pool is
            missing a required var.
    """
    env = os.environ if environ is None else environ
    pool_keys = _parse_pool_keys(env.get(_POOL_KEYS_ENV_VAR))
    entries = [_load_pool_entry(key, env) for key in pool_keys]
    return PoolRegistry(entries)
