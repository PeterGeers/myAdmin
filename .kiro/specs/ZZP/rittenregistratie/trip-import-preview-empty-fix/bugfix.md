# Bugfix Requirements Document

## Introduction

The ZZP trip import wizard (`ritten registratie` import) renders an empty Preview step and leaves the Import action unusable, even though the upload succeeds. The browser Network tab confirms `POST /api/zzp/trips/import` returns `200 OK` with a populated response body, so the data reaches the browser but is never shown.

The root cause is a contract mismatch between the backend import endpoint and the frontend wizard:

1. The endpoint returns the validation result **flat** at the top level (`{ success, total_rows, valid, warnings, errors, rows, preview }`), but the frontend reads it from a nested `data` property (`resp.data`). Because `data` does not exist, the wizard stores `undefined` as its validation state, and both the Preview and Import render functions short-circuit to render nothing.
2. Each preview row is annotated by the backend with underscore-prefixed fields (`_status`, `_messages`), while the frontend reads `status` and `messages`, so even after the first mismatch is fixed the per-row status badges would be empty.
3. The commit call (`POST /api/zzp/trips/import/commit`) sends `{ vehicle_id, column_mapping }`, but the backend requires a non-empty `rows` list and ignores `column_mapping`, so a commit would be rejected once the user could reach it.

A second, independently confirmed defect compounds the problem. The backend date parser `ZZPTripImportService._normalize_date` (`backend/src/services/zzp_trip_import_service.py`) only accepts dates where `len(date_str) == 10` with separators at fixed string positions (`date_str[2]`/`date_str[5]` for DD-MM-YYYY and DD/MM/YYYY, `date_str[4]`/`date_str[7]` for ISO YYYY-MM-DD). The user's verified export produces semicolon-separated CSV with Dutch headers that map correctly via `DEFAULT_COLUMN_MAPPING`, but the `trip_date` values are non-zero-padded numeric dates with a year, e.g. `5-5-2026` and `17-5-2026` (day-month-year, hyphen-separated). A value like `5-5-2026` is 8 characters, so it fails the length/position guard on every branch and each row is flagged `_status = "error"` with "Ongeldig datumformaat". Well-formed, unambiguous Dutch dates are rejected purely because day/month are not zero-padded, producing `valid = 0` and an all-error preview even after the wizard-display defects above are fixed.

A third, independently confirmed defect affects multi-sheet Excel uploads. `ZZPTripImportService._read_dataframe` (`backend/src/services/zzp_trip_import_service.py`) calls `pd.read_excel(file_stream, dtype=str)` with no `sheet_name` argument, so pandas defaults to the **first** worksheet. Verified against the user's real workbook (`Rittenregistratie.xlsx`, inspected via openpyxl + pandas), the file has two sheets: `Blad1` (first) carries only five columns [Vertrekadres, Categorie, Doel, Klant, Notities] and lacks Datum/Bestemming/Begin KM/Eind KM, while `ritten_import_template` (second) holds the full, correct data with all nine mapped headers [Datum, Vertrekadres, Bestemming, Begin KM, Eind KM, Categorie, Doel, Klant, Notities]. Because the reader only ever sees `Blad1`, all 17 real rows are flagged "Verplicht veld ontbreekt" for the four required columns that live solely on the correct sheet, yielding `valid = 0` and an all-error preview even once the wizard contract works. Compounding this, on the correct sheet the Datum column stores genuine Excel datetime values (openpyxl/pandas surface them as `datetime`, e.g. `2026-05-05 00:00:00`) rather than the `5-5-2026` string form from the CSV, so the date parser must additionally accept a date value that carries a time component or arrives as a datetime/date object, keeping only the date portion. The chosen fix is to auto-pick the first worksheet whose header row contains the mapped columns (the required-field subset); when no worksheet contains the expected columns the upload SHALL fail (`success: false`) with a clear file-level message naming both the columns found and the columns expected, rather than silently falling back to the first sheet. CSV uploads are single-sheet and remain unaffected.

A further robustness concern on the same Excel surface involves formula cells. The user reported that some fields in the correct sheet use `x.zoeken(...)` (the Dutch name for Excel's XLOOKUP), so mapped columns can be formulas that look up values from another tab. The import reader uses pandas `read_excel`, which returns the cached computed value Excel saved for a formula cell; it does not evaluate formulas. A resolved XLOOKUP whose value Excel saved therefore reads fine. The failure mode is an *unresolved* formula: a cell whose cached value is absent (e.g. a file written programmatically and never recalculated) reads as None/empty, or a broken formula whose cached value is an Excel error marker string such as `#N/A`, `#REF!`, `#VALUE!`, `#NAME?`, `#DIV/0!`, `#NULL!`, or `#NUM!`. In the user's current workbook all nine mapped columns happen to carry literal values (the only formula is in an unmapped extra column K, `=E2-D2`, whose cached values are present), so this file is fine — but XLOOKUP-heavy versions of the sheet are a real concern. The chosen fix detects recognized Excel error markers and flags that row `_status = "error"` with a specific message naming the column and the marker (e.g. "Formulewaarde niet berekend: '#N/A' in kolom Datum") instead of letting the marker masquerade as a generic required-field or invalid-format error; formulas are never evaluated, and an unresolved formula that reads as plain empty/None continues to be handled by the existing required-field check.

This document captures the observable defects, the correct behavior, and the existing behavior that must be preserved.

## Bug Analysis

### Current Behavior (Defect)

The import request succeeds at the network level, but the wizard fails to surface the result and cannot complete an import.

1.1 WHEN the user uploads a valid file and `POST /api/zzp/trips/import` returns `200 OK` with the validation payload at the top level THEN the system reads the result from a non-existent `resp.data` property and stores `undefined` as the validation state

1.2 WHEN the validation state is `undefined` and the wizard advances to the Preview step THEN the system renders an empty Preview (no summary counts, no rows) because the Preview renderer returns nothing for a null validation state

1.3 WHEN the validation state is `undefined` and the wizard reaches the Import step THEN the system renders nothing for the commit summary and never shows an enabled Import button, leaving the Import action unusable

1.4 WHEN the backend annotates each preview row with `_status` and `_messages` THEN the system reads the non-existent `status` and `messages` fields, so each row's status badge resolves to empty/undefined

1.5 WHEN the user triggers the commit action THEN the system sends `{ vehicle_id, column_mapping }` without the validated `rows`, so the backend rejects the request with a "rows must be a non-empty list" error

The backend date parser rejects valid non-zero-padded numeric dates.

4.1 WHEN a `trip_date` is a non-zero-padded hyphen-separated Dutch date (e.g. `5-5-2026`, `3-6-2026`) THEN the system flags the row `_status = "error"` with "Ongeldig datumformaat" because the value is not exactly 10 characters and fails the fixed length/position guard in `_normalize_date`

4.2 WHEN a `trip_date` is a non-zero-padded slash-separated Dutch date (e.g. `5/5/2026`) THEN the system flags the row `_status = "error"` with "Ongeldig datumformaat" for the same fixed length/position reason

4.3 WHEN every row in an otherwise valid import carries such a non-zero-padded date THEN the system reports `valid = 0` and produces an all-error preview, even after the wizard-display defects (sections 1–2) are fixed

The Excel reader reads the wrong worksheet and cannot read datetime-valued dates.

7.1 WHEN a multi-sheet Excel workbook is uploaded whose first sheet does NOT contain the mapped column headers but another sheet does THEN the system reads only the first sheet (because `_read_dataframe` calls `pd.read_excel(...)` with no `sheet_name`), so the real data on the other sheet is never read

7.2 WHEN the first sheet is read but lacks the required mapped columns (e.g. `Blad1` lacks Datum/Bestemming/Begin KM/Eind KM) THEN the system flags every row with "Verplicht veld ontbreekt" for those columns, reporting `valid = 0` and an all-error preview

7.3 WHEN the correct sheet stores the Datum column as real Excel datetime values (surfaced as datetime such as `2026-05-05 00:00:00`) THEN the system would fail to normalize the value because `_normalize_date` only handles the fixed-length string forms and does not accept a datetime/date object or an ISO date carrying a time component

7.4 WHEN a mapped cell contains an Excel error marker (e.g. `#N/A`, `#REF!`) because an XLOOKUP/formula did not resolve THEN the system currently treats it as an ordinary string value, so it either passes through as garbage or triggers a generic required-field/format error, with no indication that the underlying cause is an unresolved formula

### Expected Behavior (Correct)

The wizard should map the actual response shape into its preview state, display the validated rows and counts, and send the data the commit endpoint requires.

2.1 WHEN the user uploads a valid file and `POST /api/zzp/trips/import` returns `200 OK` with the validation payload at the top level THEN the system SHALL read the result from the top-level response fields and store a populated validation state

2.2 WHEN the validation state is populated and the wizard advances to the Preview step THEN the system SHALL render the summary counts (total, valid, warnings, errors) and the preview rows

2.3 WHEN the validation state is populated and the wizard reaches the Import step THEN the system SHALL render the commit summary and present an Import button that is enabled whenever at least one valid row exists

2.4 WHEN a preview row carries the backend status and messages (`_status` / `_messages`) THEN the system SHALL display the correct status badge (OK / warning / error) and its associated messages

2.5 WHEN the user triggers the commit action THEN the system SHALL send the validated `rows` (and vehicle id) that the commit endpoint requires, so a successful commit imports the valid rows

The backend date parser should accept non-zero-padded numeric day/month components by splitting on the separator and validating numeric ranges, rather than relying on fixed string length/positions.

5.1 WHEN a `trip_date` is a non-zero-padded hyphen-separated date (`D-M-YYYY`, `D-MM-YYYY`, `DD-M-YYYY`, including the existing `DD-MM-YYYY`) THEN `_normalize_date` SHALL split on `-`, validate `1 <= month <= 12`, `1 <= day <= 31`, `year >= 1900`, and SHALL return the zero-padded `YYYY-MM-DD` form (e.g. `5-5-2026` → `2026-05-05`)

5.2 WHEN a `trip_date` is a non-zero-padded slash-separated date (`D/M/YYYY`, including the existing `DD/MM/YYYY`) THEN `_normalize_date` SHALL split on `/`, validate the same numeric ranges, and SHALL return the zero-padded `YYYY-MM-DD` form

5.3 WHEN a `trip_date` is an ISO `YYYY-MM-DD` date THEN `_normalize_date` SHALL CONTINUE to accept it and return it normalized to zero-padded `YYYY-MM-DD`

5.4 WHEN every row in an otherwise valid import carries a non-zero-padded numeric date THEN the system SHALL report the correct `valid` count and a populated preview (the year is always present in the input, so the system SHALL NOT perform any year inference or guessing)

The Excel reader should select the worksheet that actually contains the mapped columns, fail clearly when none does, and the date parser should accept datetime-valued dates.

8.1 WHEN an Excel workbook is read THEN `_read_dataframe` SHALL scan all worksheets and select the first whose header row contains the mapped column headers (matched against the supplied `column_mapping` keys, else `DEFAULT_COLUMN_MAPPING` keys, at minimum the required-field headers Datum, Vertrekadres, Bestemming, Begin KM, Eind KM, Categorie, Doel); CSV files are single-sheet and SHALL be unaffected by sheet selection

8.2 WHEN a matching worksheet is found (e.g. the second sheet `ritten_import_template`) THEN the reader SHALL read that sheet and its rows SHALL validate through the normal validation path, so the correct sheet produces the expected valid rows

8.3 WHEN NO worksheet contains the expected columns THEN the parser SHALL return `success: false` with an error message that names both the columns found and the columns expected (e.g. "Geen werkblad met de verwachte kolommen gevonden"), and the wizard SHALL show that message and keep the user on the Upload step (no empty or all-error preview), rather than silently falling back to the first sheet

8.4 WHEN a `trip_date` arrives as an ISO date carrying a time component (e.g. `2026-05-05 00:00:00`) or as a datetime/date object THEN `_normalize_date` SHALL accept it and normalize to the zero-padded `YYYY-MM-DD` date portion only, discarding any time component and applying no timezone/time semantics and no year inference

8.5 WHEN a mapped cell value is one of the recognized Excel error markers (`#N/A`, `#REF!`, `#VALUE!`, `#NAME?`, `#DIV/0!`, `#NULL!`, `#NUM!`, including a leading `#` error form) THEN the system SHALL flag that row `_status = "error"` with a specific message naming the column and the error marker (e.g. "Formulewaarde niet berekend: '#N/A' in kolom Datum"), and SHALL NOT evaluate the formula; the row-level validation otherwise proceeds normally for the other columns

### Unchanged Behavior (Regression Prevention)

Existing wizard flows and the backend validation logic must remain unchanged.

3.1 WHEN `POST /api/zzp/trips/import` returns `success: false` with an error THEN the system SHALL CONTINUE TO show the upload-failed error toast and keep the user on the Upload step

3.2 WHEN the validation result reports zero valid rows THEN the system SHALL CONTINUE TO disable the Import button

3.3 WHEN the user is on the Upload step THEN the system SHALL CONTINUE TO disable the Back button and only offer Next (and SHALL CONTINUE TO offer only Back on the final Import step)

3.4 WHEN a file is parsed and validated by the backend import service THEN the system SHALL CONTINUE TO apply the existing required-field, date, odometer-continuity, and duplicate-detection validation unchanged, returning the same per-row status counts

3.5 WHEN the template download action is used THEN the system SHALL CONTINUE TO download the CSV template unchanged

The date-parser fix must not relax rejection of truly invalid dates or change already-valid parsing.

6.1 WHEN a `trip_date` is missing a year (e.g. `5-5`) THEN `_normalize_date` SHALL CONTINUE to reject it with the "Ongeldig datumformaat" error and `_status = "error"`

6.2 WHEN a `trip_date` contains non-numeric day/month components (e.g. the old `5-mei`) THEN `_normalize_date` SHALL CONTINUE to reject it with "Ongeldig datumformaat" and `_status = "error"`

6.3 WHEN a `trip_date` has an out-of-range day or month (e.g. `32-5-2026`, `5-13-2026`) THEN `_normalize_date` SHALL CONTINUE to reject it with "Ongeldig datumformaat" and `_status = "error"`

6.4 WHEN a `trip_date` is already zero-padded (`05-05-2026`, `2026-05-05`, `05/05/2026`) THEN `_normalize_date` SHALL CONTINUE to accept it and normalize it to the identical `YYYY-MM-DD` result as before

6.5 WHEN rows pass date validation THEN the system SHALL CONTINUE TO apply the existing required-field, odometer-continuity, duplicate-detection, and category/purpose-warning validation unchanged

The sheet-selection fix must not change single-sheet or first-sheet-matching reads, CSV handling, column filtering, formula-cell reads, or the surface (b) date behavior.

9.1 WHEN a single-sheet workbook, or a workbook whose first sheet already contains the mapped headers, is uploaded THEN the reader SHALL CONTINUE TO read that same sheet as before (header-match selects the first matching sheet, which is the first sheet)

9.2 WHEN a CSV file is uploaded THEN the system SHALL CONTINUE TO parse it with the existing semicolon-first, comma-fallback logic, unaffected by worksheet selection

9.3 WHEN a sheet contains unmapped or extra trailing columns (e.g. stray `Unnamed` columns) THEN the system SHALL CONTINUE TO ignore them

9.4 WHEN a `trip_date` uses any format covered by surface (b) (non-padded numeric `D-M-YYYY`, `D/M/YYYY`, ISO `YYYY-MM-DD`) THEN the system SHALL CONTINUE TO accept and normalize it identically, and SHALL CONTINUE TO reject truly-invalid dates (missing year, non-numeric, out-of-range)

9.5 WHEN a worksheet cell is a formula that computes a value (a "view" of another sheet) THEN the system SHALL CONTINUE TO read its cached computed value via pandas, with no new formula handling introduced

9.6 WHEN a formula/XLOOKUP cell has a valid cached computed value THEN the system SHALL CONTINUE TO read that cached value via pandas as today (no formula evaluation, no new handling), and a formula cell that reads as plain empty/None SHALL CONTINUE TO be handled by the existing required-field check

## Bug Condition Derivation

The spec now covers **three independent defect surfaces**, each with its own bug condition:

- **(a) Wizard contract** — the frontend wizard cannot map/render/commit a successful import-validation response (sections 1–3).
- **(b) Date parser** — `_normalize_date` rejects valid non-zero-padded numeric Dutch/ISO dates (sections 4–6).
- **(c) Excel sheet selection + formula error markers** — `_read_dataframe` reads the first worksheet with no error even when the mapped columns live on another sheet, the parser cannot read datetime-valued dates, and a mapped cell carrying an Excel error marker from an unresolved formula (XLOOKUP/`x.zoeken`) is treated as an ordinary value rather than being flagged (sections 7–9).

**F**: the import wizard + import/commit contract, `_normalize_date`, **and** `_read_dataframe` as they exist today (unfixed).
**F'**: the fixed wizard + contract, the fixed `_normalize_date`, **and** the fixed `_read_dataframe`.

### Surface (a): Wizard contract

```pascal
FUNCTION isBugCondition_wizard(X)
  INPUT: X of type ImportResponse            // response of POST /api/zzp/trips/import
  OUTPUT: boolean

  // Bug triggers when a successful import validation payload is returned,
  // because the frontend cannot map the flat shape / underscore fields,
  // and the commit cannot be completed.
  RETURN X.success = true
END FUNCTION
```

```pascal
// Property: Fix Checking — populated preview + usable import
FOR ALL X WHERE isBugCondition_wizard(X) DO
  state ← mapResponseToPreviewState'(X)
  ASSERT state IS NOT null
     AND state.total_rows = X.total_rows
     AND state.preview = X.preview
     AND previewRendersRows(state)
     AND importButtonEnabled(state) = (state.valid > 0)
     AND commitPayload'(state) CONTAINS validated rows
END FOR
```

```pascal
// Property: Preservation Checking — non-buggy inputs unchanged
FOR ALL X WHERE NOT isBugCondition_wizard(X) DO
  // e.g. X.success = false (upload error)
  ASSERT F(X) = F'(X)        // same error toast, same step, same navigation gating
END FOR
```

### Surface (b): Date parser

```pascal
FUNCTION isBugCondition_parser(d)
  INPUT: d of type string                     // a trip_date cell value
  OUTPUT: boolean

  // Bug triggers when d is a valid non-zero-padded numeric Dutch/ISO date
  // (year always present) that _normalize_date currently rejects purely
  // because it is not exactly 10 chars with separators at fixed positions.
  RETURN isValidNumericDutchOrIsoDate(d)      // D-M-YYYY, D/M/YYYY, or YYYY-M-D family,
                                              //   1<=month<=12, 1<=day<=31, year>=1900
     AND NOT isTenCharFixedPosition(d)        //   i.e. not already zero-padded 10-char form
END FUNCTION
```

```pascal
// Property: Fix Checking — non-padded numeric dates normalize correctly
FOR ALL d WHERE isBugCondition_parser(d) DO
  result ← normalizeDate'(d)
  ASSERT result = zeroPaddedIso(d)            // e.g. "5-5-2026"  -> "2026-05-05"
                                              //      "17-5-2026" -> "2026-05-17"
     AND result MATCHES /^\d{4}-\d{2}-\d{2}$/
END FOR
```

```pascal
// Property: Preservation Checking — parser behavior otherwise unchanged
FOR ALL d WHERE NOT isBugCondition_parser(d) DO
  ASSERT normalizeDate(d) = normalizeDate'(d)
  // Covers:
  //  - already zero-padded forms (05-05-2026, 2026-05-05, 05/05/2026) -> same normalized result
  //  - truly invalid dates (missing year "5-5", non-numeric "5-mei",
  //    out-of-range "32-5-2026") -> still rejected (None -> "Ongeldig datumformaat", _status="error")
  // No year inference is introduced: the year is always present in the input.
END FOR
```

### Surface (c): Excel sheet selection

```pascal
FUNCTION isBugCondition_sheet(wb)
  INPUT: wb of type ExcelWorkbook              // an uploaded .xlsx workbook
  OUTPUT: boolean

  // Bug triggers in two ways on the Excel surface:
  //  (1) the FIRST worksheet's header row does not contain the mapped column
  //      headers (required-field subset), because _read_dataframe reads only the
  //      first sheet with no sheet_name and gives no file-level feedback; or
  //  (2) a mapped cell on the selected sheet carries an Excel error marker from
  //      an unresolved formula (XLOOKUP / x.zoeken), which is treated as an
  //      ordinary value rather than being flagged.
  // (1) applies to multi-sheet workbooks where the data lives on a later sheet,
  // and to any workbook whose first sheet lacks the headers.
  RETURN NOT firstSheetContainsMappedHeaders(wb)   // mapped headers = column_mapping keys,
                                                   //   else DEFAULT_COLUMN_MAPPING keys
      OR someMappedCellIsErrorMarker(wb)           // cell value in { #N/A, #REF!, #VALUE!,
                                                   //   #NAME?, #DIV/0!, #NULL!, #NUM! }
END FUNCTION
```

```pascal
// Property: Fix Checking — correct sheet selected, or clear failure
FOR ALL wb WHERE isBugCondition_sheet(wb) DO
  result ← readDataframe'(wb)
  IF NOT firstSheetContainsMappedHeaders(wb) THEN
    IF someSheetContainsMappedHeaders(wb) THEN
      // e.g. Rittenregistratie.xlsx: Blad1 (first) lacks headers,
      //      ritten_import_template (second) has all mapped headers.
      ASSERT result.sheet = firstSheetContainingMappedHeaders(wb)
         AND rowsValidateNormally(result)         // correct sheet -> valid rows
    ELSE
      ASSERT result.success = false
         AND result.error NAMES columnsFound(wb)
         AND result.error NAMES columnsExpected(wb)   // no silent fallback to first sheet
         AND wizardStaysOnUploadStep(result)
    END IF
  END IF

  // Error-marker handling on the selected sheet (no formula evaluation):
  FOR ALL (row, col) WHERE isErrorMarker(cellValue(result, row, col)) DO
    ASSERT rowStatus'(result, row) = "error"
       AND rowMessage'(result, row) NAMES col
       AND rowMessage'(result, row) NAMES cellValue(result, row, col)   // the marker string
       AND NOT formulaEvaluated(result)
  END FOR
END FOR
```

```pascal
// Property: Preservation Checking — non-buggy inputs unchanged
FOR ALL wb WHERE NOT isBugCondition_sheet(wb) DO
  ASSERT readDataframe(wb) = readDataframe'(wb)
  // Covers:
  //  - single-sheet workbooks, and workbooks whose first sheet already has the
  //    mapped headers -> header-match selects the same (first) sheet as before
  //  - CSV uploads (semicolon-first, comma fallback) -> single-sheet, unaffected
  //  - unmapped / extra trailing (Unnamed) columns -> still ignored
  //  - formula "view" cells with a valid cached value -> still read as that cached
  //    value via pandas, identical to today (no formula evaluation)
  //  - formula cells that read as plain empty/None -> still fall through to the
  //    existing required-field check (no new handling)
  // Surface (b) date behavior is unchanged; datetime-valued dates on the selected
  // sheet normalize to the zero-padded YYYY-MM-DD date portion only.
END FOR
```
