# Design — Rittenregistratie Billing-Teardown Completion Fix

## Overview

Finish the trip-side billing teardown that `rittenregistratie-tax-log-redesign` (`fc31b179f`)
started. The DB migration already dropped `contact_id`, `is_billable`, `is_billed`,
`invoice_id` from `zzp_trips`; this fix removes the service-, route-, and type-layer code that
still references those dropped columns, bringing the trip module back into conformance with
the parent spec (Req 4.3–4.8, 5.5). No schema change is needed — the migration is done; this
is a code-only sweep plus paired-test updates.

## Architecture context

Flask / MySQL plane (`backend/src/routes` + `backend/src/services`), per steering
`30-backend-api-flask-mysql` and `31-backend-database-flask-mysql`. The trip module layers:

```
routes/zzp_trip_routes.py          (HTTP; @cognito_required/@tenant_required)
  └─ services/zzp_trip_service.py   (facade: UPDATABLE_FIELDS, _serialize, mark_as_billed)
       └─ services/zzp_trip_query_service.py  (SQL: _TRIP_COLUMNS, mark_as_billed UPDATE)
services/zzp_invoice_service.py     (invoices feature — OUT OF SCOPE except its trip path)
  └─ services/zzp_invoice_factory.py (create_invoice_from_trips → trip_service.mark_as_billed)
frontend/src/types/zzpTrips.ts      (Trip, TripFilters, RoutePreset)
```

## Decisions

### D1 — Remove the trip-billing methods, don't stub them
`mark_as_billed` (trip service + query service) and `create_invoice_from_trips` (invoice
service + factory, trip branch) are **deleted**, not left as 404/no-ops. Parent Req 4.4 is
unambiguous: "no callable invoice-from-trips service path." A stub still invites a caller.
Delete the methods and the `trip.get("is_billed")`/`is_cancelled` billing guards in the
factory's trip branch.

### D2 — The invoice service keeps its time-entry path
`zzp_invoice_service` / `zzp_invoice_factory` also host `create_invoice_from_time_entries`
(TimeTracking feature — out of scope). Only the **trip** branch is removed. The factory's
time-entry path, `time_tracking_service.mark_as_billed`, and all `invoices` / `time_entries`
SQL stay byte-for-byte unchanged. Verify with a git diff scoped to the trip branch only.

### D3 — `_TRIP_COLUMNS` already correct; only the write/serialize paths need edits
The read path (`_TRIP_COLUMNS` in `zzp_trip_query_service.py`) was already fixed on Sunday
(it excludes the billing columns). So `_serialize`'s `is_billable`/`is_billed` coercion is
pure dead code (those keys are never in a row) — remove them, keep `is_gap_fill`/
`is_cancelled`. `UPDATABLE_FIELDS` is the real latent bug: drop `is_billable` from it.

### D4 — Filters: confirm, don't re-engineer
Parent Req 4.3 says `is_billed`/`contact_id` list filters are silently ignored. The query
service comment already states they are "not wired into the WHERE builder." Verify the WHERE
builder truly ignores unknown keys (no `SELECT ... WHERE is_billed`); if a residual billing
branch exists, remove it. No new filtering behaviour.

### D5 — Routes: verify unregistered
Grep `routes/` for `from-trips`, `/unbilled`, and any trip route that references the billing
symbols. Parent Req 4.1/4.2 require 404. If a residual blueprint route exists, remove it and
its handler; otherwise this is a verification-only task.

### D6 — Frontend slice is already done
F1–F3 (type cleanup + guard hardening) are implemented in the working tree. They move under
this spec unchanged; no further frontend design needed beyond re-homing them into a commit on
this spec's branch.

## Change-with-tests mapping (per steering 30, §Change-With-Tests)

| Product edit | Paired test(s) to update in the same change |
|---|---|
| `zzp_trip_service.py` UPDATABLE_FIELDS / _serialize | `backend/tests/**/test_zzp_trip_service*.py` |
| remove `mark_as_billed` (service + query) | `backend/tests/**/test_zzp_trip*service*.py` (drop/convert billing cases) |
| remove `create_invoice_from_trips` (service + factory trip branch) | `backend/tests/**/test_zzp_invoice*.py` (drop trip-path cases; KEEP time-entry cases) |
| route verification/removal | `backend/tests/**/test_zzp_trip_routes*.py` |
| `frontend/src/types/zzpTrips.ts` | `frontend/src/__tests__/ZZPTripsBillingAbsence.test.ts` (already hardened) |

## Risks

- **Over-removal into TimeTracking.** Mitigation: scope every backend edit to the trip branch;
  diff-check that `create_invoice_from_time_entries` and `time_tracking_service` are untouched.
- **Hidden caller of `create_invoice_from_trips`.** Mitigation: grep for callers before delete
  (frontend has none — the redesign removed them; backend callers are only the factory→service
  chain being removed together).
- **MySQL plane verification needs a DB.** Use the `#database` skill for any query-against-real-
  data verification; unit tests mock the DB and are the primary gate.
