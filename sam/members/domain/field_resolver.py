"""
S5 Task 1.2 — the per-tenant **variable field overlay** + ``FieldResolver`` (design C3, R2.2/R2.3).

The member data model is two layers (see ``members-wireframe.md`` / design C3):

    fixed base registry (platform-owned, identical every tenant)   ── fixed_fields.py
        ⊕
    per-tenant VARIABLE overlay ("club details", resolved by tenant_id)  ── this module

``FieldResolver.resolve(tenant_id) -> FieldConfig`` merges the two and produces the single
**resolved field config** the presentation-only React frontend renders (R2.3). It reuses the
proven myAdmin ``FieldConfigMixin`` / ``tenant_template_config`` pattern — *per-tenant field
config resolved by tenant, layered over a platform base* — generalised for the SAM plane:

- **Where the overlay comes from is injected, not hard-wired.** The resolver depends on a
  :class:`TenantOverlayProvider` (a ``Protocol``), exactly as ``FieldConfigMixin`` depends on
  a ``parameter_service``. In the SAM plane the concrete provider is DynamoDB-backed config
  (the ``tenant_template_config`` analogue), wired in a later step; here the domain layer
  stays **storage-agnostic** (no boto3) and **tenant-agnostic** (no ``if tenant == ...``).
- **Adding a tenant needs NO schema change (R2.2).** A new tenant is *new overlay data* handed
  to the provider — never a code or table-shape change. The fixed base is untouched; the
  overlay is applied *over* it, keyed by ``tenant_id``.

Overlay authority (mirrors ``FieldConfigMixin``, kept safe by design):
- an overlay may **add** variable fields (club details, e.g. h-dcn Motor), which land under the
  member record's ``overlay`` attribute, and
- **override presentation-only** aspects of a *fixed* field (its label, whether it is visible,
  its ordering, and — for an *optional* fixed field — whether it is required in this tenant),
- but it may **NEVER** weaken a platform invariant: it cannot drop/rename a fixed field, make a
  platform-``required`` fixed field optional, change a fixed field's ``type``, collide with a
  fixed field's key, or touch the closed ``membership.status`` enum. Those are the base
  registry's ``ALWAYS_REQUIRED``-style guarantees. Violations raise :class:`OverlayError`
  (fail fast — a config bug, not user input).

What this module is NOT:
- It does not persist anything (that is the repository, task 1.4 / Step 4).
- It does not validate a *member record* — it resolves the *field config*. Member validation
  against the fixed base is ``validate_fixed_fields`` (task 1.1); the ``membership_type``
  catalog reference check is the MembershipService's (C8, task 5.3).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping, Optional, Protocol, Sequence, runtime_checkable

from .fixed_fields import (
    FIXED_FIELDS,
    FieldGroup,
    FieldType,
    FixedField,
)

__all__ = [
    "OVERLAY_GROUP",
    "FieldOrigin",
    "ResolvedField",
    "FieldConfig",
    "OverlayField",
    "FixedFieldOverride",
    "TenantOverlay",
    "TenantOverlayProvider",
    "StaticOverlayProvider",
    "OverlayError",
    "FieldResolver",
]

#: The group name variable overlay fields live under on the member record (design data model:
#: ``member["overlay"][...]``). Distinct from the fixed :class:`FieldGroup` values so a variable
#: field can never masquerade as a first-class fixed attribute.
OVERLAY_GROUP = "overlay"


# ── The resolved shapes the frontend renders ─────────────────────────────────────────


class FieldOrigin(str, Enum):
    """Whether a resolved field came from the platform base or a tenant overlay."""

    FIXED = "fixed"        # from the platform base registry (fixed_fields.py)
    VARIABLE = "variable"  # from the per-tenant overlay ("club details")


@dataclass(frozen=True)
class ResolvedField:
    """One field in the resolved config — a fixed field (possibly overlaid) or a variable one.

    This is the presentation-facing shape: it carries everything the frontend needs to render
    the field and nothing it needs to *enforce* (the authoritative rules stay server-side).
    ``group`` is a string so it spans both the fixed groups (``personal`` / ``membership``) and
    the variable :data:`OVERLAY_GROUP` (``overlay``).
    """

    key: str                       # canonical key within the group (e.g. "name", "motor_type")
    group: str
    type: FieldType
    required: bool
    origin: FieldOrigin
    label: Mapping[str, str] = field(default_factory=dict)   # i18n {"nl": ..., "en": ...}
    choices: Optional[Sequence[str]] = None                  # for FieldType.ENUM
    visible: bool = True
    order: int = 0

    def dotted_key(self) -> str:
        """Fully-qualified path of the field, e.g. ``personal.name`` / ``overlay.motor_type``."""
        return f"{self.group}.{self.key}"


@dataclass(frozen=True)
class FieldConfig:
    """The resolved field config for one tenant: fixed base ⊕ per-tenant overlay (design C3).

    ``fields`` is the flat, deterministically-ordered list (by group, then ``order``, then
    key) the frontend renders. :meth:`by_group` returns the same fields bucketed by their
    first-class member attribute (``personal`` / ``membership`` / ``overlay``), the shape the
    resolved config is served in.
    """

    tenant_id: str
    fields: tuple[ResolvedField, ...]

    def by_group(self) -> Mapping[str, tuple[ResolvedField, ...]]:
        buckets: dict[str, list[ResolvedField]] = {}
        for f in self.fields:
            buckets.setdefault(f.group, []).append(f)
        return {g: tuple(fs) for g, fs in buckets.items()}

    def field(self, dotted_key: str) -> Optional[ResolvedField]:
        """Return the resolved field for a canonical dotted key, or ``None``."""
        for f in self.fields:
            if f.dotted_key() == dotted_key:
                return f
        return None

    def variable_fields(self) -> tuple[ResolvedField, ...]:
        """Only the tenant's variable (overlay) fields."""
        return tuple(f for f in self.fields if f.origin is FieldOrigin.VARIABLE)

    def visible_fields(self) -> tuple[ResolvedField, ...]:
        """The fields the frontend should show (an overlay may hide a fixed field for a tenant)."""
        return tuple(f for f in self.fields if f.visible)


# ── The overlay data model (what a tenant supplies — new tenant = new data, R2.2) ─────


@dataclass(frozen=True)
class OverlayField:
    """A tenant-defined **variable** field ("club detail", e.g. h-dcn Motor type).

    Purely additive data — declaring one for a tenant needs no schema change (R2.2). It lands
    under the record's ``overlay`` attribute; the resolver assigns it :data:`FieldOrigin.VARIABLE`.
    """

    key: str
    type: FieldType = FieldType.STRING
    required: bool = False
    label: Mapping[str, str] = field(default_factory=dict)
    choices: Optional[Sequence[str]] = None
    visible: bool = True
    order: int = 0


@dataclass(frozen=True)
class FixedFieldOverride:
    """A tenant's **presentation-only** override of a *fixed* field.

    A tenant may relabel a fixed field, reorder it, hide it, or (for an *optional* fixed field)
    mark it required in its context. It may **not** weaken a platform invariant — the resolver
    rejects any attempt to (see :class:`OverlayError`). A ``None`` attribute means "leave the
    base value as-is".
    """

    label: Optional[Mapping[str, str]] = None
    visible: Optional[bool] = None
    required: Optional[bool] = None   # may only tighten (optional→required), never loosen
    order: Optional[int] = None


@dataclass(frozen=True)
class TenantOverlay:
    """The full per-tenant overlay: added variable fields + presentation overrides of fixed ones.

    This is the *data* a tenant supplies (h-dcn, then any future club) — the whole point of R2.2
    is that this is all it takes to onboard a tenant: no code, no schema. An empty overlay (the
    default) resolves to exactly the fixed base.
    """

    #: New variable fields, keyed by their canonical key (lands under the ``overlay`` group).
    fields: Mapping[str, OverlayField] = field(default_factory=dict)
    #: Presentation overrides of fixed fields, keyed by canonical dotted key (``group.field``).
    overrides: Mapping[str, FixedFieldOverride] = field(default_factory=dict)


class OverlayError(Exception):
    """Raised when a tenant overlay tries to violate a platform invariant (a config bug).

    Carries ``reasons`` (dotted-key → why) so a misconfiguration surfaces all problems at once.
    """

    def __init__(self, reasons: Mapping[str, str]):
        self.reasons = dict(reasons)
        detail = "; ".join(f"{k}: {v}" for k, v in self.reasons.items())
        super().__init__(f"invalid tenant field overlay: {detail}")


# ── The overlay provider seam (mirrors FieldConfigMixin's parameter_service) ──────────


@runtime_checkable
class TenantOverlayProvider(Protocol):
    """Supplies a tenant's :class:`TenantOverlay`, resolved by ``tenant_id``.

    The resolver depends on this shape, not on where the config lives — exactly as
    ``FieldConfigMixin`` depends on a ``parameter_service``. The SAM-plane concrete provider is
    DynamoDB-backed tenant config (the ``tenant_template_config`` analogue), injected in a later
    step; the domain layer never imports it. A tenant with no configured overlay MUST yield an
    **empty** overlay (→ resolves to the fixed base), never an error.
    """

    def get_overlay(self, tenant_id: str) -> TenantOverlay:
        ...


class StaticOverlayProvider:
    """An in-memory :class:`TenantOverlayProvider` backed by a ``{tenant_id: TenantOverlay}`` map.

    The storage-agnostic default: used by tests and any caller that already holds the overlays
    (e.g. seeded h-dcn config), and the reference against which the DynamoDB-backed provider is
    later swapped in. Unknown tenants resolve to an **empty** overlay (fixed base only) — the
    fail-safe default (adding a tenant is additive; a missing overlay is not an error).
    """

    def __init__(self, overlays: Optional[Mapping[str, TenantOverlay]] = None):
        self._overlays = dict(overlays or {})

    def get_overlay(self, tenant_id: str) -> TenantOverlay:
        return self._overlays.get(tenant_id, TenantOverlay())


# ── The resolver ──────────────────────────────────────────────────────────────────────

# A dotted-key → fixed-field lookup, used to validate overrides (single source of truth).
_FIXED_BY_DOTTED: Mapping[str, FixedField] = {f.dotted_key(): f for f in FIXED_FIELDS}
_FIXED_KEYS: frozenset[str] = frozenset(f.key for f in FIXED_FIELDS)


class FieldResolver:
    """Resolves ``tenant_id -> FieldConfig`` = fixed base registry ⊕ per-tenant overlay (C3).

    Storage-agnostic and tenant-agnostic: it is constructed with a
    :class:`TenantOverlayProvider` and merges whatever overlay that provider returns over the
    platform fixed base. The generic core has no tenant conditionals — h-dcn is just the first
    ``tenant_id`` whose overlay the provider happens to carry (Property 5).
    """

    def __init__(self, overlay_provider: TenantOverlayProvider):
        self._provider = overlay_provider

    def resolve(self, tenant_id: str) -> FieldConfig:
        """Return the resolved field config for ``tenant_id`` (fixed base ⊕ overlay).

        Steps: read the tenant's overlay from the provider → validate it against the platform
        invariants (raise :class:`OverlayError` on violation) → apply presentation overrides to
        the fixed fields → append the tenant's variable fields → sort deterministically (by
        group, then order, then key) so the resolved config is stable for the frontend.
        """
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise ValueError("tenant_id must be a non-empty string")

        overlay = self._provider.get_overlay(tenant_id)
        self._reject_invalid_overlay(overlay)

        resolved: list[ResolvedField] = [
            self._apply_override(fixed, overlay) for fixed in FIXED_FIELDS
        ]
        resolved.extend(
            self._as_variable_field(name, of) for name, of in overlay.fields.items()
        )

        resolved.sort(key=lambda f: (f.group, f.order, f.key))
        return FieldConfig(tenant_id=tenant_id, fields=tuple(resolved))

    # ── internals ─────────────────────────────────────────────────────────────────────

    @staticmethod
    def _apply_override(fixed: FixedField, overlay: TenantOverlay) -> ResolvedField:
        """Project a fixed field into a resolved field, applying any presentation override."""
        override = overlay.overrides.get(fixed.dotted_key())
        label: Mapping[str, str] = fixed.label
        required = fixed.required
        visible = True
        order = fixed.order
        if override is not None:
            if override.label is not None:
                label = override.label
            if override.required is not None:
                required = override.required
            if override.visible is not None:
                visible = override.visible
            if override.order is not None:
                order = override.order
        return ResolvedField(
            key=fixed.key,
            group=fixed.group.value,
            type=fixed.type,
            required=required,
            origin=FieldOrigin.FIXED,
            label=label,
            choices=fixed.choices,
            visible=visible,
            order=order,
        )

    @staticmethod
    def _as_variable_field(name: str, of: OverlayField) -> ResolvedField:
        """Project a tenant-defined variable field into a resolved field under the overlay group."""
        return ResolvedField(
            key=of.key or name,
            group=OVERLAY_GROUP,
            type=of.type,
            required=of.required,
            origin=FieldOrigin.VARIABLE,
            label=of.label,
            choices=of.choices,
            visible=of.visible,
            order=of.order,
        )

    @staticmethod
    def _reject_invalid_overlay(overlay: TenantOverlay) -> None:
        """Fail fast if the overlay tries to weaken a platform invariant (a config bug)."""
        reasons: dict[str, str] = {}

        for dotted, override in overlay.overrides.items():
            fixed = _FIXED_BY_DOTTED.get(dotted)
            if fixed is None:
                reasons[dotted] = (
                    "overrides an unknown fixed field (only fixed fields may be overridden)"
                )
                continue
            # An overlay may tighten (optional → required) but never loosen a platform-required field.
            if override.required is False and fixed.required:
                reasons[dotted] = "cannot make a platform-required fixed field optional"

        for name, of in overlay.fields.items():
            key = of.key or name
            dotted = f"{OVERLAY_GROUP}.{key}"
            # A variable field may not collide with the canonical key of a fixed field.
            if key in _FIXED_KEYS:
                reasons[dotted] = "variable field key collides with a fixed field key"
            elif of.type is FieldType.ENUM and not of.choices:
                reasons[dotted] = "an enum variable field must declare choices"

        if reasons:
            raise OverlayError(reasons)
