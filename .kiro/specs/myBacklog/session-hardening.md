# Session Hardening — Idle Logout (+ the phone trip-logger tension)

> **Backlog analysis, not an active spec.** Surfaced during the Railway-breach rotation
> (`.kiro/specs/Common/Security/railway-breach-rotation/`) but OUT OF SCOPE for it. Two distinct
> initiatives are captured here: (A) a 60-minute idle logout for the main app, and (B) an
> unauthenticated phone "quick trip registration" write path. They pull in OPPOSITE directions, so
> the design must reconcile them deliberately — see §4.

## 1. The concern (as reported)

- On any device, myAdmin reopens in the state it was left — even after days — without re-login.
- Desired: **enforce logout after 60 minutes** (of inactivity).
- Caveat: the **quick trip registration** on a phone should still be usable **without a login** — a
  simple app that tracks trips and stores the data in myAdmin.

## 2. Why it stays logged in for days (current behaviour — evidenced)

The persistence is **AWS Amplify (v6) doing what it is designed to do**, not a custom session.

- Amplify is configured once at boot (`frontend/src/index.tsx:11` → `Amplify.configure(awsconfig)`;
  config in `frontend/src/aws-exports.ts`, authorization-code + PKCE, scopes openid/email/profile).
- Amplify's default token storage is the browser's **localStorage**, so the id/access/refresh
  tokens survive tab close and browser restart. On load Amplify rehydrates the session.
- **Token lifetimes** (pinned in `infrastructure/cognito.tf` for app client `myAdmin-client`):
  - `access_token_validity = 60` minutes
  - `id_token_validity = 60` minutes
  - `refresh_token_validity = 30` **days**
  - `ALLOW_REFRESH_TOKEN_AUTH` enabled; public client (no secret).
- **Silent refresh:** every `fetchAuthSession()` (used across `authService.ts` and service modules)
  transparently exchanges the 30-day refresh token for fresh 60-minute tokens. This is what keeps a
  user effectively logged in for up to 30 days with no credential re-entry.
- **No idle/inactivity handling exists anywhere** (frontend or backend) — confirmed by search. The
  only logout is the explicit user-initiated `AuthContext.logout()` → Amplify `signOut()`
  (`frontend/src/context/AuthContext.tsx:139-147`). The only token gate is a point-in-time
  `isAuthenticated()` `exp` check in `authService.ts` — not inactivity-based.
- `app.py:120` sets `PERMANENT_SESSION_LIFETIME = 300`, but it is **inert**: there is no Flask
  `secret_key` and no `flask.session` usage, so it affects nothing.

### Key clarification (mental model)

The Cognito "60-minute" token validity is **not** the same as a 60-minute idle logout. The token
already expires every 60 minutes — but Amplify auto-renews it for 30 days. **Idle logout means
stopping that auto-renewal after 60 minutes of no user activity and forcing a fresh login.** That is
net-new work.

## 3. Backend is stateless — idle enforcement must be client-driven

- The Flask backend is **pure per-request JWT verification** (no server session, no `secret_key`).
  `@cognito_required` → `extract_user_credentials` → `JWTVerifier.verify_token` (RS256 vs JWKS,
  `iss`/audience/`exp` checked, 30s clock-skew leeway). An expired token → HTTP 401 "Token has
  expired" (`backend/src/auth/cognito_utils.py`, `backend/src/auth/jwt_verifier.py`).
- Fail-closed: in production, if the verifier is unconfigured, requests get 503 (no unsigned
  fallback). Base64 fallback is local-dev/test only.
- Consequence: the backend already enforces the 60-minute token `exp`, but it has **no concept of
  "last activity."** A client with a live Amplify session just presents a freshly-refreshed token.
  So an inactivity policy must be enforced **client-side** (stop Amplify auto-refresh / force
  `signOut()` after 60 min idle); the backend will keep accepting any still-valid/refreshed token.

## 4. The tension: idle logout vs. no-login phone trip-logger

These are opposite requirements and cannot share one session model:

- **(A) 60-min idle logout** → shorten/cap the session, force re-auth. More security, less convenience.
- **(B) no-login phone trip-logger** → a long-lived, login-free writer. Max convenience, and it
  deliberately bypasses the very login (A) enforces.

Therefore the trip-logger needs its **own, separate, narrowly-scoped auth path** — NOT the
Amplify/Cognito user session.

### Current trip endpoints block a no-login writer (evidenced)

`backend/src/routes/zzp_trip_routes.py` + `zzp_trip_import_export_routes.py`: **every** trip write
(create, gap-fill, update, cancel, import, commit) is triple-decorated
`@cognito_required(required_permissions=["zzp_crud"])` + `@tenant_required()` +
`@module_required("ZZP")`. There is **no** unauthenticated or lighter-auth write path, and the
`tenant` / `created_by` are derived from the **verified identity**, never from the request body.
Data lands in `zzp_trips` (tenant-scoped by `administration`) with a `zzp_trip_audit` trail.

So a no-login phone logger **cannot** reach the existing endpoints — it would require a NEW write
path with its own credential.

## 5. Options

### Initiative A — 60-minute idle logout (session hardening)

- **A1. Client-side idle timer.** Activity listeners (click/keypress/visibilitychange); after 60 min
  of no activity, call Amplify `signOut()` and route to login. Optionally a "you'll be logged out in
  N min" warning. Simplest; purely frontend; no infra change.
- **A2. Cap the effective session.** Also stop silent refresh past a hard ceiling (e.g. refuse to
  auto-renew beyond X hours) so even an active tab eventually re-auths. Stronger; more UX friction.
- **A3. Shorten the Cognito refresh token.** Lower `refresh_token_validity` in `cognito.tf` (e.g. 1
  day). Reduces the 30-day window but does NOT give a true 60-min *idle* logout on its own (an active
  user still refreshes). Best combined with A1. Requires a Cognito/Terraform change + redeploy.
- Recommended: **A1 (+ optionally A3)**. A1 delivers the actual "60-min idle" behaviour; A3 shrinks
  the worst-case persistence window as defense in depth.

### Initiative B — phone trip-logger without login (new scoped write path)

- **B1. Long-lived device token.** A per-device, revocable token scoped to ONE tenant + create-trip
  only (not full `zzp_crud`). New endpoint (e.g. `POST /api/zzp/trips/device`) authenticated by the
  device token, append-only, rate-limited. The phone stores the token; "re-activate without login"
  = the token persists on the device.
- **B2. Device-code / pairing flow.** Pair the phone once (authenticated), mint a device token, then
  login-free thereafter. Same server surface as B1, nicer onboarding.
- **B3. PWA with a very long Cognito refresh token for a dedicated app-client.** Reuses Cognito but
  with a separate public client tuned for long life. Simpler, but it is still a full user session
  (weaker scoping than a purpose-built device token) and re-introduces the persistence risk (A) is
  trying to remove — so it conflicts with A unless carefully separated.
- **Threat model to resolve before building:** a login-free writer is a credential on a phone that
  can write trip data for the tenant. If the phone is lost it must be **revocable**, **scoped**
  (single tenant, create-trip only), **append-only**, and **rate-limited**. Design, do not improvise.

## 6. Scope / sequencing recommendation

- Keep BOTH out of the Railway-breach rotation (which is nearly complete and focused).
- Treat each as its own lightweight spec when picked up:
  - **Session idle-timeout hardening** (Initiative A) — higher priority: persistent 30-day sessions
    on any device are exactly the exposure the breach mindset targets. Mostly a frontend change (A1),
    optionally a small Cognito change (A3).
  - **Phone trip-logger unauthenticated write path** (Initiative B) — a genuine NEW auth surface;
    design the threat model (B1/B2) before implementing. Lower priority / more care.

## 7. Open questions

1. Idle logout: hard logout at 60 min, or warn-then-logout? Any "remember me" exception?
2. Should the 60-min idle apply to ALL users, or exempt the trip-logger device entirely (likely yes,
   since B is a separate path)?
3. Trip-logger: how is a device paired/authorized the first time (B1 token issuance vs B2 pairing)?
4. Should `refresh_token_validity` (currently 30 days) be shortened as defense in depth (A3)?

---
*Source of current-state facts: code investigation on 2026-10-22 — `frontend/src/services/authService.ts`,
`frontend/src/aws-exports.ts`, `frontend/src/context/AuthContext.tsx`, `infrastructure/cognito.tf`,
`backend/src/auth/cognito_utils.py`, `backend/src/auth/jwt_verifier.py`,
`backend/src/routes/zzp_trip_routes.py` (+ import/export routes). No design committed.*
