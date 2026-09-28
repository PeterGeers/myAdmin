# Implementation Plan — S4: Project Resolved Entitlement into the Token

- Status: Complete (functions delivered; live production trigger — T18 — deferred to S5, the first app migration)
- Spec: `.kiro/specs/multi-tenant/s4-token-entitlement-projection/` (`requirements.md`, `design.md`)
- Roadmap step: S4. Depends on S2 (done) + S3 (done) + the standing test pool.
- Convention: test-first (test pool + Docker MySQL) → gated promotion to Pool A. Property
  tests use Hypothesis, ≥100 iterations, tagged `Feature: s4-token-entitlement-projection,
  Property N: ...`. Follow workspace database-patterns + testing-standards. Long-running
  processes via the background-process tool (`.kiro/steering/local-dynamodb-testing.md`).

## Overview

S4 stamps each user's resolved per-tenant entitlement (roles ∩ active modules) into the
Pool A token at issuance via a Cognito Pre-Token-Generation Lambda, so both planes —
especially a SAM-backed module's Lambda — authorize from the verified token alone,
without a request-time MySQL query. A single pure resolver is the source of truth and is
shared with the Flask plane's `role_cache.py` + module gate (one rule, two carriers).
Built test-first (test pool + Docker MySQL), then gated to production Pool A.

## Tasks

## Phase 0 — Environment + fixtures

- [x] **T0. Confirm the S4 test environment** (R6.1)
  - Reuse S3's stack: test pool `eu-west-1_xyrlzfqbl` in the issuer→pool registry, Docker
    MySQL up, `user_tenant_roles` / `tenant_modules` fixtures present (the S3 seed script
    `scripts/local/seed-governance-mysql.py` — e.g. GoodwinSolutions + `s3test_*`). Add
    any S4-specific test users/rows needed (a multi-tenant user for the size-budget case).
    Fail-fast env for the Lambda's MySQL config (no dangerous fallback).

## Phase 1 — D1: the pure resolver (single source of truth)

- [x] **T1. Implement the pure `resolve_entitlement` resolver** (R1.1, R1.2, R1.4)
  - `(user_roles_by_tenant, active_modules_by_tenant, module_registry) -> per-tenant
    entitlement map`. Pure (no I/O), deterministic. Capability present iff a granting role
    is held AND its module is active for that tenant; backing-agnostic; global roles not
    re-derived. Place in shared backend code (e.g. `backend/src/auth/entitlement_resolver.py`)
    so both the Lambda and the Flask plane import it.
- [x] **T2. Prove resolver ≡ Flask decision** (R1.3, R4.1)
  - A shared decision helper (or test) that composes `role_cache.get_tenant_roles` +
    `module_registry` gate, and assert the resolver yields the identical decision. This is
    the one-rule-two-carriers guarantee; example unit tests here, property in T7.
- [x] **T3. Unit tests — resolver examples/edge cases** (R1.1)
  - Seeded rows → expected entitlement: full-access user, read-only user, role for an
    inactive module (excluded), tenant with no active modules (empty), multi-tenant user,
    unicode emails, duplicate roles. `backend/tests/unit/`.

## Phase 2 — D3: claim codec (shape, size, versioning)

- [x] **T4. Implement the entitlement claim codec** (R3.1, R3.2, R3.3)
  - Encode/decode `custom:entitlements` = `{ v, t: {tenant->[cap]}, [overflow] }`;
    version marker; compact encoding; size-budget check; over-budget → overflow signal
    (never silent truncation); unknown `v` on decode → safe fallback.
- [x] **T5. Unit tests — codec + budget boundaries** (R3.1, R3.2, R3.3) — covered by test_entitlement_claim_codec.py (T4): 25 tests incl. round-trip, at/over-budget overflow (not truncation), unknown-version fallback, empty + large-near-budget.
  - Round-trip identity; at/over the size budget → overflow signal not truncation;
    unknown-version decode falls back. `backend/tests/unit/`.

## Phase 3 — property-based verification (resolver + codec)

- [x] **T6. Property test — resolver equivalence to the Flask plane** (R1.3, R4.1)
  - **Property 1** — for any state, the resolver's decision equals `role_cache` + module
    gate for every `(user, tenant, capability)`. Hypothesis, ≥100 examples, MySQL faked.
- [x] **T7. Property test — only active-module capabilities are entitled** (R1.1)
  - **Property 2** — no inactive/absent module's capability appears; disabling a module
    removes exactly its capabilities.
- [x] **T8. Property test — tenant isolation of entitlement** (R1.1)
  - **Property 3** — tenant `T`'s entitlement depends only on `T`'s roles + active
    modules, never another tenant's.
- [x] **T9. Property test — purity / determinism** (R1.2)
  - **Property 4** — resolving twice yields an identical map.
- [x] **T10. Property test — claim round-trip + budget** (R3.1, R3.2, R3.3)
  - **Property 5** — encode→decode identity; fits budget or signals overflow; unknown
    `v` → fallback.

## Phase 4 — D2: the Pre-Token-Generation Lambda

- [x] **T11. Implement the PreTokenGen Lambda handler** (R2.1, R2.2, R2.4)
  - V2 trigger. Identify the user from the event; read `user_tenant_roles` +
    active `tenant_modules` read-only (DatabaseManager, parameterized); call the T1
    resolver; encode via T4; set `claimsToAddOrOverride` additively (do NOT touch
    `cognito:groups` / `custom:tenants`). Zero governance writes.
- [x] **T12. Fail-safe + fail-fast wiring** (R2.3, R2.5)
  - Resolution failure → omit the claim (fail-closed for entitlement) + log by user
    identity (no secrets); never a partial/garbage claim. Missing DB/registry config →
    fail-fast throw (no wrong-datastore fallback).
- [x] **T13. Unit tests — Lambda handler (mocked Cognito event + faked MySQL)** (R2.1–R2.5) — covered by sam/tests/test_pretokengen_handler.py + test_pretokengen_failsafe.py (T11/T12): happy-path additive stamping, resolution error omits+logs, missing config throws, existing claims untouched, read-only DB. 24 passed.
  - Happy path stamps the expected claim additively; resolution error omits the claim +
    logs; missing config throws; existing claims untouched. `backend/tests/unit/`.

## Phase 5 — read side (both planes, additive)

- [x] **T14. Module-plane reader** (R5.1, R5.2)
  - Extend `sam/shared/auth_utils.py` (+ tests in `sam/tests/`) to read + decode the
    entitlement claim from the **verified** token and expose a per-tenant capability
    check — no MySQL, no S3 read for the per-user answer. Reuse the S2 verify harness.
- [x] **T15. Flask-plane reader (optional, additive)** (R5.3)
  - An optional helper that prefers the token claim and falls back to `role_cache.py`,
    guaranteed the same decision (T2/T6). No regression to existing Flask authorization.

## Phase 6 — integration + gated promotion

- [x] **T16. Integration test — token carries entitlement (test pool)** (acceptance)
  - 1–3 examples against the **test pool + Docker MySQL**: a seeded test user logs in;
    the issued token carries the expected `custom:entitlements`; `cognito:groups` /
    `custom:tenants` unchanged; the module-plane reader authorizes correctly. Reuse the
    S2/S3 harness. Ask the user if questions arise. Gates the production step.
- [x] **T17. Decide + document staleness + revocation** (R4.2, R4.3)
  - Fix the token-lifetime / staleness window and the revocation policy for
    security-critical downgrades (short lifetime + forced re-auth and/or server-side
    check for the sensitive subset). Record it (feeds the ADR).
- [~] **T18. Promote the PreTokenGen trigger to production Pool A, gated** (R6.2, R6.3) — DEFERRED to S5 (first app migration). Rationale: wire the live trigger driven by a real consumer, not in a vacuum; functions are built+tested+available. See ADR 0006 + s5-members-first-migration/migration-plan.md.
  - Attach the validated Lambda as Pool A's Pre-Token-Generation trigger **only after**
    T16 passes. Rollback path = detach the trigger (restores prior behavior). Verify a
    real Pool A token carries the claim and existing claims are unchanged. Never prod-first;
    no dangerous fallback. **High-risk / human-gated — confirm before attaching.**

## Phase 7 — governance (definition of done)

- [x] **T19. Author/extend architecture + auth steering** (R7.1)
  - Record: entitlement projected into the token at issuance (not per-request MySQL); the
    token = per-user path, S3 DynamoDB = tenant-level path (do not conflate); the single
    shared resolver; the bounded-staleness + revocation decision. Fold into
    `architecture.md` / `authentication.md`.
- [x] **T20. Record ADR 0006** (R7.2)
  - "Resolved per-tenant entitlement projected into the Pool A token via a
    Pre-Token-Generation Lambda; one resolver shared with `role_cache.py`; bounded
    staleness + revocation policy; Pool B deferred (no entitlement claim)." Append-only in
    `docs/decisions/`, matching the 0005 format.
- [x] **T21. Mark the spec Complete** and update the roadmap S4 status + governance-delta row.

## Definition of done

- **D1 resolver:** pure, deterministic, equivalent to `role_cache.py` + module gate
  (Properties 1–4 pass); global roles unchanged.
- **D3 codec:** compact, versioned, round-trips, respects the size budget with a defined
  over-budget signal (Property 5 pass); never silently truncated.
- **D2 Lambda:** stamps the entitlement claim at issuance from a read-only MySQL read,
  additive to existing Pool A claims, fail-safe (no partial claim), fail-fast on config.
- **Read side:** the module plane authorizes from the verified token claim with no
  request-time MySQL; the Flask plane is unchanged and any adoption yields the same
  decision.
- **Staleness/revocation:** bounded, documented window + a defined revocation policy.
- **Test-first + gated:** validated on the test pool + Docker MySQL first; the Pool A
  trigger attached only after validation, with a rollback path; no dangerous fallback.
- **Pool B not precluded.**
- **Governance:** architecture/auth steering + ADR 0006 exist and match the behavior;
  roadmap S4 status updated.


## Notes

- **Distinct from S3 (do not conflate).** S3 projects *tenant-level* facts into a
  DynamoDB table; S4 projects the *per-user resolved* answer into the token. Both may be
  needed; this spec builds only the S4 token path.
- **One resolver, two carriers.** The pure resolver (T1) is the single resolution rule,
  imported by both the PreTokenGen Lambda and the Flask plane, so the token claim and
  `role_cache.py` can never disagree for the same MySQL state (equivalence proven in T2/T6).
- **High-risk step:** T18 attaches a trigger to production Pool A — human-gated, confirm
  before attaching; rollback = detach the trigger.
- **Pool B is deferred** (no entitlement claim); S4 must not preclude it.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["T0"] },
    { "id": 1, "tasks": ["T1", "T4"] },
    { "id": 2, "tasks": ["T2", "T3", "T5"] },
    { "id": 3, "tasks": ["T6", "T7", "T8", "T9", "T10"] },
    { "id": 4, "tasks": ["T11"] },
    { "id": 5, "tasks": ["T12", "T13"] },
    { "id": 6, "tasks": ["T14", "T15"] },
    { "id": 7, "tasks": ["T16", "T17"] },
    { "id": 8, "tasks": ["T18"] },
    { "id": 9, "tasks": ["T19", "T20"] },
    { "id": 10, "tasks": ["T21"] }
  ]
}
```
