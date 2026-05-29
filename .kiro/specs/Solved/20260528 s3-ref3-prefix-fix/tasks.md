# Tasks: S3 Ref3 Prefix Fix

## Task 1: Write bug condition exploration property test

Write a property-based test that demonstrates the bug exists on unfixed code. The test should call `_handle_s3_upload` with a mocked S3 provider that has a non-empty `bucket` attribute and assert that `result['url'] == result['reference']`. This test is EXPECTED TO FAIL on the current (unfixed) code, confirming the bug.

- [x] Create test file `backend/tests/unit/test_output_service_s3_prefix_bug.py`
- [x] Mock `StorageProvider` with a `bucket` attribute set to a non-empty string
- [x] Mock `provider.upload()` to return a plain S3 key like `tenant/invoices/general/uuid_file.pdf`
- [x] Call `OutputService._handle_s3_upload()` with the mocked provider
- [x] Assert `result['url'] == result['reference']` (plain key, no `s3://` prefix)
- [x] Assert `not result['url'].startswith('s3://')`
- [x] Use `@given` with strategies for tenant name, filename, and bucket name
- [x] Run test and confirm it FAILS (proving the bug exists)

## Task 2: Fix output_service.py — remove s3:// URI construction

Apply the primary backend fix: change `_handle_s3_upload` to use `url = reference` instead of `f"s3://{bucket}/{reference}"`.

- [x] Open `backend/src/services/output_service.py`
- [x] In `_handle_s3_upload`, replace the block:
  ```python
  bucket = getattr(provider, 'bucket', '')
  if bucket:
      url = f"s3://{bucket}/{reference}"
  else:
      url = reference
  ```
  With:
  ```python
  url = reference
  ```
- [x] Keep the existing `logger.info` line that logs the reference
- [x] Run the exploration test from Task 1 and confirm it now PASSES

## Task 3: Add frontend defensive fix for legacy Ref3 values

Add `s3://` prefix stripping in `handleRef3Click` to handle existing database rows that already have the full URI stored.

- [x] Open `frontend/src/components/BankingProcessor.tsx`
- [x] In `handleRef3Click`, add prefix stripping before calling the presigned-url API:
  ```typescript
  const key = ref3.startsWith("s3://")
    ? ref3.replace(/^s3:\/\/[^/]+\//, "")
    : ref3;
  ```
- [x] Use `key` instead of `ref3` in the `authenticatedGet` call
- [x] Verify Google Drive URL path (`startsWith('https://drive.goo')`) is unaffected
- [x] Verify plain S3 keys (no prefix) pass through unchanged

## Task 4: Write preservation property test

Write a property-based test confirming that the fix does not change behavior for non-S3-bucket paths (test/local mode where provider has no bucket).

- [x] Add test to `backend/tests/unit/test_output_service_s3_prefix_bug.py`
- [x] Mock provider WITHOUT a `bucket` attribute (or empty string)
- [x] Call `_handle_s3_upload` and assert `result['url'] == result['reference']`
- [x] Use `@given` with strategies for tenant name and filename
- [x] Run test and confirm it PASSES (preservation holds)

## Task 5: Write frontend unit test for legacy prefix stripping

Write a unit test verifying `handleRef3Click` correctly strips the `s3://bucket/` prefix from legacy Ref3 values and passes the plain key to the API.

- [x] Create or extend test file for BankingProcessor handleRef3Click
- [x] Test case: `s3://myadmin-shared-production/tenant/invoices/file.pdf` → API called with `tenant/invoices/file.pdf`
- [x] Test case: `tenant/invoices/file.pdf` (already correct) → API called with same value
- [x] Test case: `https://drive.google.com/...` → opens in new tab, no API call
- [x] Test case: `https://other-url.com` → copies to clipboard, no API call
