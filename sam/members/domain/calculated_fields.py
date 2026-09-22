"""
S5c Task 1.3 — the **calculated (derived) fields** of the member model (design C-FIELDS, R4.4).

A calculated field is **derived, read-only, and NEVER stored** — it is computed on demand from
one or more stored fixed fields (its ``inputs``) in the domain/presentation layer and surfaced
as a read-only :class:`~sam.members.domain.field_resolver.ResolvedField` (origin
``CALCULATED``) so view contexts (Phase 3) and modals (Phase 4) can reference it by key exactly
like a fixed or overlay field. Every entry here is one **Calculated** row of the classification
table (design Data Models); no calculated field is defined that is not a table row, and no
Calculated row is left unimplemented (task 1.5 asserts the table ⇄ definitions mapping is total).

The registry, with English canonical ``snake_case`` keys + ``{nl,en}`` labels (R4.6/R4.7):

    personal:    display_name   (from first_name + name_infix + last_name)
                 age            (from birth_date)
                 birthday       (day+month from birth_date)
    membership:  years_member   (from joined_date)
    administrative (functional group; stored bucket membership):
                 application_year (from the record's creation year — created_at)

It is deliberately **storage-agnostic** (no DynamoDB) and **tenant-agnostic** (no
``if tenant == ...``). Because a calculated field is never stored, ``validate_fixed_fields``
does not check it, and the repository never persists it. The derivations are pure functions of
the record; a missing/blank input yields ``None`` (the field simply isn't shown), never a raise.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Optional, Sequence

from .fixed_fields import FieldGroup, FieldType

__all__ = [
    "CalculatedField",
    "CALCULATED_FIELDS",
    "calculated_field_by_key",
    "compute_calculated_fields",
]


# ── The derivation functions (pure; missing input → None, never raise) ────────────────


def _s(value: Any) -> str:
    """Coerce a value to a stripped string ("" for None/blank)."""
    return str(value).strip() if value is not None else ""


def _personal(record: Mapping[str, Any]) -> Mapping[str, Any]:
    p = record.get("personal") if isinstance(record, Mapping) else None
    return p if isinstance(p, Mapping) else {}


def _membership(record: Mapping[str, Any]) -> Mapping[str, Any]:
    m = record.get("membership") if isinstance(record, Mapping) else None
    return m if isinstance(m, Mapping) else {}


def _parse_iso_date(value: Any) -> Optional[_dt.date]:
    """Parse an ISO-8601 ``YYYY-MM-DD`` (or ``YYYY-MM-DDT...``) string to a date, else None."""
    text = _s(value)
    if not text:
        return None
    try:
        return _dt.date.fromisoformat(text[:10])
    except ValueError:
        return None


def _derive_display_name(record: Mapping[str, Any]) -> Optional[str]:
    """``first_name`` [+ ``name_infix``] + ``last_name`` — the human-readable short name."""
    p = _personal(record)
    parts = [_s(p.get("first_name")), _s(p.get("name_infix")), _s(p.get("last_name"))]
    joined = " ".join(part for part in parts if part)
    return joined or None


def _derive_age(record: Mapping[str, Any], *, today: Optional[_dt.date] = None) -> Optional[int]:
    """Whole years between ``birth_date`` and today (never negative → None for a future date)."""
    born = _parse_iso_date(_personal(record).get("birth_date"))
    if born is None:
        return None
    ref = today or _dt.date.today()
    years = ref.year - born.year - ((ref.month, ref.day) < (born.month, born.day))
    return years if years >= 0 else None


def _derive_birthday(record: Mapping[str, Any]) -> Optional[str]:
    """Day + month of ``birth_date`` as ``MM-DD`` (year-independent), else None."""
    born = _parse_iso_date(_personal(record).get("birth_date"))
    if born is None:
        return None
    return f"{born.month:02d}-{born.day:02d}"


def _derive_years_member(
    record: Mapping[str, Any], *, today: Optional[_dt.date] = None
) -> Optional[int]:
    """Whole years since ``joined_date`` (membership tenure), else None."""
    joined = _parse_iso_date(_membership(record).get("joined_date"))
    if joined is None:
        return None
    ref = today or _dt.date.today()
    years = ref.year - joined.year - ((ref.month, ref.day) < (joined.month, joined.day))
    return years if years >= 0 else None


def _derive_application_year(record: Mapping[str, Any]) -> Optional[int]:
    """The application year: the ``created_at`` year, else the ``joined_date`` year.

    Prefer the record-creation timestamp (``created_at``); when it is absent (e.g. a data
    migration that did not stamp it), fall back to the ``joined_date`` year — for this pilot
    the signature/joined date is effectively the application year (small future discrepancies
    are acceptable; a later refinement may stamp created_at from the source Aanmeldingsjaar).
    Returns ``None`` only when neither date is present.
    """
    created = _parse_iso_date(_membership(record).get("created_at"))
    if created is not None:
        return created.year
    joined = _parse_iso_date(_membership(record).get("joined_date"))
    return joined.year if joined is not None else None


# ── The calculated-field definition ───────────────────────────────────────────────────


@dataclass(frozen=True)
class CalculatedField:
    """One derived, read-only field: its canonical key, type, inputs, and derivation.

    ``group`` is the field's storage/structural bucket for grouping purposes only (a calculated
    field is NEVER stored). ``functional_group`` is its base display group (R4.9), which a
    tenant may reassign via a ``fixed_overrides`` entry keyed by the field's dotted key.
    ``inputs`` names the fixed fields it derives from (for traceability + the resolved field's
    ``calculated_from``). ``compute`` is the pure derivation; a missing input yields ``None``.
    """

    key: str
    group: FieldGroup
    type: FieldType
    label: Mapping[str, str] = field(default_factory=dict)
    inputs: Sequence[str] = ()
    functional_group: Optional[str] = None
    show_when: Optional[Mapping[str, Any]] = None
    order: int = 0
    compute: Optional[Callable[[Mapping[str, Any]], Any]] = None

    def dotted_key(self) -> str:
        """Fully-qualified path of the calculated field, e.g. ``personal.display_name``."""
        return f"{self.group.value}.{self.key}"

    def default_functional_group(self) -> str:
        """The field's base display group — its explicit value, else its storage group."""
        return self.functional_group or self.group.value

    def evaluate(self, record: Mapping[str, Any]) -> Any:
        """Compute the derived value for ``record`` (``None`` when inputs are absent)."""
        return self.compute(record) if self.compute is not None else None


#: The calculated-field registry — one entry per **Calculated** classification-table row.
CALCULATED_FIELDS: tuple[CalculatedField, ...] = (
    CalculatedField(
        key="display_name",
        group=FieldGroup.PERSONAL,
        type=FieldType.STRING,
        label={"nl": "Korte naam", "en": "Display name"},
        inputs=("personal.first_name", "personal.name_infix", "personal.last_name"),
        order=5,
        compute=_derive_display_name,
    ),
    CalculatedField(
        key="age",
        group=FieldGroup.PERSONAL,
        type=FieldType.STRING,  # rendered as text; a number is not a stored FieldType
        label={"nl": "Leeftijd", "en": "Age"},
        inputs=("personal.birth_date",),
        order=55,
        compute=_derive_age,
    ),
    CalculatedField(
        key="birthday",
        group=FieldGroup.PERSONAL,
        type=FieldType.STRING,
        label={"nl": "Verjaardag", "en": "Birthday"},
        inputs=("personal.birth_date",),
        order=56,
        compute=_derive_birthday,
    ),
    CalculatedField(
        key="years_member",
        group=FieldGroup.MEMBERSHIP,
        type=FieldType.STRING,
        label={"nl": "Jaren lid", "en": "Years member"},
        inputs=("membership.joined_date",),
        order=45,
        compute=_derive_years_member,
    ),
    CalculatedField(
        key="application_year",
        group=FieldGroup.MEMBERSHIP,      # not stored; grouped under membership for ordering
        type=FieldType.STRING,
        label={"nl": "Aanmeldingsjaar", "en": "Application year"},
        inputs=("membership.created_at", "membership.joined_date"),
        functional_group="membership",  # user decision: application year is membership data (R4.9)
        order=95,
        compute=_derive_application_year,
    ),
)

# Fail fast at import time on a duplicate calculated key, or a collision with a fixed field key —
# calculated keys share the canonical-key namespace and must be unique/non-colliding.
from .fixed_fields import FIXED_FIELDS as _FIXED_FIELDS  # noqa: E402 (import after registry decl)

_seen: set[str] = set()
_fixed_dotted = {f.dotted_key() for f in _FIXED_FIELDS}
for _c in CALCULATED_FIELDS:
    _dk = _c.dotted_key()
    if _dk in _seen:
        raise ValueError(f"duplicate calculated-field key: {_dk}")
    if _dk in _fixed_dotted:
        raise ValueError(f"calculated-field key collides with a fixed field: {_dk}")
    _seen.add(_dk)
del _seen, _fixed_dotted, _c, _dk


_CALC_BY_DOTTED: Mapping[str, CalculatedField] = {c.dotted_key(): c for c in CALCULATED_FIELDS}


def calculated_field_by_key(dotted_key: str) -> Optional[CalculatedField]:
    """Return the :class:`CalculatedField` for a canonical dotted key, or ``None``."""
    return _CALC_BY_DOTTED.get(dotted_key)


def compute_calculated_fields(record: Mapping[str, Any]) -> dict[str, Any]:
    """Compute every calculated field for ``record`` → ``{dotted_key: value|None}``.

    A convenience for the presentation layer (list/modal projection): derives all calculated
    values in one pass. Never stored, never raises — a field whose inputs are absent maps to
    ``None`` (the frontend simply omits it).
    """
    return {c.dotted_key(): c.evaluate(record) for c in CALCULATED_FIELDS}
