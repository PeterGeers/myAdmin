# ZZP Quick Trip Silent Save Failure Bugfix Design

## Overview

The mobile quick trip entry page silently loses trips when the backend rejects a create with a `{success: false}` body. `handleSubmit` in `frontend/src/pages/ZZPTripQuick.tsx` calls `await createTrip(tripData)` but discards the resolved value, then unconditionally shows the success toast and resets the form. Because the HTTP layer resolves (rather than throws) on 4xx/5xx responses, the `catch` block never fires for a validation rejection, so the user sees "success" while the trip is not stored.

The fix is narrow and local to `handleSubmit`: capture the `createTrip` response, branch on `resp.success`, and only show success + reset the form when `resp.success === true`. On a falsy `success`, show an error toast with the backend's `error` message (or a Dutch fallback) and leave the form untouched so the data can be retried. The existing `catch` for genuine network/parse errors stays as-is.

No change is made to the backend, to `apiService`'s throw behavior, or to any other caller of `tripService`.

## Glossary

- **Bug_Condition (C)**: The condition that triggers the bug — `createTrip` resolves (does not throw) with a response whose `success` flag is falsy, i.e. the backend rejected the create (typically an HTTP 400 `{success: false, error: ...}` body such as `end_odometer must be greater than start_odometer`).
- **Property (P)**: The desired behavior when C holds — the component shows an error toast using the backend's `error` message (or a Dutch fallback) and leaves the form intact (no reset, no odometer advance) rather than showing success.
- **Preservation**: The existing behavior for all non-C inputs that must remain unchanged — the happy-path `success: true` success toast + form reset, the `catch` path for true network/parse errors, and all client-side validation guards.
- **`handleSubmit`**: The async submit handler in `frontend/src/pages/ZZPTripQuick.tsx` that validates the form, builds `tripData`, calls `createTrip`, and (currently unconditionally) toasts success and resets the form.
- **`createTrip`**: The service function in `frontend/src/services/tripService.ts` that POSTs to `/api/zzp/trips` and returns the parsed JSON body typed as `ApiTripResponse` (`{ success: boolean; data: Trip; error?: string; ... }`). It does not throw on a `{success:false}` body.
- **`ApiTripResponse.success`**: The boolean flag in the create response that distinguishes a persisted trip (`true`) from a rejected one (`false`).

## Bug Details

### Bug Condition

The bug manifests when the create request completes at the HTTP layer but the backend reports a logical failure in the body. `authenticatedRequest` in `apiService.ts` only special-cases HTTP 401; for any other status it returns the `Response` without throwing. `createTrip` then does `resp.json()` and returns the parsed body. So a backend validation rejection surfaces to `handleSubmit` as a *resolved* promise carrying `{ success: false, error: "..." }`. `handleSubmit` ignores the resolved value entirely and runs its success path, so the bug fires whenever `success` is false.

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input of type ApiTripResponse  // the resolved result of createTrip(tripData)
  OUTPUT: boolean

  RETURN createTripResolved(input)          // the promise resolved, i.e. no network/parse error thrown
         AND input.success = false          // backend rejected the create
END FUNCTION
```

### Examples

- Return leg with swapped preset addresses where `end_odometer <= start_odometer`: backend returns HTTP 400 `{ success: false, error: "end_odometer must be greater than start_odometer" }`. Expected: error toast shown, form kept. Actual: "Rit geregistreerd!" success toast, form reset, trip lost.
- Any other backend validation rejection returning `{ success: false, error: "<message>" }`. Expected: error toast with that message, form kept. Actual: success toast, form reset.
- A `{ success: false }` body with no `error` field. Expected: error toast with a generic Dutch fallback message, form kept. Actual: success toast, form reset.
- (Edge, non-bug) `{ success: true, data: {...} }`: success toast + reset — correct, must stay unchanged.

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- The happy path (`success: true`) must still show the "Rit geregistreerd!" success toast and reset the form (clear end odometer, addresses, purpose, Klant, preset selection) and advance the start odometer to the just-entered end value.
- A genuine network or JSON-parse error (promise rejection) must still land in the existing `catch` block and show the "Fout bij registreren" error toast.
- All client-side validation guards (missing vehicle, missing addresses, invalid end km-stand, missing category, missing purpose, Klant > 255 chars) must still block submission with their existing warning toasts and retain entered values, without calling `createTrip`.
- The Klant trimming/null payload behavior, required-one category/purpose validation, and odometer pre-fill behavior must remain exactly as the existing tests assert.

**Scope:**
All inputs where the bug condition does NOT hold must be completely unaffected by this fix. This includes:
- Successful creates (`success: true`).
- Promise rejections from network/parse failures.
- Submissions blocked by client-side validation before `createTrip` is ever called.

## Hypothesized Root Cause

Based on the investigation, the root cause is confirmed (not merely hypothesized):

1. **Discarded response in `handleSubmit`**: The call is `await createTrip(tripData);` with no capture of the return value, so the `success` flag is never read. This is the direct cause of the silent failure.

2. **HTTP layer does not throw on `{success:false}` bodies**: `authenticatedRequest` returns the `Response` for any non-401 status without throwing, and `createTrip` returns `resp.json()` as-is. A backend rejection therefore resolves rather than rejects, so the `catch` block cannot catch it. (This is correct, intended behavior of the shared layer and is explicitly out of scope to change.)

3. **Unconditional success path**: The success toast and the form-reset block run on every resolved call, independent of the response contents.

The fix targets cause (1)/(3) only: branch on `resp.success` in `handleSubmit`.

## Correctness Properties

Property 1: Bug Condition - Rejected create must not report success

_For any_ input where the bug condition holds (`createTrip` resolves with `success === false`), the fixed `handleSubmit` SHALL show an error toast using the backend's `error` message when present (or a generic Dutch fallback when absent) and SHALL NOT show the success toast and SHALL NOT reset the form or advance the start odometer, so the entered end odometer and addresses are preserved for retry.

**Validates: Requirements 2.1, 2.2, 2.3**

Property 2: Preservation - Success and error-path behavior unchanged

_For any_ input where the bug condition does NOT hold (`createTrip` resolves with `success === true`, or the promise rejects with a network/parse error, or client-side validation blocks the submit), the fixed `handleSubmit` SHALL produce the same result as the original function, preserving the success toast + form reset on success, the `catch` error toast on true rejections, and the validation guards.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4**

## Fix Implementation

### Changes Required

**File**: `frontend/src/pages/ZZPTripQuick.tsx`

**Function**: `handleSubmit`

**Specific Changes**:
1. **Capture the response**: Replace `await createTrip(tripData);` with `const resp = await createTrip(tripData);`.

2. **Guard on `resp.success`**: Immediately after the call, if `!resp.success`, show an error toast and return early without touching the form:
   - Title: a short Dutch error title (e.g. "Rit niet opgeslagen").
   - Description: `resp.error` when truthy, otherwise a generic Dutch fallback (e.g. "De rit kon niet worden opgeslagen. Controleer de gegevens en probeer opnieuw.").
   - `status: 'error'`.
   - Do NOT run the reset block and do NOT advance `startOdometer`.

3. **Keep the success path for `success === true` only**: The existing "Rit geregistreerd!" success toast and the form-reset block (advance `startOdometer`, clear `endOdometer`, `startAddress`, `endAddress`, `tripPurpose`, `clientName`, `klantError`, `selectedPresetId`) run only when `resp.success` is truthy.

4. **Leave the `catch` block unchanged**: It continues to handle genuine network/parse rejections with the "Fout bij registreren" toast.

5. **Leave `finally` unchanged**: `setSubmitting(false)` still runs on every path.

No type changes are required: `createTrip` already returns `ApiTripResponse` with `success: boolean` and `error?: string`.

## Testing Strategy

### Validation Approach

Two-phase approach: first write a bug-condition exploration test that FAILS on the unfixed component (proving the silent-failure bug), plus a positive preservation test that PASSES on the unfixed component (capturing the happy path); then apply the fix and confirm the exploration test passes and the preservation test still passes. Tests live in the existing `frontend/src/__tests__/ZZPTripQuick.test.tsx` using Vitest + jsdom + RTL, services mocked, `render` from `@/test-utils`, Chakra auto-mock (per `.kiro/steering/33-frontend-testing.md`).

Because the Chakra mock's `useToast` returns a fresh `vi.fn()` on each call and does not render toast content into the DOM, the reliable observable signal is the **form reset side effect**: on the happy path the end odometer / addresses are cleared and the start odometer advances; on a rejection they must be preserved. The exploration test asserts the entered values are preserved on `success:false` (fails on unfixed code because the form is wrongly reset) and that `createTrip` was actually called with the rejected payload.

### Exploratory Bug Condition Checking

**Goal**: Surface a counterexample demonstrating that a `{success:false}` resolution is treated as success on the unfixed component. Confirm the root cause (discarded response / unconditional success path).

**Test Plan**: Mock `createTrip` to resolve with `{ success: false, error: 'end_odometer must be greater than start_odometer' }`. Render the page, fill a valid-looking quick-entry form (addresses, end odometer, purpose), submit, then assert that the form was NOT reset — the entered end odometer and addresses remain. Run on the UNFIXED component to observe the failure.

**Test Cases**:
1. **Rejected-create preserves form**: `createTrip` → `{success:false, error:'...'}`; after submit, end km-stand still shows the entered value and addresses are retained (will FAIL on unfixed code — the component resets them).
2. **`createTrip` was called with the rejected payload**: confirms the submit reached the service (sanity that the failure is about response handling, not blocked validation).

**Expected Counterexamples**:
- On unfixed code the end km-stand field is cleared (empty) and addresses are blank after a `success:false` response, proving the component ran its success/reset path for a rejected create.
- Root cause confirmed: the resolved `{success:false}` value is ignored and the unconditional reset runs.

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed function produces the expected behavior (error toast, no reset).

**Pseudocode:**
```
FOR ALL input WHERE isBugCondition(input) DO            // createTrip resolves, success === false
  handleSubmit_fixed(input)
  ASSERT errorToastShown(input.error OR dutchFallback)
  ASSERT NOT successToastShown
  ASSERT formNotReset                                   // end odometer + addresses preserved
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed function behaves identically to the original.

**Pseudocode:**
```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT handleSubmit_original(input) = handleSubmit_fixed(input)
END FOR
// non-bug inputs: success === true (success toast + reset),
// promise rejection (catch toast), client-side validation blocks (warning toast, no createTrip).
```

**Testing Approach**: The non-bug input domain here is small and discrete (success / network-reject / validation-blocked), so representative example-based tests plus the already-present validation/Klant/odometer tests cover preservation well. The existing test suite already encodes the happy-path reset and validation behavior; those tests must continue to pass unchanged. A positive case asserting `success:true` still shows success and resets is retained/added.

**Test Plan**: Observe the happy path on the unfixed code (success → form reset), keep a test asserting it, and rely on the existing validation/Klant/odometer tests for the remaining non-bug behavior. Confirm all pass before and after the fix.

**Test Cases**:
1. **Happy-path reset preserved**: `createTrip` → `{success:true, data:{...}}`; after submit the end km-stand is cleared and start odometer advances — passes before and after the fix.
2. **Validation guards preserved**: existing tests (missing purpose, Klant > 255) continue to block submission and retain values — unchanged.
3. **Odometer pre-fill preserved**: existing tests for start-odometer pre-fill continue to pass.

### Unit Tests

- Rejected create (`success:false`) preserves the entered form values (exploration test — fails before fix, passes after).
- Successful create (`success:true`) resets the form and advances the start odometer (preservation).
- Existing Klant trimming/null, Klant length guard, required-one category/purpose, and odometer pre-fill tests remain green.

### Property-Based Tests

- Not required for this fix: the bug condition reduces to a single discrete branch (`success === false`) and the non-bug domain is a small finite set of outcomes. Example-based tests give full branch coverage; a scoped property-style assertion over `{success:false}` with/without an `error` message is sufficient and is covered by the exploration test plus a fallback-message case.

### Integration Tests

- Covered at the unit/component level here. End-to-end (real backend 400 → error toast, form retained) is validated manually against the live quick-entry page; automated E2E is out of scope for this narrow fix.

## Addendum — Backend Root Cause (scope expanded during verification)

Manual verification found the real HTTP 400 driving the data loss:
`Invalid trip_purpose 'Financieel advies'. Must be one of: Klantbezoek, Vergadering, Materiaal ophalen, Overig`.

**Chain:** a route preset's `default_purpose` ("Financieel advies") → copied into the quick-entry form by `handlePresetSelect` → sent to `POST /api/zzp/trips` → rejected by `TripService._validate_category_and_purpose` which checks `trip_purpose` against the `zzp_ritten.trip_purposes` parameter. That parameter has no configuration/seed surface anywhere in the codebase (read-only, half-wired), so every tenant is pinned to the MODULE_REGISTRY default list and any legitimate off-list purpose is rejected.

**Fix:** `trip_purpose` is treated as free-text, business-owned data; its allow-list validation is removed on the create path (`zzp_trip_service.py`) and the import path (`zzp_trip_import/validation.py`). `trip_category` stays validated (fixed taxonomy driving bijtelling). This complements Property 1/2 (the frontend now surfaces real errors; the backend no longer invents this one). Paired backend tests updated per the change-with-tests contract.
