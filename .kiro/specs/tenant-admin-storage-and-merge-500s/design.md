# tenant-admin-storage-and-merge-500s Bugfix Design

## Overview

Two independent endpoints on the Flask/MySQL plane return `500 INTERNAL SERVER ERROR`, and both
deliberately hide the real exception behind `routes.error_responses.error_response` (generic
client message + correlation `error_id`, full stack logged server-side, never `str(e)`). No
server logs are available for the captured `error_id`s, so the first diagnostic objective for
each bug is to establish the true underlying exception by code + schema inspection.

This design keeps the two bugs as **separate, independently-scoped concerns** and fixes each at
its root cause while honoring the plane's hard constraints:

- **Bug 1** — `POST /api/media-assets/merge-duplicates` → 500 `"Merge duplicates error"`
  (route `admin_maintenance_endpoints.py::merge_duplicates` → service
  `services/media_asset/lifecycle.py::merge_duplicates`, helper `helpers.py::_delete_raw`).
- **Bug 2** — `GET /api/tenant-admin/storage/config` → 500 `"Tenant storage request failed"`
  with `include_success=False`
  (route `tenant_admin_storage.py::get_storage_config`).

The strategy is: identify the hidden exception for each, apply the **minimal** correct fix
(Bug 2's config read must stop depending on a table that may no longer exist in the resolved DB
target; Bug 1's merge must stop assuming an S3 delete always succeeds and must fix the
transaction-ordering flaw), and — because `merge_duplicates` currently has **zero** test
coverage — add reproduce-the-bug and preservation tests under the change-with-tests contract.

The error-response convention is unchanged in both routes; Bug 2 keeps `include_success=False`.

## Glossary

- **Bug_Condition (C)**: The condition that triggers the bug. Two distinct conditions:
  `isBugCondition_merge(X)` (Bug 1) and `isBugCondition_config(X)` (Bug 2).
- **Property (P)**: The desired behavior for inputs where C holds — the endpoint succeeds (200)
  for a valid request instead of masking a 500.
- **Preservation**: Existing behavior that must remain unchanged by the fix — validation 400s,
  auth 401/403, tenant isolation, the `error_response` shape (including `include_success=False`
  for Bug 2), and the behavior of every sibling endpoint not named in the bug.
- **`merge_duplicates`**: Service method in `services/media_asset/lifecycle.py` (LifecycleMixin)
  that re-attaches references from each duplicate asset to the kept asset, deletes each
  duplicate's S3 object and DB rows, and ensures the kept asset is `ACTIVE`.
- **`_delete_raw`**: Helper in `services/media_asset/helpers.py` that performs the raw S3
  `delete_object` and **returns `True`/`False`** (it swallows `ClientError`/`Exception` and
  returns `False` — it does not raise).
- **`get_storage_config`**: Route handler in `tenant_admin_storage.py` that reads the tenant's
  folder-id configuration and returns it as a `{config_key: config_value}` map.
- **`tenant_config`**: Legacy MySQL table (`administration, config_key, config_value, is_secret`)
  holding tenant settings. Being superseded by the `parameters` table via
  `migrate_tenant_config_to_parameters.py` (a **copy**, not a rename/drop).
- **`parameters`**: The current key-value configuration store
  (`scope, scope_id, namespace, key, value, value_type, is_secret`), read through
  `ParameterService` with scope chain `user → role → tenant → system`.
- **`administration`**: The tenant key on this plane; always flows from
  `@tenant_required`/`get_current_tenant`, never hardcoded.

---

# Bug 1 — POST /api/media-assets/merge-duplicates

## Bug Details

### Bug Condition

The bug manifests when a tenant admin submits a well-formed merge request — `keep_asset_id`
present and existing for the tenant, `duplicate_asset_ids` a non-empty list — yet
`merge_duplicates` raises an **unhandled** exception on its failing code path. The route catches
it and returns 500 `{"success": false, "error": "Merge duplicates error", "error_id": "<uuid>"}`,
so no merge happens and the real cause is hidden.

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input of type MergeRequest { tenant, keep_asset_id, duplicate_asset_ids }
  OUTPUT: boolean

  RETURN input.keep_asset_id is present
     AND input.duplicate_asset_ids is a non-empty list
     AND keep_asset_exists_for_tenant(input.tenant, input.keep_asset_id)
     AND merge_duplicates(input) raises an unhandled exception
END FUNCTION
```

### Examples

- `merge_duplicates(tenant, keep="ast_01M5ETNER53YMN4ZPM7KKMZ2FN", dups=["ast_01M5ETN15MM6ZWXWZT37B5543G"])`
  where both assets exist for the tenant → **expected** 200
  `{"success": true, "kept": "<keep>", "merged": N, "deleted": 1}`; **actual** 500
  `"Merge duplicates error"`.
- A duplicate whose S3 object is already gone (prior partial delete, lifecycle expiry, or an S3
  permission issue): `_delete_raw` returns `False`, the code **ignores the return value** and
  proceeds to delete the DB row — so an S3 failure does not itself raise here, but the merge
  silently deletes the registry row while the S3 object may linger (a correctness smell, not the
  500 by itself).
- A duplicate with a reference whose `(asset_id, entity_type, entity_id)` already exists on the
  kept asset: the re-attach `INSERT` violates `UNIQUE INDEX idx_asset_entity`; this is caught as
  `IntegrityError` and skipped — **not** the bug.
- Edge: `duplicate_asset_ids` contains only the `keep_asset_id` or only wrong-tenant/non-existent
  IDs → every iteration is skipped; expected `{"success": true, "merged": 0, "deleted": 0}`.

### Root-Cause Analysis

Because the route hides the exception, the true cause was established by inspection of the merge
code path, the two tables it touches, and the helper it calls.

**Evidence gathered:**

1. **Service wiring is sound** — `pkg._get_service()` resolves through
   `routes.service_accessors.make_db_service_accessor(lambda db: MediaAssetService(db, ParameterService(db)))`,
   building a fresh `DatabaseManager` per call. This is **not** the fault (hypothesis refuted).

2. **Schema is present and matches the queries** — `20260811120000_create_s3_assets.json`
   creates `s3_assets` (columns incl. `status`, `orphaned_at`, `updated_at ON UPDATE
   CURRENT_TIMESTAMP`, `content_hash`) and `s3_asset_references`
   (`administration, asset_id, entity_type, entity_id, created_at`, with
   `UNIQUE INDEX idx_asset_entity (asset_id, entity_type, entity_id)` and
   `CONSTRAINT fk_asset_ref_asset FOREIGN KEY (asset_id) REFERENCES s3_assets(id) ON DELETE
   CASCADE`). The merge's column references all match — a missing/renamed table/column is
   **unlikely** (lower-probability branch, kept in view below).

3. **`_delete_raw` cannot raise** — it catches `ClientError` and `Exception` and returns a
   boolean. So an S3 failure inside the merge does **not** surface as an unhandled exception; it
   returns `False` and is currently **ignored** by `merge_duplicates`. This diverges from
   `delete_asset`/`force_delete`, which both treat `if not deleted: return {"success": False,
   "error": "S3 deletion failed"}`.

4. **The re-attach `IntegrityError` is caught** — `from db_exceptions import IntegrityError` is
   imported and the duplicate-reference case is handled, so a benign unique-constraint collision
   is not the raise.

5. **The transaction ordering is the real defect.** Inside the per-duplicate
   `with self.db.transaction()` block the code does, in order: (a) re-insert each of the
   duplicate's references pointing at `keep_asset_id`; (b) `DELETE ... FROM s3_asset_references
   WHERE asset_id = dup_id`; (c) `_delete_raw`; (d) `DELETE FROM s3_assets WHERE id = dup_id`.
   The `s3_asset_references.fk_asset_ref_asset` FK is `ON DELETE CASCADE` **from `s3_assets`** —
   but step (a) inserts rows keyed on `keep_asset_id` (which is **not** being deleted), so the
   cascade on step (d) only removes the duplicate's own rows. The latent fault is that any
   **reference whose insert raised a non-`IntegrityError` DatabaseError** (e.g. a deadlock /
   lock-wait timeout under `transaction()`, or a value that violates a different constraint)
   propagates out of the `except IntegrityError` (which only catches the unique collision),
   aborts the `transaction()` (rollback + re-raise), and bubbles to the route as the 500.

**Most probable root cause (primary):** `merge_duplicates` has **two coupled defects** on the
failing path:
   - **(P1) It ignores `_delete_raw`'s return value.** Unlike `delete_asset`/`force_delete`, it
     does not check `deleted`. The correct, minimal behavior per 2.2 is the *delete-tolerance*
     pattern the service uses elsewhere: a failed S3 delete must not abort the whole merge — it
     should be logged and tolerated (the registry row is still removed and the reference re-home
     is what matters for the user), OR, if parity with `delete_asset` is preferred, surface a
     caller-safe `success:false`. We adopt **tolerate-and-log** (consistent with "merge should
     succeed for the reproduced input", 2.1/2.2) so a stale/again-missing S3 object does not 500
     the whole group.
   - **(P2) The re-attach only tolerates `IntegrityError`.** Any other `DatabaseError` raised
     mid-loop escapes the `except IntegrityError`, rolls the transaction back, and 500s. The fix
     scopes the re-attach to tolerate the *expected* duplicate-key case precisely and lets the
     merge make forward progress, while still letting genuinely unexpected exceptions flow to
     `error_response` (2.5).

**Remaining uncertainty & safety under either branch:** Without the server log we cannot be 100%
certain whether the captured 500 came from (P2) a non-`IntegrityError` DB error on re-attach, or
from a lower-probability missing/renamed column on one of the two tables (branch 2 above). The
fix is **safe under either branch**:
   - If the cause was the S3 return-value / re-attach handling, the corrected tolerance makes the
     reproduced merge succeed.
   - If the cause were instead a genuine schema mismatch, the fix does **not** mask it — the
     residual, genuinely-unexpected exception still flows through `error_response(e, "Merge
     duplicates error", status=500)` (2.5) with full server-side logging, so the next occurrence
     is diagnosable. We add no silent `except: pass`.

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors (Bug 1):**
- Missing/absent `keep_asset_id` or non-list `duplicate_asset_ids` → the route's deliberate 400
  validation responses, unchanged (3.? / 2.4).
- Keep asset not found for the tenant → service returns `{"success": false, "error": "Keep asset
  '<id>' not found"}`, which the route maps to **HTTP 400** (3.1).
- A duplicate ID equal to the keep asset ID → skipped; the kept asset is never deleted (3.2).
- A reference that already exists on the kept asset → `IntegrityError` tolerated, that reference
  skipped (3.3).
- Non-existent / wrong-tenant duplicate IDs → skipped, not raised (2.3).
- `@cognito_required(required_permissions=["storage_manage"])` + `@tenant_required()` enforced
  ahead of any merge logic (3.4).
- Every other maintenance endpoint (`/unregistered`, `/delete-unregistered`, `/import`,
  `/duplicates`, `/retention-settings`) behaves exactly as before (3.5).
- All DB access stays parameterized `%s` through `DatabaseManager`/`transaction()` with
  `administration = %s` isolation; no hardcoded tenant.

**Scope:** All inputs that do NOT satisfy `isBugCondition_merge` are completely unaffected.

## Hypothesized Root Cause

Summarized from the analysis above:

1. **Ignored S3 delete result (P1, primary)**: `merge_duplicates` discards `_delete_raw`'s
   boolean, unlike the sibling delete methods. A failed/again-missing S3 object is silently
   dropped; the intended delete-tolerance behavior is not applied.
2. **Over-narrow exception tolerance on re-attach (P2, primary)**: only `IntegrityError` is
   caught; any other `DatabaseError` mid-loop aborts the `transaction()` and 500s.
3. **Schema mismatch on `s3_assets` / `s3_asset_references` (secondary, lower probability)**: a
   missing/renamed column would also 500. Considered less likely because the create-migration
   matches the queries; the fix stays safe here by not masking a residual exception.
4. **Service wiring via `pkg._get_service()` (refuted)**: the accessor is correct.

## Correctness Properties

Property 1: Bug Condition - Merge succeeds for a valid duplicate group

_For any_ input where the bug condition holds (isBugCondition returns true) — a valid
merge request whose keep asset exists for the tenant and whose duplicate list is non-empty — the
fixed `merge_duplicates` SHALL complete the merge: re-attach references from each tenant-owned
duplicate to the kept asset (tolerating an already-present reference), tolerate a failed/again-
missing S3 delete without aborting, delete each duplicate's DB rows, ensure the kept asset is
`ACTIVE`, and return `{"success": true, "kept": "<keep>", "merged": N, "deleted": M}` (route 200)
— instead of raising and 500ing.

**Validates: Requirements 2.1, 2.2, 2.3**

Property 2: Preservation - Non-buggy merge inputs behave identically

_For any_ input where the bug condition does NOT hold (isBugCondition returns false), the fixed
function SHALL produce the same result as the original, preserving: keep-asset-not-found →
`success:false`/400; invalid payload → deliberate 400; self-referential or wrong-tenant/non-
existent duplicate IDs → skipped; already-present reference → `IntegrityError` tolerated; and any
genuinely unexpected exception → `error_response(e, "Merge duplicates error", status=500)`.

**Validates: Requirements 2.4, 2.5, 3.1, 3.2, 3.3, 3.4, 3.5**

## Fix Implementation

### Changes Required

**File**: `backend/src/services/media_asset/lifecycle.py`
**Function**: `LifecycleMixin.merge_duplicates`

1. **Apply delete-tolerance to the S3 delete (P1)**: capture `deleted = self._delete_raw(bucket,
   s3_key)` and, when `False`, log a warning via `_maslog()` (key: tenant + dup_id + s3_key) and
   **continue** removing the DB row — the merge still succeeds. This mirrors the service's
   existing "best-effort cleanup" style while keeping the registry authoritative. (Do not copy
   `delete_asset`'s hard `return {"success": False}` — that method's contract differs; merge must
   make forward progress per 2.2.)
2. **Tighten re-attach tolerance precisely (P2)**: keep `except IntegrityError` for the
   duplicate-key collision (3.3). Do **not** broaden it to a bare `except` — genuinely unexpected
   `DatabaseError`s must still propagate so 2.5 holds. If analysis of the live log later confirms
   a specific tolerable DB error, scope the catch to that exact exception only; otherwise the
   narrowed behavior is already correct and the residual error is surfaced safely.
3. **No change to tenant isolation or parameterization** — every statement already uses `%s` and
   `administration = %s`; preserve exactly.
4. **No route change required for the happy path** — the route already maps `success:true` → 200,
   `success:false` → 400, and wraps the residual in `error_response(..., "Merge duplicates
   error", status=500)`.

> The minimal, behavior-correct change is (1) + the deliberate scoping decision in (2). This makes
> the reproduced merge succeed and stops the silent S3-result drop, without masking a schema
> defect should that be the real (secondary) cause.

## Testing Strategy

### Validation Approach

Two phases: first reproduce the 500/silent-drop on the **unfixed** `merge_duplicates`, then verify
the fix succeeds for the buggy input and preserves every non-buggy path. `merge_duplicates`
currently has **NO test anywhere** (grep for `merge_duplicates`/`merge-duplicates` across
`backend/tests` returns nothing), so Bug 1 requires **adding** coverage, not just updating it.

### Exploratory Bug Condition Checking

**Goal**: Surface the counterexample on unfixed code and confirm the root cause.

**Test Plan**: Drive `MediaAssetService.merge_duplicates` with a `mock_db` whose
`transaction()` yields a mock cursor (the established `mock_db.transaction.return_value.__enter__
= MagicMock(return_value=(cursor, conn))` pattern from `test_media_asset_service.py`), and patch
`_delete_raw`. Run against unfixed code to observe the failure.

**Test Cases** (unfixed):
1. **Re-attach raises non-IntegrityError** — cursor's re-attach `INSERT` raises a
   `DatabaseError` (not `IntegrityError`); unfixed code lets it propagate out of
   `merge_duplicates` (will fail: raises instead of returning).
2. **S3 delete fails** — `_delete_raw` returns `False`; unfixed code ignores it and still deletes
   the DB row with no warning (will fail the intended tolerate-and-log assertion).

**Expected Counterexamples**: an unhandled `DatabaseError` escaping the service (case 1) and a
dropped S3-failure signal (case 2).

### Fix Checking

**Goal**: For all inputs where the bug condition holds, the fixed function returns the success
result.

**Pseudocode:**
```
FOR ALL input WHERE isBugCondition(input) DO
  result := merge_duplicates_fixed(input.tenant, input.keep_asset_id, input.duplicate_asset_ids)
  ASSERT result["success"] = true
     AND result["kept"] = input.keep_asset_id
     AND no unhandled exception
END FOR
```

### Preservation Checking

**Goal**: For all inputs where the bug condition does NOT hold, fixed = original.

**Pseudocode:**
```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT merge_duplicates_original(input) = merge_duplicates_fixed(input)
END FOR
```

**Testing Approach**: Property-based testing fits preservation — generate random (tenant,
keep_asset_id, duplicate_asset_ids) shapes incl. self-references, wrong-tenant IDs, empty lists,
and already-present references, asserting skip/409-tolerance semantics are unchanged. Unit tests
cover the enumerated cases.

**Test Cases** (preservation):
1. Keep asset not found → `{"success": false, "error": "Keep asset '<id>' not found"}` (service),
   mapped to 400 by the route.
2. Duplicate ID == keep ID → skipped, kept asset not deleted.
3. Already-present reference on kept asset → `IntegrityError` tolerated, that ref skipped, merge
   still `success:true`.
4. Wrong-tenant / non-existent duplicate IDs → skipped; `{"success": true, "merged": 0,
   "deleted": 0}`.

### Unit Tests

Add to `backend/tests/unit/test_media_asset_service.py` (new `TestMergeDuplicates` class; uses the
module `mock_db` + autouse env/boto3 fixtures):
- `test_merge_duplicates_valid_group_returns_success_and_counts`
- `test_merge_duplicates_s3_delete_fails_tolerated_and_logged_still_succeeds`
- `test_merge_duplicates_reattach_integrityerror_skipped_merge_succeeds`
- `test_merge_duplicates_reattach_unexpected_dberror_propagates` (reproduce-the-bug)
- `test_merge_duplicates_keep_asset_not_found_returns_error`
- `test_merge_duplicates_self_reference_skipped`
- `test_merge_duplicates_wrong_tenant_duplicate_skipped`
- Tenant-isolation assertion: every executed statement carries `administration = %s` with the
  tenant value.

### Property-Based Tests

Add `backend/tests/unit/test_media_asset_merge_props.py` (`*_props.py` naming): generate random
duplicate-group inputs and assert (a) fix-checking — valid groups return `success:true`; (b)
preservation — skip semantics for self/wrong-tenant IDs are invariant.

### Integration / API Tests

Add to `backend/tests/api/test_media_asset_routes.py` (route-level, patching
`routes.media_asset_routes._get_service`):
- `test_merge_duplicates_success_returns_200`
- `test_merge_duplicates_missing_keep_asset_id_returns_400`
- `test_merge_duplicates_missing_duplicate_ids_returns_400`
- `test_merge_duplicates_service_not_found_returns_400`
- `test_merge_duplicates_unexpected_exception_returns_500_generic_with_error_id`
  (asserts body is `{"success": false, "error": "Merge duplicates error", "error_id": <uuid>}`
  and that `str(e)` is NOT present). If a `test_duplicate_api.py` / `test_duplicate_detection_routes.py`
  already owns the `/duplicates` list route, co-locate the merge API tests consistently; commit any
  fixtures under `backend/tests/fixtures/`.

---

# Bug 2 — GET /api/tenant-admin/storage/config

## Bug Details

### Bug Condition

The bug manifests when an authenticated Tenant_Admin requests `GET
/api/tenant-admin/storage/config`. The handler resolves `tenant = get_current_tenant(request)`
then runs a raw `SELECT config_key, config_value, is_secret FROM tenant_config WHERE
administration = %s AND (config_key LIKE '%_folder_id')`. An unhandled exception is raised; the
route returns 500 `{"error": "Tenant storage request failed", "error_id": "<uuid>"}` with **no**
`success` key (because this route uses `error_response(..., include_success=False)`).

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input of type ConfigRequest { tenant }
  OUTPUT: boolean

  RETURN authenticated_as_tenant_admin(input)
     AND get_storage_config(input) raises an unhandled exception
END FUNCTION
```

### Examples

- Tenant_Admin GETs `/config` when `tenant_config` has been dropped/absent in the resolved DB
  target after `migrate_tenant_config_to_parameters.py` → the `SELECT` raises a table-missing
  `DatabaseError` → **actual** 500 `{"error": "Tenant storage request failed", "error_id":
  "..."}`; **expected** 200 `{"success": true, "tenant": "<t>", "config": {<folder_id keys>}}`.
- Tenant_Admin GETs `/config` and the `is_secret` column was dropped during the migration while
  the table lingers → the `SELECT`'s `is_secret` reference raises an unknown-column error →
  same 500.
- `LIKE '%_folder_id'` over-matches: the `_` is a single-char SQL-LIKE wildcard, so the pattern
  matches any key ending in `<any-char>folder_id` (e.g. `xfolder_id`), not only keys with a
  literal `_folder_id` suffix — a latent correctness smell independent of the 500.
- Edge: tenant has no folder-id config → **expected** 200 with an empty `config` object (6.3),
  never a 500.

### Root-Cause Analysis

The route hides the exception, so the cause was established by inspecting the migration, the
source(s) of truth for storage config, and the query.

**Evidence gathered:**

1. **The storage config moved from `tenant_config` to `parameters`.**
   `backend/src/migrations/migrate_tenant_config_to_parameters.py` (and the SQL twin
   `backend/sql/migrate_tenant_config_to_parameters.sql`) copy every `tenant_config` row into
   `parameters`, mapping `google_drive_*` and `storage_*` keys into the `storage` namespace at
   tenant scope. The repository's **own service-layer accessor already treats `parameters` as
   primary**: `auth/tenant_context.get_tenant_config()` reads via `ParameterService.get_param`
   first and only **falls back** to `tenant_config` "during migration". So the canonical read
   path is `parameters` via `ParameterService`, and `get_storage_config` is the **one** read that
   still hits `tenant_config` directly and unguarded.

2. **`get_storage_config` is the outlier.** The `PUT /config` and `/usage` handlers in the same
   file also touch `tenant_config`, but the bug report scopes Bug 2 to the `GET /config` read
   path (6.4 keeps the siblings unchanged). `get_storage_config` issues a raw
   `DatabaseManager().execute_query` — it does **not** delegate to the service layer, violating
   the "routes delegate to the service layer" rule and coupling the read to a table that may no
   longer exist.

3. **`tenant_config` existence in the resolved DB target is unconfirmed from the live DB.** A
   direct schema probe against the local Docker target failed on credentials (`Access denied for
   user 'root'`), so we could not positively confirm/deny the table at design time. The migration
   **copies** rather than drops, so `tenant_config` *may* still exist in some targets — but the
   production (Railway) target is exactly where the migration SQL is documented to run, and a
   dropped table or a dropped `is_secret` column there is the most consistent explanation for an
   authenticated Tenant_Admin hitting a 500 on a plain read.

4. **The `LIKE '%_folder_id'` predicate over-matches** (4.3). `_` is a LIKE wildcard; the
   intended meaning is "ends with the literal `_folder_id`". This is a real correctness smell but
   is **not** the cause of the 500 (a bad `LIKE` returns wrong/extra rows, it does not raise).

**Most probable root cause (primary):** `get_storage_config` reads a **stale source of truth** —
it queries `tenant_config` (and its `is_secret` column) directly, but storage/folder config now
lives in the `parameters` table (`storage` namespace). In the resolved production DB target, the
direct `SELECT` against the superseded table/column raises a `DatabaseError`, which the route
masks as a 500.

**Remaining uncertainty & safety under either branch:** We could not confirm from the live DB
whether the exact failure is (a) table missing, (b) `is_secret` column missing, or (c)
`get_current_tenant` returning `None`/raising. The fix is **safe under all three**:
   - **(a)/(b)** are removed by reading from the current source via the service layer
     (`ParameterService` / `get_tenant_config`-style access), so the handler no longer depends on
     `tenant_config` or its `is_secret` column at all.
   - **(c)** is addressed by validating the resolved tenant: if `get_current_tenant` yields a
     falsy tenant, surface a clear, caller-safe outcome consistent with tenant-isolation rules
     (no silent hardcoded default) rather than letting a `None` tenant produce an opaque 500
     (5.4). No hardcoded `administration` is ever introduced.
   - Any residual unexpected error still flows through `error_response(e, "Tenant storage request
     failed", status=500, include_success=False)` (5.5), so nothing is masked.

### Why fix the `LIKE '%_folder_id'` over-match here (4.3 / 5.3)

Fixing the wildcard **is** part of the correct fix, because moving the read to `parameters`
changes *how* we enumerate folder-id keys. Two acceptable, precise options:
   - Enumerate the `storage` namespace for the tenant via `ParameterService.get_params_by_namespace("storage", tenant)`
     and select keys whose name ends with the literal suffix `_folder_id` (a precise Python
     `str.endswith("_folder_id")` filter — no SQL LIKE at all), **or**
   - If any residual SQL LIKE is retained, escape the underscore: `LIKE '%\\_folder_id' ESCAPE
     '\\'` so only a literal `_folder_id` suffix matches.
The namespace-enumeration option is preferred: it is the service-layer read, it eliminates the
wildcard entirely, and it returns exactly the genuine folder-id keys (5.3). The handler keeps
returning keys **as-is** (e.g. `google_drive_invoices_folder_id`) to preserve 6.2.

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors (Bug 2):**
- Unauthenticated / non-`Tenant_Admin` → rejected by `@cognito_required(required_roles=["Tenant_Admin"])`
  (401/403) before any config lookup (6.1).
- Tenant with folder-id config → keys returned **as-is** mapped to their values (6.2).
- Tenant with no folder-id config → 200 with empty `config` object, never 500 (6.3).
- Sibling endpoints `/folders`, `PUT /config`, `/test`, `/usage` behave exactly as before, all
  keeping the `include_success=False` error shape (6.4). **This fix is scoped to `GET /config`.**
- Every query scoped with `administration = %s` using the session-resolved tenant (6.5); no
  hardcoded tenant.
- The 500 fallback keeps shape `{"error": <generic>, "error_id": <uuid>}` with **no** `success`
  key (`include_success=False`) and never echoes `str(e)` (5.5).

**Scope:** All inputs that do NOT satisfy `isBugCondition_config` are completely unaffected —
auth rejections, empty-config reads, and the sibling endpoints.

## Hypothesized Root Cause

1. **Stale source of truth (primary)**: `get_storage_config` reads `tenant_config` (+ `is_secret`)
   directly; config now lives in `parameters` (`storage` namespace) per the migration. In the
   production target the superseded table/column makes the raw `SELECT` raise.
2. **`LIKE '%_folder_id'` over-match (contributing correctness defect)**: `_` is a LIKE wildcard,
   so the predicate does not require a literal underscore; corrected as part of moving to the
   service-layer read.
3. **`get_current_tenant` resolving to `None`/raising (lower probability)**: handled by explicit
   tenant validation with a caller-safe outcome and no hardcoded default.

## Correctness Properties

Property 3: Bug Condition - Storage config read returns 200 with the folder-id map

_For any_ input where the bug condition holds (isBugCondition returns true) — an authenticated
Tenant_Admin request to `GET /config` against a healthy resolved DB target — the fixed handler
SHALL read the tenant's folder-id configuration from the current source via the service layer and
return 200 `{"success": true, "tenant": "<tenant>", "config": {<folder_id keys>: <values>}}`,
with keys returned as-is and only genuine `_folder_id`-suffixed keys included, instead of raising
and 500ing.

**Validates: Requirements 5.1, 5.2, 5.3**

Property 4: Preservation - Non-buggy storage/config inputs behave identically

_For any_ input where the bug condition does NOT hold (isBugCondition returns false), the fixed
function SHALL produce the same result as the original, preserving: unauthenticated/non-
Tenant_Admin → 401/403; a tenant with no folder-id config → 200 with empty `config`; keys
returned as-is; and any residual unexpected error → `error_response(e, "Tenant storage request
failed", status=500, include_success=False)` (bare `{"error", "error_id"}`, no `success`, never
`str(e)`).

**Validates: Requirements 5.4, 5.5, 6.1, 6.2, 6.3, 6.4, 6.5**

## Fix Implementation

### Changes Required

**File**: `backend/src/routes/tenant_admin_storage.py`
**Function**: `get_storage_config`

1. **Read from the current source via the service layer, not `tenant_config` directly.** Replace
   the raw `SELECT ... FROM tenant_config` with a service-layer read of the tenant's `storage`
   namespace — e.g. `ParameterService(db).get_params_by_namespace("storage", tenant)` (or a thin
   tenant-settings/service method wrapping it) — and build the `{config_key: config_value}` map
   from the returned params, keeping keys **as-is** (6.2). This removes all dependency on the
   `tenant_config` table and its `is_secret` column (fixes root cause (a)/(b)).
2. **Enumerate folder-id keys precisely (5.3 / 4.3).** From the namespace params, include only
   keys ending in the literal suffix `_folder_id` via `str.endswith("_folder_id")` — eliminating
   the `LIKE '%_folder_id'` wildcard over-match entirely. (If a SQL LIKE is retained anywhere,
   escape it: `LIKE '%\\_folder_id' ESCAPE '\\'`.)
3. **Validate the resolved tenant (5.4).** If `get_current_tenant(request)` returns a falsy value,
   return a clear, caller-safe response consistent with the plane's tenant-isolation rules (no
   silent hardcoded default) rather than letting a `None` tenant produce an opaque 500. Keep the
   `include_success=False` shape for any error path.
4. **Keep tenant isolation + parameterization.** The service-layer read is tenant-scoped
   (`scope='tenant', scope_id=tenant`, parameterized); no hardcoded `administration` (6.5).
5. **Preserve the error convention (5.5).** The `except Exception` path is unchanged:
   `error_response(e, "Tenant storage request failed", status=500, include_success=False)`.
6. **Do not touch the siblings.** `/folders`, `PUT /config`, `/test`, `/usage` are explicitly out
   of scope (6.4) and remain as-is in this change.

> Note: this introduces a small service-layer read in place of an inline query, satisfying "routes
> delegate to the service layer." Prefer reusing an existing accessor (`get_tenant_config`
> pattern / a `TenantSettingsService`-style method) over adding new direct SQL.

## Testing Strategy

### Validation Approach

Two phases: reproduce the 500 on the **unfixed** `get_storage_config` when the `tenant_config`
read fails, then verify the fixed handler returns 200 from `parameters` and preserves every
non-buggy path (auth, empty config, residual-error shape).

### Exploratory Bug Condition Checking

**Goal**: Surface the counterexample on unfixed code and confirm the stale-source cause.

**Test Plan**: In `backend/tests/api/test_tenant_admin_storage.py` (class
`TestTenantAdminStorageConfig`), patch `routes.tenant_admin_storage.DatabaseManager` so
`execute_query` raises a `DatabaseError` simulating "table/column missing", with
`get_current_tenant` patched to a test tenant. Run against unfixed code.

**Test Cases** (unfixed):
1. **`tenant_config` SELECT raises** — `execute_query` raises `DatabaseError`; unfixed handler
   returns 500 `{"error": "Tenant storage request failed", "error_id": ...}` (reproduces the
   bug; the existing `test_get_config_returns_data` passes only because it mocks the table as
   present — it does not cover the migrated-away target).

**Expected Counterexample**: an authenticated Tenant_Admin receiving a 500 on a plain read.

### Fix Checking

**Goal**: For all inputs where the bug condition holds, the fixed handler returns 200 + folder-id
map.

**Pseudocode:**
```
FOR ALL input WHERE isBugCondition(input) DO
  result := get_storage_config_fixed(input.tenant)
  ASSERT result.status = 200
     AND result.body["success"] = true
     AND result.body["config"] is a {folder_id_key: value} map
     AND no unhandled exception
END FOR
```

### Preservation Checking

**Goal**: For all inputs where the bug condition does NOT hold, fixed = original.

**Pseudocode:**
```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT get_storage_config_original(input) = get_storage_config_fixed(input)
END FOR
```

**Testing Approach**: Property-based testing fits the key-filtering preservation — generate random
mixes of `storage`-namespace keys (folder-id and non-folder-id, incl. tricky `xfolder_id` vs
`x_folder_id`) and assert only literal `_folder_id`-suffixed keys appear, with values returned
as-is. Unit/API tests cover auth, empty-config, and the error shape.

**Test Cases** (preservation):
1. Tenant with folder-id params → 200, keys as-is mapped to values (6.2).
2. Tenant with no folder-id params → 200 with empty `config` (6.3), not a 500.
3. `LIKE` over-match guard → a key like `xfolder_id` (no literal underscore) is **excluded**,
   while `google_drive_invoices_folder_id` is included (5.3 / 4.3).
4. Unauthenticated / non-Tenant_Admin → 401/403 (6.1) — existing
   `test_get_storage_config_unauthenticated_returns_401_or_403` must still pass.
5. Residual unexpected error → 500 with bare `{"error", "error_id"}`, **no** `success` key, no
   `str(e)` (5.5).

### Unit Tests

Add/adjust in `backend/tests/unit/test_storage_routes.py` (and `test_storage.py` if it owns the
config read) — the service-layer read logic (namespace → folder-id filter → map):
- `test_storage_config_reads_from_parameters_namespace`
- `test_storage_config_filters_only_literal_folder_id_suffix`
- `test_storage_config_empty_namespace_returns_empty_map`

### Property-Based Tests

Add a `*_props.py` (e.g. `test_storage_config_key_filter_props.py`): generate random key sets and
assert the folder-id filter includes exactly the literal-`_folder_id` keys (no wildcard
over-match), values preserved.

### Integration / API Tests

Update `backend/tests/api/test_tenant_admin_storage.py`, class `TestTenantAdminStorageConfig`:
- **Update** `test_get_config_returns_data` to mock the **new** source (`parameters` via
  `ParameterService` / the service read) instead of `DatabaseManager.execute_query` on
  `tenant_config`, asserting the same 200 + keys-as-is contract (change-with-tests: the old
  assertion against a `tenant_config` mock must not be left asserting the removed behavior).
- **Add** `test_get_config_source_unavailable_returns_500_generic` (reproduce-the-bug → should
  pass after fix only if the new source also errors; asserts bare `{"error", "error_id"}`, no
  `success`, no `str(e)`).
- **Add** `test_get_config_empty_returns_200_empty_config` (6.3).
- **Add** `test_get_config_excludes_wildcard_overmatch_key` (5.3).
- Keep `test_get_storage_config_unauthenticated_returns_401_or_403` unchanged (6.1).
- Commit any fixtures under `backend/tests/fixtures/`; never point a test at a git-ignored scratch
  file.

---

## Cross-Bug Notes

- The two fixes are independent and must land as two clearly-scoped diffs; neither touches the
  other's files beyond their named routes/services.
- Both keep the `error_response` convention; Bug 2 keeps `include_success=False`.
- Both keep `administration = %s` tenant isolation with the session-resolved tenant and no
  hardcoded tenant; all DB access stays parameterized through `DatabaseManager`/service layer.
- Change-with-tests contract applies to both: `merge_duplicates` needs **new** coverage (none
  exists today); `get_storage_config`'s allocated test must be **updated** to the new source in
  the same change. Run the paired tests before considering each change done:
  `python -m pytest backend/tests/unit/test_media_asset_service.py backend/tests/api/test_media_asset_routes.py backend/tests/api/test_tenant_admin_storage.py backend/tests/unit/test_storage_routes.py -q`.
