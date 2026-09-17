# S2 — Verify JWT Signatures on Both Backends — Tasks

- Status: Complete
- Companion to `requirements.md` + `design.md` (same folder). Task refs cite the
  requirement(s) each satisfies.

## Phase 1 — Test environment (prerequisite, in-scope)

- [x] **T1. Stand up the standing test Cognito pool** (R4, R6.0, `environments_and_testing.md`)
  - Create a standing Essentials-tier pool in the identity (personal) account that
    **mirrors production Pool A** (app-client config, claim shapes, groups, and the
    Pre-Token-Generation trigger). This pool becomes a **permanent part of the
    test/dev environment** — the pool that local dev and the test suite authenticate
    against for all identity work (S2/S3/S4), alongside Docker MySQL + `test_`
    DynamoDB. It is **NOT** a second production pool; production stays on the existing
    Pool A — the Cognito pool **named `myAdmin`** (`eu-west-1_Hdp40eWmu`) — which S2
    updates in place (R6.0).
  - Seed a small set of throwaway test users (one per role / claim shape).
  - Record the pool id, issuer (`iss`), `jwks_uri`, and app-client id.
  - Update `aws-accounts.md` with the created pool's real id (replace "to create").
- [x] **T2. Wire the test environment for local runs** (R4)
  - Confirm Docker MySQL + `test_`-prefixed DynamoDB are reachable.
  - Set fail-fast env vars for the issuer→pool registry pointing at the test pool
    (throw on missing — no defaults).

## Phase 2 — Shared verification contract

- [x] **T3. Define the issuer→pool registry** (R3.1, R3.2)
  - Config map `iss → { jwks_uri, audience/client_id, pool_label }`, env-driven,
    fail-fast. Pools are **configuration, not code**: the test pool is the first
    registry entry (validation environment); **production Pool A
    (`eu-west-1_Hdp40eWmu`) is added as a registry entry in Phase 6**, Pool B later.
    Adding a pool is never a code change.
- [x] **T4. Implement JWKS fetch + cache with rotation handling** (R3.3)
  - Cache by `iss`; `kid` miss → single refetch; still unknown → 401.
  - Flask plane: module-level cache + TTL. Module plane: global/execution-env scope.

## Phase 3 — Flask plane (myAdmin — Flask/MySQL)

- [x] **T5. Extend `jwt_verifier.py` to the issuer→pool registry** (R1.2, R3)
  - Verify RS256 signature, `iss`, audience/`client_id`, `exp` against the resolved
    pool's JWKS.
- [x] **T6. Audit every authenticated route for verifier coverage** (R1.1)
  - Enumerate all authenticated routes; ensure the auth/tenant decorators are
    present on each; close gaps.
- [x] **T7. Remove unverified-header trust in the Flask plane** (R2)
  - Roles from verified `cognito:groups`; tenant from verified token; delete any
    read of `X-Enhanced-Groups` / `X-Tenant` as a source of truth.

## Phase 4 — Module plane (SAM/Lambda — the h-dcn SAM stack: members/events/webshop) — signature verification only

> The module plane gets **signature verification only** in S2. Reading **tenant**
> from the token needs tenant-awareness the module does not have until **S5** — that
> binding is **out of scope here** (R2.4).

- [x] **T8. Replace base64-only decode in `auth_utils.py` with JWKS verification** (R1.2, R3)
  - Full signature contract per `design.md`; prefer the API Gateway Cognito
    authorizer, with handlers reading claims only from the verified context.
- [x] **T9. Remove unverified-header trust in the module plane** (R2.1, R2.2)
  - Drop `X-Enhanced-Groups` trust; derive groups from the verified token.
  - (Tenant-from-token binding: **deferred to S5**, not done here.)

## Phase 5 — Tests (against the test pool)

- [x] **T10. Verification test matrix — both planes** (acceptance criteria)
  - Valid token → accept; tampered signature → 401; wrong issuer → 401; wrong
    audience → 401; expired → 401; unknown `kid` (rotation) → refetch → accept/401.
- [x] **T11. Header-trust negative tests** (R2)
  - Setting `X-Enhanced-Groups` / `X-Tenant` has **no effect** on the authorization
    decision, on both planes.
- [x] **T12. Confirm test validation is complete before any prod promotion** (R4.1)
  - All test-matrix + header-trust tests green against the test pool + Docker MySQL
    + `test_` DynamoDB. This is the gate for Phase 6.

## Phase 6 — Update the existing production pool (Pool A) in place, gated (R4.2, R6)

> Production stays on the **existing** Pool A (`eu-west-1_Hdp40eWmu`). No new
> production pool is created — whatever pool-side change S2 needs was first validated
> on the standing **test pool** (T1, the permanent test/dev fixture) and is now
> applied to Pool A itself. (R6.0)

> **Plan change (ADR 0003):** myAdmin is the platform base and h-dcn modules are
> **imported into it** — there is **no separate h-dcn SAM stack to deploy** in S2.
> The module-plane signature-verification tooling is delivered as the self-contained
> `sam/` module in the myAdmin repo and is the **mandated starting point** that
> imported modules adopt (documented in S1 `module-contract.md`). So the module-plane
> work below is "tooling shipped + documented for import," not a deploy.

- [x] **T13a. Apply the S2 pool-side change to the existing Pool A (rehearsed on the test pool)** (R6.0, R6.1)
  - Make on Pool A (`eu-west-1_Hdp40eWmu`) whatever pool-side change S2 requires —
    e.g. app-client audience, claim shape, or Pre-Token-Generation trigger — identical
    to the change already validated on the test pool. **Update in place; do not create
    a new pool.** If S2 needs no pool-side change, record that and skip to T13b.
  - Register Pool A's `iss` / `jwks_uri` in the issuer→pool registry (config, not code)
    so production myAdmin verifies real Pool A tokens alongside the test pool.
- [x] **T13b. Promote verified-JWT behavior to myAdmin production and validate against Pool A** (R6.1, R6.3, R3.2)
  - Deploy through myAdmin's existing production pipeline (myAdmin is the base,
    evolved in place — no trunk cutover). Gate: test matrix green, staging/dry-run
    pass, rollback path ready.
  - **Terminal step:** confirm **real Pool A tokens verify against Pool A's JWKS in
    production** and that header-trust removal causes no regression. S2 is not done
    until the change is validated against the **existing production pool**, not only
    the test pool.
- [x] **T13c. Deliver module-plane signature verification as the `sam/` import starting point (no separate deploy)** (R6.2)
  - **Plan corrected (ADR 0003):** there is **no separate h-dcn SAM stack to deploy**.
    myAdmin is the platform base; h-dcn modules are **imported into it**. The
    module-plane signature-verification tooling is delivered as the self-contained
    `sam/` module in the myAdmin repo (`sam/shared/auth_utils.py`), and it is the
    **mandated starting point** that imported modules adopt (vendored as a shared
    module or Lambda layer). h-dcn's own stack is **not modified**.
  - **Deliverable:** the `sam/` tooling **plus** its documentation as the import
    starting point in S1 `module-contract.md` (Seam 3) — **not** a deploy. Nothing to
    promote to a greenfield production. Tenant-claim completion remains **S5**.
- [x] **T13d. Confirm myAdmin prod verified and module-plane tooling ready + documented for import** (R6.2)
  - The **Flask plane (myAdmin)** is live/hardened in production and validated against
    Pool A (forged token → 401, real token → 200). The **module plane** has **no
    separate live system in S2** — its tooling ships as `sam/` for future imports. So
    "both live systems still work" reduces to: **myAdmin prod verified; module-plane
    tooling ready and documented for import** (`sam/` + S1 `module-contract.md`). No
    half-broken state.

## Phase 7 — Governance (definition of done)

- [x] **T14. Author/extend auth steering** (R5.1)
  - Verified-JWT-only, no unverified-header trust, issuer→pool JWKS verification,
    cached JWKS + rotation (in `authentication.md` or extend `identity.md` /
    `architecture.md`).
- [x] **T15. Record the ADR** (R5.2)
  - "Verified-JWT-only; no unverified-header trust; per-issuer JWKS verification."
    Append-only in `docs/decisions/`.
- [x] **T16. Mark the spec Complete** and update the roadmap S2 status.

## Definition of done

- All acceptance criteria in `requirements.md` pass on **both** planes against the
  test pool **first** (the promotion gate).
- No authenticated route/handler reads claims from an unverified token; headers are
  ignored for authorization.
- **Shipped:** verified-JWT behavior is **live in myAdmin production** (Flask plane
  fully hardened, incl. tenant/roles from the verified token), promoted after test
  validation. The module plane has signature verification deployed to its greenfield
  production; module plane **tenant-from-token is deferred to S5** and does not block S2.
- **Existing production pool updated in place:** the change is validated first on the
  standing **test pool** (a permanent test/dev fixture), then applied to and verified
  against the **existing production pool Pool A** (`eu-west-1_Hdp40eWmu`). No new
  production pool is created; the test pool is the durable validation environment, not
  the destination (R6.0, R3.2).
- **Both live systems still work** — no half-broken intermediate state (the
  roadmap's shippable-step principle).
- Auth steering + ADR exist and match the implemented behavior.
