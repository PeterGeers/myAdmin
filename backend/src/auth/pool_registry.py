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
from dataclasses import dataclass

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

    def entries_in_declared_order(self) -> list[PoolConfig]:
        """Return the :class:`PoolConfig` entries in ``COGNITO_POOL_KEYS`` order.

        Read-only, additive accessor. The registry is built by
        :func:`load_pool_registry` from the declared pool keys in order, and the
        backing ``dict`` preserves insertion order, so the returned list mirrors the
        ``COGNITO_POOL_KEYS`` declaration order.

        This is used by the admin-pool resolver's email-mode probe, which walks the
        pools in a deterministic, declared order. It does not touch any existing
        lookup behavior (:meth:`get`/:meth:`require`/:meth:`issuers`) that the
        validation path relies on.

        Returns:
            The pools as an ordered list, matching ``COGNITO_POOL_KEYS`` order.
        """
        return list(self._by_iss.values())

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


# ===========================================================================
# Active resolved identity (test-environment spec — Common/test-environment, T6)
# ===========================================================================
#
# Design contract (`.kiro/specs/Common/test-environment/first-draft/design.md` §6):
#
#     "`backend/src/auth/pool_registry.py` keeps its `COGNITO_POOL_KEYS` loader,
#      but the ACTIVE identity (which pool this unit *is*) comes from
#      `ResolvedConfig.cognito`; the guard checks that identity is registered."
#
# The multi-pool verification registry above (`load_pool_registry` / `PoolRegistry`)
# is UNCHANGED — the verifier (`JWTVerifier`) must still validate tokens from several
# pools (the test pool AND the production pools) regardless of which environment this
# unit *is*. What this section adds is ORTHOGONAL and ADDITIVE: a way to obtain the
# unit's OWN active identity — the single pool/client that `APP_ENV` selects via the
# Environment_Resolver (Req 8.3) — plus a coherence check that the active pool is
# among the registered verification pools (Req 4.1).
#
# Fail-fast / no-default discipline is preserved: deriving the active identity never
# invents a pool, and `active_pool_from_registry` raises `UnknownIssuerError` (not a
# silent fallback) when the resolved pool is absent from the registry.

# The env var naming the Cognito region, consulted (with AWS_REGION) only to build the
# issuer URL from a resolved pool id. Mirrors `cognito_utils` / `jwt_verifier`.
_REGION_ENV_VARS = ("COGNITO_REGION", "AWS_REGION")
_DEFAULT_REGION = "eu-west-1"


def _resolve_region(environ: Mapping[str, str]) -> str:
    """Return the Cognito region for building issuer URLs.

    Reads ``COGNITO_REGION`` then ``AWS_REGION``; falls back to ``eu-west-1`` — the
    only account/region the pools live in (see ``23-aws-accounts.md``). The region is
    a non-secret public identifier, so a default here is a convenience, not a
    dangerous environment fallback (the environment selection itself is already pinned
    by ``APP_ENV`` upstream).
    """
    for name in _REGION_ENV_VARS:
        value = environ.get(name)
        if value and value.strip():
            return value.strip()
    return _DEFAULT_REGION


def issuer_for_pool_id(pool_id: str, region: str) -> str:
    """Build the Cognito issuer URL (`iss` claim value) for a user pool id.

    The issuer URL embeds the pool id as its trailing path segment:
    ``https://cognito-idp.{region}.amazonaws.com/{pool_id}`` — the same shape
    :class:`~auth.jwt_verifier.JWTVerifier` constructs. This is the inverse of
    :func:`auth.admin_pool_resolver.pool_id_from_issuer`.

    Args:
        pool_id: The Cognito User Pool id (e.g. ``eu-west-1_xyrlzfqbl``).
        region: The AWS region the pool lives in.

    Returns:
        The full issuer URL.
    """
    return f"https://cognito-idp.{region}.amazonaws.com/{pool_id}"


@dataclass(frozen=True)
class ResolvedIdentity:
    """The running unit's OWN active Cognito identity, resolved from ``APP_ENV``.

    This is distinct from the verification :class:`PoolRegistry` (which may hold
    several pools): it names the single pool/client that the active environment
    selects (Req 8.3). It is derived from ``ResolvedConfig.cognito`` produced by the
    Environment_Resolver, never from a hostname or an incidental signal.

    Attributes:
        iss: The issuer URL for the active pool (the registry key for a cross-check).
        pool_id: The active Cognito User Pool id (public identifier).
        client_id: The active Cognito App Client id (public identifier).
        client_secret: The active client secret value, or ``""`` when the pool has
            no secret (the test pool — Req 7.3, 8.4). Resolved from the env var the
            definition references, so no secret value is hardcoded.
        pool_label: Human-readable pool label (e.g. ``myAdmin-test``, ``myAdmin``).
    """

    iss: str
    pool_id: str
    client_id: str
    client_secret: str
    pool_label: str

    @property
    def has_client_secret(self) -> bool:
        """``True`` iff a non-empty client secret is set for the active pool."""
        return bool(self.client_secret and self.client_secret.strip())


def resolved_identity(
    resolved_cognito, environ: Mapping[str, str] | None = None
) -> ResolvedIdentity:
    """Derive the active identity from the resolver's ``ResolvedConfig.cognito``.

    This is the single way to obtain which pool/client THIS unit *is* for the active
    ``APP_ENV`` (Req 6.1, 6.3, 8.3). The resolver hands us public identifiers plus a
    *reference* to the client secret (an env var name, or ``""`` for the test pool);
    this function dereferences that secret ref against the environment so the caller
    gets the concrete-but-possibly-empty secret without the definition ever embedding
    a real value (Req 8.5).

    Empty-secret handling (Req 7.3, 8.4): the test pool's ``client_secret_ref`` is the
    empty string in the Environment_Definition, which yields an empty ``client_secret``
    here — the test app-client has no secret, and no code path requires one. A
    non-empty ``client_secret_ref`` is treated as the NAME of an env var holding the
    secret; if that var is unset/blank the resolved secret is empty (fail-safe for the
    secret value specifically — the environment selection is already pinned by
    ``APP_ENV``, so an empty secret here never silently flips the environment).

    Args:
        resolved_cognito: The ``ResolvedConfig.cognito`` object from the
            Environment_Resolver (duck-typed: must expose ``pool_id``, ``client_id``,
            ``client_secret_ref`` and ``pool_label``). Not imported as a type to keep
            :mod:`auth.pool_registry` free of a hard dependency on the environment
            package.
        environ: Optional environment mapping (defaults to :data:`os.environ`).
            Injectable for tests.

    Returns:
        The :class:`ResolvedIdentity` for the active environment.
    """
    env = os.environ if environ is None else environ
    region = _resolve_region(env)
    pool_id = resolved_cognito.pool_id
    iss = issuer_for_pool_id(pool_id, region)

    # Dereference the client-secret ref. The test pool uses "" (no secret, Req 7.3/8.4);
    # a non-empty ref names an env var holding the secret value.
    secret_ref = (resolved_cognito.client_secret_ref or "").strip()
    if secret_ref == "":
        client_secret = ""
    else:
        client_secret = (env.get(secret_ref) or "").strip()

    return ResolvedIdentity(
        iss=iss,
        pool_id=pool_id,
        client_id=resolved_cognito.client_id,
        client_secret=client_secret,
        pool_label=resolved_cognito.pool_label,
    )


def active_pool_from_registry(
    resolved_cognito,
    registry: PoolRegistry,
    environ: Mapping[str, str] | None = None,
) -> PoolConfig:
    """Return the registered :class:`PoolConfig` for the active resolved pool.

    Coherence check (Req 4.1, 8.3): the pool that ``APP_ENV`` selects as this unit's
    OWN identity MUST be one of the pools the verification registry knows about. This
    resolves the active identity (via :func:`resolved_identity`), looks its issuer up
    in the (multi-pool, unchanged) registry, and returns that entry.

    This does NOT reduce the registry to a single pool — the registry keeps every
    pool for verification. It only asserts the active identity is represented there,
    and hands back the registry's own entry for that pool so callers reuse one source
    of truth for the active pool's JWKS/audience.

    Args:
        resolved_cognito: The ``ResolvedConfig.cognito`` from the resolver.
        registry: The loaded multi-pool verification :class:`PoolRegistry`.
        environ: Optional environment mapping (defaults to :data:`os.environ`).

    Returns:
        The registry's :class:`PoolConfig` for the active resolved pool.

    Raises:
        UnknownIssuerError: The active resolved pool's issuer is not registered —
            an explicit, loggable failure, never a silent wrong-pool fallback.
    """
    identity = resolved_identity(resolved_cognito, environ=environ)
    # Prefer an exact issuer match (the registry key). Fall back to a pool-id-substring
    # match so the check is robust whether the resolver's region matches the registry's
    # issuer region exactly (the issuer URL embeds the pool id either way).
    entry = registry.get(identity.iss)
    if entry is not None:
        return entry
    for candidate_iss in registry.issuers():
        if identity.pool_id in candidate_iss:
            return registry.require(candidate_iss)
    raise UnknownIssuerError(identity.iss)
