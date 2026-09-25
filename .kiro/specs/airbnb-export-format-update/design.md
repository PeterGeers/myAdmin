# Design Document

## Overview

Airbnb changed its CSV export layout. The new exports ship as two files that share one column
family but differ by which columns are present, and every booking now appears as two rows — a
`Boeking` row and a `Doorloop totaal` row — sharing one `Bevestigingscode`, interleaved with
informational `Payout` rows. This design rewires the Airbnb ingest path across three modules
while keeping the `Booking_Dict` output contract (Requirement 8) and the tenant-scoped `bnb` /
`bnbplanned` tables unchanged, so downstream persistence, summaries, and reporting keep working.

The change touches three files:

- **`backend/src/str_airbnb_parser.py`** — full rewrite. Read the CSV with pandas, drop
  `Payout` rows, group the rest by `Bevestigingscode`, and emit one booking dict per group with
  gross and channel fee summed from the group's rows.
- **`backend/src/str_processor.py`** (`scan_str_files`, `_process_airbnb_multi`) — detect the
  new Airbnb format by header content or an `airbnb` filename token, classify each file as
  pending vs. realised, and pass that classification into the parser so it drives status.
- **`backend/src/str_database.py`** — add an Airbnb upsert that mirrors `upsert_direct_bookings`
  (keyed refresh by `reservationCode` within channel + administration), applied to `bnb` for
  realised bookings and `bnbplanned` for planned bookings.

The old `reservation`-style parser is replaced, not kept alongside.

### Ground truth from the sample files

The design is grounded in the two sample exports under `.agent-output/`:
`airbnb_pending.csv` (a Pending_File) and `airbnb_08_2026-09_2026.csv` (a Realised_File).

Observed facts that shape the design:

- **Header whitespace and BOM.** Column names carry leading/trailing padding
  (`" Type           "`, `" Bruto-inkomsten"`) and the first column carries a UTF-8 BOM
  (`\ufeffDatum`). Cell values are space-padded too (`"  76.67"`, `" 0.00         "`).
  Every column name and every consumed value must be stripped before use.
- **Header difference.** The Realised_File header adds `Verwacht op`, `Uitbetaald`, and
  `Kosten voor snelle uitbetaling`; the Pending_File header lacks all three. Both share
  `Type` and `Bruto-inkomsten`.
- **Row pairing.** Each booking is a `Boeking` row (carries `Bedrag`, `Servicekosten`,
  `Bruto-inkomsten`) plus a `Doorloop totaal` row (carries a smaller `Bruto-inkomsten`, zero
  `Servicekosten`). Both rows repeat the same `Bevestigingscode`, dates, guest, and listing.
- **Payout rows.** `Type = Payout`, blank `Bevestigingscode`, an amount only in `Uitbetaald`.
  Informational; excluded from grouping.
- **Mixed amount notation.** `Bruto-inkomsten` uses US notation (`274.80`, `76.67`) while
  `Servicekosten` uses quoted European notation (`"42,59"`, `"13,25"`) or `0.00`. Both notations
  appear in the same file, so the amount parser must accept both.
- **Dates are `MM/DD/YYYY`** (`09/23/2026`, `09/04/2026`).

The two verified worked examples (both present in `airbnb_pending.csv`):

| Bevestigingscode | Boeking Bruto | Doorloop Bruto | Gross (sum) | Boeking Service | Doorloop Service | Fee (sum) |
|---|---|---|---|---|---|---|
| `HMXDT8WAFF` | 274.80 | 76.67 | **351.47** | "42,59" | 0.00 | **42.59** |
| `HMTFCHFWTP` | 85.50 | 23.86 | **109.36** | "13,25" | 0.00 | **13.25** |

These match Requirement 3.5 and 3.6 exactly and become the anchor assertions of the test suite.

## Architecture

### End-to-end flow

```
Upload (routes/str_routes.py: str_upload)
   │  platform == "airbnb", temp file paths
   ▼
STRProcessor.process_str_files(paths, "airbnb")
   └─► _process_airbnb_multi(paths)
          └─► process_airbnb_multi(paths, tax_rate_service, tenant)   [str_airbnb_parser]
                 ├─ per file: read CSV, strip headers, classify pending vs realised
                 ├─ drop Payout rows
                 ├─ group remaining rows by Bevestigingscode
                 ├─ per group: build Booking_Dict (gross/fee summed, taxes, dates, status)
                 └─ return list[Booking_Dict]  (status = planned | realised from file class)
   ▼
separate_by_status(bookings)   [existing]  → realised / planned / already_loaded
   ▼  (user reviews, then POST /api/str/save)
str_save (routes/str_routes.py)
   ├─ platform == "airbnb": str_db.upsert_airbnb_bookings(realised, planned, tenant)
   │      ├─ realised → bnb   (INSERT new / UPDATE existing by reservationCode)
   │      └─ planned  → bnbplanned (INSERT new / UPDATE existing by reservationCode)
   └─ (non-airbnb platforms keep their existing save paths)
```

### Layering and responsibilities

| Layer | Component | Responsibility |
|---|---|---|
| Scan | `str_processor.scan_str_files` | Classify download-folder files by platform. Detect Airbnb by header (`Type` + `Bruto-inkomsten`) or `airbnb` filename token. |
| Parse | `str_airbnb_parser.process_airbnb_multi` | Orchestrate multi-file read, per-file classification, Payout filtering, grouping, and dict assembly. |
| Parse | `str_airbnb_parser` helpers | Amount parsing, date parsing, single-group assembly. |
| Calculate | `str_utils.calculate_str_taxes` | VAT / tourist tax / net from gross, check-in date, channel fee. **Reused unchanged.** |
| Enrich | `country_detector.detect_country` | Country from `addInfo` text only (no phone column). **Reused unchanged.** |
| Persist | `str_database.upsert_airbnb_bookings` | Keyed refresh into `bnb` (realised) and `bnbplanned` (planned). **New.** |

The Booking.com, Direct, and VRBO codepaths are untouched.

## Components and Interfaces

### 1. `str_processor.scan_str_files` — detection & classification

Replaces the `reservation` filename rule. Because file scanning reads a folder, detection needs
to peek at each CSV's header to decide Airbnb membership and pending-vs-realised.

```python
AIRBNB_REALISED_MARKERS = ("Uitbetaald", "Verwacht op")   # both present → realised

def _airbnb_header_columns(file_path: str) -> list[str] | None:
    """Return stripped header names for a CSV, or None if unreadable."""
    try:
        header = pd.read_csv(file_path, nrows=0).columns.tolist()
        return [str(c).replace("\ufeff", "").strip() for c in header]
    except Exception:
        return None

def _is_airbnb_file(filename: str, columns: list[str] | None) -> bool:
    if "airbnb" in filename.lower():                      # Req 1.2
        return True
    if columns and "Type" in columns and "Bruto-inkomsten" in columns:  # Req 1.1
        return True
    return False

def _airbnb_is_realised(columns: list[str]) -> bool:
    return all(m in columns for m in AIRBNB_REALISED_MARKERS)  # Req 1.3 / 1.4
```

`scan_str_files` returns Airbnb files split by classification so the caller knows the target
table without re-reading headers:

```python
files = {
    "airbnb_realised": [], "airbnb_pending": [],
    "booking": [], "booking_payout": [], "direct": [],
}
# for each .csv: columns = _airbnb_header_columns(fp)
#   if _is_airbnb_file(file, columns):
#       (files["airbnb_realised"] if columns and _airbnb_is_realised(columns)
#        else files["airbnb_pending"]).append(fp)
```

- Req 1.1: header has `Type` **and** `Bruto-inkomsten` → Airbnb.
- Req 1.2: filename contains `airbnb` → Airbnb (header may be unreadable / token-only).
- Req 1.3: header has `Uitbetaald` **and** `Verwacht op` → Realised_File.
- Req 1.4: header lacks both → Pending_File.
- Req 1.5: the `reservation` token is removed from the scanner entirely.

Filename-token Airbnb files whose header cannot be read default to **pending** (safer: planned
bookings are refreshed in `bnbplanned`, never mixed into realised history).

### 2. `str_airbnb_parser` — parse & calculate

The public entry keeps its name and signature so `str_processor._process_airbnb_multi` and the
route layer need no interface change beyond passing classification. Classification is passed
explicitly per call so the parser never re-guesses status from dates.

```python
def process_airbnb_multi(
    file_paths: list[str],
    tax_rate_service=None,
    tenant: str | None = None,
    status: str = "realised",   # "planned" for Pending_File batches
) -> list[dict]:
    """Read Airbnb CSV(s) of a single classification, group by Bevestigingscode,
    and return one Booking_Dict per group with the given status."""
```

The caller invokes it once per classification bucket (once for pending paths with
`status="planned"`, once for realised paths with `status="realised"`), so a batch is
homogeneous and status is unambiguous (Req 6.1, 6.3, 6.5).

Internal helpers:

```python
def parse_airbnb_amount(value) -> float: ...
def parse_airbnb_date(value: str) -> datetime | None: ...
def build_booking_from_group(
    code: str, rows: pd.DataFrame, source_file: str, status: str,
    tax_rate_service, tenant,
) -> dict: ...
```

### 3. `str_database.upsert_airbnb_bookings` — persistence

New method mirroring `upsert_direct_bookings`, but parameterized by channel (`airbnb`) and by
target table, and applied to both `bnb` (realised) and `bnbplanned` (planned).

```python
def upsert_airbnb_bookings(
    self,
    realised: list[dict],
    planned: list[dict],
    tenant: str | None = None,
) -> dict:
    """Keyed upsert of Airbnb bookings.
       realised → bnb, planned → bnbplanned, keyed by reservationCode
       within channel 'airbnb' + administration.
       Returns {'realised_inserted','realised_updated','planned_inserted','planned_updated'}.
    """
```

Both halves reuse one private helper that: (1) selects existing `reservationCode`s for
`channel='airbnb'` and the administration from the target table, (2) splits incoming dicts into
new vs. existing, (3) INSERTs new rows, (4) UPDATEs existing rows in place (Req 10.1–10.4).

## The amount-parsing algorithm

Requirement 4 requires accepting three notations and treating blank/non-numeric as zero. The
existing `str_utils.parse_amount` already handles European and symbol-stripping, but Airbnb
values arrive quoted and space-padded and mix US notation in the same file, so the parser is
implemented locally to be explicit and unit-testable against the exact sample values.

Decision rule (grounded in the samples: `"1.234,56"`, `"42,59"`, `274.80`, `0.00`, blank):

```
parse_airbnb_amount(value):
    if value is NaN or blank-after-strip:            → 0.0            (Req 4.4)
    s = str(value); strip quotes, spaces, € symbol
    if s has a comma:                                 # European
        parts = s.split(",")
        if len(parts) == 2:
            integer = parts[0] with "." removed       # drop thousands sep
            s = integer + "." + parts[1]              (Req 4.2, 4.3)
        else:
            s = s.replace(",", ".")
    # else: already US-style with "." decimal          (Req 4.1)
    try float(s) else 0.0                              (Req 4.4)
```

Worked cases:

- `274.80` → no comma → `float("274.80")` = **274.80**.
- `"1.234,56"` → comma, two parts → integer `"1234"`, decimal `"56"` → **1234.56**.
- `"42,59"` → comma, two parts → integer `"42"`, decimal `"59"` → **42.59**.
- `"0.00"` / `0.00` → no comma → **0.0**. Blank / `NaN` / `"—"` → **0.0**.

## The group-by algorithm

Requirement 2: group by non-blank `Bevestigingscode`, one dict per group, Payout rows excluded,
attributes read from the group's rows.

```
build_bookings(df, source_file, status, ...):
    df.columns = [strip BOM + whitespace for each column name]
    # Req 2.3: drop Payout rows and any row with a blank confirmation code
    df = df where Type.strip() != "Payout"
    df = df where Bevestigingscode.strip() != ""
    bookings = []
    for code, group in df.groupby(Bevestigingscode.strip()):   # Req 2.1
        bookings.append(build_booking_from_group(code, group, source_file, status, ...))
    return bookings                                             # Req 2.2 (one per group)
```

`build_booking_from_group` derives each field from the group (Req 2.4). Attributes that are
identical across the pair (dates, guest, listing, nights, reservation date) are read from the
first row; amounts are summed across all rows:

- `Gross_Amount = Σ parse_airbnb_amount(Bruto-inkomsten)` over the group (Req 3.1).
- `Channel_Fee = Σ parse_airbnb_amount(Servicekosten)` over the group (Req 3.2).
- No hardcoded 15% factor anywhere (Req 3.4).

For `HMXDT8WAFF` this yields gross `76.67 + 274.80 = 351.47` and fee `0.00 + 42.59 = 42.59`.

## File-classification & routing flow

Status is a property of the source file, not the booking date (Req 6.5). The classification made
in `scan_str_files` (or, for uploads, inferred from the uploaded file's header) is threaded down:

1. **Pending_File** → parser called with `status="planned"` → each dict has `status="planned"`
   (Req 6.1) → route sends these to `bnbplanned` (Req 6.2).
2. **Realised_File** → parser called with `status="realised"` → each dict has
   `status="realised"` (Req 6.3) → route sends these to `bnb` (Req 6.4).

For the upload route (`str_upload`), the uploaded files are classified by header the same way
(`_airbnb_is_realised` on the stripped header) so a single upload of mixed pending + realised
files routes each correctly. `separate_by_status` continues to split the combined list on the
dict `status` field, so the review UI and the existing `already_loaded` dedup keep working.

## Upsert flow

`upsert_airbnb_bookings` runs inside one `self.transaction()` block (matching
`upsert_direct_bookings`). For each half (realised→`bnb`, planned→`bnbplanned`):

```
existing = SELECT DISTINCT reservationCode
           FROM <table>
           WHERE channel = 'airbnb'
             AND administration = %s          # tenant-scoped (Req 10.1)
             AND reservationCode IS NOT NULL
new      = [b for b in half if b.reservationCode not in existing]   # Req 10.2
existing = [b for b in half if b.reservationCode in existing]       # Req 10.3
INSERT each new row (full column list, administration = tenant)
UPDATE each existing row (financials, dates, listing, guest, status, sourceFile)
       WHERE reservationCode = %s AND channel = 'airbnb' AND administration = %s
```

All queries are parameterized (`%s`) and always filter/insert `administration` explicitly,
satisfying tenant isolation. When `tenant` is `None`, the `administration` predicate is omitted
(matching the existing `upsert_direct_bookings` fallback) — but the route layer always supplies
the tenant from `@tenant_required()`, so production paths are always scoped.

Re-importing the same file therefore updates in place rather than duplicating (Req 10), for both
realised (`bnb`) and planned (`bnbplanned`) bookings (Req 10.4). This replaces the current
planned path's delete-by-`channel/listing/administration` behavior for Airbnb with a keyed
refresh, so a re-import that drops a previously-planned booking leaves its old row untouched
rather than wiping the whole listing.

## Data shapes

### Input row (stripped column names)

Shared columns: `Datum`, `Type`, `Bevestigingscode`, `Boekingsdatum`, `Begindatum`,
`Einddatum`, `Nachten`, `Gast`, `Advertentie`, `Informatie`, `Referentienummer`, `Valuta`,
`Bedrag`, `Servicekosten`, `Schoonmaakkosten`, `Bruto-inkomsten`,
`Door Airbnb doorbelaste en afgedragen heffingen`, `Inkomstenjaar`.
Realised_File additionally: `Verwacht op`, `Uitbetaald`, `Kosten voor snelle uitbetaling`.

### Consumed columns → output mapping

| Source column | Output field | Notes |
|---|---|---|
| `Bevestigingscode` | `reservationCode` + group key | Req 8.4 |
| `Boekingsdatum` | `reservationDate`; drives `daysBeforeReservation` | MM/DD/YYYY, Req 5.2 / 9.3 |
| `Begindatum` | `checkinDate`; drives `year`,`q`,`m` | MM/DD/YYYY, Req 5.2 / 5.4 |
| `Einddatum` | `checkoutDate` | MM/DD/YYYY, Req 5.2 |
| `Nachten` | `nights` | int |
| `Gast` | `guestName` | |
| `Advertentie` | `listing` | via `normalize_listing_name`, Req 8.3 |
| `Bruto-inkomsten` | summed into `amountGross` | Req 3.1 |
| `Servicekosten` | summed into `amountChannelFee` | Req 3.2 |
| `Informatie` (+ full row) | `addInfo`; feeds `detect_country` | Req 7.3 |

### Ignored columns (Req 9)

`Schoonmaakkosten`, `Door Airbnb doorbelaste en afgedragen heffingen`,
`Kosten voor snelle uitbetaling`, `Verwacht op`, `Uitbetaald`, `Datum`, `Referentienummer`,
`Inkomstenjaar` are excluded from calculation and output. `Valuta` is not read into any output
field; currency is treated as EUR (Req 9.2).

### Output `Booking_Dict` (unchanged contract — Req 8.1)

`sourceFile`, `channel` (`"airbnb"`, Req 8.2), `listing`, `checkinDate`, `checkoutDate`,
`nights`, `guests`, `amountGross`, `amountChannelFee`, `guestName`, `phone`, `reservationCode`,
`reservationDate`, `status`, `addInfo`, `amountVat`, `amountTouristTax`, `amountNett`,
`pricePerNight`, `year`, `q`, `m`, `daysBeforeReservation`, `country`.

Defaults for fields with no source column (Req 7):

- `guests` = **2** (no guest-count column, Req 7.1).
- `phone` = `""` (no contact column, Req 7.2); `country` derived from `addInfo` only (Req 7.3).
- Dates emitted as `YYYY-MM-DD` after parsing `MM/DD/YYYY`.
- `pricePerNight` = `amountNett / nights` when `nights > 0` else `0`.

## Error handling

Malformed input must degrade gracefully — an ingest run of ~40 bookings should never abort on
one bad row.

| Condition | Handling |
|---|---|
| A file fails to read | Skip it, record the basename, continue; raise `ValueError` only if **all** files fail (preserves existing `process_airbnb_multi` contract). |
| Row has blank `Bevestigingscode` (Payout or stray) | Excluded during grouping (Req 2.3). |
| Unparseable amount (blank, `NaN`, non-numeric) | `parse_airbnb_amount` returns `0.0` (Req 4.4); the group still produces a dict. |
| Unparseable date | `parse_airbnb_date` returns `None`; the field falls back — `checkinDate`/`checkoutDate`/`reservationDate` default to today's date string, and derived `year/q/m` fall back to the current year / `q=1` / `m=1`, `daysBeforeReservation=0` (mirrors the current parser's `except` behavior). |
| Missing expected column | `row.get(col, "")` / column-presence checks return empty → treated as blank → amount 0 / date fallback; never `KeyError`. |
| Header column names padded / BOM-prefixed | Normalized once at read time (`strip` + BOM removal) before any lookup. |
| DB error during upsert | Caught as `DatabaseError`; the transaction rolls back and the method returns zero counts with an `error` key (matching `upsert_direct_bookings`). |

Amounts are never silently invented: a zero from an unparseable fee is a real zero, and gross is
the true sum of whatever parsed. This keeps the data-ownership rule intact (algorithms interpret,
never fabricate).

## Testing Strategy

**Dual approach.** Property tests (Hypothesis, ≥100 iterations) cover the parsing/grouping/
calculation logic where behavior varies with input; example and integration tests cover the two
verified worked examples, file classification, and the DB upsert.

### Anchored example tests (highest priority)

Run the parser over `.agent-output/airbnb_pending.csv` and assert:

- `HMXDT8WAFF` → `amountGross == 351.47`, `amountChannelFee == 42.59` (Req 3.5).
- `HMTFCHFWTP` → `amountGross == 109.36`, `amountChannelFee == 13.25` (Req 3.6).
- Both dicts have `status == "planned"`, `channel == "airbnb"`, `guests == 2`, `phone == ""`.
- Exactly one dict per confirmation code; no dict has a blank `reservationCode` (Payout rows
  dropped).

Classification tests over both sample headers:

- `airbnb_pending.csv` header → Pending_File; `airbnb_08_2026-09_2026.csv` header → Realised_File.
- A file named `something-airbnb.csv` with an unreadable header still classifies as Airbnb.
- A former `reservation*.csv` name no longer classifies as Airbnb by name alone.

### Amount-parser unit tests

`274.80→274.80`, `"1.234,56"→1234.56`, `"42,59"→42.59`, `"0.00"→0.0`, `""→0.0`,
`NaN→0.0`, `"—"→0.0`, `" 76.67 "→76.67` (padding).

### DB upsert integration test (against local Docker MySQL / test schema)

Insert a planned Airbnb booking, re-run the same import, assert one row in `bnbplanned` (updated,
not duplicated); repeat for a realised booking into `bnb`. Verify tenant scoping (a second
administration with the same `reservationCode` is untouched).

### Property tests (Hypothesis)

*Note:* the DB layer and `calculate_str_taxes` are exercised by example/integration tests; the
property tests target the pure parsing/grouping/classification logic plus the keyed-refresh
idempotence. Each property test implements one entry from the numbered **Correctness Properties**
section below (Properties 1–11) — the numbering there is authoritative and is what the task list
references. The pure-logic properties map to tasks as follows:

- **Property 1 (Airbnb file detection):** task 4.3. (Validates 1.1, 1.2, 1.5)
- **Property 2 (Realised vs. pending classification):** task 4.4. (Validates 1.3, 1.4)
- **Property 3 (One dict per group, Payout excluded):** task 2.8. (Validates 2.1, 2.2, 2.3)
- **Property 4 (Gross is the sum of Bruto-inkomsten):** task 2.4. (Validates 3.1)
- **Property 5 (Channel fee is the sum of Servicekosten, no hardcoded factor):** task 2.5.
  (Validates 3.2, 3.4)
- **Property 6 (Amounts parse across notations):** task 2.6. (Validates 4.1, 4.2, 4.3)
- **Property 7 (Blank or non-numeric amounts are zero):** task 2.7. (Validates 4.4)
- **Property 8 (Dates and derived periods):** task 2.9. (Validates 5.1–5.4, 9.3)
- **Property 9 (Status follows file classification):** task 4.6. (Validates 6.1, 6.3, 6.5)
- **Property 10 (Output contract completeness):** task 2.10.
  (Validates 2.4, 7.1, 7.2, 8.1–8.4, 9.1, 9.2)
- **Property 11 (Re-import is idempotent — keyed refresh):** task 5.3. (Validates 10.1, 10.2, 10.3)

Property tests tag: **Feature: airbnb-export-format-update, Property {n}: {text}**.

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of
a system — a formal statement about what the system should do. Properties bridge human-readable
specifications and machine-verifiable correctness guarantees.*

### Property 1: Airbnb file detection

*For any* CSV file, the File_Scanner classifies it as an Airbnb file if and only if its name
contains the token `airbnb`, or its (whitespace/BOM-stripped) header contains both a `Type`
column and a `Bruto-inkomsten` column; a `reservation` filename token alone does not classify it.

**Validates: Requirements 1.1, 1.2, 1.5**

### Property 2: Realised vs. pending classification

*For any* Airbnb file header, the File_Scanner classifies it as a Realised_File if and only if
the header contains both `Uitbetaald` and `Verwacht op`, and otherwise as a Pending_File.

**Validates: Requirements 1.3, 1.4**

### Property 3: Grouping produces one booking per confirmation code, Payout rows excluded

*For any* interleaving of `Boeking`, `Doorloop totaal`, and `Payout` rows, the Airbnb_Parser
produces exactly one Booking_Dict for each distinct non-blank `Bevestigingscode` and no
Booking_Dict for any Payout_Row or blank-code row.

**Validates: Requirements 2.1, 2.2, 2.3**

### Property 4: Gross is the sum of Bruto-inkomsten

*For any* Booking_Group, the emitted `amountGross` equals the sum of the parsed `Bruto-inkomsten`
values across all rows in the group.

**Validates: Requirements 3.1**

### Property 5: Channel fee is the sum of Servicekosten (no hardcoded factor)

*For any* Booking_Group, the emitted `amountChannelFee` equals the sum of the parsed
`Servicekosten` values across all rows in the group, independent of the gross amount.

**Validates: Requirements 3.2, 3.4**

### Property 6: Amounts parse across notations

*For any* amount value written in US notation (period decimal), quoted European notation with a
period thousands separator, or European notation without a thousands separator, the Airbnb_Parser
parses it to the corresponding numeric value.

**Validates: Requirements 4.1, 4.2, 4.3**

### Property 7: Blank or non-numeric amounts are zero

*For any* blank or non-numeric amount value, the Airbnb_Parser treats it as zero.

**Validates: Requirements 4.4**

### Property 8: Dates and derived periods

*For any* set of `Begindatum`, `Einddatum`, and `Boekingsdatum` values in `MM/DD/YYYY` form, the
Airbnb_Parser sets `checkinDate`, `checkoutDate`, and `reservationDate` to those same calendar
days, derives `year`, `q`, and `m` from the check-in date, and sets `daysBeforeReservation` to
the number of days between the reservation date and the check-in date.

**Validates: Requirements 5.1, 5.2, 5.3, 5.4, 9.3**

### Property 9: Status follows file classification

*For any* parsed batch, every Booking_Dict's `status` equals `planned` when the batch came from a
Pending_File and `realised` when it came from a Realised_File, independent of the check-in date
relative to the current date.

**Validates: Requirements 6.1, 6.3, 6.5**

### Property 10: Output contract completeness

*For any* Booking_Group, the emitted Booking_Dict contains exactly the 24 contract fields (and no
ignored source column becomes a field), with `channel` equal to `airbnb`, `reservationCode` equal
to the group's `Bevestigingscode`, `listing` equal to `normalize_listing_name(Advertentie)`,
`guests` equal to `2`, and `phone` empty.

**Validates: Requirements 2.4, 7.1, 7.2, 8.1, 8.2, 8.3, 8.4, 9.1, 9.2**

### Property 11: Re-import is idempotent (keyed refresh)

*For any* set of Booking_Dicts within a given channel and administration, importing the set twice
results in the same number of persisted rows as importing it once — a Reservation_Code absent for
the channel and administration is inserted, and one that already exists is updated in place.

**Validates: Requirements 10.1, 10.2, 10.3**
