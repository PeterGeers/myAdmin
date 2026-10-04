"""
Module-plane JWT verification — issuer->pool registry (extracted from ``auth_utils``).

Config-not-code, fail-fast — mirrors the Flask plane T3. Re-exported from
:mod:`sam.shared.auth_utils`; the public import surface is unchanged.

Reads ``COGNITO_POOL_KEYS`` for the declared pool keys, then loads each pool's four
required env vars into a :class:`PoolConfig`. Any missing/blank var — or a blank
``COGNITO_POOL_KEYS`` — raises :class:`PoolRegistryError`. The loader never returns a
partial, empty, or defaulted registry (no-dangerous-fallbacks).
"""

from __future__ import annotations

import os
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from sam.shared._auth_errors import PoolRegistryError, UnknownIssuerError

# The env var that declares which pools exist: a comma-separated list of pool keys.
# Each key K prefixes that pool's four required vars ({K}_COGNITO_ISSUER, etc.).
_POOL_KEYS_ENV_VAR = "COGNITO_POOL_KEYS"

_POOL_VAR_SUFFIXES = (
    "COGNITO_ISSUER",
    "COGNITO_JWKS_URI",
    "COGNITO_CLIENT_ID",
    "COGNITO_POOL_LABEL",
)


@dataclass(frozen=True)
class PoolConfig:
    """A single issuer->pool registry entry.

    Attributes:
        iss: The token issuer (the ``iss`` claim value) — the registry key.
        jwks_uri: JWKS endpoint used to fetch signing keys for this pool.
        audience: App-client id, matched against ``aud`` / ``client_id``.
        pool_label: Human-readable label for logs/diagnostics.
    """

    iss: str
    jwks_uri: str
    audience: str
    pool_label: str


def _require_pool_env(pool_key: str, suffix: str, environ: Mapping[str, str]) -> str:
    """Return a required per-pool env var, or raise if missing/blank (no defaults)."""
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


def _parse_pool_keys(raw: str | None) -> list[str]:
    """Split COGNITO_POOL_KEYS into a clean, ordered, de-duplicated list (fail-fast)."""
    if raw is None or raw.strip() == "":
        raise PoolRegistryError(
            f"'{_POOL_KEYS_ENV_VAR}' is missing or blank. Declare at least one pool "
            f"key; an empty registry is a misconfiguration, not a valid state "
            f"(no-dangerous-fallbacks)."
        )
    keys: list[str] = []
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

    :meth:`get` returns ``None`` for an unknown issuer; :meth:`require` raises
    :class:`UnknownIssuerError`. The verifier turns either into a 401. The registry
    never guesses a pool for an unrecognized ``iss``.
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
        """Return the pool for ``iss`` or raise :class:`UnknownIssuerError`."""
        pool = self._by_iss.get(iss)
        if pool is None:
            raise UnknownIssuerError(iss)
        return pool

    def issuers(self) -> list[str]:
        """Return the registered issuers (diagnostics only, not decisions)."""
        return list(self._by_iss.keys())

    def __len__(self) -> int:
        return len(self._by_iss)

    def __contains__(self, iss: object) -> bool:
        return iss in self._by_iss


def load_pool_registry(environ: Mapping[str, str] | None = None) -> PoolRegistry:
    """Load the issuer->pool registry from the environment (fail-fast, no defaults).

    Reads ``COGNITO_POOL_KEYS`` for the declared pool keys, then loads each pool's
    four required vars into a :class:`PoolConfig`. Any missing/blank var — or a blank
    ``COGNITO_POOL_KEYS`` — raises :class:`PoolRegistryError`. The loader never
    returns a partial, empty, or defaulted registry.
    """
    env = os.environ if environ is None else environ
    pool_keys = _parse_pool_keys(env.get(_POOL_KEYS_ENV_VAR))
    entries = [_load_pool_entry(key, env) for key in pool_keys]
    return PoolRegistry(entries)


__all__ = [
    "PoolConfig",
    "PoolRegistry",
    "load_pool_registry",
]
