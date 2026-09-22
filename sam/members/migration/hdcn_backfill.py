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
import io
import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Iterator, Mapping, Optional, Protocol, Sequence

from sam.members.domain.fixed_fields import (
    FieldValidationError,
    validate_fixed_fields,
)
from sam.members.domain.scope_canon import scope_canon
from sam.members.domain.scope_dimensions import HDCN_SCOPE_CONFIG

__all__ = [
    "HDCN_TENANT_ID",
    "FIXED_SOURCE_COLUMNS",
    "MembershipTypeMapper",
    "RowTransformError",
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

#: The h-dcn ``region`` dimension's canonical value set (Noord/Zuid/Oost/West), sourced from
#: ``scope_dimensions.HDCN_SCOPE_CONFIG`` so the importer and enforcement share ONE vocabulary
#: (no drift). This is the closed set of canonical values the member's ``region`` field may
#: hold after normalization.
_HDCN_REGION_VALUES: tuple[str, ...] = next(
    (tuple(d.values) for d in HDCN_SCOPE_CONFIG if d.key == "region"),
    (),
)

#: Region normalization via the SHARED ``scope_canon`` (S5d R9.2, D5): a raw export value is
#: matched against the dimension's canonical value set by canonical equality (``scope_canon``
#: applied identically to both sides — case / diacritic / separator fold), so lowercase /
#: accented / spacing variants land on the dimension's canonical spelling (e.g. ``"noord"`` →
#: ``"Noord"``). This is the SAME canonicalizer enforcement uses, so a stored member value and
#: a granted value share one vocabulary (Property 4). An unknown region (no canonical match) is
#: preserved verbatim and surfaced in the report — the transform never silently drops data
#: (R9.3), and the R9.5 verification (task 2.4) flags any such un-normalizable value.
_REGION_CANONICAL_BY_CANON: Mapping[str, str] = {
    scope_canon(v): v for v in _HDCN_REGION_VALUES
}


# ── Source-column contract (the h-dcn Ledenbestand shape the transform reads) ─────────

#: The raw source column names the transform maps into the FIXED base. The h-dcn Ledenbestand
#: (Google Sheet) columns → member-record fixed fields. Any column NOT named here (and not the
#: region/type columns below) is treated as a club/Motor detail and folded into ``overlay``.
FIXED_SOURCE_COLUMNS: Mapping[str, str] = {
    # source column      -> dotted member-record fixed key (s5c canonical EN keys)
    "member_id": "member_id",
    # `naam` is h-dcn's single display-name column; the s5c base splits name into
    # first_name/last_name/name_infix/initials. Splitting a free-form `naam` reliably is
    # h-dcn's concern (its export can carry the parts), so for the reused backfill we map the
    # single `naam` column onto the required `personal.last_name` (so a name-only export still
    # produces a valid fixed record); an export that already carries `voornaam`/`achternaam`
    # etc. maps them directly via the entries below. (Judgment aligned to the classification
    # table; noted in the task report.)
    "naam": "personal.last_name",
    "voornaam": "personal.first_name",
    "achternaam": "personal.last_name",
    "tussenvoegsel": "personal.name_infix",
    "initialen": "personal.initials",
    "geslacht": "personal.gender",
    "telefoon": "personal.phone",
    "email": "personal.email",
    # `adres` is h-dcn's single address column; the s5c base splits address into
    # street/postal_code/city/country (all stored under `personal`). Map the single `adres`
    # column onto `personal.street` (the primary address line); split columns map directly.
    "adres": "personal.street",
    "straat": "personal.street",
    "postcode": "personal.postal_code",
    "woonplaats": "personal.city",
    "land": "personal.country",
    "geboortedatum": "personal.birth_date",
    "lidnummer": "membership.member_number",
    "status": "membership.status",
    "lidmaatschapstype": "membership.membership_type",
    "ingangsdatum": "membership.joined_date",
    # NOTE: `einddatum` (the h-dcn "left" date) has no Fixed row in the s5c classification
    # table (the `left` STATUS is kept via MembershipStatus; there is no `left` *field*), so it
    # is an unmapped column and folds into `overlay` per the Phase 6 import rule.
}

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


def _canonical_region(value: str) -> str:
    """Normalize a raw region to the dimension's canonical value via the shared ``scope_canon``.

    S5d R9.2/D5: the raw export value is matched against the dimension's canonical value set by
    canonical equality (``scope_canon`` applied to both sides), so case / diacritic / separator
    variants (``"noord"``, ``"NOORD"``, ``"Noord "``) all land on the canonical spelling
    (``"Noord"``). This is the SAME canonicalizer enforcement uses, so a stored member value and
    a granted value share one vocabulary (Property 4). An un-normalizable value (no canonical
    match) is preserved verbatim rather than silently dropped (R9.3 — surfaced by the runner and
    the R9.5 verification, task 2.4)."""
    canon = scope_canon(value)
    if not canon:
        return value.strip()
    return _REGION_CANONICAL_BY_CANON.get(canon, value.strip())


def map_hdcn_row(
    raw_row: Mapping[str, Any],
    *,
    type_mapper: Optional[MembershipTypeMapper] = None,
    tenant_id: str = HDCN_TENANT_ID,
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
      ``personal`` / ``membership`` (+ the top-level ``member_id``); ``status`` is mapped
      from h-dcn's Dutch vocabulary to the closed platform enum.
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
    member_id: Optional[str] = None
    region_raw: Optional[str] = None
    reasons: dict[str, str] = {}

    for column, value in raw_row.items():
        col = (column or "").strip()
        col_lower = col.lower()
        cleaned = _clean(value)

        if col_lower == _REGION_SOURCE_COLUMN:
            region_raw = cleaned if isinstance(cleaned, str) else None
            continue

        dotted = FIXED_SOURCE_COLUMNS.get(col_lower)
        if dotted is None:
            # Unknown column → a club/Motor variable overlay field (kept verbatim).
            if cleaned is not None:
                overlay[col] = cleaned
            continue

        if dotted == "member_id":
            member_id = cleaned if isinstance(cleaned, str) else (str(cleaned) if cleaned is not None else None)
            continue

        group, key = dotted.split(".", 1)
        target = personal if group == "personal" else membership

        if key == "status" and isinstance(cleaned, str):
            mapped = _STATUS_MAP.get(cleaned.strip().lower())
            target[key] = mapped if mapped is not None else cleaned
        elif key == "membership_type":
            if cleaned is None:
                reasons["membership.membership_type"] = "is required"
            else:
                try:
                    target[key] = mapper.to_code(cleaned)
                except ValueError as exc:
                    reasons["membership.membership_type"] = str(exc)
        elif cleaned is not None:
            target[key] = cleaned

    member_ref = member_id or membership.get("member_number") or "<unknown>"

    if not member_id:
        reasons["member_id"] = "source row has no member_id / lidnummer to key on"

    # S5d D1/R3.4: the region is a PLAIN member field, not a `scope_values` bucket. h-dcn's
    # `region` is a tenant-added field → its storage bucket is `overlay`. Store the CANONICAL
    # value (normalized via the shared `scope_canon`, R9.2) as a SCALAR (single-valued per
    # scope field, R3.2). An absent region omits the field entirely (no empty placeholder).
    if region_raw:
        overlay[_REGION_FIELD_KEY] = _canonical_region(region_raw)

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
) -> BackfillPlan:
    """Read the source (read-only) + transform every row into a :class:`BackfillPlan`.

    Non-destructive: it only iterates the adapter's ``rows()`` (a read) and builds an in-memory
    plan — it never writes anything. Rows that fail to map are collected into
    :attr:`BackfillPlan.errors` (the dry-run reports them; the batch is not aborted). Member
    numbers that repeat within the batch are recorded as would-be uniqueness conflicts
    (Property 6) so ``--apply`` can be trusted to report rather than overwrite.
    """
    plan = BackfillPlan(tenant_id=tenant_id, source_description=adapter.describe())
    seen_numbers: dict[str, list[str]] = {}

    for raw in adapter.rows():
        plan.source_row_count += 1
        try:
            record = map_hdcn_row(raw, type_mapper=type_mapper, tenant_id=tenant_id)
        except RowTransformError as exc:
            plan.errors.append((exc.member_ref, exc.reasons))
            continue

        member_id = record["member_id"]
        number = record["membership"]["member_number"]
        type_code = record["membership"]["membership_type"]
        # S5d D1: region is a plain scalar field on `overlay.region` now (no `scope_values`).
        region_value = record.get("overlay", {}).get(_REGION_FIELD_KEY)
        region = (region_value,) if region_value else ()

        plan.transformed.append(
            TransformedRow(
                member_id=member_id,
                member_number=number,
                member_type_code=type_code,
                region=region,
                record=record,
            )
        )
        if not region:
            plan.rows_missing_region.append(member_id)
        seen_numbers.setdefault(number, []).append(member_id)

    plan.duplicate_member_numbers = {
        number: ids for number, ids in seen_numbers.items() if len(ids) > 1
    }
    return plan
