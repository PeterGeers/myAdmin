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

from typing import Any

from .calculated_fields import CALCULATED_FIELDS, CalculatedField
from .fixed_fields import (
    FIXED_FIELDS,
    EnumOption,
    FieldGroup,
    FieldType,
    FixedField,
    MemberNumberFormat,
)

__all__ = [
    "OVERLAY_GROUP",
    "FieldOrigin",
    "ResolvedField",
    "FieldConfig",
    "OverlayField",
    "FixedFieldOverride",
    "FunctionalGroup",
    "TenantOverlay",
    "TenantOverlayProvider",
    "StaticOverlayProvider",
    "OverlayError",
    "FieldResolver",
    "evaluate_show_when",
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
    label: Mapping[str, str] = field(default_factory=dict)   # i18n {"nl": ..., "en": ...}
    choices: Optional[Sequence[str]] = None                  # for FieldType.ENUM (bare value list)
    options: Optional[Sequence[EnumOption]] = None           # rich enum options {value,label,roles?} (R4.11/R4.12)
    functional_group: str = ""                               # PARAMETER-DRIVEN display group (R4.9), orthogonal to `group`
    member_number_format: Optional[MemberNumberFormat] = None  # only on member_number (task 1.4b)
    show_when: Optional[Mapping[str, Any]] = None            # per-field conditional visibility (R4.12)
    calculated_from: Optional[Sequence[str]] = None          # inputs of a CALCULATED field (R4.4), else None
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
    functional_groups: tuple["FunctionalGroup", ...] = ()

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
    choices: Optional[Sequence[str]] = None
    options: Optional[Sequence[EnumOption]] = None
    functional_group: Optional[str] = None
    show_when: Optional[Mapping[str, Any]] = None
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
    functional_group: Optional[str] = None   # reassign the field's display group (R4.9); storage bucket unchanged
    options: Optional[Sequence[EnumOption]] = None  # tenant enum values/labels/roles for a Fixed enum (R4.11/R4.12)
    show_when: Optional[Mapping[str, Any]] = None   # per-field conditional visibility (R4.12)
    member_number_format: Optional[MemberNumberFormat] = None  # only meaningful for member_number (task 1.4b)
    order: Optional[int] = None


@dataclass(frozen=True)
class FunctionalGroup:
    """One entry of a tenant's **functional (display) group** catalog (R4.9).

    A functional group is a presentation-only bucket the frontend sections view contexts /
    modals by (e.g. "address", "motor", "financial"). It is orthogonal to the STORAGE bucket
    (``personal`` / ``membership`` / ``overlay``, fixed by origin). Every field's
    ``functional_group`` must reference the ``key`` of one of these catalog entries
    (reference-validated, Property 7). ``label`` is the localized ``{nl,en}`` section heading;
    ``order`` sorts the sections.
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
    one of these keys — the resolver rejects a dangling reference (Property 7). An **empty**
    catalog disables that check (a tenant that authors no catalog uses only base defaults).
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

    def __init__(self, overlays: Optional[Mapping[str, TenantOverlay]] = None):
        self._overlays = dict(overlays or {})

    def get_overlay(self, tenant_id: str) -> TenantOverlay:
        return self._overlays.get(tenant_id, TenantOverlay())


# ── The resolver ──────────────────────────────────────────────────────────────────────

# A dotted-key → fixed-field lookup, used to validate overrides (single source of truth).
_FIXED_BY_DOTTED: Mapping[str, FixedField] = {f.dotted_key(): f for f in FIXED_FIELDS}
_FIXED_KEYS: frozenset[str] = frozenset(f.key for f in FIXED_FIELDS)
# Calculated fields may be RE-PRESENTED by an override (relabel/reorder/hide/reassign group) but
# never have their derived nature changed, so they are a valid — but read-only — override target.
_CALCULATED_BY_DOTTED: Mapping[str, CalculatedField] = {
    c.dotted_key(): c for c in CALCULATED_FIELDS
}
_CALCULATED_KEYS: frozenset[str] = frozenset(c.key for c in CALCULATED_FIELDS)
#: All canonical keys a variable (overlay) field must not collide with (fixed + calculated).
_RESERVED_KEYS: frozenset[str] = _FIXED_KEYS | _CALCULATED_KEYS


class FieldResolver:
    """Resolves ``tenant_id -> FieldConfig`` = fixed base registry ⊕ per-tenant overlay (C3).

    Storage-agnostic and tenant-agnostic: it is constructed with a
    :class:`TenantOverlayProvider` and merges whatever overlay that provider returns over the
    platform fixed base. The generic core has no tenant conditionals — h-dcn is just the first
    ``tenant_id`` whose overlay the provider happens to carry (Property 5).
    """

    def __init__(self, overlay_provider: TenantOverlayProvider):
        self._provider = overlay_provider

    def resolve(
        self,
        tenant_id: str,
        scope_vocab: Optional[Mapping[str, Sequence[str]]] = None,
    ) -> FieldConfig:
        """Return the resolved field config for ``tenant_id`` (fixed base ⊕ overlay).

        Steps: read the tenant's overlay from the provider → validate it against the platform
        invariants (raise :class:`OverlayError` on violation) → apply presentation overrides to
        the fixed fields → append the tenant's variable fields → sort deterministically (by
        group, then order, then key) so the resolved config is stable for the frontend.

        ``scope_vocab`` (S5j / design D1a) is an optional ``{member_field_key: values}`` map
        derived by the caller from the tenant's ENABLED scope dimensions (keyed by each
        dimension's ``field``). An OVERLAY ``enum`` field with NO inline choices whose key is in
        this map gets its ``choices`` sourced from that vocabulary — so a scope-dimension-backed
        dropdown (h-dcn ``region``) needs no duplicated inline choices (``scope_dimensions`` is
        the single source of truth). A choiceless enum that is NOT in the map is still a genuine
        config bug and is still rejected (fail-fast preserved). ``None`` = no sourcing.
        """
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise ValueError("tenant_id must be a non-empty string")

        overlay = self._provider.get_overlay(tenant_id)
        vocab = dict(scope_vocab or {})
        # Validation and variable-field projection both honor the scope vocabulary, so a
        # dimension-backed choiceless enum is treated as if it declared those choices.
        self._reject_invalid_overlay(overlay, scope_vocab=vocab)

        resolved: list[ResolvedField] = [
            self._apply_override(fixed, overlay) for fixed in FIXED_FIELDS
        ]
        # Calculated fields (R4.4): derived, read-only, NEVER stored. They resolve like fixed
        # fields (a tenant may re-present them via a `fixed_overrides` entry keyed by their
        # dotted key), so view contexts / modals can reference them by key uniformly.
        resolved.extend(
            self._as_calculated_field(calc, overlay) for calc in CALCULATED_FIELDS
        )
        resolved.extend(
            self._as_variable_field(name, of, scope_vocab=vocab)
            for name, of in overlay.fields.items()
        )

        resolved.sort(key=lambda f: (f.group, f.order, f.key))
        # Surface the tenant's functional-group (display) catalog (R4.9), ordered by
        # (order, key), so the frontend can SECTION the modals/contexts by it (C-SURFACE).
        groups = tuple(
            sorted(overlay.functional_groups.values(), key=lambda g: (g.order, g.key))
        )
        return FieldConfig(
            tenant_id=tenant_id, fields=tuple(resolved), functional_groups=groups
        )

    # ── internals ─────────────────────────────────────────────────────────────────────

    @staticmethod
    def _apply_override(fixed: FixedField, overlay: TenantOverlay) -> ResolvedField:
        """Project a fixed field into a resolved field, applying any presentation override."""
        override = overlay.overrides.get(fixed.dotted_key())
        label: Mapping[str, str] = fixed.label
        required = fixed.required
        visible = True
        order = fixed.order
        functional_group = fixed.default_functional_group()  # base default (R4.9)
        options = fixed.options
        show_when = fixed.show_when
        member_number_format = fixed.member_number_format
        if override is not None:
            if override.label is not None:
                label = override.label
            if override.required is not None:
                required = override.required
            if override.visible is not None:
                visible = override.visible
            if override.order is not None:
                order = override.order
            if override.functional_group is not None:
                functional_group = override.functional_group
            if override.options is not None:
                options = override.options
            if override.show_when is not None:
                show_when = override.show_when
            if override.member_number_format is not None:
                member_number_format = override.member_number_format
        # Keep `choices` (the bare value list) coherent with rich `options` when a tenant
        # supplies them (so consumers that read either stay consistent).
        choices = fixed.choices
        if options is not None:
            choices = tuple(o.value for o in options)
        return ResolvedField(
            key=fixed.key,
            group=fixed.group.value,
            type=fixed.type,
            required=required,
            origin=FieldOrigin.FIXED,
            label=label,
            choices=choices,
            options=options,
            functional_group=functional_group,
            member_number_format=member_number_format,
            show_when=show_when,
            visible=visible,
            order=order,
        )

    @staticmethod
    def _as_calculated_field(calc: CalculatedField, overlay: TenantOverlay) -> ResolvedField:
        """Project a derived (calculated) field into a read-only resolved field (R4.4).

        Calculated fields are NEVER stored. Like fixed fields they may be re-presented by a
        ``fixed_overrides`` entry keyed by their dotted key (relabel / reorder / hide / reassign
        functional group), but their type/required/read-only nature is fixed by the platform.
        """
        override = overlay.overrides.get(calc.dotted_key())
        label: Mapping[str, str] = calc.label
        visible = True
        order = calc.order
        functional_group = calc.default_functional_group()
        show_when = calc.show_when
        if override is not None:
            if override.label is not None:
                label = override.label
            if override.visible is not None:
                visible = override.visible
            if override.order is not None:
                order = override.order
            if override.functional_group is not None:
                functional_group = override.functional_group
            if override.show_when is not None:
                show_when = override.show_when
        return ResolvedField(
            key=calc.key,
            group=calc.group.value,
            type=calc.type,
            required=False,            # a derived field is never required input
            origin=FieldOrigin.CALCULATED,
            label=label,
            functional_group=functional_group,
            show_when=show_when,
            calculated_from=tuple(calc.inputs),
            visible=visible,
            read_only=True,
            order=order,
        )

    @staticmethod
    def _as_variable_field(
        name: str,
        of: OverlayField,
        scope_vocab: Optional[Mapping[str, Sequence[str]]] = None,
    ) -> ResolvedField:
        """Project a tenant-defined variable field into a resolved field under the overlay group.

        S5j (design D1a): an ``enum`` field with no inline choices/options whose key is bound to
        a scope dimension (present in ``scope_vocab``) sources its ``choices`` from that
        dimension's values — ``scope_dimensions.values`` is the single source of truth, so the
        overlay stores no duplicate list.
        """
        key = of.key or name
        choices = of.choices
        if of.options is not None:
            choices = tuple(o.value for o in of.options)
        elif (
            of.type is FieldType.ENUM
            and not of.choices
            and scope_vocab is not None
            and key in scope_vocab
        ):
            choices = tuple(scope_vocab[key])
        return ResolvedField(
            key=key,
            group=OVERLAY_GROUP,
            type=of.type,
            required=of.required,
            origin=FieldOrigin.VARIABLE,
            label=of.label,
            choices=choices,
            options=of.options,
            functional_group=of.functional_group or OVERLAY_GROUP,
            show_when=of.show_when,
            visible=of.visible,
            order=of.order,
        )

    @staticmethod
    def _reject_invalid_overlay(
        overlay: TenantOverlay,
        scope_vocab: Optional[Mapping[str, Sequence[str]]] = None,
    ) -> None:
        """Fail fast if the overlay tries to weaken a platform invariant (a config bug).

        Rejects (Property 7 fail-fast semantics): an override of an unknown field key; loosening
        a platform-required fixed field; a variable field colliding with a fixed/calculated key;
        an enum field with no options/choices; and any ``functional_group`` reference (on a fixed
        override, a calculated override, or a variable field) that is not present in the tenant's
        ``functional_groups`` catalog (when a non-empty catalog is authored).

        S5j (design D1a): an ``enum`` field with no inline choices is NOT a config bug when it is
        bound to a scope dimension — i.e. its key is present in ``scope_vocab`` (the
        ``{field: values}`` map the caller derives from the tenant's enabled scope dimensions).
        Such a field legitimately sources its choices from ``scope_dimensions.values``. A
        choiceless enum NOT in the map is still rejected (fail-fast preserved).
        """
        reasons: dict[str, str] = {}
        catalog = set(overlay.functional_groups.keys())
        vocab_keys = set((scope_vocab or {}).keys())

        def _check_group(dotted: str, group: Optional[str]) -> None:
            # Reference-validate only when the tenant authored a catalog (empty → base defaults).
            if group and catalog and group not in catalog:
                reasons[dotted] = (
                    f"functional_group {group!r} is not in the functional_groups catalog"
                )

        for dotted, override in overlay.overrides.items():
            fixed = _FIXED_BY_DOTTED.get(dotted)
            calc = _CALCULATED_BY_DOTTED.get(dotted)
            if fixed is None and calc is None:
                reasons[dotted] = (
                    "overrides an unknown field (only fixed/calculated fields may be overridden)"
                )
                continue
            if fixed is not None:
                # An overlay may tighten (optional → required) but never loosen a required field.
                if override.required is False and fixed.required:
                    reasons[dotted] = "cannot make a platform-required fixed field optional"
            _check_group(dotted, override.functional_group)

        for name, of in overlay.fields.items():
            key = of.key or name
            dotted = f"{OVERLAY_GROUP}.{key}"
            # A variable field may not collide with the canonical key of a fixed/calculated field.
            if key in _RESERVED_KEYS:
                reasons[dotted] = "variable field key collides with a fixed/calculated field key"
            elif (
                of.type is FieldType.ENUM
                and not of.choices
                and not of.options
                and key not in vocab_keys  # S5j: a scope-dimension-backed enum sources its
                # choices from scope_dimensions.values — not a config bug (design D1a).
            ):
                reasons[dotted] = "an enum variable field must declare choices/options"
            _check_group(dotted, of.functional_group)

        if reasons:
            raise OverlayError(reasons)


# ── show_when conditional-visibility evaluation (R4.12) ───────────────────────────────


def _member_value(record: Mapping[str, Any], key: str) -> Any:
    """Look up a (possibly dotted) field value in a member record.

    ``key`` may be a bare field key (``membership_type``) or a dotted storage path
    (``membership.membership_type`` / ``personal.gender`` / ``overlay.motor_brand``). A bare
    key is searched across the record's storage groups (``personal`` / ``membership`` /
    ``overlay``) and then the record's top-level scalars (the flattened row shape the frontend
    sends). Returns ``None`` when unresolved.
    """
    if "." in key:
        group, _, sub = key.partition(".")
        bucket = record.get(group)
        if isinstance(bucket, Mapping):
            return bucket.get(sub)
        return None
    for group in ("personal", "membership", OVERLAY_GROUP):
        bucket = record.get(group)
        if isinstance(bucket, Mapping) and key in bucket:
            return bucket.get(key)
    return record.get(key)


def evaluate_show_when(
    show_when: Optional[Mapping[str, Any]], record: Mapping[str, Any]
) -> bool:
    """Return whether a field's ``show_when`` condition holds for ``record`` (R4.12).

    Convention (shared verbatim with the frontend so the client and server agree): ``show_when``
    is a mapping of ``{controlling_field_key: expected}``, ALL entries of which must hold (an
    implicit AND). ``expected`` may be a single scalar (the record value must equal it) or a
    list/tuple (the record value must be one of them). A controlling key resolves against the
    member record (bare key searched across storage groups + top-level, or a dotted path).

    An ``None``/empty ``show_when`` means the field is ALWAYS shown (returns ``True``). This is
    the single authoritative predicate: the server uses it so a HIDDEN field is not required
    (:meth:`MembershipService._required_when_visible`), and the frontend uses the same rule so a
    hidden field is not rendered/validated — the two never disagree.
    """
    if not show_when:
        return True
    for controlling_key, expected in show_when.items():
        actual = _member_value(record, controlling_key)
        if isinstance(expected, (list, tuple, set)):
            if actual not in set(expected):
                return False
        else:
            if actual != expected:
                return False
    return True
