"""
s5c Task 2.4 — authoritative save-time validation for the ``members.*`` parameters
(Flask/MySQL plane; design C-SCHEMA / C-VIEW, Property 7 fail-fast).

This is the Flask-plane guard that runs on a PUT of a ``members.*`` parameter *before*
the value is stored, so a bad config never corrupts the projected tenant config:

- **``members.field_overlay``** — reuses the SAM-domain ``FieldResolver._reject_invalid_overlay``
  semantics (fail-fast): reject an override of an unknown field key, a variable field colliding
  with a fixed/calculated key, an enum variable field with no choices, and — the s5c addition
  (R4.9) — any ``functional_group`` (on a fixed override or a variable field) that is not present
  in the tenant's ``functional_groups`` catalog. It also rejects loosening a platform-required
  fixed field (optional-only tightening).
- **``members.view_contexts``** — reject any ``columns`` / ``filterable_columns`` /
  ``default_sort.field`` ``field_key`` that is NOT resolvable in the tenant's field set
  (fixed ⊕ calculated ⊕ overlay-added ⊕ enabled scope-dimension keys), mirroring the same
  fail-fast (R5.1a).

Cross-plane reuse decision (task 2.4 guidance)
----------------------------------------------
The task asks us to *prefer reuse* of the SAM-domain resolver, and to reimplement the minimal
equivalent (referencing the same contract) only if a cross-plane import is not clean. **We
reimplement here**, because:

- The two planes are independently deployed and packaged: the Flask/MySQL app (``backend/src``,
  Railway) and the SAM module (``sam/members``, Lambda) have **separate** Python paths, pytest
  configs, and dependency trees. ``backend/src`` does not (and must not) place ``sam`` on its
  import path — importing ``sam.members.domain.field_resolver`` into the Flask runtime would
  couple the Railway service to the Lambda package and drag SAM's dependencies into Flask.
- The projection layer already re-expresses these same overlay/scope shapes on the Flask plane
  (``projection_sync.py`` reads ``members.*`` and builds ``config#fields`` / ``config#scope``);
  a small, self-contained validator here is consistent with that boundary.

To keep the two implementations honest, the platform base field-key set below is a **direct
transcription** of the canonical keys in ``sam/members/domain/fixed_fields.py`` +
``calculated_fields.py`` (the single source of truth for field names). The rejection is
fail-fast with a descriptive :class:`MembersConfigError` (mirroring ``OverlayError`` /
``FieldValidationError``) and never mutates or stores the config.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

__all__ = [
    "CALCULATED_FIELD_KEYS",
    "FIXED_FIELD_KEYS",
    "OVERLAY_GROUP",
    "MembersConfigError",
    "validate_field_overlay",
    "validate_members_param",
    "validate_view_contexts",
]


class MembersConfigError(ValueError):
    """Raised when a ``members.*`` parameter fails save-time validation (a config bug).

    Subclasses :class:`ValueError` so the ``members.*`` PUT/save path surfaces it as a 400
    (the parameter routes already translate ``ValueError`` → 400). Carries ``reasons`` (a
    key → human-readable why map) so a misconfiguration surfaces every problem at once —
    mirroring the SAM-domain ``OverlayError`` / ``FieldValidationError``.
    """

    def __init__(self, reasons: Mapping[str, str]):
        self.reasons = dict(reasons)
        detail = "; ".join(f"{k}: {v}" for k, v in self.reasons.items())
        super().__init__(f"invalid members config: {detail}")


#: The storage bucket variable (overlay) fields live under (mirrors field_resolver.OVERLAY_GROUP).
OVERLAY_GROUP = "overlay"

# ── The platform base field-key set — transcribed from the SAM domain registries ──────
# Single source of truth for field NAMES lives in sam/members/domain/{fixed,calculated}_fields.py.
# These sets MUST match those canonical keys (fixed base + calculated fields). Kept as a plain
# transcription so the Flask save path can resolve view-context references without importing SAM.

#: Fixed base fields, as canonical dotted keys (fixed_fields.PERSONAL_FIELDS + MEMBERSHIP_FIELDS).
FIXED_FIELD_KEYS: frozenset[str] = frozenset(
    {
        # personal
        "personal.first_name",
        "personal.last_name",
        "personal.name_infix",
        "personal.initials",
        "personal.birth_date",
        "personal.gender",
        "personal.email",
        "personal.phone",
        "personal.street",
        "personal.postal_code",
        "personal.city",
        "personal.country",
        # membership
        "membership.member_number",
        "membership.status",
        "membership.membership_type",
        "membership.joined_date",
        "membership.created_at",
        "membership.updated_at",
    }
)

#: Calculated (derived, read-only) fields, as canonical dotted keys (calculated_fields.py).
CALCULATED_FIELD_KEYS: frozenset[str] = frozenset(
    {
        "personal.display_name",
        "personal.age",
        "personal.birthday",
        "membership.years_member",
        "membership.application_year",
    }
)

#: All platform base canonical dotted keys (fixed ⊕ calculated) — the fixed half of resolution.
_BASE_DOTTED_KEYS: frozenset[str] = FIXED_FIELD_KEYS | CALCULATED_FIELD_KEYS

#: The bare (undotted) canonical keys — a view context may reference a field by its short key
#: (e.g. "member_number") as in the design examples, so both forms resolve.
_BASE_BARE_KEYS: frozenset[str] = frozenset(
    k.split(".", 1)[1] for k in _BASE_DOTTED_KEYS
)

#: The fixed-base dotted keys that are platform-REQUIRED (may be tightened, never loosened).
#: Transcribed from fixed_fields.py (required=True): the overlay may not make these optional.
_REQUIRED_FIXED_KEYS: frozenset[str] = frozenset(
    {
        "personal.first_name",
        "personal.last_name",
        "personal.email",
        "membership.member_number",
        "membership.status",
        "membership.membership_type",
        "membership.joined_date",
    }
)


# ── helpers ───────────────────────────────────────────────────────────────────────────


def _as_str_list(value: Any) -> list[str]:
    """Coerce a value to a list of strings (tolerating a single string or None)."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        return [v for v in value if isinstance(v, str)]
    return []


def _catalog_keys(overlay: Mapping[str, Any]) -> set[str]:
    """The set of functional-group keys declared in an overlay's functional_groups catalog."""
    catalog = overlay.get("functional_groups") or []
    keys: set[str] = set()
    if isinstance(catalog, list):
        for entry in catalog:
            if isinstance(entry, Mapping):
                k = entry.get("key")
                if isinstance(k, str) and k:
                    keys.add(k)
    return keys


# ── field_overlay validation (reuse of FieldResolver._reject_invalid_overlay semantics) ─


def validate_field_overlay(overlay: Any) -> None:
    """Fail fast if a ``members.field_overlay`` object would violate a platform invariant.

    Mirrors ``FieldResolver._reject_invalid_overlay`` (SAM domain) plus the R4.9 catalog check:

    - an override target must be a known fixed/calculated field (dotted key);
    - a fixed override may not loosen a platform-required field (optional-only tightening);
    - a variable field key may not collide with a fixed/calculated canonical key;
    - an ``enum`` variable field must declare ``choices``;
    - every ``functional_group`` referenced (fixed override or variable field) must be present
      in the tenant's ``functional_groups`` catalog (checked only when a non-empty catalog is
      authored — an empty catalog uses base defaults, exactly like the domain resolver).

    Raises :class:`MembersConfigError` (with a key → reason map) on any violation.
    """
    if overlay is None:
        return
    if not isinstance(overlay, Mapping):
        raise MembersConfigError({"field_overlay": "must be an object"})

    reasons: dict[str, str] = {}
    catalog = _catalog_keys(overlay)

    def _check_group(dotted: str, group: str | None) -> None:
        # Reference-validate only when the tenant authored a catalog (empty → base defaults).
        if group and catalog and group not in catalog:
            reasons[dotted] = (
                f"functional_group {group!r} is not in the functional_groups catalog"
            )

    # fixed_overrides — keyed by canonical dotted key of a fixed/calculated field.
    overrides = overlay.get("fixed_overrides") or {}
    if isinstance(overrides, Mapping):
        for dotted, spec in overrides.items():
            if dotted not in _BASE_DOTTED_KEYS:
                reasons[dotted] = (
                    "overrides an unknown field "
                    "(only fixed/calculated fields may be overridden)"
                )
                continue
            if isinstance(spec, Mapping):
                if spec.get("required") is False and dotted in _REQUIRED_FIXED_KEYS:
                    reasons[dotted] = (
                        "cannot make a platform-required fixed field optional"
                    )
                _check_group(dotted, spec.get("functional_group"))

    # fields — the added variable fields, keyed by canonical key (lands under `overlay`).
    fields = overlay.get("fields") or {}
    if isinstance(fields, Mapping):
        for name, spec in fields.items():
            key = (spec.get("key") if isinstance(spec, Mapping) else None) or name
            dotted = f"{OVERLAY_GROUP}.{key}"
            if key in _BASE_BARE_KEYS:
                reasons[dotted] = (
                    "variable field key collides with a fixed/calculated field key"
                )
            elif (
                isinstance(spec, Mapping)
                and spec.get("type") == "enum"
                and not spec.get("choices")
                and not spec.get("options")
            ):
                reasons[dotted] = "an enum variable field must declare choices/options"
            if isinstance(spec, Mapping):
                _check_group(dotted, spec.get("functional_group"))

    if reasons:
        raise MembersConfigError(reasons)


# ── view_contexts validation (R5.1a — every field_key must resolve) ────────────────────


def _resolvable_field_keys(
    field_overlay: Mapping[str, Any] | None,
    scope_dimensions: Iterable[Any] | None,
) -> set[str]:
    """The full set of field_keys a view context may reference for this tenant.

    Resolution set = fixed base ⊕ calculated ⊕ overlay-added variable fields ⊕ enabled
    scope-dimension keys — accepting both the canonical dotted form (``personal.first_name``)
    and the bare short key (``first_name``), since the design examples reference columns by
    their short key. Scope-dimension keys (e.g. ``region``) are resolvable because a view
    context may surface a scope value as a column (design C-VIEW / C-SCOPE).
    """
    keys: set[str] = set(_BASE_DOTTED_KEYS) | set(_BASE_BARE_KEYS)

    # overlay-added variable fields (both overlay.<key> and bare <key>)
    if isinstance(field_overlay, Mapping):
        fields = field_overlay.get("fields") or {}
        if isinstance(fields, Mapping):
            for name, spec in fields.items():
                key = (spec.get("key") if isinstance(spec, Mapping) else None) or name
                if isinstance(key, str) and key:
                    keys.add(key)
                    keys.add(f"{OVERLAY_GROUP}.{key}")

    # enabled scope-dimension keys
    for dim in scope_dimensions or []:
        if isinstance(dim, Mapping):
            k = dim.get("key")
            enabled = dim.get("enabled", True)
            if isinstance(k, str) and k and enabled:
                keys.add(k)

    return keys


def validate_view_contexts(
    view_contexts: Any,
    *,
    field_overlay: Mapping[str, Any] | None = None,
    scope_dimensions: Iterable[Any] | None = None,
) -> None:
    """Fail fast if any ``members.view_contexts`` field_key does not resolve (R5.1a).

    Every ``columns`` / ``filterable_columns`` entry and the ``default_sort.field`` of each
    context must resolve in the tenant's field set (fixed ⊕ calculated ⊕ overlay ⊕ enabled
    scope dimensions). An unresolvable reference is rejected at Save (authoring) — mirroring
    ``FieldResolver._reject_invalid_overlay`` fail-fast — so the projection never carries a
    dangling column. An empty list is valid (→ one default context downstream).

    ``field_overlay`` / ``scope_dimensions`` are the tenant's sibling ``members.*`` values,
    used to widen the resolvable key set with the tenant's own parameter/overlay fields and
    scope dimensions.

    Raises :class:`MembersConfigError` (with a context.field → reason map) on any violation.
    """
    if view_contexts is None:
        return
    if not isinstance(view_contexts, (list, tuple)):
        raise MembersConfigError({"view_contexts": "must be a list"})

    resolvable = _resolvable_field_keys(field_overlay, scope_dimensions)
    reasons: dict[str, str] = {}

    for idx, ctx in enumerate(view_contexts):
        if not isinstance(ctx, Mapping):
            reasons[f"view_contexts[{idx}]"] = "must be an object"
            continue
        ctx_key = ctx.get("key") if isinstance(ctx.get("key"), str) else f"[{idx}]"

        referenced: list[tuple[str, str]] = []  # (label, field_key)
        for col in _as_str_list(ctx.get("columns")):
            referenced.append(("columns", col))
        for col in _as_str_list(ctx.get("filterable_columns")):
            referenced.append(("filterable_columns", col))
        default_sort = ctx.get("default_sort")
        if isinstance(default_sort, Mapping):
            sort_field = default_sort.get("field")
            if isinstance(sort_field, str) and sort_field:
                referenced.append(("default_sort.field", sort_field))

        for label, field_key in referenced:
            if field_key not in resolvable:
                reasons[f"{ctx_key}.{label}.{field_key}"] = (
                    f"references field_key {field_key!r} which does not resolve in the "
                    "tenant's field set (fixed / parameter / calculated / scope dimension)"
                )

    if reasons:
        raise MembersConfigError(reasons)


# ── dispatch entry point used by the parameter save path ───────────────────────────────


def validate_members_param(
    key: str,
    value: Any,
    *,
    sibling_field_overlay: Mapping[str, Any] | None = None,
    sibling_scope_dimensions: Iterable[Any] | None = None,
) -> None:
    """Validate one ``members.<key>`` value on save; no-op for keys with no save-time rule.

    Dispatches to the per-key validator:
    - ``field_overlay``  → :func:`validate_field_overlay`
    - ``view_contexts``  → :func:`validate_view_contexts` (widened by the tenant's sibling
      ``field_overlay`` / ``scope_dimensions`` so the tenant's own added fields resolve)

    ``scope_dimensions`` has no cross-reference rule of its own here (its internal shape is
    validated by the SAM ``ScopeConfig`` on read); a PUT of it is accepted as-is. Raises
    :class:`MembersConfigError` on any violation; returns None otherwise.
    """
    if key == "field_overlay":
        validate_field_overlay(value)
    elif key == "view_contexts":
        # When validating view_contexts, the overlay/scope come from the sibling params (the
        # value being saved is the view_contexts list itself).
        validate_view_contexts(
            value,
            field_overlay=sibling_field_overlay,
            scope_dimensions=sibling_scope_dimensions,
        )
