# Implementation Plan

## S3 — Tenant/Role Claims + Tenant System-of-Record + Projection to DynamoDB — Tasks

- Status: Draft
- Companion to `requirements.md` + `design.md` (same folder). Task refs cite the
  requirement(s) each satisfies.
- Decision of record: ADR 0003 + ADR 0004; S3 authors ADR 0005 (Phase 6).

> S3 is claims-contract + system-of-record + a build-heavy one-directional projection.
> Test-first: everything is validated against the **test pool (`eu-west-1_xyrlzfqbl`) +
> Docker MySQL + `test_` DynamoDB** before any production Pool A change. Governance
> (steering + ADR 0005) is part of the definition of done. Sub-tasks marked `*` are
> optional (tests) and are not implemented by default. Language: the existing Python
> backend (no language choice needed — design uses real code, not pseudocode).

## Overview

A phased, test-first implementation plan: stand up the test environment (Phase 1),
validate the Pool A claim contract without rebuilding it (Phase 2), ratify and harden the
MySQL system-of-record and retire the dead table (Phase 3), build the build-heavy
one-directional MySQL→DynamoDB projection with property tests (Phase 4), then gate
production promotion and the manual legacy-pool decommission (Phase 5) and close out
governance — steering + ADR 0005 (Phase 6). Local dev/test tooling is set up first (Phase 0): local DynamoDB-in-Docker so the
projection and its tests run offline (long-running processes via `control_bash_process`).
Everything is validated against the test pool + Docker MySQL + **local DynamoDB**
(preferred; cloud `test_` / `-Test` tables as fallback) before any production Pool A change.

## Tasks

## Phase 0 — Local dev/test tooling (do first)

> Decision: set up local DynamoDB-in-Docker **up front** so the projection (Phase 4)
> and its tests run **locally** rather than against cloud `test_` / `-Test` tables. Any
> long-running process here (docker compose, `sam local`, DynamoDB Local) MUST be run via
> the **`control_bash_process`** tool (action `start`, background) — never as a foreground
> `execute_bash`, which blocks the session. Match-or-better than h-dcn's setup
> (`~/projects/h-dcn/scripts/local/` + its `local-backend-testing` spec); if it cannot
> clearly beat that, fall back to the `test_`/`-Test` cloud tables (S3 does not hard-depend
> on local DynamoDB).

> **T0 implementation note (done).** The long-running-process discipline and the
> local-DynamoDB workflow are recorded in the steering file
> `.kiro/steering/local-dynamodb-testing.md` (every later phase follows it). Local
> DynamoDB is wired into `docker-compose.yml` (`dynamodb-local`, `-sharedDb`, network
> `myadmin-local`, alias `dynamodb-local:8000`, host `8000`); the projection's DynamoDB
> client (`backend/src/services/dynamodb_client.py`) uses `AWS_ENDPOINT_URL_DYNAMODB`
> only when set and fail-fasts on missing table/region (R4.1); seed/teardown live at
> `scripts/local/`; env vars documented in `backend/.env.example`.

- [x] **T0. Stand up local DynamoDB (Docker) + long-running-process discipline** (R4.1)
  - **(a) Long-running-process rule:** run docker compose / `sam local` / DynamoDB Local
    with **`control_bash_process`** (`start` in background; monitor/stop as needed). Do NOT
    launch them via foreground `execute_bash`. Document this in the S3 workflow so every
    later phase follows it.
  - **(b) Local DynamoDB (the T30 work, brought forward):** add `amazon/dynamodb-local`
    (`-sharedDb`) to myAdmin's existing `docker-compose.yml` so it comes up alongside MySQL
    + backend in one stack (better than h-dcn's standalone scripts). Point the projection's
    DynamoDB client at `AWS_ENDPOINT_URL_DYNAMODB` **only when set**, fail-fast otherwise
    (no accidental cloud writes, no silent fallback — S3 R4.1). Provide seed + teardown and
    a short local-testing note/steering. Reference h-dcn: named network so `sam local`
    reaches it at `dynamodb-local:8000`, host port `8000` for seeding via
    `http://localhost:8000`; native WSL Docker (not Docker Desktop).
  - **Outcome:** Phase 4's projection + property/integration tests run fully **offline**
    against local DynamoDB; the cloud `test_` / `-Test` tables become a fallback, not the
    primary local path. If local DynamoDB is not clearly better, skip (b) and keep using
    `test_` tables — but still adopt (a).

## Phase 1 — Test environment (prerequisite, in-scope)

- [x] **T1. Confirm the test environment is wired for S3** (R4.1)
  - Confirm the standing test pool `eu-west-1_xyrlzfqbl` (S2 fixture) is reachable and
    registered in the issuer→pool registry (`COGNITO_POOL_KEYS`), Docker MySQL is up,
    and `test_`-prefixed DynamoDB is reachable.
  - Set fail-fast env vars for the projection table name (`test_` prefix) and the pool
    registry (throw on missing — **no defaults**, no production fallback).
- [x] **T2. Seed test governance fixtures** (R4.1)
  - Seed Docker MySQL with a small, reproducible set of `tenants`, `tenant_modules`
    (incl. a SAM-backed-module tenant, e.g. h-dcn → members/events/webshop), and
    `user_tenant_roles` rows — one per role/claim shape. Scripted, throwaway.
  - **Add-on — GoodwinSolutions test-login instructions (deliverable of T2).** Produce a
    short how-to (in this spec folder, e.g. `INSTRUCTIONS.md`, or a README section) for
    logging in and testing as the **GoodwinSolutions** tenant with each enabled module and
    the appropriate per-module role. Ground it in the verified facts below; state the
    current wiring gap honestly (local dev today points at production Pool A — test-pool
    wiring is T1; a GoodwinSolutions-scoped **test** user does not exist yet — this task
    seeds it).
    - **GoodwinSolutions enabled modules** (dev `tenant_modules`): **FIN, STR, TENADMIN,
      ZZP** (all active).
    - **Module → required role(s)** (`services/module_registry.py`): FIN →
      `Finance_CRUD` / `Finance_Read` / `Finance_Export`; STR → `STR_CRUD` / `STR_Read` /
      `STR_Export`; TENADMIN → `Tenant_Admin`; ZZP (`depends_on: FIN`) → `ZZP_CRUD` /
      `ZZP_Read` / `ZZP_Export`.
    - **Role → capability** (`auth/cognito_utils.py` `ROLE_PERMISSIONS`): `*_CRUD` =
      create/read/update/delete/list/export for that module; `*_Read` = read/list;
      `*_Export` = export (+read); `Tenant_Admin` = tenant admin/config/users/modules/
      storage; `SysAdmin` = system config/logs/audit only (**no tenant data**);
      `Administrators` / `System_CRUD` = wildcard `*`.
    - **How authz resolves** (so the doc is correct): GLOBAL roles come from the token
      `cognito:groups`; PER-TENANT roles (the Finance_*/STR_*/ZZP_*/Tenant_Admin grants)
      resolve from MySQL `user_tenant_roles` via `auth/role_cache.py` — **not** the token.
      `custom:tenants` lists selectable tenants; the `X-Tenant` header selects one and is
      validated against that list (unlisted → 403). So testing "as GoodwinSolutions with
      module X's role" needs: (a) a test-pool user whose `custom:tenants` includes
      `GoodwinSolutions`, (b) matching `user_tenant_roles` rows for
      `administration='GoodwinSolutions'` for that user's email, (c) `X-Tenant:
      GoodwinSolutions` on requests.
    - **Seed a GoodwinSolutions test user** (this task): e.g. `test-goodwin@example.com`
      with `custom:tenants` including `GoodwinSolutions`, and `user_tenant_roles` rows for
      `administration='GoodwinSolutions'` covering all four modules — full-access set
      `Finance_CRUD, STR_CRUD, ZZP_CRUD, Tenant_Admin` (mirroring the real full-access
      grant `peter@pgeers.nl`), plus optional read-only variants (`Finance_Read`,
      `STR_Read`, `ZZP_Read`) to test allow/deny (e.g. `Finance_Read` can view but a
      create → 403).
    - **Per-module verification checklist** the doc should include: for each of
      FIN / STR / TENADMIN / ZZP — the role that unlocks it, one representative screen/
      endpoint, and expected allow vs 403. Gotchas: `X-Tenant` must be in the verified
      `custom:tenants`; ZZP depends on FIN; SysAdmin is global (no tenant data); token
      claims refresh only on re-login; WSL pager/exit-code notes live in
      `shell-environment.md`.

## Phase 2 — D1: Pool A claim contract (identity claims) — validate, don't rebuild

- [x] **T3. Document Pool A's claim shape as the platform contract** (R1.1)
  - `cognito:groups` = GLOBAL roles only (SysAdmin / Administrators / System_CRUD);
    `custom:tenants` = the user's tenant list; per-tenant roles live in MySQL
    `user_tenant_roles`, **not** the token in S3. This wording seeds the Phase 6 steering.
- [x] **T4. Validate Pool A selection + claim interpretation via the S2 registry** (R1.2, R4.1)
  - Confirm both planes select Pool A by `iss` (S2 registry, config-not-code) and read
    `cognito:groups`/`custom:tenants` correctly. **No new verification code** — reuse the
    S2 path; add validation only.
- [x] **T5. Confirm per-tenant role resolution stays in MySQL** (R1.3)
  - Confirm `backend/src/auth/role_cache.py` resolves per-tenant roles from
    `user_tenant_roles`; only global roles come from `cognito:groups`. Confirm S3 adds
    **no** per-tenant role / entitlement claim to the token (entitlement-in-token = S4).
- [x] **T6. Integration test — Pool A claim contract (against the test pool)** (acceptance: D1)
  - 1–3 examples: a test-pool token → selected as Pool A; `cognito:groups` read as global
    roles; `custom:tenants` read as the tenant list; per-tenant roles NOT taken from the
    token. Reuse the S2 harness.
- [x] **T7. Unit tests — role_cache per-tenant resolution** (R1.3)
  - Seeded `user_tenant_roles` rows → correct per-tenant role set; global roles come from
    `cognito:groups`.

## Phase 3 — D2: MySQL system-of-record (ratify + harden + retire dead table)

- [x] **T8. Ratify the system-of-record scope** (R3.1, R3.2, R3.3)
  - Confirm `tenants` / `tenant_modules` / `user_tenant_roles` are authoritative for
    **all** tenants incl. SAM-backed-module tenants (not only finance). Confirm authority
    does not move to the module plane and no module owns a writable copy.
- [x] **T9. Confirm no remaining readers of `tenant_role_allocation`** (R3.4)
  - Grep application code, scripts, and SQL for readers. (Grounded: `role_cache.py` and
    `backend/` have none; only `backend/sql/create_tenant_role_allocation_table.sql`
    remains; SysAdmin-Module already derives roles from `tenant_modules` + groups.)
- [x] **T10. Retire `tenant_role_allocation` (additive/safe)** (R3.4, R4)
  - Deprecate/remove the dead DDL artifact after T9 confirms no readers. Do **not**
    destroy any live governance data. Record the retirement (feeds the ADR).

## Phase 4 — D3: One-directional MySQL→DynamoDB projection (build-heavy)

- [x] **T11. Define the projection table shape + fail-fast resolution** (R5.4, R4.1)
  - `{ENV_PREFIX}governance_projection`: PK `tenant_id` (== `administration`), SK
    `record_type#id`, `version` attr. Env-resolved table name (`test_` in test/dev),
    fail-fast on missing. Plan IAM `dynamodb:LeadingKeys` scoping.
- [x] **T12. Implement the pure `ProjectionItem` builder** (R5.3)
  - `(tenant, tenant_modules[], user_tenant_roles[]) -> ProjectionItem[]` for the
    tenant-level subset (tenants with SAM-backed modules enabled). Exclude any
    token-only (per-user resolved) data — that is S4. Attach `version`.
- [x] **T13. Property test — projection fidelity** (R5.3)
  - **Property 2: Projection fidelity (exactly the tenant-level subset)**
  - **Validates: Requirements R5.3**
- [x] **T14. Implement `ProjectionValidator` (write-time validation)** (R5.5)
  - Reject an item missing its tenant key / required fields; sync fails loudly, no
    partial write.
- [x] **T15. Property test — write-time validation** (R5.5)
  - **Property 5: Write-time validation rejects malformed rows**
  - **Validates: Requirements R5.5**
- [x] **T16. Implement `ProjectionSync` (sole writer, versioned, idempotent)** (R5.1, R5.2, R5.6, R5.9)
  - Read source rows, build + validate items, conditional-write (`version` monotonic) to
    the projection table. **Zero** MySQL writes; sync is the only writer of the table.
- [x] **T17. Property test — one-directional projection** (R5.1, R5.2, R5.9)
  - **Property 1: One-directional projection (write-only, no split brain)**
  - **Validates: Requirements R5.1, R5.2, R5.9**
- [x] **T18. Property test — idempotent, versioned sync** (R5.6, R5.8)
  - **Property 4: Idempotent, versioned sync**
  - **Validates: Requirements R5.6, R5.8**
- [x] **T19. Implement tenant-scoped read side + cache invalidation** (R5.4, R5.8, R5.9)
  - Module read path reads only its own `tenant_id` partition; compares `version` for
    staleness/refresh; **never** writes the projection or MySQL.
- [x] **T20. Property test — tenant isolation** (R5.4)
  - **Property 3: Tenant isolation of the projection**
  - **Validates: Requirements R5.4**
- [x] **T21. Implement the on-change sync trigger + reconciliation backstop** (R5.7)
  - Governance write paths (provisioning / module enable-disable / role grant) enqueue a
    sync for the affected `administration`; a periodic idempotent reconciliation backstops
    missed signals. Bounded, documented delay.
- [x] **T22. Property test — convergence after a source change** (R5.7, R5.8)
  - **Property 6: Convergence after a source change**
  - **Validates: Requirements R5.7, R5.8**

- [x] **T23. Checkpoint — projection validated against LOCAL DynamoDB (T0)**
  - Ensure all property tests + the end-to-end sync smoke (Docker MySQL → **local**
    DynamoDB projection → tenant-scoped read) pass, using the Phase 0 local stack (cloud
    `test_` / `-Test` tables only as fallback). Ask the user if questions arise. This gates
    any production step.

## Phase 5 — Gated promotion + legacy-pool decommission (manual, high-risk)

> Production Pool A (`eu-west-1_Hdp40eWmu`) is touched only after Phase 2–4 pass on the
> test environment. Legacy-pool decommission is manual and dependency-gated.

- [x] **T24. Promote any Pool A-side change to production Pool A, gated** (R1.5, R4.2)
  - If D1 required a pool-side change, apply the exact change already validated on the
    test pool to Pool A in place (rollback path ready). If no pool-side change was
    needed, record Pool A as confirmed as-is. Settles the `migration_plan.md` Gate 1
    Pool A confirmation.
- [x] **T25. Promote the projection to production, gated** (R4.2, R4.3)
  - Create the production projection table (PAY_PER_REQUEST, `DeletionPolicy: Retain` /
    managed outside CFN) and run the sync; verify a tenant-scoped read. Gate on T23.
- [x] **T26. Decommission legacy pools — manual, dependency-checked** (R2.1, R2.2, R2.3)
  - Confirm no application/Railway/IaC dependency on `eu-west-1_OAT3oPCIm`,
    `eu-west-1_VtKQHhXGN`; final backup; **manual** deletion.
    Guardrail: **never** Pool A (`eu-west-1_Hdp40eWmu`) or the test pool
    (`eu-west-1_xyrlzfqbl`) — assert the exclusion, not a comment.

## Phase 6 — Governance (definition of done)

- [x] **T27. Author/extend auth/tenant steering** (R6.1)
  - Record the Pool A claim contract (global roles in `cognito:groups`, `custom:tenants`
    list, per-tenant roles in MySQL); MySQL as tenant system-of-record; the
    one-directional MySQL→DynamoDB projection rule (write-only, versioned, no split
    brain, module reads only). Fold into `identity.md` / `architecture.md` or a scoped
    tenant-data steering file.
- [x] **T28. Record ADR 0005** (R6.2)
  - "Two-pool (audience-split) identity — **Pool A now, Pool B deferred**; MySQL is the
    tenant system-of-record; one-directional MySQL→DynamoDB projection." Note that adding
    Pool B later is config-only via the S2 registry. Append-only in `docs/decisions/`.
- [x] **T29. Mark the spec Complete** and update the roadmap S3 status + governance-delta
      row.

## Phase 7 — (moved) Local DynamoDB tooling is now Phase 0 / T0

> **Moved up.** What was an optional post-S3 nice-to-have (local DynamoDB-in-Docker) is
> now done **up front** in **Phase 0 / T0** so the projection tests run locally from the
> start. See T0 for the authoritative task. The reference detail below is retained for
> context; the actionable checkbox lives in T0. If local DynamoDB does not clearly beat the
> `test_`/`-Test` cloud tables, fall back to those — S3 does not hard-depend on it.

- [ ] **T30. Local DynamoDB (Docker) for offline projection testing - match-or-better than h-dcn** (nice-to-have)
  - **Reference (h-dcn, `~/projects/h-dcn/scripts/local/` + its `local-backend-testing`
    spec):** an `amazon/dynamodb-local` container (`-sharedDb`) on a named Docker network
    (`hdcn-local`, alias `dynamodb-local`) reachable by SAM local at
    `http://dynamodb-local:8000`, host port `8000` published for seeding via
    `http://localhost:8000`; handlers use `AWS_ENDPOINT_URL_DYNAMODB`; idempotent
    up/down scripts + a seed script; native WSL Docker (not Docker Desktop).
  - **"Better" bar for myAdmin (only adopt if it clears it):** fold DynamoDB Local into
    myAdmin's existing compose stack so it starts alongside MySQL + backend in one command
    (one stack, not separate scripts); point the S3 projection's DynamoDB client at
    `AWS_ENDPOINT_URL_DYNAMODB` **only when set**, fail-fast otherwise (no accidental cloud
    writes, no silent fallback - consistent with S3 R4.1); provide seed + teardown;
    document it in a myAdmin local-testing note/steering.
  - **Payoff:** the S3 projection (D3) and its property/integration tests run fully
    offline against local DynamoDB instead of the cloud `test_` / `-Test` tables - the
    `test_`-table approach becomes a fallback, not the primary local path.
  - **Guardrail:** this changes only the *local test* datastore wiring; it must not alter
    the projection's one-directional contract, production behavior, or the fail-fast env
    discipline. If it cannot clearly beat the h-dcn/`test_`-table status quo, do not ship it.

## Definition of done

- **D1:** Pool A's claim shape is documented and validated (groups=global roles,
  `custom:tenants`=list, per-tenant roles from MySQL via `role_cache.py`); both planes
  select Pool A by `iss` via the S2 registry. Any Pool A-side change was validated on the
  test pool first, then gated to production; `migration_plan.md` Gate 1 Pool A
  confirmation is settled.
- **D2:** `tenants` / `tenant_modules` / `user_tenant_roles` ratified as authoritative for
  SAM-module tenants as well as finance tenants; `tenant_role_allocation` retired with no
  remaining readers and no data loss.
- **D3:** the tenant-level projection is **one-directional** (write-only, sync is the sole
  writer, module reads only), **validated** at write time, **versioned + idempotent**,
  tenant-scoped, converges after source changes, and invalidates the read side on version
  change — all validated against `test_` DynamoDB + Docker MySQL first.
- **No dangerous fallback:** missing pool/registry/table env vars fail fast; nothing can
  silently point identity or projection work at production.
- **Pool B not precluded:** nothing built in S3 blocks adding Pool B later as a
  config-only registry entry with a singular `tenant_id` claim.
- **Governance:** auth/tenant steering + ADR 0005 exist and match the implemented
  behavior; roadmap S3 status updated.

## Notes

- Tasks marked `*` are optional (property/integration/unit tests) and can be skipped for
  a faster MVP; core implementation tasks are never optional.
- Property tests run **≥100 iterations** and are tagged **Feature: s3-claims-and-projection,
  Property {N}: {property text}**; MySQL/DynamoDB are faked in-memory so properties test
  logic, not the datastores.
- S3's projection (tenant-level → DynamoDB table) is **distinct from S4** (per-user
  resolved answer → token). Do not conflate.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["T1", "T2"] },
    { "id": 1, "tasks": ["T3", "T5", "T8", "T9", "T11"] },
    { "id": 2, "tasks": ["T4", "T10", "T12", "T14"] },
    { "id": 3, "tasks": ["T6", "T7", "T13", "T15", "T16"] },
    { "id": 4, "tasks": ["T17", "T18", "T19"] },
    { "id": 5, "tasks": ["T20", "T21"] },
    { "id": 6, "tasks": ["T22"] },
    { "id": 7, "tasks": ["T24", "T25", "T26"] },
    { "id": 8, "tasks": ["T27", "T28"] }
  ]
}
```
