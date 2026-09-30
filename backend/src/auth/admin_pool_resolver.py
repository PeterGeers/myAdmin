"""
Shared registry-backed pool resolution for admin Cognito operations.

Bugfix ``cognito-admin-pool-resolution`` (RCA R1 + R2). Admin Cognito operations
historically resolved their target user pool from the legacy single-pool env var
``COGNITO_USER_POOL_ID`` (which points at the PROD pool in every environment), while
**token validation** resolves the pool correctly through the issuer->pool registry
(:mod:`auth.pool_registry` + :mod:`auth.cognito_utils`) keyed by the token ``iss``.
The result is a split-brain: a dev/test user validates against the TEST pool but every
admin op silently acts on the PROD pool.

This module is the ONE shared resolver every admin op calls to obtain its target
``user_pool_id``. It is the admin-side mirror of how ``cognito_utils`` resolves the
validation pool and reuses :func:`auth.pool_registry.load_pool_registry` /
:class:`~auth.pool_registry.PoolRegistry` and the SAME :class:`JWTVerifier` unchanged.

Two entry modes:

* **Token mode** (:func:`resolve_pool_id_for_token`) — resolve by the caller token's
  cryptographically verified ``iss``, mirroring validation exactly (2.3).
* **Email mode** (:func:`resolve_pool_id_for_email`) — resolve which registered pool a
  user belongs to for tokenless flows (forgot-password), by probing ``admin_get_user``
  across the registered pools in declared order (2.5), with an explicit disambiguation
  rule when an email exists in more than one pool (2.6).

Registry-first, never legacy-first (3.4): the legacy ``COGNITO_USER_POOL_ID`` is
consulted ONLY when the registry is absent (``COGNITO_POOL_KEYS`` unset/blank),
mirroring ``cognito_utils._get_jwt_verifier`` step (2) exactly. When the registry is
present the legacy var is never read.
"""

import logging
import os

import boto3
from botocore.exceptions import ClientError

from auth.pool_registry import PoolRegistry, PoolRegistryError, load_pool_registry

logger = logging.getLogger(__name__)

# The env var that declares the multi-pool registry (mirrors cognito_utils selection).
_POOL_KEYS_ENV_VAR = "COGNITO_POOL_KEYS"
# The legacy single-pool var, consulted ONLY in the registry-absent branch (3.4).
_LEGACY_POOL_ID_ENV_VAR = "COGNITO_USER_POOL_ID"


# --- Errors ---------------------------------------------------------------------


class PoolResolutionError(RuntimeError):
    """Raised when the target pool cannot be resolved at all.

    Covers a misconfigured registry (a :class:`PoolRegistryError` surfaced rather than
    silently falling back to the legacy var) and the registry-absent branch when the
    legacy ``COGNITO_USER_POOL_ID`` is also unset. Never a silent wrong-pool action —
    consistent with the no-dangerous-fallbacks guardrail the validation path uses.
    """


class UserPoolNotFoundError(PoolResolutionError):
    """Raised when an email is not found in any registered pool (email mode).

    Not-found-surfacing ops map this to a clear non-500 (e.g. HTTP 404). The
    forgot-password path passes ``anti_enumeration=True`` and receives ``None`` instead,
    preserving anti-enumeration (2.7).
    """

    def __init__(self, email: str):
        self.email = email
        super().__init__(
            f"User '{email}' was not found in any registered Cognito pool."
        )


class AmbiguousUserPoolError(PoolResolutionError):
    """Raised when an email exists in more than one registered pool and there is no
    caller token to disambiguate (2.6).

    Never a silent first-match. Callers map it deterministically: forgot-password
    treats it as "cannot safely act" (still returns success without acting);
    not-found-surfacing ops return a clear non-500 (HTTP 409 Conflict).
    """

    def __init__(self, email: str, hits: list[str]):
        self.email = email
        self.hits = list(hits)
        super().__init__(
            f"User '{email}' exists in more than one registered pool "
            f"({', '.join(self.hits)}); refusing to guess (no caller token to "
            f"disambiguate)."
        )


# --- Pool-id derivation (shared) ------------------------------------------------


def pool_id_from_issuer(iss: str) -> str:
    """Return the user pool id (trailing path segment) from a Cognito issuer URL.

    ``PoolConfig`` has no ``user_pool_id`` field; the pool id is the last path segment
    of the issuer URL
    ``https://cognito-idp.{region}.amazonaws.com/{user_pool_id}``.

    Args:
        iss: The issuer URL (the ``iss`` claim value).

    Returns:
        The trailing path segment, e.g. ``eu-west-1_xyrlzfqbl``.
    """
    return iss.rstrip("/").rsplit("/", 1)[-1]


# --- Registry access, mirroring cognito_utils selection order -------------------


def _registry_or_none() -> PoolRegistry | None:
    """Return the issuer->pool registry, or ``None`` when it is not configured.

    Mirrors ``cognito_utils._get_jwt_verifier`` steps (1)/(2) EXACTLY:

    1. ``COGNITO_POOL_KEYS`` present and non-blank -> :func:`load_pool_registry`. A
       :class:`PoolRegistryError` surfaces as :class:`PoolResolutionError` — never a
       silent legacy read.
    2. Otherwise -> ``None`` (registry absent -> caller uses the legacy fallback).

    Returns:
        A populated :class:`PoolRegistry`, or ``None`` when the registry is absent.

    Raises:
        PoolResolutionError: ``COGNITO_POOL_KEYS`` is declared but the registry is
            misconfigured.
    """
    pool_keys = os.environ.get(_POOL_KEYS_ENV_VAR)
    if pool_keys is not None and pool_keys.strip() != "":
        try:
            return load_pool_registry()
        except PoolRegistryError as e:
            raise PoolResolutionError(
                f"Issuer->pool registry is misconfigured; cannot resolve the target "
                f"pool ({e}). Refusing to fall back to the legacy single-pool var "
                f"when the registry is declared."
            ) from e
    return None


def _legacy_pool_id_or_raise() -> str:
    """Return the legacy single-pool id, ONLY valid in the registry-absent branch.

    Mirrors ``cognito_utils._get_jwt_verifier`` step (2): when ``COGNITO_POOL_KEYS``
    is absent, ``COGNITO_USER_POOL_ID`` is permitted as the single-pool fallback (3.4).
    If it too is unset, raise :class:`PoolResolutionError` — no silent wrong-pool
    action.

    Returns:
        The legacy ``COGNITO_USER_POOL_ID`` value.

    Raises:
        PoolResolutionError: The legacy var is unset/blank in the fallback branch.
    """
    legacy = os.environ.get(_LEGACY_POOL_ID_ENV_VAR)
    if legacy is None or legacy.strip() == "":
        raise PoolResolutionError(
            f"Cannot resolve the target Cognito pool: the registry "
            f"({_POOL_KEYS_ENV_VAR}) is not configured and the legacy fallback "
            f"({_LEGACY_POOL_ID_ENV_VAR}) is also unset."
        )
    return legacy.strip()


def _entries_in_declared_order(registry: PoolRegistry):
    """Return the registry's :class:`PoolConfig` entries in declaration order.

    Prefers the additive read-only :meth:`PoolRegistry.entries_in_declared_order`
    accessor (Task 3.2). Until that accessor lands this falls back to reconstructing
    declared order from the registry's public API (``issuers()`` preserves the
    ``COGNITO_POOL_KEYS`` declaration order because the registry stores entries in an
    insertion-ordered dict). The fallback is read-only and does not touch the
    validation path.
    """
    accessor = getattr(registry, "entries_in_declared_order", None)
    if callable(accessor):
        return list(accessor())
    return [registry.require(iss) for iss in registry.issuers()]


# --- Cognito probe helper -------------------------------------------------------


def _get_cognito_client():
    """Build a Cognito Identity Provider client for admin probes.

    Isolated in a tiny factory so tests can patch it (``admin_pool_resolver.boto3``)
    without a real AWS call.
    """
    return boto3.client(
        "cognito-idp",
        region_name=os.getenv("AWS_REGION", "eu-west-1"),
    )


def admin_user_exists(pool_id: str, email: str, *, client=None) -> bool:
    """Return whether ``email`` exists in the pool ``pool_id`` (probe, no leak).

    Performs ``admin_get_user`` and maps ``UserNotFoundException`` to ``False``. The
    boolean result is used only internally by :func:`resolve_pool_id_for_email`; it is
    never surfaced to callers, so probing does not create an enumeration oracle (2.7).

    Args:
        pool_id: The Cognito user pool id to probe.
        email: The username/email to look up.
        client: Optional pre-built ``cognito-idp`` client to probe with. A caller that
            already holds a client (e.g. :class:`~services.cognito_service.CognitoService`)
            passes its own so the probe and the subsequent admin op share one client;
            when ``None`` a client is built via :func:`_get_cognito_client`.

    Returns:
        ``True`` if the user exists in ``pool_id``, ``False`` if not found.

    Raises:
        ClientError: Any non ``UserNotFoundException`` error is propagated (a genuine
            failure is not silently treated as "absent").
    """
    if client is None:
        client = _get_cognito_client()
    try:
        client.admin_get_user(UserPoolId=pool_id, Username=email)
        return True
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") == "UserNotFoundException":
            return False
        raise


# --- Disambiguation (2.6) -------------------------------------------------------


def disambiguate(
    hits: list[str],
    registry: PoolRegistry,
    *,
    caller_token: str | None = None,
) -> str:
    """Resolve an email that exists in more than one registered pool (2.6).

    Explicit, documented rule — never a silent first-match:

    1. **Token context wins when available.** If the operation also carries a caller
       token whose registry pool is among ``hits``, resolve to that pool. This keeps
       admin ops consistent with the pool the caller is authenticated against.
    2. **Otherwise, ambiguity is an error, not a guess.** Raise
       :class:`AmbiguousUserPoolError`.

    Args:
        hits: The pool ids the email was found in (len >= 2 at the call site).
        registry: The issuer->pool registry (unused directly today; kept for the
            documented signature and future per-pool rules).
        caller_token: Optional caller JWT to disambiguate by the authenticated pool.

    Returns:
        The single resolved pool id.

    Raises:
        AmbiguousUserPoolError: More than one pool matches and no caller token
            disambiguates.
    """
    if caller_token is not None:
        token_pool_id = resolve_pool_id_for_token(caller_token)
        if token_pool_id in hits:
            return token_pool_id
    raise AmbiguousUserPoolError(email="<unknown>", hits=hits)


# --- Token mode (2.3) -----------------------------------------------------------


def resolve_pool_id_for_token(jwt_token: str) -> str:
    """Resolve the target pool id from a caller's verified token ``iss`` (2.3).

    Reuses the SAME :class:`JWTVerifier` validation uses (via
    ``cognito_utils._get_jwt_verifier``), so token mode resolves the pool from the
    same cryptographically verified ``iss`` as validation — no second, weaker path.

    Args:
        jwt_token: Raw JWT (without the ``Bearer `` prefix).

    Returns:
        The registry-resolved user pool id for the token's issuer.

    Raises:
        PoolResolutionError: The registry is misconfigured, or (registry-absent
            branch) the legacy var is unset.
        Verifier / registry errors: An unverifiable token or an unregistered issuer
            surfaces the underlying verification/registry error (rejected, never a
            guessed pool).
    """
    registry = _registry_or_none()
    if registry is None:
        return _legacy_pool_id_or_raise()

    # Reuse the SAME verifier validation uses — do NOT build a second, weaker path.
    from auth.cognito_utils import _get_jwt_verifier

    verifier = _get_jwt_verifier()
    if verifier is None:
        raise PoolResolutionError(
            "Cannot resolve the target pool from the caller token: no JWT verifier is "
            "configured for token-mode resolution."
        )

    payload = verifier.verify_token(jwt_token)
    iss = payload.get("iss")
    if not iss:
        raise PoolResolutionError("Verified token carries no issuer (iss).")

    pool = registry.require(iss)  # UnknownIssuerError -> reject
    return pool_id_from_issuer(pool.iss)


# --- Email mode (2.5 / 2.6 / 2.7) ----------------------------------------------


def resolve_pool_id_for_email(
    email: str,
    *,
    anti_enumeration: bool = False,
    caller_token: str | None = None,
    client=None,
) -> str | None:
    """Resolve which registered pool ``email`` belongs to (email mode, 2.5).

    Probes ``admin_get_user`` across the registered pools in declared order
    (:meth:`PoolRegistry.entries_in_declared_order`). Zero new persistent state, always
    consistent with the registry (the single source of truth).

    Args:
        email: The user's email/username.
        anti_enumeration: When ``True`` (forgot-password), a not-found returns ``None``
            instead of raising, so the endpoint can still report success (2.7 / 3.5).
        caller_token: Optional caller JWT used only to disambiguate a multi-pool hit
            (2.6).
        client: Optional pre-built ``cognito-idp`` client used for the ``admin_get_user``
            probes. A caller that already holds a client passes its own so probe and
            op share one client; when ``None`` a client is built per probe.

    Returns:
        The resolved user pool id, or ``None`` when not found and
        ``anti_enumeration=True``.

    Raises:
        UserPoolNotFoundError: Not found in any pool and ``anti_enumeration`` is False.
        AmbiguousUserPoolError: Found in more than one pool and no caller token
            disambiguates.
        PoolResolutionError: Registry misconfigured, or (registry-absent branch) the
            legacy var is unset.
    """
    registry = _registry_or_none()
    if registry is None:
        return _legacy_pool_id_or_raise()

    candidate_pool_ids = [
        pool_id_from_issuer(p.iss) for p in _entries_in_declared_order(registry)
    ]
    hits = [
        pid
        for pid in candidate_pool_ids
        if admin_user_exists(pid, email, client=client)
    ]

    if len(hits) == 0:
        if anti_enumeration:
            return None
        raise UserPoolNotFoundError(email)
    if len(hits) > 1:
        try:
            return disambiguate(hits, registry, caller_token=caller_token)
        except AmbiguousUserPoolError:
            # Re-raise with the real email (disambiguate has no email context).
            raise AmbiguousUserPoolError(email, hits) from None
    return hits[0]
