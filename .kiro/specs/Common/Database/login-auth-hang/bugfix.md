# Bugfix Requirements Document

## Introduction

After a user logs in to the myAdmin frontend (running against the Railway-backed
backend), the app hangs on the loading screen showing "Authenticatiestatus
controleren" ("Checking authentication status") for 15+ minutes before it finally
renders. Once it does render, no data loads from the Railway database and the network
log is filled with `GET /api/auth/me` requests returning HTTP 401
`{"error":"Missing or invalid Authorization header"}`.

The user is genuinely authenticated: valid Cognito tokens (accessToken, idToken,
refreshToken, LastAuthUser) with intact `cognito:groups` and `custom:entitlements`
are present in localStorage. The defect is therefore not an authentication failure
but two coupled front-end sequencing problems:

- **Defect A (the hang):** the auth gate has no timeout. `checkAuthState()` in
  `frontend/src/context/AuthContext.tsx` sets `loading=true` and only clears it after
  a sequential await chain that includes `getCurrentUserRoles()`. That function does
  an un-timed, un-abortable `fetch(\`${apiUrl}/api/auth/me\`)` in
  `frontend/src/services/authService.ts` (~line 206). If that request (or its CORS
  preflight) stalls — consistent with a Railway cold start — the loading gate in
  `frontend/src/App.tsx` (~line 128) stays pinned for the full stall duration.

- **Defect B (the 401s / no data):** authenticated API calls are firing before the
  Amplify session/token is rehydrated. `getCurrentUserRoles()` only attaches
  `Authorization: Bearer <idToken>` when the idToken is already present; when the
  Amplify session has not rehydrated yet, requests go out with no header. The backend
  `backend/src/auth/cognito_utils.py` then returns 401
  `Missing or invalid Authorization header`, and the catch block silently swallows the
  failure ("API not available — fall back to JWT"), so no Railway data loads.

Relevant files:
- `frontend/src/context/AuthContext.tsx` — `checkAuthState`, `loading`, mount `useEffect`
- `frontend/src/services/authService.ts` — `getCurrentUserRoles`, the `/api/auth/me` fetch (~line 206)
- `frontend/src/App.tsx` — loading gate (~line 128), `/api/status` fetch (~line 92)
- `backend/src/auth/cognito_utils.py` — source of the 401 "Missing or invalid Authorization header"

## Bug Analysis

### Current Behavior (Defect)

What currently happens when a user logs in with valid Cognito tokens present, while
the backend `/api/auth/me` request (or its CORS preflight) is slow to respond:

1.1 WHEN the app mounts after login and the `/api/auth/me` fetch inside `getCurrentUserRoles()` stalls THEN the system keeps `loading=true` and stays on the "Authenticatiestatus controleren" loading gate for the full stall duration (observed 15+ minutes) with no timeout, abort, or fallback.

1.2 WHEN `checkAuthState()` runs on mount THEN the system awaits the full sequential chain (`checkAuthenticated` → `getCurrentUser` → `getCurrentUserEmail` → `getCurrentUserName` → `getCurrentUserRoles` → `getCurrentUserTenants`) before clearing `loading` in the `finally` block, so any one slow call blocks the entire auth gate.

1.3 WHEN an authenticated API call (e.g. `/api/auth/me` or a data fetch) is issued before the Amplify session/token has rehydrated THEN the system sends the request with no `Authorization: Bearer` header and the backend returns HTTP 401 `{"error":"Missing or invalid Authorization header"}`.

1.4 WHEN `getCurrentUserRoles()` receives a non-ok/401 response from `/api/auth/me` THEN the system silently swallows the failure in the empty catch block ("API not available — fall back to JWT") so the failure is invisible and no Railway data loads.

### Expected Behavior (Correct)

What should happen instead for those same conditions:

2.1 WHEN the app mounts after login and the `/api/auth/me` fetch is slow THEN the system SHALL bound the wait with a timeout/abort and resolve the auth gate promptly, degrading to JWT-derived roles (`cognito:groups`) rather than hanging on the loading screen.

2.2 WHEN `checkAuthState()` runs on mount THEN the system SHALL clear `loading` within a bounded time so the app renders promptly, regardless of any single slow downstream call.

2.3 WHEN an authenticated API call is issued THEN the system SHALL first ensure the Amplify session/token is rehydrated so the request carries a valid `Authorization: Bearer` header, and the backend SHALL accept it (no spurious 401).

2.4 WHEN `getCurrentUserRoles()` receives a non-ok/401 response from `/api/auth/me` THEN the system SHALL surface the failure (observable, e.g. logged) and fall back to JWT-derived roles so authenticated Railway data can still load.

### Unchanged Behavior (Regression Prevention)

Existing behavior that must be preserved for inputs that do NOT trigger the bug:

3.1 WHEN the user is not authenticated (no valid Cognito tokens) THEN the system SHALL CONTINUE TO set `user=null` and clear `loading`, showing the unauthenticated state as before.

3.2 WHEN `/api/auth/me` responds promptly with a valid Bearer header THEN the system SHALL CONTINUE TO use the merged (global + per-tenant) roles from the API response exactly as it does today.

3.3 WHEN the API is genuinely unavailable AND a valid session exists THEN the system SHALL CONTINUE TO fall back to JWT `cognito:groups` roles rather than clearing the user or blocking indefinitely.

3.4 WHEN the tenant is switched in-app via `refreshRolesForTenant(tenant)` THEN the system SHALL CONTINUE TO re-resolve only `user.roles` for that tenant, preserving the out-of-order guard (sequence + latest-requested-tenant) so a late response for a superseded tenant is discarded.

3.5 WHEN a request arrives at the backend with no, malformed, or empty `Authorization` header THEN `backend/src/auth/cognito_utils.py` SHALL CONTINUE TO return HTTP 401 `{"error":"Missing or invalid Authorization header"}` (the backend contract is correct and must not change).

## Bug Condition Derivation

### Bug Condition Function

```pascal
FUNCTION isBugCondition(X)
  INPUT: X of type AuthGateScenario
    // X describes an app-mount/auth scenario: session state, token
    // rehydration state, and downstream /api/auth/me latency.
  OUTPUT: boolean

  // The bug is triggered when the user is authenticated but either
  // (A) a downstream auth call stalls with no bounded wait, or
  // (B) an authenticated request fires before the Bearer token is ready.
  RETURN X.hasValidCognitoTokens = true
         AND (
           (X.authMeLatency > acceptableTimeout AND X.hasTimeoutOrAbort = false)
           OR
           (X.requestIssuedBeforeTokenRehydrated = true)
         )
END FUNCTION
```

### Property Specification (Fix Checking)

```pascal
// Property: Fix Checking - Bounded auth gate + Bearer-gated requests
FOR ALL X WHERE isBugCondition(X) DO
  result <- checkAuthState'(X)   // F' = fixed
  ASSERT loading_resolves_within_bounded_time(result)
     AND (authenticated_request(X) IMPLIES has_bearer_header(request))
     AND no_indefinite_hang(result)
END FOR
```

### Preservation Goal (Preservation Checking)

```pascal
// Property: Preservation Checking - non-buggy inputs unchanged
// F  = original (unfixed) behavior
// F' = fixed behavior
FOR ALL X WHERE NOT isBugCondition(X) DO
  ASSERT F(X) = F'(X)
END FOR
```

This ensures that for prompt-response logins, unauthenticated states, in-app tenant
switches, and the backend's 401 contract, the fixed code behaves identically to the
original.
