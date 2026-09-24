"""
S5 Task 5.1 — h-dcn's concrete Rung-3 hook implementations + their registration.

This module is the **tenant-scoped** home of h-dcn's bespoke member logic (design C5,
`generic-membership-design.md` §3 Rung 3). It is the ONLY place the ``tenant_id="h-dcn"``
literal and h-dcn's member rules appear — the generic core
(:mod:`sam.members.domain.membership_service` et al.) never branches on the tenant
(Property 5). h-dcn plugs into the core purely through the named extension points of
:class:`sam.members.domain.tenant_hooks.TenantHookRegistry`.

Rung discipline (R1.3) — where each h-dcn difference actually landed:

- ``derive_member_number`` — **REMOVED (s5k).** Member numbering is no longer auto-generated on
  any plane. ``member_number`` is a plain OPTIONAL string the caller/import supplies (h-dcn's real
  numbers are ``M#####``, imported). The former ``L-``/pad-6 counter formatter was deleted; a
  duplicate number is a data-quality concern, not a write-time conflict.
- ``validate_member`` — **REGISTERED (Rung 3).** h-dcn is a motor club: an ACTIVE h-dcn member
  must carry a motorcycle detail in the variable overlay (``overlay.motor``/``motor_type``).
  This is a club-specific field rule over the tenant's *variable overlay*, which the generic
  fixed-field validator (:func:`sam.members.domain.fixed_fields.validate_fixed_fields`) does
  not — and should not — know about, so it is a hook. Applicants / non-active members are not
  required to have registered a motorcycle yet, so the check only bites once the member is
  ACTIVE.
- ``on_transition`` — **LEFT ON THE SAFE DEFAULT (no-op).** h-dcn's activation/approval
  workflow is fully captured by the declarative lifecycle graph + guards (Rung 1-2,
  :data:`sam.members.domain.lifecycle_config.HDCN_LIFECYCLE_CONFIG`). h-dcn has no genuinely
  bespoke transition side-effect in the repo today, so registering one would be inventing a
  need — the ladder working as intended (a difference that stayed below Rung 3).
- ``resolve_visible_regions`` — **LEFT ON THE SAFE DEFAULT (identity).** Regional visibility
  is **fully declarative** via :func:`sam.members.domain.scope_access.resolve_scope_access`
  (task 3.1, Rung 1-2: admin/all → ``["*"]``, a scoped grant → its declared-value subset,
  ``required_for`` without a grant → deny). s5d clean break (R2.2/R8.1): the scope subset comes
  from the projected ``scopegrant#`` grant sourced from ``user_tenant_scope`` — NOT a ``Regio_*``
  role-name decode. h-dcn's ``determine_regional_access`` generalized cleanly, so NO Rung-3 hook
  is needed — a POSITIVE rung-distribution finding for the Go/No-Go.
- ``calculate_fee`` — **NOT REGISTERED.** h-dcn has no per-record fee computation; the named
  point exists for future clubs only.

Net h-dcn Rung-3 footprint: **1 of 5** named points registered (``validate_member``); the other
four stayed at Rung 1-2, are unused, or were removed (``derive_member_number``, s5k) — direct
evidence for the Go/No-Go rung distribution (R8.2).
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

from sam.members.domain.fixed_fields import MembershipStatus
from sam.members.domain.tenant_hooks import HookName, TenantHookRegistry

__all__ = [
    "HDCN_TENANT_ID",
    "hdcn_validate_member",
    "register_hdcn_hooks",
]

#: The tenant this package implements. Confined to this tenant-scoped package (Property 5).
HDCN_TENANT_ID = "h-dcn"

# s5k: `hdcn_derive_member_number` (an `L-`/pad-6 counter formatter) was DELETED. Member numbering
# is no longer auto-generated on any plane — `member_number` is a plain optional string the
# caller/import supplies (h-dcn's real numbers are `M#####`, imported). See spec s5k.


def _overlay(record: Mapping[str, Any]) -> Mapping[str, Any]:
    """The record's variable overlay sub-mapping (h-dcn club/Motor details), or empty."""
    overlay = record.get("overlay") if isinstance(record, Mapping) else None
    return overlay if isinstance(overlay, Mapping) else {}


def _current_status(record: Mapping[str, Any]) -> Optional[str]:
    """The record's ``membership.status`` as a raw string, or ``None``."""
    membership = record.get("membership") if isinstance(record, Mapping) else None
    if not isinstance(membership, Mapping):
        return None
    status = membership.get("status")
    return str(status) if status is not None else None


def hdcn_validate_member(
    tenant_id: str, record: Mapping[str, Any]
) -> Dict[str, str]:
    """Validate h-dcn's club-specific member rules (Rung-3 ``validate_member``).

    Layered ON TOP of the generic fixed-field validation (the core still runs
    :func:`sam.members.domain.fixed_fields.validate_fixed_fields` itself). h-dcn is a motor
    club, so an **ACTIVE** member must have a motorcycle recorded in the variable overlay
    (``overlay.motor`` or ``overlay.motor_type`` — either key satisfies it). Applicants /
    pending / other non-active members are NOT required to have registered a motorcycle yet,
    so the rule only applies at ``status == "active"``.

    Returns a mapping of ``dotted_key -> reason`` (empty when the record is valid), the same
    shape :func:`sam.members.domain.fixed_fields.validate_fixed_fields` uses, so the write
    route (task 5.2) can merge these errors with the fixed-field errors and surface them all
    at once.
    """
    errors: Dict[str, str] = {}
    if _current_status(record) == MembershipStatus.ACTIVE.value:
        overlay = _overlay(record)
        motor = overlay.get("motor") or overlay.get("motor_type")
        if not (isinstance(motor, str) and motor.strip()):
            errors["overlay.motor"] = (
                "an active h-dcn member must have a motorcycle recorded"
            )
    return errors


def register_hdcn_hooks(registry: TenantHookRegistry) -> TenantHookRegistry:
    """Bind h-dcn's Rung-3 hook implementations into ``registry`` for ``tenant_id="h-dcn"``.

    The single wiring point (called once at module composition). It registers ONLY the hook
    h-dcn genuinely needs — ``validate_member`` — and deliberately leaves ``on_transition``
    (safe no-op), ``resolve_visible_regions`` (declarative at Rung 1-2), and ``calculate_fee``
    (unused) on their safe generic defaults. (s5k removed ``derive_member_number`` — member
    numbering is no longer generated.) Returns the same ``registry`` for chaining.
    """
    registry.register(HookName.VALIDATE_MEMBER, HDCN_TENANT_ID, hdcn_validate_member)
    return registry
