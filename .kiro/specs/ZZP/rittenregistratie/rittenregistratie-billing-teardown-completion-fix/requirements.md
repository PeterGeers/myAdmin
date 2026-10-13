# Requirements — Rittenregistratie Billing-Teardown Completion Fix

## Introduction

The `rittenregistratie-tax-log-redesign` feature (merged Mon 2026-10-12 in commit
`fc31b179f`, "feat(zzp): rittenregistratie tax-log redesign + trips pagination") removed
the trip-billing model from the ZZP trips feature: it dropped the billing/contact-link
columns from `zzp_trips` and replaced the formal `contact_id` link with a free-text
`client_name`. The **database migration ran** (confirmed: `zzp_trip_query_service.py`
documents the post-redesign `zzp_trips` schema as excluding `contact_id`, `is_billable`,
`is_billed`, `invoice_id`), and the **trips read path and primary UI were updated**.

**But the teardown was executed incompletely.** Code that reads, writes, filters, and
exposes the now-dropped billing columns was left behind across both planes. Because the
redesigned frontend no longer *calls* these paths, the leftovers are latent — they compile
and the happy path works — but they are landmines: any request that reaches them issues SQL
against columns that no longer exist on `zzp_trips`, and they contradict the already-approved
redesign requirements (`rittenregistratie-tax-log-redesign` Req 4.3–4.8 and Req 5.5).

This bugfix spec exists to **finish the Sunday redesign** — bring the trip module back into
conformance with its own approved requirements. It is a **bugfix** (restore intended,
already-specified behaviour), not a new feature. The authoritative behaviour is the parent
redesign spec; this spec enumerates the concrete leftovers and the verification that each is
gone.

> **Scope boundary (unchanged from the parent spec).** The out-of-scope features are **not**
> touched: the `contacts` table / Contacts_Feature, and the TimeTracking_Feature
> (`ZZPTimeTracking`, `ZZPInvoices`, `zzp_invoice_service`, `time_tracking_service`,
> `zzp_invoice_factory`'s time-entry path). `is_billable` / `is_billed` / `invoice_id` /
> `contact_id` are legitimate there and MUST remain. Only the **trip-side** billing surface
> is removed.

## Evidence (leftovers found, with locations)

### Frontend (partially fixed in branch `spec/full-test-suite-fixes-2026-10-13`)

| # | File | Leftover | Status |
|---|------|----------|--------|
| F1 | `frontend/src/types/zzpTrips.ts` | `TripFilters.contact_id`, `TripFilters.is_billed` | ✅ removed (this effort) |
| F2 | `frontend/src/types/zzpTrips.ts` | `RoutePreset.contact_id` (FK into contacts table; no consumer reads it) | ✅ removed (this effort) |
| F3 | `frontend/src/__tests__/ZZPTripsBillingAbsence.test.ts` | guard only checked the `Trip` interface — blind to `TripFilters` / `RoutePreset` | ✅ hardened (this effort) |

> F1–F3 are already implemented in the working tree of the CI-fix branch and should be
> re-homed under this spec (they are the frontend slice of this bugfix). tsc passes;
> `ZZPTripsBillingAbsence.test.ts` is green at 28 render-free assertions.

### Backend (NOT yet touched — the substantive remaining work)

| # | File:line | Leftover | Violates |
|---|-----------|----------|----------|
| B1 | `backend/src/services/zzp_trip_service.py` `UPDATABLE_FIELDS` (~line 67) | `"is_billable"` in the update field list → `update_trip` can emit `UPDATE zzp_trips SET is_billable=%s` against a dropped column | redesign Req 4.6/4.7 |
| B2 | `backend/src/services/zzp_trip_service.py` `_serialize` (~line 293) | boolean coercion loops over dead `"is_billable"`, `"is_billed"` keys | redesign Req 4.5/4.6 |
| B3 | `backend/src/services/zzp_trip_service.py` (~line 137) + `zzp_trip_query_service.py` `mark_as_billed` (~line 302) | live `mark_as_billed` → `UPDATE zzp_trips SET is_billed=TRUE, invoice_id=%s WHERE … is_billed=FALSE` against dropped columns | redesign Req 4.4 |
| B4 | `backend/src/services/zzp_invoice_service.py` `create_invoice_from_trips` (~line 488) + `zzp_invoice_factory.py` `create_invoice_from_trips` (~line 98) incl. `trip.get("is_billed")` guard (~line 139) | callable invoice-from-trips service path still present | redesign Req 4.4 |
| B5 | trips routes | confirm `POST /api/zzp/invoices/from-trips` and `GET /api/zzp/trips/unbilled` are unregistered (redesign Req 4.1/4.2) and the list-trips route ignores `is_billed`/`contact_id` filters (Req 4.3) — verify, remove any residual route/handler | redesign Req 4.1–4.3 |

> **Caveat to resolve during design:** B3/B4 are a *chain* — `create_invoice_from_trips`
> (service → factory) calls `mark_as_billed`. The parent spec (Req 4.4) requires NO callable
> invoice-from-trips or unbilled-trips trip path. The out-of-scope `zzp_invoice_service` also
> contains the time-entry invoice path, which MUST stay; only the **trip** path is removed.
> The exact seam (delete the trip method vs. make it a hard-404) is a design decision, not a
> requirements one.

## Requirements

### Requirement 1 — Trip service writes/reads no billing fields

**User story:** As the trip module, I persist and return trips with no billing fields, so
that the service matches the post-redesign `zzp_trips` schema and cannot emit SQL against
dropped columns.

#### Acceptance Criteria
1. THE trip service SHALL NOT include `is_billable` (or `is_billed`, `invoice_id`,
   `contact_id`) in any insert, update, or allowed-field list used to build a write against
   `zzp_trips` (fixes B1).
2. WHEN a trip row is serialized for a response, THE trip service SHALL NOT reference
   `is_billable` or `is_billed` (fixes B2); it MAY still coerce the real columns
   `is_gap_fill` and `is_cancelled`.
3. WHEN a user updates or cancels a trip with a valid payload, THE trip service SHALL
   complete the operation applying no `is_billed`-based rejection (redesign Req 4.7/4.8).

### Requirement 2 — No callable trip-billing service path

**User story:** As the trip module, I expose no invoice-from-trips or mark-trips-billed or
unbilled-trips operation, so that no code path references the dropped `zzp_trips` billing
columns.

#### Acceptance Criteria
1. THE trip module SHALL expose no callable `mark_as_billed` operation that updates
   `zzp_trips.is_billed` / `invoice_id` (fixes B3).
2. THE trip module SHALL expose no callable `create_invoice_from_trips` and no
   `get_unbilled_trips` service path (fixes B4; redesign Req 4.4).
3. THE out-of-scope TimeTracking invoice path (`create_invoice_from_time_entries`,
   `time_tracking_service.mark_as_billed`, and the `invoices`/`time_entries` tables) SHALL
   remain fully intact and unmodified (redesign Req 4 scope boundary).

### Requirement 3 — Routes conform

**User story:** As a client, requests to removed trip-billing endpoints are not found, and
billing filters on the list route are ignored without error.

#### Acceptance Criteria
1. THE `POST /api/zzp/invoices/from-trips` and `GET /api/zzp/trips/unbilled` routes SHALL
   NOT be registered (redesign Req 4.1/4.2) — verify; remove any residual handler.
2. IF a list-trips request carries an `is_billed` or `contact_id` query filter, THEN THE
   trip module SHALL ignore it and return the full unfiltered set with no error (redesign
   Req 4.3).

### Requirement 4 — Frontend trip types carry no billing fields

**User story:** As the frontend trip module, my type definitions declare no billing or
formal-contact-link fields, so the UI cannot send them.

#### Acceptance Criteria
1. THE `Trip`, `TripFilters`, and `RoutePreset` interfaces in `frontend/src/types/zzpTrips.ts`
   SHALL declare none of `contact_id`, `is_billable`, `is_billed`, `invoice_id` (fixes
   F1/F2; redesign Req 5.5).
2. A render-free static guard test SHALL assert the absence in (1) across all three
   interfaces, so a reintroduction fails CI (fixes F3).

### Requirement 5 — Change-with-tests contract

**User story:** As a maintainer, every behavioural edit updates its paired tests in the same
change, so conformance is locked in and the nightly Full Test Suite stays green.

#### Acceptance Criteria
1. WHEN a trip-service / route billing path is removed, THE paired backend tests
   (`backend/tests/**/*trip*`, `*invoice*`) SHALL be updated in the same change to assert the
   absence (no stale test asserting the old billing behaviour).
2. WHEN the fix lands, `backend/.venv` `pytest` for the affected trip/invoice tests, the SAM
   plane, and the frontend trip tests SHALL pass; `ruff check`/`ruff format --check` SHALL be
   clean.

## Lessons / why this happened

- **The Sunday redesign (`fc31b179f`) landed the migration + UI but not the full service-layer
  teardown.** The approved parent requirements (Req 4.3–4.8) were correct and complete; the
  *execution* stopped short of removing the trip-side billing service/route code, leaving it
  referencing dropped columns.
- **The absence guard had a blind spot.** `ZZPTripsBillingAbsence.test.ts` checked only the
  `Trip` interface, so `TripFilters.is_billed`/`contact_id` and `RoutePreset.contact_id`
  survived CI. Fixed by extending the guard to all three interfaces.
- **A dropped-column migration must be paired with a service-layer sweep.** When a migration
  removes columns, grep every service/route/type that names those columns in the same change —
  a migration that outruns its code leaves latent SQL-against-missing-column bugs.
