# Bugfix Requirements Document

## Introduction

In the mobile Quick trip entry page ("Snelle invoer" / Rittenregistratie, `frontend/src/pages/ZZPTripQuick.tsx`), a ZZP user registers trips one leg at a time. After saving an outbound leg she taps the 🔄 reverse button on a route preset to swap the addresses and taps "REGISTREER RIT" again to log the return leg. The UI shows the green "Rit geregistreerd!" success toast and clears the form, but the return trip is NOT persisted — it is silently lost. The outbound leg saves correctly.

The return leg is rejected by backend validation (HTTP 400 `{success: false, error: "..."}`, e.g. `end_odometer must be greater than start_odometer`), but the frontend's `handleSubmit` never inspects the response `success` flag. The HTTP layer does not throw on 4xx/5xx bodies (only 401 is special-cased), so the `createTrip` promise resolves normally with a `{success: false}` body and the `catch` block never fires. The component unconditionally shows the success toast and resets the form, producing silent data loss. The tenant (kimgeers) has already lost two return trips this way.

This bugfix is scoped narrowly to `ZZPTripQuick.handleSubmit`. The backend is correct and is out of scope. The shared HTTP layer (`apiService`) throw behavior is out of scope. Other callers of `createTrip`/`tripService` are out of scope (explicit user decision). Recovery of the two already-lost trips is out of scope.

## Bug Analysis

### Current Behavior (Defect)

When the backend rejects a trip create with a `{success: false}` body (returned over HTTP 400/500 that the HTTP layer resolves rather than throws), the component treats it as a success.

1.1 WHEN `createTrip` resolves with a response whose `success` is false (backend rejected the trip, e.g. return leg where `end_odometer <= start_odometer`) THEN the system shows the green "Rit geregistreerd!" success toast as if the trip were saved
1.2 WHEN `createTrip` resolves with a response whose `success` is false THEN the system resets the quick-entry form (clears end odometer, start/end addresses, purpose, Klant, selected preset) and advances the start odometer, discarding the user's entered data so it cannot be retried
1.3 WHEN `createTrip` resolves with a response whose `success` is false THEN the system does not surface the backend's `error` message to the user, leaving no indication that the save failed

### Expected Behavior (Correct)

2.1 WHEN `createTrip` resolves with a response whose `success` is false THEN the system SHALL show an error toast (status "error"), NOT the success toast
2.2 WHEN `createTrip` resolves with a response whose `success` is false THEN the system SHALL use the backend's `error` message as the error description when present, falling back to a generic Dutch message when it is absent
2.3 WHEN `createTrip` resolves with a response whose `success` is false THEN the system SHALL NOT reset the form and SHALL NOT advance the start odometer, so the user's entered end odometer and addresses are preserved for retry

### Unchanged Behavior (Regression Prevention)

3.1 WHEN `createTrip` resolves with a response whose `success` is true THEN the system SHALL CONTINUE TO show the "Rit geregistreerd!" success toast and reset the form (clear fields, advance the start odometer) exactly as before
3.2 WHEN `createTrip` rejects with a true network or JSON-parse error THEN the system SHALL CONTINUE TO fall into the existing `catch` block and show the "Fout bij registreren" error toast
3.3 WHEN client-side validation fails (no vehicle, missing addresses, invalid end km-stand, missing category or purpose, Klant over 255 chars) THEN the system SHALL CONTINUE TO block submission with the existing warning toasts and retain entered values, without calling `createTrip`
3.4 WHEN the Klant input, category/purpose required-one validation, and odometer pre-fill behaviors are exercised THEN the system SHALL CONTINUE TO behave exactly as the existing tests assert

## Addendum — Root Cause Found During Manual Verification (scope expanded)

The original document scoped this bug narrowly to the frontend and assumed "the backend is correct". Manual verification against the live TEST backend disproved that assumption and surfaced the TRUE root cause, which has two parts:

1. **Frontend (original fix):** `ZZPTripQuick.handleSubmit` ignored the `createTrip` response `success` flag and reported false success — the silent data loss. Fixed by branching on `resp.success` (error toast + form preserved on failure). Covered by the exploration/preservation tests in `ZZPTripQuick.test.tsx`.

2. **Backend (newly identified, now in scope):** the actual HTTP 400 was `Invalid trip_purpose 'Financieel advies'. Must be one of: Klantbezoek, Vergadering, Materiaal ophalen, Overig`. The create path (`TripService._validate_category_and_purpose`) validated `trip_purpose` against an allow-list sourced from the `zzp_ritten.trip_purposes` parameter (fallback: MODULE_REGISTRY default). That parameter is **only ever read, never written or configurable** — a half-wired feature with no admin/config surface (comparable to the removed billing feature). The non-listed value `"Financieel advies"` reached the form by being copied from a **route preset's `default_purpose`** (presets auto-learn/carry arbitrary purpose text), which `handlePresetSelect` applies verbatim. The phantom allow-list then rejected the owner's own legitimate descriptive text.

**Resolution (user decision):** `trip_purpose` is free-text, business-owned data (data-ownership rule — the system must not reject the owner's own descriptive text), so its allow-list validation is REMOVED on both the create path and the import path. `trip_category` remains validated: it is a small fixed taxonomy (Zakelijk / Privé / Woon-werk) that drives bijtelling and summary logic.

### Backend behavior change

- `backend/src/services/zzp_trip_service.py::_validate_category_and_purpose` — validates `trip_category` only; any non-empty `trip_purpose` is accepted (still subject to the required-field check in `validate_fields`).
- `backend/src/services/zzp_trip_import/validation.py::validate_category_purpose` — no longer warns on an unknown `trip_purpose` (keeps the unknown-category warning), so the import path matches the create path.
- Paired tests updated (change-with-tests contract) in `test_zzp_trip_service.py`, `test_zzp_trip_import_validate.py`.

The two parts are complementary: the frontend fix makes genuine save failures visible instead of silent; the backend fix removes the invalid rejection that was the real cause of kimgeers' lost trips.
