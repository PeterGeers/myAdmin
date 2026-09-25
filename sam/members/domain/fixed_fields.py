"""
S5c Task 1.2 — the **fixed base field registry** (personal + membership), broadened
row-by-row from the s5c design "Field classification table" (design Data Models, R4.1/R4.10).

This is the platform-owned base of the member data model (R4.3, design C-FIELDS). It defines
the fields that are **identical for every tenant** and are stored as **first-class attributes**
of the tenant-scoped member record, using **English canonical ``snake_case`` keys** + ``{nl,en}``
labels (R4.6/R4.7). Every entry here is one **Fixed** row of the classification table; no field
is defined that is not a Fixed row, and no Fixed row is left unimplemented (task 1.5 asserts the
table ⇄ definitions mapping is total).

The base, grouped by **storage** bucket (structural, fixed by origin — distinct from the
parameter-driven *functional/display* group of R4.9, which lives on ``ResolvedField`` and is
NOT set here):

    personal:    first_name, last_name, name_infix, initials, birth_date, gender,
                 email, phone, street, postal_code, city, country
                 (address fields STORE under ``personal``; their display group "address" is
                 parameter-driven, task 1.4a — not here)
    membership:  member_number, status, membership_type, joined_date,
                 created_at, updated_at   (the last two are system timestamps; per the
                 classification table their functional group is "administrative", but their
                 STORAGE bucket is ``membership`` — the FieldGroup enum stays personal/membership)

It is deliberately **storage-agnostic** (no DynamoDB, no boto3) and **tenant-agnostic**
(no ``if tenant == ...``) — it is the fixed half of ``FieldResolver.resolve(tenant_id)``, over
which the per-tenant *variable* overlay (``members.field_overlay``) is merged. The registry owns:

- the **canonical field keys** (the single source of truth for field names — no free strings
  scattered across handlers/repository), grouped and ordered, and
- **validation** of a member's fixed data against those field definitions (required-ness, type,
  and the closed membership-status enum),

so the domain layer (and only the domain layer) is the authoritative validator; the React
frontend renders the resolved config and is never trusted to enforce a rule.

R4.2 — **a Fixed field MAY have Parameter enum values.** ``gender`` and ``status`` are Fixed
fields whose *value list* is tenant config (buckets 1/4 of design "Dropdown / enum fields"). The
registry does NOT hardcode a tenant's vocabulary:
- ``status`` uses the platform-canonical **closed** :class:`MembershipStatus` set (the platform
  keeps its lifecycle state set; the tenant enum *values*/labels are config — task 2 leaves
  ``MembershipStatus`` intact because it is imported across the lifecycle/hooks/handler layers).
- ``gender`` is a Fixed enum with **no baked-in choices** — its option list is tenant-supplied via
  ``members.field_overlay`` (so h-dcn's ``M/V/X/N`` is data, not a code constant). Until a tenant
  supplies choices the base leaves them open (any non-blank string).

R4.8 — **``member_number`` is an OPTIONAL Fixed ``string``** (never numeric; s5k): stable,
sortable, and leading-zero-safe. Its tenant **format pattern** (e.g. ``Nr-0001`` / a regex) is a
Parameter added in task 1.4b and only validates a PRESENT value; **there is no generation and no
uniqueness guard** — the number is supplied by manual entry / import (a duplicate is a
data-quality concern, not a write-time conflict).

What this module is NOT:
- It does not validate the *variable overlay* (that is resolved per tenant by ``FieldResolver``).
- It does not enforce the ``member_number`` **format pattern** (task 1.4b) or **value-level enum
  role gating** (task 1.4c) — those are added by later tasks on the resolved field.
- It does not validate ``membership_type`` against the Lidmaatschap Beheer catalog — the registry
  only guarantees the value is a well-formed non-empty code; the authoritative *reference* check
  against a live catalog entry is the MembershipService's job (C8).
- It does not validate ``scope_values`` (``region`` is a scope dimension, ``members.scope_dimensions``).
"""

from __future__ import annotations

import datetime as _dt
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Optional, Sequence

from sam.members.domain.error_codes import (
    FieldError,
    VALIDATION_INVALID_DATE,
    VALIDATION_MUST_BE_A_STRING,
    VALIDATION_MUST_BE_ONE_OF,
    VALIDATION_MUST_NOT_BE_BLANK,
    VALIDATION_REQUIRED,
    VALIDATION_UNSUPPORTED_FIELD_TYPE,
    MEMBER_NUMBER_FORMAT,
)

__all__ = [
    "FieldError",
    "FieldGroup",
    "FieldType",
    "MembershipStatus",
    "EnumOption",
    "MemberNumberFormat",
    "MEMBER_NUMBER_FIELD_KEY",
    "FixedField",
    "FieldValidationError",
    "PERSONAL_FIELDS",
    "MEMBERSHIP_FIELDS",
    "FIXED_FIELDS",
    "FIXED_FIELD_GROUPS",
    "field_by_key",
    "canonical_keys",
    "option_values",
    "roles_for_option",
    "validate_member_number_format",
    "validate_fixed_fields",
]


# ── Enumerations ────────────────────────────────────────────────────────────────────


class FieldGroup(str, Enum):
    """The top-level **storage** buckets of the member record the fixed fields live under.

    Structural and fixed-by-origin (distinct from the parameter-driven *functional/display*
    group of R4.9). These map 1:1 to the first-class attributes of the tenant-scoped member
    record (``member["personal"][...]`` / ``member["membership"][...]``). Address fields store
    under ``personal``; system timestamps store under ``membership``.
    """

    PERSONAL = "personal"
    MEMBERSHIP = "membership"


class FieldType(str, Enum):
    """Canonical value types the base registry validates. Storage-agnostic (no DB types)."""

    STRING = "string"
    DATE = "date"          # ISO-8601 calendar date, YYYY-MM-DD
    ENUM = "enum"          # value must be one of ``FixedField.choices`` (None → open, tenant config)
    REFERENCE = "reference"  # a code that references another entity (e.g. catalog); shape-checked only


class MembershipStatus(str, Enum):
    """The closed membership-status enum (platform-fixed lifecycle state set).

    Per the classification table ``status`` is a **Fixed (Parameter enum values)** field: the
    platform keeps this closed state set; a tenant's enum *values*/labels are config. The
    *transition graph* between these states is tenant **config** (design C2) — the registry only
    fixes the set of legal status *values* every tenant shares.

    NOTE: this enum is imported across ``lifecycle_config`` / ``transition_hooks`` /
    ``tenant_hooks`` / ``handler/app`` / ``tenants/hdcn/hooks`` / ``hdcn_backfill`` — its values
    MUST stay intact.
    """

    APPLICATION = "application"
    PENDING = "pending"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    LAPSED = "lapsed"
    LEFT = "left"


# ── Enum options + value-level role gating (R4.11 / R4.12) ────────────────────────────


@dataclass(frozen=True)
class EnumOption:
    """One selectable option of an ``ENUM`` field — ``{value, label{nl,en}, roles?}`` (R4.11/R4.12).

    This is the single model for a dropdown option wherever an option list lives (design
    "Dropdown / enum fields", buckets 1/2): the enum *values* of a Fixed field (``gender`` /
    ``status``) and the ``choices`` of a Parameter/overlay field. ``value`` is the stored,
    canonical option value; ``label`` is the localized ``{nl,en}`` display text the frontend
    renders; ``roles`` is the **value-level role gate** (R4.12) — the set of roles permitted to
    SELECT this option. An option with **no** ``roles`` (``None``/empty) is available to anyone
    who may edit the field; a non-empty ``roles`` restricts the option to those roles.

    Enforcement (design "Role-restricted enum values"): the frontend filters a dropdown to the
    caller's allowed options as a convenience, but the **domain layer authoritatively rejects**
    a create/edit that sets a role-restricted value the caller may not choose (see
    :func:`roles_for_option`). Frozen because it is shared config, never mutated in place.
    """

    value: str
    label: Mapping[str, str] = field(default_factory=dict)
    roles: Optional[Sequence[str]] = None

    def allows_role(self, caller_roles: Sequence[str]) -> bool:
        """Return True if a caller holding ``caller_roles`` may select this option (R4.12).

        Open (unrestricted) options are always allowed; a role-restricted option is allowed
        only when the caller holds at least one of the option's ``roles``.
        """
        if not self.roles:
            return True
        return any(r in set(self.roles) for r in (caller_roles or ()))


@dataclass(frozen=True)
class MemberNumberFormat:
    """A tenant-configurable ``member_number`` format constraint (R4.2/R4.8, task 1.4b).

    ``member_number`` stays a Fixed **string** (never numeric); its *format* is tenant
    Parameter config. A tenant expresses the format one of two ways (mutually usable):

    - a **prefix + zero-padded width** (e.g. ``prefix="Nr-"``, ``width=4`` → ``Nr-0001``): the
      value must equal the prefix followed by exactly ``width`` digits; or
    - a **regex** (``regex=r"..."``): the value must fully match it.

    When both are given the regex takes precedence. An empty format (the default) imposes no
    constraint beyond the base "non-blank string". **There is no generation (s5k)** — the number
    is supplied by manual entry / import; this only *validates* a PRESENT entered value
    (create/edit/import), and an absent value is allowed (member_number is optional).
    """

    prefix: str = ""
    width: int = 0
    regex: Optional[str] = None

    def is_empty(self) -> bool:
        """True when this format imposes no constraint (no regex and no positive width)."""
        return not self.regex and self.width <= 0

    def as_regex(self) -> Optional[str]:
        """Return the effective regex for this format, or ``None`` when unconstrained.

        A supplied ``regex`` wins; otherwise a ``prefix``+``width`` is compiled into an
        anchored ``^<escaped-prefix>\\d{width}$`` pattern.
        """
        if self.regex:
            return self.regex
        if self.width > 0:
            return rf"^{re.escape(self.prefix)}\d{{{int(self.width)}}}$"
        return None

    def matches(self, value: str) -> bool:
        """True if ``value`` satisfies the format (an empty format matches any non-blank string)."""
        pattern = self.as_regex()
        if pattern is None:
            return True
        try:
            return re.fullmatch(pattern, value) is not None
        except re.error:
            # A malformed tenant regex is a config bug — fail closed (nothing matches) rather
            # than silently accepting; the authoring-time validation should have caught it.
            return False

    def example(self) -> Optional[str]:
        """A human-readable example value (``prefix`` + ``width`` zeros+1), for error messages."""
        if self.regex:
            return None
        if self.width > 0:
            return f"{self.prefix}{1:0{int(self.width)}d}"
        return None


#: The canonical dotted key of the member-number field (single source of truth).
MEMBER_NUMBER_FIELD_KEY = "membership.member_number"


# ── Field definition ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class FixedField:
    """One platform-fixed field: its canonical key, storage group, type, and validation rules.

    ``key`` is the **canonical field key** (English, ``snake_case``) — the single source of truth
    for the field's name. ``group`` places it under a first-class member attribute (its STORAGE
    bucket). Instances are frozen (immutable) because the base registry is a constant shared by
    every tenant. ``choices`` is optional even for ``ENUM`` fields: an ``ENUM`` with no ``choices``
    is an **open** enum whose value list is tenant config (R4.2, e.g. ``gender``).
    """

    key: str
    group: FieldGroup
    type: FieldType
    required: bool = False
    label: Mapping[str, str] = field(default_factory=dict)   # i18n, e.g. {"nl": ..., "en": ...}
    choices: Optional[Sequence[str]] = None                  # for FieldType.ENUM (None → open/tenant-config)
    options: Optional[Sequence[EnumOption]] = None           # rich enum options {value,label,roles?} (R4.11/R4.12)
    functional_group: Optional[str] = None                   # base default display group (R4.9); None → storage group
    member_number_format: Optional[MemberNumberFormat] = None  # only meaningful for member_number (task 1.4b)
    show_when: Optional[Mapping[str, Any]] = None            # per-field conditional-visibility condition (R4.12)
    order: int = 0

    def dotted_key(self) -> str:
        """Fully-qualified path of the field in the record, e.g. ``membership.status``."""
        return f"{self.group.value}.{self.key}"

    def default_functional_group(self) -> str:
        """The field's base functional (display) group — its explicit value or its storage group.

        The *functional group* (R4.9) is a presentation attribute distinct from the STORAGE
        bucket (:class:`FieldGroup`). Fixed fields get a base default here (which a tenant may
        override via ``members.field_overlay`` ``fixed_overrides``); when unset it falls back to
        the field's storage group so every resolved field always carries a non-empty group.
        """
        return self.functional_group or self.group.value


class FieldValidationError(Exception):
    """Raised when a member's fixed data fails base-registry validation.

    Carries ``errors`` — a mapping of dotted field key → :class:`FieldError` (a machine ``code``
    + human ``detail`` + optional ``params``, RFC 9457 per-entry) — so callers (the domain
    service / handler) can surface all problems at once, LOCALIZED via the code, rather than one
    raw English string at a time (API response & error standard v1.0).
    """

    def __init__(self, errors: Mapping[str, FieldError]):
        self.errors: dict[str, FieldError] = dict(errors)
        detail = "; ".join(f"{k}: {v.detail}" for k, v in self.errors.items())
        super().__init__(f"fixed-field validation failed: {detail}")


# ── The registry (personal + membership) — one FixedField per Fixed classification row ─

PERSONAL_FIELDS: tuple[FixedField, ...] = (
    # Name parts (universal) — classification: `first_name, last_name, name_infix, initials`.
    FixedField(
        key="first_name",
        group=FieldGroup.PERSONAL,
        type=FieldType.STRING,
        required=True,
        label={"nl": "Voornaam", "en": "First name"},
        order=10,
    ),
    FixedField(
        key="last_name",
        group=FieldGroup.PERSONAL,
        type=FieldType.STRING,
        required=True,
        label={"nl": "Achternaam", "en": "Last name"},
        order=20,
    ),
    FixedField(
        key="name_infix",
        group=FieldGroup.PERSONAL,
        type=FieldType.STRING,
        required=False,
        label={"nl": "Tussenvoegsel", "en": "Name infix"},
        order=30,
    ),
    FixedField(
        key="initials",
        group=FieldGroup.PERSONAL,
        type=FieldType.STRING,
        required=False,
        label={"nl": "Initialen", "en": "Initials"},
        order=40,
    ),
    # Birth date — classification: `birth_date` (Fixed). `age`/`birthday` are Calculated (task 1.3).
    FixedField(
        key="birth_date",
        group=FieldGroup.PERSONAL,
        type=FieldType.DATE,
        required=False,
        label={"nl": "Geboortedatum", "en": "Date of birth"},
        order=50,
    ),
    # Gender — Fixed field, **Parameter enum values** (R4.2): open enum, tenant supplies choices.
    FixedField(
        key="gender",
        group=FieldGroup.PERSONAL,
        type=FieldType.ENUM,
        required=False,
        choices=None,  # tenant config (e.g. h-dcn M/V/X/N) via members.field_overlay
        label={"nl": "Geslacht", "en": "Gender"},
        order=60,
    ),
    # Contact — classification: `email` (Fixed), `phone` (Fixed). NOTE: `email` is NOT
    # required. It is account identity WHEN a member is also a login user, but most members
    # are records-only (e.g. ~66% of the h-dcn Ledenbestand have no email). Requiring it would
    # make the majority of a real membership un-importable, so the platform keeps it optional;
    # a tenant that runs member logins enforces email presence at the account-creation edge,
    # not on the member record.
    FixedField(
        key="email",
        group=FieldGroup.PERSONAL,
        type=FieldType.STRING,
        required=False,
        label={"nl": "E-mail", "en": "Email"},
        order=70,
    ),
    FixedField(
        key="phone",
        group=FieldGroup.PERSONAL,
        type=FieldType.STRING,
        required=False,
        label={"nl": "Telefoon", "en": "Phone"},
        order=80,
    ),
    # Address (universal) — classification group "address" is the FUNCTIONAL/display group
    # (parameter-driven, task 1.4a); these fields STORE under `personal`.
    FixedField(
        key="street",
        group=FieldGroup.PERSONAL,
        type=FieldType.STRING,
        required=False,
        label={"nl": "Straat", "en": "Street"},
        order=90,
    ),
    FixedField(
        key="postal_code",
        group=FieldGroup.PERSONAL,
        type=FieldType.STRING,
        required=False,
        label={"nl": "Postcode", "en": "Postal code"},
        order=100,
    ),
    FixedField(
        key="city",
        group=FieldGroup.PERSONAL,
        type=FieldType.STRING,
        required=False,
        label={"nl": "Woonplaats", "en": "City"},
        order=110,
    ),
    FixedField(
        key="country",
        group=FieldGroup.PERSONAL,
        type=FieldType.STRING,
        required=False,
        label={"nl": "Land", "en": "Country"},
        order=120,
    ),
)

MEMBERSHIP_FIELDS: tuple[FixedField, ...] = (
    # member_number — Fixed **string** (never numeric), OPTIONAL (s5k). Manual entry / import;
    # NO auto-generation and NO uniqueness guard — a duplicate is a data-quality concern, not a
    # write-time conflict. The optional tenant format pattern (task 1.4b) only validates a
    # PRESENT value; sponsors/clubs/numberless members persist with an empty member_number.
    FixedField(
        key="member_number",
        group=FieldGroup.MEMBERSHIP,
        type=FieldType.STRING,
        required=False,
        label={"nl": "Lidnummer", "en": "Member number"},
        order=10,
    ),
    # status — Fixed field, **Parameter enum values** (R4.2). The platform keeps the closed
    # MembershipStatus set; tenant labels/values are config. Choices are the canonical set here;
    # the tenant may relabel/restrict via overlay without changing the platform state set.
    FixedField(
        key="status",
        group=FieldGroup.MEMBERSHIP,
        type=FieldType.ENUM,
        required=True,
        choices=tuple(s.value for s in MembershipStatus),
        # Rich options (R4.11): the platform-canonical closed lifecycle set with {nl,en} labels.
        # No `roles` restriction on any status option in the base (a tenant may add gating via
        # overlay); frontend renders these labels, the domain still validates against `choices`.
        options=(
            EnumOption(value="application", label={"nl": "Aanmelding", "en": "Application"}),
            EnumOption(value="pending", label={"nl": "In behandeling", "en": "Pending"}),
            EnumOption(value="active", label={"nl": "Actief", "en": "Active"}),
            EnumOption(value="suspended", label={"nl": "Geschorst", "en": "Suspended"}),
            EnumOption(value="lapsed", label={"nl": "Verlopen", "en": "Lapsed"}),
            EnumOption(value="left", label={"nl": "Uitgeschreven", "en": "Left"}),
        ),
        label={"nl": "Status", "en": "Status"},
        order=20,
    ),
    # membership_type — Fixed reference to the Lidmaatschap Beheer catalog (tenant data, C8).
    # The registry shape-checks the value; the authoritative live-catalog reference check is
    # the MembershipService's. Value-level role gating on options is task 1.4c.
    FixedField(
        key="membership_type",
        group=FieldGroup.MEMBERSHIP,
        type=FieldType.REFERENCE,
        required=True,
        label={"nl": "Lidmaatschapstype", "en": "Membership type"},
        order=30,
    ),
    # joined_date — Fixed date, required. `years_member` is Calculated from it (task 1.3).
    FixedField(
        key="joined_date",
        group=FieldGroup.MEMBERSHIP,
        type=FieldType.DATE,
        required=True,
        label={"nl": "Ingangsdatum", "en": "Joined date"},
        order=40,
    ),
    # System timestamps — Fixed (system). Classification functional group is "administrative";
    # STORAGE bucket is `membership` (the FieldGroup enum stays personal/membership). Optional at
    # the registry level — they are stamped by the repository, not required user input.
    FixedField(
        key="created_at",
        group=FieldGroup.MEMBERSHIP,
        type=FieldType.STRING,
        required=False,
        label={"nl": "Aangemaakt op", "en": "Created at"},
        functional_group="administrative",  # display group per the classification table (R4.9)
        order=90,
    ),
    FixedField(
        key="updated_at",
        group=FieldGroup.MEMBERSHIP,
        type=FieldType.STRING,
        required=False,
        label={"nl": "Bijgewerkt op", "en": "Updated at"},
        functional_group="administrative",  # display group per the classification table (R4.9)
        order=100,
    ),
)

#: The full fixed base registry, personal first then membership, both in ``order``.
FIXED_FIELDS: tuple[FixedField, ...] = PERSONAL_FIELDS + MEMBERSHIP_FIELDS

#: The registry grouped by first-class (storage) attribute (the shape resolved config is served in).
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


# ── Enum-option helpers (R4.11 / R4.12) ───────────────────────────────────────────────


def option_values(options: Optional[Sequence[EnumOption]]) -> tuple[str, ...]:
    """The bare option *values* of a rich enum-option list (for value-membership checks)."""
    return tuple(o.value for o in (options or ()))


def roles_for_option(
    options: Optional[Sequence[EnumOption]], value: Any
) -> Optional[frozenset[str]]:
    """Return the role gate for the option whose value == ``value`` (R4.12).

    Returns ``None`` when the value is not a role-restricted option (unknown value, or an
    option with no ``roles`` → open to anyone who may edit the field); returns a frozenset of
    permitted roles when the option is gated. Callers use this to authoritatively reject a
    create/edit that sets a role-restricted value the caller may not choose.
    """
    for opt in options or ():
        if opt.value == value:
            return frozenset(opt.roles) if opt.roles else None
    return None


# ── member_number format validation (task 1.4b) ───────────────────────────────────────


def validate_member_number_format(
    value: Any, fmt: Optional[MemberNumberFormat]
) -> Optional[FieldError]:
    """Return a :class:`FieldError` if ``value`` violates the tenant ``member_number`` format, else None.

    Authoritative create/edit/import validation (R4.2/R4.8): a present ``member_number`` must be
    a non-blank string AND satisfy the tenant format pattern (when one is configured). An empty/
    absent format imposes no constraint beyond "non-blank string". Generation stays OUT.

    All failures carry the ``errors.member.numberFormat`` code (API standard v1.0); ``params``
    carries the format hint (``example``/``pattern``) for i18n interpolation, and ``detail`` keeps
    the English message so a client that cannot resolve the code still shows it.
    """
    if not isinstance(value, str) or not value.strip():
        return FieldError(code=MEMBER_NUMBER_FORMAT, detail="must be a non-blank string")
    if fmt is None or fmt.is_empty():
        return None
    if not fmt.matches(value):
        example = fmt.example()
        pattern = fmt.as_regex()
        if example is not None:
            return FieldError(
                code=MEMBER_NUMBER_FORMAT,
                detail=f"must match the tenant member-number format (e.g. {example})",
                params={"example": example},
            )
        return FieldError(
            code=MEMBER_NUMBER_FORMAT,
            detail=f"must match the tenant member-number format {pattern!r}",
            params={"pattern": pattern},
        )
    return None


# ── Validation ──────────────────────────────────────────────────────────────────────

_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _validate_date(value: Any) -> Optional[FieldError]:
    """Return a :class:`FieldError` if ``value`` is not an ISO-8601 (YYYY-MM-DD) date, else None.

    Both the wrong-shape and the impossible-calendar-date cases carry the shared
    ``validation.invalidDate`` code; ``detail`` keeps the specific English wording.
    """
    if not isinstance(value, str) or not _ISO_DATE_RE.match(value):
        return FieldError(
            code=VALIDATION_INVALID_DATE, detail="must be an ISO-8601 date (YYYY-MM-DD)"
        )
    try:
        _dt.date.fromisoformat(value)
    except ValueError:
        return FieldError(code=VALIDATION_INVALID_DATE, detail="is not a valid calendar date")
    return None


def _validate_value(fld: FixedField, value: Any) -> Optional[FieldError]:
    """Validate a single present, non-null value against its field definition.

    Returns a :class:`FieldError` (machine ``code`` + English ``detail`` + optional ``params``),
    or None when the value is valid.

    A blank/whitespace string on an OPTIONAL field is treated as "empty" (valid) — clearing an
    optional field (e.g. wiping the Dutch ``tussenvoegsel``/name_infix) is a normal edit, not an
    error. Only a REQUIRED string/reference field rejects a blank value ("must not be blank").
    """
    if fld.type is FieldType.STRING or fld.type is FieldType.REFERENCE:
        if not isinstance(value, str):
            return FieldError(code=VALIDATION_MUST_BE_A_STRING, detail="must be a string")
        if not value.strip():
            if fld.required:
                return FieldError(
                    code=VALIDATION_MUST_NOT_BE_BLANK, detail="must not be blank"
                )
            return None
        return None

    if fld.type is FieldType.DATE:
        return _validate_date(value)

    if fld.type is FieldType.ENUM:
        # An ENUM with no `choices` is an OPEN enum (its value list is tenant config, R4.2):
        # the base only requires a well-formed non-blank string; the resolved tenant field
        # (with tenant-supplied choices) enforces membership downstream.
        if fld.choices is None:
            if not isinstance(value, str) or not value.strip():
                return FieldError(
                    code=VALIDATION_MUST_BE_A_STRING, detail="must be a non-blank string"
                )
            return None
        if value not in fld.choices:
            allowed = ", ".join(fld.choices)
            return FieldError(
                code=VALIDATION_MUST_BE_ONE_OF,
                detail=f"must be one of: {allowed}",
                params={"allowed": list(fld.choices)},
            )
        return None

    # Defensive: an unknown type in the registry is a programming error, not user input.
    return FieldError(
        code=VALIDATION_UNSUPPORTED_FIELD_TYPE, detail=f"unsupported field type: {fld.type}"
    )


def validate_fixed_fields(
    member: Mapping[str, Any],
    *,
    partial: bool = False,
) -> None:
    """Validate a member record's **fixed** (personal + membership) data.

    ``member`` is the record shape from the design data model — a mapping with ``personal`` and
    ``membership`` sub-mappings. Only the fixed base registry is checked here; the per-tenant
    variable overlay, scope values, and the membership-type *catalog reference* are validated
    elsewhere (see module docstring).

    Rules enforced:
    - **required** fields must be present and non-null (unless ``partial=True``, used for
      update/patch flows where absent keys mean "leave unchanged");
    - present, non-null values must satisfy their field **type** (string non-blank; date
      ISO-8601; status one of the closed :class:`MembershipStatus` enum; an OPEN enum a
      non-blank string; reference a non-blank code);
    - a ``None`` value clears an **optional** field (allowed) but fails a **required** one.

    Raises :class:`FieldValidationError` (with a key→reason map) if anything is invalid;
    returns None on success.
    """
    errors: dict[str, FieldError] = {}

    for fld in FIXED_FIELDS:
        group_data = member.get(fld.group.value)
        present_group = isinstance(group_data, Mapping)
        has_key = present_group and (fld.key in group_data)
        value = group_data.get(fld.key) if present_group else None

        if not has_key or value is None:
            # Missing/null: an error only if required and we are not doing a partial update.
            missing = (not has_key) or (value is None)
            if fld.required and missing and not (partial and not has_key):
                errors[fld.dotted_key()] = FieldError(
                    code=VALIDATION_REQUIRED, detail="is required"
                )
            continue

        reason = _validate_value(fld, value)
        if reason is not None:
            errors[fld.dotted_key()] = reason

    if errors:
        raise FieldValidationError(errors)
