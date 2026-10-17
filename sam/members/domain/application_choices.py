"""Enum **application choice SUBSET** — public-form exposure + submit validation (R4a; design seam c).

An enum / choice field that a tenant selects onto the public application form (R4.2–R4.4) MAY
declare an **application choice subset** — ``ResolvedField.application_choices`` (a tuple of bare
values, ``None`` = full set, D20/R4a). This module is the single home of the two operations that
subset drives, kept PURE (no I/O) and module-neutral so both the public field-config read
(Phase 4) and the ``create_application`` validator (Phase 2) call the same authority:

- :func:`application_subset_choices` — the choices EXPOSED on the public form for a field: the
  declared subset when present, else the field's full resolved choices (back-compatible default,
  R4a.2). This is what the public schema serves and the form renders.
- :func:`validate_application_choice` — validate a SUBMITTED value against that subset (R4a.3):
  a value outside the subset is rejected with a field-level :class:`FieldError` (merged into the
  R1a 422 ``errors`` array by the caller), EVEN IF it is a valid staff-facing choice.

Fail-loud on a bad subset (R4a.4)
---------------------------------
The subset MUST be a subset of the field's resolved choices. A ``application_choices`` entry that
is NOT one of the field's choices is a **config bug**, not applicant input — it is surfaced
fail-fast as an :class:`OverlayError` (the same discipline the resolver applies to an enum with no
choices), never silently accepted. This mirrors the Flask write-time projection validator (task
8.3, R4c.3: "subset ⊆ field choices"); this is the SAM read-side guard that the same invariant
holds when the resolved field is actually consumed, so a subset slipping past authoring can never
expose or accept an off-list value.

Shape tolerance
---------------
``ResolvedField.choices`` is contractually a bare value list, but a tenant's raw overlay JSON can
carry rich option objects (``{"value", "label"}``) or ``EnumOption`` instances under ``choices``;
those flow through un-normalized in some paths. Every choice is coerced to its string value
(:func:`_choice_value`) so the subset/membership checks and error messages are robust to either
shape and NEVER raise on a malformed shape (a malformed value must surface as a 422/config error,
never a 502). This mirrors ``WritesMixin._choice_value``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from .error_codes import VALIDATION_MUST_BE_ONE_OF, FieldError
from .fixed_fields import FieldType

if TYPE_CHECKING:
    from ._field_models import OverlayError, ResolvedField

__all__ = [
    "application_subset_choices",
    "validate_application_choice",
]


def _choice_value(choice: Any) -> str:
    """Coerce a single enum choice to its string *value*, tolerant of shape.

    ``ResolvedField.choices`` is normally a bare value list, but a tenant's raw overlay JSON can
    carry rich option objects (``{"value": ..., "label": ...}``) or an ``EnumOption`` under
    ``choices``. Return the ``value`` for those, else the plain string — so a subset/membership
    check never chokes on a dict. Mirrors ``WritesMixin._choice_value`` (kept in sync).
    """
    if isinstance(choice, Mapping):
        return str(choice.get("value", ""))
    value_attr = getattr(choice, "value", None)
    if value_attr is not None:
        return str(value_attr)
    return str(choice)


def _resolved_choice_values(field: "ResolvedField") -> tuple[str, ...]:
    """The field's full resolved choices as a bare, shape-tolerant string tuple (order-preserving)."""
    return tuple(_choice_value(c) for c in (field.choices or ()))


def application_subset_choices(field: "ResolvedField") -> tuple[str, ...]:
    """Return the enum choices EXPOSED on the public application form for ``field`` (R4a.2).

    When the field declares a subset (``application_choices`` is not ``None``), ONLY the subset is
    offered, in its declared order; when it declares none (``None``), the field's full resolved
    choices are offered (back-compatible default, R4a.2).

    Fail-loud (R4a.4): a declared subset MUST be a subset of the field's resolved choices. A subset
    entry that is NOT one of the field's choices is a config bug and raises :class:`OverlayError`
    (keyed by the field's dotted key), never silently dropped — the same fail-fast discipline the
    resolver applies to an enum with no choices.

    Pure: safe to call from the public read (Phase 4) and the submit validator (Phase 2) alike.
    """
    # Imported here (not at module top) to avoid an import cycle: ``_field_models`` imports from
    # ``fixed_fields``, and this module imports ``ResolvedField``/``OverlayError`` from it — the
    # function-local import keeps the single source of ``OverlayError`` without the cycle.
    from ._field_models import OverlayError

    full = _resolved_choice_values(field)
    subset = field.application_choices
    if subset is None:
        # No subset declared → the full choice set is offered (back-compatible default).
        return full

    allowed = set(full)
    dangling = [value for value in subset if value not in allowed]
    if dangling:
        offenders = ", ".join(repr(v) for v in dangling)
        raise OverlayError(
            {
                field.dotted_key(): (
                    f"application_choices subset entr{'y' if len(dangling) == 1 else 'ies'} "
                    f"{offenders} not in the field's choices — a subset must be ⊆ the field "
                    f"choices (R4a.4)"
                )
            }
        )
    # Preserve the tenant-declared subset order (what the form renders / pre-selects first from).
    return tuple(subset)


def validate_application_choice(field: "ResolvedField", value: Any) -> FieldError | None:
    """Validate a SUBMITTED value against the field's application subset (R4a.3).

    Returns ``None`` when the value is acceptable, or a :class:`FieldError`
    (``VALIDATION_MUST_BE_ONE_OF`` with ``params={"allowed": [...]}``) when it is outside the
    subset — EVEN IF it is a valid staff-facing choice. The caller merges the returned error into
    the shared ``{field: FieldError}`` map (surfaced as a 422 ``errors`` entry).

    Scope (R4a.3): this validates ONLY enum/choice fields that actually offer a closed choice set
    on the form. A non-enum field, or an enum with no resolved choices (an open enum, tenant
    config), is not subset-gated here and returns ``None`` — required-ness and the live-catalog
    reference check (``membership_type``, R11) remain the caller's separate concerns. An
    absent/blank value is likewise left to the required-ness rule (a blank is not "outside the
    subset").

    Fail-loud (R4a.4): computing the subset re-runs the subset ⊆ choices guard, so a submit against
    a field with a broken subset raises :class:`OverlayError` (config bug) rather than validating.
    """
    if field.type is not FieldType.ENUM:
        return None

    allowed = application_subset_choices(field)
    if not allowed:
        # Open enum (no closed choice set) — nothing to gate against here.
        return None

    # An absent/blank value is the required-ness rule's concern, not the subset's.
    if value is None or (isinstance(value, str) and not value.strip()):
        return None

    if _choice_value(value) not in set(allowed):
        return FieldError(
            code=VALIDATION_MUST_BE_ONE_OF,
            detail=f"must be one of: {', '.join(allowed)}",
            params={"allowed": list(allowed)},
        )
    return None
