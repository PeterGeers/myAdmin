# S3 / T25 — Production Promotion of the Governance Projection

- Status: Promoted (production projection table created; sync ran; verified empty)
- Task: **T25. Promote the projection to production, gated** (`tasks.md`, Phase 5)
- Requirements: **R4.2, R4.3** (test-first, then gated promotion of the validated path)
- Gated by: **T23** (projection sync + read validated against LOCAL DynamoDB — passed)
- Companion to `requirements.md` + `design.md` (D3) + `system-of-record-ratification.md`.
- Guardrails followed: `.kiro/steering/aws-accounts.md` + `Analysis/migration_plan.md`
  (a prior CFN deploy DELETED prod data — hence: table managed OUTSIDE CloudFormation,
  retain semantics, PAY_PER_REQUEST, region eu-west-1, non-destructive only).

> T25 promotes the **already-validated** (T23, local DynamoDB) one-directional
> MySQL→DynamoDB projection path to production. It creates the production projection
> table and runs the sync in a **safe, scoped** way. The correct, expected outcome for
> today is a **created-but-empty** table: the shipped `MODULE_REGISTRY` registers no
> SAM-backed module, so the projection builder emits **zero** items until S5 registers
> real SAM modules. Nothing to project yet ≠ a failure — it is the designed state.

## Production table (created, managed OUTSIDE CloudFormation)

| Aspect | Value |
| --- | --- |
| **Table name** | `governance_projection` (production; drops the `test_` dev/test prefix — design's `{ENV_PREFIX}governance_projection`) |
| **AWS account** | `506221081911` (infrastructure & data account — where DynamoDB lives, per `aws-accounts.md`) |
| **Region** | `eu-west-1` |
| **ARN** | `arn:aws:dynamodb:eu-west-1:506221081911:table/governance_projection` |
| **Partition key (PK)** | `tenant_id` (S) — `== administration`, the tenancy boundary (R5.4) |
| **Sort key (SK)** | `sk` (S) — holds the `record_type#id` composite (e.g. `tenant`, `module#members`, `role#email#role`) |
| **Version attribute** | `version` (non-key, per-item; monotonic — R5.6) |
| **Billing mode** | `PAY_PER_REQUEST` (on-demand) |
| **Status** | `ACTIVE` |
| **Managed by** | **Outside CloudFormation** — created directly via boto3/CLI. No CFN stack owns it, so no stack update/delete can drop it. Tagged `managed-by=outside-cloudformation`, `spec=s3-claims-and-projection`, `deletion-policy=retain-human-only`. |

Key schema matches T11 / design D3 exactly and matches the local table created by the T0
seed script (`scripts/local/seed-dynamodb-local.py`), so the validated path (T23) and the
production path share one shape.

### Create method (exact call)

Created idempotently via boto3 (`nonprofit-deploy` profile → assumes
`NonprofitDeployRole` into `506221081911`), equivalent to:

```
aws dynamodb create-table \
  --table-name governance_projection \
  --attribute-definitions \
      AttributeName=tenant_id,AttributeType=S \
      AttributeName=sk,AttributeType=S \
  --key-schema \
      AttributeName=tenant_id,KeyType=HASH \
      AttributeName=sk,KeyType=RANGE \
  --billing-mode PAY_PER_REQUEST \
  --tags Key=managed-by,Value=outside-cloudformation \
         Key=spec,Value=s3-claims-and-projection \
         Key=deletion-policy,Value=retain-human-only \
  --profile nonprofit-deploy --region eu-west-1
```

**Preflight (before mutating):** `describe_table governance_projection` returned
`ResourceNotFoundException` → the table did **not** previously exist → this was a create,
not a modify. The create logic is idempotent: had the table existed, the run would
**skip** creation and report "existed" — it never deletes, recreates, or modifies an
existing table.

## Sync scope + what it wrote

The sync is the **sole writer** of the projection table (R5.1/R5.2/R5.9) and is read-only
against MySQL. It was run in a **safe, scoped** way, NOT a blind `sync_all()`:

- **T23 hazard handled (no crash, no partial writes).** The projection builder's
  SAM-gate resolves each active module's backing via `MODULE_REGISTRY`; an **unknown**
  module (one not yet registered) makes `module_backing()` **raise**. A blind
  `sync_all()` across a real tenant carrying a not-yet-registered module (members / events
  / webshop — those land in S5) would abort. The scoped runner therefore **skips** any
  tenant whose active modules are not all recognized by the shipped `MODULE_REGISTRY`,
  logging the skip, rather than crashing or writing partial data. The shipped
  `MODULE_REGISTRY` was **not** modified to force this.
- **Deterministic empty projection.** `MODULE_REGISTRY` registers exactly
  `FIN, STR, TENADMIN, ZZP` — **all `flask`-backed, ZERO SAM-backed**. The builder emits
  items only for tenants with a **SAM-backed** module enabled, so it produces **zero
  items for every tenant** regardless of source until S5 registers real SAM modules.

**Sync result (production `governance_projection`):**

- Tenants seen: **11**
- Eligible & synced (all active modules recognized): **9**
  (`GoodwinSolutions, InterimManagement, kimengerbrand, kimgeers, PeterPrive, s3test_fin,
  s3test_full, s3test_str, vandenheuvelhoveniers`)
- Skipped for unknown modules (deferred to S5, T23 guard): **2**
  - `myAdmin` → `ADMIN`
  - `s3test_hdcn` → `events`, `members`, `webshop`
- **Items written: 0** — nothing to project yet (no SAM-backed module registered). This is
  the valid, expected result.

> Source note: the reachable MySQL in the promotion environment is the standing
> dev/governance DB, not the Railway production DB (no Railway prod DB connection is
> configured here). Because the projection output is **deterministically empty** (no
> SAM-backed module registered), **zero** items were written to the production table
> regardless of source — no dev data was or could be projected into production. When S5
> registers real SAM modules and the sync runs against the production system-of-record,
> the same scoped sync will populate the table; until then the correct state is empty.

## Tenant-scoped read verification (R4.3 path, against production)

Verified with the real `ProjectionReader` (the module-plane read side) against the
**production** table, per tenant (partition-key scoped, R5.4):

- `ProjectionReader.query_tenant(<administration>)` for all 11 tenants → **0 items** total.
- Independent check: `aws dynamodb scan --table-name governance_projection --select COUNT`
  → `Count: 0`.

→ The production projection is **EMPTY**, matching the expected outcome. The read path
(the T23-validated `ProjectionReader`) works against the production table; there is simply
nothing projected yet.

## Fail-fast / no-dangerous-fallback discipline actually exercised (R4.1)

- `AWS_ENDPOINT_URL_DYNAMODB` was **UNSET** for the production run — the fail-fast client
  (`backend/src/services/dynamodb_client.py`) then resolves **real AWS**. (The local `.env`
  sets it to `http://localhost:8000` for the local emulator; the promotion run explicitly
  removed that leak and asserted the endpoint override was `None` before any write.)
- `GOVERNANCE_PROJECTION_TABLE=governance_projection` (production name; no `test_` prefix).
- `AWS_REGION=eu-west-1`.
- Credentials: the `nonprofit-deploy` profile (assumes `NonprofitDeployRole` into
  `506221081911`). The run asserted `sts:GetCallerIdentity` = account `506221081911`
  before writing, refusing to proceed against any other account. (Static personal-account
  keys leaked by `.env` were removed so the profile — not the wrong account — was used.)

## Rollback / runbook

The promotion created **one empty table** and wrote **zero items** — the blast radius is a
single new, empty resource. Because the table is managed **outside CloudFormation** with
**retain / human-only deletion** semantics, no automated process can remove it.

**To (re-)populate the projection later (normal operation, non-destructive):**
- Ensure S5 has registered the real SAM-backed module(s) in `MODULE_REGISTRY`.
- Run the scoped sync against the **production system-of-record** (Railway MySQL) with:
  `GOVERNANCE_PROJECTION_TABLE=governance_projection`, `AWS_REGION=eu-west-1`,
  `AWS_ENDPOINT_URL_DYNAMODB` **UNSET**, credentials = `nonprofit-deploy` profile.
  The sync is idempotent (R5.6): re-runs on unchanged source are no-ops. On-change
  triggers + periodic reconciliation (`services/projection_sync_trigger.py`, T21) keep it
  converged within a bounded delay (R5.7/R5.8).

**To safely disable/remove (requires EXPLICIT human action — never automated):**
- **Disable (reversible):** point the module plane away from the projection (config), or
  stop the sync trigger/reconciliation. The table + data are left intact.
- **Remove (irreversible — DATA DELETION, human-gated):** deleting the table
  (`aws dynamodb delete-table --table-name governance_projection --profile nonprofit-deploy
  --region eu-west-1`) is a **destructive** operation and must be performed **manually by a
  human**, with a backup first, mirroring the `aws-accounts.md` / `migration_plan.md`
  guardrail (never `--delete` / `rm --recursive` against data; back up before any data
  move). No tooling in this repo deletes it. Today the table is empty, so removal loses no
  data — but the human-gated discipline still applies so the pattern holds once S5
  populates it.

**Blast-radius / safety summary:** new empty table only; no existing table touched; no
MySQL write; no data deleted; PAY_PER_REQUEST so an empty table costs ~nothing at rest.

## Findings summary (R4.2, R4.3)

- **R4.2 — satisfied.** The projection path validated on the local stack (T23) was
  promoted to production **only after** that validation, gated on T23, with a rollback
  path ready (above). Production endpoint = real AWS; no prod-first work.
- **R4.3 — satisfied.** The sync + read path (validated against local DynamoDB in T23) was
  exercised against the **production** projection table: table created, scoped sync ran
  without crashing on unknown-module tenants, and a tenant-scoped `ProjectionReader` read
  confirmed the (expected-empty) state.
- **Expected-empty is correct.** Zero items projected because no SAM-backed module is
  registered yet; S5 populates the projection. The table, shape, billing, region,
  outside-CFN/retain management, and the safe scoped-sync + read path are all in place.
