"""
S5 Task 1.1 — the **fixed base field registry** (personal + membership).

This is the platform-owned base of the member data model (R2.1, design C3/data models).
It defines the fields that are **identical for every tenant** and are stored as
**first-class attributes** of the tenant-scoped member record:

    personal:   name, contact, address, birthdate
    membership: member_number, status, membership_type, joined, left

It is deliberately **storage-agnostic** (no DynamoDB, no boto3) and **tenant-agnostic**
(no ``if tenant == ...``) — it is the fixed half of ``FieldResolver.resolve(tenant_id)``
(task 1.2), over which the per-tenant *variable* overlay is merged. The registry owns:

- the **canonical field keys** (the single source of truth for field names — no free
  strings scattered across handlers/repository), grouped and ordered, and
- **validation** of a member's fixed data against those field definitions
  (required-ness, type, and the closed membership-status enum),

so the domain layer (and only the domain layer) is the authoritative validator; the React
frontend renders the resolved config and is never trusted to enforce a rule.

What this module is NOT:
- It does not validate the *variable overlay* (that is resolved per tenant — task 1.2).
- It does not validate ``membership_type`` against the Lidmaatschap Beheer catalog — the
  registry only guarantees the value is a well-formed non-empty code; the authoritative
  *reference* check against a live catalog entry is the MembershipService's job (C8,
  task 1.5 / 5.3).
- It does not validate ``scope_values`` (a platform-fixed field with tenant values,
  modelled by the scope-dimension design — task 1.3).
"""

from __future__ import annotations

import datetime as _dt
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Mapping, Optional, Sequence

__all__ = [
    "FieldGroup",
    "FieldType",
    "MembershipStatus",
    "FixedField",
    "FieldValidationError",
    "PERSONAL_FIELDS",
    "MEMBERSHIP_FIELDS",
    "FIXED_FIELDS",
    "FIXED_FIELD_GROUPS",
    "field_by_key",
    "canonical_keys",
    "validate_fixed_fields",
]


# ── Enumerations ────────────────────────────────────────────────────────────────────


class FieldGroup(str, Enum):
    """The top-level attribute buckets of the member record the fixed fields live under.

    These map 1:1 to the first-class attributes of the tenant-scoped member record
    (``member["personal"][...]`` / ``member["membership"][...]``) — see design data models.
    """

    PERSONAL = "personal"
    MEMBERSHIP = "membership"


class FieldType(str, Enum):
    """Canonical value types the base registry validates. Storage-agnostic (no DB types)."""

    STRING = "string"
    DATE = "date"          # ISO-8601 calendar date, YYYY-MM-DD
    ENUM = "enum"          # value must be one of ``FixedField.choices``
    REFERENCE = "reference"  # a code that references another entity (e.g. catalog); shape-checked only


class MembershipStatus(str, Enum):
    """The closed membership-status enum (platform-fixed vocabulary).

    The *transition graph* between these states is tenant **config** (design C2, task 5) —
    the registry only fixes the set of legal status *values* every tenant shares.
    """

    APPLICATION = "application"
    PENDING = "pending"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    LAPSED = "lapsed"
    LEFT = "left"


# ── Field definition ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class FixedField:
    """One platform-fixed field: its canonical key, group, type, and validation rules.

    ``key`` is the **canonical field key** — the single source of truth for the field's
    name. ``group`` places it under a first-class member attribute. Instances are frozen
    (immutable) because the base registry is a constant shared by every tenant.
    """

    key: str
    group: FieldGroup
    type: FieldType
    required: bool = False
    label: Mapping[str, str] = field(default_factory=dict)   # i18n, e.g. {"nl": ..., "en": ...}
    choices: Optional[Sequence[str]] = None                  # for FieldType.ENUM
    order: int = 0

    def dotted_key(self) -> str:
        """Fully-qualified path of the field in the record, e.g. ``membership.status``."""
        return f"{self.group.value}.{self.key}"


class FieldValidationError(Exception):
    """Raised when a member's fixed data fails base-registry validation.

    Carries ``errors`` — a mapping of dotted field key → human-readable reason — so callers
    (the domain service / handler) can surface all problems at once rather than one at a time.
    """

    def __init__(self, errors: Mapping[str, str]):
        self.errors = dict(errors)
        detail = "; ".join(f"{k}: {v}" for k, v in self.errors.items())
        super().__init__(f"fixed-field validation failed: {detail}")


# ── The registry (personal + membership) ─────────────────────────────────────────────

PERSONAL_FIELDS: tuple[FixedField, ...] = (
    FixedField(
        key="name",
        group=FieldGroup.PERSONAL,
        type=FieldType.STRING,
        required=True,
        label={"nl": "Naam", "en": "Name"},
        order=10,
    ),
    FixedField(
        key="contact",
        group=FieldGroup.PERSONAL,
        type=FieldType.STRING,
        required=True,
        label={"nl": "Contact", "en": "Contact"},
        order=20,
    ),
    FixedField(
        key="address",
        group=FieldGroup.PERSONAL,
        type=FieldType.STRING,
        required=False,
        label={"nl": "Adres", "en": "Address"},
        order=30,
    ),
    FixedField(
        key="birthdate",
        group=FieldGroup.PERSONAL,
        type=FieldType.DATE,
        required=False,
        label={"nl": "Geboortedatum", "en": "Date of birth"},
        order=40,
    ),
)

MEMBERSHIP_FIELDS: tuple[FixedField, ...] = (
    FixedField(
        key="member_number",
        group=FieldGroup.MEMBERSHIP,
        type=FieldType.STRING,
        required=True,
        label={"nl": "Lidnummer", "en": "Member number"},
        order=10,
    ),
    FixedField(
        key="status",
        group=FieldGroup.MEMBERSHIP,
        type=FieldType.ENUM,
        required=True,
        choices=tuple(s.value for s in MembershipStatus),
        label={"nl": "Status", "en": "Status"},
        order=20,
    ),
    FixedField(
        # References a Lidmaatschap Beheer catalog code (C8). The registry shape-checks the
        # value; the authoritative live-catalog reference check is the MembershipService's.
        key="membership_type",
        group=FieldGroup.MEMBERSHIP,
        type=FieldType.REFERENCE,
        required=True,
        label={"nl": "Lidmaatschapstype", "en": "Membership type"},
        order=30,
    ),
    FixedField(
        key="joined",
        group=FieldGroup.MEMBERSHIP,
        type=FieldType.DATE,
        required=True,
        label={"nl": "Ingangsdatum", "en": "Joined"},
        order=40,
    ),
    FixedField(
        # Null while the member has not left; a date once they have.
        key="left",
        group=FieldGroup.MEMBERSHIP,
        type=FieldType.DATE,
        required=False,
        label={"nl": "Einddatum", "en": "Left"},
        order=50,
    ),
)

#: The full fixed base registry, personal first then membership, both in ``order``.
FIXED_FIELDS: tuple[FixedField, ...] = PERSONAL_FIELDS + MEMBERSHIP_FIELDS

#: The registry grouped by first-class attribute (the shape resolved config is served in).
FIXED_FIELD_GROUPS: Mapping[FieldGroup, tuple[FixedField, ...]] = {
    FieldGroup.PERSONAL: PERSONAL_FIELDS,
    FieldGroup.MEMBERSHIP: MEMBERSHIP_FIELDS,
}

# Fail fast at import time if two fields ever collide on a canonical dotted key — the
# registry is the single source of truth for field names, so duplicates must be impossible.
_seen_keys: set[str] = set()
for _f in FIXED_FIELDS:
    _dotted = _f.dotted_key()
    if _dotted in _seen_keys:
        raise ValueError(f"duplicate canonical fixed-field key: {_dotted}")
    _seen_keys.add(_dotted)
del _seen_keys, _f, _dotted


# ── Lookups ───────────────────────────────────────────────────────────────────────────

_FIELD_BY_DOTTED: Mapping[str, FixedField] = {f.dotted_key(): f for f in FIXED_FIELDS}


def field_by_key(dotted_key: str) -> Optional[FixedField]:
    """Return the :class:`FixedField` for a canonical dotted key (``group.field``), or None."""
    return _FIELD_BY_DOTTED.get(dotted_key)


def canonical_keys() -> tuple[str, ...]:
    """All canonical dotted keys in registry order — the field-name source of truth."""
    return tuple(f.dotted_key() for f in FIXED_FIELDS)


# ── Validation ──────────────────────────────────────────────────────────────────────

_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _validate_date(value: Any) -> Optional[str]:
    """Return an error reason if ``value`` is not an ISO-8601 (YYYY-MM-DD) date, else None."""
    if not isinstance(value, str) or not _ISO_DATE_RE.match(value):
        return "must be an ISO-8601 date (YYYY-MM-DD)"
    try:
        _dt.date.fromisoformat(value)
    except ValueError:
        return "is not a valid calendar date"
    return None


def _validate_value(fld: FixedField, value: Any) -> Optional[str]:
    """Validate a single present, non-null value against its field definition.

    Returns an error reason string, or None when the value is valid.
    """
    if fld.type is FieldType.STRING or fld.type is FieldType.REFERENCE:
        if not isinstance(value, str):
            return "must be a string"
        if not value.strip():
            return "must not be blank"
        return None

    if fld.type is FieldType.DATE:
        return _validate_date(value)

    if fld.type is FieldType.ENUM:
        if value not in (fld.choices or ()):
            allowed = ", ".join(fld.choices or ())
            return f"must be one of: {allowed}"
        return None

    # Defensive: an unknown type in the registry is a programming error, not user input.
    return f"unsupported field type: {fld.type}"


def validate_fixed_fields(
    member: Mapping[str, Any],
    *,
    partial: bool = False,
) -> None:
    """Validate a member record's **fixed** (personal + membership) data.

    ``member`` is the record shape from the design data model — a mapping with
    ``personal`` and ``membership`` sub-mappings. Only the fixed base registry is checked
    here; the per-tenant variable overlay, scope values, and the membership-type *catalog
    reference* are validated elsewhere (see module docstring).

    Rules enforced:
    - **required** fields must be present and non-null (unless ``partial=True``, used for
      update/patch flows where absent keys mean "leave unchanged");
    - present, non-null values must satisfy their field **type** (string non-blank; date
      ISO-8601; status one of the closed :class:`MembershipStatus` enum; reference a
      non-blank code);
    - a ``None`` value clears an **optional** field (allowed) but fails a **required** one.

    Raises :class:`FieldValidationError` (with a key→reason map) if anything is invalid;
    returns None on success.
    """
    errors: dict[str, str] = {}

    for fld in FIXED_FIELDS:
        group_data = member.get(fld.group.value)
        present_group = isinstance(group_data, Mapping)
        has_key = present_group and (fld.key in group_data)
        value = group_data.get(fld.key) if present_group else None

        if not has_key or value is None:
            # Missing/null: an error only if required and we are not doing a partial update.
            missing = (not has_key) or (value is None)
            if fld.required and missing and not (partial and not has_key):
                errors[fld.dotted_key()] = "is required"
            continue

        reason = _validate_value(fld, value)
        if reason is not None:
            errors[fld.dotted_key()] = reason

    if errors:
        raise FieldValidationError(errors)
