# Design — Members config projection fix + `view_contexts` retirement

## Overview

Two independent workstreams, one spec. **A** hardens the projection write so content, not a
version proxy, decides whether to write (R1). **B** runs the deferred `view_contexts`
retirement (R2). They share no code; A can ship before B. Everything is on the Flask/MySQL +
projection plane. No SAM domain change.

Key existing components (all in `backend/src/services/`):
- `projection_sync.py` — `ProjectionSync` (sole writer). `_conditional_put` → `_stored_version`
  → `_supersedes` → `table.put_item(ConditionExpression=…)`. `sync_administration` builds the
  per-tenant item batch, calls `validate_items`, then puts each item.
- `_projection_config_builders.py` — `build_config_fields_row` / `build_config_scope_row` /
  `build_config_mail_row`; `_config_row_version` derives `version` from param `updated_at`.
- `parameter_service.py` — `ParameterService.get_param` (in-memory `_cache`), `get_param_revision`
  (uncached).

---

## Architecture

Two independent workstreams on the Flask/MySQL + projection plane, no SAM domain change:
- **A — projection write hardening** (`ProjectionSync` in `backend/src/services/projection_sync.py` + the shared `_projection_config_builders.py` seam + `ParameterService`).
- **B — `view_contexts` retirement** (a MySQL migration + removal of the Flask view-context builder + a frontend key-reference removal).
A ships before B so the ad-hoc `died` re-sync can be done. Both flow through the existing on-change trigger (`projection_sync_trigger`) and the sole-writer `ProjectionSync`.

## A. Projection write: content-driven, validate-before-write (R1)

### A1. Root-cause recap (what we are changing and why)

Today `_conditional_put(item)`:
1. reads `stored_version` for the item's key,
2. writes only if `_supersedes(item.version, stored_version)` (strictly greater),
3. puts with a DynamoDB `ConditionExpression` (`#v < :incoming`) as a concurrency backstop.

Failure mode (proven on `test`): the stored row can hold STALE content stamped at the CURRENT
source version. Then step 2 is permanently false (incoming == stored), and the correct content
can never land. Root enabler: the build reads content through `ParameterService.get_param`'s
in-memory cache, which can serialize a stale value while `version` (from the uncached
`get_param_revision`) is fresh — so version and content desync.

### A2. Change 1 — build from a coherent (uncached) source

`ProjectionSync` must not serialize stale content. Options (pick the least invasive that holds):
- **Preferred:** at the start of `sync_administration`, use a `ParameterService` whose members
  cache is empty/invalidated for the tenant being synced (either construct a fresh
  `ParameterService` for the sync run, or call a new `ParameterService.invalidate(tenant=…)` /
  `invalidate_namespace("members", tenant)` before building). The sync already receives its
  source provider; thread a fresh/clean param service through the builders.
- The builders (`build_config_*_row`) are unchanged — they already produce correct content from
  whatever param value they are handed; the fix is to hand them a non-stale value.

Result: a built row's CONTENT always matches its VERSION (both derived from the same current
source read). This alone would prevent NEW desyncs, but it cannot heal an ALREADY-wedged row —
hence A3.

### A3. Change 2 — write decision is content-driven (heals wedged rows, stays idempotent)

Replace "version strictly greater" as the WRITE GATE with a CONTENT comparison, keeping version
only for recording + the datastore concurrency backstop.

New `_conditional_put(item)` logic:
1. Read the stored item (full attributes, not just version) for the key.
2. Compute the CONTENT of incoming vs stored, EXCLUDING the volatile `version`/bookkeeping
   attributes (compare the semantic payload — `attributes` / the `fields`,`overrides`,
   `functional_groups`,`default_page_size` etc. — canonicalized: sorted keys, stable JSON).
   Use a stable content hash or a normalized deep-equal.
3. If stored is absent OR content differs → WRITE (criterion R1.2, R1.8: heals the wedge).
   If content is equal → SKIP (criterion R1.3, R1.6: idempotent, no churn).
4. On write, set `version` to the current source revision (monotonic-ish, for recording +
   ordering), and keep the DynamoDB `ConditionExpression` ONLY as a concurrency guard so two
   racing writers don't interleave — but NO LONGER let an equal/!greater version BLOCK a
   content change. (If the datastore conditional rejects a genuine concurrent advance, treat as
   benign no-op exactly as today.)

Design note on the conditional expression: today it is `#v < :incoming`. Because the write gate
is now content, the datastore guard must not reintroduce the wedge. Either (a) drop the
version condition and rely on last-writer-wins for the rare true race (acceptable: single-process
Flask drains its queue serially — `projection_sync_trigger`), or (b) make the condition a
content/etag guard rather than a strictly-greater-version guard. Prefer (a) for simplicity unless
a concrete concurrency need argues for (b); document the choice in the task.

### A4. Change 3 — validate completeness/syntax before write (R1.4)

`sync_administration` already calls `validate_items(items)` before the put loop (atomic per
tenant). Confirm/extend `validate_items` so a `config#fields` row that is structurally
incomplete or malformed is REJECTED (raises), rather than written or silently skipped. A build
that cannot produce a valid row is a LOUD failure surfaced to the caller (the parameter-admin
save route already folds projection outcome into its response — `_project_tenant_change`), not a
stale-leave. No new silent path.

### A5. Generality (R1.7)

All three changes live in `ProjectionSync` / the shared builder seam, so they apply uniformly to
`config#fields`, `config#scope`, `config#mail`, and any future `config#*`. The `scopegrant#…`
reconcile (delete-obsolete) path is unchanged — it already heals removals; the content gate
complements it for updates.

## Correctness Properties

Property 1: Heal — for any stored row whose content differs from the freshly-built row (including the "equal version, different content" wedge), a sync WRITES the fresh content.
**Validates: Requirements 1.2, 1.8**

Property 2: Idempotent — for any row whose built content equals stored content, a re-sync writes nothing and leaves the row byte-identical.
**Validates: Requirements 1.3, 1.6**

Property 3: Validity — a sync never writes a row that fails `validate_items`; an invalid build raises rather than leaving stale content.
**Validates: Requirements 1.4**

Property 4: Concrete regression — a tenant overlay authoring `membership.status` including `died` projects a `config#fields` whose `overrides["membership.status"]` vocabulary contains `died`, exactly as `gender` values already do.
**Validates: Requirements 1.8**

---

## B. `view_contexts` retirement (R2 — Phase-2 step d)

### B1. Data migration (R2.1)

New migration under `backend/src/migrations/` (mirrors the existing
`migrate_overrides_to_fixed_overrides.py` pattern): `administration`-scoped, dry-run by default
(`--apply` to write), idempotent. Deletes every `scope='tenant'`, `namespace='members'`,
`key='view_contexts'` row from `parameters`. Logs scanned/deleted. Parameterized queries only.
Separately, remove any stored `config#views` projection rows (a small DynamoDB cleanup — query
`sk = config#views` per tenant and delete; or let the removed builder + a reconcile pass drop
them). Document both.

### B2. Flask-plane module removal (R2.3, R2.6)

If present, delete `build_config_views_row` and any view-context domain/validation modules and
their wiring in `projection_sync.py` / `_projection_config_builders.py` so the sync no longer
emits a `config#views` row. Update/remove paired tests (change-with-tests). Verified prerequisite:
SAM already stopped serializing `view_contexts` (step c), so removing the builder breaks no
reader.

### B3. Frontend reference removal (R2.2)

In `frontend/src/services/membersConfigService.ts`: remove `view_contexts` from
`MEMBERS_PARAM_KEYS` and `MEMBERS_PARAM_TO_CONFIG_ID`. Update `membersConfigService.test.ts`
(re-point the generic save-helper test from `view_contexts` to a surviving key such as
`field_overlay` — do not weaken). Confirm no SPA component read path exists (already verified).

### B4. Verification (R2.4, R2.5)

A repo-wide search for `view_contexts` (excluding `.aws-sam/**`, `node_modules`, and
`.kiro/specs`/`.kiro/steering` docs) finds NO reader and NO authoring-key declaration. Confirm
the live column chooser (Session Columns: `getColumnPreferences`/`saveColumnPreferences` over the
field-config field list) and `default_page_size` pagination are untouched.

---

## Components and Interfaces

- `ProjectionSync._conditional_put(item)` — CHANGED: reads the full stored item, compares semantic content (not version), writes on difference/absence, skips on equality.
- `ProjectionSync.sync_administration(administration)` — CHANGED: builds rows from a non-stale `ParameterService`; still calls `validate_items` before the put loop.
- `ParameterService` — CHANGED: a cache-invalidation / uncached-read seam so the sync never serializes a stale value.
- `_projection_config_builders.build_config_*_row` — UNCHANGED output shape; fed a fresh value.
- Migration `backend/src/migrations/retire_members_view_contexts.py` (B) — NEW: deletes the stored `members.view_contexts` rows; dry-run default.
- `build_config_views_row` + view-context modules (B) — DELETED if present.
- `frontend/src/services/membersConfigService.ts` (B) — `view_contexts` removed from `MEMBERS_PARAM_KEYS` / `MEMBERS_PARAM_TO_CONFIG_ID`.

## Data Models

- **`config#*` projection item** — `{tenant_id (PK), sk, version, attributes{…}}`. R1 compares the `attributes` payload (canonicalized), treating `version` as bookkeeping only.
- **Content key for the gate** — a stable hash / normalized deep-equal over the item's semantic payload with `version` and other volatile bookkeeping excluded.
- **`parameters` row (source)** — `{scope, scope_id, namespace, key, value(json), updated_at}`; `members.view_contexts` rows are the delete target in B.

## Error Handling

- A malformed/incomplete built row fails `validate_items` and RAISES before any put — surfaced through the parameter-admin save route's `_project_tenant_change` outcome (saved-but-not-delivered + reason), never a silent stale-leave (R1.4).
- A genuine DynamoDB conditional-check failure (concurrent writer) remains a benign no-op.
- The B migration is dry-run by default; `--apply` required to write; idempotent re-run is safe.

## Testing strategy

- **A (projection):** property-based tests (Hypothesis) for P1–P4 over an in-memory fake
  projection table + fake `ParameterService`, plus a targeted test reproducing the exact wedge
  (stored = 6-value status at version V; source = 7-value at version V; assert the sync writes
  the 7-value content). Reuse the SAM/Flask projection test fakes where they exist. Change-with-
  tests: update any existing `projection_sync` / builder tests that asserted the strict-greater
  gate to the content-gate behaviour (align, never weaken).
- **B (retirement):** migration unit test (dry-run makes no change; `--apply` deletes only the
  targeted rows; idempotent re-run is a no-op); frontend `membersConfigService.test.ts` update;
  a guard test/search asserting no live `view_contexts` reader remains.

## Rollout

1. Land A (behind the normal test gate) — then run the ad-hoc h-dcn re-sync; `died` appears.
2. Land B.
3. Full Test Suite green on `test` → promote `test` → `main`.

Both planes’ suites must pass: `sam/pytest.ini`, `backend` pytest, and the frontend vitest.
