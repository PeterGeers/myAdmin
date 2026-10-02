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
import sys
import uuid
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from sam.members.domain.fixed_fields import (
    FieldValidationError,
    validate_fixed_fields,
)
from sam.members.domain.scope_canon import scope_canon

__all__ = [
    "DEFAULT_GOOGLE_CREDENTIALS_FILE",
    "DUPLICATE_HEADER_INDEX_SEP",
    "HDCN_TENANT_ID",
    "BackfillPlan",
    "ColumnShiftWarning",
    "DuplicateHeaderConflict",
    "FileSourceAdapter",
    "GoogleSheetsSourceAdapter",
    "HdcnSourceAdapter",
    "IterableSourceAdapter",
    "LegacyDynamoSourceAdapter",
    "MembershipTypeMapper",
    "RegionCanonicalizer",
    "RowSkipped",
    "RowTransformError",
    "TransformedRow",
    "build_backfill_plan",
    "build_position_tracked_row",
    "contract_source_columns",
    "detect_column_shift",
    "map_hdcn_row",
]

#: The pilot tenant the backfill stamps. This is the ONE legitimate place a tenant literal
#: lives (design constraint): the backfill's whole job is to stamp the pilot tenant onto the
#: migrated records. It must NOT become an ``if tenant == "h-dcn"`` branch in the generic core.
HDCN_TENANT_ID = "h-dcn"

#: Default filesystem PATH to the service-account JSON key the read-only Google Sheets adapter
#: authenticates with (R4.3). Defaults to the SHARED h-dcn key — ONE key both the h-dcn importer
#: and this SAM backfill use (the "HDCN Ledenbestand" Sheet is already shared with that service
#: account as Viewer, so no Google Console change is needed). The file is gitignored and may be
#: ABSENT on disk; the operator places it before the first live run, or overrides with
#: ``--credentials`` (D5/D6). Never a real credential in the repo — only this path.
DEFAULT_GOOGLE_CREDENTIALS_FILE = "/home/peter/projects/h-dcn/.googleCredentials.json"

#: The ONLY OAuth scope the adapter requests to READ sheet values (R4.2/R5.1) — read-only, so the
#: service account can never write/update/delete the source. Resolving a sheet by TITLE
#: (``spreadsheet_name``) additionally needs a read-only Drive scope (added in ``_load_credentials``
#: only for that path) — see :data:`_DRIVE_READONLY_SCOPE`.
_SHEETS_READONLY_SCOPE = "https://www.googleapis.com/auth/spreadsheets.readonly"

#: Read-only Drive scope, added ONLY when resolving a spreadsheet by its human title via a
#: read-only ``files.list`` (title → id). Never used for value reads. Read-only (R4.2/R5.1).
_DRIVE_READONLY_SCOPE = "https://www.googleapis.com/auth/drive.readonly"


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
        aliases: Mapping[str, str] | None = None,
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


# ── Duplicate-header position tracking (shared by every source adapter, R1.1/R1.2) ────

#: Separator between a repeated header and its column index in a position-tracked key
#: (``E-mailadres#34``). Chosen to match the s5m mapping-contract ``source_column`` form
#: (``<header>#<colindex>``, R0.1/R1.1) so an adapter's row keys line up with the CSV.
DUPLICATE_HEADER_INDEX_SEP = "#"

#: Matches a trailing ``#<digits>`` position-index suffix so the transform can strip it back
#: to the BASE header before consulting the mapping tables / dispositions (R1.3).
_INDEXED_HEADER_RE = re.compile(r"^(?P<base>.*)#(?P<index>\d+)$")


def build_position_tracked_row(
    headers: Sequence[Any],
    values: Sequence[Any],
) -> dict[str, Any]:
    """Build one ``{header: value}`` row that NEVER loses a column to a header collision (R1.1).

    The SHARED row-build helper used by every source adapter (``FileSourceAdapter`` reading the
    raw CSV header row, ``GoogleSheetsSourceAdapter._rows_from_matrix``, task 5) so file and
    sheet sources behave identically (R1.2). A plain ``dict(zip(headers, values))`` would let a
    repeated header's LAST occurrence silently clobber the earlier one (Python dict
    last-occurrence-wins) — precisely the bug that dropped ``peter@pgeer.nl`` when an empty
    duplicate ``E-mailadres`` at col 34 overwrote the populated col 12.

    Instead each REPEATED header is made unique by appending its 1-based COLUMN INDEX: the FIRST
    occurrence keeps the BARE header, later occurrences become ``<header>#<colindex>`` — e.g.
    ``E-mailadres`` (col 12) and ``E-mailadres#34`` (col 34). The index is the source column
    position (1-based, matching the ``<header>#<colindex>`` mapping-contract form, R0.1). The
    transform (:func:`map_hdcn_row`) strips the ``#<colindex>`` back to the base header (R1.3) so
    both feed the same target and coalesce first-non-empty.

    A blank-named column (``header`` empty/whitespace) is kept VERBATIM under its empty key here
    (the transform drops it later, R1.5) — its column index is still consumed so later headers
    keep their true position. Short value rows are tolerated (missing cells → ``""``); this
    helper does not pad — the adapters normalize row width before calling it.
    """
    row: dict[str, Any] = {}
    seen: dict[str, int] = {}
    for col_index, header in enumerate(headers, start=1):
        base = "" if header is None else str(header).strip()
        value = values[col_index - 1] if col_index - 1 < len(values) else ""
        occurrence = seen.get(base, 0) + 1
        seen[base] = occurrence
        # First occurrence keeps the bare header; a repeat is disambiguated by its column index.
        key = base if occurrence == 1 else f"{base}{DUPLICATE_HEADER_INDEX_SEP}{col_index}"
        row[key] = value
    return row


def _base_header(column: str) -> str:
    """Strip a trailing ``#<colindex>`` position suffix back to the BASE header (R1.3).

    ``E-mailadres#34`` → ``E-mailadres``; a bare header (or a header that merely CONTAINS a
    ``#`` without a trailing numeric index) is returned unchanged. Matching against the mapping
    tables / dispositions is always on this base so every position-tracked duplicate of a header
    resolves to the SAME target and coalesces (R1.3/R1.4).
    """
    m = _INDEXED_HEADER_RE.match(column)
    return m.group("base") if m else column


# ── Source-column contract: the SINGLE authored mapping is the CSV (R0.1/R0.2/D0) ─────
#
# s5m single-source-of-truth cleanup (R0.1/R0.4): the source→target mapping is authored in ONE
# place — ``scripts/aws/h-dcn/members_source_mapping.csv`` (parsed into a ``MappingContract`` by
# ``members_mapping_loader``). There is NO second hand-maintained Python dict that can drift from
# (or contradict) the CSV. The old module-level ``FIXED_SOURCE_COLUMNS`` / ``OVERLAY_SOURCE_
# COLUMNS`` dicts (and the source-column-name constants ``_SIGNED_DATE_COLUMN`` /
# ``_JOIN_YEAR_COLUMN`` / ``_REGION_SOURCE_COLUMN`` and the dead ``_STATUS_MAP`` /
# ``_REGION_STORAGE_GROUP``) were retired: their "which column feeds which target" knowledge now
# lives in the contract rows (the ``date``-ruled joined_date coalesce inputs, the ``region``-ruled
# source column, etc.). Only the genuinely-DERIVED logic below is code, and it sources any column
# NAMES from the loaded contract, never from a private copy.

#: Default ``membership.status`` when the source carries no status (the Ledenbestand has no status
#: column — A.2 decision): a genuinely-derived default, not source-column knowledge.
_DEFAULT_MEMBERSHIP_STATUS = "active"

#: joined_date DATE-valued source columns (BASE headers, lower-cased) in PRIORITY order. This is
#: the genuinely-DERIVED combination order for the ``membership.joined_date`` target, which the
#: contract declares via several ``coalesce`` inputs but which must be combined by an explicit
#: priority rather than by the columns' raw sheet position (``Tijdstempel`` is physically col 0
#: but is only the FALLBACK). Both inputs are parsed by :func:`_parse_source_date` (Dutch
#: day-first ``d-m-yyyy`` AND ISO). Order (user-confirmed): the signature date wins, then the
#: (widest-populated) member-since timestamp.
_JOINED_DATE_DATE_SOURCES = ("datum ondertekening", "tijdstempel")

#: joined_date bare-YEAR fallback source (BASE header, lower-cased): ``Aanmeldingsjaar`` → mapped
#: to ``<year>-01-01`` only when no date-valued input above parsed. Kept LAST in the derivation.
_JOINED_DATE_YEAR_SOURCE = "aanmeldingsjaar"

#: The member FIELD the region normalizes onto. S5d D1/R3.4: scope is a PLAIN member field —
#: the retired ``scope_values`` bucket is gone. For h-dcn ``region`` is a TENANT-ADDED field, so
#: its storage bucket is ``overlay`` (dotted key ``overlay.region``). The value is a SCALAR
#: (a member is single-valued per scope field, R3.2), never a list. This is the derived TARGET
#: key, not source-column knowledge — the SOURCE column for region is declared in the contract
#: (the row whose ``rule`` is ``region``).
_REGION_FIELD_KEY = "region"


def contract_source_columns(contract: Any) -> set[str]:
    """Return the set of BASE source headers (lower-cased) the loaded contract MAPS to a target.

    The single-source-of-truth replacement for the old ``FIXED_SOURCE_COLUMNS.keys()`` probe: it
    reads the loaded :class:`MappingContract` (task 2), so "which columns are recognized as
    mapped" can never drift from the authored CSV. Includes every FIXED (``personal.*`` /
    ``membership.*``) and OVERLAY (``overlay.*``, incl. the region column) source header. The
    disposition sets (calculated / excluded / additional_info) are deliberately EXCLUDED — a
    caller wanting the mapped-vs-unmapped split treats those as "not a mapped target".
    """
    return set(contract.fixed.keys()) | set(contract.overlay.keys())


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

    ONE intentional-skip rule raises this today, landing the row in the plan's ``skipped``
    bucket — counted as SKIPPED, never as an error, never transformed/written:

    - **Empty/spacer row** — a row with NO meaningful data (no populated cell — where a
      NO-VALID-EMAIL placeholder counts as empty and the blank-named column is ignored). A
      placeholder-only row (e.g. ``E-mailadres`` = "GEEN GELDIG EMAILADRES") is treated as empty
      and skipped SILENTLY, regardless of its (blank) ``SAM Code``.

    A row that HAS meaningful data is NOT skipped — even one with a blank ``SAM Code``: a missing
    authoritative member number on a real data row is a data-gap ERROR (RowTransformError,
    reported, not written), not a silent skip. So over-skipping cannot hide a real member.

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
        aliases: Mapping[str, str] | None = None,
        known_codes: Iterable[str] | None = None,
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


def _clean(value: Any) -> str | None:
    """Normalize a raw cell: strip strings, treat empty / whitespace as absent (``None``)."""
    if value is None:
        return None
    if isinstance(value, str):
        s = value.strip()
        return s or None
    return value  # non-string (already-typed) values pass through


#: The AUTHORITATIVE source column that supplies the human ``member_number`` VERBATIM (the
#: "SAM Code" identity change, user-approved). The real h-dcn Google Sheet now carries a new
#: FIRST column ``SAM Code`` holding the formatted number for every data row — Members
#: ``M<5 digits>`` (``M06599``), Donateurs ``D00001``++, Contacts ``C00001``++. This column is
#: HUMAN-OWNED and STABLE (survives a sheet re-sort), so the importer READS it verbatim (trimmed)
#: and NEVER regenerates it — replacing the old fragile derivation (M+Lidnummer / D-skip /
#: C_+Achternaam). Matched on its BASE header, case-insensitive.
_SAM_CODE_COLUMN = "sam code"

#: The ``member_number`` FORMAT the SAM Code must satisfy (mirrors the tenant format authored in
#: ``members_config.json`` → ``membership.field_overlay.member_number.format.regex``): a Member
#: ``M#####`` / Donateur ``D#####`` / Contact ``C#####`` — all a single letter + exactly 5 digits.
#: A present SAM Code that does NOT match is a data gap (RowTransformError), never silently kept.
#: Kept in sync with the config regex; the importer validates the code it reads against it here
#: (``validate_fixed_fields`` does NOT enforce the tenant member_number format — that is Parameter
#: config resolved elsewhere — so the transform validates the authoritative code itself).
_MEMBER_NUMBER_FORMAT_RE = re.compile(r"^(M\d{5}|D\d{5}|C\d{5})$")


_ISO_DATE_PREFIX_RE = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})(?:[T ].*)?$")
#: Dutch ``d-m-yyyy`` / ``dd-mm-yyyy`` (DAY-first), with an OPTIONAL trailing ` hh:mm[:ss]` time
#: part. Groups: day, month, year. Verified against the live h-dcn sheet: ``Datum ondertekening``
#: (``13-4-2023``, no time) and ``Tijdstempel`` (``4-5-2026 10:59:37`` — SOME carry a time).
_DUTCH_DATE_RE = re.compile(r"^(\d{1,2})-(\d{1,2})-(\d{4})(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?$")
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


def _valid_ymd(year: int, month: int, day: int) -> str | None:
    """Return a normalized ``YYYY-MM-DD`` string for a valid calendar date, else None.

    Uses :class:`datetime.date` so an impossible calendar day (e.g. ``31-2``, ``29-2`` in a
    non-leap year) is rejected as well as a plainly out-of-range month/day. Returning None keeps
    the caller's contract: an optional date field stays unset rather than raising or fabricating.
    """
    try:
        return _dt.date(year, month, day).isoformat()
    except ValueError:
        return None


def _parse_source_date(raw: Any) -> str | None:
    """Normalize a source date/datetime string to a bare ``YYYY-MM-DD``, or None.

    ONE code path used by BOTH ``joined_date`` and ``birth_date`` (and the overlay date fields)
    so their date handling can never drift. Accepts two shapes seen on the live h-dcn sheet, in
    ADDITION to the ISO form the OLD fixture uses:

    - **Dutch ``d-m-yyyy`` / ``dd-mm-yyyy``** — DAY-first (user-confirmed): ``4-5-2026`` is
      4 May 2026 (day=4, month=5). An OPTIONAL trailing ` hh:mm` / ` hh:mm:ss` time part
      (``Tijdstempel`` carries some) is ignored — only the date is kept. Verified real samples:
      ``13-4-2023`` → ``2023-04-13``, ``22-11-2025`` → ``2025-11-22``.
    - **ISO ``YYYY-MM-DD``** (optionally followed by ``T…`` / ` …` time, as in the fixture's
      ``2010-01-01T00:00:00.000Z``) → the leading calendar date.

    Both are validated as real calendar dates (month 1-12, day 1-31, no impossible days); an
    out-of-range or unparseable value returns None — the optional field stays unset, never
    raises, never fabricates a date.
    """
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    # ISO first (YYYY-MM-DD[...]): the four-digit YEAR leads, so it is unambiguous vs the Dutch
    # day-first form (which leads with a 1-2 digit day).
    m = _ISO_DATE_PREFIX_RE.match(s)
    if m:
        return _valid_ymd(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    # Dutch d-m-yyyy (day-first), optional trailing time.
    m = _DUTCH_DATE_RE.match(s)
    if m:
        return _valid_ymd(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    return None


#: Backwards-compatible alias. Historically the transform reduced an ISO datetime to its date
#: part via ``_iso_date_part``; that role is now the broader :func:`_parse_source_date` (Dutch
#: day-first ``d-m-yyyy`` AND ISO). The alias keeps any existing reference working and reads
#: correctly at every call site (both fixed and overlay date fields route through it).
_iso_date_part = _parse_source_date


def _year_to_iso(raw: Any) -> str | None:
    """Map a bare year (e.g. ``"2023"``) to ``<year>-01-01``, or None if not a 4-digit year."""
    if raw is None:
        return None
    m = _YEAR_RE.match(str(raw))
    return f"{m.group(1)}-01-01" if m else None


def _row_has_meaningful_data(raw_row: Mapping[str, Any]) -> bool:
    """True if a raw source row carries ANY meaningful (populated) cell (R7.2 empty-row test).

    Used to detect a truly-EMPTY row that must be SKIPPED (not counted as an error, not written).
    A cell is "meaningful" when, after normalization, it still holds a value:
    - the blank-NAMED column (empty/whitespace header) is IGNORED (it is a Google-Sheet export
      artifact, dropped by the transform anyway, R1.5);
    - an ``E-mailadres`` cell that is a NO-VALID-EMAIL placeholder (``_NO_VALID_EMAIL_INDICATORS``,
      e.g. "GEEN GELDIG EMAILADRES") normalizes to empty and so does NOT count as meaningful —
      a placeholder-only row is therefore empty and skipped silently;
    - every other cell counts as meaningful when it is non-blank after a plain strip.

    The header is matched on its BASE (position-tracking ``#<colindex>`` stripped) so a
    duplicate column is judged like its bare sibling.
    """
    for column, value in raw_row.items():
        base = _base_header((column or "").strip())
        if base == "":
            continue  # blank-named column is a dropped artifact — never "meaningful"
        cleaned = _clean(value)
        if cleaned is None:
            continue
        # An email placeholder normalizes to empty — it does not make the row meaningful.
        if base.lower() == "e-mailadres" and _normalize_email(cleaned) is None:
            continue
        return True
    return False


def _read_sam_code(raw_row: Mapping[str, Any]) -> str | None:
    """Read the authoritative ``SAM Code`` cell VERBATIM (trimmed), or None when blank/absent.

    The SAM Code identity change (user-approved): ``member_number`` is now READ from the sheet's
    ``SAM Code`` column (matched on its BASE header ``sam code``, case-insensitive — it is the
    first column) rather than DERIVED from ``Lidnummer``/``Achternaam``. A present code is used
    verbatim (trimmed); the caller validates it against :data:`_MEMBER_NUMBER_FORMAT_RE`. A blank
    / absent cell yields ``None`` (the caller decides: an empty row is skipped, a meaningful row
    with a blank code is a data-gap error). A position-tracked duplicate is matched on its base.
    """
    for column, value in raw_row.items():
        if _base_header((column or "").strip()).lower() == _SAM_CODE_COLUMN:
            cleaned = _clean(value)
            if cleaned is not None:
                return str(cleaned).strip()
    return None


# ── Per-rule value conversions (the mapping-contract `rule` strategies, R0.2/R0.3/D0b) ─

#: Gender normalization — PORTED (s5m R8.1) from h-dcn's proven importer
#: (``import_members_sheets.py`` v2.0 ``gender_mapping``), RETARGETED (R8.2) onto THIS tenant's
#: ``gender`` enum authored in ``members_config.json`` (``M``/``V``/``X``/``N`` — the four
#: choices on ``personal.gender``). Dutch ``Man``/``Vrouw`` (and the bare ``m``/``v``, plus the
#: English ``male``/``female``) → ``M``/``V``; ``anders``/``other`` → ``X`` ("Anders"); an
#: explicit "prefer not to say" → ``N``. Already-canonical ``M``/``V``/``X``/``N`` pass through
#: (matched case-folded). An UNRECOGNIZED value is kept VERBATIM (never silently forced to a
#: wrong code) so the fixed-field validation against the tenant ``gender`` choices surfaces it.
_GENDER_MAP: Mapping[str, str] = {
    # → M
    "man": "M",
    "m": "M",
    "male": "M",
    "manlijk": "M",
    "mannelijk": "M",
    "heer": "M",
    "dhr": "M",
    # → V
    "vrouw": "V",
    "v": "V",
    "f": "V",
    "female": "V",
    "vrouwelijk": "V",
    "mevrouw": "V",
    "mevr": "V",
    # → X ("Anders" / other)
    "x": "X",
    "anders": "X",
    "other": "X",
    "divers": "X",
    # → N ("Wil niet zeggen" / prefer not to say)
    "n": "N",
    "onbekend": "N",
    "unknown": "N",
    "wil niet zeggen": "N",
    "prefer not to say": "N",
    "zegt liever niet": "N",
}


def _normalize_gender(raw: Any) -> str | None:
    """Normalize a raw gender to the tenant enum (``M``/``V``/``X``/``N``), else keep verbatim."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    return _GENDER_MAP.get(s.lower(), s)


#: Magazine (``Clubblad``) → the ``magazine_pref`` enum ``Geen``/``Papier``/``Digitaal`` (R0.2).
#: PORTED (s5m R8.1) from h-dcn's ``Clubblad`` knowledge in ``import_members_sheets.py`` v2.0,
#: RETARGETED (R8.2) onto THIS tenant's ``magazine_pref`` choices in ``members_config.json``
#: (``Geen``/``Papier``/``Digitaal``). h-dcn's OLD Clubblad→membership-status rule
#: (Papier→"Sponsor" / Digitaal→"Club") is NOT copied — those were h-dcn Dutch STATUS strings
#: on the old table and are not a valid SAM ``membership_type``/``status`` in this catalog (D8);
#: only the PREFERENCE variant knowledge (which spellings mean paper vs digital vs none) is
#: reused. ``Papier``/``Digitaal`` map as-is (case/space-folded); anything meaning "none" (or
#: empty, or unrecognized) falls back to ``Geen`` (the catch-all fallback, R0.2).
_MAGAZINE_MAP: Mapping[str, str] = {
    # → Papier
    "papier": "Papier",
    "paper": "Papier",
    "print": "Papier",
    "gedrukt": "Papier",
    "op papier": "Papier",
    "papieren": "Papier",
    # → Digitaal
    "digitaal": "Digitaal",
    "digital": "Digitaal",
    "digitale": "Digitaal",
    "pdf": "Digitaal",
    "email": "Digitaal",
    "e-mail": "Digitaal",
    "online": "Digitaal",
    # → Geen (none / not wanted). Empty + unrecognized ALSO fall back to Geen (see below).
    "geen": "Geen",
    "none": "Geen",
    "nee": "Geen",
    "no": "Geen",
    "niet": "Geen",
    "n.v.t.": "Geen",
    "nvt": "Geen",
}


def _normalize_magazine(raw: Any) -> str:
    """Map a raw ``Clubblad`` value → ``magazine_pref`` enum; empty/unrecognized → ``Geen``."""
    if raw is None:
        return "Geen"
    s = str(raw).strip()
    if not s:
        return "Geen"
    return _MAGAZINE_MAP.get(s.lower(), "Geen")


#: Email "NO-VALID-EMAIL" indicators — PORTED (s5m R8.1) from h-dcn's importer: sheet cells that
#: are placeholders meaning "this member has no real email" rather than an actual address (the
#: sheet was hand-maintained, and operators typed these to mark a missing/absent address). Such
#: a value must be treated as EMPTY (the field left unset), NOT stored as if it were an address —
#: otherwise ``no@email.com`` etc. would look like a deliverable address. Matched case-folded on
#: the trimmed cell; a genuine address is never in this set. Kept as DATA (extensible), not code.
_NO_VALID_EMAIL_INDICATORS: frozenset[str] = frozenset(
    {
        "geen",
        "geen email",
        "geen e-mail",
        "geen emailadres",
        "geen e-mailadres",
        "geen mail",
        "geen geldig emailadres",
        "geen geldig e-mailadres",
        "onbekend",
        "n.v.t.",
        "nvt",
        "n/a",
        "na",
        "none",
        "no email",
        "no e-mail",
        "noemail",
        "no@email.com",
        "geen@email.com",
        "geen@geen.nl",
        "-",
        "--",
        ".",
        "x",
        "xxx",
    }
)


def _normalize_email(raw: Any) -> str | None:
    """Normalize a raw email cell; a NO-VALID-EMAIL placeholder (R8.1) is treated as empty.

    Returns the trimmed address, or ``None`` when the cell is blank OR is one of the
    :data:`_NO_VALID_EMAIL_INDICATORS` placeholders (so a fake "geen email" marker never lands
    on ``personal.email`` as if it were a real address). A genuine address passes through
    verbatim (trimmed) — this does NOT validate deliverability, only strips known placeholders.
    """
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    if s.lower() in _NO_VALID_EMAIL_INDICATORS:
        return None
    return s


# ── Column-shift detection (data-quality safeguard, ported R8.1) ──────────────────────

#: One detected COLUMN-SHIFT signal on a source row (R8.1) — a value that landed in a column it
#: does not belong in, indicating the row's cells are shifted (a hand-maintained-sheet hazard).
#: PORTED from h-dcn's importer, which detected a YEAR value sitting in ``Geslacht`` (gender) and
#: a GENDER value sitting in ``Regio`` (region). Purely a WARNING surfaced in the fidelity report
#: (like :class:`DuplicateHeaderConflict`) — it never blocks a row nor rewrites a value; the
#: operator inspects the flagged column and fixes the source. Carries the offending column (base
#: header), the suspicious value, and a short human reason.
@dataclass(frozen=True)
class ColumnShiftWarning:
    column: str
    value: str
    reason: str


#: A 4-digit year sitting where a gender is expected (``Geslacht``) — the classic shift signal.
_LOOKS_LIKE_YEAR_RE = re.compile(r"^(19|20)\d{2}$")
#: The known gender tokens (lower-cased) — a gender token sitting in ``Regio`` signals a shift.
_GENDER_TOKENS: frozenset[str] = frozenset({"m", "v", "man", "vrouw", "male", "female", "x"})


def detect_column_shift(raw_row: Mapping[str, Any]) -> list[ColumnShiftWarning]:
    """Detect column-shift signals on a source row (data-quality safeguard, R8.1 port).

    Returns a list of :class:`ColumnShiftWarning` (empty when the row looks well-aligned). Two
    signals ported from h-dcn's importer, matched on the BASE header (so a position-tracked
    duplicate is checked too):
    - a YEAR value (``19xx``/``20xx``) in ``Geslacht`` — a birth year shifted into the gender
      column;
    - a GENDER token (``M``/``V``/``Man``/``Vrouw``/…) in ``Regio`` — a gender shifted into the
      region column.
    It only READS the row (pure) — it neither mutates nor drops anything.
    """
    warnings: list[ColumnShiftWarning] = []
    for column, value in raw_row.items():
        base = _base_header((column or "").strip()).lower()
        s = "" if value is None else str(value).strip()
        if not s:
            continue
        if base == "geslacht" and _LOOKS_LIKE_YEAR_RE.match(s):
            warnings.append(
                ColumnShiftWarning(
                    column=(column or "").strip(),
                    value=s,
                    reason="a year-like value in the gender column (Geslacht) suggests the "
                    "row's columns are shifted",
                )
            )
        elif base == "regio" and s.lower() in _GENDER_TOKENS:
            warnings.append(
                ColumnShiftWarning(
                    column=(column or "").strip(),
                    value=s,
                    reason="a gender-like value in the region column (Regio) suggests the "
                    "row's columns are shifted",
                )
            )
    return warnings


#: A simple IBAN test for the ``iban_or_payment`` conditional split (R0.3, per the CSV note):
#: a value that (space-stripped) is >= 15 chars and starts with two letters is treated as an
#: IBAN. This is deliberately loose (a data-quality heuristic, not a mod-97 validation) — the
#: point is only to route a bank number to ``iban`` and free text to ``payment_method``.
_IBAN_MIN_LEN = 15
_IBAN_HEAD_RE = re.compile(r"^[A-Za-z]{2}")


def _looks_like_iban(value: str) -> bool:
    compact = re.sub(r"\s+", "", value)
    return len(compact) >= _IBAN_MIN_LEN and bool(_IBAN_HEAD_RE.match(compact))


def _split_iban_or_payment(raw: Any) -> tuple[str | None, str | None]:
    """Split one ``Bankrekeningnummer`` value into (iban, payment_method) (R0.3 conditional split).

    - a value passing :func:`_looks_like_iban` → ``iban=value`` (compacted) + ``payment_method``
      = ``"incasso"`` (the common case is thus pre-populated for most members);
    - a non-IBAN, non-empty value → ``payment_method`` = that raw text, ``iban`` left unset;
    - an empty value → both unset (``None``, ``None``).
    """
    if raw is None:
        return (None, None)
    s = str(raw).strip()
    if not s:
        return (None, None)
    if _looks_like_iban(s):
        return (re.sub(r"\s+", "", s), "incasso")
    return (None, s)


# ── The authored mapping contract (loaded once, cached) ───────────────────────────────

#: The parsed default mapping contract, lazily loaded + cached (the transform's default when a
#: caller passes no explicit ``contract``). Loading is deferred to first use because the loader
#: (``scripts/aws/h-dcn/members_mapping_loader.py``) is NOT on the normal import path — importing
#: ``hdcn_backfill`` in the SAM Lambda runtime must never require the onboarding scripts dir.
_DEFAULT_CONTRACT_CACHE: Any = None


def _load_default_contract() -> Any:
    """Load + cache the authored default :class:`MappingContract` (spec D0), lazily by path.

    The loader + CSV live under ``scripts/aws/h-dcn/`` (not a Python package), so this imports
    the module BY PATH (mirroring how the runner loads ``members_config_loader``) and caches the
    result. ``map_hdcn_row`` calls this only when its caller supplies no explicit ``contract`` —
    the runner (task 6) will pass the already-loaded contract, avoiding the re-load.
    """
    global _DEFAULT_CONTRACT_CACHE
    if _DEFAULT_CONTRACT_CACHE is None:
        import importlib.util

        _hdcn_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
            "scripts",
            "aws",
            "h-dcn",
        )
        _loader_path = os.path.join(_hdcn_dir, "members_mapping_loader.py")
        # The mapping loader imports its sibling ``members_config_loader`` as a top-level name for
        # the drift guard, so the onboarding scripts dir must be importable while we load it.
        if _hdcn_dir not in sys.path:
            sys.path.insert(0, _hdcn_dir)
        # Reuse an already-imported loader if present (e.g. the tests import it directly). Else
        # import it BY PATH and REGISTER it in ``sys.modules`` BEFORE ``exec_module`` — ``@dataclass``
        # resolves its module via ``sys.modules[cls.__module__]`` during class creation, so an
        # unregistered module makes that lookup return ``None`` (an ``AttributeError`` on load).
        _module = sys.modules.get("members_mapping_loader")
        if _module is None:
            _spec = importlib.util.spec_from_file_location("members_mapping_loader", _loader_path)
            _module = importlib.util.module_from_spec(_spec)
            sys.modules["members_mapping_loader"] = _module
            _spec.loader.exec_module(_module)  # type: ignore[union-attr]
        _DEFAULT_CONTRACT_CACHE = _module.load_mapping_contract()
    return _DEFAULT_CONTRACT_CACHE


#: One reported duplicate-header conflict (R1.6): two DIFFERENT non-empty values shared a base
#: header, the first-in-column-order was KEPT, and this is the losing column (its INDEXED name,
#: e.g. ``E-mailadres#34``) + the base header + the kept vs dropped values, so the fidelity
#: report can show the operator exactly which column lost and reconcile the source.
@dataclass(frozen=True)
class DuplicateHeaderConflict:
    base_header: str
    losing_column: str
    kept_value: str
    dropped_value: str


def map_hdcn_row(
    raw_row: Mapping[str, Any],
    *,
    type_mapper: MembershipTypeMapper | None = None,
    tenant_id: str = HDCN_TENANT_ID,
    region_canonicalizer: RegionCanonicalizer | None = None,
    conflicts: list[DuplicateHeaderConflict] | None = None,
    shift_warnings: list[ColumnShiftWarning] | None = None,
    contract: Any = None,
) -> dict[str, Any]:
    """Map ONE raw h-dcn member row to a member record for the new model (pure, no I/O).

    The produced record matches the design data model (S5d D1: NO ``scope_values`` bucket —
    scope is a plain member field)::

        { tenant_id, member_id,
          personal:   { first_name, last_name, name_infix, initials, gender, email, phone,
                        street, postal_code, city, country, birth_date },
          membership: { member_number, status, membership_type, joined_date },
          overlay:    { region: <canonical region>,     # h-dcn: the scope FIELD, a scalar
                        <canonical overlay key>: <value>, ..., additional_info: <concat> } }

    **Contract-driven (s5m Task 3, R0.3/D0).** The source→target mapping and every non-mapped
    column's disposition come from the loaded :class:`MappingContract` (task 2's
    ``members_mapping_loader.load_mapping_contract``) — NOT hardcoded dicts. Pass an explicit
    ``contract`` (the runner does, once per batch) or leave it ``None`` to lazily load + cache
    the authored default (``scripts/aws/h-dcn/members_source_mapping.csv``). Each column is
    resolved in this order (design D2b): **FIXED → OVERLAY → CALCULATED (skip) → EXCLUDED (skip)
    → additional_info** (anything mapped nowhere, kept, is concatenated into
    ``overlay.additional_info``).

    Per-``rule`` conversions applied to the coalesced source value (R0.2/R0.3):
    - ``single`` / ``coalesce`` — copy (string), first-non-empty across duplicate/ordered columns;
    - ``date`` — ISO datetime → bare ``YYYY-MM-DD`` (``birth_date`` optional, and the membership
      ``deregistration_date`` / ``termination_date`` overlay dates; absent/unparseable → unset);
    - ``member_number`` — READ VERBATIM (trimmed) from the authoritative ``SAM Code`` column
      (Members ``M#####`` / Donateurs ``D#####`` / Contacts ``C#####``); validated against the
      format regex. A meaningful row with a blank/malformed ``SAM Code`` is a data-gap error
      (reported, not written); an empty/spacer row is skipped. It is NEVER derived/regenerated;
    - ``membership_type`` — free text → catalog ``type_code`` (via ``type_mapper``, C8);
    - ``region`` — canonicalized onto the tenant region value set (a scalar ``overlay.region``);
    - ``gender`` — Dutch ``Man``/``Vrouw`` (and ``m``/``v``) → tenant enum ``M``/``V``;
    - ``magazine`` — ``Clubblad`` → ``magazine_pref`` (``Geen``/``Papier``/``Digitaal``, fallback
      ``Geen``);
    - ``iban_or_payment`` — one ``Bankrekeningnummer`` → ``overlay.iban`` + ``overlay.
      payment_method`` (valid IBAN → iban + ``incasso``; non-IBAN text → payment_method=text).

    ``tenant_id`` defaults to the pilot ``"h-dcn"`` (the value the backfill stamps). Raises
    :class:`RowTransformError` if the row cannot produce a valid fixed record.

    **Duplicate-header safety (R1.3/R1.4/R1.6).** The adapters hand this transform a
    collision-free row where a repeated source header has been position-tracked to
    ``<header>#<colindex>`` (:func:`build_position_tracked_row`). Here each column key is first
    stripped back to its BASE header (:func:`_base_header`) before consulting the contract, so
    every column sharing a base feeds the SAME target and is combined by first-non-empty
    COALESCE: the first non-empty value in column order wins; a later empty NEVER overwrites it.
    Two DIFFERENT non-empty values sharing a base are a genuine conflict — the first is kept and
    the loser is recorded (by its INDEXED column name) into the optional ``conflicts`` list for
    the fidelity report (R1.6). A blank-named column is still dropped (R1.5).

    **Data-quality safeguards (R8.1, ported from h-dcn's importer).** ``personal.email`` cells
    that are NO-VALID-EMAIL placeholders (``geen email``, ``n.v.t.``, …) are treated as EMPTY so
    a fake marker never wins the coalesce nor lands as a deliverable address. If a
    ``shift_warnings`` list is supplied, column-shift signals (a year in ``Geslacht``, a gender
    token in ``Regio``) are appended to it for the report — a warning only; nothing is blocked
    or rewritten.
    """
    mapper = type_mapper or MembershipTypeMapper()
    contract = contract if contract is not None else _load_default_contract()

    # ── SAM Code identity + empty-row skip ─────────────────────────────────────────────
    # The authoritative human ``member_number`` is READ from the ``SAM Code`` column verbatim
    # (user-approved identity change) — no longer DERIVED from Lidnummer/Achternaam. Read it up
    # front (on its BASE header, so a position-tracked duplicate is matched like its bare sibling)
    # to drive both the empty-row skip and the member_number below.
    sam_code = _read_sam_code(raw_row)

    # Empty/spacer row: NO meaningful data (no populated cell — a NO-VALID-EMAIL placeholder and
    # the blank-named column count as empty). Skipped SILENTLY (RowSkipped) regardless of SAM
    # Code — never an error, never written. A meaningful row with a blank SAM Code is NOT skipped
    # here; it becomes a data-gap error below.
    if not _row_has_meaningful_data(raw_row):
        raise RowSkipped("empty row (no meaningful data)", label="<empty>")

    personal: dict[str, Any] = {}
    membership: dict[str, Any] = {}
    overlay: dict[str, Any] = {}
    reasons: dict[str, str] = {}
    conflict_out = conflicts if conflicts is not None else []

    # Column-shift detection (R8.1, data-quality safeguard): flag year-in-Geslacht /
    # gender-in-Regio into the optional ``shift_warnings`` list for the fidelity report. Never
    # blocks the row nor rewrites a value — the operator inspects the flagged source column.
    if shift_warnings is not None:
        shift_warnings.extend(detect_column_shift(raw_row))

    # First-non-empty COALESCE bookkeeping (R1.3/R1.4): a logical slot is "filled" by the FIRST
    # column (in row order) that carries a non-empty value for it. Later columns sharing the same
    # base header either agree (no-op) or conflict (recorded, first-in-order kept). Keyed by a
    # stable slot id (the dotted target, "overlay:<key>", "additional_info:<base>", …); carries
    # the kept RAW value + the INDEXED column that supplied it, so a later conflict can name the
    # loser. ``slot_raw`` holds the accepted raw value so the rule conversion runs AFTER the loop
    # (once every column sharing a base has been seen — a blank duplicate can never mask a
    # populated sibling, R1.4).
    filled: dict[str, tuple[str, str]] = {}
    slot_raw: dict[str, Any] = {}
    #: Additional-info accumulator: ordered (label, value) pairs collected in source-column order
    #: and joined into ``overlay.additional_info`` after the loop (R2.7).
    additional: list[tuple[str, str]] = []
    #: joined_date source values collected PER source base header (lower-cased) — NOT collapsed
    #: into the one column-order coalesce slot. joined_date has several contract inputs
    #: (``Datum ondertekening`` / ``Tijdstempel`` / ``Aanmeldingsjaar``) that must be combined by
    #: an EXPLICIT PRIORITY order (below), not by their raw sheet-column order (``Tijdstempel`` is
    #: col 0, so a plain first-non-empty-in-column-order coalesce would wrongly let it beat the
    #: authoritative ``Datum ondertekening`` at col 30). First non-empty per base header is kept.
    joined_date_by_source: dict[str, str] = {}

    def _coalesce(slot: str, indexed_column: str, base: str, new_value: Any) -> bool:
        """Return True if ``slot`` should accept ``new_value`` now (first non-empty wins).

        Records a :class:`DuplicateHeaderConflict` (and returns False) when the slot is already
        filled by a DIFFERENT non-empty value from an earlier column (R1.6). A later empty value
        never reaches here (callers guard on ``cleaned is not None``), so it can never overwrite.
        """
        new_str = str(new_value).strip() if not isinstance(new_value, str) else new_value.strip()
        prior = filled.get(slot)
        if prior is None:
            filled[slot] = (new_str, indexed_column)
            return True
        kept_value, _kept_col = prior
        if kept_value != new_str:
            conflict_out.append(
                DuplicateHeaderConflict(
                    base_header=base,
                    losing_column=indexed_column,
                    kept_value=kept_value,
                    dropped_value=new_str,
                )
            )
        return False  # a genuine duplicate (equal or conflicting) — first-in-order already kept

    # PASS 1 (in column order): coalesce each source column onto its contract slot. The rule
    # CONVERSION is deferred to pass 2 so a blank duplicate can never mask a populated sibling.
    for column, value in raw_row.items():
        indexed_column = (column or "").strip()
        # R1.3: match on the BASE header — strip a position-tracking `#<colindex>` suffix so a
        # duplicated header resolves to the SAME target as its bare sibling and coalesces.
        base = _base_header(indexed_column)
        col_lower = base.lower()
        cleaned = _clean(value)

        # R1.5: a blank-named source column is dropped (DynamoDB rejects an empty attribute
        # name). Its index was already consumed by the row-builder; nothing to store.
        if base == "":
            continue

        fixed_map = contract.fixed.get(col_lower)
        overlay_map = contract.overlay.get(col_lower)

        # FIXED (personal.*/membership.*) — coalesce the RAW value onto the dotted-key slot.
        if fixed_map is not None:
            slot = fixed_map.target
            # joined_date: DON'T fold its several inputs into the one column-order slot. Keep
            # each source column's first-non-empty value under its BASE header so PASS 2 can
            # combine them by an explicit PRIORITY order (Datum ondertekening → Tijdstempel →
            # Aanmeldingsjaar), independent of the columns' physical sheet order (R: joined_date
            # fallback). A position-tracked duplicate of the SAME source column still coalesces
            # (first non-empty per base header wins).
            if slot == "membership.joined_date":
                if cleaned is not None and col_lower not in joined_date_by_source:
                    joined_date_by_source[col_lower] = (
                        cleaned if isinstance(cleaned, str) else str(cleaned).strip()
                    )
                continue
            # EMAIL (R8.1): strip a NO-VALID-EMAIL placeholder to empty DURING coalesce, so a
            # fake "geen email" marker in an earlier column never wins over a real address in a
            # later duplicate — and never lands on personal.email as if it were deliverable.
            if slot == "personal.email":
                cleaned = _normalize_email(cleaned)
            if cleaned is not None and _coalesce(slot, indexed_column, base, cleaned):
                slot_raw[slot] = cleaned
            continue

        # OVERLAY (canonical overlay.* key(s)) — a `single`/`coalesce` row names one target; the
        # `iban_or_payment` conditional split names two. Coalesce the RAW source value onto a
        # slot keyed by the source base header (both targets share the one source value).
        if overlay_map is not None:
            slot = f"overlay-src:{col_lower}"
            if cleaned is not None and _coalesce(slot, indexed_column, base, cleaned):
                slot_raw[slot] = (overlay_map, cleaned)
            continue

        # CALCULATED — the value is DERIVED by a calculated field, NOT stored (R2.2/R2.6).
        if col_lower in contract.calculated:
            continue

        # EXCLUDED — deliberately dropped, unfit / (near-)duplicate (R2.6).
        if col_lower in contract.excluded:
            continue

        # additional_info (declared, R2.7) OR any unmapped-but-kept column — concatenate into
        # overlay.additional_info as `Label: value` (source header as the label). Coalesce so a
        # position-tracked duplicate does not double-count; a genuine conflict is reported.
        if cleaned is not None and _coalesce(
            f"additional_info:{col_lower}", indexed_column, base, cleaned
        ):
            additional.append((indexed_column, str(cleaned).strip()))

    # PASS 2: convert each coalesced raw value by its declared rule and write the target.

    # ── FIXED targets ────────────────────────────────────────────────────────────────
    for slot, raw in slot_raw.items():
        fmap = None
        # Only fixed slots are dotted keys present in the contract's fixed map (by target).
        for m in contract.fixed.values():
            if m.target == slot:
                fmap = m
                break
        if fmap is None:
            continue  # an overlay slot — handled below
        group, key = slot.split(".", 1)
        target = personal if group == "personal" else membership
        rule = fmap.rule

        if key == "member_number":
            # Handled after the loop from the authoritative ``SAM Code`` (read verbatim) — the
            # raw value coalesced onto this slot is NOT copied as a plain string here.
            continue
        if key == "membership_type":
            try:
                target[key] = mapper.to_code(raw)
            except ValueError as exc:
                reasons[slot] = str(exc)
            continue
        if rule == "date":
            # birth_date / joined_date etc. — reduce an ISO datetime to a bare YYYY-MM-DD. An
            # unparseable value simply leaves the (optional) field unset (R2.1/R3.3). joined_date
            # additionally gets a year/today fallback below.
            iso = _iso_date_part(raw)
            if iso is not None:
                target[key] = iso
            continue
        if rule == "gender":
            g = _normalize_gender(raw)
            if g is not None:
                target[key] = g
            continue
        # single / coalesce string copy. The JSON export carries some fixed fields as numbers
        # (Postcode / Telefoonnummer as ints), so coerce to a trimmed string for the validator.
        target[key] = str(raw).strip() if not isinstance(raw, str) else raw

    # joined_date — derived from its several contract inputs by an EXPLICIT PRIORITY order, NOT
    # the columns' raw sheet order. Each input's value was collected per base header in PASS 1.
    #   1. Datum ondertekening (the signature date — authoritative) parsed as a date;
    #   2. else Tijdstempel (the member-since timestamp — the widest-populated column, 1215/1242)
    #      parsed as a date — the fallback added so a member with no signature date but a
    #      timestamp gets a REAL join date instead of today;
    #   3. else Aanmeldingsjaar (a bare registration year) → <year>-01-01;
    #   4. else default to today so a real member is never dropped for a missing join date
    #      (A.2 decision).
    # Both date inputs go through the SAME date parser (Dutch d-m-yyyy AND ISO) — the fix that
    # stops every real Dutch date falling through to today.
    joined_date: str | None = None
    for _src in _JOINED_DATE_DATE_SOURCES:  # date-valued inputs, in priority order
        _val = joined_date_by_source.get(_src)
        if _val is not None:
            joined_date = _parse_source_date(_val)
            if joined_date is not None:
                break
    if joined_date is None:  # year fallback (Aanmeldingsjaar → <year>-01-01)
        _year_val = joined_date_by_source.get(_JOINED_DATE_YEAR_SOURCE)
        if _year_val is not None:
            joined_date = _year_to_iso(_year_val)
    membership["joined_date"] = joined_date or _dt.date.today().isoformat()

    # ── OVERLAY targets (canonical keys) ───────────────────────────────────────────────
    region_raw: str | None = None
    for slot, payload in slot_raw.items():
        if not slot.startswith("overlay-src:"):
            continue
        overlay_map, raw = payload
        rule = overlay_map.rule

        if rule == "region":
            # Deferred: canonicalized after the loop (needs the injected canonicalizer). Stored
            # on the plain `overlay.region` field as a SCALAR (S5d D1 — no scope_values bucket).
            if isinstance(raw, str):
                region_raw = raw
            continue
        if rule == "iban_or_payment":
            iban, payment = _split_iban_or_payment(raw)
            if iban is not None:
                overlay["iban"] = iban
            if payment is not None:
                overlay["payment_method"] = payment
            continue
        if rule == "magazine":
            overlay[overlay_map.targets[0]] = _normalize_magazine(raw)
            continue
        if rule == "date":
            # Filterable overlay date fields (deregistration_date / termination_date): stored
            # only when the source parses to a date, else left unset (R2.3).
            iso = _iso_date_part(raw)
            if iso is not None:
                overlay[overlay_map.targets[0]] = iso
            continue
        # single / coalesce — copy onto the canonical overlay key (string).
        overlay[overlay_map.targets[0]] = str(raw).strip() if not isinstance(raw, str) else raw

    # membership_type is a REQUIRED fixed field. Flag it missing only if NO column supplied a
    # value and no code was mapped (a blank duplicate never masks a populated sibling, R1.4).
    if (
        "membership_type" not in membership
        and "membership.membership_type" not in reasons
        and "membership.membership_type" not in slot_raw
    ):
        reasons["membership.membership_type"] = "is required"

    # ── member_number — READ from the authoritative ``SAM Code`` (identity change) ──────
    # The human number is READ verbatim from the ``SAM Code`` column (Members ``M#####`` /
    # Donateurs ``D#####`` / Contacts ``C#####``), NOT derived from Lidnummer/Achternaam. This
    # row already passed the empty-row test above, so it IS a meaningful data row:
    #   - a present, non-blank SAM Code that MATCHES the format → used verbatim as member_number;
    #   - a present SAM Code that does NOT match the format → a data-gap error (reported, not
    #     written) — the authoritative code is malformed and must be fixed at source;
    #   - a BLANK/absent SAM Code on a meaningful row → a data-gap error (reported, not written):
    #     a missing code is a real gap, NOT something to silently derive around (user-approved).
    if sam_code is None:
        reasons["membership.member_number"] = (
            "meaningful row has a blank 'SAM Code' — the authoritative member number is missing "
            "(fix the source; the importer never derives it)"
        )
    elif not _MEMBER_NUMBER_FORMAT_RE.match(sam_code):
        reasons["membership.member_number"] = (
            f"'SAM Code' {sam_code!r} does not match the member-number format "
            f"{_MEMBER_NUMBER_FORMAT_RE.pattern!r} (expected M#####/D#####/C#####)"
        )
    else:
        membership["member_number"] = sam_code

    # A.2 DERIVED: status — the export has no status column → default "active".
    membership.setdefault("status", _DEFAULT_MEMBERSHIP_STATUS)

    # A.2: mint a STABLE internal id (uuid4) — the export carries no member_id, and the internal
    # id is intentionally decoupled from the human `member_number`. ONBOARDING §2.
    member_id = str(uuid.uuid4())
    # Best-effort ref for the fidelity report: the member_number if valid, else the raw (possibly
    # blank/malformed) SAM Code, else a name — so a data-gap row can still be found in the source.
    member_ref = (
        membership.get("member_number")
        or sam_code
        or _skip_label(personal, overlay)
    )

    # region (deferred canonicalization): store the CANONICAL value as a SCALAR on overlay.region
    # (S5d D1/R3.4). An absent region omits the field entirely (no empty placeholder).
    if region_raw:
        canon = region_canonicalizer or _NULL_REGION_CANONICALIZER
        overlay[_REGION_FIELD_KEY] = canon.canonical(region_raw)

    # additional_info (R2.7): concatenate the kept leftovers as `Label: value` pairs in stable
    # source-column order, ` | ` delimiter, only non-empty cells. Unset if nothing contributed.
    info = " | ".join(f"{label}: {val}" for label, val in additional if val)
    if info:
        overlay["additional_info"] = info

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
    anything else → CSV. Pass ``fmt="csv"``/``"json"`` to force a format.

    **Duplicate-header safety (R1.1/R1.2).** The CSV path reads the RAW header row itself (via
    ``csv.reader``) and builds each row with the SHARED :func:`build_position_tracked_row` helper —
    NOT ``csv.DictReader``, which silently collapses a repeated header to its last occurrence. A
    duplicate header therefore becomes a distinct ``<header>#<colindex>`` key, exactly as
    :meth:`GoogleSheetsSourceAdapter._rows_from_matrix` does, so file and sheet sources hand the
    transform identical, collision-free rows.
    """

    def __init__(self, path: str, *, fmt: str | None = None, encoding: str = "utf-8"):
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
        # Read the RAW header row ourselves (NOT ``csv.DictReader``, which builds a plain dict
        # keyed by header and so SILENTLY COLLAPSES a repeated header to its last occurrence —
        # exactly the bug that dropped ``peter@pgeer.nl`` when an empty duplicate ``E-mailadres``
        # clobbered the populated one). Instead we position-track every column with the SHARED
        # ``build_position_tracked_row`` helper so a duplicate header becomes ``<header>#<colindex>``
        # and file + sheet sources behave identically (R1.1/R1.2).
        reader = csv.reader(fh)
        try:
            headers = next(reader)
        except StopIteration:
            return  # empty file → no rows
        for values in reader:
            yield build_position_tracked_row(headers, values)

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


class GoogleSheetsSourceAdapter:
    """A READ-ONLY :class:`HdcnSourceAdapter` reading the live "HDCN Ledenbestand" Sheet DIRECTLY.

    Reads the Sheet via the Google Sheets API and yields the SAME ``{header: value}`` row shape
    as :class:`FileSourceAdapter`, so :func:`map_hdcn_row` is source-agnostic (R4.1). It is
    duck-typed against the :class:`HdcnSourceAdapter` Protocol (``rows()`` / ``describe()``) — no
    base class.

    **READ-ONLY (R4.2/R5.1).** Authenticates a service account with ONLY the
    :data:`_SHEETS_READONLY_SCOPE` (``spreadsheets.readonly``), and calls ONLY
    ``spreadsheets.values.get``. Resolving a sheet by TITLE (``spreadsheet_name``) additionally
    requests the read-only Drive scope (:data:`_DRIVE_READONLY_SCOPE`) for a single ``files.list``.
    It NEVER writes, updates, or deletes the source — the live Sheet stays h-dcn's system of record.

    **Credentials (R4.3).** Reuses the EXISTING h-dcn service account (the Sheet is already shared
    with it as Viewer). ``credentials_file`` defaults to the shared key
    :data:`DEFAULT_GOOGLE_CREDENTIALS_FILE` (overridable via the runner's ``--credentials``). A
    missing/invalid key file fails FAST with actionable setup guidance
    (:meth:`_load_credentials` → :class:`FileNotFoundError`).

    **Lazy imports (R4.4).** EVERY ``from google...`` / ``from googleapiclient...`` import lives
    INSIDE the methods, never at module top — so ``import hdcn_backfill`` in the SAM Lambda runtime
    (whose layer ships no Google libs) never fails. Mirrors ``backend/src/services/
    google_oauth_service.py``.

    Construction requires an id OR a name (not both required, at least one). ``worksheet`` is the
    tab name (becomes the A1 range prefix ``'<tab>'!A1:ZZ``); ``cell_range`` overrides the derived
    range entirely.
    """

    #: The A1 column span read when no explicit ``cell_range`` is given — a generous width so a
    #: 49-column sheet (with duplicates + a trailing blank) is fully captured. ``_rows_from_matrix``
    #: trims to the header row's real width.
    _DEFAULT_A1_SPAN = "A1:ZZ"

    def __init__(
        self,
        *,
        spreadsheet_id: str | None = None,
        spreadsheet_name: str | None = None,
        worksheet: str | None = None,
        credentials_file: str = DEFAULT_GOOGLE_CREDENTIALS_FILE,
        cell_range: str | None = None,
    ):
        if not (spreadsheet_id or spreadsheet_name):
            raise ValueError(
                "GoogleSheetsSourceAdapter needs a spreadsheet_id or a spreadsheet_name "
                "(pass --sheet-id or --sheet-name)"
            )
        self._spreadsheet_id = spreadsheet_id.strip() if spreadsheet_id else None
        self._spreadsheet_name = spreadsheet_name.strip() if spreadsheet_name else None
        self._worksheet = worksheet.strip() if worksheet else None
        self._credentials_file = credentials_file
        self._cell_range = cell_range

    # ── Auth (lazy, read-only) ─────────────────────────────────────────────────────────

    def _load_credentials(self, *, include_drive: bool = False):
        """Load the service-account credentials, read-only scopes (R4.2/R4.3). LAZY import.

        Fails FAST with an actionable :class:`FileNotFoundError` if the key file is missing, is
        not valid JSON, or is a placeholder template (mirroring h-dcn's ``test_google_connection``
        checks: file exists, valid JSON, not the template). ``include_drive`` adds the read-only
        Drive scope needed ONLY to resolve a spreadsheet by title.
        """
        path = self._credentials_file
        if not os.path.isfile(path):
            raise FileNotFoundError(
                f"Google service-account key not found at {path!r}. Place the EXISTING h-dcn "
                f"service-account JSON key there (re-download from Google Cloud if absent; the "
                f"'HDCN Ledenbestand' Sheet is already shared with that account as Viewer), or "
                f"pass --credentials <path>."
            )
        try:
            with open(path, "r", encoding="utf-8") as fh:
                info = json.load(fh)
        except (OSError, ValueError) as exc:
            raise FileNotFoundError(
                f"Google service-account key at {path!r} is not valid JSON ({exc}). Re-download "
                f"the service-account key from Google Cloud, or pass --credentials <path>."
            ) from exc
        if not isinstance(info, Mapping) or info.get("type") != "service_account":
            raise FileNotFoundError(
                f"Google service-account key at {path!r} is not a service-account key (missing "
                f'"type": "service_account" — it may be a placeholder template or an OAuth client '
                f"secret). Re-download the service-account key from Google Cloud."
            )

        # LAZY import (R4.4) — never at module top, so the SAM Lambda runtime (no Google libs) is safe.
        from google.oauth2 import service_account

        scopes = [_SHEETS_READONLY_SCOPE]
        if include_drive:
            scopes.append(_DRIVE_READONLY_SCOPE)
        return service_account.Credentials.from_service_account_file(path, scopes=scopes)

    def _resolve_spreadsheet_id(self) -> str:
        """Return the spreadsheet id — use ``spreadsheet_id`` directly, else resolve by TITLE.

        Title resolution is a single READ-ONLY Drive ``files.list`` for a spreadsheet named
        exactly ``spreadsheet_name``; it fails clearly if 0 or >1 sheets match. LAZY imports.
        """
        if self._spreadsheet_id:
            return self._spreadsheet_id

        creds = self._load_credentials(include_drive=True)
        # LAZY import (R4.4).
        from googleapiclient.discovery import build

        drive = build("drive", "v3", credentials=creds, cache_discovery=False)
        safe_name = (self._spreadsheet_name or "").replace("'", "\\'")
        query = (
            f"name = '{safe_name}' and "
            "mimeType = 'application/vnd.google-apps.spreadsheet' and trashed = false"
        )
        response = (
            drive.files()
            .list(q=query, fields="files(id, name)", spaces="drive", pageSize=10)
            .execute()
        )
        matches = response.get("files", [])
        if not matches:
            raise ValueError(
                f"No Google Sheet titled {self._spreadsheet_name!r} was found (is it shared with "
                f"the service account as Viewer?). Prefer --sheet-id for an unambiguous lookup."
            )
        if len(matches) > 1:
            ids = ", ".join(m.get("id", "?") for m in matches)
            raise ValueError(
                f"{len(matches)} Google Sheets are titled {self._spreadsheet_name!r} ({ids}). "
                f"Use --sheet-id to disambiguate."
            )
        return matches[0]["id"]

    # ── Value fetch (single read-only values.get) ─────────────────────────────────────

    def _a1_range(self) -> str:
        """The A1 range to read: explicit ``cell_range``, else ``'<tab>'!A1:ZZ`` (or bare span)."""
        if self._cell_range:
            return self._cell_range
        if self._worksheet:
            # Quote the tab name for A1 notation (a name with spaces MUST be quoted).
            return f"'{self._worksheet}'!{self._DEFAULT_A1_SPAN}"
        return self._DEFAULT_A1_SPAN

    def _fetch_values(self) -> list[list[Any]]:
        """Fetch the raw value MATRIX via a single READ-ONLY ``spreadsheets.values.get`` (R4.2).

        Returns the list-of-rows matrix Google returns (each row a list of cell values; short
        rows are naturally shorter — :meth:`_rows_from_matrix` pads them). LAZY imports (R4.4).
        """
        creds = self._load_credentials()
        spreadsheet_id = self._resolve_spreadsheet_id()
        # LAZY import (R4.4).
        from googleapiclient.discovery import build

        sheets = build("sheets", "v4", credentials=creds, cache_discovery=False)
        result = (
            sheets.spreadsheets()
            .values()
            .get(spreadsheetId=spreadsheet_id, range=self._a1_range())
            .execute()
        )
        return result.get("values", [])

    # ── Matrix → position-tracked rows (R1/R4.5) ───────────────────────────────────────

    @staticmethod
    def _rows_from_matrix(matrix: Sequence[Sequence[Any]]) -> list[dict[str, Any]]:
        """Turn a Sheets value MATRIX into position-tracked ``{header: value}`` rows (R4.5/R1).

        Row 0 is the header row; each later row is zipped to it. Short rows are PADDED to the
        header width (Sheets omits trailing empty cells) so every header always gets a value.
        Duplicate headers are made unique via the SHARED :func:`build_position_tracked_row` helper
        (``<header>#<colindex>``), and a blank-named column is kept verbatim here (the transform
        drops it, R1.5). Pure — no network — so it is unit-testable on a synthetic matrix.
        """
        if not matrix:
            return []
        headers = list(matrix[0])
        width = len(headers)
        rows: list[dict[str, Any]] = []
        for raw_values in matrix[1:]:
            values = list(raw_values)
            if len(values) < width:
                values = values + [""] * (width - len(values))  # pad short rows to header width
            rows.append(build_position_tracked_row(headers, values))
        return rows

    def rows(self) -> Iterable[Mapping[str, Any]]:
        return self._rows_from_matrix(self._fetch_values())

    def describe(self) -> str:
        target = self._spreadsheet_id or self._spreadsheet_name or "<unknown>"
        tab = f" [tab {self._worksheet!r}]" if self._worksheet else ""
        return f"Google Sheet {target}{tab} (READ-ONLY, direct API)"


class LegacyDynamoSourceAdapter:
    """READ-ONLY adapter over the legacy h-dcn ``Members`` DynamoDB table (documented STUB).

    Sketched here so the runner's source seam is complete, but intentionally NOT required to
    run or test the backfill: h-dcn's real member data lives in a Google Sheet (demo-only),
    and this adapter would only ever *read* the legacy table (a full ``scan``/``query``) —
    it performs **no** writes, updates, or deletes, so reading it is non-destructive (R5.2,
    aws-accounts guardrail: never destructive against a data table). A concrete implementation
    would reuse ``services.dynamodb_client.get_dynamodb_resource`` and page a read-only
    ``scan`` of the legacy table, mapping each legacy item's attributes to the source-column
    names declared in the authored mapping contract (``members_source_mapping.csv``). It is left
    unbuilt on purpose (YAGNI for the pilot),
    and ``rows()`` raises so nobody accidentally relies on live legacy access.
    """

    def __init__(self, table_name: str, *, region: str | None = None):
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
    #: (label, reason) for rows intentionally SKIPPED (counted as "skipped (empty)", DISTINCT
    #: from errors — never transformed/written). s5m follow-up: an R7.2 EMPTY row (incl. a
    #: placeholder-only row) and a Donateur-coded ``Lidnummer`` row both land here (see RowSkipped).
    skipped: list[tuple[str, str]] = field(default_factory=list)
    #: non-empty member numbers appearing on more than one row in this batch — a DATA-QUALITY
    #: warning only (reported; NOT skipped or blocked — the uniqueness guard was removed in s5k).
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
    type_mapper: MembershipTypeMapper | None = None,
    tenant_id: str = HDCN_TENANT_ID,
    region_canonicalizer: RegionCanonicalizer | None = None,
) -> BackfillPlan:
    """Read the source (read-only) + transform every row into a :class:`BackfillPlan`.

    Non-destructive: it only iterates the adapter's ``rows()`` (a read) and builds an in-memory
    plan — it never writes anything. Rows that fail to map are collected into
    :attr:`BackfillPlan.errors` (the dry-run reports them; the batch is not aborted). s5k: EVERY
    transformable row is imported — a numberless row is a valid member (empty ``member_number``)
    and a reused number is a DATA-QUALITY warning recorded in
    :attr:`BackfillPlan.duplicate_member_numbers` (reported, never skipped or overwritten — the
    ``membernum#`` uniqueness guard was removed).
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

        number = record["membership"].get("member_number", "")
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
        # Group ONLY by a non-empty number: an empty `member_number` (numberless sponsor/club)
        # is not a "reused number" and must never be lumped into a duplicate bucket.
        if number:
            number_owners.setdefault(number, []).append(record["member_id"])

    plan.duplicate_member_numbers = {
        number: ids for number, ids in number_owners.items() if len(ids) > 1
    }

    # PASS 2: s5k — IMPORT EVERY ROW, including reused numbers. The `membernum#` uniqueness guard
    # is gone: a member number reused in the source is a DATA-QUALITY warning, not a write-time
    # conflict, so it no longer justifies dropping real members. `duplicate_member_numbers` is
    # still computed and REPORTED (the fidelity report lists it) so the data owner can reconcile a
    # recycled/duplicated Lidnummer in the source — but nothing is skipped for it.
    for cand in candidates:
        plan.transformed.append(cand)
        if not cand.region:
            plan.rows_missing_region.append(cand.member_id)

    return plan
