"""
S4 D2 (amended, Option A) — the Pool A Pre-Token-Generation Lambda handler (T11).

Cognito **V2** Pre-Token-Generation trigger. At token issuance it:

1. Identifies the user (email/sub) from ``event["request"]["userAttributes"]``.
2. Reads that user's tenant list from the event's **verified** ``custom:tenants``
   claim (``_identify_tenants``) — the same claim the S2/S3 planes trust.
3. Reads the user's per-tenant roles + the active modules for those tenants from
   the **S3 DynamoDB projection** (read-only) via
   :class:`~sam.pretokengen.projection_governance_reader.ProjectionGovernanceReader`.
4. Resolves the per-tenant entitlement via the **shared** T1 resolver
   (:func:`auth.entitlement_resolver.resolve_entitlement`).
5. Encodes it compactly via the **shared** T4 codec
   (:func:`auth.entitlement_claim_codec.encode_entitlements`).
6. Stamps it **additively** into the V2 response at BOTH the id-token and
   access-token generation ``claimsToAddOrOverride`` under
   :data:`auth.entitlement_claim_codec.CLAIM_NAME` (``custom:entitlements``) —
   never touching ``cognito:groups`` / ``custom:tenants`` (R2.4).

Design amendment A — read the projection, not MySQL
---------------------------------------------------
The reader seam is the S3 one-directional DynamoDB projection, NOT MySQL
(``mysql-connector`` is no longer imported here or bundled). The Lambda runs in
AWS under Cognito's ~5s budget; reading Railway MySQL from AWS on every cold
start was an operational hazard and a bend of the S1 "a module Lambda never
opens a MySQL connection" contract. The pure T1 resolver and T4 codec are
UNCHANGED — only the *source* of the rows changed (projection instead of MySQL),
so the token claim and the Flask plane's ``role_cache.py`` decision still cannot
diverge for the same governance state.

The user's tenants come from the verified ``custom:tenants`` claim; each tenant's
projection partition is Queried once. An empty/absent ``custom:tenants`` yields an
empty tenant list → an empty entitlement (``{v:1,t:{}}``), which is a legitimate
state (especially before S5 registers real SAM-backed modules), NOT an error.

Fail-safe vs fail-fast (T12 — two DISTINCT behaviours)
------------------------------------------------------
These are deliberately different failure modes with opposite policies; the code
below keeps them apart so one can never be mistaken for the other:

- **Fail-fast — genuine MISCONFIGURATION (R2.5).** A missing/blank required env
  var for the projection table/region is a *deploy-time* fault, not a per-request
  hiccup. The reader resolves its table **fail-fast** on first use
  (:class:`services.dynamodb_client.DynamoDBConfigError` from
  :func:`services.projection_schema.get_projection_table_resource`). That error
  **propagates** out of the handler — it is NOT swallowed as a per-request omit.
  The fail-safe ``except`` explicitly re-raises the config-error types
  (``DynamoDBConfigError``, and ``GovernanceConfigError`` if still importable) as
  a belt-and-braces guard, so a config error can never be misread as a transient
  runtime error. (Reader construction is memoised at cold start via
  :func:`_init_reader`; the table itself resolves lazily on first read.)

- **Fail-safe — RUNTIME resolution failure at issuance (R2.3).** If the reader's
  DynamoDB Query, the resolver, the codec, or the stamping raise at runtime
  (query error, malformed item, resolver/codec error), the handler does **not**
  stamp a partial/garbage claim. It computes + encodes the claim value FULLY
  first and only stamps once the value is in hand, so stamping is
  **all-or-nothing** across BOTH token generations — a mid-way error leaves ZERO
  ``custom:entitlements`` rather than a half-written one. On failure it **omits**
  the claim (fail-closed for entitlement; readers fall back to their own source of
  truth), **logs** by user identity + the exception TYPE only (never secrets, DB
  config values, item contents, or exception payloads that could carry data), and
  returns a **valid, unmutated-re-our-claim** event so an entitlement blip never
  breaks login. (Design default = omit-and-log, not fail-the-issuance.)
"""

from __future__ import annotations

import logging
import os
import sys
from collections.abc import Mapping
from typing import Any

# --- Vendored-backend path wiring (see package docstring / T18 packaging) ------
# The deploy bundle vendors backend/src/auth/* + backend/src/services/* onto the
# artifact; adding backend/src here makes `import auth.*` / `import services.*`
# resolve in local test, CI, and the deployed Lambda alike.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_BACKEND_SRC = os.path.join(_REPO_ROOT, "backend", "src")
if _BACKEND_SRC not in sys.path:
    sys.path.insert(0, _BACKEND_SRC)

from auth.cognito_utils import _normalize_tenants_claim  # noqa: E402
from auth.entitlement_claim_codec import CLAIM_NAME, encode_entitlements  # noqa: E402
from auth.entitlement_resolver import resolve_entitlement  # noqa: E402
from services.dynamodb_client import DynamoDBConfigError  # noqa: E402
from services.module_registry import MODULE_REGISTRY  # noqa: E402

from sam.pretokengen.projection_governance_reader import (  # noqa: E402
    ProjectionGovernanceReader,
)

logger = logging.getLogger(__name__)

# The config-error types that are FAIL-FAST: a deploy-time misconfiguration that
# must PROPAGATE loudly, never be swallowed by the per-request fail-safe omit
# (R2.5). ``DynamoDBConfigError`` is the projection reader's config error (missing
# table/region env) — the only governance source this Lambda reads (Design
# amendment A: the DynamoDB projection, never MySQL).
_CONFIG_ERRORS: tuple[type[BaseException], ...] = (DynamoDBConfigError,)


def _identify_user(event: Mapping) -> str:
    """Extract the user's identity (email, falling back to sub) from a V2 event.

    Cognito puts the verified identity in ``event["request"]["userAttributes"]``.
    ``user_tenant_roles`` (projected as ``role#<email>#<role>``) is keyed by
    ``email`` (S3 contract), so we prefer the ``email`` attribute; ``sub`` is a
    last resort for logging/keying.

    Raises:
        ValueError: If neither ``email`` nor ``sub`` is present — the event does
            not identify a user, so there is no one to resolve entitlement for.
    """
    attributes = (event.get("request") or {}).get("userAttributes") or {}
    email = (attributes.get("email") or "").strip()
    if email:
        return email
    sub = (attributes.get("sub") or "").strip()
    if sub:
        return sub
    raise ValueError("Pre-Token-Generation event has no email/sub to identify the user")


def _identify_tenants(event: Mapping) -> list[str]:
    """Return the user's tenant list from the event's verified ``custom:tenants``.

    Cognito delivers ``custom:tenants`` as a real list, a JSON-encoded string, a
    JSON string with escaped quotes, or a scalar. This reuses the SAME shape
    adapter the S2/S3 planes use (:func:`auth.cognito_utils._normalize_tenants_claim`)
    rather than hand-rolling the parsing, so the Lambda and the Flask plane agree
    on how the claim is read.

    An empty/absent ``custom:tenants`` yields an empty list → an empty entitlement
    downstream (``{v:1,t:{}}``), which is a legitimate state, NOT an error (a user
    with no projectable tenants simply carries no per-tenant entitlement).
    """
    attributes = (event.get("request") or {}).get("userAttributes") or {}
    raw = attributes.get("custom:tenants", [])
    return _normalize_tenants_claim(raw)


def _build_reader() -> ProjectionGovernanceReader:
    """Build the read-only projection-backed governance reader.

    Its ``.table`` resolves **fail-fast** on first use (missing/blank projection
    table/region env → :class:`DynamoDBConfigError` from the S3 client), so a
    misconfigured Lambda fails loudly on the first read rather than silently
    omitting the claim (R2.5). Called from :func:`_init_reader` at cold start.
    """
    return ProjectionGovernanceReader()


# --- Cold-start (module-init) reader cache -------------------------------------
# The reader is built lazily-once and cached on the module for the life of a warm
# Lambda container. Its DynamoDB table resolves lazily + fail-fast on first read,
# so a misconfigured Lambda fails fast and visibly (DynamoDBConfigError) instead
# of silently omitting the entitlement claim for every login. That config error
# propagates out of the handler (fail-fast, R2.5); it is never caught by the
# per-request fail-safe path (R2.3).
_reader_cache: ProjectionGovernanceReader | None = None


def _init_reader() -> ProjectionGovernanceReader:
    """Return the process-cached reader, building it once at cold start.

    The build is memoised for the life of the warm Lambda container. The reader's
    ``.table`` (and thus the fail-fast config validation) resolves on the first
    read; a :class:`DynamoDBConfigError` raised there is NOT caught — it propagates
    so a misconfiguration surfaces loudly (R2.5).
    """
    global _reader_cache
    if _reader_cache is None:
        _reader_cache = _build_reader()
    return _reader_cache


def _stamp_claim_v2(event: dict, claim_name: str, claim_value: str) -> dict:
    """Additively stamp ``claim_name = claim_value`` into the V2 response.

    Sets the claim on BOTH the id-token and access-token generation blocks under
    ``claimsToAddOrOverride`` so the ID token AND the access token the API path
    verifies carry the entitlement (R2.1). Every intermediate container is created
    only if absent, and only the single ``claim_name`` key is written — existing
    claims (``cognito:groups`` / ``custom:tenants`` and anything else) are left
    untouched (R2.4, additive-only). Returns the mutated event.

    Cognito delivers the V2 event with these containers **present but ``null``**
    (``response``, ``claimsAndScopeOverrideDetails``, and each generation block are
    seeded as JSON ``null`` → Python ``None``), so a plain ``setdefault`` would
    return that existing ``None`` and the next ``.setdefault`` would raise
    ``'NoneType' object has no attribute 'setdefault'``. ``_child_dict`` therefore
    treats present-but-``None`` (or any non-mapping) exactly like absent — it
    installs a fresh dict — so stamping is robust to both the test shape (empty
    dicts) and the real Cognito shape (nulls).
    """

    def _child_dict(container: dict, key: str) -> dict:
        """Return ``container[key]`` as a dict, creating/replacing it if the key is
        absent or its value is ``None``/non-mapping. Additive: existing dict
        contents are preserved."""
        existing = container.get(key)
        if not isinstance(existing, dict):
            existing = {}
            container[key] = existing
        return existing

    response = _child_dict(event, "response")
    details = _child_dict(response, "claimsAndScopeOverrideDetails")

    for generation_key in ("idTokenGeneration", "accessTokenGeneration"):
        generation = _child_dict(details, generation_key)
        add_or_override = _child_dict(generation, "claimsToAddOrOverride")
        # Additive: only our claim key is set; nothing else is read or removed.
        add_or_override[claim_name] = claim_value

    return event


def handler(event: dict, context: Any = None) -> dict:
    """Cognito V2 Pre-Token-Generation entry point (T11 happy path).

    Reads the projection read-only for the user's ``custom:tenants``, resolves +
    encodes the entitlement, and stamps it additively onto both token generations.
    Returns the mutated event for Cognito.

    Args:
        event: The Cognito V2 Pre-Token-Generation event.
        context: The Lambda context (unused).

    Returns:
        The mutated event with ``custom:entitlements`` added to both the id- and
        access-token ``claimsToAddOrOverride`` (existing claims untouched).
    """
    user_identity = _identify_user(event)
    tenants = _identify_tenants(event)

    # --- Reader construction lives OUTSIDE the fail-safe try. ------------------
    # The reader itself is cheap to build; its table resolves fail-fast on first
    # use inside the try below. A DynamoDBConfigError from that resolution is a
    # deploy-time misconfiguration and MUST propagate loudly — the fail-safe
    # except re-raises the config-error types so it can never become an omit.
    reader = _init_reader()

    # --- FAIL-SAFE (R2.3): the whole runtime entitlement computation is guarded. -
    # Compute + encode the claim value FULLY first; only stamp once it is in hand,
    # so stamping is all-or-nothing across BOTH generations (no half-written claim).
    try:
        roles_by_tenant = reader.get_user_roles_by_tenant(user_identity, tenants)
        active_modules_by_tenant = reader.get_active_modules_by_tenant(tenants)
        entitlement_map = resolve_entitlement(
            roles_by_tenant, active_modules_by_tenant, MODULE_REGISTRY
        )
        claim_value = encode_entitlements(entitlement_map)
    except _CONFIG_ERRORS:
        # FAIL-FAST (R2.5): a config error (e.g. DynamoDBConfigError from the
        # fail-fast table resolution) is a deploy-time misconfiguration, never a
        # fail-safe omit. Re-raise so this except can never be the thing that
        # swallows it.
        raise
    except Exception as exc:
        # Transient runtime failure (DynamoDB query blip, malformed item,
        # resolver/codec error). Omit the claim (fail-closed for entitlement) and
        # log by identity + the exception TYPE only — NEVER secrets, config,
        # item contents, or the exception payload (which could carry data). The
        # event is returned unmutated re: our claim, so login is not broken.
        # Nothing was stamped, so this is all-or-nothing: ZERO custom:entitlements
        # on either generation.
        logger.warning(
            "PreTokenGen: omitting entitlement claim for user=%s after a "
            "resolution failure (%s); token issued without custom:entitlements",
            user_identity,
            type(exc).__name__,
        )
        return event

    logger.info(
        "PreTokenGen: stamped entitlement claim for user=%s tenants=%d",
        user_identity,
        len(entitlement_map),
    )
    return _stamp_claim_v2(event, CLAIM_NAME, claim_value)
