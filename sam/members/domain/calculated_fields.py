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
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from .fixed_fields import FieldGroup, FieldType

__all__ = [
    "CALCULATED_FIELDS",
    "CalculatedField",
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


def _parse_iso_date(value: Any) -> _dt.date | None:
    """Parse an ISO-8601 ``YYYY-MM-DD`` (or ``YYYY-MM-DDT...``) string to a date, else None."""
    text = _s(value)
    if not text:
        return None
    try:
        return _dt.date.fromisoformat(text[:10])
    except ValueError:
        return None


def _derive_display_name(record: Mapping[str, Any]) -> str | None:
    """``first_name`` [+ ``name_infix``] + ``last_name`` — the human-readable short name."""
    p = _personal(record)
    parts = [_s(p.get("first_name")), _s(p.get("name_infix")), _s(p.get("last_name"))]
    joined = " ".join(part for part in parts if part)
    return joined or None


def _derive_age(
    record: Mapping[str, Any], *, today: _dt.date | None = None
) -> int | None:
    """Whole years between ``birth_date`` and today (never negative → None for a future date)."""
    born = _parse_iso_date(_personal(record).get("birth_date"))
    if born is None:
        return None
    ref = today or _dt.date.today()
    years = ref.year - born.year - ((ref.month, ref.day) < (born.month, born.day))
    return years if years >= 0 else None


def _derive_birthday(record: Mapping[str, Any]) -> str | None:
    """Day + month of ``birth_date`` as ``MM-DD`` (year-independent), else None."""
    born = _parse_iso_date(_personal(record).get("birth_date"))
    if born is None:
        return None
    return f"{born.month:02d}-{born.day:02d}"


def _derive_birth_day(record: Mapping[str, Any]) -> str | None:
    """Day-of-month of ``birth_date`` as zero-padded text (``01``–``31``), else None.

    Zero-padded (not ``1``–``31``) so a substring column filter is unambiguous: filtering
    ``01`` matches only the 1st, never 10/11/21/31. Mirrors the already-padded ``birthday``
    (``MM-DD``). Still a two-char text value — the field type stays STRING.
    """
    born = _parse_iso_date(_personal(record).get("birth_date"))
    return f"{born.day:02d}" if born is not None else None


def _derive_birth_month(record: Mapping[str, Any]) -> str | None:
    """Month of ``birth_date`` as zero-padded text (``01``–``12``), else None.

    Zero-padded (not ``1``–``12``) so a substring column filter is unambiguous: filtering
    ``01`` matches only January, never 10/11/12. Mirrors the already-padded ``birthday``.
    """
    born = _parse_iso_date(_personal(record).get("birth_date"))
    return f"{born.month:02d}" if born is not None else None


def _derive_birth_year(record: Mapping[str, Any]) -> str | None:
    """Year of ``birth_date`` (``YYYY``) as text, else None."""
    born = _parse_iso_date(_personal(record).get("birth_date"))
    return str(born.year) if born is not None else None


def _derive_birth_quarter(record: Mapping[str, Any]) -> str | None:
    """Calendar quarter of ``birth_date`` (``(month - 1) // 3 + 1`` → ``1``–``4``), else None."""
    born = _parse_iso_date(_personal(record).get("birth_date"))
    return str((born.month - 1) // 3 + 1) if born is not None else None


def _coerce_nonneg_int(value: Any, *, default: int = 0) -> int:
    """Coerce a stored value to a non-negative int, else ``default``.

    Used for optional year counts (``previous_years`` etc.) that come from
    admin-entered judgement rather than system accumulation.
    Negative numbers and non-integer strings are treated as invalid → ``default``.
    """
    if value is None:
        return default
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return n if n >= 0 else default


def _reference_date(m: Mapping[str, Any], today: _dt.date | None = None) -> _dt.date:
    """Reference date for tenure math.

    If the membership is closed (``left``/``lapsed``) use ``leaving_date`` so the
    closed-period length is frozen; otherwise use ``today`` (or the supplied
    reference date).
    """
    if (m.get("status") or "").strip().lower() in {"left", "lapsed"}:
        left = _parse_iso_date(m.get("leaving_date"))
        if left is not None:
            return left
    return today or _dt.date.today()


def _derive_years_member(
    record: Mapping[str, Any], *, today: _dt.date | None = None
) -> int | None:
    """Years member (tenure): admin-entered prior years + elapsed years since join.

    ``previous_years`` (admin-entered, on the membership bucket) holds tenure from
    closed prior periods — no history is retained, only one necessary integer.
    For a closed membership (``left``/``lapsed``) the reference date is
    ``leaving_date`` so the closed-period length is frozen.
    """
    m = _membership(record)
    joined = _parse_iso_date(m.get("joined_date"))
    if joined is None:
        return None
    prev = _coerce_nonneg_int(m.get("previous_years"), default=0)
    ref = _reference_date(m, today)
    current = ref.year - joined.year
    return prev + current if current >= 0 else None


def _derive_application_year(record: Mapping[str, Any]) -> int | None:
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
    functional_group: str | None = None
    show_when: Mapping[str, Any] | None = None
    order: int = 0
    compute: Callable[[Mapping[str, Any]], Any] | None = None

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
        key="birth_day",
        group=FieldGroup.PERSONAL,
        type=FieldType.STRING,
        label={"nl": "Geboortedag", "en": "Birth day"},
        inputs=("personal.birth_date",),
        order=57,
        compute=_derive_birth_day,
    ),
    CalculatedField(
        key="birth_month",
        group=FieldGroup.PERSONAL,
        type=FieldType.STRING,
        label={"nl": "Geboortemaand", "en": "Birth month"},
        inputs=("personal.birth_date",),
        order=58,
        compute=_derive_birth_month,
    ),
    CalculatedField(
        key="birth_year",
        group=FieldGroup.PERSONAL,
        type=FieldType.STRING,
        label={"nl": "Geboortejaar", "en": "Birth year"},
        inputs=("personal.birth_date",),
        order=59,
        compute=_derive_birth_year,
    ),
    CalculatedField(
        key="birth_quarter",
        group=FieldGroup.PERSONAL,
        type=FieldType.STRING,
        label={"nl": "Geboortekwartaal", "en": "Birth quarter"},
        inputs=("personal.birth_date",),
        order=60,
        compute=_derive_birth_quarter,
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
        group=FieldGroup.MEMBERSHIP,  # not stored; grouped under membership for ordering
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
from .fixed_fields import (
    FIXED_FIELDS as _FIXED_FIELDS,
)

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


_CALC_BY_DOTTED: Mapping[str, CalculatedField] = {
    c.dotted_key(): c for c in CALCULATED_FIELDS
}


def calculated_field_by_key(dotted_key: str) -> CalculatedField | None:
    """Return the :class:`CalculatedField` for a canonical dotted key, or ``None``."""
    return _CALC_BY_DOTTED.get(dotted_key)


def compute_calculated_fields(record: Mapping[str, Any]) -> dict[str, Any]:
    """Compute every calculated field for ``record`` → ``{dotted_key: value|None}``.

    A convenience for the presentation layer (list/modal projection): derives all calculated
    values in one pass. Never stored, never raises — a field whose inputs are absent maps to
    ``None`` (the frontend simply omits it).
    """
    return {c.dotted_key(): c.evaluate(record) for c in CALCULATED_FIELDS}
