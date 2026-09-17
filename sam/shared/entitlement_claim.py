"""
S4 D3 — module-plane VENDORED decoder for the ``custom:entitlements`` claim (T14).

This is a **vendored mirror** of the *decode* half of the single-source codec
``backend/src/auth/entitlement_claim_codec.py`` (T4). It exists so the module
plane's shared auth layer (:mod:`sam.shared.auth_utils`) can decode the entitlement
claim **without importing anything from ``backend/src``** — the ``sam/shared``
package is deliberately standalone (see ``sam/conftest.py`` and the ``auth_utils``
module docstring): it is vendored / shipped as a Lambda **layer** to three separate
modules (``members`` / ``events`` / ``webshop``), so it must not depend on the Flask
backend package the way the dedicated ``sam/pretokengen`` Lambda does.

Why vendor instead of ``sys.path``-import backend/src (as ``sam/pretokengen`` does)?
-----------------------------------------------------------------------------------
``sam/pretokengen`` is one dedicated Lambda that ships with ``backend/src`` vendored
onto its artifact, so it can ``import auth.entitlement_claim_codec`` directly. The
``sam/shared`` layer has a **stricter** contract — no ``backend/src`` dependency at
all, so any of the three modules can consume it as a standalone layer. The decoder is
tiny and **pure** (stdlib ``json`` only), so vendoring a copy is cheap and keeps the
layer boundary intact.

Drift protection
----------------
Because this is a copy, it can drift from the single source. ``sam/tests`` contains a
**drift test** (``test_entitlement_claim.py``) that decodes a shared set of claim
vectors through BOTH this vendored decoder and the backend codec and asserts they
produce identical results, so the two can never silently diverge. The single source
of truth for the *format* remains ``backend/src/auth/entitlement_claim_codec.py``;
this file only mirrors its decode behaviour.

Claim shape (mirrors T4)
------------------------
Normal (fits budget)::

    {"v": 1, "t": {"<administration>": ["<cap>", ...], ...}}

Over budget (overflow signal — never a truncated ``t``)::

    {"v": 1, "overflow": true, "t_keys": ["<administration>", ...]}

Unknown / missing ``v`` or a malformed value → a safe **fallback** result
(``fallback_required=True``, empty map) — a decoder that does not recognise the
format must never mis-parse or break auth.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

# The Pool A token claim name carrying the resolved per-tenant entitlement.
# Mirrors auth.entitlement_claim_codec.CLAIM_NAME (kept in sync by the drift test).
CLAIM_NAME: str = "custom:entitlements"

# The current claim format version. Mirrors auth.entitlement_claim_codec.CLAIM_VERSION.
CLAIM_VERSION: int = 1

__all__ = [
    "CLAIM_NAME",
    "CLAIM_VERSION",
    "DecodedEntitlements",
    "decode_entitlements",
]


@dataclass(frozen=True)
class DecodedEntitlements:
    """The result of decoding a ``custom:entitlements`` claim value.

    Exactly one interpretation holds; callers MUST branch on :attr:`is_overflow` /
    :attr:`fallback_required` before trusting :attr:`tenants`.

    Attributes:
        version: The ``v`` marker read from the claim (``None`` if absent).
        tenants: ``{tenant -> [capability, ...]}`` — populated ONLY for a
            recognised, non-overflow claim; empty for overflow / unknown-version
            claims (never a partial map).
        tenant_keys: The tenant list. For a normal claim this is
            ``sorted(tenants.keys())``; for an **overflow** claim it is the
            ``t_keys`` list (the tenants the reader must resolve server-side).
        is_overflow: ``True`` when the claim is the overflow signal — the token
            does NOT carry the per-user answer and the reader must consult the S3
            projection / a server endpoint for :attr:`tenant_keys`.
        fallback_required: ``True`` when the decoder could not interpret the claim
            as the current format (unknown/missing ``v``, malformed value). The
            reader must fall back to its own source of truth and MUST NOT treat the
            claim as an answer.
    """

    version: int | None
    tenants: dict[str, list[str]] = field(default_factory=dict)
    tenant_keys: list[str] = field(default_factory=list)
    is_overflow: bool = False
    fallback_required: bool = False

    def capabilities_for(self, tenant: str) -> list[str] | None:
        """Return the resolved capabilities for ``tenant`` from a usable claim.

        Returns the capability list when the claim is a recognised, non-overflow
        claim that contains ``tenant``. Returns ``None`` when the reader must not
        trust the token for that tenant — i.e. the claim requires fallback, is an
        overflow signal, or does not list the tenant. ``None`` therefore means "the
        token does not answer this; consult your fallback", never "no capabilities"
        (an empty *list* is the explicit "no capabilities" answer).
        """
        if self.fallback_required or self.is_overflow:
            return None
        return self.tenants.get(tenant)


def _unknown_fallback(version: int | None) -> DecodedEntitlements:
    """Build the safe-fallback result for an unrecognised/malformed claim."""
    return DecodedEntitlements(
        version=version,
        tenants={},
        tenant_keys=[],
        is_overflow=False,
        fallback_required=True,
    )


def decode_entitlements(claim_value: object) -> DecodedEntitlements:
    """Decode a ``custom:entitlements`` claim value into a usable result.

    Pure and total: it NEVER raises on a malformed/foreign/unknown-version claim —
    instead it returns a safe-fallback :class:`DecodedEntitlements`
    (``fallback_required=True``) so a decoder that does not recognise the format
    cannot break auth. The caller inspects :attr:`DecodedEntitlements.fallback_required`
    / :attr:`DecodedEntitlements.is_overflow` before trusting the map.

    Args:
        claim_value: The raw claim as read from the verified token. Accepts a JSON
            **string** (how Cognito stores it) or an already-parsed **dict**.
            Anything else, or invalid JSON, yields the safe fallback.

    Returns:
        A :class:`DecodedEntitlements` — see its attribute docs for the three
        interpretations (normal / overflow / fallback).
    """
    # Accept either the stored JSON string or an already-parsed dict.
    if isinstance(claim_value, str):
        try:
            parsed = json.loads(claim_value)
        except (ValueError, TypeError):
            return _unknown_fallback(version=None)
    elif isinstance(claim_value, Mapping):
        parsed = claim_value
    else:
        # None, int, list, etc. — nothing we can interpret. Fall back.
        return _unknown_fallback(version=None)

    if not isinstance(parsed, Mapping):
        # e.g. a JSON string that decoded to a list or scalar.
        return _unknown_fallback(version=None)

    version = parsed.get("v")

    # Unknown/missing version — fall back (never mis-parse a future format).
    if version != CLAIM_VERSION:
        return _unknown_fallback(version=version if isinstance(version, int) else None)

    # Recognised version — is it the overflow signal?
    if parsed.get("overflow") is True:
        raw_keys = parsed.get("t_keys", [])
        tenant_keys = (
            sorted(str(k) for k in raw_keys)
            if isinstance(raw_keys, Sequence) and not isinstance(raw_keys, str)
            else []
        )
        return DecodedEntitlements(
            version=version,
            tenants={},
            tenant_keys=tenant_keys,
            is_overflow=True,
            fallback_required=False,
        )

    # Recognised version, normal form — read the per-tenant map defensively.
    raw_map = parsed.get("t", {})
    if not isinstance(raw_map, Mapping):
        # Recognised version but the payload is malformed — fall back rather than
        # surface a garbage/partial map.
        return _unknown_fallback(version=version)

    tenants: dict[str, list[str]] = {}
    for tenant, caps in raw_map.items():
        if isinstance(caps, Sequence) and not isinstance(caps, str):
            tenants[str(tenant)] = [str(c) for c in caps]
        else:
            # Malformed capability list for a tenant — treat the whole claim as
            # untrustworthy rather than partially interpret it.
            return _unknown_fallback(version=version)

    return DecodedEntitlements(
        version=version,
        tenants=tenants,
        tenant_keys=sorted(tenants.keys()),
        is_overflow=False,
        fallback_required=False,
    )
