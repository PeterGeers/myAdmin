# Trip Import Preview Empty Fix — Bugfix Design

## Overview

The ZZP trip-import wizard (`Rittenregistratie` import) renders an empty Preview step
and leaves the Import action unusable even though `POST /api/zzp/trips/import` returns
`200 OK` with a populated body. There are three independent defect surfaces, all of which
this design addresses:

- **(a) Wizard contract (frontend).** The backend returns the validation result **flat**
  at the top level (`{ success, total_rows, valid, warnings, errors, rows, preview }`) and
  annotates each preview row with underscore-prefixed fields (`_row_number`, `_status`,
  `_messages`). The frontend reads the payload from a nested `resp.data` property and reads
  per-row `status` / `messages` / `row_number`, so the wizard stores `undefined` and renders
  nothing. The commit call also sends `{ vehicle_id, column_mapping }`, but the commit
  endpoint requires a non-empty `rows` list and ignores `column_mapping`.
- **(b) Date parser (backend).** `TripImportService._normalize_date` guards every branch on
  `len(date_str) == 10` with separators at fixed string positions, so a valid non-zero-padded
  Dutch date like `5-5-2026` (8 chars) is rejected on every branch and the row is flagged
  `_status = "error"` with "Ongeldig datumformaat". A real export of unambiguous dates then
  reports `valid = 0`.
- **(c) Excel handling (backend).** `TripImportService._read_dataframe` calls
  `pd.read_excel(file_stream, dtype=str)` with no `sheet_name`, so pandas reads only the
  **first** worksheet. When the mapped columns live on a later sheet (verified against the
  user's `Rittenregistratie.xlsx`, where the first sheet `Blad1` carries only five columns
  and the second sheet `ritten_import_template` holds the full data), every row fails the
  required-field check and the preview is all-error. On the correct sheet the Datum column
  holds real Excel datetime values (surfaced under `dtype=str` as strings like
  `2026-05-05 00:00:00`), which the surface-(b) parser does not accept, and mapped cells can
  carry Excel error markers (`#N/A`, `#REF!`, …) from unresolved XLOOKUP/`x.zoeken` formulas
  that are silently treated as ordinary values.

The strategy honors the **backend contract as the source of truth**. We do **not** change the
backend response shape or the backend validation semantics (other than widening the date
parser's accepted-input surface, selecting the correct worksheet, and flagging Excel error
markers). The frontend is adjusted to read the flat shape and the underscore-prefixed fields
the backend actually sends, and to send the validated `rows` on commit. The date parser is
redesigned to split on the separator and validate numeric ranges instead of relying on fixed
string length/positions, with no year inference and identical results for already-valid
inputs; it additionally accepts a datetime/date object or an ISO string carrying a time
component and keeps only the date portion. The Excel reader selects the first worksheet whose
header row contains the required mapped columns (failing clearly with a found-vs-expected
message when none does), and recognized Excel error markers in mapped cells flag the row as an
error naming the column and the marker. CSV uploads are single-sheet and unaffected.

## Glossary

- **Bug_Condition (C)**: The condition that triggers a bug. Three surfaces: (a) a successful
  import-validation response the wizard cannot map/render/commit; (b) a valid non-zero-padded
  numeric date `_normalize_date` currently rejects; (c) an Excel workbook whose first sheet
  lacks the mapped columns (so the wrong sheet is read), a datetime-valued date, or a mapped
  cell carrying an Excel error marker.
- **Property (P)**: The desired behavior. (a) populated preview state, rendered rows, enabled
  import, commit payload containing the validated rows; (b) the non-padded date normalizes to
  zero-padded `YYYY-MM-DD`; (c) the worksheet containing the mapped columns is selected (or a
  clear found-vs-expected failure is returned), datetime-valued dates normalize to the
  `YYYY-MM-DD` date portion, and error-marker cells flag the row as an error.
- **Preservation**: Existing behavior that must stay unchanged — upload-error handling, the
  disable-Import-when-no-valid-rows rule, step navigation gating, template download, and the
  backend's required-field / odometer-continuity / duplicate-detection / category-purpose
  validation; plus already-valid date parsing and rejection of truly invalid dates; plus
  single-sheet / first-sheet-matching reads, CSV parsing, extra-column filtering, and
  cached-formula-value reads on the Excel surface.
- **Mapped headers / required header set**: The file-column headers in the active mapping
  (`column_mapping` keys, else `DEFAULT_COLUMN_MAPPING` keys). The **required header set** is
  the subset of those keys whose internal field names are in `REQUIRED_IMPORT_FIELDS` — at
  minimum Datum, Vertrekadres, Bestemming, Begin KM, Eind KM, Categorie, Doel (Klant/Notities
  are optional). A worksheet "matches" when its stripped column set is a superset of the
  required header set.
- **`_read_dataframe`**: The static reader in
  `backend/src/services/zzp_trip_import_service.py` that turns a file stream + extension into a
  pandas DataFrame (semicolon-first/comma-fallback for CSV; `pd.read_excel` for `.xlsx`/`.xls`).
- **Excel error marker**: One of `#N/A`, `#REF!`, `#VALUE!`, `#NAME?`, `#DIV/0!`, `#NULL!`,
  `#NUM!` (and the general leading-`#…` Excel error form) — the cached value Excel saves for a
  broken/unresolved formula cell. Not evaluated by pandas; read as a literal string.
- **`importTrips` / `commitImport`**: Service functions in
  `frontend/src/services/tripService.ts` that call `POST /api/zzp/trips/import` and
  `POST /api/zzp/trips/import/commit`.
- **`ApiImportResponse`**: The TypeScript response type for the import endpoint in
  `tripService.ts` — currently nests fields under `data`.
- **`ImportRow`**: The per-row preview type in `frontend/src/types/zzpTrips.ts` — currently
  declares `row_number` / `status` / `messages`.
- **`ZZPTripImport`**: The wizard page component in `frontend/src/pages/ZZPTripImport.tsx`
  (holds `validationResult`, `handleNext`, `handleCommit`, `getStatusBadge`, `renderPreviewStep`).
- **`_normalize_date`**: The static date parser in
  `backend/src/services/zzp_trip_import_service.py` that normalizes a `trip_date` string to
  `YYYY-MM-DD` or returns `None`.
- **`validationResult`**: The wizard's React state holding the mapped validation payload used
  by the Preview and Import renderers.

## Bug Details

### Bug Condition

**Surface (a) — Wizard contract.** The bug manifests whenever `POST /api/zzp/trips/import`
returns a successful validation payload. The wizard reads it from a non-existent `resp.data`
property (storing `undefined`), reads non-existent per-row `status` / `messages` / `row_number`
fields, and on commit sends `column_mapping` instead of the validated `rows` the backend
requires.

**Surface (b) — Date parser.** The bug manifests whenever a `trip_date` is a valid
non-zero-padded numeric Dutch/ISO date (year always present) that is not exactly 10 characters
with separators at the fixed positions `_normalize_date` checks.

**Surface (c) — Excel handling.** The bug manifests in three ways on an uploaded `.xlsx`/`.xls`
workbook: (1) the **first** worksheet's stripped header row does not contain the required
mapped headers, yet another sheet does, because `_read_dataframe` reads only the first sheet
(no `sheet_name`) with no file-level feedback; (2) a mapped `trip_date` cell is a datetime/date
object or an ISO string carrying a time component (e.g. `2026-05-05 00:00:00`), which the
surface-(b) parser does not accept; (3) a mapped cell on the selected sheet carries an Excel
error marker (`#N/A`, `#REF!`, …) from an unresolved formula and is treated as an ordinary
value instead of being flagged.

**Formal Specification:**

```
FUNCTION isBugCondition(input)
  INPUT: input — an ImportResponse X (surface a), a trip_date value d (surface b/c),
                 or an Excel workbook wb (surface c)
  OUTPUT: boolean

  // Surface (a): wizard contract
  IF input is an ImportResponse X THEN
    RETURN X.success = true
           // frontend cannot map flat shape / underscore fields, and commit omits rows

  // Surface (b): date parser
  IF input is a trip_date string d THEN
    RETURN isValidNumericDutchOrIsoDate(d)   // D-M-YYYY, D/M/YYYY, or YYYY-M-D family;
                                             //   1<=month<=12, 1<=day<=31, year>=1900
           AND NOT isTenCharFixedPosition(d) // i.e. not already the zero-padded 10-char form

  // Surface (c): Excel handling
  IF input is an Excel workbook wb THEN
    RETURN NOT firstSheetContainsRequiredHeaders(wb)   // required header set from mapping keys
                                                       //   whose fields are REQUIRED_IMPORT_FIELDS
        OR someMappedCellIsDatetimeValued(wb)          // datetime/date obj or "YYYY-MM-DD HH:MM:SS"
        OR someMappedCellIsErrorMarker(wb)             // in { #N/A, #REF!, #VALUE!, #NAME?,
                                                       //   #DIV/0!, #NULL!, #NUM! }
END FUNCTION
```

### Examples

- `POST /api/zzp/trips/import` → `200 OK` `{ success:true, total_rows:12, valid:12, ... }`.
  Expected: Preview shows "Totaal: 12 / Geldig: 12" and 12 rows. Actual: Preview is empty
  (reads `resp.data`, which is `undefined`). (Requirements 1.1, 1.2)
- A preview row `{ _row_number:1, _status:"ok", _messages:[] }`. Expected: a green "OK" badge.
  Actual: badge color/label resolve from undefined `status`. (Requirement 1.4)
- Commit sends `{ vehicle_id, column_mapping:{} }`. Expected: backend imports valid rows.
  Actual: backend returns `400 "rows must be a non-empty list"`. (Requirement 1.5)
- `_normalize_date("5-5-2026")`. Expected: `"2026-05-05"`. Actual: `None` → row error
  "Ongeldig datumformaat" (8 chars fails the fixed-position guard). (Requirement 4.1)
- `_normalize_date("5/5/2026")`. Expected: `"2026-05-05"`. Actual: `None`. (Requirement 4.2)
- Edge: `_normalize_date("17-5-2026")`. Expected: `"2026-05-17"`. Actual: `None` (9 chars).
  (Requirements 4.1, 4.3)
- `Rittenregistratie.xlsx` with `Blad1` (first, 5 columns) + `ritten_import_template` (second,
  all 9 mapped headers). Expected: the reader selects `ritten_import_template` and its 17 rows
  validate normally. Actual: only `Blad1` is read, so every row is "Verplicht veld ontbreekt"
  for Datum/Bestemming/Begin KM/Eind KM → `valid = 0`. (Requirements 7.1, 7.2, 8.1, 8.2)
- A workbook where no sheet contains the required headers. Expected: `success: false` with a
  message naming the columns found and the columns expected; wizard stays on Upload. Actual:
  silent fallback to the first sheet → empty/all-error preview. (Requirements 7.1, 8.3)
- `_normalize_date("2026-05-05 00:00:00")`. Expected: `"2026-05-05"`. Actual: `None` (13+ chars,
  fails the fixed-position guard). Likewise a `datetime.date(2026, 5, 5)` object. (Requirements
  7.3, 8.4)
- A mapped Datum cell equal to `"#N/A"`. Expected: the row is flagged `_status = "error"` with
  "Formulewaarde niet berekend: '#N/A' in kolom trip_date". Actual: treated as an ordinary
  string, producing a generic required-field/format error with no indication of the real cause.
  (Requirements 7.4, 8.5)

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**

- Upload failure (`success: false`) still shows the upload-failed error toast and keeps the
  user on the Upload step. (Requirement 3.1)
- The Import button stays disabled whenever `valid === 0`. (Requirement 3.2)
- Step navigation gating is unchanged: Back disabled on Upload, only Back on the final Import
  step. (Requirement 3.3)
- Backend `validate_import` keeps the existing required-field, date, odometer-continuity, and
  duplicate-detection validation, returning the same per-row status counts for inputs that were
  already valid. (Requirement 3.4)
- The CSV template download is unchanged. (Requirement 3.5)
- `_normalize_date` still rejects missing-year (`5-5`), non-numeric (`5-mei`), and out-of-range
  (`32-5-2026`, `5-13-2026`) dates, and still produces the identical normalized result for
  already-zero-padded inputs. (Requirements 6.1–6.4)
- Downstream validation after date parsing (required-field, odometer-continuity, duplicate,
  category/purpose warnings) is unchanged. (Requirement 6.5)
- A single-sheet workbook, or one whose first sheet already contains the mapped headers, still
  reads that same (first) sheet as before — header-match selects the first matching sheet.
  (Requirement 9.1)
- CSV files still parse via the existing semicolon-first, comma-fallback logic, unaffected by
  worksheet selection. (Requirement 9.2)
- Unmapped / extra trailing columns (e.g. stray `Unnamed` columns) are still ignored.
  (Requirement 9.3)
- Surface-(b) date behavior is unchanged: non-padded numeric / ISO dates still normalize
  identically and truly-invalid dates are still rejected. (Requirement 9.4)
- Formula "view" cells with a valid cached computed value are still read as that cached value
  via pandas (no formula evaluation, no new handling); a formula cell that reads as plain
  empty/None still falls through to the existing required-field check. (Requirements 9.5, 9.6)

**Scope:**

All inputs that are NOT (a) a successful import response, (b) a valid non-zero-padded numeric
date, or (c) an Excel workbook whose first sheet lacks the mapped headers / a datetime-valued
date / an error-marker cell should be completely unaffected. This includes:

- Failed/`success:false` import responses (upload errors).
- Already-zero-padded dates and ISO dates (same normalized result as before).
- Truly invalid dates (still rejected, same error, same `_status = "error"`).
- Single-sheet / first-sheet-matching workbooks, CSV uploads, extra columns, and valid cached
  formula values (all unchanged).

> The expected *correct* behavior is defined in the Correctness Properties section
> (Property 1 for each surface). This section documents what must NOT change.

## Hypothesized Root Cause

**Surface (a) — Wizard contract.** The frontend types were written against an assumed envelope
shape rather than the actual backend contract.

1. **Nested-vs-flat envelope mismatch.** `ApiImportResponse` declares a nested `data` object
   and `ZZPTripImport.handleNext` reads `resp.data`; the backend returns the fields flat at the
   top level. `resp.data` is `undefined`, so `validationResult` is `null` and both renderers
   short-circuit. (Requirements 1.1, 1.2, 1.3)
2. **Per-row field naming mismatch.** `ImportRow` declares `row_number` / `status` / `messages`;
   the backend annotates rows with `_row_number` / `_status` / `_messages`. `getStatusBadge`
   and the Preview table read the unprefixed names and get `undefined`. (Requirement 1.4)
3. **Commit payload mismatch.** `commitImport` and `handleCommit` send
   `{ vehicle_id, column_mapping }`; the commit route requires a non-empty `rows` list and
   ignores `column_mapping`. (Requirement 1.5)

**Surface (b) — Date parser.** `_normalize_date` encodes the format check as fixed string
positions (`len == 10`, `date_str[2]`/`date_str[5]`, `date_str[4]`/`date_str[7]`). This conflates
"zero-padded" with "valid", so any non-padded component (fewer than 10 chars) fails before the
numeric-range check runs. The fix is to detect the separator, split, and validate numeric ranges
regardless of component width. (Requirements 4.1–4.3)

**Surface (c) — Excel handling.** Three distinct root causes on the same reader surface:

1. **First-sheet-only read.** `_read_dataframe` calls `pd.read_excel(file_stream, dtype=str)`
   with no `sheet_name`, so pandas defaults to the first worksheet. A multi-sheet workbook whose
   data lives on a later sheet (or any workbook whose first sheet lacks the headers) is read from
   the wrong sheet, and the required-field check then flags every row. The reader has no notion of
   which columns are expected because `_read_dataframe` currently takes only `(file_stream, ext)`
   and does not receive the mapping. The fix must give the selection logic the required header
   set — either by passing it into `_read_dataframe`, or by performing selection in `parse_file`
   where `mapping` is already available — and read all sheets
   (`pd.read_excel(file_stream, sheet_name=None, dtype=str)`), picking the first whose stripped
   header set is a superset of the required headers, failing clearly when none matches.
   (Requirements 7.1, 7.2, 8.1, 8.2, 8.3)
2. **Datetime-valued dates.** Even with `dtype=str`, Excel datetime cells surface as strings
   carrying a time component (`2026-05-05 00:00:00`), and defensively a real `datetime`/`date`
   object can arrive. The fixed-position `_normalize_date` cannot parse either. The fix is to
   split off a leading date token (on whitespace or `T`) and tolerate a `datetime`/`date` object
   before the existing separator/range logic runs. (Requirements 7.3, 8.4)
3. **Unflagged error markers.** A broken/unresolved formula (XLOOKUP / `x.zoeken`) leaves an
   Excel error marker (`#N/A`, `#REF!`, …) as the cached cell value. pandas reads it as a literal
   string, so it masquerades as a generic required-field/format error. The fix is a per-cell check
   during row cleaning/validation that recognizes the marker set and flags the row with a specific
   message naming the column and the marker — never evaluating the formula. (Requirements 7.4, 8.5)

## Correctness Properties

Property 1: Bug Condition — Wizard maps/renders/commits a successful import response

_For any_ import response where the bug condition holds (`X.success = true`), the fixed wizard
SHALL map the flat top-level fields into a populated validation state, render the summary counts
and preview rows (reading the underscore-prefixed `_row_number` / `_status` / `_messages`), enable
the Import button exactly when `valid > 0`, and send a commit payload containing the validated
`rows` (plus `vehicle_id`) that the commit endpoint requires.

**Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5**

Property 2: Preservation — Non-successful responses and wizard gating unchanged

_For any_ input where the wizard bug condition does NOT hold (e.g. `X.success = false`), the fixed
wizard SHALL produce the same result as the original: the same upload-failed error toast, the user
kept on the Upload step, the Import button disabled when `valid === 0`, and the same step
navigation gating.

**Validates: Requirements 3.1, 3.2, 3.3, 3.5**

Property 3: Bug Condition — Non-padded numeric dates normalize correctly

_For any_ `trip_date` where the parser bug condition holds (a valid non-zero-padded numeric
Dutch/ISO date), the fixed `_normalize_date` SHALL return the zero-padded `YYYY-MM-DD` form
(e.g. `5-5-2026` → `2026-05-05`, `17-5-2026` → `2026-05-17`), matching `/^\d{4}-\d{2}-\d{2}$/`,
with no year inference.

**Validates: Requirements 5.1, 5.2, 5.3, 5.4**

Property 4: Preservation — Already-valid dates unchanged, invalid dates still rejected

_For any_ `trip_date` where the parser bug condition does NOT hold, the fixed `_normalize_date`
SHALL produce the same result as the original: already-zero-padded / ISO inputs normalize to the
identical `YYYY-MM-DD`, and missing-year / non-numeric / out-of-range inputs are still rejected
(return `None` → "Ongeldig datumformaat", `_status = "error"`). Downstream validation
(required-field, odometer-continuity, duplicate, category/purpose) is unchanged.

**Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.5**

Property 5: Bug Condition — Correct worksheet selected (or clear failure), datetime dates normalize, error markers flagged

_For any_ Excel workbook where the surface-(c) bug condition holds, the fixed import SHALL: (1)
when the first worksheet lacks the required mapped headers but another sheet contains them, read
the first worksheet whose stripped header set is a superset of the required header set, so its
rows validate normally; (2) when no worksheet contains the required headers, return
`success: false` with an error message naming both the columns found and the columns expected,
without silently falling back to the first sheet; (3) normalize a `trip_date` that is a
datetime/date object or an ISO string carrying a time component (e.g. `2026-05-05 00:00:00`) to
the zero-padded `YYYY-MM-DD` date portion only; and (4) when a mapped cell equals a recognized
Excel error marker (`#N/A`, `#REF!`, `#VALUE!`, `#NAME?`, `#DIV/0!`, `#NULL!`, `#NUM!`), flag
that row `_status = "error"` with a specific message naming the column and the marker, never
evaluating the formula.

**Validates: Requirements 8.1, 8.2, 8.3, 8.4, 8.5**

Property 6: Preservation — Single-sheet/first-match/CSV identical, extra columns ignored, cached formula values and empty/None unchanged

_For any_ input where the surface-(c) bug condition does NOT hold, the fixed import SHALL produce
the same result as the original: a single-sheet workbook or one whose first sheet already
contains the mapped headers reads the same (first) sheet as before; CSV files parse via the
existing semicolon-first/comma-fallback logic unaffected by worksheet selection; unmapped / extra
trailing columns are still ignored; formula cells with a valid cached computed value are still
read as that cached value via pandas with no formula evaluation; and a mapped cell that is plain
empty/None (including an unresolved formula that reads as empty) is still handled by the existing
required-field check. Surface-(b) date behavior is unchanged.

**Validates: Requirements 9.1, 9.2, 9.3, 9.4, 9.5, 9.6**

## Fix Implementation

### Changes Required

Assuming our root-cause analysis is correct. The backend response shape is the source of truth
and is NOT changed; the frontend is aligned to it, and the backend parser's accepted-input
surface is widened.

#### Change 1 — Flat import response type and mapping (Requirements 2.1, 2.2, 2.3)

**File**: `frontend/src/services/tripService.ts`
**Type**: `ApiImportResponse`

**Before intent**: fields nested under `data` (`{ success, data: { total_rows, valid, warnings,
errors, preview } }`), missing `rows`.
**After intent**: fields flat at the top level, matching the backend:

```ts
interface ApiImportResponse {
  success: boolean;
  total_rows: number;
  valid: number;
  warnings: number;
  errors: number;
  rows: ImportRow[];       // full validated set (used by commit)
  preview: ImportRow[];    // first 20 rows for display
  message?: string;
  error?: string;
}
```

**File**: `frontend/src/pages/ZZPTripImport.tsx`
**Function**: `handleNext` (Upload → Preview branch)

**Before intent**: `setValidationResult(resp.data as unknown as ImportValidationResult)`.
**After intent**: build the state from the flat fields and store `rows` so commit can use them:

```ts
setValidationResult({
  total_rows: resp.total_rows,
  valid: resp.valid,
  warnings: resp.warnings,
  errors: resp.errors,
  preview: resp.preview,
  rows: resp.rows,
});
```

Extend the local `ImportValidationResult` interface with `rows: ImportRow[]` so the commit step
has the full validated set.

#### Change 2 — Read underscore-prefixed per-row fields (Requirement 2.4)

**File**: `frontend/src/types/zzpTrips.ts`
**Type**: `ImportRow`

**Before intent**: `row_number`, `status`, `messages`.
**After intent**: match the backend annotations:

```ts
export interface ImportRow {
  _row_number: number;
  trip_date: string;
  start_address: string;
  end_address: string;
  start_odometer: number;
  end_odometer: number;
  trip_category?: string;
  trip_purpose?: string;
  contact_name?: string;
  notes?: string;
  _status: 'ok' | 'warning' | 'error';
  _messages: string[];
}
```

**File**: `frontend/src/pages/ZZPTripImport.tsx`
**Function**: `getStatusBadge` and `renderPreviewStep` table body.

**Before intent**: reads `row.status`, `row.messages`, `row.row_number`.
**After intent**: reads `row._status`, `row._messages`, `row._row_number`:

```ts
const getStatusBadge = (row: ImportRow) => {
  const colorMap = { ok: 'green', warning: 'yellow', error: 'red' };
  const labelMap = { ok: 'OK', warning: 'Waarschuwing', error: 'Fout' };
  return (
    <Tooltip
      label={row._messages?.length > 0 ? row._messages.join('\n') : 'Geen opmerkingen'}
      placement="top" hasArrow
    >
      <Badge colorScheme={colorMap[row._status]} cursor="pointer">{labelMap[row._status]}</Badge>
    </Tooltip>
  );
};
```

In the table body, replace `row.row_number` with `row._row_number`.

#### Change 3 — Commit sends validated rows (Requirement 2.5)

**File**: `frontend/src/services/tripService.ts`
**Function**: `commitImport`

**Before intent**: `commitImport(vehicleId, mapping: ColumnMapping)` sending
`{ vehicle_id, column_mapping }`.
**After intent**: send the validated rows the backend requires, with optional
`skip_error_rows` (the backend already supports it):

```ts
export async function commitImport(
  vehicleId: number,
  rows: ImportRow[],
  skipErrorRows = true,
): Promise<ApiResponse & { imported?: number; skipped?: number }> {
  const resp = await authenticatedPost(buildEndpoint(`${BASE}/import/commit`), {
    vehicle_id: vehicleId,
    rows,
    skip_error_rows: skipErrorRows,
  });
  return resp.json();
}
```

**File**: `frontend/src/pages/ZZPTripImport.tsx`
**Function**: `handleCommit`

**Before intent**: builds an empty `ColumnMapping` and calls `commitImport(selectedVehicle,
mapping)`.
**After intent**: pass the validated rows from state:

```ts
const resp = await commitImport(selectedVehicle, validationResult?.rows ?? [], true);
```

Setting `skip_error_rows = true` matches the wizard's displayed promise ("Rijen met fouten worden
overgeslagen"). `ColumnMapping` may remain exported for the service's other needs; it is no longer
used by the commit call.

#### Change 4 — Range-based date normalization (Requirements 5.1, 5.2, 5.3, 5.4)

**File**: `backend/src/services/zzp_trip_import_service.py`
**Function**: `TripImportService._normalize_date` (staticmethod)

**Before intent**: three branches each guarded by `len(date_str) == 10` and fixed separator
positions; non-padded components (fewer than 10 chars) fall through to `return None`.
**After intent**: detect the separator, split into exactly three numeric parts, infer the ordering
(ISO when the first part is 4 digits, otherwise day-month-year), validate numeric ranges, and
return the zero-padded ISO form. No fixed length/position checks; no year inference.

```
FUNCTION _normalize_date(date_str)
  IF date_str is falsy OR not a string: RETURN None
  date_str := date_str.strip()

  // choose separator: '-' or '/' (reject if neither / mixed)
  IF '-' in date_str: sep := '-'
  ELSE IF '/' in date_str: sep := '/'
  ELSE: RETURN None

  parts := date_str.split(sep)
  IF len(parts) != 3: RETURN None
  IF any part is empty OR not all-digits: RETURN None   // rejects "5-mei", "5-5" (len 2)

  // ISO when first component is 4 digits (YYYY-M-D); else Dutch day-month-year
  IF len(parts[0]) == 4:
    year, month, day := int(parts[0]), int(parts[1]), int(parts[2])
  ELSE:
    day, month, year := int(parts[0]), int(parts[1]), int(parts[2])

  IF 1 <= month <= 12 AND 1 <= day <= 31 AND year >= 1900:
    RETURN format "%04d-%02d-%02d" % (year, month, day)
  RETURN None
END FUNCTION
```

Notes:

- "all-digits" (`str.isdigit`) rejects non-numeric components (`5-mei`) and signed/decimal forms.
- `len(parts) != 3` rejects missing-year (`5-5` → 2 parts) and keeps the existing rejection.
- Range checks preserve rejection of `32-5-2026` / `5-13-2026`.
- Already-padded/ISO inputs flow through the same branches and produce the identical result, so
  Preservation holds.
- The error message in `_validate_date_format` is unchanged (still lists
  `YYYY-MM-DD, DD-MM-YYYY, of DD/MM/YYYY`); only the accepted-input surface widens.

#### Change 5 — Header-matching worksheet selection (Requirements 8.1, 8.2, 8.3; preservation 9.1, 9.2, 9.3)

**File**: `backend/src/services/zzp_trip_import_service.py`
**Functions**: `_read_dataframe` (staticmethod) and `parse_file`

**Before intent**: `_read_dataframe(file_stream, ext)` reads CSV with semicolon-first /
comma-fallback and reads Excel with `pd.read_excel(file_stream, dtype=str)` — no `sheet_name`,
so pandas returns the first worksheet. `_read_dataframe` does not know the column mapping.

**After intent**: give the Excel branch the required header set and have it scan all sheets and
select the first that matches. The required header set is computed from `mapping` (already
resolved in `parse_file` as `column_mapping or DEFAULT_COLUMN_MAPPING`): the mapping keys whose
internal field names are in `REQUIRED_IMPORT_FIELDS` (Datum, Vertrekadres, Bestemming, Begin KM,
Eind KM, Categorie, Doel — Klant/Notities are optional and excluded). The CSV path is unchanged.

Signature/flow: pass the required header set into `_read_dataframe` as a new optional argument,
so the single call site in `parse_file` supplies it and the CSV path ignores it:

```
FUNCTION _read_dataframe(file_stream, ext, required_headers=None)
  IF ext == ".csv":
    ... existing semicolon-first / comma-fallback logic UNCHANGED ...   # single-sheet, 9.2
    RETURN df
  ELSE IF ext in (".xlsx", ".xls"):
    sheets := pd.read_excel(file_stream, sheet_name=None, dtype=str)    # ordered dict name->df
    IF required_headers is falsy:                                       # defensive: old behavior
      RETURN first sheet's df
    FOR sheet_name, sheet_df IN sheets.items():                        # insertion order
      stripped := { str(c).strip() FOR c IN sheet_df.columns }
      IF required_headers ⊆ stripped:                                   # superset match
        RETURN sheet_df                                                 # first matching sheet, 8.1/8.2
    RAISE SheetSelectionError(found=<union/per-sheet columns>, expected=required_headers)
  ELSE:
    RAISE ValueError(...)                                               # unchanged
END FUNCTION
```

In `parse_file`, compute the required header set and pass it in; translate the no-match failure
into the standard `success: false` envelope with a found-vs-expected message (no silent fallback):

```
mapping := column_mapping or DEFAULT_COLUMN_MAPPING
required_headers := { file_col FOR file_col, field IN mapping.items()
                      IF field IN REQUIRED_IMPORT_FIELDS }
try:
  df := _read_dataframe(file_stream, ext, required_headers)
except SheetSelectionError as e:                       # NO match on any sheet (8.3)
  return { success: false, rows: [], total_rows: 0,
           columns_found: e.found, columns_mapped: [], unmapped_columns: [],
           error: "Geen werkblad met de verwachte kolommen gevonden. "
                  "Gevonden kolommen: {e.found}. Verwachte kolommen: {sorted(required_headers)}." }
except Exception as e:
  ... existing "Could not read file" branch UNCHANGED ...
```

Notes:

- The existing header-strip (`df.columns = [str(col).strip() ...]`) and column-mapping /
  `unmapped_columns` logic in `parse_file` run unchanged on the selected sheet; matching
  compares against the **same** stripped headers so a single-sheet or first-matching workbook
  selects exactly the sheet pandas returned before (Requirement 9.1), and extra/`Unnamed`
  columns are still ignored (Requirement 9.3).
- `required_headers ⊆ stripped` means "the sheet has at least the required columns"; optional
  columns (Klant/Notities) do not affect selection.
- `SheetSelectionError` is a small internal exception (module-private); `parse_file` catches it
  *before* the generic `except Exception` so the clear found-vs-expected message is not masked by
  the "Could not read file" branch. CSV never raises it (single-sheet path returns directly).

#### Change 6 — Datetime-aware date normalization (Requirement 8.4; preservation 9.4)

**File**: `backend/src/services/zzp_trip_import_service.py`
**Function**: `TripImportService._normalize_date` (staticmethod)

**Before intent**: after Change 4, `_normalize_date` accepts a string date and splits on the
separator; it does not accept a datetime/date object or a string carrying a time component.

**After intent**: at the top of the function, coerce a `datetime`/`date` object and strip any
time component from a string, then fall through to the Change-4 separator/range logic:

```
FUNCTION _normalize_date(date_value)
  IF date_value is falsy: RETURN None

  // (c) datetime/date object → ISO date portion directly
  IF date_value is a datetime OR date:
    RETURN date_value.strftime("%Y-%m-%d")           # e.g. date(2026,5,5) -> "2026-05-05"

  IF not isinstance(date_value, str): RETURN None
  s := date_value.strip()

  // (c) strip a trailing time component: take the leading date token
  //     "2026-05-05 00:00:00" -> "2026-05-05"; "2026-05-05T00:00:00" -> "2026-05-05"
  s := split(s, on whitespace or 'T')[0]

  ... Change-4 separator detection, 3-part split, numeric-range validation UNCHANGED ...
END FUNCTION
```

Notes:

- Taking the leading token before separator logic means a pure date string (no time) is
  unaffected, so Change-4 / surface-(b) behavior is identical for all surface-(b) inputs
  (Requirement 9.4). The split only ever removes a trailing ` HH:MM:SS` or `THH:MM:SS`.
- No timezone or time semantics are applied, and no year inference is introduced — only the
  date portion is kept.
- `_validate_date_format` already calls `self._normalize_date(str(date_value))`; the `str(...)`
  wrapper is harmless for strings. To let an actual `datetime`/`date` object reach the object
  branch, `_validate_date_format` passes the raw `date_value` through (the `isinstance` guards in
  `_normalize_date` handle both forms), and its "Ongeldig datumformaat" message is unchanged.

#### Change 7 — Excel error-marker detection (Requirement 8.5; preservation 9.5, 9.6)

**File**: `backend/src/services/zzp_trip_import_service.py`
**Function**: a new per-cell check invoked during row validation (e.g. `_validate_error_markers`,
called from `validate_import`'s Phase-1 per-row loop alongside `_validate_required_fields`)

**Before intent**: a mapped cell carrying an Excel error marker is treated as an ordinary string
and surfaces only as a generic required-field/format error.

**After intent**: recognize the marker set and flag the row with a specific, column-naming
message. Define the marker set as a module constant and check only **mapped** cells:

```
EXCEL_ERROR_MARKERS := { "#N/A", "#REF!", "#VALUE!", "#NAME?", "#DIV/0!", "#NULL!", "#NUM!" }

FUNCTION isExcelErrorMarker(value)
  IF not isinstance(value, str): RETURN False
  v := value.strip()
  RETURN v IN EXCEL_ERROR_MARKERS
         OR (v startswith "#" AND v endswith ("!" or "?"))   # general leading-'#...' error form

FUNCTION _validate_error_markers(row)
  FOR field IN mapped internal field names present in row:    # skip _-prefixed helper keys
    value := row.get(field)
    IF isExcelErrorMarker(value):
      row["_messages"].append(
        "Formulewaarde niet berekend: '{value}' in kolom {field}")   # e.g. ... in kolom trip_date
      row["_status"] = "error"
END FUNCTION
```

Wire-in: call `self._validate_error_markers(row)` in the Phase-1 loop in `validate_import`
(before or alongside the existing `_validate_required_fields` / `_validate_date_format` calls),
so the row is flagged `error` regardless of what the other checks conclude.

Notes:

- Formulas are never evaluated — only the cached marker string pandas returns is inspected
  (Requirement 9.5). A valid cached formula value is an ordinary value and is unaffected
  (Requirement 9.6).
- A plain empty/None cell is NOT an error marker (`isExcelErrorMarker` requires a `#…` string),
  so an unresolved formula that reads as empty continues to be handled by the existing
  required-field check (Requirement 9.6).
- The message prefers the internal field name (`trip_date`); the original header could be used
  instead if the mapping is threaded through, but the internal name is already on the row and is
  stable across mappings.

## Testing Strategy

### Validation Approach

Two-phase approach per surface: first surface counterexamples that demonstrate the bug on
unfixed code, then verify the fix works and preserves existing behavior. The backend parser and
reader are pure/DB-free and get direct `pytest` unit tests; the wizard mapping is verified at the
frontend level (mapping/render/commit-payload) against the fixed service types.

Backend tests live under `backend/tests/unit/` (auto-marked `unit`), following the existing
`test_zzp_trip_import_validate.py` / `test_zzp_trip_import_commit.py` /
`test_zzp_trip_import_service.py` conventions: `sys.path` insert of `src`, a `mock_db` fixture
returning no existing trips, `TripImportService(db=mock_db)`, and the
`test_{function}_{scenario}_{expected}` naming format. Add parser cases to a new or existing
`backend/tests/unit/test_zzp_trip_import_validate.py` test class (e.g. `TestNormalizeDate`), since
`_normalize_date` is reachable as `TripImportService._normalize_date` without a DB. Add the
surface-(c) sheet-selection and error-marker cases to
`backend/tests/unit/test_zzp_trip_import_service.py` (the parse/read surface), using the same
`mock_db` fixture and `TripImportService(db=mock_db)` for `parse_file` / `validate_import`.

Surface-(c) tests construct **in-memory** workbooks with `pandas.ExcelWriter` (openpyxl engine)
writing to an `io.BytesIO()`, then rewind (`buf.seek(0)`) and pass the buffer plus a filename
ending in `.xlsx` to `parse_file`. `pandas` and `openpyxl` are already backend dependencies (the
service imports `pandas as pd` and reads Excel). CSV cases build an `io.BytesIO`/`io.StringIO`
with semicolon-separated text, unchanged from existing CSV tests.

Run: `cd backend && source .venv/bin/activate && pytest tests/unit/test_zzp_trip_import_validate.py tests/unit/test_zzp_trip_import_service.py -v`.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate each bug BEFORE implementing the fix, and
confirm the root-cause analysis.

**Test Plan**: Call `TripImportService._normalize_date` directly on non-padded inputs on the
UNFIXED code and assert the (wrong) `None` result to document the defect; for the wizard, assert
that mapping `resp.data` from a flat response yields `undefined` (the empty-preview cause).

**Test Cases**:
1. **Hyphen non-padded** — `_normalize_date("5-5-2026")` returns `None` on unfixed code
   (should become `"2026-05-05"`). (will fail after fix is applied → becomes the fix test)
2. **Slash non-padded** — `_normalize_date("5/5/2026")` returns `None` on unfixed code.
3. **Mixed-width** — `_normalize_date("17-5-2026")` returns `None` on unfixed code.
4. **Wizard mapping** — a flat `{ success:true, total_rows:3, ... }` read as `resp.data` is
   `undefined`, producing a null validation state and an empty preview.
5. **Wrong-sheet read** — build a workbook whose first sheet `Blad1` has only
   [Vertrekadres, Categorie, Doel] and a second sheet with all required headers + data; on
   unfixed code `parse_file` reads `Blad1`, so `validate_import` reports every row
   "Verplicht veld ontbreekt" and `valid == 0`.
6. **Datetime-valued date** — `_normalize_date("2026-05-05 00:00:00")` returns `None` on unfixed
   code (and `_normalize_date(datetime.date(2026, 5, 5))` would raise/return `None`).
7. **Error marker** — a row with a mapped `trip_date` cell of `"#N/A"` on unfixed code produces
   only a generic "Ongeldig datumformaat" error, with no indication the cause is an unresolved
   formula.

**Expected Counterexamples**:
- `_normalize_date` returns `None` for non-padded numeric dates purely due to the fixed
  length/position guard.
- The wizard stores `undefined` because the fields are flat, not nested under `data`.
- `parse_file` reads only the first worksheet (no `sheet_name`), so required columns on a later
  sheet are never seen.
- `_normalize_date` returns `None` for `"2026-05-05 00:00:00"` (13+ chars) and does not accept a
  datetime/date object.
- An Excel error-marker cell passes through as an ordinary string, masquerading as a
  required-field/format error.

### Fix Checking

**Goal**: For all inputs where the bug condition holds, the fixed function produces the expected
behavior.

**Pseudocode:**

```
// Surface (b) parser
FOR ALL d WHERE isBugCondition_parser(d) DO
  ASSERT _normalize_date_fixed(d) = zeroPaddedIso(d)
     AND result MATCHES /^\d{4}-\d{2}-\d{2}$/
END FOR

// Surface (a) wizard
FOR ALL X WHERE X.success = true DO
  state := mapResponseToPreviewState_fixed(X)
  ASSERT state IS NOT null
     AND state.total_rows = X.total_rows AND state.preview = X.preview
     AND previewRendersRows(state)
     AND importButtonEnabled(state) = (state.valid > 0)
     AND commitPayload_fixed(state) CONTAINS state.rows
END FOR

// Surface (c) Excel reader
FOR ALL wb WHERE isBugCondition_sheet(wb) DO
  IF NOT firstSheetContainsRequiredHeaders(wb) THEN
    IF someSheetContainsRequiredHeaders(wb) THEN
      result := parse_file_fixed(wb)
      ASSERT result.success = true
         AND selectedSheet(result) = firstSheetContainingRequiredHeaders(wb)
    ELSE
      result := parse_file_fixed(wb)
      ASSERT result.success = false
         AND result.error NAMES columnsFound(wb)
         AND result.error NAMES columnsExpected(wb)   // no silent first-sheet fallback
    END IF
  END IF
END FOR
FOR ALL d WHERE d is datetime-valued DO                // "2026-05-05 00:00:00" or date obj
  ASSERT _normalize_date_fixed(d) = "2026-05-05"
END FOR
FOR ALL (row, col) WHERE isExcelErrorMarker(cell(row, col)) DO
  ASSERT rowStatus_fixed(row) = "error"
     AND rowMessage_fixed(row) NAMES col AND NAMES cell(row, col)
     AND NOT formulaEvaluated(result)
END FOR
```

**Surface (c) accepted datetime-valued dates (expected normalized output):**

| Input                     | Expected output | Requirement |
| ------------------------- | --------------- | ----------- |
| `"2026-05-05 00:00:00"`   | `2026-05-05`    | 8.4         |
| `"2026-05-05T00:00:00"`   | `2026-05-05`    | 8.4         |
| `datetime.date(2026,5,5)` | `2026-05-05`    | 8.4         |
| `datetime(2026,5,5,0,0)`  | `2026-05-05`    | 8.4         |

**Backend accepted non-padded inputs (expected normalized output):**

| Input         | Expected output | Requirement |
| ------------- | --------------- | ----------- |
| `5-5-2026`    | `2026-05-05`    | 5.1         |
| `3-6-2026`    | `2026-06-03`    | 5.1         |
| `17-5-2026`   | `2026-05-17`    | 5.1         |
| `5-12-2026`   | `2026-12-05`    | 5.1         |
| `5/5/2026`    | `2026-05-05`    | 5.2         |
| `3/6/2026`    | `2026-06-03`    | 5.2         |
| `17/5/2026`   | `2026-05-17`    | 5.2         |
| `2026-5-5`    | `2026-05-05`    | 5.3 (ISO non-padded) |

### Preservation Checking

**Goal**: For all inputs where the bug condition does NOT hold, the fixed function produces the
same result as the original.

**Pseudocode:**

```
// Surface (b) parser
FOR ALL d WHERE NOT isBugCondition_parser(d) DO
  ASSERT _normalize_date_original(d) = _normalize_date_fixed(d)
END FOR

// Surface (a) wizard
FOR ALL X WHERE X.success = false DO
  ASSERT wizard_original(X) = wizard_fixed(X)   // same error toast, step, gating
END FOR

// Surface (c) Excel reader
FOR ALL wb WHERE NOT isBugCondition_sheet(wb) DO
  ASSERT parse_file_original(wb) = parse_file_fixed(wb)
  // single-sheet / first-sheet-match workbooks -> same (first) sheet selected
  // CSV uploads -> semicolon-first/comma-fallback path, unaffected by selection
  // unmapped / extra (Unnamed) columns -> still ignored
  // valid cached formula values -> read as that value via pandas (no evaluation)
  // plain empty/None cells -> still caught by the required-field check
END FOR
```

**Testing Approach**: Table-driven unit tests cover the enumerable date domain precisely; this
is preferred over randomized property testing here because the accepted/rejected sets are small
and fully specified, and exact expected outputs make regressions obvious. (Hypothesis-style
property testing exists elsewhere in `backend/tests` and could be added later to assert the
`/^\d{4}-\d{2}-\d{2}$/` shape across generated valid dates, but is not required for this fix.)

**Backend preserved already-valid inputs (identical result as before):**

| Input         | Expected output | Requirement |
| ------------- | --------------- | ----------- |
| `05-05-2026`  | `2026-05-05`    | 6.4         |
| `15-01-2026`  | `2026-01-15`    | 6.4         |
| `2026-05-05`  | `2026-05-05`    | 6.4         |
| `05/05/2026`  | `2026-05-05`    | 6.4         |

**Backend rejected invalid inputs (still `None` → error):**

| Input         | Reason                | Requirement |
| ------------- | --------------------- | ----------- |
| `5-5`         | missing year (2 parts)| 6.1         |
| `2026`        | missing parts         | 6.1         |
| `5-mei`       | non-numeric component | 6.2         |
| `5-mei-2026`  | non-numeric component | 6.2         |
| `32-5-2026`   | day out of range      | 6.3         |
| `5-13-2026`   | month out of range    | 6.3         |
| `0-5-2026`    | day out of range      | 6.3         |
| `5-5-1899`    | year < 1900           | 6.3/6.4     |
| `""` / `None` | empty / non-string    | 6.1         |

**Surface (c) preserved reads (identical result as before):**

| Scenario                                            | Expectation                                  | Requirement |
| --------------------------------------------------- | -------------------------------------------- | ----------- |
| Single-sheet `.xlsx` whose only sheet has headers   | selects that (first) sheet, same rows        | 9.1         |
| Multi-sheet `.xlsx` whose first sheet has headers   | selects the first sheet (unchanged)          | 9.1         |
| Semicolon CSV                                        | parsed by existing CSV path, unaffected      | 9.2         |
| Sheet with extra / `Unnamed` trailing columns        | extra columns ignored, as today              | 9.3         |
| Mapped cell with a valid cached formula value       | read as that value via pandas (no eval)      | 9.5, 9.6    |
| Mapped cell plain empty/None (incl. unresolved→empty)| still caught by required-field check only    | 9.6         |

**Wizard preservation test cases**:
1. **Upload error** — `importTrips` resolves `{ success:false }`: wizard shows the upload-failed
   toast and stays on the Upload step. (Requirement 3.1)
2. **Zero valid rows** — mapped state `valid === 0`: Import button is disabled. (Requirement 3.2)
3. **Navigation gating** — Back disabled on Upload; only Back shown on the Import step.
   (Requirement 3.3)
4. **Template download** — unchanged behavior. (Requirement 3.5)

### Unit Tests

- Backend `_normalize_date`: the accepted / preserved / rejected tables above, one assertion per
  row, named e.g. `test_normalize_date_non_padded_hyphen_returns_iso`,
  `test_normalize_date_padded_input_unchanged`,
  `test_normalize_date_missing_year_returns_none`.
- Backend `validate_import` end-to-end (Requirement 5.4): feed rows whose only non-standard trait
  is non-padded dates (`make_valid_row(trip_date="5-5-2026")`) and assert `valid == len(rows)`
  with a populated `preview` and all `_status == "ok"` (continuity-permitting), using the existing
  `mock_db` fixture.
- Frontend: `getStatusBadge` returns the correct colorScheme/label for `_status` ok/warning/error
  and joins `_messages`; the Upload→Preview mapping yields a populated `validationResult` from a
  flat response; `commitImport` posts `{ vehicle_id, rows, skip_error_rows }`.
- Backend sheet selection (Requirements 8.1, 8.2; preservation 9.1, 9.2) — build in-memory
  workbooks with `pandas.ExcelWriter(buf, engine="openpyxl")` → `buf.seek(0)` → `parse_file`:
  - `test_parse_file_decoy_first_sheet_selects_matching_second_sheet` — a decoy first sheet
    lacking the required headers plus a second sheet carrying all mapped headers + rows; assert
    `result.success is True`, the returned `columns_found`/rows come from the second sheet, and
    `total_rows` matches the data on that sheet.
  - `test_parse_file_single_sheet_unchanged_selection` — a one-sheet workbook with the headers;
    assert the same sheet/rows as a direct `pd.read_excel(..., sheet_name=0)` read.
  - `test_parse_file_csv_unaffected_by_sheet_selection` — a semicolon CSV; assert the existing
    CSV parse result is unchanged.
- Backend no-match failure (Requirement 8.3) —
  `test_parse_file_no_sheet_matches_returns_success_false`: a workbook where no sheet has the
  required headers; assert `result["success"] is False` and the `error` string contains both the
  found columns and the expected columns (`required_headers`).
- Backend `_normalize_date` datetime cases (Requirement 8.4) — add rows to the parser table/class:
  `test_normalize_date_iso_with_time_returns_date` (`"2026-05-05 00:00:00"` → `"2026-05-05"`),
  `test_normalize_date_iso_with_t_separator_returns_date`,
  `test_normalize_date_date_object_returns_date` (`datetime.date(2026,5,5)` → `"2026-05-05"`),
  `test_normalize_date_datetime_object_returns_date`.
- Backend error-marker cases (Requirement 8.5; preservation 9.6) — feed `validate_import` rows via
  `mock_db`: `test_validate_import_na_marker_flags_row_error` (mapped `trip_date` = `"#N/A"` →
  that row `_status == "error"` and a `_messages` entry contains both the column name and `#N/A`),
  `test_validate_import_ref_marker_flags_row_error` (`"#REF!"`),
  `test_validate_import_empty_cell_still_required_field_error` (plain `None`/`""` → the normal
  "Verplicht veld ontbreekt" error, NOT an error-marker message — unchanged behavior),
  `test_validate_import_valid_cached_value_unaffected` (an ordinary looked-up value is `ok`).

### Property-Based Tests

- Optional (not required for this fix): generate valid dates and assert the fixed
  `_normalize_date` output always matches `/^\d{4}-\d{2}-\d{2}$/` and round-trips padded inputs
  unchanged. Generate random `success:false` responses and assert the wizard remains on Upload.
- Optional (surface c): generate random non-`#` strings and assert `isExcelErrorMarker` returns
  `False` (only recognized markers flag), and generate datetimes within range and assert
  `_normalize_date` returns the `YYYY-MM-DD` date portion.

### Integration Tests

- Full wizard flow: upload a semicolon-separated CSV with non-padded Dutch dates (mirroring the
  user's verified export) → Preview shows the correct counts and rows with status badges → Import
  button enabled when `valid > 0` → commit posts the validated `rows` and reports `imported`.
- Full wizard flow (surface c): upload a multi-sheet `.xlsx` mirroring `Rittenregistratie.xlsx`
  (decoy `Blad1` first, data on `ritten_import_template`) → the correct sheet is selected, Preview
  shows the real rows with datetime-valued dates normalized, Import enabled when `valid > 0`.
- No-match `.xlsx` upload → wizard shows the found-vs-expected error toast and stays on the Upload
  step (Requirement 8.3).
- Context: switching back to Upload and re-uploading repopulates state without stale rows.
- Verify the backend `/import` → `/import/commit` round-trip: the `rows` returned by `/import`
  are accepted by `/import/commit` (non-empty list), confirming the end-to-end contract.
