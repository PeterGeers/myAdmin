"""
S4 T15 — the Flask-plane entitlement reader (OPTIONAL, ADDITIVE).

This module offers an *optional* helper the Flask plane may adopt to answer
"what may this user do in this tenant?" preferring the resolved entitlement the
S4 Pre-Token-Generation Lambda stamps into the verified token
(``custom:entitlements``), and falling back to the historical MySQL path when
the token does not carry the answer.

Additive / no regression (R5.3)
-------------------------------
Nothing here changes the existing Flask authorization surface. The
``cognito_required`` / ``tenant_required`` decorators, the ``module_registry``
gate, and every existing permission check keep working exactly as before. This
module introduces **new** functions that a route may opt into; it does not
rewrite or wrap the current decorators, and importing it has no side effects.
Adoption is a choice, not a forced migration.

One rule, two carriers — the same-decision guarantee (R5.3 / R4.1)
------------------------------------------------------------------
The whole point of S4 is that the token claim and the Flask plane's server-side
decision can never disagree for the same MySQL state. This helper preserves that
by NOT reimplementing the resolution rule on either path:

- **Token (fast) path** — decode ``custom:entitlements`` via the shared codec
  (:func:`auth.entitlement_claim_codec.decode_entitlements`). That claim was
  produced by the Lambda from the SAME T1 resolver
  (:func:`auth.entitlement_resolver.resolve_entitlement`).
- **DB (fallback) path** — read the user's per-tenant roles via the real
  ``role_cache.get_tenant_roles``, gather the tenant's ACTIVE modules via the
  real ``module_registry.has_module`` gate, then compute the answer with the
  SAME T1 :func:`resolve_entitlement`.

Because both carriers run the identical T1 rule over the identical MySQL state,
the token-path and DB-path answers are guaranteed to match — this is exactly the
composition the T2 equivalence test
(``test_entitlement_resolver_flask_equivalence.py``) proved equal to the Flask
decision (``role_cache`` → module gate → permission expansion). The only
difference between the carriers is *when* each was computed (bounded staleness,
D4), never *what* rule was applied.

When does the fallback trigger?
-------------------------------
The token path is used only when the verified token carries a **usable** answer
for the tenant: the claim decodes, is the recognised version, is NOT an overflow
signal, is NOT a fallback (unknown/missing version / malformed), AND lists the
tenant. In every other case — claim absent, overflow, fallback required, or the
tenant simply not present in the claim — this helper falls back to the MySQL
path and computes the identical answer from the system of record.

Verified-only (R5.1)
--------------------
The token claim is read ONLY from an already-verified claims mapping (the Flask
plane already has the verified Cognito claims on the request). This module never
reads an entitlement from an unverified header.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping

from auth.entitlement_claim_codec import CLAIM_NAME, decode_entitlements
from auth.entitlement_resolver import resolve_entitlement
from auth.role_cache import get_tenant_roles
from services.module_registry import MODULE_REGISTRY, has_module

logger = logging.getLogger(__name__)

__all__ = [
    "has_capability",
    "resolve_capabilities",
    "resolve_capabilities_from_db",
]


def _active_modules_for_tenant(tenant: str, db, module_registry: Mapping) -> list[str]:
    """Return the modules that are ACTIVE for ``tenant`` (the real module gate).

    Uses the real :func:`services.module_registry.has_module` — the exact gate the
    Flask plane's ``module_required`` decorator enforces — over the registry's
    modules, so the fallback path's activity view is identical to production
    authorization. Reads ``tenant_modules`` only (backing-agnostic).
    """
    active: list[str] = []
    for module_name in module_registry:
        if has_module(db, tenant, module_name):
            active.append(module_name)
    return active


def resolve_capabilities_from_db(
    email: str,
    tenant: str,
    db,
    *,
    module_registry: Mapping = MODULE_REGISTRY,
) -> set[str]:
    """Compute a user's capabilities for ``tenant`` from MySQL — the fallback path.

    This is the historical Flask decision, composed from the REAL functions (not a
    reimplementation of the rule), and it is exactly the composition the T2
    equivalence test proved equal to the Flask plane's decision:

    1. ``role_cache.get_tenant_roles`` — the user's raw per-tenant roles (the same
       cached, MySQL-backed reader ``cognito_required`` uses).
    2. ``module_registry.has_module`` — the real module gate deciding which modules
       are ACTIVE for the tenant.
    3. :func:`auth.entitlement_resolver.resolve_entitlement` — the shared T1 rule
       that intersects roles with active modules and expands to capabilities.

    Args:
        email: The user's email (the ``user_tenant_roles`` key).
        tenant: The administration / tenant key.
        db: A ``DatabaseManager`` (or compatible) for the role + module reads.
        module_registry: The module registry; defaults to the real
            ``MODULE_REGISTRY``. Injectable for tests.

    Returns:
        The set of capability strings the user holds for ``tenant`` (empty set if
        none). ``{"*"}`` for a wildcard grant, matching the resolver.
    """
    roles = get_tenant_roles(email, tenant, db)
    active_modules = _active_modules_for_tenant(tenant, db, module_registry)

    # Reuse the SAME T1 resolver the Lambda used — one rule, two carriers.
    resolved = resolve_entitlement(
        user_roles_by_tenant={tenant: roles},
        active_modules_by_tenant={tenant: active_modules},
        module_registry=module_registry,
    )
    return set(resolved.get(tenant, []))


def resolve_capabilities(
    verified_claims: Mapping,
    tenant: str,
    db,
    *,
    module_registry: Mapping = MODULE_REGISTRY,
) -> set[str]:
    """Resolve a user's capabilities for ``tenant`` — token-preferred, DB-fallback.

    The optional, additive Flask-plane reader (R5.3). It prefers the resolved answer
    the S4 PreTokenGen Lambda stamped into the **verified** token and falls back to
    the MySQL path only when the token does not carry a usable answer for the
    tenant. Both paths yield the IDENTICAL decision for the same MySQL state because
    both run the shared T1 resolver (the token via the Lambda that produced the
    claim, the DB path here directly) — the R5.3 / R4.1 one-rule-two-carriers
    guarantee, proven equivalent to the Flask decision in T2.

    This does not touch or change any existing Flask authorization; it is a new
    helper a route may adopt.

    Token (fast) path — used when the token answers, NO DB read:
        the verified ``custom:entitlements`` claim decodes, is the recognised
        version, is not an overflow signal, does not require fallback, AND lists
        ``tenant``. Its capabilities for the tenant are returned directly.

    DB (fallback) path — used otherwise (claim absent / overflow / fallback /
        tenant not in the claim): the answer is computed from MySQL via
        :func:`resolve_capabilities_from_db` (``role_cache`` → module gate → T1
        resolver).

    Args:
        verified_claims: The already-verified Cognito claims for the request (the
            Flask plane has these on the request). The entitlement claim is read
            ONLY from here (R5.1) — never from an unverified header. ``email`` is
            taken from these claims for the fallback path.
        tenant: The administration / tenant key.
        db: A ``DatabaseManager`` (or compatible) used ONLY on the fallback path.
        module_registry: The module registry; defaults to the real
            ``MODULE_REGISTRY``. Injectable for tests.

    Returns:
        The set of capability strings the user holds for ``tenant``.
    """
    raw_claim = verified_claims.get(CLAIM_NAME) if verified_claims else None
    decoded = decode_entitlements(raw_claim)

    token_caps = decoded.capabilities_for(tenant)
    if token_caps is not None:
        # Token carries a usable per-user answer for this tenant — no DB read.
        return set(token_caps)

    # Token does not answer (absent / overflow / fallback / tenant not listed) —
    # fall back to MySQL and compute the identical answer via the shared T1 rule.
    email = verified_claims.get("email") if verified_claims else None
    if not email:
        # Without an identity we cannot query user_tenant_roles; fail closed
        # (no capabilities) rather than guess — mirrors the fail-safe stance.
        logger.warning(
            "entitlement fallback for tenant %s has no verified email claim; "
            "returning no capabilities (fail-closed)",
            tenant,
        )
        return set()

    return resolve_capabilities_from_db(
        email, tenant, db, module_registry=module_registry
    )


def has_capability(
    verified_claims: Mapping,
    tenant: str,
    capability: str,
    db,
    *,
    module_registry: Mapping = MODULE_REGISTRY,
) -> bool:
    """Return whether the user holds ``capability`` for ``tenant`` (token-preferred).

    A thin decision helper over :func:`resolve_capabilities`: prefers the verified
    token's resolved entitlement and falls back to MySQL, guaranteeing the same
    decision either way (R5.3). A wildcard grant (``"*"``) satisfies any capability,
    matching :func:`auth.cognito_utils.get_permissions_for_roles`.

    Args:
        verified_claims: The already-verified Cognito claims (R5.1).
        tenant: The administration / tenant key.
        capability: The capability token to check (e.g. ``"finance_read"``).
        db: A ``DatabaseManager`` used ONLY on the fallback path.
        module_registry: The module registry; defaults to the real ``MODULE_REGISTRY``.

    Returns:
        ``True`` iff the user holds ``capability`` (or a wildcard) for ``tenant``.
    """
    caps = resolve_capabilities(
        verified_claims, tenant, db, module_registry=module_registry
    )
    return "*" in caps or capability in caps
