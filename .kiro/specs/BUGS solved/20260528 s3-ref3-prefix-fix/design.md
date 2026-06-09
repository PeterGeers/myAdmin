# S3 Ref3 Prefix Fix — Bugfix Design

## Overview

The `Ref3` field in the `mutaties` table stores a full S3 URI (`s3://bucket/key`) instead of just the tenant-relative S3 key. This prevents the frontend from generating presigned URLs for invoice PDFs linked to banking transactions. The fix removes the `s3://` prefix construction in `output_service.py` and adds a data migration to correct existing records.

## Glossary

- **Bug_Condition (C)**: The condition that triggers the bug — when `_handle_s3_upload` in `output_service.py` uploads to an S3 provider that has a non-empty `bucket` attribute, causing the `url` field to be wrapped as `s3://{bucket}/{reference}` instead of using the plain key
- **Property (P)**: The desired behavior — the `url` field in the storage result must equal the plain S3 key (the `reference` value returned by `provider.upload()`), so that `Ref3` stores a tenant-relative key like `tenant/invoices/general/uuid_file.pdf`
- **Preservation**: Existing behavior that must remain unchanged: Google Drive URL handling, local/test mode storage, the `s3_shared_storage.upload()` return value, and the frontend `handleRef3Click` logic for non-S3 paths
- **`_handle_s3_upload`**: The method in `backend/src/services/output_service.py` (~line 216) that uploads invoice PDFs to S3 and returns a result dict with `url`, `reference`, and `filename` fields
- **`invoice_booking_helper.py`**: The service that reads `storage_result.get('url')` and passes it as `ref3` when creating journal entries in the `mutaties` table
- **`handleRef3Click`**: The frontend function in `BankingProcessor.tsx` that determines how to open a `Ref3` value — S3 keys go through the presigned-url endpoint, Google Drive URLs open directly, others copy to clipboard
- **Presigned-url endpoint**: `GET /api/storage/presigned-url?key=...` in `backend/src/routes/storage.py` that validates the key starts with `{tenant}/` and generates a time-limited download URL

## Bug Details

### Bug Condition

The bug manifests when `output_service.py` uploads an invoice PDF to an S3 shared bucket via `StorageProvider`. The `provider.upload()` method correctly returns a plain S3 key (e.g., `kimgeers/invoices/general/764608e787ea_INV-2026-0001.pdf`), but `_handle_s3_upload` then wraps it as `s3://{bucket}/{reference}`, producing a full URI that downstream consumers cannot use.

**Formal Specification:**

```
FUNCTION isBugCondition(input)
  INPUT: input of type StorageUploadContext
  OUTPUT: boolean

  provider := get_storage_provider(input.administration)
  bucket := getattr(provider, 'bucket', '')

  RETURN bucket != ''
         AND provider.upload() returns plain S3 key
         AND _handle_s3_upload constructs url as f"s3://{bucket}/{reference}"
END FUNCTION
```

### Examples

- **Example 1**: Upload invoice for tenant `kimgeers` → `provider.upload()` returns `kimgeers/invoices/general/764608e787ea_INV-2026-0001.pdf` → `_handle_s3_upload` stores `s3://myadmin-shared-production/kimgeers/invoices/general/764608e787ea_INV-2026-0001.pdf` in Ref3 → Frontend passes this to presigned-url endpoint → Endpoint rejects because key doesn't start with `kimgeers/` (it starts with `s3://`)
- **Example 2**: Upload invoice for tenant `petervdberg` → same pattern → `s3://myadmin-shared-production/petervdberg/invoices/...` stored → `handleRef3Click` sees `s3://` prefix, treats it as a protocol scheme, falls through to clipboard copy instead of fetching presigned URL
- **Example 3**: Upload in test/local mode (no bucket) → `_handle_s3_upload` uses `url = reference` → works correctly (no bug in this path)
- **Edge case**: Existing records already have the `s3://bucket/` prefix in `Ref3` — these need a data migration to strip the prefix

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**

- Google Drive URLs in `Ref3` (starting with `https://drive.goo`) must continue to open directly in a new tab
- Other HTTP/HTTPS URLs in `Ref3` must continue to be copied to clipboard
- Local/test mode storage (no bucket) must continue to store the reference value directly
- The `s3_shared_storage.upload()` method must continue to return the plain S3 key
- The `invoice_service.py` S3 upload path (which already returns `{'url': s3_key}` correctly) must remain unchanged
- Mouse clicks, keyboard navigation, and all other `BankingProcessor.tsx` interactions must remain unchanged

**Scope:**
All inputs that do NOT involve `output_service.py` uploading to an S3 provider with a non-empty bucket should be completely unaffected by this fix. This includes:

- Google Drive uploads via `_handle_gdrive_upload`
- Local/test mode uploads where `bucket` is empty
- Direct S3 key storage via `invoice_service.py`
- All frontend behavior (no frontend changes required)

## Hypothesized Root Cause

Based on the code analysis, the root cause is confirmed (not hypothesized):

1. **Incorrect URL Construction in `output_service.py`** (line ~268): The code `url = f"s3://{bucket}/{reference}"` wraps the plain S3 key with a protocol prefix and bucket name. This was likely added for logging/debugging purposes or by analogy with how S3 URIs are displayed in AWS Console, but it breaks the downstream data flow.

2. **Downstream Assumption Mismatch**: `invoice_booking_helper.py` reads `storage_result.get('url')` and stores it directly as `ref3`. It assumes `url` is a usable reference — either a plain S3 key or an HTTP URL. The `s3://` scheme satisfies neither expectation.

3. **Frontend Logic Bypass**: `handleRef3Click` checks `!ref3.startsWith('http')` to identify S3 keys. A value starting with `s3://` doesn't start with `http`, so it enters the S3 branch — but the presigned-url endpoint then rejects it because the key doesn't start with `{tenant}/`.

4. **No Existing Data Migration**: Records already written with the `s3://bucket/` prefix remain broken until corrected.

## Correctness Properties

Property 1: Bug Condition - Ref3 Stores Plain S3 Key

_For any_ storage upload where the provider has a non-empty bucket (isBugCondition returns true), the fixed `_handle_s3_upload` function SHALL return a result where `url` equals the plain S3 key (the `reference` value), without any `s3://` or bucket prefix.

**Validates: Requirements 2.1, 2.2, 2.3**

Property 2: Preservation - Non-S3-Bucket Paths Unchanged

_For any_ storage upload where the provider does NOT have a non-empty bucket (isBugCondition returns false, e.g., test/local mode), the fixed `_handle_s3_upload` function SHALL produce the same result as the original function, preserving the existing behavior of using `url = reference` directly.

**Validates: Requirements 3.3, 3.4, 3.5**

## Fix Implementation

### Changes Required

**File**: `backend/src/services/output_service.py`

**Function**: `_handle_s3_upload`

**Specific Changes**:

1. **Remove S3 URI construction**: Replace the conditional block:

   ```python
   bucket = getattr(provider, 'bucket', '')
   if bucket:
       url = f"s3://{bucket}/{reference}"
   else:
       url = reference
   ```

   With simply:

   ```python
   url = reference
   ```

   The `reference` value from `provider.upload()` is already the correct tenant-relative S3 key.

2. **Keep logging unchanged**: The `logger.info` call can still log the bucket for debugging, but the `url` field in the return dict must be the plain key.

**File**: New migration script (e.g., `backend/scripts/database/fix_ref3_s3_prefix.py`)

**Specific Changes**: 3. **Data migration**: Strip the `s3://bucket/` prefix from existing `Ref3` values in the `mutaties` table:

```sql
UPDATE mutaties
SET Ref3 = SUBSTRING(Ref3, LENGTH('s3://bucket_name/') + 1)
WHERE Ref3 LIKE 's3://%'
```

The migration must:

- Detect the bucket name dynamically from the `S3_SHARED_BUCKET` environment variable
- Only update rows where `Ref3` starts with `s3://`
- Log the number of affected rows
- Be idempotent (safe to run multiple times)

4. **Add database migration record**: Register the migration in the `database_migrations` table for tracking.

5. **Optional guard in presigned-url endpoint**: As defense-in-depth, the `/api/storage/presigned-url` endpoint could strip a leading `s3://bucket/` prefix if encountered, but this is secondary to fixing the source.

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the bug on unfixed code, then verify the fix works correctly and preserves existing behavior.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix. Confirm the root cause by observing the `s3://` prefix in the return value.

**Test Plan**: Write unit tests that call `_handle_s3_upload` with a mocked S3 provider (one that has a non-empty `bucket` attribute) and assert the returned `url` field. Run on UNFIXED code to observe the `s3://` prefix.

**Test Cases**:

1. **S3 Shared Upload Test**: Mock provider with `bucket='myadmin-shared-production'`, call `_handle_s3_upload` → observe `url` starts with `s3://` (will fail assertion for plain key on unfixed code)
2. **Ref3 Flow Test**: Trace the full flow from `_handle_s3_upload` through `invoice_booking_helper` → observe `Ref3` contains `s3://` prefix (will fail on unfixed code)
3. **Presigned URL Rejection Test**: Pass an `s3://`-prefixed key to the presigned-url endpoint → observe 403 response because tenant prefix check fails (demonstrates the user-facing bug)

**Expected Counterexamples**:

- `_handle_s3_upload` returns `{'url': 's3://myadmin-shared-production/kimgeers/invoices/...'}` instead of `{'url': 'kimgeers/invoices/...'}`
- Presigned-url endpoint returns 403 for keys starting with `s3://`

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed function produces the expected behavior.

**Pseudocode:**

```
FOR ALL input WHERE isBugCondition(input) DO
  result := _handle_s3_upload_fixed(input)
  ASSERT result.url = result.reference
  ASSERT NOT result.url.startswith("s3://")
  ASSERT result.url.startswith(input.administration + "/")
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed function produces the same result as the original function.

**Pseudocode:**

```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT _handle_s3_upload_original(input) = _handle_s3_upload_fixed(input)
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:

- It generates many test cases automatically across the input domain (various filenames, content types, tenant names)
- It catches edge cases that manual unit tests might miss (special characters in filenames, empty content)
- It provides strong guarantees that behavior is unchanged for all non-buggy inputs

**Test Plan**: Observe behavior on UNFIXED code first for non-bucket providers (test/local mode), then write property-based tests capturing that behavior.

**Test Cases**:

1. **Local Mode Preservation**: Verify that when provider has no bucket, `url = reference` continues to work identically before and after fix
2. **Google Drive Path Preservation**: Verify that `_handle_gdrive_upload` is completely unaffected by the fix
3. **Frontend handleRef3Click Preservation**: Verify that Google Drive URLs, HTTP URLs, and plain S3 keys all route correctly (no frontend changes needed, but verify behavior)
4. **invoice_service.py Path Preservation**: Verify the alternative S3 upload path in `invoice_service.py` continues to store plain keys correctly

### Unit Tests

- Test `_handle_s3_upload` with mocked S3 provider (bucket set) returns plain key
- Test `_handle_s3_upload` with mocked provider (no bucket) returns reference unchanged
- Test presigned-url endpoint accepts plain S3 keys starting with `{tenant}/`
- Test presigned-url endpoint rejects keys with `s3://` prefix (defense-in-depth)
- Test data migration script correctly strips prefix from affected rows
- Test data migration is idempotent (running twice produces same result)

### Property-Based Tests

- Generate random tenant names and filenames, verify `_handle_s3_upload` always returns a key starting with `{tenant}/` (never `s3://`)
- Generate random storage results, verify `invoice_booking_helper` stores the exact `url` value as `ref3` without modification
- Generate random `Ref3` values (mix of S3 keys, Google Drive URLs, HTTP URLs), verify `handleRef3Click` routes each correctly

### Integration Tests

- Test full flow: upload invoice PDF → verify `Ref3` in database is plain S3 key → fetch presigned URL → verify 200 response
- Test data migration on a database with mixed `Ref3` values (some with prefix, some without, some Google Drive URLs)
- Test that existing Google Drive `Ref3` values are unaffected by the migration (only `s3://` prefixed values are updated)
