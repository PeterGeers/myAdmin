"""Position-tracked source rows and header helpers.

Part of the h-dcn backfill package (code-quality-fixes-2026-11-12 task 3).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from sam.members.domain.scope_canon import scope_canon

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
    set it authors into ``members.scope_dimensions`` (from
    ``scripts/onboarding/members/h-dcn/members_config.json``)
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
        key = (
            base
            if occurrence == 1
            else f"{base}{DUPLICATE_HEADER_INDEX_SEP}{col_index}"
        )
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
