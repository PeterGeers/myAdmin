"""Resolved-field + overlay DATA MODEL for the member field resolver (design C3).

This is the pure, storage-agnostic data layer that :mod:`field_resolver` resolves into and
over: the resolved shapes the frontend renders (:class:`ResolvedField`, :class:`FieldConfig`),
the per-tenant overlay a tenant supplies (:class:`OverlayField`, :class:`FieldScope`,
:class:`FixedFieldOverride`, :class:`FunctionalGroup`, :class:`TenantOverlay`), the
fail-fast :class:`OverlayError`, and the provider seam (:class:`TenantOverlayProvider` +
:class:`StaticOverlayProvider`).

It carries NO resolution logic — ``FieldResolver`` (and the ``show_when`` evaluation and the
reserved-key lookups) stay in :mod:`field_resolver`, which re-exports every name here so the
public import surface ``sam.members.domain.field_resolver`` is unchanged. These definitions
depend only on the fixed/calculated field registries, so they never form an import cycle with
the resolver.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol, runtime_checkable

from .fixed_fields import (
    EnumOption,
    FieldType,
    MemberNumberFormat,
)

__all__ = [
    "OVERLAY_GROUP",
    "FieldConfig",
    "FieldOrigin",
    "FieldProvenance",
    "FieldScope",
    "FixedFieldOverride",
    "FunctionalGroup",
    "OverlayError",
    "OverlayField",
    "ResolvedField",
    "StaticOverlayProvider",
    "TenantOverlay",
    "TenantOverlayProvider",
]

#: The group name variable overlay fields live under on the member record (design data model:
#: ``member["overlay"][...]``). Distinct from the fixed :class:`FieldGroup` values so a variable
#: field can never masquerade as a first-class fixed attribute.
OVERLAY_GROUP = "overlay"


# ── The resolved shapes the frontend renders ─────────────────────────────────────────


class FieldOrigin(str, Enum):
    """Where a resolved field came from: the platform base, a tenant overlay, or a derivation."""

    FIXED = "fixed"            # from the platform base registry (fixed_fields.py)
    VARIABLE = "variable"      # from the per-tenant overlay ("club details")
    CALCULATED = "calculated"  # derived read-only field, NEVER stored (calculated_fields.py, R4.4)


class FieldProvenance(str, Enum):
    """The single-list PROVENANCE marker (Phase 3 step 8, R1.2) — derived at resolve time.

    Phase 3 collapses the former two-section fixed/overlay presentation into ONE unified field
    list, where each field shows a badge indicating its origin. That badge is this marker,
    DERIVED from how the field resolved — it is NOT a new stored shape (R1.4) and introduces no
    new field position (R1.3): the resolved field SET and the ``(group, order, key)`` order are
    unchanged by its addition (Property 1, R1.6).

    It is orthogonal to :class:`FieldOrigin` (the STORAGE/source layer, kept verbatim so no
    existing consumer breaks). Provenance refines origin with whether a base field carries a
    tenant presentation override:

    - :attr:`BASE` — a platform base field (fixed OR calculated) with NO tenant override applied.
    - :attr:`BASE_OVERRIDDEN` — a platform base field re-presented by a tenant ``fixed_overrides``
      entry (relabelled / reordered / hidden / regrouped / tightened). Still immovable: Phase 3
      keeps every current fixed field in the resolved set (it does NOT adopt
      "only ``member_id`` is fixed", R1.5).
    - :attr:`TENANT_ADDED` — a tenant-defined variable (overlay) field ("club detail").
    """

    BASE = "base"                        # platform base field, no tenant override
    TENANT_ADDED = "tenant_added"        # tenant-defined variable (overlay) field
    BASE_OVERRIDDEN = "base_overridden"  # platform base field re-presented by a tenant override


@dataclass(frozen=True)
class ResolvedField:
    """One field in the resolved config — a fixed field (possibly overlaid) or a variable one.

    This is the presentation-facing shape: it carries everything the frontend needs to render
    the field and nothing it needs to *enforce* (the authoritative rules stay server-side).
    ``group`` is a string so it spans both the fixed groups (``personal`` / ``membership``) and
    the variable :data:`OVERLAY_GROUP` (``overlay``).
    """

    key: str                       # canonical key within the group (e.g. "first_name", "motor_type")
    group: str                     # STORAGE bucket: "personal" / "membership" / "overlay" (fixed by origin)
    type: FieldType
    required: bool
    origin: FieldOrigin
    # Single-list PROVENANCE badge (Phase 3 step 8, R1.2), DERIVED at resolve time from how the
    # field resolved — base / tenant-added / base-overridden. Orthogonal to `origin` (the storage
    # layer); defaults to BASE so adding it changes neither the resolved field SET nor the
    # `(group, order, key)` ordering (Property 1, R1.6).
    provenance: FieldProvenance = FieldProvenance.BASE
    label: Mapping[str, str] = field(default_factory=dict)   # i18n {"nl": ..., "en": ...}
    choices: Sequence[str] | None = None                  # for FieldType.ENUM (bare value list)
    options: Sequence[EnumOption] | None = None           # rich enum options {value,label,roles?} (R4.11/R4.12)
    functional_group: str = ""                               # PARAMETER-DRIVEN display group (R4.9), orthogonal to `group`
    member_number_format: MemberNumberFormat | None = None  # only on member_number (task 1.4b)
    show_when: Mapping[str, Any] | None = None            # per-field conditional visibility (R4.12)
    calculated_from: Sequence[str] | None = None          # inputs of a CALCULATED field (R4.4), else None
    #: The field's SCOPE attribute (remediation R3.5), carried from the overlay/override onto the
    #: resolved field so the serializer can emit it and the authoring UI can READ the current scope
    #: state back. ``None`` when the field is not a scope axis. This is read re-presentation ONLY —
    #: scope RESOLUTION (``handler/app.py`` → ``allowed_scopes``) still consumes the ``config#scope``
    #: row via ``ScopeConfig`` UNCHANGED (R3.8); the authoritative projection is unaffected.
    scope: FieldScope | None = None
    visible: bool = True
    read_only: bool = False                                  # True for CALCULATED fields (derived, never stored)
    order: int = 0

    def dotted_key(self) -> str:
        """Fully-qualified path of the field, e.g. ``personal.first_name`` / ``overlay.motor_type``."""
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
    #: The tenant's functional (display) group catalog (R4.9), ordered by ``order`` then key.
    #: Empty when the tenant authored no catalog (fields then carry only base-default groups).
    #: Modals / view contexts SECTION by these (design C-SURFACE); a field whose
    #: ``functional_group`` is absent from this catalog falls back to a default section at render.
    functional_groups: tuple[FunctionalGroup, ...] = ()

    def by_group(self) -> Mapping[str, tuple[ResolvedField, ...]]:
        buckets: dict[str, list[ResolvedField]] = {}
        for f in self.fields:
            buckets.setdefault(f.group, []).append(f)
        return {g: tuple(fs) for g, fs in buckets.items()}

    def field(self, dotted_key: str) -> ResolvedField | None:
        """Return the resolved field for a canonical dotted key, or ``None``."""
        for f in self.fields:
            if f.dotted_key() == dotted_key:
                return f
        return None

    def variable_fields(self) -> tuple[ResolvedField, ...]:
        """Only the tenant's variable (overlay) fields."""
        return tuple(f for f in self.fields if f.origin is FieldOrigin.VARIABLE)

    def calculated_fields(self) -> tuple[ResolvedField, ...]:
        """Only the derived (calculated, never-stored) fields (R4.4)."""
        return tuple(f for f in self.fields if f.origin is FieldOrigin.CALCULATED)

    def visible_fields(self) -> tuple[ResolvedField, ...]:
        """The fields the frontend should show (an overlay may hide a fixed field for a tenant)."""
        return tuple(f for f in self.fields if f.visible)


# ── The overlay data model (what a tenant supplies — new tenant = new data, R2.2) ─────


@dataclass(frozen=True)
class OverlayField:
    """A tenant-defined **variable** field ("club detail", e.g. h-dcn Motor type).

    Purely additive data — declaring one for a tenant needs no schema change (R2.2). It lands
    under the record's ``overlay`` attribute; the resolver assigns it :data:`FieldOrigin.VARIABLE`.
    ``functional_group`` (R4.9) is the field's PARAMETER-DRIVEN display group (referencing the
    tenant's ``functional_groups`` catalog); it is orthogonal to the storage bucket (always
    ``overlay`` for a variable field). ``options`` model the rich enum choices
    (``{value,label,roles?}``, R4.11/R4.12); ``show_when`` carries a per-field conditional-
    visibility condition (R4.12) so a hidden field is not required server-side.
    """

    key: str
    type: FieldType = FieldType.STRING
    required: bool = False
    label: Mapping[str, str] = field(default_factory=dict)
    choices: Sequence[str] | None = None
    options: Sequence[EnumOption] | None = None
    functional_group: str | None = None
    show_when: Mapping[str, Any] | None = None
    visible: bool = True
    order: int = 0
    #: Phase 3 step 9 (R2.1) — the SAM READ representation of scope-binding as a field
    #: attribute: when this field is authored as a scope axis, its scope config
    #: (:class:`FieldScope`); ``None`` otherwise. This is the authoring/read re-presentation
    #: ONLY — scope RESOLUTION (``handler/app.py`` → ``allowed_scopes``) continues to consume
    #: the ``config#scope`` row via ``ScopeConfig`` UNCHANGED (R2.3), and the ``config#scope``
    #: dimensions are the authoritative projection the resolver reads (semantic equivalence,
    #: Property 2). The resolver CARRIES this attribute onto the resolved field (remediation
    #: R3.5) so the serializer emits it and the authoring UI can read the current scope state
    #: back; it does not drive scope RESOLUTION.
    scope: FieldScope | None = None


@dataclass(frozen=True)
class FieldScope:
    """The SAM read shape of a field's ``scope`` attribute (Phase 3 step 9, R2.1).

    Expresses, as a field attribute, that a field is a scope axis — ``enabled``, with its value
    vocabulary (``values``), an optional i18n ``label``, and the capabilities that REQUIRE a
    grant (``required_for``). It mirrors the aspects of a :class:`ScopeDimension` that are
    authored per field (the dimension ``key``/``field`` derive from the field's own key, so they
    are NOT carried here). Read-only re-presentation: the authoritative scope projection the
    resolver consumes is still the ``config#scope`` row (``ScopeConfig``), kept semantically
    equivalent by the Flask builder (Property 2).
    """

    enabled: bool = True
    values: Sequence[str] = ()
    label: Mapping[str, str] = field(default_factory=dict)
    required_for: Sequence[str] = ()


@dataclass(frozen=True)
class FixedFieldOverride:
    """A tenant's **presentation-only** override of a *fixed* field.

    A tenant may relabel a fixed field, reorder it, hide it, or (for an *optional* fixed field)
    mark it required in its context. It may **not** weaken a platform invariant — the resolver
    rejects any attempt to (see :class:`OverlayError`). A ``None`` attribute means "leave the
    base value as-is".
    """

    label: Mapping[str, str] | None = None
    visible: bool | None = None
    required: bool | None = None   # may only tighten (optional→required), never loosen
    functional_group: str | None = None   # reassign the field's display group (R4.9); storage bucket unchanged
    options: Sequence[EnumOption] | None = None  # tenant enum values/labels/roles for a Fixed enum (R4.11/R4.12)
    show_when: Mapping[str, Any] | None = None   # per-field conditional visibility (R4.12)
    member_number_format: MemberNumberFormat | None = None  # only meaningful for member_number (task 1.4b)
    order: int | None = None
    #: Phase 3 step 9 (R2.1) — the SAM READ representation of scope-binding as a field attribute
    #: on a FIXED field (e.g. ``region``). ``None`` when the fixed field is not re-presented as a
    #: scope axis. Read re-presentation only; scope RESOLUTION stays on ``config#scope`` /
    #: ``ScopeConfig`` (R2.3), kept semantically equivalent by the Flask builder (Property 2). The
    #: resolver CARRIES this attribute onto the resolved field (remediation R3.5) so the serializer
    #: emits it and the authoring UI can read the current scope state back.
    scope: FieldScope | None = None


@dataclass(frozen=True)
class FunctionalGroup:
    """One entry of a tenant's **functional (display) group** catalog (R4.9).

    A functional group is a presentation-only bucket the frontend sections view contexts /
    modals by (e.g. "address", "motor", "financial"). It is orthogonal to the STORAGE bucket
    (``personal`` / ``membership`` / ``overlay``, fixed by origin). Every field's
    ``functional_group`` must reference the ``key`` of a group in the catalog's group set —
    ``attribute_catalog.BASE_FUNCTIONAL_GROUPS`` ⊕ the tenant's authored entries (Phase 1, R5.3) —
    else the resolver rejects it as a dangling reference (Property 7). ``label`` is the localized
    ``{nl,en}`` section heading; ``order`` sorts the sections.
    """

    key: str
    label: Mapping[str, str] = field(default_factory=dict)
    order: int = 0


@dataclass(frozen=True)
class TenantOverlay:
    """The full per-tenant overlay: functional-group catalog + variable fields + fixed overrides.

    This is the *data* a tenant supplies (h-dcn, then any future club) — the whole point of R2.2
    is that this is all it takes to onboard a tenant: no code, no schema. An empty overlay (the
    default) resolves to exactly the fixed base (with each field's base default functional group).

    ``functional_groups`` is the tenant's display-group catalog (R4.9): a ``functional_group``
    referenced by any field (fixed override, calculated override, or a variable field) MUST be
    one of the catalog's group keys — the resolver rejects a dangling reference (Property 7).
    The catalog's group set is ``BASE_FUNCTIONAL_GROUPS`` ⊕ this tenant catalog (Phase 1, R5.3):
    a reference to a BASE key (``personal`` / ``address`` / ``membership`` / ``administrative``)
    is valid even when this catalog is **empty** (a tenant that authors no catalog resolves
    against the base set; R5.4), while a reference to a NON-base key absent from the tenant
    catalog is still a dangling reference and is rejected.
    """

    #: New variable fields, keyed by their canonical key (lands under the ``overlay`` group).
    fields: Mapping[str, OverlayField] = field(default_factory=dict)
    #: Presentation overrides of fixed (and calculated) fields, keyed by canonical dotted key.
    overrides: Mapping[str, FixedFieldOverride] = field(default_factory=dict)
    #: The tenant's functional-group (display) catalog, keyed by group ``key`` (R4.9).
    functional_groups: Mapping[str, FunctionalGroup] = field(default_factory=dict)


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

    def __init__(self, overlays: Mapping[str, TenantOverlay] | None = None):
        self._overlays = dict(overlays or {})

    def get_overlay(self, tenant_id: str) -> TenantOverlay:
        return self._overlays.get(tenant_id, TenantOverlay())
