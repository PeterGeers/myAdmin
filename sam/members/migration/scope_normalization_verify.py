"""
S5d Task 2.4 — the **normalization verification** (R9.5, R9.3, R9.6; design → Testing
Strategy "Normalization (R9.5)", Error Handling "Un-normalizable member value").

Exact-match enforcement (R3.5) is only CORRECT if a member's scope-field value and a
granted value are drawn from ONE canonical vocabulary. Dirty/variant member data (a
trailing space, ``"Noord Holland"`` vs ``"Noord-Holland"``) makes an exact filter
**silently return nothing**. This module is the first-class, testable check that makes
such a normalization gap VISIBLE instead of manifesting as an unexplained empty result
(R9.5 / R9.3) — the class of bug that was hit and fixed in s5c.

Two pieces, both PURE (no I/O, no boto3, no live system) so they unit-test without AWS —
the SAM-plane CLI runner (``scripts/aws/verify-member-scope-normalization.py``) supplies
the DynamoDB read, exactly as ``backfill-hdcn-members.py`` drives the pure
``map_hdcn_row`` transform:

1. :func:`verify_scope_normalization` — the R9.5 FIRST clause. For a tenant's member set
   and a scope dimension, it collects EVERY distinct member scope-field value, canonicalizes
   each with the shared :func:`~sam.members.domain.scope_canon.scope_canon`, and asserts each
   canonicalizes to a member of the dimension's canonical value set (itself canonicalized).
   Any value with NO canonical match is REPORTED (an "offender") rather than silently kept as
   a non-matching variant or silently dropped (R9.3). The returned
   :class:`ScopeNormalizationReport` carries the offenders + the full distinct-value census,
   so the runner can print a human report and exit non-zero when the tenant is un-normalized.

2. :func:`members_matching_grant` — the R9.5 SECOND clause helper. Given a grant's values,
   it returns exactly the members whose scope-field value matches (canonical equality via
   ``scope_canon`` — the SAME comparison enforcement uses, R9.6), so a test can assert an
   EXACT grant (e.g. ``region=["Oost"]``) returns the expected NON-EMPTY subset.

Both read the member's SCALAR scope-field value via the shared field→bucket accessor
(:func:`~sam.members.domain.field_resolver._member_value`), resolving the dimension's
``field`` (``members.scope_dimensions[dim].field``, default = dimension ``key`` — h-dcn's
``region`` dimension binds to the tenant-added ``overlay.region`` field) nested-bucket-first
with a flat fallback — the bucket is NEVER hardcoded. Canonicalization is NEVER
reimplemented here: the one shared ``scope_canon`` is used, so this check agrees byte-for-byte
with enforcement and normalization-at-write (Property 4).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Mapping, Sequence

from sam.members.domain.field_resolver import _member_value
from sam.members.domain.scope_canon import scope_canon
from sam.members.domain.scope_dimensions import ScopeDimension

__all__ = [
    "ScopeNormalizationReport",
    "verify_scope_normalization",
    "members_matching_grant",
    "member_scope_value",
]


def member_scope_value(member: Mapping[str, Any], dimension: ScopeDimension) -> Any:
    """Return a member's RAW scalar value for ``dimension``'s bound field, or ``None``.

    The dimension binds to a normal member field (``dimension.field``, defaulting to the
    dimension ``key`` — h-dcn's ``region`` binds to ``overlay.region``). The value is read via
    the shared field→bucket accessor (nested-bucket-first with a flat top-level fallback), so
    the storage bucket is resolved from config, never hardcoded (design ODx1). A member is
    single-valued per scope field (R3.2), so this is a scalar. Returns ``None`` when the field
    is absent.
    """
    if not isinstance(member, Mapping):
        return None
    # `field` defaults to `key` on ScopeDimension.__post_init__, so this is always a real key.
    return _member_value(member, dimension.field or dimension.key)


@dataclass(frozen=True)
class ScopeNormalizationReport:
    """The result of the R9.5 normalization check for one tenant + dimension.

    - ``ok`` — ``True`` when every distinct member scope-field value canonicalizes to a member
      of the dimension's canonical value set (no un-normalized values, R9.5).
    - ``offenders`` — the distinct RAW member values that did NOT map to any canonical value
      (R9.3 — surfaced, never silently kept/dropped). Order-stable (first-seen).
    - ``distinct_values`` — every distinct RAW scope-field value present across the members
      (a census; blank/absent values are excluded — they are an ABSENT grant, not a variant).
    - ``canonical_values`` — the dimension's canonical value set (as authored), for the report.
    - ``members_scanned`` — how many member records were examined.
    """

    tenant_id: str
    dimension_key: str
    field_key: str
    ok: bool
    offenders: Sequence[str] = field(default_factory=tuple)
    distinct_values: Sequence[str] = field(default_factory=tuple)
    canonical_values: Sequence[str] = field(default_factory=tuple)
    members_scanned: int = 0


def verify_scope_normalization(
    tenant_id: str,
    members: Sequence[Mapping[str, Any]],
    dimension: ScopeDimension,
) -> ScopeNormalizationReport:
    """Assert every distinct member scope-field value is in ``dimension``'s canonical set (R9.5).

    The R9.5 FIRST clause. Collects the DISTINCT raw values the members carry for the
    dimension's bound field, canonicalizes each with the shared ``scope_canon``, and checks it
    against the dimension's canonical value set (each canonical value likewise reduced by
    ``scope_canon`` — so the comparison is canonical-vs-canonical, R9.6). A raw value whose
    canonical form is NOT in that set is an offender (R9.3): the member would silently match
    nothing under exact enforcement, so it is reported rather than hidden.

    Blank / absent field values are NOT offenders — an absent scope value is a deny-by-default
    ABSENCE, not an un-normalizable variant; it is simply excluded from the census.

    Returns a :class:`ScopeNormalizationReport` (``ok`` is ``True`` iff there are no
    offenders). Pure: no I/O — the caller supplies the already-read member records.
    """
    field_key = dimension.field or dimension.key

    # The dimension's canonical vocabulary, reduced to canonical space once (R9.6).
    canonical_by_canon = {scope_canon(v): v for v in dimension.values}

    distinct: List[str] = []
    seen_raw: set[str] = set()
    offenders: List[str] = []
    seen_offender: set[str] = set()

    for member in members:
        raw = member_scope_value(member, dimension)
        if raw is None:
            continue
        raw_str = raw if isinstance(raw, str) else str(raw)
        canonical = scope_canon(raw_str)
        if not canonical:
            # Blank after canonicalization → an absent value, not a variant. Skip the census.
            continue
        if raw_str not in seen_raw:
            seen_raw.add(raw_str)
            distinct.append(raw_str)
        # A distinct value with no canonical counterpart is an un-normalized value (R9.3).
        if canonical not in canonical_by_canon and raw_str not in seen_offender:
            seen_offender.add(raw_str)
            offenders.append(raw_str)

    return ScopeNormalizationReport(
        tenant_id=tenant_id,
        dimension_key=dimension.key,
        field_key=field_key,
        ok=not offenders,
        offenders=tuple(offenders),
        distinct_values=tuple(distinct),
        canonical_values=tuple(dimension.values),
        members_scanned=len(members),
    )


def members_matching_grant(
    members: Sequence[Mapping[str, Any]],
    grant_values: Sequence[str],
    dimension: ScopeDimension,
) -> List[Mapping[str, Any]]:
    """Return the members whose scope-field value matches ``grant_values`` (R9.5 second clause).

    The exact-grant subset: a member is included when its (canonicalized) scope-field value is
    one of the (canonicalized) granted values — canonical equality via the SAME ``scope_canon``
    enforcement uses (R9.6), so this mirrors what ``_in_scope`` would admit for a scoped
    caller. Used by the R9.5 second-clause test: an exact grant (e.g. ``["Oost"]``) returns
    exactly the members carrying that value — a NON-EMPTY subset over a normalized member set.

    (This is intentionally NOT the wildcard/deny path — it exercises a concrete value grant,
    which is what R9.5 asks the verification to demonstrate.)
    """
    granted = {scope_canon(v) for v in grant_values}
    granted.discard("")  # a blank grant value can never match a real member value
    matched: List[Mapping[str, Any]] = []
    for member in members:
        raw = member_scope_value(member, dimension)
        if raw is None:
            continue
        canonical = scope_canon(raw if isinstance(raw, str) else str(raw))
        if canonical and canonical in granted:
            matched.append(member)
    return matched
