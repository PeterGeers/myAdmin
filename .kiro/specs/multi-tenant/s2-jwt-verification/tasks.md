# S2 — Verify JWT Signatures on Both Backends — Tasks

- Status: Draft
- Companion to `requirements.md` + `design.md` (same folder). Task refs cite the
  requirement(s) each satisfies.

## Phase 1 — Test environment (prerequisite, in-scope)

- [~] **T1. Stand up the standing test Cognito pool** (R4, `environments_and_testing.md`)
  - Create a permanent Essentials-tier pool in the identity (personal) account,
    mirroring Pool A's app-client config, claim shapes, and groups.
  - Seed a small set of throwaway test users (one per role / claim shape).
  - Record the pool id, issuer (`iss`), `jwks_uri`, and app-client id.
  - Update `aws-accounts.md` with the created pool's real id (replace "to create").
- [~] **T2. Wire the test environment for local runs** (R4)
  - Confirm Docker MySQL + `test_`-prefixed DynamoDB are reachable.
  - Set fail-fast env vars for the issuer→pool registry pointing at the test pool
    (throw on missing — no defaults).

## Phase 2 — Shared verification contract

- [~] **T3. Define the issuer→pool registry** (R3.1, R3.2)
  - Config map `iss → { jwks_uri, audience/client_id, pool_label }`, env-driven,
    fail-fast. Seed with the test pool; structured so Pool A / Pool B are added as
    config later.
- [~] **T4. Implement JWKS fetch + cache with rotation handling** (R3.3)
  - Cache by `iss`; `kid` miss → single refetch; still unknown → 401.
  - Admin: module-level cache + TTL. Portal: global/execution-env scope.

## Phase 3 — Admin plane (Flask/MySQL, `mysaas/admin/`)

- [~] **T5. Extend `jwt_verifier.py` to the issuer→pool registry** (R1.2, R3)
  - Verify RS256 signature, `iss`, audience/`client_id`, `exp` against the resolved
    pool's JWKS.
- [~] **T6. Audit every authenticated route for verifier coverage** (R1.1)
  - Enumerate all authenticated routes; ensure the auth/tenant decorators are
    present on each; close gaps.
- [~] **T7. Remove unverified-header trust in admin** (R2)
  - Roles from verified `cognito:groups`; tenant from verified token; delete any
    read of `X-Enhanced-Groups` / `X-Tenant` as a source of truth.

## Phase 4 — Portal plane (SAM/Lambda, h-dcn origin) — signature verification only

> Portal gets **signature verification only** in S2. Reading **tenant** from the
> token needs tenant-awareness the portal does not have until **S5** — that binding
> is **out of scope here** (R2.4).

- [~] **T8. Replace base64-only decode in `auth_utils.py` with JWKS verification** (R1.2, R3)
  - Full signature contract per `design.md`; prefer the API Gateway Cognito
    authorizer, with handlers reading claims only from the verified context.
- [~] **T9. Remove unverified-header trust in portal** (R2.1, R2.2)
  - Drop `X-Enhanced-Groups` trust; derive groups from the verified token.
  - (Tenant-from-token binding: **deferred to S5**, not done here.)

## Phase 5 — Tests (against the test pool)

- [~] **T10. Verification test matrix — both planes** (acceptance criteria)
  - Valid token → accept; tampered signature → 401; wrong issuer → 401; wrong
    audience → 401; expired → 401; unknown `kid` (rotation) → refetch → accept/401.
- [~] **T11. Header-trust negative tests** (R2)
  - Setting `X-Enhanced-Groups` / `X-Tenant` has **no effect** on the authorization
    decision, on both planes.
- [~] **T12. Confirm test validation is complete before any prod promotion** (R4.1)
  - All test-matrix + header-trust tests green against the test pool + Docker MySQL
    + `test_` DynamoDB. This is the gate for Phase 6.

## Phase 6 — Gated promotion to production (the shippable outcome) (R4.2, R6)

- [~] **T13a. Add Pool A as a verified issuer** (R3, R6.1)
  - Extend the issuer→pool registry so production myAdmin verifies real Pool A tokens
    (`eu-west-1_Hdp40eWmu`), alongside the test pool.
- [~] **T13b. Promote verified-JWT behavior to myAdmin production** (R6.1, R6.3)
  - Deploy through the current myAdmin production pipeline (independent of S6b).
    Gate: test matrix green, staging/dry-run pass, rollback path ready.
  - Verify real Pool A tokens pass and header-trust removal causes no regression.
- [~] **T13c. Deploy portal signature verification to its (greenfield) production** (R6.2)
  - Low-stakes (~one real user). Tenant-claim completion remains S5.
- [~] **T13d. Confirm both live systems still work** (R6.2)
  - myAdmin fully hardened in prod; portal signature-verified. No half-broken state.

## Phase 7 — Governance (definition of done)

- [~] **T14. Author/extend auth steering** (R5.1)
  - Verified-JWT-only, no unverified-header trust, issuer→pool JWKS verification,
    cached JWKS + rotation (in `authentication.md` or extend `identity.md` /
    `architecture.md`).
- [~] **T15. Record the ADR** (R5.2)
  - "Verified-JWT-only; no unverified-header trust; per-issuer JWKS verification."
    Append-only in `docs/decisions/`.
- [~] **T16. Mark the spec Complete** and update the roadmap S2 status.

## Definition of done

- All acceptance criteria in `requirements.md` pass on **both** planes against the
  test pool **first** (the promotion gate).
- No authenticated route/handler reads claims from an unverified token; headers are
  ignored for authorization.
- **Shipped:** verified-JWT behavior is **live in myAdmin production** (admin plane
  fully hardened, incl. tenant/roles from the verified token), promoted after test
  validation. Portal has signature verification deployed to its greenfield
  production; portal **tenant-from-token is deferred to S5** and does not block S2.
- **Both live systems still work** — no half-broken intermediate state (the
  roadmap's shippable-step principle).
- Auth steering + ADR exist and match the implemented behavior.
