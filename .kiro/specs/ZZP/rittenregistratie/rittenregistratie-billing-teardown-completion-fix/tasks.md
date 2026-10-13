# Implementation Plan — Rittenregistratie Billing-Teardown Completion Fix

## Overview

Finish the trip-side billing teardown left incomplete by the Sunday redesign (`fc31b179f`).
The `zzp_trips` migration already dropped `contact_id`/`is_billable`/`is_billed`/`invoice_id`;
this plan removes the leftover code that still references them, across frontend types and the
backend service/route layers, with paired-test updates. Effort: **S** ≤ 30 min · **M** ≤ 2 h.
Verification assumes `cd backend && source .venv/bin/activate` (backend) / `cd frontend`
(frontend). Order: land the already-done frontend slice first, then the backend sweep, then
full verification.

## Tasks

### Frontend (already implemented — re-home + verify)

- [x] 1. **F1/F2. Remove billing/contact-link fields from trip types.** [S] — DONE in working
  tree; commit under this spec.
  - **Files**: `frontend/src/types/zzpTrips.ts` — removed `TripFilters.contact_id`,
    `TripFilters.is_billed`, `RoutePreset.contact_id`. Verified: every `getTrips()` caller and
    `buildFilters()` set none of them; no `RoutePreset` consumer reads `contact_id`.
  - **Verification**:
    ```bash
    cd frontend && npx tsc --noEmit -p tsconfig.json   # -> 0 errors
    ```

- [x] 2. **F3. Harden the render-free absence guard to all three trip interfaces.** [S] — DONE.
  - **Files**: `frontend/src/__tests__/ZZPTripsBillingAbsence.test.ts` — now asserts `Trip`,
    `TripFilters`, and `RoutePreset` declare no `contact_id`/`is_billable`/`is_billed`; also
    absorbed the billing-reference greps from the heavy render test, and `ZZPTrips.test.tsx`
    was slimmed to a single page mount.
  - **Verification**:
    ```bash
    cd frontend && npx vitest run src/__tests__/ZZPTripsBillingAbsence.test.ts   # -> all pass (28)
    ```

### Backend — High (CI-blocking once paired tests assert absence)

- [x] 3. **B1. Drop `is_billable` from `UPDATABLE_FIELDS` in `zzp_trip_service.py`.** [S] —
  latent bug: `update_trip` builds `UPDATE zzp_trips SET …` from this list, so `is_billable`
  would target a dropped column.
  - **File**: `backend/src/services/zzp_trip_service.py` (`UPDATABLE_FIELDS`, ~line 67).
  - **Action**: remove the `"is_billable"` entry.
  - **Verification**:
    ```bash
    cd backend && source .venv/bin/activate
    grep -n "is_billable" src/services/zzp_trip_service.py   # -> no UPDATABLE_FIELDS hit
    python -m pytest tests -k "zzp_trip_service" -q
    ```

- [x] 4. **B2. Remove dead `is_billable`/`is_billed` coercion in trip `_serialize`.** [S] —
  the read path (`_TRIP_COLUMNS`) already excludes these, so the keys are never in a row.
  - **File**: `backend/src/services/zzp_trip_service.py` (~line 293). Keep `is_gap_fill`,
    `is_cancelled`.
  - **Verification**: `python -m pytest tests -k "zzp_trip_service" -q`

- [x] 5. **B3. Remove the trip `mark_as_billed` path (service + query service).** [M] —
  live `UPDATE zzp_trips SET is_billed=TRUE, invoice_id=%s …` against dropped columns.
  - **Files**: `backend/src/services/zzp_trip_service.py` (facade `mark_as_billed`, ~line 137),
    `backend/src/services/zzp_trip_query_service.py` (`mark_as_billed` + its `# ── Billing ──`
    section, ~line 302).
  - **Action**: delete both methods. Update/remove paired tests asserting the old billing
    update. Confirm no remaining caller except the invoice-factory trip branch removed in B4.
  - **Verification**:
    ```bash
    grep -rn "mark_as_billed" src/services/zzp_trip*.py   # -> none
    python -m pytest tests -k "zzp_trip" -q
    ```

- [x] 6. **B4. Remove the trip branch of `create_invoice_from_trips` (invoice service +
  factory).** [M] — parent Req 4.4: no callable invoice-from-trips path. KEEP the time-entry
  path and everything else in these files.
  - **Files**: `backend/src/services/zzp_invoice_service.py` (`create_invoice_from_trips`,
    ~line 488), `backend/src/services/zzp_invoice_factory.py` (`create_invoice_from_trips` +
    `trip.get("is_billed")`/`is_cancelled` guards, ~line 98–182).
  - **Action**: delete the trip-path method on the service and its factory implementation
    (incl. the `trip_service.mark_as_billed` call). Do NOT touch
    `create_invoice_from_time_entries` or `time_tracking_service.mark_as_billed`. Update paired
    invoice tests: drop the trip-path cases, keep the time-entry cases.
  - **Verification**:
    ```bash
    grep -rn "create_invoice_from_trips" src/   # -> none
    grep -rn "create_invoice_from_time_entries" src/   # -> still present (unchanged)
    python -m pytest tests -k "invoice" -q
    ```

- [x] 7. **B5. Verify routes conform (and remove any residual).** [S] — parent Req 4.1–4.3.
  - **Files**: `backend/src/routes/zzp_trip_routes.py`, `backend/src/routes/zzp_time_routes.py`
    (invoices-from-trips lived near the invoice routes — confirm it is gone), `app.py`
    registration.
  - **Action**: confirm `POST /api/zzp/invoices/from-trips` and `GET /api/zzp/trips/unbilled`
    are unregistered; confirm the list route's filter builder ignores `is_billed`/`contact_id`.
    Remove any residual handler/route found.
  - **Verification**:
    ```bash
    grep -rn "from-trips\|/unbilled\|get_unbilled" src/routes/   # -> none for trips
    python -m pytest tests -k "zzp_trip_routes" -q
    ```

### Verification — full gate (after 1–7)

- [x] 8. **V1. Full paired-plane verification.** [S]
  - **Verification**:
    ```bash
    cd backend && source .venv/bin/activate
    ruff check src/ && ruff format --check src/            # -> clean
    python -m pytest tests -k "zzp_trip or invoice" -q      # -> all pass, no stale billing cases
    cd /home/peter/projects/myAdmin && PYTHONPATH=. python -m pytest sam/tests -q   # -> green (unaffected)
    cd frontend && npx vitest run src/__tests__/ZZPTrips.test.tsx src/__tests__/ZZPTripsBillingAbsence.test.ts
    ```
  - Optional: a schema sanity check that `zzp_trips` has none of the four billing columns (use
    the `#database` skill / `railway-db.sh` wrapper — read-only `SHOW COLUMNS FROM zzp_trips`).

## Notes

- **This is a bugfix: restore conformance to the already-approved `rittenregistratie-tax-log-
  redesign` requirements (Req 4.3–4.8, 5.5).** No new behaviour; the authoritative spec is the
  parent redesign.
- **Scope boundary is strict.** TimeTracking_Feature and Contacts_Feature are untouched;
  `is_billable`/`is_billed`/`invoice_id`/`contact_id` remain legitimate there. Every backend
  edit is scoped to the trip branch; diff-check the time-entry invoice path is unmodified.
- **No schema/migration work here** — the Sunday migration already dropped the columns. If a
  schema check reveals the columns are in fact still present, STOP: that is a different problem
  (migration did not run) and changes this spec's premise.
- The frontend slice (tasks 1–2) is implemented in the working tree of
  `spec/full-test-suite-fixes-2026-10-13`; it should be committed on this spec's own branch
  rather than the CI-fix PR.
