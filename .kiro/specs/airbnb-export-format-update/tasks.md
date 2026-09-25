# Implementation Plan: Airbnb Export Format Update

## Overview

This plan rewires the Airbnb ingest path across three backend modules while preserving the
`Booking_Dict` output contract and the tenant-scoped `bnb` / `bnbplanned` tables. Work proceeds
bottom-up: first the pure parsing helpers (`parse_airbnb_amount`, `parse_airbnb_date`), then the
`str_airbnb_parser` rewrite that groups paired rows into one booking dict per confirmation code,
then scanner detection and pending/realised classification threaded through the processor and
upload route, then the `str_database.upsert_airbnb_bookings` keyed refresh, and finally the
anchored example, classification, integration, and property-based tests plus end-to-end wiring.

Language: **Python** (Flask backend). Tests: **pytest + Hypothesis**.

Shell / test convention (WSL):
```bash
cd backend && source .venv/bin/activate && pytest tests/unit/test_str_airbnb_parser.py -v
```

## Tasks

- [x] 1. Amount and date parsers in `str_airbnb_parser`
  - [x] 1.1 Implement `parse_airbnb_amount(value) -> float`
    - Strip quotes, spaces, and `€`; return `0.0` for `NaN`/blank-after-strip.
    - Comma present with two parts: drop `.` thousands sep from integer part, join integer + `.` + decimal; single-part comma: replace `,` with `.`.
    - No comma: parse as US-style period-decimal. Non-numeric `float()` failure → `0.0`.
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

  - [x] 1.2 Write unit tests for `parse_airbnb_amount`
    - Cases: `274.80→274.80`, `"1.234,56"→1234.56`, `"42,59"→42.59`, `"0.00"→0.0`, `""→0.0`, `NaN→0.0`, `"—"→0.0`, `" 76.67 "→76.67` (padding).
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

  - [x] 1.3 Implement `parse_airbnb_date(value) -> datetime | None`
    - Parse `MM/DD/YYYY`; strip padding before parse; return `None` on failure (caller applies today/current-year fallback).
    - _Requirements: 5.1_

  - [x] 1.4 Write unit tests for `parse_airbnb_date`
    - Valid `09/23/2026` → 2026-09-23; padded `" 09/04/2026 "`; blank/garbage → `None`.
    - _Requirements: 5.1_

- [x] 2. Rewrite `str_airbnb_parser` grouping and dict assembly
  - [x] 2.1 Implement `build_booking_from_group(code, rows, source_file, status, tax_rate_service, tenant) -> dict`
    - `amountGross = Σ parse_airbnb_amount(Bruto-inkomsten)`; `amountChannelFee = Σ parse_airbnb_amount(Servicekosten)`; no hardcoded 15%.
    - Dates from first row via `parse_airbnb_date` with today/current-year fallback; derive `year/q/m` from check-in, `daysBeforeReservation = (checkin - reservation).days`.
    - Taxes/net via `calculate_str_taxes(gross, checkin, fee, tax_rate_service, tenant)`; `pricePerNight = amountNett/nights` when `nights>0` else `0`.
    - Defaults: `guests=2`, `phone=""`, `channel="airbnb"`, `country=detect_country(addInfo)`, `listing=normalize_listing_name(Advertentie)`, `reservationCode=code`, `status` as passed. Emit exactly the 24 contract fields.
    - _Requirements: 2.4, 3.1, 3.2, 3.3, 3.4, 5.2, 5.3, 5.4, 7.1, 7.2, 7.3, 8.1, 8.2, 8.3, 8.4, 9.1, 9.2, 9.3_

  - [x] 2.2 Rewrite `process_airbnb_multi(file_paths, tax_rate_service=None, tenant=None, status="realised")`
    - Per file: read CSV with pandas, strip BOM + whitespace from column names; drop `Payout` rows and blank-`Bevestigingscode` rows; group by stripped `Bevestigingscode`; one `build_booking_from_group` call per group.
    - Skip unreadable files (record basename, continue); raise `ValueError` only if all files fail. Return `list[Booking_Dict]` all tagged with the passed `status`.
    - _Requirements: 2.1, 2.2, 2.3, 6.1, 6.3, 6.5_

  - [x] 2.3 Anchored example tests against `.agent-output/airbnb_pending.csv`
    - `HMXDT8WAFF` → `amountGross==351.47`, `amountChannelFee==42.59`; `HMTFCHFWTP` → `amountGross==109.36`, `amountChannelFee==13.25`.
    - Both dicts: `status=="planned"`, `channel=="airbnb"`, `guests==2`, `phone==""`; exactly one dict per code; no blank `reservationCode` (Payout dropped).
    - _Requirements: 3.5, 3.6, 2.2, 2.3, 7.1, 7.2_

  - [x] 2.4 Property test — Gross is sum of Bruto-inkomsten
    - **Property 4: Gross is the sum of Bruto-inkomsten**
    - **Validates: Requirements 3.1**

  - [x] 2.5 Property test — Channel fee is sum of Servicekosten, no hardcoded factor
    - **Property 5: Channel fee is the sum of Servicekosten (no hardcoded factor)**
    - **Validates: Requirements 3.2, 3.4**

  - [x] 2.6 Property test — Amounts parse across notations
    - **Property 6: Amounts parse across notations**
    - **Validates: Requirements 4.1, 4.2, 4.3**

  - [x] 2.7 Property test — Blank or non-numeric amounts are zero
    - **Property 7: Blank or non-numeric amounts are zero**
    - **Validates: Requirements 4.4**

  - [x] 2.8 Property test — Grouping: one booking per code, Payout excluded
    - **Property 3: Grouping produces one booking per confirmation code, Payout rows excluded**
    - **Validates: Requirements 2.1, 2.2, 2.3**

  - [x] 2.9 Property test — Dates and derived periods
    - **Property 8: Dates and derived periods**
    - **Validates: Requirements 5.1, 5.2, 5.3, 5.4, 9.3**

  - [x] 2.10 Property test — Output contract completeness
    - **Property 10: Output contract completeness**
    - **Validates: Requirements 2.4, 7.1, 7.2, 8.1, 8.2, 8.3, 8.4, 9.1, 9.2**

- [x] 3. Checkpoint — parser complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Scanner detection and classification in `str_processor`
  - [x] 4.1 Implement Airbnb detection helpers in `scan_str_files`
    - Add `_airbnb_header_columns` (read header, strip BOM + whitespace, `None` on failure), `_is_airbnb_file` (name token `airbnb` OR header has `Type` + `Bruto-inkomsten`), `_airbnb_is_realised` (header has both `Uitbetaald` and `Verwacht op`).
    - Split scan output into `airbnb_realised` / `airbnb_pending`; unreadable-header token-only files default to pending. Remove the `reservation` filename token rule.
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

  - [x] 4.2 Classification unit tests over both sample headers
    - `airbnb_pending.csv` header → Pending_File; `airbnb_08_2026-09_2026.csv` header → Realised_File; `something-airbnb.csv` with unreadable header → Airbnb (pending); former `reservation*.csv` name alone → not Airbnb.
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

  - [x] 4.3 Property test — Airbnb file detection
    - **Property 1: Airbnb file detection**
    - **Validates: Requirements 1.1, 1.2, 1.5**

  - [x] 4.4 Property test — Realised vs. pending classification
    - **Property 2: Realised vs. pending classification**
    - **Validates: Requirements 1.3, 1.4**

  - [x] 4.5 Thread classification through `_process_airbnb_multi` and `process_airbnb_multi` call sites
    - Call parser once per bucket: pending paths with `status="planned"`, realised paths with `status="realised"`; return the combined list so `separate_by_status` splits on the dict `status` field.
    - _Requirements: 6.1, 6.3, 6.5_

  - [x] 4.6 Property test — Status follows file classification
    - **Property 9: Status follows file classification**
    - **Validates: Requirements 6.1, 6.3, 6.5**

- [x] 5. Persistence: `str_database.upsert_airbnb_bookings`
  - [x] 5.1 Implement `upsert_airbnb_bookings(realised, planned, tenant=None) -> dict`
    - Mirror `upsert_direct_bookings` inside one `self.transaction()`; one private helper per half: SELECT existing `reservationCode`s for `channel='airbnb'` + administration from target table, split incoming into new/existing, INSERT new, UPDATE existing in place.
    - realised → `bnb`, planned → `bnbplanned`; all queries parameterized (`%s`) and administration-scoped (predicate omitted when `tenant is None`). Return `{realised_inserted, realised_updated, planned_inserted, planned_updated}`; on `DatabaseError` roll back and return zero counts with `error`.
    - _Requirements: 10.1, 10.2, 10.3, 10.4_

  - [x] 5.2 DB upsert idempotence integration test (local Docker MySQL test schema)
    - Insert a planned booking, re-run same import → one row in `bnbplanned` (updated, not duplicated); repeat for realised → `bnb`; a second administration with the same `reservationCode` is untouched (tenant scoping).
    - _Requirements: 10.1, 10.2, 10.3, 10.4_

  - [x] 5.3 Property test — Re-import is idempotent (keyed refresh)
    - **Property 11: Re-import is idempotent (keyed refresh)**
    - **Validates: Requirements 10.1, 10.2, 10.3**

- [x] 6. Wire the upload/save route
  - [x] 6.1 Route Airbnb save through `upsert_airbnb_bookings`
    - In `str_save` (routes/str_routes.py) for `platform == "airbnb"`, classify uploaded files by stripped header (`_airbnb_is_realised`), pass `tenant` from `@tenant_required()`, and send realised → `bnb`, planned → `bnbplanned` via the new upsert. Leave Booking.com / Direct / VRBO paths untouched.
    - _Requirements: 6.2, 6.4, 10.4_

- [x] 7. Final checkpoint — verification and wiring
  - Run the full suite and lint: `cd backend && source .venv/bin/activate && pytest -v` (property tests ≥100 iterations) and the project linter.
  - Confirm both sample files import end-to-end: `airbnb_pending.csv` → planned in `bnbplanned`, `airbnb_08_2026-09_2026.csv` → realised in `bnb`, with the two anchor codes matching Req 3.5 / 3.6.
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP.
- Each task references specific requirements for traceability; property tasks reference the design's numbered properties.
- Property tests use Hypothesis with ≥100 iterations and are tagged `Feature: airbnb-export-format-update, Property {n}: {text}`.
- `calculate_str_taxes`, `detect_country`, and `normalize_listing_name` are reused unchanged.
- The old `reservation`-style parser and the `reservation` filename token are replaced, not kept.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.3", "4.1", "5.1"] },
    { "id": 1, "tasks": ["1.2", "1.4", "2.1", "4.2", "4.3", "4.4", "5.2", "5.3"] },
    { "id": 2, "tasks": ["2.2", "6.1"] },
    { "id": 3, "tasks": ["2.3", "2.4", "2.5", "2.6", "2.7", "2.8", "2.9", "2.10", "4.5"] },
    { "id": 4, "tasks": ["4.6"] }
  ]
}
```
