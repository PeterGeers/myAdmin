"""Read-only source adapters (iterable / file / Google Sheets / legacy).

Part of the h-dcn backfill package (code-quality-fixes-2026-11-12 task 3).
"""

from __future__ import annotations

import csv
import io
import json
import os
from collections.abc import Iterable, Iterator, Mapping, Sequence
from typing import Any, Protocol

from .source_layout import (
    _DRIVE_READONLY_SCOPE,
    _SHEETS_READONLY_SCOPE,
    DEFAULT_GOOGLE_CREDENTIALS_FILE,
    build_position_tracked_row,
)

# ── Source adapters (READ-ONLY; never modify the live source) ─────────────────────────


class HdcnSourceAdapter(Protocol):
    """A read-only source of raw h-dcn member rows.

    Implementations MUST be non-destructive: they only *read* the source (a Google-Sheet
    export, or the legacy ``Members`` table read-only) — they never write, update, or delete
    it (R5.2). ``rows()`` yields plain mappings (one per member) with the h-dcn source column
    names as keys, which :func:`map_hdcn_row` then transforms.
    """

    def rows(self) -> Iterable[Mapping[str, Any]]: ...

    def describe(self) -> str:
        """A short human description of the source (shown in the fidelity report header)."""
        ...


class IterableSourceAdapter:
    """An in-memory :class:`HdcnSourceAdapter` over a list of row mappings.

    The storage-agnostic default used by tests (and any caller that already holds the rows).
    Read-only by construction — it never mutates the rows it was handed.
    """

    def __init__(
        self, rows: Sequence[Mapping[str, Any]], *, description: str = "in-memory rows"
    ):
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
            raise ValueError(
                f"unsupported source format {self._fmt!r} (expected csv or json)"
            )

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
            raise ValueError(
                'JSON source must be a list of row objects (or {"rows": [...]})'
            )
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
        return service_account.Credentials.from_service_account_file(
            path, scopes=scopes
        )

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
                values = values + [""] * (
                    width - len(values)
                )  # pad short rows to header width
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
