# Design Document

## S5d — Member-user scope assignment (field-value scope, Tenant-Admin managed) — Design

- Requirements: `./requirements.md` (R1–R9; decisions D1–D5 settled).
- Builds on: **s5c** (`.kiro/specs/multi-tenant/s5c-members-runnable-in-spa/`) — the Members surface,
  `members.scope_dimensions` config, the `scopegrant#<email>#<dimension>` projection row, and the
  module's `resolve_scope_access` are in place. s5d REPLACES how scope is authored + stored + derived.
- Not in production → **clean break**: no compatibility bridge, no migration; the `Regio_*` role-name
  scope encoding and the `scope_values` bucket are REMOVED (D1, R8).
- Decisions of record: ADR 0004 (verified JWT), 0005 (MySQL SoR + one-directional projection),
  0006 (entitlement-in-token via PreTokenGen reading the projection).
- Steering: `20-platform-architecture`, `21-identity`, `31-backend-database-flask-mysql`,
  `32-frontend-ui`, `33/34` (testing), `35-sam-module-architecture-sam`, `40-spec-workflow`.
- Grounding code (cited throughout):
  - Flask/MySQL: `backend/src/services/projection_sync.py` (`DatabaseSourceProvider`, `TenantSource`,
    `build_scopegrant_rows`, `_decode_grant_for_dimension`/`_scoped_role_prefix` — TO REMOVE),
    `projection_sync_trigger.py` (`enqueue_sync`), `parameter_service.py`,
    `backend/src/routes/tenant_admin_roles.py` + `tenant_admin_users.py` (user-management surface),
    `backend/src/config/members_parameters.json` (`scope_dimensions` editor def),
    `backend/src/migrations/*`.
  - SAM module (READ side, mostly unchanged): `sam/members/domain/scope_access.py`
    (`resolve_scope_access`), `sam/members/repository/projection_config_reader.py`
    (`get_scope_grants`, `get_scope_config`), `sam/members/domain/membership_service.py`
    (`_in_scope`, `_record_scope_values`), `sam/members/domain/scope_dimensions.py`.
  - Frontend: `frontend/src/components/TenantAdmin/UserManagement.tsx`, `frontend/src/types/members.ts`.

## Overview

Scope becomes exactly what the requirements state: **a member FIELD + a VALUE (or values) to filter
on**. A user's visible members are the rows whose value for a scope field is in the user's granted
values (canonicalized-equality; `["*"]` = all; no grant = deny). Scope is authored per-user in a new
governance table, projected to the SAME `scopegrant#…` rows the module already reads, and enforced by
the SAME `resolve_scope_access` seam — only the SOURCE of the grant and the member VALUE change.

Three orthogonal axes are kept cleanly separate (a distinction settled during requirements):
- **Capability** (what actions) — module roles in `user_tenant_roles`, hierarchical
  (`Members_CRUD` ⊃ `Members_Export` ⊃ `Members_Read`), expanded to `members:*` capabilities by
  `ROLE_PERMISSIONS`. UNCHANGED by s5d.
- **Governance** (who administers) — `Tenant_Admin` (no `members:*` capability; it assigns others'
  access). UNCHANGED.
- **Scope** (which members) — the NEW `user_tenant_scope` axis. This is all s5d changes.

## Architecture

### Where each change lands

| Change | Plane | Where |
| --- | --- | --- |
| New `user_tenant_scope` table | Flask/MySQL | migration under `backend/src/migrations/` |
| Scope authoring API (read/set per user) | Flask/MySQL | new route (e.g. `tenant_admin_scope.py`) + service |
| Projection: derive `scopegrant#…` from the table | Flask/MySQL | `projection_sync.py` (`TenantSource`, `DatabaseSourceProvider`, `build_scopegrant_rows`); REMOVE role-decode |
| Remove `Regio_*` role encoding | Flask/MySQL | `projection_sync.py` decode helpers; any `Regio_*` seed rows |
| Scope-dimension model: drop `multi_valued`, support N dimensions | Flask/MySQL config + SAM domain | `members_parameters.json`, `sam/members/domain/scope_dimensions.py` |
| Enforcement: read member FIELD + canonicalized-equality | SAM module domain | `membership_service.py` `_record_scope_values`/`_in_scope`; shared `scope_canon` |
| Retire `scope_values` + `_surface_scope_values` | SAM module domain | `membership_service.py` (+ import writes the field) |
| Tenant-Admin scope editor (per user) | Frontend | `frontend/src/components/TenantAdmin/UserManagement.tsx` (+ API client, types) |
| Multi-dimension enforcement (AND) | SAM module edge/domain | `handler/app.py` scope seam + service |

## Data Models

### New table `user_tenant_scope` (D3, R1.1)

```sql
CREATE TABLE user_tenant_scope (
    id INT AUTO_INCREMENT PRIMARY KEY,
    email          VARCHAR(255) NOT NULL,
    administration VARCHAR(50)  NOT NULL,
    module         VARCHAR(50)  NOT NULL,   -- MEMBERS / EVENTS / WEBSHOP / ...  (module that owns the dimensions)
    scopes         JSON NOT NULL,           -- that module's dimensions: { "<dimension>": ["<value>", ...] | ["*"] }  (VALUES ONLY)
    created_at     DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at     DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    created_by     VARCHAR(255),
    UNIQUE KEY uk_user_tenant_scope (email, administration, module),  -- one record per user-per-tenant-PER-MODULE
    INDEX idx_administration (administration),
    INDEX idx_admin_module (administration, module),
    FOREIGN KEY (administration) REFERENCES tenants(administration)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

- **Grain: per (email, administration, MODULE).** Scope dimensions are a MODULE-OWNED concept —
  `scope_dimensions` is declared as a module-namespaced parameter (`"module": "MEMBERS"` in
  `members_parameters.json`), and roles are already per-module (`Members_*`/`Events_*`). So scope is
  keyed per module, mirroring roles. This is REQUIRED, not cosmetic: the SAME dimension name can
  exist in several modules of ONE tenant with DIFFERENT grants — e.g. h-dcn defines `region` in
  Members, Events AND Webshop, and a user may be scoped to `Oost` in Members, `Oost+Friesland` in
  Events, and `["*"]` in Webshop. A single `(email, administration)` row could not represent that
  (the `region` key would collide); the `module` column disambiguates it.
- **Cross-tenant isolation (unaffected).** Every row is keyed by `administration` (NOT NULL, FK to
  `tenants`, all queries `WHERE administration = %s` — steering 31). A different tenant with
  different modules simply has its own rows for its own modules; a tenant whose modules define NO
  scope dimensions has no rows at all. There is ZERO cross-tenant interference — module scope for
  tenant A never touches tenant B.
- **`scopes` JSON:** that MODULE's dimensions only — keys = dimension keys (`region`, `age_group`,
  …), values = a list of canonical VALUES or the sentinel `["*"]` (all-access). Absent dimension /
  empty list = no grant for that dimension (deny). No labels stored (D3).
- **Independence (R1.3):** never read/written together with `user_tenant_roles`.

> **s5d scope note.** s5d builds the **MEMBERS** slice only (Events/Webshop don't exist yet). The
> table, key, and projection loop are **module-generic** (forward-compatible — a future module needs
> NO re-migration), but the projection builder, authoring API, and UI s5d delivers operate on
> `module = 'MEMBERS'`. Other modules slot in later by defining their own `<module>.scope_dimensions`
> and reusing the same table + builder loop.

### `scope_values` retired (D1, R3.4, R8.2)

**The member data record has ZERO awareness of scope.** A member simply HAS a `region` — a plain
membership attribute, a fact about the member. Whether `region` is USED as a scope dimension is a
TENANT CONFIGURATION decision (`members.scope_dimensions`), made entirely OUTSIDE the data record.
The record must not know or care that some tenant scopes on it — scope is a lens applied to the
data, not a property of it.

Therefore:
- The s5c `scope_values.<dim>` bucket and the `_surface_scope_values` enrichment are REMOVED
  ENTIRELY (deleted, not replaced).
- The scope field is a NORMAL member field in its STORAGE bucket. For h-dcn, `region` is a
  TENANT-ADDED (overlay) field — not a platform fixed field — so it lives in the `overlay` bucket
  like every other tenant-added field (`motor_brand`, `clubblad_pref`, …):
  ```json
  "overlay": { "region": "Noord-Holland", "motor_brand": "...", "clubblad_pref": "..." }
  ```
  (Do NOT confuse STORAGE bucket with FUNCTIONAL group: `region`'s storage bucket is `overlay`
  because it is tenant-added; its FUNCTIONAL/display group is `membership` per the tenant's
  functional-group assignment. The two are orthogonal — R4.9.) No `scope_values` anywhere. The word
  "scope" appears ONLY in the tenant config (`members.scope_dimensions`) and the enforcement path —
  never in the member record. (A platform-fixed field used as a scope dimension by some other tenant
  would live in its own fixed bucket, e.g. `membership.status`; the point is the value lives on its
  NORMAL field, whatever bucket that is — resolved via the field config, not hardcoded.)
- **Single value (scalar), not a list.** A member is single-valued per scope field (R3.2), so the
  field holds a plain scalar (`"region": "Noord-Holland"`), NOT a list. The list shape was an
  artifact of the retired `scope_values` multi-valued design. (The USER GRANT is still multi-value;
  the MEMBER field is a scalar.)
- The importer/member-write stores the CANONICAL value on the field (R9.2).

### Scope-dimension model change (R6.3, R6.1)

`members.scope_dimensions` (MySQL param, authored in Tenant-Admin) is the SOURCE OF TRUTH for which
FIELD each dimension binds to and its canonical `values`. Changes:
- **Add `field`** (the member field key the dimension scopes on; defaults to the dimension `key` for
  back-compat with h-dcn `region`).
- **Remove `multi_valued`** (out of scope, R3.2) from the dimension model + `members_parameters.json`
  editor def + `sam/members/domain/scope_dimensions.ScopeDimension`.
- **Multiple dimensions**: the list already supports N entries; the design removes the module's
  "take the first enabled dimension" shortcut and enforces EVERY required dimension (R6.2/R3.3).

## Components and Interfaces

### Projection: derive scopegrant from `user_tenant_scope` (R2)

`ProjectionSync` is the sole writer; the `scopegrant#<email>#<dimension>` ROW SHAPE is UNCHANGED
(R2.5). Only the source changes.

**The full path to the SAM module (4 hops).** Only hop [2] changes; [3] and [4] are UNCHANGED.

```
[1] MySQL user_tenant_scope
    (email, administration, module='MEMBERS', scopes={"region":["Oost","Friesland"]})
        │  read-only, by ProjectionSync
[2] ProjectionSync.build_scopegrant_rows  (Flask/MySQL plane — SOLE writer)
    filter module='MEMBERS'; per (user, dimension with a grant) → one ProjectionItem:
        tenant_id  = 'h-dcn'
        sort_key   = 'scopegrant#<email>#region'
        attributes = {'dimension':'region', 'values':['Oost','Friesland']}
        │  conditional PutItem
[3] DynamoDB governance_projection  (READ MODEL)
    PK='h-dcn'  SK='scopegrant#<email>#region'  {dimension, values, version}
        │  one Query per tenant partition, at request time
[4] SAM module MembersProjectionReader.get_scope_grants(tenant_id, email)
    → {'region': ['Oost','Friesland']} → resolve_scope_access → allowed_scopes
    → list_members filters members by (canonicalized) field value
```

**The `scopegrant#<email>#<dimension>` row is byte-for-byte identical to today** — so the SAM reader
(`get_scope_grants`), `resolve_scope_access`, and the DynamoDB row shape are ALL UNCHANGED. The ONLY
change is where hop [2] gets `values`: from the `user_tenant_scope.scopes` JSON instead of decoding
role names. The stable `scopegrant#…` row is the interface between the two planes — this is what
makes the clean break cheap (no SAM read-path change, no DynamoDB schema change).

**`module` is a MySQL-side concept only.** The projected row is `scopegrant#<email>#<dimension>` with
NO module segment — the Members module's reader queries only within the Members projection context,
so module is implicit downstream. The `module` column exists on the MySQL table to disambiguate a
user's grants across modules and to route the builder (filter `module='MEMBERS'`); it is NOT carried
into the SAM-facing row for the single-module (Members) case s5d delivers. (See ODx3 for the
multi-module-projection question.)

1. **`TenantSource`** gains `user_tenant_scope: Sequence[Mapping]` (rows `{email, module, scopes}`).
2. **`DatabaseSourceProvider.get_tenant_source`** adds
   `SELECT email, module, scopes FROM user_tenant_scope WHERE administration = %s` and carries the rows.
3. **`build_scopegrant_rows(tenant, user_tenant_scope, parameter_service)`** is rewritten to read the
   table instead of decoding role names. s5d builds the MEMBERS slice:
   - Filter the rows to `module = 'MEMBERS'` (the s5d slice; a future module runs the same loop with
     its own module token + its own `<module>.scope_dimensions`).
   - For each such user row, parse `scopes` JSON; for each dimension with a non-empty grant, emit
     `scopegrant#<email>#<dimension>` with `values` = the granted list, or `["*"]` for all-access.
   - Absent dimension / empty list → emit NO row (deny-by-default, R2.3).
   - Values validated against the dimension's `values` from `members.scope_dimensions`
     (belt-and-suspenders; primary validation is at authoring, R4.2).
   - The projected `scopegrant#<email>#<dimension>` row is UNCHANGED (R2.5). It lives in the
     Members-module projection context already, so module is implicit in the consumer; a future
     module's grants project into ITS own module context — no key collision across modules.
4. **REMOVE** `_decode_grant_for_dimension`, `_scoped_role_prefix`, `_SCOPED_ROLE_SEPARATORS`,
   `WILDCARD_VALUE` role machinery, and the `user_tenant_roles`-sourced grant path (R2.2). The
   `build_scopegrant_rows` signature changes from `(tenant, user_tenant_roles, param_svc)` to
   `(tenant, user_tenant_scope, param_svc)`; `sync_administration` passes `source.user_tenant_scope`.
5. **`enqueue_sync(tenant)`** fires on every scope write (R2.4), same as role writes today.

### Projection invocation + freshness (who triggers the update)

**Who invokes it:**
- **On-change (primary):** the scope authoring endpoint (`PUT .../scope/<module>`) calls
  `enqueue_sync(tenant)` after committing the row — exactly as `tenant_admin_roles.py` does for role
  writes. In the Flask monolith the default `ProjectionSyncTrigger` drains SYNCHRONOUSLY
  (`drain_on_enqueue=True`) → `sync_administration(tenant)` rebuilds that tenant's rows in the same
  request. Best-effort: a failure is logged, never breaks the write.
- **Reconciliation (backstop):** `reconcile()` → idempotent `sync_all()` catches any missed signal.

**FRESHNESS HAZARD (must be handled — known from s5c).** `sync_administration` writes each projection
row under a VERSION-GUARDED conditional put: it writes only when the incoming `version` supersedes
the stored one, and `version` derives from the TENANT row (`_scope_config_version`). A grant-only
change does NOT bump the tenant version, so:
- a NEW `scopegrant#…` row (user had no grant) → new SK → writes fine; but
- an UPDATED grant (Oost → Oost+Friesland) or a REMOVED grant (cleared → deny) → the SK already
  exists and, with an unchanged version, the conditional put SKIPS it → the projection stays STALE.
  (This is the exact issue that forced a manual `config#*` row delete in s5c.)

Since updating and REMOVING grants are core to this feature, s5d MUST fix this rather than inherit
it. Design decision (settle in tasks — ODx4):
- **(a) version bump:** bump a per-tenant projection version (or per-record etag) on any governance
  write so the conditional put always supersedes; AND
- **(b) diff/delete-obsolete:** the scopegrant builder computes the DESIRED set of
  `scopegrant#<email>#<dimension>` rows for the tenant and DELETES obsolete rows (a cleared/downgraded
  grant), not just puts current ones — so removals and downgrades propagate regardless of version.
Recommended: (b) for correctness of removals + (a) so updates aren't skipped. Enforcement's
deny-by-default means a stale-but-present grant is a SECURITY-relevant staleness (a user keeps seeing
members they were unscoped from), so this is not optional polish.

**DECIDED:** auto-on-write (`enqueue_sync`) stays the PRIMARY trigger, fixed at the mechanism level
by (a)+(b) so adds, updates AND removals propagate with no staleness window and no divergence from
role/config writes. In ADDITION, a Tenant-Admin **"Re-sync now"** action
(`POST /api/tenant-admin/projection/resync`) provides a forced full re-projection as a
convenience/recovery path (post-bulk-edit, or retry after a failed background sync). The manual
action is a belt to the auto-trigger's suspenders — never the sole path.

### Enforcement: canonicalized field-value filter (R3, R9, D5)

The module READ path stays the same shape; two changes land in `membership_service.py`:

1. **`_record_scope_values(member, dimension_key)`** SHALL read the member's SCALAR value from the
   dimension's normal field (resolved from `members.scope_dimensions[dim].field`, default = `dim`
   key) in its storage bucket — for h-dcn `member["overlay"]["region"]` (region is a tenant-added
   overlay field) — resolved via the field
   config (nested-bucket-first, flat fallback, reusing the existing accessor). It reads a normal
   field; there is NO `scope_values`. Returns `[canon(value)]` for a present value or `[]` for
   absent (the member is single-valued per field, R3.2). The name may be kept for continuity, but it
   no longer implies a `scope_values` bucket.
2. **`_in_scope`** SHALL compare using a shared **`scope_canon(value)`** canonicalization (trim +
   casefold + diacritic-fold + separator-fold) applied to BOTH the member value and each granted value
   (D5/R9.6), then set-intersect. `["*"]` short-circuits to visible. Empty grant → not visible.
3. **Multiple dimensions (R3.3) — `allowed_scopes` becomes a per-dimension MAP (ODx2 resolved,
   Option A).** Today `_resolve_scope_access` returns a flat `List[str]` for a SINGLE dimension
   (`dimension = enabled[0]` shortcut) and `RouteContext.allowed_scopes` is that list. Change:
   - **Edge (`handler/app.py` `_resolve_scope_access`):** drop the `enabled[0]` shortcut; LOOP over
     ALL enabled dimensions, resolving each independently via the unchanged per-dimension
     `resolve_scope_access`, and return `Dict[str, List[str]]` — e.g.
     `{ "region": ["Oost"], "age_group": ["U15"] }`. A dimension with no grant maps to `[]` (deny
     for that dimension).
   - **`RouteContext.allowed_scopes`** type changes `List[str]` → `Dict[str, List[str]]`.
   - **`_in_scope`** drops the single `dimension_key` param and iterates the map: for EACH dimension
     the member's canonicalized field value must intersect that dimension's allowed values; `["*"]`
     passes that dimension, `[]` fails it. The member is visible only if it passes EVERY dimension
     (AND — R3.3). `_record_scope_values` is called once per dimension (reads each dimension's field).
   - **Single-dimension tenants (h-dcn today)** are the N=1 case — a one-entry map — so their
     behavior is unchanged; there is NO special-casing of one vs many dimensions.
   - `get_scope_grants` is UNCHANGED (already returns `{dimension: values}`); the edge now consumes
     ALL its keys instead of one.
   - **Scope of the change:** the `allowed_scopes` TYPE change ripples through the edge, the service
     read methods (`list_members`/`get_member`/`get_self`/`export`/`_authorize_write`), and every test
     that builds a `RouteContext` or calls `_in_scope` with a flat list. Mechanical but broad — a
     dedicated task (clean-break license makes it acceptable; no dual shape).

#### Shared canonicalization `scope_canon` (R9.6)

A single pure function is the ONE canonicalizer used everywhere a scope value is compared or stored:
- **Steps:** `unicodedata.normalize("NFKD")` → strip combining marks (diacritic-fold) → casefold →
  collapse/fold separators (space/`-`/`/` → a single canonical separator) → trim.
- **Used by:** enforcement compare (`_in_scope`), authoring validation (R4.2), the importer/member-write
  normalization (R9.2), and the R9.5 verification check — so all sites agree byte-for-byte.
- **Placement:** module-plane domain util (e.g. `sam/members/domain/scope_canon.py`); the Flask-plane
  importer uses an identical transcription (the two planes don't share a Python path — same pattern as
  `members_config_validation.py` transcribing the field-key set). A property test asserts the two
  implementations agree on a shared vocabulary (guards drift).
- **NEVER partial/prefix/fuzzy** — exact-equality on the canonicalized form (R3.5).

### API — scope authoring (R4)

New Tenant-Admin endpoints (mirroring `tenant_admin_roles.py` conventions: `@cognito_required(
required_roles=["Tenant_Admin"])`, tenant from `@tenant_required()`/verified context, `enqueue_sync`
on write):

The endpoints are MODULE-scoped (the `module` path/param segment; s5d serves `MEMBERS`):

- **`GET /api/tenant-admin/users/<username>/scope/<module>`** — return the user's current `scopes`
  JSON for the current tenant + module (empty object if none). s5d serves `module = members`.
- **`PUT /api/tenant-admin/users/<username>/scope/<module>`** — atomic overwrite (R4.5) of the
  `(email, administration, module)` row. Body: `{ "scopes": { "<dimension>": ["<value>", ...] |
  ["*"] } }`. Validates each dimension key exists in the tenant's `<module>.scope_dimensions` and
  each value is in that dimension's canonical `values` (via `scope_canon` compare); rejects unknown
  dimension/value (R4.2). Clearing all → deletes the row (deny). Fires `enqueue_sync(tenant)`.
- **`GET /api/tenant-admin/scope-dimensions/<module>`** (or reuse the module-parameters read) —
  return the enabled scope dimensions + their canonical values for the current tenant + module,
  sourced from the MySQL `<module>.scope_dimensions` param DIRECTLY (D4/R5.1), for the picker. s5d:
  `members.scope_dimensions`.
- **`POST /api/tenant-admin/projection/resync`** — an OPTIONAL manual "Re-sync now" action
  (`Tenant_Admin`). Forces a full re-projection of the CURRENT tenant via the trigger's
  reconcile/forced path (a guaranteed diff-and-replace, ODx4), returning a small summary
  (written/removed counts). This is a CONVENIENCE + RECOVERY surface — NOT the primary trigger:
  auto-on-write (`enqueue_sync`) remains the default so the projection is never silently stale. Use
  it after a bulk edit, or to retry if a best-effort background sync failed.

All are tenant-scoped (Property 1) and write only the current verified tenant's rows. The `module`
path segment keeps the API forward-compatible for Events/Webshop without a new route shape.

### Frontend — scope editor on the user-management screen (R4, D2)

Extend `frontend/src/components/TenantAdmin/UserManagement.tsx` (the existing screen where roles are
managed). For each user who holds a Members capability role (R4.6):
- A **Scope** section listing each enabled scope dimension (from `GET .../scope-dimensions`).
- Per dimension: a **multi-select** of the dimension's PLAIN values (label where available, value
  otherwise — never `Regio_`), plus an **All** toggle (→ `["*"]`).
- **Fuzzy typeahead** over the value list (diacritic/spacing-tolerant) as an authoring convenience only
  (R5.4) — selecting always yields a canonical value; fuzzy never changes what is stored.
- **Save** issues `PUT .../scope` with the selected set (atomic overwrite); clearing all removes the grant.
- Types in `frontend/src/types/members.ts`: a `ScopeGrant = Record<string, string[]>` shape and a
  `ScopeDimensionOption` for the picker.

## Testing Strategy

- **Backend unit** (`backend/tests/unit/`): `user_tenant_scope` service round-trip + per-tenant
  isolation; `build_scopegrant_rows` from the table (single/multi value, `["*"]`, absent→no row);
  role-decode removal (the removed helpers no longer exist / are not called); authoring API validation
  (unknown dimension/value rejected; atomic overwrite; clear→delete→deny; `enqueue_sync` fired).
- **SAM domain** (`sam/tests/`): `_record_scope_values` reads the field (not `scope_values`);
  `_in_scope` canonicalized-equality (case/diacritic/separator variants match; partials do NOT);
  multi-dimension AND; `["*"]`; deny; `scope_canon` property test (cross-plane agreement).
- **E2E (R7.3):** Tenant-Admin sets `member-test@example.com` → `region:["Oost"]` → projection
  `scopegrant#…#region=["Oost"]` → `list_members` returns only Oost → `["*"]` returns all → clear → none.
- **Frontend** (`frontend/src/__tests__/`): scope editor renders per-dimension multi-selects of plain
  values + All toggle + fuzzy filter; save writes the selected set.
- **Normalization (R9.5):** a check that every distinct member scope-field value is in the dimension's
  canonical set (no un-normalized values) for the pilot tenant.

## Correctness Properties

### Property 1: Single source of truth

**Validates: Requirements 1, 8.2**

 A user's scope for a tenant exists in exactly ONE place —
  `user_tenant_scope` — and a member's scope value in exactly ONE place — its scope field. No
  `scope_values` bucket, no `Regio_*` role encoding. (R1, D1)
### Property 2: One-directional projection

**Validates: Requirements 2.4, 2.5**

 The module NEVER reads MySQL; scope flows MySQL `user_tenant_scope`
  → `ProjectionSync` (sole writer) → `scopegrant#…` → module. A scope write always `enqueue_sync`s.
  (ADR 0005, R2.4)
### Property 3: Deny-by-default

**Validates: Requirements 1.5, 2.3**

 Absence of a grant for a required dimension = deny (no row projected →
  no scope → see nothing). Never allow-all on absence. (R1.5, R2.3)
### Property 4: Canonical exactness

**Validates: Requirements 3.5, 9.6**

 Enforcement is exact-equality on `scope_canon(value)` applied
  identically to member value and grant value — never partial/prefix/fuzzy. The SAME function is
  used to normalize on write, so stored member values and grants share one vocabulary. (R3.5, R9)
### Property 5: Axis independence

**Validates: Requirements 1.2, 1.3**

 Capability (roles), governance (Tenant_Admin), and scope
  (`user_tenant_scope`) are independent; changing one never mutates another. (R1.3)
### Property 6: Multi-dimension AND

**Validates: Requirements 3.3, 6.2**

 A member is visible only if it passes EVERY required dimension;
  each dimension is evaluated independently against its own grant. (R3.3, R6.2)

## Error Handling

- **Unknown dimension/value at authoring** → 400, reject the whole PUT (atomic; nothing written).
  The picker only offers canonical values, so this guards API/direct callers. (R4.2)
- **Malformed `scopes` JSON in the table** (defensive) → the projection builder skips the
  malformed user row (logs), never raises — a bad row cannot break the tenant's whole sync (mirrors
  the existing builders' empty-is-valid tolerance).
- **Absent scope record** → no `scopegrant#…` rows for that user → deny-by-default (not an error).
- **Un-normalizable member value (R9.3)** → surfaced by the R9.5 verification check / import report,
  never silently kept as a non-matching variant.
- **`enqueue_sync` failure** → best-effort/logged; the scope write still succeeds; reconciliation
  backstops (same contract as role writes today).

## REUSE / ADD / REFACTOR / REMOVE

| Component | Verdict | s5d action |
| --- | --- | --- |
| `sam/members/domain/scope_access.py` (`resolve_scope_access`) | KEEP | unchanged (grant shape unchanged) |
| `projection_config_reader.get_scope_grants` | KEEP | unchanged (reads the same `scopegrant#…` rows) |
| `membership_service._record_scope_values` | REFACTOR | read the dimension's FIELD (not `scope_values`) + canon |
| `membership_service._in_scope` | REFACTOR | canonicalized-equality via `scope_canon` |
| `membership_service._surface_scope_values` + `scope_values` | REMOVE | retired (D1) |
| `scope_dimensions.ScopeDimension` | REFACTOR | add `field`; remove `multi_valued` |
| `projection_sync.build_scopegrant_rows` | REFACTOR | source from `user_tenant_scope` |
| `projection_sync` role-decode (`_decode_grant_for_dimension`/`_scoped_role_prefix`) | REMOVE | delete (R2.2) |
| `projection_sync.TenantSource` / `DatabaseSourceProvider` | ADD | carry `user_tenant_scope` rows |
| `user_tenant_scope` table | ADD | new migration |
| scope authoring route + service | ADD | `tenant_admin_scope.py` + service |
| `scope_canon` shared canonicalizer | ADD | domain util + Flask transcription + drift test |
| `members_parameters.json` scope_dimensions def | REFACTOR | add `field`; remove `multi_valued` |
| `frontend/.../TenantAdmin/UserManagement.tsx` | REFACTOR | add per-user scope editor |
| `user_tenant_roles` semantics | KEEP | unchanged (capabilities only; `Regio_*` no longer used) |

## Open design items

- **ODx1 (RESOLVED)** The scope field is a NORMAL member field in its STORAGE bucket, a SCALAR
  value; the member record has NO scope awareness and NO `scope_values` bucket. For h-dcn `region`
  is a TENANT-ADDED (overlay) field → stored at `overlay.region` (storage bucket `overlay`;
  functional/display group `membership` — orthogonal). Enforcement resolves field→bucket via the
  field config (never hardcoded) and reads it nested-bucket-first with a flat fallback (the existing
  `valueFor` accessor semantics), so a fixed-field scope dimension in another tenant works too.
- **ODx2 (RESOLVED — Option A)** `allowed_scopes` becomes a per-dimension map
  `Dict[str, List[str]]`; the edge resolves ALL enabled dimensions (drops the `enabled[0]` shortcut)
  and `_in_scope` requires the member to pass EVERY dimension (AND). Single-dimension tenants are the
  N=1 case (one-entry map), unchanged. See the enforcement section item 3.
- **ODx3 (future, not s5d)** When Events/Webshop ALSO project a scope dimension of the same name
  (e.g. `region`) for the same tenant, their `scopegrant#<email>#<dimension>` rows would collide IF
  they share one projection partition/namespace. Resolve when a second module lands: either each
  module projects into its OWN projection namespace/table (keeping `scopegrant#…#<dimension>`
  unambiguous per module), or the projected row gains a module segment
  (`scopegrant#<email>#<module>#<dimension>`). s5d (Members only) does NOT hit this; the MySQL
  `module` column already keeps the SOURCE unambiguous. Flagged so the single-module row shape is a
  conscious choice, not an accidental corner.
- **ODx4 (DECIDED — implement in s5d)** Projection freshness for grant UPDATE/REMOVAL. The
  version-guarded conditional put would skip a changed/cleared `scopegrant#…` row (security-relevant
  staleness). RESOLUTION: implement BOTH (a) a version/etag bump on governance write so updates
  supersede, and (b) a diff-and-delete-obsolete step in the scopegrant builder so removals/downgrades
  propagate. Auto-on-write stays PRIMARY; a Tenant-Admin "Re-sync now" action
  (`POST /api/tenant-admin/projection/resync`) is added as an optional forced-reproject
  convenience/recovery path (not the sole trigger).
