# Parameter Noise — Analysis

## The Problem

The Tenant Admin UI shows parameters that aren't relevant to the tenant's configuration. This creates confusion and cognitive overhead.

## Current State

### What exists in the schema (`parameter_schema.py`)

The schema already has the right building blocks:

- **`module`** field on namespaces (e.g., `'module': 'STR'`, `'module': 'ZZP'`)
- **`visible_when`** rules on individual parameters (e.g., `'visible_when': {'invoice_provider': 'google_drive'}`)
- **`get_schema_for_tenant(tenant_modules)`** function that filters namespaces by active modules

### Where it breaks down

1. **Storage tab vs Advanced Parameters overlap** — The Storage tab provides a polished UI for provider selection, credentials, folder IDs, and logo upload. But the same raw parameters (`invoice_provider`, `s3_shared_bucket`, `google_drive_folder_id`, etc.) also appear in the Advanced Parameters view. Users see the same thing twice.

2. **`visible_when` not enforced in the frontend** — The Advanced Parameters view renders all parameters in a namespace without checking `visible_when` conditions. So `s3_tenant_bucket` shows even when the provider is `s3_shared`, and `company_logo_s3_key` shows even when the provider is `google_drive`.

3. **Duplicate branding across modules** — `company_logo_s3_key` and `company_logo_file_id` exist in both `str_branding` and `zzp_branding`. If a tenant has both STR and ZZP, they see the logo field twice. In practice, most tenants use the same logo for both.

4. **Phantom options** — `s3_tenant` is listed as a provider option but isn't implemented. It creates the impression of a feature that doesn't exist.

5. **Platform-level vs tenant-level confusion** — `s3_shared_bucket` is set by the platform (provisioning service reads `S3_SHARED_BUCKET` env var). A tenant admin shouldn't need to see or edit it — it's not their concern.

## Observed Symptoms

| What the tenant admin sees                       | What they should see                                |
| ------------------------------------------------ | --------------------------------------------------- |
| `s3_shared_bucket` = `myadmin-shared-production` | Nothing — this is platform-managed                  |
| `s3_tenant_bucket` (empty)                       | Nothing — feature doesn't exist yet                 |
| `company_logo_s3_key` in str_branding            | Only if tenant has STR module AND uses S3           |
| `company_logo_s3_key` in zzp_branding            | Only if tenant has ZZP module AND uses S3           |
| `company_logo_file_id` in str_branding           | Only if tenant has STR module AND uses Google Drive |
| Storage provider dropdown in Advanced Parameters | Nothing — Storage tab handles this                  |

## Design Principles

1. **Show only what's actionable** — If the tenant admin can't or shouldn't change it, don't show it
2. **One place for each setting** — If the Storage tab manages storage, the Advanced Parameters tab shouldn't show storage parameters
3. **Context-aware filtering** — Parameters should be filtered by:
   - Active modules (STR, ZZP, FIN)
   - Active storage provider (Google Drive, S3 Shared)
   - Ownership (platform-managed vs tenant-managed)
4. **No phantom features** — Don't show options for unimplemented functionality

## Possible Approaches

### Option A: Hide managed parameters from Advanced view

Add a `'managed_by'` field to parameters that are owned by a dedicated tab:

```python
'invoice_provider': {
    ...
    'managed_by': 'storage_tab',  # Don't show in Advanced Parameters
},
's3_shared_bucket': {
    ...
    'managed_by': 'platform',  # Never show to tenant admins
},
```

The Advanced Parameters view filters out anything with `managed_by` set.

**Pros**: Minimal change, clear ownership model
**Cons**: Doesn't solve the `visible_when` enforcement issue

### Option B: Enforce `visible_when` in the frontend

Make the Advanced Parameters component actually evaluate `visible_when` conditions against current parameter values before rendering.

**Pros**: Uses existing schema metadata, no backend changes
**Cons**: Requires fetching current values to evaluate conditions, more complex frontend logic

### Option C: Backend returns only visible parameters

Change the `/api/tenant-admin/parameters/schema` endpoint to evaluate `visible_when` server-side and return only the parameters that should be visible given the tenant's current configuration.

**Pros**: Single source of truth, frontend stays simple
**Cons**: Backend needs to read current values to filter, slightly more complex API

### Option D: Combine A + C (recommended)

1. Mark platform-managed and tab-managed parameters so they never appear in Advanced
2. Have the backend evaluate `visible_when` and module filtering before returning the schema
3. Remove `s3_tenant` from provider options until it's implemented

This gives the cleanest result with the least frontend complexity.

## Specific Fixes Needed

1. **Remove `s3_tenant` from provider options** — not implemented, creates confusion
2. **Mark `s3_shared_bucket` as platform-managed** — tenant admin can't change it
3. **Mark `storage.*` namespace as managed by Storage tab** — don't show in Advanced
4. **Enforce `visible_when` server-side** — API returns only relevant parameters
5. **Consider merging branding** — single `branding` namespace instead of `str_branding` + `zzp_branding` for shared fields (logo, company name, address). Module-specific fields stay separate.

## Questions to Resolve

- Should branding be unified into one namespace, or keep separate per module? (Some tenants might want different branding per module)
- Should the Advanced Parameters tab exist at all, or should every parameter group have its own dedicated tab/section?
- What's the right UX for a tenant admin who switches storage provider? (e.g., from Google Drive to S3 — do old Google Drive parameters get hidden immediately?)
