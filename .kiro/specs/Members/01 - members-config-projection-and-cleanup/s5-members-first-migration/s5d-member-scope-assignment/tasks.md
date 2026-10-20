# Implementation Plan

## S5d — Member-user scope assignment (field-value scope, Tenant-Admin managed) — Tasks

- Requirements: `./requirements.md` (R1–R9, decisions D1–D5) · Design: `./design.md`
  (Data Models, Components, Correctness Properties P1–P6, decisions ODx1/ODx2 resolved,
  ODx3 future, ODx4 decided).
- Builds on s5c (Members surface + `scopegrant#…` projection + `resolve_scope_access`). Not in
  production → clean break: remove the `Regio_*` role encoding and the `scope_values` bucket; no
  migration, no dual shape.
- Legend: `[ ]` todo · `[H]` human-run/gated · `(dt)` dev/test-first · each task cites the
  Requirement(s) + design Component/Property it implements.
- **Execution rules (steering):** follow `41-shell-environment.md` (WSL path split; exit code `-1`
  is not failure — judge by the `<<<DONE marker=$?>>>` marker; empty output ≠ finished; no
  long-running foreground processes), `31-backend-database-flask-mysql.md` (parameterized `%s`;
  `administration NOT NULL` + `idx_administration` + FK on every tenant table), `34-backend-testing`,
  `33-frontend-testing`, `35-sam-module-architecture-sam`.
- **Scope of s5d:** builds the **MEMBERS** module slice on a **module-generic** table/API/loop
  (Events/Webshop slot in later with no re-migration).

## Overview

s5d replaces how a member-user's scope is authored, stored, and derived — WITHOUT changing the
SAM module's `scopegrant#…` read contract. It adds a `user_tenant_scope` table (per
user-per-tenant-per-module, JSON values-only), derives the projection from it (removing the
`Regio_*` role encoding), retires the `scope_values` bucket (scope becomes a plain member field),
enforces via canonicalized-equality across multiple dimensions (AND), and gives the Tenant Admin a
per-user scope editor on the existing user-management screen. s5d delivers the MEMBERS slice on a
module-generic foundation.

## Tasks

## Phase 0 — Storage + shared canonicalizer (foundation)

- [x] **0.1 Add the `user_tenant_scope` migration** (`backend/src/migrations/`): table keyed
  `(email, administration, module)` with `scopes JSON NOT NULL`, `created_at/updated_at/created_by`,
  `UNIQUE KEY (email, administration, module)`, `INDEX idx_administration`, `INDEX (administration,
  module)`, `FOREIGN KEY (administration) REFERENCES tenants(administration)`. MySQL 9.x: no
  `IF (NOT) EXISTS` on indexes. _(R1.1; design Data Models; P1)_
- [x] **0.2 Add the shared `scope_canon` canonicalizer** — a pure function `scope_canon(value)`:
  NFKD normalize → strip combining marks (diacritic-fold) → casefold → fold separators
  (space/`-`/`/` → one canonical separator) → trim. Module-plane home
  `sam/members/domain/scope_canon.py`; Flask-plane identical transcription (the two planes share no
  Python path — same pattern as `members_config_validation.py`). NEVER partial/prefix/fuzzy.
  _(R9.6, D5; design Components → scope_canon; P4)_
- [x] **0.3 Cross-plane drift test for `scope_canon`** — a property test asserting the SAM and Flask
  transcriptions produce identical output over a shared vocabulary (guards drift). _(R9.6; P4)_

## Phase 1 — Scope-dimension model (add `field`, drop `multi_valued`, support N dimensions)

- [x] **1.1 Refactor `ScopeDimension`** (`sam/members/domain/scope_dimensions.py`): ADD `field` (the
  member field key the dimension binds to; default = dimension `key`); REMOVE `multi_valued`.
  _(R6.1, R6.3, R3.2; design Data Models → dimension model)_
- [x] **1.2 Update the `scope_dimensions` editor def** (`backend/src/config/members_parameters.json`):
  add the `field` object-field; remove the `multi_valued` boolean. _(R6.3; design)_
- [x] **1.3 Update the projection reader** (`sam/members/repository/projection_config_reader.py`
  `_build_dimension`) + any `ScopeConfig` consumers to carry `field` and drop `multi_valued`.
  _(R6.1; design)_

## Phase 2 — Retire `scope_values`; member value on a normal field (data has NO scope awareness)

- [x] **2.1 Remove `_surface_scope_values` + the `scope_values` read** from
  `sam/members/domain/membership_service.py` (`_enrich_calculated` no longer surfaces scope; the
  bucket is gone). _(R3.4, R8.2, D1; design → scope_values retired; P1)_
- [x] **2.2 Refactor `_record_scope_values(member, dimension_key)`** to read the member's SCALAR value
  from the dimension's NORMAL field, resolved field→bucket via the field config (h-dcn: `overlay.region`
  — a tenant-added field), nested-bucket-first with flat fallback; return `[scope_canon(value)]` or
  `[]`. No `scope_values`. _(R3.1, R3.4, ODx1; design Components → enforcement item 1; P1/P4)_
- [x] **2.3 Store the scope field as a normal field on member write/import** — the importer
  (`scripts/…`/`load_real.py` equivalent) and any member-write path write the CANONICAL value on the
  field (h-dcn `overlay.region`), NOT `scope_values`. Use `scope_canon` for normalization. _(R9.2, D1)_
- [x] **2.4 Normalization verification (R9.5)** — a check/script asserting EVERY distinct member
  scope-field value for the pilot tenant is in the dimension's canonical set (no un-normalized
  values), and surfacing (R9.3) any that are not. _(R9.3, R9.5)_

## Phase 3 — Projection: derive `scopegrant#…` from `user_tenant_scope` (remove role decode)

- [x] **3.1 Carry `user_tenant_scope` in the source** (`projection_sync.py`): `TenantSource` gains
  `user_tenant_scope: Sequence[Mapping]`; `DatabaseSourceProvider.get_tenant_source` adds
  `SELECT email, module, scopes FROM user_tenant_scope WHERE administration = %s`. _(R2.1; design → projection)_
- [x] **3.2 Rewrite `build_scopegrant_rows`** to source from the table (signature
  `(tenant, user_tenant_scope, param_svc)`): filter `module='MEMBERS'`; per (user, dimension) with a
  non-empty grant emit `scopegrant#<email>#<dimension>` = `{dimension, values}` (or `["*"]`); absent/
  empty → no row (deny); validate values against `members.scope_dimensions` (belt-and-suspenders).
  `sync_administration` passes `source.user_tenant_scope`. _(R2.1, R2.3, R2.5; P2/P3)_
- [x] **3.3 REMOVE the role-decode path** — delete `_decode_grant_for_dimension`,
  `_scoped_role_prefix`, `_SCOPED_ROLE_SEPARATORS`, the `Regio_` machinery, and the
  `user_tenant_roles`-sourced grant path. Remove any seeded `Regio_*` rows (dev/test cleanup).
  _(R2.2, R8.1, D1; P1)_
- [x] **3.4 Freshness fix — version bump (ODx4a)** — bump a per-tenant projection version (or
  per-record etag) on governance write so the conditional put SUPERSEDES an existing `scopegrant#…`
  row on UPDATE. _(R2.4, ODx4; P2)_
- [x] **3.5 Freshness fix — diff-and-delete-obsolete (ODx4b)** — the scopegrant builder computes the
  DESIRED set of `scopegrant#<email>#<dimension>` rows for the tenant and DELETES obsolete rows
  (cleared/downgraded grant), so REMOVALS/downgrades propagate regardless of version. _(R2.3, ODx4; P3)_

## Phase 4 — Enforcement: per-dimension map + AND (ODx2)

- [x] **4.1 `allowed_scopes` → per-dimension map** — change `RouteContext.allowed_scopes` from
  `List[str]` to `Dict[str, List[str]]`; the edge `_resolve_scope_access`
  (`sam/members/handler/app.py`) drops the `enabled[0]` shortcut and resolves ALL enabled dimensions
  via the unchanged `resolve_scope_access`, returning `{dimension: values}` (no grant → `[]`).
  _(R3.3, R6.2, ODx2; design → enforcement item 3; P6)_
- [x] **4.2 `_in_scope` iterates the map** — member visible only if it passes EVERY dimension
  (canonicalized intersection; `["*"]` passes, `[]` fails). Drop the single `dimension_key` param;
  update `list_members`/`get_member`/`get_self`/`export`/`_authorize_write` call sites to the map.
  _(R3.1, R3.2, R3.3, R3.5; P4/P6)_

## Phase 5 — Scope authoring API + manual re-sync (Flask/MySQL)

- [x] **5.1 Scope service** (read/write `user_tenant_scope`): get a user's `scopes` for
  `(email, administration, module)`; atomic overwrite; clear→delete row; per-tenant isolation.
  _(R1.1, R1.3, R4.5)_
- [x] **5.2 Authoring routes** (`backend/src/routes/tenant_admin_scope.py`, `@cognito_required(
  ["Tenant_Admin"])`, `@tenant_required()`): `GET /api/tenant-admin/users/<username>/scope/<module>`;
  `PUT …/scope/<module>` (validate each dimension key + value against `<module>.scope_dimensions` via
  `scope_canon`; reject unknown; atomic overwrite; clear→delete→deny; fire `enqueue_sync(tenant)`);
  `GET /api/tenant-admin/scope-dimensions/<module>` (values from the MySQL param DIRECTLY, D4).
  _(R4.2, R4.3, R5.1, R2.4; P2)_
- [x] **5.3 Manual "Re-sync now"** — `POST /api/tenant-admin/projection/resync` (`Tenant_Admin`):
  forced full re-projection of the current tenant (diff-and-replace), returns written/removed counts.
  Convenience/recovery only — auto-on-write stays primary. _(ODx4; design → invocation + freshness)_

## Phase 6 — Frontend scope editor (on the existing user-management screen)

- [x] **6.1 API client + types** (`frontend/src/services/…`, `frontend/src/types/members.ts`):
  `getUserScope(username, module)` / `setUserScope(...)` / `getScopeDimensions(module)`; a
  `ScopeGrant = Record<string, string[]>` + `ScopeDimensionOption` type. _(R4.1, R5.1)_
- [x] **6.2 Scope editor in `UserManagement.tsx`** — for each user holding a Members capability role
  (R4.6), a Scope section: per enabled dimension a MULTI-SELECT of PLAIN values + an **All** toggle
  (→ `["*"]`); save issues `PUT …/scope/<module>` (atomic overwrite; clear removes the grant).
  _(R4.1, R4.3, R4.4, R4.6, D2)_
- [x] **6.3 Fuzzy typeahead in the picker** — diacritic/spacing-tolerant filter over the value list;
  AUTHORING convenience only — selection always yields a canonical value (never changes what is
  stored). _(R5.3, R5.4)_

## Phase 7 — Tests + end-to-end verification

- [x] **7.1 Backend unit** — `user_tenant_scope` service round-trip + per-tenant/per-module isolation;
  `build_scopegrant_rows` from the table (single/multi value, `["*"]`, absent→no row); role-decode
  removed; authoring validation (unknown dimension/value rejected; atomic overwrite; clear→delete→deny;
  `enqueue_sync` fired); freshness (update supersedes; removal deletes the row). _(R7.1; P1/P2/P3)_
- [x] **7.2 SAM domain** — `_record_scope_values` reads the field (not `scope_values`); `_in_scope`
  canonicalized-equality (case/diacritic/separator variants match; partials do NOT); per-dimension map
  AND; `["*"]`; deny; `scope_canon` cross-plane drift test. _(R7.2; P4/P6)_
- [x] **7.3 E2E** — Tenant-Admin sets `member-test@example.com` → `region:["Oost"]` → projection
  `scopegrant#…#region=["Oost"]` → `list_members` returns only Oost → change to `["*"]` returns all →
  clear → returns none (proves add/update/remove propagate — ODx4). _(R7.3; P2/P3)_
- [x] **7.4 Frontend** — scope editor renders per-dimension multi-selects of plain values + All toggle
  + fuzzy filter; save writes the selected set; only member-capable users get the editor. _(R7.4)_

## Task Dependency Graph

Waves group tasks that can proceed in parallel; each wave completes before the next. Phase 0
(table + `scope_canon`) is the foundation everything builds on.

```json
{
  "waves": [
    { "id": 0, "tasks": ["0.1", "0.2", "0.3"] },
    { "id": 1, "tasks": ["1.1", "1.2", "1.3"] },
    { "id": 2, "tasks": ["2.1", "2.2"] },
    { "id": 3, "tasks": ["2.3", "2.4"] },
    { "id": 4, "tasks": ["3.1", "3.2"] },
    { "id": 5, "tasks": ["3.3", "3.4", "3.5"] },
    { "id": 6, "tasks": ["4.1", "4.2"] },
    { "id": 7, "tasks": ["5.1", "5.2"] },
    { "id": 8, "tasks": ["5.3", "6.1"] },
    { "id": 9, "tasks": ["6.2", "6.3"] },
    { "id": 10, "tasks": ["7.1", "7.2", "7.4"] },
    { "id": 11, "tasks": ["7.3"] }
  ]
}
```

## Notes

- **Critical path:** 0.1/0.2 → 3.1→3.2→3.3 (+3.4/3.5) → 4.1→4.2 → 5.1→5.2 → 6.2 → 7.3.
- **Parallelism:** Phase 1 (dimension model) and Phase 2 (retire `scope_values`) are largely
  independent once `scope_canon` (0.2) exists; the frontend (Phase 6) starts once the 5.2 endpoints
  exist; per-phase unit tests (7.1/7.2/7.4) land WITH their phase, and the 7.3 E2E is last.
- **Clean break:** no `Regio_*` compatibility, no `scope_values` dual-read, no migration — dev/test
  `Regio_*` rows are removed as data cleanup (3.3).
- **Freshness (ODx4):** 3.4 (version bump) + 3.5 (diff-delete) together make auto-on-write correct
  for add/update/remove; 5.3 adds the manual re-sync as recovery. This is security-relevant — a
  stale grant lets a user see members they were unscoped from.
- **Module-generic:** the table/API/builder loop are module-parameterized; s5d runs the MEMBERS
  slice. Events/Webshop reuse them by adding their own `<module>.scope_dimensions` (see design ODx3
  for the future multi-module projection-collision question).
