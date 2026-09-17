"""
S4 D3 — the entitlement claim codec (shape, size budget, versioning).

This module encodes/decodes the compact, versioned token claim that carries a
user's resolved per-tenant entitlement (the output of the T1 resolver
:func:`auth.entitlement_resolver.resolve_entitlement`). It is imported by both:

- the Pre-Token-Generation Lambda (S4 T11), which *encodes* the resolver output
  and stamps it as ``custom:entitlements`` into the Pool A token at issuance, and
- the readers on both planes (S4 T14 module plane / T15 Flask plane), which
  *decode* the claim from the **verified** token to authorize without a
  request-time MySQL query.

It is deliberately **pure** (no I/O, no clock, no env) so the T10 property test
can drive it and both carriers reuse it. Correctness over completeness is the
governing rule (R3.3): a reader must never mistake an overflow claim for the
whole entitlement.

Claim shape (D3, R3.1)
----------------------
Normal (fits budget)::

    {
        "v": 1,                       # format version — readers check this first
        "t": {                        # per-tenant resolved capabilities
            "<administration>": ["<cap>", ...],
            ...
        }
    }

Over budget (R3.3) — a compact **overflow signal**, never a truncated ``t``::

    {
        "v": 1,
        "overflow": true,             # the reader MUST consult the server / S3
        "t_keys": ["<administration>", ...]   # which tenants the user belongs to
    }

The overflow form keeps the tenant *list* (cheap, bounded) but drops the
capability *lists* (the expensive part). A reader seeing ``overflow`` knows the
token does not carry the per-user answer and must fall back to the S3 DynamoDB
projection / a server endpoint for those tenants. It is NOT a partial answer.

Encoding (R3.2 — compactness)
-----------------------------
JSON with the most compact separators (``","`` / ``":"``), keys already short
(``v`` / ``t`` / ``overflow`` / ``t_keys``) and capability tokens already short
(``module:action`` style, e.g. ``finance_read``). Cognito stores the claim as a
string, so we emit a compact JSON string and measure its **UTF-8 byte length**.

Size budget (R3.2) — CHOSEN VALUE + rationale
---------------------------------------------
:data:`DEFAULT_BUDGET_BYTES` = **3072 bytes (3 KiB)** for the encoded claim value.

Rationale: Cognito's ID/access token has a practical size ceiling (the total
encoded JWT must stay well under browser/gateway header limits — Cognito rejects
oversized tokens, and API Gateway caps request headers around 8–10 KB total).
The token already carries the standard OIDC claims plus the S3 contract claims
(``cognito:groups``, ``custom:tenants``) and signature. Reserving **3 KiB** for
``custom:entitlements`` leaves generous headroom for the rest of the token while
comfortably fitting a realistic multi-tenant admin: e.g. ~10 tenants × ~8
capabilities of ~14 chars ≈ 1.1 KB encoded. A user large enough to exceed 3 KiB
is an outlier best served by the server-side / S3 path (the overflow signal),
not by inflating every token. The budget is a **named constant** so it can be
tuned in one place as the token contract evolves.

Versioning (R3.1)
-----------------
The ``v`` marker lets readers evolve the format. :func:`decode_entitlements` on
an unknown or missing ``v`` returns a well-defined **safe fallback** (an
``unknown``-form :class:`DecodedEntitlements` with no capabilities and
``fallback_required=True``) rather than raising or mis-parsing — a decoder that
does not recognise the format must never break auth (it falls back to
``role_cache.py`` on the Flask plane / deny-or-consult-S3 on the module plane).
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

# The Pool A token claim name carrying the resolved per-tenant entitlement.
CLAIM_NAME: str = "custom:entitlements"

# The current claim format version (R3.1). Bump when the shape changes; readers
# check this and fall back on an unrecognised value.
CLAIM_VERSION: int = 1

# The bounded size budget (in UTF-8 bytes) for the ENCODED claim value (R3.2).
# See the module docstring for the rationale behind 3 KiB.
DEFAULT_BUDGET_BYTES: int = 3072

# Compact JSON separators (no whitespace) — used everywhere we encode.
_COMPACT_SEPARATORS = (",", ":")


@dataclass(frozen=True)
class DecodedEntitlements:
    """The result of decoding a ``custom:entitlements`` claim value.

    Exactly one of the interpretations below holds; callers should branch on
    :attr:`is_overflow` / :attr:`fallback_required` before trusting
    :attr:`tenants`.

    Attributes:
        version: The ``v`` marker read from the claim (``None`` if absent).
        tenants: ``{tenant -> [capability, ...]}`` — the per-tenant resolved
            capability map, populated ONLY for a recognised, non-overflow claim.
            Empty for overflow or unknown-version claims (never a partial map).
        tenant_keys: The tenant list. For a normal claim this is
            ``tenants.keys()``; for an **overflow** claim it is the ``t_keys``
            list (the tenants the reader must resolve server-side).
        is_overflow: ``True`` when the claim is the overflow signal — the token
            does NOT carry the per-user answer and the reader must consult the
            S3 projection / a server endpoint for :attr:`tenant_keys` (R3.3).
        fallback_required: ``True`` when the decoder could not interpret the
            claim as the current format (unknown/missing ``v``, malformed
            value). The reader must fall back to its own source of truth
            (``role_cache.py`` / deny) and MUST NOT treat the claim as an
            answer (R3.1).
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
        overflow signal, or does not list the tenant. ``None`` therefore means
        "the token does not answer this; consult your fallback", never "no
        capabilities" (an empty *list* is the explicit "no capabilities" answer).
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


def _encoded_byte_length(value: str) -> int:
    """UTF-8 byte length of an encoded claim string (the budgeted quantity)."""
    return len(value.encode("utf-8"))


def _normalise_map(
    entitlement_map: Mapping[str, Sequence[str]],
) -> dict[str, list[str]]:
    """Return a deterministic ``{tenant -> sorted[unique caps]}`` copy.

    Tolerates duplicate capabilities and unsorted input so encoding is stable
    regardless of how the resolver output was constructed. Does not invent or
    drop tenants — an empty capability list is preserved (the tenant is present
    but grants nothing), matching the resolver's contract.
    """
    normalised: dict[str, list[str]] = {}
    for tenant, caps in entitlement_map.items():
        unique = sorted({c for c in (caps or []) if c})
        normalised[tenant] = unique
    return normalised


def encode_entitlements(
    entitlement_map: Mapping[str, Sequence[str]],
    *,
    budget: int = DEFAULT_BUDGET_BYTES,
) -> str:
    """Encode a resolved per-tenant entitlement map into the claim value.

    Consumes the T1 resolver's output shape
    (``{tenant -> sorted list[capabilities]}`` from
    :func:`auth.entitlement_resolver.resolve_entitlement`) and produces the
    compact, versioned string the Lambda stamps as ``custom:entitlements``.

    Pure and deterministic (no I/O): the same input always yields the same
    string, so it is PBT-friendly (T10) and safe to reuse across carriers.

    Args:
        entitlement_map: ``{tenant -> [capability, ...]}``. Duplicate/unsorted
            capabilities are tolerated (normalised to sorted-unique) so the
            encoding is stable.
        budget: The maximum UTF-8 byte length of the encoded value. Defaults to
            :data:`DEFAULT_BUDGET_BYTES`. If the normal encoding would exceed
            this, the function emits the **overflow signal** instead of
            truncating (R3.3).

    Returns:
        A compact JSON string. Either the normal form
        ``{"v":1,"t":{...}}`` (when it fits ``budget``) or the overflow form
        ``{"v":1,"overflow":true,"t_keys":[...]}`` (when it does not). The
        overflow form is itself compact and its ``t_keys`` list is the bounded
        tenant list, so it fits comfortably within any sane budget.

    Notes:
        - **Never silently truncates** (R3.3): a reader can always distinguish a
          complete claim (``t`` present, no ``overflow``) from an overflow
          signal (``overflow`` present, no ``t``).
        - The version marker is always the current :data:`CLAIM_VERSION` (R3.1).
    """
    normalised = _normalise_map(entitlement_map)

    normal_claim = {"v": CLAIM_VERSION, "t": normalised}
    encoded = json.dumps(
        normal_claim, separators=_COMPACT_SEPARATORS, ensure_ascii=False, sort_keys=True
    )

    if _encoded_byte_length(encoded) <= budget:
        return encoded

    # Over budget — emit the overflow signal (never a truncated capability map).
    overflow_claim = {
        "v": CLAIM_VERSION,
        "overflow": True,
        "t_keys": sorted(normalised.keys()),
    }
    return json.dumps(
        overflow_claim,
        separators=_COMPACT_SEPARATORS,
        ensure_ascii=False,
        sort_keys=True,
    )


def decode_entitlements(claim_value: object) -> DecodedEntitlements:
    """Decode a ``custom:entitlements`` claim value into a usable result.

    Pure and total: it NEVER raises on a malformed/foreign/unknown-version claim
    — instead it returns a safe-fallback :class:`DecodedEntitlements`
    (``fallback_required=True``) so a decoder that does not recognise the format
    cannot break auth (R3.1). The caller inspects
    :attr:`DecodedEntitlements.fallback_required` /
    :attr:`DecodedEntitlements.is_overflow` before trusting the map.

    Args:
        claim_value: The raw claim as read from the verified token. Accepts a
            JSON **string** (how Cognito stores it) or an already-parsed
            **dict** (convenience for tests/readers). Anything else, or invalid
            JSON, yields the safe fallback.

    Returns:
        A :class:`DecodedEntitlements`:
        - **recognised normal claim** (``v == CLAIM_VERSION``, ``t`` present):
          ``tenants`` populated, ``tenant_keys`` = its keys,
          ``is_overflow=False``, ``fallback_required=False``.
        - **recognised overflow claim** (``v == CLAIM_VERSION``,
          ``overflow == true``): ``tenants`` empty, ``tenant_keys`` = ``t_keys``,
          ``is_overflow=True`` — the reader must consult the server / S3 (R3.3).
        - **unknown/missing ``v`` or malformed value**: the safe fallback
          (``fallback_required=True``, empty map) — the reader falls back to its
          own source of truth (R3.1).
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
        # Recognised version but the payload is malformed — fall back rather
        # than surface a garbage/partial map.
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
