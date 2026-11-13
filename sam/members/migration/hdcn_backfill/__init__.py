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

from .field_values import (
    ColumnShiftWarning,
    DuplicateHeaderConflict,
    detect_column_shift,
)
from .field_values import (
    _load_default_contract as _load_default_contract,
)
from .field_values import (
    _parse_source_date as _parse_source_date,
)
from .plan import (
    BackfillPlan,
    TransformedRow,
    build_backfill_plan,
)
from .source_layout import (
    DEFAULT_GOOGLE_CREDENTIALS_FILE,
    DUPLICATE_HEADER_INDEX_SEP,
    HDCN_TENANT_ID,
    RegionCanonicalizer,
    build_position_tracked_row,
)
from .sources import (
    FileSourceAdapter,
    GoogleSheetsSourceAdapter,
    HdcnSourceAdapter,
    IterableSourceAdapter,
    LegacyDynamoSourceAdapter,
)
from .transform import (
    map_hdcn_row,
)
from .vocabulary import (
    MembershipTypeMapper,
    RowSkipped,
    RowTransformError,
    contract_source_columns,
)
