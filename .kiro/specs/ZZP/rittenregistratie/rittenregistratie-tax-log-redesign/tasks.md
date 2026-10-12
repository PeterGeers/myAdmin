# Implementation Plan: Rittenregistratie Tax-Log Redesign

## Overview

This plan converts the design into incremental, test-first coding steps. It redesigns the
existing ZZP trip module into a pure Belastingdienst kilometer log: it adds a free-text
`client_name` (Klant) field end-to-end, removes the never-approved trip-billing model
(`is_billable`, `is_billed`, `invoice_id`, trip `contact_id` link, invoice-from-trips,
unbilled-trips, guards, routes, UI), seeds route presets from imports, and fixes the import
preview to show per-row validation messages inline.

Because this is a redesign of existing code (not greenfield), every task **updates existing
tests alongside the code it changes** (change-with-tests contract, Req 10.7) — it does not
only add new tests. The schema migration lands and is verified locally early; the
irreversible Railway production migration is isolated as the final, human-gated, manual task
that the agent must NOT run autonomously.

### Conventions

- **Property-based tests** use Hypothesis (backend), minimum 100 iterations, each tagged with
  a comment: `# Feature: rittenregistratie-tax-log-redesign, Property N: <text>`.
- **Backend shell (WSL):** `cd /home/peter/projects/myAdmin/backend && source .venv/bin/activate && pytest tests/unit/<file> -v`
- **Frontend shell:** `cd /home/peter/projects/myAdmin/frontend && npx vitest run` and `npx tsc --noEmit`
- Frontend tests follow `.kiro/steering/33-frontend-testing.md`.
- Each task cites the requirement sub-clauses (Req N.M) and design properties (Property N) it implements.

## Tasks

- [x] 1. Discover and record the actual FK constraint names on Local_Docker
  - Query `information_schema.KEY_COLUMN_USAGE` / `TABLE_CONSTRAINTS` on schema `finance`,
    table `zzp_trips`, for the `contact_id → contacts` and `invoice_id → invoices` foreign
    key constraint names (expected conventional names `zzp_trips_ibfk_2` / `zzp_trips_ibfk_3`,
    but verify — do not assume).
  - Also record the actual index names present (`idx_admin_contact`, `idx_admin_billed`,
    `idx_zzp_trips_admin_billable_contact`).
  - Record the discovered names (write to `.agent-output/zzp-fk-names.txt`) so the migration
    author pins the real names; never apply to Railway with an unverified FK name.
  - _Requirements: 3.1, 9.1_ · _Design: Data Model Change (FK constraint-name discovery), D5_

- [x] 2. Author the new JSON migration file
  - [x] 2.1 Write `backend/src/migrations/<timestamp>_zzp_trips_tax_log_redesign.json`
    - Follow the existing JSON format: `name`, `description`, `timestamp`, `up` (array,
      executed in order, each committed), `down` (array, executed in **reverse** order by
      `rollback_migration`), `version`.
    - `up` ordering (FKs/indexes before columns, Req 3.1):
      1. `ALTER TABLE zzp_trips ADD COLUMN client_name VARCHAR(255) DEFAULT NULL` (Req 2.1).
      2. `DROP FOREIGN KEY` on `contact_id` (discovered name), then on `invoice_id`.
      3. `DROP INDEX idx_admin_contact ON zzp_trips`; `DROP INDEX idx_admin_billed ON zzp_trips`;
         `DROP INDEX idx_zzp_trips_admin_billable_contact ON zzp_trips` — **plain `DROP INDEX`,
         no `IF EXISTS`** (MySQL 9.4 — Req 3.7).
      4. `DROP COLUMN contact_id`, `invoice_id`, `is_billable`, `is_billed` (Req 3.2).
    - `down` reverses to the exact pre-migration definition: re-add the four columns with
      their original definitions (`is_billable BOOLEAN DEFAULT FALSE`,
      `is_billed BOOLEAN DEFAULT FALSE`, `invoice_id INT DEFAULT NULL`,
      `contact_id INT DEFAULT NULL`), re-create the three indexes, re-create both FKs
      (`contact_id→contacts(id)`, `invoice_id→invoices(id)`), and `DROP COLUMN client_name`.
      Author the array so reversed execution yields: add columns → add indexes → add FKs →
      drop `client_name` (Req 3.6).
    - Keep `project_name`, `notes`, `route_description`, generated `distance_km`,
      `is_gap_fill`, `is_cancelled`, `cancel_reason`, `version` untouched (Req 1.7, Req 3.4).
    - _Requirements: 2.1, 3.1, 3.2, 3.3, 3.4, 3.6, 3.7, 9.7_ · _Design: New migration file, D4_

- [x] 3. Migration up/down round-trip test (local scratch DB)
  - [x] 3.1 Write migration round-trip test
    - Capture the `zzp_trips` schema; apply `up`; assert the four billing columns and three
      indexes are gone and `client_name` is present (Req 3.2, 3.3, 2.1); apply `down`; assert
      the schema equals the captured pre-migration definition (Req 3.6).
    - Assert the `contacts` table definition is byte-for-byte identical before and after
      (Req 3.5).
    - Assert the migration `up` SQL contains no `IF EXISTS` on index drops (Req 3.7).
    - Assert a second apply reports "already applied" and does not re-run (Req 9.6).
    - _Requirements: 2.1, 3.2, 3.3, 3.5, 3.6, 3.7, 9.6_ · _Design: Migration test_

- [x] 4. Apply the migration on Local_Docker and verify
  - Run the migration via `DatabaseMigration().run_all_migrations()` against Local_Docker.
  - Verify (report within 10s, Req 9.2): `client_name` present; `is_billable`, `is_billed`,
    `invoice_id`, `contact_id` absent (schema inspection); existing trips still readable
    (`SELECT ... FROM zzp_trips WHERE administration = %s` returns rows without error).
  - This is a required task and must complete before any backend code that assumes the new
    schema is exercised against the DB.
  - _Requirements: 9.1, 9.2_ · _Design: Rollout Plan Step 1_

- [x] 5. Backend — `client_name` end-to-end in import service
  - [x] 5.1 Update `zzp_trip_import_service.py` mapping and commit INSERT
    - `DEFAULT_COLUMN_MAPPING`: change `"Klant" -> "contact_name"` to `"Klant" -> "client_name"`
      (Req 2.7).
    - `commit_import` INSERT: write `client_name` instead of `contact_id`; remove
      `is_billable`/`is_billed`/`invoice_id` from the insert; keep `is_gap_fill`,
      `is_cancelled`, `version`, `created_by`, `project_name`, `notes`, `route_description`
      (Req 2.7, Req 4.6).
    - Trim whitespace on persisted `client_name`; empty/blank → `None` (Req 2.1, 2.7).
    - Klant length validation: if value length > 255, mark that row an error with a message
      naming the 255-char limit, do not persist it, do not abort the batch (Req 2.8).
    - _Requirements: 2.1, 2.7, 2.8, 4.6_ · _Design: import_service modifications; Properties 4, 5_
  - [x] 5.2 Update/extend `test_zzp_trip_import_service.py` + `test_zzp_trip_import_commit.py` property tests
    - **Property 4: Client_Name import round-trip** — committing a row persists `client_name`
      equal to the trimmed input, and `null` for empty/blank cells. **Validates: Req 2.1, 2.7**
    - **Property 5: Over-length Klant row rejected, others preserved** — in a mixed batch,
      over-length rows become error rows carrying the 255-char message and do not persist,
      while every other valid row still commits. **Validates: Req 2.8**
    - Tag each with the Hypothesis property comment; min 100 iterations.
    - _Requirements: 2.1, 2.7, 2.8, 10.7_

- [x] 6. Backend — preset seeding from import
  - [x] 6.1 Add preset seeding to `commit_import` in `zzp_trip_import_service.py`
    - After the commit loop, iterate rows committed as non-error and call
      `RoutePresetService.increment_usage(tenant, start_address, end_address,
      default_category=trip_category, default_purpose=trip_purpose,
      typical_distance_km=(end_odometer - start_odometer))` once per committed non-error row;
      skip error rows entirely (Req 6.1).
    - Wrap each call in `try/except`: on failure log a warning and attach a **non-fatal** note
      to that row's result; never roll back the committed trip or the import (Req 6.4).
    - Seed **after** successful commit, never inside the per-row insert (D2).
    - _Requirements: 6.1, 6.2, 6.3, 6.4_ · _Design: import_service preset seeding, D2; Properties 10, 11, 12_
  - [x] 6.2 Update/extend `test_zzp_route_preset_service.py` + import tests for preset learning
    - **Property 10: Preset learning runs once per committed non-error row** — `increment_usage`
      invoked exactly once per committed non-error row, zero times per error row.
      **Validates: Req 6.1**
    - **Property 11: Preset use_count equals occurrence count** — each auto-learned preset's
      `use_count` equals the number of committed rows carrying that normalized (case-insensitive,
      trimmed) from/to pair; distinct pairs yield distinct presets. **Validates: Req 6.2, 6.3**
    - **Property 12: Preset learning failure is non-fatal** — when learning raises for a row,
      the trip and import stay committed and a non-fatal note is recorded for that row.
      **Validates: Req 6.4**
    - Tag each with the Hypothesis property comment; min 100 iterations.
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 10.7_

- [x] 7. Backend — confirm date validation unchanged (`_normalize_date`)
  - [x] 7.1 Add/keep date property tests in `test_zzp_trip_import_validate.py`
    - Confirm `_normalize_date` needs **no code change**: rejects yearless/non-numeric-month
      values without inference, accepts the documented formats, message names the value and
      format.
    - **Property 13: Invalid dates rejected without inference** — yearless (`5-mei`, `17-mei`)
      or non-numeric month (`mei`, `jan`, `dec`) rows are rejected with no year inferred.
      **Validates: Req 8.1, 8.2**
    - **Property 14: Rejected-date message names the value and is bounded** — per-row error
      message contains the exact offending value and the expected format, length ≤ 500 chars.
      **Validates: Req 8.3**
    - **Property 15: Rejected rows retained in the preview** — every input row appears in the
      preview; invalid-date rows are present and marked as errors, never dropped.
      **Validates: Req 8.4**
    - **Property 16: Accepted date formats normalize to ISO** — accepted formats
      (`YYYY-MM-DD`; `DD-MM-YYYY`/`DD/MM/YYYY` padded or not; `datetime`/`date` objects)
      normalize to `YYYY-MM-DD` and are not rejected for date validity. **Validates: Req 8.5**
    - Tag each with the Hypothesis property comment; min 100 iterations.
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 10.7_ · _Design: _normalize_date no change_

- [x] 8. Backend — CRUD service (create / gap-fill / update / cancel)
  - [x] 8.1 Update `zzp_trip_crud_service.py`
    - `create_trip` INSERT: remove `contact_id` and `is_billable`; add `client_name`
      (Req 4.6, Req 2.1).
    - gap-fill INSERT: remove `contact_id` and `is_billable`; add `client_name`; keep
      `is_gap_fill = TRUE` (Req 4.6, Req 10.2).
    - `update_trip`: remove the `is_billed` "block editing billed trips" guard (Req 4.7).
    - `cancel_trip`: remove the `is_billed` "block cancellation of billed trips" guard (Req 4.8).
    - `UPDATABLE_FIELDS`: remove `contact_id`, `is_billable`; add `client_name`.
    - _Requirements: 2.1, 4.6, 4.7, 4.8, 10.2_ · _Design: crud_service modifications; Properties 1, 2, 3, 8, 9, 17_
  - [x] 8.2 Update `test_zzp_trip_service.py` (crud paths) property + example tests
    - **Property 1: Trip persistence and generated distance** — valid trip persists date,
      addresses, odometers, category, purpose, `project_name`, `notes`, with
      `distance_km == end - start`. **Validates: Req 1.1, 1.2, 1.7**
    - **Property 2: End-before-start odometer is rejected** — create/update rejected with an
      odometer error, nothing persisted, input retained. **Validates: Req 1.3**
    - **Property 3: Invalid category is rejected** — category outside {Zakelijk, Privé,
      Woon-werk} rejected, nothing persisted. **Validates: Req 1.5**
    - **Property 8: Billing-free invariant (records and responses)** — created/gap-filled
      records never contain `contact_id`, nested `contact`, `is_billable`, `is_billed`,
      `invoice_id`. **Validates: Req 4.5, 4.6**
    - **Property 9: Mutations never blocked by billing state** — update (valid payload) and
      cancel complete and persist regardless of any prior billing value. **Validates: Req 4.7, 4.8**
    - **Property 17: Gap-detection flag reflects odometer continuity** — flag set when
      `start_odometer` ≠ prior trip's `end_odometer` for the same vehicle, not set when equal.
      **Validates: Req 10.2**
    - Example tests: three category values accepted (Req 1.4); `client_name` empty → null on
      create (Req 2.5-equivalent persistence).
    - Tag property tests with the Hypothesis comment; min 100 iterations.
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.7, 2.1, 4.5, 4.6, 4.7, 4.8, 10.2, 10.7_

- [x] 9. Backend — query service
  - [x] 9.1 Update `zzp_trip_query_service.py`
    - Delete `enrich_with_contacts` and remove all its call sites in `get_trip`, `list`, and
      the former `get_unbilled_trips` path; trips return `client_name` directly, no nested
      contact object (Req 4.5).
    - Delete `get_unbilled_trips` (Req 4.4).
    - Remove `is_billed` and `contact_id` from the list-trips filter building — such filters
      are ignored, returning the full unfiltered set (Req 4.3).
    - Trip SELECT returns `client_name` and existing non-billing columns; no `contact_id`,
      no contacts JOIN (Req 4.5).
    - Preserve `WHERE administration = %s` on every query path; missing tenant → reject /
      no rows (Req 10.5, 10.6).
    - _Requirements: 4.3, 4.4, 4.5, 10.5, 10.6_ · _Design: query_service modifications, D6; Properties 7, 8, 18, 19_
  - [x] 9.2 Update query tests (in `test_zzp_trip_service.py` query paths)
    - **Property 7: Billing filters ignored (metamorphic)** — listing with `is_billed`/
      `contact_id` filters returns the same set as listing without them, no error.
      **Validates: Req 4.3**
    - **Property 8: Billing-free invariant** — retrieved/listed trips carry no `contact_id`,
      nested `contact`, `is_billable`, `is_billed`, `invoice_id`. **Validates: Req 4.5, 4.6**
    - **Property 18: Tenant isolation on every trip query** — get/list executed SQL includes
      `WHERE administration = %s` bound to the tenant; never returns another tenant's rows.
      **Validates: Req 10.5**
    - **Property 19: Missing tenant yields no rows** — query without a bound tenant is rejected
      and returns no rows. **Validates: Req 10.6**
    - Example test: `get_unbilled_trips` no longer exists / not callable (Req 4.4).
    - Tag property tests with the Hypothesis comment; min 100 iterations.
    - _Requirements: 4.3, 4.4, 4.5, 10.5, 10.6, 10.7_

- [x] 10. Backend — facade service `zzp_trip_service.py`
  - [x] 10.1 Update the facade
    - `UPDATABLE_FIELDS` (facade copy): replace `contact_id` with `client_name`.
    - Remove the `get_unbilled_trips` delegation (Req 4.4).
    - _Requirements: 4.4_ · _Design: facade modifications_

- [x] 11. Backend — export service
  - [x] 11.1 Update `zzp_trip_export_service.py`
    - Replace the `LEFT JOIN contacts c ON t.contact_id = c.id` / `c.company_name AS
      contact_name` with `SELECT t.client_name` directly (drop the contacts JOIN); map
      `client_name -> "Klant"` (Req 2.9).
    - Remove the `contact_id` export filter.
    - Keep the PDF/CSV/XLSX Klant column sourced from `client_name`; empty when null (Req 2.9).
    - _Requirements: 2.9_ · _Design: export_service modifications; Property 6_
  - [x] 11.2 Update `test_zzp_trip_export_service.py`
    - **Property 6: Export Klant mirrors Client_Name** — exported Klant equals each trip's
      `client_name` (empty when null), produced without any contacts join. **Validates: Req 2.9**
    - Tag with the Hypothesis comment; min 100 iterations.
    - _Requirements: 2.9, 10.7_

- [x] 12. Backend — route removals and filter passthroughs
  - [x] 12.1 Update `zzp_trip_import_export_routes.py` and `zzp_trip_routes.py`
    - Delete `create_invoice_from_trips` (`POST /api/zzp/invoices/from-trips`) so it 404s
      (Req 4.1); delete `_get_invoice_service` if now unused.
    - Remove the `contact_id` export filter passthrough (Req 4.3).
    - Delete `get_unbilled_trips` endpoint (`GET /api/zzp/trips/unbilled`) so it 404s (Req 4.2).
    - Remove `is_billed` / `contact_id` filter passthroughs in the list route (Req 4.3).
    - _Requirements: 4.1, 4.2, 4.3_ · _Design: route deletions, D6_
  - [x] 12.2 Add route-removal integration tests
    - `POST /api/zzp/invoices/from-trips` returns 404 (Req 4.1); `GET /api/zzp/trips/unbilled`
      returns 404 (Req 4.2).
    - List route with `is_billed`/`contact_id` query filters returns full unfiltered set, no
      error (Req 4.3, reinforces Property 7).
    - _Requirements: 4.1, 4.2, 4.3, 10.7_

- [x] 13. Checkpoint — backend green
  - Ensure all tests pass, ask the user if questions arise.
  - Run the full backend trip suite: `cd /home/peter/projects/myAdmin/backend && source .venv/bin/activate && pytest tests/unit/test_zzp_trip_import_service.py tests/unit/test_zzp_trip_import_commit.py tests/unit/test_zzp_trip_import_validate.py tests/unit/test_zzp_route_preset_service.py tests/unit/test_zzp_trip_service.py tests/unit/test_zzp_trip_export_service.py -v`

- [x] 14. Frontend — types `zzpTrips.ts`
  - [x] 14.1 Update `frontend/src/types/zzpTrips.ts`
    - `Trip`: drop `contact_id`, `contact?`, `is_billable`, `is_billed`, `invoice_id`; add
      `client_name: string | null` (Req 5.5, Req 2.1).
    - `ImportRow`: rename `contact_name?: string` to `client_name?: string` (Req 2.7).
    - _Requirements: 2.1, 2.7, 5.5_ · _Design: frontend type modifications_

- [x] 15. Frontend — `tripService.ts`
  - [x] 15.1 Update `frontend/src/services/tripService.ts`
    - Remove `getUnbilledTrips` (Req 5.4).
    - Remove the trip-side usage/import of `createInvoiceFromTrips` (do not modify the
      TimeTracking service file — Req 5.6).
    - Confirm no hardcoded `km_rate`/`0.23` remains in the service (Req 5.3).
    - _Requirements: 5.3, 5.4, 5.6_ · _Design: tripService modifications_
  - [x] 15.2 Update `tripService.test.ts`
    - Assert `getUnbilledTrips` is gone and no `createInvoiceFromTrips` usage; no billing-
      derived rows returned (Req 5.4); no `km_rate` reference (Req 5.3).
    - _Requirements: 5.3, 5.4, 10.7_

- [x] 16. Frontend — `ZZPTrips.tsx` list page
  - [x] 16.1 Update `frontend/src/pages/ZZPTrips.tsx`
    - Remove the `"Fact."` (`is_billable`) `FilterableHeader` column and its cell badge (Req 5.1).
    - Change the Client column source from `trip.contact?.company_name` to `trip.client_name`;
      render an empty cell when null (Req 2.6).
    - Remove `billableTrips` useMemo, `handleInvoiceSelected`, the invoice button, the
      `createInvoiceFromTrips` import, and all `is_billed`/`is_billable`/`contact_id` usages
      (Req 5.2, Req 5.4).
    - _Requirements: 2.6, 5.1, 5.2, 5.4_ · _Design: ZZPTrips modifications_
  - [x] 16.2 Update `ZZPTrips` tests
    - No Fact. column; Client column sourced from `client_name` (value shown, empty cell when
      null); no invoice button; no `createInvoiceFromTrips` usage.
    - _Requirements: 2.6, 5.1, 5.2, 5.4, 10.7_

- [x] 17. Frontend — `ZZPTripQuick.tsx` quick entry
  - [x] 17.1 Update `frontend/src/pages/ZZPTripQuick.tsx`
    - Add a free-text Klant input bound to `client_name` in form state and in the `tripData`
      payload sent to `createTrip` (Req 2.3); empty input → `null`/omitted (Req 2.5).
    - Client-side length guard: reject submission when Klant exceeds 255 chars, retain the
      entered value, show an error (Req 2.4).
    - Keep vehicle select, presets, odometer chaining/pre-fill (Req 10.1), category/purpose
      selects with required-one validation (Req 10.3, 10.4).
    - _Requirements: 2.3, 2.4, 2.5, 10.1, 10.3, 10.4_ · _Design: ZZPTripQuick modifications_
  - [x] 17.2 Update/add `ZZPTripQuick` tests
    - Klant input present and writes `client_name`; empty → null (Req 2.5); >255 blocked with
      retained value + error (Req 2.4); category/purpose required-one preserved and missing-
      selection error (Req 10.3, 10.4); odometer pre-fill preserved (Req 10.1).
    - _Requirements: 2.3, 2.4, 2.5, 10.1, 10.3, 10.4, 10.7_

- [x] 18. Frontend — `ZZPTripImport.tsx` import preview
  - [x] 18.1 Update `frontend/src/pages/ZZPTripImport.tsx`
    - Add a Klant column populated from each row's `client_name`; empty cell when blank/absent
      (Req 7.5).
    - Render per-row `_messages` **inline and visibly** (not only in a hover Tooltip): each
      message as a separate, visually distinct inline entry (messages column or expandable
      line under the row), so rejected rows show the reason without hover/focus (Req 7.1–7.3).
      Clean rows (0 messages) show no message block (Req 7.4).
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_ · _Design: ZZPTripImport modifications_
  - [x] 18.2 Update `ZZPTripImport` tests
    - Klant column present (value + empty cell); per-row messages rendered inline/visible
      without hover; multiple messages shown as distinct entries; clean rows show none.
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 10.7_

- [x] 19. Frontend — absence confirmations
  - [x] 19.1 Static/smoke assertions
    - No `km_rate`/`0.23` anywhere in trip UI or trip service (Req 5.3).
    - `Trip` type declares no billing fields and has `client_name` (Req 5.5).
    - TimeTracking files (`ZZPTimeTracking.tsx`, `ZZPInvoices.tsx`, `zzpInvoiceService`) have
      zero modifications (Req 5.6).
    - _Requirements: 5.3, 5.5, 5.6_ · _Design: Smoke/static tests_

- [x] 20. Final checkpoint — full suite green
  - Ensure all tests pass, ask the user if questions arise.
  - Backend: full trip suite (task 13 command) green.
  - Frontend: `cd /home/peter/projects/myAdmin/frontend && npx tsc --noEmit` and
    `npx vitest run` green across all touched areas.
  - Clean up scratch files under `.agent-output/` (e.g. `zzp-fk-names.txt`).
  - Note: the Railway production migration (task 21) is a separate human-gated task and is
    NOT part of this autonomous checkpoint.

- [x] 21. Railway production migration — MANUAL, HUMAN-GATED (do NOT run autonomously)
  - **This task requires an explicit human go-ahead and MUST NOT be executed by the agent/
    orchestrator autonomously.** It drops columns on live production data irreversibly.
  - Pre-check for real data loss before dropping (Req 9.4, rollout Step 3):
    `PYTHONPATH=backend/src backend/scripts/railway-db.sh python -c "..."` running
    `SELECT COUNT(*) FROM zzp_trips WHERE contact_id IS NOT NULL OR is_billed = 1;` — only
    proceed if the count is **0**; if non-zero, stop and escalate (irreversibility note).
  - Confirm Local_Docker verification (task 4) passed: all four billing columns absent AND
    all pre-existing trip records readable, before targeting Railway (Req 9.3).
  - Require and record an explicit human go-ahead for this specific migration; with no
    recorded go-ahead the run is aborted and Railway data left unchanged (Req 9.4, 9.5).
  - Apply via the Railway wrapper:
    `PYTHONPATH=backend/src backend/scripts/railway-db.sh python -c "from database_migrations import DatabaseMigration; DatabaseMigration().run_all_migrations()"`.
  - Re-run the Step-1 verification queries against Railway (client_name present; billing cols
    absent; existing trips readable). Already-applied migrations are skipped (Req 9.6).
  - _Requirements: 9.1, 9.3, 9.4, 9.5, 9.6_ · _Design: Rollout Plan Steps 2–3, Irreversibility note_

## Notes

- Tasks marked with `*` are optional/test or manual tasks. Per the change-with-tests contract
  (Req 10.7) the test sub-tasks update existing suites to the new model; they are marked
  optional only so an MVP pass can defer them, but they are expected for a compliant redesign.
- Task 21 is marked optional specifically because it is a **manual, human-gated production
  operation** that the autonomous agent must not run — it is the last task and clearly flagged.
- Each task references specific requirement sub-clauses and (where applicable) design
  properties for traceability.
- Property tests use Hypothesis, min 100 iterations, tagged
  `# Feature: rittenregistratie-tax-log-redesign, Property N: <text>`.
- The migration lands and is verified locally (tasks 1–4) before any backend code assuming
  the new schema runs against the DB; frontend follows backend; the irreversible Railway
  migration is isolated at the end.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1"] },
    { "id": 1, "tasks": ["2.1"] },
    { "id": 2, "tasks": ["3.1", "4"] },
    { "id": 3, "tasks": ["5.1", "8.1", "9.1", "11.1", "12.1", "14.1"] },
    { "id": 4, "tasks": ["6.1", "10.1", "15.1", "16.1", "17.1", "18.1"] },
    { "id": 5, "tasks": ["5.2", "6.2", "7.1", "8.2", "9.2", "11.2", "12.2", "15.2", "16.2", "17.2", "18.2", "19.1"] },
    { "id": 6, "tasks": ["21"] }
  ]
}
```
