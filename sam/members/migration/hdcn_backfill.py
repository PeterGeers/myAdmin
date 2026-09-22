"""
S5 Task 4.1 — the h-dcn member **backfill** transform + read-only source adapters (R5.2,
design "New tenant-scoped tables + backfill" / C6 / C3, Property 7).

This reproduces the *purpose* of h-dcn's historical ``migrationHDCNLedenbestand`` import
(the Ledenbestand import from a Google Sheet) — mapping h-dcn's flat member rows into the
NEW module's tenant-scoped data model — but targets ``sam-members`` and is **dry-run first**
and **non-destructive** (it never modifies the live source; the live data stays the source
of truth until a gated cutover).

Two concerns are split so the transform is unit-testable without any live system:

1. **Source adapters (pluggable, READ-ONLY)** — :class:`HdcnSourceAdapter` yields raw h-dcn
   member rows. :class:`FileSourceAdapter` reads a CSV or JSON export (a Google-Sheet export
   *is* a CSV/JSON), so a dry-run runs against a fixture without touching Google or DynamoDB.
   :class:`LegacyDynamoSourceAdapter` is a documented stub for reading the legacy ``Members``
   table READ-ONLY — reading is non-destructive, and it NEVER writes/modifies the source.

2. **A pure transform** — :func:`map_hdcn_row` maps one raw row to a member record
   ``{ tenant_id, member_id, personal{}, membership{}, overlay{region:<canonical>, ...} }``,
   using the s5c **English canonical Fixed keys** (this is the one place the Dutch→EN column
   translation happens). It stamps ``tenant_id = "h-dcn"``, normalizes the h-dcn region onto
   the plain ``overlay.region`` scope FIELD via the shared ``scope_canon`` (S5d D1/R9.2 — the
   retired ``scope_values`` bucket is gone), folds club/Motor + unmapped columns into ``overlay``,
   maps the h-dcn membership-type
   value to a catalog ``type_code`` (C8), and validates the produced fixed fields via
   :func:`sam.members.domain.fixed_fields.validate_fixed_fields` so a bad mapping fails
   loudly in dry-run. It is storage-agnostic and tenant-agnostic in *mechanism* — the only
   tenant literal is the pilot value being stamped, which is this script's whole job.

The catalog itself is seeded by task 4.2; this backfill only *maps to* a ``type_code`` and
(optionally) validates it against a set of expected codes — the two stay decoupled.
"""

from __future__ import annotations

import csv
import datetime as _dt
import io
import json
import os
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Iterable, Iterator, Mapping, Optional, Protocol, Sequence

from sam.members.domain.fixed_fields import (
    FieldValidationError,
    validate_fixed_fields,
)
from sam.members.domain.scope_canon import scope_canon

__all__ = [
    "HDCN_TENANT_ID",
    "FIXED_SOURCE_COLUMNS",
    "MembershipTypeMapper",
    "RegionCanonicalizer",
    "RowTransformError",
    "RowSkipped",
    "map_hdcn_row",
    "HdcnSourceAdapter",
    "FileSourceAdapter",
    "IterableSourceAdapter",
    "LegacyDynamoSourceAdapter",
    "TransformedRow",
    "BackfillPlan",
    "build_backfill_plan",
]

#: The pilot tenant the backfill stamps. This is the ONE legitimate place a tenant literal
#: lives (design constraint): the backfill's whole job is to stamp the pilot tenant onto the
#: migrated records. It must NOT become an ``if tenant == "h-dcn"`` branch in the generic core.
HDCN_TENANT_ID = "h-dcn"

class RegionCanonicalizer:
    """Normalizes a raw export region onto a tenant's CANONICAL value set (A.10 / D17).

    The canonical vocabulary is **TENANT DATA**, injected — it is NOT sourced from any core
    constant (the generic core ships no tenant's regions). Onboarding passes the same value
    set it authors into ``members.scope_dimensions`` (from ``scripts/aws/h-dcn/members_config.json``)
    so the importer and enforcement share ONE vocabulary (Property 4, no drift).

    Two-step match (S5d R9.2/D5):
    1. an optional spelling ALIAS keyed by ``scope_canon`` of the raw value (for a genuine
       letter difference ``scope_canon`` cannot fold — e.g. h-dcn's ``Drente`` → ``Drenthe``),
       then
    2. canonical-equality against the value set (``scope_canon`` on both sides — case /
       diacritic / separator fold).

    An unknown region (no alias, no canonical match) is preserved VERBATIM (trimmed) and thus
    surfaced by the R9.5 verification (R9.3) — never silently dropped. An EMPTY canonicalizer
    (no values) leaves every value verbatim; callers that need canonicalization MUST supply the
    tenant's values (there is no hidden default vocabulary).
    """

    def __init__(
        self,
        values: Iterable[str] = (),
        *,
        aliases: Optional[Mapping[str, str]] = None,
    ):
        self._canonical_by_canon: dict[str, str] = {scope_canon(v): v for v in values}
        # aliases: raw spelling -> canonical value; matched on the raw's scope_canon.
        self._alias_by_canon: dict[str, str] = {
            scope_canon(raw): canonical for raw, canonical in (aliases or {}).items()
        }

    def canonical(self, value: str) -> str:
        canon = scope_canon(value)
        if not canon:
            return value.strip()
        if canon in self._alias_by_canon:
            return self._alias_by_canon[canon]
        return self._canonical_by_canon.get(canon, value.strip())


#: A neutral EMPTY canonicalizer — the safe default when a caller supplies no tenant vocabulary
#: (every region kept verbatim). Real onboarding/tests pass a populated RegionCanonicalizer.
_NULL_REGION_CANONICALIZER = RegionCanonicalizer()


# ── Source-column contract (the h-dcn Ledenbestand shape the transform reads) ─────────

#: The raw source column names the transform maps into the FIXED base. The h-dcn Ledenbestand
#: (Google Sheet) columns → member-record fixed fields. Any column NOT named here (and not the
#: region/type columns below) is treated as a club/Motor detail and folded into ``overlay``.
FIXED_SOURCE_COLUMNS: Mapping[str, str] = {
    # source column (LOWER-CASED; the transform matches on `col.strip().lower()`)
    #                      -> dotted member-record fixed key (s5c canonical EN keys)
    #
    # NOTE (A.2, verified against the real Ledenbestand.json export 2026-09-22): the export
    # has NO `member_id` column — the internal `member_id` is MINTED as a uuid4 by the
    # transform (stable/opaque, decoupled from the human number). The human number is
    # `Lidnummer` -> `membership.member_number` (shaped to `M00001` at map time). Column
    # headers are capitalized / multi-word in the source; keys here are the lower-cased form.
    #
    # `naam` is a single display-name fallback (older exports); the current export carries the
    # split parts (`Voornaam`/`Achternaam`/...), which map directly below.
    "naam": "personal.last_name",
    "voornaam": "personal.first_name",
    "achternaam": "personal.last_name",
    "tussenvoegsel": "personal.name_infix",
    "initialen": "personal.initials",
    "geslacht": "personal.gender",
    "telefoon": "personal.phone",
    "telefoonnummer": "personal.phone",  # real export header
    "email": "personal.email",
    "e-mailadres": "personal.email",  # real export header
    # `adres` is a single address-line fallback; `straat` / `straat en huisnummer` are the
    # real headers. The s5c base splits address into street/postal_code/city/country (stored
    # under `personal`); map the primary line onto `personal.street`.
    "adres": "personal.street",
    "straat": "personal.street",
    "straat en huisnummer": "personal.street",  # real export header
    "postcode": "personal.postal_code",
    "woonplaats": "personal.city",
    "land": "personal.country",
    # NOTE: `birth_date` is NOT imported as a fixed field. h-dcn treats it as a CALCULATED
    # field (day+month only — "geboorte datum zonder jaar", a privacy choice), so `Geboorte
    # datum` / `Geboortedag` / `Geboortemaand` / `Geboortejaar` are NOT mapped here; they fold
    # into overlay (available if a later calculated field wants them). `personal.birth_date`
    # stays unset (it is optional in the fixed registry).
    "lidnummer": "membership.member_number",
    "lidmaatschapstype": "membership.membership_type",
    "soort lidmaatschap": "membership.membership_type",  # real export header
    # NOTE: `membership.status` and `membership.joined_date` are NOT simple column maps — they
    # are DERIVED after the column loop (see below):
    #   * status: the export has NO status column → default to "active" (all Ledenbestand rows
    #     are current members; a later refactor may derive left/lapsed from Afmelding/Beeindiging).
    #   * joined_date: date-part of `Datum ondertekening`, falling back to `<Aanmeldingsjaar>-01-01`.
    # NOTE: `einddatum`/`Afmelding`/`Beeindiging` (the h-dcn "left" dates) have no Fixed row in
    # the s5c classification table, so they fold into `overlay`. `Aanmeldingsjaar` is a
    # CALCULATED field (used here only as a joined_date fallback input, never stored as fixed).
}

#: Source columns for the DERIVED membership fields (status default + joined_date). Kept as
#: named constants so the derivation and the "unmapped column" fold agree on the exact headers.
_SIGNED_DATE_COLUMN = "datum ondertekening"      # ISO datetime → joined_date (date part)
_JOIN_YEAR_COLUMN = "aanmeldingsjaar"            # 4-digit year → joined_date fallback (<year>-01-01)
_DEFAULT_MEMBERSHIP_STATUS = "active"            # no status column in the export (A.2 decision)

#: The source column carrying the h-dcn region (normalized onto the ``overlay.region`` field).
_REGION_SOURCE_COLUMN = "regio"

#: The member FIELD the region normalizes onto. S5d D1/R3.4: scope is a PLAIN member field —
#: the retired ``scope_values`` bucket is gone. For h-dcn ``region`` is a TENANT-ADDED field, so
#: its storage bucket is ``overlay`` (dotted key ``overlay.region``). The value is a SCALAR
#: (a member is single-valued per scope field, R3.2), never a list.
_REGION_STORAGE_GROUP = "overlay"
_REGION_FIELD_KEY = "region"

#: h-dcn's live status vocabulary (Dutch) → the platform's closed MembershipStatus values.
#: h-dcn's export may carry either the Dutch or the canonical value; both map through.
_STATUS_MAP: Mapping[str, str] = {
    "aanvraag": "application",
    "in behandeling": "pending",
    "actief": "active",
    "geschorst": "suspended",
    "verlopen": "lapsed",
    "vertrokken": "left",
    # already-canonical values pass through unchanged
    "application": "application",
    "pending": "pending",
    "active": "active",
    "suspended": "suspended",
    "lapsed": "lapsed",
    "left": "left",
}


class RowTransformError(Exception):
    """Raised when a single source row cannot be mapped to a valid member record.

    Carries ``member_ref`` (a best-effort identifier for the offending row so it can be found
    in the source) and ``reasons`` (dotted-key → why). The runner collects these per row into
    the fidelity report rather than aborting the whole dry-run on the first bad row.
    """

    def __init__(self, member_ref: str, reasons: Mapping[str, str]):
        self.member_ref = member_ref
        self.reasons = dict(reasons)
        detail = "; ".join(f"{k}: {v}" for k, v in self.reasons.items())
        super().__init__(f"row {member_ref!r} could not be mapped: {detail}")


class RowSkipped(Exception):
    """Raised when a source row is intentionally NOT a member and is skipped (not an error).

    A member record's identity is its ``member_number``; a row with NONE (an empty export
    scaffold row, or a clubblad/magazine distribution entry for an organisation — a dealer,
    sister club, or sponsor with no ``Lidnummer``) is not a member. These belong in a future
    CONTACT table, not ``sam-members``. The runner counts them as SKIPPED — reported for
    transparency, but never blocking ``--apply`` the way a real mapping error does.

    Carries ``reason`` (why it was skipped) and ``label`` (a best-effort human identifier —
    e.g. the organisation name — for the report).
    """

    def __init__(self, reason: str, *, label: str = "<empty>"):
        self.reason = reason
        self.label = label
        super().__init__(f"row {label!r} skipped: {reason}")


# ── membership_type → catalog code mapping (C8; decoupled from the 4.2 seed) ──────────


class MembershipTypeMapper:
    """Maps an h-dcn source membership-type value to a Lidmaatschap Beheer catalog ``type_code``.

    h-dcn's live type vocabulary is free-form label text (e.g. "Erelid", "Donateur",
    "Sponsor"); the new model stores a catalog *code* the member references (C8). This mapper
    turns a label into a normalized code (lowercase, spaces→``_``, separators stripped) and,
    when given a set of ``known_codes``, VALIDATES that the produced code is one the catalog is
    expected to carry — surfacing a mismatch rather than inventing a code.

    It deliberately does NOT read or seed the catalog (that authoritative seed is task 4.2);
    the backfill only maps + validates the reference, keeping the two decoupled. When
    ``known_codes`` is ``None`` the mapper is permissive (any well-formed code is accepted),
    so a dry-run can run before the catalog exists and still report the codes it would write.
    """

    #: Explicit label→code overrides (applied before the generic normalization). Kept as DATA
    #: (h-dcn's known types) — not code branches — so extending it needs no logic change.
    DEFAULT_ALIASES: Mapping[str, str] = {
        "erelid": "erelid",
        "honorary member": "erelid",
        "donateur": "donateur",
        "donor": "donateur",
        "sponsor": "sponsor",
        "gewoon lid": "gewoon_lid",
        "regular member": "gewoon_lid",
        "lid": "gewoon_lid",
        # Family memberships — real h-dcn export types (gezins_lid: ~200, gezins_donateur: ~17).
        "gezins lid": "gezins_lid",
        "gezinslid": "gezins_lid",
        "family member": "gezins_lid",
        "gezins donateur": "gezins_donateur",
        "gezinsdonateur": "gezins_donateur",
        "family donor": "gezins_donateur",
        # A.4: `overig` ("Other") — an admin-gated catalog type (ONBOARDING §4 bucket 3).
        "overig": "overig",
        "other": "overig",
        # Real Ledenbestand spelling variants (census 2026-09-22) folded onto the 6+1 codes:
        "ere lid": "erelid",                              # "Ere lid" (spaced) → erelid
        "gezins donateur zonder motor": "gezins_donateur",  # "...zonder motor" is not a type axis
        "donateur zonder motor": "donateur",
        # A.4 decision (ONBOARDING §6.1): "Clubblad" on a NUMBERED member → `overig`.
        # Clubblad is a magazine subscription, not a real membership type; a member who
        # carries it is imported as type "Other". (Clubblad ORGANISATION rows have no member
        # number and are skipped entirely — they never reach the type mapper.)
        "clubblad": "overig",
    }

    def __init__(
        self,
        *,
        aliases: Optional[Mapping[str, str]] = None,
        known_codes: Optional[Iterable[str]] = None,
    ):
        self._aliases = {k.strip().lower(): v for k, v in (aliases or self.DEFAULT_ALIASES).items()}
        self._known_codes = set(known_codes) if known_codes is not None else None

    @staticmethod
    def normalize_code(value: str) -> str:
        """Normalize a raw label to a catalog-code shape: lowercase, spaces→``_``, trimmed."""
        code = value.strip().lower()
        code = re.sub(r"\s+", "_", code)
        # A code becomes a sort-key id segment (see table_design) — drop the separator char.
        code = code.replace("#", "")
        return code

    def to_code(self, raw_value: Any) -> str:
        """Return the catalog ``type_code`` for a raw h-dcn membership-type value.

        Raises :class:`ValueError` if the value is blank, or (when ``known_codes`` was given)
        if the mapped code is not one of the expected catalog codes — a loud mismatch rather
        than a silently-invented type.
        """
        if not isinstance(raw_value, str) or not raw_value.strip():
            raise ValueError("membership type is blank")
        alias = self._aliases.get(raw_value.strip().lower())
        code = alias if alias is not None else self.normalize_code(raw_value)
        if not code:
            raise ValueError(f"membership type {raw_value!r} normalizes to an empty code")
        if self._known_codes is not None and code not in self._known_codes:
            raise ValueError(
                f"membership type {raw_value!r} maps to code {code!r} which is not in the "
                f"expected catalog codes (seed via task 4.2, then re-run)"
            )
        return code


# ── The pure transform (storage-agnostic; the heart of the backfill) ──────────────────


def _clean(value: Any) -> Optional[str]:
    """Normalize a raw cell: strip strings, treat empty / whitespace as absent (``None``)."""
    if value is None:
        return None
    if isinstance(value, str):
        s = value.strip()
        return s or None
    return value  # non-string (already-typed) values pass through


#: Member-number format (A.2 / ONBOARDING §3): the human member number is a Fixed **string**,
#: prefix ``M`` + a zero-padded 5-digit sequence (``M00001``) so it sorts lexicographically
#: (``M00001`` < ``M00002`` < … < ``M00010``) — a bare integer would sort ``1, 10, 2``. The
#: tenant format pattern authored in ``members.field_overlay`` is ``^M\d{5}$``; the backfill
#: shapes the source ``Lidnummer`` to match it here.
_MEMBER_NUMBER_PREFIX = "M"
_MEMBER_NUMBER_WIDTH = 5
_DIGITS_RE = re.compile(r"\d+")


_ISO_DATE_PREFIX_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})")
_YEAR_RE = re.compile(r"^\s*(\d{4})\s*$")


def _skip_label(personal: Mapping[str, Any], overlay: Mapping[str, Any]) -> str:
    """A best-effort human identifier for a SKIPPED row (for the report).

    Prefers the name parts already mapped (last/first), else any overlay ``naam``-like value,
    else ``<empty>``. Purely cosmetic — used only in the skipped-rows report.
    """
    last = str(personal.get("last_name", "")).strip()
    first = str(personal.get("first_name", "")).strip()
    name = " ".join(p for p in (first, last) if p)
    return name or "<empty>"


def _iso_date_part(raw: Any) -> Optional[str]:
    """Extract the ``YYYY-MM-DD`` date part from a source date/datetime string, or None.

    The h-dcn export carries dates as ISO datetimes (e.g. ``2023-04-12T22:00:00.000Z``); the
    fixed registry wants a bare ISO calendar date. Takes the leading ``YYYY-MM-DD`` when present.
    """
    if raw is None:
        return None
    m = _ISO_DATE_PREFIX_RE.match(str(raw).strip())
    return m.group(1) if m else None


def _year_to_iso(raw: Any) -> Optional[str]:
    """Map a bare year (e.g. ``"2023"``) to ``<year>-01-01``, or None if not a 4-digit year."""
    if raw is None:
        return None
    m = _YEAR_RE.match(str(raw))
    return f"{m.group(1)}-01-01" if m else None


def _shape_member_number(raw: Any) -> Optional[str]:
    """Shape a raw source member number to the ``M00001`` form, or return None if unusable.

    Accepts an int, or a string that either already matches ``^M\\d{5}$`` (passed through) or
    contains a run of digits (extracted + zero-padded to width, prefixed with ``M``). A value
    with no digits yields ``None`` (the caller then records a missing-number reason).
    """
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    # Already in the canonical shape (any digit count) → normalize the zero-padding to width.
    if s[:1].upper() == _MEMBER_NUMBER_PREFIX and s[1:].isdigit():
        digits = s[1:]
    else:
        m = _DIGITS_RE.search(s)
        if not m:
            return None
        digits = m.group(0)
    return f"{_MEMBER_NUMBER_PREFIX}{int(digits):0{_MEMBER_NUMBER_WIDTH}d}"


def map_hdcn_row(
    raw_row: Mapping[str, Any],
    *,
    type_mapper: Optional[MembershipTypeMapper] = None,
    tenant_id: str = HDCN_TENANT_ID,
    region_canonicalizer: Optional["RegionCanonicalizer"] = None,
) -> dict[str, Any]:
    """Map ONE raw h-dcn member row to a member record for the new model (pure, no I/O).

    The produced record matches the design data model (S5d D1: NO ``scope_values`` bucket —
    scope is a plain member field)::

        { tenant_id, member_id,
          personal:   { first_name, last_name, name_infix, initials, gender, email, phone,
                        street, postal_code, city, country, birth_date },
          membership: { member_number, status, membership_type, joined_date },
          overlay:    { region: <canonical region>,     # h-dcn: the scope FIELD, a scalar
                        <club/Motor + unmapped detail>: <value>, ... } }

    Steps:
    - **Fixed base split** — columns named in :data:`FIXED_SOURCE_COLUMNS` land under
      ``personal`` / ``membership``; ``status`` is mapped from h-dcn's Dutch vocabulary to the
      closed platform enum; the source ``Lidnummer`` is shaped to the ``M00001``
      ``member_number`` string. The top-level ``member_id`` is MINTED as a uuid4 (the export
      has no member_id column; A.2/ONBOARDING §2).
    - **membership_type → catalog code** — the raw type value is mapped to a ``type_code``
      via ``type_mapper`` (C8; the catalog seed is task 4.2, kept decoupled).
    - **overlay.region (the scope field)** — the ``regio`` column is normalized to the
      dimension's canonical value via the shared ``scope_canon`` (S5d R9.2/D1) and stored as a
      SCALAR on the ``overlay.region`` field (h-dcn's ``region`` is a tenant-added overlay
      field). There is NO ``scope_values`` bucket — the member record has zero scope awareness.
      An absent region omits the field (reported by the runner; a scoped user never matches it).
    - **variable overlay** — every remaining, non-empty source column (club/Motor details)
      folds into ``overlay`` unchanged, so no source data is silently dropped (fidelity).
    - **validation** — the fixed fields are validated with ``validate_fixed_fields`` so a bad
      mapping raises loudly (surfaced per-row in the dry-run report), never a silent write.

    ``tenant_id`` defaults to the pilot ``"h-dcn"`` (the value the backfill stamps). Raises
    :class:`RowTransformError` if the row cannot produce a valid fixed record.
    """
    mapper = type_mapper or MembershipTypeMapper()

    personal: dict[str, Any] = {}
    membership: dict[str, Any] = {}
    overlay: dict[str, Any] = {}
    region_raw: Optional[str] = None
    signed_date_raw: Any = None   # `Datum ondertekening` → joined_date (primary)
    join_year_raw: Any = None     # `Aanmeldingsjaar` → joined_date fallback (calculated field)
    reasons: dict[str, str] = {}

    for column, value in raw_row.items():
        col = (column or "").strip()
        col_lower = col.lower()
        cleaned = _clean(value)

        if col_lower == _REGION_SOURCE_COLUMN:
            region_raw = cleaned if isinstance(cleaned, str) else None
            continue

        if col_lower == _SIGNED_DATE_COLUMN:
            signed_date_raw = cleaned
            continue
        if col_lower == _JOIN_YEAR_COLUMN:
            # Aanmeldingsjaar is a CALCULATED field — captured ONLY as a joined_date fallback
            # input; NOT stored as a fixed/overlay field.
            join_year_raw = cleaned
            continue

        dotted = FIXED_SOURCE_COLUMNS.get(col_lower)
        if dotted is None:
            # Unknown column → a club/Motor variable overlay field (kept verbatim).
            if cleaned is not None:
                overlay[col] = cleaned
            continue

        group, key = dotted.split(".", 1)
        target = personal if group == "personal" else membership

        if key == "member_number":
            # A.2: shape the source `Lidnummer` to the sortable `M00001` string. A source
            # value with no digits is unusable → recorded as a missing-number reason below.
            shaped = _shape_member_number(cleaned)
            if shaped is not None:
                target[key] = shaped
        elif key == "membership_type":
            if cleaned is None:
                reasons["membership.membership_type"] = "is required"
            else:
                try:
                    target[key] = mapper.to_code(cleaned)
                except ValueError as exc:
                    reasons["membership.membership_type"] = str(exc)
        elif cleaned is not None:
            # Fixed personal/membership fields reaching this branch are STRING-typed (dates
            # are handled elsewhere). The JSON export carries some as numbers (e.g. Postcode /
            # Telefoonnummer as ints), so coerce to a trimmed string to satisfy the string
            # validator — no data loss, just a type fix (A.2).
            target[key] = str(cleaned).strip() if not isinstance(cleaned, str) else cleaned

    # SKIP non-members: a row with no usable member number (Lidnummer) is NOT a member — an
    # empty export scaffold row, or a clubblad/magazine distribution entry for an organisation
    # (dealer / sister club / sponsor). These belong in a future CONTACT table, not
    # `sam-members`. Skipping is intentional and NON-blocking (RowSkipped, not an error), so
    # `--apply` is not choked by them. (A.2 decision: leave non-members out.)
    if not membership.get("member_number"):
        label = _skip_label(personal, overlay)
        raise RowSkipped("no member number (Lidnummer) — not a member", label=label)

    # A.2 DERIVED membership fields (no direct source column):
    #  * status — the export has no status column → default to "active" (A.2 decision; all
    #    Ledenbestand rows are current members). A later refactor may derive left/lapsed.
    membership.setdefault("status", _DEFAULT_MEMBERSHIP_STATUS)
    #  * joined_date — date-part of `Datum ondertekening`; if absent, `<Aanmeldingsjaar>-01-01`;
    #    if STILL absent (a numbered member with no signing date and no join year), default to
    #    today (sysdate) so a real member is never dropped for a missing join date (A.2 decision).
    #    Aanmeldingsjaar is a calculated field, used here only as a fallback INPUT.
    joined = (
        _iso_date_part(signed_date_raw)
        or _year_to_iso(join_year_raw)
        or _dt.date.today().isoformat()
    )
    membership["joined_date"] = joined

    # A.2: mint a STABLE internal id (uuid4) — the export carries no member_id, and the
    # internal id is intentionally decoupled from the human `member_number` (which may be
    # reformatted/renumbered without re-keying the record subtree). ONBOARDING §2.
    member_id = str(uuid.uuid4())

    member_ref = membership.get("member_number") or "<unknown>"

    # S5d D1/R3.4: the region is a PLAIN member field, not a `scope_values` bucket. h-dcn's
    # `region` is a tenant-added field → its storage bucket is `overlay`. Store the CANONICAL
    # value (normalized via the shared `scope_canon`, R9.2) as a SCALAR (single-valued per
    # scope field, R3.2). An absent region omits the field entirely (no empty placeholder).
    if region_raw:
        canon = region_canonicalizer or _NULL_REGION_CANONICALIZER
        overlay[_REGION_FIELD_KEY] = canon.canonical(region_raw)

    record: dict[str, Any] = {
        "tenant_id": tenant_id,
        "member_id": member_id,
        "personal": personal,
        "membership": membership,
        "overlay": overlay,
    }

    # Validate the FIXED half loudly so a bad mapping never becomes a silent write.
    try:
        validate_fixed_fields(record)
    except FieldValidationError as exc:
        reasons.update(exc.errors)

    if reasons:
        raise RowTransformError(str(member_ref), reasons)

    return record


# ── Source adapters (READ-ONLY; never modify the live source) ─────────────────────────


class HdcnSourceAdapter(Protocol):
    """A read-only source of raw h-dcn member rows.

    Implementations MUST be non-destructive: they only *read* the source (a Google-Sheet
    export, or the legacy ``Members`` table read-only) — they never write, update, or delete
    it (R5.2). ``rows()`` yields plain mappings (one per member) with the h-dcn source column
    names as keys, which :func:`map_hdcn_row` then transforms.
    """

    def rows(self) -> Iterable[Mapping[str, Any]]:
        ...

    def describe(self) -> str:
        """A short human description of the source (shown in the fidelity report header)."""
        ...


class IterableSourceAdapter:
    """An in-memory :class:`HdcnSourceAdapter` over a list of row mappings.

    The storage-agnostic default used by tests (and any caller that already holds the rows).
    Read-only by construction — it never mutates the rows it was handed.
    """

    def __init__(self, rows: Sequence[Mapping[str, Any]], *, description: str = "in-memory rows"):
        self._rows = [dict(r) for r in rows]
        self._description = description

    def rows(self) -> Iterable[Mapping[str, Any]]:
        for r in self._rows:
            yield dict(r)  # hand out copies — callers cannot mutate the source

    def describe(self) -> str:
        return f"{self._description} ({len(self._rows)} rows)"


class FileSourceAdapter:
    """A READ-ONLY :class:`HdcnSourceAdapter` over a CSV or JSON export file.

    A Google-Sheet export of the h-dcn Ledenbestand *is* a CSV (or a JSON dump), so this lets
    the dry-run run against an exported fixture with NO access to Google or DynamoDB. The file
    is opened for reading only and is never written back (non-destructive, R5.2).

    Format detection: ``.json`` → a JSON array of row objects (or ``{"rows": [...]}``);
    anything else → CSV with a header row (``csv.DictReader``). Pass ``fmt="csv"``/``"json"``
    to force a format.
    """

    def __init__(self, path: str, *, fmt: Optional[str] = None, encoding: str = "utf-8"):
        self._path = path
        self._encoding = encoding
        self._fmt = (fmt or self._infer_format(path)).lower()
        if self._fmt not in ("csv", "json"):
            raise ValueError(f"unsupported source format {self._fmt!r} (expected csv or json)")

    @staticmethod
    def _infer_format(path: str) -> str:
        return "json" if path.lower().endswith(".json") else "csv"

    def rows(self) -> Iterable[Mapping[str, Any]]:
        # Open for READ only ("r"). This adapter never opens the source for writing.
        with open(self._path, "r", encoding=self._encoding, newline="") as fh:
            if self._fmt == "json":
                yield from self._read_json(fh.read())
            else:
                yield from self._read_csv(fh)

    @staticmethod
    def _read_csv(fh: io.TextIOBase) -> Iterator[Mapping[str, Any]]:
        for row in csv.DictReader(fh):
            # DictReader keys are the header names; values are strings (or None for short rows).
            yield {k: v for k, v in row.items() if k is not None}

    @staticmethod
    def _read_json(text: str) -> Iterator[Mapping[str, Any]]:
        data = json.loads(text)
        if isinstance(data, Mapping) and "rows" in data:
            data = data["rows"]
        if not isinstance(data, list):
            raise ValueError("JSON source must be a list of row objects (or {\"rows\": [...]})")
        for row in data:
            if not isinstance(row, Mapping):
                raise ValueError("each JSON source row must be an object")
            yield dict(row)

    def describe(self) -> str:
        return f"{self._fmt.upper()} export file {os.path.basename(self._path)!r}"


class LegacyDynamoSourceAdapter:
    """READ-ONLY adapter over the legacy h-dcn ``Members`` DynamoDB table (documented STUB).

    Sketched here so the runner's source seam is complete, but intentionally NOT required to
    run or test the backfill: h-dcn's real member data lives in a Google Sheet (demo-only),
    and this adapter would only ever *read* the legacy table (a full ``scan``/``query``) —
    it performs **no** writes, updates, or deletes, so reading it is non-destructive (R5.2,
    aws-accounts guardrail: never destructive against a data table). A concrete implementation
    would reuse ``services.dynamodb_client.get_dynamodb_resource`` and page a read-only
    ``scan`` of the legacy table, mapping each legacy item's attributes to the source-column
    names in :data:`FIXED_SOURCE_COLUMNS`. It is left unbuilt on purpose (YAGNI for the pilot),
    and ``rows()`` raises so nobody accidentally relies on live legacy access.
    """

    def __init__(self, table_name: str, *, region: Optional[str] = None):
        self._table_name = table_name
        self._region = region

    def rows(self) -> Iterable[Mapping[str, Any]]:  # pragma: no cover - deliberate stub
        raise NotImplementedError(
            "LegacyDynamoSourceAdapter is a read-only stub (task 4.1): the pilot uses a "
            "Google-Sheet CSV/JSON export via FileSourceAdapter. A live read-only scan of the "
            "legacy Members table can be implemented here without ANY write to the source."
        )

    def describe(self) -> str:
        return f"legacy DynamoDB table {self._table_name!r} (READ-ONLY; stub)"


# ── Transform result + fidelity plan (what the runner renders / applies) ──────────────


@dataclass(frozen=True)
class TransformedRow:
    """One successfully transformed source row: the produced member record + a back-reference."""

    member_id: str
    member_number: str
    member_type_code: str
    region: tuple[str, ...]
    record: Mapping[str, Any]


@dataclass
class BackfillPlan:
    """The result of transforming a source, ready to render (dry-run) or apply.

    A **fidelity check** of the transform against the source: counts, the per-field mapping
    summary, per-row validation errors, sample transformed records, and the member numbers
    that would collide within the batch. In dry-run the runner renders this and writes
    NOTHING; only with ``--apply`` does it persist :attr:`transformed` via the repository.
    """

    tenant_id: str
    source_description: str
    source_row_count: int = 0
    transformed: list[TransformedRow] = field(default_factory=list)
    #: (member_ref, {dotted_key: reason}) for rows that failed to map — surfaced, never dropped.
    errors: list[tuple[str, Mapping[str, str]]] = field(default_factory=list)
    #: (label, reason) for rows intentionally SKIPPED as non-members (no member number — an
    #: empty scaffold row or a clubblad/organisation entry). Reported, NON-blocking for --apply.
    skipped: list[tuple[str, str]] = field(default_factory=list)
    #: member numbers appearing on more than one row in this batch (would-be uniqueness conflicts).
    duplicate_member_numbers: dict[str, list[str]] = field(default_factory=dict)
    #: rows whose region did not resolve to a scope value (reported, not fatal).
    rows_missing_region: list[str] = field(default_factory=list)

    @property
    def ok_count(self) -> int:
        return len(self.transformed)

    @property
    def error_count(self) -> int:
        return len(self.errors)

    @property
    def skipped_count(self) -> int:
        return len(self.skipped)

    def field_mapping_summary(self) -> dict[str, int]:
        """Count, across successful rows, how many carry each fixed dotted field + overlay keys.

        A quick fidelity signal: it shows the mapping actually populated the expected fields
        (e.g. every row has ``membership.member_number``) and how widely overlay/club fields
        appear.
        """
        counts: dict[str, int] = {}
        for t in self.transformed:
            rec = t.record
            for group in ("personal", "membership"):
                for key in (rec.get(group) or {}):
                    counts[f"{group}.{key}"] = counts.get(f"{group}.{key}", 0) + 1
            # S5d D1: the scope field (region) is a plain `overlay.region` field now — it is
            # counted by the overlay loop below (no separate `scope_values.region` count).
            for key in (rec.get("overlay") or {}):
                counts[f"overlay.{key}"] = counts.get(f"overlay.{key}", 0) + 1
        return counts


def build_backfill_plan(
    adapter: HdcnSourceAdapter,
    *,
    type_mapper: Optional[MembershipTypeMapper] = None,
    tenant_id: str = HDCN_TENANT_ID,
    region_canonicalizer: Optional["RegionCanonicalizer"] = None,
) -> BackfillPlan:
    """Read the source (read-only) + transform every row into a :class:`BackfillPlan`.

    Non-destructive: it only iterates the adapter's ``rows()`` (a read) and builds an in-memory
    plan — it never writes anything. Rows that fail to map are collected into
    :attr:`BackfillPlan.errors` (the dry-run reports them; the batch is not aborted). Member
    numbers that repeat within the batch are recorded as would-be uniqueness conflicts
    (Property 6) so ``--apply`` can be trusted to report rather than overwrite.
    """
    plan = BackfillPlan(tenant_id=tenant_id, source_description=adapter.describe())

    # PASS 1: transform every row into a candidate; collect member-numbers so duplicates can
    # be identified across the WHOLE batch (not just "already seen so far"). Skips/errors are
    # recorded here; the region-missing tally is deferred to pass 2 (only kept rows count).
    candidates: list[TransformedRow] = []
    number_owners: dict[str, list[str]] = {}

    for raw in adapter.rows():
        plan.source_row_count += 1
        try:
            record = map_hdcn_row(
                raw,
                type_mapper=type_mapper,
                tenant_id=tenant_id,
                region_canonicalizer=region_canonicalizer,
            )
        except RowSkipped as exc:
            plan.skipped.append((exc.label, exc.reason))
            continue
        except RowTransformError as exc:
            plan.errors.append((exc.member_ref, exc.reasons))
            continue

        number = record["membership"]["member_number"]
        region_value = record.get("overlay", {}).get(_REGION_FIELD_KEY)
        candidates.append(
            TransformedRow(
                member_id=record["member_id"],
                member_number=number,
                member_type_code=record["membership"]["membership_type"],
                region=(region_value,) if region_value else (),
                record=record,
            )
        )
        number_owners.setdefault(number, []).append(record["member_id"])

    plan.duplicate_member_numbers = {
        number: ids for number, ids in number_owners.items() if len(ids) > 1
    }

    # PASS 2: LEAVE DUPLICATES OUT (user decision, ONBOARDING §6.1). A member number reused in
    # the source is a data conflict (a recycled Lidnummer for a different person, or a true
    # duplicate entry). Rather than an arbitrary "first-wins", SKIP **every** occurrence of a
    # duplicated number — reported, non-blocking — so the data owner resolves the conflict in
    # the source (assign new numbers / merge / drop) and re-runs. Only uniquely-numbered rows
    # are written.
    for cand in candidates:
        if cand.member_number in plan.duplicate_member_numbers:
            plan.skipped.append(
                (
                    cand.member_number,
                    "duplicate member number in the batch — ALL occurrences left out; "
                    "resolve the source conflict then re-run",
                )
            )
            continue
        plan.transformed.append(cand)
        if not cand.region:
            plan.rows_missing_region.append(cand.member_id)

    return plan
