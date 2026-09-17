# S3 / T8 — System-of-Record Scope Ratification

- Status: Ratified
- Task: **T8. Ratify the system-of-record scope** (`tasks.md`, Phase 3 / D2)
- Requirements: **R3.1, R3.2, R3.3**
- Companion to `requirements.md` + `design.md` (D2) + `claim-contract.md` (same folder).
- Feeds: **ADR 0005** (T28) and the auth/tenant steering (T27).

> T8 is a **ratification / confirmation** task — no production code change and no
> property-based test. This note records what was inspected and the two findings the
> task must settle: (1) the MySQL scope of authority, and (2) that authority does **not**
> move to the module plane and no module owns a writable copy. A focused validation test
> was added where it adds value (see "Validation" below).

## What was ratified (R3.1)

`tenants`, `tenant_modules`, and `user_tenant_roles` are the **authoritative** source for
tenant governance — which tenants exist, which modules each tenant has enabled, and which
per-tenant roles each user holds — for **all** tenants, **including** tenants that will
later enable **SAM-backed modules** (not only finance tenants).

Confirmed by inspecting the DDL — the three tables are keyed on the tenancy key
`administration` and carry no module-specific coupling, so they cover a SAM-backed-module
tenant (e.g. an h-dcn tenant entitled to `members`/`events`/`webshop` once S5 lands)
identically to a finance tenant:

| Table | DDL | Key | Authoritative for |
| --- | --- | --- | --- |
| `tenants` | `backend/sql/create_tenants_table.sql` | `administration` (UNIQUE) | which tenants exist + tenant-level attributes |
| `tenant_modules` | `backend/sql/phase5_tenant_modules.sql` | `(administration, module_name)` UNIQUE; `is_active` | which modules each tenant has enabled |
| `user_tenant_roles` | `backend/src/migrations/create_user_tenant_roles.sql` | `(email, administration, role)` UNIQUE; FK → `tenants(administration)` | per-user, per-tenant role grants |

Backing-agnostic by construction: `tenant_modules` records `module_name` with **no**
`backing` awareness, and `MODULE_REGISTRY` entitlement
(`services/module_registry.py` — `has_module` / `module_required` / `activate_module`)
reads `tenant_modules` **only** and never inspects the descriptor's `backing` kind. A
`sam`-backed module is entitled, enabled, and role-gated exactly like an in-process
`flask` module. This is the settled S1 position (module-contract Seam 2 — "A SAM-backed
module introduces no new entitlement path").

## Global vs per-tenant authority (R3.2)

- **Global** roles — `SysAdmin` / `Administrators` / `System_CRUD` — are sourced from the
  token's `cognito:groups` (the claim contract, D1).
- **Everything per-tenant** is resolved from `user_tenant_roles`. On the Flask plane this
  is `backend/src/auth/role_cache.py` → the parameterized
  `SELECT role FROM user_tenant_roles WHERE email = %s AND administration = %s` (cached,
  5-min TTL). `role_cache.py` reads **no** other governance table and derives roles from
  **no** claim. (Pinned by `test_s3_per_tenant_role_source_of_record.py`, T5.)

## Authority does not move to the module plane / no writable copy (R3.3)

The load-bearing finding. Authority for tenant governance stays in MySQL; the module
plane (SAM/Lambda) never becomes a second writer:

- **No module owns a writable copy.** A module's need for tenant/module/role facts is met
  in exactly one of two one-directional ways — the **token** (S4 entitlement projection)
  or the **read-only MySQL→DynamoDB projection** (D3). Both flow *forward* from MySQL;
  MySQL remains the sole writer of record. This is the S1 "Data ownership" seam.
- **Never a request-time MySQL query from a Lambda.** The Flask plane can afford a cached
  MySQL read (`role_cache.py`) because it is a monolith next to MySQL; a Lambda cannot,
  and the S1 contract forbids the stopgap.
- **Confirmed at the module plane (`sam/`).** The shipped module-plane code
  (`sam/shared/auth_utils.py`) authorizes from the **verified token only** —
  `get_verified_identity` / `get_verified_claims` / `get_groups` read `sub` / `email` /
  `cognito:groups` from verified claims and nothing else. There is:
  - **no MySQL client** anywhere under `sam/` — a grep for
    `mysql` / `pymysql` / `mysql.connector` / `DatabaseManager` / `execute_query` /
    `connect(` returns **no matches**; and
  - **no MySQL dependency** — `sam/shared/requirements.txt` pins only `PyJWT`,
    `cryptography`, `requests` (no DB driver);
  - **no read of `user_tenant_roles` / `tenant_modules`** on the request path.

  So the module plane is structurally incapable of opening a MySQL connection or of
  writing governance facts back — the "no writable copy / no two-way write" invariant
  holds by construction, not merely by convention.

## Relationship to the retired `tenant_role_allocation` (context, owned by T9/T10)

The dead `tenant_role_allocation` table is **not** part of the system of record. It is
confirmed absent in dev and prod with **no code readers**; available roles derive from
`tenant_modules` + Cognito groups. Its retirement (delete of the unused DDL file) is
tracked by **T9** (confirm no readers) and **T10** (retire) — noted here only so the
ratified scope is unambiguous: the system of record is exactly the three tables above.

## Validation

A focused, no-DB validation test was added to keep the R3.3 finding from silently
regressing (a future edit adding a MySQL client to the module plane would break it):

- `backend/tests/unit/test_s3_system_of_record_scope.py`
  - Asserts the module plane (`sam/`) declares **no** MySQL client dependency
    (`sam/shared/requirements.txt`) and imports **no** MySQL client in any `sam/*.py`
    source (AST-level import scan) — the "authority does not move to the module plane /
    no writable copy" guardrail (R3.1–R3.3).
  - Asserts the three system-of-record tables' DDL exists and is keyed on
    `administration` (R3.1).

Existing coverage this complements (not duplicates):
- `test_s3_per_tenant_role_source_of_record.py` (T5) — per-tenant roles resolve from
  MySQL, global roles from the token, no token-claim authoring.
- `test_module_registry.py` — entitlement is backing-agnostic (`tenant_modules` only).
- `test_check_db_imports.py` — the `mysql.connector` import boundary for `backend/`.

## Findings summary

- **R3.1 — ratified.** The three MySQL tables are authoritative for governance across all
  tenants, including SAM-backed-module tenants; entitlement is backing-agnostic.
- **R3.2 — confirmed.** Global roles from `cognito:groups`; per-tenant roles from
  `user_tenant_roles` via `role_cache.py`.
- **R3.3 — confirmed.** Authority does not move to the module plane and no module owns a
  writable copy; the `sam/` plane has no MySQL client and reads only the verified token.
  Module needs are met via the token (S4) or the read-only projection (D3), never a
  request-time MySQL query from a Lambda.

---

# S3 / T9 — Confirmation: no remaining readers of `tenant_role_allocation`

- Status: Confirmed
- Task: **T9. Confirm no remaining readers of `tenant_role_allocation`** (`tasks.md`, Phase 3 / D2)
- Requirements: **R3.4**
- Gates: **T10** (retirement). This is a confirmation/verification task — **no** production
  code changed and **nothing** was deleted here (delete of the artifact is T10's job).

## Verdict

**No remaining readers — Y/N: N (there are none).** Safe to proceed to T10.

## DDL artifact existence

The only physical artifact the design/requirements attributed to the dead table —
`backend/sql/create_tenant_role_allocation_table.sql` — **does not exist**:

- `file_search` for `create_tenant_role_allocation_table.sql` (including gitignored
  files) → **no files found**.
- Directory listing of `backend/sql/` (48 files) contains **no**
  `create_tenant_role_allocation_table.sql`.

This confirms the prior orchestrator observation: the DDL file was already removed. There
is therefore no code artifact for T10 to delete; T10 is effectively a record-only closeout
(the table is absent in dev/prod per prior confirmation, and the DDL file is gone).

## Reader search — scope and results

Searched application code, scripts, SQL, the module plane, and migrations for any
**reader** (SELECT / JOIN / query / ORM model / code that reads the table):

| Scope searched | Query | Result |
| --- | --- | --- |
| `backend/src/**`, `backend/sql/**`, `backend/scripts/**`, `scripts/**`, `sam/**`, `backend/src/migrations/**` | `tenant_role_allocation` | **no matches** |
| Repo-wide code files (`**/*.py,*.sql,*.js,*.ts,*.sh,*.yaml,*.yml,*.toml`), case-insensitive | `tenant.?role.?allocation` | 1 match — a **negative-assertion test** (not a reader), see below |
| `**/migrations/**`, `**/*.json` | `tenant.?role.?allocation` | only spec metadata (`tasks.meta.json`) — not a reader |

### Code readers vs doc/comment/test mentions

- **Code readers: NONE.** No SELECT/JOIN/query, no ORM model, no code reads the table
  anywhere under `backend/src/`, `backend/sql/`, `backend/scripts/`, `scripts/`, `sam/`,
  or the JSON/SQL migrations.
- The specifically cited file, `backend/src/auth/role_cache.py`, reads **only**
  `user_tenant_roles` (`SELECT role FROM user_tenant_roles WHERE email = %s AND
  administration = %s`) — it does not reference `tenant_role_allocation`.
- The single code-file match repo-wide is
  `backend/tests/unit/test_s3_per_tenant_role_source_of_record.py`:
  `assert "tenant_role_allocation" not in source`. This is a **guardrail assertion** (a
  test that the table is NOT read), i.e. the opposite of a reader.
- All other matches are **documentation / spec mentions** (this spec's `design.md`,
  `requirements.md`, `tasks.md`, roadmap/analysis docs, and the SysAdmin-Module spec,
  which explicitly lists the table as *removed from scope* and derives available roles
  from `tenant_modules` + Cognito groups).

## Corroboration

- SysAdmin-Module spec (`.kiro/specs/Common/SysAdmin-Module/design.md`,`TASKS.md`,
  review summary) records the table as removed and derives roles from `tenant_modules` +
  Cognito groups — consistent with the grounded expectation.
- The T8 ratification (above) already confirmed the module plane (`sam/`) has no MySQL
  client at all, so no Lambda reads any governance table, let alone this one.

## Findings summary (R3.4)

- **DDL file:** `backend/sql/create_tenant_role_allocation_table.sql` — **absent**
  (already removed).
- **Readers:** **none** in code, SQL, scripts, the module plane, or migrations; the only
  code reference is a negative-assertion guardrail test.
- **Verdict:** no remaining readers → **T10 (retirement) is unblocked**; T10 has no file
  to delete and is a record-only close-out.

---

# S3 / T10 — Retirement of `tenant_role_allocation` (record-only, additive/safe)

- Status: Retired
- Task: **T10. Retire `tenant_role_allocation` (additive/safe)** (`tasks.md`, Phase 3 / D2)
- Requirements: **R3.4, R4** (safe/additive — non-destructive)
- Gated by: **T9** (confirmed no remaining readers; DDL artifact already absent).
- Feeds: **ADR 0005** (T28) and the auth/tenant steering (T27).

> T10 is a **record-only** close-out. T9 established there is nothing to delete and no
> data to drop; this note formally records the artifact as retired so the definition of
> done (D2) and ADR 0005 can cite a settled retirement.

## What was done (and deliberately not done)

- **DDL file — verified absent again, nothing deleted.** Re-checked at T10 time:
  `file_search` for `create_tenant_role_allocation_table.sql` (including gitignored
  files) → **no files found**. The unused DDL artifact was already removed prior to S3, so
  there was no file for T10 to delete. Had it existed, T10 would have removed **only** that
  one unused DDL file and nothing else.
- **No database table dropped, no data destroyed.** The `tenant_role_allocation` table is
  confirmed **absent** in dev and prod — there is no physical table and no rows. No
  `DROP TABLE`, no migration, and no touch of any live governance data. Consistent with the
  workspace data-ownership rule: never destroy live data. **R4 (safe/additive) holds — the
  retirement is non-destructive.**
- **No live readers — reconfirmed at T10.** A final repo-wide search for
  `tenant_role_allocation` (`**/*.{py,sql,js,ts,sh,yaml,yml,toml}`) returns a **single**
  match: the negative-assertion guardrail test
  `backend/tests/unit/test_s3_per_tenant_role_source_of_record.py`
  (`assert "tenant_role_allocation" not in source`) — the opposite of a reader. No
  SELECT/JOIN/ORM/query reads the table anywhere in code, SQL, scripts, the `sam/` module
  plane, or migrations. All remaining textual mentions are documentation/spec references.

## Retirement record

| Aspect | State at retirement |
| --- | --- |
| DDL artifact (`backend/sql/create_tenant_role_allocation_table.sql`) | **Absent** (already removed; nothing deleted by T10) |
| Physical table (dev / prod) | **Absent** — no table, no rows |
| Code / SQL / script / Lambda readers | **None** (only a negative-assertion guardrail test) |
| Data lost | **None** — nothing dropped or destroyed |
| Nature of change | **Additive / safe (R4)** — record-only close-out |
| System of record after retirement | Exactly `tenants` + `tenant_modules` + `user_tenant_roles` (per T8) |

The negative-assertion guardrail test is retained intentionally: it pins the retirement so
a future edit re-introducing a reader of `tenant_role_allocation` fails loudly.

## Findings summary (R3.4, R4)

- **R3.4 — retired.** `tenant_role_allocation` is retired: DDL artifact absent, no physical
  table/data, no remaining readers. The system of record is unambiguously the three tables
  ratified in T8.
- **R4 — safe.** The retirement was non-destructive and additive: nothing live was touched,
  no table dropped, no data lost. Verified by re-checking artifact absence and the reader
  search rather than by any delete.
- **Feeds ADR 0005 (T28):** this retirement, with "no readers / no data loss", is the
  evidence the ADR cites for the D2 outcome — "`tenant_role_allocation` retired with no
  remaining readers and no data loss".

---

# S3 / T24 — Pool A confirmed as-is (record-only, R1.5 / R4.2)

- Status: Confirmed as-is (no pool-side change)
- Task: **T24. Promote any Pool A-side change to production Pool A, gated** (`tasks.md`, Phase 5)
- Requirements: **R1.5, R4.2**
- Companion to `requirements.md` + `design.md` (D1) + `claim-contract.md` (same folder).
- Feeds: **ADR 0005** (T28); settles `migration_plan.md` **Gate 1** Pool A confirmation.

> T24 is a **record-only** close-out. It has **zero** production mutation. No Cognito API
> call, no pool config change, no live change of any kind was made to production Pool A
> (`eu-west-1_Hdp40eWmu`). This note formally records the settled outcome so the definition
> of done (D1) and ADR 0005 can cite it, and so `migration_plan.md` Gate 1's Pool A
> confirmation is closed.

## Verdict

**No pool-side change was needed → Pool A is confirmed as-is.**

S3 required **no** claim-tightening and **no** pool-side change to production Pool A beyond
what S2 already settled. The D1 deliverable was to *document and validate* an already-correct
claim shape (T3–T7), not to rebuild or modify the pool. Under design D1 ("Pool-side change is
gated": *"If no change is needed, Pool A is confirmed as-is and that is recorded"*) and R1.5
(*"If S3 needs no pool-side change (contract already correct), that is recorded and Pool A is
confirmed as-is"*), this is the recorded confirmation.

## What was re-verified (read-only / doc-level)

| Evidence | Confirms |
| --- | --- |
| `design.md` → D1 "Pool-side change is gated" | Records the no-change → confirm-as-is path explicitly. |
| `requirements.md` → R1.5 | No pool-side change ⇒ record + confirm Pool A as-is. |
| `claim-contract.md` (T3) | Pool A already carries `cognito:groups` (GLOBAL roles) + `custom:tenants` (list) exactly as the S2 verifier expects; **S3 adds no verification code**; selection is **config-only** via the S2 issuer→pool registry (select by `iss`). |
| `backend/.env.example` (lines ~128–132) | "No pool-side change was needed: Pool A already issues RS256/JWKS tokens with cognito:groups + custom:tenants exactly as the S2 verifier expects (confirmed by a read-only diff against the standing test pool — identical attrs/groups/LambdaConfig)." Pool A's registry entry (`PROD_A_COGNITO_*`) already exists (added in S2). |
| `system-of-record-ratification.md` (T8) | The `sam/` module plane authorizes from the verified token only; the claim contract is read through the existing S2 path — no new S3 pool machinery. |

No evidence anywhere that S3 required a pool-side change. The D1 tasks (T3–T7) were
documentation + validation of the existing shape; no `AWS`/Cognito mutation was ever
introduced by S3.

## No production mutation (R4.2)

- **Zero** live/AWS change to production Pool A (`eu-west-1_Hdp40eWmu`): no Cognito API
  mutation, no pool config change.
- Pool selection is **config-not-code** (S2 registry): both planes select Pool A by `iss`;
  Pool A's registry entry (`PROD_A_COGNITO_*`) already exists from S2. Nothing to promote.
- R4.2 ("promote to production only after test validation, gated") is satisfied **vacuously**
  — there is no pool-side change to promote. A rollback path is therefore not applicable
  (nothing was changed).

## Settlement

- **`migration_plan.md` Gate 1 — Pool A confirmation: SETTLED.** Pool A = the admin
  `myAdmin` pool (`eu-west-1_Hdp40eWmu`), confirmed as-is. **Pool B is deferred** (not built
  in S3; addable later as a config-only S2 registry entry).
- **Feeds ADR 0005 (T28):** this confirmation ("no pool-side change; Pool A confirmed as-is;
  selection is config-not-code") is the evidence the ADR cites for the D1 outcome.

## Findings summary (R1.5, R4.2)

- **R1.5 — confirmed as-is.** S3 needed no pool-side change; the Pool A claim contract was
  already correct. Recorded here; Pool A confirmed as-is.
- **R4.2 — satisfied (no promotion needed).** No production Pool A mutation was made; there
  was nothing to gate/promote. Config-not-code selection means Pool A's registry entry was
  already in place from S2.
- **Gate 1 (migration_plan.md):** Pool A confirmation settled (Pool A now; Pool B deferred).
