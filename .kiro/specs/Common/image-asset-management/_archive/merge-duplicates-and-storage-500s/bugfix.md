# Bugfix Requirements Document

## Introduction

Two independent endpoints in the tenant-administration / manage-assets area of the Flask/MySQL
backend plane return `500 INTERNAL SERVER ERROR`. Both routes deliberately swallow the real
exception through `routes.error_responses.error_response` (generic client message + `error_id`,
full stack logged server-side), so the client sees only a generic message and the true cause is
not visible in the response. The bug report (`.kiro/specs/myBacklog/findings.md`) captured two
`error_id`s but no server logs are available for them, so each underlying exception must be
established by code inspection and, where useful, by reflecting on the resolved DB schema.

This spec fixes BOTH 500s as two separate, clearly-scoped concerns:

- **Bug 1** — `POST /api/media-assets/merge-duplicates` returns 500
  (route `backend/src/routes/media_asset_routes/admin_maintenance_endpoints.py::merge_duplicates`
  → service `backend/src/services/media_asset/lifecycle.py::merge_duplicates`).
- **Bug 2** — `GET /api/tenant-admin/storage/config` returns 500
  (route `backend/src/routes/tenant_admin_storage.py::get_storage_config`).

Both routes keep their existing error-response convention; Bug 2's route additionally uses
`include_success=False` and that shape must be preserved.

The first diagnostic objective for each bug is to determine what the underlying exception
actually is (the routes hide it). Each bug is expressed below as a distinct bug condition with
its own current / expected / unchanged behavior clauses.

### Shared constraints the fix MUST honor (Flask/MySQL plane steering)

- Caught exceptions continue to flow through `routes.error_responses.error_response`
  (generic client message + `error_id`, full stack logged server-side); never echo `str(e)`.
  Bug 2's route must keep `include_success=False`.
- Routes delegate to the service layer; no business logic is added to routes.
- All DB access goes through `DatabaseManager` / `dialect_helpers` with parameterized `%s`
  queries; tenant isolation via `administration = %s`, where the tenant value flows from
  `@tenant_required` / `get_current_tenant` and is never hardcoded.
- Change-with-tests contract: any behavior change to a route/service MUST update its allocated
  test(s) in the SAME change. Allocated tests to find and update:
  - Bug 1 service `src/services/media_asset/lifecycle.py` →
    `backend/tests/**/test_*media_asset*` / `test_*duplicate*` (e.g.
    `backend/tests/unit/test_media_asset_service.py`,
    `backend/tests/api/test_duplicate_detection_routes.py`,
    `backend/tests/integration/test_duplicate_*`), plus any `*_props.py` property tests.
  - Bug 1 route `src/routes/media_asset_routes/admin_maintenance_endpoints.py` →
    `backend/tests/api/test_media_asset_routes.py` / `test_duplicate_api.py`.
  - Bug 2 route `src/routes/tenant_admin_storage.py` →
    `backend/tests/api/test_tenant_admin_storage.py` (class `TestTenantAdminStorageConfig`),
    and related `backend/tests/unit/test_storage_routes.py` / `test_storage.py`.
  - Committed fixtures/samples the tests read live under `backend/tests/fixtures/`; never point a
    test at a git-ignored scratch file.

## Bug Analysis

This spec covers two independent bugs. To keep the required canonical sections intact, each
section below is split into a **Bug 1 (merge-duplicates)** block and a **Bug 2 (storage/config)**
block. Clause numbering: section 1/2/3 clauses belong to Bug 1, section 4/5/6 clauses belong to
Bug 2.

### Current Behavior (Defect)

#### Bug 1 — POST /api/media-assets/merge-duplicates

When a tenant admin requests a merge of duplicate assets (payload
`{keep_asset_id: "ast_01M5ETNER53YMN4ZPM7KKMZ2FN", duplicate_asset_ids: ["ast_01M5ETN15MM6ZWXWZT37B5543G"]}`),
the service raises an unhandled exception inside `merge_duplicates`; the route catches it and
returns a generic 500 (`{"success": false, "error": "Merge duplicates error", "error_id": "..."}`),
so the real cause is hidden from the client and no merge is performed.

1.1 WHEN a valid merge-duplicates request is submitted (keep asset exists, one or more duplicate
    asset IDs supplied) THEN the service raises an unhandled exception and the route returns
    500 `{"success": false, "error": "Merge duplicates error", "error_id": "<uuid>"}`
1.2 WHEN `merge_duplicates` hits its failing code path THEN the real exception type and message
    are only logged server-side under the `error_id` and are NOT determinable from the response
    (the first diagnostic objective is to identify this underlying exception — candidates to
    investigate: a DB error on `s3_assets` / `s3_asset_references` such as a missing/renamed table
    or column, an S3 delete inside `_delete_raw` that raises rather than returns `False`, or the
    service wiring via `pkg._get_service()`)
1.3 WHEN the exception is raised mid-transaction THEN the partial `self.db.transaction()` work for
    that duplicate is rolled back and no assets are merged or deleted, leaving the duplicate group
    unresolved for the tenant

#### Bug 2 — GET /api/tenant-admin/storage/config

When a Tenant_Admin opens the storage-config function, the handler resolves the tenant via
`get_current_tenant(request)` then runs a `SELECT config_key, config_value, is_secret FROM
tenant_config WHERE administration = %s AND (config_key LIKE '%_folder_id')`. An unhandled
exception is raised; the route catches it and returns 500
`{"error": "Tenant storage request failed", "error_id": "..."}` (note: no `success` key, because
this route uses `error_response(..., include_success=False)`).

4.1 WHEN a Tenant_Admin requests `GET /api/tenant-admin/storage/config` THEN the handler raises an
    unhandled exception and returns 500 `{"error": "Tenant storage request failed",
    "error_id": "<uuid>"}` with no `success` key
4.2 WHEN the handler hits its failing code path THEN the real exception type and message are only
    logged server-side under the `error_id` and are NOT determinable from the response (the first
    diagnostic objective is to identify this underlying exception — candidates to investigate: the
    `tenant_config` table or its `is_secret` column not existing in the resolved DB target —
    note the `tenant_config → parameters` migration, `migrate_tenant_config_to_parameters.py` —
    or `get_current_tenant(request)` resolving to `None`/raising)
4.3 WHEN the `config_key LIKE '%_folder_id'` predicate runs THEN the `_` is interpreted by SQL
    LIKE as a single-character wildcard, so the pattern over-matches (it does not require a literal
    underscore before `folder_id`); this is a correctness smell to confirm and, if it contributes
    to the fault, address as part of the root cause

### Expected Behavior (Correct)

#### Bug 1 — POST /api/media-assets/merge-duplicates

2.1 WHEN a valid merge-duplicates request is submitted (keep asset exists and belongs to the
    tenant, duplicate IDs belong to the tenant) THEN the system SHALL complete the merge:
    re-attach references from each duplicate to the kept asset, delete each duplicate's S3 object
    and DB records, ensure the kept asset is `ACTIVE`, and return 200
    `{"success": true, "kept": "<id>", "merged": <N>, "deleted": <N>}`
2.2 WHEN the underlying failing condition identified in 1.2 is a defect in the merge logic or its
    data access (e.g. a wrong table/column reference, or `_delete_raw` surfacing an error that
    should be tolerated per the delete-tolerance pattern used elsewhere in the service) THEN the
    system SHALL fix that root cause so the merge succeeds for the reproduced input, rather than
    masking it
2.3 WHEN a duplicate asset ID does not exist or belongs to another tenant THEN the system SHALL
    skip that ID (not raise) and continue, consistent with the existing tenant-isolation and
    skip semantics, returning a `success: true` result reflecting what was actually merged
2.4 WHEN the request is genuinely invalid (missing `keep_asset_id`, or `duplicate_asset_ids` is
    absent/not a list) THEN the system SHALL CONTINUE TO return the existing deliberate 400
    validation responses, unchanged
2.5 WHEN an unexpected exception still occurs after the fix THEN the route SHALL CONTINUE TO
    return it via `error_response(e, "Merge duplicates error", status=500)` — generic client
    message + `error_id`, full stack logged server-side, never `str(e)`

#### Bug 2 — GET /api/tenant-admin/storage/config

5.1 WHEN a Tenant_Admin requests `GET /api/tenant-admin/storage/config` and the resolved DB target
    is healthy THEN the system SHALL return 200
    `{"success": true, "tenant": "<tenant>", "config": {<config_key>: <config_value>, ...}}`
    built from the tenant's folder-id configuration rows
5.2 WHEN the underlying failing condition identified in 4.2 is that the storage/folder
    configuration no longer lives in `tenant_config` (or its shape changed) THEN the system SHALL
    read the configuration from the correct, current source via the service/data-access layer so
    the endpoint returns the tenant's folder IDs, rather than querying a table/column that is not
    present in the resolved DB target
5.3 WHEN the `LIKE '%_folder_id'` predicate is confirmed to over-match or mis-target keys THEN the
    system SHALL correct the match so only genuine folder-id keys are returned (e.g. escape the
    literal underscore or match the intended key set precisely)
5.4 WHEN `get_current_tenant(request)` cannot resolve a tenant THEN the system SHALL surface a
    clear, caller-safe outcome consistent with the plane's tenant-isolation rules (no silent
    hardcoded tenant default), rather than an opaque 500
5.5 WHEN an unexpected exception still occurs after the fix THEN the route SHALL CONTINUE TO return
    it via `error_response(e, "Tenant storage request failed", status=500, include_success=False)`
    — generic message + `error_id`, no `success` key, full stack logged server-side, never
    `str(e)`

### Unchanged Behavior (Regression Prevention)

#### Bug 1 — POST /api/media-assets/merge-duplicates

3.1 WHEN the keep asset does not exist for the tenant THEN the system SHALL CONTINUE TO return
    `{"success": false, "error": "Keep asset '<id>' not found"}` with HTTP 400 (the route maps a
    `success: false` service result to 400)
3.2 WHEN a duplicate ID equals the keep asset ID THEN the system SHALL CONTINUE TO skip it without
    deleting the kept asset
3.3 WHEN references already exist on the kept asset THEN the system SHALL CONTINUE TO tolerate the
    `IntegrityError` on re-attach and skip the duplicate reference
3.4 WHEN the caller lacks the `storage_manage` permission or tenant context THEN the system SHALL
    CONTINUE TO enforce `@cognito_required(required_permissions=["storage_manage"])` and
    `@tenant_required()` ahead of any merge logic
3.5 WHEN other media-asset maintenance endpoints (unregistered, import, duplicates list,
    retention) are called THEN the system SHALL CONTINUE TO behave exactly as before — the fix is
    scoped to the merge path

#### Bug 2 — GET /api/tenant-admin/storage/config

6.1 WHEN the caller is unauthenticated or lacks the `Tenant_Admin` role THEN the system SHALL
    CONTINUE TO reject the request via `@cognito_required(required_roles=["Tenant_Admin"])`
    (401/403) before any config lookup
6.2 WHEN the tenant has folder-id configuration present THEN the system SHALL CONTINUE TO return
    the keys as-is (e.g. `google_drive_invoices_folder_id`) mapped to their configured values
6.3 WHEN the tenant has no folder-id configuration THEN the system SHALL CONTINUE TO return 200
    with an empty `config` object (not a 500)
6.4 WHEN the other tenant-admin storage endpoints are called (`/folders`, `PUT /config`, `/test`,
    `/usage`) THEN the system SHALL CONTINUE TO behave exactly as before — the fix is scoped to the
    `GET /config` read path, and all of these keep the `include_success=False` error shape
6.5 WHEN tenant isolation is applied THEN the system SHALL CONTINUE TO scope every query with
    `administration = %s` using the tenant resolved from the authenticated session

## Deriving the Bug Conditions

Two distinct bug conditions, one per bug. `F` is the current (unfixed) handler/service; `F'` is
the fixed version.

### Bug 1 — merge-duplicates

```pascal
FUNCTION isBugCondition_merge(X)
  INPUT: X of type MergeRequest { tenant, keep_asset_id, duplicate_asset_ids }
  OUTPUT: boolean

  // A well-formed merge request for an existing keep asset still 500s today
  // because merge_duplicates raises an unhandled exception on its failing path.
  RETURN X.keep_asset_id is present
     AND X.duplicate_asset_ids is a non-empty list
     AND keep_asset_exists_for_tenant(X.tenant, X.keep_asset_id)
     AND merge_raises_unhandled_exception(X)
END FUNCTION
```

```pascal
// Property: Fix Checking — merge succeeds for the reproduced buggy input
FOR ALL X WHERE isBugCondition_merge(X) DO
  result ← merge_duplicates'(X.tenant, X.keep_asset_id, X.duplicate_asset_ids)
  ASSERT result.success = true
     AND result.kept = X.keep_asset_id
     AND no_unhandled_exception(result)
END FOR
```

```pascal
// Property: Preservation Checking — non-buggy inputs behave identically
FOR ALL X WHERE NOT isBugCondition_merge(X) DO
  ASSERT merge_duplicates(X) = merge_duplicates'(X)
  // e.g. missing keep asset -> 400 "not found"; invalid payload -> 400 validation;
  //      wrong-tenant / self-reference duplicate IDs -> skipped as before.
END FOR
```

### Bug 2 — storage/config

```pascal
FUNCTION isBugCondition_config(X)
  INPUT: X of type ConfigRequest { tenant }
  OUTPUT: boolean

  // An authenticated Tenant_Admin GET /config 500s today because the config
  // read raises (table/column absent in resolved DB target, or tenant unresolved).
  RETURN authenticated_as_tenant_admin(X)
     AND get_storage_config_raises_unhandled_exception(X)
END FUNCTION
```

```pascal
// Property: Fix Checking — config read returns 200 with the folder-id map
FOR ALL X WHERE isBugCondition_config(X) DO
  result ← get_storage_config'(X.tenant)
  ASSERT result.status = 200
     AND result.body.success = true
     AND result.body.config is an object of folder-id keys -> values
     AND no_unhandled_exception(result)
END FOR
```

```pascal
// Property: Preservation Checking — non-buggy inputs behave identically
FOR ALL X WHERE NOT isBugCondition_config(X) DO
  ASSERT get_storage_config(X) = get_storage_config'(X)
  // e.g. unauthenticated / non-Tenant_Admin -> 401/403 as before;
  //      no folder-id config -> 200 with empty config;
  //      any residual unexpected error -> error_response(..., include_success=False).
END FOR
```
